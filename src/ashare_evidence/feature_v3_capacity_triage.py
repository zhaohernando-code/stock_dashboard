from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock


FEATURE_V3_CAPACITY_TRIAGE_VERSION = "feature_v3_capacity_triage.v1"


def build_feature_v3_capacity_triage(
    session: Session,
    *,
    top_candidate_summary_artifact: str | Path,
) -> dict[str, Any]:
    """Compare remaining capacity blockers with retained liquid candidates using v3 source fields."""

    summary_path = Path(top_candidate_summary_artifact)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    date_summaries = summary.get("summary") or []

    blocking_gate_ids: list[str] = []
    triage_dates: list[dict[str, Any]] = []
    for item in date_summaries:
        as_of_date = date.fromisoformat(str(item["as_of_date"]))
        source_symbol = str(item["source_symbol"])
        day_rows = _market_bar_rows_for_day(session, as_of_date)
        by_symbol = {str(row["symbol"]): row for row in day_rows}

        candidate_symbols = _candidate_symbols(item)
        selected_symbols = [source_symbol, *[symbol for symbol in candidate_symbols if symbol != source_symbol]]
        selected_rows = [
            _selected_symbol_row(item, symbol=symbol, market_row=by_symbol.get(symbol), all_day_rows=day_rows)
            for symbol in selected_symbols
        ]
        missing_symbols = [row["symbol"] for row in selected_rows if row["market_bar_found"] is False]
        if missing_symbols:
            blocking_gate_ids.append("feature_v3_capacity_triage:missing_selected_market_bar")

        liquid_rows = [row for row in selected_rows[1:] if row["market_bar_found"]]
        source_row = selected_rows[0]
        best_liquid = item.get("best_liquid_candidate") or {}
        source_net = _safe_float(item.get("source_net_excess_return"))
        best_liquid_net = _safe_float(best_liquid.get("net_excess_return"))
        triage_dates.append(
            {
                "as_of_date": as_of_date.isoformat(),
                "source_symbol": source_symbol,
                "source_net_excess_return": source_net,
                "best_liquid_net_excess_return": best_liquid_net,
                "future_return_gap_to_best_liquid": (
                    source_net - best_liquid_net if source_net is not None and best_liquid_net is not None else None
                ),
                "source_total_mv_percentile": source_row.get("total_mv_percentile"),
                "source_circ_mv_percentile": source_row.get("circ_mv_percentile"),
                "source_pb_percentile": source_row.get("pb_percentile"),
                "median_top_liquid_total_mv_percentile": _median_present(
                    row.get("total_mv_percentile") for row in liquid_rows
                ),
                "median_top_liquid_circ_mv_percentile": _median_present(
                    row.get("circ_mv_percentile") for row in liquid_rows
                ),
                "selected_symbols": selected_rows,
                "missing_symbols": missing_symbols,
            }
        )

    if not triage_dates:
        blocking_gate_ids.append("feature_v3_capacity_triage:no_summary_dates")

    source_total_mv_percentiles = _present(row.get("source_total_mv_percentile") for row in triage_dates)
    liquid_total_mv_percentiles = _present(row.get("median_top_liquid_total_mv_percentile") for row in triage_dates)
    gaps = _present(row.get("future_return_gap_to_best_liquid") for row in triage_dates)
    return {
        "artifact_type": "feature_v3_capacity_triage",
        "schema_version": FEATURE_V3_CAPACITY_TRIAGE_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": sorted(set(blocking_gate_ids)),
        "claim_ceiling": "triage_only_no_pit_matrix_rebuild_no_model_replay",
        "source_summary_artifact": str(summary_path),
        "source_summary_type": summary.get("artifact_type"),
        "date_count": len(triage_dates),
        "source_total_mv_percentile_range": _value_range(source_total_mv_percentiles),
        "median_liquid_total_mv_percentile_range": _value_range(liquid_total_mv_percentiles),
        "future_return_gap_to_best_liquid_range": _value_range(gaps),
        "triage_signal": (
            "v3 market-cap/capacity fields can express the low-ADV blocker, "
            "but liquid substitution still needs formal replay because the retained best-liquid labels lag materially"
        ),
        "dates": triage_dates,
    }


def _market_bar_rows_for_day(session: Session, as_of_date: date) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            Stock.symbol,
            Stock.name,
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
            MarketBar.observed_at >= datetime.combine(as_of_date, time.min, tzinfo=UTC),
            MarketBar.observed_at <= datetime.combine(as_of_date, time.max, tzinfo=UTC),
        )
    ).mappings()
    return [dict(row) for row in rows]


def _candidate_symbols(item: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    best = item.get("best_liquid_candidate") or {}
    if best.get("symbol"):
        symbols.append(str(best["symbol"]))
    for candidate in item.get("top10_liquid_by_future_return") or []:
        symbol = candidate.get("symbol")
        if symbol and str(symbol) not in symbols:
            symbols.append(str(symbol))
    return symbols


def _selected_symbol_row(
    item: dict[str, Any],
    *,
    symbol: str,
    market_row: dict[str, Any] | None,
    all_day_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    is_source = symbol == str(item["source_symbol"])
    candidate = None if is_source else _candidate_by_symbol(item, symbol)
    row = market_row or {}
    return {
        "symbol": symbol,
        "name": row.get("name"),
        "role": "source_underfilled_winner" if is_source else "top_liquid_future_return_candidate",
        "market_bar_found": market_row is not None,
        "net_excess_return": _safe_float(item.get("source_net_excess_return"))
        if is_source
        else _safe_float((candidate or {}).get("net_excess_return")),
        "top_candidate_rank": None if is_source else (candidate or {}).get("rank"),
        "summary_avg_amount_20d": _safe_float(item.get("source_avg_amount_20d"))
        if is_source
        else _safe_float((candidate or {}).get("avg_amount_20d")),
        "day_amount": _safe_float(row.get("amount")),
        "turnover_rate": _safe_float(row.get("turnover_rate")),
        "total_mv": _safe_float(row.get("total_mv")),
        "circ_mv": _safe_float(row.get("circ_mv")),
        "pe_ttm": _safe_float(row.get("pe_ttm")),
        "pb": _safe_float(row.get("pb")),
        "total_mv_percentile": _percentile(all_day_rows, "total_mv", row.get("total_mv")),
        "circ_mv_percentile": _percentile(all_day_rows, "circ_mv", row.get("circ_mv")),
        "pe_ttm_percentile": _percentile(all_day_rows, "pe_ttm", row.get("pe_ttm")),
        "pb_percentile": _percentile(all_day_rows, "pb", row.get("pb")),
    }


def _candidate_by_symbol(item: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    for candidate in item.get("top10_liquid_by_future_return") or []:
        if str(candidate.get("symbol")) == symbol:
            return candidate
    best = item.get("best_liquid_candidate") or {}
    if str(best.get("symbol")) == symbol:
        return best
    return None


def _percentile(rows: list[dict[str, Any]], field: str, value: Any) -> float | None:
    target = _safe_float(value)
    if target is None or target <= 0:
        return None
    values = sorted(row_value for row in rows if (row_value := _safe_float(row.get(field))) is not None and row_value > 0)
    if not values:
        return None
    less_or_equal = sum(1 for row_value in values if row_value <= target)
    return less_or_equal / len(values)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _present(values: Any) -> list[float]:
    return [float(value) for value in values if value is not None]


def _median_present(values: Any) -> float | None:
    present = _present(values)
    return median(present) if present else None


def _value_range(values: list[float]) -> list[float] | None:
    return [min(values), max(values)] if values else None
