#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo 'Install Docker Desktop (Windows/Mac) or Docker Engine with Compose (Linux).'; exit 1; }
if [ ! -f .env ]; then
  cp .env.example .env
  token=$(openssl rand -hex 32)
  worker_token=$(openssl rand -hex 32)
  python_cmd=$(command -v python3 || command -v python || true)
  if [ -n "$python_cmd" ]; then
    "$python_cmd" scripts/bootstrap.py
  else
    # POSIX sed path avoids requiring Python for Docker-only launches.
    sed "s/^UGC_TOKEN=$/UGC_TOKEN=$token/; s/^UGC_WORKER_TOKEN=$/UGC_WORKER_TOKEN=$worker_token/" .env > .env.tmp
    mv .env.tmp .env
  fi
  chmod 600 .env
fi
docker compose up -d --build api worker
echo 'ReelForge is starting at http://localhost:8000'
echo 'Use the UGC_TOKEN value in .env to sign in. It stays on your machine.'
echo 'First image build can take several minutes. Logs: docker compose logs -f worker'
