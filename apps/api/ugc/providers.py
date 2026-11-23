import base64
import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from . import accounting, config, db
from .creative import cache_key


class NeedsAttention(RuntimeError):
    """An ambiguous paid submission must be reconciled, never blindly repeated."""


def run(command, timeout=300):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[-2400:] or result.stdout[-2400:])
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path], 60))


def duration(path):
    return float(probe(path)['format']['duration'])


def checked_download(url, path):
    host = urlparse(url).hostname or ''
    if urlparse(url).scheme != 'https' or not (host == 'fal.media' or host.endswith('.fal.media') or host.endswith('.fal.ai')):
        raise ValueError('Provider result must be on a trusted HTTPS fal media host')
    tmp = path.with_suffix(path.suffix + '.part')
    with httpx.stream('GET', url, timeout=180, follow_redirects=False) as response:
        response.raise_for_status()
        count = 0
        with tmp.open('wb') as out:
            for chunk in response.iter_bytes():
                count += len(chunk)
                if count > 500 * 1024 * 1024:
                    raise ValueError('Provider file exceeds 500 MB')
                out.write(chunk)
    tmp.replace(path)


def upload(path):
    import fal_client
    return fal_client.upload_file(str(path))


def fal(job, stage, endpoint, arguments, estimate, key):
    if config.MODE != 'production' or not os.getenv('FAL_KEY'):
        raise ValueError('Set UGC_MODE=production and FAL_KEY to enable paid inference')
    existing = db.one('SELECT * FROM requests WHERE key=?', (key,))
    if existing and existing['state'] == 'submitting':
        raise NeedsAttention('Paid submission outcome is unknown. Reconcile this request in Settings before retrying: ' + key)
    if existing and existing['state'] == 'failed':
        raise NeedsAttention('Provider rejected this request. Reconcile it in Settings before retrying: ' + key)
    sid = accounting.reserve(job, stage, estimate, key)
    headers = {'Authorization': 'Key ' + os.environ['FAL_KEY']}
    with httpx.Client(timeout=90) as client:
        if not existing:
            # Record before network submission. A lost response is never an automatic resubmit.
            with db.connection(True) as c:
                prior = c.execute('SELECT 1 FROM requests WHERE key=?', (key,)).fetchone()
                if prior:
                    raise NeedsAttention('Another worker owns this provider request; retry after it finishes.')
                c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)', (key, job['id'], endpoint,
                    json.dumps(dict(cost_id=sid)), 'submitting', time.time()))
            try:
                response = client.post('https://queue.fal.run/' + endpoint, headers=headers, json=arguments)
                if 400 <= response.status_code < 500:
                    db.execute("UPDATE requests SET state='failed', data=? WHERE key=?", (json.dumps(dict(cost_id=sid, status=response.status_code)), key))
                response.raise_for_status()
                payload = response.json()
                # Only contact URLs returned by the authenticated queue API, on its host.
                for field in ('status_url', 'response_url'):
                    u = urlparse(payload[field])
                    if u.scheme != 'https' or u.hostname != 'queue.fal.run':
                        raise ValueError('Unexpected fal queue URL')
                payload['cost_id'] = sid
                db.execute("UPDATE requests SET data=?, state='queued' WHERE key=?", (json.dumps(payload), key))
            except Exception as e:
                raise NeedsAttention(f'Provider submission needs reconciliation ({type(e).__name__}). Request key: {key}') from e
        else:
            payload = existing['data']
        if existing and existing['state'] == 'done':
            return payload['result']
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            state = db.one('SELECT cancel_requested FROM jobs WHERE id=?', (job['id'],))
            if state and state['cancel_requested']:
                raise NeedsAttention('Cancellation requested. The submitted provider job may still incur cost; its request ID was retained.')
            status_response = client.get(payload['status_url'], headers=headers)
            status_response.raise_for_status()
            status = status_response.json()['status']
            if status == 'COMPLETED':
                result_response = client.get(payload['response_url'], headers=headers)
                if result_response.is_error:
                    db.execute("UPDATE requests SET state='failed' WHERE key=?", (key,))
                    accounting.settle(sid)
                result_response.raise_for_status()
                result = result_response.json()
                payload['result'] = result
                db.execute("UPDATE requests SET state='done', data=? WHERE key=?", (json.dumps(payload), key))
                accounting.settle(sid)
                return result
            time.sleep(2)
    raise NeedsAttention('Provider is still running after one hour; request retained. Resume to poll the same request.')


def cache_get(key):
    row = db.one('SELECT * FROM cache WHERE key=?', (key,))
    if row and (config.MEDIA / row['path']).is_file():
        return config.MEDIA / row['path'], row['data']
    return None


def cache_put(key, path, data):
    db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',
        (key, str(path.relative_to(config.MEDIA)), json.dumps(data), time.time()))
    return path, data


def voice(job, script, creator):
    provider = 'demo' if job['spec']['model'] == 'demo' else os.getenv('UGC_TTS_PROVIDER', 'fal')
    key = cache_key('voice-v2', provider, script['text'], creator['voice'])
    cached = cache_get(key)
    if cached:
        return *cached, True
    target = config.MEDIA / (key + '.wav')
    if provider == 'demo':
        import shutil
        if shutil.which('espeak-ng') or shutil.which('espeak'):
            run([shutil.which('espeak-ng') or shutil.which('espeak'), '-s', '155', '-w', target, script['text']])
        elif shutil.which('say'):
            aiff = target.with_suffix('.aiff')
            run(['say', '-r', '155', '-o', aiff, script['text']])
            run(['ffmpeg', '-y', '-i', aiff, '-ar', '24000', target])
            aiff.unlink(missing_ok=True)
        else:
            raise ValueError('Demo speech needs espeak-ng (included in Docker) or macOS say')
    elif provider == 'local':
        sid = accounting.reserve(job, 'voice', .02, key)
        response = httpx.post(os.getenv('UGC_VOICE_URL', 'http://localhost:8091') + '/speech',
            headers={'Authorization': 'Bearer ' + config.WORKER_TOKEN},
            json=dict(text=script['text'], voice=creator['voice'], key=key), timeout=300)
        response.raise_for_status()
        target.write_bytes(response.content)
        accounting.settle(sid)
    else:
        result = fal(job, 'voice', 'fal-ai/kokoro/american-english',
            dict(prompt=script['text'], voice=creator['voice'], speed=1), max(.01, len(script['text']) / 1000 * .05), key)
        checked_download(result['audio']['url'], target)
    data = dict(duration=duration(target), provider=provider, voice=creator['voice'])
    cache_put(key, target, data)
    return target, data, False


def portrait(job, creator):
    reference = creator.get('reference_asset_id')
    if reference:
        asset = db.one('SELECT * FROM assets WHERE id=? AND approved=1', (reference,))
        if not asset or asset['kind'] != 'image':
            raise ValueError('Creator reference must be an approved image')
        return config.MEDIA / asset['path'], {}, True
    key = cache_key('portrait-v1', creator['description'])
    cached = cache_get(key)
    if cached:
        return *cached, True
    target = config.MEDIA / (key + '.png')
    result = fal(job, 'portrait', 'fal-ai/flux/schnell', dict(prompt=creator['description'] +
        ', original fictional person, realistic skin texture, no product, no text, no logos',
        image_size=dict(width=576, height=1024), num_images=1, num_inference_steps=4, seed=job['spec']['seed']), .02, key)
    checked_download(result['images'][0]['url'], target)
    cache_put(key, target, {})
    return target, {}, False


def talking(job, image, audio, seconds, model):
    key = cache_key('talking-v2', job['spec']['model'], image.name, audio.name, job['spec']['seed'])
    cached = cache_get(key)
    if cached:
        return *cached, True
    target = config.MEDIA / (key + '.mp4')
    if job['spec']['model'] == 'infinitetalk':
        # The remote worker caches by key, preventing duplicate inference after network failures.
        sid = accounting.reserve(job, 'avatar', float(os.getenv('UGC_GPU_HOURLY', '.75')) * 1, key)
        started = time.monotonic()
        if os.getenv('UGC_AVATAR_TRANSPORT','http') == 'runpod':
            runpod_avatar(job,key,image,audio,target,sid)
            cache_put(key,target,dict(duration=duration(target)))
            return target,dict(duration=duration(target)),False
        base = os.environ['UGC_AVATAR_URL'].rstrip('/')
        with httpx.Client(timeout=120, headers={'Authorization': 'Bearer '+config.WORKER_TOKEN}) as client:
            with image.open('rb') as img, audio.open('rb') as wav:
                response = client.post(base+'/jobs',data=dict(key=key,seed=str(job['spec']['seed'])),
                    files=dict(image=(image.name,img,'image/png'),audio=(audio.name,wav,'audio/wav')))
            response.raise_for_status()
            while time.monotonic()-started<3600:
                response = client.get(base+'/jobs/'+key)
                response.raise_for_status()
                status = response.json()
                if status['status']=='failed':
                    raise NeedsAttention(status['error']+'; inspect GPU host logs before retrying.')
                if status['status']=='completed':
                    response = client.get(base+'/jobs/'+key+'/result')
                    response.raise_for_status()
                    target.write_bytes(response.content)
                    accounting.settle(sid, status['runtime_seconds']/3600*float(os.getenv('UGC_GPU_HOURLY','.75')), 'runtime estimate; idle/storage excluded')
                    break
                time.sleep(3)
            else:
                raise NeedsAttention('Avatar worker timeout; the persistent job key was retained. Resume to reconnect.')
    else:
        estimate = seconds * model['rate'] * 1.2
        result = fal(job, 'avatar', model['endpoint'],
            dict(image_url=upload(image), audio_url=upload(audio), resolution=model['resolution']), estimate, key)
        checked_download(result['video']['url'], target)
    cache_put(key, target, dict(duration=duration(target)))
    return target, dict(duration=duration(target)), False


def runpod_avatar(job,key,image,audio,target,sid):
    token = os.getenv('RUNPOD_API_KEY','')
    endpoint = os.getenv('RUNPOD_ENDPOINT_ID','')
    if not token or not endpoint or not endpoint.replace('-','').isalnum():
        raise ValueError('Configure RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID')
    base = 'https://api.runpod.ai/v2/'+endpoint
    headers = {'Authorization':'Bearer '+token}
    existing = db.one('SELECT * FROM requests WHERE key=?',(key,))
    if existing and existing['state'] in ('submitting','failed'):
        raise NeedsAttention('RunPod submission requires reconciliation: '+key)
    with httpx.Client(timeout=120,headers=headers) as client:
        if not existing:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',(key,job['id'],'runpod:'+endpoint,json.dumps(dict(cost_id=sid)),'submitting',time.time()))
            try:
                response = client.post(base+'/run',json={'input':dict(key=key,seed=job['spec']['seed'],
                    image_base64=base64.b64encode(image.read_bytes()).decode(),audio_base64=base64.b64encode(audio.read_bytes()).decode()),
                    'policy':{'executionTimeout':3500000}})
                response.raise_for_status()
                payload = response.json()
                db.execute("UPDATE requests SET data=?,state='queued' WHERE key=?",(json.dumps(payload),key))
            except Exception as e:
                raise NeedsAttention('RunPod submission outcome uncertain. Attach its job ID before resuming: '+key) from e
        else:
            payload = existing['data']
        deadline = time.monotonic()+3600
        while time.monotonic()<deadline:
            response = client.get(base+'/status/'+payload['id'])
            response.raise_for_status()
            result = response.json()
            status = result['status']
            if status in ('FAILED','CANCELLED','TIMED_OUT'):
                db.execute("UPDATE requests SET state='failed',data=? WHERE key=?",(json.dumps(result),key))
                accounting.settle(sid)
                raise NeedsAttention('RunPod job '+status+'. Check the GPU logs before resubmitting.')
            if status=='COMPLETED':
                output = result['output']
                if output.get('error'):
                    raise NeedsAttention(output['error'])
                target.write_bytes(base64.b64decode(output['video_base64'],validate=True))
                # Exclude large inline output from SQLite; retain the provider job ID.
                db.execute("UPDATE requests SET state='done' WHERE key=?",(key,))
                billed_seconds = result.get('executionTime',output.get('runtime_seconds',0)*1000)/1000
                accounting.settle(sid,billed_seconds/3600*float(os.getenv('UGC_GPU_HOURLY','.75')),'provider execution time × configured rate; startup/storage may differ')
                return
            time.sleep(3)
    raise NeedsAttention('RunPod still running; resume to poll the existing job.')


def wan(job, image=None):
    from .workflows import wan_workflow
    key = cache_key('wan-v1', job['spec']['product']['description'], image.name if image else None, job['spec']['seed'])
    cached = cache_get(key)
    if cached:
        return *cached, True
    target = config.MEDIA / (key + '.mp4')
    base = os.getenv('UGC_COMFY_URL', 'http://localhost:8188').rstrip('/')
    with httpx.Client(timeout=120, headers={'Authorization': 'Bearer ' + config.WORKER_TOKEN}) as client:
        reference = None
        if image:
            with image.open('rb') as file:
                response = client.post(base+'/upload/image', files={'image': (image.name, file)}, data={'overwrite': 'true'})
            response.raise_for_status()
            reference = response.json()['name']
        workflow = wan_workflow(job['spec']['product'], job['spec']['seed'], reference)
        sid = accounting.reserve(job, 'broll', float(os.getenv('UGC_LOCAL_HOURLY', '.10')), key)
        existing = db.one('SELECT * FROM requests WHERE key=?', (key,))
        if existing and existing['state'] == 'submitting':
            raise NeedsAttention('ComfyUI submission uncertain; inspect the queue before reconciling request ' + key)
        if existing:
            pid = existing['data']['prompt_id']
        else:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)', (key, job['id'], 'comfyui', '{}', 'submitting', time.time()))
            response = client.post(base+'/prompt', json=dict(prompt=workflow, client_id=key))
            response.raise_for_status()
            pid = response.json()['prompt_id']
            db.execute("UPDATE requests SET data=?,state='queued' WHERE key=?", (json.dumps(dict(prompt_id=pid)), key))
        started = time.monotonic()
        while time.monotonic()-started < 3600:
            response = client.get(base+'/history/'+pid)
            response.raise_for_status()
            history = response.json().get(pid)
            if history:
                if history.get('status', {}).get('status_str') == 'error':
                    raise NeedsAttention('ComfyUI failed. Check worker logs, lower resolution/frames if out of memory. Request: ' + key)
                outputs = history.get('outputs', {})
                files = [v for output in outputs.values() for name in ('images', 'gifs', 'videos') for v in output.get(name, []) if v.get('filename', '').endswith('.mp4')]
                if not files:
                    raise ValueError('ComfyUI finished but returned no MP4. Check SaveVideo node.')
                result = client.get(base+'/view', params=files[0])
                result.raise_for_status()
                target.write_bytes(result.content)
                db.execute("UPDATE requests SET state='done' WHERE key=?", (key,))
                accounting.settle(sid)  # Includes an hour reserved, until billing reconciliation.
                cache_put(key, target, dict(duration=duration(target)))
                return target, dict(duration=duration(target)), False
            time.sleep(3)
    raise NeedsAttention('ComfyUI timeout. Inspect the retained prompt before retrying.')
