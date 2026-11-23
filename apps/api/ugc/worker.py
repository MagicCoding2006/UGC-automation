import json
import os
import signal
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from . import accounting, config, db, providers
from .creative import build_script
from .registry import MODELS
from .render import render, technical_qa
from .schemas import Batch
from .service import make_batch

STOP = threading.Event()


def stage(job, name, message):
    state = db.one('SELECT cancel_requested,owner FROM jobs WHERE id=?', (job['id'],))
    if not state or state['cancel_requested']:
        raise InterruptedError('Cancelled before the next step')
    if state['owner'] != job['owner']:
        raise InterruptedError('Lease ownership changed')
    db.execute('UPDATE jobs SET stage=?,updated=? WHERE id=?', (name, time.time(), job['id']))
    db.event(job['id'], name, message)


def process(job):
    spec = job['spec']
    try:
        if spec['model']!='demo' and config.MODE!='production':
            raise ValueError('Demo mode does not execute production jobs; enable production mode before resuming')
        stage(job, 'script', 'Selecting approved hooks, product facts and CTA')
        script = build_script(spec['product'], spec['hook_index'], spec['seed'], spec['duration'])
        script['demo'] = spec['model'] == 'demo'
        stage(job, 'voice', 'Generating a reusable voiceover')
        audio, voice_data, reused = providers.voice(job, script, spec['creator'])
        db.event(job['id'], 'voice', 'Cache hit: reused voiceover' if reused else 'Voiceover generated')
        if voice_data['duration'] > spec['duration'] * 1.65:
            raise ValueError('Speech is too long for this brief. Shorten approved hooks or claims.')
        assets = [db.one('SELECT * FROM assets WHERE id=? AND approved=1', (id,)) for id in spec['asset_ids']]
        if not all(assets):
            raise ValueError('Source asset was removed or is no longer approved')
        footage = None
        if MODELS[spec['model']]['type'] == 'talking':
            stage(job, 'portrait', 'Loading a consistent creator portrait')
            image, _, reused = providers.portrait(job, spec['creator'])
            db.event(job['id'], 'portrait', 'Reused creator identity' if reused else 'Created original fictional portrait')
            stage(job, 'video', 'Generating an audio-driven talking video')
            footage, _, reused = providers.talking(job, image, audio, voice_data['duration'], spec.get('model_config',MODELS[spec['model']]))
            db.event(job['id'], 'video', 'Cache hit: reused generated clip' if reused else 'Talking clip generated')
        elif spec['model'] == 'wan-local':
            stage(job, 'video', 'Generating Wan B-roll with CPU offload; one GPU job at a time')
            image = next((config.MEDIA/a['path'] for a in assets if a['kind']=='image'), None)
            footage, _, reused = providers.wan(job, image)
        stage(job, 'edit', 'Editing vertical video, normalizing audio and burning captions')
        result = render(job, script, audio, footage, assets)
        stage(job, 'qa', 'Checking full decode, dimensions, duration and audio/video streams')
        qa = technical_qa(config.MEDIA/result['video'], result['duration'])
        result.update(script=script, voice=voice_data, model=spec['model'], creator=spec['creator']['name'],
            demo=spec['model']=='demo', source_footage=str(footage.relative_to(config.MEDIA)) if footage else None)
        directory = config.MEDIA / job['id']
        (directory/'manifest.json').write_text(json.dumps(dict(creative_id=job['id'], batch_id=job['batch_id'], spec=spec,
            result=result, qa=qa, disclosure=script['disclosure']), indent=2))
        qualified = db.one("SELECT COUNT(*) AS n FROM jobs WHERE status='approved' AND json_extract(spec,'$.qualification_key')=? AND json_extract(qa,'$.review.realism')>=4 AND json_extract(qa,'$.review.lipsync')>=4 AND json_extract(qa,'$.review.product_accuracy')>=4", (spec.get('qualification_key','missing'),))['n'] >= 3
        status = 'review' if qa['passed'] else 'rejected'
        if qa['passed'] and config.AUTO_APPROVE and qualified and spec['model'] != 'demo':
            status = 'approved'
            qa['auto_approved'] = True
            qa['qualification'] = 'At least three prior human approvals with scores >=4 on this product/creator/model route'
        db.execute('UPDATE jobs SET status=?,stage=?,result=?,qa=?,error=NULL,owner=NULL,lease=NULL,updated=? WHERE id=?',
            (status, 'complete', json.dumps(result), json.dumps(qa), time.time(), job['id']))
        db.event(job['id'], 'complete', 'Ready for review' if status=='review' else status)
    except InterruptedError as e:
        db.execute("UPDATE jobs SET status='cancelled',error=?,owner=NULL,lease=NULL,updated=? WHERE id=? AND owner=?", (str(e), time.time(), job['id'], job['owner']))
    except Exception as e:
        if isinstance(e, accounting.BudgetExceeded):
            status = 'budget_blocked'
        elif isinstance(e, providers.NeedsAttention):
            status = 'attention'
        elif job['attempts'] < config.MAX_ATTEMPTS and not isinstance(e, ValueError):
            status = 'queued'
        else:
            status = 'failed'
        message = str(e)[:2500]
        db.execute('UPDATE jobs SET status=?,error=?,owner=NULL,lease=NULL,available=?,updated=? WHERE id=? AND owner=?',
            (status, message, time.time()+min(60*job['attempts'], 300), time.time(), job['id'], job['owner']))
        db.event(job['id'], 'error', message, 'error')
        print(f'{job["id"]}: {status}: {message}', flush=True)


def scheduler():
    for automation in db.rows('SELECT * FROM automations WHERE enabled=1 AND next_run<=?', (time.time(),)):
        backlog = db.one("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')")['n']
        if backlog >= 2000:
            return
        key = 'schedule:' + automation['id']
        with db.connection(True) as c:
            pending = c.execute('SELECT data FROM settings WHERE key=?', (key,)).fetchone()
            slot = json.loads(pending['data']) if pending else int(automation['next_run'])
            c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', (key, json.dumps(slot)))
        try:
            spec = Batch.model_validate(automation['spec'])
            spec.seed = (spec.seed+slot) % 2147483647
            spec.name += ' · ' + time.strftime('%Y-%m-%d', time.gmtime(slot))
            make_batch(spec, f'auto_{automation["id"]}_{slot}')
            with db.connection(True) as c:
                c.execute('UPDATE automations SET next_run=?,last_error=NULL WHERE id=?', (time.time()+automation['interval_hours']*3600, automation['id']))
                c.execute('DELETE FROM settings WHERE key=?', (key,))
        except Exception as e:
            db.execute('UPDATE automations SET last_error=?,next_run=? WHERE id=?', (str(e)[:1000], time.time()+600, automation['id']))


def loop(index):
    owner = db.uid('worker_') + str(index)
    current = [None]
    def heartbeat():
        while not STOP.wait(10):
            db.execute('INSERT OR REPLACE INTO heartbeats VALUES(?,?)', (owner, time.time()))
            if current[0]:
                db.execute("UPDATE jobs SET lease=? WHERE id=? AND owner=? AND status='running'", (time.time()+120, current[0], owner))
    threading.Thread(target=heartbeat, daemon=True).start()
    db.execute('INSERT OR REPLACE INTO heartbeats VALUES(?,?)', (owner, time.time()))
    last_schedule = 0
    while not STOP.is_set():
        if index == 0 and time.monotonic()-last_schedule > 15:
            scheduler()
            last_schedule = time.monotonic()
        job = db.claim(owner)
        if job:
            current[0] = job['id']
            process(job)
            current[0] = None
        else:
            STOP.wait(1)
    db.execute('DELETE FROM heartbeats WHERE id=?', (owner,))


def main():
    db.initialize()
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    count = int(os.getenv('UGC_WORKER_CONCURRENCY', '1'))
    if not 1 <= count <= 8:
        raise ValueError('Worker concurrency must be 1–8; keep at 1 on a 12 GB GPU')
    print(f'UGC worker started: {config.MODE}, concurrency={count}', flush=True)
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(loop, i) for i in range(count)]
        for future in futures:
            future.result()


if __name__ == '__main__':
    main()
