#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:8000/api}"

if [ -n "${PNPM_BIN:-}" ]; then
  exec "$PNPM_BIN" dev
fi

if command -v pnpm >/dev/null 2>&1; then
  exec pnpm dev
fi

if [ -f "$ROOT_DIR/.codex-tools/pnpm-11.5.1/bin/pnpm.cjs" ]; then
  exec node "$ROOT_DIR/.codex-tools/pnpm-11.5.1/bin/pnpm.cjs" dev
fi

echo "pnpm 未安装。请先运行 corepack enable && corepack prepare pnpm@11.5.1 --activate，或设置 PNPM_BIN。" >&2
exit 1
