#!/usr/bin/env bash
set -euo pipefail
python /opt/download_models.py
exec python main.py --listen 0.0.0.0 --port 8188 --lowvram --cpu-vae --disable-auto-launch --disable-all-custom-nodes --preview-method none
