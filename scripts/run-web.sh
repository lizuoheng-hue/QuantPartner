#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.nvm/versions/node/v24.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

if command -v npm >/dev/null 2>&1; then
  NPM_BIN="$(command -v npm)"
else
  NPM_BIN="$(find -L "$HOME/.nvm/versions/node" -path '*/bin/npm' -perm -111 2>/dev/null | sort -V | tail -n 1)"
fi

if [[ -z "${NPM_BIN:-}" ]]; then
  echo "npm executable not found" >&2
  exit 1
fi

cd "$ROOT/frontend"
exec "$NPM_BIN" start -- --hostname 127.0.0.1
