"""Ground scripts in approved product copy; never invent testimonials.

Optional Ollama acts as a selector of approved copy, not an unrestricted claim
writer. This makes unattended script generation auditable and cheap.
"""
import hashlib
import json
import os
import re
import httpx


def cache_key(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_script(product, hook_index, seed, duration):
    hook = product['hooks'][hook_index % len(product['hooks'])]
    claims = list(product['claims'])
    if os.getenv('UGC_SCRIPT_PROVIDER', 'template') == 'ollama':
        r = httpx.post(os.getenv('UGC_OLLAMA_URL', 'http://localhost:11434') + '/api/generate',
            json=dict(model=os.getenv('UGC_OLLAMA_MODEL', 'qwen2.5:3b'), stream=False, format='json',
                options=dict(seed=seed, temperature=.4, num_predict=120),
                prompt='Choose the most relevant claim indices for this audience. Return JSON {"indices":[0,1]}. '
                       'Only select existing claims. Audience: ' + product['audience'] + '\nClaims: ' + json.dumps(claims)), timeout=180)
        r.raise_for_status()
        indices = json.loads(r.json()['response'])['indices']
        selected = [claims[i] for i in indices if isinstance(i, int) and 0 <= i < len(claims)]
        if selected:
            claims = list(dict.fromkeys(selected))
    # Keep scripts short enough for a natural read; measured speech is the final clock.
    limit = int(duration * 2.2)
    sentences = [hook, product['name'] + '.']
    for claim in claims:
        if len(' '.join(sentences + [claim, product['cta']]).split()) <= limit:
            sentences.append(claim.rstrip('.!?') + '.')
    sentences.append(product['cta'])
    script = ' '.join(sentences)
    for forbidden in product.get('forbidden_claims', []):
        if forbidden.lower() in script.lower():
            raise ValueError(f'Script contains blocked wording: {forbidden}')
    return dict(text=script, sentences=sentences, hook=hook, claims_used=[x for x in claims if x in script],
        disclosure='AI-generated spokesperson and voice. Product details supplied by the brand.',
        shot_plan=[dict(kind='creator', start=0, fraction=.45), dict(kind='product', fraction=.35), dict(kind='cta', fraction=.20)])


def caption_chunks(text, duration):
    words = text.split()
    chunks = [' '.join(words[i:i+5]) for i in range(0, len(words), 5)]
    weights = [len(c.split()) for c in chunks]
    total = sum(weights) or 1
    start = 0
    cues = []
    for chunk, weight in zip(chunks, weights):
        end = start + duration * weight / total
        cues.append(dict(start=round(start, 3), end=round(end, 3), text=chunk))
        start = end
    return cues


def caption_text(value):
    # ASS control codes and newlines must never come from product copy.
    return re.sub(r'[{}\\\r\n]', ' ', value)


def draft_hooks(name, claims):
    """Original hook structures containing only supplied factual assertions.

    These are drafts for brand review; no synthetic personal testimonial or
    performance promise is added. The pipeline later uses the saved copy.
    """
    hooks = [f"Let's take a closer look at {name}.", f"The details matter. Meet {name}.",
             f"Thinking about {name}? Start here.", f"Here's a quick look at {name}."]
    for claim in claims[:8]:
        fact = claim.strip().rstrip('.!?')
        hooks += [f'{fact}. Take a closer look.', f'A detail to know: {fact}.']
    return list(dict.fromkeys(h for h in hooks if len(h)<=250))


def draft_creator():
    import random
    rng = random.SystemRandom()
    names = [('Maya','af_heart'),('Jordan','am_michael'),('Riley','af_bella'),('Noah','am_liam'),('Casey','af_nicole'),('Sam','am_adam'),('Avery','af_sarah'),('Morgan','af_sky')]
    name, voice = rng.choice(names)
    hair = rng.choice(['short dark curly hair','shoulder-length wavy brown hair','short sandy hair','long dark braids','short auburn hair'])
    setting = rng.choice(['a bright home kitchen','a relaxed living room','a tidy home studio','a home entryway with soft daylight'])
    outfit = rng.choice(['a neutral cotton t-shirt','a casual denim overshirt','a simple linen shirt','a muted green sweater'])
    age = rng.choice(['late 20s','early 30s','late 30s','early 40s','late 40s'])
    return dict(name=name,description=f'Original fictional adult creator in their {age}, {hair}, wearing {outfit}, in {setting}. Warm conversational expression, realistic skin texture, natural window light, candid smartphone head-and-shoulders portrait, looking toward camera. No logos, no text.',voice=voice,
        reference_asset_id=None,rights='Original fictional synthetic persona',color=rng.choice(['#ddb6fe','#a6d9f5','#f7bf86','#b8d8ad']),generated=True)
