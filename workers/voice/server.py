"""CPU Kokoro service: no GPU allocation and no concurrent model loads."""
import hashlib
import hmac
import json
import os
import re
import threading
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title='ReelForge voice worker')
lock = threading.Lock()
pipeline = None
out = Path(os.getenv('OUTPUT_DIR', '/outputs'))
out.mkdir(parents=True, exist_ok=True)
VOICES = {'af_heart','af_bella','af_nicole','af_sarah','af_sky','am_adam','am_michael','am_liam'}


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    voice: str = 'af_heart'
    key: str = Field(pattern='^[a-f0-9]{64}$')


def auth(value):
    token = os.getenv('UGC_WORKER_TOKEN', '')
    if not token or not hmac.compare_digest(value.encode(), ('Bearer '+token).encode()):
        raise HTTPException(401, 'Worker token required')


@app.get('/health')
def health():
    return dict(ok=True, model_loaded=pipeline is not None, device='cpu')


@app.post('/speech')
def speech(body: Speech, authorization: str = Header(default='')):
    auth(authorization)
    if body.voice not in VOICES:
        raise HTTPException(400,'Unknown voice')
    global pipeline
    fingerprint = hashlib.sha256(json.dumps([body.text,body.voice]).encode()).hexdigest()
    # Use payload hash for the disk cache; a client cannot reuse a key for another script.
    path = out/(fingerprint+'.wav')
    with lock:
        if not path.exists():
            import numpy as np
            import soundfile as sf
            import torch
            from kokoro import KPipeline
            torch.set_num_threads(int(os.getenv('VOICE_THREADS', '4')))
            if pipeline is None:
                pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', device='cpu')
            parts = [audio.cpu().numpy() for _, _, audio in pipeline(body.text, voice=body.voice, speed=1)]
            if not parts:
                raise HTTPException(422,'No speech generated')
            temp = path.with_suffix('.tmp.wav')
            sf.write(temp,np.concatenate(parts),24000)
            temp.replace(path)
    return FileResponse(path,media_type='audio/wav')
