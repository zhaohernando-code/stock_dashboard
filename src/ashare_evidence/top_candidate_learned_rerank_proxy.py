from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


TOP_CANDIDATE_LEARNED_RERANK_PROXY_VERSION = "top_candidate_learned_rerank_proxy.v1"

DEFAULT_FEATURE_NAMES = (
    "score",
    "return_5d_percentile",
    "return_20d_percentile",
    "amount_10d_vs_20d_percentile",
    "turnover_rate_percentile",
    "avg_amount_20d",
    "low_volatility_percentile",
    "max_drawdown_20d",
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


def _feature_value(row: dict[str, Any], feature_name: str) -> float:
    raw_value = row.get(feature_name)
    if raw_value is None:
        raw_value = (row.get("rank_weight_feature_values") or {}).get(feature_name)
    if feature_name == "avg_amount_20d":
        return math.log1p(max(_safe_float(raw_value), 0.0))
    return _safe_float(raw_value)


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
    return covariance / ((var_x**0.5) * (var_y**0.5))


def _train_linear_reranker(
    rows: list[dict[str, Any]],
    *,
    feature_names: tuple[str, ...],
) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    targets = [_safe_float(row.get("net_excess_return")) for row in rows]
    weights: dict[str, float] = {}
    stats: dict[str, tuple[float, float]] = {}
    for feature_name in feature_names:
        xs = [_feature_value(row, feature_name) for row in rows]
        mean_value = sum(xs) / len(xs) if xs else 0.0
        std_value = (sum((value - mean_value) ** 2 for value in xs) / len(xs)) ** 0.5 if xs else 0.0
        weights[feature_name] = max(min(_correlation(xs, targets) / 2.0, 1.0), -1.0)
        stats[feature_name] = (mean_value, std_value)
    if "score" in weights:
        weights["score"] = max(weights["score"], 0.15)
    if "low_volatility_percentile" in weights:
        weights["low_volatility_percentile"] = min(weights["low_volatility_percentile"], 0.0)
    return weights, stats


def _rerank_score(
    row: dict[str, Any],
    *,
    weights: dict[str, float],
    stats: dict[str, tuple[float, float]],
) -> float:
    score = 0.0
    for feature_name, weight in weights.items():
        mean_value, std_value = stats[feature_name]
        if std_value <= 0:
            continue
        score += weight * ((_feature_value(row, feature_name) - mean_value) / std_value)
    return score


def _weighted_return(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    total_weight = sum(_safe_float(row.get("portfolio_weight"), 1.0) for row in rows)
    if total_weight <= 0:
        return 0.0
    return (
        sum(_safe_float(row.get("net_excess_return")) * _safe_float(row.get("portfolio_weight"), 1.0) for row in rows)
        / total_weight
    )


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


def build_top_candidate_learned_fillable_rerank_proxy(
    top_candidate_inventory: dict[str, Any],
    *,
    min_train_dates: int = 60,
    top_k: int = 3,
    fillable_avg_amount_20d_threshold: float = 18_200_000.0,
    feature_names: tuple[str, ...] = DEFAULT_FEATURE_NAMES,
) -> dict[str, Any]:
    rows = list(top_candidate_inventory.get("candidate_rows") or [])
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        as_of_date = str(row.get("as_of_date") or "")
        if as_of_date:
            by_date[as_of_date].append(row)
    dates = sorted(by_date)
    baseline: list[tuple[str, float]] = []
    fillable: list[tuple[str, float]] = []
    learned_all: list[tuple[str, float]] = []
    learned_fillable: list[tuple[str, float]] = []
    selected_weight_samples: list[dict[str, Any]] = []
    for date_index, as_of_date in enumerate(dates):
        ranked_rows = sorted(by_date[as_of_date], key=lambda row: int(_safe_float(row.get("rank"), 999999.0)))
        if date_index < min_train_dates:
            continue
        train_rows = [row for train_date in dates[:date_index] for row in by_date[train_date]]
        weights, stats = _train_linear_reranker(train_rows, feature_names=feature_names)
        fillable_rows = [
            row for row in ranked_rows if _safe_float(row.get("avg_amount_20d")) >= fillable_avg_amount_20d_threshold
        ]
        learned_all_rows = sorted(ranked_rows, key=lambda row: _rerank_score(row, weights=weights, stats=stats), reverse=True)
        learned_fillable_rows = sorted(
            fillable_rows,
            key=lambda row: _rerank_score(row, weights=weights, stats=stats),
            reverse=True,
        )
        baseline.append((as_of_date, _weighted_return(ranked_rows[:top_k])))
        fillable.append((as_of_date, _weighted_return(fillable_rows[:top_k])))
        learned_all.append((as_of_date, _weighted_return(learned_all_rows[:top_k])))
        learned_fillable.append((as_of_date, _weighted_return(learned_fillable_rows[:top_k])))
        if len(selected_weight_samples) < 5:
            selected_weight_samples.append(
                {
                    "as_of_date": as_of_date,
                    "weights": {feature_name: round(weight, 6) for feature_name, weight in weights.items()},
                    "baseline_symbols": [str(row.get("symbol") or "") for row in ranked_rows[:top_k]],
                    "learned_fillable_symbols": [str(row.get("symbol") or "") for row in learned_fillable_rows[:top_k]],
                }
            )
    baseline_stats = _curve_stats(baseline)
    learned_fillable_stats = _curve_stats(learned_fillable)
    blocking_gate_ids: list[str] = []
    if learned_fillable_stats["mean"] < baseline_stats["mean"]:
        blocking_gate_ids.append("learned_fillable_mean_below_baseline")
    if learned_fillable_stats["negative_month_count"] > baseline_stats["negative_month_count"]:
        blocking_gate_ids.append("learned_fillable_negative_month_count_above_baseline")
    if _safe_float(learned_fillable_stats["path_drawdown_sum"]) < _safe_float(baseline_stats["path_drawdown_sum"]):
        blocking_gate_ids.append("learned_fillable_path_drawdown_worse_than_baseline")
    return {
        "artifact_type": "top_candidate_learned_fillable_rerank_proxy",
        "schema_version": TOP_CANDIDATE_LEARNED_RERANK_PROXY_VERSION,
        "claim_ceiling": "retained_top_candidate_inventory_proxy_only_no_model_replay_no_promotion",
        "source_inventory_id": top_candidate_inventory.get("artifact_id"),
        "source_trial_id": top_candidate_inventory.get("trial_id"),
        "date_count": len(dates),
        "evaluated_date_count": len(baseline),
        "candidate_row_count": len(rows),
        "feature_names": list(feature_names),
        "min_train_dates": min_train_dates,
        "top_k": top_k,
        "fillable_avg_amount_20d_threshold": fillable_avg_amount_20d_threshold,
        "variants": {
            "baseline_topk_original_rank": baseline_stats,
            "original_rank_topk_fillable_only": _curve_stats(fillable),
            "learned_topk_all_candidates": _curve_stats(learned_all),
            "learned_topk_fillable_only": learned_fillable_stats,
        },
        "weight_samples": selected_weight_samples,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "interpretation": (
            "Diagnostic only. A learned reranker over a retained TopN inventory must improve the original-rank "
            "baseline on mean, negative months and path drawdown before a full replay is justified."
        ),
    }


def write_top_candidate_learned_fillable_rerank_proxy(payload: dict[str, Any], output_json: str | Path) -> Path:
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
