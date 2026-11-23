"""RunPod Serverless adapter; same model invocation as the HTTP worker."""
import base64
import json
import re
import time
from pathlib import Path
import runpod
from server import ROOT, infer


def handler(event):
    data = event['input']
    key = data['key']
    if not re.fullmatch('[a-f0-9]{64}',key):
        return {'error':'Invalid generation key'}
    directory = ROOT/key
    directory.mkdir(exist_ok=True,parents=True)
    result = directory/'result.mp4'
    if not result.exists():
        image = base64.b64decode(data['image_base64'],validate=True)
        audio = base64.b64decode(data['audio_base64'],validate=True)
        if max(len(image),len(audio))>20*1024*1024:
            return {'error':'Inputs exceed 20 MB'}
        (directory/'image.png').write_bytes(image)
        (directory/'audio.wav').write_bytes(audio)
        (directory/'meta.json').write_text(json.dumps(dict(seed=int(data.get('seed',42)))))
        (directory/'input.json').write_text(json.dumps(dict(prompt='A person speaking naturally to camera, realistic expression, stable identity.',cond_video=str(directory/'image.png'),cond_audio=dict(person1=str(directory/'audio.wav')))))
        infer(directory)
    state = json.loads((directory/'state.json').read_text())
    if state['status']!='completed':
        return {'error':state.get('error','Generation failed')}
    return dict(video_base64=base64.b64encode(result.read_bytes()).decode(),runtime_seconds=state.get('runtime_seconds',0))


runpod.serverless.start({'handler':handler})
