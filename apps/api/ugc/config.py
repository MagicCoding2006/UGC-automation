import os
import math
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / '.env')
DATA = Path(os.getenv('UGC_DATA_DIR', str(ROOT / 'data'))).resolve()
MEDIA = DATA / 'media'
DB = DATA / 'ugc.sqlite3'
MODE = os.getenv('UGC_MODE', 'demo')
TOKEN = os.getenv('UGC_TOKEN', '')
DAILY_BUDGET = float(os.getenv('UGC_DAILY_BUDGET', '25'))
MAX_ATTEMPTS = int(os.getenv('UGC_MAX_ATTEMPTS', '2'))
RESOLUTION = int(os.getenv('UGC_RENDER_RESOLUTION', '720'))
AUTO_APPROVE = os.getenv('UGC_AUTO_APPROVE', 'false').lower() == 'true'
SECURE_COOKIE = os.getenv('UGC_SECURE_COOKIE', 'false').lower() == 'true'
WORKER_TOKEN = os.getenv('UGC_WORKER_TOKEN', '')
if MODE not in ('demo', 'production'):
    raise RuntimeError('UGC_MODE must be demo or production')
for variable,allowed in [('UGC_TTS_PROVIDER',('fal','local')),('UGC_SCRIPT_PROVIDER',('template','ollama')),('UGC_AVATAR_TRANSPORT',('http','runpod'))]:
    value = os.getenv(variable)
    if value and value not in allowed:
        raise RuntimeError(variable+' must be one of '+', '.join(allowed))
if not math.isfinite(DAILY_BUDGET) or DAILY_BUDGET<0:
    raise RuntimeError('UGC_DAILY_BUDGET must be a nonnegative finite amount')
if not 1<=MAX_ATTEMPTS<=10:
    raise RuntimeError('UGC_MAX_ATTEMPTS must be 1–10')
for directory in (DATA, MEDIA):
    directory.mkdir(parents=True, exist_ok=True)
