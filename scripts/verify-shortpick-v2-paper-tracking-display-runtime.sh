#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$HOME/codex/runtime/projects/ashare-dashboard}"
API_BASE_URL="${ASHARE_LOCAL_API_BASE_URL:-http://127.0.0.1:8000}"
CANONICAL_BASE_URL="${ASHARE_CANONICAL_BASE_URL:-https://hernando-zhao.cn/projects/ashare-dashboard/}"
PAGE_URL="${ASHARE_VERIFY_SHORTPICK_V2_PAGE_URL:-${CANONICAL_BASE_URL%/}/?view=shortpick-v2&shortpickV2Tab=paper-tracking}"
EXPECTED_COMMIT="${ASHARE_VERIFY_EXPECTED_COMMIT:-$(git rev-parse HEAD)}"
PWCLI="${PWCLI:-$HOME/.codex/skills/playwright/scripts/playwright_cli.sh}"
API_TIMEOUT_SECONDS="${ASHARE_VERIFY_API_TIMEOUT_SECONDS:-30}"
API_PREWARM_TIMEOUT_SECONDS="${ASHARE_VERIFY_API_PREWARM_TIMEOUT_SECONDS:-120}"
BROWSER_WAIT_SECONDS="${ASHARE_VERIFY_BROWSER_WAIT_SECONDS:-45}"

API_PAYLOAD_FILE="$(mktemp)"
REPLAY_API_PAYLOAD_FILE="$(mktemp)"
PAGE_TEXT_FILE="$(mktemp)"
REPLAY_PAGE_TEXT_FILE="$(mktemp)"
CLICK_RESULT_FILE="$(mktemp)"
PLAYWRIGHT_SESSION="shortpick-v2-paper-display-$$"

cleanup() {
  PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" close >/dev/null 2>&1 || true
  rm -f "$API_PAYLOAD_FILE" "$REPLAY_API_PAYLOAD_FILE" "$PAGE_TEXT_FILE" "$REPLAY_PAGE_TEXT_FILE" "$CLICK_RESULT_FILE"
}
trap cleanup EXIT

step() {
  printf '[shortpick-v2-paper-runtime] %s\n' "$*"
}

wait_for_visible_terms() {
  local label="$1"
  local output_file="$2"
  shift 2

  local terms_file
  terms_file="$(mktemp)"
  printf '%s\n' "$@" > "$terms_file"

  local deadline=$((SECONDS + BROWSER_WAIT_SECONDS))
  while true; do
    PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" --raw eval "() => document.body.innerText" > "$output_file" || true
    if ASHARE_VERIFY_TERMS_FILE="$terms_file" ASHARE_VERIFY_TEXT_FILE="$output_file" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

text = Path(os.environ["ASHARE_VERIFY_TEXT_FILE"]).read_text(encoding="utf-8")
terms = [
    item
    for item in Path(os.environ["ASHARE_VERIFY_TERMS_FILE"]).read_text(encoding="utf-8").splitlines()
    if item
]
missing = [term for term in terms if term not in text]
raise SystemExit(1 if missing else 0)
PY
    then
      rm -f "$terms_file"
      return 0
    fi
    if (( SECONDS >= deadline )); then
      ASHARE_VERIFY_TERMS_FILE="$terms_file" ASHARE_VERIFY_TEXT_FILE="$output_file" "$PYTHON_BIN" - <<'PY' >&2
from __future__ import annotations

import os
from pathlib import Path

text = Path(os.environ["ASHARE_VERIFY_TEXT_FILE"]).read_text(encoding="utf-8")
terms = [
    item
    for item in Path(os.environ["ASHARE_VERIFY_TERMS_FILE"]).read_text(encoding="utf-8").splitlines()
    if item
]
missing = [term for term in terms if term not in text]
print(f"missing terms: {missing}")
PY
      rm -f "$terms_file"
      echo "$label did not render required terms within ${BROWSER_WAIT_SECONDS}s" >&2
      return 1
    fi
    sleep 1
  done
}

step "Checking runtime commit stamp"
COMMIT_FILE="$RUNTIME_ROOT/output/releases/latest-successful.commit"
if [[ ! -f "$COMMIT_FILE" ]]; then
  echo "Missing runtime commit stamp: $COMMIT_FILE" >&2
  exit 1
fi
RUNTIME_COMMIT="$(tr -d '[:space:]' < "$COMMIT_FILE")"
if [[ "$RUNTIME_COMMIT" != "$EXPECTED_COMMIT" ]]; then
  echo "Runtime commit mismatch: expected $EXPECTED_COMMIT, got $RUNTIME_COMMIT" >&2
  exit 1
fi

PAPER_API_URL="$API_BASE_URL/shortpick-lab-v2/paper-tracking"
step "Prewarming served v2 paper-tracking API"
curl --max-time "$API_PREWARM_TIMEOUT_SECONDS" -fsS "$PAPER_API_URL" -o "$API_PAYLOAD_FILE"
step "Fetching served v2 paper-tracking API"
curl --max-time "$API_TIMEOUT_SECONDS" -fsS "$PAPER_API_URL" -o "$API_PAYLOAD_FILE"
ASHARE_SHORTPICK_V2_API_PAYLOAD_FILE="$API_PAYLOAD_FILE" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(message)


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{label} must be a list")
    return value


def parse_iso_day(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        fail(f"{label} must be an ISO date, got {value!r}: {exc}")


payload = json.loads(Path(os.environ["ASHARE_SHORTPICK_V2_API_PAYLOAD_FILE"]).read_text(encoding="utf-8"))
display = require_dict(payload.get("paper_display"), "paper_display")
coverage = require_dict(display.get("coverage"), "paper_display.coverage")
summary = require_dict(payload.get("summary"), "summary")
table = require_dict(display.get("table"), "paper_display.table")
latest_trade = require_dict(display.get("latest_trade"), "paper_display.latest_trade")
strategy_explanation = require_dict(display.get("strategy_explanation"), "paper_display.strategy_explanation")
charts = require_list(display.get("charts"), "paper_display.charts")
rows = require_list(table.get("rows"), "paper_display.table.rows")

if display.get("title") != "试验田v2纸面追踪":
    fail(f"unexpected display title: {display.get('title')!r}")
if latest_trade.get("title") != "最新模拟交易":
    fail(f"unexpected latest trade title: {latest_trade.get('title')!r}")
if strategy_explanation.get("title") != "策略说明":
    fail(f"unexpected strategy explanation title: {strategy_explanation.get('title')!r}")
if table.get("title") != "模拟交易明细":
    fail(f"unexpected table title: {table.get('title')!r}")
chart_titles = {str(item.get("title") or "") for item in charts if isinstance(item, dict)}
if not {"覆盖情况", "动作分布"} <= chart_titles:
    fail(f"missing expected chart titles: {sorted(chart_titles)}")

start = "2026-05-08"
if coverage.get("coverage_start") != start:
    fail(f"coverage_start must be {start}, got {coverage.get('coverage_start')!r}")

available = [str(item) for item in require_list(coverage.get("available_source_signal_dates"), "available_source_signal_dates")]
covered = {str(item) for item in require_list(coverage.get("covered_signal_dates"), "covered_signal_dates")}
gaps = {str(item) for item in require_list(coverage.get("gap_signal_dates"), "gap_signal_dates")}
if not available:
    fail("available_source_signal_dates is empty; 2026-05-08 replay window is not backed by source dates")
if any(parse_iso_day(item, "available_source_signal_dates") < parse_iso_day(start, "coverage_start") for item in available):
    fail("available_source_signal_dates contains dates before 2026-05-08")

latest_available = max(available)
if coverage.get("latest_source_signal_date") != latest_available:
    fail(
        "latest_source_signal_date must equal the latest available source date: "
        f"expected {latest_available}, got {coverage.get('latest_source_signal_date')!r}"
    )
coverage_end = str(coverage.get("coverage_end") or "")
if coverage_end and parse_iso_day(coverage_end, "coverage_end") < parse_iso_day(latest_available, "latest available source date"):
    fail(f"coverage_end {coverage_end!r} is before latest available source date {latest_available!r}")

missing_dates = sorted(set(available) - (covered | gaps))
if missing_dates:
    fail(f"available source dates missing row-or-gap accounting: {missing_dates[:10]}")
if coverage.get("row_or_gap_accounting_passed") is not True:
    fail("row_or_gap_accounting_passed must be true")
if coverage.get("row_or_gap_config_accounting_passed") is not True:
    fail("row_or_gap_config_accounting_passed must be true")

replay_count = int(coverage.get("replay_row_count") or 0)
gap_count = int(coverage.get("source_gap_count") or 0)
true_forward_count = int(coverage.get("true_forward_record_count") or 0)
if replay_count + gap_count <= 0:
    fail("expected at least one replay row or source-gap row in the paper display window")
if int(summary.get("replay_record_count") or 0) != replay_count:
    fail("summary.replay_record_count must match coverage.replay_row_count")
if int(summary.get("display_source_gap_count") or 0) != gap_count:
    fail("summary.display_source_gap_count must match coverage.source_gap_count")
if int(summary.get("true_forward_record_count") or 0) != true_forward_count:
    fail("summary.true_forward_record_count must match coverage.true_forward_record_count")

if not rows:
    fail("paper_display.table.rows is empty")
if not any(isinstance(row, dict) and row.get("tracking_tag") == "回放" for row in rows):
    fail("paper_display.table.rows must include visible 回放 rows")
if true_forward_count > 0 and not any(
    isinstance(row, dict) and row.get("tracking_tag") == "真实前向" for row in rows
):
    fail("true-forward count is positive but no visible table row is tagged 真实前向")
for row in rows:
    if not isinstance(row, dict):
        fail("paper_display.table.rows contains a non-object row")
    row_signal_date = str(row.get("signal_date") or row.get("signal_date_text") or "")
    if not row_signal_date:
        fail("paper_display.table.rows contains a row without signal_date")
    if parse_iso_day(row_signal_date, "paper_display.table.rows.signal_date") < parse_iso_day(start, "coverage_start"):
        fail(f"paper_display.table.rows contains a row before {start}: {row_signal_date}")
    if row.get("tracking_tag") == "真实前向" and row.get("note") and "回放" in str(row.get("note")):
        fail("true-forward row note must not describe the row as replay")

rendered_display = json.dumps(display, ensure_ascii=False)
for forbidden in ("delay_buy", "retry_buy", "later_entry", "v2 Paper Ledger Rows"):
    if forbidden in rendered_display:
        fail(f"forbidden raw display token leaked through API display: {forbidden}")
for forbidden_key in ("config_id", "decision_action", "source_state"):
    if re.search(rf'"{forbidden_key}"\s*:', rendered_display):
        fail(f"paper_display visible projection still exposes raw key {forbidden_key}")

print(
    "served API display verification passed: "
    f"available={len(available)}, replay={replay_count}, gaps={gap_count}, true_forward={true_forward_count}"
)
PY

step "Fetching served v2 historical-replay API"
curl --max-time "$API_TIMEOUT_SECONDS" -fsS "$API_BASE_URL/shortpick-lab-v2/historical-replay?sample_limit=0" -o "$REPLAY_API_PAYLOAD_FILE"
ASHARE_SHORTPICK_V2_REPLAY_API_PAYLOAD_FILE="$REPLAY_API_PAYLOAD_FILE" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(message)


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{label} must be a list")
    return value


payload = json.loads(Path(os.environ["ASHARE_SHORTPICK_V2_REPLAY_API_PAYLOAD_FILE"]).read_text(encoding="utf-8"))
summary = require_dict(payload.get("summary"), "historical replay summary")
selected_configs = require_list(payload.get("selected_configs"), "historical replay selected_configs")
baseline_configs = require_list(payload.get("baseline_configs"), "historical replay baseline_configs")
holdout_configs = require_list(payload.get("holdout_configs"), "historical replay holdout_configs")
rejected_configs = require_list(payload.get("rejected_configs"), "historical replay rejected_configs")
if payload.get("claim_ceiling") != "research_observation":
    fail(f"historical replay claim_ceiling changed: {payload.get('claim_ceiling')!r}")
if payload.get("evidence_basis") not in {"historical_account_replay_selection", "h10_governance_summary_only"}:
    fail(f"historical replay evidence_basis changed: {payload.get('evidence_basis')!r}")
if int(summary.get("decision_sample_limit", -1)) != 0:
    fail(f"historical replay decision_sample_limit must be 0, got {summary.get('decision_sample_limit')!r}")
if int(summary.get("selected_config_count") or 0) != len(selected_configs):
    fail("historical replay selected_config_count must match selected_configs length")
if int(summary.get("baseline_config_count") or 0) != len(baseline_configs):
    fail("historical replay baseline_config_count must match baseline_configs length")
if int(summary.get("holdout_config_count") or 0) != len(holdout_configs):
    fail("historical replay holdout_config_count must match holdout_configs length")
if int(summary.get("rejected_config_count") or 0) != len(rejected_configs):
    fail("historical replay rejected_config_count must match rejected_configs length")
expected_h10 = [
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1",
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1",
]
selected_by_id = {
    str(row.get("config_id")): row
    for row in selected_configs
    if isinstance(row, dict) and row.get("config_id")
}
if list(selected_by_id) != expected_h10:
    fail(f"historical replay selected configs regressed: expected={expected_h10}, actual={list(selected_by_id)}")
champion_summary = selected_by_id[expected_h10[0]].get("summary")
shadow_summary = selected_by_id[expected_h10[1]].get("summary")
if not isinstance(champion_summary, dict) or not (2.70 <= float(champion_summary.get("total_return", -99)) <= 2.72):
    fail(f"fixed85 champion total_return regressed: {champion_summary!r}")
if not isinstance(shadow_summary, dict) or not (2.55 <= float(shadow_summary.get("total_return", -99)) <= 2.59):
    fail(f"fixed80 control total_return regressed: {shadow_summary!r}")
fixed90 = "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1"
diagnostic = [
    row for row in holdout_configs
    if isinstance(row, dict) and row.get("config_id") == fixed90
]
if not diagnostic or diagnostic[0].get("gate_status") != "diagnostic_only":
    fail("fixed90 diagnostic-only holdout row is missing or promoted")
for bucket_name, bucket in (
    ("selected_configs", selected_configs),
    ("baseline_configs", baseline_configs),
    ("holdout_configs", holdout_configs),
    ("rejected_configs", rejected_configs),
):
    for row in bucket:
        if not isinstance(row, dict):
            fail(f"historical replay {bucket_name} contains a non-object row")
        if row.get("decision_samples"):
            fail(f"historical replay {bucket_name} leaked decision_samples despite sample_limit=0")
        if bucket_name in {"baseline_configs", "rejected_configs"} and row.get("gate_status") != "legacy_reference":
            fail(f"historical replay {bucket_name} row must be legacy_reference, got {row.get('gate_status')!r}")
print("served historical replay API verification passed")
PY

step "Rendering served paper tab in a real browser"
if [[ ! -x "$PWCLI" ]]; then
  echo "Missing Playwright CLI wrapper: $PWCLI" >&2
  exit 1
fi
if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required for Playwright CLI verification." >&2
  exit 1
fi

PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" open "$PAGE_URL" >/dev/null
wait_for_visible_terms \
  "served paper tab" \
  "$PAGE_TEXT_FILE" \
  "最新模拟交易" \
  "策略观察组" \
  "纸面收益走势" \
  "累计纸面收益" \
  "策略退出效果排名" \
  "覆盖情况" \
  "动作分布" \
  "模拟交易明细" \
  "回放补齐不计入真实前向收益"
PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" --raw eval \
  "() => { const target = Array.from(document.querySelectorAll('[role=tab]')).find((el) => (el.textContent || '').trim() === '历史回放'); if (!target) return false; target.click(); return true; }" \
  > "$CLICK_RESULT_FILE"
if ! grep -q "true" "$CLICK_RESULT_FILE"; then
  echo "Could not click served historical replay tab" >&2
  exit 1
fi
wait_for_visible_terms \
  "served historical replay tab" \
  "$REPLAY_PAGE_TEXT_FILE" \
  "历史回放核心读数" \
  "配置与基线" \
  "8.5 万目标买入方案" \
  "8 万目标买入方案"

ASHARE_SHORTPICK_V2_PAGE_TEXT_FILE="$PAGE_TEXT_FILE" \
ASHARE_SHORTPICK_V2_REPLAY_PAGE_TEXT_FILE="$REPLAY_PAGE_TEXT_FILE" \
"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import os
import re
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


text = Path(os.environ["ASHARE_SHORTPICK_V2_PAGE_TEXT_FILE"]).read_text(encoding="utf-8")
replay_text = Path(os.environ["ASHARE_SHORTPICK_V2_REPLAY_PAGE_TEXT_FILE"]).read_text(encoding="utf-8")
allowed_snake_case = {
    item.strip()
    for item in os.environ.get("ASHARE_VERIFY_ALLOWED_VISIBLE_SNAKE_CASE", "").split(",")
    if item.strip()
}


def check_visible_text(label: str, body: str, required_terms: list[str]) -> None:
    missing = [term for term in required_terms if term not in body]
    if missing:
        fail(f"{label} is missing required visible terms: {missing}")

    for forbidden in (
        "contract_ready",
        "research_observation",
        "true_forward_tracking",
        "historical_account_replay",
        "decision_action",
        "config_id",
        "source_state",
        "delay_buy",
        "retry_buy",
        "v2 Paper Ledger Rows",
        "backend read APIs",
        "ledger",
        "artifact",
    ):
        if forbidden in body:
            fail(f"{label} leaked forbidden visible text: {forbidden}")

    snake_hits = sorted(
        set(re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]*\b", body)) - allowed_snake_case
    )
    if snake_hits:
        fail(f"{label} leaked snake_case/key-shaped visible text: {snake_hits[:20]}")


check_visible_text(
    "served paper tab",
    text,
    [
        "试验田v2",
        "纸面追踪",
        "最新模拟交易",
        "策略说明",
        "策略观察组",
        "纸面收益走势",
        "累计纸面收益",
        "策略退出效果排名",
        "覆盖情况",
        "动作分布",
        "模拟交易明细",
        "真实前向",
        "回放",
        "回放补齐不计入真实前向收益",
        "研究观察",
        "不延迟买入",
        "不允许延迟买入",
        "只读研究口径",
    ],
)
check_visible_text(
    "served historical replay tab",
    replay_text,
    [
        "试验田v2",
        "历史回放",
        "历史回放核心读数",
        "信号日",
        "交易日",
        "配置与基线",
        "8.5 万目标买入方案",
        "8 万目标买入方案",
        "留出与未采用配置统计",
        "覆盖状态",
        "研究观察",
        "已记录来源",
    ],
)
for forbidden_replay_detail in ("决策样本", "标的 / 排名", "资金 / 数量", "入选位置"):
    if forbidden_replay_detail in replay_text:
        fail(f"served historical replay tab leaked concrete replay detail text: {forbidden_replay_detail}")

print("served page visible-text verification passed for paper and historical replay tabs")
PY

step "Done"
