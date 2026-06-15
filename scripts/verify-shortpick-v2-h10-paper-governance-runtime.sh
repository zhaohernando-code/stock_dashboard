#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
API_BASE_URL="${ASHARE_LOCAL_API_BASE_URL:-http://127.0.0.1:8000}"
PUBLISH_REFRESH_MODE="${ASHARE_PUBLISH_REFRESH_MODE:-skip}"
PUBLISH_VERIFY_MODE="${ASHARE_PUBLISH_VERIFY_MODE:-canonical}"

if [[ "$PUBLISH_REFRESH_MODE" != "skip" ]]; then
  echo "Refusing runtime verification with ASHARE_PUBLISH_REFRESH_MODE=$PUBLISH_REFRESH_MODE; W-004 requires skip." >&2
  exit 1
fi

step() {
  printf '[h10-paper-governance-runtime] %s\n' "$*"
}

step "Running default fast pytest"
"$PYTHON_BIN" -m pytest -q

step "Running policy audit"
PYTHONPATH=src "$PYTHON_BIN" -m ashare_evidence.cli policy-audit \
  --fail-on-new-unclassified \
  --fail-on-direct-config-read \
  --fail-on-formula-side-effects \
  --fail-on-missing-config-lineage

step "Checking committed clean worktree before publish"
DIRTY_STATUS="$(git status --short --untracked-files=normal)"
if [[ -n "$DIRTY_STATUS" ]]; then
  echo "Refusing runtime verification from a dirty worktree. Commit changes first." >&2
  echo "$DIRTY_STATUS" >&2
  exit 1
fi

step "Publishing local runtime"
ASHARE_PUBLISH_REFRESH_MODE="$PUBLISH_REFRESH_MODE" \
ASHARE_PUBLISH_VERIFY_MODE="$PUBLISH_VERIFY_MODE" \
  bash scripts/publish-local-runtime.sh

step "Verifying served shortpick v2 paper-tracking summary"
SUMMARY_PAYLOAD="$(curl -fsS "$API_BASE_URL/shortpick-lab-v2/paper-tracking/summary")"
ASHARE_H10_PAPER_GOVERNANCE_SUMMARY_PAYLOAD="$SUMMARY_PAYLOAD" "$PYTHON_BIN" - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["ASHARE_H10_PAPER_GOVERNANCE_SUMMARY_PAYLOAD"])
summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
records = payload.get("records") if isinstance(payload.get("records"), list) else []
governance = payload.get("paper_governance") or payload.get("governance") or {}
if not isinstance(governance, dict):
    raise SystemExit("paper governance payload is missing or not an object")

record_count = summary.get("record_count", len(records))
if record_count != 0 or records:
    raise SystemExit(f"expected zero true-forward paper rows, got record_count={record_count}, records={len(records)}")

status = governance.get("status") or governance.get("recommendation_status")
if status != "forward_observation_ready_with_open_risks":
    raise SystemExit(f"unexpected governance status: {status!r}")

paper_status = governance.get("paper_tracking_status")
if paper_status != "not_started_no_true_forward_rows":
    raise SystemExit(f"unexpected paper tracking status: {paper_status!r}")

candidate_ids = set(governance.get("selected_config_ids") or governance.get("candidate_config_ids") or [])
required = {
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1",
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1",
}
if candidate_ids != required:
    raise SystemExit(
        "unexpected h10 governance candidates: "
        f"expected={sorted(required)}, actual={sorted(candidate_ids)}"
    )

fixed90 = "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1"
if fixed90 in candidate_ids:
    raise SystemExit("fixed90 must not appear in served candidate ids")

diagnostic_ids = set(governance.get("diagnostic_rejected_config_ids") or [])
if fixed90 not in diagnostic_ids:
    raise SystemExit("fixed90 diagnostic rejection is missing")

print("served paper governance verification passed")
PY

step "Done"
