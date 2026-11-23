"""Authenticated asynchronous avatar jobs with persistent idempotency keys.

Each subprocess exits after inference to release VRAM. That trades model-load
latency for isolation and predictable memory use. Benchmark warm custom workers
before replacing this conservative default.
"""
import hmac
import json
import math
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Form, File, UploadFile, Depends
from fastapi.responses import FileResponse

ROOT = Path(os.getenv('OUTPUT_DIR','/outputs'))
ROOT.mkdir(parents=True, exist_ok=True)
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.Lock()
ACTIVE = set()


def auth(authorization: str = Header(default='')):
    token = os.getenv('UGC_WORKER_TOKEN','')
    if not token or not hmac.compare_digest(authorization.encode(),('Bearer '+token).encode()):
        raise HTTPException(401,'Worker token required')


def validate_key(key):
    if not re.fullmatch('[a-f0-9]{64}',key):
        raise HTTPException(400,'Invalid job key')
    return ROOT/key


def write_state(directory, state, **values):
    path = directory/'state.json'
    temp = directory/'state.tmp'
    temp.write_text(json.dumps(dict(status=state,updated=time.time(),**values)))
    temp.replace(path)


def infer(directory):
    key = directory.name
    try:
        write_state(directory,'running')
        payload = json.loads((directory/'input.json').read_text())
        meta = json.loads((directory/'meta.json').read_text())
        probe = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(directory/'audio.wav')],capture_output=True,text=True,check=True)
        seconds = float(json.loads(probe.stdout)['format']['duration'])
        if not 1 <= seconds <= 45:
            raise ValueError('Audio must be 1–45 seconds')
        command = ['python','generate_infinitetalk.py',
            '--ckpt_dir','/models/Wan2.1-I2V-14B-480P',
            '--wav2vec_dir','/models/chinese-wav2vec2-base',
            '--infinitetalk_dir','/models/InfiniteTalk/single/infinitetalk.safetensors',
            '--input_json',str(directory/'input.json'), '--size','infinitetalk-480',
            '--sample_steps',os.getenv('AVATAR_STEPS','40'), '--mode','streaming',
            '--motion_frame','9', '--num_persistent_param_in_dit','0', '--t5_cpu',
            '--base_seed',str(meta['seed']), '--max_frame_num',str(min(1125,math.ceil(seconds*25)+25)),
            '--audio_save_dir',str(directory/'audio_features'), '--save_file',str(directory/'result')]
        started = time.monotonic()
        with (directory/'inference.log').open('w') as log:
            result = subprocess.run(command,cwd='/opt/InfiniteTalk',stdout=log,stderr=subprocess.STDOUT,timeout=3500)
        if result.returncode or not (directory/'result.mp4').exists():
            raise RuntimeError('Inference failed; inspect the job inference.log on the GPU host')
        write_state(directory,'completed',runtime_seconds=time.monotonic()-started)
    except Exception as e:
        write_state(directory,'failed',error=str(e)[:1000])
    finally:
        with LOCK:
            ACTIVE.discard(key)


def enqueue(directory):
    if directory.name not in ACTIVE:
        ACTIVE.add(directory.name)
        POOL.submit(infer,directory)


@asynccontextmanager
async def lifespan(app):
    # Restart interrupted jobs using the same inputs and key, not a new paid request.
    with LOCK:
        for path in ROOT.glob('*/state.json'):
            if json.loads(path.read_text()).get('status') in ('queued','running'):
                enqueue(path.parent)
    yield


app = FastAPI(title='ReelForge avatar worker',lifespan=lifespan)


@app.get('/health')
def health():
    return dict(ok=True,queued=len(ACTIVE),concurrency=1)


@app.post('/jobs',status_code=202,dependencies=[Depends(auth)])
async def submit(key: str = Form(...), seed: int = Form(42), image: UploadFile=File(...), audio: UploadFile=File(...)):
    directory = validate_key(key)
    if (directory/'state.json').exists():
        return json.loads((directory/'state.json').read_text()) | dict(key=key)
    if len(ACTIVE)>=100:
        raise HTTPException(429,'GPU queue is full')
    image_bytes = await image.read(20*1024*1024+1)
    audio_bytes = await audio.read(20*1024*1024+1)
    if max(len(image_bytes),len(audio_bytes))>20*1024*1024:
        raise HTTPException(413,'Each input is limited to 20 MB')
    from PIL import Image
    import io
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
    except Exception as e:
        raise HTTPException(400,'Invalid portrait image') from e
    with LOCK:
        if (directory/'state.json').exists():
            return json.loads((directory/'state.json').read_text()) | dict(key=key)
        directory.mkdir(exist_ok=True)
        (directory/'image.png').write_bytes(image_bytes)
        (directory/'audio.wav').write_bytes(audio_bytes)
        (directory/'meta.json').write_text(json.dumps(dict(seed=seed)))
        (directory/'input.json').write_text(json.dumps(dict(prompt='A person speaking naturally to the camera, subtle head movements, realistic expression, stable identity.',cond_video=str(directory/'image.png'),cond_audio=dict(person1=str(directory/'audio.wav')))))
        write_state(directory,'queued')
        enqueue(directory)
    return dict(key=key,status='queued')


@app.get('/jobs/{key}',dependencies=[Depends(auth)])
def status(key: str):
    path = validate_key(key)/'state.json'
    if not path.exists():
        raise HTTPException(404,'Unknown job')
    return json.loads(path.read_text())


@app.get('/jobs/{key}/result',dependencies=[Depends(auth)])
def result(key: str):
    directory = validate_key(key)
    path = directory/'result.mp4'
    state = directory/'state.json'
    if not path.exists() or not state.exists() or json.loads(state.read_text())['status']!='completed':
        raise HTTPException(409,'Not complete')
    return FileResponse(path,media_type='video/mp4')
