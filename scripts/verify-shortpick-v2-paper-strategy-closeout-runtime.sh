#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"

step() {
  printf '[shortpick-v2-paper-closeout] %s\n' "$*"
}

step "Running focused v2 backend and paper-contract tests"
PYTHONPATH=src "$PYTHON_BIN" -m pytest -q \
  tests/test_shortpick_v2_read_model_api.py \
  tests/test_shortpick_v2_paper_tracking_contract.py

step "Checking H10 historical replay read-model inventory"
PYTHONPATH=src "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

from ashare_evidence.shortpick_v2_h10_paper_governance import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
)
from ashare_evidence.shortpick_v2_read_model import build_shortpick_v2_historical_replay_read_model


def fail(message: str) -> None:
    raise SystemExit(message)


payload = build_shortpick_v2_historical_replay_read_model(sample_limit=0)
selected = payload.get("selected_configs")
if not isinstance(selected, list):
    fail("selected_configs must be a list")
selected_by_id = {
    str(item.get("config_id")): item
    for item in selected
    if isinstance(item, dict) and item.get("config_id")
}
expected_selected = [H10_QUIET_CHAMPION_CONFIG_ID, H10_QUIET_CAPITAL_SHADOW_CONFIG_ID]
if list(selected_by_id) != expected_selected:
    fail(f"selected H10 configs regressed: expected={expected_selected}, actual={list(selected_by_id)}")

champion = selected_by_id[H10_QUIET_CHAMPION_CONFIG_ID]
shadow = selected_by_id[H10_QUIET_CAPITAL_SHADOW_CONFIG_ID]
champion_summary = champion.get("summary") if isinstance(champion.get("summary"), dict) else {}
shadow_summary = shadow.get("summary") if isinstance(shadow.get("summary"), dict) else {}
if not (2.70 <= float(champion_summary.get("total_return", -99)) <= 2.72):
    fail(f"champion total_return regressed: {champion_summary.get('total_return')!r}")
if not (0.53 <= float(champion_summary.get("annualized_return", -99)) <= 0.55):
    fail(f"champion annualized_return regressed: {champion_summary.get('annualized_return')!r}")
if not (-0.13 <= float(champion_summary.get("max_drawdown", 99)) <= -0.10):
    fail(f"champion max_drawdown regressed: {champion_summary.get('max_drawdown')!r}")
if not (2.55 <= float(shadow_summary.get("total_return", -99)) <= 2.59):
    fail(f"capital shadow total_return regressed: {shadow_summary.get('total_return')!r}")
if not (0.50 <= float(shadow_summary.get("annualized_return", -99)) <= 0.53):
    fail(f"capital shadow annualized_return regressed: {shadow_summary.get('annualized_return')!r}")

holdout = payload.get("holdout_configs")
if not isinstance(holdout, list):
    fail("holdout_configs must be a list")
diagnostic = [
    item for item in holdout
    if isinstance(item, dict) and item.get("config_id") == H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID
]
if not diagnostic:
    fail("fixed90 diagnostic boundary config disappeared from holdout configs")
if diagnostic[0].get("gate_status") != "diagnostic_only":
    fail(f"fixed90 gate_status must remain diagnostic_only, got {diagnostic[0].get('gate_status')!r}")

for bucket_name in ("baseline_configs", "rejected_configs"):
    bucket = payload.get(bucket_name)
    if not isinstance(bucket, list):
        fail(f"{bucket_name} must be a list")
    for row in bucket:
        if not isinstance(row, dict):
            fail(f"{bucket_name} contains a non-object row")
        if row.get("config_id") in expected_selected:
            fail(f"{bucket_name} must not contain H10 selected config {row.get('config_id')}")
        if row.get("gate_status") != "legacy_reference":
            fail(f"{bucket_name} must keep old rows as legacy_reference, got {row.get('gate_status')!r}")

for bucket_name in ("selected_configs", "baseline_configs", "holdout_configs", "rejected_configs"):
    bucket = payload.get(bucket_name)
    if not isinstance(bucket, list):
        fail(f"{bucket_name} must be a list")
    for row in bucket:
        if isinstance(row, dict) and row.get("decision_samples"):
            fail(f"{bucket_name} leaked decision samples despite sample_limit=0")

summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
inventory = summary.get("h10_strategy_inventory") if isinstance(summary.get("h10_strategy_inventory"), dict) else {}
if inventory.get("benchmark_config_id") != H10_QUIET_CHAMPION_CONFIG_ID:
    fail("h10_strategy_inventory benchmark_config_id is not the fixed85 champion")
if inventory.get("capital_shadow_config_id") != H10_QUIET_CAPITAL_SHADOW_CONFIG_ID:
    fail("h10_strategy_inventory capital_shadow_config_id is not the fixed80 control")

print("H10 historical replay inventory verification passed")
PY

step "Checking v2 paper frontend markers"
"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


component = Path("frontend/src/components/ShortpickLabV2View.tsx").read_text(encoding="utf-8")
styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

required_component_terms = [
    "策略观察组",
    "账户净值走势",
    "账户累计收益",
    "账户最大回撤对比",
    "搜索日期、标的、动作、原因",
    "退出状态",
    "前向观察候选",
    "冻结主策略",
    "资金影子对照",
    "H10 候选满足资金和整手约束，可进入纸面观察。",
    "旧策略搜索结果只作为历史弱结果参照",
]
missing = [term for term in required_component_terms if term not in component]
if missing:
    fail(f"ShortpickLabV2View is missing required user-facing markers: {missing}")

required_style_terms = [
    ".shortpick-v2-return-chart-grid",
    ".shortpick-v2-filter-bar",
    ".shortpick-v2-filter-search",
    ".shortpick-v2-filter-select",
]
missing_styles = [term for term in required_style_terms if term not in styles]
if missing_styles:
    fail(f"styles.css is missing required v2 paper markers: {missing_styles}")

for forbidden in (
    'value?.includes("旧 strategy-search")',
    'value?.includes("H10")',
    "delay_buy",
    "retry_buy",
    "later_entry",
):
    if forbidden in component:
        fail(f"frontend component still contains forbidden visible/raw pattern: {forbidden}")

print("v2 paper frontend marker verification passed")
PY

step "Building frontend"
npm --prefix frontend run build

step "Done"
