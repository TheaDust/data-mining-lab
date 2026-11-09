#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r task7/requirements.lock.txt
fi
if [ ! -f task7/web/dist/index.html ]; then
  (cd task7/web && npm ci --no-audit --no-fund && npm run build)
fi
exec .venv/bin/python -m uvicorn task7.api:app --host 127.0.0.1 --port "${SHANXING_PORT:-8000}"
