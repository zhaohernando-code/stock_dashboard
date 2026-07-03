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
PYTHON_BIN="$VENV_PATH/bin/python"
ARTIFACT_ROOT_HELPER="$REPO_ROOT/scripts/ashare-artifact-root.sh"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi

# shellcheck source=scripts/ashare-artifact-root.sh
source "$ARTIFACT_ROOT_HELPER"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export ASHARE_DATABASE_URL="${ASHARE_DATABASE_URL:-sqlite:///$REPO_ROOT/data/ashare_dashboard.db}"
ashare_resolve_local_artifact_root "$REPO_ROOT"

API_BASE_URL="${ASHARE_API_BASE_URL:-http://127.0.0.1:8000}"
PAPER_TRACKING_API_TIMEOUT_SECONDS="${ASHARE_SHORTPICK_PAPER_TRACKING_API_TIMEOUT_SECONDS:-180}"
RULE_DEFINED_AT="${ASHARE_SHORTPICK_CONTROL_RULE_DEFINED_AT:-2026-06-11}"
WORK_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

PAPER_TRACKING_PATH="$WORK_DIR/paper-tracking.json"
CONTROL_PLAN_PATH="$WORK_DIR/credible-control-plan.json"

curl -fsSL \
  --max-time "$PAPER_TRACKING_API_TIMEOUT_SECONDS" \
  "$API_BASE_URL/shortpick-lab/paper-tracking" \
  -o "$PAPER_TRACKING_PATH"

"$PYTHON_BIN" -m ashare_evidence.cli shortpick-governance-credible-control-plan \
  --database-url "$ASHARE_DATABASE_URL" \
  --paper-tracking-path "$PAPER_TRACKING_PATH" \
  --rule-defined-at "$RULE_DEFINED_AT" \
  --output-path "$CONTROL_PLAN_PATH" >/dev/null

"$PYTHON_BIN" -m ashare_evidence.cli shortpick-governance-retrospective-replay \
  --database-url "$ASHARE_DATABASE_URL" \
  --request-path "$CONTROL_PLAN_PATH" \
  --paper-tracking-path "$PAPER_TRACKING_PATH" \
  --output-dir "$ASHARE_ARTIFACT_ROOT/shortpick_retrospective_replays" >/dev/null

"$PYTHON_BIN" -m ashare_evidence.cli shortpick-governance-combined-ledger-materialize \
  --database-url "$ASHARE_DATABASE_URL" \
  --artifact-root "$ASHARE_ARTIFACT_ROOT"
