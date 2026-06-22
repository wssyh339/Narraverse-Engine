#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Preserve CLI-env overrides before loading .env so caller can temporarily override
# values such as BACKEND_PORT/BACKEND_HOST without editing the file.
OVERRIDE_HOST="${BACKEND_HOST:-}"
OVERRIDE_PORT="${BACKEND_PORT:-}"
OVERRIDE_PYTHON_BIN="${PYTHON_BIN:-}"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

BACKEND_HOST="${OVERRIDE_HOST:-${BACKEND_HOST:-0.0.0.0}}"
BACKEND_PORT="${OVERRIDE_PORT:-${BACKEND_PORT:-8000}}"
PYTHON_BIN="${OVERRIDE_PYTHON_BIN:-${PYTHON_BIN:-python}}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: Python executable \"$PYTHON_BIN\" is not available." >&2
  exit 1
fi

if ! python - <<PY
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("0.0.0.0", int("${BACKEND_PORT}")))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
then
  echo "ERROR: Backend port ${BACKEND_PORT} is already in use." >&2
  echo "Hint: pass a free port, e.g. BACKEND_PORT=8001 ./scripts/dev-backend.sh" >&2
  exit 1
fi

exec "$PYTHON_BIN" -m uvicorn --app-dir backend app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
