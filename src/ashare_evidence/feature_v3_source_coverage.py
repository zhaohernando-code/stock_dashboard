from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar


FEATURE_V3_SOURCE_COVERAGE_AUDIT_VERSION = "feature_v3_source_coverage_audit.v1"


def audit_feature_v3_source_coverage(
    session: Session,
    *,
    observed_start: date | None = None,
    observed_end: date | None = None,
    min_market_cap_coverage: float = 0.95,
    min_valuation_coverage: float = 0.50,
) -> dict[str, Any]:
    """Audit source coverage for feature-matrix v3 without building the large matrix."""

    filters = [MarketBar.timeframe == "1d"]
    if observed_start is not None:
        filters.append(MarketBar.observed_at >= _start_of_day(observed_start))
    if observed_end is not None:
        filters.append(MarketBar.observed_at <= _end_of_day(observed_end))

    row = session.execute(
        select(
            func.count(MarketBar.id),
            func.min(MarketBar.observed_at),
            func.max(MarketBar.observed_at),
            func.count(MarketBar.total_mv),
            func.count(MarketBar.circ_mv),
            func.count(MarketBar.pe_ttm),
            func.count(MarketBar.pb),
            func.sum(case((MarketBar.total_mv > 0, 1), else_=0)),
            func.sum(case((MarketBar.circ_mv > 0, 1), else_=0)),
            func.sum(case((MarketBar.pe_ttm > 0, 1), else_=0)),
            func.sum(case((MarketBar.pb > 0, 1), else_=0)),
        ).where(*filters)
    ).one()
    (
        total_rows,
        min_observed_at,
        max_observed_at,
        total_mv_non_null,
        circ_mv_non_null,
        pe_ttm_non_null,
        pb_non_null,
        total_mv_positive,
        circ_mv_positive,
        pe_ttm_positive,
        pb_positive,
    ) = row
    total_rows = int(total_rows or 0)

    fields = {
        "total_mv": _field_summary(total_rows, total_mv_non_null, total_mv_positive),
        "circ_mv": _field_summary(total_rows, circ_mv_non_null, circ_mv_positive),
        "pe_ttm": _field_summary(total_rows, pe_ttm_non_null, pe_ttm_positive),
        "pb": _field_summary(total_rows, pb_non_null, pb_positive),
    }

    blocking_gate_ids: list[str] = []
    if total_rows <= 0:
        blocking_gate_ids.append("feature_v3_source_coverage:no_market_bar_rows")
    for field_name in ("total_mv", "circ_mv"):
        if fields[field_name]["positive_ratio"] < min_market_cap_coverage:
            blocking_gate_ids.append(f"feature_v3_source_coverage:{field_name}_positive_ratio_below_gate")
    for field_name in ("pe_ttm", "pb"):
        if fields[field_name]["positive_ratio"] < min_valuation_coverage:
            blocking_gate_ids.append(f"feature_v3_source_coverage:{field_name}_positive_ratio_below_gate")

    blocking_gate_ids = sorted(set(blocking_gate_ids))
    return {
        "artifact_type": "feature_v3_source_coverage_audit",
        "schema_version": FEATURE_V3_SOURCE_COVERAGE_AUDIT_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "claim_ceiling": "source_coverage_audit_only_no_pit_matrix_rebuild_no_model_replay",
        "observed_window": {
            "start": observed_start.isoformat() if observed_start else None,
            "end": observed_end.isoformat() if observed_end else None,
            "min_observed_at": min_observed_at.isoformat() if min_observed_at else None,
            "max_observed_at": max_observed_at.isoformat() if max_observed_at else None,
        },
        "row_count": total_rows,
        "gates": {
            "min_market_cap_positive_ratio": min_market_cap_coverage,
            "min_valuation_positive_ratio": min_valuation_coverage,
        },
        "fields": fields,
    }


def _field_summary(total_rows: int, non_null_count: Any, positive_count: Any) -> dict[str, Any]:
    non_null = int(non_null_count or 0)
    positive = int(positive_count or 0)
    denominator = max(total_rows, 1)
    return {
        "non_null_count": non_null,
        "positive_count": positive,
        "non_null_ratio": non_null / denominator,
        "positive_ratio": positive / denominator,
    }


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)
