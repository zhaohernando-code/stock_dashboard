from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from ashare_evidence.phase2.common import spearman_correlation
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_CANDIDATE_RUN_SCHEMA_VERSION = "walk_forward_model_candidate_run.v1"


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


def _score_row(feature_row: dict[str, Any], *, model_spec: dict[str, Any], params: dict[str, Any]) -> float:
    spec_type = str(model_spec.get("model_type") or "")
    momentum = _feature(feature_row, "price_momentum", "return_10d") or _feature(
        feature_row, "price_momentum", "return_5d"
    )
    liquidity = _feature(feature_row, "liquidity", "avg_amount_20d")
    overheat = _feature(feature_row, "reversal_overheat", "return_1d")
    volatility = _feature(feature_row, "volatility_risk", "volatility_20d")
    regime = _feature(feature_row, "regime", "benchmark_return_20d")
    crowding = _feature(feature_row, "crowding", "amount_vs_20d_avg")
    if spec_type == "deterministic_baseline":
        return momentum + 0.000000001 * liquidity - 0.5 * overheat
    if spec_type == "regularized_rank_linear":
        alpha = _safe_float(params.get("regularization_alpha"), 1.0)
        return (momentum + 0.2 * crowding + 0.1 * regime - 0.3 * volatility - 0.2 * overheat) / max(alpha, 0.1)
    if spec_type == "shallow_tree_ranker":
        depth_bonus = _safe_float(params.get("max_depth"), 2.0) * 0.01
        breakout_bonus = 0.05 if momentum > 0 and crowding > 1 else 0.0
        risk_penalty = 0.05 if volatility > 0.2 else 0.0
        return momentum + breakout_bonus + depth_bonus - risk_penalty
    if spec_type == "bounded_regime_conditioned_linear":
        multiplier = 1.0
        if regime > 0:
            multiplier = 1.0 + min(regime, 0.3)
        elif regime < 0:
            multiplier = 1.0 + max(regime, -0.3)
        return (momentum + 0.15 * crowding - 0.25 * volatility) * min(max(multiplier, 0.5), 1.5)
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
                "label_row": label_row,
                "target_label": (label_row.get("labels") or {}).get("net_excess_return_10d_after_costs"),
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
    dates = sorted({str(row.get("as_of_date")) for row in joined_rows if row.get("as_of_date")})
    splits = _walk_forward_splits(dates, min_train_dates=min_train_dates, test_window_dates=test_window_dates)
    specs = list(model_spec_registry.get("model_specs") or [])
    selected = set(selected_model_spec_ids or [str(spec.get("model_spec_id")) for spec in specs])
    known = {str(spec.get("model_spec_id")) for spec in specs}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"unregistered model specs requested: {', '.join(unknown)}")
    trial_summaries: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []

    for spec in specs:
        spec_id = str(spec.get("model_spec_id") or "")
        if spec_id not in selected:
            continue
        trials = _grid_trials(spec.get("hyperparameter_grid") or {})
        for trial_index, params in enumerate(trials):
            trial_id = f"{spec_id}:trial-{trial_index:03d}"
            trial_predictions: list[dict[str, Any]] = []
            for split in splits:
                if split["status"] != "ready":
                    continue
                test_dates = set(split["test_dates"])
                for joined in joined_rows:
                    if str(joined["as_of_date"]) not in test_dates:
                        continue
                    score = _score_row(joined["feature_row"], model_spec=spec, params=params)
                    prediction = {
                        "trial_id": trial_id,
                        "model_spec_id": spec_id,
                        "split_id": split["split_id"],
                        "symbol": joined["symbol"],
                        "as_of_date": joined["as_of_date"],
                        "universe_row_id": joined["universe_row_id"],
                        "score": score,
                        "target_label": joined["target_label"],
                        "label_status": joined["label_status"],
                    }
                    prediction["row_digest"] = _stable_digest(prediction)
                    trial_predictions.append(prediction)
            metrics = _trial_metrics(trial_predictions)
            trial_summaries.append(
                {
                    "trial_id": trial_id,
                    "model_spec_id": spec_id,
                    "params": params,
                    "metrics": metrics,
                    "gate_status": "blocked",
                    "blocking_gate_ids": _trial_blockers(metrics, len(splits)),
                }
            )
            prediction_rows.extend(trial_predictions)

    content_digest = _stable_digest(
        {
            "feature_matrix": feature_matrix.get("artifact_id"),
            "label_matrix": label_matrix.get("artifact_id"),
            "registry": model_spec_registry.get("artifact_id"),
            "splits": splits,
            "trial_summaries": trial_summaries,
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
        "split_count": len(splits),
        "trial_count": len(trial_summaries),
        "prediction_row_count": len(prediction_rows),
        "splits": splits,
        "trial_summaries": trial_summaries,
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
