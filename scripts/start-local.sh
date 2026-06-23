#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

BUNDLED_PYTHON="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/backend/.venv/bin/python"
elif [[ -x "$BUNDLED_PYTHON" ]]; then
  PYTHON_BIN="$BUNDLED_PYTHON"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if [[ ! -d "$ROOT/frontend/.next" ]]; then
  (cd "$ROOT/frontend" && npm run build)
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    screen -S quantpartner-api -X quit 2>/dev/null || true
    screen -dmS quantpartner-api /bin/bash -lc "exec '$ROOT/scripts/run-api.sh' >>'$RUN_DIR/api.log' 2>&1"
  fi
  if ! curl -fsS http://127.0.0.1:3000 >/dev/null 2>&1; then
    screen -S quantpartner-web -X quit 2>/dev/null || true
    screen -dmS quantpartner-web /bin/bash -lc "exec '$ROOT/scripts/run-web.sh' >>'$RUN_DIR/web.log' 2>&1"
  fi
else
  if [[ ! -f "$RUN_DIR/api.pid" ]] || ! kill -0 "$(cat "$RUN_DIR/api.pid")" 2>/dev/null; then
    (cd "$ROOT/backend" && nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >"$RUN_DIR/api.log" 2>&1 & echo $! >"$RUN_DIR/api.pid")
  fi
  if [[ ! -f "$RUN_DIR/web.pid" ]] || ! kill -0 "$(cat "$RUN_DIR/web.pid")" 2>/dev/null; then
    (cd "$ROOT/frontend" && nohup npm start -- --hostname 127.0.0.1 >"$RUN_DIR/web.log" 2>&1 & echo $! >"$RUN_DIR/web.pid")
  fi
fi

for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:3000 >/dev/null 2>&1; then
    echo "QuantPartner is running:"
    echo "  Web: http://127.0.0.1:3000"
    echo "  API: http://127.0.0.1:8000/docs"
    exit 0
  fi
  sleep 0.5
done

echo "QuantPartner failed to start. Recent logs:" >&2
tail -n 30 "$RUN_DIR/api.log" "$RUN_DIR/web.log" >&2 || true
exit 1
