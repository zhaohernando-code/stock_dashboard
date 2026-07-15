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
RANK5_REPLACEMENT_QUALITY_KEYS = frozenset(
    {
        "max_score_gap",
        "min_avg_amount_20d",
        "min_return_20d_percentile",
        "min_return_5d_percentile",
        "min_distance_from_20d_high",
        "max_path_realized_volatility_20d",
        "max_path_downside_semivolatility_20d",
        "min_path_max_drawdown_20d",
        "min_path_up_day_ratio_20d",
        "min_path_trend_efficiency_20d",
    }
)


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
    candidate_inventory_rows: list[dict[str, Any]] | None = None,
    candidate_configurations: list[dict[str, Any]] | None = None,
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
    inventory_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_inventory_rows or []:
        if isinstance(row, dict) and row.get("as_of_date"):
            inventory_by_day[_parse_day(row["as_of_date"])].append(row)
    configurations = candidate_configurations or contract["candidate_configurations"]
    results = [
        _simulate_config(
            config,
            picks_by_day=picks_by_day,
            inventory_by_day=inventory_by_day,
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
        for config in configurations
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


def project_shortpick_v3_initial_entry_orders(
    *,
    config: dict[str, Any],
    picks: list[dict[str, Any]],
    signal_day: date,
    planned_entry_day: date,
    estimated_close_by_symbol: dict[str, float],
    selected_top_k: int,
    initial_cash_cny: float = DEFAULT_INITIAL_CASH_CNY,
    buy_cost_bps: float = DEFAULT_BUY_COST_BPS,
    board_lot_size: int = DEFAULT_BOARD_LOT_SIZE,
    max_single_symbol_cost_basis_pct: float = DEFAULT_MAX_SINGLE_SYMBOL_COST_BASIS_PCT,
    min_order_notional_cny: float = DEFAULT_MIN_ORDER_NOTIONAL_CNY,
    account_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project frozen forward orders with the same sizing and account constraints as replay."""

    budget_mode = str(config.get("budget_mode") or "fixed_initial_cash_fraction")
    max_single_signal_deployment_pct = _safe_float(
        config.get("max_single_signal_deployment_pct"),
        DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT,
    )
    per_signal_budget = float(config["per_signal_target_budget_cny"])
    current_nav_cny = _safe_float((account_state or {}).get("latest_nav_cny"), initial_cash_cny)
    if budget_mode == "current_nav_fraction":
        per_signal_budget = min(
            current_nav_cny / max(float(config["target_active_tranche_count"]), 1.0),
            current_nav_cny * max_single_signal_deployment_pct,
        )
    bars_by_symbol = {
        symbol: [_Bar(day=planned_entry_day, close=float(close))]
        for symbol, close in estimated_close_by_symbol.items()
        if close and close > 0
    }
    requests = [
        {
            "pick": pick,
            "signal_day": signal_day,
            "entry_index": 0,
            "planned_exit_day": OPEN_ENDED_EXIT_DAY,
        }
        for pick in picks
        if str(pick.get("symbol") or "") in bars_by_symbol
    ]
    existing_positions = _positions_from_account_state(account_state)
    rows, _cash, _positions = _process_entry_buys(
        planned_entry_day,
        cash=_safe_float((account_state or {}).get("cash_cny"), initial_cash_cny),
        open_positions=existing_positions,
        requests=requests,
        rank_allocation_mode=str(config.get("rank_allocation_mode") or "model_rank_weight_with_board_lot_skip"),
        bars_by_symbol=bars_by_symbol,
        selected_top_k=selected_top_k,
        per_signal_budget=per_signal_budget,
        board_lot_size=board_lot_size,
        buy_cost_rate=buy_cost_bps / 10000.0,
        initial_cash_cny=initial_cash_cny,
        max_single_symbol_cost_basis_pct=max_single_symbol_cost_basis_pct,
        min_order_notional_cny=_safe_float(config.get("min_order_notional_cny"), min_order_notional_cny),
    )
    symbols_with_price = set(bars_by_symbol)
    missing_price_rows = [
        _skip(
            signal_day,
            str(pick.get("symbol") or ""),
            str(pick.get("stock_name") or pick.get("name") or pick.get("symbol") or ""),
            int(float(pick.get("rank") or 0)),
            "missing_latest_close_price",
        )
        for pick in picks
        if str(pick.get("symbol") or "") not in symbols_with_price
    ]
    return [*rows, *missing_price_rows]


def _positions_from_account_state(account_state: dict[str, Any] | None) -> list[_Position]:
    positions: list[_Position] = []
    for row in (account_state or {}).get("positions") or []:
        if not isinstance(row, dict):
            continue
        try:
            positions.append(
                _Position(
                    signal_day=_parse_day(row["signal_date"]),
                    entry_day=_parse_day(row["entry_date"]),
                    planned_exit_day=OPEN_ENDED_EXIT_DAY,
                    symbol=str(row["symbol"]),
                    stock_name=str(row.get("name") or row["symbol"]),
                    rank=int(float(row.get("rank") or 0)),
                    shares=int(float(row.get("shares") or 0)),
                    entry_price=_safe_float(row.get("entry_price_cny")),
                    cost_basis=_safe_float(row.get("cost_basis_cny")),
                    target_notional=_safe_float(row.get("target_notional_cny")),
                    last_price=_safe_float(row.get("last_price_cny"), _safe_float(row.get("entry_price_cny"))),
                    peak_price=_safe_float(row.get("peak_price_cny"), _safe_float(row.get("entry_price_cny"))),
                    entry_features=dict(row.get("entry_features") or {}),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return [position for position in positions if position.shares > 0]


def _simulate_config(
    config: dict[str, Any],
    *,
    picks_by_day: dict[date, list[dict[str, Any]]],
    inventory_by_day: dict[date, list[dict[str, Any]]],
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
    executable_picks_by_day = _apply_rank1_quality_overlay(picks_by_day, config=config)
    entry_requests_by_day, pre_loop_skips = _entry_requests_by_day(
        accepted_signals,
        picks_by_day=executable_picks_by_day,
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
    max_single_signal_deployment_pct = _safe_float(
        config.get("max_single_signal_deployment_pct"),
        DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT,
    )
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
                    current_nav * max_single_signal_deployment_pct,
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
                affordable_replacement_policy=config.get("affordable_replacement_policy"),
                inventory_by_day=inventory_by_day,
            )
            order_rows.extend(buys)
            reason_counts.update(row["reason"] for row in buys if row["action"] == "skip")
        cash, rebalance_sells, open_positions = _process_market_value_concentration_rebalance(
            current_day,
            cash=cash,
            open_positions=open_positions,
            bars_by_symbol=bars_by_symbol,
            policy=config.get("market_value_concentration_rebalance"),
        )
        order_rows.extend(rebalance_sells)
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
    affordable_replacement_policy: Any = None,
    inventory_by_day: dict[date, list[dict[str, Any]]] | None = None,
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
        if (
            not _bought
            and len(buy_rows) == 1
            and buy_rows[0].get("reason") == "price_too_high_for_slot"
            and isinstance(affordable_replacement_policy, dict)
        ):
            replacement_request = _affordable_replacement_request(
                request,
                trade_day=trade_day,
                target_notional=target_notional,
                positions=positions,
                signal_requests=ordered_requests,
                inventory_by_day=inventory_by_day or {},
                bars_by_symbol=bars_by_symbol,
                policy=affordable_replacement_policy,
                board_lot_size=board_lot_size,
                buy_cost_rate=buy_cost_rate,
                min_order_notional_cny=min_order_notional_cny,
            )
            if replacement_request is not None:
                replacement_rows, cash, positions, replacement_bought = _try_buy_request(
                    replacement_request,
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
                if replacement_bought:
                    replacement_rows[0].update(
                        {
                            "reason": "bought_affordable_rank4_5_replacement",
                            "replacement_original_symbol": str(pick.get("symbol") or ""),
                            "replacement_inventory_rank": int(
                                float((replacement_request["pick"] or {}).get("replacement_inventory_rank") or 0)
                            ),
                        }
                    )
                    rows.extend(replacement_rows)
                    continue
        rows.extend(buy_rows)
    return rows, cash, positions


def _apply_rank1_quality_overlay(
    picks_by_day: dict[date, list[dict[str, Any]]],
    *,
    config: dict[str, Any],
) -> dict[date, list[dict[str, Any]]]:
    overlay = config.get("rank1_quality_overlay")
    if not isinstance(overlay, dict):
        return {day: [dict(row) for row in rows] for day, rows in picks_by_day.items()}
    result: dict[date, list[dict[str, Any]]] = {}
    for signal_day, rows in picks_by_day.items():
        rank1 = next((row for row in rows if int(_safe_float(row.get("rank"))) == 1), None)
        scale = _rank1_quality_scale(rank1, overlay=overlay) if rank1 is not None else 1.0
        result[signal_day] = [
            {
                **row,
                "portfolio_weight": _safe_float(row.get("portfolio_weight"), 1.0) * scale,
                "rank1_quality_overlay_scale": scale,
            }
            for row in rows
        ]
    return result


def _rank1_quality_scale(rank1: dict[str, Any], *, overlay: dict[str, Any]) -> float:
    weak_benchmark_return_20d_lt = overlay.get("weak_benchmark_return_20d_lt")
    if (
        weak_benchmark_return_20d_lt is not None
        and _feature_value(rank1, "benchmark_return_20d") < _safe_float(weak_benchmark_return_20d_lt)
    ):
        return _safe_float(overlay.get("weak_scale"), 1.0)
    checks = (
        _feature_value(rank1, "return_20d_percentile")
        >= _safe_float(overlay.get("strong_return_20d_percentile_min"), 0.95),
        _feature_value(rank1, "return_5d_percentile")
        >= _safe_float(overlay.get("strong_return_5d_percentile_min"), 0.93),
        _feature_value(rank1, "benchmark_return_20d")
        >= _safe_float(overlay.get("strong_benchmark_return_20d_min"), 0.0),
        _feature_value(rank1, "industry_return_20d_excess")
        <= _safe_float(overlay.get("strong_industry_return_20d_excess_max"), 0.50),
        _feature_value(rank1, "distance_from_20d_high")
        >= _safe_float(overlay.get("strong_distance_from_20d_high_min"), -0.08),
    )
    benchmark_return_10d_min = overlay.get("strong_benchmark_return_10d_min")
    if benchmark_return_10d_min is not None:
        checks = (
            *checks,
            _feature_value(rank1, "benchmark_return_10d") >= _safe_float(benchmark_return_10d_min),
        )
    return _safe_float(overlay.get("strong_scale"), 1.0) if all(checks) else 1.0


def _feature_value(row: dict[str, Any], key: str) -> float:
    nested = row.get("rank_weight_feature_values")
    if isinstance(nested, dict) and nested.get(key) is not None:
        return _safe_float(nested.get(key))
    return _safe_float(row.get(key))


def rank5_replacement_quality_rejection_reason(
    candidate: dict[str, Any],
    *,
    inventory_rank: int,
    original_score: float,
    policy: Any,
) -> str | None:
    """Return a fail-closed rejection reason using signal-day-only Rank5 fields."""

    if inventory_rank != 5 or not isinstance(policy, dict):
        return None
    unsupported_keys = sorted(set(policy) - RANK5_REPLACEMENT_QUALITY_KEYS)
    if unsupported_keys:
        raise ValueError(f"unsupported Rank5 replacement quality keys: {unsupported_keys}")
    checks = (
        ("max_score_gap", "score", "rank5_quality_score_gap_above_max", "max"),
        ("min_avg_amount_20d", "avg_amount_20d", "rank5_quality_avg_amount_below_min", "min"),
        (
            "min_return_20d_percentile",
            "return_20d_percentile",
            "rank5_quality_return20_below_min",
            "min",
        ),
        (
            "min_return_5d_percentile",
            "return_5d_percentile",
            "rank5_quality_return5_below_min",
            "min",
        ),
        (
            "min_distance_from_20d_high",
            "distance_from_20d_high",
            "rank5_quality_distance_high_below_min",
            "min",
        ),
        (
            "max_path_realized_volatility_20d",
            "path_realized_volatility_20d",
            "rank5_quality_path_volatility_above_max",
            "max_value",
        ),
        (
            "max_path_downside_semivolatility_20d",
            "path_downside_semivolatility_20d",
            "rank5_quality_path_downside_above_max",
            "max_value",
        ),
        (
            "min_path_max_drawdown_20d",
            "path_max_drawdown_20d",
            "rank5_quality_path_drawdown_below_min",
            "min",
        ),
        (
            "min_path_up_day_ratio_20d",
            "path_up_day_ratio_20d",
            "rank5_quality_path_up_ratio_below_min",
            "min",
        ),
        (
            "min_path_trend_efficiency_20d",
            "path_trend_efficiency_20d",
            "rank5_quality_path_efficiency_below_min",
            "min",
        ),
    )
    for policy_key, feature_key, reason, comparison in checks:
        if policy_key not in policy:
            continue
        raw_value = candidate.get(feature_key)
        if raw_value is None:
            return f"rank5_quality_missing_{feature_key}"
        observed = _safe_float(raw_value)
        threshold = _safe_float(policy[policy_key])
        if comparison == "max":
            if observed < original_score - threshold:
                return reason
        elif comparison == "max_value":
            if observed > threshold:
                return reason
        elif observed < threshold:
            return reason
    return None


def _affordable_replacement_request(
    original_request: dict[str, Any],
    *,
    trade_day: date,
    target_notional: float,
    positions: list[_Position],
    signal_requests: list[dict[str, Any]],
    inventory_by_day: dict[date, list[dict[str, Any]]],
    bars_by_symbol: dict[str, list[_Bar]],
    policy: dict[str, Any],
    board_lot_size: int,
    buy_cost_rate: float,
    min_order_notional_cny: float,
) -> dict[str, Any] | None:
    original_pick = original_request["pick"]
    signal_day = original_request["signal_day"]
    original_score = _safe_float(original_pick.get("score"))
    rank_min = int(_safe_float(policy.get("inventory_rank_min"), 4.0))
    rank_max = int(_safe_float(policy.get("inventory_rank_max"), 5.0))
    max_score_gap = _safe_float(policy.get("max_score_gap"), 0.10)
    min_fill_ratio = _safe_float(policy.get("min_fill_ratio"), 0.75)
    policy_min_notional = _safe_float(policy.get("min_order_notional_cny"), min_order_notional_cny)
    excluded_symbols = {position.symbol for position in positions}
    excluded_symbols.update(str((request.get("pick") or {}).get("symbol") or "") for request in signal_requests)
    candidates = sorted(
        inventory_by_day.get(signal_day, []),
        key=lambda row: int(_safe_float(row.get("rank"), 999.0)),
    )
    for candidate in candidates:
        inventory_rank = int(_safe_float(candidate.get("rank")))
        symbol = str(candidate.get("symbol") or "")
        if not rank_min <= inventory_rank <= rank_max or not symbol or symbol in excluded_symbols:
            continue
        if candidate.get("selection_allowed") is False:
            continue
        if _safe_float(candidate.get("score")) < original_score - max_score_gap:
            continue
        if rank5_replacement_quality_rejection_reason(
            candidate,
            inventory_rank=inventory_rank,
            original_score=original_score,
            policy=policy.get("rank5_quality_policy"),
        ):
            continue
        bars = bars_by_symbol.get(symbol) or []
        entry_index = next((index for index, bar in enumerate(bars) if bar.day == trade_day), None)
        if entry_index is None:
            continue
        one_lot_cash = bars[entry_index].close * board_lot_size * (1.0 + buy_cost_rate)
        lot_count = int(target_notional // one_lot_cash) if one_lot_cash > 0 else 0
        cash_spent = lot_count * one_lot_cash
        fill_ratio = cash_spent / target_notional if target_notional else 0.0
        if one_lot_cash > target_notional or cash_spent < policy_min_notional or fill_ratio < min_fill_ratio:
            continue
        horizon = int(_safe_float(original_pick.get("target_horizon_days"), 20.0))
        exit_index = entry_index + horizon
        replacement_pick = {
            **candidate,
            "rank": int(_safe_float(original_pick.get("rank"))),
            "replacement_inventory_rank": inventory_rank,
            "replacement_original_symbol": str(original_pick.get("symbol") or ""),
            "target_horizon_days": horizon,
        }
        return {
            "pick": replacement_pick,
            "signal_day": signal_day,
            "entry_index": entry_index,
            "exit_index": exit_index if exit_index < len(bars) else None,
            "planned_exit_day": bars[exit_index].day if exit_index < len(bars) else None,
        }
    return None


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


def _process_market_value_concentration_rebalance(
    current_day: date,
    *,
    cash: float,
    open_positions: list[_Position],
    bars_by_symbol: dict[str, list[_Bar]],
    policy: Any,
) -> tuple[float, list[dict[str, Any]], list[_Position]]:
    if not isinstance(policy, dict) or not open_positions:
        return cash, [], open_positions
    threshold = _safe_float(policy.get("threshold"), 0.25)
    board_lot_size = int(_safe_float(policy.get("board_lot_size"), 100.0))
    sell_cost_rate = _safe_float(policy.get("sell_cost_bps"), 25.0) / 10_000.0
    positions = list(open_positions)
    values_by_symbol: Counter[str] = Counter()
    prices: dict[str, float] = {}
    for position in positions:
        price = _price_on_day(bars_by_symbol.get(position.symbol) or [], current_day)
        if price is not None:
            position.last_price = price
        prices[position.symbol] = position.last_price
        values_by_symbol[position.symbol] += position.shares * position.last_price
    nav = cash + sum(values_by_symbol.values())
    rows: list[dict[str, Any]] = []
    for symbol in sorted(values_by_symbol, key=values_by_symbol.get, reverse=True):
        price = prices[symbol]
        symbol_positions = [position for position in positions if position.symbol == symbol]
        available_shares = sum(position.shares for position in symbol_positions)
        post_value = values_by_symbol[symbol]
        post_nav = nav
        sell_shares = 0
        while (
            sell_shares + board_lot_size <= available_shares
            and post_nav > 0
            and post_value / post_nav > threshold
        ):
            sell_shares += board_lot_size
            post_value -= board_lot_size * price
            post_nav -= board_lot_size * price * sell_cost_rate
        if sell_shares <= 0:
            continue
        remaining_to_sell = sell_shares
        removed_cost_basis = 0.0
        for position in sorted(symbol_positions, key=lambda row: (row.entry_day, row.signal_day)):
            if remaining_to_sell <= 0:
                break
            position_sell_shares = min(position.shares, remaining_to_sell)
            cost_basis_per_share = position.cost_basis / position.shares if position.shares else 0.0
            removed_cost_basis += position_sell_shares * cost_basis_per_share
            position.shares -= position_sell_shares
            position.cost_basis -= position_sell_shares * cost_basis_per_share
            remaining_to_sell -= position_sell_shares
        positions = [position for position in positions if position.shares > 0]
        proceeds = sell_shares * price * (1.0 - sell_cost_rate)
        cash += proceeds
        nav = post_nav
        values_by_symbol[symbol] = post_value
        rows.append(
            {
                "action": "sell",
                "reason": "market_value_concentration_rebalance",
                "signal_day": current_day.isoformat(),
                "trade_day": current_day.isoformat(),
                "symbol": symbol,
                "stock_name": symbol_positions[0].stock_name,
                "rank": 0,
                "shares": sell_shares,
                "price": price,
                "cost_basis_cny": removed_cost_basis,
                "proceeds_cny": proceeds,
                "pnl_cny": proceeds - removed_cost_basis,
                "return": proceeds / removed_cost_basis - 1.0 if removed_cost_basis else 0.0,
                "cash_after_cny": cash,
                "exposure_before": (post_value + sell_shares * price) / (post_nav + sell_shares * price * sell_cost_rate)
                if post_nav > 0
                else 0.0,
                "exposure_after": post_value / post_nav if post_nav > 0 else 0.0,
            }
        )
    return cash, rows, positions


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
                "entry_reason": (
                    "bought_affordable_rank4_5_replacement"
                    if position.entry_features.get("replacement_original_symbol")
                    else "bought"
                ),
                "replacement_original_symbol": position.entry_features.get("replacement_original_symbol"),
                "replacement_inventory_rank": position.entry_features.get("replacement_inventory_rank"),
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
        "max_single_signal_deployment_pct": _safe_float(
            config.get("max_single_signal_deployment_pct"),
            config["per_signal_target_budget_pct"],
        ),
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
