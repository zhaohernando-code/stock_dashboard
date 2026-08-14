#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from ashare_evidence.db import session_scope
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.rank5_forward_observation import (
    RANK5_FORWARD_BENCHMARK_SYMBOL,
    RANK5_FORWARD_OBSERVATION_START_DATE,
    build_rank5_forward_observation_artifact,
    build_rank5_shadow_observation,
)
from ashare_evidence.rank5_path_quality import enrich_inventory_with_path_quality_features
from ashare_evidence.rolling_tranche_account_replay import (
    load_daily_close_bars_for_symbols,
    project_shortpick_v3_initial_entry_orders,
    rank5_replacement_quality_rejection_reason,
)
from ashare_evidence.rolling_tranche_execution_contract import build_shortpick_v3_rolling_tranche_execution_contract
from ashare_evidence.round75_shadow_tracking import (
    ROUND75_ACTIVATION_DATE,
    ROUND75_SHADOW_LABEL,
    ROUND75_SHADOW_STRATEGY_ID,
    validate_round75_signal_registry,
)
from ashare_evidence.shortpick_strategy_lab_read_model import (
    INITIAL_CASH_CNY,
    LEGACY_RANK45_REPLACEMENT_CONTROL_ID,
    MAIN_CONFIG_ID,
    NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
    PAPER_STATE_ENV,
    PAPER_STATE_SCHEMA_VERSION,
    QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
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
UPSTREAM_META_STABILITY_STRATEGY_LABEL = "对照组：上游元信号稳健缩放"
QUALITY_REPLACEMENT_REBALANCE_STRATEGY_LABEL = "稳定盈利前沿：仅 Rank4 可买替补 + 25% 暴露再平衡"
V3_MODEL_SPEC_ID = "selected_exhaustion_date_scaled_v3_top3_20d_v1"
REQUIRED_V3_MODEL_SPEC_IDS = (V3_MODEL_SPEC_ID, NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID)
V3_PLAN_SOURCE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_CANDIDATE_RUN_SOURCE"
V3_SOURCE_DATABASE_URL_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_SOURCE_DATABASE_URL"
V3_DAILY_SOURCE_DIR_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_V3_DAILY_SOURCE_DIR"
EXTERNAL_PLAN_SOURCE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_PLAN_SOURCE"
ROUND75_SHADOW_SIGNAL_ENV = "ASHARE_SHORTPICK_ROUND75_SHADOW_SIGNALS"
ROUND75_SHADOW_TRACKING_ENV = "ASHARE_SHORTPICK_ROUND75_SHADOW_TRACKING"
BUY_COST_RATE = 20.0 / 10_000.0
SELL_COST_RATE = 25.0 / 10_000.0
ALLOWED_EXTERNAL_PLAN_SOURCES = {
    "external_v3_selected_top_k_plan",
    "selected_top_k_candidate_run_rolling_tranche_engine",
}
STRATEGY_MODEL_SPEC_IDS = {
    MAIN_CONFIG_ID: V3_MODEL_SPEC_ID,
    UPSTREAM_META_STABILITY_CONTROL_ID: V3_MODEL_SPEC_ID,
    QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID: NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
}
STRATEGY_LABELS = {
    MAIN_CONFIG_ID: MAIN_STRATEGY_LABEL,
    QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID: QUALITY_REPLACEMENT_REBALANCE_STRATEGY_LABEL,
    UPSTREAM_META_STABILITY_CONTROL_ID: UPSTREAM_META_STABILITY_STRATEGY_LABEL,
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


def _daily_source_dir() -> Path:
    configured = os.getenv(V3_DAILY_SOURCE_DIR_ENV)
    if configured:
        return Path(configured)
    configured_state = os.getenv(PAPER_STATE_ENV)
    if configured_state:
        return Path(configured_state).parent / "shortpick-strategy-lab-v3-candidate-run-sources"
    return _repo_root() / "data" / "shortpick-strategy-lab-v3-candidate-run-sources"


def _daily_source_path(signal_day: date) -> Path:
    return _daily_source_dir() / f"{signal_day.isoformat()}.json"


def _round75_shadow_signal_path() -> Path:
    configured = os.getenv(ROUND75_SHADOW_SIGNAL_ENV)
    if configured:
        return Path(configured)
    return _repo_root() / "data" / "shortpick-round75-shadow-signals.json"


def _round75_shadow_tracking_payload() -> dict[str, Any] | None:
    configured = os.getenv(ROUND75_SHADOW_TRACKING_ENV)
    path = Path(configured) if configured else _repo_root() / "data" / "shortpick-round75-shadow-tracking.json"
    payload = _load_json(path)
    if payload is None:
        return None
    return {**payload, "artifact_path": str(path)}


def _round75_shadow_signals() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    path = _round75_shadow_signal_path()
    payload = _load_json(path)
    if payload is None:
        return {}, {
            "status": "blocked_missing_signal_registry",
            "path": str(path),
            "future_information_violation_count": 0,
        }
    try:
        validation = validate_round75_signal_registry(payload)
    except (KeyError, TypeError, ValueError) as exc:
        return {}, {
            "status": "blocked_invalid_signal_registry",
            "path": str(path),
            "future_information_violation_count": 0,
            "message": str(exc),
        }
    activation = date.fromisoformat(str(payload.get("activation_date") or ROUND75_ACTIVATION_DATE))
    signals = {
        (str(row["effective_deferral_day"]), str(row["position_key"])): row
        for row in validation["signals"]
        if date.fromisoformat(str(row["decision_day"])) >= activation
    }
    return signals, {
        "status": "ready",
        "path": str(path),
        "signal_count": validation["signal_count"],
        "true_forward_signal_count": validation["true_forward_signal_count"],
        "evaluated_through": validation["evaluated_through"],
        "future_information_violation_count": validation["future_information_violation_count"],
    }


def _round75_signals_for_source_day(
    latest_source_day: date,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    signals, status = _round75_shadow_signals()
    registry_through = status.get("evaluated_through")
    if registry_through and date.fromisoformat(str(registry_through)) < latest_source_day:
        return {}, {
            **status,
            "status": "stale_fail_closed",
            "latest_source_day": latest_source_day.isoformat(),
            "external_actions_enabled": False,
            "message": "Round 75 registry is stale; core shadow continues but no external extension may execute.",
        }
    return signals, {
        **status,
        "latest_source_day": latest_source_day.isoformat(),
        "external_actions_enabled": status.get("status") == "ready",
    }


def _candidate_source_signal_day(payload: dict[str, Any]) -> date:
    configured = str(payload.get("signal_date") or "")
    if configured:
        return date.fromisoformat(configured)
    candidate_dates = [
        str(row.get("as_of_date") or "")
        for trial in payload.get("trial_diagnostics") or []
        if isinstance(trial, dict)
        for row in trial.get("selected_top_k_picks_by_date") or []
        if isinstance(row, dict) and row.get("as_of_date")
    ]
    if not candidate_dates:
        raise ValueError("candidate source has no signal_date or selected pick dates")
    return date.fromisoformat(max(candidate_dates))


def _write_daily_source(payload: dict[str, Any], *, capture_mode: str) -> Path:
    signal_day = _candidate_source_signal_day(payload)
    archived = {
        **payload,
        "signal_date": signal_day.isoformat(),
        "paper_source_capture_mode": capture_mode,
        "paper_source_captured_at": datetime.now(UTC).isoformat(),
    }
    return write_latest_v3_candidate_run_source(archived, _daily_source_path(signal_day))


def _market_days(session: Any, *, start_day: date, end_day: date) -> list[date]:
    rows = session.execute(
        select(func.date(MarketBar.observed_at), func.count())
        .where(
            MarketBar.timeframe == "1d",
            func.date(MarketBar.observed_at) >= start_day.isoformat(),
            func.date(MarketBar.observed_at) <= end_day.isoformat(),
        )
        .group_by(func.date(MarketBar.observed_at))
        .having(func.count() >= 200)
        .order_by(func.date(MarketBar.observed_at).asc())
    ).all()
    return [date.fromisoformat(str(row[0])) for row in rows]


def _ensure_daily_candidate_sources(latest_source: dict[str, Any]) -> list[dict[str, Any]]:
    latest_signal_day = _candidate_source_signal_day(latest_source)
    tracking_start_day = date.fromisoformat(TRACKING_START_DATE)
    sources: list[dict[str, Any]] = []
    with session_scope(_v3_source_database_url()) as session:
        days = _market_days(session, start_day=tracking_start_day, end_day=latest_signal_day)
        if latest_signal_day not in days:
            days.append(latest_signal_day)
        for signal_day in sorted(set(days)):
            path = _daily_source_path(signal_day)
            payload = _load_json(path)
            if payload is None:
                if signal_day == latest_signal_day:
                    payload = latest_source
                    capture_mode = "daily_forward_capture"
                else:
                    payload = build_latest_v3_candidate_run_source(
                        session,
                        as_of_date=signal_day,
                        validation_run_id=f"shortpick-strategy-lab-v3-synchronized-{signal_day.isoformat()}",
                    )
                    capture_mode = "synchronized_start_backfill"
                _write_daily_source(payload, capture_mode=capture_mode)
                payload = _load_json(path) or payload
            sources.append(payload)
    return sorted(sources, key=lambda row: str(row.get("signal_date") or ""))


def _empty_account_state(strategy_id: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "strategy_label": STRATEGY_LABELS[strategy_id],
        "tracking_start_date": TRACKING_START_DATE,
        "cash_cny": float(INITIAL_CASH_CNY),
        "latest_nav_cny": float(INITIAL_CASH_CNY),
        "positions": [],
        "nav_points": [],
    }


def _initial_account_states() -> dict[str, dict[str, Any]]:
    return {strategy_id: _empty_account_state(strategy_id) for strategy_id in STRATEGY_LABELS}


def _close_prices_on_day(session: Any, *, day: date, symbols: set[str]) -> dict[str, float]:
    if not symbols:
        return {}
    rows = session.execute(
        select(Stock.symbol, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(
            Stock.symbol.in_(symbols),
            MarketBar.timeframe == "1d",
            func.date(MarketBar.observed_at) == day.isoformat(),
        )
        .order_by(MarketBar.id.asc())
    ).all()
    return {str(symbol): float(close_price) for symbol, close_price in rows if close_price and close_price > 0}


def _position_exit_reason(position: dict[str, Any], *, current_day: date, price: float, exit_policy: str) -> str | None:
    entry_price = _safe_float(position.get("entry_price_cny")) or 0.0
    peak_price = _safe_float(position.get("peak_price_cny")) or entry_price
    position_return = price / entry_price - 1.0 if entry_price else 0.0
    peak_return = peak_price / entry_price - 1.0 if entry_price else 0.0
    drawdown_from_peak = price / peak_price - 1.0 if peak_price else 0.0
    entry_day = date.fromisoformat(str(position["entry_date"]))
    holding_calendar_days = (current_day - entry_day).days
    deferred_exit_day = str(position.get("pit_external_deferred_exit_day") or "")
    if deferred_exit_day:
        if current_day >= date.fromisoformat(deferred_exit_day):
            return "pit_external_event_confirmed_rebound_extension_exit"
        original_exit_day = str(position.get("pit_external_original_exit_day") or "")
        if original_exit_day and current_day > date.fromisoformat(original_exit_day):
            start_price = _safe_float(position.get("pit_external_deferral_start_price")) or 0.0
            prior_price = _safe_float(position.get("pit_external_prior_close_price")) or price
            peak_price = _safe_float(position.get("pit_external_deferral_peak_price")) or start_price
            if start_price > 0 and peak_price > 0:
                prior_return = prior_price / start_price - 1.0
                stop_loss = _safe_float(position.get("pit_external_deferral_stop_loss_pct")) or 0.0
                if stop_loss > 0 and prior_return <= -stop_loss:
                    return "pit_external_deferral_next_day_stop_loss"
                activation = _safe_float(position.get("pit_external_deferral_trailing_activation_pct")) or 0.0
                drawdown_limit = _safe_float(position.get("pit_external_deferral_trailing_drawdown_pct")) or 0.0
                peak_return = peak_price / start_price - 1.0
                prior_drawdown = prior_price / peak_price - 1.0
                if (
                    activation > 0
                    and drawdown_limit > 0
                    and peak_return >= activation
                    and prior_drawdown <= -drawdown_limit
                ):
                    return "pit_external_deferral_next_day_profit_trailing_exit"
        return None
    if int(position.get("trading_days_held") or 0) >= int(position.get("target_horizon_days") or 20):
        return "mechanical_horizon"
    if current_day <= entry_day:
        return None
    if exit_policy == "rank3_pullback_rank1_quick_fail_guard":
        distance_from_20d_high = _safe_float((position.get("entry_features") or {}).get("distance_from_20d_high"))
        rank = int(position.get("rank") or 0)
        if rank == 1 and holding_calendar_days <= 8 and peak_return >= 0.06 and position_return <= -0.02:
            return "dynamic_rank1_quick_spike_failed"
        if (
            rank >= 3
            and distance_from_20d_high is not None
            and distance_from_20d_high <= -0.01
            and holding_calendar_days >= 10
            and position_return <= -0.08
            and drawdown_from_peak <= -0.10
        ):
            return "dynamic_rank3_entry_pullback_late_trend_loss_guard"
    return None


def _record_row(
    *,
    order: dict[str, Any],
    action: str,
    trade_day: date,
    shares: int,
    price: float,
    cash_after: float,
    note: str,
    return_value: float | None = None,
) -> dict[str, Any]:
    strategy_id = str(order.get("strategy_id") or "")
    signal_date = str(order.get("signal_date") or "")
    symbol = str(order.get("symbol") or "")
    return {
        "row_key": f"{strategy_id}:{signal_date}:{trade_day.isoformat()}:{action}:{symbol}:{shares}",
        "action": action,
        "action_label": "买入" if action == "buy" else "卖出",
        "strategy_id": strategy_id,
        "strategy_label": str(order.get("strategy_label") or STRATEGY_LABELS.get(strategy_id) or strategy_id),
        "signal_date": signal_date,
        "trade_date": trade_day.isoformat(),
        "symbol": symbol,
        "name": str(order.get("name") or symbol),
        "rank": order.get("rank"),
        "shares": shares,
        "price_cny": round(price, 4),
        "quantity_text": f"{shares} 股",
        "cash_after_cny": round(cash_after, 2),
        "cash_after_text": f"{cash_after:,.2f} 元",
        "exit_state_text": "持仓中" if action == "buy" else "已退出",
        "return": return_value,
        "return_text": "未退出" if return_value is None else f"{return_value:+.2%}",
        "note": note,
        "evidence_basis": str(order.get("paper_source_capture_mode") or "daily_forward_capture"),
        "replacement_inventory_rank": order.get("replacement_inventory_rank"),
        "replacement_original_symbol": order.get("replacement_original_symbol"),
        "affordable_replacement_active": order.get("affordable_replacement_active") is True,
        "rank5_forward_observation_key": order.get("rank5_forward_observation_key"),
    }


def _settle_account_day(
    *,
    session: Any,
    current_day: date,
    account_states: dict[str, dict[str, Any]],
    pending_orders: list[dict[str, Any]],
    records: list[dict[str, Any]],
    execution_events: list[dict[str, Any]],
    round75_shadow_signals: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    due_orders = [row for row in pending_orders if str(row.get("planned_entry_date") or "") == current_day.isoformat()]
    remaining_orders = [row for row in pending_orders if row not in due_orders]
    symbols = {
        str(row.get("symbol") or "")
        for row in due_orders
        if row.get("symbol")
    }
    for state in account_states.values():
        symbols.update(str(row.get("symbol") or "") for row in state["positions"] if row.get("symbol"))
    close_by_symbol = _close_prices_on_day(session, day=current_day, symbols=symbols)

    for strategy_id, state in account_states.items():
        config = _rolling_config_by_id(strategy_id)
        exit_policy = str(config.get("exit_policy") or "mechanical_horizon")
        still_open: list[dict[str, Any]] = []
        for position in state["positions"]:
            price = close_by_symbol.get(str(position.get("symbol") or ""))
            if price is None:
                still_open.append(position)
                continue
            prior_close_price = _safe_float(position.get("last_price_cny")) or price
            if current_day > date.fromisoformat(str(position["entry_date"])):
                position["trading_days_held"] = int(position.get("trading_days_held") or 0) + 1
            position["pit_external_prior_close_price"] = prior_close_price
            position["last_price_cny"] = price
            position["peak_price_cny"] = max(_safe_float(position.get("peak_price_cny")) or price, price)
            if strategy_id == ROUND75_SHADOW_STRATEGY_ID:
                position_key = str(
                    position.get("position_key")
                    or "|".join(
                        (
                            str(position.get("signal_date") or ""),
                            str(position.get("entry_date") or ""),
                            str(position.get("symbol") or ""),
                            str(int(_safe_float(position.get("rank")) or 0)),
                        )
                    )
                )
                signal = (round75_shadow_signals or {}).get((current_day.isoformat(), position_key))
                if signal is not None and not position.get("pit_external_deferred_exit_day"):
                    execution = signal.get("execution") if isinstance(signal.get("execution"), dict) else {}
                    position.update(
                        {
                            "pit_external_deferred_exit_day": execution.get("deferred_exit_day")
                            or signal.get("deferred_exit_day"),
                            "pit_external_original_exit_day": current_day.isoformat(),
                            "pit_external_deferral_start_price": prior_close_price,
                            "pit_external_deferral_peak_price": prior_close_price,
                            "pit_external_deferral_stop_loss_pct": execution.get("deferral_stop_loss_pct"),
                            "pit_external_deferral_trailing_activation_pct": execution.get(
                                "deferral_trailing_activation_pct"
                            ),
                            "pit_external_deferral_trailing_drawdown_pct": execution.get(
                                "deferral_trailing_drawdown_pct"
                            ),
                            "pit_external_signal_decision_day": signal.get("decision_day"),
                            "pit_external_signal_available_at": signal.get("available_at"),
                            "pit_external_signal_source_artifact_id": signal.get("source_artifact_id"),
                        }
                    )
                    execution_events.append(
                        {
                            "action": "extend_exit_horizon",
                            "reason": "pit_external_event_confirmed_rebound_extension",
                            "strategy_id": strategy_id,
                            "decision_day": signal.get("decision_day"),
                            "trade_date": current_day.isoformat(),
                            "position_key": position_key,
                            "symbol": position.get("symbol"),
                            "available_at": signal.get("available_at"),
                            "source_artifact_id": signal.get("source_artifact_id"),
                        }
                    )
                if position.get("pit_external_deferred_exit_day"):
                    position["pit_external_deferral_peak_price"] = max(
                        _safe_float(position.get("pit_external_deferral_peak_price")) or prior_close_price,
                        prior_close_price,
                    )
            reason = _position_exit_reason(position, current_day=current_day, price=price, exit_policy=exit_policy)
            if reason is None:
                still_open.append(position)
                continue
            proceeds = int(position["shares"]) * price * (1.0 - SELL_COST_RATE)
            state["cash_cny"] += proceeds
            cost_basis = _safe_float(position.get("cost_basis_cny")) or 0.0
            position_return = proceeds / cost_basis - 1.0 if cost_basis else 0.0
            records.append(
                _record_row(
                    order={**position, "strategy_id": strategy_id, "strategy_label": state["strategy_label"]},
                    action="sell",
                    trade_day=current_day,
                    shares=int(position["shares"]),
                    price=price,
                    cash_after=state["cash_cny"],
                    note=f"按 {reason} 退出。",
                    return_value=position_return,
                )
            )
        state["positions"] = still_open

    for order in sorted(due_orders, key=lambda row: 0 if row.get("action") == "buy" else 1):
        strategy_id = str(order.get("strategy_id") or "")
        state = account_states.get(strategy_id)
        if state is None:
            continue
        price = close_by_symbol.get(str(order.get("symbol") or ""))
        if price is None:
            remaining_orders.append(order)
            continue
        requested_shares = int(_safe_float(order.get("shares")) or 0)
        if order.get("action") == "sell":
            shares_left = requested_shares
            next_positions: list[dict[str, Any]] = []
            for position in state["positions"]:
                if shares_left <= 0 or position.get("symbol") != order.get("symbol"):
                    next_positions.append(position)
                    continue
                sold = min(int(position["shares"]), shares_left)
                proceeds = sold * price * (1.0 - SELL_COST_RATE)
                state["cash_cny"] += proceeds
                shares_left -= sold
                if sold < int(position["shares"]):
                    position["shares"] = int(position["shares"]) - sold
                    next_positions.append(position)
                records.append(
                    _record_row(
                        order=order,
                        action="sell",
                        trade_day=current_day,
                        shares=sold,
                        price=price,
                        cash_after=state["cash_cny"],
                        note="按单票市值暴露再平衡计划卖出。",
                    )
                )
            state["positions"] = next_positions
            continue
        affordable_shares = int(state["cash_cny"] // (price * (1.0 + BUY_COST_RATE)) // 100 * 100)
        shares = min(requested_shares, affordable_shares)
        max_symbol_cost = INITIAL_CASH_CNY * (_safe_float(_rolling_config_by_id(strategy_id).get("max_single_symbol_cost_basis_pct")) or 0.35)
        existing_cost = sum(
            _safe_float(position.get("cost_basis_cny")) or 0.0
            for position in state["positions"]
            if position.get("symbol") == order.get("symbol")
        )
        concentration_shares = int(max((max_symbol_cost - existing_cost), 0.0) // (price * (1.0 + BUY_COST_RATE)) // 100 * 100)
        shares = min(shares, concentration_shares)
        if shares <= 0:
            execution_events.append(
                {
                    "action": "skip_fill",
                    "reason": "insufficient_cash_or_concentration_cap_at_actual_close",
                    "strategy_id": strategy_id,
                    "signal_date": order.get("signal_date"),
                    "trade_date": current_day.isoformat(),
                    "symbol": order.get("symbol"),
                }
            )
            continue
        cash_spent = shares * price * (1.0 + BUY_COST_RATE)
        state["cash_cny"] -= cash_spent
        position = {
            "position_id": f"{strategy_id}:{order.get('signal_date')}:{order.get('symbol')}:{current_day.isoformat()}",
            "position_key": "|".join(
                (
                    str(order.get("signal_date") or ""),
                    current_day.isoformat(),
                    str(order.get("symbol") or ""),
                    str(int(_safe_float(order.get("rank")) or 0)),
                )
            ),
            "strategy_id": strategy_id,
            "strategy_label": state["strategy_label"],
            "signal_date": str(order.get("signal_date") or ""),
            "entry_date": current_day.isoformat(),
            "symbol": str(order.get("symbol") or ""),
            "name": str(order.get("name") or order.get("symbol") or ""),
            "rank": int(_safe_float(order.get("rank")) or 0),
            "shares": shares,
            "entry_price_cny": price,
            "cost_basis_cny": cash_spent,
            "target_notional_cny": _safe_float(order.get("target_notional_cny")) or shares * price,
            "target_horizon_days": int(_safe_float(order.get("target_horizon_days")) or 20),
            "trading_days_held": 0,
            "last_price_cny": price,
            "peak_price_cny": price,
            "entry_features": dict(order.get("entry_features") or {}),
            "paper_source_capture_mode": order.get("paper_source_capture_mode"),
            "replacement_inventory_rank": order.get("replacement_inventory_rank"),
            "replacement_original_symbol": order.get("replacement_original_symbol"),
            "affordable_replacement_active": order.get("affordable_replacement_active") is True,
            "rank5_forward_observation_key": order.get("rank5_forward_observation_key"),
        }
        state["positions"].append(position)
        fill_note = f"按冻结计划于 {current_day.isoformat()} 收盘价 {price:.2f} 元成交。"
        if shares != requested_shares:
            fill_note += f" 受实际现金或集中度约束，计划 {requested_shares} 股，实际 {shares} 股。"
        records.append(
            _record_row(
                order=order,
                action="buy",
                trade_day=current_day,
                shares=shares,
                price=price,
                cash_after=state["cash_cny"],
                note=fill_note,
            )
        )

    for state in account_states.values():
        invested_value = sum(
            int(position["shares"])
            * (close_by_symbol.get(str(position.get("symbol") or "")) or _safe_float(position.get("last_price_cny")) or 0.0)
            for position in state["positions"]
        )
        state["latest_nav_cny"] = state["cash_cny"] + invested_value
        state["nav_points"].append(
            {
                "date": current_day.isoformat(),
                "cash_cny": round(state["cash_cny"], 2),
                "invested_value_cny": round(invested_value, 2),
                "nav_cny": round(state["latest_nav_cny"], 2),
            }
        )
    return remaining_orders


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


def _latest_close_price(session: Any, symbol: str, *, as_of_date: date | None = None) -> float | None:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        return None
    query = select(MarketBar).where(MarketBar.stock_id == stock.id, MarketBar.timeframe == "1d")
    if as_of_date is not None:
        query = query.where(func.date(MarketBar.observed_at) <= as_of_date.isoformat())
    bar = session.scalar(query.order_by(MarketBar.observed_at.desc(), MarketBar.id.desc()).limit(1))
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
        "target_horizon_days": int(_safe_float(pick.get("target_horizon_days")) or 20),
        "entry_features": dict(pick),
        "plan_source": "selected_top_k_candidate_run_rolling_tranche_engine",
        "model_spec_id": model_spec_id,
        "note": note,
    }


def _rolling_config_by_id(config_id: str) -> dict[str, Any]:
    contract = build_shortpick_v3_rolling_tranche_execution_contract()
    lookup_id = LEGACY_RANK45_REPLACEMENT_CONTROL_ID if config_id == ROUND75_SHADOW_STRATEGY_ID else config_id
    for config in contract["candidate_configurations"]:
        if config.get("config_id") == lookup_id:
            resolved = dict(config)
            resolved["config_id"] = config_id
            return resolved
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
    strategy_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    policy = config.get("affordable_replacement_policy")
    if not isinstance(policy, dict) or skipped_row.get("reason") != policy.get("trigger_reason"):
        return None, [], []
    target_notional = _safe_float(skipped_row.get("target_notional_cny")) or 0.0
    original_score = _safe_float(original_pick.get("score")) or 0.0
    rank_min = int(_safe_float(policy.get("inventory_rank_min")) or 4)
    rank_max = int(_safe_float(policy.get("inventory_rank_max")) or 5)
    if strategy_id == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID and (rank_min, rank_max) != (4, 4):
        raise ValueError("The active stable-profit frontier must fail closed to Rank4-only replacement.")
    max_score_gap = _safe_float(policy.get("max_score_gap")) or 0.10
    min_fill_ratio = _safe_float(policy.get("min_fill_ratio")) or 0.75
    min_notional = _safe_float(policy.get("min_order_notional_cny")) or 250.0
    board_lot_size = int(_safe_float(policy.get("board_lot_size")) or 100)
    buy_cost_rate = 20.0 / 10_000.0
    rank5_observations: list[dict[str, Any]] = []
    for inventory_sequence, candidate in enumerate(inventory, start=1):
        if int(_safe_float(candidate.get("rank")) or 0) != 5:
            continue
        base_reason, _ = _replacement_base_rejection_reason(
            candidate=candidate,
            original_score=original_score,
            target_notional=target_notional,
            estimated_close_by_symbol=estimated_close_by_symbol,
            selected_symbols=selected_symbols,
            max_score_gap=max_score_gap,
            min_fill_ratio=min_fill_ratio,
            min_notional=min_notional,
            board_lot_size=board_lot_size,
            buy_cost_rate=buy_cost_rate,
        )
        rank5_observations.append(
            build_rank5_shadow_observation(
                strategy_id=strategy_id,
                signal_date=str(skipped_row.get("signal_day") or ""),
                planned_trade_date=str(skipped_row.get("trade_day") or ""),
                original_pick=original_pick,
                candidate=candidate,
                inventory_sequence=inventory_sequence,
                shadow_base_eligible=base_reason is None,
                base_eligibility_reason=base_reason,
            )
        )
    rejections: list[dict[str, Any]] = []
    for candidate in inventory:
        inventory_rank = int(_safe_float(candidate.get("rank")) or 0)
        if inventory_rank < rank_min or inventory_rank > rank_max:
            continue
        symbol = str(candidate.get("symbol") or "")
        reason, sizing = _replacement_base_rejection_reason(
            candidate=candidate,
            original_score=original_score,
            target_notional=target_notional,
            estimated_close_by_symbol=estimated_close_by_symbol,
            selected_symbols=selected_symbols,
            max_score_gap=max_score_gap,
            min_fill_ratio=min_fill_ratio,
            min_notional=min_notional,
            board_lot_size=board_lot_size,
            buy_cost_rate=buy_cost_rate,
        )
        if reason not in {
            "inventory_selection_not_allowed",
            "duplicate_selected_on_signal",
            "replacement_score_gap_above_max",
        }:
            quality_reason = rank5_replacement_quality_rejection_reason(
                candidate,
                inventory_rank=inventory_rank,
                original_score=original_score,
                policy=policy.get("rank5_quality_policy"),
            )
            if quality_reason:
                reason = quality_reason
        if reason is None:
            price = float(sizing["price"])
            lot_count = int(sizing["lot_count"])
            fill_ratio = float(sizing["fill_ratio"])
            selected_observation = next(
                (
                    observation
                    for observation in rank5_observations
                    if observation.get("candidate_symbol") == symbol
                ),
                None,
            )
            if selected_observation is not None:
                selected_observation["selected_by_current_r14"] = True
                selected_observation["selection_decision"] = "selected_by_current_r14"
            for observation in rank5_observations:
                if observation.get("shadow_base_eligible") is True and observation is not selected_observation:
                    observation["selection_decision"] = "shadow_base_eligible_not_selected"
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
                "rank5_forward_observation_key": (
                    selected_observation.get("observation_key") if selected_observation is not None else None
                ),
            }, rejections, rank5_observations
        rejections.append({"symbol": symbol, "inventory_rank": inventory_rank, "reason": reason})
    for observation in rank5_observations:
        if observation.get("shadow_base_eligible") is True:
            observation["selection_decision"] = "shadow_base_eligible_not_selected"
    return None, rejections, rank5_observations


def _replacement_base_rejection_reason(
    *,
    candidate: dict[str, Any],
    original_score: float,
    target_notional: float,
    estimated_close_by_symbol: dict[str, float],
    selected_symbols: set[str],
    max_score_gap: float,
    min_fill_ratio: float,
    min_notional: float,
    board_lot_size: int,
    buy_cost_rate: float,
) -> tuple[str | None, dict[str, float | int]]:
    symbol = str(candidate.get("symbol") or "")
    price = estimated_close_by_symbol.get(symbol)
    if candidate.get("selection_allowed") is False:
        return "inventory_selection_not_allowed", {}
    if symbol in selected_symbols:
        return "duplicate_selected_on_signal", {}
    if (_safe_float(candidate.get("score")) or 0.0) < original_score - max_score_gap:
        return "replacement_score_gap_above_max", {}
    if price is None:
        return "missing_latest_close_price", {}
    one_lot_cash = price * board_lot_size * (1.0 + buy_cost_rate)
    lot_count = int(target_notional // one_lot_cash)
    cash_spent = lot_count * one_lot_cash
    fill_ratio = cash_spent / target_notional if target_notional else 0.0
    sizing: dict[str, float | int] = {
        "price": price,
        "lot_count": lot_count,
        "cash_spent": cash_spent,
        "fill_ratio": fill_ratio,
    }
    if one_lot_cash > target_notional:
        return "one_lot_exceeds_original_rank_budget_including_fee", sizing
    if cash_spent < min_notional:
        return "replacement_notional_below_minimum", sizing
    if fill_ratio < min_fill_ratio:
        return "replacement_fill_ratio_below_min", sizing
    return None, sizing


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
        price = _latest_close_price(session, symbol, as_of_date=signal_day)
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
        account_state=account_state,
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
            replacement, replacement_rejections, rank5_forward_observations = _affordable_replacement_order(
                skipped_row=row,
                original_pick=pick,
                inventory=replacement_inventory or [],
                estimated_close_by_symbol=estimated_close_by_symbol,
                selected_symbols=selected_symbols,
                config=config,
                strategy_id=strategy_id,
            )
            if strategy_id == ROUND75_SHADOW_STRATEGY_ID:
                # Round 75 reproduces its own frozen Rank4/5 core. Its Rank5
                # rows must not count toward the separate V3 Rank5 promotion study.
                rank5_forward_observations = []
            if replacement is not None:
                replacement_pick = replacement.pop("replacement_pick")
                replacement_policy = config.get("affordable_replacement_policy") or {}
                inventory_rank_min = int(_safe_float(replacement_policy.get("inventory_rank_min")) or 0)
                inventory_rank_max = int(_safe_float(replacement_policy.get("inventory_rank_max")) or 0)
                inventory_rank_label = (
                    f"Rank{inventory_rank_min}"
                    if inventory_rank_min == inventory_rank_max
                    else f"Rank{inventory_rank_min}-{inventory_rank_max}"
                )
                replacement_note = (
                    f"原 Rank{int(_safe_float(pick.get('rank')) or 0)} 股票 {symbol} 一手超过目标预算；"
                    f"按同日 PIT Top20 库存、分差不超过 0.10、库存 {inventory_rank_label}、"
                    f"填充率不低于 75% 的规则，"
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
                        "rank5_forward_observation_key": replacement.get("rank5_forward_observation_key"),
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
                        "rank5_forward_observations": rank5_forward_observations,
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
            if rank5_forward_observations:
                diagnostic["rank5_forward_observations"] = rank5_forward_observations
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
    candidate_run: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if candidate_run is None:
        candidate_run, source_status = _load_v3_candidate_run_source()
    else:
        source_status = {
            "status": "ready_daily_candidate_source",
            "artifact_id": candidate_run.get("artifact_id"),
            "signal_date": candidate_run.get("signal_date"),
            "paper_source_capture_mode": candidate_run.get("paper_source_capture_mode"),
        }
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
        rank5_symbols = {
            str(row.get("symbol") or "")
            for row in rank_adjusted_inventory
            if int(_safe_float(row.get("rank")) or 0) == 5 and row.get("symbol")
        }
        inventory_signal_day = date.fromisoformat(rank_adjusted_signal_date)
        rank5_history = load_daily_close_bars_for_symbols(
            session,
            symbols=rank5_symbols,
            start_day=inventory_signal_day - timedelta(days=90),
            end_day=inventory_signal_day,
        )
        rank_adjusted_inventory = enrich_inventory_with_path_quality_features(
            rank_adjusted_inventory,
            market_bars_by_symbol=rank5_history,
        )
        main_orders, main_diagnostics = _build_strategy_orders(
            session=session,
            picks=picks,
            signal_date=signal_date,
            tranche_count=MAIN_TRANCHE_COUNT,
            min_order_notional=MAIN_MIN_ORDER_NOTIONAL_CNY,
            strategy_id=MAIN_CONFIG_ID,
            strategy_label=MAIN_STRATEGY_LABEL,
            model_spec_id=V3_MODEL_SPEC_ID,
            account_state=(account_states or {}).get(MAIN_CONFIG_ID),
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
            account_state=(account_states or {}).get(UPSTREAM_META_STABILITY_CONTROL_ID),
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
    planned_orders = [
        *main_orders,
        *quality_orders,
        *quality_rebalance_orders,
        *upstream_meta_orders,
    ]
    capture_mode = str(candidate_run.get("paper_source_capture_mode") or "daily_forward_capture")
    for order in planned_orders:
        order["paper_source_capture_mode"] = capture_mode
        order["source_candidate_artifact_id"] = candidate_run.get("artifact_id")
    diagnostics = [
        *main_diagnostics,
        *quality_diagnostics,
        *quality_rebalance_diagnostics,
        *upstream_meta_diagnostics,
    ]
    for diagnostic in diagnostics:
        observations = diagnostic.get("rank5_forward_observations")
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if isinstance(observation, dict):
                observation["paper_source_capture_mode"] = capture_mode
                observation["source_candidate_artifact_id"] = candidate_run.get("artifact_id")
    return planned_orders, {
        **source_status,
        "status": "ready"
        if main_orders
        or quality_orders
        or quality_rebalance_orders
        or upstream_meta_orders
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
        "diagnostics": diagnostics,
        "message": "计划单由三条活跃策略和一条 Round 75 影子对照按同一 v3 selected_top_k rolling tranche 订单语义生成。",
    }


def _rebuild_forward_paper_ledger(
    sources: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    account_states = _initial_account_states()
    records: list[dict[str, Any]] = []
    pending_orders: list[dict[str, Any]] = []
    plan_history: list[dict[str, Any]] = []
    execution_events: list[dict[str, Any]] = []
    rank5_forward_observations: list[dict[str, Any]] = []
    latest_plan_status: dict[str, Any] = {"status": "ready_no_executable_orders"}
    if not sources:
        empty_observation = build_rank5_forward_observation_artifact(
            [],
            market_bars_by_symbol={},
            paper_records=[],
            as_of_day=date.fromisoformat(TRACKING_START_DATE),
        )
        return (
            records,
            account_states,
            pending_orders,
            latest_plan_status,
            plan_history,
            execution_events,
            empty_observation,
        )

    tracking_start_day = date.fromisoformat(TRACKING_START_DATE)
    latest_source_day = max(date.fromisoformat(str(source["signal_date"])) for source in sources)
    with session_scope(_v3_source_database_url()) as session:
        market_days = _market_days(session, start_day=tracking_start_day, end_day=latest_source_day)
        market_day_index = 0
        for source in sources:
            signal_day = date.fromisoformat(str(source["signal_date"]))
            while market_day_index < len(market_days) and market_days[market_day_index] <= signal_day:
                pending_orders = _settle_account_day(
                    session=session,
                    current_day=market_days[market_day_index],
                    account_states=account_states,
                    pending_orders=pending_orders,
                    records=records,
                    execution_events=execution_events,
                )
                market_day_index += 1
            planned_orders, latest_plan_status = _v3_model_generated_plan(
                account_states=account_states,
                candidate_run=source,
            )
            for diagnostic in latest_plan_status.get("diagnostics") or []:
                if not isinstance(diagnostic, dict):
                    continue
                rank5_forward_observations.extend(
                    row
                    for row in diagnostic.get("rank5_forward_observations") or []
                    if isinstance(row, dict)
                )
            pending_orders.extend(planned_orders)
            plan_history.append(
                {
                    "signal_date": signal_day.isoformat(),
                    "source_artifact_id": source.get("artifact_id"),
                    "source_capture_mode": source.get("paper_source_capture_mode"),
                    "planned_order_count": len(planned_orders),
                    "planned_orders": planned_orders,
                }
            )
        while market_day_index < len(market_days):
            pending_orders = _settle_account_day(
                session=session,
                current_day=market_days[market_day_index],
                account_states=account_states,
                pending_orders=pending_orders,
                records=records,
                execution_events=execution_events,
            )
            market_day_index += 1
        observation_symbols = {
            str(row.get("candidate_symbol") or "")
            for row in rank5_forward_observations
            if row.get("candidate_symbol")
        }
        observation_symbols.add(RANK5_FORWARD_BENCHMARK_SYMBOL)
        observation_bars = load_daily_close_bars_for_symbols(
            session,
            symbols=observation_symbols,
            start_day=RANK5_FORWARD_OBSERVATION_START_DATE,
            end_day=latest_source_day,
        )
        rank5_forward_observation = build_rank5_forward_observation_artifact(
            rank5_forward_observations,
            market_bars_by_symbol=observation_bars,
            paper_records=records,
            as_of_day=latest_source_day,
        )

    strategy_order = {strategy_id: index for index, strategy_id in enumerate(STRATEGY_LABELS)}
    for ledger_sequence, record in enumerate(records):
        record["ledger_sequence"] = ledger_sequence
    records.sort(
        key=lambda row: (
            str(row.get("trade_date") or ""),
            strategy_order.get(str(row.get("strategy_id") or ""), 99),
            int(row.get("ledger_sequence") or 0),
        )
    )
    latest_plan_status = {
        **latest_plan_status,
        "tracking_start_date": TRACKING_START_DATE,
        "daily_source_count": len(sources),
        "daily_source_date_from": str(sources[0].get("signal_date") or ""),
        "daily_source_date_to": str(sources[-1].get("signal_date") or ""),
        "synchronized_backfill_source_count": sum(
            1 for source in sources if source.get("paper_source_capture_mode") == "synchronized_start_backfill"
        ),
    }
    return (
        records,
        account_states,
        pending_orders,
        latest_plan_status,
        plan_history,
        execution_events,
        rank5_forward_observation,
    )


def _merge_round75_shadow_migration(
    existing: dict[str, Any],
    rebuilt: tuple[
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
    ],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Add the shadow account while preserving every original V3 ledger row."""

    (
        rebuilt_records,
        rebuilt_states,
        rebuilt_orders,
        rebuilt_status,
        rebuilt_history,
        rebuilt_events,
        _rebuilt_rank5,
    ) = rebuilt
    original_ids = set(STRATEGY_LABELS) - {ROUND75_SHADOW_STRATEGY_ID}
    existing_records = [row for row in existing.get("records") or [] if isinstance(row, dict)]
    records = [row for row in existing_records if row.get("strategy_id") in original_ids]
    records.extend(row for row in rebuilt_records if row.get("strategy_id") == ROUND75_SHADOW_STRATEGY_ID)
    existing_states = existing.get("account_states") if isinstance(existing.get("account_states"), dict) else {}
    account_states = {
        strategy_id: existing_states[strategy_id]
        for strategy_id in original_ids
        if isinstance(existing_states.get(strategy_id), dict)
    }
    account_states[ROUND75_SHADOW_STRATEGY_ID] = rebuilt_states[ROUND75_SHADOW_STRATEGY_ID]
    existing_orders = [row for row in existing.get("planned_orders") or [] if isinstance(row, dict)]
    planned_orders = [row for row in existing_orders if row.get("strategy_id") in original_ids]
    planned_orders.extend(
        row for row in rebuilt_orders if row.get("strategy_id") == ROUND75_SHADOW_STRATEGY_ID
    )

    shadow_history = {
        str(row.get("signal_date") or ""): [
            order
            for order in row.get("planned_orders") or []
            if isinstance(order, dict) and order.get("strategy_id") == ROUND75_SHADOW_STRATEGY_ID
        ]
        for row in rebuilt_history
        if isinstance(row, dict)
    }
    plan_history: list[dict[str, Any]] = []
    for row in existing.get("plan_history") or []:
        if not isinstance(row, dict):
            continue
        original_orders = [
            order
            for order in row.get("planned_orders") or []
            if isinstance(order, dict) and order.get("strategy_id") in original_ids
        ]
        merged_orders = [*original_orders, *shadow_history.get(str(row.get("signal_date") or ""), [])]
        plan_history.append({**row, "planned_order_count": len(merged_orders), "planned_orders": merged_orders})

    existing_status = existing.get("plan_generation_status") or {}
    shadow_diagnostics = [
        row
        for row in rebuilt_status.get("diagnostics") or []
        if isinstance(row, dict) and row.get("strategy_id") == ROUND75_SHADOW_STRATEGY_ID
    ]
    plan_status = {
        **existing_status,
        "diagnostics": [
            row
            for row in existing_status.get("diagnostics") or []
            if isinstance(row, dict) and row.get("strategy_id") in original_ids
        ]
        + shadow_diagnostics,
        "round75_shadow_signal_registry": rebuilt_status.get("round75_shadow_signal_registry"),
        "message": "原三组账本保持不变；Round 75 作为独立影子对照加入。",
    }
    execution_events = [
        row for row in existing.get("execution_events") or [] if isinstance(row, dict)
    ]
    execution_events.extend(
        row
        for row in rebuilt_events
        if isinstance(row, dict) and row.get("strategy_id") == ROUND75_SHADOW_STRATEGY_ID
    )
    rank5_forward_observation = (
        existing.get("rank5_forward_observation")
        if isinstance(existing.get("rank5_forward_observation"), dict)
        else build_rank5_forward_observation_artifact(
            [], market_bars_by_symbol={}, paper_records=records, as_of_day=date.today()
        )
    )
    return (
        records,
        account_states,
        planned_orders,
        plan_status,
        plan_history,
        execution_events,
        rank5_forward_observation,
    )


def _advance_existing_forward_paper_ledger(
    existing: dict[str, Any],
    latest_source: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Advance one or more new source days without replaying frozen history."""

    coverage = existing.get("source_coverage") or {}
    previous_source_day = date.fromisoformat(str(coverage["end_date"]))
    latest_source_day = date.fromisoformat(str(latest_source["signal_date"]))
    account_states = {
        strategy_id: state
        for strategy_id, state in (existing.get("account_states") or {}).items()
        if strategy_id in STRATEGY_LABELS and isinstance(state, dict)
    }
    records = [row for row in existing.get("records") or [] if isinstance(row, dict)]
    planned_orders = [row for row in existing.get("planned_orders") or [] if isinstance(row, dict)]
    plan_history = [row for row in existing.get("plan_history") or [] if isinstance(row, dict)]
    execution_events = [row for row in existing.get("execution_events") or [] if isinstance(row, dict)]
    rank5_forward_observation = existing.get("rank5_forward_observation") or {}
    if latest_source_day <= previous_source_day:
        plan_status = dict(existing.get("plan_generation_status") or {})
        plan_status.pop("round75_shadow_signal_registry", None)
        return (
            records,
            account_states,
            planned_orders,
            plan_status,
            plan_history,
            execution_events,
            rank5_forward_observation,
        )

    with session_scope(_v3_source_database_url()) as session:
        for market_day in _market_days(
            session,
            start_day=previous_source_day + timedelta(days=1),
            end_day=latest_source_day,
        ):
            planned_orders = _settle_account_day(
                session=session,
                current_day=market_day,
                account_states=account_states,
                pending_orders=planned_orders,
                records=records,
                execution_events=execution_events,
            )
        new_orders, plan_status = _v3_model_generated_plan(
            account_states=account_states,
            candidate_run=latest_source,
        )
        planned_orders.extend(new_orders)
    plan_history.append(
        {
            "signal_date": latest_source_day.isoformat(),
            "source_artifact_id": latest_source.get("artifact_id"),
            "source_capture_mode": latest_source.get("paper_source_capture_mode"),
            "planned_order_count": len(new_orders),
            "planned_orders": new_orders,
        }
    )
    next_sequence = max((int(row.get("ledger_sequence") or -1) for row in records), default=-1) + 1
    for row in records:
        if row.get("ledger_sequence") is None:
            row["ledger_sequence"] = next_sequence
            next_sequence += 1
    plan_status = {
        **plan_status,
        "tracking_start_date": TRACKING_START_DATE,
        "daily_source_count": int(coverage.get("source_count") or len(plan_history)) + 1,
        "daily_source_date_from": coverage.get("start_date") or TRACKING_START_DATE,
        "daily_source_date_to": latest_source_day.isoformat(),
        "synchronized_backfill_source_count": int(
            (existing.get("plan_generation_status") or {}).get("synchronized_backfill_source_count") or 0
        ),
    }
    return (
        records,
        account_states,
        planned_orders,
        plan_status,
        plan_history,
        execution_events,
        rank5_forward_observation,
    )


def main() -> int:
    path = _state_path()
    existing = _load_json(path) or {}
    sourced_orders, source_status = _external_plan_source_orders()
    if source_status is not None:
        existing_records = existing.get("records") if isinstance(existing.get("records"), list) else []
        records = [
            row
            for row in existing_records
            if isinstance(row, dict) and str(row.get("strategy_id") or "") in STRATEGY_LABELS
        ]
        existing_account_states = (
            existing.get("account_states") if isinstance(existing.get("account_states"), dict) else {}
        )
        account_states = {
            strategy_id: existing_account_states.get(strategy_id)
            if isinstance(existing_account_states.get(strategy_id), dict)
            else _empty_account_state(strategy_id)
            for strategy_id in STRATEGY_LABELS
        }
        planned_orders = sourced_orders
        plan_status = source_status
        plan_history = existing.get("plan_history") if isinstance(existing.get("plan_history"), list) else []
        execution_events = (
            existing.get("execution_events") if isinstance(existing.get("execution_events"), list) else []
        )
        rank5_forward_observation = (
            existing.get("rank5_forward_observation")
            if isinstance(existing.get("rank5_forward_observation"), dict)
            else build_rank5_forward_observation_artifact(
                [],
                market_bars_by_symbol={},
                paper_records=records,
                as_of_day=date.today(),
            )
        )
        source_coverage = existing.get("source_coverage") if isinstance(existing.get("source_coverage"), dict) else {}
    else:
        latest_source, latest_source_status = _load_v3_candidate_run_source()
        if latest_source is None:
            raise RuntimeError(str(latest_source_status.get("message") or "v3 candidate-run source unavailable"))
        existing_states = existing.get("account_states") if isinstance(existing.get("account_states"), dict) else {}
        existing_has_all_strategies = set(STRATEGY_LABELS).issubset(existing_states)
        existing_coverage = (
            existing.get("source_coverage") if isinstance(existing.get("source_coverage"), dict) else {}
        )
        if existing_has_all_strategies and existing_coverage.get("end_date"):
            (
                records,
                account_states,
                planned_orders,
                plan_status,
                plan_history,
                execution_events,
                rank5_forward_observation,
            ) = _advance_existing_forward_paper_ledger(existing, latest_source)
            latest_source_day = date.fromisoformat(str(latest_source["signal_date"]))
            previous_source_day = date.fromisoformat(str(existing_coverage["end_date"]))
            advanced = latest_source_day > previous_source_day
            source_coverage = {
                **existing_coverage,
                "end_date": max(latest_source_day, previous_source_day).isoformat(),
                "source_count": int(existing_coverage.get("source_count") or len(plan_history)) + int(advanced),
                "strategy_count": len(account_states),
                "common_start_enforced": True,
                "update_mode": "append_only_incremental",
            }
        else:
            daily_sources = _ensure_daily_candidate_sources(latest_source)
            rebuilt = _rebuild_forward_paper_ledger(daily_sources)
            (
                records,
                account_states,
                planned_orders,
                plan_status,
                plan_history,
                execution_events,
                rank5_forward_observation,
            ) = rebuilt
            source_coverage = {
                "start_date": daily_sources[0].get("signal_date") if daily_sources else TRACKING_START_DATE,
                "end_date": daily_sources[-1].get("signal_date") if daily_sources else TRACKING_START_DATE,
                "source_count": len(daily_sources),
                "strategy_count": len(account_states),
                "common_start_enforced": True,
                "update_mode": "full_rebuild_no_prior_state",
            }
    records = [
        row for row in records
        if isinstance(row, dict) and str(row.get("strategy_id") or "") in STRATEGY_LABELS
    ]
    planned_orders = [
        row for row in planned_orders
        if isinstance(row, dict) and str(row.get("strategy_id") or "") in STRATEGY_LABELS
    ]
    execution_events = [
        row for row in execution_events
        if not isinstance(row, dict) or str(row.get("strategy_id") or "") in STRATEGY_LABELS
    ]
    plan_status = dict(plan_status)
    plan_status.pop("round75_shadow_signal_registry", None)
    source_coverage = {**source_coverage, "strategy_count": len(STRATEGY_LABELS)}
    payload = {
        "schema_version": PAPER_STATE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tracking_start_date": TRACKING_START_DATE,
        "records": [row for row in records if isinstance(row, dict)],
        "account_states": account_states,
        "planned_orders": planned_orders,
        "plan_generation_status": plan_status,
        "plan_history": plan_history,
        "execution_events": execution_events,
        "source_coverage": source_coverage,
        "rank5_forward_observation": rank5_forward_observation,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    print(
        json.dumps(
            {
                "status": "ok",
                "path": str(path),
                "record_count": len(records),
                "planned_order_count": len(planned_orders),
                "strategy_count": len(account_states),
                "rank5_forward_matured_count": (
                    (rank5_forward_observation.get("progress") or {}).get("matured_shadow_observation_count", 0)
                ),
                "coverage_start": source_coverage.get("start_date"),
                "coverage_end": source_coverage.get("end_date"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
