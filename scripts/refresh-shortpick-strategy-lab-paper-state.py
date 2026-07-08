#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from math import floor
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ashare_evidence.db import session_scope
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.shortpick_strategy_lab_read_model import (
    CONTROL_CONFIG_ID,
    INITIAL_CASH_CNY,
    MAIN_CONFIG_ID,
    PAPER_STATE_ENV,
    PAPER_STATE_SCHEMA_VERSION,
    TRACKING_START_DATE,
    next_calendar_day,
)
from ashare_evidence.shortpick_strategy_lab_v3_projection import (
    build_latest_v3_candidate_run_source,
    default_v3_candidate_run_source_path,
    write_latest_v3_candidate_run_source,
)

MAIN_TRANCHE_COUNT = 14
CONTROL_TRANCHE_COUNT = 15
MAIN_MIN_ORDER_NOTIONAL_CNY = 2250
CONTROL_MIN_ORDER_NOTIONAL_CNY = 1000
BOARD_LOT_SIZE = 100
MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT = 0.25
MAIN_STRATEGY_LABEL = "主策略：14 tranche 分层退出"
CONTROL_STRATEGY_LABEL = "对照组：15 tranche 低集中复投"
V3_MODEL_SPEC_ID = "selected_exhaustion_date_scaled_v3_top3_20d_v1"
V3_PLAN_SOURCE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_CANDIDATE_RUN_SOURCE"
V3_SOURCE_DATABASE_URL_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_SOURCE_DATABASE_URL"
EXTERNAL_PLAN_SOURCE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_PLAN_SOURCE"
ALLOWED_EXTERNAL_PLAN_SOURCES = {
    "external_v3_selected_top_k_plan",
    "selected_top_k_candidate_run_rolling_tranche_engine",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_path() -> Path:
    configured = os.getenv(PAPER_STATE_ENV)
    if configured:
        return Path(configured)
    return _repo_root() / "data" / "shortpick-strategy-lab-paper-state.json"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _v3_source_database_url() -> str | None:
    configured = os.getenv(V3_SOURCE_DATABASE_URL_ENV)
    if configured:
        return configured
    hot_db = _repo_root() / "data" / "ashare_hot.db"
    if hot_db.exists() and hot_db.stat().st_size > 0:
        return f"sqlite:///{hot_db}"
    return os.getenv("ASHARE_DATABASE_URL")


def _external_plan_source_orders() -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    source = os.getenv(EXTERNAL_PLAN_SOURCE_ENV)
    if not source:
        return [], None
    payload = _load_json(Path(source))
    if payload is None:
        return [], {
            "status": "blocked_invalid_external_v3_plan_source",
            "source_env": EXTERNAL_PLAN_SOURCE_ENV,
            "path": source,
            "message": "显式计划源不存在或不是有效 JSON；不会降级使用旧候选源。",
        }
    rows = (payload or {}).get("planned_orders") or []
    if not isinstance(rows, list):
        return [], {
            "status": "blocked_invalid_external_v3_plan_source",
            "source_env": EXTERNAL_PLAN_SOURCE_ENV,
            "path": source,
            "message": "显式计划源缺少 planned_orders 数组；不会降级使用旧候选源。",
        }
    orders = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("model_spec_id") == V3_MODEL_SPEC_ID
        and row.get("plan_source") in ALLOWED_EXTERNAL_PLAN_SOURCES
        and row.get("strategy_id") in {MAIN_CONFIG_ID, CONTROL_CONFIG_ID}
        and str(row.get("symbol") or "")
        and int(_safe_float(row.get("shares")) or 0) > 0
    ]
    if not orders:
        return [], {
            "status": "blocked_no_valid_external_v3_plan_orders",
            "source_env": EXTERNAL_PLAN_SOURCE_ENV,
            "path": source,
            "model_spec_id": V3_MODEL_SPEC_ID,
            "message": "显式计划源没有符合 v3 selected_top_k/rolling tranche 合同的有效订单；不会用旧计划冒充 v3 前向。",
        }
    return orders, {
        "status": "ready_external_plan_source",
        "source_env": EXTERNAL_PLAN_SOURCE_ENV,
        "path": source,
        "model_spec_id": V3_MODEL_SPEC_ID,
        "message": "计划单来自显式提供且通过 v3 合同校验的计划源。",
    }


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _latest_close_price(session: Any, symbol: str) -> float | None:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        return None
    bar = session.scalar(
        select(MarketBar)
        .where(MarketBar.stock_id == stock.id, MarketBar.timeframe == "1d")
        .order_by(MarketBar.observed_at.desc(), MarketBar.id.desc())
        .limit(1)
    )
    return float(bar.close_price) if bar is not None and bar.close_price > 0 else None


def _selected_pick_plan_row(
    pick: dict[str, Any],
    *,
    signal_date: str,
    price: float,
    shares: int,
    target_notional: float,
    note: str,
    strategy_id: str,
    strategy_label: str,
) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "strategy_label": strategy_label,
        "signal_date": signal_date,
        "planned_entry_date": next_calendar_day(datetime.fromisoformat(signal_date).date()) if signal_date else "",
        "symbol": str(pick.get("symbol") or ""),
        "name": str(pick.get("stock_name") or pick.get("name") or pick.get("symbol") or ""),
        "rank": int(_safe_float(pick.get("rank")) or 0),
        "shares": shares,
        "entry_timing": "次日收盘",
        "estimated_entry_price_cny": price,
        "estimated_notional_cny": round(shares * price, 2),
        "target_notional_cny": round(target_notional, 2),
        "portfolio_weight": pick.get("portfolio_weight"),
        "rank_weight_multiplier": pick.get("rank_weight_multiplier"),
        "model_score": pick.get("score"),
        "plan_source": "selected_top_k_candidate_run_rolling_tranche_engine",
        "model_spec_id": V3_MODEL_SPEC_ID,
        "note": note,
    }


def _load_v3_candidate_run_source() -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source_path = Path(os.getenv(V3_PLAN_SOURCE_ENV) or default_v3_candidate_run_source_path(_repo_root()))
    if not source_path.exists():
        with session_scope(_v3_source_database_url()) as session:
            generated = build_latest_v3_candidate_run_source(session)
        write_latest_v3_candidate_run_source(generated, source_path)
    payload = _load_json(source_path)
    if payload is None:
        return None, {
            "status": "blocked_invalid_v3_candidate_run_source",
            "source_env": V3_PLAN_SOURCE_ENV,
            "path": str(source_path),
            "message": "v3 candidate-run 源不存在或不是有效 JSON。",
        }
    return payload, {
        "status": "ready",
        "source_env": V3_PLAN_SOURCE_ENV,
        "path": str(source_path),
        "artifact_id": payload.get("artifact_id"),
    }


def _selected_v3_trial(candidate_run: dict[str, Any]) -> dict[str, Any] | None:
    diagnostics = candidate_run.get("trial_diagnostics")
    if not isinstance(diagnostics, list):
        return None
    for trial in diagnostics:
        if not isinstance(trial, dict):
            continue
        if str(trial.get("model_spec_id") or "") == V3_MODEL_SPEC_ID:
            return trial
    return None


def _latest_selected_top_k_picks(trial: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    picks = [row for row in trial.get("selected_top_k_picks_by_date") or [] if isinstance(row, dict)]
    if not picks:
        return None, []
    latest_date = max(str(row.get("as_of_date") or "") for row in picks)
    if not latest_date:
        return None, []
    return latest_date, [row for row in picks if str(row.get("as_of_date") or "") == latest_date]


def _build_strategy_orders(
    *,
    session: Any,
    picks: list[dict[str, Any]],
    signal_date: str,
    tranche_count: int,
    min_order_notional: float,
    strategy_id: str,
    strategy_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    slot_budget = INITIAL_CASH_CNY / tranche_count
    per_signal_budget = min(slot_budget, INITIAL_CASH_CNY * MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT)
    selected_top_k = max(len(picks), 1)
    orders: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for pick in sorted(picks, key=lambda row: int(_safe_float(row.get("rank")) or 999)):
        symbol = str(pick.get("symbol") or "")
        rank = int(_safe_float(pick.get("rank")) or 0)
        portfolio_weight = _safe_float(pick.get("portfolio_weight")) or 0.0
        rank_weight_multiplier = _safe_float(pick.get("rank_weight_multiplier")) or 0.0
        target_notional = per_signal_budget * portfolio_weight * rank_weight_multiplier / selected_top_k
        if target_notional <= 0:
            diagnostics.append(
                {
                    "action": "no_order",
                    "reason": "zero_target_allocation",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "name": str(pick.get("stock_name") or symbol),
                    "rank": rank,
                    "target_notional_cny": round(target_notional, 2),
                }
            )
            continue
        if target_notional < min_order_notional:
            diagnostics.append(
                {
                    "action": "skip",
                    "reason": "below_min_order_notional",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "name": str(pick.get("stock_name") or symbol),
                    "rank": rank,
                    "target_notional_cny": round(target_notional, 2),
                }
            )
            continue
        price = _latest_close_price(session, symbol)
        if price is None:
            diagnostics.append(
                {
                    "action": "skip",
                    "reason": "missing_latest_close_price",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "name": str(pick.get("stock_name") or symbol),
                    "rank": rank,
                    "target_notional_cny": round(target_notional, 2),
                }
            )
            continue
        one_lot_notional = price * BOARD_LOT_SIZE
        if one_lot_notional > target_notional:
            diagnostics.append(
                {
                    "action": "skip",
                    "reason": "price_too_high_for_slot",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "name": str(pick.get("stock_name") or symbol),
                    "rank": rank,
                    "target_notional_cny": round(target_notional, 2),
                    "one_lot_notional_cny": round(one_lot_notional, 2),
                }
            )
            continue
        shares = int(floor(target_notional / one_lot_notional) * BOARD_LOT_SIZE)
        if shares < BOARD_LOT_SIZE or shares * price < min_order_notional:
            diagnostics.append(
                {
                    "action": "skip",
                    "reason": "board_lot_rounding_below_min_order",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "name": str(pick.get("stock_name") or symbol),
                    "rank": rank,
                    "target_notional_cny": round(target_notional, 2),
                }
            )
            continue
        note = (
            f"按 v3 selected_top_k 的 Rank 权重生成；单 tranche 预算约 {slot_budget:.0f} 元，"
            f"该 Rank 目标金额约 {target_notional:.2f} 元；按最新收盘价 {price:.2f} 元估算，"
            f"买入 {shares} 股，预计占用 {shares * price:.2f} 元。"
        )
        orders.append(
            _selected_pick_plan_row(
                pick,
                signal_date=signal_date,
                price=price,
                shares=shares,
                target_notional=target_notional,
                note=note,
                strategy_id=strategy_id,
                strategy_label=strategy_label,
            )
        )
    return orders, diagnostics


def _v3_model_generated_plan() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_run, source_status = _load_v3_candidate_run_source()
    if candidate_run is None:
        return [], source_status
    trial = _selected_v3_trial(candidate_run)
    if trial is None:
        return [], {
            **source_status,
            "status": "blocked_missing_selected_v3_trial",
            "model_spec_id": V3_MODEL_SPEC_ID,
            "message": "candidate-run 中没有 v3 selected_exhaustion trial。",
        }
    signal_date, picks = _latest_selected_top_k_picks(trial)
    if signal_date is None:
        signal_date = str(candidate_run.get("signal_date") or "")
    if signal_date is None or not signal_date:
        return [], {
            **source_status,
            "status": "blocked_empty_selected_top_k",
            "model_spec_id": V3_MODEL_SPEC_ID,
            "message": "candidate-run 中没有 signal_date 或 selected_top_k_picks_by_date。",
        }
    if not picks:
        return [], {
            **source_status,
            "status": "ready_no_executable_orders",
            "model_spec_id": V3_MODEL_SPEC_ID,
            "signal_date": signal_date,
            "selected_top_k": int(_safe_float(trial.get("selected_top_k")) or 0),
            "selected_pick_count": 0,
            "diagnostics": [
                {
                    "action": "no_order",
                    "reason": "model_selected_cash_or_no_selected_top_k",
                    "signal_block_reasons": trial.get("signal_block_reasons") or candidate_run.get("signal_block_reasons") or [],
                    "strategy_id": MAIN_CONFIG_ID,
                }
            ],
            "message": "v3 candidate-run 已生成；模型当天选择现金或没有可执行 selected_top_k，纸面追踪不会降级使用旧候选。",
        }
    with session_scope() as session:
        main_orders, main_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=MAIN_TRANCHE_COUNT,
            min_order_notional=MAIN_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=MAIN_CONFIG_ID,
            strategy_label=MAIN_STRATEGY_LABEL,
        )
        control_orders, control_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=CONTROL_TRANCHE_COUNT,
            min_order_notional=CONTROL_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=CONTROL_CONFIG_ID,
            strategy_label=CONTROL_STRATEGY_LABEL,
        )
    return [*main_orders, *control_orders], {
        **source_status,
        "status": "ready" if main_orders or control_orders else "ready_no_executable_orders",
        "model_spec_id": V3_MODEL_SPEC_ID,
        "signal_date": signal_date,
        "selected_top_k": int(_safe_float(trial.get("selected_top_k")) or len(picks)),
        "selected_pick_count": len(picks),
        "diagnostics": [*main_diagnostics, *control_diagnostics],
        "message": "计划单由 v3 selected_top_k candidate-run 按 rolling tranche 订单语义生成。",
    }


def main() -> int:
    path = _state_path()
    existing = _load_json(path) or {}
    records = existing.get("records") if isinstance(existing.get("records"), list) else []
    plan_status: dict[str, Any] = {}
    sourced_orders, source_status = _external_plan_source_orders()
    if source_status is not None:
        planned_orders = sourced_orders
        plan_status = source_status
    else:
        planned_orders, plan_status = _v3_model_generated_plan()
    payload = {
        "schema_version": PAPER_STATE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tracking_start_date": str(existing.get("tracking_start_date") or TRACKING_START_DATE),
        "records": [row for row in records if isinstance(row, dict)],
        "planned_orders": planned_orders,
        "plan_generation_status": plan_status,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    print(json.dumps({"status": "ok", "path": str(path), "planned_order_count": len(planned_orders)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
