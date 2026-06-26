#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
BACKEND_ENV_HELPER="$REPO_ROOT/scripts/ashare-backend-env.sh"

if [[ "${ASHARE_SHORTPICK_V2_PAPER_LEDGER_REFRESH:-1}" != "1" ]]; then
  echo "Shortpick v2 paper ledger refresh skipped by ASHARE_SHORTPICK_V2_PAPER_LEDGER_REFRESH." >&2
  exit 0
fi

# shellcheck source=scripts/ashare-backend-env.sh
source "$BACKEND_ENV_HELPER"
ashare_source_backend_env "$ENV_FILE"

VENV_PATH="${ASHARE_LOCAL_VENV_PATH:-$REPO_ROOT/.venv-mac}"
PYTHON_BIN="$VENV_PATH/bin/python"
ARTIFACT_ROOT_HELPER="$REPO_ROOT/scripts/ashare-artifact-root.sh"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi

# shellcheck source=scripts/ashare-artifact-root.sh
source "$ARTIFACT_ROOT_HELPER"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export ASHARE_DATABASE_URL="${ASHARE_DATABASE_URL:-sqlite:///$REPO_ROOT/data/ashare_hot.db}"
ashare_resolve_local_artifact_root "$REPO_ROOT"

OUTPUT_PATH="${ASHARE_SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT:-$REPO_ROOT/output/shortpick-v2-paper-tracking-ledger.json}"

"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-paper-ledger-refresh \
  --database-url "$ASHARE_DATABASE_URL" \
  --output "$OUTPUT_PATH" \
  "$@"
