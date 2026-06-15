#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python}"

exec "$PYTHON_BIN" -m uvicorn --app-dir backend app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
