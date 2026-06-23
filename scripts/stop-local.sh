#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/.run"

if [[ "$(uname -s)" == "Darwin" ]]; then
  screen -S quantpartner-web -X quit 2>/dev/null || true
  screen -S quantpartner-api -X quit 2>/dev/null || true
  # screen 退出后，某些 npm/uvicorn 子进程可能已经脱离会话；按本项目端口兜底停止。
  for port in 3000 8000; do
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  done
  for _ in {1..20}; do
    if ! lsof -tiTCP:3000 -sTCP:LISTEN >/dev/null 2>&1 && ! lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
else
  for service in web api; do
    pid_file="$RUN_DIR/$service.pid"
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file")"
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
      fi
      rm -f "$pid_file"
    fi
  done
fi

echo "QuantPartner local services stopped."
