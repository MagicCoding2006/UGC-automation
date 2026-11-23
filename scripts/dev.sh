#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -q -r apps/api/requirements-dev.txt
(cd apps/web && npm ci --no-audit --no-fund && npm run build)
export PYTHONPATH="$PWD/apps/api"
.venv/bin/python -m ugc.worker &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM
.venv/bin/uvicorn ugc.main:app --host 127.0.0.1 --port 8000
