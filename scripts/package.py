#!/usr/bin/env python3
"""Create a portable source ZIP from Git's nonignored files; no dependencies/secrets."""
import hashlib
import subprocess
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
out=root/'artifacts'
out.mkdir(exist_ok=True)
archive=out/'reelforge-source.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name in sorted(set(filter(None,paths))):
        path=root/name
        if path.is_file() and not name.startswith(('.git/','.env/','data/','artifacts/')) and name!='.env':
            z.write(path,'ReelForge/'+name)
print(archive)
print('SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())
