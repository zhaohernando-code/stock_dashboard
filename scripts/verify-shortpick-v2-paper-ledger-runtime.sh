#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
BACKEND_ENV_HELPER="$REPO_ROOT/scripts/ashare-backend-env.sh"

# shellcheck source=scripts/ashare-backend-env.sh
source "$BACKEND_ENV_HELPER"
ashare_source_backend_env "$ENV_FILE"

VENV_PATH="${ASHARE_LOCAL_VENV_PATH:-$REPO_ROOT/.venv-mac}"
PYTHON_BIN="$VENV_PATH/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi

API_BASE_URL="${ASHARE_API_BASE_URL:-http://127.0.0.1:8000}"
API_TIMEOUT_SECONDS="${ASHARE_SHORTPICK_V2_PAPER_LEDGER_API_TIMEOUT_SECONDS:-60}"
FULL_API_MAX_SECONDS="${ASHARE_SHORTPICK_V2_PAPER_FULL_API_MAX_SECONDS:-10}"
MIN_TRUE_FORWARD_SIGNAL_DATE="${ASHARE_SHORTPICK_V2_PAPER_LEDGER_MIN_SIGNAL_DATE:-2026-06-16}"
WORK_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

curl -fsSL --max-time "$API_TIMEOUT_SECONDS" "$API_BASE_URL/health" -o "$WORK_DIR/health.json"
curl -fsSL --max-time "$API_TIMEOUT_SECONDS" \
  "$API_BASE_URL/shortpick-lab-v2/paper-tracking/summary" \
  -o "$WORK_DIR/summary.json"
FULL_API_SECONDS="$(
  curl -fsSL --max-time "$API_TIMEOUT_SECONDS" \
  -w "%{time_total}" \
  "$API_BASE_URL/shortpick-lab-v2/paper-tracking" \
  -o "$WORK_DIR/paper-tracking.json"
)"

"$PYTHON_BIN" - \
  "$WORK_DIR/summary.json" \
  "$WORK_DIR/paper-tracking.json" \
  "$MIN_TRUE_FORWARD_SIGNAL_DATE" \
  "$FULL_API_SECONDS" \
  "$FULL_API_MAX_SECONDS" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
full = json.load(open(sys.argv[2], encoding="utf-8"))
min_true_forward_signal_date = sys.argv[3]
full_api_seconds = float(sys.argv[4])
full_api_max_seconds = float(sys.argv[5])
allowed_config_ids = {
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1",
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1",
}

ledger_ref = (summary.get("source_artifacts") or {}).get("paper_ledger") or {}
summary_counts = summary.get("summary") or {}
coverage = summary.get("coverage") or (summary.get("paper_display") or {}).get("coverage") or {}
records = full.get("records") or []

if ledger_ref.get("artifact_family") != "shortpick_v2_paper_tracking_ledger":
    raise SystemExit(f"unexpected paper ledger source: {ledger_ref}")
if ledger_ref.get("status") == "missing":
    raise SystemExit(f"paper ledger source is missing: {ledger_ref}")
if int(summary_counts.get("record_count") or 0) <= 0:
    raise SystemExit(f"expected nonzero record_count, got {summary_counts}")
true_forward_record_count = coverage.get("true_forward_record_count")
if true_forward_record_count is None:
    true_forward_record_count = summary_counts.get("true_forward_record_count")
if int(true_forward_record_count or 0) <= 0:
    raise SystemExit(f"expected true-forward records, got summary={summary_counts}, coverage={coverage}")
if not records:
    raise SystemExit("full paper tracking payload returned no records")
if full_api_seconds > full_api_max_seconds:
    raise SystemExit(
        f"full paper tracking API exceeded latency threshold: "
        f"{full_api_seconds:.3f}s > {full_api_max_seconds:.3f}s"
    )

for record in records:
    config_id = record.get("config_id")
    if config_id not in allowed_config_ids:
        raise SystemExit(f"unexpected v2 paper config_id: {record}")
    if record.get("evidence_basis") != "true_forward_tracking":
        raise SystemExit(f"record evidence_basis is not true_forward_tracking: {record}")
    if record.get("decision_action") not in {"buy_primary", "buy_fallback", "skip"}:
        raise SystemExit(f"unexpected decision action: {record}")
    if str(record.get("signal_date") or "") < min_true_forward_signal_date:
        raise SystemExit(f"record before H10 governance true-forward boundary: {record}")

print(
    json.dumps(
        {
            "status": "ok",
            "record_count": summary_counts.get("record_count"),
            "true_forward_record_count": coverage.get("true_forward_record_count"),
            "full_api_seconds": round(full_api_seconds, 3),
            "full_api_max_seconds": full_api_max_seconds,
            "ledger_path": ledger_ref.get("path"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
PY
