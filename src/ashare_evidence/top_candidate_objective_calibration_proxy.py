from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


TOP_CANDIDATE_OBJECTIVE_CALIBRATION_PROXY_VERSION = "top_candidate_objective_calibration_proxy.v1"

DEFAULT_OBJECTIVE_FEATURE_NAMES = (
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


def _train_standardized_linear(
    rows: list[dict[str, Any]],
    *,
    feature_names: tuple[str, ...],
    targets: list[float],
) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    weights: dict[str, float] = {}
    stats: dict[str, tuple[float, float]] = {}
    for feature_name in feature_names:
        xs = [_feature_value(row, feature_name) for row in rows]
        mean_value = sum(xs) / len(xs) if xs else 0.0
        std_value = (sum((value - mean_value) ** 2 for value in xs) / len(xs)) ** 0.5 if xs else 0.0
        weights[feature_name] = max(min(_correlation(xs, targets), 1.0), -1.0)
        stats[feature_name] = (mean_value, std_value)
    return weights, stats


def _empty_fit_stats(feature_names: tuple[str, ...]) -> dict[str, Any]:
    return {
        "count": 0,
        "sum_y": 0.0,
        "sum_y2": 0.0,
        "features": {
            feature_name: {"sum_x": 0.0, "sum_x2": 0.0, "sum_xy": 0.0}
            for feature_name in feature_names
        },
    }


def _aggregate_fit_stats(
    rows: list[dict[str, Any]],
    *,
    feature_names: tuple[str, ...],
    targets: list[float],
) -> dict[str, Any]:
    stats = _empty_fit_stats(feature_names)
    for row, target in zip(rows, targets, strict=True):
        stats["count"] += 1
        stats["sum_y"] += target
        stats["sum_y2"] += target * target
        for feature_name in feature_names:
            value = _feature_value(row, feature_name)
            feature_stats = stats["features"][feature_name]
            feature_stats["sum_x"] += value
            feature_stats["sum_x2"] += value * value
            feature_stats["sum_xy"] += value * target
    return stats


def _add_fit_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["count"] += int(source.get("count") or 0)
    target["sum_y"] += _safe_float(source.get("sum_y"))
    target["sum_y2"] += _safe_float(source.get("sum_y2"))
    for feature_name, source_stats in (source.get("features") or {}).items():
        target_stats = target["features"].setdefault(
            feature_name,
            {"sum_x": 0.0, "sum_x2": 0.0, "sum_xy": 0.0},
        )
        target_stats["sum_x"] += _safe_float(source_stats.get("sum_x"))
        target_stats["sum_x2"] += _safe_float(source_stats.get("sum_x2"))
        target_stats["sum_xy"] += _safe_float(source_stats.get("sum_xy"))


def _weights_from_fit_stats(fit_stats: dict[str, Any]) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    count = int(fit_stats.get("count") or 0)
    weights: dict[str, float] = {}
    stats: dict[str, tuple[float, float]] = {}
    if count <= 0:
        return weights, stats
    mean_y = _safe_float(fit_stats.get("sum_y")) / count
    var_y = max(_safe_float(fit_stats.get("sum_y2")) / count - mean_y * mean_y, 0.0)
    for feature_name, values in (fit_stats.get("features") or {}).items():
        mean_x = _safe_float(values.get("sum_x")) / count
        var_x = max(_safe_float(values.get("sum_x2")) / count - mean_x * mean_x, 0.0)
        covariance = _safe_float(values.get("sum_xy")) / count - mean_x * mean_y
        corr = covariance / ((var_x**0.5) * (var_y**0.5)) if var_x > 0 and var_y > 0 else 0.0
        weights[feature_name] = max(min(corr, 1.0), -1.0)
        stats[feature_name] = (mean_x, var_x**0.5)
    return weights, stats


def _score_row(
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


def _tail_targets_by_objective(
    train_rows: list[dict[str, Any]],
    *,
    objective: str,
    positive_top_k: int,
    negative_bottom_k: int,
) -> list[float]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in train_rows:
        by_date[str(row.get("as_of_date") or "")].append(row)
    targets_by_id: dict[int, float] = {}
    for rows in by_date.values():
        ranked = sorted(rows, key=lambda row: _safe_float(row.get("net_excess_return")), reverse=True)
        positive_rows = ranked[:positive_top_k]
        negative_rows = ranked[-negative_bottom_k:] if negative_bottom_k > 0 else []
        positive_ids = {id(row) for row in positive_rows}
        negative_ids = {id(row) for row in negative_rows}
        for row in rows:
            value = _safe_float(row.get("net_excess_return"))
            if objective == "return_magnitude":
                targets_by_id[id(row)] = value * abs(value)
            elif objective == "positive_return_magnitude":
                targets_by_id[id(row)] = max(value, 0.0)
            elif objective == "calibrated_tail":
                if id(row) in positive_ids:
                    targets_by_id[id(row)] = max(value, 0.0)
                elif id(row) in negative_ids:
                    targets_by_id[id(row)] = min(value, 0.0)
                else:
                    targets_by_id[id(row)] = 0.0
            elif objective == "pairwise_top_bottom":
                if id(row) in positive_ids:
                    targets_by_id[id(row)] = 1.0
                elif id(row) in negative_ids:
                    targets_by_id[id(row)] = -1.0
                else:
                    targets_by_id[id(row)] = 0.0
            else:
                targets_by_id[id(row)] = value
    return [targets_by_id.get(id(row), 0.0) for row in train_rows]


def build_top_candidate_objective_calibration_proxy(
    top_candidate_inventory: dict[str, Any],
    *,
    min_train_dates: int = 60,
    top_k: int = 3,
    fillable_avg_amount_20d_threshold: float = 18_200_000.0,
    positive_top_k: int = 20,
    negative_bottom_k: int = 20,
    feature_names: tuple[str, ...] = DEFAULT_OBJECTIVE_FEATURE_NAMES,
) -> dict[str, Any]:
    rows = list(top_candidate_inventory.get("candidate_rows") or [])
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        as_of_date = str(row.get("as_of_date") or "")
        if as_of_date:
            by_date[as_of_date].append(row)
    dates = sorted(by_date)
    objective_names = (
        "return_linear",
        "return_magnitude",
        "positive_return_magnitude",
        "calibrated_tail",
        "pairwise_top_bottom",
    )
    date_fit_stats: dict[str, dict[str, dict[str, Any]]] = {objective: {} for objective in objective_names}
    for as_of_date in dates:
        fillable_rows = [
            row for row in by_date[as_of_date] if _safe_float(row.get("avg_amount_20d")) >= fillable_avg_amount_20d_threshold
        ]
        if not fillable_rows:
            continue
        for objective in objective_names:
            if objective == "return_linear":
                targets = [_safe_float(row.get("net_excess_return")) for row in fillable_rows]
            else:
                targets = _tail_targets_by_objective(
                    fillable_rows,
                    objective=objective,
                    positive_top_k=positive_top_k,
                    negative_bottom_k=negative_bottom_k,
                )
            date_fit_stats[objective][as_of_date] = _aggregate_fit_stats(
                fillable_rows,
                feature_names=feature_names,
                targets=targets,
            )
    cumulative_fit_stats = {objective: _empty_fit_stats(feature_names) for objective in objective_names}
    curves: dict[str, list[tuple[str, float]]] = {
        "baseline_topk_original_rank": [],
        "original_rank_topk_fillable_only": [],
        **{f"{objective}_topk_fillable": [] for objective in objective_names},
    }
    weight_samples: list[dict[str, Any]] = []
    for date_index, as_of_date in enumerate(dates):
        ranked_rows = sorted(by_date[as_of_date], key=lambda row: int(_safe_float(row.get("rank"), 999999.0)))
        if date_index < min_train_dates:
            for objective in objective_names:
                if as_of_date in date_fit_stats[objective]:
                    _add_fit_stats(cumulative_fit_stats[objective], date_fit_stats[objective][as_of_date])
            continue
        fillable_rows = [
            row for row in ranked_rows if _safe_float(row.get("avg_amount_20d")) >= fillable_avg_amount_20d_threshold
        ]
        curves["baseline_topk_original_rank"].append((as_of_date, _weighted_return(ranked_rows[:top_k])))
        curves["original_rank_topk_fillable_only"].append((as_of_date, _weighted_return(fillable_rows[:top_k])))
        if not fillable_rows:
            for objective in objective_names:
                curves[f"{objective}_topk_fillable"].append((as_of_date, 0.0))
        else:
            for objective in objective_names:
                weights, stats = _weights_from_fit_stats(cumulative_fit_stats[objective])
                selected = sorted(
                    fillable_rows,
                    key=lambda row: _score_row(row, weights=weights, stats=stats),
                    reverse=True,
                )[:top_k]
                curves[f"{objective}_topk_fillable"].append((as_of_date, _weighted_return(selected)))
                if len(weight_samples) < 8:
                    weight_samples.append(
                        {
                            "as_of_date": as_of_date,
                            "objective": objective,
                            "weights": {feature_name: round(weight, 6) for feature_name, weight in weights.items()},
                            "selected_symbols": [str(row.get("symbol") or "") for row in selected],
                        }
                    )
        for objective in objective_names:
            if as_of_date in date_fit_stats[objective]:
                _add_fit_stats(cumulative_fit_stats[objective], date_fit_stats[objective][as_of_date])
    variant_stats = {name: _curve_stats(curve) for name, curve in curves.items()}
    baseline = variant_stats["baseline_topk_original_rank"]
    fillable_baseline = variant_stats["original_rank_topk_fillable_only"]
    promising_variants: list[str] = []
    for name, stats in variant_stats.items():
        if name in {"baseline_topk_original_rank", "original_rank_topk_fillable_only"}:
            continue
        if (
            _safe_float(stats.get("mean")) >= _safe_float(fillable_baseline.get("mean"))
            and int(stats.get("negative_month_count") or 0) <= int(fillable_baseline.get("negative_month_count") or 0)
            and _safe_float(stats.get("path_drawdown_sum")) >= _safe_float(fillable_baseline.get("path_drawdown_sum"))
            and _safe_float(stats.get("mean")) >= _safe_float(baseline.get("mean")) * 0.8
        ):
            promising_variants.append(name)
    blocking_gate_ids: list[str] = []
    if not promising_variants:
        blocking_gate_ids.append("no_objective_variant_beats_fillable_baseline_and_retains_original_rank_floor")
    return {
        "artifact_type": "top_candidate_objective_calibration_proxy",
        "schema_version": TOP_CANDIDATE_OBJECTIVE_CALIBRATION_PROXY_VERSION,
        "claim_ceiling": "retained_top_candidate_inventory_objective_proxy_only_no_model_replay_no_promotion",
        "source_inventory_id": top_candidate_inventory.get("artifact_id"),
        "source_trial_id": top_candidate_inventory.get("trial_id"),
        "date_count": len(dates),
        "evaluated_date_count": len(curves["baseline_topk_original_rank"]),
        "candidate_row_count": len(rows),
        "feature_names": list(feature_names),
        "min_train_dates": min_train_dates,
        "top_k": top_k,
        "fillable_avg_amount_20d_threshold": fillable_avg_amount_20d_threshold,
        "positive_top_k": positive_top_k,
        "negative_bottom_k": negative_bottom_k,
        "variants": variant_stats,
        "promising_variants": promising_variants,
        "gate_status": "passed" if promising_variants else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "weight_samples": weight_samples,
        "interpretation": (
            "Diagnostic only. Objective variants over retained TopN inventory must beat the fillable original-rank "
            "baseline on mean, negative months and path drawdown while preserving most of the original-rank floor "
            "before a new full713 replay is justified."
        ),
    }


def write_top_candidate_objective_calibration_proxy(payload: dict[str, Any], output_json: str | Path) -> Path:
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
