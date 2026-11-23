"""Create local config without printing or replacing existing secrets."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
env = root / '.env'
if not env.exists():
    env.write_text((root/'.env.example').read_text())
text = env.read_text()
lines = []
for line in text.splitlines():
    if line in ('UGC_TOKEN=', 'UGC_WORKER_TOKEN='):
        line += secrets.token_hex(32)
    lines.append(line)
env.write_text('\n'.join(lines)+'\n')
env.chmod(0o600)
print('Workspace configuration ready. Secrets are stored in .env and were not printed.')
