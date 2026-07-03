#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs"
BACKEND_LOG="$LOG_DIR/dev-backend.log"
FRONTEND_LOG="$LOG_DIR/dev-frontend.log"

mkdir -p "$LOG_DIR"

if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "WARN: .env not found. Copying .env.example to .env for local development."
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

OVERRIDE_BACKEND_HOST="${BACKEND_HOST:-}"
OVERRIDE_BACKEND_PORT="${BACKEND_PORT:-}"
OVERRIDE_FRONTEND_HOST="${FRONTEND_HOST:-}"
OVERRIDE_FRONTEND_PORT="${FRONTEND_PORT:-}"
OVERRIDE_FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-}"
OVERRIDE_VITE_API_BASE_URL="${VITE_API_BASE_URL:-}"
OVERRIDE_PYTHON_BIN="${PYTHON_BIN:-}"
OVERRIDE_PNPM_BIN="${PNPM_BIN:-}"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export BACKEND_HOST="${OVERRIDE_BACKEND_HOST:-${BACKEND_HOST:-0.0.0.0}}"
export BACKEND_PORT="${OVERRIDE_BACKEND_PORT:-${BACKEND_PORT:-8000}}"
export FRONTEND_HOST="${OVERRIDE_FRONTEND_HOST:-${FRONTEND_HOST:-0.0.0.0}}"
export FRONTEND_PORT="${OVERRIDE_FRONTEND_PORT:-${FRONTEND_PORT:-5173}}"
export FRONTEND_ORIGIN="${OVERRIDE_FRONTEND_ORIGIN:-${FRONTEND_ORIGIN:-http://localhost:${FRONTEND_PORT}}}"
export VITE_API_BASE_URL="${OVERRIDE_VITE_API_BASE_URL:-${VITE_API_BASE_URL:-http://localhost:${BACKEND_PORT}/api}}"
export PYTHON_BIN="${OVERRIDE_PYTHON_BIN:-${PYTHON_BIN:-python}}"
export PNPM_BIN="${OVERRIDE_PNPM_BIN:-${PNPM_BIN:-}}"

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
  exit "$status"
}

trap cleanup EXIT INT TERM

: > "$BACKEND_LOG"
: > "$FRONTEND_LOG"

echo "Starting backend..."
"$ROOT_DIR/scripts/dev-backend.sh" >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

echo "Starting frontend..."
"$ROOT_DIR/scripts/dev-frontend.sh" >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

echo
echo "Narraverse Engine is starting."
echo "Frontend: http://localhost:${FRONTEND_PORT:-5173}"
echo "Backend:  http://localhost:${BACKEND_PORT:-8000}/api"
echo "Docs:     http://localhost:${BACKEND_PORT:-8000}/docs"
echo
echo "Logs:"
echo "  Backend:  $BACKEND_LOG"
echo "  Frontend: $FRONTEND_LOG"
echo
echo "Press Ctrl+C to stop both services."

while true; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Backend process exited. Last log lines:"
    tail -n 40 "$BACKEND_LOG" || true
    exit 1
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "Frontend process exited. Last log lines:"
    tail -n 40 "$FRONTEND_LOG" || true
    exit 1
  fi
  sleep 1
done
