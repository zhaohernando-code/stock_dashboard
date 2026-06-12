#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_FRONTEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.frontend.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

FRONTEND_DIR="$REPO_ROOT/frontend"
PORT="${ASHARE_LOCAL_FRONTEND_PORT:-5173}"
CODEX_ROOT="${CODEX_ROOT:-$HOME/codex}"
NODE_RESOLVER="${CODEX_NODE_RESOLVER:-$CODEX_ROOT/scripts/resolve-node-runtime.sh}"

if [[ ! -x "$NODE_RESOLVER" ]]; then
  echo "Node runtime resolver is not executable: $NODE_RESOLVER" >&2
  exit 1
fi

ensure_frontend_dependencies() {
  if [[ ! -f "$FRONTEND_DIR/package-lock.json" ]]; then
    echo "Frontend package-lock.json missing: $FRONTEND_DIR/package-lock.json" >&2
    exit 1
  fi

  if [[ -x "$FRONTEND_DIR/node_modules/.bin/tsc" && -x "$FRONTEND_DIR/node_modules/.bin/vite" ]]; then
    return 0
  fi

  echo "[frontend] Installing dependencies with npm ci"
  npm --prefix "$FRONTEND_DIR" ci
}

ensure_frontend_dependencies
cd "$FRONTEND_DIR"

BOOT_BUILD="${ASHARE_FRONTEND_BOOT_BUILD:-auto}"
if [[ "$BOOT_BUILD" == "1" || "$BOOT_BUILD" == "true" || ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
  npm run build
else
  echo "[frontend] Reusing existing dist; set ASHARE_FRONTEND_BOOT_BUILD=1 to force a boot-time rebuild"
fi
exec "$NODE_RESOLVER" --no-default-requirements --exec \
  "$REPO_ROOT/scripts/serve-frontend-dist.mjs" \
  --root "$FRONTEND_DIR/dist" \
  --host 127.0.0.1 \
  --port "$PORT"
