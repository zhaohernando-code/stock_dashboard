#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

VENV_PATH="${ASHARE_LOCAL_VENV_PATH:-$REPO_ROOT/.venv-mac}"
PORT="${ASHARE_LOCAL_BACKEND_PORT:-8000}"
ARTIFACT_ROOT_HELPER="$REPO_ROOT/scripts/ashare-artifact-root.sh"

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi

# shellcheck source=scripts/ashare-artifact-root.sh
source "$ARTIFACT_ROOT_HELPER"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export ASHARE_DATABASE_URL="${ASHARE_DATABASE_URL:-sqlite:///$REPO_ROOT/data/ashare_dashboard.db}"
ashare_resolve_local_artifact_root "$REPO_ROOT"

exec "$VENV_PATH/bin/python" -m uvicorn ashare_evidence.api:app --host 127.0.0.1 --port "$PORT"
