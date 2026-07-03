from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from ashare_evidence.phase2.common import spearman_correlation
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_CANDIDATE_RUN_SCHEMA_VERSION = "walk_forward_model_candidate_run.v1"
MAX_STORED_PREDICTIONS_PER_TRIAL = 2000
MODEL_FEATURE_DEFS = (
    ("return_5d", "price_momentum", "return_5d"),
    ("return_10d", "price_momentum", "return_10d"),
    ("return_20d", "price_momentum", "return_20d"),
    ("return_1d", "reversal_overheat", "return_1d"),
    ("distance_from_20d_high", "reversal_overheat", "distance_from_20d_high"),
    ("volatility_20d", "volatility_risk", "volatility_20d"),
    ("avg_amount_20d", "liquidity", "avg_amount_20d"),
    ("amount_vs_20d_avg", "crowding", "amount_vs_20d_avg"),
    ("benchmark_return_20d", "regime", "benchmark_return_20d"),
    ("benchmark_volatility_20d", "regime", "benchmark_volatility_20d"),
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


def _feature(row: dict[str, Any], group: str, key: str) -> float:
    values = row.get("feature_values") or {}
    group_values = values.get(group) or {}
    return _safe_float(group_values.get(key))


def _model_feature_values(feature_row: dict[str, Any]) -> dict[str, float]:
    return {name: _feature(feature_row, group, key) for name, group, key in MODEL_FEATURE_DEFS}


def _target(row: dict[str, Any], *, horizon_days: int = 10) -> float | None:
    value = row.get("target_labels_by_horizon", {}).get(str(horizon_days))
    if value is None:
        value = row.get("target_label")
    if value is None:
        return None
    target = _safe_float(value)
    return target if horizon_days == 10 else target - 0.001


def _correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mean_x = mean(xs)
    mean_y = mean(ys)
    std_x = pstdev(xs)
    std_y = pstdev(ys)
    if std_x == 0 or std_y == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / len(xs) / (std_x * std_y)


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


def _fit_model(rows: list[dict[str, Any]], *, model_spec: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    spec_type = str(model_spec.get("model_type") or "")
    horizon_days = int(model_spec.get("prediction_horizon_days") or 10)
    if spec_type == "deterministic_baseline":
        return {
            "model_family": "deterministic_baseline_no_fit",
            "train_row_count": len(rows),
            "prediction_horizon_days": horizon_days,
            "feature_stats": {},
        }
    alpha = _safe_float(params.get("regularization_alpha"), 1.0)
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
    return momentum


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
                "purge_days": 20,
                "embargo_days": 20,
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
                "purge_days": 20,
                "embargo_days": 20,
            }
        )
        split_index += 1
        start += test_window_dates
    return splits


def _trial_metrics(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in predictions if row.get("target_label") is not None]
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in scored:
        by_date.setdefault(str(row["as_of_date"]), []).append(row)
    rank_ics: list[float] = []
    top_returns: list[float] = []
    spreads: list[float] = []
    for rows in by_date.values():
        if len(rows) < 2:
            continue
        scores = [_safe_float(row.get("score")) for row in rows]
        labels = [_safe_float(row.get("target_label")) for row in rows]
        rank_ics.append(spearman_correlation(scores, labels))
        ordered = sorted(rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        bucket_size = max(1, len(ordered) // 5)
        top = [_safe_float(row.get("target_label")) for row in ordered[:bucket_size]]
        bottom = [_safe_float(row.get("target_label")) for row in ordered[-bucket_size:]]
        top_returns.append(mean(top))
        spreads.append(mean(top) - mean(bottom))
    return {
        "prediction_count": len(predictions),
        "labeled_prediction_count": len(scored),
        "rank_ic_mean": mean(rank_ics) if rank_ics else None,
        "positive_rank_ic_rate": sum(1 for value in rank_ics if value > 0) / len(rank_ics) if rank_ics else None,
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
        best = max(rows, key=lambda row: _safe_float(row.get("score")))
        top_picks.append(
            {
                "symbol": best.get("symbol"),
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "net_excess_return": _safe_float(best.get("target_label")),
                "score": _safe_float(best.get("score")),
            }
        )
    return top_picks


def _trial_diagnostics(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "split_rank_ics": _rank_ics_by_field(predictions, field="split_id"),
        "date_rank_ics": _rank_ics_by_field(predictions, field="as_of_date"),
        "top_picks_by_date": _top_picks_by_date(predictions),
    }


def _stored_prediction_sample(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(predictions) <= MAX_STORED_PREDICTIONS_PER_TRIAL:
        return predictions
    head_count = MAX_STORED_PREDICTIONS_PER_TRIAL // 2
    tail_count = MAX_STORED_PREDICTIONS_PER_TRIAL - head_count
    return [*predictions[:head_count], *predictions[-tail_count:]]


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
        for trial_index, params in enumerate(trials):
            trial_id = f"{spec_id}:trial-{trial_index:03d}"
            trial_predictions: list[dict[str, Any]] = []
            fit_summaries: list[dict[str, Any]] = []
            for split in splits:
                if split["status"] != "ready":
                    continue
                train_dates = list(split["train_dates"])
                test_dates = list(split["test_dates"])
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
                        "test_date_count": len(test_dates),
                        "train_row_count": fitted_model.get("train_row_count"),
                        "fitted_model_family": fitted_model.get("model_family"),
                        "fitted_model_digest": fitted_model_digest,
                        "fitted_model_summary": _fitted_model_summary(fitted_model),
                    }
                )
                for joined in test_rows:
                    score = _score_row(
                        joined["feature_row"],
                        model_spec=spec,
                        params=params,
                        fitted_model=fitted_model,
                        feature_values=joined["feature_values_flat"],
                    )
                    prediction = {
                        "trial_id": trial_id,
                        "model_spec_id": spec_id,
                        "split_id": split["split_id"],
                        "fitted_model_digest": fitted_model_digest,
                        "symbol": joined["symbol"],
                        "as_of_date": joined["as_of_date"],
                        "universe_row_id": joined["universe_row_id"],
                        "score": score,
                        "target_label": _target(joined, horizon_days=horizon_days),
                        "target_horizon_days": horizon_days,
                        "label_status": joined["label_status"],
                    }
                    prediction["row_digest"] = _stable_digest(prediction)
                    trial_predictions.append(prediction)
            metrics = _trial_metrics(trial_predictions)
            diagnostics = _trial_diagnostics(trial_predictions)
            trial_summaries.append(
                {
                    "trial_id": trial_id,
                    "model_spec_id": spec_id,
                    "params": params,
                    "metrics": metrics,
                    "fit_summaries": fit_summaries,
                    "gate_status": "blocked",
                    "blocking_gate_ids": _trial_blockers(metrics, len(splits)),
                }
            )
            trial_diagnostics.append(
                {
                    "trial_id": trial_id,
                    "model_spec_id": spec_id,
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
        "config_version": "shortpick_model_candidate_runner:v1",
        "validation_protocol": {
            "runner_policy": "registered_model_specs_only",
            "primary_row_source": "pit_feature_matrix_joined_to_executable_label_matrix",
            "evaluation_row_policy": "label_status_ready_and_target_label_present_only",
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


def _trial_blockers(metrics: dict[str, Any], split_count: int) -> list[str]:
    blockers: list[str] = []
    if split_count < 2:
        blockers.append("insufficient_walk_forward_splits")
    if _safe_float(metrics.get("labeled_prediction_count")) < 60:
        blockers.append("insufficient_labeled_predictions")
    if metrics.get("rank_ic_mean") is None:
        blockers.append("missing_rank_ic")
    elif _safe_float(metrics.get("rank_ic_mean")) <= 0.02:
        blockers.append("rank_ic_below_gate")
    if metrics.get("positive_rank_ic_rate") is None:
        blockers.append("missing_positive_ic_rate")
    elif _safe_float(metrics.get("positive_rank_ic_rate")) < 0.55:
        blockers.append("positive_ic_rate_below_gate")
    if _safe_float(metrics.get("top_quantile_net_excess_mean")) <= 0:
        blockers.append("top_quantile_net_excess_not_positive")
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
