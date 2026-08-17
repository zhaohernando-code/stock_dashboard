from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.model_candidate_runner import (
    _fit_model,
    _grid_trials,
    _iter_artifact_rows,
    _load_artifact_metadata_without_rows,
    _model_feature_values,
    _position_weight,
    _rank_signal_feature_subset,
    _score_row,
    _selection_allowed,
)
from ashare_evidence.model_spec_registry import build_model_spec_registry_artifact
from ashare_evidence.shortpick_strategy_lab_v3_projection import NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID

SCHEMA_VERSION = "external_context_exact_v3_core_snapshot.v1"
V3_INCEPTION_DATE = "2023-09-07"


def _digest(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix == ".gz":
        with gzip.open(source, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must be a JSON object: {source}")
    return payload


def _model_spec(model_spec_id: str) -> dict[str, Any]:
    registry = build_model_spec_registry_artifact(validation_run_id="external-context-exact-v3-core")
    for spec in registry.get("model_specs") or []:
        if isinstance(spec, dict) and spec.get("model_spec_id") == model_spec_id:
            return spec
    raise ValueError(f"model spec is not registered: {model_spec_id}")


def build_exact_v3_core_snapshot(
    *,
    candidate_dataset_path: str | Path,
    feature_matrix_paths: list[str | Path],
    model_spec_id: str = NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
    trial_index: int = 0,
) -> dict[str, Any]:
    candidate_dataset = _read_json(candidate_dataset_path)
    candidate_rows = list(candidate_dataset.get("rows") or [])
    target_keys = {
        (str(row.get("signal_day") or ""), str(row.get("symbol") or ""))
        for row in candidate_rows
        if row.get("signal_day") and row.get("symbol")
    }
    if len(target_keys) != len(candidate_rows):
        raise ValueError("candidate dataset contains duplicate or incomplete signal_day/symbol keys")
    spec = _model_spec(model_spec_id)
    trials = _grid_trials(spec.get("hyperparameter_grid") or {})
    if not 0 <= trial_index < len(trials):
        raise ValueError("trial_index is outside the registered grid")
    params = trials[trial_index]
    fitted_model = _fit_model([], model_spec=spec, params=params)
    resolved: dict[tuple[str, str], dict[str, Any]] = {}
    matrix_refs: list[dict[str, Any]] = []
    overlap_row_count = 0
    overlap_feature_disagreement_count = 0
    overlap_core_score_disagreement_count = 0
    overlap_feature_disagreement_sample: list[dict[str, Any]] = []
    for raw_path in feature_matrix_paths:
        path = Path(raw_path)
        metadata = _load_artifact_metadata_without_rows(path)
        if metadata.get("feature_version") != "shortpick_model_pit_feature_matrix:v3":
            raise ValueError(f"exact V3 core requires feature matrix v3: {path}")
        matrix_refs.append(
            {
                "path": str(path),
                "artifact_id": metadata.get("artifact_id"),
                "feature_version": metadata.get("feature_version"),
                "source_data_time_range": metadata.get("source_data_time_range"),
            }
        )
        for feature_row in _iter_artifact_rows(path):
            key = (str(feature_row.get("as_of_date") or ""), str(feature_row.get("symbol") or ""))
            if key not in target_keys:
                continue
            values = _model_feature_values(feature_row)
            score = _score_row(
                feature_row,
                model_spec=spec,
                params=params,
                fitted_model=fitted_model,
                feature_values=values,
            )
            selection_allowed, selection_block_reasons = _selection_allowed(
                values,
                selection_policy=spec.get("selection_policy") or {},
                params=params,
            )
            row = {
                "signal_day": key[0],
                "symbol": key[1],
                "stock_name": feature_row.get("stock_name"),
                "industry_code": feature_row.get("industry_code"),
                "industry_name": feature_row.get("industry_name"),
                "core_score": score,
                "selection_allowed": selection_allowed,
                "selection_block_reasons": selection_block_reasons,
                "portfolio_weight_before_rank_adjustment": (
                    _position_weight(
                        values,
                        selection_policy=spec.get("selection_policy") or {},
                        params=params,
                    )
                    if selection_allowed
                    else 0.0
                ),
                "rank_signal_feature_values": _rank_signal_feature_subset(values),
                "core_feature_values": values,
                "source_feature_matrix_id": metadata.get("artifact_id"),
                "source_feature_row_digest": feature_row.get("row_digest"),
                "source_cutoff_at_or_before_as_of": feature_row.get("source_cutoff_at_or_before_as_of"),
            }
            existing = resolved.get(key)
            if existing is not None:
                overlap_row_count += 1
                comparison_fields = (
                    "core_score",
                    "selection_allowed",
                    "selection_block_reasons",
                    "portfolio_weight_before_rank_adjustment",
                    "rank_signal_feature_values",
                    "core_feature_values",
                )
                if any(existing.get(field) != row.get(field) for field in comparison_fields):
                    overlap_feature_disagreement_count += 1
                    if existing.get("core_score") != row.get("core_score"):
                        overlap_core_score_disagreement_count += 1
                    if len(overlap_feature_disagreement_sample) < 100:
                        overlap_feature_disagreement_sample.append(
                            {
                                "signal_day": key[0],
                                "symbol": key[1],
                                "retained_matrix": existing.get("source_feature_matrix_id"),
                                "later_matrix": metadata.get("artifact_id"),
                                "retained_core_score": existing.get("core_score"),
                                "later_core_score": row.get("core_score"),
                            }
                        )
                # Matrix arguments are chronological precedence. Retain the first
                # frozen row so a later rebuilt matrix cannot revise history.
                continue
            resolved[key] = row

    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in resolved.values():
        by_day.setdefault(str(row["signal_day"]), []).append(row)
    day_stats: list[dict[str, Any]] = []
    for signal_day, rows in sorted(by_day.items()):
        eligible = [row for row in rows if row["selection_allowed"]]
        scores = [float(row["core_score"]) for row in eligible]
        score_mean = mean(scores) if scores else None
        score_std = pstdev(scores) if len(scores) > 1 else None
        ordered = sorted(eligible, key=lambda row: (-float(row["core_score"]), str(row["symbol"])))
        for rank, row in enumerate(ordered, start=1):
            row["candidate_pool_core_rank"] = rank
            row["candidate_pool_core_score_z"] = (
                (float(row["core_score"]) - score_mean) / score_std
                if score_mean is not None and score_std not in {None, 0.0}
                else 0.0
            )
        for row in rows:
            row["row_digest"] = _digest({key: value for key, value in row.items() if key != "row_digest"})
        day_stats.append(
            {
                "signal_day": signal_day,
                "candidate_row_count": len(rows),
                "selection_allowed_count": len(eligible),
                "core_score_mean": score_mean,
                "core_score_population_std": score_std,
                "zscore_scope": "retained_personal_outer_filtered_opportunity_candidates_only",
            }
        )
    output_rows = sorted(resolved.values(), key=lambda row: (row["signal_day"], row["symbol"]))
    missing_keys = sorted(target_keys - set(resolved))
    coverage_ratio = len(output_rows) / len(candidate_rows) if candidate_rows else 0.0
    candidate_dates = sorted({str(row.get("signal_day") or "") for row in candidate_rows})
    covered_dates = sorted(by_day)
    active_target_keys = {key for key in target_keys if key[0] >= V3_INCEPTION_DATE}
    active_resolved_keys = set(resolved) & active_target_keys
    active_missing_keys = active_target_keys - set(resolved)
    material = {
        "artifact_type": "external_context_exact_v3_core_snapshot",
        "schema_version": SCHEMA_VERSION,
        "model_spec_id": model_spec_id,
        "trial_id": f"{model_spec_id}:trial-{trial_index:03d}",
        "model_params_digest": _digest(params),
        "source_candidate_dataset_id": candidate_dataset.get("artifact_id"),
        "source_candidate_dataset_digest": candidate_dataset.get("content_digest"),
        "source_feature_matrices": matrix_refs,
        "matrix_overlap_policy": "argument_order_earliest_frozen_matrix_wins_later_overlap_audit_only",
        "candidate_row_count": len(candidate_rows),
        "resolved_core_score_count": len(output_rows),
        "missing_core_score_count": len(missing_keys),
        "core_score_coverage_ratio": coverage_ratio,
        "v3_inception_date": V3_INCEPTION_DATE,
        "pre_v3_inception_candidate_row_count": len(target_keys - active_target_keys),
        "v3_active_window_candidate_row_count": len(active_target_keys),
        "v3_active_window_resolved_core_score_count": len(active_resolved_keys),
        "v3_active_window_missing_core_score_count": len(active_missing_keys),
        "v3_active_window_core_score_coverage_ratio": (
            len(active_resolved_keys) / len(active_target_keys) if active_target_keys else 0.0
        ),
        "candidate_date_range": [candidate_dates[0], candidate_dates[-1]] if candidate_dates else None,
        "covered_date_range": [covered_dates[0], covered_dates[-1]] if covered_dates else None,
        "missing_key_sample": [
            {"signal_day": signal_day, "symbol": symbol} for signal_day, symbol in missing_keys[:100]
        ],
        "daily_candidate_pool_stats": day_stats,
        "rows": output_rows,
        "quality": {
            "overlap_row_count": overlap_row_count,
            "overlap_feature_disagreement_count": overlap_feature_disagreement_count,
            "overlap_core_score_disagreement_count": overlap_core_score_disagreement_count,
            "overlap_feature_disagreement_sample": overlap_feature_disagreement_sample,
            "source_cutoff_violation_count": sum(
                row.get("source_cutoff_at_or_before_as_of") is not True for row in output_rows
            ),
            "exact_raw_core_score_ready": bool(output_rows) and all(
                row.get("source_cutoff_at_or_before_as_of") is True for row in output_rows
            ),
            "full_candidate_window_ready": len(missing_keys) == 0,
            "v3_active_window_complete": len(active_missing_keys) == 0,
        },
        "claim_ceiling": (
            "exact_registered_v3_trial000_core_score_for_covered_candidates; "
            "candidate_pool_z_is_not_full_universe_z_and_no_external_weight_result_is_computed"
        ),
        "network_used": False,
        "v3_signal_changed": False,
    }
    return {
        **material,
        "content_digest": _digest(material),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def write_exact_v3_core_snapshot(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    material = {key: value for key, value in payload.items() if key not in {"content_digest", "generated_at"}}
    if _digest(material) != payload.get("content_digest"):
        raise ValueError("exact V3 core snapshot content digest mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable exact V3 core snapshot collision: {target}")
    if not target.exists():
        target.write_text(rendered, encoding="utf-8")
    return target


__all__ = ["build_exact_v3_core_snapshot", "write_exact_v3_core_snapshot"]
