import os

MODELS = {
    'demo': dict(name='Preview renderer', provider='Local CPU', type='demo', rate=0,
        description='Animated test cards + system speech. Tests the pipeline, not realistic AI footage.', vram='None', license='Project code: MIT'),
    'remix': dict(name='Product footage remix', provider='Local FFmpeg', type='edit', rate=0,
        description='Approved product footage + fresh voiceover, captions and edit. Lowest marginal cost.', vram='None', license='Your source assets'),
    'fabric-480': dict(name='Fabric · 480p', provider='fal.ai', type='talking', rate=.08,
        endpoint='veed/fabric-1.0', resolution='480p', description='Audio-driven talking portrait. Economy benchmark.', vram='Hosted', license='Provider commercial terms'),
    'fabric-720': dict(name='Fabric · 720p', provider='fal.ai', type='talking', rate=.15,
        endpoint='veed/fabric-1.0', resolution='720p', description='Audio-driven talking portrait. Quality benchmark.', vram='Hosted', license='Provider commercial terms'),
    'infinitetalk': dict(name='InfiniteTalk · self-hosted', provider='Your GPU', type='talking', rate=0,
        description='Included dedicated avatar worker. Start on a 48+ GB cloud GPU; benchmark before scaling.', vram='48+ GB recommended', license='Apache-2.0; component licenses apply'),
    'wan-local': dict(name='Wan 2.2 · 5B', provider='Your 5070 / ComfyUI', type='broll', rate=0,
        description='480×832, 81 frames, single job, CPU offload. Product B-roll + voiceover; no lip-sync.', vram='12 GB target; benchmark required', license='Wan weights: Apache-2.0; ComfyUI: GPL-3.0'),
}


def list_models():
    output = []
    for id, model in MODELS.items():
        ready = id in ('demo', 'remix') or bool(os.getenv(
            'FAL_KEY' if id.startswith('fabric') else 'UGC_AVATAR_URL' if id == 'infinitetalk' else 'UGC_COMFY_URL'))
        if id=='infinitetalk' and os.getenv('UGC_AVATAR_TRANSPORT')=='runpod':
            ready = bool(os.getenv('RUNPOD_API_KEY') and os.getenv('RUNPOD_ENDPOINT_ID'))
        output.append(dict(id=id, **model, configured=ready,
            rate_note='USD / generated second, checked 2026-11-23' if model['rate'] else 'Measured runtime × configured hourly rate; estimates until reconciled'))
    return output
