from __future__ import annotations

from pathlib import Path
from typing import Any

from ashare_evidence.dashboard_projection_registry import (
    build_dashboard_projection_registry_artifact,
    write_dashboard_projection_registry_artifact,
)
from ashare_evidence.governance_promotion import (
    build_governance_promotion_decision_artifact,
    write_governance_promotion_decision_artifact,
)


def _walk_forward_gate_from_candidate_run(candidate_run: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if int(candidate_run.get("split_count") or 0) < 2:
        blockers.append("insufficient_walk_forward_splits")
    if int(candidate_run.get("prediction_row_count") or 0) <= 0:
        blockers.append("missing_candidate_predictions")
    return {
        "artifact_type": "walk_forward_model_candidate_run",
        "schema_version": candidate_run.get("schema_version"),
        "artifact_id": candidate_run.get("artifact_id"),
        "validation_run_id": candidate_run.get("validation_run_id"),
        "generated_at": candidate_run.get("generated_at"),
        "source_db_snapshot_id": candidate_run.get("source_db_snapshot_id"),
        "source_data_time_range": candidate_run.get("source_data_time_range"),
        "feature_version": candidate_run.get("feature_version"),
        "label_version": candidate_run.get("label_version"),
        "code_version": candidate_run.get("code_version"),
        "config_version": candidate_run.get("config_version"),
        "validation_protocol": candidate_run.get("validation_protocol"),
        "claim_ceiling": "candidate_run_only",
        "promotion_status": "blocked_from_production",
        "gate_readout": {
            "gate_status": "blocked" if blockers else "walk_forward_ready",
            "blocking_gate_ids": blockers,
        },
    }


def _oos_gate_from_comparison_report(comparison_report: dict[str, Any]) -> dict[str, Any]:
    leaderboard = list(comparison_report.get("candidate_leaderboard") or [])
    best = leaderboard[0] if leaderboard else {}
    blockers = [str(item) for item in best.get("blocking_gate_ids") or []]
    if not leaderboard:
        blockers.append("missing_candidate_leaderboard")
    return {
        "artifact_type": "model_comparison_report_oos_gate",
        "schema_version": "model_comparison_report_oos_gate.v1",
        "artifact_id": f"{comparison_report.get('artifact_id')}:oos-gate",
        "validation_run_id": comparison_report.get("validation_run_id"),
        "generated_at": comparison_report.get("generated_at"),
        "source_db_snapshot_id": comparison_report.get("source_db_snapshot_id"),
        "source_data_time_range": comparison_report.get("source_data_time_range"),
        "feature_version": comparison_report.get("feature_version"),
        "label_version": comparison_report.get("label_version"),
        "code_version": comparison_report.get("code_version"),
        "config_version": "model_comparison_report_oos_gate:v1",
        "validation_protocol": {
            "artifact_role": "model_comparison_report_oos_gate",
            "source": "candidate_leaderboard_best_trial",
        },
        "claim_ceiling": "oos_gate_only",
        "promotion_status": "blocked_from_production",
        "gate_readout": {
            "gate_status": "blocked" if blockers else "oos_ready",
            "blocking_gate_ids": blockers,
        },
    }


def _multiple_testing_gate_from_comparison_report(comparison_report: dict[str, Any]) -> dict[str, Any]:
    overfit = comparison_report.get("overfit_diagnostics") if isinstance(comparison_report, dict) else {}
    blockers = [str(item) for item in (overfit or {}).get("blocking_gate_ids") or []]
    return {
        "artifact_type": "pbo_dsr_multiple_comparison",
        "schema_version": "pbo_dsr_multiple_comparison.v1",
        "artifact_id": f"{comparison_report.get('artifact_id')}:multiple-testing-gate",
        "validation_run_id": comparison_report.get("validation_run_id"),
        "generated_at": comparison_report.get("generated_at"),
        "source_db_snapshot_id": comparison_report.get("source_db_snapshot_id"),
        "source_data_time_range": comparison_report.get("source_data_time_range"),
        "feature_version": "not_applicable_multiple_testing_diagnostics",
        "label_version": comparison_report.get("label_version"),
        "code_version": comparison_report.get("code_version"),
        "config_version": "model_comparison_report_multiple_testing_gate:v1",
        "validation_protocol": {
            "artifact_role": "pbo_dsr_multiple_comparison",
            "source": "model_comparison_report_overfit_diagnostics",
        },
        "claim_ceiling": "multiple_testing_diagnostic_only",
        "promotion_status": "blocked_from_production",
        "gate_readout": {
            "gate_status": "multiple_testing_ready" if not blockers else "blocked",
            "blocking_gate_ids": blockers,
        },
    }


def build_model_governance_and_projection_artifacts(
    *,
    validation_run_id: str,
    candidate_run: dict[str, Any],
    comparison_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    source_data_time_range = comparison_report.get("source_data_time_range") or {}
    governance = build_governance_promotion_decision_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=str(comparison_report.get("source_db_snapshot_id") or ""),
        source_data_time_range=source_data_time_range if isinstance(source_data_time_range, dict) else {},
        candidate_kind="model_comparison_report",
        candidate_artifact=comparison_report,
        objective_universe=None,
        walk_forward_protocol=_walk_forward_gate_from_candidate_run(candidate_run),
        oos_validation=_oos_gate_from_comparison_report(comparison_report),
        multiple_testing_diagnostics=_multiple_testing_gate_from_comparison_report(comparison_report),
    )
    registry = build_dashboard_projection_registry_artifact(
        validation_run_id=validation_run_id,
        source_db_snapshot_id=str(comparison_report.get("source_db_snapshot_id") or ""),
        source_data_time_range=source_data_time_range if isinstance(source_data_time_range, dict) else {},
        candidate_kind="model_comparison_report",
        candidate_artifact=comparison_report,
        governance_decision=governance,
    )
    return {
        "governance_promotion_decision": governance,
        "dashboard_approved_projection_registry": registry,
    }


def write_model_governance_and_projection_artifacts(
    artifacts: dict[str, dict[str, Any]],
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(artifact_root) if artifact_root else None
    return {
        "governance_promotion_decision": write_governance_promotion_decision_artifact(
            artifacts["governance_promotion_decision"],
            artifact_root=str(root) if root else "",
        ),
        "dashboard_approved_projection_registry": write_dashboard_projection_registry_artifact(
            artifacts["dashboard_approved_projection_registry"],
            artifact_root=str(root) if root else "",
        ),
    }
