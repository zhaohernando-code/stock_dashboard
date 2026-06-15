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

API_PAYLOAD_FILE="$(mktemp)"
REPLAY_API_PAYLOAD_FILE="$(mktemp)"
PAGE_TEXT_FILE="$(mktemp)"
REPLAY_PAGE_TEXT_FILE="$(mktemp)"
PLAYWRIGHT_SESSION="shortpick-v2-paper-display-$$"

cleanup() {
  PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" close >/dev/null 2>&1 || true
  rm -f "$API_PAYLOAD_FILE" "$REPLAY_API_PAYLOAD_FILE" "$PAGE_TEXT_FILE" "$REPLAY_PAGE_TEXT_FILE"
}
trap cleanup EXIT

step() {
  printf '[shortpick-v2-paper-runtime] %s\n' "$*"
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

step "Fetching served v2 paper-tracking API"
curl -fsS "$API_BASE_URL/shortpick-lab-v2/paper-tracking" -o "$API_PAYLOAD_FILE"
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
curl -fsS "$API_BASE_URL/shortpick-lab-v2/historical-replay?sample_limit=0" -o "$REPLAY_API_PAYLOAD_FILE"
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
if payload.get("claim_ceiling") != "research_observation":
    fail(f"historical replay claim_ceiling changed: {payload.get('claim_ceiling')!r}")
if payload.get("evidence_basis") != "historical_account_replay_selection":
    fail(f"historical replay evidence_basis changed: {payload.get('evidence_basis')!r}")
if int(summary.get("selected_config_count") or 0) <= 0:
    fail("historical replay selected_config_count must be positive")
if not selected_configs:
    fail("historical replay selected_configs must not be empty")
if not baseline_configs:
    fail("historical replay baseline_configs must not be empty")
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
PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" run-code \
  "await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(1500);" \
  >/dev/null
PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" eval "() => document.body.innerText" > "$PAGE_TEXT_FILE"
PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" run-code \
  "await page.getByRole('tab', { name: '历史回放' }).click({ timeout: 10000 }); await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(1500);" \
  >/dev/null
PLAYWRIGHT_CLI_SESSION="$PLAYWRIGHT_SESSION" "$PWCLI" eval "() => document.body.innerText" > "$REPLAY_PAGE_TEXT_FILE"

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
        "入选配置",
        "覆盖状态",
        "回放来源",
        "研究观察",
        "历史账户回放筛选",
        "已记录来源",
    ],
)
for forbidden_replay_detail in ("决策样本", "标的 / 排名", "资金 / 数量", "入选位置"):
    if forbidden_replay_detail in replay_text:
        fail(f"served historical replay tab leaked concrete replay detail text: {forbidden_replay_detail}")

print("served page visible-text verification passed for paper and historical replay tabs")
PY

step "Done"
