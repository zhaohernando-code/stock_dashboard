#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from math import floor
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from ashare_evidence.db import session_scope
from ashare_evidence.models import MarketBar, ShortpickCandidate, ShortpickExperimentRun, Stock
from ashare_evidence.shortpick_strategy_lab_read_model import (
    CONTROL_CONFIG_ID,
    INITIAL_CASH_CNY,
    MAIN_CONFIG_ID,
    PAPER_STATE_ENV,
    PAPER_STATE_SCHEMA_VERSION,
    TRACKING_START_DATE,
    next_calendar_day,
)

MAIN_TRANCHE_COUNT = 14
CONTROL_TRANCHE_COUNT = 15
MAIN_MIN_ORDER_NOTIONAL_CNY = 2250
CONTROL_MIN_ORDER_NOTIONAL_CNY = 1000
BOARD_LOT_SIZE = 100
MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT = 0.25
AFFORDABLE_CONTROL_ROLES = {
    "market_factor_control_repeated_exposure_low_turnover_uptrend",
    "market_factor_control_drawdown_reversal_low_turnover_uptrend",
    "market_factor_control_same_symbol_cooldown_low_turnover_uptrend",
    "frozen_paper_primary",
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


def _plan_source_orders() -> list[dict[str, Any]]:
    source = os.getenv("ASHARE_SHORTPICK_STRATEGY_LAB_PLAN_SOURCE")
    if not source:
        return []
    payload = _load_json(Path(source))
    rows = (payload or {}).get("planned_orders") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


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


def _candidate_plan_row(
    candidate: ShortpickCandidate,
    *,
    price: float,
    shares: int,
    note: str,
    strategy_id: str,
    strategy_label: str,
) -> dict[str, Any]:
    payload = candidate.candidate_payload or {}
    overlay = payload.get("market_factor_overlay") if isinstance(payload.get("market_factor_overlay"), dict) else {}
    signal_date = str(overlay.get("latest_trade_day") or "")
    return {
        "strategy_id": strategy_id,
        "strategy_label": strategy_label,
        "signal_date": signal_date,
        "planned_entry_date": next_calendar_day(datetime.fromisoformat(signal_date).date()) if signal_date else "",
        "symbol": candidate.symbol,
        "name": candidate.name,
        "shares": shares,
        "entry_timing": "次日收盘",
        "estimated_entry_price_cny": price,
        "estimated_notional_cny": round(shares * price, 2),
        "source_candidate_id": candidate.id,
        "source_rank": overlay.get("source_rank"),
        "model_score": overlay.get("score"),
        "plan_source": "latest_shortpick_market_factor_candidates_v3_projection",
        "note": note,
    }


def _latest_candidate_rows(session: Any) -> list[ShortpickCandidate]:
    latest_run_date = session.scalar(select(func.max(ShortpickExperimentRun.run_date)))
    if latest_run_date is None:
        return []
    latest_run = session.scalar(
        select(ShortpickExperimentRun)
        .where(ShortpickExperimentRun.run_date == latest_run_date, ShortpickExperimentRun.status == "completed")
        .order_by(ShortpickExperimentRun.id.desc())
        .limit(1)
    )
    if latest_run is None:
        return []
    return list(
        session.scalars(
            select(ShortpickCandidate)
            .where(ShortpickCandidate.run_id == latest_run.id)
            .order_by(ShortpickCandidate.id.asc())
        ).all()
    )


def _candidate_sort_key(candidate: ShortpickCandidate) -> tuple[float, float, int]:
    payload = candidate.candidate_payload or {}
    overlay = payload.get("market_factor_overlay") if isinstance(payload.get("market_factor_overlay"), dict) else {}
    score = _safe_float(overlay.get("score")) or 0.0
    source_rank = _safe_float(overlay.get("source_rank")) or 999.0
    return (-score, source_rank, candidate.id)


def _select_affordable_candidate(
    session: Any,
    candidates: list[ShortpickCandidate],
    *,
    tranche_count: int,
    min_order_notional: float,
    excluded_symbols: set[str] | None = None,
) -> tuple[ShortpickCandidate, int, str] | None:
    excluded = excluded_symbols or set()
    slot_budget = INITIAL_CASH_CNY / tranche_count
    max_notional = INITIAL_CASH_CNY * MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT
    for candidate in sorted(candidates, key=_candidate_sort_key):
        if candidate.symbol in excluded:
            continue
        payload = candidate.candidate_payload or {}
        overlay = payload.get("market_factor_overlay") if isinstance(payload.get("market_factor_overlay"), dict) else {}
        if overlay.get("random_control_hash"):
            continue
        tracking_role = str(payload.get("tracking_role") or "")
        if tracking_role not in AFFORDABLE_CONTROL_ROLES:
            continue
        price = _latest_close_price(session, candidate.symbol)
        if price is None:
            continue
        one_lot_notional = price * BOARD_LOT_SIZE
        if one_lot_notional > min(slot_budget, max_notional):
            continue
        shares = int(floor(slot_budget / one_lot_notional) * BOARD_LOT_SIZE)
        if shares < BOARD_LOT_SIZE or shares * price < min_order_notional:
            continue
        note = (
            f"单 tranche 预算约 {slot_budget:.0f} 元；按最新收盘价 {price:.2f} 元估算，"
            f"买入 {shares} 股，预计占用 {shares * price:.2f} 元。"
        )
        return candidate, shares, note
    return None


def _model_generated_orders() -> list[dict[str, Any]]:
    try:
        with session_scope() as session:
            candidates = _latest_candidate_rows(session)
            main_plan = _select_affordable_candidate(
                session,
                candidates,
                tranche_count=MAIN_TRANCHE_COUNT,
                min_order_notional=MAIN_MIN_ORDER_NOTIONAL_CNY,
            )
            main_candidate = main_plan[0] if main_plan is not None else None
            control_plan = _select_affordable_candidate(
                session,
                candidates,
                tranche_count=CONTROL_TRANCHE_COUNT,
                min_order_notional=CONTROL_MIN_ORDER_NOTIONAL_CNY,
                excluded_symbols={main_candidate.symbol} if main_candidate is not None else set(),
            )
            orders: list[dict[str, Any]] = []
            if main_plan is not None:
                main, shares, note = main_plan
                price = _latest_close_price(session, main.symbol)
                if price is not None:
                    orders.append(
                        _candidate_plan_row(
                            main,
                            price=price,
                            shares=shares,
                            note=note,
                            strategy_id=MAIN_CONFIG_ID,
                            strategy_label="主策略：14 tranche 分层退出",
                        )
                    )
            if control_plan is not None:
                control, shares, note = control_plan
                price = _latest_close_price(session, control.symbol)
                if price is not None:
                    orders.append(
                        _candidate_plan_row(
                            control,
                            price=price,
                            shares=shares,
                            note=note,
                            strategy_id=CONTROL_CONFIG_ID,
                            strategy_label="对照组：15 tranche 低集中复投",
                        )
                    )
            return orders
    except Exception:
        return []


def main() -> int:
    path = _state_path()
    existing = _load_json(path) or {}
    records = existing.get("records") if isinstance(existing.get("records"), list) else []
    existing_orders = existing.get("planned_orders") if isinstance(existing.get("planned_orders"), list) else []
    planned_orders = (
        _plan_source_orders()
        or _model_generated_orders()
        or [row for row in existing_orders if isinstance(row, dict)]
    )
    payload = {
        "schema_version": PAPER_STATE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tracking_start_date": str(existing.get("tracking_start_date") or TRACKING_START_DATE),
        "records": [row for row in records if isinstance(row, dict)],
        "planned_orders": planned_orders,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    print(json.dumps({"status": "ok", "path": str(path), "planned_order_count": len(planned_orders)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
