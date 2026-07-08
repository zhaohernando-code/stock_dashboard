from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.capacity_opportunity_archetype_sample import _is_executable_main_board_stock
from ashare_evidence.capacity_opportunity_set_discovery import (
    DEFAULT_BENCHMARK_SYMBOL,
    DEFAULT_BENCHMARK_SYMBOLS,
    _attach_percentiles,
    _market_histories_for_window,
    _metrics_by_symbol,
)


CAPACITY_LIQUID_WINNER_FEATURE_AUDIT_VERSION = "capacity_liquid_winner_feature_audit.v1"
COMBO_SEARCH_FEATURE_FIELDS = [
    "avg_amount_20d_percentile",
    "amount_10d_vs_20d_percentile",
    "industry_return_5d_excess_percentile",
    "industry_return_20d_excess_percentile",
    "return_5d_percentile",
    "return_20d_percentile",
    "turnover_rate_percentile",
    "volatility_20d_percentile",
    "total_mv_percentile",
    "daily_return_1d_percentile",
    "open_gap_1d_percentile",
    "intraday_return_1d_percentile",
    "close_range_position",
    "upper_shadow_ratio_percentile",
    "distance_to_20d_high_percentile",
    "distance_to_20d_low_percentile",
    "limitup_like_5d_count_percentile",
    "mid_liquidity_score",
    "mega_cap_penalty",
    "pullback_20d_score",
    "low_drawdown_score",
]

SCORE_RECIPES = {
    "pressure_turnover_rebound": {
        "amount_10d_vs_20d_percentile": 1.0,
        "return_5d_percentile": 1.0,
        "turnover_rate_percentile": 1.0,
        "volatility_20d_percentile": 0.25,
        "avg_amount_20d_percentile": -0.25,
    },
    "mid_liquidity_pressure_turn": {
        "amount_10d_vs_20d_percentile": 1.0,
        "return_5d_percentile": 0.8,
        "turnover_rate_percentile": 0.8,
        "mid_liquidity_score": 0.6,
        "mega_cap_penalty": -0.5,
    },
    "pullback_pressure_turn": {
        "amount_10d_vs_20d_percentile": 1.0,
        "return_5d_percentile": 0.8,
        "turnover_rate_percentile": 0.7,
        "pullback_20d_score": 0.7,
        "avg_amount_20d_percentile": -0.15,
    },
    "low_drawdown_turnover_pressure": {
        "amount_10d_vs_20d_percentile": 0.9,
        "return_5d_percentile": 0.7,
        "turnover_rate_percentile": 0.8,
        "low_drawdown_score": 0.8,
        "avg_amount_20d_percentile": -0.2,
    },
    "industry_strength_pressure_turn": {
        "industry_return_5d_excess_percentile": 0.9,
        "industry_return_20d_excess_percentile": 0.7,
        "amount_10d_vs_20d_percentile": 0.8,
        "turnover_rate_percentile": 0.6,
        "avg_amount_20d_percentile": -0.15,
    },
    "industry_pullback_pressure_turn": {
        "industry_return_5d_excess_percentile": 0.8,
        "amount_10d_vs_20d_percentile": 0.8,
        "turnover_rate_percentile": 0.6,
        "pullback_20d_score": 0.6,
        "mega_cap_penalty": -0.3,
    },
    "price_action_breakout_pressure": {
        "daily_return_1d_percentile": 0.7,
        "close_range_position": 0.5,
        "distance_to_20d_high_percentile": 0.8,
        "amount_10d_vs_20d_percentile": 0.7,
        "turnover_rate_percentile": 0.5,
        "upper_shadow_ratio_percentile": -0.4,
    },
    "limitup_followthrough_pressure": {
        "limitup_like_5d_count_percentile": 0.9,
        "daily_return_1d_percentile": 0.6,
        "industry_return_5d_excess_percentile": 0.5,
        "amount_10d_vs_20d_percentile": 0.6,
        "mega_cap_penalty": -0.3,
    },
}


def build_capacity_liquid_winner_feature_audit(
    session: Session,
    *,
    opportunity_discovery_artifact: str | Path,
    fallback_preflight_artifact: str | Path | None = None,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    top_rank_threshold: int = 25,
) -> dict[str, Any]:
    opportunity = json.loads(Path(opportunity_discovery_artifact).read_text(encoding="utf-8"))
    fallback = (
        json.loads(Path(fallback_preflight_artifact).read_text(encoding="utf-8"))
        if fallback_preflight_artifact
        else {}
    )
    fallback_symbols_by_date = _fallback_symbols_by_date(fallback)
    full_fill_avg_amount_20d = _safe_float(opportunity.get("full_fill_avg_amount_20d_required"))

    date_results: list[dict[str, Any]] = []
    for item in opportunity.get("dates") or []:
        as_of_date_text = str(item.get("as_of_date") or "")
        if not as_of_date_text:
            continue
        as_of_date = date.fromisoformat(as_of_date_text)
        histories = _market_histories_for_window(session, as_of_date)
        metrics = _metrics_by_symbol(
            histories,
            as_of_date=as_of_date,
            benchmark_symbol=benchmark_symbol,
        )
        benchmark = metrics.get(benchmark_symbol)
        if not benchmark or benchmark.get("future_return_20d") is None:
            continue
        benchmark_future = _safe_float(benchmark.get("future_return_20d"))
        candidates = [
            row
            for symbol, row in metrics.items()
            if symbol not in DEFAULT_BENCHMARK_SYMBOLS
            and _is_executable_main_board_stock(symbol, row.get("name"))
            and _safe_float(row.get("avg_amount_20d")) >= full_fill_avg_amount_20d
            and row.get("future_return_20d") is not None
        ]
        all_executable_rows = [
            row
            for symbol, row in metrics.items()
            if symbol not in DEFAULT_BENCHMARK_SYMBOLS and _is_executable_main_board_stock(symbol, row.get("name"))
        ]
        _attach_industry_relative_features(all_executable_rows)
        _attach_percentiles(
            candidates,
            fields=[
                "avg_amount_20d",
                "return_5d",
                "return_20d",
                "industry_return_5d_excess",
                "industry_return_20d_excess",
                "amount_10d_vs_20d",
                "volatility_20d",
                "turnover_rate",
                "total_mv",
                "circ_mv",
                "max_drawdown_20d",
                "pe_ttm",
                "pb",
                "daily_return_1d",
                "open_gap_1d",
                "intraday_return_1d",
                "upper_shadow_ratio",
                "distance_to_20d_high",
                "distance_to_20d_low",
                "limitup_like_5d_count",
            ],
        )
        for row in candidates:
            row["future_excess_return_20d"] = _safe_float(row.get("future_return_20d")) - benchmark_future
            _attach_derived_scores(row)
        candidate_by_symbol = {str(row.get("symbol") or ""): row for row in candidates}
        target_symbols = [
            str(row.get("symbol"))
            for row in item.get("top_liquid_by_future_excess") or []
            if row.get("symbol")
        ][:3]
        recipe_results = []
        for recipe_name, weights in SCORE_RECIPES.items():
            scored = [
                {
                    **_compact_candidate(row),
                    "feature_score": _score_candidate(row, weights),
                }
                for row in candidates
            ]
            scored.sort(
                key=lambda row: (_safe_float(row.get("feature_score")), _safe_float(row.get("avg_amount_20d"))),
                reverse=True,
            )
            ranks = {str(row.get("symbol") or ""): index + 1 for index, row in enumerate(scored)}
            target_ranks = [
                {"symbol": symbol, "rank": ranks.get(symbol), "row": _compact_candidate(candidate_by_symbol.get(symbol, {}))}
                for symbol in target_symbols
            ]
            fallback_ranks = [
                {"symbol": symbol, "rank": ranks.get(symbol), "row": _compact_candidate(candidate_by_symbol.get(symbol, {}))}
                for symbol in fallback_symbols_by_date.get(as_of_date_text, [])
            ]
            recipe_results.append(
                {
                    "recipe": recipe_name,
                    "top_ranked": scored[:10],
                    "target_ranks": target_ranks,
                    "fallback_ranks": fallback_ranks,
                    "best_target_rank": min((rank["rank"] for rank in target_ranks if rank["rank"] is not None), default=None),
                    "worst_target_rank": max((rank["rank"] for rank in target_ranks if rank["rank"] is not None), default=None),
                }
            )
        combo_candidates = [
            _compact_candidate(row)
            for row in candidates
        ]
        date_results.append(
            {
                "as_of_date": as_of_date_text,
                "candidate_count": len(candidates),
                "target_symbols": target_symbols,
                "fallback_symbols": fallback_symbols_by_date.get(as_of_date_text, []),
                "recipe_results": recipe_results,
                "combo_search_candidates": combo_candidates,
            }
        )

    recipe_summary = _recipe_summary(date_results, top_rank_threshold=top_rank_threshold)
    combo_search = _target_fitted_combo_search(date_results, top_rank_threshold=top_rank_threshold)
    promising_recipes = [
        row["recipe"]
        for row in recipe_summary
        if row["date_count"] > 0
        and row["dates_with_target_top_rank_within_threshold"] == row["date_count"]
        and row["median_best_target_rank"] is not None
        and row["median_best_target_rank"] <= top_rank_threshold
    ]
    blocking_gate_ids = []
    if not date_results:
        blocking_gate_ids.append("capacity_liquid_winner_feature_audit:no_dates")
    if not promising_recipes:
        blocking_gate_ids.append("capacity_liquid_winner_feature_audit:no_recipe_ranks_targets_consistently")
    return {
        "artifact_type": "capacity_liquid_winner_feature_audit",
        "schema_version": CAPACITY_LIQUID_WINNER_FEATURE_AUDIT_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "claim_ceiling": "blocker_date_feature_audit_only_no_model_replay_no_promotion",
        "source_opportunity_discovery_artifact": str(Path(opportunity_discovery_artifact)),
        "source_fallback_preflight_artifact": str(Path(fallback_preflight_artifact)) if fallback_preflight_artifact else None,
        "top_rank_threshold": top_rank_threshold,
        "score_recipes": SCORE_RECIPES,
        "recipe_summary": recipe_summary,
        "target_fitted_combo_search": combo_search,
        "promising_recipes": promising_recipes,
        "dates": [_strip_combo_search_candidates(row) for row in date_results],
        "interpretation": _interpretation(promising_recipes),
    }


def write_capacity_liquid_winner_feature_audit(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _fallback_symbols_by_date(fallback: dict[str, Any]) -> dict[str, list[str]]:
    by_date: dict[str, list[str]] = {}
    details = (fallback.get("variant_details") or {}).get("fallback_prototype_frontier_excess") or []
    for row in details:
        symbols = [
            str(item.get("symbol"))
            for item in row.get("fallback_rows") or []
            if item.get("symbol")
        ]
        if row.get("as_of_date"):
            by_date[str(row["as_of_date"])] = symbols
    return by_date


def _attach_derived_scores(row: dict[str, Any]) -> None:
    avg_amount_pct = _safe_float(row.get("avg_amount_20d_percentile"))
    total_mv_pct = _safe_float(row.get("total_mv_percentile"))
    return_20d_pct = _safe_float(row.get("return_20d_percentile"))
    drawdown_pct = _safe_float(row.get("max_drawdown_20d_percentile"))
    row["mid_liquidity_score"] = 1.0 - min(abs(avg_amount_pct - 0.45) / 0.45, 1.0)
    row["mega_cap_penalty"] = max(total_mv_pct - 0.75, 0.0)
    row["pullback_20d_score"] = 1.0 - return_20d_pct
    row["low_drawdown_score"] = drawdown_pct


def _score_candidate(row: dict[str, Any], weights: dict[str, float]) -> float:
    return sum(_safe_float(row.get(field)) * weight for field, weight in weights.items())


def _recipe_summary(date_results: list[dict[str, Any]], *, top_rank_threshold: int) -> list[dict[str, Any]]:
    summaries = []
    for recipe_name in SCORE_RECIPES:
        best_ranks = []
        fallback_best_ranks = []
        result_date_count = 0
        for date_row in date_results:
            result = next((row for row in date_row["recipe_results"] if row["recipe"] == recipe_name), None)
            if result is None:
                continue
            result_date_count += 1
            if result["best_target_rank"] is not None:
                best_ranks.append(int(result["best_target_rank"]))
            fallback_ranks = [
                int(row["rank"]) for row in result.get("fallback_ranks") or [] if row.get("rank") is not None
            ]
            if fallback_ranks:
                fallback_best_ranks.append(min(fallback_ranks))
        summaries.append(
            {
                "recipe": recipe_name,
                "date_count": result_date_count,
                "dates_with_target_top_rank_within_threshold": sum(
                    1 for rank in best_ranks if rank <= top_rank_threshold
                ),
                "best_target_ranks": best_ranks,
                "median_best_target_rank": _median(best_ranks),
                "fallback_best_ranks": fallback_best_ranks,
                "median_fallback_best_rank": _median(fallback_best_ranks),
            }
        )
    return summaries


def _target_fitted_combo_search(
    date_results: list[dict[str, Any]],
    *,
    top_rank_threshold: int,
    max_terms: int = 5,
) -> dict[str, Any]:
    """Find whether existing fields can target-fit the known blocker-date liquid winners.

    This intentionally optimizes on the blocker dates and is therefore diagnostic only. A passing combo
    must still go through a sampled walk-forward preflight before any model replay.
    """

    selected_terms: list[dict[str, Any]] = []
    best_evaluation = _evaluate_combo_terms(date_results, selected_terms, top_rank_threshold=top_rank_threshold)
    available_terms = [
        {"field": field, "weight": weight}
        for field in COMBO_SEARCH_FEATURE_FIELDS
        for weight in (1.0, -1.0)
    ]
    for _ in range(max_terms):
        candidates = [
            term for term in available_terms if term not in selected_terms and _opposite_term(term) not in selected_terms
        ]
        next_best: tuple[tuple[float, ...], dict[str, Any], dict[str, Any]] | None = None
        for term in candidates:
            evaluation = _evaluate_combo_terms(
                date_results,
                [*selected_terms, term],
                top_rank_threshold=top_rank_threshold,
            )
            key = _combo_objective_key(evaluation)
            if next_best is None or key < next_best[0]:
                next_best = (key, term, evaluation)
        if next_best is None or next_best[0] >= _combo_objective_key(best_evaluation):
            break
        selected_terms.append(next_best[1])
        best_evaluation = next_best[2]

    return {
        "claim_ceiling": "target_fitted_existing_feature_combo_diagnostic_only_no_model_replay_no_promotion",
        "feature_pool": COMBO_SEARCH_FEATURE_FIELDS,
        "max_terms": max_terms,
        "selected_terms": selected_terms,
        **best_evaluation,
    }


def _evaluate_combo_terms(
    date_results: list[dict[str, Any]],
    terms: list[dict[str, Any]],
    *,
    top_rank_threshold: int,
) -> dict[str, Any]:
    date_rank_results = []
    best_ranks = []
    fallback_best_ranks = []
    for date_row in date_results:
        candidates = [
            {**row, "feature_score": _score_candidate(row, {term["field"]: term["weight"] for term in terms})}
            for row in date_row.get("combo_search_candidates") or []
        ]
        candidates.sort(
            key=lambda row: (_safe_float(row.get("feature_score")), _safe_float(row.get("avg_amount_20d"))),
            reverse=True,
        )
        ranks = {str(row.get("symbol") or ""): index + 1 for index, row in enumerate(candidates)}
        target_ranks = [
            {"symbol": symbol, "rank": ranks.get(symbol)}
            for symbol in date_row.get("target_symbols") or []
        ]
        fallback_ranks = [
            {"symbol": symbol, "rank": ranks.get(symbol)}
            for symbol in date_row.get("fallback_symbols") or []
        ]
        best_target_rank = min((row["rank"] for row in target_ranks if row["rank"] is not None), default=None)
        best_fallback_rank = min((row["rank"] for row in fallback_ranks if row["rank"] is not None), default=None)
        if best_target_rank is not None:
            best_ranks.append(int(best_target_rank))
        if best_fallback_rank is not None:
            fallback_best_ranks.append(int(best_fallback_rank))
        date_rank_results.append(
            {
                "as_of_date": date_row.get("as_of_date"),
                "best_target_rank": best_target_rank,
                "target_ranks": target_ranks,
                "best_fallback_rank": best_fallback_rank,
                "fallback_ranks": fallback_ranks,
                "top_ranked": [
                    {
                        "symbol": row.get("symbol"),
                        "name": row.get("name"),
                        "feature_score": row.get("feature_score"),
                        "future_excess_return_20d": row.get("future_excess_return_20d"),
                    }
                    for row in candidates[:10]
                ],
            }
        )
    dates_within_threshold = sum(1 for rank in best_ranks if rank <= top_rank_threshold)
    return {
        "gate_status": "passed" if date_rank_results and dates_within_threshold == len(date_rank_results) else "blocked",
        "blocking_gate_ids": []
        if date_rank_results and dates_within_threshold == len(date_rank_results)
        else ["capacity_liquid_winner_feature_audit:target_fitted_combo_not_consistent"],
        "date_count": len(date_rank_results),
        "dates_with_target_top_rank_within_threshold": dates_within_threshold,
        "best_target_ranks": best_ranks,
        "median_best_target_rank": _median(best_ranks),
        "max_best_target_rank": max(best_ranks) if best_ranks else None,
        "fallback_best_ranks": fallback_best_ranks,
        "median_fallback_best_rank": _median(fallback_best_ranks),
        "date_results": date_rank_results,
    }


def _combo_objective_key(evaluation: dict[str, Any]) -> tuple[float, ...]:
    date_count = int(evaluation.get("date_count") or 0)
    within = int(evaluation.get("dates_with_target_top_rank_within_threshold") or 0)
    ranks = [int(rank) for rank in evaluation.get("best_target_ranks") or []]
    fallback_ranks = [int(rank) for rank in evaluation.get("fallback_best_ranks") or []]
    missing_dates = max(date_count - within, 0)
    worst_rank = max(ranks) if ranks else 999999
    median_rank = _median(ranks) or 999999.0
    rank_sum = sum(ranks) if ranks else 999999
    fallback_median = _median(fallback_ranks) or 0.0
    return (missing_dates, worst_rank, median_rank, rank_sum, -fallback_median)


def _opposite_term(term: dict[str, Any]) -> dict[str, Any]:
    return {"field": term["field"], "weight": -float(term["weight"])}


def _strip_combo_search_candidates(date_row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in date_row.items() if key != "combo_search_candidates"}


def _compact_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "future_excess_return_20d": _safe_float(row.get("future_excess_return_20d")),
        "avg_amount_20d": _safe_float(row.get("avg_amount_20d")),
        "industry_name": row.get("industry_name"),
        "avg_amount_20d_percentile": _safe_float(row.get("avg_amount_20d_percentile")),
        "amount_10d_vs_20d_percentile": _safe_float(row.get("amount_10d_vs_20d_percentile")),
        "industry_return_5d_excess": _safe_float(row.get("industry_return_5d_excess")),
        "industry_return_5d_excess_percentile": _safe_float(row.get("industry_return_5d_excess_percentile")),
        "industry_return_20d_excess": _safe_float(row.get("industry_return_20d_excess")),
        "industry_return_20d_excess_percentile": _safe_float(row.get("industry_return_20d_excess_percentile")),
        "return_5d_percentile": _safe_float(row.get("return_5d_percentile")),
        "return_20d_percentile": _safe_float(row.get("return_20d_percentile")),
        "turnover_rate_percentile": _safe_float(row.get("turnover_rate_percentile")),
        "volatility_20d_percentile": _safe_float(row.get("volatility_20d_percentile")),
        "total_mv_percentile": _safe_float(row.get("total_mv_percentile")),
        "daily_return_1d": _safe_float(row.get("daily_return_1d")),
        "daily_return_1d_percentile": _safe_float(row.get("daily_return_1d_percentile")),
        "open_gap_1d": _safe_float(row.get("open_gap_1d")),
        "open_gap_1d_percentile": _safe_float(row.get("open_gap_1d_percentile")),
        "intraday_return_1d": _safe_float(row.get("intraday_return_1d")),
        "intraday_return_1d_percentile": _safe_float(row.get("intraday_return_1d_percentile")),
        "close_range_position": _safe_float(row.get("close_range_position")),
        "upper_shadow_ratio": _safe_float(row.get("upper_shadow_ratio")),
        "upper_shadow_ratio_percentile": _safe_float(row.get("upper_shadow_ratio_percentile")),
        "distance_to_20d_high": _safe_float(row.get("distance_to_20d_high")),
        "distance_to_20d_high_percentile": _safe_float(row.get("distance_to_20d_high_percentile")),
        "distance_to_20d_low": _safe_float(row.get("distance_to_20d_low")),
        "distance_to_20d_low_percentile": _safe_float(row.get("distance_to_20d_low_percentile")),
        "limitup_like_5d_count": _safe_float(row.get("limitup_like_5d_count")),
        "limitup_like_5d_count_percentile": _safe_float(row.get("limitup_like_5d_count_percentile")),
        "mid_liquidity_score": _safe_float(row.get("mid_liquidity_score")),
        "mega_cap_penalty": _safe_float(row.get("mega_cap_penalty")),
        "pullback_20d_score": _safe_float(row.get("pullback_20d_score")),
        "low_drawdown_score": _safe_float(row.get("low_drawdown_score")),
    }


def _attach_industry_relative_features(rows: list[dict[str, Any]]) -> None:
    grouped_5d: dict[str, list[float]] = {}
    grouped_20d: dict[str, list[float]] = {}
    for row in rows:
        industry = str(row.get("industry_name") or "unknown")
        grouped_5d.setdefault(industry, []).append(_safe_float(row.get("return_5d")))
        grouped_20d.setdefault(industry, []).append(_safe_float(row.get("return_20d")))
    median_5d = {industry: _median_float(values) for industry, values in grouped_5d.items()}
    median_20d = {industry: _median_float(values) for industry, values in grouped_20d.items()}
    for row in rows:
        industry = str(row.get("industry_name") or "unknown")
        row["industry_return_5d_excess"] = _safe_float(row.get("return_5d")) - median_5d.get(industry, 0.0)
        row["industry_return_20d_excess"] = _safe_float(row.get("return_20d")) - median_20d.get(industry, 0.0)


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _median_float(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _interpretation(promising_recipes: list[str]) -> str:
    if promising_recipes:
        return (
            "At least one PIT-safe feature recipe ranks blocker-date liquid winners consistently near the top. "
            "This justifies a bounded fallback preflight using that recipe, not promotion."
        )
    return (
        "No existing PIT-safe feature recipe ranks blocker-date liquid winners consistently enough. "
        "This points to missing features or a need to keep the lower-capital contract."
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed
