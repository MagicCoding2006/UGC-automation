import csv
import hmac
import io
import json
import os
import secrets
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, ValidationError
from . import accounting, analytics, config, db
from .providers import probe
from .registry import list_models
from .schemas import Automation, Batch, Creator, Metric, Product, Review
from .service import make_batch, quote
from .creative import draft_hooks, draft_creator


@asynccontextmanager
async def lifespan(app):
    db.initialize()
    yield


app = FastAPI(title='UGC Studio', version='1.0.0', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)
LOGIN_ATTEMPTS = {}


@app.middleware('http')
async def access(request: Request, call_next):
    path = request.url.path
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if origin and urlparse(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Cross-origin writes are disabled'}, status_code=403)
    if not config.TOKEN:
        # Prevent accidental unauthenticated LAN deployment and DNS rebinding.
        if request.url.hostname not in ('localhost', '127.0.0.1', '::1', 'testserver'):
            return JSONResponse({'detail': 'Set UGC_TOKEN before remote access'}, status_code=403)
    if path.startswith(('/api/', '/media/')) and path not in ('/api/health', '/api/session') and config.TOKEN:
        token = request.headers.get('authorization', '').removeprefix('Bearer ') or request.cookies.get('ugc_session', '')
        if not hmac.compare_digest(token.encode(), config.TOKEN.encode()):
            return JSONResponse({'detail': 'Sign in with your workspace token'}, status_code=401)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store' if path.startswith('/api/') else 'private, max-age=60'
    return response


@app.exception_handler(ValueError)
async def bad_input(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


class Login(BaseModel):
    token: str


@app.post('/api/session')
def login(body: Login, request: Request, response: Response):
    address = request.client.host if request.client else 'unknown'
    now = time.time()
    attempts = [t for t in LOGIN_ATTEMPTS.get(address, []) if now-t < 60]
    if len(attempts) >= 10:
        raise HTTPException(429, 'Too many attempts; wait one minute')
    if config.TOKEN and not hmac.compare_digest(body.token.encode(), config.TOKEN.encode()):
        LOGIN_ATTEMPTS[address] = attempts + [now]
        raise HTTPException(401, 'Incorrect workspace token')
    response.set_cookie('ugc_session', config.TOKEN, httponly=True, samesite='strict', secure=config.SECURE_COOKIE, max_age=86400*7)
    return {'ok': True}


@app.delete('/api/session')
def logout(response: Response):
    response.delete_cookie('ugc_session')
    return {'ok': True}


@app.get('/api/health')
def health():
    return {'ok': True, 'service': 'ugc-studio'}


def require(table, id):
    # Table names are internal constants, never request input.
    row = db.one(f'SELECT * FROM {table} WHERE id=?', (id,))
    if not row:
        raise HTTPException(404, 'Not found')
    return row


@app.get('/api/state')
def state():
    counts = db.rows('SELECT status,COUNT(*) count FROM jobs GROUP BY status')
    batches = db.rows('SELECT b.*, (SELECT COUNT(*) FROM jobs WHERE batch_id=b.id) count, (SELECT COUNT(*) FROM jobs WHERE batch_id=b.id AND status=\'approved\') approved, (SELECT COALESCE(SUM(amount),0) FROM spend WHERE batch_id=b.id AND state!=\'released\') cost FROM batches b ORDER BY created DESC LIMIT 100')
    return dict(products=db.rows('SELECT * FROM products ORDER BY created DESC'),
        creators=db.rows('SELECT * FROM creators ORDER BY created'),
        assets=db.rows('SELECT * FROM assets ORDER BY created DESC LIMIT 500'),
        batches=batches, jobs=db.rows('SELECT * FROM jobs ORDER BY created DESC LIMIT 100'),
        counts={r['status']:r['count'] for r in counts}, models=list_models(), costs=accounting.summary(),
        workers=db.rows('SELECT * FROM heartbeats WHERE updated>?', (time.time()-35,)),
        automations=db.rows('SELECT * FROM automations ORDER BY created DESC'),
        mode=config.MODE, daily_budget=config.DAILY_BUDGET, auto_approve=config.AUTO_APPROVE,
        production_approved=db.one("SELECT COUNT(*) n FROM jobs WHERE status='approved' AND json_extract(spec,'$.model')!='demo'")['n'],
        timezone=os.getenv('UGC_TIMEZONE', 'America/Indiana/Indianapolis'),
        config=dict(fal=bool(os.getenv('FAL_KEY')), tts=os.getenv('UGC_TTS_PROVIDER','fal'),
            script=os.getenv('UGC_SCRIPT_PROVIDER','template'), resolution=config.RESOLUTION),
        analytics=analytics.report())


@app.post('/api/products', status_code=201)
def create_product(body: Product):
    id = db.uid('prod_')
    db.execute('INSERT INTO products VALUES(?,?,?)', (id, body.model_dump_json(), time.time()))
    return require('products', id)


class HookDraft(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    claims: list[str] = Field(min_length=1,max_length=20)


@app.post('/api/creative/hooks')
def create_hook_drafts(body: HookDraft):
    if any(len(c)>250 or not c.strip() for c in body.claims):
        raise ValueError('Claims must contain 1–250 characters')
    return dict(hooks=draft_hooks(body.name,body.claims),status='draft',
        note='Review these opening lines before saving them as approved product copy.')


@app.post('/api/creators/draft')
def create_creator_draft():
    return draft_creator()


@app.put('/api/products/{id}')
def update_product(id: str, body: Product):
    require('products', id)
    db.execute('UPDATE products SET data=? WHERE id=?', (body.model_dump_json(), id))
    return require('products', id)


def check_creator(body):
    if body.reference_asset_id:
        asset = require('assets', body.reference_asset_id)
        if asset['kind'] != 'image' or not asset['approved']:
            raise ValueError('Reference must be an approved image')


@app.post('/api/creators', status_code=201)
def create_creator(body: Creator):
    check_creator(body)
    id = db.uid('creator_')
    db.execute('INSERT INTO creators VALUES(?,?,?)', (id, body.model_dump_json(), time.time()))
    return require('creators', id)


@app.put('/api/creators/{id}')
def update_creator(id: str, body: Creator):
    require('creators', id)
    check_creator(body)
    db.execute('UPDATE creators SET data=? WHERE id=?', (body.model_dump_json(), id))
    return require('creators', id)


@app.post('/api/assets', status_code=201)
async def upload_asset(file: UploadFile = File(...), product_id: str = Form(''), rights: str = Form(...), approved: bool = Form(False)):
    if len(rights.strip()) < 10:
        raise ValueError('Record the source and commercial usage rights')
    if product_id:
        require('products', product_id)
    suffix = Path(file.filename or '').suffix.lower()
    allowed = {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.webm'}
    if suffix not in allowed:
        raise ValueError('Use PNG, JPG, WEBP, MP4, MOV or WEBM')
    id = db.uid('asset_')
    path = config.MEDIA / (id+suffix)
    try:
        size = 0
        with path.open('wb') as out:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > 100*1024*1024:
                    raise ValueError('Upload limit is 100 MB')
                out.write(chunk)
        kind = 'image' if suffix in ('.png','.jpg','.jpeg','.webp') else 'video'
        if kind == 'image':
            with Image.open(path) as image:
                image.verify()
        else:
            info = probe(path)
            if not any(s['codec_type']=='video' for s in info['streams']):
                raise ValueError('File has no video stream')
        db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)',
            (id, product_id or None, kind, path.name, (file.filename or 'Asset')[:200], rights[:2000], int(approved), time.time()))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return require('assets', id)


@app.patch('/api/assets/{id}')
def approve_asset(id: str, approved: bool):
    require('assets', id)
    db.execute('UPDATE assets SET approved=? WHERE id=?', (int(approved), id))
    return require('assets', id)


@app.post('/api/batches/quote')
def batch_quote(body: Batch):
    return quote(body)


@app.post('/api/batches', status_code=201)
def create_batch(body: Batch, request: Request):
    key = request.headers.get('idempotency-key')
    if key and (len(key)>100 or not all(c.isalnum() or c in '_-' for c in key)):
        raise ValueError('Idempotency-Key must be 1–100 letters, numbers, underscores or hyphens')
    return make_batch(body, 'batch_'+key if key else None)


@app.get('/api/jobs')
def jobs(batch_id: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0):
    where, args = [], []
    if batch_id:
        where.append('batch_id=?'); args.append(batch_id)
    if status:
        where.append('status=?'); args.append(status)
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    return dict(items=db.rows('SELECT * FROM jobs'+clause+' ORDER BY created DESC LIMIT ? OFFSET ?', (*args, min(max(limit,1),500), max(offset,0))),
                total=db.one('SELECT COUNT(*) AS n FROM jobs'+clause, args)['n'])


@app.get('/api/jobs/{id}')
def job_detail(id: str):
    return dict(**require('jobs', id), events=db.rows('SELECT * FROM events WHERE job_id=? ORDER BY id', (id,)),
                spend=db.rows('SELECT * FROM spend WHERE job_id=?', (id,)))


@app.post('/api/jobs/{id}/cancel')
def cancel_job(id: str):
    job = require('jobs', id)
    if job['status'] not in ('queued','running','budget_blocked','attention','failed'):
        raise ValueError('Only unfinished jobs can be cancelled')
    db.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status='running' THEN status ELSE 'cancelled' END,updated=? WHERE id=?", (time.time(),id))
    return require('jobs', id)


@app.post('/api/jobs/{id}/retry')
def retry_job(id: str):
    job = require('jobs', id)
    if job['status'] not in ('failed','attention','budget_blocked','cancelled'):
        raise ValueError('This job is not retryable')
    db.execute("UPDATE jobs SET status='queued',cancel_requested=0,available=0,error=NULL,attempts=0,updated=? WHERE id=?", (time.time(),id))
    db.event(id, 'queued', 'Manually resumed; cached stages and provider request IDs retained')
    return require('jobs', id)


class BudgetUpdate(BaseModel):
    budget: float = Field(gt=0, le=100000)


@app.patch('/api/batches/{id}/budget')
def update_budget(id: str, body: BudgetUpdate):
    require('batches', id)
    used = db.one("SELECT COALESCE(SUM(amount),0) AS total FROM spend WHERE batch_id=? AND state!='released'", (id,))['total']
    if body.budget < used:
        raise ValueError('Cap cannot be lower than already committed costs')
    db.execute('UPDATE batches SET budget=? WHERE id=?', (body.budget,id))
    return require('batches',id)


@app.post('/api/jobs/{id}/review')
def review_job(id: str, body: Review):
    job = require('jobs', id)
    if job['status'] not in ('review','approved','rejected') or not job['result']:
        raise ValueError('A finished clip is required')
    qa = job['qa']
    if body.decision=='approved' and not qa['passed']:
        raise ValueError('Technical QA failed; fix the source before approval')
    qa['review'] = body.model_dump() | dict(reviewed_at=time.time())
    db.execute('UPDATE jobs SET status=?,qa=?,updated=? WHERE id=?', (body.decision,json.dumps(qa),time.time(),id))
    db.event(id,'review',body.decision+': '+body.notes)
    manifest = config.MEDIA/id/'manifest.json'
    if manifest.exists():
        values = json.loads(manifest.read_text())
        values['qa'] = qa
        values['approval_status'] = body.decision
        manifest.write_text(json.dumps(values,indent=2))
    return require('jobs',id)


@app.get('/api/batches/{id}/export')
def export_batch(id: str, include_demo: bool = False):
    batch = require('batches',id)
    jobs = db.rows("SELECT * FROM jobs WHERE batch_id=? AND status='approved'", (id,))
    jobs = [j for j in jobs if include_demo or not j['result'].get('demo')]
    if not jobs:
        raise ValueError('No approved production videos. Demo exports require include_demo=true.')
    directory = config.DATA / 'exports'
    directory.mkdir(exist_ok=True)
    path = directory/(id+'.zip')
    buffer = io.StringIO()
    fields = ['creative_id','file','caption','landing_url','disclosure','model','creator','demo']
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for j in jobs:
            result = j['result']
            folder = config.MEDIA/j['id']
            for name in ('final.mp4','captions.srt','manifest.json','poster.jpg'):
                archive.write(folder/name, j['id']+'/'+name)
            url = urlparse(j['spec']['product'].get('landing_url',''))
            params = dict(parse_qsl(url.query)) | dict(utm_source='social',utm_medium='organic',utm_campaign=id,utm_content=j['id'])
            landing = urlunparse(url._replace(query=urlencode(params))) if url.scheme else ''
            writer.writerow(dict(creative_id=j['id'],file=j['id']+'/final.mp4',caption=result['script']['text'],
                landing_url=landing,disclosure=result['script']['disclosure'],model=result['model'],creator=result['creator'],demo=result.get('demo',False)))
        archive.writestr('publishing.csv',buffer.getvalue())
        archive.writestr('README.txt','Approved export package. Set the platform AI disclosure label when publishing realistic synthetic content. Verify caption timing, product accuracy and current platform requirements. UTM links use organic defaults; change medium for paid campaigns. No publishing or advertising spend is automated.\n')
    return FileResponse(path, filename=id+'.zip')


@app.get('/api/analytics')
def get_analytics(batch_id: str | None = None):
    return analytics.report(batch_id)


@app.get('/api/metrics/template')
def metrics_template():
    return Response('job_id,platform,date,impressions,views,clicks,customers,revenue,media_spend\n', media_type='text/csv', headers={'Content-Disposition':'attachment; filename=metrics-template.csv'})


@app.post('/api/metrics/import')
async def import_metrics(file: UploadFile=File(...)):
    contents = await file.read(2*1024*1024+1)
    if len(contents)>2*1024*1024:
        raise ValueError('CSV limit is 2 MB')
    records = []
    try:
        for i, row in enumerate(csv.DictReader(io.StringIO(contents.decode('utf-8-sig')))):
            if i >= 10000:
                raise ValueError('CSV limit is 10,000 rows')
            record = Metric.model_validate(row)
            require('jobs',record.job_id)
            if record.clicks>record.impressions or record.customers>record.clicks:
                raise ValueError(f'Row {i+2}: customers ≤ clicks ≤ impressions is required for these funnel metrics')
            records.append(record)
    except (UnicodeError, ValidationError) as e:
        raise ValueError('Invalid CSV: '+str(e)[:1000]) from e
    with db.connection(True) as c:
        for r in records:
            c.execute('INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id,platform,date) DO UPDATE SET impressions=excluded.impressions,views=excluded.views,clicks=excluded.clicks,customers=excluded.customers,revenue=excluded.revenue,media_spend=excluded.media_spend',
                (db.uid('metric_'),r.job_id,r.platform,r.date,r.impressions,r.views,r.clicks,r.customers,r.revenue,r.media_spend,time.time()))
    return dict(imported=len(records), semantics='Daily snapshots replace the same creative/platform/date, preventing double counting. Customers must be newly acquired customers, not orders.')


@app.post('/api/automations', status_code=201)
def create_automation(body: Automation):
    require('products',body.batch.product_id)
    id = db.uid('auto_')
    db.execute('INSERT INTO automations VALUES(?,?,?,?,?,?,?,?)', (id,body.name,body.batch.model_dump_json(),int(body.enabled),body.interval_hours,time.time()+body.interval_hours*3600,None,time.time()))
    return require('automations',id)


@app.patch('/api/automations/{id}')
def toggle_automation(id: str, enabled: bool):
    require('automations',id)
    db.execute('UPDATE automations SET enabled=? WHERE id=?',(int(enabled),id))
    return require('automations',id)


@app.get('/api/requests')
def provider_requests():
    return db.rows('SELECT * FROM requests ORDER BY created DESC LIMIT 200')


class Reconcile(BaseModel):
    action: str
    request_id: str = ''
    amount: float | None = Field(default=None, ge=0)


@app.post('/api/requests/{key}/reconcile')
def reconcile(key: str, body: Reconcile):
    row = db.one('SELECT * FROM requests WHERE key=?',(key,))
    if not row:
        raise HTTPException(404,'Request not found')
    if body.action == 'attach':
        if not body.request_id or len(body.request_id)>200 or not all(c.isalnum() or c in '_-' for c in body.request_id):
            raise ValueError('Enter the provider request ID from your dashboard')
        if row['provider']=='comfyui':
            payload = dict(prompt_id=body.request_id)
        elif row['provider'].startswith('runpod:'):
            payload = dict(id=body.request_id)
        else:
            # fal uses the first two path segments as the application route for polling.
            root = '/'.join(row['provider'].split('/')[:2])
            base = 'https://queue.fal.run/'+root+'/requests/'+body.request_id
            payload = dict(request_id=body.request_id,status_url=base+'/status',response_url=base,cost_id='cost_'+key)
        db.execute("UPDATE requests SET data=?,state='queued' WHERE key=?", (json.dumps(payload),key))
    elif body.action == 'confirm_not_submitted':
        if row['state']=='done':
            raise ValueError('Completed requests cannot be resubmitted')
        with db.connection(True) as c:
            billed = c.execute("SELECT 1 FROM spend WHERE id=? AND state='committed'",('cost_'+key,)).fetchone()
            if billed:
                raise ValueError('This attempt already has committed costs. Use retry_failed to preserve them and reserve a new attempt.')
            c.execute('DELETE FROM requests WHERE key=?',(key,))
            c.execute("DELETE FROM spend WHERE id=? AND state='reserved'",('cost_'+key,))
    elif body.action == 'retry_failed':
        if row['state']!='failed':
            raise ValueError('Only definitively failed requests may be retried with a fresh reservation')
        archived = key+'_archived_'+db.uid()
        with db.connection(True) as c:
            c.execute("UPDATE requests SET key=?,state='archived_failed' WHERE key=?",(archived,key))
            c.execute('UPDATE spend SET id=? WHERE id=?',('cost_'+archived,'cost_'+key))
    elif body.action == 'cost' and body.amount is not None:
        accounting.settle('cost_'+key, body.amount, 'invoice reconciled')
    else:
        raise ValueError('Choose attach, confirm_not_submitted, retry_failed or cost')
    db.event(row['job_id'],'reconcile',body.action)
    return dict(ok=True)


# Same-origin assets: workspace token/cookie guards private product images and clips.
app.mount('/media',StaticFiles(directory=config.MEDIA),name='media')
web = config.ROOT/'apps/web/dist'
if web.exists():
    app.mount('/',StaticFiles(directory=web,html=True),name='web')
