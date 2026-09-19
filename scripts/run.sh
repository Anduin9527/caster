#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f config.env ]; then set -a; source config.env; set +a; fi
exec .venv/bin/uvicorn aigc.api:app --host 127.0.0.1 --port 8189 --workers 1
