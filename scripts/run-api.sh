#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLED_PYTHON="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"

if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/backend/.venv/bin/python"
elif [[ -x "$BUNDLED_PYTHON" ]]; then
  PYTHON_BIN="$BUNDLED_PYTHON"
else
  PYTHON_BIN="python3"
fi

cd "$ROOT/backend"
exec "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
