#!/usr/bin/env python3
"""Consistent SQLite snapshot plus media archive; secrets excluded."""
import argparse
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('destination',type=Path)
p.add_argument('--data',type=Path,default=Path(os.getenv('UGC_DATA_DIR','data')))
a=p.parse_args()
if not (a.data/'ugc.sqlite3').exists():
    p.error('No ugc.sqlite3 in the selected data directory')
a.destination.mkdir(parents=True,exist_ok=True)
archive=a.destination/('reelforge-'+time.strftime('%Y%m%d-%H%M%S')+'.zip')
with tempfile.TemporaryDirectory() as temporary:
    snapshot=Path(temporary)/'ugc.sqlite3'
    with sqlite3.connect(a.data/'ugc.sqlite3') as source, sqlite3.connect(snapshot) as target:
        source.backup(target)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(snapshot,'ugc.sqlite3')
        for path in (a.data/'media').rglob('*'):
            if path.is_file() and not path.name.endswith(('.part','.tmp')):
                z.write(path,str(path.relative_to(a.data)))
print(archive)
