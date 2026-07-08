from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import floor
from statistics import mean, quantiles
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.rolling_tranche_execution_contract import (
    DEFAULT_BOARD_LOT_SIZE,
    DEFAULT_INITIAL_CASH_CNY,
    DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT,
    DEFAULT_MAX_SINGLE_SYMBOL_COST_BASIS_PCT,
    DEFAULT_MIN_ORDER_NOTIONAL_CNY,
    build_shortpick_v3_rolling_tranche_execution_contract,
)

DEFAULT_BUY_COST_BPS = 20.0
DEFAULT_SELL_COST_BPS = 25.0
DEFAULT_MAX_ENTRY_LAG_DAYS = 7
OPEN_ENDED_EXIT_DAY = date.max


@dataclass
class _Bar:
    day: date
    close: float


@dataclass
class _Position:
    signal_day: date
    entry_day: date
    planned_exit_day: date
    symbol: str
    stock_name: str
    rank: int
    shares: int
    entry_price: float
    cost_basis: float
    target_notional: float
    last_price: float
    peak_price: float
    entry_features: dict[str, Any]


def load_daily_close_bars_for_symbols(
    session: Session,
    *,
    symbols: set[str],
    start_day: date,
    end_day: date,
) -> dict[str, list[dict[str, Any]]]:
    if not symbols:
        return {}
    start_at = datetime.combine(start_day, time.min, tzinfo=UTC)
    end_at = datetime.combine(end_day, time.max, tzinfo=UTC)
    rows = session.execute(
        select(Stock.symbol, MarketBar.observed_at, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(
            Stock.symbol.in_(symbols),
            MarketBar.timeframe == "1d",
            MarketBar.observed_at >= start_at,
            MarketBar.observed_at <= end_at,
        )
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for symbol, observed_at, close_price in rows:
        by_symbol[str(symbol)].append(
            {
                "day": observed_at.date(),
                "close": float(close_price),
            }
        )
    return dict(by_symbol)


def build_shortpick_v3_rolling_account_replay_artifact(
    *,
    candidate_run: dict[str, Any],
    trial_id: str,
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    initial_cash_cny: float = DEFAULT_INITIAL_CASH_CNY,
    buy_cost_bps: float = DEFAULT_BUY_COST_BPS,
    sell_cost_bps: float = DEFAULT_SELL_COST_BPS,
    min_order_notional_cny: float = DEFAULT_MIN_ORDER_NOTIONAL_CNY,
    max_entry_lag_days: int = DEFAULT_MAX_ENTRY_LAG_DAYS,
) -> dict[str, Any]:
    trial = _trial_diagnostic(candidate_run, trial_id=trial_id)
    selected_picks = [
        row
        for row in trial.get("selected_top_k_picks_by_date") or []
        if isinstance(row, dict) and row.get("as_of_date")
    ]
    selected_top_k = int(float(trial.get("selected_top_k") or 1))
    contract = build_shortpick_v3_rolling_tranche_execution_contract(
        model_spec_id=str(trial.get("model_spec_id") or ""),
        initial_cash_cny=initial_cash_cny,
        min_order_notional_cny=min_order_notional_cny,
    )
    bars = _normalize_bars(market_bars_by_symbol)
    signal_days = sorted({_parse_day(row["as_of_date"]) for row in selected_picks})
    picks_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in selected_picks:
        picks_by_day[_parse_day(row["as_of_date"])].append(row)
    results = [
        _simulate_config(
            config,
            picks_by_day=picks_by_day,
            signal_days=signal_days,
            bars_by_symbol=bars,
            selected_top_k=selected_top_k,
            initial_cash_cny=initial_cash_cny,
            buy_cost_bps=buy_cost_bps,
            sell_cost_bps=sell_cost_bps,
            board_lot_size=contract["account_profile"]["board_lot_size"],
            max_single_symbol_cost_basis_pct=contract["hard_constraints"]["max_single_symbol_cost_basis_pct"],
            min_order_notional_cny=min_order_notional_cny,
            max_entry_lag_days=max_entry_lag_days,
        )
        for config in contract["candidate_configurations"]
    ]
    return {
        "artifact_type": "shortpick_v3_rolling_account_replay",
        "schema_version": "shortpick_v3_rolling_account_replay.v1",
        "status": "completed",
        "claim_ceiling": "historical_account_replay_research_only",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "trial_id": trial_id,
        "model_spec_id": trial.get("model_spec_id"),
        "execution_contract": {
            "artifact_type": contract["artifact_type"],
            "schema_version": contract["schema_version"],
            "execution_mode": contract["hard_constraints"]["execution_mode"],
            "forbidden_execution_modes": contract["forbidden_execution_modes"],
            "max_single_signal_deployment_pct": DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT,
        },
        "account_profile": {
            "initial_cash_cny": initial_cash_cny,
            "buy_cost_bps": buy_cost_bps,
            "sell_cost_bps": sell_cost_bps,
            "board_lot_size": DEFAULT_BOARD_LOT_SIZE,
            "max_single_symbol_cost_basis_pct": DEFAULT_MAX_SINGLE_SYMBOL_COST_BASIS_PCT,
            "min_order_notional_cny": min_order_notional_cny,
            "max_entry_lag_days": max_entry_lag_days,
        },
        "data_scope": {
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "selected_pick_count": len(selected_picks),
            "market_symbol_count": len(bars),
        },
        "results": results,
        "leaderboard": sorted(
            [
                {
                    "config_id": row["config_id"],
                    "total_return": row["summary"]["total_return"],
                    "max_drawdown": row["summary"]["max_drawdown"],
                    "negative_month_count": row["summary"]["negative_month_count"],
                    "skipped_order_rate": row["summary"]["skipped_order_rate"],
                    "skipped_signal_rate": row["summary"]["skipped_signal_rate"],
                    "mean_invested_ratio": row["summary"]["mean_invested_ratio"],
                }
                for row in results
            ],
            key=lambda row: (
                row["negative_month_count"],
                -float(row["total_return"]),
                -float(row["max_drawdown"]),
            ),
        ),
        "interpretation": (
            "This is a cash-account rolling tranche replay. It does not reuse the same cash across overlapping "
            "holds and does not allow monthly full-capital rotation."
        ),
    }


def _simulate_config(
    config: dict[str, Any],
    *,
    picks_by_day: dict[date, list[dict[str, Any]]],
    signal_days: list[date],
    bars_by_symbol: dict[str, list[_Bar]],
    selected_top_k: int,
    initial_cash_cny: float,
    buy_cost_bps: float,
    sell_cost_bps: float,
    board_lot_size: int,
    max_single_symbol_cost_basis_pct: float,
    min_order_notional_cny: float,
    max_entry_lag_days: int,
) -> dict[str, Any]:
    cadence = int(config["signal_cadence_trade_days"])
    cadence_offset = int(config.get("signal_cadence_offset_trade_days") or 0) % max(cadence, 1)
    accepted_signals = [day for index, day in enumerate(signal_days) if index % cadence == cadence_offset]
    entry_requests_by_day, pre_loop_skips = _entry_requests_by_day(
        accepted_signals,
        picks_by_day=picks_by_day,
        bars_by_symbol=bars_by_symbol,
        max_entry_lag_days=max_entry_lag_days,
    )
    active_days = _active_days(signal_days, bars_by_symbol, end_day=_max_planned_exit_day(entry_requests_by_day))
    cash = float(initial_cash_cny)
    open_positions: list[_Position] = []
    nav_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = list(pre_loop_skips)
    reason_counts: Counter[str] = Counter()
    reason_counts.update(row["reason"] for row in pre_loop_skips)
    buy_cost_rate = buy_cost_bps / 10000.0
    sell_cost_rate = sell_cost_bps / 10000.0
    per_signal_budget = float(config["per_signal_target_budget_cny"])
    exit_policy = str(config.get("exit_policy") or "mechanical_horizon")
    budget_mode = str(config.get("budget_mode") or "fixed_initial_cash_fraction")
    config_min_order_notional_cny = _safe_float(config.get("min_order_notional_cny"), min_order_notional_cny)

    for current_day in active_days:
        cash, sells, open_positions = _process_sells(
            current_day,
            cash=cash,
            open_positions=open_positions,
            bars_by_symbol=bars_by_symbol,
            sell_cost_rate=sell_cost_rate,
            exit_policy=exit_policy,
        )
        order_rows.extend(sells)
        if current_day in entry_requests_by_day:
            current_per_signal_budget = per_signal_budget
            if budget_mode == "current_nav_fraction":
                current_nav = _nav_row(
                    current_day,
                    cash=cash,
                    open_positions=open_positions,
                    bars_by_symbol=bars_by_symbol,
                )["nav_cny"]
                current_per_signal_budget = min(
                    current_nav / max(float(config["target_active_tranche_count"]), 1.0),
                    current_nav * DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT,
                )
            buys, cash, open_positions = _process_entry_buys(
                current_day,
                cash=cash,
                open_positions=open_positions,
                requests=entry_requests_by_day[current_day],
                rank_allocation_mode=str(config.get("rank_allocation_mode") or "model_rank_weight_with_board_lot_skip"),
                bars_by_symbol=bars_by_symbol,
                selected_top_k=selected_top_k,
                per_signal_budget=current_per_signal_budget,
                board_lot_size=board_lot_size,
                buy_cost_rate=buy_cost_rate,
                initial_cash_cny=initial_cash_cny,
                max_single_symbol_cost_basis_pct=max_single_symbol_cost_basis_pct,
                min_order_notional_cny=config_min_order_notional_cny,
            )
            order_rows.extend(buys)
            reason_counts.update(row["reason"] for row in buys if row["action"] == "skip")
        nav_rows.append(_nav_row(current_day, cash=cash, open_positions=open_positions, bars_by_symbol=bars_by_symbol))

    summary = _summary(
        config=config,
        nav_rows=nav_rows,
        order_rows=order_rows,
        reason_counts=reason_counts,
        accepted_signal_count=len(accepted_signals),
        initial_cash_cny=initial_cash_cny,
    )
    summary["annualized_return"] = _annualized_return(
        nav_rows,
        start_day=signal_days[0] if signal_days else None,
        initial_cash_cny=initial_cash_cny,
    )
    return {
        "config_id": config["config_id"],
        "config": config,
        "summary": summary,
        "reason_counts": dict(reason_counts),
        "monthly_returns": _monthly_returns(nav_rows, initial_cash_cny=initial_cash_cny),
        "order_ledger": order_rows,
        "nav_rows": nav_rows,
        "sample_orders": order_rows[:20],
        "worst_orders": sorted(
            [row for row in order_rows if row["action"] == "sell"], key=lambda row: row.get("pnl_cny", 0.0)
        )[:10],
        "nav_tail": nav_rows[-5:],
    }


def _entry_requests_by_day(
    accepted_signals: list[date],
    *,
    picks_by_day: dict[date, list[dict[str, Any]]],
    bars_by_symbol: dict[str, list[_Bar]],
    max_entry_lag_days: int,
) -> tuple[dict[date, list[dict[str, Any]]], list[dict[str, Any]]]:
    requests_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    skips: list[dict[str, Any]] = []
    for signal_day in accepted_signals:
        for pick in sorted(picks_by_day.get(signal_day, []), key=lambda row: int(float(row.get("rank") or 999))):
            symbol = str(pick.get("symbol") or "")
            stock_name = str(pick.get("stock_name") or symbol)
            rank = int(float(pick.get("rank") or 0))
            bars = bars_by_symbol.get(symbol) or []
            entry_index = _next_bar_index_after(bars, signal_day)
            if entry_index is None:
                skips.append(_skip(signal_day, symbol, stock_name, rank, "missing_entry_bar"))
                continue
            if (bars[entry_index].day - signal_day).days > max_entry_lag_days:
                skips.append(_skip(signal_day, symbol, stock_name, rank, "missing_entry_bar_near_signal"))
                continue
            horizon = int(float(pick.get("target_horizon_days") or 20))
            exit_index = entry_index + horizon
            planned_exit_day = bars[exit_index].day if exit_index < len(bars) else None
            requests_by_day[bars[entry_index].day].append(
                {
                    "pick": pick,
                    "signal_day": signal_day,
                    "entry_index": entry_index,
                    "exit_index": exit_index if exit_index < len(bars) else None,
                    "planned_exit_day": planned_exit_day,
                }
            )
    return dict(requests_by_day), skips


def _process_entry_buys(
    trade_day: date,
    *,
    cash: float,
    open_positions: list[_Position],
    requests: list[dict[str, Any]],
    rank_allocation_mode: str,
    bars_by_symbol: dict[str, list[_Bar]],
    selected_top_k: int,
    per_signal_budget: float,
    board_lot_size: int,
    buy_cost_rate: float,
    initial_cash_cny: float,
    max_single_symbol_cost_basis_pct: float,
    min_order_notional_cny: float,
) -> tuple[list[dict[str, Any]], float, list[_Position]]:
    rows: list[dict[str, Any]] = []
    positions = list(open_positions)
    symbol_cost_basis = Counter({position.symbol: position.cost_basis for position in positions})
    ordered_requests = sorted(
        requests,
        key=lambda row: (row["signal_day"], int(float((row["pick"] or {}).get("rank") or 999))),
    )
    if rank_allocation_mode == "consolidate_to_first_executable_rank":
        grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for request in ordered_requests:
            grouped[request["signal_day"]].append(request)
        for signal_day, signal_requests in sorted(grouped.items()):
            signal_budget = sum(
                per_signal_budget
                * _safe_float((request["pick"] or {}).get("portfolio_weight"), 1.0)
                * _safe_float((request["pick"] or {}).get("rank_weight_multiplier"), 1.0)
                / max(float(selected_top_k), 1.0)
                for request in signal_requests
            )
            bought = False
            bought_request: dict[str, Any] | None = None
            deferred_skips: list[dict[str, Any]] = []
            for request in signal_requests:
                buy_rows, cash, positions, bought = _try_buy_request(
                    request,
                    cash=cash,
                    positions=positions,
                    symbol_cost_basis=symbol_cost_basis,
                    bars_by_symbol=bars_by_symbol,
                    target_notional=signal_budget,
                    board_lot_size=board_lot_size,
                    buy_cost_rate=buy_cost_rate,
                    initial_cash_cny=initial_cash_cny,
                    max_single_symbol_cost_basis_pct=max_single_symbol_cost_basis_pct,
                    min_order_notional_cny=min_order_notional_cny,
                )
                if bought:
                    rows.extend(buy_rows)
                    bought_request = request
                    break
                deferred_skips.extend(buy_rows)
            if not bought:
                rows.extend(deferred_skips[:1])
            else:
                rows.extend(deferred_skips)
                bought_index = signal_requests.index(bought_request) if bought_request in signal_requests else 0
                for request_index, request in enumerate(signal_requests):
                    if request_index <= bought_index:
                        continue
                    pick = request["pick"]
                    rows.append(
                        {
                            "action": "no_order",
                            "reason": "budget_consolidated_to_first_executable_rank",
                            "signal_day": signal_day.isoformat(),
                            "trade_day": trade_day.isoformat(),
                            "symbol": str(pick.get("symbol") or ""),
                            "stock_name": str(pick.get("stock_name") or pick.get("symbol") or ""),
                            "rank": int(float(pick.get("rank") or 0)),
                            "target_notional_cny": 0.0,
                        }
                    )
        return rows, cash, positions
    if rank_allocation_mode != "model_rank_weight_with_board_lot_skip":
        raise ValueError(f"unsupported rank allocation mode: {rank_allocation_mode}")
    for request in ordered_requests:
        pick = request["pick"]
        target_notional = (
            per_signal_budget
            * _safe_float(pick.get("portfolio_weight"), 1.0)
            * _safe_float(pick.get("rank_weight_multiplier"), 1.0)
            / max(float(selected_top_k), 1.0)
        )
        if target_notional <= 0:
            rows.append(_no_order(request, trade_day, "zero_target_allocation", target_notional))
            continue
        buy_rows, cash, positions, _bought = _try_buy_request(
            request,
            cash=cash,
            positions=positions,
            symbol_cost_basis=symbol_cost_basis,
            bars_by_symbol=bars_by_symbol,
            target_notional=target_notional,
            board_lot_size=board_lot_size,
            buy_cost_rate=buy_cost_rate,
            initial_cash_cny=initial_cash_cny,
            max_single_symbol_cost_basis_pct=max_single_symbol_cost_basis_pct,
            min_order_notional_cny=min_order_notional_cny,
        )
        rows.extend(buy_rows)
    return rows, cash, positions


def _no_order(request: dict[str, Any], trade_day: date, reason: str, target_notional: float) -> dict[str, Any]:
    pick = request["pick"]
    signal_day = request["signal_day"]
    return {
        "action": "no_order",
        "reason": reason,
        "signal_day": signal_day.isoformat(),
        "trade_day": trade_day.isoformat(),
        "symbol": str(pick.get("symbol") or ""),
        "stock_name": str(pick.get("stock_name") or pick.get("symbol") or ""),
        "rank": int(float(pick.get("rank") or 0)),
        "target_notional_cny": target_notional,
    }


def _try_buy_request(
    request: dict[str, Any],
    *,
    cash: float,
    positions: list[_Position],
    symbol_cost_basis: Counter[str],
    bars_by_symbol: dict[str, list[_Bar]],
    target_notional: float,
    board_lot_size: int,
    buy_cost_rate: float,
    initial_cash_cny: float,
    max_single_symbol_cost_basis_pct: float,
    min_order_notional_cny: float,
) -> tuple[list[dict[str, Any]], float, list[_Position], bool]:
    pick = request["pick"]
    signal_day = request["signal_day"]
    symbol = str(pick.get("symbol") or "")
    stock_name = str(pick.get("stock_name") or symbol)
    rank = int(float(pick.get("rank") or 0))
    bars = bars_by_symbol.get(symbol) or []
    entry_bar = bars[int(request["entry_index"])]
    one_lot_notional = entry_bar.close * board_lot_size
    if target_notional < min_order_notional_cny:
        return [_skip(signal_day, symbol, stock_name, rank, "below_min_order_notional", target_notional)], cash, positions, False
    if one_lot_notional > target_notional:
        return [_skip(signal_day, symbol, stock_name, rank, "price_too_high_for_slot", target_notional)], cash, positions, False
    shares = int(floor(target_notional / one_lot_notional) * board_lot_size)
    if shares <= 0:
        return [_skip(signal_day, symbol, stock_name, rank, "board_lot_rounding_zero", target_notional)], cash, positions, False
    gross_cost = shares * entry_bar.close
    cash_spent = gross_cost * (1.0 + buy_cost_rate)
    if cash_spent > cash:
        return [_skip(signal_day, symbol, stock_name, rank, "insufficient_cash", target_notional)], cash, positions, False
    max_symbol_cost = initial_cash_cny * max_single_symbol_cost_basis_pct
    if symbol_cost_basis[symbol] + cash_spent > max_symbol_cost:
        return (
            [_skip(signal_day, symbol, stock_name, rank, "single_symbol_concentration_cap", target_notional)],
            cash,
            positions,
            False,
        )
    position = _Position(
        signal_day=signal_day,
        entry_day=entry_bar.day,
        planned_exit_day=request["planned_exit_day"] or OPEN_ENDED_EXIT_DAY,
        symbol=symbol,
        stock_name=stock_name,
        rank=rank,
        shares=shares,
        entry_price=entry_bar.close,
        cost_basis=cash_spent,
        target_notional=target_notional,
        last_price=entry_bar.close,
        peak_price=entry_bar.close,
        entry_features=dict(pick),
    )
    updated_positions = [*positions, position]
    updated_cash = cash - cash_spent
    symbol_cost_basis[symbol] += cash_spent
    return (
        [
            {
                "action": "buy",
                "reason": "bought",
                "signal_day": signal_day.isoformat(),
                "trade_day": entry_bar.day.isoformat(),
                "symbol": symbol,
                "stock_name": stock_name,
                "rank": rank,
                "shares": shares,
                "price": entry_bar.close,
                "target_notional_cny": target_notional,
                "cash_spent_cny": cash_spent,
                "cash_after_cny": updated_cash,
            }
        ],
        updated_cash,
        updated_positions,
        True,
    )


def _process_sells(
    current_day: date,
    *,
    cash: float,
    open_positions: list[_Position],
    bars_by_symbol: dict[str, list[_Bar]],
    sell_cost_rate: float,
    exit_policy: str,
) -> tuple[float, list[dict[str, Any]], list[_Position]]:
    rows: list[dict[str, Any]] = []
    still_open: list[_Position] = []
    for position in open_positions:
        price = _price_on_day(bars_by_symbol.get(position.symbol) or [], current_day)
        if price is not None:
            position.last_price = price
            position.peak_price = max(position.peak_price, price)
        exit_reason = _exit_reason(position, current_day=current_day, price=price, exit_policy=exit_policy)
        if exit_reason is None:
            still_open.append(position)
            continue
        proceeds = position.shares * price * (1.0 - sell_cost_rate)
        cash += proceeds
        pnl = proceeds - position.cost_basis
        rows.append(
            {
                "action": "sell",
                "reason": exit_reason,
                "signal_day": position.signal_day.isoformat(),
                "trade_day": current_day.isoformat(),
                "symbol": position.symbol,
                "stock_name": position.stock_name,
                "rank": position.rank,
                "shares": position.shares,
                "entry_price": position.entry_price,
                "price": price,
                "cost_basis_cny": position.cost_basis,
                "proceeds_cny": proceeds,
                "pnl_cny": pnl,
                "return": pnl / position.cost_basis if position.cost_basis else 0.0,
                "cash_after_cny": cash,
            }
        )
    return cash, rows, still_open


def _exit_reason(position: _Position, *, current_day: date, price: float | None, exit_policy: str) -> str | None:
    if price is None:
        return None
    if current_day >= position.planned_exit_day:
        return "mechanical_horizon"
    if exit_policy == "stop_loss_12pct" and current_day > position.entry_day:
        position_return = price / position.entry_price - 1.0 if position.entry_price else 0.0
        if position_return <= -0.12:
            return "dynamic_stop_loss_12pct"
        return None
    if current_day <= position.entry_day:
        return None
    position_return = price / position.entry_price - 1.0 if position.entry_price else 0.0
    peak_return = position.peak_price / position.entry_price - 1.0 if position.entry_price else 0.0
    drawdown_from_peak = price / position.peak_price - 1.0 if position.peak_price else 0.0
    holding_calendar_days = (current_day - position.entry_day).days
    if exit_policy == "loss_trailing_quick_fail":
        if position_return <= -0.08:
            return "dynamic_stop_loss_8pct"
        if peak_return >= 0.12 and drawdown_from_peak <= -0.06:
            return "dynamic_trailing_profit_giveback"
        if holding_calendar_days <= 7 and peak_return >= 0.06 and position_return <= 0.005:
            return "dynamic_quick_spike_failed"
        return None
    if exit_policy == "late_trend_loss_guard":
        if holding_calendar_days >= 10 and position_return <= -0.08 and drawdown_from_peak <= -0.10:
            return "dynamic_late_trend_loss_guard"
        return None
    if exit_policy == "rank23_late_trend_loss_guard":
        if (
            position.rank >= 2
            and holding_calendar_days >= 10
            and position_return <= -0.08
            and drawdown_from_peak <= -0.10
        ):
            return "dynamic_rank23_late_trend_loss_guard"
        return None
    if exit_policy == "rank3_late_trend_loss_guard":
        if (
            position.rank >= 3
            and holding_calendar_days >= 10
            and position_return <= -0.08
            and drawdown_from_peak <= -0.10
        ):
            return "dynamic_rank3_late_trend_loss_guard"
        return None
    if exit_policy == "rank3_entry_pullback_late_trend_loss_guard":
        distance_from_20d_high = _safe_float(position.entry_features.get("distance_from_20d_high"))
        if (
            position.rank >= 3
            and distance_from_20d_high <= -0.01
            and holding_calendar_days >= 10
            and position_return <= -0.08
            and drawdown_from_peak <= -0.10
        ):
            return "dynamic_rank3_entry_pullback_late_trend_loss_guard"
        return None
    if exit_policy == "rank3_pullback_rank1_quick_fail_guard":
        distance_from_20d_high = _safe_float(position.entry_features.get("distance_from_20d_high"))
        if (
            position.rank == 1
            and holding_calendar_days <= 8
            and peak_return >= 0.06
            and position_return <= -0.02
        ):
            return "dynamic_rank1_quick_spike_failed"
        if (
            position.rank >= 3
            and distance_from_20d_high <= -0.01
            and holding_calendar_days >= 10
            and position_return <= -0.08
            and drawdown_from_peak <= -0.10
        ):
            return "dynamic_rank3_entry_pullback_late_trend_loss_guard"
        return None
    if exit_policy == "rank23_strong_benchmark_pullback_late_loss_guard":
        benchmark_return_20d = _safe_float(position.entry_features.get("benchmark_return_20d"))
        distance_from_20d_high = _safe_float(position.entry_features.get("distance_from_20d_high"))
        if (
            position.rank >= 2
            and benchmark_return_20d >= 0.06
            and distance_from_20d_high <= -0.04
            and holding_calendar_days >= 10
            and position_return <= -0.08
            and drawdown_from_peak <= -0.10
        ):
            return "dynamic_rank23_strong_benchmark_pullback_late_loss_guard"
        return None
    if exit_policy != "profit_guard_quick_fail_trend_break":
        return None
    if position_return <= -0.10:
        return "dynamic_stop_loss_10pct"
    if holding_calendar_days <= 7 and peak_return >= 0.08 and position_return <= 0.01:
        return "dynamic_quick_spike_failed"
    if peak_return >= 0.18 and drawdown_from_peak <= -0.08 and position_return >= 0.04:
        return "dynamic_profit_guard_giveback"
    if holding_calendar_days >= 14 and position_return <= -0.03 and drawdown_from_peak <= -0.08:
        return "dynamic_trend_break_loss"
    return None


def _summary(
    *,
    config: dict[str, Any],
    nav_rows: list[dict[str, Any]],
    order_rows: list[dict[str, Any]],
    reason_counts: Counter[str],
    accepted_signal_count: int,
    initial_cash_cny: float,
) -> dict[str, Any]:
    final_nav = nav_rows[-1]["nav_cny"] if nav_rows else initial_cash_cny
    buys = [row for row in order_rows if row["action"] == "buy"]
    sells = [row for row in order_rows if row["action"] == "sell"]
    skips = [row for row in order_rows if row["action"] == "skip"]
    no_orders = [row for row in order_rows if row["action"] == "no_order"]
    accepted_signal_days = {
        str(row.get("signal_day") or "")
        for row in order_rows
        if row.get("action") in {"buy", "skip", "no_order"} and row.get("signal_day")
    }
    bought_signal_days = {str(row.get("signal_day") or "") for row in buys if row.get("signal_day")}
    skipped_signal_count = len(accepted_signal_days - bought_signal_days)
    monthly = _monthly_returns(nav_rows, initial_cash_cny=initial_cash_cny)
    invested_ratios = [row["invested_ratio"] for row in nav_rows]
    drawdown = _max_drawdown([row["nav_cny"] for row in nav_rows])
    return {
        "initial_cash_cny": initial_cash_cny,
        "final_nav_cny": final_nav,
        "total_return": final_nav / initial_cash_cny - 1.0 if initial_cash_cny else 0.0,
        "max_drawdown": drawdown,
        "negative_month_count": sum(1 for row in monthly if row["return"] < 0),
        "worst_monthly_return": min((row["return"] for row in monthly), default=0.0),
        "accepted_signal_count": accepted_signal_count,
        "buy_order_count": len(buys),
        "sell_order_count": len(sells),
        "skip_order_count": len(skips),
        "no_order_count": len(no_orders),
        "skipped_order_rate": len(skips) / max(len(skips) + len(buys), 1),
        "skipped_signal_count": skipped_signal_count,
        "skipped_signal_rate": skipped_signal_count / max(accepted_signal_count, 1),
        "mean_invested_ratio": mean(invested_ratios) if invested_ratios else 0.0,
        "p95_invested_ratio": _p95(invested_ratios),
        "max_invested_ratio": max(invested_ratios, default=0.0),
        "max_position_count": max((row["open_position_count"] for row in nav_rows), default=0),
        "max_single_signal_deployment_pct": config["per_signal_target_budget_pct"],
        "max_single_symbol_exposure_pct": max((row["max_single_symbol_exposure_pct"] for row in nav_rows), default=0.0),
        "turnover": (
            sum(_safe_float(row.get("cash_spent_cny")) for row in buys)
            + sum(_safe_float(row.get("proceeds_cny")) for row in sells)
        )
        / initial_cash_cny
        if initial_cash_cny
        else 0.0,
        "reason_counts": dict(reason_counts),
    }


def _nav_row(
    current_day: date,
    *,
    cash: float,
    open_positions: list[_Position],
    bars_by_symbol: dict[str, list[_Bar]],
) -> dict[str, Any]:
    values_by_symbol: Counter[str] = Counter()
    invested = 0.0
    for position in open_positions:
        price = _price_on_day(bars_by_symbol.get(position.symbol) or [], current_day)
        if price is not None:
            position.last_price = price
        value = position.shares * position.last_price
        values_by_symbol[position.symbol] += value
        invested += value
    nav = cash + invested
    return {
        "day": current_day.isoformat(),
        "cash_cny": cash,
        "invested_value_cny": invested,
        "nav_cny": nav,
        "invested_ratio": invested / nav if nav else 0.0,
        "open_position_count": len(open_positions),
        "max_single_symbol_exposure_pct": max(values_by_symbol.values(), default=0.0) / nav if nav else 0.0,
    }


def _skip(
    signal_day: date,
    symbol: str,
    stock_name: str,
    rank: int,
    reason: str,
    target_notional: float | None = None,
) -> dict[str, Any]:
    return {
        "action": "skip",
        "reason": reason,
        "signal_day": signal_day.isoformat(),
        "trade_day": signal_day.isoformat(),
        "symbol": symbol,
        "stock_name": stock_name,
        "rank": rank,
        "target_notional_cny": target_notional,
    }


def _normalize_bars(market_bars_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, list[_Bar]]:
    result: dict[str, list[_Bar]] = {}
    for symbol, rows in market_bars_by_symbol.items():
        bars = [
            _Bar(day=_parse_day(row["day"]), close=_safe_float(row.get("close")))
            for row in rows
            if row.get("day") and _safe_float(row.get("close")) > 0
        ]
        result[symbol] = sorted(bars, key=lambda row: row.day)
    return result


def _max_planned_exit_day(entry_requests_by_day: dict[date, list[dict[str, Any]]]) -> date | None:
    if any(
        request.get("planned_exit_day") is None
        for requests in entry_requests_by_day.values()
        for request in requests
    ):
        return None
    return max(
        (
            request["planned_exit_day"]
            for requests in entry_requests_by_day.values()
            for request in requests
            if isinstance(request.get("planned_exit_day"), date)
        ),
        default=max(entry_requests_by_day, default=None),
    )


def _active_days(signal_days: list[date], bars_by_symbol: dict[str, list[_Bar]], *, end_day: date | None) -> list[date]:
    if not signal_days:
        return []
    first = signal_days[0]
    all_days = sorted({bar.day for bars in bars_by_symbol.values() for bar in bars})
    last = end_day or max(all_days, default=first)
    return [day for day in all_days if first <= day <= last]


def _next_bar_index_after(bars: list[_Bar], signal_day: date) -> int | None:
    for index, bar in enumerate(bars):
        if bar.day > signal_day:
            return index
    return None


def _price_on_day(bars: list[_Bar], day: date) -> float | None:
    for bar in bars:
        if bar.day == day:
            return bar.close
    return None


def _monthly_returns(nav_rows: list[dict[str, Any]], *, initial_cash_cny: float) -> list[dict[str, Any]]:
    if not nav_rows:
        return []
    month_end: dict[str, float] = {}
    for row in nav_rows:
        month_end[str(row["day"])[:7]] = _safe_float(row.get("nav_cny"))
    rows: list[dict[str, Any]] = []
    previous = initial_cash_cny
    for month, nav in sorted(month_end.items()):
        rows.append({"month": month, "ending_nav_cny": nav, "return": nav / previous - 1.0 if previous else 0.0})
        previous = nav
    return rows


def _max_drawdown(values: list[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        peak = value if peak is None else max(peak, value)
        if peak and peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def _annualized_return(nav_rows: list[dict[str, Any]], *, start_day: date | None, initial_cash_cny: float) -> float:
    if not nav_rows or start_day is None or initial_cash_cny <= 0:
        return 0.0
    end_day = _parse_day(nav_rows[-1]["day"])
    years = (end_day - start_day).days / 365.25
    if years <= 0:
        return 0.0
    final_nav = _safe_float(nav_rows[-1].get("nav_cny"), initial_cash_cny)
    return (final_nav / initial_cash_cny) ** (1.0 / years) - 1.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) < 20:
        return max(values)
    return quantiles(values, n=20, method="inclusive")[18]


def _trial_diagnostic(candidate_run: dict[str, Any], *, trial_id: str) -> dict[str, Any]:
    for row in candidate_run.get("trial_diagnostics") or []:
        if isinstance(row, dict) and row.get("trial_id") == trial_id:
            return row
    raise ValueError(f"trial_id not found: {trial_id}")


def _parse_day(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
