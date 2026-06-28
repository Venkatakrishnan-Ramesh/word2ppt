#!/usr/bin/env bash
# Start word2ppt. Creates a venv on first run, installs deps, loads .env, serves.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
if [[ ! -d "$VENV" ]]; then
  echo "→ Creating virtual environment…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r requirements.txt
fi

# Load .env if present (export every KEY=VALUE line).
if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
echo "→ Serving on http://${HOST}:${PORT}"
exec "$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" "$@"
