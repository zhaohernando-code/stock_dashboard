from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock


CAPACITY_OPPORTUNITY_SET_DISCOVERY_VERSION = "capacity_opportunity_set_discovery.v1"
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"
DEFAULT_BENCHMARK_SYMBOLS = {"000300.SH", "000905.SH", "000852.SH"}


def build_capacity_opportunity_set_discovery(
    session: Session,
    *,
    top_candidate_summary_artifact: str | Path,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    portfolio_notional_cny: float = 1_000_000.0,
    slot_capital_weight: float = 0.91,
    max_adv_participation_rate: float = 0.05,
    top_n: int = 20,
) -> dict[str, Any]:
    """Discover whether full-market liquid winners exist outside the retained TopN boundary.

    This is a future-return triage over a few known capacity-blocker dates. It intentionally does not
    claim model replay evidence: the result is used to decide whether opportunity-set/scoring work is
    worth pursuing before paying the cost of a full matrix rebuild.
    """

    summary_path = Path(top_candidate_summary_artifact)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    date_summaries = list(summary.get("summary") or [])
    full_fill_avg_amount_20d = (
        portfolio_notional_cny * slot_capital_weight / max(max_adv_participation_rate, 0.000001)
    )

    blocking_gate_ids: list[str] = []
    dates: list[dict[str, Any]] = []
    for item in date_summaries:
        try:
            as_of_date = date.fromisoformat(str(item["as_of_date"]))
        except (KeyError, ValueError):
            blocking_gate_ids.append("capacity_opportunity_set_discovery:invalid_summary_date")
            continue
        source_symbol = str(item.get("source_symbol") or "")
        histories = _market_histories_for_window(session, as_of_date)
        metrics = _metrics_by_symbol(histories, as_of_date=as_of_date, benchmark_symbol=benchmark_symbol)
        benchmark = metrics.get(benchmark_symbol)
        source = metrics.get(source_symbol)
        if not benchmark:
            blocking_gate_ids.append(f"capacity_opportunity_set_discovery:{as_of_date}:missing_benchmark")
            benchmark_return_20d = None
        else:
            benchmark_return_20d = benchmark.get("future_return_20d")
        if not source:
            blocking_gate_ids.append(f"capacity_opportunity_set_discovery:{as_of_date}:missing_source")

        source_db_excess = (
            _safe_float(source.get("future_return_20d")) - _safe_float(benchmark_return_20d)
            if source and benchmark_return_20d is not None
            else None
        )
        source_artifact_net = _safe_float(item.get("source_net_excess_return"))
        candidates = [
            row
            for symbol, row in metrics.items()
            if symbol not in DEFAULT_BENCHMARK_SYMBOLS
            and symbol != source_symbol
            and _safe_float(row.get("avg_amount_20d"), 0.0) >= full_fill_avg_amount_20d
            and row.get("future_return_20d") is not None
        ]
        for row in candidates:
            row["future_excess_return_20d"] = (
                _safe_float(row.get("future_return_20d")) - _safe_float(benchmark_return_20d)
                if benchmark_return_20d is not None
                else None
            )
        _attach_percentiles(
            candidates,
            fields=[
                "avg_amount_20d",
                "return_5d",
                "return_20d",
                "amount_10d_vs_20d",
                "volatility_20d",
                "turnover_rate",
                "total_mv",
            ],
        )
        candidates.sort(key=lambda row: _safe_float(row.get("future_excess_return_20d"), -999.0), reverse=True)
        artifact_floor = source_artifact_net if source_artifact_net is not None else None
        db_source_floor = source_db_excess if source_db_excess is not None else None
        artifact_nondegrading = [
            row
            for row in candidates
            if artifact_floor is not None and _safe_float(row.get("future_excess_return_20d"), -999.0) >= artifact_floor
        ]
        db_source_nondegrading = [
            row
            for row in candidates
            if db_source_floor is not None and _safe_float(row.get("future_excess_return_20d"), -999.0) >= db_source_floor
        ]
        top_rows = candidates[: max(top_n, 1)]
        retained_symbols = _retained_summary_symbols(item)
        for row in top_rows:
            row["present_in_retained_top10_liquid_summary"] = row["symbol"] in retained_symbols

        dates.append(
            {
                "as_of_date": as_of_date.isoformat(),
                "source_symbol": source_symbol,
                "benchmark_symbol": benchmark_symbol,
                "benchmark_future_return_20d": benchmark_return_20d,
                "source_artifact_net_excess_return": source_artifact_net,
                "source_db_future_excess_return_20d": source_db_excess,
                "source_avg_amount_20d": _safe_float(item.get("source_avg_amount_20d")),
                "full_fill_avg_amount_20d_required": full_fill_avg_amount_20d,
                "liquid_universe_candidate_count": len(candidates),
                "non_degrading_liquid_count_vs_artifact_net": len(artifact_nondegrading),
                "non_degrading_liquid_count_vs_db_source_excess": len(db_source_nondegrading),
                "best_liquid_future_excess_return_20d": top_rows[0].get("future_excess_return_20d")
                if top_rows
                else None,
                "best_liquid_symbol": top_rows[0].get("symbol") if top_rows else None,
                "top_liquid_by_future_excess": [_compact_candidate_row(row) for row in top_rows],
            }
        )

    if not date_summaries:
        blocking_gate_ids.append("capacity_opportunity_set_discovery:no_summary_dates")
    dates_with_artifact_nondegrading = sum(
        1 for row in dates if int(row["non_degrading_liquid_count_vs_artifact_net"]) > 0
    )
    dates_with_db_source_nondegrading = sum(
        1 for row in dates if int(row["non_degrading_liquid_count_vs_db_source_excess"]) > 0
    )
    return {
        "artifact_type": "capacity_opportunity_set_discovery",
        "schema_version": CAPACITY_OPPORTUNITY_SET_DISCOVERY_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": sorted(set(blocking_gate_ids)),
        "claim_ceiling": "future_return_opportunity_set_triage_only_no_model_replay_no_promotion",
        "source_summary_artifact": str(summary_path),
        "source_summary_type": summary.get("artifact_type"),
        "portfolio_notional_cny": portfolio_notional_cny,
        "slot_capital_weight": slot_capital_weight,
        "max_adv_participation_rate": max_adv_participation_rate,
        "full_fill_avg_amount_20d_required": full_fill_avg_amount_20d,
        "date_count": len(dates),
        "dates_with_non_degrading_liquid_candidates_vs_artifact_net": dates_with_artifact_nondegrading,
        "dates_with_non_degrading_liquid_candidates_vs_db_source_excess": dates_with_db_source_nondegrading,
        "interpretation": _interpretation(dates, len(date_summaries)),
        "dates": dates,
    }


def write_capacity_opportunity_set_discovery(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _market_histories_for_window(session: Session, as_of_date: date) -> dict[str, list[dict[str, Any]]]:
    start = as_of_date - timedelta(days=80)
    end = as_of_date + timedelta(days=60)
    rows = session.execute(
        select(
            Stock.symbol,
            Stock.name,
            Stock.profile_payload,
            MarketBar.observed_at,
            MarketBar.open_price,
            MarketBar.high_price,
            MarketBar.low_price,
            MarketBar.close_price,
            MarketBar.amount,
            MarketBar.turnover_rate,
            MarketBar.total_mv,
            MarketBar.circ_mv,
            MarketBar.pe_ttm,
            MarketBar.pb,
        )
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(
            MarketBar.timeframe == "1d",
            MarketBar.observed_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            MarketBar.observed_at <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
        )
        .order_by(Stock.symbol, MarketBar.observed_at)
    ).mappings()
    histories: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        histories.setdefault(str(row["symbol"]), []).append(dict(row))
    return histories


def _metrics_by_symbol(
    histories: dict[str, list[dict[str, Any]]],
    *,
    as_of_date: date,
    benchmark_symbol: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for symbol, rows in histories.items():
        metric = _symbol_metrics(symbol, rows, as_of_date=as_of_date)
        if metric is not None:
            metric["role"] = "benchmark" if symbol == benchmark_symbol else "stock"
            result[symbol] = metric
    return result


def _symbol_metrics(symbol: str, rows: list[dict[str, Any]], *, as_of_date: date) -> dict[str, Any] | None:
    idx = next((index for index, row in enumerate(rows) if _row_date(row) == as_of_date), None)
    if idx is None or idx < 20 or idx + 20 >= len(rows):
        return None
    current = rows[idx]
    close = _safe_float(current.get("close_price"))
    open_price = _safe_float(current.get("open_price"))
    high_price = _safe_float(current.get("high_price"))
    low_price = _safe_float(current.get("low_price"))
    previous_close = _safe_float(rows[idx - 1].get("close_price"))
    future_close = _safe_float(rows[idx + 20].get("close_price"))
    if close is None or close <= 0 or future_close is None or future_close <= 0:
        return None
    trailing_20 = rows[idx - 19 : idx + 1]
    trailing_10 = rows[idx - 9 : idx + 1]
    closes_21 = [_safe_float(row.get("close_price")) for row in rows[idx - 20 : idx + 1]]
    closes_21 = [value for value in closes_21 if value is not None and value > 0]
    prior_closes_20 = closes_21[:-1]
    avg_amount_20d = mean(_safe_float(row.get("amount"), 0.0) for row in trailing_20)
    avg_amount_10d = mean(_safe_float(row.get("amount"), 0.0) for row in trailing_10)
    returns = [closes_21[index] / closes_21[index - 1] - 1.0 for index in range(1, len(closes_21))]
    rolling_high_20 = max(prior_closes_20) if prior_closes_20 else close
    rolling_low_20 = min(prior_closes_20) if prior_closes_20 else close
    high_low_range = max(_safe_float(high_price, close) - _safe_float(low_price, close), 0.0)
    limitup_like_5d_count = _limitup_like_count(rows, idx, lookback=5)
    return {
        "symbol": symbol,
        "name": current.get("name"),
        "industry_name": (current.get("profile_payload") or {}).get("industry"),
        "industry_code": (current.get("profile_payload") or {}).get("industry_code"),
        "avg_amount_20d": avg_amount_20d,
        "amount_10d_vs_20d": avg_amount_10d / max(avg_amount_20d, 0.000001) - 1.0,
        "return_5d": close / _safe_float(rows[idx - 5].get("close_price")) - 1.0,
        "return_20d": close / _safe_float(rows[idx - 20].get("close_price")) - 1.0,
        "volatility_20d": _stddev(returns),
        "max_drawdown_20d": _max_drawdown(closes_21),
        "turnover_rate": _safe_float(current.get("turnover_rate")),
        "total_mv": _safe_float(current.get("total_mv")),
        "circ_mv": _safe_float(current.get("circ_mv")),
        "pe_ttm": _safe_float(current.get("pe_ttm")),
        "pb": _safe_float(current.get("pb")),
        "daily_return_1d": close / previous_close - 1.0 if previous_close and previous_close > 0 else 0.0,
        "open_gap_1d": open_price / previous_close - 1.0
        if open_price and open_price > 0 and previous_close and previous_close > 0
        else 0.0,
        "intraday_return_1d": close / open_price - 1.0 if open_price and open_price > 0 else 0.0,
        "close_range_position": (close - _safe_float(low_price, close)) / high_low_range if high_low_range > 0 else 0.5,
        "upper_shadow_ratio": (_safe_float(high_price, close) - close) / close if close > 0 else 0.0,
        "distance_to_20d_high": close / rolling_high_20 - 1.0 if rolling_high_20 > 0 else 0.0,
        "distance_to_20d_low": close / rolling_low_20 - 1.0 if rolling_low_20 > 0 else 0.0,
        "limitup_like_5d_count": limitup_like_5d_count,
        "future_return_20d": future_close / close - 1.0,
    }


def _attach_percentiles(rows: list[dict[str, Any]], *, fields: list[str]) -> None:
    for field in fields:
        values = sorted(_safe_float(row.get(field)) for row in rows if _safe_float(row.get(field)) is not None)
        if not values:
            continue
        for row in rows:
            value = _safe_float(row.get(field))
            if value is None:
                row[f"{field}_percentile"] = None
                continue
            row[f"{field}_percentile"] = sum(1 for item in values if item <= value) / len(values)


def _compact_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "symbol",
        "name",
        "future_excess_return_20d",
        "future_return_20d",
        "avg_amount_20d",
        "avg_amount_20d_percentile",
        "return_5d",
        "return_5d_percentile",
        "return_20d",
        "return_20d_percentile",
        "amount_10d_vs_20d",
        "amount_10d_vs_20d_percentile",
        "volatility_20d",
        "volatility_20d_percentile",
        "turnover_rate",
        "turnover_rate_percentile",
        "total_mv",
        "total_mv_percentile",
        "circ_mv",
        "max_drawdown_20d",
        "daily_return_1d",
        "open_gap_1d",
        "intraday_return_1d",
        "close_range_position",
        "upper_shadow_ratio",
        "distance_to_20d_high",
        "distance_to_20d_low",
        "limitup_like_5d_count",
        "present_in_retained_top10_liquid_summary",
    ]
    return {field: row.get(field) for field in fields}


def _limitup_like_count(rows: list[dict[str, Any]], idx: int, *, lookback: int) -> int:
    start = max(1, idx - lookback + 1)
    count = 0
    for index in range(start, idx + 1):
        close = _safe_float(rows[index].get("close_price"))
        previous_close = _safe_float(rows[index - 1].get("close_price"))
        if close and previous_close and previous_close > 0 and close / previous_close - 1.0 >= 0.095:
            count += 1
    return count


def _retained_summary_symbols(item: dict[str, Any]) -> set[str]:
    symbols: set[str] = set()
    best = item.get("best_liquid_candidate") or {}
    if best.get("symbol"):
        symbols.add(str(best["symbol"]))
    for row in item.get("top10_liquid_by_future_return") or []:
        if row.get("symbol"):
            symbols.add(str(row["symbol"]))
    return symbols


def _interpretation(dates: list[dict[str, Any]], source_date_count: int) -> str:
    if not dates:
        return "No dates were available for opportunity-set discovery."
    artifact_hits = sum(1 for row in dates if row["non_degrading_liquid_count_vs_artifact_net"] > 0)
    if artifact_hits == 0:
        return (
            "No full-market liquid candidate matched the retained source net-excess floor on the blocker dates; "
            "capacity likely needs a lower-capital contract or new return source."
        )
    if artifact_hits < source_date_count:
        return (
            "Full-market liquid future winners exist on some blocker dates but not all. This supports a richer "
            "opportunity-set/scoring investigation, not another same-score TopN expansion or promotion claim."
        )
    return (
        "Full-market liquid future winners exist on all blocker dates. The next research step should diagnose "
        "which ex-ante features can rank them before formal replay."
    )


def _row_date(row: dict[str, Any]) -> date | None:
    value = row.get("observed_at")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def _stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst
