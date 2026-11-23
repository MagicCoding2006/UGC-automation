import math
from . import db


def wilson(successes, trials, z=1.96):
    if trials <= 0:
        return None
    p = successes / trials
    denom = 1 + z*z/trials
    center = (p + z*z/(2*trials))/denom
    half = z*math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials))/denom
    return [max(0, center-half), min(1, center+half)]


def report(batch_id=None):
    jobs = db.rows('SELECT id,batch_id,status,spec FROM jobs' + (' WHERE batch_id=?' if batch_id else ''), (batch_id,) if batch_id else ())
    metrics = {r['job_id']: r for r in db.rows('SELECT job_id,SUM(impressions) impressions,SUM(views) views,SUM(clicks) clicks,SUM(customers) customers,SUM(revenue) revenue,SUM(media_spend) media_spend FROM metrics GROUP BY job_id')}
    costs = {r['job_id']: r['cost'] for r in db.rows("SELECT job_id,SUM(amount) cost FROM spend WHERE state!='released' GROUP BY job_id")}
    groups = {}
    for j in jobs:
        spec = j['spec']
        # Cross-product comparisons would confound different customer economics.
        key = (spec['product_id'], spec['model'], spec['arm'] if batch_id else 'all')
        group = groups.setdefault(key, dict(product_id=spec['product_id'], product=spec['product']['name'],
            model=spec['model'], arm=spec['arm'] if batch_id else 'all', attempts=0, approved=0, failed=0,
            production_spend=0, impressions=0, views=0, clicks=0, customers=0, revenue=0, media_spend=0,
            contribution_ltv=spec['product']['price']*spec['product']['lifetime_orders']*spec['product']['contribution_margin']))
        group['attempts'] += 1
        group['approved'] += int(j['status']=='approved')
        group['failed'] += int(j['status'] in ('failed','rejected'))
        group['production_spend'] += costs.get(j['id'], 0)
        for field in ('impressions','views','clicks','customers','revenue','media_spend'):
            group[field] += metrics.get(j['id'], {}).get(field, 0)
    for g in groups.values():
        g['ctr'] = g['clicks']/g['impressions'] if g['impressions'] else None
        g['ctr_interval'] = wilson(g['clicks'], g['impressions'])
        g['click_conversion'] = g['customers']/g['clicks'] if g['clicks'] else None
        g['cac'] = (g['media_spend']+g['production_spend'])/g['customers'] if g['customers'] else None
        g['ltv_cac'] = g['contribution_ltv']/g['cac'] if g['cac'] else None
        g['max_cac'] = g['contribution_ltv']/3
        g['cost_per_approved'] = g['production_spend']/g['approved'] if g['approved'] else None
        g['expected_contribution'] = g['customers']*g['contribution_ltv']-g['production_spend']-g['media_spend']
        g['evidence'] = 'exploratory' if g['customers'] < 30 else 'descriptive; validate with controlled distribution'
    return list(groups.values())
