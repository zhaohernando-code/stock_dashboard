from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


CAPACITY_OPPORTUNITY_FEATURE_GAP_VERSION = "capacity_opportunity_feature_gap.v1"


def build_capacity_opportunity_feature_gap_probe(
    opportunity_discovery: dict[str, Any],
    *,
    top_k: int = 5,
    near_floor_ratio: float = 0.75,
) -> dict[str, Any]:
    """Probe whether discovered full-market liquid winners look reachable by broad ex-ante archetypes.

    This intentionally consumes only an existing opportunity-discovery artifact. It is a replay triage gate,
    not a training routine and not acceptance evidence.
    """

    dates = list(opportunity_discovery.get("dates") or [])
    full_fill_avg_amount_20d = _safe_float(opportunity_discovery.get("full_fill_avg_amount_20d_required"))
    date_summaries: list[dict[str, Any]] = []
    blocking_gate_ids: list[str] = []

    for item in dates:
        source_floor = _safe_float(item.get("source_artifact_net_excess_return"))
        top_rows = list(item.get("top_liquid_by_future_excess") or [])[: max(top_k, 1)]
        analyzed_rows = [
            _analyze_candidate(
                row,
                source_floor=source_floor,
                full_fill_avg_amount_20d=full_fill_avg_amount_20d,
                near_floor_ratio=near_floor_ratio,
            )
            for row in top_rows
        ]
        best = analyzed_rows[0] if analyzed_rows else None
        nondegrading_rows = [
            row for row in analyzed_rows if row["meets_source_floor"] and row["archetypes"]
        ]
        near_rows = [row for row in analyzed_rows if row["meets_near_floor"] and row["archetypes"]]
        retained_present_count = sum(1 for row in analyzed_rows if row["present_in_retained_top10_liquid_summary"])
        date_summaries.append(
            {
                "as_of_date": item.get("as_of_date"),
                "source_symbol": item.get("source_symbol"),
                "source_artifact_net_excess_return": source_floor,
                "best_liquid_symbol": item.get("best_liquid_symbol"),
                "best_liquid_future_excess_return_20d": item.get("best_liquid_future_excess_return_20d"),
                "best_gap_to_source_floor": (
                    _safe_float(item.get("best_liquid_future_excess_return_20d")) - source_floor
                    if source_floor is not None
                    and _safe_float(item.get("best_liquid_future_excess_return_20d")) is not None
                    else None
                ),
                "best_candidate_has_archetype": bool(best and best["archetypes"]),
                "covered_nondegrading_candidate_count": len(nondegrading_rows),
                "covered_near_floor_candidate_count": len(near_rows),
                "top_k_retained_top10_liquid_present_count": retained_present_count,
                "top_k_retained_top10_liquid_present_rate": retained_present_count / len(analyzed_rows)
                if analyzed_rows
                else 0.0,
                "top_candidates": analyzed_rows,
            }
        )

    if not date_summaries:
        blocking_gate_ids.append("capacity_opportunity_feature_gap:no_dates")

    date_count = len(date_summaries)
    dates_with_archetype_best = sum(1 for row in date_summaries if row["best_candidate_has_archetype"])
    dates_with_nondegrading_archetype = sum(
        1 for row in date_summaries if int(row["covered_nondegrading_candidate_count"]) > 0
    )
    dates_with_near_floor_archetype = sum(
        1 for row in date_summaries if int(row["covered_near_floor_candidate_count"]) > 0
    )
    if date_count and dates_with_nondegrading_archetype < date_count:
        blocking_gate_ids.append(
            "capacity_opportunity_feature_gap:not_all_dates_have_nondegrading_covered_liquid_archetype"
        )
    if date_count and dates_with_archetype_best < date_count:
        blocking_gate_ids.append("capacity_opportunity_feature_gap:not_all_best_liquid_candidates_are_archetype_covered")

    retained_best_present_count = sum(
        1
        for row in date_summaries
        for candidate in row["top_candidates"][:1]
        if candidate["present_in_retained_top10_liquid_summary"]
    )
    return {
        "artifact_type": "capacity_opportunity_feature_gap",
        "schema_version": CAPACITY_OPPORTUNITY_FEATURE_GAP_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": sorted(set(blocking_gate_ids)),
        "claim_ceiling": "feature_gap_triage_only_no_model_replay_no_promotion",
        "source_opportunity_discovery_id": opportunity_discovery.get("artifact_id"),
        "source_opportunity_discovery_type": opportunity_discovery.get("artifact_type"),
        "full_fill_avg_amount_20d_required": full_fill_avg_amount_20d,
        "top_k": top_k,
        "near_floor_ratio": near_floor_ratio,
        "date_count": date_count,
        "dates_with_archetype_covered_best_liquid_candidate": dates_with_archetype_best,
        "dates_with_nondegrading_archetype_candidate": dates_with_nondegrading_archetype,
        "dates_with_near_floor_archetype_candidate": dates_with_near_floor_archetype,
        "best_liquid_candidate_retained_top10_present_count": retained_best_present_count,
        "archetype_definitions": _archetype_definitions(),
        "interpretation": _interpretation(
            date_count=date_count,
            dates_with_archetype_best=dates_with_archetype_best,
            dates_with_nondegrading_archetype=dates_with_nondegrading_archetype,
            dates_with_near_floor_archetype=dates_with_near_floor_archetype,
        ),
        "dates": date_summaries,
    }


def write_capacity_opportunity_feature_gap_probe(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _analyze_candidate(
    row: dict[str, Any],
    *,
    source_floor: float | None,
    full_fill_avg_amount_20d: float | None,
    near_floor_ratio: float,
) -> dict[str, Any]:
    future_excess = _safe_float(row.get("future_excess_return_20d"))
    return {
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "future_excess_return_20d": future_excess,
        "gap_to_source_floor": future_excess - source_floor
        if future_excess is not None and source_floor is not None
        else None,
        "meets_source_floor": bool(future_excess is not None and source_floor is not None and future_excess >= source_floor),
        "meets_near_floor": bool(
            future_excess is not None
            and source_floor is not None
            and future_excess >= source_floor * max(near_floor_ratio, 0.0)
        ),
        "present_in_retained_top10_liquid_summary": bool(row.get("present_in_retained_top10_liquid_summary")),
        "archetypes": _candidate_archetypes(row, full_fill_avg_amount_20d=full_fill_avg_amount_20d),
        "features": {
            "avg_amount_20d": _safe_float(row.get("avg_amount_20d")),
            "avg_amount_20d_percentile": _safe_float(row.get("avg_amount_20d_percentile")),
            "amount_10d_vs_20d_percentile": _safe_float(row.get("amount_10d_vs_20d_percentile")),
            "return_5d_percentile": _safe_float(row.get("return_5d_percentile")),
            "return_20d_percentile": _safe_float(row.get("return_20d_percentile")),
            "turnover_rate_percentile": _safe_float(row.get("turnover_rate_percentile")),
            "volatility_20d_percentile": _safe_float(row.get("volatility_20d_percentile")),
            "total_mv_percentile": _safe_float(row.get("total_mv_percentile")),
        },
    }


def _candidate_archetypes(row: dict[str, Any], *, full_fill_avg_amount_20d: float | None) -> list[str]:
    archetypes: list[str] = []
    avg_amount = _safe_float(row.get("avg_amount_20d"), 0.0) or 0.0
    full_fill_ready = full_fill_avg_amount_20d is None or avg_amount >= full_fill_avg_amount_20d
    amount_expansion = _safe_float(row.get("amount_10d_vs_20d_percentile"), 0.0) or 0.0
    return_5d = _safe_float(row.get("return_5d_percentile"), 0.0) or 0.0
    return_20d = _safe_float(row.get("return_20d_percentile"), 0.0) or 0.0
    turnover = _safe_float(row.get("turnover_rate_percentile"), 0.0) or 0.0
    volatility = _safe_float(row.get("volatility_20d_percentile"), 1.0) or 1.0
    total_mv = _safe_float(row.get("total_mv_percentile"), 0.0) or 0.0
    avg_amount_pct = _safe_float(row.get("avg_amount_20d_percentile"), 0.0) or 0.0

    if full_fill_ready and amount_expansion >= 0.75 and return_5d >= 0.75 and turnover >= 0.75:
        archetypes.append("turnover_amount_rebound")
    if full_fill_ready and avg_amount_pct >= 0.80 and total_mv >= 0.75 and return_20d <= 0.85 and volatility <= 0.75:
        archetypes.append("large_liquid_pullback")
    if full_fill_ready and amount_expansion >= 0.65 and volatility <= 0.35 and return_20d <= 0.70:
        archetypes.append("low_volatility_pullback_turn")
    if full_fill_ready and total_mv <= 0.30 and amount_expansion >= 0.75 and turnover >= 0.75:
        archetypes.append("small_mid_turnover_reversal")
    return archetypes


def _archetype_definitions() -> dict[str, str]:
    return {
        "turnover_amount_rebound": "full-fill liquid, top-quartile amount expansion, top-quartile 5d return, and top-quartile turnover",
        "large_liquid_pullback": "full-fill liquid, top-liquidity/top-market-cap, not high 20d rank, and not high volatility",
        "low_volatility_pullback_turn": "full-fill liquid, amount expansion, low volatility, and non-leading 20d rank",
        "small_mid_turnover_reversal": "full-fill liquid, small/mid market-cap percentile, amount expansion, and high turnover",
    }


def _interpretation(
    *,
    date_count: int,
    dates_with_archetype_best: int,
    dates_with_nondegrading_archetype: int,
    dates_with_near_floor_archetype: int,
) -> str:
    if date_count <= 0:
        return "No opportunity dates were available; no replay is justified."
    if dates_with_nondegrading_archetype == date_count:
        return (
            "Every blocker date has a non-degrading full-fill candidate covered by broad archetypes. "
            "This can justify a bounded opportunity-generator preflight, but still not promotion."
        )
    if dates_with_archetype_best == date_count and dates_with_near_floor_archetype == date_count:
        return (
            "Broad archetypes can describe the best liquid candidates, but at least one date still lacks a "
            "non-degrading liquid replacement. Do not run full713 solely from this probe."
        )
    return (
        "The existing full-market liquid winners are not consistently covered by broad archetypes or do not "
        "retain the source return floor. A new opportunity-set model needs more source features before replay."
    )


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed
