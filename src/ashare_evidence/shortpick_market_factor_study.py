from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock

INDEX_SYMBOLS = {"000300.SH", "000905.SH", "000852.SH"}
DEFAULT_STRATEGIES = ("base", "turnover", "ret10", "combo")
DEFAULT_HORIZONS = (1, 3, 5, 10, 20)
LIMIT_UP_BANDS = {
    "default": 0.10,
    "st": 0.05,
    "star_or_chinext": 0.20,
    "beijing": 0.30,
}


@dataclass(frozen=True)
class _Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    amount: float
    turnover: float | None


@dataclass
class _Series:
    symbol: str
    name: str
    bars: list[_Bar]
    by_day: dict[date, int]


def build_shortpick_market_factor_study(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    train_end: date,
    holdout_start: date,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = 20.0,
    apply_limit_up_filter: bool = False,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    walk_forward_lookback_days: int = 120,
) -> dict[str, Any]:
    series_by_symbol = _load_daily_series(session)
    benchmark = series_by_symbol.get("000300.SH")
    if benchmark is None:
        raise LookupError("CSI300 benchmark series 000300.SH is required.")
    signal_days = _eligible_signal_days(series_by_symbol, start_date=start_date, end_date=end_date)
    selections = {
        strategy: _build_strategy_selections(
            series_by_symbol,
            signal_days=signal_days,
            strategy=strategy,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
        for strategy in DEFAULT_STRATEGIES
    }
    rows_by_strategy = {
        strategy: _evaluation_rows(
            series_by_symbol,
            benchmark=benchmark,
            selections=selection,
            horizons=horizons,
            cost_bps=cost_bps,
            apply_limit_up_filter=apply_limit_up_filter,
        )
        for strategy, selection in selections.items()
    }
    walk_forward = _walk_forward_rows(
        rows_by_strategy=rows_by_strategy,
        signal_days=signal_days,
        train_end=train_end,
        holdout_start=holdout_start,
        lookback_days=walk_forward_lookback_days,
    )
    rows_by_strategy["walk_forward_selected"] = walk_forward["rows"]

    periods = {
        "train": {"start": start_date, "end": train_end},
        "holdout": {"start": holdout_start, "end": end_date},
        "replay_window": {"start": max(holdout_start, date(2026, 3, 26)), "end": min(end_date, date(2026, 4, 30))},
        "all": {"start": start_date, "end": end_date},
    }
    period_summary = {
        period: {
            strategy: _summarize_rows(rows, start=window["start"], end=window["end"], horizons=horizons)
            for strategy, rows in rows_by_strategy.items()
        }
        for period, window in periods.items()
    }
    paired_vs_base = {
        period: {
            strategy: _paired_diff(
                rows_by_strategy[strategy],
                rows_by_strategy["base"],
                start=window["start"],
                end=window["end"],
            )
            for strategy in rows_by_strategy
            if strategy != "base"
        }
        for period, window in periods.items()
    }
    monthly = {
        strategy: _monthly_summary(rows, start=start_date, end=end_date)
        for strategy, rows in rows_by_strategy.items()
    }
    return {
        "experiment": "shortpick_market_factor_study",
        "validation_mode": "market_only_after_close_t_plus_1_close_entry",
        "config": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "train_end": train_end.isoformat(),
            "holdout_start": holdout_start.isoformat(),
            "pool_limit": pool_limit,
            "rank_limit": rank_limit,
            "cost_bps": cost_bps,
            "apply_limit_up_filter": apply_limit_up_filter,
            "horizons": list(horizons),
            "walk_forward_lookback_days": walk_forward_lookback_days,
            "strategies": list(rows_by_strategy),
        },
        "data_scope": {
            "signal_day_count": len(signal_days),
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        },
        "period_summary": period_summary,
        "paired_vs_base": paired_vs_base,
        "walk_forward_selection": walk_forward["selection"],
        "monthly_summary": monthly,
    }


def _load_daily_series(session: Session) -> dict[str, _Series]:
    rows = session.execute(
        select(Stock, MarketBar)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    grouped: dict[str, tuple[str, list[_Bar]]] = {}
    for stock, bar in rows:
        day = bar.observed_at.date()
        if not bar.close_price:
            continue
        grouped.setdefault(stock.symbol, (stock.name, []))[1].append(
            _Bar(
                day=day,
                open=float(bar.open_price),
                high=float(bar.high_price),
                low=float(bar.low_price),
                close=float(bar.close_price),
                amount=float(bar.amount or 0.0),
                turnover=None if bar.turnover_rate is None else float(bar.turnover_rate),
            )
        )
    output: dict[str, _Series] = {}
    for symbol, (name, bars) in grouped.items():
        deduped: dict[date, _Bar] = {}
        for bar in bars:
            deduped[bar.day] = bar
        ordered = [deduped[day] for day in sorted(deduped)]
        output[symbol] = _Series(
            symbol=symbol,
            name=name,
            bars=ordered,
            by_day={bar.day: index for index, bar in enumerate(ordered)},
        )
    return output


def _eligible_signal_days(series_by_symbol: dict[str, _Series], *, start_date: date, end_date: date) -> list[date]:
    counts: dict[date, int] = defaultdict(int)
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        for index, bar in enumerate(series.bars):
            if start_date <= bar.day <= end_date and index >= 20 and index + 2 < len(series.bars):
                counts[bar.day] += 1
    return [day for day in sorted(counts) if counts[day] >= 45]


def _build_strategy_selections(
    series_by_symbol: dict[str, _Series],
    *,
    signal_days: list[date],
    strategy: str,
    pool_limit: int,
    rank_limit: int,
) -> dict[date, list[str]]:
    selections: dict[date, list[str]] = {}
    for signal_day in signal_days:
        contexts = [
            context
            for symbol, series in series_by_symbol.items()
            if symbol not in INDEX_SYMBOLS
            for context in [_context_for_signal_day(series, signal_day)]
            if context is not None
        ]
        pool = sorted(
            contexts,
            key=lambda item: (
                item["return_1d"],
                item["amount"],
                item["turnover_rate"],
            ),
            reverse=True,
        )[:pool_limit]
        if not pool:
            selections[signal_day] = []
            continue
        if strategy == "base":
            ranked = pool
        else:
            ranked = sorted(pool, key=lambda item, strategy=strategy: _strategy_score(pool, item, strategy), reverse=True)
        selections[signal_day] = [item["symbol"] for item in ranked[:rank_limit]]
    return selections


def _context_for_signal_day(series: _Series, signal_day: date) -> dict[str, Any] | None:
    index = series.by_day.get(signal_day)
    if index is None or index < 20 or index + 2 >= len(series.bars):
        return None
    latest = series.bars[index]
    if latest.amount <= 0:
        return None
    return {
        "symbol": series.symbol,
        "return_1d": _lookback_return(series, index, 1),
        "return_5d": _lookback_return(series, index, 5),
        "return_10d": _lookback_return(series, index, 10),
        "amount": latest.amount,
        "turnover_rate": latest.turnover or 0.0,
    }


def _lookback_return(series: _Series, index: int, days: int) -> float:
    start = series.bars[index - days]
    end = series.bars[index]
    return end.close / start.close - 1 if start.close else 0.0


def _strategy_score(pool: list[dict[str, Any]], item: dict[str, Any], strategy: str) -> float:
    if strategy == "turnover":
        return _percentile(pool, "turnover_rate", item["symbol"])
    if strategy == "ret10":
        return _percentile(pool, "return_10d", item["symbol"])
    if strategy == "combo":
        return (
            _percentile(pool, "return_1d", item["symbol"])
            + 0.5 * _percentile(pool, "return_5d", item["symbol"])
            + 0.5 * _percentile(pool, "turnover_rate", item["symbol"])
        )
    raise ValueError(f"Unknown strategy: {strategy}")


def _percentile(pool: list[dict[str, Any]], key: str, symbol: str) -> float:
    ranked = sorted(pool, key=lambda item: float(item.get(key) or 0.0), reverse=True)
    if len(ranked) <= 1:
        return 1.0
    for rank, item in enumerate(ranked):
        if item["symbol"] == symbol:
            return 1.0 - rank / (len(ranked) - 1)
    return 0.0


def _evaluation_rows(
    series_by_symbol: dict[str, _Series],
    *,
    benchmark: _Series,
    selections: dict[date, list[str]],
    horizons: tuple[int, ...],
    cost_bps: float,
    apply_limit_up_filter: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    roundtrip_cost = float(cost_bps) / 10000.0
    for signal_day, symbols in selections.items():
        for symbol in symbols:
            series = series_by_symbol.get(symbol)
            if series is None:
                continue
            for horizon in horizons:
                row = _evaluate_one(
                    series=series,
                    benchmark=benchmark,
                    signal_day=signal_day,
                    horizon=horizon,
                    roundtrip_cost=roundtrip_cost,
                    apply_limit_up_filter=apply_limit_up_filter,
                )
                if row is not None:
                    rows.append(row)
    return rows


def _evaluate_one(
    *,
    series: _Series,
    benchmark: _Series,
    signal_day: date,
    horizon: int,
    roundtrip_cost: float,
    apply_limit_up_filter: bool,
) -> dict[str, Any] | None:
    signal_index = series.by_day.get(signal_day)
    if signal_index is None:
        return None
    entry_index = signal_index + 1
    exit_index = entry_index + horizon
    if exit_index >= len(series.bars):
        return None
    entry = series.bars[entry_index]
    previous = series.bars[signal_index]
    if apply_limit_up_filter and _entry_is_unfillable_limit_up(series, entry_index):
        return {
            "signal_day": signal_day,
            "symbol": series.symbol,
            "horizon": horizon,
            "status": "entry_unfillable_limit_up",
        }
    exit_bar = series.bars[exit_index]
    benchmark_entry_index = benchmark.by_day.get(entry.day)
    benchmark_exit_index = benchmark.by_day.get(exit_bar.day)
    if benchmark_entry_index is None or benchmark_exit_index is None:
        return {
            "signal_day": signal_day,
            "symbol": series.symbol,
            "horizon": horizon,
            "status": "pending_benchmark_data",
        }
    stock_return = exit_bar.close / entry.close - 1 if entry.close else None
    benchmark_entry = benchmark.bars[benchmark_entry_index]
    benchmark_exit = benchmark.bars[benchmark_exit_index]
    benchmark_return = benchmark_exit.close / benchmark_entry.close - 1 if benchmark_entry.close else None
    if stock_return is None or benchmark_return is None:
        return None
    return {
        "signal_day": signal_day,
        "symbol": series.symbol,
        "horizon": horizon,
        "status": "completed",
        "entry_day": entry.day,
        "exit_day": exit_bar.day,
        "entry_day_return": entry.close / previous.close - 1 if previous.close else None,
        "stock_return": stock_return,
        "benchmark_return": benchmark_return,
        "excess_return": stock_return - benchmark_return,
        "net_excess_return": stock_return - benchmark_return - roundtrip_cost,
    }


def _entry_is_unfillable_limit_up(series: _Series, entry_index: int) -> bool:
    entry = series.bars[entry_index]
    previous = series.bars[entry_index - 1] if entry_index > 0 else None
    if previous is None or not previous.close:
        return True
    one_price = _near(entry.open, entry.high) and _near(entry.high, entry.low) and _near(entry.low, entry.close)
    limit_band = _limit_band(series.symbol, series.name)
    day_return = entry.close / previous.close - 1
    return bool(one_price and day_return >= limit_band * 0.95)


def _near(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.01, abs(right) * 0.0001)


def _limit_band(symbol: str, name: str) -> float:
    if "ST" in name.upper():
        return LIMIT_UP_BANDS["st"]
    if symbol.endswith(".BJ"):
        return LIMIT_UP_BANDS["beijing"]
    ticker = symbol.split(".", 1)[0]
    if ticker.startswith(("300", "301", "688")):
        return LIMIT_UP_BANDS["star_or_chinext"]
    return LIMIT_UP_BANDS["default"]


def _walk_forward_rows(
    *,
    rows_by_strategy: dict[str, list[dict[str, Any]]],
    signal_days: list[date],
    train_end: date,
    holdout_start: date,
    lookback_days: int,
) -> dict[str, Any]:
    candidate_strategies = [strategy for strategy in DEFAULT_STRATEGIES if strategy != "base"]
    months = sorted({(day.year, day.month) for day in signal_days if day >= holdout_start})
    selection: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    for year, month in months:
        month_days = [day for day in signal_days if day.year == year and day.month == month]
        if not month_days:
            continue
        first_day = month_days[0]
        train_days = [day for day in signal_days if day < first_day]
        lookback = set(train_days[-lookback_days:])
        scores = {
            strategy: _summarize_rows(
                rows_by_strategy[strategy],
                start=min(lookback) if lookback else first_day,
                end=max(lookback) if lookback else first_day,
                horizons=(1, 3, 5, 10),
                allowed_signal_days=lookback,
            )
            for strategy in candidate_strategies
        }
        selected = max(
            candidate_strategies,
            key=lambda strategy: (
                scores[strategy].get("trimmed_mean_net_excess_return") or -999.0,
                scores[strategy].get("positive_net_excess_rate") or 0.0,
            ),
        )
        selection.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "selected_strategy": selected,
                "lookback_signal_day_count": len(lookback),
                "lookback_scores": scores,
            }
        )
        month_set = set(month_days)
        output_rows.extend([row for row in rows_by_strategy[selected] if row["signal_day"] in month_set])
    return {"selection": selection, "rows": output_rows}


def _summarize_rows(
    rows: list[dict[str, Any]],
    *,
    start: date,
    end: date,
    horizons: tuple[int, ...],
    allowed_signal_days: set[date] | None = None,
) -> dict[str, Any]:
    scoped = [
        row for row in rows
        if start <= row["signal_day"] <= end
        and row["horizon"] in horizons
        and (allowed_signal_days is None or row["signal_day"] in allowed_signal_days)
    ]
    completed = [row for row in scoped if row["status"] == "completed"]
    net = [float(row["net_excess_return"]) for row in completed]
    excess = [float(row["excess_return"]) for row in completed]
    by_horizon = {
        str(horizon): _metric_block([row for row in completed if row["horizon"] == horizon])
        for horizon in horizons
    }
    return {
        "signal_day_count": len({row["signal_day"] for row in scoped}),
        "selected_symbol_day_count": len({(row["signal_day"], row["symbol"]) for row in scoped}),
        "completed_count": len(completed),
        "blocked_count": len([row for row in scoped if row["status"] != "completed"]),
        "mean_excess_return": _mean(excess),
        "trimmed_mean_excess_return": _trimmed_mean(excess),
        "positive_excess_rate": _positive_rate(excess),
        "mean_net_excess_return": _mean(net),
        "trimmed_mean_net_excess_return": _trimmed_mean(net),
        "positive_net_excess_rate": _positive_rate(net),
        "by_horizon": by_horizon,
    }


def _metric_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["net_excess_return"]) for row in rows]
    return {
        "completed_count": len(rows),
        "mean_net_excess_return": _mean(values),
        "trimmed_mean_net_excess_return": _trimmed_mean(values),
        "positive_net_excess_rate": _positive_rate(values),
    }


def _paired_diff(
    strategy_rows: list[dict[str, Any]],
    base_rows: list[dict[str, Any]],
    *,
    start: date,
    end: date,
) -> dict[str, Any]:
    strategy_means = _mean_by_day_horizon(strategy_rows, start=start, end=end)
    base_means = _mean_by_day_horizon(base_rows, start=start, end=end)
    diffs = [
        value - base_means[key]
        for key, value in strategy_means.items()
        if key in base_means
    ]
    return {
        "paired_count": len(diffs),
        "mean_diff_net_excess_return": _mean(diffs),
        "trimmed_mean_diff_net_excess_return": _trimmed_mean(diffs),
        "win_rate": _positive_rate(diffs),
    }


def _mean_by_day_horizon(rows: list[dict[str, Any]], *, start: date, end: date) -> dict[tuple[date, int], float]:
    grouped: dict[tuple[date, int], list[float]] = defaultdict(list)
    for row in rows:
        if row["status"] == "completed" and start <= row["signal_day"] <= end:
            grouped[(row["signal_day"], int(row["horizon"]))].append(float(row["net_excess_return"]))
    return {key: _mean(values) or 0.0 for key, values in grouped.items()}


def _monthly_summary(rows: list[dict[str, Any]], *, start: date, end: date) -> list[dict[str, Any]]:
    months = sorted({(row["signal_day"].year, row["signal_day"].month) for row in rows if start <= row["signal_day"] <= end})
    output = []
    for year, month in months:
        month_rows = [
            row for row in rows
            if row["signal_day"].year == year
            and row["signal_day"].month == month
            and row["status"] == "completed"
        ]
        values = [float(row["net_excess_return"]) for row in month_rows]
        output.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "completed_count": len(month_rows),
                "mean_net_excess_return": _mean(values),
                "trimmed_mean_net_excess_return": _trimmed_mean(values),
                "positive_net_excess_rate": _positive_rate(values),
            }
        )
    return output


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _trimmed_mean(values: list[float], proportion: float = 0.1) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    trim = int(len(ordered) * proportion)
    trimmed = ordered[trim : len(ordered) - trim] if len(ordered) - 2 * trim > 0 else ordered
    return _mean(trimmed)


def _positive_rate(values: list[float]) -> float | None:
    return sum(1 for value in values if value > 0) / len(values) if values else None
