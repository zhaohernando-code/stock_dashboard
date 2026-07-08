from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from math import sqrt
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.research_artifact_store import (
    _ensure_artifact_write_allowed,
    artifact_path,
    write_research_validation_artifact,
)

MODEL_EXPLORATION_PROTOCOL_VERSION = "shortpick_model_exploration_p1:v1"
MODEL_EXPLORATION_FEATURE_VERSION = "shortpick_model_pit_feature_matrix:v3"
MODEL_EXPLORATION_LABEL_VERSION = "shortpick_model_executable_label_matrix:v3"
MODEL_EXPLORATION_ACCOUNT_PROFILE = "new_retail_cash_account"
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"
DEFAULT_HORIZONS = (5, 10, 20)
ENTRY_PRICE_SOURCE_NEXT_CLOSE = "next_close"
ENTRY_PRICE_SOURCE_SAME_DAY_CLOSE_PROXY = "same_day_close_research_proxy"
ENTRY_PRICE_SOURCES = {ENTRY_PRICE_SOURCE_NEXT_CLOSE, ENTRY_PRICE_SOURCE_SAME_DAY_CLOSE_PROXY}


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return current / previous - 1


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _std(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = sum(values) / len(values)
    return (sum((value - avg) ** 2 for value in values) / len(values)) ** 0.5


def _observed_day(value: datetime) -> date:
    return value.date()


def _bar_row(stock: Stock, bar: MarketBar) -> dict[str, Any]:
    return {
        "id": bar.id,
        "bar_key": bar.bar_key,
        "stock_id": stock.id,
        "symbol": stock.symbol,
        "observed_at": bar.observed_at,
        "observed_date": _observed_day(bar.observed_at),
        "open_price": float(bar.open_price),
        "high_price": float(bar.high_price),
        "low_price": float(bar.low_price),
        "close_price": float(bar.close_price),
        "volume": float(bar.volume),
        "amount": float(bar.amount),
        "turnover_rate": bar.turnover_rate,
        "total_mv": bar.total_mv,
        "circ_mv": bar.circ_mv,
        "pe_ttm": bar.pe_ttm,
        "pb": bar.pb,
        "lineage_hash": bar.lineage_hash,
    }


def _is_benchmark_stock(stock: Stock) -> bool:
    profile = stock.profile_payload or {}
    return stock.symbol in {"000300.SH", "000905.SH", "000852.SH"} or str(profile.get("industry") or "") == "benchmark"


def _is_st_stock(stock: Stock) -> bool:
    profile = stock.profile_payload or {}
    name = str(stock.name or profile.get("name") or "")
    return bool(profile.get("is_st")) or name.upper().startswith(("ST", "*ST"))


def _board(stock: Stock) -> str:
    profile = stock.profile_payload or {}
    if profile.get("board"):
        return str(profile["board"])
    ticker = str(stock.ticker or stock.symbol.split(".")[0])
    if ticker.startswith(("688", "689")):
        return "STAR"
    if ticker.startswith(("300", "301")):
        return "ChiNext"
    if ticker.startswith(("8", "4")):
        return "BSE"
    if ticker.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
        return "main_board"
    return "unknown"


def _account_eligibility(stock: Stock) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if stock.status != "active":
        reasons.append("stock_status_not_active")
    if stock.delisted_date is not None:
        reasons.append("delisted")
    if _is_st_stock(stock):
        reasons.append("st_or_special_treatment")
    if _is_benchmark_stock(stock):
        reasons.append("benchmark_index_not_stock_candidate")
    if _board(stock) != "main_board":
        reasons.append("not_new_retail_main_board")
    return not reasons, reasons


def _limit_state(current: dict[str, Any], previous: dict[str, Any] | None) -> str:
    if previous is None:
        return "unknown_no_previous_bar"
    daily_return = _pct_change(_safe_float(current["close_price"]), _safe_float(previous["close_price"]))
    if daily_return is None:
        return "unknown_previous_close_zero"
    if daily_return >= 0.095:
        return "limit_up_like"
    if daily_return <= -0.095:
        return "limit_down_like"
    return "normal"


def _window(values: list[float], size: int) -> list[float]:
    return values[-size:] if len(values) >= size else values[:]


def _return_from(closes: list[float], horizon: int) -> float | None:
    if len(closes) <= horizon:
        return None
    return _pct_change(closes[-1], closes[-horizon - 1])


def _execution_state_for_bar(
    *,
    bar: dict[str, Any] | None,
    previous_bar: dict[str, Any] | None,
    side: str,
    price_source: str,
) -> dict[str, Any]:
    if bar is None:
        return {
            "date": None,
            "price_source": price_source,
            "side": side,
            "limit_state": None,
            "volume": None,
            "amount": None,
            "close_price": None,
            "status": "blocked",
            "block_reasons": ["missing_bar"],
        }
    limit_state = _limit_state(bar, previous_bar)
    block_reasons: list[str] = []
    if _safe_float(bar.get("volume")) <= 0:
        block_reasons.append("suspended_or_stale")
    if side == "buy" and limit_state == "limit_up_like":
        block_reasons.append("unbuyable_limit_up")
    if side == "sell" and limit_state == "limit_down_like":
        block_reasons.append("unsellable_limit_down")
    return {
        "date": bar["observed_date"].isoformat(),
        "price_source": price_source,
        "side": side,
        "limit_state": limit_state,
        "volume": _safe_float(bar.get("volume")),
        "amount": _safe_float(bar.get("amount")),
        "close_price": _safe_float(bar.get("close_price")),
        "status": "blocked" if block_reasons else "tradable_research_proxy",
        "block_reasons": block_reasons,
    }


def _features_for_bars(
    *,
    symbol: str,
    stock_name: str | None = None,
    board: str | None = None,
    industry_code: str | None = None,
    industry_name: str | None = None,
    as_of_day: date,
    stock_bars: list[dict[str, Any]],
    stock_index: int,
    benchmark_bars: list[dict[str, Any]],
    benchmark_index: int | None,
    universe_row_id: str,
    source_snapshot_id: str,
) -> dict[str, Any]:
    stock_window = stock_bars[max(0, stock_index - 40) : stock_index + 1]
    benchmark_window = (
        benchmark_bars[max(0, benchmark_index - 20) : benchmark_index + 1]
        if benchmark_index is not None
        else []
    )
    closes = [_safe_float(row["close_price"]) for row in stock_window]
    highs = [_safe_float(row["high_price"]) for row in stock_window]
    amounts = [_safe_float(row["amount"]) for row in stock_window]
    volumes = [_safe_float(row["volume"]) for row in stock_window]
    returns = [
        value
        for index in range(1, len(closes))
        if (value := _pct_change(closes[index], closes[index - 1])) is not None
    ]
    benchmark_closes = [_safe_float(row["close_price"]) for row in benchmark_window]
    current = stock_bars[stock_index]
    previous = stock_bars[stock_index - 1] if stock_index >= 1 else None
    daily_return = _pct_change(_safe_float(current["close_price"]), _safe_float(previous["close_price"])) if previous else None
    avg_amount_20d = _mean(_window(amounts, 20))
    feature_values = {
        "price_momentum": {
            "return_3d": _return_from(closes, 3),
            "return_5d": _return_from(closes, 5),
            "return_10d": _return_from(closes, 10),
            "return_20d": _return_from(closes, 20),
            "return_40d": _return_from(closes, 40),
            "benchmark_return_20d": _return_from(benchmark_closes, 20),
        },
        "reversal_overheat": {
            "return_1d": daily_return,
            "distance_from_20d_high": closes[-1] / max(_window(highs, 20) or [closes[-1]]) - 1 if closes[-1] else None,
            "distance_from_40d_high": closes[-1] / max(_window(highs, 40) or [closes[-1]]) - 1 if closes[-1] else None,
        },
        "volatility_risk": {
            "volatility_10d": _std(_window(returns, 10)) * sqrt(10),
            "volatility_20d": _std(_window(returns, 20)) * sqrt(20),
            "max_drawdown_20d": closes[-1] / max(_window(highs, 20) or [closes[-1]]) - 1 if closes[-1] else None,
            "max_drawdown_40d": closes[-1] / max(_window(highs, 40) or [closes[-1]]) - 1 if closes[-1] else None,
        },
        "liquidity": {
            "avg_amount_10d": _mean(_window(amounts, 10)),
            "avg_amount_20d": avg_amount_20d,
            "avg_volume_20d": _mean(_window(volumes, 20)),
            "turnover_rate": current.get("turnover_rate"),
            "zero_volume_count_20d": sum(1 for value in _window(volumes, 20) if value <= 0),
        },
        "valuation_capacity": {
            "total_mv": current.get("total_mv"),
            "circ_mv": current.get("circ_mv"),
            "pe_ttm": current.get("pe_ttm"),
            "pb": current.get("pb"),
        },
        "execution": {
            "limit_state": _limit_state(current, previous),
            "suspension_or_stale_proxy": _safe_float(current.get("volume")) <= 0,
            "t_plus_1_required": True,
            "board_lot_size": 100,
        },
        "regime": {
            "benchmark_return_10d": _return_from(benchmark_closes, 10),
            "benchmark_return_20d": _return_from(benchmark_closes, 20),
            "benchmark_volatility_20d": _std(
                [
                    value
                    for index in range(1, len(benchmark_closes))
                    if (value := _pct_change(benchmark_closes[index], benchmark_closes[index - 1])) is not None
                ][-20:]
            )
            * sqrt(20),
        },
        "crowding": {
            "amount_vs_20d_avg": _safe_float(current.get("amount")) / max(avg_amount_20d, 1.0),
            "symbol_recent_exposure_count": 0,
            "winner_identity_used": False,
        },
    }
    row = {
        "row_id": f"feature:{symbol}:{as_of_day.isoformat()}",
        "universe_row_id": universe_row_id,
        "symbol": symbol,
        "stock_name": stock_name,
        "board": board,
        "industry_code": industry_code,
        "industry_name": industry_name,
        "as_of_date": as_of_day.isoformat(),
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "feature_group_versions": {
            "price_momentum": "v1",
            "reversal_overheat": "v1",
            "volatility_risk": "v1",
            "liquidity": "v1",
            "valuation_capacity": "v1",
            "execution": "v1",
            "regime": "v1",
            "crowding": "v1",
        },
        "source_input_snapshot_id": source_snapshot_id,
        "source_cutoff_at_or_before_as_of": True,
        "latest_feature_bar_date": as_of_day.isoformat(),
        "missing_feature_flags": _missing_feature_flags(feature_values, benchmark_window),
        "diagnostic_only_features": [],
        "feature_values": feature_values,
    }
    row["row_digest"] = _stable_digest(row)
    return row


def _missing_feature_flags(feature_values: dict[str, Any], benchmark_until_as_of: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if len(benchmark_until_as_of) < 21:
        flags.append("limited_benchmark_history")
    for group_name, group in feature_values.items():
        if isinstance(group, dict) and any(value is None for value in group.values()):
            flags.append(f"{group_name}_partial")
    return sorted(set(flags))


def _group_value(row: dict[str, Any], group: str, key: str) -> float:
    return _safe_float(((row.get("feature_values") or {}).get(group) or {}).get(key))


def _percentiles(values: list[float]) -> list[float]:
    if len(values) <= 1:
        return [0.0 for _ in values]
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0 for _ in values]
    for rank, index in enumerate(order):
        ranks[index] = rank / (len(values) - 1)
    return ranks


def _enrich_cross_sectional_features(
    feature_rows: list[dict[str, Any]],
    universe_rows: list[dict[str, Any]],
) -> None:
    universe_by_row_id = {str(row["row_id"]): row for row in universe_rows}
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in feature_rows:
        rows_by_date.setdefault(str(row["as_of_date"]), []).append(row)

    percentile_specs = {
        "return_5d": ("price_momentum", "return_5d"),
        "return_20d": ("price_momentum", "return_20d"),
        "turnover_rate": ("liquidity", "turnover_rate"),
        "volatility_20d": ("volatility_risk", "volatility_20d"),
        "amount_vs_20d_avg": ("crowding", "amount_vs_20d_avg"),
        "total_mv": ("valuation_capacity", "total_mv"),
        "circ_mv": ("valuation_capacity", "circ_mv"),
        "pe_ttm": ("valuation_capacity", "pe_ttm"),
        "pb": ("valuation_capacity", "pb"),
    }
    for rows in rows_by_date.values():
        percentile_values: dict[str, list[float]] = {}
        for output_name, (group, key) in percentile_specs.items():
            percentile_values[f"{output_name}_pct"] = _percentiles([_group_value(row, group, key) for row in rows])

        industry_return_5d: dict[str, list[float]] = {}
        industry_return_20d: dict[str, list[float]] = {}
        for row in rows:
            universe_row = universe_by_row_id.get(str(row.get("universe_row_id"))) or {}
            industry_name = str(universe_row.get("industry_name") or "unknown")
            industry_return_5d.setdefault(industry_name, []).append(_group_value(row, "price_momentum", "return_5d"))
            industry_return_20d.setdefault(industry_name, []).append(_group_value(row, "price_momentum", "return_20d"))
        industry_median_5d = {industry: _median(values) for industry, values in industry_return_5d.items()}
        industry_median_20d = {industry: _median(values) for industry, values in industry_return_20d.items()}

        amount_10d_vs_20d_values: list[float] = []
        for row in rows:
            avg_amount_10d = _group_value(row, "liquidity", "avg_amount_10d")
            avg_amount_20d = _group_value(row, "liquidity", "avg_amount_20d")
            amount_10d_vs_20d_values.append(avg_amount_10d / max(avg_amount_20d, 1.0) - 1.0)
        amount_10d_vs_20d_percentiles = _percentiles(amount_10d_vs_20d_values)

        for index, row in enumerate(rows):
            values = row["feature_values"]
            avg_amount_10d = _group_value(row, "liquidity", "avg_amount_10d")
            avg_amount_20d = _group_value(row, "liquidity", "avg_amount_20d")
            volatility_10d = _group_value(row, "volatility_risk", "volatility_10d")
            volatility_20d = _group_value(row, "volatility_risk", "volatility_20d")
            universe_row = universe_by_row_id.get(str(row.get("universe_row_id"))) or {}
            industry_name = str(universe_row.get("industry_name") or "unknown")
            values["cross_sectional"] = {
                "return_5d_percentile": percentile_values["return_5d_pct"][index],
                "return_20d_percentile": percentile_values["return_20d_pct"][index],
                "turnover_rate_percentile": percentile_values["turnover_rate_pct"][index],
                "volatility_20d_percentile": percentile_values["volatility_20d_pct"][index],
                "amount_vs_20d_avg_percentile": percentile_values["amount_vs_20d_avg_pct"][index],
                "total_mv_percentile": percentile_values["total_mv_pct"][index],
                "circ_mv_percentile": percentile_values["circ_mv_pct"][index],
                "pe_ttm_percentile": percentile_values["pe_ttm_pct"][index],
                "pb_percentile": percentile_values["pb_pct"][index],
                "low_turnover_percentile": 1.0 - percentile_values["turnover_rate_pct"][index],
                "low_volatility_percentile": 1.0 - percentile_values["volatility_20d_pct"][index],
                "small_total_mv_percentile": 1.0 - percentile_values["total_mv_pct"][index],
                "small_circ_mv_percentile": 1.0 - percentile_values["circ_mv_pct"][index],
                "industry_return_5d_excess": _group_value(row, "price_momentum", "return_5d")
                - industry_median_5d.get(industry_name, 0.0),
                "industry_return_20d_excess": _group_value(row, "price_momentum", "return_20d")
                - industry_median_20d.get(industry_name, 0.0),
                "amount_10d_vs_20d": avg_amount_10d / max(avg_amount_20d, 1.0) - 1.0,
                "amount_10d_vs_20d_percentile": amount_10d_vs_20d_percentiles[index],
                "volatility_10d_vs_20d": volatility_10d / max(volatility_20d, 0.000001) - 1.0,
            }
            row["feature_group_versions"]["cross_sectional"] = "v1"
            if any(value is None for value in values["cross_sectional"].values()):
                row["missing_feature_flags"] = sorted(
                    set(row.get("missing_feature_flags") or []) | {"cross_sectional_partial"}
                )
            row["row_digest"] = _stable_digest(
                {
                    "row_id": row.get("row_id"),
                    "universe_row_id": row.get("universe_row_id"),
                    "symbol": row.get("symbol"),
                    "as_of_date": row.get("as_of_date"),
                    "feature_version": row.get("feature_version"),
                    "feature_values": row.get("feature_values"),
                    "missing_feature_flags": row.get("missing_feature_flags"),
                }
            )


def _label_for_row(
    *,
    symbol: str,
    as_of_day: date,
    stock_bars: list[dict[str, Any]],
    stock_index: int,
    benchmark_bars: list[dict[str, Any]],
    benchmark_by_day: dict[date, int],
    horizons: tuple[int, ...],
    universe_row_id: str,
    source_snapshot_id: str,
    entry_price_source: str,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"unsupported entry_price_source: {entry_price_source}")
    entry_offset = 1 if entry_price_source == ENTRY_PRICE_SOURCE_NEXT_CLOSE else 0
    entry_index = stock_index + entry_offset
    entry_bar = stock_bars[entry_index] if entry_index < len(stock_bars) else None
    entry_day = entry_bar["observed_date"] if entry_bar else as_of_day
    entry_close = _safe_float(entry_bar["close_price"]) if entry_bar else None
    benchmark_entry_index = benchmark_by_day.get(entry_day)
    labels: dict[str, Any] = {}
    block_reasons: set[str] = set()
    if entry_bar is None:
        block_reasons.add("missing_stock_entry_bar")
    if benchmark_entry_index is None:
        block_reasons.add("missing_benchmark_entry_bar")
    previous_entry_bar = stock_bars[entry_index - 1] if entry_index > 0 and entry_bar is not None else None
    entry_execution = _execution_state_for_bar(
        bar=entry_bar,
        previous_bar=previous_entry_bar,
        side="buy",
        price_source=entry_price_source,
    )
    for reason in entry_execution["block_reasons"]:
        if reason == "missing_bar":
            continue
        if reason == "suspended_or_stale":
            block_reasons.add("suspended_or_stale_entry")
        elif reason == "unbuyable_limit_up":
            block_reasons.add("unbuyable_limit_up_entry")
        else:
            block_reasons.add(f"{reason}_entry")

    exit_dates_by_horizon: dict[str, str | None] = {}
    exit_tradability_by_horizon: dict[str, str] = {}
    exit_execution_by_horizon: dict[str, dict[str, Any]] = {}
    for horizon in horizons:
        stock_exit_index = entry_index + horizon
        stock_exit = stock_bars[stock_exit_index] if stock_exit_index < len(stock_bars) else None
        stock_exit_previous = stock_bars[stock_exit_index - 1] if stock_exit is not None and stock_exit_index > 0 else None
        benchmark_exit = (
            benchmark_bars[benchmark_entry_index + horizon]
            if benchmark_entry_index is not None and benchmark_entry_index + horizon < len(benchmark_bars)
            else None
        )
        stock_return = _pct_change(_safe_float(stock_exit["close_price"]), entry_close) if stock_exit and entry_close else None
        benchmark_return = None
        if benchmark_entry_index is not None and benchmark_exit is not None:
            benchmark_entry_close = _safe_float(benchmark_bars[benchmark_entry_index]["close_price"])
            benchmark_return = _pct_change(_safe_float(benchmark_exit["close_price"]), benchmark_entry_close)
        if stock_exit is None:
            block_reasons.add(f"missing_stock_exit_bar_{horizon}d")
        if benchmark_exit is None:
            block_reasons.add(f"missing_benchmark_exit_bar_{horizon}d")
        labels[f"forward_return_{horizon}d"] = stock_return
        labels[f"benchmark_return_{horizon}d"] = benchmark_return
        labels[f"excess_return_{horizon}d"] = (
            stock_return - benchmark_return if stock_return is not None and benchmark_return is not None else None
        )
        exit_execution = _execution_state_for_bar(
            bar=stock_exit,
            previous_bar=stock_exit_previous,
            side="sell",
            price_source="future_close_research_proxy",
        )
        horizon_key = str(horizon)
        exit_dates_by_horizon[horizon_key] = exit_execution["date"]
        exit_execution_by_horizon[horizon_key] = exit_execution
        if stock_exit is None:
            exit_tradability_by_horizon[horizon_key] = "blocked"
        else:
            exit_tradability_by_horizon[horizon_key] = str(exit_execution["status"])
        for reason in exit_execution["block_reasons"]:
            if reason == "missing_bar":
                continue
            if reason == "suspended_or_stale":
                block_reasons.add(f"suspended_or_stale_exit_{horizon}d")
            elif reason == "unsellable_limit_down":
                block_reasons.add(f"unsellable_limit_down_exit_{horizon}d")
            else:
                block_reasons.add(f"{reason}_exit_{horizon}d")

    excess_10d = labels.get("excess_return_10d")
    net_excess_10d = excess_10d - 0.001 if excess_10d is not None else None
    labels["net_excess_return_10d_after_costs"] = net_excess_10d
    labels["top_quantile_label_10d"] = net_excess_10d is not None and net_excess_10d > 0
    label_status = "ready" if not block_reasons and labels.get("excess_return_10d") is not None else "blocked"
    row = {
        "row_id": f"label:{symbol}:{as_of_day.isoformat()}",
        "universe_row_id": universe_row_id,
        "symbol": symbol,
        "as_of_date": as_of_day.isoformat(),
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "source_input_snapshot_id": source_snapshot_id,
        "entry_price_source": entry_price_source,
        "signal_date": as_of_day.isoformat(),
        "entry_date": entry_day.isoformat() if entry_bar else None,
        "entry_execution": entry_execution,
        "entry_trade_day_offset": entry_offset,
        "exit_price_source": "future_close_research_proxy",
        "exit_dates_by_horizon": exit_dates_by_horizon,
        "exit_tradability_by_horizon": exit_tradability_by_horizon,
        "exit_execution_by_horizon": exit_execution_by_horizon,
        "cost_assumption": {"round_trip_cost": 0.001, "stress_multiplier": 2.0},
        "tradability_status": "blocked" if block_reasons else "tradable_research_proxy",
        "label_block_reasons": sorted(block_reasons),
        "label_status": label_status,
        "labels": labels,
    }
    row["row_digest"] = _stable_digest(row)
    return row


def _recent_as_of_dates(
    session: Session,
    *,
    benchmark_symbol: str,
    limit: int,
    forward_horizon_days: int = 0,
    entry_trade_day_offset: int = 0,
) -> list[date]:
    benchmark = session.scalar(select(Stock).where(Stock.symbol == benchmark_symbol).limit(1))
    if benchmark is not None:
        rows = list(
            session.scalars(
                select(MarketBar.observed_at)
                .where(MarketBar.stock_id == benchmark.id, MarketBar.timeframe == "1d")
                .order_by(MarketBar.observed_at.asc(), MarketBar.id.asc())
            )
        )
        benchmark_days = sorted({_observed_day(row) for row in rows})
        required_forward_days = forward_horizon_days + entry_trade_day_offset
        eligible_days = (
            benchmark_days[: -required_forward_days]
            if required_forward_days > 0 and len(benchmark_days) > required_forward_days
            else benchmark_days
        )
        return eligible_days[-limit:]
    rows = list(
        session.scalars(
            select(MarketBar.observed_at)
            .where(MarketBar.timeframe == "1d")
            .order_by(MarketBar.observed_at.asc(), MarketBar.id.asc())
        )
    )
    market_days = sorted({_observed_day(row) for row in rows})
    required_forward_days = forward_horizon_days + entry_trade_day_offset
    eligible_days = (
        market_days[: -required_forward_days]
        if required_forward_days > 0 and len(market_days) > required_forward_days
        else market_days
    )
    return eligible_days[-limit:]


def _bars_by_stock(
    session: Session,
    *,
    start_day: date | None = None,
    end_day: date | None = None,
) -> tuple[dict[str, Stock], dict[str, list[dict[str, Any]]]]:
    stocks = list(session.scalars(select(Stock).order_by(Stock.symbol.asc(), Stock.id.asc())).all())
    stocks_by_symbol = {stock.symbol: stock for stock in stocks}
    stocks_by_id = {int(stock.id): stock for stock in stocks}
    bar_query = select(MarketBar).where(MarketBar.timeframe == "1d")
    if start_day is not None:
        bar_query = bar_query.where(MarketBar.observed_at >= datetime.combine(start_day, datetime.min.time(), tzinfo=UTC))
    if end_day is not None:
        bar_query = bar_query.where(MarketBar.observed_at <= datetime.combine(end_day, datetime.max.time(), tzinfo=UTC))
    bars = list(session.scalars(bar_query.order_by(MarketBar.observed_at, MarketBar.id)))
    by_symbol: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in stocks_by_symbol}
    for bar in bars:
        stock = stocks_by_id.get(int(bar.stock_id))
        if stock is None:
            continue
        by_symbol.setdefault(stock.symbol, []).append(_bar_row(stock, bar))
    for rows in by_symbol.values():
        rows.sort(key=lambda row: (row["observed_date"], row["id"]))
    return stocks_by_symbol, by_symbol


def _ordered_days_from_input_snapshot(session: Session, input_snapshot: dict[str, Any]) -> list[date]:
    protocol = input_snapshot.get("validation_protocol") or {}
    source_range = input_snapshot.get("source_data_time_range") or {}
    benchmark_symbol = str(protocol.get("benchmark_symbol") or DEFAULT_BENCHMARK_SYMBOL)
    as_of_start = date.fromisoformat(str(source_range["as_of_start"]))
    as_of_end = date.fromisoformat(str(source_range["as_of_end"]))
    benchmark = session.scalar(select(Stock).where(Stock.symbol == benchmark_symbol).limit(1))
    if benchmark is None:
        raise ValueError(f"benchmark stock not found for input snapshot: {benchmark_symbol}")
    rows = list(
        session.scalars(
            select(MarketBar.observed_at)
            .where(
                MarketBar.stock_id == benchmark.id,
                MarketBar.timeframe == "1d",
                MarketBar.observed_at >= datetime.combine(as_of_start, datetime.min.time(), tzinfo=UTC),
                MarketBar.observed_at <= datetime.combine(as_of_end, datetime.max.time(), tzinfo=UTC),
            )
            .order_by(MarketBar.observed_at.asc(), MarketBar.id.asc())
        )
    )
    ordered_days = sorted({_observed_day(row) for row in rows})
    expected_count = int(input_snapshot.get("as_of_date_count") or 0)
    if expected_count and len(ordered_days) != expected_count:
        raise ValueError(
            "input snapshot as_of date count mismatch: "
            f"expected {expected_count}, rebuilt {len(ordered_days)} from {benchmark_symbol}"
        )
    return ordered_days


def _iter_label_rows_from_input_snapshot(
    session: Session,
    *,
    input_snapshot: dict[str, Any],
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    min_history_days: int = 2,
) -> Any:
    protocol = input_snapshot.get("validation_protocol") or {}
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"unsupported entry_price_source: {entry_price_source}")
    benchmark_symbol = str(protocol.get("benchmark_symbol") or DEFAULT_BENCHMARK_SYMBOL)
    horizons = tuple(int(value) for value in (protocol.get("horizons") or DEFAULT_HORIZONS))
    ordered_days = _ordered_days_from_input_snapshot(session, input_snapshot)
    start_day = min(ordered_days) - timedelta(days=90) if ordered_days else None
    end_day = max(ordered_days) + timedelta(days=max(horizons) * 3 + 10) if ordered_days else None
    stocks_by_symbol, bars_by_symbol = _bars_by_stock(session, start_day=start_day, end_day=end_day)
    benchmark_bars = bars_by_symbol.get(benchmark_symbol, [])
    benchmark_by_day = {row["observed_date"]: index for index, row in enumerate(benchmark_bars)}
    eligible_symbols = [
        symbol
        for symbol, stock in sorted(stocks_by_symbol.items())
        if _account_eligibility(stock)[0] and bars_by_symbol.get(symbol)
    ]
    source_snapshot_id = str(input_snapshot.get("artifact_id") or "")
    for symbol in eligible_symbols:
        rows = bars_by_symbol[symbol]
        index_by_day = {row["observed_date"]: index for index, row in enumerate(rows)}
        for as_of_day in ordered_days:
            stock_index = index_by_day.get(as_of_day)
            if stock_index is None or stock_index + 1 < min_history_days:
                continue
            yield _label_for_row(
                symbol=symbol,
                as_of_day=as_of_day,
                stock_bars=rows,
                stock_index=stock_index,
                benchmark_bars=benchmark_bars,
                benchmark_by_day=benchmark_by_day,
                horizons=horizons,
                universe_row_id=f"universe:{symbol}:{as_of_day.isoformat()}",
                source_snapshot_id=source_snapshot_id,
                entry_price_source=entry_price_source,
            )


def _eligible_symbols_from_input_snapshot(
    input_snapshot: dict[str, Any],
    *,
    stocks_by_symbol: dict[str, Stock],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> list[str]:
    stock_metadata = input_snapshot.get("stock_metadata")
    if isinstance(stock_metadata, list):
        symbols = [
            str(row.get("symbol") or "")
            for row in stock_metadata
            if isinstance(row, dict) and row.get("eligible_for_account_profile")
        ]
        return sorted(symbol for symbol in symbols if symbol in stocks_by_symbol and bars_by_symbol.get(symbol))
    return sorted(
        symbol
        for symbol, stock in stocks_by_symbol.items()
        if _account_eligibility(stock)[0] and bars_by_symbol.get(symbol)
    )


def _iter_feature_date_rows_from_input_snapshot(
    session: Session,
    *,
    input_snapshot: dict[str, Any],
    min_history_days: int = 2,
) -> Any:
    protocol = input_snapshot.get("validation_protocol") or {}
    benchmark_symbol = str(protocol.get("benchmark_symbol") or DEFAULT_BENCHMARK_SYMBOL)
    ordered_days = _ordered_days_from_input_snapshot(session, input_snapshot)
    start_day = min(ordered_days) - timedelta(days=90) if ordered_days else None
    end_day = max(ordered_days) if ordered_days else None
    stocks_by_symbol, bars_by_symbol = _bars_by_stock(session, start_day=start_day, end_day=end_day)
    benchmark_bars = bars_by_symbol.get(benchmark_symbol, [])
    benchmark_by_day = {row["observed_date"]: index for index, row in enumerate(benchmark_bars)}
    eligible_symbols = _eligible_symbols_from_input_snapshot(
        input_snapshot,
        stocks_by_symbol=stocks_by_symbol,
        bars_by_symbol=bars_by_symbol,
    )
    index_by_symbol_day = {
        symbol: {row["observed_date"]: index for index, row in enumerate(bars_by_symbol.get(symbol, []))}
        for symbol in eligible_symbols
    }
    source_snapshot_id = str(input_snapshot.get("artifact_id") or "")
    for as_of_day in ordered_days:
        universe_rows: list[dict[str, Any]] = []
        feature_rows: list[dict[str, Any]] = []
        benchmark_index = benchmark_by_day.get(as_of_day)
        for symbol in eligible_symbols:
            stock = stocks_by_symbol[symbol]
            rows = bars_by_symbol[symbol]
            stock_index = index_by_symbol_day[symbol].get(as_of_day)
            if stock_index is None or stock_index + 1 < min_history_days:
                continue
            current = rows[stock_index]
            previous = rows[stock_index - 1] if stock_index > 0 else None
            universe_row = {
                "row_id": f"universe:{symbol}:{as_of_day.isoformat()}",
                "symbol": symbol,
                "as_of_date": as_of_day.isoformat(),
                "stock_name": stock.name,
                "board": _board(stock),
                "industry_code": (stock.profile_payload or {}).get("industry_code"),
                "industry_name": (stock.profile_payload or {}).get("industry"),
                "eligible_for_account_profile": True,
                "account_profile": MODEL_EXPLORATION_ACCOUNT_PROFILE,
                "eligibility_reasons": [],
                "has_market_bar": True,
                "has_benchmark_bar": as_of_day in benchmark_by_day,
                "is_st": _is_st_stock(stock),
                "is_suspended_or_stale": _safe_float(current.get("volume")) <= 0,
                "limit_state": _limit_state(current, previous),
                "tradable_lot_size": 100,
                "source_lineage": {
                    "stock_id": stock.id,
                    "market_bar_id": current["id"],
                    "market_bar_key": current["bar_key"],
                    "market_bar_lineage_hash": current.get("lineage_hash"),
                },
            }
            universe_row["row_digest"] = _stable_digest(universe_row)
            universe_rows.append(universe_row)
            feature_rows.append(
                _features_for_bars(
                    symbol=symbol,
                    stock_name=stock.name,
                    board=universe_row["board"],
                    industry_code=universe_row["industry_code"],
                    industry_name=universe_row["industry_name"],
                    as_of_day=as_of_day,
                    stock_bars=rows,
                    stock_index=stock_index,
                    benchmark_bars=benchmark_bars,
                    benchmark_index=benchmark_index,
                    universe_row_id=universe_row["row_id"],
                    source_snapshot_id=source_snapshot_id,
                )
            )
        _enrich_cross_sectional_features(feature_rows, universe_rows)
        yield feature_rows


def _feature_gate_readout_from_counts(*, row_count: int) -> dict[str, Any]:
    blockers = [] if row_count else ["missing_feature_rows"]
    return {
        "gate_status": "blocked" if blockers else "feature_matrix_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "feature_matrix_only",
        "blocking_gate_ids": blockers,
    }


def rebuild_pit_feature_matrix_from_input_snapshot(
    session: Session,
    *,
    input_snapshot: dict[str, Any],
    validation_run_id: str,
    artifact_root: str | Path,
) -> dict[str, Any]:
    temp_dir = artifact_path("pit_feature_matrix", "feature-rebuild-temp", root=Path(artifact_root)).parent
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_rows = temp_dir / f".{validation_run_id}.rows.jsonl.tmp"
    if temp_rows.exists():
        temp_rows.unlink()
    digest_hasher = hashlib.sha256()
    row_count = 0
    with temp_rows.open("w", encoding="utf-8") as temp_handle:
        for rows in _iter_feature_date_rows_from_input_snapshot(session, input_snapshot=input_snapshot):
            for row in rows:
                row_count += 1
                digest_hasher.update(str(row.get("row_digest") or "").encode("utf-8"))
                digest_hasher.update(b"\n")
                temp_handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
                temp_handle.write("\n")
    row_content_digest = digest_hasher.hexdigest()
    artifact_id = f"pit-feature-matrix-{row_content_digest[:16]}"
    target = artifact_path("pit_feature_matrix", artifact_id, root=Path(artifact_root))
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    artifact_refs = input_snapshot.get("artifact_refs") or {}
    metadata = {
        "artifact_type": "pit_feature_matrix",
        "schema_version": "pit_feature_matrix.v1",
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": generated_at,
        "source_db_snapshot_id": input_snapshot.get("source_db_snapshot_id"),
        "source_data_time_range": input_snapshot.get("source_data_time_range"),
        "code_version": "unresolved_local_checkout",
        "config_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
        "storage_boundary": "research_validation_artifact_store_only",
        "promotion_status": "blocked_from_production",
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "label_version": "not_applicable_feature_matrix",
        "source_input_snapshot_id": input_snapshot.get("artifact_id"),
        "source_universe_date_matrix_id": artifact_refs.get("universe_date_matrix"),
        "validation_protocol": input_snapshot.get("validation_protocol"),
        "gate_readout": _feature_gate_readout_from_counts(row_count=row_count),
        "claim_ceiling": "feature_matrix_only",
        "row_count": row_count,
        "row_content_digest": row_content_digest,
        "feature_groups": [
            "price_momentum",
            "reversal_overheat",
            "volatility_risk",
            "liquidity",
            "valuation_capacity",
            "execution",
            "regime",
            "crowding",
            "cross_sectional",
        ],
    }
    with target.open("w", encoding="utf-8") as handle:
        handle.write("{\n")
        for _index, key in enumerate(sorted(metadata)):
            handle.write(f"  {json.dumps(key, ensure_ascii=False)}: ")
            handle.write(json.dumps(metadata[key], ensure_ascii=False, sort_keys=True, default=str))
            handle.write(",\n")
        handle.write('  "rows": [\n')
        first = True
        with temp_rows.open("r", encoding="utf-8") as temp_handle:
            for line in temp_handle:
                if not first:
                    handle.write(",\n")
                first = False
                handle.write(line.rstrip("\n"))
        handle.write("\n  ]\n}\n")
    temp_rows.unlink(missing_ok=True)
    return {
        **metadata,
        "path": str(target),
        "rows_written": row_count,
    }


def rebuild_executable_label_matrix_from_input_snapshot(
    session: Session,
    *,
    input_snapshot: dict[str, Any],
    validation_run_id: str,
    artifact_root: str | Path,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
) -> dict[str, Any]:
    digest_hasher = hashlib.sha256()
    row_count = 0
    ready_count = 0
    for row in _iter_label_rows_from_input_snapshot(
        session,
        input_snapshot=input_snapshot,
        entry_price_source=entry_price_source,
    ):
        row_count += 1
        if row.get("label_status") == "ready":
            ready_count += 1
        digest_hasher.update(str(row.get("row_digest") or "").encode("utf-8"))
        digest_hasher.update(b"\n")
    row_content_digest = digest_hasher.hexdigest()
    artifact_id = f"executable-label-matrix-{row_content_digest[:16]}"
    target = artifact_path("executable_label_matrix", artifact_id, root=Path(artifact_root))
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    protocol = dict(input_snapshot.get("validation_protocol") or {})
    protocol["entry_price_source"] = entry_price_source
    protocol["entry_trade_day_offset"] = 1 if entry_price_source == ENTRY_PRICE_SOURCE_NEXT_CLOSE else 0
    generated_at = datetime.now(UTC).isoformat()
    artifact_refs = input_snapshot.get("artifact_refs") or {}
    metadata = {
        "artifact_type": "executable_label_matrix",
        "schema_version": "executable_label_matrix.v1",
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": generated_at,
        "source_db_snapshot_id": input_snapshot.get("source_db_snapshot_id"),
        "source_data_time_range": input_snapshot.get("source_data_time_range"),
        "code_version": "unresolved_local_checkout",
        "config_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
        "storage_boundary": "research_validation_artifact_store_only",
        "promotion_status": "blocked_from_production",
        "feature_version": "not_applicable_label_matrix",
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "source_input_snapshot_id": input_snapshot.get("artifact_id"),
        "source_universe_date_matrix_id": artifact_refs.get("universe_date_matrix"),
        "validation_protocol": protocol,
        "gate_readout": _label_gate_readout_from_counts(row_count=row_count, ready_count=ready_count),
        "claim_ceiling": "label_matrix_only",
        "row_count": row_count,
        "row_content_digest": row_content_digest,
    }
    with target.open("w", encoding="utf-8") as handle:
        handle.write("{\n")
        for index, key in enumerate(sorted(metadata)):
            handle.write(f"  {json.dumps(key, ensure_ascii=False)}: ")
            handle.write(json.dumps(metadata[key], ensure_ascii=False, sort_keys=True, default=str))
            handle.write(",\n")
        handle.write('  "rows": [\n')
        first = True
        for row in _iter_label_rows_from_input_snapshot(
            session,
            input_snapshot=input_snapshot,
            entry_price_source=entry_price_source,
        ):
            if not first:
                handle.write(",\n")
            first = False
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
        handle.write("\n  ]\n}\n")
    return {
        **metadata,
        "path": str(target),
        "rows_written": row_count,
        "ready_rows": ready_count,
    }


def build_model_exploration_p1_artifacts(
    session: Session,
    *,
    validation_run_id: str,
    as_of_dates: list[date] | None = None,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    min_history_days: int = 2,
    max_as_of_dates: int | None = None,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
) -> dict[str, dict[str, Any]]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"unsupported entry_price_source: {entry_price_source}")
    entry_trade_day_offset = 1 if entry_price_source == ENTRY_PRICE_SOURCE_NEXT_CLOSE else 0
    ordered_days = sorted(set(as_of_dates or []))
    if not ordered_days and max_as_of_dates is not None:
        ordered_days = _recent_as_of_dates(
            session,
            benchmark_symbol=benchmark_symbol,
            limit=max_as_of_dates,
            forward_horizon_days=max(horizons),
            entry_trade_day_offset=entry_trade_day_offset,
        )
    start_day = min(ordered_days) - timedelta(days=90) if ordered_days else None
    end_day = max(ordered_days) + timedelta(days=max(horizons) * 3 + 10) if ordered_days else None
    stocks_by_symbol, bars_by_symbol = _bars_by_stock(session, start_day=start_day, end_day=end_day)
    benchmark_bars = bars_by_symbol.get(benchmark_symbol, [])
    benchmark_by_day = {row["observed_date"]: index for index, row in enumerate(benchmark_bars)}
    eligible_symbols: list[str] = []
    stock_metadata: list[dict[str, Any]] = []
    for symbol, stock in sorted(stocks_by_symbol.items()):
        eligible, reasons = _account_eligibility(stock)
        if eligible and bars_by_symbol.get(symbol):
            eligible_symbols.append(symbol)
        stock_metadata.append(
            {
                "symbol": symbol,
                "stock_id": stock.id,
                "stock_name": stock.name,
                "board": _board(stock),
                "status": stock.status,
                "eligible_for_account_profile": eligible,
                "eligibility_reasons": reasons,
                "bar_count": len(bars_by_symbol.get(symbol, [])),
            }
        )

    candidate_days = set(ordered_days)
    if not candidate_days:
        for symbol in eligible_symbols:
            rows = bars_by_symbol.get(symbol, [])
            for index, row in enumerate(rows):
                if index + 1 >= min_history_days:
                    candidate_days.add(row["observed_date"])
    ordered_days = sorted(candidate_days)
    if max_as_of_dates is not None:
        ordered_days = ordered_days[-max_as_of_dates:]

    source_digest = _stable_digest(
        {
            "validation_run_id": validation_run_id,
            "benchmark_symbol": benchmark_symbol,
            "eligible_symbols": eligible_symbols,
            "as_of_dates": [day.isoformat() for day in ordered_days],
            "horizons": horizons,
            "stock_metadata": stock_metadata,
        }
    )
    input_snapshot_id = f"model-exploration-input-snapshot-{source_digest[:16]}"
    universe_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []

    for symbol in eligible_symbols:
        stock = stocks_by_symbol[symbol]
        rows = bars_by_symbol[symbol]
        index_by_day = {row["observed_date"]: index for index, row in enumerate(rows)}
        for as_of_day in ordered_days:
            stock_index = index_by_day.get(as_of_day)
            if stock_index is None or stock_index + 1 < min_history_days:
                continue
            current = rows[stock_index]
            previous = rows[stock_index - 1] if stock_index > 0 else None
            universe_row = {
                "row_id": f"universe:{symbol}:{as_of_day.isoformat()}",
                "symbol": symbol,
                "as_of_date": as_of_day.isoformat(),
                "stock_name": stock.name,
                "board": _board(stock),
                "industry_code": (stock.profile_payload or {}).get("industry_code"),
                "industry_name": (stock.profile_payload or {}).get("industry"),
                "eligible_for_account_profile": True,
                "account_profile": MODEL_EXPLORATION_ACCOUNT_PROFILE,
                "eligibility_reasons": [],
                "has_market_bar": True,
                "has_benchmark_bar": as_of_day in benchmark_by_day,
                "is_st": _is_st_stock(stock),
                "is_suspended_or_stale": _safe_float(current.get("volume")) <= 0,
                "limit_state": _limit_state(current, previous),
                "tradable_lot_size": 100,
                "source_lineage": {
                    "stock_id": stock.id,
                    "market_bar_id": current["id"],
                    "market_bar_key": current["bar_key"],
                    "market_bar_lineage_hash": current.get("lineage_hash"),
                },
            }
            universe_row["row_digest"] = _stable_digest(universe_row)
            universe_rows.append(universe_row)
            benchmark_index = benchmark_by_day.get(as_of_day)
            feature_rows.append(
                _features_for_bars(
                    symbol=symbol,
                    stock_name=stock.name,
                    board=universe_row["board"],
                    industry_code=universe_row["industry_code"],
                    industry_name=universe_row["industry_name"],
                    as_of_day=as_of_day,
                    stock_bars=rows,
                    stock_index=stock_index,
                    benchmark_bars=benchmark_bars,
                    benchmark_index=benchmark_index,
                    universe_row_id=universe_row["row_id"],
                    source_snapshot_id=input_snapshot_id,
                )
            )
            label_rows.append(
                _label_for_row(
                    symbol=symbol,
                    as_of_day=as_of_day,
                    stock_bars=rows,
                    stock_index=stock_index,
                    benchmark_bars=benchmark_bars,
                    benchmark_by_day=benchmark_by_day,
                    horizons=horizons,
                    universe_row_id=universe_row["row_id"],
                    source_snapshot_id=input_snapshot_id,
                    entry_price_source=entry_price_source,
                )
            )

    _enrich_cross_sectional_features(feature_rows, universe_rows)
    universe_digest = _stable_digest([row.get("row_digest") for row in universe_rows])
    feature_digest = _stable_digest([row.get("row_digest") for row in feature_rows])
    label_digest = _stable_digest([row.get("row_digest") for row in label_rows])
    universe_artifact_id = f"universe-date-matrix-{universe_digest[:16]}"
    feature_artifact_id = f"pit-feature-matrix-{feature_digest[:16]}"
    label_artifact_id = f"executable-label-matrix-{label_digest[:16]}"
    generated_at = datetime.now(UTC).isoformat()
    common = {
        "validation_run_id": validation_run_id,
        "generated_at": generated_at,
        "source_db_snapshot_id": source_digest[:16],
        "source_data_time_range": {
            "as_of_start": ordered_days[0].isoformat() if ordered_days else None,
            "as_of_end": ordered_days[-1].isoformat() if ordered_days else None,
        },
        "code_version": "unresolved_local_checkout",
        "config_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
        "storage_boundary": "research_validation_artifact_store_only",
        "promotion_status": "blocked_from_production",
    }
    input_snapshot = {
        **common,
        "artifact_type": "model_exploration_input_snapshot",
        "schema_version": "model_exploration_input_snapshot.v1",
        "artifact_id": input_snapshot_id,
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "validation_protocol": {
            "protocol_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
            "primary_row_source": "objective_universe_x_as_of_date",
            "forbidden_primary_sources": [
                "recommendation_rows",
                "active_watchlist",
                "factor_observation_rows",
                "recommendation_payload.factor_breakdown",
                "post_hoc_winner_identity",
            ],
            "benchmark_symbol": benchmark_symbol,
            "horizons": list(horizons),
            "entry_price_source": entry_price_source,
            "entry_trade_day_offset": entry_trade_day_offset,
        },
        "gate_readout": _matrix_gate_readout(len(eligible_symbols), len(ordered_days), len(universe_rows)),
        "claim_ceiling": "data_coverage_blocked"
        if len(eligible_symbols) < 200 or len(ordered_days) < 60 or len(universe_rows) < 12000
        else "model_research_input_only",
        "stock_metadata": stock_metadata,
        "eligible_symbol_count": len(eligible_symbols),
        "as_of_date_count": len(ordered_days),
        "universe_row_count": len(universe_rows),
        "benchmark_symbol": benchmark_symbol,
        "artifact_refs": {
            "universe_date_matrix": universe_artifact_id,
            "pit_feature_matrix": feature_artifact_id,
            "executable_label_matrix": label_artifact_id,
        },
    }
    universe_matrix = {
        **common,
        "artifact_type": "universe_date_matrix",
        "schema_version": "universe_date_matrix.v1",
        "artifact_id": universe_artifact_id,
        "feature_version": "not_applicable_universe_matrix",
        "label_version": "not_applicable_universe_matrix",
        "source_input_snapshot_id": input_snapshot_id,
        "validation_protocol": input_snapshot["validation_protocol"],
        "gate_readout": _matrix_gate_readout(len(eligible_symbols), len(ordered_days), len(universe_rows)),
        "claim_ceiling": input_snapshot["claim_ceiling"],
        "row_count": len(universe_rows),
        "row_content_digest": universe_digest,
        "rows": universe_rows,
    }
    feature_matrix = {
        **common,
        "artifact_type": "pit_feature_matrix",
        "schema_version": "pit_feature_matrix.v1",
        "artifact_id": feature_artifact_id,
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "label_version": "not_applicable_feature_matrix",
        "source_input_snapshot_id": input_snapshot_id,
        "source_universe_date_matrix_id": universe_artifact_id,
        "validation_protocol": input_snapshot["validation_protocol"],
        "gate_readout": _feature_gate_readout(feature_rows),
        "claim_ceiling": "feature_matrix_only",
        "row_count": len(feature_rows),
        "row_content_digest": feature_digest,
        "feature_groups": [
            "price_momentum",
            "reversal_overheat",
            "volatility_risk",
            "liquidity",
            "valuation_capacity",
            "execution",
            "regime",
            "crowding",
            "cross_sectional",
        ],
        "rows": feature_rows,
    }
    label_matrix = {
        **common,
        "artifact_type": "executable_label_matrix",
        "schema_version": "executable_label_matrix.v1",
        "artifact_id": label_artifact_id,
        "feature_version": "not_applicable_label_matrix",
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "source_input_snapshot_id": input_snapshot_id,
        "source_universe_date_matrix_id": universe_artifact_id,
        "validation_protocol": input_snapshot["validation_protocol"],
        "gate_readout": _label_gate_readout(label_rows),
        "claim_ceiling": "label_matrix_only",
        "row_count": len(label_rows),
        "row_content_digest": label_digest,
        "rows": label_rows,
    }
    return {
        "model_exploration_input_snapshot": input_snapshot,
        "universe_date_matrix": universe_matrix,
        "pit_feature_matrix": feature_matrix,
        "executable_label_matrix": label_matrix,
    }


def _matrix_gate_readout(unique_symbols: int, as_of_dates: int, total_rows: int) -> dict[str, Any]:
    blockers: list[str] = []
    if unique_symbols < 200:
        blockers.append("insufficient_unique_symbols_for_model_claims")
    if as_of_dates < 60:
        blockers.append("insufficient_as_of_dates_for_model_claims")
    if total_rows < 12000:
        blockers.append("insufficient_universe_date_rows_for_model_claims")
    return {
        "gate_status": "blocked" if blockers else "research_input_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "data_coverage_blocked" if blockers else "model_research_input_only",
        "blocking_gate_ids": blockers,
        "thresholds": {
            "minimum_unique_symbols_for_claims": 200,
            "minimum_as_of_dates_for_claims": 60,
            "minimum_total_rows_for_claims": 12000,
        },
    }


def _feature_gate_readout(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [] if rows else ["missing_feature_rows"]
    return {
        "gate_status": "blocked" if blockers else "feature_matrix_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "feature_matrix_only",
        "blocking_gate_ids": blockers,
    }


def _label_gate_readout(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ready_rows = sum(1 for row in rows if row.get("label_status") == "ready")
    return _label_gate_readout_from_counts(row_count=len(rows), ready_count=ready_rows)


def _label_gate_readout_from_counts(*, row_count: int, ready_count: int) -> dict[str, Any]:
    blockers: list[str] = []
    if row_count <= 0:
        blockers.append("missing_label_rows")
    if ready_count < row_count:
        blockers.append("blocked_or_partial_label_rows")
    return {
        "gate_status": "blocked" if blockers else "label_matrix_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "label_matrix_only",
        "blocking_gate_ids": blockers,
        "ready_row_count": ready_count,
        "row_count": row_count,
    }


def write_model_exploration_p1_artifacts(
    artifacts: dict[str, dict[str, Any]],
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(artifact_root) if artifact_root else None
    written: dict[str, Path] = {}
    for artifact_type, payload in artifacts.items():
        written[artifact_type] = write_research_validation_artifact(
            artifact_type,
            str(payload["artifact_id"]),
            payload,
            root=root,
        )
    return written
