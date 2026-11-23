#!/usr/bin/env bash
set -euo pipefail
if [ -n "${RUNPOD_VOLUME_PATH:-}" ]; then
  mkdir -p "$RUNPOD_VOLUME_PATH/models" "$RUNPOD_VOLUME_PATH/cache"
  ln -sfn "$RUNPOD_VOLUME_PATH/models" /models
  ln -sfn "$RUNPOD_VOLUME_PATH/cache" /cache
fi
if [ "${AVATAR_SERVERLESS:-false}" != true ] && [ -z "${UGC_WORKER_TOKEN:-}" ]; then echo 'Set UGC_WORKER_TOKEN before exposing the worker.'; exit 1; fi
python /service/download_models.py
if [ "${AVATAR_SERVERLESS:-false}" = true ]; then exec python /service/runpod_handler.py; fi
exec uvicorn server:app --app-dir /service --host 0.0.0.0 --port 8092 --workers 1
