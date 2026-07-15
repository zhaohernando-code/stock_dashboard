from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from math import isfinite, sqrt
from statistics import pstdev
from typing import Any

PATH_QUALITY_RETURN_WINDOW = 20
PATH_QUALITY_FEATURE_KEYS = (
    "path_realized_volatility_20d",
    "path_downside_semivolatility_20d",
    "path_max_drawdown_20d",
    "path_up_day_ratio_20d",
    "path_trend_efficiency_20d",
)


def enrich_inventory_with_path_quality_features(
    candidate_inventory_rows: Iterable[Mapping[str, Any]],
    *,
    market_bars_by_symbol: Mapping[str, Iterable[Mapping[str, Any]]],
    return_window: int = PATH_QUALITY_RETURN_WINDOW,
) -> list[dict[str, Any]]:
    """Add signal-day point-in-time close-path features to candidate inventory rows."""

    if return_window <= 0:
        raise ValueError("return_window must be positive")
    indexed_bars = {
        str(symbol): _indexed_valid_closes(rows)
        for symbol, rows in market_bars_by_symbol.items()
    }
    enriched: list[dict[str, Any]] = []
    for source_row in candidate_inventory_rows:
        row = dict(source_row)
        as_of_day = _iso_day(row.get("as_of_date"))
        days, closes = indexed_bars.get(str(row.get("symbol") or ""), ([], []))
        end_index = bisect_right(days, as_of_day) if as_of_day is not None else 0
        available_returns = max(0, min(return_window, end_index - 1))
        row["path_feature_observation_count"] = available_returns
        if available_returns < return_window:
            row.update(dict.fromkeys(PATH_QUALITY_FEATURE_KEYS))
        else:
            path_closes = closes[end_index - return_window - 1 : end_index]
            row.update(_path_quality_features(path_closes))
        enriched.append(row)
    return enriched


def _indexed_valid_closes(rows: Iterable[Mapping[str, Any]]) -> tuple[list[date], list[float]]:
    latest_by_day: dict[date, float] = {}
    for row in rows:
        day = _iso_day(row.get("day"))
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if day is not None and isfinite(close) and close > 0:
            latest_by_day[day] = close
    ordered = sorted(latest_by_day.items())
    return [day for day, _ in ordered], [close for _, close in ordered]


def _path_quality_features(closes: list[float]) -> dict[str, float]:
    returns = [current / previous - 1.0 for previous, current in zip(closes, closes[1:])]
    downside_semivolatility = sqrt(sum(min(value, 0.0) ** 2 for value in returns) / len(returns))
    running_peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        running_peak = max(running_peak, close)
        max_drawdown = min(max_drawdown, close / running_peak - 1.0)
    path_movement = sum(abs(value) for value in returns)
    trend_efficiency = abs(sum(returns)) / path_movement if path_movement else 0.0
    return {
        "path_realized_volatility_20d": pstdev(returns),
        "path_downside_semivolatility_20d": downside_semivolatility,
        "path_max_drawdown_20d": max_drawdown,
        "path_up_day_ratio_20d": sum(value > 0 for value in returns) / len(returns),
        "path_trend_efficiency_20d": trend_efficiency,
    }


def _iso_day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
