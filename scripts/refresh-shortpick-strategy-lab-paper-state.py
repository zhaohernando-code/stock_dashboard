#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ashare_evidence.db import session_scope
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.rolling_tranche_account_replay import project_shortpick_v3_initial_entry_orders
from ashare_evidence.rolling_tranche_execution_contract import build_shortpick_v3_rolling_tranche_execution_contract
from ashare_evidence.shortpick_strategy_lab_read_model import (
    CONDITIONAL_AGGRESSIVE_CONTROL_ID,
    CONTROL_CONFIG_ID,
    INITIAL_CASH_CNY,
    MAIN_CONFIG_ID,
    META_SIGNAL_QUALITY_CONTROL_ID,
    NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID,
    NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
    PAPER_STATE_ENV,
    PAPER_STATE_SCHEMA_VERSION,
    QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
    THREE_PART_STABILITY_CONTROL_ID,
    TRACKING_START_DATE,
    UPSTREAM_META_STABILITY_CONTROL_ID,
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
MAIN_STRATEGY_LABEL = "主策略：14 tranche 分层退出"
CONTROL_STRATEGY_LABEL = "对照组：15 tranche 低集中复投"
CONDITIONAL_AGGRESSIVE_STRATEGY_LABEL = "对照组：条件化攻击模式"
THREE_PART_STABILITY_STRATEGY_LABEL = "对照组：三段稳定性控制"
META_SIGNAL_QUALITY_STRATEGY_LABEL = "对照组：元信号质量分层"
UPSTREAM_META_STABILITY_STRATEGY_LABEL = "对照组：上游元信号稳健缩放"
NEGATIVE_MONTH_RANK_ADJUSTED_STRATEGY_LABEL = "对照组：递归上游 Rank 权重调整"
QUALITY_REPLACEMENT_REBALANCE_STRATEGY_LABEL = "候选对照：高质量可买替补 + 25% 暴露再平衡"
V3_MODEL_SPEC_ID = "selected_exhaustion_date_scaled_v3_top3_20d_v1"
REQUIRED_V3_MODEL_SPEC_IDS = (V3_MODEL_SPEC_ID, NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID)
V3_PLAN_SOURCE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_CANDIDATE_RUN_SOURCE"
V3_SOURCE_DATABASE_URL_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_SOURCE_DATABASE_URL"
EXTERNAL_PLAN_SOURCE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_PLAN_SOURCE"
ALLOWED_EXTERNAL_PLAN_SOURCES = {
    "external_v3_selected_top_k_plan",
    "selected_top_k_candidate_run_rolling_tranche_engine",
}
STRATEGY_MODEL_SPEC_IDS = {
    MAIN_CONFIG_ID: V3_MODEL_SPEC_ID,
    UPSTREAM_META_STABILITY_CONTROL_ID: V3_MODEL_SPEC_ID,
    META_SIGNAL_QUALITY_CONTROL_ID: V3_MODEL_SPEC_ID,
    THREE_PART_STABILITY_CONTROL_ID: V3_MODEL_SPEC_ID,
    CONDITIONAL_AGGRESSIVE_CONTROL_ID: V3_MODEL_SPEC_ID,
    CONTROL_CONFIG_ID: V3_MODEL_SPEC_ID,
    NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID: NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
    QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID: NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
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
        and row.get("model_spec_id") == STRATEGY_MODEL_SPEC_IDS.get(str(row.get("strategy_id") or ""))
        and row.get("plan_source") in ALLOWED_EXTERNAL_PLAN_SOURCES
        and row.get("strategy_id")
        in STRATEGY_MODEL_SPEC_IDS
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


def _next_business_day(value: date) -> date:
    next_day = value + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return next_day


def _selected_pick_plan_row(
    order: dict[str, Any],
    pick: dict[str, Any],
    *,
    note: str,
    strategy_id: str,
    strategy_label: str,
    model_spec_id: str,
) -> dict[str, Any]:
    shares = int(_safe_float(order.get("shares")) or 0)
    price = _safe_float(order.get("price")) or 0.0
    target_notional = _safe_float(order.get("target_notional_cny")) or 0.0
    return {
        "action": "buy",
        "strategy_id": strategy_id,
        "strategy_label": strategy_label,
        "signal_date": str(order.get("signal_day") or ""),
        "planned_entry_date": str(order.get("trade_day") or ""),
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
        "rank_portfolio_adjustment_multiplier": pick.get("rank_portfolio_adjustment_multiplier"),
        "rank_portfolio_adjustment_reasons": pick.get("rank_portfolio_adjustment_reasons"),
        "model_score": pick.get("score"),
        "plan_source": "selected_top_k_candidate_run_rolling_tranche_engine",
        "model_spec_id": model_spec_id,
        "note": note,
    }


def _rolling_config_by_id(config_id: str) -> dict[str, Any]:
    contract = build_shortpick_v3_rolling_tranche_execution_contract()
    for config in contract["candidate_configurations"]:
        if config.get("config_id") == config_id:
            return dict(config)
    raise RuntimeError(f"missing rolling tranche config: {config_id}")


def _pick_feature_values(pick: dict[str, Any]) -> dict[str, Any]:
    merged = {
        key: pick.get(key)
        for key in (
            "benchmark_return_20d",
            "return_20d_percentile",
            "return_5d_percentile",
            "industry_return_20d_excess",
            "distance_from_20d_high",
            "turnover_rate_percentile",
            "avg_amount_20d",
        )
        if pick.get(key) is not None
    }
    values = pick.get("rank_weight_feature_values")
    if isinstance(values, dict):
        merged.update(values)
    values = pick.get("feature_values_flat")
    if isinstance(values, dict):
        merged.update(values)
    return merged


def _conditional_aggressive_scale(picks: list[dict[str, Any]], config: dict[str, Any]) -> tuple[float, bool, str]:
    overlay = config.get("conditional_aggressive_overlay")
    if not isinstance(overlay, dict):
        return 1.0, False, ""
    target_rank = int(_safe_float(overlay.get("rank")) or 1)
    rank_pick = next((pick for pick in picks if int(_safe_float(pick.get("rank")) or 0) == target_rank), None)
    if rank_pick is None:
        return 1.0, False, "未找到 Rank1，条件化攻击覆盖未启用。"
    values = _pick_feature_values(rank_pick)
    checks = (
        _safe_float(values.get("benchmark_return_20d")) is not None
        and (_safe_float(values.get("benchmark_return_20d")) or 0.0)
        >= (_safe_float(overlay.get("min_benchmark_return_20d")) or 0.0),
        _safe_float(values.get("return_20d_percentile")) is not None
        and (_safe_float(values.get("return_20d_percentile")) or 0.0)
        >= (_safe_float(overlay.get("min_return_20d_percentile")) or 0.98),
        _safe_float(values.get("industry_return_20d_excess")) is not None
        and (_safe_float(values.get("industry_return_20d_excess")) or 0.0)
        <= (_safe_float(overlay.get("max_industry_return_20d_excess")) or 0.35),
        _safe_float(values.get("distance_from_20d_high")) is not None
        and (_safe_float(values.get("distance_from_20d_high")) or 0.0)
        >= (_safe_float(overlay.get("min_distance_from_20d_high")) or -0.08),
    )
    if not all(checks):
        return 1.0, False, "Rank1 未满足条件化攻击覆盖，按 14 tranche 主策略同口径生成。"
    scale = _safe_float(overlay.get("scale")) or 1.0
    return scale, True, f"Rank1 满足条件化攻击覆盖，组合权重按 {scale:.4f} 倍生成。"


def _apply_portfolio_weight_scale(picks: list[dict[str, Any]], scale: float) -> list[dict[str, Any]]:
    if scale == 1.0:
        return [dict(pick) for pick in picks]
    scaled: list[dict[str, Any]] = []
    for pick in picks:
        next_pick = dict(pick)
        base_weight = _safe_float(next_pick.get("portfolio_weight"))
        next_pick["portfolio_weight"] = (base_weight if base_weight is not None else 1.0) * scale
        next_pick["conditional_aggressive_weight_scale"] = scale
        scaled.append(next_pick)
    return scaled


def _three_part_stability_scale(picks: list[dict[str, Any]], config: dict[str, Any]) -> tuple[float, bool, str]:
    overlay = config.get("three_part_stability_overlay")
    if not isinstance(overlay, dict):
        return 1.0, False, ""
    rank_pick = next((pick for pick in picks if int(_safe_float(pick.get("rank")) or 0) == 1), None)
    if rank_pick is None:
        return 1.0, False, "未找到 Rank1，三段稳定性控制未启用。"
    values = _pick_feature_values(rank_pick)
    benchmark_return_20d = _safe_float(values.get("benchmark_return_20d"))
    return_20d_percentile = _safe_float(values.get("return_20d_percentile"))
    industry_return_20d_excess = _safe_float(values.get("industry_return_20d_excess"))
    distance_from_20d_high = _safe_float(values.get("distance_from_20d_high"))

    scale = 1.0
    reasons: list[str] = []
    weak_active = (
        benchmark_return_20d is not None
        and return_20d_percentile is not None
        and benchmark_return_20d < (_safe_float(overlay.get("weak_benchmark_return_20d_lt")) or -0.02)
        and return_20d_percentile < (_safe_float(overlay.get("weak_return_20d_percentile_lt")) or 1.01)
    )
    if weak_active:
        weak_scale = _safe_float(overlay.get("weak_scale")) or 1.0
        scale *= weak_scale
        reasons.append(f"弱基准段按 {weak_scale:.2f} 倍降权")

    strong_active = (
        benchmark_return_20d is not None
        and return_20d_percentile is not None
        and industry_return_20d_excess is not None
        and distance_from_20d_high is not None
        and benchmark_return_20d >= (_safe_float(overlay.get("strong_benchmark_return_20d_min")) or 0.0)
        and return_20d_percentile >= (_safe_float(overlay.get("strong_return_20d_percentile_min")) or 0.98)
        and industry_return_20d_excess <= (_safe_float(overlay.get("strong_industry_return_20d_excess_max")) or 0.50)
        and distance_from_20d_high >= (_safe_float(overlay.get("strong_distance_from_20d_high_min")) or -0.08)
    )
    if strong_active:
        strong_scale = _safe_float(overlay.get("strong_scale")) or 1.0
        scale *= strong_scale
        reasons.append(f"强信号段按 {strong_scale:.2f} 倍加权")
    if not reasons:
        return 1.0, False, "三段稳定性控制未触发，按基础权重生成。"
    return scale, True, "；".join(reasons) + "。"


def _meta_signal_quality_scale(picks: list[dict[str, Any]], config: dict[str, Any]) -> tuple[float, bool, str]:
    overlay = config.get("meta_signal_quality_overlay")
    if not isinstance(overlay, dict):
        return 1.0, False, ""
    rank_pick = next((pick for pick in picks if int(_safe_float(pick.get("rank")) or 0) == 1), None)
    if rank_pick is None:
        return 1.0, False, "未找到 Rank1，元信号质量分层未启用。"
    values = _pick_feature_values(rank_pick)
    benchmark_return_20d = _safe_float(values.get("benchmark_return_20d"))
    industry_return_20d_excess = _safe_float(values.get("industry_return_20d_excess"))

    scale = 1.0
    reasons: list[str] = []
    leadership_active = (
        benchmark_return_20d is not None
        and industry_return_20d_excess is not None
        and benchmark_return_20d
        >= (_safe_float(overlay.get("industry_leadership_benchmark_return_20d_min")) or 0.05)
        and industry_return_20d_excess
        >= (_safe_float(overlay.get("industry_leadership_industry_return_20d_excess_min")) or 0.35)
    )
    if leadership_active:
        leadership_scale = _safe_float(overlay.get("industry_leadership_scale")) or 1.0
        scale *= leadership_scale
        reasons.append(f"行业领导力段按 {leadership_scale:.2f} 倍加权")

    low_quality_active = (
        benchmark_return_20d is not None
        and industry_return_20d_excess is not None
        and benchmark_return_20d <= (_safe_float(overlay.get("low_quality_benchmark_return_20d_max")) or 0.08)
        and industry_return_20d_excess <= (_safe_float(overlay.get("low_quality_industry_return_20d_excess_max")) or 0.20)
    )
    if low_quality_active:
        low_quality_scale = _safe_float(overlay.get("low_quality_scale")) or 1.0
        scale *= low_quality_scale
        reasons.append(f"低质量信号段按 {low_quality_scale:.2f} 倍降权")

    if not reasons:
        return 1.0, False, "元信号质量分层未触发，按基础权重生成。"
    return scale, True, "；".join(reasons) + "。"


def _rank1_quality_scale(picks: list[dict[str, Any]], config: dict[str, Any]) -> tuple[float, bool, str]:
    overlay = config.get("rank1_quality_overlay")
    if not isinstance(overlay, dict):
        return 1.0, False, ""
    rank_pick = next((pick for pick in picks if int(_safe_float(pick.get("rank")) or 0) == 1), None)
    if rank_pick is None:
        return 1.0, False, "未找到 Rank1，高质量强信号覆盖未启用。"
    values = _pick_feature_values(rank_pick)
    checks = (
        (_safe_float(values.get("return_20d_percentile")) or 0.0)
        >= (_safe_float(overlay.get("strong_return_20d_percentile_min")) or 0.95),
        (_safe_float(values.get("return_5d_percentile")) or 0.0)
        >= (_safe_float(overlay.get("strong_return_5d_percentile_min")) or 0.93),
        (_safe_float(values.get("benchmark_return_20d")) or 0.0)
        >= (_safe_float(overlay.get("strong_benchmark_return_20d_min")) or 0.0),
        (_safe_float(values.get("industry_return_20d_excess")) or 0.0)
        <= (_safe_float(overlay.get("strong_industry_return_20d_excess_max")) or 0.50),
        (_safe_float(values.get("distance_from_20d_high")) or 0.0)
        >= (_safe_float(overlay.get("strong_distance_from_20d_high_min")) or -0.08),
    )
    if not all(checks):
        return 1.0, False, "Rank1 未满足高质量强信号条件，按基础权重生成。"
    scale = _safe_float(overlay.get("strong_scale")) or 1.0
    return scale, True, f"Rank1 满足高质量强信号条件，组合权重按 {scale:.2f} 倍生成。"


def _strategy_portfolio_weight_scale(picks: list[dict[str, Any]], config: dict[str, Any]) -> tuple[float, bool, str]:
    conditional_scale, conditional_active, conditional_note = _conditional_aggressive_scale(picks, config)
    stability_scale, stability_active, stability_note = _three_part_stability_scale(picks, config)
    meta_scale, meta_active, meta_note = _meta_signal_quality_scale(picks, config)
    quality_scale, quality_active, quality_note = _rank1_quality_scale(picks, config)
    scale = conditional_scale * stability_scale * meta_scale * quality_scale
    notes = [note for note in (conditional_note, stability_note, meta_note, quality_note) if note]
    return scale, conditional_active or stability_active or meta_active or quality_active, "".join(notes)


def _load_v3_candidate_run_source() -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source_path = Path(os.getenv(V3_PLAN_SOURCE_ENV) or default_v3_candidate_run_source_path(_repo_root()))
    payload = _load_json(source_path)
    if payload is None or not _candidate_run_has_required_model_specs(payload):
        with session_scope(_v3_source_database_url()) as session:
            generated = build_latest_v3_candidate_run_source(session, model_spec_ids=REQUIRED_V3_MODEL_SPEC_IDS)
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


def _candidate_run_has_required_model_specs(candidate_run: dict[str, Any]) -> bool:
    diagnostics = candidate_run.get("trial_diagnostics")
    if not isinstance(diagnostics, list):
        return False
    present = {
        str(trial.get("model_spec_id") or "")
        for trial in diagnostics
        if isinstance(trial, dict)
    }
    if not set(REQUIRED_V3_MODEL_SPEC_IDS).issubset(present):
        return False
    rank_adjusted = next(
        (
            trial
            for trial in diagnostics
            if isinstance(trial, dict)
            and str(trial.get("model_spec_id") or "") == NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID
        ),
        None,
    )
    return isinstance(rank_adjusted, dict) and isinstance(rank_adjusted.get("ranked_candidate_inventory_by_date"), list)


def _selected_v3_trial(candidate_run: dict[str, Any], *, model_spec_id: str) -> dict[str, Any] | None:
    diagnostics = candidate_run.get("trial_diagnostics")
    if not isinstance(diagnostics, list):
        return None
    for trial in diagnostics:
        if not isinstance(trial, dict):
            continue
        if str(trial.get("model_spec_id") or "") == model_spec_id:
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


def _latest_ranked_candidate_inventory(trial: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    rows = [row for row in trial.get("ranked_candidate_inventory_by_date") or [] if isinstance(row, dict)]
    if not rows:
        return None, []
    latest_date = max(str(row.get("as_of_date") or "") for row in rows)
    return latest_date, sorted(
        [row for row in rows if str(row.get("as_of_date") or "") == latest_date],
        key=lambda row: int(_safe_float(row.get("rank")) or 999),
    )


def _affordable_replacement_order(
    *,
    skipped_row: dict[str, Any],
    original_pick: dict[str, Any],
    inventory: list[dict[str, Any]],
    estimated_close_by_symbol: dict[str, float],
    selected_symbols: set[str],
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    policy = config.get("affordable_replacement_policy")
    if not isinstance(policy, dict) or skipped_row.get("reason") != policy.get("trigger_reason"):
        return None, []
    target_notional = _safe_float(skipped_row.get("target_notional_cny")) or 0.0
    original_score = _safe_float(original_pick.get("score")) or 0.0
    rank_min = int(_safe_float(policy.get("inventory_rank_min")) or 4)
    rank_max = int(_safe_float(policy.get("inventory_rank_max")) or 5)
    max_score_gap = _safe_float(policy.get("max_score_gap")) or 0.10
    min_fill_ratio = _safe_float(policy.get("min_fill_ratio")) or 0.75
    min_notional = _safe_float(policy.get("min_order_notional_cny")) or 250.0
    board_lot_size = int(_safe_float(policy.get("board_lot_size")) or 100)
    buy_cost_rate = 20.0 / 10_000.0
    rejections: list[dict[str, Any]] = []
    for candidate in inventory:
        inventory_rank = int(_safe_float(candidate.get("rank")) or 0)
        if inventory_rank < rank_min or inventory_rank > rank_max:
            continue
        symbol = str(candidate.get("symbol") or "")
        reason: str | None = None
        price = estimated_close_by_symbol.get(symbol)
        if candidate.get("selection_allowed") is False:
            reason = "inventory_selection_not_allowed"
        elif symbol in selected_symbols:
            reason = "duplicate_selected_on_signal"
        elif (_safe_float(candidate.get("score")) or 0.0) < original_score - max_score_gap:
            reason = "replacement_score_gap_above_max"
        elif price is None:
            reason = "missing_latest_close_price"
        else:
            one_lot_cash = price * board_lot_size * (1.0 + buy_cost_rate)
            lot_count = int(target_notional // one_lot_cash)
            cash_spent = lot_count * one_lot_cash
            fill_ratio = cash_spent / target_notional if target_notional else 0.0
            if one_lot_cash > target_notional:
                reason = "one_lot_exceeds_original_rank_budget_including_fee"
            elif cash_spent < min_notional:
                reason = "replacement_notional_below_minimum"
            elif fill_ratio < min_fill_ratio:
                reason = "replacement_fill_ratio_below_min"
            else:
                replacement_pick = {
                    **candidate,
                    "rank": int(_safe_float(original_pick.get("rank")) or 0),
                    "replacement_inventory_rank": inventory_rank,
                    "replacement_original_symbol": str(original_pick.get("symbol") or ""),
                }
                return {
                    "action": "buy",
                    "reason": "bought_affordable_rank4_5_replacement",
                    "signal_day": skipped_row.get("signal_day"),
                    "trade_day": skipped_row.get("trade_day"),
                    "symbol": symbol,
                    "rank": replacement_pick["rank"],
                    "shares": lot_count * board_lot_size,
                    "price": price,
                    "target_notional_cny": target_notional,
                    "replacement_pick": replacement_pick,
                    "replacement_fill_ratio": fill_ratio,
                    "replacement_inventory_rank": inventory_rank,
                }, rejections
        rejections.append({"symbol": symbol, "inventory_rank": inventory_rank, "reason": reason})
    return None, rejections


def _market_exposure_rebalance_orders(
    *,
    session: Any,
    account_state: dict[str, Any] | None,
    planned_buys: list[dict[str, Any]],
    strategy_id: str,
    strategy_label: str,
    signal_date: str,
    planned_trade_date: str,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    policy = config.get("market_value_concentration_rebalance")
    if not isinstance(policy, dict):
        return [], []
    state = account_state if isinstance(account_state, dict) else {}
    cash = _safe_float(state.get("cash_cny"))
    if cash is None:
        cash = INITIAL_CASH_CNY
    positions: dict[str, dict[str, Any]] = {}
    for row in state.get("positions") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "")
        shares = int(_safe_float(row.get("shares")) or 0)
        if symbol and shares > 0:
            positions[symbol] = {**row, "shares": shares}
    buy_cost_rate = 20.0 / 10_000.0
    for order in planned_buys:
        if order.get("action") != "buy":
            continue
        symbol = str(order.get("symbol") or "")
        shares = int(_safe_float(order.get("shares")) or 0)
        price = _safe_float(order.get("estimated_entry_price_cny")) or 0.0
        if not symbol or shares <= 0 or price <= 0:
            continue
        current = positions.setdefault(symbol, {"symbol": symbol, "name": order.get("name"), "shares": 0})
        current["shares"] = int(current["shares"]) + shares
        cash -= shares * price * (1.0 + buy_cost_rate)
    prices = {
        symbol: _latest_close_price(session, symbol)
        for symbol in positions
    }
    values = {
        symbol: row["shares"] * float(prices[symbol])
        for symbol, row in positions.items()
        if prices.get(symbol) is not None
    }
    nav = cash + sum(values.values())
    threshold = _safe_float(policy.get("threshold")) or 0.25
    board_lot_size = int(_safe_float(policy.get("board_lot_size")) or 100)
    sell_cost_rate = (_safe_float(policy.get("sell_cost_bps")) or 25.0) / 10_000.0
    orders: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for symbol in sorted(values, key=values.get, reverse=True):
        price = float(prices[symbol] or 0.0)
        shares = int(positions[symbol]["shares"])
        exposure_before = values[symbol] / nav if nav > 0 else 0.0
        if exposure_before <= threshold:
            continue
        sell_shares = 0
        post_value = values[symbol]
        post_nav = nav
        while sell_shares + board_lot_size <= shares and post_nav > 0 and post_value / post_nav > threshold:
            sell_shares += board_lot_size
            post_value -= board_lot_size * price
            post_nav -= board_lot_size * price * sell_cost_rate
        if sell_shares <= 0:
            continue
        exposure_after = post_value / post_nav if post_nav > 0 else 0.0
        orders.append(
            {
                "action": "sell",
                "strategy_id": strategy_id,
                "strategy_label": strategy_label,
                "signal_date": signal_date,
                "planned_entry_date": planned_trade_date,
                "symbol": symbol,
                "name": str(positions[symbol].get("name") or symbol),
                "shares": sell_shares,
                "entry_timing": "计划买入完成后的当日收盘再平衡",
                "estimated_entry_price_cny": price,
                "estimated_notional_cny": round(sell_shares * price, 2),
                "plan_source": "market_value_concentration_rebalance",
                "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
                "reason": "market_value_concentration_rebalance",
                "exposure_before": exposure_before,
                "exposure_after": exposure_after,
                "threshold": threshold,
                "note": f"按收盘市值将 {symbol} 的单票暴露从 {exposure_before:.2%} 降至 {exposure_after:.2%}。",
            }
        )
        diagnostics.append(
            {
                "action": "sell",
                "reason": "market_value_concentration_rebalance",
                "strategy_id": strategy_id,
                "symbol": symbol,
                "shares": sell_shares,
                "exposure_before": exposure_before,
                "exposure_after": exposure_after,
            }
        )
        nav = post_nav
        values[symbol] = post_value
    return orders, diagnostics


def _build_strategy_orders(
    *,
    session: Any,
    picks: list[dict[str, Any]],
    signal_date: str,
    tranche_count: int,
    min_order_notional: float,
    strategy_id: str,
    strategy_label: str,
    model_spec_id: str,
    replacement_inventory: list[dict[str, Any]] | None = None,
    account_state: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_top_k = max(len(picks), 1)
    signal_day = datetime.fromisoformat(signal_date).date()
    planned_entry_day = _next_business_day(signal_day) if signal_date else signal_day
    config = {
        **_rolling_config_by_id(strategy_id),
        "target_active_tranche_count": tranche_count,
        "min_order_notional_cny": min_order_notional,
    }
    portfolio_weight_scale, overlay_active, overlay_note = _strategy_portfolio_weight_scale(picks, config)
    executable_picks = _apply_portfolio_weight_scale(picks, portfolio_weight_scale)
    estimated_close_by_symbol: dict[str, float] = {}
    picks_by_symbol = {str(pick.get("symbol") or ""): pick for pick in executable_picks}
    for pick in [*executable_picks, *(replacement_inventory or [])]:
        symbol = str(pick.get("symbol") or "")
        if symbol in estimated_close_by_symbol:
            continue
        price = _latest_close_price(session, symbol)
        if price is not None:
            estimated_close_by_symbol[symbol] = price
    projected_orders = project_shortpick_v3_initial_entry_orders(
        config=config,
        picks=executable_picks,
        signal_day=signal_day,
        planned_entry_day=planned_entry_day,
        estimated_close_by_symbol=estimated_close_by_symbol,
        selected_top_k=selected_top_k,
        initial_cash_cny=INITIAL_CASH_CNY,
        max_single_symbol_cost_basis_pct=_safe_float(config.get("max_single_symbol_cost_basis_pct")) or 0.35,
    )
    orders: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    held_symbols = {
        str(row.get("symbol") or "")
        for row in (account_state or {}).get("positions", [])
        if isinstance(row, dict) and int(_safe_float(row.get("shares")) or 0) > 0
    }
    selected_symbols = set(picks_by_symbol) | held_symbols
    for row in projected_orders:
        symbol = str(row.get("symbol") or "")
        pick = picks_by_symbol.get(symbol, {})
        if row.get("action") != "buy":
            replacement, replacement_rejections = _affordable_replacement_order(
                skipped_row=row,
                original_pick=pick,
                inventory=replacement_inventory or [],
                estimated_close_by_symbol=estimated_close_by_symbol,
                selected_symbols=selected_symbols,
                config=config,
            )
            if replacement is not None:
                replacement_pick = replacement.pop("replacement_pick")
                replacement_note = (
                    f"原 Rank{int(_safe_float(pick.get('rank')) or 0)} 股票 {symbol} 一手超过目标预算；"
                    f"按同日 PIT Top20 库存、分差不超过 0.10、库存 Rank4-5、填充率不低于 75% 的规则，"
                    f"替换为 {replacement_pick.get('stock_name') or replacement_pick.get('symbol')}，"
                    f"买入 {int(_safe_float(replacement.get('shares')) or 0)} 股。"
                )
                order = _selected_pick_plan_row(
                    replacement,
                    replacement_pick,
                    note=replacement_note,
                    strategy_id=strategy_id,
                    strategy_label=strategy_label,
                    model_spec_id=model_spec_id,
                )
                order.update(
                    {
                        "replacement_original_symbol": symbol,
                        "replacement_inventory_rank": replacement.get("replacement_inventory_rank"),
                        "replacement_fill_ratio": replacement.get("replacement_fill_ratio"),
                        "affordable_replacement_active": True,
                    }
                )
                orders.append(order)
                diagnostics.append(
                    {
                        "action": "replace",
                        "reason": replacement.get("reason"),
                        "strategy_id": strategy_id,
                        "original_symbol": symbol,
                        "symbol": replacement.get("symbol"),
                        "replacement_inventory_rank": replacement.get("replacement_inventory_rank"),
                        "candidate_rejections": replacement_rejections,
                    }
                )
                continue
            diagnostic = {
                "action": row.get("action"),
                "reason": row.get("reason"),
                "strategy_id": strategy_id,
                "symbol": symbol,
                "name": str(pick.get("stock_name") or pick.get("name") or symbol),
                "rank": int(_safe_float(row.get("rank")) or _safe_float(pick.get("rank")) or 0),
                "target_notional_cny": round(_safe_float(row.get("target_notional_cny")) or 0.0, 2),
            }
            if row.get("reason") == "price_too_high_for_slot" and symbol in estimated_close_by_symbol:
                diagnostic["one_lot_notional_cny"] = round(estimated_close_by_symbol[symbol] * 100, 2)
            diagnostics.append(diagnostic)
            if replacement_rejections:
                diagnostic["replacement_rejections"] = replacement_rejections
            continue
        note = (
            "按 v3 selected_top_k 与 rolling tranche 回放同一买入内核生成；"
            f"该 Rank 目标金额约 {(_safe_float(row.get('target_notional_cny')) or 0.0):.2f} 元；"
            f"按最新收盘价 {(_safe_float(row.get('price')) or 0.0):.2f} 元估算，"
            f"买入 {int(_safe_float(row.get('shares')) or 0)} 股，"
            f"预计占用 {((_safe_float(row.get('shares')) or 0.0) * (_safe_float(row.get('price')) or 0.0)):.2f} 元。"
        )
        if overlay_note:
            note = f"{note}{overlay_note}"
        orders.append(
            _selected_pick_plan_row(
                row,
                pick,
                note=note,
                strategy_id=strategy_id,
                strategy_label=strategy_label,
                model_spec_id=model_spec_id,
            )
        )
        orders[-1]["conditional_aggressive_overlay_active"] = overlay_active
        orders[-1]["conditional_aggressive_weight_scale"] = portfolio_weight_scale
    return orders, diagnostics


def _v3_model_generated_plan(
    *,
    account_states: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_run, source_status = _load_v3_candidate_run_source()
    if candidate_run is None:
        return [], source_status
    trial = _selected_v3_trial(candidate_run, model_spec_id=V3_MODEL_SPEC_ID)
    if trial is None:
        return [], {
            **source_status,
            "status": "blocked_missing_selected_v3_trial",
            "model_spec_id": V3_MODEL_SPEC_ID,
            "message": "candidate-run 中没有 v3 selected_exhaustion trial。",
        }
    rank_adjusted_trial = _selected_v3_trial(candidate_run, model_spec_id=NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID)
    if rank_adjusted_trial is None:
        return [], {
            **source_status,
            "status": "blocked_missing_negative_month_rank_adjusted_trial",
            "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
            "message": "candidate-run 中没有递归上游 Rank 权重调整 trial；不会用旧 v3 源冒充新候选。",
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
    rank_adjusted_signal_date, rank_adjusted_picks = _latest_selected_top_k_picks(rank_adjusted_trial)
    inventory_signal_date, rank_adjusted_inventory = _latest_ranked_candidate_inventory(rank_adjusted_trial)
    if rank_adjusted_signal_date is None:
        rank_adjusted_signal_date = str(candidate_run.get("signal_date") or signal_date)
    if inventory_signal_date != rank_adjusted_signal_date:
        rank_adjusted_inventory = []
    if not picks:
        if not rank_adjusted_picks:
            return [], {
                **source_status,
                "status": "ready_no_executable_orders",
                "model_spec_id": V3_MODEL_SPEC_ID,
                "model_spec_ids": list(REQUIRED_V3_MODEL_SPEC_IDS),
                "signal_date": signal_date,
                "selected_top_k": int(_safe_float(trial.get("selected_top_k")) or 0),
                "selected_pick_count": 0,
                "selected_pick_count_by_model_spec": {
                    V3_MODEL_SPEC_ID: 0,
                    NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID: 0,
                },
                "diagnostics": [
                    {
                        "action": "no_order",
                        "reason": "model_selected_cash_or_no_selected_top_k",
                        "signal_block_reasons": (
                            trial.get("signal_block_reasons") or candidate_run.get("signal_block_reasons") or []
                        ),
                        "strategy_id": MAIN_CONFIG_ID,
                    }
                ],
                "message": "v3 candidate-run 已生成；模型当天选择现金或没有可执行 selected_top_k，纸面追踪不会降级使用旧候选。",
            }
        source_status = {
            **source_status,
            "primary_model_status": "ready_no_selected_top_k",
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
            model_spec_id=V3_MODEL_SPEC_ID,
        )
        conditional_orders, conditional_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=MAIN_TRANCHE_COUNT,
            min_order_notional=MAIN_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=CONDITIONAL_AGGRESSIVE_CONTROL_ID,
            strategy_label=CONDITIONAL_AGGRESSIVE_STRATEGY_LABEL,
            model_spec_id=V3_MODEL_SPEC_ID,
        )
        stability_orders, stability_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=MAIN_TRANCHE_COUNT,
            min_order_notional=1000.0,
            strategy_id=THREE_PART_STABILITY_CONTROL_ID,
            strategy_label=THREE_PART_STABILITY_STRATEGY_LABEL,
            model_spec_id=V3_MODEL_SPEC_ID,
        )
        meta_orders, meta_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=MAIN_TRANCHE_COUNT,
            min_order_notional=1000.0,
            strategy_id=META_SIGNAL_QUALITY_CONTROL_ID,
            strategy_label=META_SIGNAL_QUALITY_STRATEGY_LABEL,
            model_spec_id=V3_MODEL_SPEC_ID,
        )
        upstream_meta_orders, upstream_meta_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=MAIN_TRANCHE_COUNT,
            min_order_notional=MAIN_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=UPSTREAM_META_STABILITY_CONTROL_ID,
            strategy_label=UPSTREAM_META_STABILITY_STRATEGY_LABEL,
            model_spec_id=V3_MODEL_SPEC_ID,
        )
        rank_adjusted_orders, rank_adjusted_diagnostics = _build_strategy_orders(
            session=session,
            picks=rank_adjusted_picks,
            signal_date=rank_adjusted_signal_date,
            tranche_count=CONTROL_TRANCHE_COUNT,
            min_order_notional=CONTROL_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID,
            strategy_label=NEGATIVE_MONTH_RANK_ADJUSTED_STRATEGY_LABEL,
            model_spec_id=NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
        )
        quality_orders, quality_diagnostics = _build_strategy_orders(
            session=session,
            picks=rank_adjusted_picks,
            signal_date=rank_adjusted_signal_date,
            tranche_count=CONTROL_TRANCHE_COUNT,
            min_order_notional=250.0,
            strategy_id=QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
            strategy_label=QUALITY_REPLACEMENT_REBALANCE_STRATEGY_LABEL,
            model_spec_id=NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
            replacement_inventory=rank_adjusted_inventory,
            account_state=(account_states or {}).get(QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID),
        )
        quality_config = _rolling_config_by_id(QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID)
        quality_trade_date = (
            str(quality_orders[0].get("planned_entry_date") or "")
            if quality_orders
            else _next_business_day(date.fromisoformat(rank_adjusted_signal_date)).isoformat()
        )
        quality_rebalance_orders, quality_rebalance_diagnostics = _market_exposure_rebalance_orders(
            session=session,
            account_state=(account_states or {}).get(QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID),
            planned_buys=quality_orders,
            strategy_id=QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
            strategy_label=QUALITY_REPLACEMENT_REBALANCE_STRATEGY_LABEL,
            signal_date=rank_adjusted_signal_date,
            planned_trade_date=quality_trade_date,
            config=quality_config,
        )
        control_orders, control_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=CONTROL_TRANCHE_COUNT,
            min_order_notional=CONTROL_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=CONTROL_CONFIG_ID,
            strategy_label=CONTROL_STRATEGY_LABEL,
            model_spec_id=V3_MODEL_SPEC_ID,
        )
    return [
        *main_orders,
        *quality_orders,
        *quality_rebalance_orders,
        *upstream_meta_orders,
        *rank_adjusted_orders,
        *meta_orders,
        *stability_orders,
        *conditional_orders,
        *control_orders,
    ], {
        **source_status,
        "status": "ready"
        if main_orders
        or quality_orders
        or quality_rebalance_orders
        or upstream_meta_orders
        or rank_adjusted_orders
        or meta_orders
        or stability_orders
        or conditional_orders
        or control_orders
        else "ready_no_executable_orders",
        "model_spec_id": V3_MODEL_SPEC_ID,
        "model_spec_ids": list(REQUIRED_V3_MODEL_SPEC_IDS),
        "signal_date": signal_date,
        "selected_top_k": int(_safe_float(trial.get("selected_top_k")) or len(picks)),
        "selected_pick_count": len(picks),
        "selected_pick_count_by_model_spec": {
            V3_MODEL_SPEC_ID: len(picks),
            NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID: len(rank_adjusted_picks),
        },
        "ranked_candidate_inventory_count_by_model_spec": {
            NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID: len(rank_adjusted_inventory),
        },
        "diagnostics": [
            *main_diagnostics,
            *quality_diagnostics,
            *quality_rebalance_diagnostics,
            *upstream_meta_diagnostics,
            *rank_adjusted_diagnostics,
            *meta_diagnostics,
            *stability_diagnostics,
            *conditional_diagnostics,
            *control_diagnostics,
        ],
        "message": "计划单由 v3 selected_top_k candidate-run 按 rolling tranche 订单语义生成。",
    }


def main() -> int:
    path = _state_path()
    existing = _load_json(path) or {}
    records = existing.get("records") if isinstance(existing.get("records"), list) else []
    account_states = existing.get("account_states") if isinstance(existing.get("account_states"), dict) else {}
    plan_status: dict[str, Any] = {}
    sourced_orders, source_status = _external_plan_source_orders()
    if source_status is not None:
        planned_orders = sourced_orders
        plan_status = source_status
    else:
        planned_orders, plan_status = _v3_model_generated_plan(account_states=account_states)
    payload = {
        "schema_version": PAPER_STATE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tracking_start_date": str(existing.get("tracking_start_date") or TRACKING_START_DATE),
        "records": [row for row in records if isinstance(row, dict)],
        "account_states": account_states,
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
