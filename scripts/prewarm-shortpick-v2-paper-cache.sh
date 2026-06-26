#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
BACKEND_ENV_HELPER="$REPO_ROOT/scripts/ashare-backend-env.sh"

if [[ "${ASHARE_SHORTPICK_V2_PAPER_CACHE_PREWARM:-1}" != "1" ]]; then
  echo "Shortpick v2 paper cache prewarm skipped by ASHARE_SHORTPICK_V2_PAPER_CACHE_PREWARM." >&2
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
export ASHARE_ARTIFACT_ROOT="${ASHARE_SHORTPICK_V2_PAPER_CACHE_PREWARM_ARTIFACT_ROOT:-$REPO_ROOT/data/runtime-artifacts}"
ashare_resolve_local_artifact_root "$REPO_ROOT"

"$PYTHON_BIN" - <<'PY'
import json
import time

from ashare_evidence.db import get_database_url, get_session_factory
from ashare_evidence.shortpick_v2_read_model import build_shortpick_v2_paper_tracking_read_model

started = time.perf_counter()
Session = get_session_factory(get_database_url())
with Session() as session:
    payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)
elapsed = time.perf_counter() - started
coverage = payload.get("paper_display", {}).get("coverage", {})
print(
    json.dumps(
        {
            "status": "ok",
            "elapsed_seconds": round(elapsed, 3),
            "replay_row_count": coverage.get("replay_row_count"),
            "coverage_end": coverage.get("coverage_end"),
            "account_curve_count": coverage.get("account_curve_count"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
PY
