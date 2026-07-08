from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ashare_evidence.models import (
    FeatureSnapshot,
    MarketBar,
    ModelResult,
    NewsEntityLink,
    NewsItem,
    Recommendation,
    SectorMembership,
    Stock,
)


PIT_SOURCE_READINESS_AUDIT_VERSION = "pit_source_readiness_audit.v1"


def audit_pit_source_readiness(
    session: Session,
    *,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float = 0.90,
) -> dict[str, Any]:
    """Audit whether runtime DB has additional PIT-safe historical sources for model research.

    This is intentionally source-readiness only. It does not build feature matrices, train models, replay
    strategies, call providers, or promote any strategy.
    """

    sources = {
        "market_bars_ohlcv_valuation": _market_bar_source(session, observed_start, observed_end, min_coverage_ratio),
        "stock_profile_static_industry": _stock_profile_source(session),
        "sector_memberships": _sector_membership_source(session, observed_start, observed_end, min_coverage_ratio),
        "news_items_entity_links": _news_source(session, observed_start, observed_end, min_coverage_ratio),
        "feature_snapshots": _feature_snapshot_source(session, observed_start, observed_end, min_coverage_ratio),
        "model_results": _model_result_source(session, observed_start, observed_end, min_coverage_ratio),
        "recommendations": _recommendation_source(session, observed_start, observed_end, min_coverage_ratio),
    }
    new_ready_sources = [
        name
        for name, summary in sources.items()
        if summary["readiness_status"] == "ready_new_pit_source"
    ]
    blocking_gate_ids = []
    if not new_ready_sources:
        blocking_gate_ids.append("pit_source_readiness:no_additional_historical_pit_source_ready")
    return {
        "artifact_type": "pit_source_readiness_audit",
        "schema_version": PIT_SOURCE_READINESS_AUDIT_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "claim_ceiling": "source_readiness_only_no_data_fetch_no_feature_matrix_no_model_replay_no_promotion",
        "observed_window": {
            "start": observed_start.isoformat(),
            "end": observed_end.isoformat(),
        },
        "min_coverage_ratio": min_coverage_ratio,
        "ready_new_pit_sources": new_ready_sources,
        "sources": sources,
        "interpretation": _interpretation(new_ready_sources),
    }


def write_pit_source_readiness_audit(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _market_bar_source(
    session: Session,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
) -> dict[str, Any]:
    filters = [
        MarketBar.timeframe == "1d",
        MarketBar.observed_at >= _start_of_day(observed_start),
        MarketBar.observed_at <= _end_of_day(observed_end),
    ]
    row = session.execute(
        select(
            func.count(MarketBar.id),
            func.min(MarketBar.observed_at),
            func.max(MarketBar.observed_at),
            func.sum(case((MarketBar.turnover_rate.is_not(None), 1), else_=0)),
            func.sum(case((MarketBar.total_mv.is_not(None), 1), else_=0)),
            func.sum(case((MarketBar.circ_mv.is_not(None), 1), else_=0)),
            func.sum(case((MarketBar.pe_ttm.is_not(None), 1), else_=0)),
            func.sum(case((MarketBar.pb.is_not(None), 1), else_=0)),
        ).where(*filters)
    ).one()
    total_rows = int(row[0] or 0)
    fields = {
        "turnover_rate": _ratio(total_rows, row[3]),
        "total_mv": _ratio(total_rows, row[4]),
        "circ_mv": _ratio(total_rows, row[5]),
        "pe_ttm": _ratio(total_rows, row[6]),
        "pb": _ratio(total_rows, row[7]),
    }
    status, blockers = _source_status(
        row_count=total_rows,
        min_observed_at=row[1],
        max_observed_at=row[2],
        observed_start=observed_start,
        observed_end=observed_end,
        min_coverage_ratio=min_coverage_ratio,
        known_existing=True,
    )
    return {
        "readiness_status": status,
        "blocking_gate_ids": blockers,
        "pit_role": "existing_feature_source",
        "row_count": total_rows,
        "min_observed_at": _iso(row[1]),
        "max_observed_at": _iso(row[2]),
        "field_non_null_ratios": fields,
        "feature_implication": "Already used by v3 OHLCV/liquidity/valuation/capacity/price-action diagnostics.",
    }


def _stock_profile_source(session: Session) -> dict[str, Any]:
    rows = list(session.execute(select(Stock.status, Stock.profile_payload)).all())
    total = len(rows)
    active = sum(1 for status, _profile in rows if status == "active")
    industry_count = sum(1 for _status, profile in rows if (profile or {}).get("industry"))
    market_board_count = sum(1 for _status, profile in rows if (profile or {}).get("market_board") or (profile or {}).get("market"))
    return {
        "readiness_status": "existing_static_source_ready",
        "blocking_gate_ids": [],
        "pit_role": "existing_static_profile_source",
        "row_count": total,
        "active_stock_count": active,
        "field_non_null_ratios": {
            "industry": _ratio(total, industry_count),
            "market_or_market_board": _ratio(total, market_board_count),
        },
        "feature_implication": "Already usable as static industry/board metadata, but target-fitted liquid-winner audit still failed with industry-relative fields.",
    }


def _sector_membership_source(
    session: Session,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(SectorMembership.id),
            func.min(SectorMembership.effective_from),
            func.max(SectorMembership.effective_from),
            func.count(func.distinct(SectorMembership.stock_id)),
        )
    ).one()
    stock_count = int(session.scalar(select(func.count(Stock.id))) or 0)
    linked_stock_ratio = _ratio(stock_count, row[3])
    blockers = []
    sector_stock_blocker = _stock_coverage_blocker(
        linked_stock_ratio,
        min_coverage_ratio=min_coverage_ratio,
        blocker_id="pit_source_readiness:sector_membership_stock_coverage_below_gate",
    )
    if sector_stock_blocker:
        blockers.append(sector_stock_blocker)
    status, window_blockers = _source_status(
        row_count=int(row[0] or 0),
        min_observed_at=row[1],
        max_observed_at=row[2],
        observed_start=observed_start,
        observed_end=observed_end,
        min_coverage_ratio=min_coverage_ratio,
        known_existing=False,
        missing_window_allowed=True,
    )
    blockers.extend(window_blockers)
    if blockers:
        status = "blocked_sparse_or_incomplete"
    return {
        "readiness_status": status,
        "blocking_gate_ids": sorted(set(blockers)),
        "pit_role": "candidate_cross_sectional_taxonomy_source",
        "row_count": int(row[0] or 0),
        "linked_stock_count": int(row[3] or 0),
        "linked_stock_ratio": linked_stock_ratio,
        "min_effective_from": _iso(row[1]),
        "max_effective_from": _iso(row[2]),
        "feature_implication": "Would support richer sector hierarchy only if historical stock coverage is materially expanded.",
    }


def _news_source(
    session: Session,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(NewsItem.id),
            func.min(NewsItem.published_at),
            func.max(NewsItem.published_at),
        )
    ).one()
    link_count = int(session.scalar(select(func.count(NewsEntityLink.id))) or 0)
    status, blockers = _source_status(
        row_count=int(row[0] or 0),
        min_observed_at=row[1],
        max_observed_at=row[2],
        observed_start=observed_start,
        observed_end=observed_end,
        min_coverage_ratio=min_coverage_ratio,
        known_existing=False,
    )
    if int(row[0] or 0) > 0 and row[1] and row[1].date() > observed_start:
        blockers.append("pit_source_readiness:news_history_starts_after_research_window")
        status = "blocked_history_too_short"
    return {
        "readiness_status": status,
        "blocking_gate_ids": sorted(set(blockers)),
        "pit_role": "candidate_event_sentiment_source",
        "row_count": int(row[0] or 0),
        "entity_link_count": link_count,
        "min_published_at": _iso(row[1]),
        "max_published_at": _iso(row[2]),
        "feature_implication": "Potential future forward-tracking/event feature source, but not enough history for 2023-2026 full713 replay.",
    }


def _feature_snapshot_source(
    session: Session,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(FeatureSnapshot.id),
            func.min(FeatureSnapshot.as_of),
            func.max(FeatureSnapshot.as_of),
            func.count(func.distinct(FeatureSnapshot.feature_set_name)),
            func.count(func.distinct(FeatureSnapshot.stock_id)),
        )
    ).one()
    stock_count = int(session.scalar(select(func.count(Stock.id))) or 0)
    linked_stock_ratio = _ratio(stock_count, row[4])
    status, blockers = _source_status(
        row_count=int(row[0] or 0),
        min_observed_at=row[1],
        max_observed_at=row[2],
        observed_start=observed_start,
        observed_end=observed_end,
        min_coverage_ratio=min_coverage_ratio,
        known_existing=False,
    )
    feature_stock_blocker = _stock_coverage_blocker(
        linked_stock_ratio,
        min_coverage_ratio=min_coverage_ratio,
        blocker_id="pit_source_readiness:feature_snapshot_stock_coverage_below_gate",
    )
    if feature_stock_blocker:
        blockers.append(feature_stock_blocker)
        status = "blocked_sparse_or_incomplete"
    return {
        "readiness_status": status,
        "blocking_gate_ids": sorted(set(blockers)),
        "pit_role": "candidate_precomputed_feature_source",
        "row_count": int(row[0] or 0),
        "feature_set_count": int(row[3] or 0),
        "linked_stock_count": int(row[4] or 0),
        "linked_stock_ratio": linked_stock_ratio,
        "min_as_of": _iso(row[1]),
        "max_as_of": _iso(row[2]),
        "feature_implication": "Could be useful only if populated with PIT-safe historical features across the full research window.",
    }


def _model_result_source(
    session: Session,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(ModelResult.id),
            func.min(ModelResult.as_of_data_time),
            func.max(ModelResult.as_of_data_time),
        )
    ).one()
    status, blockers = _source_status(
        row_count=int(row[0] or 0),
        min_observed_at=row[1],
        max_observed_at=row[2],
        observed_start=observed_start,
        observed_end=observed_end,
        min_coverage_ratio=min_coverage_ratio,
        known_existing=False,
    )
    blockers.append("pit_source_readiness:model_results_are_model_outputs_not_raw_independent_source")
    return {
        "readiness_status": "blocked_output_leakage_risk" if int(row[0] or 0) else status,
        "blocking_gate_ids": sorted(set(blockers)),
        "pit_role": "model_output_not_independent_raw_source",
        "row_count": int(row[0] or 0),
        "min_as_of_data_time": _iso(row[1]),
        "max_as_of_data_time": _iso(row[2]),
        "feature_implication": "Do not use as a new independent alpha source for model exploration without a separate leakage-proof contract.",
    }


def _recommendation_source(
    session: Session,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(Recommendation.id),
            func.min(Recommendation.as_of_data_time),
            func.max(Recommendation.as_of_data_time),
        )
    ).one()
    status, blockers = _source_status(
        row_count=int(row[0] or 0),
        min_observed_at=row[1],
        max_observed_at=row[2],
        observed_start=observed_start,
        observed_end=observed_end,
        min_coverage_ratio=min_coverage_ratio,
        known_existing=False,
    )
    blockers.append("pit_source_readiness:recommendations_are_prior_strategy_outputs")
    return {
        "readiness_status": "blocked_output_leakage_risk" if int(row[0] or 0) else status,
        "blocking_gate_ids": sorted(set(blockers)),
        "pit_role": "prior_recommendation_output_not_raw_source",
        "row_count": int(row[0] or 0),
        "min_as_of_data_time": _iso(row[1]),
        "max_as_of_data_time": _iso(row[2]),
        "feature_implication": "Do not use as a new independent alpha source because it would entangle the new model with previous recommendation policy outputs.",
    }


def _source_status(
    *,
    row_count: int,
    min_observed_at: datetime | None,
    max_observed_at: datetime | None,
    observed_start: date,
    observed_end: date,
    min_coverage_ratio: float,
    known_existing: bool,
    missing_window_allowed: bool = False,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if row_count <= 0:
        blockers.append("pit_source_readiness:no_rows")
        return "blocked_empty", blockers
    if not min_observed_at or not max_observed_at:
        blockers.append("pit_source_readiness:missing_time_bounds")
        return "blocked_missing_time_bounds", blockers
    if min_observed_at.date() > observed_start and not missing_window_allowed:
        blockers.append("pit_source_readiness:min_date_after_research_start")
    if max_observed_at.date() < observed_end:
        blockers.append("pit_source_readiness:max_date_before_research_end")
    if blockers:
        return "blocked_history_incomplete", blockers
    return ("existing_source_ready" if known_existing else "ready_new_pit_source"), blockers


def _interpretation(new_ready_sources: list[str]) -> str:
    if new_ready_sources:
        return (
            "At least one additional historical PIT source is already ready in the runtime DB. "
            "The next step can design a bounded feature family/preflight around those source(s)."
        )
    return (
        "No additional historical PIT source beyond already-used market bars and static stock profiles is ready "
        "inside the runtime DB for the full713 window. The next meaningful optimization likely requires external "
        "PIT data ingestion or a materially different label/objective, not another recipe over existing fields."
    )


def _ratio(denominator: int, numerator: Any) -> float:
    if denominator <= 0:
        return 0.0
    return int(numerator or 0) / denominator


def _stock_coverage_blocker(
    linked_stock_ratio: float,
    *,
    min_coverage_ratio: float,
    blocker_id: str,
) -> str | None:
    return blocker_id if linked_stock_ratio < min_coverage_ratio else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max)
