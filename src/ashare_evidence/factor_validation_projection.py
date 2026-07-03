from __future__ import annotations

from copy import deepcopy
from threading import RLock
from time import monotonic
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.factor_observation import (
    FACTOR_IC_STUDY_SCHEMA_VERSION,
    VALIDATION_PROTOCOL_VERSION,
    build_factor_observations,
)
from ashare_evidence.models import MarketBar, NewsEntityLink, NewsItem, Recommendation, Stock

_CACHE_TTL_SECONDS = 300.0
_CACHE_LOCK = RLock()
_SUMMARY_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _database_identity(session: Session) -> str:
    bind = session.get_bind()
    if bind is None:
        return "unbound"
    return bind.url.render_as_string(hide_password=False)


def _table_fingerprint(session: Session, model: Any, *extra_columns: Any) -> tuple[Any, ...]:
    columns = [
        func.count(model.id),
        func.max(model.id),
        func.max(model.updated_at),
        *[func.max(column) for column in extra_columns],
    ]
    return tuple(
        str(item) if item is not None else None
        for item in session.execute(select(*columns)).one()
    )


def _source_fingerprint(session: Session) -> tuple[Any, ...]:
    return (
        ("recommendations", _table_fingerprint(session, Recommendation, Recommendation.as_of_data_time)),
        ("market_bars", _table_fingerprint(session, MarketBar, MarketBar.observed_at)),
        ("news_items", _table_fingerprint(session, NewsItem, NewsItem.published_at)),
        ("news_entity_links", _table_fingerprint(session, NewsEntityLink, NewsEntityLink.effective_at)),
        ("stocks", _table_fingerprint(session, Stock)),
        ("schema_version", FACTOR_IC_STUDY_SCHEMA_VERSION),
        ("validation_protocol", VALIDATION_PROTOCOL_VERSION),
    )


def _factor_horizon_summary(study: dict[str, Any]) -> dict[str, Any]:
    horizons: dict[str, Any] = {}
    for horizon, factors in (study.get("factor_results") or {}).items():
        horizons[horizon] = {
            factor_key: {
                "rank_ic_mean": factor_data.get("rank_ic_mean"),
                "ic_ir": factor_data.get("ic_ir"),
                "positive_ic_rate": factor_data.get("positive_ic_rate"),
                "sample_count": factor_data.get("sample_count"),
            }
            for factor_key, factor_data in factors.items()
        }
    return horizons


def _project_factor_observation_summary(
    study: dict[str, Any],
    *,
    active_symbol_count: int,
) -> dict[str, Any]:
    return {
        "artifact_type": study.get("artifact_type", "factor_ic_study"),
        "status": study.get("status", "insufficient_sample"),
        "note": study.get("note"),
        "schema_version": study.get("schema_version"),
        "artifact_id": study.get("artifact_id"),
        "objective_universe": study.get("objective_universe", {}),
        "research_input_snapshot": study.get("research_input_snapshot", {}),
        "pit_feature_store": study.get("pit_feature_store", {}),
        "walk_forward_protocol": study.get("walk_forward_protocol", {}),
        "oos_validation": study.get("oos_validation", {}),
        "governance_promotion": study.get("governance_promotion", {}),
        "dashboard_projection_registry": study.get("dashboard_projection_registry", {}),
        "validation_protocol": study.get("validation_protocol", {}),
        "lineage": study.get("lineage", {}),
        "gate_readout": study.get("gate_readout", {}),
        "promotion_status": study.get("promotion_status", "blocked_from_production"),
        "claim_ceiling": study.get("claim_ceiling", "diagnostic_research_only"),
        "observation_count": study.get("observation_count", 0),
        "distinct_as_of_date_count": study.get("distinct_as_of_date_count", 0),
        "symbol_count": study.get("universe_symbol_count", active_symbol_count),
        "recommendation_sample_symbol_count": study.get("recommendation_sample_symbol_count", active_symbol_count),
        "benchmark_context": study.get("benchmark_context", {}),
        "horizons": _factor_horizon_summary(study),
    }


def build_factor_observation_summary_projection(
    session: Session,
    *,
    artifact_root: Any,
    active_symbols: set[str],
    min_records: int = 5,
    cache_ttl_seconds: float = _CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    """Return the dashboard-approved summary projection for factor validation."""
    try:
        key = (
            _database_identity(session),
            tuple(sorted(active_symbols)),
            _source_fingerprint(session),
            str(artifact_root or ""),
            int(min_records),
        )
        now = monotonic()
        with _CACHE_LOCK:
            cached = _SUMMARY_CACHE.get(key)
            if cached is not None and now - cached[0] <= cache_ttl_seconds:
                return deepcopy(cached[1])

        study = build_factor_observations(
            session,
            artifact_root=str(artifact_root or ""),
            min_records=min_records,
            persist=False,
        )
        projected = _project_factor_observation_summary(study, active_symbol_count=len(active_symbols))
        with _CACHE_LOCK:
            _SUMMARY_CACHE[key] = (now, deepcopy(projected))
        return projected
    except Exception as exc:
        return {
            "artifact_type": "factor_ic_study",
            "status": "unavailable",
            "note": f"因子 IC 研究摘要暂不可用：{exc}",
            "objective_universe": {},
            "research_input_snapshot": {},
            "pit_feature_store": {},
            "walk_forward_protocol": {},
            "oos_validation": {},
            "governance_promotion": {},
            "dashboard_projection_registry": {},
            "validation_protocol": {},
            "lineage": {},
            "gate_readout": {
                "gate_status": "blocked",
                "promotion_status": "blocked_from_production",
                "claim_ceiling": "diagnostic_research_only",
                "blocking_gate_ids": ["factor_validation_projection_unavailable"],
            },
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "diagnostic_research_only",
            "observation_count": 0,
            "distinct_as_of_date_count": 0,
            "symbol_count": len(active_symbols),
            "horizons": {},
        }
