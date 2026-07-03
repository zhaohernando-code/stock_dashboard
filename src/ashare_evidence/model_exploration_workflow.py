from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.model_candidate_runner import (
    build_walk_forward_model_candidate_run_artifact,
    write_walk_forward_model_candidate_run_artifact,
)
from ashare_evidence.model_comparison_report import (
    build_model_comparison_report_artifact,
    write_model_comparison_report_artifact,
)
from ashare_evidence.model_exploration_snapshot import (
    build_model_exploration_p1_artifacts,
    write_model_exploration_p1_artifacts,
)
from ashare_evidence.model_governance_gate import (
    build_model_governance_and_projection_artifacts,
    write_model_governance_and_projection_artifacts,
)
from ashare_evidence.model_spec_registry import build_model_spec_registry_artifact, write_model_spec_registry_artifact
from ashare_evidence.research_artifact_store import artifact_root_from_database_url


def _artifact_summary(payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "artifact_id": payload.get("artifact_id"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "path": str(path) if path else None,
        "gate_readout": payload.get("gate_readout"),
    }


def run_shortpick_model_exploration_workbench(
    session: Session,
    *,
    database_url: str | None,
    validation_run_id: str,
    as_of_dates: list[date] | None = None,
    max_as_of_dates: int | None = None,
    benchmark_symbol: str = "000300.SH",
    selected_model_spec_ids: list[str] | None = None,
    min_train_dates: int = 60,
    test_window_dates: int = 20,
    write_artifacts: bool = True,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root else artifact_root_from_database_url(database_url)
    matrix_artifacts = build_model_exploration_p1_artifacts(
        session,
        validation_run_id=validation_run_id,
        as_of_dates=as_of_dates,
        benchmark_symbol=benchmark_symbol,
        max_as_of_dates=max_as_of_dates,
    )
    registry = build_model_spec_registry_artifact(
        validation_run_id=validation_run_id,
        source_input_snapshot_id=str(matrix_artifacts["model_exploration_input_snapshot"]["artifact_id"]),
    )
    candidate_run = build_walk_forward_model_candidate_run_artifact(
        validation_run_id=validation_run_id,
        feature_matrix=matrix_artifacts["pit_feature_matrix"],
        label_matrix=matrix_artifacts["executable_label_matrix"],
        model_spec_registry=registry,
        min_train_dates=min_train_dates,
        test_window_dates=test_window_dates,
        selected_model_spec_ids=selected_model_spec_ids,
    )
    comparison_report = build_model_comparison_report_artifact(
        validation_run_id=validation_run_id,
        candidate_run=candidate_run,
        model_spec_registry=registry,
    )
    governance_artifacts = build_model_governance_and_projection_artifacts(
        validation_run_id=validation_run_id,
        candidate_run=candidate_run,
        comparison_report=comparison_report,
    )

    written_paths: dict[str, Path] = {}
    if write_artifacts:
        written_paths.update(write_model_exploration_p1_artifacts(matrix_artifacts, artifact_root=root))
        written_paths["model_spec_registry"] = write_model_spec_registry_artifact(registry, artifact_root=root)
        written_paths["walk_forward_model_candidate_run"] = write_walk_forward_model_candidate_run_artifact(
            candidate_run,
            artifact_root=root,
        )
        written_paths["model_comparison_report"] = write_model_comparison_report_artifact(
            comparison_report,
            artifact_root=root,
        )
        written_paths.update(write_model_governance_and_projection_artifacts(governance_artifacts, artifact_root=root))

    all_artifacts = {
        **matrix_artifacts,
        "model_spec_registry": registry,
        "walk_forward_model_candidate_run": candidate_run,
        "model_comparison_report": comparison_report,
        **governance_artifacts,
    }
    return {
        "status": "completed",
        "workflow": "shortpick_model_exploration_workbench_p1",
        "validation_run_id": validation_run_id,
        "artifact_root": str(root),
        "write_artifacts": write_artifacts,
        "production_effect": "forbidden",
        "runtime_db_write_policy": "read_only_input_no_business_table_writes",
        "dashboard_projection_policy": "registry_only_approved_projection_count_must_gate_dashboard",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "diagnostic_research_only",
        "artifact_summaries": {
            artifact_type: _artifact_summary(payload, written_paths.get(artifact_type))
            for artifact_type, payload in all_artifacts.items()
        },
        "blocking_summary": {
            "governance": governance_artifacts["governance_promotion_decision"].get("gate_readout", {}),
            "dashboard_projection": governance_artifacts["dashboard_approved_projection_registry"].get("gate_readout", {}),
        },
    }
