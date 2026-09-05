from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from array import array
from collections import deque
from datetime import UTC, datetime
from itertools import product
from math import log1p
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from ashare_evidence.phase2.common import spearman_correlation
from ashare_evidence.research_artifact_store import write_research_validation_artifact
from ashare_evidence.training_label_maturity import cohort_available_day, mature_training_dates

MODEL_CANDIDATE_RUN_SCHEMA_VERSION = "walk_forward_model_candidate_run.v1"
TOP_CANDIDATE_INVENTORY_SCHEMA_VERSION = "top_candidate_inventory.v1"
SCORE_RANK_PROBE_SCHEMA_VERSION = "score_rank_probe.v1"
MAX_STORED_PREDICTIONS_PER_TRIAL = 2000
ARTIFACT_ROW_ITER_CHUNK_BYTES = 4 * 1024 * 1024
STREAM_REPLAY_INSERT_BATCH_SIZE = 5000
STREAM_REPLAY_TOP_ROW_BUFFER_SIZE = 200
MODEL_FEATURE_DEFS = (
    ("return_3d", "price_momentum", "return_3d"),
    ("return_5d", "price_momentum", "return_5d"),
    ("return_10d", "price_momentum", "return_10d"),
    ("return_20d", "price_momentum", "return_20d"),
    ("return_40d", "price_momentum", "return_40d"),
    ("price_benchmark_return_20d", "price_momentum", "benchmark_return_20d"),
    ("return_1d", "reversal_overheat", "return_1d"),
    ("distance_from_20d_high", "reversal_overheat", "distance_from_20d_high"),
    ("distance_from_40d_high", "reversal_overheat", "distance_from_40d_high"),
    ("volatility_10d", "volatility_risk", "volatility_10d"),
    ("volatility_20d", "volatility_risk", "volatility_20d"),
    ("max_drawdown_20d", "volatility_risk", "max_drawdown_20d"),
    ("max_drawdown_40d", "volatility_risk", "max_drawdown_40d"),
    ("avg_amount_10d", "liquidity", "avg_amount_10d"),
    ("avg_amount_20d", "liquidity", "avg_amount_20d"),
    ("avg_volume_20d", "liquidity", "avg_volume_20d"),
    ("turnover_rate", "liquidity", "turnover_rate"),
    ("zero_volume_count_20d", "liquidity", "zero_volume_count_20d"),
    ("total_mv", "valuation_capacity", "total_mv"),
    ("circ_mv", "valuation_capacity", "circ_mv"),
    ("pe_ttm", "valuation_capacity", "pe_ttm"),
    ("pb", "valuation_capacity", "pb"),
    ("amount_vs_20d_avg", "crowding", "amount_vs_20d_avg"),
    ("symbol_recent_exposure_count", "crowding", "symbol_recent_exposure_count"),
    ("benchmark_return_10d", "regime", "benchmark_return_10d"),
    ("benchmark_return_20d", "regime", "benchmark_return_20d"),
    ("benchmark_volatility_20d", "regime", "benchmark_volatility_20d"),
    ("return_5d_percentile", "cross_sectional", "return_5d_percentile"),
    ("return_20d_percentile", "cross_sectional", "return_20d_percentile"),
    ("turnover_rate_percentile", "cross_sectional", "turnover_rate_percentile"),
    ("volatility_20d_percentile", "cross_sectional", "volatility_20d_percentile"),
    ("amount_vs_20d_avg_percentile", "cross_sectional", "amount_vs_20d_avg_percentile"),
    ("total_mv_percentile", "cross_sectional", "total_mv_percentile"),
    ("circ_mv_percentile", "cross_sectional", "circ_mv_percentile"),
    ("pe_ttm_percentile", "cross_sectional", "pe_ttm_percentile"),
    ("pb_percentile", "cross_sectional", "pb_percentile"),
    ("low_turnover_percentile", "cross_sectional", "low_turnover_percentile"),
    ("low_volatility_percentile", "cross_sectional", "low_volatility_percentile"),
    ("small_total_mv_percentile", "cross_sectional", "small_total_mv_percentile"),
    ("small_circ_mv_percentile", "cross_sectional", "small_circ_mv_percentile"),
    ("industry_return_5d_excess", "cross_sectional", "industry_return_5d_excess"),
    ("industry_return_20d_excess", "cross_sectional", "industry_return_20d_excess"),
    ("amount_10d_vs_20d", "cross_sectional", "amount_10d_vs_20d"),
    ("amount_10d_vs_20d_percentile", "cross_sectional", "amount_10d_vs_20d_percentile"),
    ("volatility_10d_vs_20d", "cross_sectional", "volatility_10d_vs_20d"),
)
MODEL_EXECUTION_FEATURE_DEFS = (
    ("limit_state", "execution", "limit_state"),
    ("suspension_or_stale_proxy", "execution", "suspension_or_stale_proxy"),
)


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _grid_trials(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = sorted(grid)
    values = [grid[key] for key in keys]
    return [dict(zip(keys, combo, strict=True)) for combo in product(*values)]


def _deterministic_score_only_model_types() -> set[str]:
    return {
        "deterministic_baseline",
        "pullback_reversal_ranker",
        "liquidity_breakout_ranker",
        "trend_quality_ranker",
        "concentrated_liquidity_momentum_ranker",
        "confirmed_concentrated_liquidity_momentum_ranker",
        "breakout_amount_confirmation_ranker",
        "regime_adaptive_breakout_defensive_ranker",
        "exhaustion_aware_regime_breakout_ranker",
        "capacity_aware_regime_breakout_ranker",
        "fillable_weak_turnaround_ranker",
    }


def _stream_fitted_model_types() -> set[str]:
    return {
        "regularized_rank_linear",
        "tail_capture_linear_ranker",
    }


def _feature(row: dict[str, Any], group: str, key: str) -> float:
    values = row.get("feature_values") or {}
    group_values = values.get(group) or {}
    return _safe_float(group_values.get(key))


def _feature_raw(row: dict[str, Any], group: str, key: str) -> Any:
    values = row.get("feature_values") or {}
    group_values = values.get(group) or {}
    return group_values.get(key)


def _model_feature_values(feature_row: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {name: _feature(feature_row, group, key) for name, group, key in MODEL_FEATURE_DEFS}
    values.update(
        {
            name: _feature_raw(feature_row, group, key)
            for name, group, key in MODEL_EXECUTION_FEATURE_DEFS
        }
    )
    return values


def _exhaustion_base_score(values: dict[str, Any], params: dict[str, Any]) -> float:
    if _uses_defensive_branch(values, params):
        return (
            _safe_float(params.get("defensive_liquidity_percentile_weight"), 1.0)
            * values.get("amount_vs_20d_avg_percentile", 0.0)
            + _safe_float(params.get("defensive_low_volatility_percentile_weight"), 1.2)
            * values.get("low_volatility_percentile", 0.0)
            + _safe_float(params.get("defensive_low_turnover_percentile_weight"), 1.2)
            * values.get("low_turnover_percentile", 0.0)
            + _safe_float(params.get("defensive_return_5d_percentile_weight"), 0.3)
            * values.get("return_5d_percentile", 0.0)
            + _safe_float(params.get("defensive_return_20d_percentile_weight"), 0.0)
            * values.get("return_20d_percentile", 0.0)
        )
    return (
        _safe_float(params.get("momentum_20d_percentile_weight"), 1.5)
        * values.get("return_20d_percentile", 0.0)
        + _safe_float(params.get("amount_10d_vs_20d_percentile_weight"), 0.8)
        * values.get("amount_10d_vs_20d_percentile", 0.0)
        + _safe_float(params.get("liquidity_percentile_weight"), 1.2)
        * values.get("amount_vs_20d_avg_percentile", 0.0)
        - _safe_float(params.get("one_day_overheat_penalty"), 0.5) * values.get("return_1d", 0.0)
    )


def _exhaustion_trigger_matches(values: dict[str, Any], params: dict[str, Any]) -> bool:
    amount_percentile = max(
        _safe_float(values.get("amount_10d_vs_20d_percentile")),
        _safe_float(values.get("amount_vs_20d_avg_percentile")),
    )
    industry_return_20d_excess = _safe_float(values.get("industry_return_20d_excess"))
    return (
        _safe_float(values.get("return_20d_percentile"))
        >= _safe_float(params.get("exhaustion_min_return_20d_percentile"), 0.95)
        and _safe_float(values.get("return_5d_percentile"))
        >= _safe_float(params.get("exhaustion_min_return_5d_percentile"), 0.98)
        and amount_percentile >= _safe_float(params.get("exhaustion_min_amount_percentile"), 0.90)
        and _safe_float(values.get("turnover_rate_percentile"))
        >= _safe_float(params.get("exhaustion_min_turnover_rate_percentile"), 0.65)
        and industry_return_20d_excess >= _safe_float(params.get("exhaustion_min_industry_return_20d_excess"), 0.10)
        and industry_return_20d_excess <= _safe_float(params.get("exhaustion_max_industry_return_20d_excess"), 0.40)
        and _safe_float(values.get("distance_from_20d_high"))
        <= _safe_float(params.get("exhaustion_max_distance_from_20d_high"), -0.015)
        and _safe_float(values.get("benchmark_return_20d"))
        <= _safe_float(params.get("exhaustion_max_benchmark_return_20d"), 1.0)
    )


def _exhaustion_reference_metadata(
    *,
    model_spec: dict[str, Any],
    params: dict[str, Any],
    feature_values: dict[str, Any],
) -> dict[str, Any]:
    if str(model_spec.get("model_type") or "") != "exhaustion_aware_regime_breakout_ranker":
        return {}
    return {
        "exhaustion_reference_score": _exhaustion_base_score(feature_values, params),
        "exhaustion_triggered": _exhaustion_trigger_matches(feature_values, params),
    }


def _target(row: dict[str, Any], *, horizon_days: int = 10) -> float | None:
    value = row.get("target_labels_by_horizon", {}).get(str(horizon_days))
    if value is None and horizon_days == 10:
        value = row.get("target_label")
    if value is None:
        return None
    target = _safe_float(value)
    return target if horizon_days == 10 else target - 0.001


def _target_total_return(row: dict[str, Any], *, horizon_days: int = 10) -> float | None:
    value = row.get("target_total_returns_by_horizon", {}).get(str(horizon_days))
    if value is None:
        return None
    return _safe_float(value) - 0.001


def _exit_horizon_days(
    feature_values: dict[str, float],
    *,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
    default_horizon_days: int,
) -> int:
    exit_policy = selection_policy.get("exit_policy") if isinstance(selection_policy, dict) else None
    if not isinstance(exit_policy, dict) or not exit_policy.get("enabled"):
        return default_horizon_days
    mode = str(exit_policy.get("mode") or "")
    if mode != "regime_stock_risk_adaptive_5_10_20":
        return default_horizon_days
    weak_regime = feature_values.get("benchmark_return_20d", 0.0) < _safe_float(
        params.get("weak_regime_benchmark_return_20d_threshold"),
        _safe_float(exit_policy.get("weak_regime_benchmark_return_20d_threshold"), 0.0),
    )
    high_regime_volatility = feature_values.get("benchmark_volatility_20d", 0.0) > _safe_float(
        params.get("high_regime_benchmark_volatility_20d_threshold"),
        _safe_float(exit_policy.get("high_regime_benchmark_volatility_20d_threshold"), 0.08),
    )
    high_stock_risk = (
        feature_values.get("volatility_20d_percentile", 0.0)
        > _safe_float(
            params.get("exit_stock_risk_volatility_20d_percentile"),
            _safe_float(exit_policy.get("exit_stock_risk_volatility_20d_percentile"), 0.80),
        )
        or feature_values.get("turnover_rate_percentile", 0.0)
        > _safe_float(
            params.get("exit_stock_risk_turnover_rate_percentile"),
            _safe_float(exit_policy.get("exit_stock_risk_turnover_rate_percentile"), 0.90),
        )
    )
    strong_regime = feature_values.get("benchmark_return_20d", 0.0) >= _safe_float(
        params.get("strong_regime_benchmark_return_20d_threshold"),
        _safe_float(exit_policy.get("strong_regime_benchmark_return_20d_threshold"), 0.03),
    )
    if (weak_regime or high_regime_volatility) and high_stock_risk:
        return int(
            _safe_float(
                params.get("risk_exit_horizon_days"),
                _safe_float(exit_policy.get("risk_exit_horizon_days"), 5),
            )
        )
    if weak_regime or high_regime_volatility:
        return int(
            _safe_float(
                params.get("weak_regime_exit_horizon_days"),
                _safe_float(exit_policy.get("weak_regime_exit_horizon_days"), 10),
            )
        )
    if strong_regime:
        return int(
            _safe_float(
                params.get("strong_regime_exit_horizon_days"),
                _safe_float(exit_policy.get("strong_regime_exit_horizon_days"), 20),
            )
        )
    return int(
        _safe_float(
            params.get("neutral_regime_exit_horizon_days"),
            _safe_float(exit_policy.get("neutral_regime_exit_horizon_days"), default_horizon_days),
        )
    )


def _correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    count = float(len(xs))
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    var_x = sum((x - mean_x) ** 2 for x in xs) / count
    var_y = sum((y - mean_y) ** 2 for y in ys) / count
    if var_x <= 0 or var_y <= 0:
        return 0.0
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / count
    return covariance / ((var_x**0.5) * (var_y**0.5))


def _linear_fit(rows: list[dict[str, Any]], *, alpha: float, horizon_days: int) -> dict[str, Any]:
    feature_values = [
        (row, row.get("feature_values_flat") or _model_feature_values(row["feature_row"]), _target(row, horizon_days=horizon_days))
        for row in rows
    ]
    feature_values = [(row, values, target) for row, values, target in feature_values if target is not None]
    targets = [float(target) for _, _, target in feature_values]
    feature_stats: dict[str, dict[str, float]] = {}
    for feature_name, _, _ in MODEL_FEATURE_DEFS:
        xs = [values[feature_name] for _, values, _ in feature_values]
        if not xs or not targets:
            continue
        std = pstdev(xs) if len(xs) > 1 else 0.0
        corr = _correlation(xs, targets)
        feature_stats[feature_name] = {
            "mean": mean(xs),
            "std": std,
            "weight": max(min(corr / max(1.0 + alpha, 0.1), 1.0), -1.0),
            "correlation": corr,
        }
    return {
        "model_family": "split_fitted_rank_linear",
        "train_row_count": len(feature_values),
        "target_mean": mean(targets) if targets else 0.0,
        "regularization_alpha": alpha,
        "feature_stats": feature_stats,
    }


def _linear_score(values: dict[str, float], fitted_model: dict[str, Any]) -> float:
    score = _safe_float(fitted_model.get("target_mean"))
    for feature_name, stats in (fitted_model.get("feature_stats") or {}).items():
        std = _safe_float(stats.get("std"))
        if std <= 0:
            continue
        z_score = (values.get(feature_name, 0.0) - _safe_float(stats.get("mean"))) / std
        score += _safe_float(stats.get("weight")) * z_score
    return score


def _tail_capture_candidate_rows(
    rows: list[dict[str, Any]],
    *,
    horizon_days: int,
    min_avg_amount_20d: float,
) -> list[tuple[dict[str, Any], dict[str, float], float]]:
    candidates: list[tuple[dict[str, Any], dict[str, float], float]] = []
    for row in rows:
        target = _target(row, horizon_days=horizon_days)
        if target is None:
            continue
        values = row.get("feature_values_flat") or _model_feature_values(row["feature_row"])
        if min_avg_amount_20d > 0 and _safe_float(values.get("avg_amount_20d")) < min_avg_amount_20d:
            continue
        if str(values.get("limit_state") or "") == "limit_up_like":
            continue
        if bool(values.get("suspension_or_stale_proxy")):
            continue
        candidates.append((row, values, float(target)))
    return candidates


def _tail_capture_linear_fit(rows: list[dict[str, Any]], *, params: dict[str, Any], horizon_days: int) -> dict[str, Any]:
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    stats = _empty_linear_fit_stats()
    positive_top_k = max(1, int(_safe_float(params.get("tail_positive_top_k"), 20.0)))
    min_avg_amount_20d = _safe_float(params.get("min_avg_amount_20d"), 0.0)
    for date_rows in rows_by_date.values():
        candidates = _tail_capture_candidate_rows(
            date_rows,
            horizon_days=horizon_days,
            min_avg_amount_20d=min_avg_amount_20d,
        )
        if not candidates:
            continue
        positive_ids = {
            str(row.get("universe_row_id") or "")
            for row, _values, _target in sorted(candidates, key=lambda item: item[2], reverse=True)[:positive_top_k]
        }
        for row, values, _target in candidates:
            _update_linear_fit_stats(stats, values, 1.0 if str(row.get("universe_row_id") or "") in positive_ids else 0.0)
    return _linear_fit_from_stats(
        stats,
        alpha=_safe_float(params.get("regularization_alpha"), 1.0),
        horizon_days=horizon_days,
    )


def _uses_defensive_branch(values: dict[str, float], params: dict[str, Any]) -> bool:
    benchmark_threshold = _safe_float(params.get("defensive_benchmark_return_20d_threshold"), 0.0)
    if values.get("benchmark_return_20d", 0.0) < benchmark_threshold:
        return True
    mode = str(params.get("defensive_condition_mode") or "benchmark_20d")
    if mode != "benchmark_20d_or_transition_stress":
        return False
    return (
        values.get("benchmark_return_10d", 0.0)
        < _safe_float(params.get("transition_benchmark_return_10d_threshold"), -0.01)
        and values.get("benchmark_return_20d", 0.0)
        < _safe_float(params.get("transition_benchmark_return_20d_ceiling"), 0.03)
        and values.get("benchmark_volatility_20d", 0.0)
        > _safe_float(params.get("transition_benchmark_volatility_20d_threshold"), 0.04)
    )


def _fit_model(rows: list[dict[str, Any]], *, model_spec: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    spec_type = str(model_spec.get("model_type") or "")
    horizon_days = int(model_spec.get("prediction_horizon_days") or 10)
    if spec_type in _deterministic_score_only_model_types():
        return {
            "model_family": f"{spec_type}_no_fit",
            "train_row_count": len(rows),
            "prediction_horizon_days": horizon_days,
            "feature_stats": {},
        }
    alpha = _safe_float(params.get("regularization_alpha"), 1.0)
    if spec_type == "tail_capture_linear_ranker":
        return _tail_capture_linear_fit(rows, params=params, horizon_days=horizon_days)
    if spec_type == "bounded_regime_conditioned_linear":
        uptrend_rows = [
            row
            for row in rows
            if _safe_float((row.get("feature_values_flat") or {}).get("benchmark_return_20d")) >= 0
        ]
        downtrend_rows = [
            row
            for row in rows
            if _safe_float((row.get("feature_values_flat") or {}).get("benchmark_return_20d")) < 0
        ]
        return {
            "model_family": "split_fitted_regime_conditioned_linear",
            "train_row_count": len(rows),
            "prediction_horizon_days": horizon_days,
            "regime_models": {
                "benchmark_nonnegative": _linear_fit(uptrend_rows or rows, alpha=alpha, horizon_days=horizon_days),
                "benchmark_negative": _linear_fit(downtrend_rows or rows, alpha=alpha, horizon_days=horizon_days),
            },
        }
    if spec_type == "shallow_tree_ranker":
        linear_model = _linear_fit(rows, alpha=alpha, horizon_days=horizon_days)
        max_depth = max(1, int(_safe_float(params.get("max_depth"), 2.0)))
        ranked_features = sorted(
            (linear_model.get("feature_stats") or {}).items(),
            key=lambda item: abs(_safe_float(item[1].get("correlation"))),
            reverse=True,
        )[:max_depth]
        feature_values = [row.get("feature_values_flat") or _model_feature_values(row["feature_row"]) for row in rows]
        stumps = []
        for feature_name, stats in ranked_features:
            xs = [values[feature_name] for values in feature_values]
            stumps.append(
                {
                    "feature_name": feature_name,
                    "threshold": median(xs) if xs else 0.0,
                    "direction": 1.0 if _safe_float(stats.get("correlation")) >= 0 else -1.0,
                    "weight": abs(_safe_float(stats.get("correlation"))),
                }
            )
        return {
            "model_family": "split_fitted_shallow_tree_stumps",
            "train_row_count": len(rows),
            "prediction_horizon_days": horizon_days,
            "stumps": stumps,
        }
    return _linear_fit(rows, alpha=alpha, horizon_days=horizon_days)


def _empty_linear_fit_stats() -> dict[str, Any]:
    return {
        "count": 0,
        "sum_y": 0.0,
        "sum_y2": 0.0,
        "features": {
            feature_name: {"sum_x": 0.0, "sum_x2": 0.0, "sum_xy": 0.0}
            for feature_name, _, _ in MODEL_FEATURE_DEFS
        },
    }


def _update_linear_fit_stats(stats: dict[str, Any], values: dict[str, float], target: float) -> None:
    stats["count"] += 1
    stats["sum_y"] += target
    stats["sum_y2"] += target * target
    for feature_name, _, _ in MODEL_FEATURE_DEFS:
        value = _safe_float(values.get(feature_name))
        feature_stats = stats["features"][feature_name]
        feature_stats["sum_x"] += value
        feature_stats["sum_x2"] += value * value
        feature_stats["sum_xy"] += value * target


def _merge_linear_fit_stats(stats_rows: list[dict[str, Any]]) -> dict[str, Any]:
    merged = _empty_linear_fit_stats()
    for stats in stats_rows:
        merged["count"] += int(stats.get("count") or 0)
        merged["sum_y"] += _safe_float(stats.get("sum_y"))
        merged["sum_y2"] += _safe_float(stats.get("sum_y2"))
        for feature_name, feature_stats in (stats.get("features") or {}).items():
            target_stats = merged["features"].setdefault(
                feature_name,
                {"sum_x": 0.0, "sum_x2": 0.0, "sum_xy": 0.0},
            )
            target_stats["sum_x"] += _safe_float(feature_stats.get("sum_x"))
            target_stats["sum_x2"] += _safe_float(feature_stats.get("sum_x2"))
            target_stats["sum_xy"] += _safe_float(feature_stats.get("sum_xy"))
    return merged


def _linear_fit_from_stats(stats: dict[str, Any], *, alpha: float, horizon_days: int) -> dict[str, Any]:
    count = int(stats.get("count") or 0)
    if count <= 0:
        return {
            "model_family": "stream_split_fitted_rank_linear",
            "train_row_count": 0,
            "target_mean": 0.0,
            "regularization_alpha": alpha,
            "prediction_horizon_days": horizon_days,
            "feature_stats": {},
        }
    target_mean = _safe_float(stats.get("sum_y")) / count
    target_var = max(_safe_float(stats.get("sum_y2")) / count - target_mean * target_mean, 0.0)
    feature_stats: dict[str, dict[str, float]] = {}
    for feature_name, values in (stats.get("features") or {}).items():
        mean_x = _safe_float(values.get("sum_x")) / count
        var_x = max(_safe_float(values.get("sum_x2")) / count - mean_x * mean_x, 0.0)
        covariance = _safe_float(values.get("sum_xy")) / count - mean_x * target_mean
        corr = covariance / ((var_x**0.5) * (target_var**0.5)) if var_x > 0 and target_var > 0 else 0.0
        feature_stats[feature_name] = {
            "mean": mean_x,
            "std": var_x**0.5,
            "weight": max(min(corr / max(1.0 + alpha, 0.1), 1.0), -1.0),
            "correlation": corr,
        }
    return {
        "model_family": "stream_split_fitted_rank_linear",
        "train_row_count": count,
        "target_mean": target_mean,
        "regularization_alpha": alpha,
        "prediction_horizon_days": horizon_days,
        "feature_stats": feature_stats,
    }


def _build_stream_linear_fit_stats_by_date(
    *,
    feature_matrix_artifact: str | Path,
    label_sqlite_path: Path,
    horizons: set[int],
) -> dict[int, dict[str, dict[str, Any]]]:
    stats_by_horizon_date: dict[int, dict[str, dict[str, Any]]] = {horizon: {} for horizon in horizons}
    for as_of_date, rows in _stream_joined_rows_by_date(
        feature_matrix_artifact=feature_matrix_artifact,
        label_sqlite_path=label_sqlite_path,
    ):
        for row in rows:
            values = row.get("feature_values_flat") or {}
            for horizon_days in horizons:
                target = _target(row, horizon_days=horizon_days)
                if target is None:
                    continue
                date_stats = stats_by_horizon_date[horizon_days].setdefault(as_of_date, _empty_linear_fit_stats())
                _update_linear_fit_stats(date_stats, values, float(target))
        for horizon_days in horizons:
            target_rows = [row for row in rows if _target(row, horizon_days=horizon_days) is not None]
            if as_of_date in stats_by_horizon_date[horizon_days]:
                stats_by_horizon_date[horizon_days][as_of_date]["label_available_on"] = cohort_available_day(
                    target_rows, horizon_days=horizon_days
                )
    return stats_by_horizon_date


def _tail_capture_config_key(*, horizon_days: int, positive_top_k: int, min_avg_amount_20d: float) -> str:
    return f"h{horizon_days}:top{positive_top_k}:minavg{min_avg_amount_20d:.4f}"


def _build_stream_tail_capture_fit_stats_by_config_date(
    *,
    feature_matrix_artifact: str | Path,
    label_sqlite_path: Path,
    configs: set[tuple[int, int, float]],
) -> dict[str, dict[str, dict[str, Any]]]:
    stats_by_config_date: dict[str, dict[str, dict[str, Any]]] = {
        _tail_capture_config_key(
            horizon_days=horizon_days,
            positive_top_k=positive_top_k,
            min_avg_amount_20d=min_avg_amount_20d,
        ): {}
        for horizon_days, positive_top_k, min_avg_amount_20d in configs
    }
    for as_of_date, rows in _stream_joined_rows_by_date(
        feature_matrix_artifact=feature_matrix_artifact,
        label_sqlite_path=label_sqlite_path,
    ):
        for horizon_days, positive_top_k, min_avg_amount_20d in configs:
            candidates = _tail_capture_candidate_rows(
                rows,
                horizon_days=horizon_days,
                min_avg_amount_20d=min_avg_amount_20d,
            )
            if not candidates:
                continue
            positive_ids = {
                str(row.get("universe_row_id") or "")
                for row, _values, _target in sorted(candidates, key=lambda item: item[2], reverse=True)[:positive_top_k]
            }
            key = _tail_capture_config_key(
                horizon_days=horizon_days,
                positive_top_k=positive_top_k,
                min_avg_amount_20d=min_avg_amount_20d,
            )
            date_stats = stats_by_config_date[key].setdefault(as_of_date, _empty_linear_fit_stats())
            date_stats["label_available_on"] = cohort_available_day(
                [row for row, _values, _target in candidates], horizon_days=horizon_days
            )
            for row, values, _target in candidates:
                binary_target = 1.0 if str(row.get("universe_row_id") or "") in positive_ids else 0.0
                _update_linear_fit_stats(date_stats, values, binary_target)
    return stats_by_config_date


def _fit_stream_model_from_date_stats(
    *,
    stats_by_date: dict[str, dict[str, Any]],
    train_dates: list[str],
    model_spec: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    horizon_days = int(model_spec.get("prediction_horizon_days") or 10)
    alpha = _safe_float(params.get("regularization_alpha"), 1.0)
    train_stats = [stats_by_date[str(train_date)] for train_date in train_dates if str(train_date) in stats_by_date]
    fitted = _linear_fit_from_stats(_merge_linear_fit_stats(train_stats), alpha=alpha, horizon_days=horizon_days)
    return fitted


def _fit_stream_tail_capture_model_from_date_stats(
    *,
    stats_by_date: dict[str, dict[str, Any]],
    train_dates: list[str],
    model_spec: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    horizon_days = int(model_spec.get("prediction_horizon_days") or 10)
    train_stats = [stats_by_date[str(train_date)] for train_date in train_dates if str(train_date) in stats_by_date]
    return _linear_fit_from_stats(
        _merge_linear_fit_stats(train_stats),
        alpha=_safe_float(params.get("regularization_alpha"), 1.0),
        horizon_days=horizon_days,
    )


def _fitted_model_summary(fitted_model: dict[str, Any]) -> dict[str, Any]:
    family = str(fitted_model.get("model_family") or "")
    if family == "split_fitted_regime_conditioned_linear":
        regime_models = fitted_model.get("regime_models") or {}
        return {
            "model_family": family,
            "train_row_count": fitted_model.get("train_row_count"),
            "regime_feature_count": {
                regime: len(model.get("feature_stats") or {}) for regime, model in regime_models.items()
            },
        }
    if family == "split_fitted_shallow_tree_stumps":
        return {
            "model_family": family,
            "train_row_count": fitted_model.get("train_row_count"),
            "stumps": fitted_model.get("stumps") or [],
        }
    feature_stats = fitted_model.get("feature_stats") or {}
    top_features = sorted(
        (
            {
                "feature_name": feature_name,
                "weight": stats.get("weight"),
                "correlation": stats.get("correlation"),
            }
            for feature_name, stats in feature_stats.items()
        ),
        key=lambda item: abs(_safe_float(item.get("weight"))),
        reverse=True,
    )[:5]
    return {
        "model_family": family,
        "train_row_count": fitted_model.get("train_row_count"),
        "top_features": top_features,
    }


def _score_row(
    feature_row: dict[str, Any],
    *,
    model_spec: dict[str, Any],
    params: dict[str, Any],
    fitted_model: dict[str, Any] | None = None,
    feature_values: dict[str, float] | None = None,
) -> float:
    spec_type = str(model_spec.get("model_type") or "")
    values = feature_values or _model_feature_values(feature_row)
    momentum = values.get("return_10d", 0.0) or values.get("return_5d", 0.0)
    liquidity = values.get("avg_amount_20d", 0.0)
    overheat = values.get("return_1d", 0.0)
    volatility = values.get("volatility_20d", 0.0)
    regime = values.get("benchmark_return_20d", 0.0)
    crowding = values.get("amount_vs_20d_avg", 0.0)
    if spec_type == "deterministic_baseline":
        return momentum + 0.000000001 * liquidity - 0.5 * overheat
    if spec_type == "regularized_rank_linear" and fitted_model:
        return _linear_score(values, fitted_model)
    if spec_type == "regularized_rank_linear":
        alpha = _safe_float(params.get("regularization_alpha"), 1.0)
        return (momentum + 0.2 * crowding + 0.1 * regime - 0.3 * volatility - 0.2 * overheat) / max(alpha, 0.1)
    if spec_type == "tail_capture_linear_ranker" and fitted_model:
        return _linear_score(values, fitted_model)
    if spec_type == "tail_capture_linear_ranker":
        return (
            0.6 * values.get("return_5d_percentile", 0.0)
            + 0.6 * values.get("return_20d_percentile", 0.0)
            + 0.4 * values.get("amount_10d_vs_20d_percentile", 0.0)
            + 0.2 * values.get("turnover_rate_percentile", 0.0)
            - 0.3 * values.get("max_drawdown_20d", 0.0)
        )
    if spec_type == "shallow_tree_ranker" and fitted_model:
        score = 0.0
        for stump in fitted_model.get("stumps") or []:
            feature_value = values.get(str(stump.get("feature_name") or ""), 0.0)
            threshold = _safe_float(stump.get("threshold"))
            direction = _safe_float(stump.get("direction"), 1.0)
            weight = _safe_float(stump.get("weight"))
            score += weight if direction * (feature_value - threshold) >= 0 else -weight
        return score
    if spec_type == "shallow_tree_ranker":
        depth_bonus = _safe_float(params.get("max_depth"), 2.0) * 0.01
        breakout_bonus = 0.05 if momentum > 0 and crowding > 1 else 0.0
        risk_penalty = 0.05 if volatility > 0.2 else 0.0
        return momentum + breakout_bonus + depth_bonus - risk_penalty
    if spec_type == "bounded_regime_conditioned_linear" and fitted_model:
        regime_key = "benchmark_nonnegative" if regime >= 0 else "benchmark_negative"
        regime_model = (fitted_model.get("regime_models") or {}).get(regime_key) or {}
        return _linear_score(values, regime_model)
    if spec_type == "bounded_regime_conditioned_linear":
        multiplier = 1.0
        if regime > 0:
            multiplier = 1.0 + min(regime, 0.3)
        elif regime < 0:
            multiplier = 1.0 + max(regime, -0.3)
        return (momentum + 0.15 * crowding - 0.25 * volatility) * min(max(multiplier, 0.5), 1.5)
    if spec_type == "pullback_reversal_ranker":
        return (
            -_safe_float(params.get("pullback_weight"), 1.2) * overheat
            + _safe_float(params.get("trend_context_weight"), 0.35) * momentum
            - _safe_float(params.get("volatility_penalty"), 0.35) * volatility
            + 0.03 * crowding
        )
    if spec_type == "liquidity_breakout_ranker":
        return (
            _safe_float(params.get("momentum_weight"), 0.6) * momentum
            + _safe_float(params.get("liquidity_confirmation_weight"), 0.35) * crowding
            - 0.4 * volatility
            - _safe_float(params.get("overheat_penalty"), 0.25) * max(overheat, 0.0)
        )
    if spec_type == "trend_quality_ranker":
        return (
            _safe_float(params.get("trend_weight"), 1.0) * values.get("return_20d", 0.0)
            + _safe_float(params.get("high_distance_weight"), 0.5) * values.get("distance_from_20d_high", 0.0)
            - _safe_float(params.get("volatility_penalty"), 0.45) * volatility
        )
    if spec_type == "concentrated_liquidity_momentum_ranker":
        liquidity_score = log1p(max(values.get("avg_amount_20d", 0.0), 0.0))
        momentum_score = values.get("return_40d", 0.0) + values.get("return_20d", 0.0)
        industry_score = values.get("industry_return_20d_excess", 0.0)
        return (
            _safe_float(params.get("liquidity_weight"), 1.0) * liquidity_score
            + _safe_float(params.get("momentum_weight"), 0.0) * momentum_score
            + _safe_float(params.get("industry_relative_weight"), 0.0) * industry_score
            - _safe_float(params.get("volatility_penalty"), 0.0) * volatility
        )
    if spec_type == "confirmed_concentrated_liquidity_momentum_ranker":
        min_return_percentile = _safe_float(params.get("min_return_20d_percentile"), 0.85)
        min_industry_excess = _safe_float(params.get("min_industry_return_20d_excess"), 0.0)
        max_turnover_percentile = _safe_float(params.get("max_turnover_rate_percentile"), 1.0)
        max_volatility_percentile = _safe_float(params.get("max_volatility_20d_percentile"), 1.0)
        if (
            values.get("return_20d_percentile", 0.0) < min_return_percentile
            or values.get("industry_return_20d_excess", 0.0) < min_industry_excess
            or values.get("turnover_rate_percentile", 0.0) > max_turnover_percentile
            or values.get("volatility_20d_percentile", 0.0) > max_volatility_percentile
        ):
            return -1_000_000.0 + values.get("return_20d_percentile", 0.0)
        liquidity_score = log1p(max(values.get("avg_amount_20d", 0.0), 0.0))
        momentum_score = values.get("return_40d", 0.0) + values.get("return_20d", 0.0)
        industry_score = values.get("industry_return_20d_excess", 0.0)
        confirmation_score = values.get("return_20d_percentile", 0.0) + values.get("amount_10d_vs_20d", 0.0)
        return (
            _safe_float(params.get("liquidity_weight"), 1.0) * liquidity_score
            + _safe_float(params.get("momentum_weight"), 0.25) * momentum_score
            + _safe_float(params.get("industry_relative_weight"), 0.0) * industry_score
            + 0.1 * confirmation_score
        )
    if spec_type == "breakout_amount_confirmation_ranker":
        return (
            _safe_float(params.get("momentum_20d_percentile_weight"), 1.5) * values.get("return_20d_percentile", 0.0)
            + _safe_float(params.get("amount_10d_vs_20d_percentile_weight"), 1.0)
            * values.get("amount_10d_vs_20d_percentile", 0.0)
            + _safe_float(params.get("liquidity_percentile_weight"), 1.0)
            * values.get("amount_vs_20d_avg_percentile", 0.0)
            - _safe_float(params.get("one_day_overheat_penalty"), 0.8) * values.get("return_1d", 0.0)
        )
    if spec_type == "regime_adaptive_breakout_defensive_ranker":
        if _uses_defensive_branch(values, params):
            return (
                _safe_float(params.get("defensive_liquidity_percentile_weight"), 1.0)
                * values.get("amount_vs_20d_avg_percentile", 0.0)
                + _safe_float(params.get("defensive_low_volatility_percentile_weight"), 1.2)
                * values.get("low_volatility_percentile", 0.0)
                + _safe_float(params.get("defensive_low_turnover_percentile_weight"), 1.2)
                * values.get("low_turnover_percentile", 0.0)
                + _safe_float(params.get("defensive_return_5d_percentile_weight"), 0.3)
                * values.get("return_5d_percentile", 0.0)
                + _safe_float(params.get("defensive_return_20d_percentile_weight"), 0.0)
                * values.get("return_20d_percentile", 0.0)
            )
        return (
            _safe_float(params.get("momentum_20d_percentile_weight"), 1.5) * values.get("return_20d_percentile", 0.0)
            + _safe_float(params.get("amount_10d_vs_20d_percentile_weight"), 0.8)
            * values.get("amount_10d_vs_20d_percentile", 0.0)
            + _safe_float(params.get("liquidity_percentile_weight"), 1.2)
            * values.get("amount_vs_20d_avg_percentile", 0.0)
            - _safe_float(params.get("one_day_overheat_penalty"), 0.5) * values.get("return_1d", 0.0)
        )
    if spec_type == "exhaustion_aware_regime_breakout_ranker":
        base_score = _exhaustion_base_score(values, params)
        if _exhaustion_trigger_matches(values, params):
            return base_score - _safe_float(params.get("exhaustion_score_penalty"), 1000.0)
        return base_score
    if spec_type == "fillable_weak_turnaround_ranker":
        full_fill_avg_amount = max(_safe_float(params.get("capacity_full_fill_avg_amount_20d"), 18_200_000.0), 1.0)
        avg_amount = max(_safe_float(values.get("avg_amount_20d")), 0.0)
        fill_depth = min(1.0, avg_amount / full_fill_avg_amount)
        capacity_shortfall = max(0.0, min(1.0, 1.0 - fill_depth))
        weak_turnaround_score = (
            _safe_float(params.get("weak_return_5d_percentile_weight"), 1.2)
            * values.get("return_5d_percentile", 0.0)
            + _safe_float(params.get("weak_amount_10d_vs_20d_percentile_weight"), 1.0)
            * values.get("amount_10d_vs_20d_percentile", 0.0)
            + _safe_float(params.get("weak_turnover_rate_percentile_weight"), 0.5)
            * values.get("turnover_rate_percentile", 0.0)
            + _safe_float(params.get("weak_return_20d_percentile_weight"), 0.4)
            * values.get("return_20d_percentile", 0.0)
            + _safe_float(params.get("weak_liquidity_percentile_weight"), 0.4)
            * values.get("amount_vs_20d_avg_percentile", 0.0)
            + _safe_float(params.get("weak_volatility_recovery_weight"), 0.2)
            * values.get("volatility_20d_percentile", 0.0)
        )
        normal_breakout_score = (
            _safe_float(params.get("momentum_20d_percentile_weight"), 1.2)
            * values.get("return_20d_percentile", 0.0)
            + _safe_float(params.get("amount_10d_vs_20d_percentile_weight"), 0.9)
            * values.get("amount_10d_vs_20d_percentile", 0.0)
            + _safe_float(params.get("liquidity_percentile_weight"), 0.8)
            * values.get("amount_vs_20d_avg_percentile", 0.0)
            + _safe_float(params.get("return_5d_percentile_weight"), 0.4)
            * values.get("return_5d_percentile", 0.0)
            - _safe_float(params.get("one_day_overheat_penalty"), 0.5) * values.get("return_1d", 0.0)
        )
        base_score = weak_turnaround_score if _uses_defensive_branch(values, params) else normal_breakout_score
        low_turnover_penalty = _safe_float(params.get("low_turnover_penalty_weight"), 0.4) * values.get(
            "low_turnover_percentile",
            0.0,
        )
        ultra_low_vol_penalty = _safe_float(params.get("ultra_low_vol_penalty_weight"), 0.3) * values.get(
            "low_volatility_percentile",
            0.0,
        )
        return (
            base_score
            + _safe_float(params.get("capacity_depth_bonus"), 0.8) * fill_depth
            - _safe_float(params.get("capacity_shortfall_penalty"), 2.0) * capacity_shortfall
            - low_turnover_penalty
            - ultra_low_vol_penalty
        )
    if spec_type == "capacity_aware_regime_breakout_ranker":
        if _uses_defensive_branch(values, params):
            base_score = (
                _safe_float(params.get("defensive_liquidity_percentile_weight"), 0.8)
                * values.get("amount_vs_20d_avg_percentile", 0.0)
                + _safe_float(params.get("defensive_low_volatility_percentile_weight"), 1.1)
                * values.get("low_volatility_percentile", 0.0)
                + _safe_float(params.get("defensive_low_turnover_percentile_weight"), 0.65)
                * values.get("low_turnover_percentile", 0.0)
                + _safe_float(params.get("defensive_return_5d_percentile_weight"), 0.3)
                * values.get("return_5d_percentile", 0.0)
                + _safe_float(params.get("defensive_return_20d_percentile_weight"), 0.2)
                * values.get("return_20d_percentile", 0.0)
            )
        else:
            base_score = (
                _safe_float(params.get("momentum_20d_percentile_weight"), 1.4)
                * values.get("return_20d_percentile", 0.0)
                + _safe_float(params.get("amount_10d_vs_20d_percentile_weight"), 0.9)
                * values.get("amount_10d_vs_20d_percentile", 0.0)
                + _safe_float(params.get("liquidity_percentile_weight"), 1.0)
                * values.get("amount_vs_20d_avg_percentile", 0.0)
                + _safe_float(params.get("return_5d_percentile_weight"), 0.15)
                * values.get("return_5d_percentile", 0.0)
                - _safe_float(params.get("one_day_overheat_penalty"), 0.5) * values.get("return_1d", 0.0)
            )
        full_fill_avg_amount = max(_safe_float(params.get("capacity_full_fill_avg_amount_20d"), 18_200_000.0), 1.0)
        avg_amount = max(_safe_float(values.get("avg_amount_20d")), 0.0)
        capacity_shortfall = max(0.0, min(1.0, (full_fill_avg_amount - avg_amount) / full_fill_avg_amount))
        small_cap_pressure = max(
            _safe_float(values.get("small_total_mv_percentile")),
            _safe_float(values.get("small_circ_mv_percentile")),
        )
        low_turnover_pressure = _safe_float(values.get("low_turnover_percentile"))
        capacity_penalty = _safe_float(params.get("capacity_shortfall_penalty"), 1.0) * capacity_shortfall * (
            1.0
            + _safe_float(params.get("small_cap_pressure_weight"), 0.5) * small_cap_pressure
            + _safe_float(params.get("low_turnover_pressure_weight"), 0.5) * low_turnover_pressure
        )
        capacity_depth_bonus = _safe_float(params.get("capacity_depth_bonus"), 0.0) * min(
            1.0,
            avg_amount / full_fill_avg_amount,
        )
        market_cap_bonus = _safe_float(params.get("market_cap_percentile_bonus"), 0.0) * max(
            _safe_float(values.get("total_mv_percentile")),
            _safe_float(values.get("circ_mv_percentile")),
        )
        return base_score + capacity_depth_bonus + market_cap_bonus - capacity_penalty
    return momentum


def _selection_allowed(
    feature_values: dict[str, float],
    *,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, list[str]]:
    cash_switch = selection_policy.get("cash_switch") if isinstance(selection_policy, dict) else None
    if not isinstance(cash_switch, dict) or not cash_switch.get("enabled"):
        blockers: list[str] = []
    else:
        blockers = []
        breached: list[str] = []
        configured_condition_count = 0
        min_benchmark_return_10d = _safe_float(
            params.get("min_benchmark_return_10d"),
            _safe_float(cash_switch.get("min_benchmark_return_10d"), -1.0),
        )
        min_benchmark_return_20d = _safe_float(
            params.get("min_benchmark_return_20d"),
            _safe_float(cash_switch.get("min_benchmark_return_20d"), -1.0),
        )
        max_benchmark_volatility_20d = _safe_float(
            params.get("max_benchmark_volatility_20d"),
            _safe_float(cash_switch.get("max_benchmark_volatility_20d"), 999.0),
        )
        if min_benchmark_return_10d > -1.0:
            configured_condition_count += 1
            if feature_values.get("benchmark_return_10d", 0.0) < min_benchmark_return_10d:
                breached.append("benchmark_return_10d_below_cash_switch")
        if min_benchmark_return_20d > -1.0:
            configured_condition_count += 1
            if feature_values.get("benchmark_return_20d", 0.0) < min_benchmark_return_20d:
                breached.append("benchmark_return_20d_below_cash_switch")
        if max_benchmark_volatility_20d < 999.0:
            configured_condition_count += 1
            if feature_values.get("benchmark_volatility_20d", 0.0) > max_benchmark_volatility_20d:
                breached.append("benchmark_volatility_20d_above_cash_switch")
        if str(cash_switch.get("condition_mode") or "any") == "all":
            if configured_condition_count > 0 and len(breached) == configured_condition_count:
                blockers.extend(breached)
        else:
            blockers.extend(breached)
    feature_gate = selection_policy.get("feature_gate") if isinstance(selection_policy, dict) else None
    if isinstance(feature_gate, dict):
        max_volatility = feature_gate.get("max_volatility_20d_percentile")
        if max_volatility is not None and feature_values.get("volatility_20d_percentile", 0.0) > _safe_float(max_volatility):
            blockers.append("volatility_20d_percentile_above_feature_gate")
        max_turnover = feature_gate.get("max_turnover_rate_percentile")
        if max_turnover is not None and feature_values.get("turnover_rate_percentile", 0.0) > _safe_float(max_turnover):
            blockers.append("turnover_rate_percentile_above_feature_gate")
        min_return_20d = feature_gate.get("min_return_20d_percentile")
        if min_return_20d is not None and feature_values.get("return_20d_percentile", 0.0) < _safe_float(min_return_20d):
            blockers.append("return_20d_percentile_below_feature_gate")
        min_amount_10d_vs_20d = feature_gate.get("min_amount_10d_vs_20d")
        if min_amount_10d_vs_20d is not None and feature_values.get("amount_10d_vs_20d", 0.0) < _safe_float(
            min_amount_10d_vs_20d
        ):
            blockers.append("amount_10d_vs_20d_below_feature_gate")
        min_avg_amount_20d = feature_gate.get("min_avg_amount_20d")
        if min_avg_amount_20d is not None and feature_values.get("avg_amount_20d", 0.0) < _safe_float(
            params.get("min_avg_amount_20d"),
            _safe_float(min_avg_amount_20d),
        ):
            blockers.append("avg_amount_20d_below_feature_gate")
        if feature_gate.get("block_limit_up_like_entry") and str(feature_values.get("limit_state") or "") == "limit_up_like":
            blockers.append("limit_up_like_entry_unfillable_feature_gate")
        if feature_gate.get("block_suspension_or_stale_proxy") and bool(
            feature_values.get("suspension_or_stale_proxy")
        ):
            blockers.append("suspension_or_stale_proxy_feature_gate")
    return not blockers, blockers


def _linear_scale_down(value: float, *, full_weight_max: float, min_weight_at: float, min_weight: float) -> float:
    if value <= full_weight_max:
        return 1.0
    if value >= min_weight_at:
        return min_weight
    denominator = max(min_weight_at - full_weight_max, 0.000001)
    progress = (value - full_weight_max) / denominator
    return 1.0 - progress * (1.0 - min_weight)


def _linear_scale_down_below(value: float, *, full_weight_min: float, min_weight_at: float, min_weight: float) -> float:
    if value >= full_weight_min:
        return 1.0
    if value <= min_weight_at:
        return min_weight
    denominator = max(full_weight_min - min_weight_at, 0.000001)
    progress = (full_weight_min - value) / denominator
    return 1.0 - progress * (1.0 - min_weight)


def _position_weight(
    feature_values: dict[str, float],
    *,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> float:
    weighting = selection_policy.get("position_weighting") if isinstance(selection_policy, dict) else None
    if not isinstance(weighting, dict) or not weighting.get("enabled"):
        return 1.0
    mode = str(weighting.get("mode") or "")
    if mode not in {
        "volatility_turnover_scaled",
        "volatility_turnover_regime_scaled",
        "conditional_regime_stock_risk_scaled",
    }:
        return 1.0
    min_weight = min(
        max(
            _safe_float(
                params.get("min_position_weight"),
                _safe_float(weighting.get("min_position_weight"), 0.35),
            ),
            0.0,
        ),
        1.0,
    )
    weak_regime = (
        feature_values.get("benchmark_return_20d", 0.0)
        < _safe_float(
            params.get("weak_regime_benchmark_return_20d_threshold"),
            _safe_float(weighting.get("weak_regime_benchmark_return_20d_threshold"), 0.0),
        )
        or feature_values.get("benchmark_volatility_20d", 0.0)
        > _safe_float(
            params.get("high_regime_benchmark_volatility_20d_threshold"),
            _safe_float(weighting.get("high_regime_benchmark_volatility_20d_threshold"), 0.08),
        )
    )
    if mode == "conditional_regime_stock_risk_scaled" and weak_regime:
        full_weight_max_volatility = _safe_float(
            params.get("weak_full_weight_max_volatility_20d_percentile"),
            _safe_float(weighting.get("weak_full_weight_max_volatility_20d_percentile"), 0.75),
        )
        full_weight_max_turnover = _safe_float(
            params.get("weak_full_weight_max_turnover_rate_percentile"),
            _safe_float(weighting.get("weak_full_weight_max_turnover_rate_percentile"), 0.80),
        )
        min_weight = min(
            max(
                _safe_float(
                    params.get("weak_regime_min_position_weight"),
                    _safe_float(weighting.get("weak_regime_min_position_weight"), min_weight),
                ),
                0.0,
            ),
            1.0,
        )
    else:
        full_weight_max_volatility = _safe_float(
            params.get("full_weight_max_volatility_20d_percentile"),
            _safe_float(weighting.get("full_weight_max_volatility_20d_percentile"), 0.80),
        )
        full_weight_max_turnover = _safe_float(
            params.get("full_weight_max_turnover_rate_percentile"),
            _safe_float(weighting.get("full_weight_max_turnover_rate_percentile"), 0.80),
        )
    volatility_scale = _linear_scale_down(
        feature_values.get("volatility_20d_percentile", 0.0),
        full_weight_max=full_weight_max_volatility,
        min_weight_at=_safe_float(
            params.get("min_weight_volatility_20d_percentile"),
            _safe_float(weighting.get("min_weight_volatility_20d_percentile"), 0.96),
        ),
        min_weight=min_weight,
    )
    turnover_scale = _linear_scale_down(
        feature_values.get("turnover_rate_percentile", 0.0),
        full_weight_max=full_weight_max_turnover,
        min_weight_at=_safe_float(
            params.get("min_weight_turnover_rate_percentile"),
            _safe_float(weighting.get("min_weight_turnover_rate_percentile"), 0.93),
        ),
        min_weight=min_weight,
    )
    scales = [volatility_scale, turnover_scale]
    if mode == "volatility_turnover_regime_scaled":
        regime_min_weight = min(
            max(
                _safe_float(
                    params.get("regime_min_position_weight"),
                    _safe_float(weighting.get("regime_min_position_weight"), min_weight),
                ),
                0.0,
            ),
            1.0,
        )
        benchmark_return_scale = _linear_scale_down_below(
            feature_values.get("benchmark_return_20d", 0.0),
            full_weight_min=_safe_float(
                params.get("full_weight_min_benchmark_return_20d"),
                _safe_float(weighting.get("full_weight_min_benchmark_return_20d"), 0.0),
            ),
            min_weight_at=_safe_float(
                params.get("min_weight_benchmark_return_20d"),
                _safe_float(weighting.get("min_weight_benchmark_return_20d"), -0.06),
            ),
            min_weight=regime_min_weight,
        )
        benchmark_volatility_scale = _linear_scale_down(
            feature_values.get("benchmark_volatility_20d", 0.0),
            full_weight_max=_safe_float(
                params.get("full_weight_max_benchmark_volatility_20d"),
                _safe_float(weighting.get("full_weight_max_benchmark_volatility_20d"), 0.04),
            ),
            min_weight_at=_safe_float(
                params.get("min_weight_benchmark_volatility_20d"),
                _safe_float(weighting.get("min_weight_benchmark_volatility_20d"), 0.08),
            ),
            min_weight=regime_min_weight,
        )
        scales.extend([benchmark_return_scale, benchmark_volatility_scale])
    return min(max(min(scales), 0.0), 1.0)


def _rank_weight_multiplier(
    rank: int,
    *,
    top_k: int,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> float:
    rank_weighting = selection_policy.get("rank_weighting") if isinstance(selection_policy, dict) else None
    if not isinstance(rank_weighting, dict) or not rank_weighting.get("enabled"):
        return 1.0
    if str(rank_weighting.get("mode") or "") != "fixed_share_profile":
        return 1.0
    profile = str(params.get("rank_weight_profile") or rank_weighting.get("profile") or "")
    profile_shares = {
        "top2_50_50": [0.50, 0.50],
        "top2_60_40": [0.60, 0.40],
        "top2_70_30": [0.70, 0.30],
        "top2_95_05": [0.95, 0.05],
        "top2_93_07": [0.93, 0.07],
        "top2_92_08": [0.92, 0.08],
        "top2_91_09": [0.91, 0.09],
        "top2_90_10": [0.90, 0.10],
        "top2_85_15": [0.85, 0.15],
        "top2_80_20": [0.80, 0.20],
        "top3_80_15_05": [0.80, 0.15, 0.05],
        "top3_70_20_10": [0.70, 0.20, 0.10],
        "top3_50_30_20": [0.50, 0.30, 0.20],
    }
    shares = profile_shares.get(profile)
    if not shares or rank < 1 or rank > len(shares):
        return 0.0
    return shares[rank - 1] * max(top_k, 1)


def _rank_weight_multipliers_for_rows(
    rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[float]:
    if not rows:
        return []
    policy = selection_policy or {}
    rank_weighting = policy.get("rank_weighting") if isinstance(policy, dict) else None
    trial_params = params or {}
    if (
        isinstance(rank_weighting, dict)
        and rank_weighting.get("enabled")
        and str(rank_weighting.get("mode") or "") == "conditional_first_rank_risk_shift"
        and len(rows) >= 2
    ):
        first_values = (
            rows[0].get("feature_values_flat")
            or rows[0].get("rank_weight_feature_values")
            or _model_feature_values(rows[0].get("feature_row") or {})
        )
        score_margin = _safe_float(rows[0].get("score")) - _safe_float(rows[1].get("score"))
        min_volatility = _safe_float(
            trial_params.get("rank1_shift_min_volatility_20d_percentile"),
            _safe_float(rank_weighting.get("rank1_shift_min_volatility_20d_percentile"), 0.80),
        )
        max_score_margin = _safe_float(
            trial_params.get("rank1_shift_max_score_margin"),
            _safe_float(rank_weighting.get("rank1_shift_max_score_margin"), 0.05),
        )
        if (
            first_values.get("volatility_20d_percentile", 0.0) >= min_volatility
            and score_margin <= max_score_margin
        ):
            shifted_params = {
                **trial_params,
                "rank_weight_profile": trial_params.get("conditional_rank_weight_profile")
                or rank_weighting.get("conditional_profile")
                or "top2_50_50",
            }
            return [
                _rank_weight_multiplier(
                    rank,
                    top_k=len(rows),
                    selection_policy={**policy, "rank_weighting": {**rank_weighting, "mode": "fixed_share_profile"}},
                    params=shifted_params,
                )
                for rank, _row in enumerate(rows, start=1)
            ]
    return [
        _rank_weight_multiplier(
            rank,
            top_k=len(rows),
            selection_policy={
                **policy,
                "rank_weighting": {**rank_weighting, "mode": "fixed_share_profile"},
            }
            if isinstance(rank_weighting, dict)
            and str(rank_weighting.get("mode") or "") == "conditional_first_rank_risk_shift"
            else policy,
            params=trial_params,
        )
        for rank, _row in enumerate(rows, start=1)
    ]


def _rank_signal_feature_values(row: dict[str, Any]) -> dict[str, Any]:
    return (
        row.get("feature_values_flat")
        or row.get("rank_weight_feature_values")
        or _model_feature_values(row.get("feature_row") or {})
    )


def _rank_segment_scope_matches(rank: int, scope: str) -> bool:
    if scope == "all_top3":
        return rank <= 3
    if scope == "rank1":
        return rank == 1
    if scope == "rank2":
        return rank == 2
    if scope == "rank3":
        return rank == 3
    if scope == "rank12":
        return rank in {1, 2}
    if scope == "rank23":
        return rank in {2, 3}
    return False


def _rank_segment_feature_value(row: dict[str, Any], values: dict[str, Any], feature: str) -> float:
    if feature == "score":
        return _safe_float(row.get("score"))
    return _safe_float(values.get(feature), _safe_float(row.get(feature)))


def _rank_segment_rule_matches(
    row: dict[str, Any],
    *,
    rank: int,
    values: dict[str, Any],
    rule: dict[str, Any],
    trial_params: dict[str, Any],
) -> bool:
    if not rule.get("enabled"):
        return False
    prefix = str(rule.get("param_prefix") or "")
    scope = str(trial_params.get(f"{prefix}_scope") or rule.get("scope") or "")
    if not _rank_segment_scope_matches(rank, scope):
        return False
    conditions = rule.get("conditions")
    if isinstance(conditions, list) and conditions:
        return all(
            isinstance(condition, dict)
            and _rank_segment_condition_matches(
                row,
                values=values,
                rule=rule,
                condition=condition,
                trial_params=trial_params,
            )
            for condition in conditions
        )
    feature = str(trial_params.get(f"{prefix}_feature") or rule.get("feature") or "")
    if not feature:
        return False
    return _rank_segment_condition_matches(
        row,
        values=values,
        rule=rule,
        condition=rule,
        trial_params=trial_params,
    )


def _rank_segment_condition_matches(
    row: dict[str, Any],
    *,
    values: dict[str, Any],
    rule: dict[str, Any],
    condition: dict[str, Any],
    trial_params: dict[str, Any],
) -> bool:
    prefix = str(rule.get("param_prefix") or "")
    feature = str(condition.get("feature") or "")
    if not feature:
        return False
    operator = str(condition.get("op") or "")
    threshold_key = str(condition.get("param_key") or "")
    threshold = _safe_float(
        _rank_segment_trial_threshold(trial_params, prefix=prefix, threshold_key=threshold_key),
        _safe_float(condition.get("threshold")),
    )
    value = _rank_segment_feature_value(row, values, feature)
    if operator == "<=":
        return value <= threshold
    if operator == ">=":
        return value >= threshold
    return False


def _rank_segment_trial_threshold(
    trial_params: dict[str, Any],
    *,
    prefix: str,
    threshold_key: str,
) -> Any:
    if threshold_key:
        if threshold_key in trial_params:
            return trial_params.get(threshold_key)
        if prefix:
            return trial_params.get(f"{prefix}_{threshold_key}")
        return None
    return trial_params.get(f"{prefix}_threshold")


def _rank_position_scale(
    row: dict[str, Any],
    *,
    rank: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    policy = selection_policy or {}
    scaling = policy.get("rank_position_scaling") if isinstance(policy, dict) else None
    if not isinstance(scaling, dict) or not scaling.get("enabled"):
        return 1.0, []
    mode = str(scaling.get("mode") or "")
    if mode != "rank1_high_momentum_low_liquidity_turnover_scale":
        return 1.0, []
    trial_params = params or {}
    values = _rank_signal_feature_values(row)
    min_benchmark_return_20d = _safe_float(
        trial_params.get("rank1_rank_scale_min_benchmark_return_20d"),
        _safe_float(scaling.get("min_benchmark_return_20d"), 0.0),
    )
    max_benchmark_return_10d = _safe_float(
        trial_params.get("rank1_rank_scale_max_benchmark_return_10d"),
        _safe_float(scaling.get("max_benchmark_return_10d"), 0.04),
    )
    min_return_5d = _safe_float(
        trial_params.get("rank1_rank_scale_min_return_5d_percentile"),
        _safe_float(scaling.get("min_return_5d_percentile"), 0.90),
    )
    min_return_20d = _safe_float(
        trial_params.get("rank1_rank_scale_min_return_20d_percentile"),
        _safe_float(scaling.get("min_return_20d_percentile"), 0.94),
    )
    min_amount = _safe_float(
        trial_params.get("rank1_rank_scale_min_amount_10d_vs_20d_percentile"),
        _safe_float(scaling.get("min_amount_10d_vs_20d_percentile"), 0.90),
    )
    min_volatility = _safe_float(
        trial_params.get("rank1_rank_scale_min_volatility_20d_percentile"),
        _safe_float(scaling.get("min_volatility_20d_percentile"), 0.55),
    )
    min_turnover = _safe_float(
        trial_params.get("rank1_rank_scale_min_turnover_rate_percentile"),
        _safe_float(scaling.get("min_turnover_rate_percentile"), 0.85),
    )
    max_avg_amount_20d = _safe_float(
        trial_params.get("rank1_rank_scale_max_avg_amount_20d"),
        _safe_float(scaling.get("max_avg_amount_20d"), 100_000_000.0),
    )
    triggered_scale = 1.0
    triggered_reasons: list[str] = []
    if rank == 1 and (
        _safe_float(values.get("benchmark_return_20d")) >= min_benchmark_return_20d
        and _safe_float(values.get("benchmark_return_10d")) <= max_benchmark_return_10d
        and _safe_float(values.get("return_5d_percentile")) >= min_return_5d
        and _safe_float(values.get("return_20d_percentile")) >= min_return_20d
        and _safe_float(values.get("amount_10d_vs_20d_percentile")) >= min_amount
        and _safe_float(values.get("volatility_20d_percentile")) >= min_volatility
        and _safe_float(values.get("turnover_rate_percentile")) >= min_turnover
        and _safe_float(values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d
    ):
        scale = min(
            max(
                _safe_float(
                    trial_params.get("rank1_rank_scale_position_scale"),
                    _safe_float(scaling.get("position_scale"), 0.0),
                ),
                0.0,
            ),
            1.0,
        )
        triggered_scale = min(triggered_scale, scale)
        triggered_reasons.append("rank1_high_momentum_low_liquidity_turnover_position_scale")
    extreme_momentum_scale = scaling.get("rank1_extreme_momentum_turnover_scale")
    if rank == 1 and isinstance(extreme_momentum_scale, dict) and extreme_momentum_scale.get("enabled"):
        extreme_min_benchmark_return_20d = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_min_benchmark_return_20d"),
            _safe_float(extreme_momentum_scale.get("min_benchmark_return_20d"), 0.03),
        )
        extreme_max_benchmark_return_10d = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_max_benchmark_return_10d"),
            _safe_float(extreme_momentum_scale.get("max_benchmark_return_10d"), 0.06),
        )
        extreme_min_return_5d = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_min_return_5d_percentile"),
            _safe_float(extreme_momentum_scale.get("min_return_5d_percentile"), 0.98),
        )
        extreme_min_return_20d = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_min_return_20d_percentile"),
            _safe_float(extreme_momentum_scale.get("min_return_20d_percentile"), 0.96),
        )
        extreme_min_amount = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_min_amount_10d_vs_20d_percentile"),
            _safe_float(extreme_momentum_scale.get("min_amount_10d_vs_20d_percentile"), 0.88),
        )
        extreme_min_volatility = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_min_volatility_20d_percentile"),
            _safe_float(extreme_momentum_scale.get("min_volatility_20d_percentile"), 0.30),
        )
        extreme_min_turnover = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_min_turnover_rate_percentile"),
            _safe_float(extreme_momentum_scale.get("min_turnover_rate_percentile"), 0.75),
        )
        extreme_max_avg_amount_20d = _safe_float(
            trial_params.get("rank1_extreme_rank_scale_max_avg_amount_20d"),
            _safe_float(extreme_momentum_scale.get("max_avg_amount_20d"), 600_000_000.0),
        )
        if (
            _safe_float(values.get("benchmark_return_20d")) >= extreme_min_benchmark_return_20d
            and _safe_float(values.get("benchmark_return_10d")) <= extreme_max_benchmark_return_10d
            and _safe_float(values.get("return_5d_percentile")) >= extreme_min_return_5d
            and _safe_float(values.get("return_20d_percentile")) >= extreme_min_return_20d
            and _safe_float(values.get("amount_10d_vs_20d_percentile")) >= extreme_min_amount
            and _safe_float(values.get("volatility_20d_percentile")) >= extreme_min_volatility
            and _safe_float(values.get("turnover_rate_percentile")) >= extreme_min_turnover
            and _safe_float(values.get("avg_amount_20d"), 999999999999.0) <= extreme_max_avg_amount_20d
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank1_extreme_rank_scale_position_scale"),
                        _safe_float(extreme_momentum_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank1_extreme_momentum_turnover_position_scale")
    neutral_chop_scale = scaling.get("rank1_neutral_chop_scale")
    if rank == 1 and isinstance(neutral_chop_scale, dict) and neutral_chop_scale.get("enabled"):
        neutral_min_benchmark_return_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_min_benchmark_return_20d"),
            _safe_float(neutral_chop_scale.get("min_benchmark_return_20d"), -0.01),
        )
        neutral_max_benchmark_return_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_max_benchmark_return_20d"),
            _safe_float(neutral_chop_scale.get("max_benchmark_return_20d"), 0.03),
        )
        neutral_max_benchmark_return_10d = _safe_float(
            trial_params.get("rank1_neutral_chop_max_benchmark_return_10d"),
            _safe_float(neutral_chop_scale.get("max_benchmark_return_10d"), 0.03),
        )
        neutral_min_benchmark_volatility_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_min_benchmark_volatility_20d"),
            _safe_float(neutral_chop_scale.get("min_benchmark_volatility_20d"), 0.04),
        )
        neutral_min_return_5d = _safe_float(
            trial_params.get("rank1_neutral_chop_min_return_5d_percentile"),
            _safe_float(neutral_chop_scale.get("min_return_5d_percentile"), 0.64),
        )
        neutral_max_return_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_max_return_20d_percentile"),
            _safe_float(neutral_chop_scale.get("max_return_20d_percentile"), 0.97),
        )
        neutral_min_amount = _safe_float(
            trial_params.get("rank1_neutral_chop_min_amount_10d_vs_20d_percentile"),
            _safe_float(neutral_chop_scale.get("min_amount_10d_vs_20d_percentile"), 0.59),
        )
        neutral_max_drawdown_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_max_drawdown_20d"),
            _safe_float(neutral_chop_scale.get("max_drawdown_20d"), -0.003),
        )
        neutral_max_avg_amount_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_max_avg_amount_20d"),
            _safe_float(neutral_chop_scale.get("max_avg_amount_20d"), 2_300_000_000.0),
        )
        benchmark_return_20d = _safe_float(values.get("benchmark_return_20d"))
        if (
            benchmark_return_20d >= neutral_min_benchmark_return_20d
            and benchmark_return_20d <= neutral_max_benchmark_return_20d
            and _safe_float(values.get("benchmark_return_10d")) <= neutral_max_benchmark_return_10d
            and _safe_float(values.get("benchmark_volatility_20d")) >= neutral_min_benchmark_volatility_20d
            and _safe_float(values.get("return_5d_percentile")) >= neutral_min_return_5d
            and _safe_float(values.get("return_20d_percentile")) <= neutral_max_return_20d
            and _safe_float(values.get("amount_10d_vs_20d_percentile")) >= neutral_min_amount
            and _safe_float(values.get("max_drawdown_20d")) <= neutral_max_drawdown_20d
            and _safe_float(values.get("avg_amount_20d"), 999999999999.0) <= neutral_max_avg_amount_20d
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank1_neutral_chop_position_scale"),
                        _safe_float(neutral_chop_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank1_neutral_chop_position_scale")
    no_drawdown_scale = scaling.get("rank1_no_drawdown_scale")
    if rank == 1 and isinstance(no_drawdown_scale, dict) and no_drawdown_scale.get("enabled"):
        no_drawdown_min_max_drawdown_20d = _safe_float(
            trial_params.get("rank1_no_drawdown_min_max_drawdown_20d"),
            _safe_float(no_drawdown_scale.get("min_max_drawdown_20d"), 0.0),
        )
        if _safe_float(values.get("max_drawdown_20d"), -999999999999.0) >= no_drawdown_min_max_drawdown_20d:
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank1_no_drawdown_position_scale"),
                        _safe_float(no_drawdown_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank1_no_drawdown_position_scale")
    high_position_pullback_scale = scaling.get("rank1_high_position_pullback_scale")
    if rank == 1 and isinstance(high_position_pullback_scale, dict) and high_position_pullback_scale.get("enabled"):
        pullback_min_max_drawdown_40d = _safe_float(
            trial_params.get("rank1_high_position_pullback_min_max_drawdown_40d"),
            _safe_float(high_position_pullback_scale.get("min_max_drawdown_40d"), -0.0439),
        )
        pullback_max_return_1d = _safe_float(
            trial_params.get("rank1_high_position_pullback_max_return_1d"),
            _safe_float(high_position_pullback_scale.get("max_return_1d"), -0.0167),
        )
        if (
            _safe_float(values.get("max_drawdown_40d"), -999999999999.0) >= pullback_min_max_drawdown_40d
            and _safe_float(values.get("return_1d"), 999999999999.0) <= pullback_max_return_1d
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank1_high_position_pullback_position_scale"),
                        _safe_float(high_position_pullback_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank1_high_position_pullback_position_scale")
    low_score_high_position_scale = scaling.get("rank1_low_score_high_position_scale")
    if rank == 1 and isinstance(low_score_high_position_scale, dict) and low_score_high_position_scale.get("enabled"):
        low_score_high_position_max_score = _safe_float(
            trial_params.get("rank1_low_score_high_position_max_score"),
            _safe_float(low_score_high_position_scale.get("max_score"), 3.3879),
        )
        low_score_high_position_min_distance_from_40d_high = _safe_float(
            trial_params.get("rank1_low_score_high_position_min_distance_from_40d_high"),
            _safe_float(low_score_high_position_scale.get("min_distance_from_40d_high"), -0.0021),
        )
        if (
            _safe_float(row.get("score"), 999999999999.0) <= low_score_high_position_max_score
            and _safe_float(values.get("distance_from_40d_high"), -999999999999.0)
            >= low_score_high_position_min_distance_from_40d_high
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank1_low_score_high_position_position_scale"),
                        _safe_float(low_score_high_position_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank1_low_score_high_position_position_scale")
    benchmark_momentum_pullback_scale = scaling.get("rank1_benchmark_momentum_pullback_scale")
    if (
        rank == 1
        and isinstance(benchmark_momentum_pullback_scale, dict)
        and benchmark_momentum_pullback_scale.get("enabled")
    ):
        benchmark_momentum_pullback_min_benchmark_return_10d = _safe_float(
            trial_params.get("rank1_benchmark_momentum_pullback_min_benchmark_return_10d"),
            _safe_float(benchmark_momentum_pullback_scale.get("min_benchmark_return_10d"), 0.0203),
        )
        benchmark_momentum_pullback_min_return_20d_percentile = _safe_float(
            trial_params.get("rank1_benchmark_momentum_pullback_min_return_20d_percentile"),
            _safe_float(benchmark_momentum_pullback_scale.get("min_return_20d_percentile"), 0.9819),
        )
        benchmark_momentum_pullback_max_return_1d = _safe_float(
            trial_params.get("rank1_benchmark_momentum_pullback_max_return_1d"),
            _safe_float(benchmark_momentum_pullback_scale.get("max_return_1d"), -0.0144),
        )
        if (
            _safe_float(values.get("benchmark_return_10d")) >= benchmark_momentum_pullback_min_benchmark_return_10d
            and _safe_float(values.get("return_20d_percentile")) >= benchmark_momentum_pullback_min_return_20d_percentile
            and _safe_float(values.get("return_1d"), 999999999999.0)
            <= benchmark_momentum_pullback_max_return_1d
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank1_benchmark_momentum_pullback_position_scale"),
                        _safe_float(benchmark_momentum_pullback_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank1_benchmark_momentum_pullback_position_scale")
    rank2_momentum_scale = scaling.get("rank2_high_momentum_turnover_scale")
    if rank == 2 and isinstance(rank2_momentum_scale, dict) and rank2_momentum_scale.get("enabled"):
        rank2_min_benchmark_return_20d = _safe_float(
            trial_params.get("rank2_rank_scale_min_benchmark_return_20d"),
            _safe_float(rank2_momentum_scale.get("min_benchmark_return_20d"), 0.0),
        )
        rank2_max_benchmark_return_10d = _safe_float(
            trial_params.get("rank2_rank_scale_max_benchmark_return_10d"),
            _safe_float(rank2_momentum_scale.get("max_benchmark_return_10d"), 0.02),
        )
        rank2_min_return_5d = _safe_float(
            trial_params.get("rank2_rank_scale_min_return_5d_percentile"),
            _safe_float(rank2_momentum_scale.get("min_return_5d_percentile"), 0.94),
        )
        rank2_min_return_20d = _safe_float(
            trial_params.get("rank2_rank_scale_min_return_20d_percentile"),
            _safe_float(rank2_momentum_scale.get("min_return_20d_percentile"), 0.90),
        )
        rank2_min_amount = _safe_float(
            trial_params.get("rank2_rank_scale_min_amount_10d_vs_20d_percentile"),
            _safe_float(rank2_momentum_scale.get("min_amount_10d_vs_20d_percentile"), 0.94),
        )
        rank2_min_volatility = _safe_float(
            trial_params.get("rank2_rank_scale_min_volatility_20d_percentile"),
            _safe_float(rank2_momentum_scale.get("min_volatility_20d_percentile"), 0.55),
        )
        rank2_min_turnover = _safe_float(
            trial_params.get("rank2_rank_scale_min_turnover_rate_percentile"),
            _safe_float(rank2_momentum_scale.get("min_turnover_rate_percentile"), 0.85),
        )
        rank2_max_avg_amount_20d = _safe_float(
            trial_params.get("rank2_rank_scale_max_avg_amount_20d"),
            _safe_float(rank2_momentum_scale.get("max_avg_amount_20d"), 800_000_000.0),
        )
        if (
            _safe_float(values.get("benchmark_return_20d")) >= rank2_min_benchmark_return_20d
            and _safe_float(values.get("benchmark_return_10d")) <= rank2_max_benchmark_return_10d
            and _safe_float(values.get("return_5d_percentile")) >= rank2_min_return_5d
            and _safe_float(values.get("return_20d_percentile")) >= rank2_min_return_20d
            and _safe_float(values.get("amount_10d_vs_20d_percentile")) >= rank2_min_amount
            and _safe_float(values.get("volatility_20d_percentile")) >= rank2_min_volatility
            and _safe_float(values.get("turnover_rate_percentile")) >= rank2_min_turnover
            and _safe_float(values.get("avg_amount_20d"), 999999999999.0) <= rank2_max_avg_amount_20d
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank2_rank_scale_position_scale"),
                        _safe_float(rank2_momentum_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank2_high_momentum_turnover_position_scale")
    rank3_momentum_scale = scaling.get("rank3_high_momentum_turnover_scale")
    if rank == 3 and isinstance(rank3_momentum_scale, dict) and rank3_momentum_scale.get("enabled"):
        rank3_min_benchmark_return_20d = _safe_float(
            trial_params.get("rank3_rank_scale_min_benchmark_return_20d"),
            _safe_float(rank3_momentum_scale.get("min_benchmark_return_20d"), 0.03),
        )
        rank3_max_benchmark_return_10d = _safe_float(
            trial_params.get("rank3_rank_scale_max_benchmark_return_10d"),
            _safe_float(rank3_momentum_scale.get("max_benchmark_return_10d"), 0.06),
        )
        rank3_min_return_5d = _safe_float(
            trial_params.get("rank3_rank_scale_min_return_5d_percentile"),
            _safe_float(rank3_momentum_scale.get("min_return_5d_percentile"), 0.96),
        )
        rank3_min_return_20d = _safe_float(
            trial_params.get("rank3_rank_scale_min_return_20d_percentile"),
            _safe_float(rank3_momentum_scale.get("min_return_20d_percentile"), 0.90),
        )
        rank3_min_amount = _safe_float(
            trial_params.get("rank3_rank_scale_min_amount_10d_vs_20d_percentile"),
            _safe_float(rank3_momentum_scale.get("min_amount_10d_vs_20d_percentile"), 0.90),
        )
        rank3_min_volatility = _safe_float(
            trial_params.get("rank3_rank_scale_min_volatility_20d_percentile"),
            _safe_float(rank3_momentum_scale.get("min_volatility_20d_percentile"), 0.75),
        )
        rank3_min_turnover = _safe_float(
            trial_params.get("rank3_rank_scale_min_turnover_rate_percentile"),
            _safe_float(rank3_momentum_scale.get("min_turnover_rate_percentile"), 0.75),
        )
        rank3_max_avg_amount_20d = _safe_float(
            trial_params.get("rank3_rank_scale_max_avg_amount_20d"),
            _safe_float(rank3_momentum_scale.get("max_avg_amount_20d"), 800_000_000.0),
        )
        if (
            _safe_float(values.get("benchmark_return_20d")) >= rank3_min_benchmark_return_20d
            and _safe_float(values.get("benchmark_return_10d")) <= rank3_max_benchmark_return_10d
            and _safe_float(values.get("return_5d_percentile")) >= rank3_min_return_5d
            and _safe_float(values.get("return_20d_percentile")) >= rank3_min_return_20d
            and _safe_float(values.get("amount_10d_vs_20d_percentile")) >= rank3_min_amount
            and _safe_float(values.get("volatility_20d_percentile")) >= rank3_min_volatility
            and _safe_float(values.get("turnover_rate_percentile")) >= rank3_min_turnover
            and _safe_float(values.get("avg_amount_20d"), 999999999999.0) <= rank3_max_avg_amount_20d
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("rank3_rank_scale_position_scale"),
                        _safe_float(rank3_momentum_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append("rank3_high_momentum_turnover_position_scale")
    segment_rules = scaling.get("segment_risk_scale_rules")
    if isinstance(segment_rules, list):
        for rule in segment_rules:
            if not isinstance(rule, dict) or not _rank_segment_rule_matches(
                row,
                rank=rank,
                values=values,
                rule=rule,
                trial_params=trial_params,
            ):
                continue
            prefix = str(rule.get("param_prefix") or "")
            scale = min(
                max(
                    _safe_float(
                        trial_params.get(f"{prefix}_position_scale"),
                        _safe_float(rule.get("position_scale"), 1.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            triggered_scale = min(triggered_scale, scale)
            triggered_reasons.append(str(rule.get("reason") or "segment_risk_position_scale"))
    return triggered_scale, triggered_reasons


def _rank_position_scales_for_rows(
    rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[tuple[float, list[str]]]:
    return [
        _rank_position_scale(row, rank=index + 1, selection_policy=selection_policy, params=params)
        for index, row in enumerate(rows)
    ]


def _rank_portfolio_adjustment_multiplier(
    row: dict[str, Any],
    *,
    rank: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    policy = selection_policy or {}
    adjustment = policy.get("rank_portfolio_adjustment") if isinstance(policy, dict) else None
    if not isinstance(adjustment, dict) or not adjustment.get("enabled"):
        return 1.0, []
    if str(adjustment.get("mode") or "") != "multiplicative_segment_rules":
        return 1.0, []
    rules = adjustment.get("rules")
    if not isinstance(rules, list):
        return 1.0, []
    trial_params = params or {}
    values = _rank_signal_feature_values(row)
    multiplier = 1.0
    reasons: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict) or not _rank_segment_rule_matches(
            row,
            rank=rank,
            values=values,
            rule=rule,
            trial_params=trial_params,
        ):
            continue
        prefix = str(rule.get("param_prefix") or "")
        raw_multiplier = _safe_float(
            trial_params.get(f"{prefix}_multiplier"),
            _safe_float(rule.get("multiplier"), 1.0),
        )
        multiplier *= min(max(raw_multiplier, 0.0), 2.0)
        reasons.append(str(rule.get("reason") or "rank_portfolio_adjustment_multiplier"))
    return multiplier, reasons


def _rank_portfolio_adjustment_multipliers_for_rows(
    rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[tuple[float, list[str]]]:
    return [
        _rank_portfolio_adjustment_multiplier(row, rank=index + 1, selection_policy=selection_policy, params=params)
        for index, row in enumerate(rows)
    ]


def _date_exposure_scale(
    gross_exposure: float,
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[float, list[str], float | None]:
    policy = selection_policy or {}
    scaling = policy.get("date_exposure_scaling") if isinstance(policy, dict) else None
    if not isinstance(scaling, dict) or not scaling.get("enabled"):
        return 1.0, [], None
    mode = str(scaling.get("mode") or "")
    if mode != "gross_exposure_floor_linear_scale":
        return 1.0, [], None
    trial_params = params or {}
    floor = _safe_float(
        trial_params.get("date_gross_exposure_floor"),
        _safe_float(scaling.get("gross_exposure_floor"), 0.0),
    )
    if floor <= 0 or gross_exposure >= floor:
        return 1.0, [], floor if floor > 0 else None
    scale = max(0.0, min(gross_exposure / floor, 1.0))
    return scale, ["gross_exposure_floor_linear_scale"], floor


def _selected_exhaustion_date_position_scale(
    selected_rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    policy = selection_policy or {}
    scaling = policy.get("selected_exhaustion_date_scale") if isinstance(policy, dict) else None
    if not isinstance(scaling, dict) or not scaling.get("enabled"):
        return 1.0, []
    trial_params = params or {}
    min_return_20d = _safe_float(
        trial_params.get("selected_exhaustion_min_return_20d_percentile"),
        _safe_float(scaling.get("min_return_20d_percentile"), 0.95),
    )
    min_return_5d = _safe_float(
        trial_params.get("selected_exhaustion_min_return_5d_percentile"),
        _safe_float(scaling.get("min_return_5d_percentile"), 0.98),
    )
    min_amount = _safe_float(
        trial_params.get("selected_exhaustion_min_amount_percentile"),
        _safe_float(scaling.get("min_amount_percentile"), 0.90),
    )
    min_turnover = _safe_float(
        trial_params.get("selected_exhaustion_min_turnover_rate_percentile"),
        _safe_float(scaling.get("min_turnover_rate_percentile"), 0.65),
    )
    min_industry_return = _safe_float(
        trial_params.get("selected_exhaustion_min_industry_return_20d_excess"),
        _safe_float(scaling.get("min_industry_return_20d_excess"), 0.10),
    )
    max_industry_return = _safe_float(
        trial_params.get("selected_exhaustion_max_industry_return_20d_excess"),
        _safe_float(scaling.get("max_industry_return_20d_excess"), 0.19747611716278968),
    )
    max_distance = _safe_float(
        trial_params.get("selected_exhaustion_max_distance_from_20d_high"),
        _safe_float(scaling.get("max_distance_from_20d_high"), -0.02),
    )
    max_benchmark_return = _safe_float(
        trial_params.get("selected_exhaustion_max_benchmark_return_20d"),
        _safe_float(scaling.get("max_benchmark_return_20d"), 0.03),
    )
    for row in selected_rows:
        values = _rank_signal_feature_values(row)
        amount_percentile = max(
            _safe_float(values.get("amount_10d_vs_20d_percentile")),
            _safe_float(values.get("amount_vs_20d_avg_percentile")),
        )
        industry_return = _safe_float(values.get("industry_return_20d_excess"))
        if (
            _safe_float(values.get("return_20d_percentile")) >= min_return_20d
            and _safe_float(values.get("return_5d_percentile")) >= min_return_5d
            and amount_percentile >= min_amount
            and _safe_float(values.get("turnover_rate_percentile")) >= min_turnover
            and industry_return >= min_industry_return
            and industry_return <= max_industry_return
            and _safe_float(values.get("distance_from_20d_high")) <= max_distance
            and _safe_float(values.get("benchmark_return_20d")) <= max_benchmark_return
        ):
            scale = min(
                max(
                    _safe_float(
                        trial_params.get("selected_exhaustion_date_position_scale"),
                        _safe_float(scaling.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            return scale, ["selected_exhaustion_medium_industry_pullback_date_scale"]
    return 1.0, []


def _selected_exposure_context(
    selected_rows: list[dict[str, Any]],
    *,
    ordered_rows: list[dict[str, Any]] | None = None,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not selected_rows:
        return {
            "rank_multipliers": [],
            "rank_position_scales": [],
            "rank_portfolio_adjustment_multipliers": [],
            "signal_scale": 1.0,
            "signal_scale_reasons": [],
            "base_gross_exposure": 0.0,
            "date_exposure_scale": 1.0,
            "date_exposure_scale_reasons": [],
            "date_exposure_floor": None,
            "date_position_scale": 1.0,
            "date_position_scale_reasons": [],
        }
    policy = selection_policy or {}
    trial_params = params or {}
    rank_multipliers = _rank_weight_multipliers_for_rows(
        selected_rows,
        selection_policy=policy,
        params=trial_params,
    )
    signal_scale, signal_scale_reasons = _signal_position_scale(
        ordered_rows or selected_rows,
        selection_policy=policy,
        params=trial_params,
    )
    rank_position_scales = _rank_position_scales_for_rows(
        selected_rows,
        selection_policy=policy,
        params=trial_params,
    )
    rank_portfolio_adjustments = _rank_portfolio_adjustment_multipliers_for_rows(
        selected_rows,
        selection_policy=policy,
        params=trial_params,
    )
    base_gross_exposure = (
        mean(
            _safe_float(row.get("portfolio_weight"), 1.0)
            * rank_multipliers[index]
            * (rank_position_scales[index][0] if index < len(rank_position_scales) else 1.0)
            for index, row in enumerate(selected_rows)
        )
        * signal_scale
    )
    date_scale, date_scale_reasons, date_floor = _date_exposure_scale(
        base_gross_exposure,
        selection_policy=policy,
        params=trial_params,
    )
    selected_date_scale, selected_date_scale_reasons = _selected_exhaustion_date_position_scale(
        selected_rows,
        selection_policy=policy,
        params=trial_params,
    )
    date_position_scale = date_scale * selected_date_scale
    date_position_scale_reasons = [*date_scale_reasons, *selected_date_scale_reasons]
    return {
        "rank_multipliers": rank_multipliers,
        "rank_position_scales": rank_position_scales,
        "rank_portfolio_adjustment_multipliers": rank_portfolio_adjustments,
        "signal_scale": signal_scale,
        "signal_scale_reasons": signal_scale_reasons,
        "base_gross_exposure": base_gross_exposure,
        "date_exposure_scale": date_scale,
        "date_exposure_scale_reasons": date_scale_reasons,
        "date_exposure_floor": date_floor,
        "date_position_scale": date_position_scale,
        "date_position_scale_reasons": date_position_scale_reasons,
    }


def _rank_signal_feature_subset(feature_values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: feature_values.get(key)
        for key in (
            "volatility_20d_percentile",
            "return_20d_percentile",
            "return_5d_percentile",
            "amount_10d_vs_20d_percentile",
            "amount_vs_20d_avg_percentile",
            "benchmark_return_20d",
            "benchmark_return_10d",
            "benchmark_volatility_20d",
            "distance_from_20d_high",
            "industry_return_20d_excess",
            "low_volatility_percentile",
            "avg_amount_20d",
            "total_mv",
            "circ_mv",
            "pe_ttm",
            "pb",
            "total_mv_percentile",
            "circ_mv_percentile",
            "small_total_mv_percentile",
            "small_circ_mv_percentile",
            "pe_ttm_percentile",
            "pb_percentile",
            "turnover_rate_percentile",
            "max_drawdown_20d",
            "max_drawdown_40d",
            "distance_from_40d_high",
            "return_1d",
        )
    }


def _signal_cash_switch_block_reasons(
    ordered_rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[str]:
    if len(ordered_rows) < 2:
        return []
    policy = selection_policy or {}
    signal_cash_switch = policy.get("signal_cash_switch") if isinstance(policy, dict) else None
    if not isinstance(signal_cash_switch, dict) or not signal_cash_switch.get("enabled"):
        return []
    mode = str(signal_cash_switch.get("mode") or "")
    if mode not in {
        "rank1_overheat_reversal_cash",
        "rank1_overheat_or_weak_regime_low_volatility_cash",
        "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_cash",
        "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_volume_tail_cash",
        "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_weak_low_liquidity_tail_cash",
        (
            "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
            "weak_low_liquidity_or_congested_momentum_tail_cash"
        ),
        (
            "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
            "weak_low_liquidity_or_congested_momentum_or_high_turnover_momentum_tail_cash"
        ),
        (
            "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
            "weak_low_liquidity_or_congested_momentum_or_weak_defensive_grind_tail_cash"
        ),
    }:
        return []
    trial_params = params or {}
    first_values = _rank_signal_feature_values(ordered_rows[0])
    score_margin = _safe_float(ordered_rows[0].get("score")) - _safe_float(ordered_rows[1].get("score"))
    max_score_margin = _safe_float(
        trial_params.get("rank1_overheat_max_score_margin"),
        _safe_float(signal_cash_switch.get("rank1_overheat_max_score_margin"), 0.03),
    )
    min_return_20d_percentile = _safe_float(
        trial_params.get("rank1_overheat_min_return_20d_percentile"),
        _safe_float(signal_cash_switch.get("rank1_overheat_min_return_20d_percentile"), 0.98),
    )
    min_return_5d_percentile = _safe_float(
        trial_params.get("rank1_overheat_min_return_5d_percentile"),
        _safe_float(signal_cash_switch.get("rank1_overheat_min_return_5d_percentile"), 0.90),
    )
    min_benchmark_return_20d = _safe_float(
        trial_params.get("rank1_overheat_min_benchmark_return_20d"),
        _safe_float(signal_cash_switch.get("rank1_overheat_min_benchmark_return_20d"), 0.04),
    )
    min_amount_percentile_raw = trial_params.get(
        "rank1_overheat_min_amount_10d_vs_20d_percentile",
        signal_cash_switch.get("rank1_overheat_min_amount_10d_vs_20d_percentile"),
    )
    min_amount_percentile = None if min_amount_percentile_raw is None else _safe_float(min_amount_percentile_raw)
    if (
        score_margin <= max_score_margin
        and _safe_float(first_values.get("return_20d_percentile")) >= min_return_20d_percentile
        and _safe_float(first_values.get("return_5d_percentile")) >= min_return_5d_percentile
        and _safe_float(first_values.get("benchmark_return_20d")) >= min_benchmark_return_20d
        and (
            min_amount_percentile is None
            or _safe_float(first_values.get("amount_10d_vs_20d_percentile")) >= min_amount_percentile
        )
    ):
        return ["rank1_overheat_reversal_cash_switch"]
    market_euphoric_volume_tail_cash = signal_cash_switch.get("rank1_market_euphoric_volume_tail_cash")
    if isinstance(market_euphoric_volume_tail_cash, dict) and market_euphoric_volume_tail_cash.get("enabled"):
        min_benchmark_return_20d_tail = _safe_float(
            trial_params.get("rank1_tail_min_benchmark_return_20d"),
            _safe_float(market_euphoric_volume_tail_cash.get("min_benchmark_return_20d"), 0.04),
        )
        min_return_5d_tail = _safe_float(
            trial_params.get("rank1_tail_min_return_5d_percentile"),
            _safe_float(market_euphoric_volume_tail_cash.get("min_return_5d_percentile"), 0.98),
        )
        min_return_20d_tail = _safe_float(
            trial_params.get("rank1_tail_min_return_20d_percentile"),
            _safe_float(market_euphoric_volume_tail_cash.get("min_return_20d_percentile"), 0.94),
        )
        min_amount_tail = _safe_float(
            trial_params.get("rank1_tail_min_amount_10d_vs_20d_percentile"),
            _safe_float(market_euphoric_volume_tail_cash.get("min_amount_10d_vs_20d_percentile"), 0.90),
        )
        min_volatility_tail = _safe_float(
            trial_params.get("rank1_tail_min_volatility_20d_percentile"),
            _safe_float(market_euphoric_volume_tail_cash.get("min_volatility_20d_percentile"), 0.55),
        )
        max_avg_amount_20d_raw = trial_params.get(
            "rank1_tail_max_avg_amount_20d",
            market_euphoric_volume_tail_cash.get("max_avg_amount_20d"),
        )
        max_avg_amount_20d = None if max_avg_amount_20d_raw is None else _safe_float(max_avg_amount_20d_raw)
        if (
            _safe_float(first_values.get("benchmark_return_20d")) >= min_benchmark_return_20d_tail
            and _safe_float(first_values.get("return_5d_percentile")) >= min_return_5d_tail
            and _safe_float(first_values.get("return_20d_percentile")) >= min_return_20d_tail
            and _safe_float(first_values.get("amount_10d_vs_20d_percentile")) >= min_amount_tail
            and _safe_float(first_values.get("volatility_20d_percentile")) >= min_volatility_tail
            and (
                max_avg_amount_20d is None
                or _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d
            )
        ):
            return ["rank1_market_euphoric_volume_tail_cash_switch"]
    weak_low_volatility = signal_cash_switch.get("weak_regime_low_volatility_cash")
    if isinstance(weak_low_volatility, dict) and weak_low_volatility.get("enabled"):
        max_benchmark_return_10d = _safe_float(
            trial_params.get("weak_low_vol_max_benchmark_return_10d"),
            _safe_float(weak_low_volatility.get("max_benchmark_return_10d"), -0.02),
        )
        min_benchmark_volatility_20d = _safe_float(
            trial_params.get("weak_low_vol_min_benchmark_volatility_20d"),
            _safe_float(weak_low_volatility.get("min_benchmark_volatility_20d"), 0.035),
        )
        min_low_volatility_percentile = _safe_float(
            trial_params.get("weak_low_vol_min_low_volatility_percentile"),
            _safe_float(weak_low_volatility.get("min_low_volatility_percentile"), 0.95),
        )
        if (
            _safe_float(first_values.get("benchmark_return_10d")) <= max_benchmark_return_10d
            and _safe_float(first_values.get("benchmark_volatility_20d")) >= min_benchmark_volatility_20d
            and _safe_float(first_values.get("low_volatility_percentile")) >= min_low_volatility_percentile
        ):
            return ["weak_regime_low_volatility_cash_switch"]
    weak_low_liquidity_tail_cash = signal_cash_switch.get("rank1_weak_low_liquidity_tail_cash")
    if isinstance(weak_low_liquidity_tail_cash, dict) and weak_low_liquidity_tail_cash.get("enabled"):
        max_benchmark_return_20d_tail = _safe_float(
            trial_params.get("rank1_weak_tail_max_benchmark_return_20d"),
            _safe_float(weak_low_liquidity_tail_cash.get("max_benchmark_return_20d"), -0.04),
        )
        max_benchmark_return_10d_raw = trial_params.get(
            "rank1_weak_tail_max_benchmark_return_10d",
            weak_low_liquidity_tail_cash.get("max_benchmark_return_10d"),
        )
        max_benchmark_return_10d_tail = (
            None if max_benchmark_return_10d_raw is None else _safe_float(max_benchmark_return_10d_raw)
        )
        min_low_volatility_tail = _safe_float(
            trial_params.get("rank1_weak_tail_min_low_volatility_percentile"),
            _safe_float(weak_low_liquidity_tail_cash.get("min_low_volatility_percentile"), 0.97),
        )
        max_turnover_tail = _safe_float(
            trial_params.get("rank1_weak_tail_max_turnover_rate_percentile"),
            _safe_float(weak_low_liquidity_tail_cash.get("max_turnover_rate_percentile"), 0.05),
        )
        max_avg_amount_20d_tail_raw = trial_params.get(
            "rank1_weak_tail_max_avg_amount_20d",
            weak_low_liquidity_tail_cash.get("max_avg_amount_20d"),
        )
        max_avg_amount_20d_tail = (
            None if max_avg_amount_20d_tail_raw is None else _safe_float(max_avg_amount_20d_tail_raw)
        )
        if (
            _safe_float(first_values.get("benchmark_return_20d")) <= max_benchmark_return_20d_tail
            and (
                max_benchmark_return_10d_tail is None
                or _safe_float(first_values.get("benchmark_return_10d")) <= max_benchmark_return_10d_tail
            )
            and _safe_float(first_values.get("low_volatility_percentile")) >= min_low_volatility_tail
            and _safe_float(first_values.get("turnover_rate_percentile"), 999999999999.0) <= max_turnover_tail
            and (
                max_avg_amount_20d_tail is None
                or _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d_tail
            )
        ):
            return ["rank1_weak_low_liquidity_tail_cash_switch"]
    weak_defensive_grind_tail_cash = signal_cash_switch.get("rank1_weak_defensive_grind_tail_cash")
    if isinstance(weak_defensive_grind_tail_cash, dict) and weak_defensive_grind_tail_cash.get("enabled"):
        max_benchmark_return_20d_grind = _safe_float(
            trial_params.get("rank1_weak_grind_max_benchmark_return_20d"),
            _safe_float(weak_defensive_grind_tail_cash.get("max_benchmark_return_20d"), -0.02),
        )
        max_benchmark_return_10d_grind = _safe_float(
            trial_params.get("rank1_weak_grind_max_benchmark_return_10d"),
            _safe_float(weak_defensive_grind_tail_cash.get("max_benchmark_return_10d"), 0.005),
        )
        max_benchmark_volatility_20d_raw = trial_params.get(
            "rank1_weak_grind_max_benchmark_volatility_20d",
            weak_defensive_grind_tail_cash.get("max_benchmark_volatility_20d"),
        )
        max_benchmark_volatility_20d_grind = (
            None if max_benchmark_volatility_20d_raw is None else _safe_float(max_benchmark_volatility_20d_raw)
        )
        min_low_volatility_grind = _safe_float(
            trial_params.get("rank1_weak_grind_min_low_volatility_percentile"),
            _safe_float(weak_defensive_grind_tail_cash.get("min_low_volatility_percentile"), 0.99),
        )
        max_turnover_grind = _safe_float(
            trial_params.get("rank1_weak_grind_max_turnover_rate_percentile"),
            _safe_float(weak_defensive_grind_tail_cash.get("max_turnover_rate_percentile"), 0.05),
        )
        max_avg_amount_20d_grind_raw = trial_params.get(
            "rank1_weak_grind_max_avg_amount_20d",
            weak_defensive_grind_tail_cash.get("max_avg_amount_20d"),
        )
        max_avg_amount_20d_grind = (
            None if max_avg_amount_20d_grind_raw is None else _safe_float(max_avg_amount_20d_grind_raw)
        )
        if (
            _safe_float(first_values.get("benchmark_return_20d")) <= max_benchmark_return_20d_grind
            and _safe_float(first_values.get("benchmark_return_10d")) <= max_benchmark_return_10d_grind
            and (
                max_benchmark_volatility_20d_grind is None
                or _safe_float(first_values.get("benchmark_volatility_20d")) <= max_benchmark_volatility_20d_grind
            )
            and _safe_float(first_values.get("low_volatility_percentile")) >= min_low_volatility_grind
            and _safe_float(first_values.get("turnover_rate_percentile"), 999999999999.0) <= max_turnover_grind
            and (
                max_avg_amount_20d_grind is None
                or _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d_grind
            )
        ):
            return ["rank1_weak_defensive_grind_tail_cash_switch"]
    congested_momentum_tail_cash = signal_cash_switch.get("rank1_congested_low_liquidity_momentum_tail_cash")
    if isinstance(congested_momentum_tail_cash, dict) and congested_momentum_tail_cash.get("enabled"):
        min_benchmark_return_20d_tail = _safe_float(
            trial_params.get("rank1_congested_tail_min_benchmark_return_20d"),
            _safe_float(congested_momentum_tail_cash.get("min_benchmark_return_20d"), -0.02),
        )
        max_benchmark_return_10d_tail = _safe_float(
            trial_params.get("rank1_congested_tail_max_benchmark_return_10d"),
            _safe_float(congested_momentum_tail_cash.get("max_benchmark_return_10d"), 0.01),
        )
        min_return_5d_tail = _safe_float(
            trial_params.get("rank1_congested_tail_min_return_5d_percentile"),
            _safe_float(congested_momentum_tail_cash.get("min_return_5d_percentile"), 0.94),
        )
        min_return_20d_tail = _safe_float(
            trial_params.get("rank1_congested_tail_min_return_20d_percentile"),
            _safe_float(congested_momentum_tail_cash.get("min_return_20d_percentile"), 0.90),
        )
        min_amount_tail = _safe_float(
            trial_params.get("rank1_congested_tail_min_amount_10d_vs_20d_percentile"),
            _safe_float(congested_momentum_tail_cash.get("min_amount_10d_vs_20d_percentile"), 0.88),
        )
        min_volatility_tail = _safe_float(
            trial_params.get("rank1_congested_tail_min_volatility_20d_percentile"),
            _safe_float(congested_momentum_tail_cash.get("min_volatility_20d_percentile"), 0.55),
        )
        max_avg_amount_20d_tail = _safe_float(
            trial_params.get("rank1_congested_tail_max_avg_amount_20d"),
            _safe_float(congested_momentum_tail_cash.get("max_avg_amount_20d"), 100_000_000.0),
        )
        if (
            _safe_float(first_values.get("benchmark_return_20d")) >= min_benchmark_return_20d_tail
            and _safe_float(first_values.get("benchmark_return_10d")) <= max_benchmark_return_10d_tail
            and _safe_float(first_values.get("return_5d_percentile")) >= min_return_5d_tail
            and _safe_float(first_values.get("return_20d_percentile")) >= min_return_20d_tail
            and _safe_float(first_values.get("amount_10d_vs_20d_percentile")) >= min_amount_tail
            and _safe_float(first_values.get("volatility_20d_percentile")) >= min_volatility_tail
            and _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d_tail
        ):
            return ["rank1_congested_low_liquidity_momentum_tail_cash_switch"]
    high_turnover_momentum_tail_cash = signal_cash_switch.get("rank1_high_turnover_momentum_tail_cash")
    if isinstance(high_turnover_momentum_tail_cash, dict) and high_turnover_momentum_tail_cash.get("enabled"):
        min_benchmark_return_20d_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_min_benchmark_return_20d"),
            _safe_float(high_turnover_momentum_tail_cash.get("min_benchmark_return_20d"), 0.0),
        )
        max_benchmark_return_10d_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_max_benchmark_return_10d"),
            _safe_float(high_turnover_momentum_tail_cash.get("max_benchmark_return_10d"), 0.02),
        )
        min_return_5d_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_min_return_5d_percentile"),
            _safe_float(high_turnover_momentum_tail_cash.get("min_return_5d_percentile"), 0.98),
        )
        min_return_20d_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_min_return_20d_percentile"),
            _safe_float(high_turnover_momentum_tail_cash.get("min_return_20d_percentile"), 0.94),
        )
        min_amount_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_min_amount_10d_vs_20d_percentile"),
            _safe_float(high_turnover_momentum_tail_cash.get("min_amount_10d_vs_20d_percentile"), 0.95),
        )
        min_volatility_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_min_volatility_20d_percentile"),
            _safe_float(high_turnover_momentum_tail_cash.get("min_volatility_20d_percentile"), 0.65),
        )
        min_turnover_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_min_turnover_rate_percentile"),
            _safe_float(high_turnover_momentum_tail_cash.get("min_turnover_rate_percentile"), 0.85),
        )
        max_avg_amount_20d_tail = _safe_float(
            trial_params.get("rank1_high_turnover_tail_max_avg_amount_20d"),
            _safe_float(high_turnover_momentum_tail_cash.get("max_avg_amount_20d"), 300_000_000.0),
        )
        if (
            _safe_float(first_values.get("benchmark_return_20d")) >= min_benchmark_return_20d_tail
            and _safe_float(first_values.get("benchmark_return_10d")) <= max_benchmark_return_10d_tail
            and _safe_float(first_values.get("return_5d_percentile")) >= min_return_5d_tail
            and _safe_float(first_values.get("return_20d_percentile")) >= min_return_20d_tail
            and _safe_float(first_values.get("amount_10d_vs_20d_percentile")) >= min_amount_tail
            and _safe_float(first_values.get("volatility_20d_percentile")) >= min_volatility_tail
            and _safe_float(first_values.get("turnover_rate_percentile")) >= min_turnover_tail
            and _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d_tail
        ):
            return ["rank1_high_turnover_momentum_tail_cash_switch"]
    high_confidence_cash = signal_cash_switch.get("rank1_high_confidence_cash")
    if isinstance(high_confidence_cash, dict) and high_confidence_cash.get("enabled"):
        min_score_margin = _safe_float(
            trial_params.get("rank1_high_confidence_min_score_margin"),
            _safe_float(high_confidence_cash.get("min_score_margin"), 0.10),
        )
        if score_margin >= min_score_margin:
            return ["rank1_high_confidence_cash_switch"]
    return []


def _signal_position_scale(
    ordered_rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    if not ordered_rows:
        return 1.0, []
    policy = selection_policy or {}
    scaling = policy.get("signal_position_scaling") if isinstance(policy, dict) else None
    if not isinstance(scaling, dict) or not scaling.get("enabled"):
        return 1.0, []
    mode = str(scaling.get("mode") or "")
    if mode != "rank1_weak_defensive_grind_scale":
        return 1.0, []
    trial_params = params or {}
    first_values = _rank_signal_feature_values(ordered_rows[0])
    scale = 1.0
    reasons: list[str] = []
    max_benchmark_return_20d = _safe_float(
        trial_params.get("rank1_weak_grind_max_benchmark_return_20d"),
        _safe_float(scaling.get("max_benchmark_return_20d"), -0.04),
    )
    max_benchmark_return_10d = _safe_float(
        trial_params.get("rank1_weak_grind_max_benchmark_return_10d"),
        _safe_float(scaling.get("max_benchmark_return_10d"), 0.01),
    )
    min_low_volatility = _safe_float(
        trial_params.get("rank1_weak_grind_min_low_volatility_percentile"),
        _safe_float(scaling.get("min_low_volatility_percentile"), 0.98),
    )
    max_turnover = _safe_float(
        trial_params.get("rank1_weak_grind_max_turnover_rate_percentile"),
        _safe_float(scaling.get("max_turnover_rate_percentile"), 0.07),
    )
    max_avg_amount_20d_raw = trial_params.get(
        "rank1_weak_grind_max_avg_amount_20d",
        scaling.get("max_avg_amount_20d"),
    )
    max_avg_amount_20d = None if max_avg_amount_20d_raw is None else _safe_float(max_avg_amount_20d_raw)
    if (
        _safe_float(first_values.get("benchmark_return_20d")) <= max_benchmark_return_20d
        and _safe_float(first_values.get("benchmark_return_10d")) <= max_benchmark_return_10d
        and _safe_float(first_values.get("low_volatility_percentile")) >= min_low_volatility
        and _safe_float(first_values.get("turnover_rate_percentile"), 999999999999.0) <= max_turnover
        and (
            max_avg_amount_20d is None
            or _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_avg_amount_20d
        )
    ):
        scale = min(
            scale,
            max(
                _safe_float(
                    trial_params.get("rank1_weak_grind_position_scale"),
                    _safe_float(scaling.get("position_scale"), 0.2),
                ),
                0.0,
            ),
            1.0,
        )
        reasons.append("rank1_weak_defensive_grind_position_scale")
    residual_momentum = scaling.get("rank1_residual_momentum_amount_tail_scale")
    if isinstance(residual_momentum, dict) and residual_momentum.get("enabled"):
        min_residual_benchmark_return_20d = _safe_float(
            trial_params.get("rank1_residual_momentum_min_benchmark_return_20d"),
            _safe_float(residual_momentum.get("min_benchmark_return_20d"), 0.03),
        )
        max_residual_benchmark_return_10d = _safe_float(
            trial_params.get("rank1_residual_momentum_max_benchmark_return_10d"),
            _safe_float(residual_momentum.get("max_benchmark_return_10d"), 0.04),
        )
        min_residual_return_5d = _safe_float(
            trial_params.get("rank1_residual_momentum_min_return_5d_percentile"),
            _safe_float(residual_momentum.get("min_return_5d_percentile"), 0.98),
        )
        min_residual_return_20d = _safe_float(
            trial_params.get("rank1_residual_momentum_min_return_20d_percentile"),
            _safe_float(residual_momentum.get("min_return_20d_percentile"), 0.96),
        )
        min_residual_amount = _safe_float(
            trial_params.get("rank1_residual_momentum_min_amount_10d_vs_20d_percentile"),
            _safe_float(residual_momentum.get("min_amount_10d_vs_20d_percentile"), 0.95),
        )
        min_residual_volatility = _safe_float(
            trial_params.get("rank1_residual_momentum_min_volatility_20d_percentile"),
            _safe_float(residual_momentum.get("min_volatility_20d_percentile"), 0.30),
        )
        max_residual_avg_amount_20d = _safe_float(
            trial_params.get("rank1_residual_momentum_max_avg_amount_20d"),
            _safe_float(residual_momentum.get("max_avg_amount_20d"), 600_000_000.0),
        )
        if (
            _safe_float(first_values.get("benchmark_return_20d")) >= min_residual_benchmark_return_20d
            and _safe_float(first_values.get("benchmark_return_10d")) <= max_residual_benchmark_return_10d
            and _safe_float(first_values.get("return_5d_percentile")) >= min_residual_return_5d
            and _safe_float(first_values.get("return_20d_percentile")) >= min_residual_return_20d
            and _safe_float(first_values.get("amount_10d_vs_20d_percentile")) >= min_residual_amount
            and _safe_float(first_values.get("volatility_20d_percentile")) >= min_residual_volatility
            and _safe_float(first_values.get("avg_amount_20d"), 999999999999.0) <= max_residual_avg_amount_20d
        ):
            scale = min(
                scale,
                max(
                    _safe_float(
                        trial_params.get("rank1_residual_momentum_position_scale"),
                        _safe_float(residual_momentum.get("position_scale"), 0.3),
                    ),
                    0.0,
                ),
                1.0,
            )
            reasons.append("rank1_residual_momentum_amount_tail_position_scale")
    neutral_chop_date_scale = scaling.get("rank1_neutral_chop_date_scale")
    if isinstance(neutral_chop_date_scale, dict) and neutral_chop_date_scale.get("enabled"):
        min_neutral_benchmark_return_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_date_min_benchmark_return_20d"),
            _safe_float(neutral_chop_date_scale.get("min_benchmark_return_20d"), -0.02),
        )
        max_neutral_benchmark_return_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_date_max_benchmark_return_20d"),
            _safe_float(neutral_chop_date_scale.get("max_benchmark_return_20d"), 0.01),
        )
        min_neutral_benchmark_volatility_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_date_min_benchmark_volatility_20d"),
            _safe_float(neutral_chop_date_scale.get("min_benchmark_volatility_20d"), 0.03),
        )
        max_neutral_return_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_date_max_return_20d_percentile"),
            _safe_float(neutral_chop_date_scale.get("max_return_20d_percentile"), 0.95),
        )
        min_neutral_return_5d = _safe_float(
            trial_params.get("rank1_neutral_chop_date_min_return_5d_percentile"),
            _safe_float(neutral_chop_date_scale.get("min_return_5d_percentile"), 0.80),
        )
        max_neutral_drawdown_20d = _safe_float(
            trial_params.get("rank1_neutral_chop_date_max_drawdown_20d"),
            _safe_float(neutral_chop_date_scale.get("max_drawdown_20d"), -0.003),
        )
        if (
            _safe_float(first_values.get("benchmark_return_20d")) >= min_neutral_benchmark_return_20d
            and _safe_float(first_values.get("benchmark_return_20d")) <= max_neutral_benchmark_return_20d
            and _safe_float(first_values.get("benchmark_volatility_20d")) >= min_neutral_benchmark_volatility_20d
            and _safe_float(first_values.get("return_20d_percentile")) <= max_neutral_return_20d
            and _safe_float(first_values.get("return_5d_percentile")) >= min_neutral_return_5d
            and _safe_float(first_values.get("max_drawdown_20d")) <= max_neutral_drawdown_20d
        ):
            scale = min(
                scale,
                max(
                    _safe_float(
                        trial_params.get("rank1_neutral_chop_date_position_scale"),
                        _safe_float(neutral_chop_date_scale.get("position_scale"), 0.0),
                    ),
                    0.0,
                ),
                1.0,
            )
            reasons.append("rank1_neutral_chop_date_position_scale")
    exhaustion_reference_date_scale = scaling.get("exhaustion_reference_date_scale")
    if isinstance(exhaustion_reference_date_scale, dict) and exhaustion_reference_date_scale.get("enabled"):
        scan_top_n = max(
            1,
            int(
                _safe_float(
                    trial_params.get("exhaustion_reference_date_scan_top_n"),
                    _safe_float(exhaustion_reference_date_scale.get("scan_top_n"), 3),
                )
            ),
        )
        reference_rows = sorted(
            ordered_rows,
            key=lambda row: _safe_float(row.get("exhaustion_reference_score"), _safe_float(row.get("score"))),
            reverse=True,
        )[:scan_top_n]
        if any(
            bool(row.get("exhaustion_triggered"))
            or _exhaustion_trigger_matches(_rank_signal_feature_values(row), trial_params)
            for row in reference_rows
        ):
            scale = min(
                scale,
                max(
                    _safe_float(
                        trial_params.get("exhaustion_reference_date_position_scale"),
                        _safe_float(exhaustion_reference_date_scale.get("position_scale"), 0.3),
                    ),
                    0.0,
                ),
                1.0,
            )
            reasons.append("exhaustion_reference_date_position_scale")
    return scale, reasons


def _select_top_k_rows(
    ordered_rows: list[dict[str, Any]],
    *,
    top_k: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not ordered_rows:
        return []
    policy = selection_policy or {}
    if _signal_cash_switch_block_reasons(ordered_rows, selection_policy=policy, params=params):
        return []
    constraints = policy.get("portfolio_constraints") if isinstance(policy, dict) else None
    if not isinstance(constraints, dict) or not constraints.get("enabled"):
        selected = ordered_rows[: max(1, top_k)]
        return _apply_slot_replacement_policy(
            ordered_rows,
            selected,
            top_k=top_k,
            selection_policy=policy,
            params=params,
        )
    trial_params = params or {}
    max_same_industry_picks = int(
        _safe_float(
            trial_params.get("max_same_industry_picks"),
            _safe_float(constraints.get("max_same_industry_picks"), max(1, top_k)),
        )
    )
    if max_same_industry_picks < 1:
        return ordered_rows[: max(1, top_k)]
    selected: list[dict[str, Any]] = []
    industry_counts: dict[str, int] = {}
    for row in ordered_rows:
        industry = str(row.get("industry_name") or row.get("industry_code") or "unknown")
        if industry_counts.get(industry, 0) >= max_same_industry_picks:
            continue
        selected.append(row)
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if len(selected) >= max(1, top_k):
            break
    if len(selected) >= max(1, top_k):
        return _apply_slot_replacement_policy(
            ordered_rows,
            selected,
            top_k=top_k,
            selection_policy=policy,
            params=params,
        )
    if str(constraints.get("fallback") or "allow_lower_rank_cross_industry") == "allow_concentration_if_needed":
        selected_ids = {id(row) for row in selected}
        for row in ordered_rows:
            if id(row) in selected_ids:
                continue
            selected.append(row)
            if len(selected) >= max(1, top_k):
                break
    return _apply_slot_replacement_policy(
        ordered_rows,
        selected,
        top_k=top_k,
        selection_policy=policy,
        params=params,
    )


def _apply_slot_replacement_policy(
    ordered_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    *,
    top_k: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    policy = selection_policy or {}
    replacement = policy.get("slot_replacement") if isinstance(policy, dict) else None
    if not isinstance(replacement, dict) or not replacement.get("enabled") or not selected_rows:
        return selected_rows
    mode = str(replacement.get("mode") or "")
    if mode != "rank1_low_score_low_amount_full_fill_topn_substitute":
        return selected_rows
    trial_params = params or {}
    updated = _apply_rank1_slot_replacement_rule(
        ordered_rows,
        selected_rows,
        top_k=top_k,
        max_score=_safe_float(
            trial_params.get("rank1_replacement_max_score"),
            _safe_float(replacement.get("max_score"), 3.1),
        ),
        max_avg_amount_20d=_safe_float(
            trial_params.get("rank1_replacement_max_avg_amount_20d"),
            _safe_float(replacement.get("max_avg_amount_20d"), 150_000_000.0),
        ),
        min_replacement_avg_amount_20d=_safe_float(
            trial_params.get("rank1_replacement_min_replacement_avg_amount_20d"),
            _safe_float(replacement.get("min_replacement_avg_amount_20d"), 20_000_000.0),
        ),
        pool_top_n=int(
            _safe_float(
                trial_params.get("rank1_replacement_pool_top_n"),
                _safe_float(replacement.get("pool_top_n"), 20),
            )
        ),
        reason="rank1_low_score_low_amount_full_fill_topn_substitute",
        source_conditions=replacement.get("source_conditions"),
        candidate_conditions=replacement.get("candidate_conditions"),
        condition_rule=replacement,
        trial_params=trial_params,
    )
    additional_rules = replacement.get("additional_rank1_replacement_rules")
    if not isinstance(additional_rules, list):
        return updated
    for rule in additional_rules:
        if not isinstance(rule, dict) or not rule.get("enabled"):
            continue
        prefix = str(rule.get("param_prefix") or "rank1_additional_replacement")
        updated = _apply_rank1_slot_replacement_rule(
            ordered_rows,
            updated,
            top_k=top_k,
            max_score=_safe_float(
                trial_params.get(f"{prefix}_max_score"),
                _safe_float(rule.get("max_score"), 3.2),
            ),
            max_avg_amount_20d=_safe_float(
                trial_params.get(f"{prefix}_max_avg_amount_20d"),
                _safe_float(rule.get("max_avg_amount_20d"), 20_000_000.0),
            ),
            min_replacement_avg_amount_20d=_safe_float(
                trial_params.get(f"{prefix}_min_replacement_avg_amount_20d"),
                _safe_float(rule.get("min_replacement_avg_amount_20d"), 100_000_000.0),
            ),
            pool_top_n=int(
                _safe_float(
                    trial_params.get(f"{prefix}_pool_top_n"),
                    _safe_float(rule.get("pool_top_n"), 20),
                )
            ),
            reason=str(rule.get("reason") or "rank1_additional_topn_slot_substitute"),
            max_turnover_rate_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_max_turnover_rate_percentile"),
                    _safe_float(rule.get("max_turnover_rate_percentile"), 1.0),
                )
                if rule.get("max_turnover_rate_percentile") is not None
                or trial_params.get(f"{prefix}_max_turnover_rate_percentile") is not None
                else None
            ),
            max_amount_10d_vs_20d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_max_amount_10d_vs_20d_percentile"),
                    _safe_float(rule.get("max_amount_10d_vs_20d_percentile"), 1.0),
                )
                if rule.get("max_amount_10d_vs_20d_percentile") is not None
                or trial_params.get(f"{prefix}_max_amount_10d_vs_20d_percentile") is not None
                else None
            ),
            min_amount_10d_vs_20d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_min_amount_10d_vs_20d_percentile"),
                    _safe_float(rule.get("min_amount_10d_vs_20d_percentile"), 0.0),
                )
                if rule.get("min_amount_10d_vs_20d_percentile") is not None
                or trial_params.get(f"{prefix}_min_amount_10d_vs_20d_percentile") is not None
                else None
            ),
            max_return_5d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_max_return_5d_percentile"),
                    _safe_float(rule.get("max_return_5d_percentile"), 1.0),
                )
                if rule.get("max_return_5d_percentile") is not None
                or trial_params.get(f"{prefix}_max_return_5d_percentile") is not None
                else None
            ),
            min_return_5d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_min_return_5d_percentile"),
                    _safe_float(rule.get("min_return_5d_percentile"), 0.0),
                )
                if rule.get("min_return_5d_percentile") is not None
                or trial_params.get(f"{prefix}_min_return_5d_percentile") is not None
                else None
            ),
            min_return_20d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_min_return_20d_percentile"),
                    _safe_float(rule.get("min_return_20d_percentile"), 0.0),
                )
                if rule.get("min_return_20d_percentile") is not None
                or trial_params.get(f"{prefix}_min_return_20d_percentile") is not None
                else None
            ),
            min_benchmark_volatility_20d=(
                _safe_float(
                    trial_params.get(f"{prefix}_min_benchmark_volatility_20d"),
                    _safe_float(rule.get("min_benchmark_volatility_20d"), 0.0),
                )
                if rule.get("min_benchmark_volatility_20d") is not None
                or trial_params.get(f"{prefix}_min_benchmark_volatility_20d") is not None
                else None
            ),
            max_drawdown_20d=(
                _safe_float(
                    trial_params.get(f"{prefix}_max_drawdown_20d"),
                    _safe_float(rule.get("max_drawdown_20d"), 1.0),
                )
                if rule.get("max_drawdown_20d") is not None
                or trial_params.get(f"{prefix}_max_drawdown_20d") is not None
                else None
            ),
            min_candidate_return_5d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_min_candidate_return_5d_percentile"),
                    _safe_float(rule.get("min_candidate_return_5d_percentile"), 0.0),
                )
                if rule.get("min_candidate_return_5d_percentile") is not None
                or trial_params.get(f"{prefix}_min_candidate_return_5d_percentile") is not None
                else None
            ),
            max_candidate_turnover_rate_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_max_candidate_turnover_rate_percentile"),
                    _safe_float(rule.get("max_candidate_turnover_rate_percentile"), 1.0),
                )
                if rule.get("max_candidate_turnover_rate_percentile") is not None
                or trial_params.get(f"{prefix}_max_candidate_turnover_rate_percentile") is not None
                else None
            ),
            max_candidate_return_20d_percentile=(
                _safe_float(
                    trial_params.get(f"{prefix}_max_candidate_return_20d_percentile"),
                    _safe_float(rule.get("max_candidate_return_20d_percentile"), 1.0),
                )
                if rule.get("max_candidate_return_20d_percentile") is not None
                or trial_params.get(f"{prefix}_max_candidate_return_20d_percentile") is not None
                else None
            ),
            min_candidate_score=(
                _safe_float(
                    trial_params.get(f"{prefix}_min_candidate_score"),
                    _safe_float(rule.get("min_candidate_score"), 0.0),
                )
                if rule.get("min_candidate_score") is not None
                or trial_params.get(f"{prefix}_min_candidate_score") is not None
                else None
            ),
            source_conditions=rule.get("source_conditions"),
            candidate_conditions=rule.get("candidate_conditions"),
            condition_rule=rule,
            trial_params=trial_params,
        )
    return updated


def _apply_rank1_slot_replacement_rule(
    ordered_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    *,
    top_k: int,
    max_score: float,
    max_avg_amount_20d: float,
    min_replacement_avg_amount_20d: float,
    pool_top_n: int,
    reason: str,
    max_turnover_rate_percentile: float | None = None,
    max_amount_10d_vs_20d_percentile: float | None = None,
    min_amount_10d_vs_20d_percentile: float | None = None,
    max_return_5d_percentile: float | None = None,
    min_return_5d_percentile: float | None = None,
    min_return_20d_percentile: float | None = None,
    min_benchmark_volatility_20d: float | None = None,
    max_drawdown_20d: float | None = None,
    min_candidate_return_5d_percentile: float | None = None,
    max_candidate_turnover_rate_percentile: float | None = None,
    max_candidate_return_20d_percentile: float | None = None,
    min_candidate_score: float | None = None,
    source_conditions: list[dict[str, Any]] | None = None,
    candidate_conditions: list[dict[str, Any]] | None = None,
    condition_rule: dict[str, Any] | None = None,
    trial_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if pool_top_n <= max(1, top_k):
        return selected_rows
    updated = list(selected_rows)
    selected_symbols = {str(row.get("symbol") or "") for row in selected_rows}
    for index, row in enumerate(selected_rows):
        rank = index + 1
        if rank != 1:
            continue
        values = _rank_signal_feature_values(row)
        if _safe_float(row.get("score"), 999999999999.0) > max_score:
            continue
        if _safe_float(values.get("avg_amount_20d"), 999999999999.0) > max_avg_amount_20d:
            continue
        if (
            max_turnover_rate_percentile is not None
            and _safe_float(values.get("turnover_rate_percentile"), 999999999999.0)
            > max_turnover_rate_percentile
        ):
            continue
        if (
            max_amount_10d_vs_20d_percentile is not None
            and _safe_float(values.get("amount_10d_vs_20d_percentile"), 999999999999.0)
            > max_amount_10d_vs_20d_percentile
        ):
            continue
        if (
            min_amount_10d_vs_20d_percentile is not None
            and _safe_float(values.get("amount_10d_vs_20d_percentile"), -999999999999.0)
            < min_amount_10d_vs_20d_percentile
        ):
            continue
        if (
            max_return_5d_percentile is not None
            and _safe_float(values.get("return_5d_percentile"), 999999999999.0) > max_return_5d_percentile
        ):
            continue
        if (
            min_return_5d_percentile is not None
            and _safe_float(values.get("return_5d_percentile"), -999999999999.0) < min_return_5d_percentile
        ):
            continue
        if (
            min_return_20d_percentile is not None
            and _safe_float(values.get("return_20d_percentile"), -999999999999.0) < min_return_20d_percentile
        ):
            continue
        if (
            min_benchmark_volatility_20d is not None
            and _safe_float(values.get("benchmark_volatility_20d"), -999999999999.0) < min_benchmark_volatility_20d
        ):
            continue
        if (
            max_drawdown_20d is not None
            and _safe_float(values.get("max_drawdown_20d"), 999999999999.0) > max_drawdown_20d
        ):
            continue
        if not _rank_replacement_conditions_match(
            row,
            values=values,
            conditions=source_conditions,
            condition_rule=condition_rule,
            trial_params=trial_params,
        ):
            continue
        for candidate in ordered_rows[:pool_top_n]:
            symbol = str(candidate.get("symbol") or "")
            if not symbol or symbol in selected_symbols:
                continue
            candidate_values = _rank_signal_feature_values(candidate)
            if _safe_float(candidate_values.get("avg_amount_20d")) < min_replacement_avg_amount_20d:
                continue
            if (
                min_candidate_return_5d_percentile is not None
                and _safe_float(candidate_values.get("return_5d_percentile"), -999999999999.0)
                < min_candidate_return_5d_percentile
            ):
                continue
            if (
                max_candidate_turnover_rate_percentile is not None
                and _safe_float(candidate_values.get("turnover_rate_percentile"), 999999999999.0)
                > max_candidate_turnover_rate_percentile
            ):
                continue
            if (
                max_candidate_return_20d_percentile is not None
                and _safe_float(candidate_values.get("return_20d_percentile"), 999999999999.0)
                > max_candidate_return_20d_percentile
            ):
                continue
            if min_candidate_score is not None and _safe_float(candidate.get("score")) < min_candidate_score:
                continue
            if not _rank_replacement_conditions_match(
                candidate,
                values=candidate_values,
                conditions=candidate_conditions,
                condition_rule=condition_rule,
                trial_params=trial_params,
            ):
                continue
            updated[index] = {
                **candidate,
                "slot_replacement_source_symbol": row.get("symbol"),
                "slot_replacement_source_score": row.get("score"),
                "slot_replacement_reason": reason,
            }
            selected_symbols.add(symbol)
            selected_symbols.discard(str(row.get("symbol") or ""))
            break
    return updated


def _rank_replacement_conditions_match(
    row: dict[str, Any],
    *,
    values: dict[str, Any],
    conditions: list[dict[str, Any]] | None,
    condition_rule: dict[str, Any] | None,
    trial_params: dict[str, Any] | None,
) -> bool:
    if not conditions:
        return True
    rule = condition_rule or {}
    params = trial_params or {}
    return all(
        isinstance(condition, dict)
        and _rank_segment_condition_matches(
            row,
            values=values,
            rule=rule,
            condition=condition,
            trial_params=params,
        )
        for condition in conditions
    )


def _weighted_return(
    rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> float:
    if not rows:
        return 0.0
    policy = selection_policy or {}
    trial_params = params or {}
    rank_scales = _rank_position_scales_for_rows(rows, selection_policy=policy, params=trial_params)
    rank_adjustments = _rank_portfolio_adjustment_multipliers_for_rows(
        rows,
        selection_policy=policy,
        params=trial_params,
    )
    return mean(
        _safe_float(row.get("target_label"))
        * _safe_float(row.get("portfolio_weight"), 1.0)
        * multiplier
        * (rank_scales[index][0] if index < len(rank_scales) else 1.0)
        * (rank_adjustments[index][0] if index < len(rank_adjustments) else 1.0)
        for index, (row, multiplier) in enumerate(
            zip(
                rows,
                _rank_weight_multipliers_for_rows(rows, selection_policy=policy, params=trial_params),
                strict=False,
            )
        )
    )


def _weighted_total_return(
    rows: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> float:
    if not rows:
        return 0.0
    policy = selection_policy or {}
    trial_params = params or {}
    rank_scales = _rank_position_scales_for_rows(rows, selection_policy=policy, params=trial_params)
    rank_adjustments = _rank_portfolio_adjustment_multipliers_for_rows(
        rows,
        selection_policy=policy,
        params=trial_params,
    )
    return mean(
        _safe_float(row.get("target_total_return"), _safe_float(row.get("target_label")))
        * _safe_float(row.get("portfolio_weight"), 1.0)
        * multiplier
        * (rank_scales[index][0] if index < len(rank_scales) else 1.0)
        * (rank_adjustments[index][0] if index < len(rank_adjustments) else 1.0)
        for index, (row, multiplier) in enumerate(
            zip(
                rows,
                _rank_weight_multipliers_for_rows(rows, selection_policy=policy, params=trial_params),
                strict=False,
            )
        )
    )


def _join_rows(feature_matrix: dict[str, Any], label_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    labels_by_universe_id = {str(row.get("universe_row_id")): row for row in label_matrix.get("rows") or []}
    joined: list[dict[str, Any]] = []
    for feature_row in feature_matrix.get("rows") or []:
        universe_row_id = str(feature_row.get("universe_row_id") or "")
        label_row = labels_by_universe_id.get(universe_row_id)
        if label_row is None:
            continue
        joined.append(
            {
                "universe_row_id": universe_row_id,
                "symbol": feature_row.get("symbol"),
                "stock_name": feature_row.get("stock_name"),
                "board": feature_row.get("board"),
                "industry_code": feature_row.get("industry_code"),
                "industry_name": feature_row.get("industry_name"),
                "as_of_date": feature_row.get("as_of_date"),
                "feature_row": feature_row,
                "feature_values_flat": _model_feature_values(feature_row),
                "label_row": label_row,
                "target_label": (label_row.get("labels") or {}).get("net_excess_return_10d_after_costs"),
                "target_labels_by_horizon": {
                    str(horizon): (label_row.get("labels") or {}).get(f"excess_return_{horizon}d")
                    for horizon in (5, 20)
                }
                | {"10": (label_row.get("labels") or {}).get("net_excess_return_10d_after_costs")},
                "target_total_returns_by_horizon": {
                    str(horizon): (label_row.get("labels") or {}).get(f"forward_return_{horizon}d")
                    for horizon in (5, 10, 20)
                },
                "label_status": label_row.get("label_status"),
            }
        )
    joined.sort(key=lambda row: (str(row.get("as_of_date") or ""), str(row.get("symbol") or "")))
    return joined


def _walk_forward_splits(dates: list[str], *, min_train_dates: int, test_window_dates: int) -> list[dict[str, Any]]:
    if len(dates) <= min_train_dates:
        return [
            {
                "split_id": "split-000-insufficient",
                "status": "insufficient_dates",
                "train_dates": dates,
                "test_dates": [],
                "purge_days": 0,
                "embargo_days": 0,
                "training_label_policy": "actual_outcome_dates_before_test_start",
            }
        ]
    splits: list[dict[str, Any]] = []
    start = min_train_dates
    split_index = 0
    while start < len(dates):
        test_dates = dates[start : start + test_window_dates]
        if not test_dates:
            break
        splits.append(
            {
                "split_id": f"split-{split_index:03d}",
                "status": "ready",
                "train_dates": dates[:start],
                "test_dates": test_dates,
                "purge_days": 0,
                "embargo_days": 0,
                "training_label_policy": "actual_outcome_dates_before_test_start",
            }
        )
        split_index += 1
        start += test_window_dates
    return splits


def _trial_metrics(
    predictions: list[dict[str, Any]],
    *,
    selected_top_k: int = 5,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scored = [row for row in predictions if row.get("target_label") is not None]
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in scored:
        by_date.setdefault(str(row["as_of_date"]), []).append(row)
    rank_ics: list[float] = []
    top_returns: list[float] = []
    top_5_returns: list[float] = []
    top_10_returns: list[float] = []
    selected_top_k_returns: list[float] = []
    spreads: list[float] = []
    for rows in by_date.values():
        if len(rows) < 2:
            continue
        if not any(row.get("selection_allowed", True) for row in rows):
            top_5_returns.append(0.0)
            top_10_returns.append(0.0)
            selected_top_k_returns.append(0.0)
            top_returns.append(0.0)
            spreads.append(0.0)
            continue
        scores = [_safe_float(row.get("score")) for row in rows]
        labels = [_safe_float(row.get("target_label")) for row in rows]
        rank_ics.append(spearman_correlation(scores, labels))
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        bucket_size = max(1, len(ordered) // 5)
        top = [_safe_float(row.get("target_label")) for row in ordered[:bucket_size]]
        bottom = [_safe_float(row.get("target_label")) for row in ordered[-bucket_size:]]
        top_5_returns.append(_weighted_return(ordered[: min(5, len(ordered))]))
        top_10_returns.append(_weighted_return(ordered[: min(10, len(ordered))]))
        selected_rows = _select_top_k_rows(
            ordered,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
        exposure_context = _selected_exposure_context(
            selected_rows,
            ordered_rows=ordered,
            selection_policy=selection_policy,
            params=params,
        )
        selected_top_k_returns.append(
            _weighted_return(
                selected_rows,
                selection_policy=selection_policy,
                params=params,
            )
            * exposure_context["signal_scale"]
            * exposure_context["date_position_scale"]
        )
        top_returns.append(mean(top))
        spreads.append(mean(top) - mean(bottom))
    return {
        "prediction_count": len(predictions),
        "labeled_prediction_count": len(scored),
        "rank_ic_mean": mean(rank_ics) if rank_ics else None,
        "positive_rank_ic_rate": sum(1 for value in rank_ics if value > 0) / len(rank_ics) if rank_ics else None,
        "top_5_net_excess_mean": mean(top_5_returns) if top_5_returns else None,
        "positive_top_5_rate": sum(1 for value in top_5_returns if value > 0) / len(top_5_returns)
        if top_5_returns
        else None,
        "top_10_net_excess_mean": mean(top_10_returns) if top_10_returns else None,
        "selected_top_k": selected_top_k,
        "selected_top_k_net_excess_mean": mean(selected_top_k_returns) if selected_top_k_returns else None,
        "positive_selected_top_k_rate": sum(1 for value in selected_top_k_returns if value > 0) / len(selected_top_k_returns)
        if selected_top_k_returns
        else None,
        "top_quantile_net_excess_mean": mean(top_returns) if top_returns else None,
        "top_bottom_spread_mean": mean(spreads) if spreads else None,
        "evaluated_date_count": len(rank_ics),
    }


def _rank_ics_by_field(predictions: list[dict[str, Any]], *, field: str) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_key.setdefault(str(row.get(field) or ""), []).append(row)
    diagnostics: list[dict[str, Any]] = []
    for key, rows in sorted(by_key.items()):
        if len(rows) < 2:
            continue
        scores = [_safe_float(row.get("score")) for row in rows]
        labels = [_safe_float(row.get("target_label")) for row in rows]
        diagnostics.append(
            {
                field: key,
                "rank_ic": spearman_correlation(scores, labels),
                "row_count": len(rows),
            }
        )
    return diagnostics


def _top_picks_by_date(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    top_picks: list[dict[str, Any]] = []
    for as_of_date, rows in sorted(by_date.items()):
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        if not active_rows:
            continue
        best = max(active_rows, key=lambda row: _safe_float(row.get("score")))
        top_picks.append(
            {
                "symbol": best.get("symbol"),
                "stock_name": best.get("stock_name"),
                "board": best.get("board"),
                "industry_code": best.get("industry_code"),
                "industry_name": best.get("industry_name"),
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "net_excess_return": _safe_float(best.get("target_label")),
                "weighted_net_excess_return": _safe_float(best.get("target_label"))
                * _safe_float(best.get("portfolio_weight"), 1.0),
                    "portfolio_weight": _safe_float(best.get("portfolio_weight"), 1.0),
                    "target_horizon_days": int(_safe_float(best.get("target_horizon_days"), 0.0)),
                    "score": _safe_float(best.get("score")),
                }
            )
    return top_picks


def _top_k_picks_by_date(
    predictions: list[dict[str, Any]],
    *,
    top_k: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    picks: list[dict[str, Any]] = []
    for as_of_date, rows in sorted(by_date.items()):
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        if not active_rows:
            continue
        ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        picks.extend(
            _top_k_picks_from_ordered_rows(
                as_of_date=as_of_date,
                ordered=ordered,
                top_k=top_k,
                selection_policy=selection_policy,
                params=params,
            )
        )
    return picks


def _top_k_picks_from_ordered_rows(
    *,
    as_of_date: str,
    ordered: list[dict[str, Any]],
    top_k: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected_rows = _select_top_k_rows(
        ordered,
        top_k=top_k,
        selection_policy=selection_policy,
        params=params,
    )
    exposure_context = _selected_exposure_context(
        selected_rows,
        ordered_rows=ordered,
        selection_policy=selection_policy,
        params=params,
    )
    rank_multipliers = exposure_context["rank_multipliers"]
    signal_scale = exposure_context["signal_scale"]
    signal_scale_reasons = exposure_context["signal_scale_reasons"]
    rank_position_scales = exposure_context["rank_position_scales"]
    rank_portfolio_adjustments = exposure_context["rank_portfolio_adjustment_multipliers"]
    date_position_scale = exposure_context["date_position_scale"]
    date_exposure_scale_reasons = exposure_context["date_exposure_scale_reasons"]
    picks: list[dict[str, Any]] = []
    for rank, picked in enumerate(selected_rows, start=1):
        rank_multiplier = rank_multipliers[rank - 1] if rank - 1 < len(rank_multipliers) else 1.0
        rank_position_scale, rank_position_scale_reasons = (
            rank_position_scales[rank - 1] if rank - 1 < len(rank_position_scales) else (1.0, [])
        )
        rank_adjustment_multiplier, rank_adjustment_reasons = (
            rank_portfolio_adjustments[rank - 1]
            if rank - 1 < len(rank_portfolio_adjustments)
            else (1.0, [])
        )
        rank_feature_values = (
            picked.get("rank_weight_feature_values") if isinstance(picked.get("rank_weight_feature_values"), dict) else {}
        )
        picks.append(
            {
                "symbol": picked.get("symbol"),
                "stock_name": picked.get("stock_name"),
                "board": picked.get("board"),
                "industry_code": picked.get("industry_code"),
                "industry_name": picked.get("industry_name"),
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "rank": rank,
                "net_excess_return": _safe_float(picked.get("target_label")),
                "weighted_net_excess_return": _safe_float(picked.get("target_label"))
                * _safe_float(picked.get("portfolio_weight"), 1.0)
                * rank_multiplier
                * signal_scale
                * rank_position_scale
                * rank_adjustment_multiplier
                * date_position_scale,
                "portfolio_weight": _safe_float(picked.get("portfolio_weight"), 1.0)
                * signal_scale
                * rank_position_scale
                * rank_adjustment_multiplier
                * date_position_scale,
                "rank_weight_multiplier": rank_multiplier,
                "rank_position_scale": rank_position_scale,
                "rank_position_scale_reasons": rank_position_scale_reasons,
                "rank_portfolio_adjustment_multiplier": rank_adjustment_multiplier,
                "rank_portfolio_adjustment_reasons": rank_adjustment_reasons,
                "slot_replacement_source_symbol": picked.get("slot_replacement_source_symbol"),
                "slot_replacement_source_score": picked.get("slot_replacement_source_score"),
                "slot_replacement_reason": picked.get("slot_replacement_reason"),
                "signal_position_scale": signal_scale,
                "signal_position_scale_reasons": signal_scale_reasons,
                "base_gross_exposure": exposure_context["base_gross_exposure"],
                "date_exposure_scale": exposure_context["date_exposure_scale"],
                "date_exposure_scale_reasons": date_exposure_scale_reasons,
                "date_exposure_floor": exposure_context["date_exposure_floor"],
                "date_position_scale": exposure_context["date_position_scale"],
                "date_position_scale_reasons": exposure_context["date_position_scale_reasons"],
                "avg_amount_20d": _safe_float(rank_feature_values.get("avg_amount_20d")),
                "amount_10d_vs_20d_percentile": _safe_float(
                    rank_feature_values.get("amount_10d_vs_20d_percentile")
                ),
                "amount_vs_20d_avg_percentile": _safe_float(
                    rank_feature_values.get("amount_vs_20d_avg_percentile")
                ),
                "benchmark_return_20d": _safe_float(rank_feature_values.get("benchmark_return_20d")),
                "distance_from_20d_high": _safe_float(rank_feature_values.get("distance_from_20d_high")),
                "industry_return_20d_excess": _safe_float(rank_feature_values.get("industry_return_20d_excess")),
                "return_20d_percentile": _safe_float(rank_feature_values.get("return_20d_percentile")),
                "return_5d_percentile": _safe_float(rank_feature_values.get("return_5d_percentile")),
                "turnover_rate_percentile": _safe_float(rank_feature_values.get("turnover_rate_percentile")),
                "target_horizon_days": int(_safe_float(picked.get("target_horizon_days"), 0.0)),
                "score": _safe_float(picked.get("score")),
            }
        )
    return picks


def _top_k_returns_by_date(
    predictions: list[dict[str, Any]],
    *,
    top_k: int,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    returns: list[dict[str, Any]] = []
    for as_of_date, rows in sorted(by_date.items()):
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        if not active_rows:
            returns.append(
                {
                    "as_of_date": as_of_date,
                    "month": as_of_date[:7],
                    "pick_count": 0,
                    "mean_net_excess_return": 0.0,
                    "mean_total_return_after_cost": 0.0,
                    "mean_target_horizon_days": None,
                    "selection_state": "cash",
                }
            )
            continue
        ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        top_rows = _select_top_k_rows(
            ordered,
            top_k=top_k,
            selection_policy=selection_policy,
            params=params,
        )
        if not top_rows:
            returns.append(
                {
                    "as_of_date": as_of_date,
                    "month": as_of_date[:7],
                    "pick_count": 0,
                    "mean_net_excess_return": 0.0,
                    "mean_total_return_after_cost": 0.0,
                    "mean_target_horizon_days": None,
                    "selection_state": "cash",
                    "selection_block_reasons": _signal_cash_switch_block_reasons(
                        ordered,
                        selection_policy=selection_policy,
                        params=params,
                    ),
                }
            )
            continue
        exposure_context = _selected_exposure_context(
            top_rows,
            ordered_rows=ordered,
            selection_policy=selection_policy,
            params=params,
        )
        signal_scale = exposure_context["signal_scale"]
        signal_scale_reasons = exposure_context["signal_scale_reasons"]
        rank_position_scales = exposure_context["rank_position_scales"]
        date_position_scale = exposure_context["date_position_scale"]
        returns.append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "pick_count": len(top_rows),
                "mean_net_excess_return": _weighted_return(
                    top_rows,
                    selection_policy=selection_policy,
                    params=params,
                )
                * signal_scale
                * date_position_scale,
                "mean_total_return_after_cost": _weighted_total_return(
                    top_rows,
                    selection_policy=selection_policy,
                    params=params,
                )
                * signal_scale
                * date_position_scale,
                "gross_exposure": exposure_context["base_gross_exposure"] * date_position_scale,
                "base_gross_exposure": exposure_context["base_gross_exposure"],
                "date_exposure_scale": exposure_context["date_exposure_scale"],
                "date_exposure_scale_reasons": exposure_context["date_exposure_scale_reasons"],
                "date_exposure_floor": exposure_context["date_exposure_floor"],
                "date_position_scale": exposure_context["date_position_scale"],
                "date_position_scale_reasons": exposure_context["date_position_scale_reasons"],
                "rank_position_scaled_pick_count": sum(
                    1 for scale, _reasons in rank_position_scales if scale < 1.0
                ),
                "slot_replacement_count": sum(
                    1 for row in top_rows if row.get("slot_replacement_source_symbol")
                ),
                "slot_replacement_reasons": sorted(
                    {
                        str(row.get("slot_replacement_reason"))
                        for row in top_rows
                        if row.get("slot_replacement_reason")
                    }
                ),
                "rank_position_scale_reasons": sorted(
                    {
                        reason
                        for _scale, reasons in rank_position_scales
                        for reason in reasons
                    }
                ),
                "mean_target_horizon_days": mean(
                    _safe_float(row.get("target_horizon_days"), 0.0) for row in top_rows
                ),
                "selection_state": "invested",
                "signal_position_scale": signal_scale,
                "signal_position_scale_reasons": signal_scale_reasons,
            }
        )
    return returns


def _industry_exposure_by_month(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = {}
    for pick in picks:
        by_month.setdefault(str(pick.get("month") or ""), []).append(pick)
    diagnostics: list[dict[str, Any]] = []
    for month, rows in sorted(by_month.items()):
        if not rows:
            continue
        industry_returns: dict[str, float] = {}
        industry_counts: dict[str, int] = {}
        for row in rows:
            industry = str(row.get("industry_name") or "unknown")
            industry_returns[industry] = industry_returns.get(industry, 0.0) + _safe_float(
                row.get("weighted_net_excess_return")
            )
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
        top_industry = max(industry_returns, key=lambda key: abs(industry_returns[key]))
        diagnostics.append(
            {
                "month": month,
                "pick_count": len(rows),
                "industry_count": len(industry_counts),
                "top_abs_contribution_industry": top_industry,
                "top_abs_contribution": industry_returns[top_industry],
                "top_abs_contribution_pick_share": industry_counts[top_industry] / len(rows),
                "industry_contributions": [
                    {
                        "industry_name": industry,
                        "pick_count": industry_counts[industry],
                        "weighted_net_excess_return_sum": industry_returns[industry],
                    }
                    for industry in sorted(
                        industry_returns,
                        key=lambda key: abs(industry_returns[key]),
                        reverse=True,
                    )[:10]
                ],
            }
        )
    return diagnostics


def _trial_diagnostics(
    predictions: list[dict[str, Any]],
    *,
    selected_top_k: int = 5,
    selection_policy: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_picks = _top_k_picks_by_date(
        predictions,
        top_k=selected_top_k,
        selection_policy=selection_policy,
        params=params,
    )
    return {
        "split_rank_ics": _rank_ics_by_field(predictions, field="split_id"),
        "date_rank_ics": _rank_ics_by_field(predictions, field="as_of_date"),
        "top_picks_by_date": _top_picks_by_date(predictions),
        "top_5_picks_by_date": _top_k_picks_by_date(predictions, top_k=5),
        "top_5_returns_by_date": _top_k_returns_by_date(predictions, top_k=5),
        "selected_top_k": selected_top_k,
        "selected_top_k_picks_by_date": selected_picks,
        "selected_top_k_returns_by_date": _top_k_returns_by_date(
            predictions,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        ),
        "selected_top_k_industry_exposure_by_month": _industry_exposure_by_month(selected_picks),
    }


def _stored_prediction_sample(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _with_row_digest(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("row_digest"):
            return row
        stored = dict(row)
        stored["row_digest"] = _stable_digest(stored)
        return stored

    if len(predictions) <= MAX_STORED_PREDICTIONS_PER_TRIAL:
        return [_with_row_digest(row) for row in predictions]
    head_count = MAX_STORED_PREDICTIONS_PER_TRIAL // 2
    tail_count = MAX_STORED_PREDICTIONS_PER_TRIAL - head_count
    return [_with_row_digest(row) for row in [*predictions[:head_count], *predictions[-tail_count:]]]


def _load_artifact_metadata_without_rows(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path)
    buffer = ""
    with artifact_path.open("r", encoding="utf-8") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            buffer += chunk
            match = re.search(r'"rows"\s*:\s*\[', buffer)
            if match:
                metadata_text = f"{buffer[: match.start()]}\n\"rows\": []\n}}"
                payload = json.loads(metadata_text)
                if not isinstance(payload, dict):
                    raise ValueError(f"artifact metadata must be a JSON object: {path}")
                return payload
            if len(buffer) > 20 * 1024 * 1024:
                raise ValueError(f"artifact rows key not found in first 20MB: {path}")
    raise ValueError(f"artifact rows key not found: {path}")


def _iter_artifact_rows(path: str | Path) -> Any:
    artifact_path = Path(path)
    with artifact_path.open("r", encoding="utf-8") as handle:
        buffer = ""
        found_rows = False
        while True:
            chunk = handle.read(ARTIFACT_ROW_ITER_CHUNK_BYTES)
            if not chunk:
                break
            buffer += chunk
            match = re.search(r'"rows"\s*:\s*\[', buffer)
            if match:
                buffer = buffer[match.end() :]
                found_rows = True
                break
            if len(buffer) > 20 * 1024 * 1024:
                raise ValueError(f"artifact rows key not found in first 20MB: {path}")
        if not found_rows:
            raise ValueError(f"artifact rows key not found: {path}")

        decoder = json.JSONDecoder()
        position = 0
        eof = False
        while True:
            while True:
                while position < len(buffer) and buffer[position] in " \r\n\t,":
                    position += 1
                if position < len(buffer):
                    break
                if eof:
                    return
                buffer = ""
                position = 0
                chunk = handle.read(ARTIFACT_ROW_ITER_CHUNK_BYTES)
                if not chunk:
                    eof = True
                    continue
                buffer += chunk
            if buffer[position] == "]":
                return
            try:
                row, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError as exc:
                chunk = handle.read(ARTIFACT_ROW_ITER_CHUNK_BYTES)
                if not chunk:
                    raise ValueError(f"failed to parse artifact row from {path}") from exc
                if position:
                    buffer = buffer[position:]
                    position = 0
                buffer += chunk
                continue
            if isinstance(row, dict):
                yield row
            position = end
            if position >= ARTIFACT_ROW_ITER_CHUNK_BYTES:
                buffer = buffer[position:]
                position = 0


def _make_prediction_from_joined_row(
    *,
    joined: dict[str, Any],
    spec: dict[str, Any],
    params: dict[str, Any],
    trial_id: str,
    split_id: str,
    fitted_model_digest: str,
    fitted_model: dict[str, Any] | None = None,
    horizon_days: int,
) -> dict[str, Any]:
    selection_policy = spec.get("selection_policy") or {}
    selection_allowed, selection_block_reasons = _selection_allowed(
        joined["feature_values_flat"],
        selection_policy=selection_policy,
        params=params,
    )
    portfolio_weight = _position_weight(
        joined["feature_values_flat"],
        selection_policy=selection_policy,
        params=params,
    )
    score = _score_row(
        joined["feature_row"],
        model_spec=spec,
        params=params,
        fitted_model=fitted_model,
        feature_values=joined["feature_values_flat"],
    )
    target_horizon_days = _exit_horizon_days(
        joined["feature_values_flat"],
        selection_policy=selection_policy,
        params=params,
        default_horizon_days=horizon_days,
    )
    return {
        "trial_id": trial_id,
        "model_spec_id": str(spec.get("model_spec_id") or ""),
        "split_id": split_id,
        "fitted_model_digest": fitted_model_digest,
        "symbol": joined["symbol"],
        "stock_name": joined.get("stock_name"),
        "board": joined.get("board"),
        "industry_code": joined.get("industry_code"),
        "industry_name": joined.get("industry_name"),
        "as_of_date": joined["as_of_date"],
        "universe_row_id": joined["universe_row_id"],
        "score": score,
        **_exhaustion_reference_metadata(
            model_spec=spec,
            params=params,
            feature_values=joined["feature_values_flat"],
        ),
        "target_label": _target(joined, horizon_days=target_horizon_days),
        "target_total_return": _target_total_return(joined, horizon_days=target_horizon_days),
        "target_horizon_days": target_horizon_days,
        "base_horizon_days": horizon_days,
        "label_status": joined["label_status"],
        "selection_allowed": selection_allowed,
        "selection_block_reasons": selection_block_reasons,
        "portfolio_weight": portfolio_weight if selection_allowed else 0.0,
        "rank_weight_feature_values": _rank_signal_feature_subset(joined["feature_values_flat"]),
    }


def _label_index_row(label_row: dict[str, Any]) -> tuple[Any, ...] | None:
    universe_row_id = str(label_row.get("universe_row_id") or "")
    if not universe_row_id:
        return None
    labels = label_row.get("labels") or {}
    if not isinstance(labels, dict):
        return None
    return (
        universe_row_id,
        str(label_row.get("as_of_date") or ""),
        str(label_row.get("symbol") or ""),
        str(label_row.get("label_status") or ""),
        labels.get("net_excess_return_10d_after_costs"),
        labels.get("excess_return_5d"),
        labels.get("excess_return_20d"),
        labels.get("forward_return_5d"),
        labels.get("forward_return_10d"),
        labels.get("forward_return_20d"),
        json.dumps({
            "label_available_dates_by_horizon": label_row.get("label_available_dates_by_horizon"),
            "exit_dates_by_horizon": label_row.get("exit_dates_by_horizon") or {},
        }),
    )


def _configure_stream_replay_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")


def _build_stream_label_index(
    *,
    label_matrix_artifact: str | Path,
    sqlite_path: Path,
) -> tuple[dict[str, int], int]:
    conn = sqlite3.connect(sqlite_path)
    try:
        _configure_stream_replay_sqlite(conn)
        conn.execute(
            "CREATE TABLE labels ("
            "universe_row_id TEXT PRIMARY KEY, "
            "as_of_date TEXT NOT NULL, "
            "symbol TEXT NOT NULL, "
            "label_status TEXT NOT NULL, "
            "net_excess_return_10d_after_costs REAL, "
            "excess_return_5d REAL, "
            "excess_return_20d REAL, "
            "forward_return_5d REAL, "
            "forward_return_10d REAL, "
            "forward_return_20d REAL, "
            "label_available_dates_json TEXT"
            ")"
        )
        batch: list[tuple[Any, ...]] = []
        ready_date_counts: dict[str, int] = {}
        indexed_count = 0
        for label_row in _iter_artifact_rows(label_matrix_artifact):
            indexed = _label_index_row(label_row)
            if indexed is None:
                continue
            universe_row_id, as_of_date, _symbol, label_status = indexed[:4]
            if label_status != "ready":
                continue
            batch.append(indexed)
            ready_date_counts[as_of_date] = ready_date_counts.get(as_of_date, 0) + 1
            indexed_count += 1
            if len(batch) >= STREAM_REPLAY_INSERT_BATCH_SIZE:
                conn.executemany("INSERT OR REPLACE INTO labels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
                batch = []
        if batch:
            conn.executemany("INSERT OR REPLACE INTO labels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
        conn.commit()
        return ready_date_counts, indexed_count
    finally:
        conn.close()


def _label_index_values(result: tuple[Any, ...]) -> dict[str, Any]:
    (
        label_status,
        net_excess_return_10d_after_costs,
        excess_return_5d,
        excess_return_20d,
        forward_return_5d,
        forward_return_10d,
        forward_return_20d,
        label_available_dates_json,
    ) = result
    return {
        "label_status": label_status,
        **json.loads(label_available_dates_json or "{}"),
        "target_label": net_excess_return_10d_after_costs,
        "target_labels_by_horizon": {
            "5": excess_return_5d,
            "10": net_excess_return_10d_after_costs,
            "20": excess_return_20d,
        },
        "target_total_returns_by_horizon": {
            "5": forward_return_5d,
            "10": forward_return_10d,
            "20": forward_return_20d,
        },
    }


PREDICTION_SQL_COLUMNS = (
    "trial_id",
    "model_spec_id",
    "as_of_date",
    "split_id",
    "fitted_model_digest",
    "symbol",
    "stock_name",
    "board",
    "industry_code",
    "industry_name",
    "universe_row_id",
    "score",
    "target_label",
    "target_total_return",
    "target_horizon_days",
    "base_horizon_days",
    "label_status",
    "selection_allowed",
    "selection_block_reasons_json",
    "portfolio_weight",
    "rank_weight_feature_values_json",
)


def _prediction_db_row(prediction: dict[str, Any]) -> tuple[Any, ...]:
    return (
        prediction.get("trial_id"),
        prediction.get("model_spec_id"),
        prediction.get("as_of_date"),
        prediction.get("split_id"),
        prediction.get("fitted_model_digest"),
        prediction.get("symbol"),
        prediction.get("stock_name"),
        prediction.get("board"),
        prediction.get("industry_code"),
        prediction.get("industry_name"),
        prediction.get("universe_row_id"),
        prediction.get("score"),
        prediction.get("target_label"),
        prediction.get("target_total_return"),
        prediction.get("target_horizon_days"),
        prediction.get("base_horizon_days"),
        prediction.get("label_status"),
        1 if prediction.get("selection_allowed", True) else 0,
        json.dumps(prediction.get("selection_block_reasons") or [], ensure_ascii=False, separators=(",", ":")),
        prediction.get("portfolio_weight"),
        json.dumps(prediction.get("rank_weight_feature_values") or {}, ensure_ascii=False, separators=(",", ":")),
    )


def _prediction_from_db_row(row: tuple[Any, ...]) -> dict[str, Any]:
    values = dict(zip(PREDICTION_SQL_COLUMNS, row, strict=True))
    return {
        "trial_id": values["trial_id"],
        "model_spec_id": values["model_spec_id"],
        "as_of_date": values["as_of_date"],
        "split_id": values["split_id"],
        "fitted_model_digest": values["fitted_model_digest"],
        "symbol": values["symbol"],
        "stock_name": values["stock_name"],
        "board": values["board"],
        "industry_code": values["industry_code"],
        "industry_name": values["industry_name"],
        "universe_row_id": values["universe_row_id"],
        "score": values["score"],
        "target_label": values["target_label"],
        "target_total_return": values["target_total_return"],
        "target_horizon_days": values["target_horizon_days"],
        "base_horizon_days": values["base_horizon_days"],
        "label_status": values["label_status"],
        "selection_allowed": bool(values["selection_allowed"]),
        "selection_block_reasons": json.loads(values["selection_block_reasons_json"] or "[]"),
        "portfolio_weight": values["portfolio_weight"],
        "rank_weight_feature_values": json.loads(values["rank_weight_feature_values_json"] or "{}"),
    }


def _stream_joined_rows_by_date(
    *,
    feature_matrix_artifact: str | Path,
    label_sqlite_path: Path,
) -> Any:
    conn = sqlite3.connect(label_sqlite_path)
    try:
        cursor = conn.cursor()
        current_date: str | None = None
        current_rows: list[dict[str, Any]] = []
        for feature_row in _iter_artifact_rows(feature_matrix_artifact):
            universe_row_id = str(feature_row.get("universe_row_id") or "")
            cursor.execute(
                "SELECT label_status, net_excess_return_10d_after_costs, excess_return_5d, excess_return_20d, "
                "forward_return_5d, forward_return_10d, forward_return_20d, label_available_dates_json "
                "FROM labels WHERE universe_row_id = ?",
                (universe_row_id,),
            )
            result = cursor.fetchone()
            if result is None:
                continue
            label_values = _label_index_values(result)
            as_of_date = str(feature_row.get("as_of_date") or "")
            if current_date is not None and as_of_date != current_date:
                yield current_date, current_rows
                current_rows = []
            current_date = as_of_date
            current_rows.append(
                {
                    "universe_row_id": universe_row_id,
                    "symbol": feature_row.get("symbol"),
                    "stock_name": feature_row.get("stock_name"),
                    "board": feature_row.get("board"),
                    "industry_code": feature_row.get("industry_code"),
                    "industry_name": feature_row.get("industry_name"),
                    "as_of_date": as_of_date,
                    "feature_row": feature_row,
                    "feature_values_flat": _model_feature_values(feature_row),
                    **label_values,
                }
            )
        if current_date is not None:
            yield current_date, current_rows
    finally:
        conn.close()


def _stream_joined_rows(
    *,
    feature_matrix_artifact: str | Path,
    label_sqlite_path: Path,
) -> Any:
    conn = sqlite3.connect(label_sqlite_path)
    try:
        cursor = conn.cursor()
        for feature_row in _iter_artifact_rows(feature_matrix_artifact):
            universe_row_id = str(feature_row.get("universe_row_id") or "")
            cursor.execute(
                "SELECT label_status, net_excess_return_10d_after_costs, excess_return_5d, excess_return_20d, "
                "forward_return_5d, forward_return_10d, forward_return_20d, label_available_dates_json "
                "FROM labels WHERE universe_row_id = ?",
                (universe_row_id,),
            )
            result = cursor.fetchone()
            if result is None:
                continue
            label_values = _label_index_values(result)
            yield {
                "universe_row_id": universe_row_id,
                "symbol": feature_row.get("symbol"),
                "stock_name": feature_row.get("stock_name"),
                "board": feature_row.get("board"),
                "industry_code": feature_row.get("industry_code"),
                "industry_name": feature_row.get("industry_name"),
                "as_of_date": str(feature_row.get("as_of_date") or ""),
                "feature_row": feature_row,
                "feature_values_flat": _model_feature_values(feature_row),
                **label_values,
            }
    finally:
        conn.close()


def _split_for_test_date(splits: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    split_by_date: dict[str, dict[str, Any]] = {}
    for split in splits:
        if split.get("status") != "ready":
            continue
        for test_date in split.get("test_dates") or []:
            split_by_date[str(test_date)] = split
    return split_by_date


def _sample_prediction_sink() -> dict[str, Any]:
    return {
        "head": [],
        "tail": deque(maxlen=MAX_STORED_PREDICTIONS_PER_TRIAL // 2),
        "seen": 0,
    }


def _add_prediction_sample(sample: dict[str, Any], prediction: dict[str, Any]) -> None:
    sample["seen"] += 1
    head_limit = MAX_STORED_PREDICTIONS_PER_TRIAL // 2
    if len(sample["head"]) < head_limit:
        sample["head"].append(prediction)
    else:
        sample["tail"].append(prediction)


def _finalize_prediction_sample(sample: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [*sample["head"], *list(sample["tail"])]
    return _stored_prediction_sample(rows)


def _empty_stream_trial_state(*, spec_id: str, trial_id: str, selected_top_k: int, horizon_days: int) -> dict[str, Any]:
    return {
        "trial_id": trial_id,
        "model_spec_id": spec_id,
        "selected_top_k": selected_top_k,
        "horizon_days": horizon_days,
        "date_buckets": {},
        "date_rank_ics": [],
        "split_scores_labels": {},
        "top_5_returns_by_date": [],
        "top_5_picks_by_date": [],
        "selected_top_k_returns_by_date": [],
        "selected_top_k_picks_by_date": [],
        "top_picks_by_date": [],
        "rank_ic_values": [],
        "top_5_returns": [],
        "top_10_returns": [],
        "selected_top_k_returns": [],
        "top_quantile_returns": [],
        "spreads": [],
        "prediction_count": 0,
        "labeled_prediction_count": 0,
        "sample": _sample_prediction_sink(),
    }


def _empty_stream_date_bucket(*, as_of_date: str, split_id: str) -> dict[str, Any]:
    return {
        "as_of_date": as_of_date,
        "split_id": split_id,
        "prediction_count": 0,
        "labeled_prediction_count": 0,
        "scores": array("d"),
        "labels": array("d"),
        "top_rows": [],
    }


def _trim_stream_top_rows(rows: list[dict[str, Any]], *, limit: int = STREAM_REPLAY_TOP_ROW_BUFFER_SIZE) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    return sorted(rows, key=lambda row: _safe_float(row.get("score")), reverse=True)[:limit]


def _add_stream_prediction_to_state(state: dict[str, Any], prediction: dict[str, Any]) -> None:
    state["prediction_count"] += 1
    _add_prediction_sample(state["sample"], prediction)
    if prediction.get("target_label") is None:
        return
    state["labeled_prediction_count"] += 1
    as_of_date = str(prediction.get("as_of_date") or "")
    bucket = state["date_buckets"].setdefault(
        as_of_date,
        _empty_stream_date_bucket(as_of_date=as_of_date, split_id=str(prediction.get("split_id") or "")),
    )
    bucket["prediction_count"] += 1
    bucket["labeled_prediction_count"] += 1
    bucket["scores"].append(_safe_float(prediction.get("score")))
    bucket["labels"].append(_safe_float(prediction.get("target_label")))
    if prediction.get("selection_allowed", True):
        bucket["top_rows"].append(prediction)
        if len(bucket["top_rows"]) > STREAM_REPLAY_TOP_ROW_BUFFER_SIZE * 2:
            bucket["top_rows"] = _trim_stream_top_rows(bucket["top_rows"])


def _consume_stream_prediction_bucket(
    *,
    state: dict[str, Any],
    bucket: dict[str, Any],
    selected_top_k: int,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> None:
    if int(bucket.get("labeled_prediction_count") or 0) < 2:
        return
    scores = list(bucket["scores"])
    labels = list(bucket["labels"])
    rank_ic = spearman_correlation(scores, labels)
    as_of_date = str(bucket.get("as_of_date") or "")
    split_id = str(bucket.get("split_id") or "")
    state["rank_ic_values"].append(rank_ic)
    state["date_rank_ics"].append({"as_of_date": as_of_date, "rank_ic": rank_ic, "row_count": len(labels)})
    split_values = state["split_scores_labels"].setdefault(split_id, {"scores": [], "labels": []})
    split_values["scores"].extend(scores)
    split_values["labels"].extend(labels)
    ordered_pairs = sorted(zip(scores, labels, strict=True), key=lambda item: item[0], reverse=True)
    active_rows = _trim_stream_top_rows(list(bucket["top_rows"]))
    if not active_rows:
        state["top_5_returns"].append(0.0)
        state["top_10_returns"].append(0.0)
        state["selected_top_k_returns"].append(0.0)
        state["top_5_returns_by_date"].append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "pick_count": 0,
                "mean_net_excess_return": 0.0,
                "mean_total_return_after_cost": 0.0,
                "mean_target_horizon_days": None,
                "selection_state": "cash",
            }
        )
        state["selected_top_k_returns_by_date"].append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "pick_count": 0,
                "mean_net_excess_return": 0.0,
                "mean_total_return_after_cost": 0.0,
                "mean_target_horizon_days": None,
                "selection_state": "cash",
            }
        )
        return
    ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
    bucket_size = max(1, len(ordered_pairs) // 5)
    top = [label for _score, label in ordered_pairs[:bucket_size]]
    bottom = [label for _score, label in ordered_pairs[-bucket_size:]]
    top_5_rows = ordered[: min(5, len(ordered))]
    top_10_rows = ordered[: min(10, len(ordered))]
    selected_rows = _select_top_k_rows(
        ordered,
        top_k=selected_top_k,
        selection_policy=selection_policy,
        params=params,
    )
    state["top_5_returns"].append(_weighted_return(top_5_rows))
    state["top_10_returns"].append(_weighted_return(top_10_rows))
    state["selected_top_k_returns"].append(
        _weighted_return(selected_rows, selection_policy=selection_policy, params=params)
    )
    state["top_quantile_returns"].append(mean(top))
    state["spreads"].append(mean(top) - mean(bottom))
    state["top_picks_by_date"].extend(_top_picks_by_date(ordered))
    state["top_5_picks_by_date"].extend(_top_k_picks_by_date(ordered, top_k=5))
    state["top_5_returns_by_date"].extend(_top_k_returns_by_date(ordered, top_k=5))
    state["selected_top_k_picks_by_date"].extend(
        _top_k_picks_by_date(
            ordered,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
    )
    state["selected_top_k_returns_by_date"].extend(
        _top_k_returns_by_date(
            ordered,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
    )


def _consume_stream_aggregated_buckets(
    *,
    state: dict[str, Any],
    selected_top_k: int,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> None:
    for _as_of_date, bucket in sorted(state["date_buckets"].items()):
        bucket["top_rows"] = _trim_stream_top_rows(bucket["top_rows"])
        _consume_stream_prediction_bucket(
            state=state,
            bucket=bucket,
            selected_top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
    state["date_buckets"] = {}


def _consume_stream_predictions_for_date(
    *,
    state: dict[str, Any],
    predictions: list[dict[str, Any]],
    selected_top_k: int,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> None:
    if not predictions:
        return
    state["prediction_count"] += len(predictions)
    labeled = [row for row in predictions if row.get("target_label") is not None]
    state["labeled_prediction_count"] += len(labeled)
    for row in predictions:
        _add_prediction_sample(state["sample"], row)
    if len(labeled) < 2:
        return
    scores = [_safe_float(row.get("score")) for row in labeled]
    labels = [_safe_float(row.get("target_label")) for row in labeled]
    rank_ic = spearman_correlation(scores, labels)
    as_of_date = str(predictions[0].get("as_of_date") or "")
    split_id = str(predictions[0].get("split_id") or "")
    state["rank_ic_values"].append(rank_ic)
    state["date_rank_ics"].append({"as_of_date": as_of_date, "rank_ic": rank_ic, "row_count": len(labeled)})
    split_values = state["split_scores_labels"].setdefault(split_id, {"scores": [], "labels": []})
    split_values["scores"].extend(scores)
    split_values["labels"].extend(labels)
    active_rows = [row for row in labeled if row.get("selection_allowed", True)]
    if not active_rows:
        state["top_5_returns"].append(0.0)
        state["top_10_returns"].append(0.0)
        state["selected_top_k_returns"].append(0.0)
        state["top_5_returns_by_date"].append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "pick_count": 0,
                "mean_net_excess_return": 0.0,
                "mean_total_return_after_cost": 0.0,
                "mean_target_horizon_days": None,
                "selection_state": "cash",
            }
        )
        state["selected_top_k_returns_by_date"].append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "pick_count": 0,
                "mean_net_excess_return": 0.0,
                "mean_total_return_after_cost": 0.0,
                "mean_target_horizon_days": None,
                "selection_state": "cash",
            }
        )
        return
    ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
    bucket_size = max(1, len(ordered) // 5)
    top = [_safe_float(row.get("target_label")) for row in ordered[:bucket_size]]
    bottom = [_safe_float(row.get("target_label")) for row in ordered[-bucket_size:]]
    top_5_rows = ordered[: min(5, len(ordered))]
    top_10_rows = ordered[: min(10, len(ordered))]
    selected_rows = _select_top_k_rows(
        ordered,
        top_k=selected_top_k,
        selection_policy=selection_policy,
        params=params,
    )
    state["top_5_returns"].append(_weighted_return(top_5_rows))
    state["top_10_returns"].append(_weighted_return(top_10_rows))
    state["selected_top_k_returns"].append(
        _weighted_return(selected_rows, selection_policy=selection_policy, params=params)
    )
    state["top_quantile_returns"].append(mean(top))
    state["spreads"].append(mean(top) - mean(bottom))
    state["top_picks_by_date"].extend(_top_picks_by_date(labeled))
    state["top_5_picks_by_date"].extend(_top_k_picks_by_date(labeled, top_k=5))
    state["top_5_returns_by_date"].extend(_top_k_returns_by_date(labeled, top_k=5))
    state["selected_top_k_picks_by_date"].extend(
        _top_k_picks_by_date(
            labeled,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
    )
    state["selected_top_k_returns_by_date"].extend(
        _top_k_returns_by_date(
            labeled,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
    )


def _finalize_stream_trial(
    *,
    state: dict[str, Any],
    spec: dict[str, Any],
    params: dict[str, Any],
    fit_summaries: list[dict[str, Any]],
    split_count: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    split_rank_ics = []
    for split_id, values in sorted(state["split_scores_labels"].items()):
        if len(values["scores"]) < 2:
            continue
        split_rank_ics.append(
            {
                "split_id": split_id,
                "rank_ic": spearman_correlation(values["scores"], values["labels"]),
                "row_count": len(values["scores"]),
            }
        )
    metrics = {
        "prediction_count": state["prediction_count"],
        "labeled_prediction_count": state["labeled_prediction_count"],
        "rank_ic_mean": mean(state["rank_ic_values"]) if state["rank_ic_values"] else None,
        "positive_rank_ic_rate": sum(1 for value in state["rank_ic_values"] if value > 0) / len(state["rank_ic_values"])
        if state["rank_ic_values"]
        else None,
        "top_5_net_excess_mean": mean(state["top_5_returns"]) if state["top_5_returns"] else None,
        "positive_top_5_rate": sum(1 for value in state["top_5_returns"] if value > 0) / len(state["top_5_returns"])
        if state["top_5_returns"]
        else None,
        "top_10_net_excess_mean": mean(state["top_10_returns"]) if state["top_10_returns"] else None,
        "selected_top_k": state["selected_top_k"],
        "selected_top_k_net_excess_mean": mean(state["selected_top_k_returns"])
        if state["selected_top_k_returns"]
        else None,
        "positive_selected_top_k_rate": sum(1 for value in state["selected_top_k_returns"] if value > 0)
        / len(state["selected_top_k_returns"])
        if state["selected_top_k_returns"]
        else None,
        "top_quantile_net_excess_mean": mean(state["top_quantile_returns"]) if state["top_quantile_returns"] else None,
        "top_bottom_spread_mean": mean(state["spreads"]) if state["spreads"] else None,
        "evaluated_date_count": len(state["rank_ic_values"]),
    }
    trial_summary = {
        "trial_id": state["trial_id"],
        "model_spec_id": state["model_spec_id"],
        "selection_policy": spec.get("selection_policy") or {},
        "params": params,
        "metrics": metrics,
        "fit_summaries": fit_summaries,
        "gate_status": "blocked",
        "blocking_gate_ids": _trial_blockers(metrics, split_count, model_spec=spec),
    }
    selected_picks = state["selected_top_k_picks_by_date"]
    trial_diagnostic = {
        "trial_id": state["trial_id"],
        "model_spec_id": state["model_spec_id"],
        "target_horizon_days": state["horizon_days"],
        "split_rank_ics": split_rank_ics,
        "date_rank_ics": state["date_rank_ics"],
        "top_picks_by_date": state["top_picks_by_date"],
        "top_5_picks_by_date": state["top_5_picks_by_date"],
        "top_5_returns_by_date": state["top_5_returns_by_date"],
        "selected_top_k": state["selected_top_k"],
        "selected_top_k_picks_by_date": selected_picks,
        "selected_top_k_returns_by_date": state["selected_top_k_returns_by_date"],
        "selected_top_k_industry_exposure_by_month": _industry_exposure_by_month(selected_picks),
    }
    return trial_summary, trial_diagnostic, _finalize_prediction_sample(state["sample"])


def build_streamed_walk_forward_model_candidate_run_artifact(
    *,
    validation_run_id: str,
    feature_matrix_artifact: str | Path,
    label_matrix_artifact: str | Path,
    model_spec_registry: dict[str, Any],
    min_train_dates: int = 60,
    test_window_dates: int = 20,
    selected_model_spec_ids: list[str] | None = None,
    source_db_snapshot_id: str | None = None,
    source_data_time_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature_metadata = _load_artifact_metadata_without_rows(feature_matrix_artifact)
    label_metadata = _load_artifact_metadata_without_rows(label_matrix_artifact)
    specs = list(model_spec_registry.get("model_specs") or [])
    selected = set(selected_model_spec_ids or [str(spec.get("model_spec_id")) for spec in specs])
    known = {str(spec.get("model_spec_id")) for spec in specs}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"unregistered model specs requested: {', '.join(unknown)}")
    unsupported = [
        str(spec.get("model_spec_id") or "")
        for spec in specs
        if str(spec.get("model_spec_id") or "") in selected
        and str(spec.get("model_type") or "") not in _deterministic_score_only_model_types()
        and str(spec.get("model_type") or "") not in _stream_fitted_model_types()
    ]
    if unsupported:
        raise ValueError(
            "streamed matrix replay only supports deterministic score-only or stream-fitted specs: "
            + ", ".join(sorted(unsupported))
        )
    with tempfile.TemporaryDirectory(prefix="stock-dashboard-label-index-") as temp_dir:
        label_sqlite_path = Path(temp_dir) / "labels.sqlite"
        ready_date_counts, indexed_label_count = _build_stream_label_index(
            label_matrix_artifact=label_matrix_artifact,
            sqlite_path=label_sqlite_path,
        )
        dates = sorted(date for date, count in ready_date_counts.items() if count > 0)
        splits = _walk_forward_splits(dates, min_train_dates=min_train_dates, test_window_dates=test_window_dates)
        split_by_test_date = _split_for_test_date(splits)
        selected_stream_fit_horizons = {
            int(spec.get("prediction_horizon_days") or 10)
            for spec in specs
            if str(spec.get("model_spec_id") or "") in selected
            and str(spec.get("model_type") or "") == "regularized_rank_linear"
        }
        tail_capture_configs: set[tuple[int, int, float]] = set()
        for spec in specs:
            if str(spec.get("model_spec_id") or "") not in selected:
                continue
            if str(spec.get("model_type") or "") != "tail_capture_linear_ranker":
                continue
            horizon_days = int(spec.get("prediction_horizon_days") or 10)
            for params in _grid_trials(spec.get("hyperparameter_grid") or {}):
                tail_capture_configs.add(
                    (
                        horizon_days,
                        max(1, int(_safe_float(params.get("tail_positive_top_k"), 20.0))),
                        _safe_float(params.get("min_avg_amount_20d"), 0.0),
                    )
                )
        stream_fit_stats_by_horizon_date = (
            _build_stream_linear_fit_stats_by_date(
                feature_matrix_artifact=feature_matrix_artifact,
                label_sqlite_path=label_sqlite_path,
                horizons=selected_stream_fit_horizons,
            )
            if selected_stream_fit_horizons
            else {}
        )
        tail_capture_stats_by_config_date = (
            _build_stream_tail_capture_fit_stats_by_config_date(
                feature_matrix_artifact=feature_matrix_artifact,
                label_sqlite_path=label_sqlite_path,
                configs=tail_capture_configs,
            )
            if tail_capture_configs
            else {}
        )
        fit_summaries_by_trial: dict[str, list[dict[str, Any]]] = {}
        fitted_models_by_trial_split: dict[tuple[str, str], dict[str, Any]] = {}
        trial_specs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        trial_states: dict[str, dict[str, Any]] = {}
        for spec in specs:
            spec_id = str(spec.get("model_spec_id") or "")
            if spec_id not in selected:
                continue
            spec_type = str(spec.get("model_type") or "")
            horizon_days = int(spec.get("prediction_horizon_days") or 10)
            selected_top_k = max(1, int(_safe_float((spec.get("selection_policy") or {}).get("top_k"), 5.0)))
            for trial_index, params in enumerate(_grid_trials(spec.get("hyperparameter_grid") or {})):
                trial_id = f"{spec_id}:trial-{trial_index:03d}"
                fit_summaries: list[dict[str, Any]] = []
                for split in splits:
                    if split.get("status") != "ready":
                        continue
                    train_dates = [str(day) for day in split["train_dates"]]
                    candidate_train_date_count = len(train_dates)
                    requires_fit = spec_type not in _deterministic_score_only_model_types()
                    if spec_type == "regularized_rank_linear":
                        training_stats = stream_fit_stats_by_horizon_date.get(horizon_days, {})
                    elif spec_type == "tail_capture_linear_ranker":
                        training_stats = tail_capture_stats_by_config_date.get(_tail_capture_config_key(
                            horizon_days=horizon_days,
                            positive_top_k=max(1, int(_safe_float(params.get("tail_positive_top_k"), 20.0))),
                            min_avg_amount_20d=_safe_float(params.get("min_avg_amount_20d"), 0.0),
                        ), {})
                    else:
                        training_stats = {}
                    if requires_fit:
                        train_dates = mature_training_dates(
                            train_dates,
                            available_by_date={day: stats.get("label_available_on") for day, stats in training_stats.items()},
                            test_start=str(split["test_dates"][0]),
                        )
                    if spec_type == "regularized_rank_linear":
                        fitted_model = _fit_stream_model_from_date_stats(
                            stats_by_date=stream_fit_stats_by_horizon_date.get(horizon_days, {}),
                            train_dates=train_dates,
                            model_spec=spec,
                            params=params,
                        )
                    elif spec_type == "tail_capture_linear_ranker":
                        config_key = _tail_capture_config_key(
                            horizon_days=horizon_days,
                            positive_top_k=max(1, int(_safe_float(params.get("tail_positive_top_k"), 20.0))),
                            min_avg_amount_20d=_safe_float(params.get("min_avg_amount_20d"), 0.0),
                        )
                        fitted_model = _fit_stream_tail_capture_model_from_date_stats(
                            stats_by_date=tail_capture_stats_by_config_date.get(config_key, {}),
                            train_dates=train_dates,
                            model_spec=spec,
                            params=params,
                        )
                    else:
                        fitted_model = _fit_model([], model_spec=spec, params=params)
                    fitted_model_digest = _stable_digest(
                        {
                            "trial_id": trial_id,
                            "split_id": split["split_id"],
                            "fitted_model": fitted_model,
                            "stream_replay": True,
                        }
                    )
                    fitted_models_by_trial_split[(trial_id, str(split["split_id"]))] = fitted_model
                    train_row_count = int(fitted_model.get("train_row_count") or 0) if requires_fit else sum(ready_date_counts.get(str(day), 0) for day in train_dates)
                    fit_summaries.append(
                        {
                            "split_id": split["split_id"],
                            "train_date_count": len(train_dates),
                            "candidate_train_date_count": candidate_train_date_count,
                            "excluded_immature_or_unknown_date_count": candidate_train_date_count - len(train_dates),
                            "fit_status": (
                                ("blocked_no_mature_training_labels" if not train_row_count
                                 else "blocked_insufficient_mature_training_dates")
                                if requires_fit and len(train_dates) < min_train_dates else "ready"
                            ),
                            "test_date_count": len(split["test_dates"]),
                            "train_row_count": train_row_count,
                            "fitted_model_family": fitted_model.get("model_family"),
                            "fitted_model_digest": fitted_model_digest,
                            "fitted_model_summary": _fitted_model_summary(fitted_model),
                        }
                    )
                fit_summaries_by_trial[trial_id] = fit_summaries
                trial_specs[trial_id] = (spec, params)
                trial_states[trial_id] = _empty_stream_trial_state(
                    spec_id=spec_id,
                    trial_id=trial_id,
                    selected_top_k=selected_top_k,
                    horizon_days=horizon_days,
                )

        joined_row_count = 0
        evaluable_keys: set[str] = set()
        conn = sqlite3.connect(label_sqlite_path)
        try:
            _configure_stream_replay_sqlite(conn)
            label_cursor = conn.cursor()
            for feature_row in _iter_artifact_rows(feature_matrix_artifact):
                universe_row_id = str(feature_row.get("universe_row_id") or "")
                label_cursor.execute(
                    "SELECT label_status, net_excess_return_10d_after_costs, excess_return_5d, excess_return_20d, "
                    "forward_return_5d, forward_return_10d, forward_return_20d, label_available_dates_json "
                    "FROM labels WHERE universe_row_id = ?",
                    (universe_row_id,),
                )
                label_result = label_cursor.fetchone()
                if label_result is None:
                    continue
                label_values = _label_index_values(label_result)
                joined = {
                    "universe_row_id": universe_row_id,
                    "symbol": feature_row.get("symbol"),
                    "stock_name": feature_row.get("stock_name"),
                    "board": feature_row.get("board"),
                    "industry_code": feature_row.get("industry_code"),
                    "industry_name": feature_row.get("industry_name"),
                    "as_of_date": str(feature_row.get("as_of_date") or ""),
                    "feature_row": feature_row,
                    "feature_values_flat": _model_feature_values(feature_row),
                    **label_values,
                }
                as_of_date = str(joined.get("as_of_date") or "")
                split = split_by_test_date.get(as_of_date)
                if split is None:
                    continue
                joined_row_count += 1
                evaluable_keys.add(str(joined["universe_row_id"]))
                for trial_id, (spec, params) in trial_specs.items():
                    horizon_days = int(spec.get("prediction_horizon_days") or 10)
                    if _target(joined, horizon_days=horizon_days) is None:
                        continue
                    fit_summary = next(
                        item for item in fit_summaries_by_trial[trial_id] if item["split_id"] == split["split_id"]
                    )
                    if fit_summary["fit_status"] != "ready":
                        continue
                    prediction = _make_prediction_from_joined_row(
                        joined=joined,
                        spec=spec,
                        params=params,
                        trial_id=trial_id,
                        split_id=str(split["split_id"]),
                        fitted_model_digest=str(fit_summary["fitted_model_digest"]),
                        fitted_model=fitted_models_by_trial_split.get((trial_id, str(split["split_id"]))),
                        horizon_days=horizon_days,
                    )
                    _add_stream_prediction_to_state(trial_states[trial_id], prediction)
            for trial_id, (spec, params) in trial_specs.items():
                selected_top_k = trial_states[trial_id]["selected_top_k"]
                _consume_stream_aggregated_buckets(
                    state=trial_states[trial_id],
                    selected_top_k=selected_top_k,
                    selection_policy=spec.get("selection_policy") or {},
                    params=params,
                )
        finally:
            conn.close()

        trial_summaries: list[dict[str, Any]] = []
        trial_diagnostics: list[dict[str, Any]] = []
        prediction_rows: list[dict[str, Any]] = []
        total_prediction_row_count = 0
        ready_split_count = len([split for split in splits if split.get("status") == "ready"])
        for trial_id, state in trial_states.items():
            spec, params = trial_specs[trial_id]
            summary, diagnostic, sample_rows = _finalize_stream_trial(
                state=state,
                spec=spec,
                params=params,
                fit_summaries=fit_summaries_by_trial[trial_id],
                split_count=ready_split_count,
            )
            trial_summaries.append(summary)
            trial_diagnostics.append(diagnostic)
            prediction_rows.extend(sample_rows)
            total_prediction_row_count += int(state["prediction_count"])

    max_split_count = len(splits)
    resolved_source_db_snapshot_id = source_db_snapshot_id or feature_metadata.get("source_db_snapshot_id")
    resolved_source_data_time_range = source_data_time_range or feature_metadata.get("source_data_time_range")
    content_digest = _stable_digest(
        {
            "feature_matrix": feature_metadata.get("artifact_id"),
            "label_matrix": label_metadata.get("artifact_id"),
            "registry": model_spec_registry.get("artifact_id"),
            "source_db_snapshot_id": resolved_source_db_snapshot_id,
            "source_data_time_range": resolved_source_data_time_range,
            "max_split_count": max_split_count,
            "trial_summaries": trial_summaries,
            "trial_diagnostics": trial_diagnostics,
            "total_prediction_row_count": total_prediction_row_count,
            "prediction_rows": prediction_rows,
            "stream_replay": True,
        }
    )
    artifact_id = f"walk-forward-model-candidate-run-{content_digest[:16]}"
    return {
        "artifact_type": "walk_forward_model_candidate_run",
        "schema_version": MODEL_CANDIDATE_RUN_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": resolved_source_db_snapshot_id,
        "source_data_time_range": resolved_source_data_time_range,
        "feature_version": feature_metadata.get("feature_version"),
        "label_version": label_metadata.get("label_version"),
        "code_version": "unresolved_local_checkout",
        "config_version": "shortpick_model_candidate_runner:v2_label_maturity:streamed_matrix_replay",
        "validation_protocol": {
            "runner_policy": "registered_model_specs_only",
            "primary_row_source": "streamed_pit_feature_matrix_joined_to_sqlite_indexed_executable_label_matrix",
            "evaluation_row_policy": "label_status_ready_and_target_label_present_only",
            "training_label_policy": "complete_cohort_actual_outcome_dates_strictly_before_test_start",
            "unknown_training_label_dates": "exclude_and_block_if_insufficient_mature_dates",
            "evaluation_limitations": [
                "evaluation_conditions_on_future_label_readiness_not_unconditional_account_performance",
                "legacy_learning_results_require_label_maturity_revalidation",
            ],
            "production_effect": "forbidden",
            "min_train_dates": min_train_dates,
            "test_window_dates": test_window_dates,
            "stream_replay": True,
            "stream_replay_limit": "deterministic_score_only_specs",
        },
        "gate_readout": {
            "gate_status": "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "candidate_run_only",
            "blocking_gate_ids": ["comparison_report_pending", "governance_promotion_pending"],
        },
        "claim_ceiling": "candidate_run_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_feature_matrix_id": feature_metadata.get("artifact_id"),
        "source_label_matrix_id": label_metadata.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "split_count": max_split_count,
        "trial_count": len(trial_summaries),
        "joined_row_count": joined_row_count,
        "evaluable_row_count": len(evaluable_keys) or indexed_label_count,
        "prediction_row_count": total_prediction_row_count,
        "stored_prediction_row_count": len(prediction_rows),
        "prediction_rows_truncated": total_prediction_row_count > len(prediction_rows),
        "prediction_storage_policy": {
            "mode": "bounded_inline_sample_with_full_trial_diagnostics_streamed_matrix_replay",
            "max_stored_predictions_per_trial": MAX_STORED_PREDICTIONS_PER_TRIAL,
        },
        "splits": splits,
        "trial_summaries": trial_summaries,
        "trial_diagnostics": trial_diagnostics,
        "prediction_rows": prediction_rows,
        "run_content_digest": content_digest,
    }


def build_deterministic_full_history_model_candidate_run_artifact(
    *,
    validation_run_id: str,
    feature_matrix_artifact: str | Path,
    model_spec_registry: dict[str, Any],
    selected_model_spec_ids: list[str],
) -> dict[str, Any]:
    """Build a full-history deterministic selection source without forward-label gating.

    This is intentionally limited to deterministic score-only specs. It exists for
    account replay over the full feature window, where selection itself must not be
    truncated by walk-forward train/test splits or forward-label readiness.
    """

    feature_metadata = _load_artifact_metadata_without_rows(feature_matrix_artifact)
    specs = list(model_spec_registry.get("model_specs") or [])
    selected = set(selected_model_spec_ids)
    known = {str(spec.get("model_spec_id")) for spec in specs}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"unregistered model specs requested: {', '.join(unknown)}")
    unsupported = [
        str(spec.get("model_spec_id") or "")
        for spec in specs
        if str(spec.get("model_spec_id") or "") in selected
        and str(spec.get("model_type") or "") not in _deterministic_score_only_model_types()
    ]
    if unsupported:
        raise ValueError(
            "full-history deterministic selection only supports deterministic score-only specs: "
            + ", ".join(sorted(unsupported))
        )

    trial_specs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    fitted_models: dict[str, dict[str, Any]] = {}
    trial_states: dict[str, dict[str, Any]] = {}
    for spec in specs:
        spec_id = str(spec.get("model_spec_id") or "")
        if spec_id not in selected:
            continue
        horizon_days = int(spec.get("prediction_horizon_days") or 10)
        selected_top_k = max(1, int(_safe_float((spec.get("selection_policy") or {}).get("top_k"), 5.0)))
        for trial_index, params in enumerate(_grid_trials(spec.get("hyperparameter_grid") or {})):
            trial_id = f"{spec_id}:trial-{trial_index:03d}"
            trial_specs[trial_id] = (spec, params)
            fitted_models[trial_id] = _fit_model([], model_spec=spec, params=params)
            trial_states[trial_id] = _empty_stream_trial_state(
                spec_id=spec_id,
                trial_id=trial_id,
                selected_top_k=selected_top_k,
                horizon_days=horizon_days,
            )

    row_count = 0
    selected_date_count_by_trial: dict[str, set[str]] = {trial_id: set() for trial_id in trial_states}
    current_date: str | None = None
    current_predictions_by_trial: dict[str, list[dict[str, Any]]] = {trial_id: [] for trial_id in trial_states}

    def _flush_current_date() -> None:
        for trial_id, predictions in current_predictions_by_trial.items():
            if not predictions:
                continue
            spec, params = trial_specs[trial_id]
            before = len(trial_states[trial_id]["selected_top_k_picks_by_date"])
            _consume_full_history_selection_date(
                state=trial_states[trial_id],
                predictions=predictions,
                selection_policy=spec.get("selection_policy") or {},
                params=params,
            )
            after = len(trial_states[trial_id]["selected_top_k_picks_by_date"])
            if after > before:
                selected_date_count_by_trial[trial_id].add(str(predictions[0].get("as_of_date") or ""))
            predictions.clear()

    for feature_row in _iter_artifact_rows(feature_matrix_artifact):
        as_of_date = str(feature_row.get("as_of_date") or "")
        if current_date is None:
            current_date = as_of_date
        elif as_of_date != current_date:
            _flush_current_date()
            current_date = as_of_date
        row_count += 1
        feature_values = _model_feature_values(feature_row)
        joined = {
            "universe_row_id": str(feature_row.get("universe_row_id") or ""),
            "symbol": feature_row.get("symbol"),
            "stock_name": feature_row.get("stock_name"),
            "board": feature_row.get("board"),
            "industry_code": feature_row.get("industry_code"),
            "industry_name": feature_row.get("industry_name"),
            "as_of_date": as_of_date,
            "feature_row": feature_row,
            "feature_values_flat": feature_values,
            "label_status": "not_required_for_full_history_selection",
            "target_label": None,
            "target_labels_by_horizon": {},
            "target_total_return": None,
            "target_total_returns_by_horizon": {},
        }
        for trial_id, (spec, params) in trial_specs.items():
            horizon_days = int(spec.get("prediction_horizon_days") or 10)
            prediction = _make_prediction_from_joined_row(
                joined=joined,
                spec=spec,
                params=params,
                trial_id=trial_id,
                split_id="full-history-deterministic-selection",
                fitted_model_digest="deterministic-score-only-no-fit",
                fitted_model=fitted_models[trial_id],
                horizon_days=horizon_days,
            )
            current_predictions_by_trial[trial_id].append(prediction)
            _add_prediction_sample(trial_states[trial_id]["sample"], prediction)
            trial_states[trial_id]["prediction_count"] += 1
    _flush_current_date()

    trial_summaries: list[dict[str, Any]] = []
    trial_diagnostics: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    total_prediction_row_count = 0
    for trial_id, state in trial_states.items():
        spec, params = trial_specs[trial_id]
        selected_picks = state["selected_top_k_picks_by_date"]
        metrics = {
            "prediction_count": state["prediction_count"],
            "selected_top_k": state["selected_top_k"],
            "selected_pick_count": len(selected_picks),
            "selected_signal_day_count": len(selected_date_count_by_trial[trial_id]),
            "label_evaluation_status": "not_required_for_full_history_selection",
        }
        trial_summaries.append(
            {
                "trial_id": trial_id,
                "model_spec_id": state["model_spec_id"],
                "selection_policy": spec.get("selection_policy") or {},
                "params": params,
                "metrics": metrics,
                "fit_summaries": [],
                "gate_status": "blocked",
                "blocking_gate_ids": ["account_replay_pending", "fair_comparison_pending"],
            }
        )
        trial_diagnostics.append(
            {
                "trial_id": trial_id,
                "model_spec_id": state["model_spec_id"],
                "target_horizon_days": state["horizon_days"],
                "split_rank_ics": [],
                "date_rank_ics": [],
                "top_picks_by_date": state["top_picks_by_date"],
                "top_5_picks_by_date": state["top_5_picks_by_date"],
                "top_5_returns_by_date": [],
                "selected_top_k": state["selected_top_k"],
                "selected_top_k_picks_by_date": selected_picks,
                "selected_top_k_returns_by_date": [],
                "selected_top_k_industry_exposure_by_month": _industry_exposure_by_month(selected_picks),
            }
        )
        sample_rows = _finalize_prediction_sample(state["sample"])
        prediction_rows.extend(sample_rows)
        total_prediction_row_count += int(state["prediction_count"])

    content_digest = _stable_digest(
        {
            "feature_matrix": feature_metadata.get("artifact_id"),
            "registry": model_spec_registry.get("artifact_id"),
            "source_data_time_range": feature_metadata.get("source_data_time_range"),
            "trial_summaries": trial_summaries,
            "trial_diagnostics": trial_diagnostics,
            "prediction_row_count": total_prediction_row_count,
            "mode": "full_history_deterministic_selection",
        }
    )
    return {
        "artifact_type": "walk_forward_model_candidate_run",
        "schema_version": MODEL_CANDIDATE_RUN_SCHEMA_VERSION,
        "artifact_id": f"walk-forward-model-candidate-run-{content_digest[:16]}",
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": feature_metadata.get("source_db_snapshot_id"),
        "source_data_time_range": feature_metadata.get("source_data_time_range"),
        "feature_version": feature_metadata.get("feature_version"),
        "label_version": "not_required_for_full_history_deterministic_selection",
        "code_version": "unresolved_local_checkout",
        "config_version": "shortpick_model_candidate_runner:v1:full_history_deterministic_selection",
        "validation_protocol": {
            "runner_policy": "registered_deterministic_model_specs_only",
            "primary_row_source": "streamed_pit_feature_matrix_without_forward_label_filter",
            "evaluation_row_policy": "all_feature_rows_selection_no_forward_label_required",
            "production_effect": "forbidden",
            "stream_replay": True,
            "walk_forward_split_gating": False,
        },
        "gate_readout": {
            "gate_status": "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "candidate_run_only",
            "blocking_gate_ids": ["account_replay_pending", "fair_comparison_pending"],
        },
        "claim_ceiling": "candidate_run_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_feature_matrix_id": feature_metadata.get("artifact_id"),
        "source_label_matrix_id": None,
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "split_count": 1,
        "trial_count": len(trial_summaries),
        "joined_row_count": row_count,
        "evaluable_row_count": row_count,
        "prediction_row_count": total_prediction_row_count,
        "stored_prediction_row_count": len(prediction_rows),
        "prediction_rows_truncated": total_prediction_row_count > len(prediction_rows),
        "prediction_storage_policy": {
            "mode": "bounded_inline_sample_with_full_trial_diagnostics_full_history_selection",
            "max_stored_predictions_per_trial": MAX_STORED_PREDICTIONS_PER_TRIAL,
        },
        "splits": [
            {
                "split_id": "full-history-deterministic-selection",
                "status": "ready",
                "train_dates": [],
                "test_dates": [],
                "purge_days": 0,
                "embargo_days": 0,
            }
        ],
        "trial_summaries": trial_summaries,
        "trial_diagnostics": trial_diagnostics,
        "prediction_rows": prediction_rows,
        "run_content_digest": content_digest,
    }


def _consume_full_history_selection_date(
    *,
    state: dict[str, Any],
    predictions: list[dict[str, Any]],
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> None:
    active_rows = [row for row in predictions if row.get("selection_allowed", True)]
    if not active_rows:
        return
    ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
    selected_top_k = int(state["selected_top_k"])
    as_of_date = str(predictions[0].get("as_of_date") or "")
    state["selected_top_k_picks_by_date"].extend(
        _top_k_picks_from_ordered_rows(
            as_of_date=as_of_date,
            ordered=ordered,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
    )


def build_walk_forward_model_candidate_run_artifact(
    *,
    validation_run_id: str,
    feature_matrix: dict[str, Any],
    label_matrix: dict[str, Any],
    model_spec_registry: dict[str, Any],
    min_train_dates: int = 60,
    test_window_dates: int = 20,
    selected_model_spec_ids: list[str] | None = None,
) -> dict[str, Any]:
    joined_rows = _join_rows(feature_matrix, label_matrix)
    specs = list(model_spec_registry.get("model_specs") or [])
    selected = set(selected_model_spec_ids or [str(spec.get("model_spec_id")) for spec in specs])
    known = {str(spec.get("model_spec_id")) for spec in specs}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"unregistered model specs requested: {', '.join(unknown)}")
    trial_summaries: list[dict[str, Any]] = []
    trial_diagnostics: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    total_prediction_row_count = 0
    all_evaluable_keys: set[str] = set()
    max_split_count = 0

    for spec in specs:
        spec_id = str(spec.get("model_spec_id") or "")
        if spec_id not in selected:
            continue
        selection_policy = spec.get("selection_policy") or {}
        horizon_days = int(spec.get("prediction_horizon_days") or 10)
        evaluable_rows = [
            row
            for row in joined_rows
            if row.get("label_status") == "ready"
            and _target(row, horizon_days=horizon_days) is not None
        ]
        all_evaluable_keys.update(str(row["universe_row_id"]) for row in evaluable_rows)
        evaluable_rows_by_date: dict[str, list[dict[str, Any]]] = {}
        for row in evaluable_rows:
            evaluable_rows_by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
        dates = sorted({str(row.get("as_of_date")) for row in evaluable_rows if row.get("as_of_date")})
        splits = _walk_forward_splits(dates, min_train_dates=min_train_dates, test_window_dates=test_window_dates)
        max_split_count = max(max_split_count, len(splits))
        trials = _grid_trials(spec.get("hyperparameter_grid") or {})
        selected_top_k = max(1, int(_safe_float((spec.get("selection_policy") or {}).get("top_k"), 5.0)))
        for trial_index, params in enumerate(trials):
            trial_id = f"{spec_id}:trial-{trial_index:03d}"
            trial_predictions: list[dict[str, Any]] = []
            fit_summaries: list[dict[str, Any]] = []
            for split in splits:
                if split["status"] != "ready":
                    continue
                train_dates = list(split["train_dates"])
                test_dates = list(split["test_dates"])
                requires_fit = str(spec.get("model_type") or "") not in _deterministic_score_only_model_types()
                candidate_train_date_count = len(train_dates)
                if requires_fit:
                    train_dates = mature_training_dates(
                        train_dates,
                        available_by_date={
                            day: cohort_available_day(evaluable_rows_by_date.get(day, []), horizon_days=horizon_days)
                            for day in train_dates
                        },
                        test_start=test_dates[0],
                    )
                train_rows = [
                    row
                    for train_date in train_dates
                    for row in evaluable_rows_by_date.get(str(train_date), [])
                ]
                fitted_model = _fit_model(train_rows, model_spec=spec, params=params)
                fitted_model_digest = _stable_digest(
                    {
                        "trial_id": trial_id,
                        "split_id": split["split_id"],
                        "fitted_model": fitted_model,
                    }
                )
                test_rows = [
                    row
                    for test_date in test_dates
                    for row in evaluable_rows_by_date.get(str(test_date), [])
                ]
                fit_summaries.append(
                    {
                        "split_id": split["split_id"],
                        "train_date_count": len(train_dates),
                        "candidate_train_date_count": candidate_train_date_count,
                        "excluded_immature_or_unknown_date_count": candidate_train_date_count - len(train_dates),
                        "fit_status": (
                            ("blocked_no_mature_training_labels" if not train_rows
                             else "blocked_insufficient_mature_training_dates")
                            if requires_fit and len(train_dates) < min_train_dates else "ready"
                        ),
                        "test_date_count": len(test_dates),
                        "train_row_count": fitted_model.get("train_row_count"),
                        "fitted_model_family": fitted_model.get("model_family"),
                        "fitted_model_digest": fitted_model_digest,
                        "fitted_model_summary": _fitted_model_summary(fitted_model),
                    }
                )
                if requires_fit and len(train_dates) < min_train_dates:
                    continue
                for joined in test_rows:
                    selection_allowed, selection_block_reasons = _selection_allowed(
                        joined["feature_values_flat"],
                        selection_policy=selection_policy,
                        params=params,
                    )
                    portfolio_weight = _position_weight(
                        joined["feature_values_flat"],
                        selection_policy=selection_policy,
                        params=params,
                    )
                    score = _score_row(
                        joined["feature_row"],
                        model_spec=spec,
                        params=params,
                        fitted_model=fitted_model,
                        feature_values=joined["feature_values_flat"],
                    )
                    target_horizon_days = _exit_horizon_days(
                        joined["feature_values_flat"],
                        selection_policy=selection_policy,
                        params=params,
                        default_horizon_days=horizon_days,
                    )
                    prediction = {
                        "trial_id": trial_id,
                        "model_spec_id": spec_id,
                        "split_id": split["split_id"],
                        "fitted_model_digest": fitted_model_digest,
                        "symbol": joined["symbol"],
                        "stock_name": joined.get("stock_name"),
                        "board": joined.get("board"),
                        "industry_code": joined.get("industry_code"),
                        "industry_name": joined.get("industry_name"),
                        "as_of_date": joined["as_of_date"],
                        "universe_row_id": joined["universe_row_id"],
                        "score": score,
                        **_exhaustion_reference_metadata(
                            model_spec=spec,
                            params=params,
                            feature_values=joined["feature_values_flat"],
                        ),
                        "target_label": _target(joined, horizon_days=target_horizon_days),
                        "target_total_return": _target_total_return(joined, horizon_days=target_horizon_days),
                        "target_horizon_days": target_horizon_days,
                        "base_horizon_days": horizon_days,
                        "label_status": joined["label_status"],
                        "selection_allowed": selection_allowed,
                        "selection_block_reasons": selection_block_reasons,
                        "portfolio_weight": portfolio_weight if selection_allowed else 0.0,
                        "rank_weight_feature_values": _rank_signal_feature_subset(joined["feature_values_flat"]),
                    }
                    trial_predictions.append(prediction)
            metrics = _trial_metrics(
                trial_predictions,
                selected_top_k=selected_top_k,
                selection_policy=selection_policy,
                params=params,
            )
            diagnostics = _trial_diagnostics(
                trial_predictions,
                selected_top_k=selected_top_k,
                selection_policy=selection_policy,
                params=params,
            )
            trial_summaries.append(
                {
                    "trial_id": trial_id,
                    "model_spec_id": spec_id,
                    "selection_policy": spec.get("selection_policy") or {},
                    "params": params,
                    "metrics": metrics,
                    "fit_summaries": fit_summaries,
                    "gate_status": "blocked",
                    "blocking_gate_ids": _trial_blockers(metrics, len(splits), model_spec=spec),
                }
            )
            trial_diagnostics.append(
                {
                    "trial_id": trial_id,
                    "model_spec_id": spec_id,
                    "target_horizon_days": horizon_days,
                    **diagnostics,
                }
            )
            total_prediction_row_count += len(trial_predictions)
            prediction_rows.extend(_stored_prediction_sample(trial_predictions))

    content_digest = _stable_digest(
        {
            "feature_matrix": feature_matrix.get("artifact_id"),
            "label_matrix": label_matrix.get("artifact_id"),
            "registry": model_spec_registry.get("artifact_id"),
            "max_split_count": max_split_count,
            "trial_summaries": trial_summaries,
            "trial_diagnostics": trial_diagnostics,
            "total_prediction_row_count": total_prediction_row_count,
            "prediction_rows": prediction_rows,
        }
    )
    artifact_id = f"walk-forward-model-candidate-run-{content_digest[:16]}"
    return {
        "artifact_type": "walk_forward_model_candidate_run",
        "schema_version": MODEL_CANDIDATE_RUN_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": feature_matrix.get("source_db_snapshot_id"),
        "source_data_time_range": feature_matrix.get("source_data_time_range"),
        "feature_version": feature_matrix.get("feature_version"),
        "label_version": label_matrix.get("label_version"),
        "code_version": "unresolved_local_checkout",
        "config_version": "shortpick_model_candidate_runner:v2_label_maturity",
        "validation_protocol": {
            "runner_policy": "registered_model_specs_only",
            "primary_row_source": "pit_feature_matrix_joined_to_executable_label_matrix",
            "evaluation_row_policy": "label_status_ready_and_target_label_present_only",
            "training_label_policy": "complete_cohort_actual_outcome_dates_strictly_before_test_start",
            "unknown_training_label_dates": "exclude_and_block_if_insufficient_mature_dates",
            "evaluation_limitations": [
                "evaluation_conditions_on_future_label_readiness_not_unconditional_account_performance",
                "legacy_learning_results_require_label_maturity_revalidation",
            ],
            "production_effect": "forbidden",
            "min_train_dates": min_train_dates,
            "test_window_dates": test_window_dates,
        },
        "gate_readout": {
            "gate_status": "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "candidate_run_only",
            "blocking_gate_ids": ["comparison_report_pending", "governance_promotion_pending"],
        },
        "claim_ceiling": "candidate_run_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_feature_matrix_id": feature_matrix.get("artifact_id"),
        "source_label_matrix_id": label_matrix.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "split_count": max_split_count,
        "trial_count": len(trial_summaries),
        "joined_row_count": len(joined_rows),
        "evaluable_row_count": len(all_evaluable_keys),
        "prediction_row_count": total_prediction_row_count,
        "stored_prediction_row_count": len(prediction_rows),
        "prediction_rows_truncated": total_prediction_row_count > len(prediction_rows),
        "prediction_storage_policy": {
            "mode": "bounded_inline_sample_with_full_trial_diagnostics",
            "max_stored_predictions_per_trial": MAX_STORED_PREDICTIONS_PER_TRIAL,
        },
        "splits": splits,
        "trial_summaries": trial_summaries,
        "trial_diagnostics": trial_diagnostics,
        "prediction_rows": prediction_rows,
        "run_content_digest": content_digest,
    }


def build_streamed_top_candidate_inventory_artifact(
    *,
    validation_run_id: str,
    feature_matrix_artifact: str | Path,
    label_matrix_artifact: str | Path,
    model_spec_registry: dict[str, Any],
    trial_id: str,
    top_n: int = 20,
    min_train_dates: int = 60,
    test_window_dates: int = 20,
    source_db_snapshot_id: str | None = None,
    source_data_time_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    feature_metadata = _load_artifact_metadata_without_rows(feature_matrix_artifact)
    label_metadata = _load_artifact_metadata_without_rows(label_matrix_artifact)
    spec, params = _resolve_registry_trial(model_spec_registry, trial_id)
    spec_id = str(spec.get("model_spec_id") or "")
    if str(spec.get("model_type") or "") not in _deterministic_score_only_model_types():
        raise ValueError(f"top candidate inventory only supports deterministic score-only specs: {spec_id}")
    horizon_days = int(spec.get("prediction_horizon_days") or 10)
    selected_top_k = max(1, int(_safe_float((spec.get("selection_policy") or {}).get("top_k"), 5.0)))
    top_by_date: dict[str, list[dict[str, Any]]] = {}
    candidate_count_by_date: dict[str, int] = {}
    prediction_row_count = 0
    selection_allowed_row_count = 0
    with tempfile.TemporaryDirectory(prefix="stock-dashboard-top-candidate-label-index-") as temp_dir:
        label_sqlite_path = Path(temp_dir) / "labels.sqlite"
        ready_date_counts, indexed_label_count = _build_stream_label_index(
            label_matrix_artifact=label_matrix_artifact,
            sqlite_path=label_sqlite_path,
        )
        dates = sorted(date for date, count in ready_date_counts.items() if count > 0)
        splits = _walk_forward_splits(dates, min_train_dates=min_train_dates, test_window_dates=test_window_dates)
        split_by_test_date = _split_for_test_date(splits)
        fit_digest_by_split: dict[str, str] = {}
        for split in splits:
            if split.get("status") != "ready":
                continue
            fitted_model = _fit_model([], model_spec=spec, params=params)
            fit_digest_by_split[str(split["split_id"])] = _stable_digest(
                {
                    "trial_id": trial_id,
                    "split_id": split["split_id"],
                    "fitted_model": fitted_model,
                    "stream_top_candidate_inventory": True,
                }
            )
        for joined in _stream_joined_rows(
            feature_matrix_artifact=feature_matrix_artifact,
            label_sqlite_path=label_sqlite_path,
        ):
            as_of_date = str(joined.get("as_of_date") or "")
            split = split_by_test_date.get(as_of_date)
            if split is None:
                continue
            split_id = str(split["split_id"])
            if _target(joined, horizon_days=horizon_days) is None:
                continue
            prediction = _make_prediction_from_joined_row(
                joined=joined,
                spec=spec,
                params=params,
                trial_id=trial_id,
                split_id=split_id,
                fitted_model_digest=fit_digest_by_split[split_id],
                horizon_days=horizon_days,
            )
            prediction_row_count += 1
            if not prediction.get("selection_allowed", True):
                continue
            selection_allowed_row_count += 1
            candidate_count_by_date[as_of_date] = candidate_count_by_date.get(as_of_date, 0) + 1
            top_rows = top_by_date.setdefault(as_of_date, [])
            top_rows.append(prediction)
            if len(top_rows) > top_n:
                top_rows.sort(key=lambda row: _safe_float(row.get("score")), reverse=True)
                del top_rows[top_n:]
    candidate_rows: list[dict[str, Any]] = []
    date_summaries: list[dict[str, Any]] = []
    for as_of_date in sorted(top_by_date):
        selected = sorted(top_by_date[as_of_date], key=lambda row: _safe_float(row.get("score")), reverse=True)[:top_n]
        date_summaries.append(
            {
                "as_of_date": as_of_date,
                "candidate_count": candidate_count_by_date.get(as_of_date, 0),
                "stored_top_candidate_count": len(selected),
            }
        )
        for rank, prediction in enumerate(selected, start=1):
            feature_values = (
                prediction.get("rank_weight_feature_values")
                if isinstance(prediction.get("rank_weight_feature_values"), dict)
                else {}
            )
            retained_feature_values = {
                key: _safe_float(value) if value is not None else None
                for key, value in feature_values.items()
            }
            candidate_rows.append(
                {
                    "as_of_date": as_of_date,
                    "month": as_of_date[:7],
                    "rank": rank,
                    "symbol": prediction.get("symbol"),
                    "stock_name": prediction.get("stock_name"),
                    "board": prediction.get("board"),
                    "industry_code": prediction.get("industry_code"),
                    "industry_name": prediction.get("industry_name"),
                    "score": _safe_float(prediction.get("score")),
                    "net_excess_return": _safe_float(prediction.get("target_label")),
                    "target_total_return": _safe_float(prediction.get("target_total_return")),
                    "target_horizon_days": int(_safe_float(prediction.get("target_horizon_days"), 0.0)),
                    "portfolio_weight": _safe_float(prediction.get("portfolio_weight"), 1.0),
                    "rank_weight_multiplier": 1.0,
                    "avg_amount_20d": _safe_float(feature_values.get("avg_amount_20d")),
                    "amount_10d_vs_20d_percentile": _safe_float(
                        feature_values.get("amount_10d_vs_20d_percentile")
                    ),
                    "turnover_rate_percentile": _safe_float(feature_values.get("turnover_rate_percentile")),
                    "rank_weight_feature_values": retained_feature_values,
                }
            )
    resolved_source_db_snapshot_id = source_db_snapshot_id or feature_metadata.get("source_db_snapshot_id")
    resolved_source_data_time_range = source_data_time_range or feature_metadata.get("source_data_time_range")
    content_digest = _stable_digest(
        {
            "feature_matrix": feature_metadata.get("artifact_id"),
            "label_matrix": label_metadata.get("artifact_id"),
            "registry": model_spec_registry.get("artifact_id"),
            "trial_id": trial_id,
            "top_n": top_n,
            "candidate_rows": candidate_rows,
            "prediction_row_count": prediction_row_count,
        }
    )
    return {
        "artifact_type": "top_candidate_inventory",
        "schema_version": TOP_CANDIDATE_INVENTORY_SCHEMA_VERSION,
        "artifact_id": f"top-candidate-inventory-{content_digest[:16]}",
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": resolved_source_db_snapshot_id,
        "source_data_time_range": resolved_source_data_time_range,
        "source_feature_matrix_id": feature_metadata.get("artifact_id"),
        "source_label_matrix_id": label_metadata.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "trial_id": trial_id,
        "model_spec_id": spec_id,
        "selected_top_k": selected_top_k,
        "target_horizon_days": horizon_days,
        "top_n": top_n,
        "prediction_row_count": prediction_row_count,
        "selection_allowed_row_count": selection_allowed_row_count,
        "indexed_label_count": indexed_label_count,
        "date_count": len(date_summaries),
        "candidate_row_count": len(candidate_rows),
        "candidate_rows": candidate_rows,
        "date_summaries": date_summaries,
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "top_candidate_inventory_only",
        "storage_boundary": "compact_top_n_per_date_no_full_prediction_rows",
        "gate_readout": {
            "gate_status": "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "top_candidate_inventory_only",
            "blocking_gate_ids": ["comparison_report_pending", "governance_promotion_pending"],
        },
    }


def build_streamed_score_rank_probe_artifact(
    *,
    validation_run_id: str,
    feature_matrix_artifact: str | Path,
    model_spec_registry: dict[str, Any],
    trial_id: str,
    target_symbols_by_date: dict[str, list[str]],
    top_n: int = 20,
) -> dict[str, Any]:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    feature_metadata = _load_artifact_metadata_without_rows(feature_matrix_artifact)
    spec, params = _resolve_registry_trial(model_spec_registry, trial_id)
    spec_id = str(spec.get("model_spec_id") or "")
    if str(spec.get("model_type") or "") not in _deterministic_score_only_model_types():
        raise ValueError(f"score rank probe only supports deterministic score-only specs: {spec_id}")
    target_dates = {str(date_value) for date_value in target_symbols_by_date}
    target_symbol_sets = {
        str(date_value): {str(symbol) for symbol in symbols}
        for date_value, symbols in target_symbols_by_date.items()
    }
    if not target_dates:
        raise ValueError("target_symbols_by_date must not be empty")
    fitted_model = _fit_model([], model_spec=spec, params=params)
    fitted_model_digest = _stable_digest(
        {
            "trial_id": trial_id,
            "fitted_model": fitted_model,
            "stream_score_rank_probe": True,
        }
    )
    selection_policy = spec.get("selection_policy") or {}
    date_rows: dict[str, list[dict[str, Any]]] = {date_value: [] for date_value in target_dates}
    scanned_row_count = 0
    scored_row_count = 0
    selection_allowed_row_count = 0
    for feature_row in _iter_artifact_rows(feature_matrix_artifact):
        as_of_date = str(feature_row.get("as_of_date") or "")
        if as_of_date not in target_dates:
            continue
        scanned_row_count += 1
        values = _model_feature_values(feature_row)
        selection_allowed, selection_block_reasons = _selection_allowed(
            values,
            selection_policy=selection_policy,
            params=params,
        )
        score = _score_row(
            feature_row,
            model_spec=spec,
            params=params,
            fitted_model=fitted_model,
            feature_values=values,
        )
        scored_row_count += 1
        if selection_allowed:
            selection_allowed_row_count += 1
        date_rows[as_of_date].append(
            {
                "symbol": feature_row.get("symbol"),
                "stock_name": feature_row.get("stock_name"),
                "board": feature_row.get("board"),
                "industry_code": feature_row.get("industry_code"),
                "industry_name": feature_row.get("industry_name"),
                "as_of_date": as_of_date,
                "universe_row_id": feature_row.get("universe_row_id"),
                "score": score,
                **_exhaustion_reference_metadata(
                    model_spec=spec,
                    params=params,
                    feature_values=values,
                ),
                "selection_allowed": selection_allowed,
                "selection_block_reasons": selection_block_reasons,
                "portfolio_weight": _position_weight(values, selection_policy=selection_policy, params=params)
                if selection_allowed
                else 0.0,
                "rank_weight_feature_values": _rank_signal_feature_subset(values),
            }
        )

    date_summaries: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    top_candidate_rows: list[dict[str, Any]] = []
    missing_targets: list[dict[str, Any]] = []
    for as_of_date in sorted(target_dates):
        rows = date_rows.get(as_of_date) or []
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        rank_by_symbol = {str(row.get("symbol")): rank for rank, row in enumerate(ordered, start=1)}
        score_by_symbol = {str(row.get("symbol")): row for row in ordered}
        stored_top = ordered[:top_n]
        date_summaries.append(
            {
                "as_of_date": as_of_date,
                "scanned_row_count": len(rows),
                "selection_allowed_row_count": len(active_rows),
                "stored_top_candidate_count": len(stored_top),
                "target_symbol_count": len(target_symbol_sets.get(as_of_date, set())),
            }
        )
        for rank, row in enumerate(stored_top, start=1):
            top_candidate_rows.append(_rank_probe_row(row, rank=rank, row_role="top_score_candidate"))
        for symbol in sorted(target_symbol_sets.get(as_of_date, set())):
            row = score_by_symbol.get(symbol)
            if row is None:
                missing_targets.append({"as_of_date": as_of_date, "symbol": symbol})
                continue
            target_rows.append(_rank_probe_row(row, rank=rank_by_symbol[symbol], row_role="target_symbol"))

    blocking_gate_ids = []
    if missing_targets:
        blocking_gate_ids.append("score_rank_probe:missing_target_symbols")
    if not target_rows:
        blocking_gate_ids.append("score_rank_probe:no_target_rows")
    content_digest = _stable_digest(
        {
            "feature_matrix": feature_metadata.get("artifact_id"),
            "registry": model_spec_registry.get("artifact_id"),
            "trial_id": trial_id,
            "target_symbols_by_date": target_symbols_by_date,
            "top_n": top_n,
            "date_summaries": date_summaries,
            "target_rows": target_rows,
            "top_candidate_rows": top_candidate_rows,
            "missing_targets": missing_targets,
        }
    )
    return {
        "artifact_id": f"score-rank-probe-{content_digest[:16]}",
        "artifact_type": "score_rank_probe",
        "schema_version": SCORE_RANK_PROBE_SCHEMA_VERSION,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_feature_matrix_id": feature_metadata.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "trial_id": trial_id,
        "model_spec_id": spec_id,
        "fitted_model_digest": fitted_model_digest,
        "feature_version": feature_metadata.get("feature_version"),
        "source_data_time_range": feature_metadata.get("source_data_time_range"),
        "target_symbols_by_date": target_symbols_by_date,
        "date_count": len(target_dates),
        "scanned_row_count": scanned_row_count,
        "scored_row_count": scored_row_count,
        "selection_allowed_row_count": selection_allowed_row_count,
        "top_n": top_n,
        "date_summaries": date_summaries,
        "target_rows": target_rows,
        "top_candidate_rows": top_candidate_rows,
        "missing_targets": missing_targets,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "claim_ceiling": "score_rank_probe_only_no_label_matrix_no_model_replay_no_promotion",
        "storage_boundary": "compact_target_rows_and_top_n_per_date_no_full_prediction_rows",
    }


def _rank_probe_row(row: dict[str, Any], *, rank: int, row_role: str) -> dict[str, Any]:
    feature_values = row.get("rank_weight_feature_values") if isinstance(row.get("rank_weight_feature_values"), dict) else {}
    return {
        "row_role": row_role,
        "as_of_date": row.get("as_of_date"),
        "rank": rank,
        "symbol": row.get("symbol"),
        "stock_name": row.get("stock_name"),
        "board": row.get("board"),
        "industry_code": row.get("industry_code"),
        "industry_name": row.get("industry_name"),
        "score": _safe_float(row.get("score")),
        "selection_allowed": bool(row.get("selection_allowed", True)),
        "selection_block_reasons": row.get("selection_block_reasons") or [],
        "portfolio_weight": _safe_float(row.get("portfolio_weight")),
        "rank_weight_feature_values": {
            key: _safe_float(value) if value is not None else None
            for key, value in feature_values.items()
        },
    }


def _resolve_registry_trial(model_spec_registry: dict[str, Any], trial_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for spec in model_spec_registry.get("model_specs") or []:
        spec_id = str(spec.get("model_spec_id") or "")
        for trial_index, params in enumerate(_grid_trials(spec.get("hyperparameter_grid") or {})):
            if f"{spec_id}:trial-{trial_index:03d}" == trial_id:
                return spec, params
    raise ValueError(f"trial_id not found in model spec registry: {trial_id}")


def _trial_blockers(metrics: dict[str, Any], split_count: int, *, model_spec: dict[str, Any] | None = None) -> list[str]:
    blockers: list[str] = []
    selection_policy = (model_spec or {}).get("selection_policy") or {}
    return_metric = str(selection_policy.get("evaluation_return_metric") or "top_quantile_net_excess_mean")
    is_concentrated_top5 = return_metric == "top_5_net_excess_mean"
    is_selected_top_k = return_metric == "selected_top_k_net_excess_mean"
    if split_count < 2:
        blockers.append("insufficient_walk_forward_splits")
    if _safe_float(metrics.get("labeled_prediction_count")) < 60:
        blockers.append("insufficient_labeled_predictions")
    if is_concentrated_top5:
        if metrics.get("positive_top_5_rate") is None:
            blockers.append("missing_positive_top_5_rate")
        elif _safe_float(metrics.get("positive_top_5_rate")) < 0.55:
            blockers.append("positive_top_5_rate_below_gate")
    elif is_selected_top_k:
        if metrics.get("positive_selected_top_k_rate") is None:
            blockers.append("missing_positive_selected_top_k_rate")
        elif _safe_float(metrics.get("positive_selected_top_k_rate")) < 0.45:
            blockers.append("positive_selected_top_k_rate_below_gate")
    else:
        if metrics.get("rank_ic_mean") is None:
            blockers.append("missing_rank_ic")
        elif _safe_float(metrics.get("rank_ic_mean")) <= 0.02:
            blockers.append("rank_ic_below_gate")
        if metrics.get("positive_rank_ic_rate") is None:
            blockers.append("missing_positive_ic_rate")
        elif _safe_float(metrics.get("positive_rank_ic_rate")) < 0.55:
            blockers.append("positive_ic_rate_below_gate")
    if _safe_float(metrics.get(return_metric)) <= 0:
        blockers.append(f"{return_metric}_not_positive")
    return blockers


def write_walk_forward_model_candidate_run_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> Path:
    return write_research_validation_artifact(
        "walk_forward_model_candidate_run",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
