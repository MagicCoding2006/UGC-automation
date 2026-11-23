import json
import os
import time
from itertools import product as cartesian
from . import config, db
from .registry import MODELS
from .schemas import Batch
from .creative import cache_key


def quote(spec):
    costs = []
    for model_id in spec.models:
        model = MODELS[model_id]
        speech = 0 if model_id == 'demo' else .03
        unit = spec.duration * model['rate'] * 1.2 + speech
        if model_id == 'infinitetalk':
            unit += float(os.getenv('UGC_GPU_HOURLY', '.75'))
        if model_id == 'wan-local':
            unit += float(os.getenv('UGC_LOCAL_HOURLY', '.10'))
        costs.append(unit)
    # Deliberately conservative: assumes every selected model is the most expensive.
    first_pass = max(costs) * spec.count + (.02 * len(spec.creator_ids) if any(MODELS[m]['type']=='talking' for m in spec.models) else 0)
    return dict(first_pass=round(first_pass, 2), with_retries=round(first_pass*config.MAX_ATTEMPTS, 2),
        billing='Planning estimates; failed attempts and shared assets are charged to the first batch using them.',
        warnings=['Duplicate combinations will reuse cached generation.' ] if spec.count > 100 else [])


def make_batch(spec: Batch, idempotency=None):
    batch_id = idempotency or db.uid('batch_')
    existing = db.one('SELECT * FROM batches WHERE id=?', (batch_id,))
    if existing:
        if existing['spec'] != spec.model_dump():
            raise ValueError('Idempotency key already belongs to a different batch request')
        return existing
    product = db.one('SELECT * FROM products WHERE id=?', (spec.product_id,))
    if not product:
        raise ValueError('Product not found')
    creators = [db.one('SELECT * FROM creators WHERE id=?', (id,)) for id in spec.creator_ids]
    if not all(creators):
        raise ValueError('Creator not found')
    assets = [db.one('SELECT * FROM assets WHERE id=?', (id,)) for id in spec.asset_ids]
    if any(not a or not a['approved'] or a['product_id'] != spec.product_id for a in assets):
        raise ValueError('Each source asset must be approved for this product')
    if any(m == 'remix' for m in spec.models) and not assets:
        raise ValueError('Remix needs at least one approved product image or video')
    if config.MODE == 'demo' and any(m != 'demo' for m in spec.models):
        raise ValueError('Demo mode permits only the preview renderer. Set UGC_MODE=production for real providers.')
    for m in spec.models:
        if m.startswith('fabric') and not os.getenv('FAL_KEY'):
            raise ValueError('FAL_KEY is missing')
        if m == 'wan-local' and not os.getenv('UGC_COMFY_URL'):
            raise ValueError('UGC_COMFY_URL is missing')
        if m == 'infinitetalk' and not os.getenv('UGC_AVATAR_URL') and os.getenv('UGC_AVATAR_TRANSPORT')!='runpod':
            raise ValueError('UGC_AVATAR_URL is missing')
        if MODELS[m]['type'] == 'talking' and not os.getenv('FAL_KEY') and any(not c['data'].get('reference_asset_id') for c in creators):
            raise ValueError('Upload creator reference portraits or set FAL_KEY to generate them')
    if spec.experiment not in ('model', 'mixed') and len(spec.models) > 1:
        raise ValueError('Choose a model experiment or mixed exploration to compare multiple models')
    estimate = quote(spec)
    if spec.budget < estimate['first_pass']:
        raise ValueError(f'Batch cap must cover the conservative first-pass quote (${estimate["first_pass"]:.2f})')
    hooks = len(product['data']['hooks'])
    combos = list(cartesian(range(hooks), range(len(creators)), spec.models)) if spec.experiment == 'mixed' else None
    now = time.time()
    with db.connection(True) as c:
        concurrent_existing = c.execute('SELECT * FROM batches WHERE id=?',(batch_id,)).fetchone()
        if concurrent_existing:
            previous = db.decode(concurrent_existing)
            if previous['spec'] != spec.model_dump():
                raise ValueError('Idempotency key already belongs to a different batch request')
            return previous
        c.execute('INSERT INTO batches VALUES(?,?,?,?,?,?)', (batch_id, spec.name, spec.product_id, spec.model_dump_json(), spec.budget, now))
        for i in range(spec.count):
            hook, creator_idx, model_id, replicate = spec.hook_index % hooks, 0, spec.models[0], i
            if spec.experiment == 'hook':
                hook, replicate = (spec.hook_index+i) % hooks, i // hooks
            elif spec.experiment == 'creator':
                creator_idx, replicate = i % len(creators), i // len(creators)
            elif spec.experiment == 'model':
                model_id, replicate = spec.models[i % len(spec.models)], i // len(spec.models)
                hook = (spec.hook_index + replicate) % hooks
            elif combos:
                hook, creator_idx, model_id = combos[i % len(combos)]
                replicate = i // len(combos)
            payload = dict(product=product['data'], product_id=spec.product_id,
                creator=creators[creator_idx]['data'], creator_id=creators[creator_idx]['id'],
                model=model_id, hook_index=hook, seed=(spec.seed+replicate) % 2147483647,
                duration=spec.duration, caption_style=spec.caption_style, asset_ids=spec.asset_ids,
                experiment=spec.experiment, arm=model_id if spec.experiment=='model' else str(hook if spec.experiment=='hook' else creator_idx),
                replicate=replicate, mode=config.MODE)
            payload['model_config'] = MODELS[model_id]
            payload['qualification_key'] = cache_key(product['data'],creators[creator_idx]['data'],MODELS[model_id])
            c.execute('INSERT INTO jobs(id,batch_id,spec,created,updated) VALUES(?,?,?,?,?)',
                (db.uid('clip_'), batch_id, json.dumps(payload), now+i*.0001, now))
    return db.one('SELECT * FROM batches WHERE id=?', (batch_id,))
