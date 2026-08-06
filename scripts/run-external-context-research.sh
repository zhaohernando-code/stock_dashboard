#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${ASHARE_LOCAL_VENV_PATH:-$REPO_ROOT/.venv-mac}"
PYTHON_BIN="$VENV_PATH/bin/python"
ARTIFACT_ROOT="${ASHARE_EXTERNAL_CONTEXT_ARTIFACT_ROOT:?ASHARE_EXTERNAL_CONTEXT_ARTIFACT_ROOT must be configured}"
PLAN_JSON="${ASHARE_EXTERNAL_CONTEXT_PLAN_JSON:-$ARTIFACT_ROOT/cninfo-full713-plan.json}"
STATE_JSON="${ASHARE_EXTERNAL_CONTEXT_STATE_JSON:-$ARTIFACT_ROOT/operations/full713-background-state.json}"
CURATION_JSON="${ASHARE_EXTERNAL_CONTEXT_CURATION_JSON:-$ARTIFACT_ROOT/official-poc/cninfo-curation-full.json}"
READINESS_JSON="${ASHARE_EXTERNAL_CONTEXT_READINESS_JSON:-$ARTIFACT_ROOT/official-poc/external-context-ablation-readiness-full.json}"
GLOBAL_AUDIT_JSON="${ASHARE_EXTERNAL_CONTEXT_GLOBAL_AUDIT_JSON:-}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi
if [[ ! -f "$PLAN_JSON" ]]; then
  echo "Missing frozen CNINFO acquisition plan at $PLAN_JSON" >&2
  exit 1
fi
if [[ -f "$STATE_JSON" ]]; then
  completed_status="$($PYTHON_BIN - "$STATE_JSON" <<'PY'
import json
import sys

try:
    status = str(json.load(open(sys.argv[1], encoding="utf-8")).get("status") or "")
except Exception:
    status = ""
print("1" if status in {"complete_cninfo_blocked_external_weight_backtest", "ready_for_external_weight_backtest"} else "0")
PY
)"
  if [[ "$completed_status" == "1" ]]; then
    echo "External-context full713 background state is already terminal: $STATE_JSON"
    exit 0
  fi
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

args=(
  research-external-context-background-run
  --plan-json "$PLAN_JSON"
  --artifact-root "$ARTIFACT_ROOT"
  --state-json "$STATE_JSON"
  --curation-output-json "$CURATION_JSON"
  --readiness-output-json "$READINESS_JSON"
  --decision-cutoff "${ASHARE_EXTERNAL_CONTEXT_DECISION_CUTOFF:-2026-05-27T23:59:59+08:00}"
  --batch-size "${ASHARE_EXTERNAL_CONTEXT_BATCH_SIZE:-100}"
  --min-request-interval-seconds "${ASHARE_EXTERNAL_CONTEXT_REQUEST_INTERVAL_SECONDS:-1.0}"
  --max-zero-progress-cycles "${ASHARE_EXTERNAL_CONTEXT_MAX_ZERO_PROGRESS_CYCLES:-12}"
  --zero-progress-backoff-seconds "${ASHARE_EXTERNAL_CONTEXT_ZERO_PROGRESS_BACKOFF_SECONDS:-60}"
)
if [[ -n "$GLOBAL_AUDIT_JSON" ]]; then
  args+=(--global-import-audit-json "$GLOBAL_AUDIT_JSON")
fi

exec /usr/bin/caffeinate -i "$PYTHON_BIN" -m ashare_evidence.cli "${args[@]}"
