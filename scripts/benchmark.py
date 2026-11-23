#!/usr/bin/env python3
"""Generate a matched model benchmark specification. Does not spend money."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--product',required=True)
p.add_argument('--creator',required=True)
p.add_argument('--models',nargs='+',default=['fabric-480','fabric-720'])
p.add_argument('--replicates',type=int,default=10)
p.add_argument('--budget',type=float,default=75)
p.add_argument('--output',type=Path,default=Path('benchmark.json'))
a=p.parse_args()
if not 1<=a.replicates*len(a.models)<=1000:
    p.error('Total clips must be 1–1000')
spec=dict(name='Matched model benchmark',product_id=a.product,creator_ids=[a.creator],models=a.models,
    count=a.replicates*len(a.models),budget=a.budget,duration=15,experiment='model',seed=104729,caption_style='bold',asset_ids=[])
a.output.write_text(json.dumps(spec,indent=2)+'\n')
print('Wrote',a.output,'— review budget and submit with scripts/ugc.py generate --spec',a.output)
