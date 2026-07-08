from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
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


CAPACITY_OPPORTUNITY_LEARNED_SAMPLE_VERSION = "capacity_opportunity_learned_sample.v2"

FEATURE_NAMES = (
    "avg_amount_20d_log",
    "avg_amount_20d_percentile",
    "amount_10d_vs_20d_percentile",
    "return_5d_percentile",
    "return_20d_percentile",
    "turnover_rate_percentile",
    "volatility_20d_percentile",
    "total_mv_percentile",
)

VARIANT_OBJECTIVES = {
    "learned_return_linear_topk": "return",
    "learned_positive_return_topk": "positive_return",
    "learned_tail_spread_topk": "tail_spread",
    "learned_frontier_excess_topk": "frontier_excess",
    "learned_frontier_positive_excess_topk": "frontier_positive_excess",
    "learned_frontier_floor_stability_topk": "frontier_floor_stability",
    "prototype_return_topk": "prototype_return",
    "prototype_frontier_excess_topk": "prototype_frontier_excess",
    "prototype_frontier_floor_stability_topk": "prototype_frontier_floor_stability",
}


def build_capacity_opportunity_learned_sample_preflight(
    session: Session,
    *,
    candidate_run: dict[str, Any],
    trial_id: str,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    sample_date_count: int = 18,
    min_train_dates: int = 6,
    top_k: int = 3,
    portfolio_notional_cny: float = 1_000_000.0,
    slot_capital_weight: float = 0.91,
    max_adv_participation_rate: float = 0.05,
) -> dict[str, Any]:
    """Run a bounded walk-forward learned opportunity-set sample.

    The model trains only on prior sampled dates and uses full-fill main-board candidates. This is a
    low-cost preflight: it is not a full713 replay and it has no promotion authority.
    """

    trial = _trial_by_id(candidate_run, trial_id)
    baseline_returns = list(trial.get("selected_top_k_returns_by_date") or [])
    sampled_dates = _sample_dates([str(row.get("as_of_date")) for row in baseline_returns], sample_date_count)
    baseline_by_date = {str(row.get("as_of_date")): _safe_float(row.get("mean_net_excess_return")) for row in baseline_returns}
    full_fill_avg_amount_20d = (
        portfolio_notional_cny * slot_capital_weight / max(max_adv_participation_rate, 0.000001)
    )

    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    skipped_dates: list[dict[str, str]] = []
    for as_of_date_text in sampled_dates:
        rows = _candidate_rows_for_date(
            session,
            as_of_date=date.fromisoformat(as_of_date_text),
            benchmark_symbol=benchmark_symbol,
            full_fill_avg_amount_20d=full_fill_avg_amount_20d,
        )
        if rows:
            for row in rows:
                row["frontier_baseline_return"] = baseline_by_date.get(as_of_date_text, 0.0)
            rows_by_date[as_of_date_text] = rows
        else:
            skipped_dates.append({"as_of_date": as_of_date_text, "reason": "no_candidate_rows"})

    evaluated_dates: list[str] = []
    variants = {variant_name: [] for variant_name in VARIANT_OBJECTIVES}
    baseline_eval_returns: list[tuple[str, float]] = []
    selected_samples: dict[str, list[dict[str, Any]]] = {name: [] for name in variants}

    available_dates = [as_of_date for as_of_date in sampled_dates if as_of_date in rows_by_date]
    for index, as_of_date_text in enumerate(available_dates):
        train_dates = available_dates[:index]
        if len(train_dates) < min_train_dates:
            continue
        train_rows = [row for train_date in train_dates for row in rows_by_date[train_date]]
        test_rows = rows_by_date[as_of_date_text]
        evaluated_dates.append(as_of_date_text)
        baseline_eval_returns.append((as_of_date_text, baseline_by_date.get(as_of_date_text, 0.0)))
        for variant_name, objective in VARIANT_OBJECTIVES.items():
            model_profile = _fit_model_profile(train_rows, objective=objective)
            scored = [
                {
                    **_compact_candidate(row),
                    "model_score": _score_row(row, model_profile=model_profile),
                }
                for row in test_rows
            ]
            scored.sort(key=lambda row: (_safe_float(row.get("model_score")), _safe_float(row.get("avg_amount_20d"))), reverse=True)
            selected = scored[: max(top_k, 1)]
            variant_return = mean(_safe_float(row.get("future_excess_return_20d")) for row in selected) if selected else 0.0
            variants[variant_name].append((as_of_date_text, variant_return))
            selected_samples[variant_name].append(
                {
                    "as_of_date": as_of_date_text,
                    "mean_future_excess_return": variant_return,
                    "selected_top_k": selected,
                    "train_date_count": len(train_dates),
                    "train_row_count": len(train_rows),
                    "model_profile": _compact_model_profile(model_profile),
                }
            )

    baseline_stats = _curve_stats(baseline_eval_returns)
    variant_stats = {name: _curve_stats(values) for name, values in variants.items()}
    promising_variants = [
        name
        for name, stats in variant_stats.items()
        if stats["period_count"] > 0
        and stats["mean"] >= baseline_stats["mean"]
        and stats["negative_month_count"] <= baseline_stats["negative_month_count"]
        and stats["path_drawdown_sum"] >= baseline_stats["path_drawdown_sum"]
    ]
    blocking_gate_ids: list[str] = []
    if not evaluated_dates:
        blocking_gate_ids.append("capacity_opportunity_learned_sample:no_evaluated_dates")
    if skipped_dates:
        blocking_gate_ids.append("capacity_opportunity_learned_sample:skipped_sample_dates")
    if not promising_variants:
        blocking_gate_ids.append("capacity_opportunity_learned_sample:no_variant_beats_frontier_sample")

    return {
        "artifact_type": "capacity_opportunity_learned_sample",
        "schema_version": CAPACITY_OPPORTUNITY_LEARNED_SAMPLE_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": sorted(set(blocking_gate_ids)),
        "claim_ceiling": "sampled_walk_forward_learned_opportunity_preflight_only_no_model_replay_no_promotion",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "trial_id": trial_id,
        "benchmark_symbol": benchmark_symbol,
        "account_filter": "main_board_prefix_000_001_002_003_600_601_603_605_excluding_st_and_delisting_names",
        "sample_date_count_requested": sample_date_count,
        "sample_date_count_loaded": len(available_dates),
        "evaluated_date_count": len(evaluated_dates),
        "min_train_dates": min_train_dates,
        "top_k": top_k,
        "full_fill_avg_amount_20d_required": full_fill_avg_amount_20d,
        "baseline_frontier_sample_stats": baseline_stats,
        "variant_objectives": VARIANT_OBJECTIVES,
        "variant_stats": variant_stats,
        "promising_variants": promising_variants,
        "skipped_dates": skipped_dates,
        "selected_samples": selected_samples,
        "interpretation": _interpretation(promising_variants, baseline_stats, variant_stats),
    }


def write_capacity_opportunity_learned_sample_preflight(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _candidate_rows_for_date(
    session: Session,
    *,
    as_of_date: date,
    benchmark_symbol: str,
    full_fill_avg_amount_20d: float,
) -> list[dict[str, Any]]:
    histories = _market_histories_for_window(session, as_of_date)
    metrics = _metrics_by_symbol(histories, as_of_date=as_of_date, benchmark_symbol=benchmark_symbol)
    benchmark = metrics.get(benchmark_symbol)
    if not benchmark or benchmark.get("future_return_20d") is None:
        return []
    benchmark_future = _safe_float(benchmark.get("future_return_20d"))
    candidates = [
        row
        for symbol, row in metrics.items()
        if symbol not in DEFAULT_BENCHMARK_SYMBOLS
        and _is_executable_main_board_stock(symbol, row.get("name"))
        and _safe_float(row.get("avg_amount_20d")) >= full_fill_avg_amount_20d
        and row.get("future_return_20d") is not None
    ]
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
    for row in candidates:
        row["future_excess_return_20d"] = _safe_float(row.get("future_return_20d")) - benchmark_future
        row["avg_amount_20d_log"] = math.log1p(max(_safe_float(row.get("avg_amount_20d")), 0.0))
    return candidates


def _fit_model_profile(rows: list[dict[str, Any]], *, objective: str) -> dict[str, Any]:
    if objective.startswith("prototype_"):
        return _fit_feature_prototype(rows, objective=objective.removeprefix("prototype_"))
    weights, stats = _fit_feature_correlations(rows, objective=objective)
    return {
        "model_type": "feature_correlation_linear",
        "objective": objective,
        "feature_weights": weights,
        "feature_stats": stats,
    }


def _fit_feature_correlations(rows: list[dict[str, Any]], *, objective: str) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    targets = [_target_value(row, objective=objective) for row in rows]
    weights: dict[str, float] = {}
    stats: dict[str, tuple[float, float]] = {}
    for feature_name in FEATURE_NAMES:
        values = [_safe_float(row.get(feature_name)) for row in rows]
        mean_value = sum(values) / len(values) if values else 0.0
        std_value = (sum((value - mean_value) ** 2 for value in values) / len(values)) ** 0.5 if values else 0.0
        stats[feature_name] = (mean_value, std_value)
        weights[feature_name] = _correlation(values, targets)
    return weights, stats


def _fit_feature_prototype(rows: list[dict[str, Any]], *, objective: str) -> dict[str, Any]:
    targets = [_target_value(row, objective=objective) for row in rows]
    stats = _feature_stats(rows)
    row_vectors = [_standardized_vector(row, stats=stats) for row in rows]
    indexed = sorted(enumerate(targets), key=lambda item: item[1])
    if not indexed:
        return {
            "model_type": "feature_prototype",
            "objective": objective,
            "feature_stats": stats,
            "good_centroid": {feature_name: 0.0 for feature_name in FEATURE_NAMES},
            "bad_centroid": {feature_name: 0.0 for feature_name in FEATURE_NAMES},
            "good_row_count": 0,
            "bad_row_count": 0,
        }
    min_bucket_size = min(max(20, len(indexed) // 20), len(indexed))
    positive_indices = [index for index, target in indexed if target > 0]
    good_indices = positive_indices[-min_bucket_size:] if len(positive_indices) >= min_bucket_size else [
        index for index, _ in indexed[-min_bucket_size:]
    ]
    negative_indices = [index for index, target in indexed if target <= 0]
    bad_indices = negative_indices[:min_bucket_size] if len(negative_indices) >= min_bucket_size else [
        index for index, _ in indexed[:min_bucket_size]
    ]
    return {
        "model_type": "feature_prototype",
        "objective": objective,
        "feature_stats": stats,
        "good_centroid": _centroid([row_vectors[index] for index in good_indices]),
        "bad_centroid": _centroid([row_vectors[index] for index in bad_indices]),
        "good_row_count": len(good_indices),
        "bad_row_count": len(bad_indices),
        "good_target_mean": mean(targets[index] for index in good_indices) if good_indices else 0.0,
        "bad_target_mean": mean(targets[index] for index in bad_indices) if bad_indices else 0.0,
    }


def _target_value(row: dict[str, Any], *, objective: str) -> float:
    value = _safe_float(row.get("future_excess_return_20d"))
    frontier_floor = _safe_float(row.get("frontier_baseline_return"))
    if objective == "positive_return":
        return max(value, 0.0)
    if objective == "tail_spread":
        if value >= 0.20:
            return value
        if value <= -0.10:
            return value
        return 0.0
    if objective == "frontier_excess":
        return value - frontier_floor
    if objective == "frontier_positive_excess":
        return max(value - frontier_floor, 0.0)
    if objective == "frontier_floor_stability":
        relative_excess = value - frontier_floor
        if value > 0 and relative_excess > 0:
            return relative_excess
        return min(relative_excess, 0.0) - max(-value, 0.0)
    return value


def _score_row(row: dict[str, Any], *, model_profile: dict[str, Any]) -> float:
    if model_profile.get("model_type") == "feature_prototype":
        vector = _standardized_vector(row, stats=model_profile.get("feature_stats") or {})
        return _squared_distance(vector, model_profile.get("bad_centroid") or {}) - _squared_distance(
            vector,
            model_profile.get("good_centroid") or {},
        )
    weights = model_profile.get("feature_weights") or {}
    stats = model_profile.get("feature_stats") or {}
    score = 0.0
    for feature_name, weight in weights.items():
        mean_value, std_value = stats[feature_name]
        if std_value <= 0:
            continue
        score += weight * ((_safe_float(row.get(feature_name)) - mean_value) / std_value)
    return score


def _feature_stats(rows: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for feature_name in FEATURE_NAMES:
        values = [_safe_float(row.get(feature_name)) for row in rows]
        mean_value = sum(values) / len(values) if values else 0.0
        std_value = (sum((value - mean_value) ** 2 for value in values) / len(values)) ** 0.5 if values else 0.0
        stats[feature_name] = (mean_value, std_value)
    return stats


def _standardized_vector(row: dict[str, Any], *, stats: dict[str, tuple[float, float]]) -> dict[str, float]:
    vector: dict[str, float] = {}
    for feature_name in FEATURE_NAMES:
        mean_value, std_value = stats.get(feature_name, (0.0, 0.0))
        vector[feature_name] = (
            (_safe_float(row.get(feature_name)) - mean_value) / std_value if std_value > 0 else 0.0
        )
    return vector


def _centroid(vectors: list[dict[str, float]]) -> dict[str, float]:
    return {
        feature_name: mean(vector.get(feature_name, 0.0) for vector in vectors) if vectors else 0.0
        for feature_name in FEATURE_NAMES
    }


def _squared_distance(left: dict[str, float], right: dict[str, float]) -> float:
    return sum((left.get(feature_name, 0.0) - right.get(feature_name, 0.0)) ** 2 for feature_name in FEATURE_NAMES)


def _compact_model_profile(model_profile: dict[str, Any]) -> dict[str, Any]:
    if model_profile.get("model_type") == "feature_prototype":
        return {
            "model_type": "feature_prototype",
            "objective": model_profile.get("objective"),
            "good_row_count": model_profile.get("good_row_count"),
            "bad_row_count": model_profile.get("bad_row_count"),
            "good_target_mean": model_profile.get("good_target_mean"),
            "bad_target_mean": model_profile.get("bad_target_mean"),
            "good_centroid": model_profile.get("good_centroid"),
            "bad_centroid": model_profile.get("bad_centroid"),
        }
    return {
        "model_type": model_profile.get("model_type"),
        "objective": model_profile.get("objective"),
        "feature_weights": model_profile.get("feature_weights"),
    }


def _compact_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "future_excess_return_20d": _safe_float(row.get("future_excess_return_20d")),
        "frontier_baseline_return": _safe_float(row.get("frontier_baseline_return")),
        "avg_amount_20d": _safe_float(row.get("avg_amount_20d")),
        "amount_10d_vs_20d_percentile": _safe_float(row.get("amount_10d_vs_20d_percentile")),
        "return_5d_percentile": _safe_float(row.get("return_5d_percentile")),
        "return_20d_percentile": _safe_float(row.get("return_20d_percentile")),
        "turnover_rate_percentile": _safe_float(row.get("turnover_rate_percentile")),
        "volatility_20d_percentile": _safe_float(row.get("volatility_20d_percentile")),
        "total_mv_percentile": _safe_float(row.get("total_mv_percentile")),
    }


def _trial_by_id(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    for trial in candidate_run.get("trial_diagnostics") or []:
        if trial.get("trial_id") == trial_id:
            return trial
    raise ValueError(f"trial_id not found in candidate run: {trial_id}")


def _sample_dates(date_values: list[str], sample_date_count: int) -> list[str]:
    dates = sorted({value for value in date_values if value})
    if len(dates) <= max(sample_date_count, 0):
        return dates
    if sample_date_count <= 1:
        return [dates[len(dates) // 2]]
    indices = [round(index * (len(dates) - 1) / (sample_date_count - 1)) for index in range(sample_date_count)]
    return [dates[index] for index in sorted(set(indices))]


def _curve_stats(returns_by_date: list[tuple[str, float]]) -> dict[str, Any]:
    values = [value for _, value in returns_by_date]
    by_month: dict[str, list[float]] = defaultdict(list)
    for as_of_date, value in returns_by_date:
        by_month[str(as_of_date)[:7]].append(value)
    monthly = {month: sum(month_values) / len(month_values) for month, month_values in by_month.items()}
    negative_months = [month for month, value in sorted(monthly.items()) if value <= 0]
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
    return {
        "period_count": len(values),
        "mean": sum(values) / len(values) if values else 0.0,
        "positive_date_rate": sum(1 for value in values if value > 0) / len(values) if values else 0.0,
        "negative_month_count": len(negative_months),
        "negative_months": negative_months,
        "worst_monthly_mean": min(monthly.values()) if monthly else None,
        "path_drawdown_sum": max_drawdown,
        "sum_return_proxy": sum(values),
    }


def _interpretation(
    promising_variants: list[str],
    baseline_stats: dict[str, Any],
    variant_stats: dict[str, dict[str, Any]],
) -> str:
    if promising_variants:
        return (
            "At least one sampled learned opportunity variant beats the frontier sample on mean, negative months, "
            "and path. This justifies a larger preflight, not promotion."
        )
    best_name = max(variant_stats, key=lambda name: _safe_float(variant_stats[name].get("mean"))) if variant_stats else ""
    best_mean = variant_stats.get(best_name, {}).get("mean")
    return (
        f"No sampled learned opportunity variant beats the frontier sample. Best mean variant `{best_name}` has "
        f"mean `{best_mean}` versus frontier `{baseline_stats.get('mean')}`; do not run full713 from this preflight."
    )


def _correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    count = float(len(xs))
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    var_x = sum((value - mean_x) ** 2 for value in xs) / count
    var_y = sum((value - mean_y) ** 2 for value in ys) / count
    if var_x <= 0 or var_y <= 0:
        return 0.0
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / count
    return max(min(covariance / ((var_x**0.5) * (var_y**0.5)), 1.0), -1.0)


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
