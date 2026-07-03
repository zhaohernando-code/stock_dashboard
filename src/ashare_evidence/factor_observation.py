from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.benchmark import CSI_BENCHMARKS, DEFAULT_BENCHMARK_ID, benchmark_close_maps
from ashare_evidence.governance_promotion import (
    build_governance_promotion_decision_artifact,
    governance_promotion_summary,
    write_governance_promotion_decision_artifact,
)
from ashare_evidence.models import MarketBar, NewsEntityLink, NewsItem, Recommendation, Stock
from ashare_evidence.multiple_testing_diagnostics import (
    build_multiple_testing_diagnostics_artifact,
    multiple_testing_diagnostics_summary,
    write_multiple_testing_diagnostics_artifact,
)
from ashare_evidence.objective_universe import (
    build_objective_universe_artifact,
    objective_universe_summary,
    write_objective_universe_artifact,
)
from ashare_evidence.oos_validation import (
    build_oos_validation_artifact,
    oos_validation_summary,
    write_oos_validation_artifact,
)
from ashare_evidence.phase2.factor_ic import FactorICResult, aggregate_ic_results, compute_rank_ic
from ashare_evidence.pit_feature_store import (
    PIT_FEATURE_STORE_SCHEMA_VERSION,
    build_pit_feature_store_artifact,
    write_pit_feature_store_artifact,
)
from ashare_evidence.recommendation_selection import recommendation_recency_ordering
from ashare_evidence.research_artifact_store import write_research_validation_artifact
from ashare_evidence.walk_forward_protocol import (
    build_walk_forward_protocol_artifact,
    walk_forward_protocol_summary,
    write_walk_forward_protocol_artifact,
)
from ashare_evidence.watchlist import active_watchlist_symbols

FACTOR_KEYS = ("price_baseline", "news_event", "fundamental", "size_factor", "reversal", "liquidity")
HORIZONS = (10, 20, 40)
MIN_SYMBOLS_PER_SNAPSHOT = 20
MIN_SNAPSHOT_COUNT = 10
MIN_UNIQUE_SYMBOLS_FOR_WEIGHTING = 50
MIN_TOTAL_SAMPLES_FOR_WEIGHTING = 600
MIN_WINDOWS_FOR_WEIGHTING = 20
RESEARCH_INPUT_SNAPSHOT_SCHEMA_VERSION = "research_input_snapshot.v1"
FACTOR_IC_STUDY_SCHEMA_VERSION = "factor_ic_study.v2"
WEIGHT_SWEEP_STUDY_SCHEMA_VERSION = "weight_sweep_study.v2"
LEGACY_FACTOR_SCORE_SOURCE = "recommendation_payload.factor_breakdown"
VALIDATION_PROTOCOL_VERSION = "research_validation_protocol.v1"
FUSION_BASELINE = {
    "price_baseline": 0.35,
    "news_event": 0.20,
    "fundamental": 0.15,
    "size_factor": 0.10,
    "reversal": 0.10,
    "liquidity": 0.10,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _validation_run_id(prefix: str) -> str:
    return f"{prefix}:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"


def _artifact_id(prefix: str, validation_run_id: str) -> str:
    digest = hashlib.sha256(validation_run_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{digest}"


def _source_db_snapshot_id(session: Session) -> str:
    bind = session.get_bind()
    if bind is None:
        return "unknown-session-bind"
    rendered = bind.url.render_as_string(hide_password=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:16]


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_data_time_range(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    as_of_dates = sorted(str(row.get("as_of_date") or "") for row in rows if row.get("as_of_date"))
    entry_days = sorted(str(row.get("entry_trade_day") or "") for row in rows if row.get("entry_trade_day"))
    exit_days = sorted(str(row.get("exit_trade_day") or "") for row in rows if row.get("exit_trade_day"))
    return {
        "as_of_start": as_of_dates[0] if as_of_dates else None,
        "as_of_end": as_of_dates[-1] if as_of_dates else None,
        "entry_trade_day_start": entry_days[0] if entry_days else None,
        "exit_trade_day_end": exit_days[-1] if exit_days else None,
    }


def _recommendation_source_rows(recommendations: list[Recommendation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in recommendations:
        payload = record.recommendation_payload or {}
        factor_breakdown = payload.get("factor_breakdown") if isinstance(payload.get("factor_breakdown"), dict) else {}
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        factor_cards = [
            {
                "factor_key": card.get("factor_key"),
                "score": card.get("score"),
                "weight": card.get("weight"),
                "status": card.get("status"),
                "direction": card.get("direction"),
                "raw_value": card.get("raw_value"),
            }
            for card in evidence.get("factor_cards", [])
            if isinstance(card, dict) and card.get("factor_key")
        ]
        rows.append(
            {
                "id": record.id,
                "recommendation_key": record.recommendation_key,
                "stock_id": record.stock_id,
                "symbol": record.stock.symbol if record.stock is not None else None,
                "model_version_id": record.model_version_id,
                "model_run_id": record.model_run_id,
                "prompt_version_id": record.prompt_version_id,
                "as_of_data_time": record.as_of_data_time.isoformat() if record.as_of_data_time else None,
                "generated_at": record.generated_at.isoformat() if record.generated_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "direction": record.direction,
                "confidence_score": record.confidence_score,
                "horizon_min_days": record.horizon_min_days,
                "horizon_max_days": record.horizon_max_days,
                "evidence_status": record.evidence_status,
                "factor_score_input": {
                    "factor_breakdown": factor_breakdown,
                    "evidence_factor_cards": sorted(
                        factor_cards,
                        key=lambda card: str(card.get("factor_key") or ""),
                    ),
                },
                "payload_digest": _stable_digest(payload),
            }
        )
    return sorted(rows, key=lambda row: (str(row["symbol"] or ""), str(row["recommendation_key"] or "")))


def _market_bar_source_fingerprint(session: Session, symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {
            "symbols": [],
            "row_count": 0,
            "rows": [],
            "row_digest": _stable_digest([]),
            "by_symbol": {},
        }
    rows = session.execute(
        select(
            Stock.symbol,
            MarketBar.id,
            MarketBar.bar_key,
            MarketBar.observed_at,
            MarketBar.open_price,
            MarketBar.high_price,
            MarketBar.low_price,
            MarketBar.close_price,
            MarketBar.volume,
            MarketBar.amount,
            MarketBar.turnover_rate,
            MarketBar.adj_factor,
            MarketBar.total_mv,
            MarketBar.circ_mv,
            MarketBar.pe_ttm,
            MarketBar.pb,
            MarketBar.updated_at,
        )
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(Stock.symbol.in_(symbols), MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    serialized_rows = [
        {
            "symbol": str(symbol),
            "id": row_id,
            "bar_key": bar_key,
            "observed_at": observed_at.isoformat() if observed_at else None,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "volume": volume,
            "amount": amount,
            "turnover_rate": turnover_rate,
            "adj_factor": adj_factor,
            "total_mv": total_mv,
            "circ_mv": circ_mv,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "updated_at": updated_at.isoformat() if updated_at else None,
        }
        for (
            symbol,
            row_id,
            bar_key,
            observed_at,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            amount,
            turnover_rate,
            adj_factor,
            total_mv,
            circ_mv,
            pe_ttm,
            pb,
            updated_at,
        ) in rows
    ]
    by_symbol: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        symbol_rows = [row for row in serialized_rows if row["symbol"] == symbol]
        days = sorted(str(row["observed_at"] or "")[:10] for row in symbol_rows if row.get("observed_at"))
        row_ids = [row["id"] for row in symbol_rows]
        by_symbol[symbol] = {
            "row_count": len(symbol_rows),
            "date_start": days[0] if days else None,
            "date_end": days[-1] if days else None,
            "row_ids_digest": _stable_digest(row_ids),
            "row_digest": _stable_digest(symbol_rows),
        }
    return {
        "symbols": symbols,
        "row_count": len(serialized_rows),
        "rows": serialized_rows,
        "row_digest": _stable_digest(serialized_rows),
        "by_symbol": by_symbol,
    }


def _news_source_fingerprint(session: Session, symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {
            "symbols": [],
            "row_count": 0,
            "rows": [],
            "row_digest": _stable_digest([]),
            "by_symbol": {},
        }
    rows = session.execute(
        select(
            Stock.symbol,
            NewsItem.id,
            NewsItem.news_key,
            NewsItem.provider_name,
            NewsItem.external_id,
            NewsItem.headline,
            NewsItem.summary,
            NewsItem.content_excerpt,
            NewsItem.published_at,
            NewsItem.event_scope,
            NewsEntityLink.id,
            NewsEntityLink.relevance_score,
            NewsEntityLink.impact_direction,
            NewsEntityLink.effective_at,
            NewsEntityLink.decay_half_life_hours,
            NewsEntityLink.market_tag,
        )
        .join(NewsEntityLink, NewsEntityLink.stock_id == Stock.id)
        .join(NewsItem, NewsItem.id == NewsEntityLink.news_id)
        .where(Stock.symbol.in_(symbols))
        .order_by(Stock.symbol.asc(), NewsEntityLink.effective_at.asc(), NewsItem.id.asc(), NewsEntityLink.id.asc())
    ).all()
    serialized_rows = [
        {
            "symbol": str(symbol),
            "id": news_id,
            "news_key": news_key,
            "provider_name": provider_name,
            "external_id": external_id,
            "headline": headline,
            "summary": summary,
            "content_excerpt": content_excerpt,
            "published_at": published_at.isoformat() if published_at else None,
            "event_scope": event_scope,
            "link_id": link_id,
            "relevance_score": relevance_score,
            "impact_direction": impact_direction,
            "effective_at": effective_at.isoformat() if effective_at else None,
            "decay_half_life_hours": decay_half_life_hours,
            "market_tag": market_tag,
        }
        for (
            symbol,
            news_id,
            news_key,
            provider_name,
            external_id,
            headline,
            summary,
            content_excerpt,
            published_at,
            event_scope,
            link_id,
            relevance_score,
            impact_direction,
            effective_at,
            decay_half_life_hours,
            market_tag,
        ) in rows
    ]
    by_symbol: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        symbol_rows = [row for row in serialized_rows if row["symbol"] == symbol]
        days = sorted(str(row["effective_at"] or row["published_at"] or "")[:10] for row in symbol_rows)
        by_symbol[symbol] = {
            "row_count": len(symbol_rows),
            "date_start": days[0] if days else None,
            "date_end": days[-1] if days else None,
            "row_digest": _stable_digest(symbol_rows),
        }
    return {
        "symbols": symbols,
        "row_count": len(serialized_rows),
        "rows": serialized_rows,
        "row_digest": _stable_digest(serialized_rows),
        "by_symbol": by_symbol,
    }


def _date_range(values: list[date]) -> dict[str, str | None]:
    days = sorted(values)
    return {
        "start": days[0].isoformat() if days else None,
        "end": days[-1].isoformat() if days else None,
    }


def _input_source_time_range(
    recommendations: list[Recommendation],
    close_maps: dict[str, dict[date, float]],
    primary_benchmark: dict[date, float],
) -> dict[str, Any]:
    as_of_days = [
        record.as_of_data_time.date()
        for record in recommendations
        if record.as_of_data_time is not None
    ]
    market_days = [day for series in close_maps.values() for day in series]
    return {
        "recommendation_as_of": _date_range(as_of_days),
        "market_bar": _date_range(market_days),
        "primary_benchmark_bar": _date_range(list(primary_benchmark)),
    }


def _validation_protocol() -> dict[str, Any]:
    return {
        "protocol_version": VALIDATION_PROTOCOL_VERSION,
        "storage_boundary": "runtime_db_read_only_input__independent_research_validation_artifact_store",
        "feature_source": LEGACY_FACTOR_SCORE_SOURCE,
        "feature_source_status": "legacy_diagnostic_only",
        "walk_forward_status": "artifact_implemented",
        "purge_embargo_status": "artifact_implemented",
        "execution_constraint_status": "daily_close_forward_return_only",
        "promotion_rule": "raw validation artifacts cannot directly modify production weights or recommendations",
    }


def _snapshot_gate_readout(
    *,
    benchmark_status: str,
    symbols: list[str],
    recommendation_count: int,
    objective_universe: dict[str, Any],
) -> dict[str, Any]:
    checks = [
        {
            "gate_id": "runtime_db_read_only_source",
            "status": "pass",
            "reason": "snapshot builder reads runtime DB inputs and writes only artifact store output",
        },
        {
            "gate_id": "objective_research_universe",
            "status": "pass" if objective_universe.get("eligible_symbol_count", 0) else "blocked",
            "reason": None
            if objective_universe.get("eligible_symbol_count", 0)
            else "objective frozen universe artifact has no eligible members",
        },
        {
            "gate_id": "pit_feature_store",
            "status": "pass",
            "reason": "factor validation path builds an independent PIT feature store artifact from this frozen snapshot",
        },
        {
            "gate_id": "benchmark_availability",
            "status": "pass" if benchmark_status == "available" else "blocked",
            "reason": None if benchmark_status == "available" else "primary benchmark bars are unavailable for this snapshot",
        },
    ]
    return {
        "gate_status": "blocked" if any(check["status"] == "blocked" for check in checks) else "input_snapshot_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "input_boundary_only",
        "checks": checks,
        "blocking_gate_ids": [check["gate_id"] for check in checks if check["status"] == "blocked"],
        "snapshot_counts": {
            "symbol_count": len(symbols),
            "recommendation_count": recommendation_count,
            "objective_universe_symbol_count": objective_universe.get("eligible_symbol_count", 0),
        },
    }


def _gate_readout(
    *,
    status: str,
    symbols: list[str],
    objective_universe: dict[str, Any],
    walk_forward_protocol: dict[str, Any],
    distinct_as_of_count: int,
    observation_count: int,
    benchmark_status: str,
) -> dict[str, Any]:
    objective_symbol_count = int(objective_universe.get("eligible_symbol_count") or 0)
    walk_forward_gate = (walk_forward_protocol.get("gate_readout") or {}).get("gate_status")
    checks = [
        {
            "gate_id": "independent_feature_source",
            "status": "blocked",
            "reason": f"factor scores still come from {LEGACY_FACTOR_SCORE_SOURCE}",
        },
        {
            "gate_id": "objective_research_universe",
            "status": "pass" if objective_symbol_count else "blocked",
            "reason": None if objective_symbol_count else "objective frozen universe artifact has no eligible members",
        },
        {
            "gate_id": "walk_forward_purged_cv",
            "status": "pass" if walk_forward_gate == "walk_forward_ready" else "blocked",
            "reason": None
            if walk_forward_gate == "walk_forward_ready"
            else "walk-forward/purge/embargo artifact has insufficient ready splits",
        },
        {
            "gate_id": "benchmark_availability",
            "status": "pass" if benchmark_status == "available" else "blocked",
            "reason": None if benchmark_status == "available" else "primary benchmark bars are unavailable for this run",
        },
        {
            "gate_id": "research_universe_width",
            "status": "pass" if objective_symbol_count >= MIN_UNIQUE_SYMBOLS_FOR_WEIGHTING else "blocked",
            "reason": (
                None
                if objective_symbol_count >= MIN_UNIQUE_SYMBOLS_FOR_WEIGHTING
                else f"requires_at_least_{MIN_UNIQUE_SYMBOLS_FOR_WEIGHTING}_unique_symbols"
            ),
        },
        {
            "gate_id": "independent_time_windows",
            "status": "pass" if distinct_as_of_count >= MIN_WINDOWS_FOR_WEIGHTING else "blocked",
            "reason": (
                None
                if distinct_as_of_count >= MIN_WINDOWS_FOR_WEIGHTING
                else f"requires_at_least_{MIN_WINDOWS_FOR_WEIGHTING}_independent_as_of_dates"
            ),
        },
        {
            "gate_id": "cross_section_samples",
            "status": "pass" if observation_count >= MIN_TOTAL_SAMPLES_FOR_WEIGHTING else "blocked",
            "reason": (
                None
                if observation_count >= MIN_TOTAL_SAMPLES_FOR_WEIGHTING
                else f"requires_at_least_{MIN_TOTAL_SAMPLES_FOR_WEIGHTING}_observation_rows"
            ),
        },
    ]
    return {
        "gate_status": "blocked" if any(check["status"] == "blocked" for check in checks) else status,
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "diagnostic_research_only",
        "checks": checks,
        "blocking_gate_ids": [check["gate_id"] for check in checks if check["status"] == "blocked"],
        "objective_universe_symbol_count": objective_symbol_count,
        "recommendation_sample_symbol_count": len(symbols),
    }


def _build_research_input_snapshot(
    *,
    session: Session,
    validation_run_id: str,
    artifact_id: str,
    recommendations: list[Recommendation],
    symbols: list[str],
    close_maps: dict[str, dict[date, float]],
    recommendation_source_rows: list[dict[str, Any]],
    objective_universe: dict[str, Any],
    market_bar_fingerprint: dict[str, Any],
    benchmark_bar_fingerprint: dict[str, Any],
    news_source_fingerprint: dict[str, Any],
    horizons: tuple[int, ...],
    primary_benchmark_symbol: str,
    primary_benchmark: dict[date, float],
    benchmark_status: str,
) -> dict[str, Any]:
    source_db_locator_id = _source_db_snapshot_id(session)
    generated_at = datetime.now(UTC).isoformat()
    recommendation_as_of_dates = sorted(
        {
            record.as_of_data_time.date().isoformat()
            for record in recommendations
            if record.as_of_data_time is not None
        }
    )
    input_content = {
        "source_db_locator_id": source_db_locator_id,
        "recommendation_source_rows": recommendation_source_rows,
        "objective_universe": objective_universe_summary(objective_universe),
        "market_bar_fingerprint": market_bar_fingerprint,
        "benchmark_bar_fingerprint": benchmark_bar_fingerprint,
        "news_source_fingerprint": news_source_fingerprint,
        "symbols": symbols,
        "horizons": list(horizons),
        "primary_benchmark_symbol": primary_benchmark_symbol,
        "benchmark_status": benchmark_status,
        "validation_protocol_version": VALIDATION_PROTOCOL_VERSION,
    }
    input_content_digest = _stable_digest(input_content)
    return {
        "artifact_type": "research_input_snapshot",
        "schema_version": RESEARCH_INPUT_SNAPSHOT_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": generated_at,
        "source_db_snapshot_id": input_content_digest[:16],
        "source_db_locator_id": source_db_locator_id,
        "input_content_digest": input_content_digest,
        "source_data_time_range": _input_source_time_range(recommendations, close_maps, primary_benchmark),
        "feature_version": "legacy_recommendation_payload_factor_breakdown:v1",
        "label_version": "daily_close_forward_excess_return:v1",
        "code_version": "unresolved_local_checkout",
        "config_version": VALIDATION_PROTOCOL_VERSION,
        "validation_protocol": {
            **_validation_protocol(),
            "artifact_role": "research_input_snapshot",
            "snapshot_policy": "freeze_runtime_db_read_only_inputs_before_validation",
        },
        "gate_readout": _snapshot_gate_readout(
            benchmark_status=benchmark_status,
            symbols=symbols,
            recommendation_count=len(recommendations),
            objective_universe=objective_universe,
        ),
        "claim_ceiling": "input_boundary_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "runtime_db_read_only_input__independent_research_validation_artifact_store",
        "source_tables": ["recommendations", "stocks", "market_bars"],
        "objective_universe": objective_universe_summary(objective_universe),
        "universe_context": {
            "source": "objective_frozen_universe",
            "status": "frozen_before_validation",
            "promotion_blocker": "promotion still requires independent feature IC/OOS/governance despite frozen universe",
        },
        "symbols": symbols,
        "recommendation_count": len(recommendations),
        "recommendation_as_of_dates": recommendation_as_of_dates,
        "recommendation_source": {
            "row_count": len(recommendation_source_rows),
            "row_digest": _stable_digest(recommendation_source_rows),
            "rows": recommendation_source_rows,
        },
        "market_bar_source": market_bar_fingerprint,
        "benchmark_bar_source": benchmark_bar_fingerprint,
        "news_source": news_source_fingerprint,
        "horizons": list(horizons),
        "benchmark_context": {
            "primary_benchmark": DEFAULT_BENCHMARK_ID,
            "primary_symbol": primary_benchmark_symbol,
            "status": benchmark_status,
            "fallback_policy": "block_ic_rows_when_primary_benchmark_unavailable",
        },
    }


def _extract_factor_scores(payload: dict[str, Any]) -> dict[str, float]:
    # Legacy diagnostic path: this reads producer output, not independent point-in-time features.
    # Do not use these scores for production weighting or promotion decisions.
    factor_breakdown = payload.get("factor_breakdown") if isinstance(payload.get("factor_breakdown"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    cards = {
        str(card.get("factor_key")): card
        for card in evidence.get("factor_cards", [])
        if isinstance(card, dict) and card.get("factor_key")
    }
    scores: dict[str, float] = {}
    for key in FACTOR_KEYS:
        raw = factor_breakdown.get(key, {}) if isinstance(factor_breakdown.get(key), dict) else {}
        card = cards.get(key, {})
        scores[key] = _safe_float(raw.get("score", card.get("score")))
    return scores


def _extract_dynamic_weights(payload: dict[str, Any]) -> dict[str, float]:
    factor_breakdown = payload.get("factor_breakdown") if isinstance(payload.get("factor_breakdown"), dict) else {}
    weights: dict[str, float] = {}
    for key in FACTOR_KEYS:
        raw = factor_breakdown.get(key, {}) if isinstance(factor_breakdown.get(key), dict) else {}
        weights[key] = _safe_float(raw.get("weight"), FUSION_BASELINE[key])
    total = sum(weights.values())
    return {key: round(value / total, 4) for key, value in weights.items()} if total > 0 else dict(FUSION_BASELINE)


def _close_maps(session: Session, symbols: list[str]) -> dict[str, dict[date, float]]:
    if not symbols:
        return {}
    rows = session.execute(
        select(Stock.symbol, MarketBar.observed_at, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(Stock.symbol.in_(symbols), MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    ).all()
    result: dict[str, dict[date, float]] = {}
    for symbol, observed_at, close_price in rows:
        result.setdefault(str(symbol), {})[observed_at.date()] = float(close_price)
    return result


def _forward_return(series: dict[date, float], as_of: date, horizon: int) -> tuple[float, date, date] | None:
    days = sorted(series)
    if not days:
        return None
    entry_idx = bisect_left(days, as_of)
    if entry_idx >= len(days):
        return None
    exit_idx = entry_idx + horizon
    if exit_idx >= len(days):
        return None
    entry_day = days[entry_idx]
    exit_day = days[exit_idx]
    entry_close = series[entry_day]
    exit_close = series[exit_day]
    if entry_close == 0:
        return None
    return exit_close / entry_close - 1.0, entry_day, exit_day


def _records_for_scope(session: Session) -> list[Recommendation]:
    symbols = active_watchlist_symbols(session)
    query = (
        select(Recommendation)
        .join(Stock)
        .options(joinedload(Recommendation.stock))
        .order_by(*recommendation_recency_ordering(stock_symbol=True))
    )
    if symbols:
        query = query.where(Stock.symbol.in_(symbols))
    return list(session.scalars(query).all())


def _bucket_returns(rows: list[dict[str, Any]], factor_key: str) -> list[dict[str, Any]]:
    valid = [
        (row["scores"][factor_key], row["forward_excess_return"], row["symbol"])
        for row in rows
        if row.get("scores", {}).get(factor_key) is not None
    ]
    if len(valid) < MIN_SYMBOLS_PER_SNAPSHOT:
        return []
    valid.sort(key=lambda item: item[0])
    bucket_count = 3 if len(valid) < 20 else 5
    buckets: list[dict[str, Any]] = []
    for bucket_index in range(bucket_count):
        start = round(bucket_index * len(valid) / bucket_count)
        end = round((bucket_index + 1) * len(valid) / bucket_count)
        bucket = valid[start:end]
        if not bucket:
            continue
        mean_return = sum(item[1] for item in bucket) / len(bucket)
        buckets.append(
            {
                "bucket": bucket_index + 1,
                "label": f"Q{bucket_index + 1}",
                "mean_forward_excess_return": round(mean_return, 6),
                "sample_count": len(bucket),
                "symbols": [item[2] for item in bucket],
            }
        )
    return buckets


def _ic_result_to_dict(result: FactorICResult) -> dict[str, Any]:
    return {
        "factor_name": result.factor_name,
        "horizon_days": result.horizon_days,
        "rank_ic_mean": result.ic_mean,
        "ic_std": result.ic_std,
        "ic_ir": result.ic_ir,
        "positive_ic_rate": result.ic_positive_rate,
        "sample_count": result.sample_count,
        "computed_at": result.computed_at,
        "period_count": result.period_count,
        "weighting_status": result.weighting_status,
        "weighting_reason": result.weighting_reason,
    }


def build_factor_observations(
    session: Session,
    *,
    artifact_root: str,
    min_records: int = MIN_SYMBOLS_PER_SNAPSHOT,
    horizons: tuple[int, ...] = HORIZONS,
    persist: bool = True,
    include_raw_research_artifacts: bool = False,
) -> dict[str, Any]:
    validation_run_id = _validation_run_id("factor-ic")
    input_snapshot_id = _artifact_id("research-input-snapshot", validation_run_id)
    recommendations = _records_for_scope(session)
    symbols = sorted({record.stock.symbol for record in recommendations if record.stock is not None})
    objective_universe = build_objective_universe_artifact(
        session,
        validation_run_id=validation_run_id,
        recommended_symbols=symbols,
    )
    close_maps = _close_maps(session, symbols)
    recommendation_source_rows = _recommendation_source_rows(recommendations)
    benchmark_maps = benchmark_close_maps(session)
    primary_benchmark_symbol = CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"]
    primary_benchmark = benchmark_maps.get(primary_benchmark_symbol, {})
    by_as_of: dict[date, list[Recommendation]] = {}
    for record in recommendations:
        if record.as_of_data_time is None or record.stock is None:
            continue
        by_as_of.setdefault(record.as_of_data_time.date(), []).append(record)

    observation_rows: list[dict[str, Any]] = []
    snapshot_results: dict[int, list[FactorICResult]] = {horizon: [] for horizon in horizons}
    per_horizon_rows: dict[int, list[dict[str, Any]]] = {horizon: [] for horizon in horizons}
    benchmark_source = "csi_index_daily"
    benchmark_status = "available"
    if not primary_benchmark:
        benchmark_source = "unavailable"
        benchmark_status = "missing_primary_benchmark_bars"
    market_bar_fingerprint = _market_bar_source_fingerprint(session, symbols)
    benchmark_bar_fingerprint = _market_bar_source_fingerprint(session, [primary_benchmark_symbol])
    news_source_fingerprint = _news_source_fingerprint(session, symbols)
    input_snapshot = _build_research_input_snapshot(
        session=session,
        validation_run_id=validation_run_id,
        artifact_id=input_snapshot_id,
        recommendations=recommendations,
        symbols=symbols,
        close_maps=close_maps,
        recommendation_source_rows=recommendation_source_rows,
        objective_universe=objective_universe,
        market_bar_fingerprint=market_bar_fingerprint,
        benchmark_bar_fingerprint=benchmark_bar_fingerprint,
        news_source_fingerprint=news_source_fingerprint,
        horizons=horizons,
        primary_benchmark_symbol=primary_benchmark_symbol,
        primary_benchmark=primary_benchmark,
        benchmark_status=benchmark_status,
    )
    pit_feature_store = build_pit_feature_store_artifact(input_snapshot)

    for as_of_day, records in sorted(by_as_of.items()):
        scored_records: list[dict[str, Any]] = []
        for record in records:
            symbol = record.stock.symbol
            forward_inputs = {
                horizon: _forward_return(close_maps.get(symbol, {}), as_of_day, horizon)
                for horizon in horizons
            }
            if not any(forward_inputs.values()):
                continue
            payload = record.recommendation_payload or {}
            scored_records.append(
                {
                    "symbol": symbol,
                    "recommendation_key": record.recommendation_key,
                    "as_of_date": as_of_day,
                    "as_of": record.as_of_data_time,
                    "direction": record.direction,
                    "scores": _extract_factor_scores(payload),
                    "dynamic_weights": _extract_dynamic_weights(payload),
                    "forward_inputs": forward_inputs,
                }
            )
        for horizon in horizons:
            horizon_rows: list[dict[str, Any]] = []
            stock_returns: list[float] = []
            for item in scored_records:
                forward = item["forward_inputs"].get(horizon)
                if forward is None:
                    continue
                stock_return, entry_day, exit_day = forward
                stock_returns.append(stock_return)
                horizon_rows.append(
                    {
                        "symbol": item["symbol"],
                        "recommendation_key": item["recommendation_key"],
                        "as_of": item["as_of"].isoformat(),
                        "as_of_date": as_of_day.isoformat(),
                        "horizon_days": horizon,
                        "direction": item["direction"],
                        "scores": item["scores"],
                        "dynamic_weights": item["dynamic_weights"],
                        "stock_forward_return": stock_return,
                        "entry_trade_day": entry_day.isoformat(),
                        "exit_trade_day": exit_day.isoformat(),
                    }
                )
            if len(horizon_rows) < min_records:
                continue
            benchmark_return = None
            if primary_benchmark:
                benchmark_forward = _forward_return(primary_benchmark, as_of_day, horizon)
                if benchmark_forward is not None:
                    benchmark_return = benchmark_forward[0]
            if benchmark_return is None:
                continue
            for row in horizon_rows:
                row["benchmark_return"] = round(float(benchmark_return), 6)
                row["benchmark_source"] = benchmark_source
                row["forward_excess_return"] = round(float(row["stock_forward_return"]) - float(benchmark_return), 6)
            factor_scores = {
                factor_key: [float(row["scores"][factor_key]) for row in horizon_rows]
                for factor_key in FACTOR_KEYS
            }
            forward_excess = [float(row["forward_excess_return"]) for row in horizon_rows]
            snapshot_results[horizon].extend(compute_rank_ic(factor_scores, forward_excess, horizon))
            per_horizon_rows[horizon].extend(horizon_rows)
            observation_rows.extend(horizon_rows)

    factor_results: dict[str, Any] = {}
    for horizon in horizons:
        aggregate = aggregate_ic_results(
            snapshot_results[horizon],
            min_period_count_for_weighting=MIN_WINDOWS_FOR_WEIGHTING,
            min_sample_count_for_weighting=MIN_TOTAL_SAMPLES_FOR_WEIGHTING,
        )
        horizon_key = f"{horizon}d"
        factor_results[horizon_key] = {}
        for factor_key in FACTOR_KEYS:
            rows = per_horizon_rows[horizon]
            item = aggregate.get(factor_key)
            factor_results[horizon_key][factor_key] = {
                **(_ic_result_to_dict(item) if item else {
                    "factor_name": factor_key,
                    "horizon_days": horizon,
                    "rank_ic_mean": None,
                    "ic_std": None,
                    "ic_ir": None,
                    "positive_ic_rate": None,
                    "sample_count": len(rows),
                    "computed_at": datetime.now(UTC).isoformat(),
                }),
                "bucket_returns": _bucket_returns(rows, factor_key),
            }

    distinct_as_of = sorted({row["as_of_date"] for row in observation_rows})
    sample_ready = len(distinct_as_of) >= MIN_SNAPSHOT_COUNT and len(observation_rows) >= MIN_SNAPSHOT_COUNT * min_records
    status = "diagnostic_only_blocked" if sample_ready else "insufficient_sample"
    walk_forward_protocol = build_walk_forward_protocol_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=input_snapshot["source_db_snapshot_id"],
        source_data_time_range=_source_data_time_range(observation_rows),
        objective_universe=objective_universe,
        input_snapshot=input_snapshot,
        pit_feature_store=pit_feature_store,
        observation_rows=observation_rows,
        horizons=list(horizons),
    )
    gate_readout = _gate_readout(
        status=status,
        symbols=symbols,
        objective_universe=objective_universe,
        walk_forward_protocol=walk_forward_protocol,
        distinct_as_of_count=len(distinct_as_of),
        observation_count=len(observation_rows),
        benchmark_status=benchmark_status,
    )
    artifact_id = _artifact_id("factor-ic-study", validation_run_id)
    results: dict[str, Any] = {
        "artifact_type": "factor_ic_study",
        "schema_version": FACTOR_IC_STUDY_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "validation_run_id": validation_run_id,
        "source_db_snapshot_id": input_snapshot["source_db_snapshot_id"],
        "source_data_time_range": _source_data_time_range(observation_rows),
        "feature_version": "legacy_recommendation_payload_factor_breakdown:v1",
        "label_version": "daily_close_forward_excess_return:v1",
        "code_version": "unresolved_local_checkout",
        "config_version": VALIDATION_PROTOCOL_VERSION,
        "research_input_snapshot": {
            "artifact_type": "research_input_snapshot",
            "schema_version": RESEARCH_INPUT_SNAPSHOT_SCHEMA_VERSION,
            "artifact_id": input_snapshot_id,
            "storage_boundary": input_snapshot["storage_boundary"],
            "promotion_status": input_snapshot["promotion_status"],
            "claim_ceiling": input_snapshot["claim_ceiling"],
        },
        "research_input_snapshot_artifact": input_snapshot,
        "objective_universe": objective_universe_summary(objective_universe),
        "walk_forward_protocol": walk_forward_protocol_summary(walk_forward_protocol),
        "pit_feature_store": {
            "artifact_type": "pit_feature_store",
            "schema_version": PIT_FEATURE_STORE_SCHEMA_VERSION,
            "artifact_id": pit_feature_store["artifact_id"],
            "storage_boundary": pit_feature_store["storage_boundary"],
            "promotion_status": pit_feature_store["promotion_status"],
            "claim_ceiling": pit_feature_store["claim_ceiling"],
            "feature_row_count": pit_feature_store["feature_row_count"],
            "feature_version": pit_feature_store["feature_version"],
        },
        "validation_protocol": _validation_protocol(),
        "lineage": {
            "source_db_snapshot_id": input_snapshot["source_db_snapshot_id"],
            "objective_universe_id": objective_universe["artifact_id"],
            "research_input_snapshot_id": input_snapshot_id,
            "pit_feature_store_id": pit_feature_store["artifact_id"],
            "walk_forward_protocol_id": walk_forward_protocol["artifact_id"],
            "source_data_time_range": _source_data_time_range(observation_rows),
            "feature_version": "legacy_recommendation_payload_factor_breakdown:v1",
            "independent_pit_feature_version": pit_feature_store["feature_version"],
            "label_version": "daily_close_forward_excess_return:v1",
            "config_version": VALIDATION_PROTOCOL_VERSION,
            "code_version": "unresolved_local_checkout",
        },
        "universe_symbol_count": objective_universe["eligible_symbol_count"],
        "recommendation_sample_symbol_count": len(symbols),
        "symbols": symbols,
        "universe_context": {
            "source": "objective_frozen_universe",
            "status": "frozen_before_validation",
            "recommendation_sample_source": "active_watchlist_recommendation_records",
            "promotion_blocker": "legacy factor observations are still diagnostic-only and require OOS/governance",
        },
        "horizons": list(horizons),
        "benchmark_context": {
            "primary_benchmark": DEFAULT_BENCHMARK_ID,
            "primary_symbol": primary_benchmark_symbol,
            "source": benchmark_source,
            "status": benchmark_status,
            "fallback_policy": "block_ic_rows_when_primary_benchmark_unavailable",
        },
        "observation_count": len(observation_rows),
        "distinct_as_of_date_count": len(distinct_as_of),
        "min_symbols_per_snapshot": min_records,
        "min_snapshot_count": MIN_SNAPSHOT_COUNT,
        "min_unique_symbols_for_weighting": MIN_UNIQUE_SYMBOLS_FOR_WEIGHTING,
        "min_total_samples_for_weighting": MIN_TOTAL_SAMPLES_FOR_WEIGHTING,
        "min_windows_for_weighting": MIN_WINDOWS_FOR_WEIGHTING,
        "gate_readout": gate_readout,
        "promotion_status": gate_readout["promotion_status"],
        "claim_ceiling": gate_readout["claim_ceiling"],
        "factor_results": factor_results,
        "observation_rows": observation_rows,
        "note": (
            "该结果仅为 legacy diagnostic：因子分数仍来自 recommendation_payload，不能用于生产权重或 promotion。"
            if status != "insufficient_sample"
            else "样本不足，不能输出精确因子可信度或权重结论。"
        ),
    }
    oos_validation = build_oos_validation_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=input_snapshot["source_db_snapshot_id"],
        source_data_time_range=_source_data_time_range(observation_rows),
        factor_study=results,
        walk_forward_protocol=walk_forward_protocol,
    )
    results["oos_validation"] = oos_validation_summary(oos_validation)
    results["lineage"] = {
        **dict(results.get("lineage") or {}),
        "oos_validation_id": oos_validation["artifact_id"],
    }
    governance_decision = build_governance_promotion_decision_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=input_snapshot["source_db_snapshot_id"],
        source_data_time_range=_source_data_time_range(observation_rows),
        candidate_kind="factor_ic_study",
        candidate_artifact=results,
        objective_universe=objective_universe,
        walk_forward_protocol=walk_forward_protocol,
        oos_validation=oos_validation,
    )
    results["governance_promotion"] = governance_promotion_summary(governance_decision)
    results["lineage"] = {
        **dict(results.get("lineage") or {}),
        "governance_promotion_decision_id": governance_decision["artifact_id"],
    }
    if include_raw_research_artifacts:
        results["objective_universe_artifact"] = objective_universe
        results["pit_feature_store_artifact"] = pit_feature_store
        results["walk_forward_protocol_artifact"] = walk_forward_protocol
        results["oos_validation_artifact"] = oos_validation
        results["governance_promotion_artifact"] = governance_decision
    if persist:
        write_objective_universe_artifact(objective_universe, artifact_root=artifact_root)
        _write_research_input_snapshot(input_snapshot, artifact_root=artifact_root, artifact_id=input_snapshot_id)
        write_pit_feature_store_artifact(pit_feature_store, artifact_root=artifact_root)
        write_walk_forward_protocol_artifact(walk_forward_protocol, artifact_root=artifact_root)
        write_oos_validation_artifact(oos_validation, artifact_root=artifact_root)
        write_governance_promotion_decision_artifact(governance_decision, artifact_root=artifact_root)
        _write_artifact(results, artifact_root=artifact_root, artifact_id=artifact_id)
    return results


def _write_research_input_snapshot(results: dict[str, Any], *, artifact_root: str, artifact_id: str) -> None:
    write_research_validation_artifact(
        "research_input_snapshot",
        artifact_id,
        results,
        root=Path(artifact_root) if artifact_root else None,
    )


def _write_artifact(results: dict[str, Any], *, artifact_root: str, artifact_id: str) -> None:
    write_research_validation_artifact(
        "factor_ic_study",
        artifact_id,
        results,
        root=Path(artifact_root) if artifact_root else None,
    )


def _build_weight_grid() -> list[tuple[str, dict[str, float]]]:
    return [
        ("baseline", dict(FUSION_BASELINE)),
        ("price_heavy", {**FUSION_BASELINE, "price_baseline": 0.45, "news_event": 0.15, "fundamental": 0.10}),
        ("news_heavy", {**FUSION_BASELINE, "price_baseline": 0.25, "news_event": 0.30, "fundamental": 0.15}),
        (
            "balanced",
            {
                "price_baseline": 0.25,
                "news_event": 0.20,
                "fundamental": 0.20,
                "size_factor": 0.12,
                "reversal": 0.12,
                "liquidity": 0.11,
            },
        ),
        ("size_aware", {**FUSION_BASELINE, "size_factor": 0.15, "reversal": 0.08, "liquidity": 0.07}),
    ]


def _weighted_score(row: dict[str, Any], weights: dict[str, float]) -> float:
    return sum(float(row["scores"].get(key, 0.0)) * float(weights.get(key, 0.0)) for key in FACTOR_KEYS)


def sweep_weights(session: Session, *, artifact_root: str, persist: bool = True) -> dict[str, Any]:
    validation_run_id = _validation_run_id("weight-sweep")
    observations = build_factor_observations(
        session,
        artifact_root=artifact_root,
        min_records=MIN_SYMBOLS_PER_SNAPSHOT,
        persist=False,
        include_raw_research_artifacts=True,
    )
    rows = observations.get("observation_rows", [])
    weight_grid = _build_weight_grid()
    sweep_results: list[dict[str, Any]] = []
    for label, weights in weight_grid:
        by_horizon: dict[int, list[FactorICResult]] = {}
        spread_rows: dict[int, list[float]] = {}
        grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault((int(row["horizon_days"]), str(row["as_of_date"])), []).append(row)
        for (horizon, _as_of), group_rows in grouped.items():
            if len(group_rows) < MIN_SYMBOLS_PER_SNAPSHOT:
                continue
            scores = [_weighted_score(row, weights) for row in group_rows]
            forward = [float(row["forward_excess_return"]) for row in group_rows]
            by_horizon.setdefault(horizon, []).extend(
                compute_rank_ic({"fusion_score": scores}, forward, horizon)
            )
            ranked = sorted(zip(scores, forward), key=lambda item: item[0])
            top = ranked[-max(1, len(ranked) // 3):]
            bottom = ranked[:max(1, len(ranked) // 3)]
            spread_rows.setdefault(horizon, []).append(
                sum(item[1] for item in top) / len(top) - sum(item[1] for item in bottom) / len(bottom)
            )
        horizon_metrics: dict[str, Any] = {}
        for horizon, ic_rows in by_horizon.items():
            aggregate = aggregate_ic_results(
                ic_rows,
                min_period_count_for_weighting=MIN_WINDOWS_FOR_WEIGHTING,
                min_sample_count_for_weighting=MIN_TOTAL_SAMPLES_FOR_WEIGHTING,
            )
            fusion = aggregate.get("fusion_score")
            spreads = spread_rows.get(horizon, [])
            horizon_metrics[f"{horizon}d"] = {
                "rank_ic_mean": fusion.ic_mean if fusion else None,
                "ic_ir": fusion.ic_ir if fusion else None,
                "positive_ic_rate": fusion.ic_positive_rate if fusion else None,
                "sample_count": fusion.sample_count if fusion else 0,
                "mean_top_bottom_spread": round(sum(spreads) / len(spreads), 6) if spreads else None,
                "snapshot_count": len(spreads),
            }
        sweep_results.append({"label": label, "weights": weights, "horizon_metrics": horizon_metrics})
    status = "insufficient_sample" if observations.get("status") == "insufficient_sample" else "diagnostic_only_blocked"
    artifact_id = _artifact_id("weight-sweep-study", validation_run_id)
    source_data_time_range = (observations.get("lineage") or {}).get("source_data_time_range", {})
    results: dict[str, Any] = {
        "artifact_type": "weight_sweep_study",
        "schema_version": WEIGHT_SWEEP_STUDY_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "validation_run_id": validation_run_id,
        "source_db_snapshot_id": (observations.get("lineage") or {}).get("source_db_snapshot_id"),
        "source_data_time_range": source_data_time_range,
        "feature_version": (observations.get("lineage") or {}).get("feature_version"),
        "label_version": (observations.get("lineage") or {}).get("label_version"),
        "code_version": (observations.get("lineage") or {}).get("code_version"),
        "config_version": VALIDATION_PROTOCOL_VERSION,
        "validation_protocol": {
            **_validation_protocol(),
            "weight_sweep_policy": "diagnostic_only_no_auto_promotion",
            "multiple_testing_status": "not_corrected",
        },
        "objective_universe": observations.get("objective_universe", {}),
        "research_input_snapshot": observations.get("research_input_snapshot", {}),
        "pit_feature_store": observations.get("pit_feature_store", {}),
        "walk_forward_protocol": observations.get("walk_forward_protocol", {}),
        "oos_validation": observations.get("oos_validation", {}),
        "lineage": observations.get("lineage", {}),
        "gate_readout": observations.get("gate_readout", {}),
        "promotion_status": "blocked_from_production",
        "claim_ceiling": (observations.get("gate_readout") or {}).get("claim_ceiling", "diagnostic_research_only"),
        "baseline_weights": FUSION_BASELINE,
        "benchmark_context": observations.get("benchmark_context", {}),
        "observation_count": observations.get("observation_count", 0),
        "distinct_as_of_date_count": observations.get("distinct_as_of_date_count", 0),
        "sweep_results": sweep_results,
        "note": "权重 sweep 只产出独立验证制品，不自动修改生产权重；不得把 in-sample 最优组合作为上线结论。",
    }
    multiple_testing_diagnostics = build_multiple_testing_diagnostics_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=(observations.get("lineage") or {}).get("source_db_snapshot_id"),
        source_data_time_range=source_data_time_range,
        weight_sweep=results,
    )
    results["multiple_testing_diagnostics"] = multiple_testing_diagnostics_summary(multiple_testing_diagnostics)
    results["validation_protocol"]["multiple_testing_status"] = (
        "artifact_implemented"
        if multiple_testing_diagnostics.get("artifact_id")
        else "not_corrected"
    )
    results["lineage"] = {
        **dict(results.get("lineage") or {}),
        "multiple_testing_diagnostics_id": multiple_testing_diagnostics["artifact_id"],
    }
    governance_decision = build_governance_promotion_decision_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=(observations.get("lineage") or {}).get("source_db_snapshot_id"),
        source_data_time_range=source_data_time_range,
        candidate_kind="weight_sweep_study",
        candidate_artifact=results,
        objective_universe=observations.get("objective_universe", {}),
        walk_forward_protocol=observations.get("walk_forward_protocol", {}),
        oos_validation=observations.get("oos_validation", {}),
        multiple_testing_diagnostics=multiple_testing_diagnostics,
    )
    results["governance_promotion"] = governance_promotion_summary(governance_decision)
    results["lineage"] = {
        **dict(results.get("lineage") or {}),
        "governance_promotion_decision_id": governance_decision["artifact_id"],
    }
    if persist:
        objective_universe = observations.get("objective_universe_artifact")
        if isinstance(objective_universe, dict) and objective_universe.get("artifact_id"):
            write_objective_universe_artifact(objective_universe, artifact_root=artifact_root)
        input_snapshot = observations.get("research_input_snapshot_artifact")
        input_snapshot_ref = observations.get("research_input_snapshot") or {}
        if isinstance(input_snapshot, dict) and input_snapshot_ref.get("artifact_id"):
            _write_research_input_snapshot(
                input_snapshot,
                artifact_root=artifact_root,
                artifact_id=str(input_snapshot_ref["artifact_id"]),
            )
        pit_feature_store = observations.get("pit_feature_store_artifact")
        if isinstance(pit_feature_store, dict) and pit_feature_store.get("artifact_id"):
            write_pit_feature_store_artifact(pit_feature_store, artifact_root=artifact_root)
        walk_forward_protocol = observations.get("walk_forward_protocol_artifact")
        if isinstance(walk_forward_protocol, dict) and walk_forward_protocol.get("artifact_id"):
            write_walk_forward_protocol_artifact(walk_forward_protocol, artifact_root=artifact_root)
        oos_validation = observations.get("oos_validation_artifact")
        if isinstance(oos_validation, dict) and oos_validation.get("artifact_id"):
            write_oos_validation_artifact(oos_validation, artifact_root=artifact_root)
        write_multiple_testing_diagnostics_artifact(multiple_testing_diagnostics, artifact_root=artifact_root)
        write_governance_promotion_decision_artifact(governance_decision, artifact_root=artifact_root)
        _write_sweep_artifact(results, artifact_root=artifact_root, artifact_id=artifact_id)
    return results


def _write_sweep_artifact(results: dict[str, Any], *, artifact_root: str, artifact_id: str) -> None:
    write_research_validation_artifact(
        "weight_sweep_study",
        artifact_id,
        results,
        root=Path(artifact_root) if artifact_root else None,
    )
