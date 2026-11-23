import concurrent.futures
import io
import json
import time
import zipfile
import pytest


def test_matched_model_experiments(workspace,batch_spec,monkeypatch):
    from ugc import db,config
    from ugc.service import make_batch
    monkeypatch.setattr(config,'MODE','production')
    monkeypatch.setenv('FAL_KEY','test-no-network')
    batch_spec.experiment='model'
    batch_spec.models=['fabric-480','fabric-720']
    batch_spec.count=6
    batch_spec.budget=100
    batch=make_batch(batch_spec)
    jobs=db.rows('SELECT * FROM jobs WHERE batch_id=? ORDER BY created',(batch['id'],))
    for a,b in zip(jobs[::2],jobs[1::2]):
        assert a['spec']['model']!=b['spec']['model']
        for field in ('creator','seed','hook_index','product','replicate'):
            assert a['spec'][field]==b['spec'][field]


def test_atomic_budget_reservations(workspace,batch_spec):
    from ugc import db,accounting
    from ugc.service import make_batch
    batch_spec.budget=1
    make_batch(batch_spec)
    jobs=db.rows('SELECT * FROM jobs')
    def reserve(j):
        try:
            accounting.reserve(j,'test',.6)
            return True
        except accounting.BudgetExceeded:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(reserve,jobs))
    assert sum(results)==1
    assert accounting.summary()['total']==pytest.approx(.6)


def test_idempotency_and_snapshots(workspace,batch_spec):
    from ugc import db
    from ugc.service import make_batch
    first=make_batch(batch_spec,'idempotent')
    assert make_batch(batch_spec,'idempotent')['id']==first['id']
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==3
    data=db.one('SELECT * FROM products WHERE id=?',('example-bottle',))['data']
    data['name']='Changed later'
    db.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(data),'example-bottle'))
    assert db.one('SELECT * FROM jobs')['spec']['product']['name']=='The Everyday Bottle'
    batch_spec.name='Different request'
    with pytest.raises(ValueError,match='different batch'):
        make_batch(batch_spec,'idempotent')


def test_queue_claims_are_exclusive_and_expired_lease_recovers(workspace,batch_spec):
    from ugc import db
    from ugc.service import make_batch
    make_batch(batch_spec)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        claims=list(pool.map(db.claim,['worker-a','worker-b','worker-c']))
    assert len({j['id'] for j in claims})==3
    assert db.claim('empty') is None
    db.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,claims[0]['id']))
    recovered=db.claim('recovery')
    assert recovered['id']==claims[0]['id']
    assert recovered['attempts']==2


def test_demo_blocks_paid_routes(client,batch_spec):
    body=batch_spec.model_dump()
    body['models']=['fabric-480']
    response=client.post('/api/batches',json=body)
    assert response.status_code==400
    assert 'Demo mode' in response.json()['detail']


def test_csv_import_is_transactional_and_replaces_daily_snapshot(client,batch_spec):
    from ugc import db
    from ugc.service import make_batch
    make_batch(batch_spec)
    job=db.one('SELECT * FROM jobs')['id']
    header='job_id,platform,date,impressions,views,clicks,customers,revenue,media_spend\n'
    row=f'{job},tiktok,2026-11-23,1000,900,20,2,64,10\n'
    for _ in range(2):
        response=client.post('/api/metrics/import',files={'file':('metrics.csv',header+row,'text/csv')})
        assert response.status_code==200
    assert db.one('SELECT SUM(customers) n FROM metrics')['n']==2
    bad=f'{job},tiktok,2026-11-24,10,9,20,2,64,10\n'
    response=client.post('/api/metrics/import',files={'file':('metrics.csv',header+row+bad,'text/csv')})
    assert response.status_code==400
    assert db.one('SELECT COUNT(*) n FROM metrics')['n']==1


def test_unknown_paid_submit_never_retries(workspace,batch_spec,monkeypatch):
    from ugc import db,config,providers
    from ugc.service import make_batch
    make_batch(batch_spec)
    job=db.one('SELECT * FROM jobs')
    monkeypatch.setattr(config,'MODE','production')
    monkeypatch.setenv('FAL_KEY','test-no-network')
    db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',('key',job['id'],'test/model','{}','submitting',time.time()))
    with pytest.raises(providers.NeedsAttention,match='unknown'):
        providers.fal(job,'video','test/model',{},1,'key')
    assert db.one('SELECT COUNT(*) n FROM spend')['n']==0


def test_cache_reuses_actual_file(workspace):
    from ugc import providers,config
    path=config.MEDIA/'asset.txt'
    path.write_text('generated output')
    providers.cache_put('key',path,{'duration':2})
    assert providers.cache_get('key')[1]['duration']==2
    path.unlink()
    assert providers.cache_get('key') is None


def test_auth_guards_media_and_api(client,monkeypatch):
    from ugc import config
    monkeypatch.setattr(config,'TOKEN','a-long-workspace-token')
    assert client.get('/api/state').status_code==401
    assert client.get('/media/missing.png').status_code==401
    assert client.post('/api/session',json={'token':'wrong'}).status_code==401
    assert client.post('/api/session',json={'token':'a-long-workspace-token'}).status_code==200
    assert client.get('/api/state').status_code==200
    assert client.post('/api/products',json={},headers={'Origin':'https://evil.example'}).status_code==403


def test_analytics_uses_correct_funnel_math(workspace,batch_spec):
    from ugc import analytics,db
    from ugc.service import make_batch
    make_batch(batch_spec)
    j=db.one('SELECT * FROM jobs')
    db.execute('INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?,?,?)',('m',j['id'],'tiktok','2026-11-23',10000,8000,150,3,96,120,time.time()))
    result=analytics.report()[0]
    assert result['ctr']==pytest.approx(.015)
    assert result['cac']==pytest.approx(40)
    assert result['contribution_ltv']==pytest.approx(22.4)
    assert result['ltv_cac']==pytest.approx(.56)
    assert result['ctr_interval'][0]<.015<result['ctr_interval'][1]


def test_blocked_claims_cannot_enter_script(workspace):
    from ugc import db
    from ugc.creative import build_script
    product=db.one('SELECT * FROM products')['data']
    product['hooks']=['This cures everything.']
    product['forbidden_claims']=['cures']
    with pytest.raises(ValueError,match='blocked wording'):
        build_script(product,0,42,15)


def test_thousand_jobs_are_queued_without_inference(workspace,batch_spec):
    from ugc import db
    from ugc.service import make_batch
    batch_spec.count=1000
    batch=make_batch(batch_spec)
    assert db.one('SELECT COUNT(*) n FROM jobs WHERE batch_id=?',(batch['id'],))['n']==1000
    assert db.one('SELECT COUNT(*) n FROM spend')['n']==0


def test_concurrent_idempotent_submissions_create_one_batch(workspace,batch_spec):
    from ugc import db
    from ugc.service import make_batch
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        batches=list(pool.map(lambda _:make_batch(batch_spec,'same-request'),range(4)))
    assert len({b['id'] for b in batches})==1
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==batch_spec.count


def test_demo_mode_does_not_execute_old_production_jobs(workspace,batch_spec,monkeypatch):
    from ugc import db,config,worker
    from ugc.service import make_batch
    monkeypatch.setattr(config,'MODE','production')
    monkeypatch.setenv('FAL_KEY','no-network')
    batch_spec.models=['fabric-480']
    batch_spec.budget=50
    make_batch(batch_spec)
    claimed=db.claim('mode-test')
    monkeypatch.setattr(config,'MODE','demo')
    worker.process(claimed)
    assert db.one('SELECT * FROM jobs WHERE id=?',(claimed['id'],))['status']=='failed'
    assert db.one('SELECT COUNT(*) n FROM spend')['n']==0


def test_retried_provider_failure_preserves_previous_cost(client,batch_spec):
    from ugc import db,accounting
    from ugc.service import make_batch
    make_batch(batch_spec)
    job=db.one('SELECT * FROM jobs')
    key='c'*64
    sid=accounting.reserve(job,'video',.5,key)
    accounting.settle(sid)
    db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',(key,job['id'],'test/model','{}','failed',time.time()))
    response=client.post(f'/api/requests/{key}/reconcile',json={'action':'confirm_not_submitted'})
    assert response.status_code==400
    response=client.post(f'/api/requests/{key}/reconcile',json={'action':'retry_failed'})
    assert response.status_code==200
    accounting.reserve(job,'video',.6,key)
    assert accounting.summary()['total']==pytest.approx(1.1)


def test_daily_cap_applies_across_batches(workspace,batch_spec,monkeypatch):
    from ugc import db,accounting,config
    from ugc.service import make_batch
    monkeypatch.setattr(config,'DAILY_BUDGET',1)
    a=make_batch(batch_spec)
    b=make_batch(batch_spec)
    first=db.one('SELECT * FROM jobs WHERE batch_id=?',(a['id'],))
    second=db.one('SELECT * FROM jobs WHERE batch_id=?',(b['id'],))
    accounting.reserve(first,'video',.6)
    with pytest.raises(accounting.BudgetExceeded,match='Daily cap'):
        accounting.reserve(second,'video',.6)


def test_hook_and_creator_drafts_need_no_paid_provider(client):
    from ugc import db
    response=client.post('/api/creative/hooks',json=dict(name='Test Bottle',claims=['Stainless steel body','Twist-off lid']))
    assert response.status_code==200
    assert response.json()['status']=='draft'
    assert any('Stainless steel body' in h for h in response.json()['hooks'])
    creator=client.post('/api/creators/draft',json={})
    assert creator.status_code==200
    assert 'fictional adult' in creator.json()['description']
    assert db.one('SELECT COUNT(*) n FROM requests')['n']==0


@pytest.mark.integration
def test_full_demo_render_review_and_export(client,batch_spec):
    import shutil
    if not shutil.which('ffmpeg') or not any(shutil.which(p) for p in ('espeak-ng','espeak','say')):
        pytest.skip('Integration test needs FFmpeg and a system speech engine')
    from ugc import db,worker,config
    from ugc.service import make_batch
    batch_spec.count=1
    batch=make_batch(batch_spec)
    claimed=db.claim('test-worker')
    worker.process(claimed)
    job=db.one('SELECT * FROM jobs WHERE id=?',(claimed['id'],))
    assert job['status']=='review', job['error']
    assert job['qa']['passed']
    assert (config.MEDIA/job['result']['video']).stat().st_size>15000
    assert client.get(f'/api/batches/{batch["id"]}/export').status_code==400
    response=client.post(f'/api/jobs/{job["id"]}/review',json=dict(decision='approved',realism=4,lipsync=4,product_accuracy=4,notes='Demo pipeline test'))
    assert response.status_code==200
    response=client.get(f'/api/batches/{batch["id"]}/export?include_demo=true')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert 'publishing.csv' in z.namelist()
        assert job['id']+'/final.mp4' in z.namelist()

