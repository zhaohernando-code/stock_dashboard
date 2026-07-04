from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from ashare_evidence.model_candidate_runner import MODEL_FEATURE_DEFS, _join_rows, _safe_float, _target
from ashare_evidence.phase2.common import spearman_correlation
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_FEATURE_DIAGNOSTIC_SCHEMA_VERSION = "model_feature_diagnostic_report.v1"
DIAGNOSTIC_HORIZONS = (5, 10, 20)
RANK_IC_MIN = 0.02
POSITIVE_IC_RATE_MIN = 0.55


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_json_artifact(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact payload must be a JSON object: {path}")
    return payload


def _infer_artifact_root(path: str | Path) -> Path:
    artifact_path = Path(path).resolve()
    for parent in artifact_path.parents:
        if parent.name == "artifacts":
            return parent
    return artifact_path.parent


def load_model_feature_diagnostic_inputs(
    *,
    feature_matrix_artifact: str | Path,
    label_matrix_artifact: str | Path,
) -> dict[str, dict[str, Any]]:
    artifacts = {
        "pit_feature_matrix": _load_json_artifact(feature_matrix_artifact),
        "executable_label_matrix": _load_json_artifact(label_matrix_artifact),
    }
    failures: list[str] = []
    if artifacts["pit_feature_matrix"].get("artifact_type") != "pit_feature_matrix":
        failures.append("feature_matrix:expected_pit_feature_matrix")
    if artifacts["executable_label_matrix"].get("artifact_type") != "executable_label_matrix":
        failures.append("label_matrix:expected_executable_label_matrix")
    feature_source_id = artifacts["pit_feature_matrix"].get("source_input_snapshot_id")
    label_source_id = artifacts["executable_label_matrix"].get("source_input_snapshot_id")
    if feature_source_id != label_source_id:
        failures.append("source_input_snapshot_id_mismatch")
    if failures:
        raise ValueError(f"invalid model feature diagnostic inputs: {', '.join(failures)}")
    return artifacts


def _rows_by_date_for_horizon(
    *,
    feature_matrix: dict[str, Any],
    label_matrix: dict[str, Any],
    horizon_days: int,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in _join_rows(feature_matrix, label_matrix):
        if row.get("label_status") != "ready":
            continue
        target = _target(row, horizon_days=horizon_days)
        if target is None:
            continue
        row = {**row, "diagnostic_target": target}
        rows_by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    return rows_by_date


def _feature_value(row: dict[str, Any], feature_name: str) -> float:
    return _safe_float((row.get("feature_values_flat") or {}).get(feature_name))


def _directional_score(value: float, direction: str) -> float:
    return value if direction == "long_high" else -value


def _diagnose_feature_direction(
    *,
    rows_by_date: dict[str, list[dict[str, Any]]],
    feature_name: str,
    feature_group: str,
    horizon_days: int,
    direction: str,
) -> dict[str, Any]:
    rank_ics: list[float] = []
    top_5_returns: list[float] = []
    top_10_returns: list[float] = []
    top_returns: list[float] = []
    bottom_returns: list[float] = []
    spreads: list[float] = []
    row_count = 0
    date_count = 0
    for as_of_date, rows in sorted(rows_by_date.items()):
        scored = [
            {
                "score": _directional_score(_feature_value(row, feature_name), direction),
                "target": _safe_float(row.get("diagnostic_target")),
            }
            for row in rows
        ]
        if len(scored) < 2:
            continue
        scores = [row["score"] for row in scored]
        targets = [row["target"] for row in scored]
        if len(set(scores)) < 2 or len(set(targets)) < 2:
            continue
        rank_ics.append(spearman_correlation(scores, targets))
        ordered = sorted(scored, key=lambda row: row["score"], reverse=True)
        bucket_size = max(1, len(ordered) // 5)
        top = [row["target"] for row in ordered[:bucket_size]]
        bottom = [row["target"] for row in ordered[-bucket_size:]]
        top_5_returns.append(mean(row["target"] for row in ordered[: min(5, len(ordered))]))
        top_10_returns.append(mean(row["target"] for row in ordered[: min(10, len(ordered))]))
        top_returns.append(mean(top))
        bottom_returns.append(mean(bottom))
        spreads.append(mean(top) - mean(bottom))
        row_count += len(scored)
        date_count += 1

    rank_ic_mean = mean(rank_ics) if rank_ics else None
    positive_rank_ic_rate = sum(1 for value in rank_ics if value > 0) / len(rank_ics) if rank_ics else None
    top_quantile_net_excess_mean = mean(top_returns) if top_returns else None
    top_bottom_spread_mean = mean(spreads) if spreads else None
    blockers: list[str] = []
    if rank_ic_mean is None or rank_ic_mean < RANK_IC_MIN:
        blockers.append("rank_ic_below_gate")
    if positive_rank_ic_rate is None or positive_rank_ic_rate < POSITIVE_IC_RATE_MIN:
        blockers.append("positive_ic_rate_below_gate")
    if top_quantile_net_excess_mean is None or top_quantile_net_excess_mean <= 0:
        blockers.append("top_quantile_net_excess_not_positive")

    return {
        "feature_name": feature_name,
        "feature_group": feature_group,
        "direction": direction,
        "prediction_horizon_days": horizon_days,
        "labeled_row_count": row_count,
        "evaluated_date_count": date_count,
        "rank_ic_mean": rank_ic_mean,
        "positive_rank_ic_rate": positive_rank_ic_rate,
        "top_5_net_excess_mean": mean(top_5_returns) if top_5_returns else None,
        "top_10_net_excess_mean": mean(top_10_returns) if top_10_returns else None,
        "top_quantile_net_excess_mean": top_quantile_net_excess_mean,
        "bottom_quantile_net_excess_mean": mean(bottom_returns) if bottom_returns else None,
        "top_bottom_spread_mean": top_bottom_spread_mean,
        "promotion_gate_blockers": blockers,
        "passes_basic_signal_gate": not blockers,
    }


def _leaderboard_sort_key(row: dict[str, Any]) -> tuple[int, float, float, float]:
    rank_ic = _safe_float(row.get("rank_ic_mean"), -1.0)
    top_return = _safe_float(row.get("top_quantile_net_excess_mean"), -1.0)
    spread = _safe_float(row.get("top_bottom_spread_mean"), -1.0)
    return (1 if row.get("passes_basic_signal_gate") else 0, rank_ic, top_return, spread)


def _candidate_generation_hints(leaderboard: list[dict[str, Any]]) -> list[dict[str, Any]]:
    passed = [row for row in leaderboard if row.get("passes_basic_signal_gate")]
    concentrated = [
        row
        for row in leaderboard
        if not row.get("passes_basic_signal_gate") and _safe_float(row.get("top_5_net_excess_mean")) > 0
    ]
    seed_rows = passed or concentrated or leaderboard[:5]
    hints: list[dict[str, Any]] = []
    for row in seed_rows[:8]:
        if row.get("passes_basic_signal_gate"):
            hint_status = "eligible_for_candidate_spec_seed"
        elif _safe_float(row.get("top_5_net_excess_mean")) > 0:
            hint_status = "concentrated_top5_positive_diagnostic_seed"
        else:
            hint_status = "diagnostic_only_below_gate"
        hints.append(
            {
                "status": hint_status,
                "feature_name": row.get("feature_name"),
                "feature_group": row.get("feature_group"),
                "direction": row.get("direction"),
                "prediction_horizon_days": row.get("prediction_horizon_days"),
                "suggested_model_family": "single_feature_seed_then_walk_forward_combo_search",
                "required_next_validation": "registered_candidate_spec_walk_forward_with_pbo_dsr_and_cost_stress",
                "blocking_reason": row.get("promotion_gate_blockers"),
            }
        )
    return hints


def build_model_feature_diagnostic_report_artifact(
    *,
    validation_run_id: str,
    feature_matrix: dict[str, Any],
    label_matrix: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    leaderboard: list[dict[str, Any]] = []
    for horizon_days in DIAGNOSTIC_HORIZONS:
        rows_by_date = _rows_by_date_for_horizon(
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            horizon_days=horizon_days,
        )
        for feature_name, feature_group, _ in MODEL_FEATURE_DEFS:
            for direction in ("long_high", "long_low"):
                leaderboard.append(
                    _diagnose_feature_direction(
                        rows_by_date=rows_by_date,
                        feature_name=feature_name,
                        feature_group=feature_group,
                        horizon_days=horizon_days,
                        direction=direction,
                    )
                )
    leaderboard = sorted(leaderboard, key=_leaderboard_sort_key, reverse=True)
    pass_count = sum(1 for row in leaderboard if row.get("passes_basic_signal_gate"))
    source_input_snapshot_id = feature_matrix.get("source_input_snapshot_id")
    body = {
        "artifact_type": "model_feature_diagnostic_report",
        "schema_version": MODEL_FEATURE_DIAGNOSTIC_SCHEMA_VERSION,
        "validation_run_id": validation_run_id,
        "generated_at": generated_at.isoformat(),
        "source_input_snapshot_id": source_input_snapshot_id,
        "source_feature_matrix_artifact_id": feature_matrix.get("artifact_id"),
        "source_label_matrix_artifact_id": label_matrix.get("artifact_id"),
        "feature_matrix_schema_version": feature_matrix.get("schema_version"),
        "label_matrix_schema_version": label_matrix.get("schema_version"),
        "diagnostic_protocol": {
            "purpose": "discover_feature_direction_horizon_signal_before_registering_strategy_specs",
            "horizons": list(DIAGNOSTIC_HORIZONS),
            "directions": ["long_high", "long_low"],
            "metrics": [
                "cross_sectional_spearman_rank_ic_by_date",
                "top_quantile_net_excess_mean",
                "top_bottom_spread_mean",
            ],
            "basic_signal_gates": {
                "rank_ic_min": RANK_IC_MIN,
                "positive_ic_rate_min": POSITIVE_IC_RATE_MIN,
                "top_quantile_net_excess_mean": "must_be_positive",
            },
            "production_effect": "forbidden",
        },
        "tested_feature_count": len(MODEL_FEATURE_DEFS),
        "tested_direction_horizon_count": len(leaderboard),
        "passing_direction_horizon_count": pass_count,
        "gate_readout": {
            "status": "diagnostic_ready",
            "strategy_found": False,
            "passing_basic_signal_gate_count": pass_count,
            "promotion_gate_status": "not_evaluated_candidate_strategy",
            "reason": "feature_diagnostics_can_seed_model_specs_but_cannot_promote_a_strategy",
        },
        "feature_leaderboard": leaderboard,
        "candidate_generation_hints": _candidate_generation_hints(leaderboard),
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "feature_signal_diagnostic_only",
    }
    body["artifact_id"] = f"model-feature-diagnostic-report-{_stable_digest(body)[:16]}"
    return body


def write_model_feature_diagnostic_report_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> Path:
    return write_research_validation_artifact(
        "model_feature_diagnostic_report",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )


def run_model_feature_diagnostics(
    *,
    validation_run_id: str,
    feature_matrix_artifact: str | Path,
    label_matrix_artifact: str | Path,
    artifact_root: str | Path | None = None,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    artifacts = load_model_feature_diagnostic_inputs(
        feature_matrix_artifact=feature_matrix_artifact,
        label_matrix_artifact=label_matrix_artifact,
    )
    payload = build_model_feature_diagnostic_report_artifact(
        validation_run_id=validation_run_id,
        feature_matrix=artifacts["pit_feature_matrix"],
        label_matrix=artifacts["executable_label_matrix"],
    )
    root = Path(artifact_root) if artifact_root else _infer_artifact_root(feature_matrix_artifact)
    path = None
    if write_artifacts:
        path = write_model_feature_diagnostic_report_artifact(payload, artifact_root=root)
    return {
        "status": "completed",
        "workflow": "shortpick_model_feature_diagnostics_v1",
        "validation_run_id": validation_run_id,
        "artifact_root": str(root),
        "write_artifacts": write_artifacts,
        "production_effect": "forbidden",
        "runtime_db_write_policy": "read_only_artifact_inputs_no_business_table_writes",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "feature_signal_diagnostic_only",
        "artifact_summary": {
            "artifact_type": payload.get("artifact_type"),
            "artifact_id": payload.get("artifact_id"),
            "promotion_status": payload.get("promotion_status"),
            "claim_ceiling": payload.get("claim_ceiling"),
            "path": str(path) if path else None,
            "gate_readout": payload.get("gate_readout"),
        },
        "top_feature_hints": payload.get("candidate_generation_hints") or [],
    }
