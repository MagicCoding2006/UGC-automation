import importlib.util
import io
import json
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_voice_worker_auth_and_cached_output(tmp_path,monkeypatch):
    monkeypatch.setenv('OUTPUT_DIR',str(tmp_path))
    monkeypatch.setenv('UGC_WORKER_TOKEN','secret-token')
    root=Path(__file__).resolve().parents[3]
    module=load('voice_test',root/'workers/voice/server.py')
    import hashlib
    path=tmp_path/(hashlib.sha256(json.dumps(['Hello','af_heart']).encode()).hexdigest()+'.wav')
    path.write_bytes(b'cached wav')
    with TestClient(module.app) as c:
        payload=dict(text='Hello',voice='af_heart',key='a'*64)
        assert c.post('/speech',json=payload).status_code==401
        response=c.post('/speech',json=payload,headers={'Authorization':'Bearer secret-token'})
        assert response.status_code==200
        assert response.content==b'cached wav'


def test_avatar_worker_accepts_and_deduplicates_jobs(tmp_path,monkeypatch):
    monkeypatch.setenv('OUTPUT_DIR',str(tmp_path))
    monkeypatch.setenv('UGC_WORKER_TOKEN','secret-token')
    root=Path(__file__).resolve().parents[3]
    module=load('avatar_test',root/'workers/infinitetalk/server.py')
    queued=[]
    monkeypatch.setattr(module,'enqueue',lambda p:queued.append(p))
    image=io.BytesIO()
    Image.new('RGB',(32,32)).save(image,format='PNG')
    with TestClient(module.app) as c:
        files={'image':('portrait.png',image.getvalue(),'image/png'),'audio':('voice.wav',b'wav','audio/wav')}
        payload=dict(key='b'*64,seed=42)
        assert c.post('/jobs',data=payload,files=files).status_code==401
        headers={'Authorization':'Bearer secret-token'}
        for _ in range(2):
            response=c.post('/jobs',data=payload,files=files,headers=headers)
            assert response.status_code==202
        assert len(queued)==1
        assert c.get('/jobs/'+'b'*64,headers=headers).json()['status']=='queued'
        assert c.get('/jobs/'+'b'*64+'/result',headers=headers).status_code==409
