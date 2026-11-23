#!/usr/bin/env python3
"""Thin CLI over the exact API used by the UI. No third-party dependencies."""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if (ROOT/'.env').exists():
    for line in (ROOT/'.env').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1)
            os.environ.setdefault(key,value)

parser=argparse.ArgumentParser(description='ReelForge automation CLI')
parser.add_argument('--url',default=os.getenv('UGC_API_URL','http://localhost:8000'))
sub=parser.add_subparsers(dest='command',required=True)
sub.add_parser('state')
sub.add_parser('doctor')
generate=sub.add_parser('generate')
generate.add_argument('--spec',required=True,type=Path,help='Batch JSON path (generate one with scripts/benchmark.py)')
generate.add_argument('--key',help='Stable idempotency key for retries from your scheduler')
watch=sub.add_parser('watch')
watch.add_argument('batch_id')
export=sub.add_parser('export')
export.add_argument('batch_id')
export.add_argument('--output',type=Path,default=Path('exports'))
export.add_argument('--include-demo',action='store_true')
args=parser.parse_args()


def call(path,body=None,headers=None,raw=False):
    headers={'Authorization':'Bearer '+os.getenv('UGC_TOKEN',''),'Content-Type':'application/json',**(headers or {})}
    request=urllib.request.Request(args.url.rstrip('/')+'/api'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=300) as response:
            data=response.read()
            return data if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        print(e.read().decode(),file=sys.stderr)
        sys.exit(1)


if args.command=='state':
    data=call('/state')
    print(json.dumps(dict(mode=data['mode'],products=[dict(id=p['id'],name=p['data']['name']) for p in data['products']],
        creators=[dict(id=c['id'],name=c['data']['name']) for c in data['creators']],counts=data['counts'],costs=data['costs']),indent=2))
elif args.command=='doctor':
    import shutil
    data=call('/state')
    print('API: connected\nMode:',data['mode'],'\nWorkers:',len(data['workers']))
    print('Speech:',data['config']['tts'],'\nFal key configured:',data['config']['fal'])
    print('Local FFmpeg:',bool(shutil.which('ffmpeg')),'(Docker includes it)')
    for model in data['models']:
        print(model['id']+':', 'configured' if model['configured'] else 'not configured', '|',model['vram'])
elif args.command=='generate':
    data=json.loads(args.spec.read_text())
    print(json.dumps(call('/batches',data,{'Idempotency-Key':args.key} if args.key else {}),indent=2))
elif args.command=='watch':
    while True:
        data=call('/jobs?batch_id='+args.batch_id+'&limit=500')
        if data['total']>500:
            for offset in range(500,data['total'],500):
                data['items'].extend(call('/jobs?batch_id='+args.batch_id+'&limit=500&offset='+str(offset))['items'])
        counts={}
        for job in data['items']:
            counts[job['status']]=counts.get(job['status'],0)+1
        print(time.strftime('%H:%M:%S'),json.dumps(counts),flush=True)
        if not any(k in counts for k in ('queued','running')):
            break
        time.sleep(5)
elif args.command=='export':
    args.output.mkdir(parents=True,exist_ok=True)
    path=args.output/(args.batch_id+'.zip')
    path.write_bytes(call('/batches/'+args.batch_id+'/export'+('?include_demo=true' if args.include_demo else ''),raw=True))
    print(path)
