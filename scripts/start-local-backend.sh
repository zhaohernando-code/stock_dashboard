#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
BACKEND_ENV_HELPER="$REPO_ROOT/scripts/ashare-backend-env.sh"

# shellcheck source=scripts/ashare-backend-env.sh
source "$BACKEND_ENV_HELPER"
ashare_source_backend_env "$ENV_FILE"

VENV_PATH="${ASHARE_LOCAL_VENV_PATH:-$REPO_ROOT/.venv-mac}"
PORT="${ASHARE_LOCAL_BACKEND_PORT:-8000}"
ARTIFACT_ROOT_HELPER="$REPO_ROOT/scripts/ashare-artifact-root.sh"
FORCE_OPERATIONS_PREWARM="${ASHARE_LOCAL_FORCE_OPERATIONS_RESPONSE_PREWARM:-1}"

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi

# shellcheck source=scripts/ashare-artifact-root.sh
source "$ARTIFACT_ROOT_HELPER"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export ASHARE_DATABASE_URL="${ASHARE_DATABASE_URL:-sqlite:///$REPO_ROOT/data/ashare_hot.db}"
ashare_resolve_local_artifact_root "$REPO_ROOT"
if [[ "$FORCE_OPERATIONS_PREWARM" != "0" ]]; then
  export ASHARE_DISABLE_OPERATIONS_RESPONSE_PREWARM=0
  export ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE="${ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE:-sync}"
fi

exec "$VENV_PATH/bin/python" -m uvicorn ashare_evidence.api:app --host 127.0.0.1 --port "$PORT"
