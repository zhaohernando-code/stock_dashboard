from __future__ import annotations

import gc
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.model_candidate_runner import (
    _load_artifact_metadata_without_rows,
    build_streamed_walk_forward_model_candidate_run_artifact,
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

REQUIRED_MATRIX_ARTIFACT_KEYS = (
    "model_exploration_input_snapshot",
    "pit_feature_matrix",
    "executable_label_matrix",
)


def _artifact_summary(payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "artifact_id": payload.get("artifact_id"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "path": str(path) if path else None,
        "gate_readout": payload.get("gate_readout"),
    }


def _load_json_artifact(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact payload must be a JSON object: {path}")
    return payload


def load_model_exploration_matrix_artifacts(
    *,
    input_snapshot_artifact: str | Path,
    feature_matrix_artifact: str | Path,
    label_matrix_artifact: str | Path,
) -> dict[str, dict[str, Any]]:
    artifacts = {
        "model_exploration_input_snapshot": _load_json_artifact(input_snapshot_artifact),
        "pit_feature_matrix": _load_json_artifact(feature_matrix_artifact),
        "executable_label_matrix": _load_json_artifact(label_matrix_artifact),
    }
    expected_types = {
        "model_exploration_input_snapshot": "model_exploration_input_snapshot",
        "pit_feature_matrix": "pit_feature_matrix",
        "executable_label_matrix": "executable_label_matrix",
    }
    failures: list[str] = []
    for key, expected_type in expected_types.items():
        artifact_type = artifacts[key].get("artifact_type")
        if artifact_type != expected_type:
            failures.append(f"{key}:expected_{expected_type}_got_{artifact_type}")
    source_input_snapshot_id = artifacts["model_exploration_input_snapshot"].get("artifact_id")
    for key in ("pit_feature_matrix", "executable_label_matrix"):
        if artifacts[key].get("source_input_snapshot_id") != source_input_snapshot_id:
            failures.append(f"{key}:source_input_snapshot_id_mismatch")
    if failures:
        raise ValueError(f"invalid model exploration matrix artifacts: {', '.join(failures)}")
    return artifacts


def run_shortpick_model_exploration_workbench(
    session: Session,
    *,
    database_url: str | None,
    validation_run_id: str,
    as_of_dates: list[date] | None = None,
    max_as_of_dates: int | None = None,
    benchmark_symbol: str = "000300.SH",
    entry_price_source: str = "next_close",
    selected_model_spec_ids: list[str] | None = None,
    min_train_dates: int = 60,
    test_window_dates: int = 20,
    write_artifacts: bool = True,
    artifact_root: str | Path | None = None,
    input_snapshot_artifact: str | Path | None = None,
    feature_matrix_artifact: str | Path | None = None,
    label_matrix_artifact: str | Path | None = None,
    stream_matrix_replay: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root else artifact_root_from_database_url(database_url)
    supplied_matrix_artifacts = [input_snapshot_artifact, feature_matrix_artifact, label_matrix_artifact]
    if any(supplied_matrix_artifacts) and not all(supplied_matrix_artifacts):
        raise ValueError("input, feature and label matrix artifacts must be supplied together")
    matrix_artifacts_reused = all(supplied_matrix_artifacts)
    if matrix_artifacts_reused and not stream_matrix_replay:
        matrix_artifacts = load_model_exploration_matrix_artifacts(
            input_snapshot_artifact=str(input_snapshot_artifact),
            feature_matrix_artifact=str(feature_matrix_artifact),
            label_matrix_artifact=str(label_matrix_artifact),
        )
    elif matrix_artifacts_reused:
        feature_matrix_metadata = _load_artifact_metadata_without_rows(str(feature_matrix_artifact))
        label_matrix_metadata = _load_artifact_metadata_without_rows(str(label_matrix_artifact))
        matrix_artifacts = {
            "model_exploration_input_snapshot": _load_json_artifact(str(input_snapshot_artifact)),
            "pit_feature_matrix": feature_matrix_metadata,
            "executable_label_matrix": label_matrix_metadata,
        }
    else:
        matrix_artifacts = build_model_exploration_p1_artifacts(
            session,
            validation_run_id=validation_run_id,
            as_of_dates=as_of_dates,
            benchmark_symbol=benchmark_symbol,
            max_as_of_dates=max_as_of_dates,
            entry_price_source=entry_price_source,
        )
    registry = build_model_spec_registry_artifact(
        validation_run_id=validation_run_id,
        source_input_snapshot_id=str(matrix_artifacts["model_exploration_input_snapshot"]["artifact_id"]),
    )
    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        if matrix_artifacts_reused and stream_matrix_replay:
            candidate_run = build_streamed_walk_forward_model_candidate_run_artifact(
                validation_run_id=validation_run_id,
                feature_matrix_artifact=str(feature_matrix_artifact),
                label_matrix_artifact=str(label_matrix_artifact),
                model_spec_registry=registry,
                min_train_dates=min_train_dates,
                test_window_dates=test_window_dates,
                selected_model_spec_ids=selected_model_spec_ids,
                source_db_snapshot_id=matrix_artifacts["model_exploration_input_snapshot"].get("source_db_snapshot_id"),
                source_data_time_range=matrix_artifacts["model_exploration_input_snapshot"].get(
                    "source_data_time_range"
                ),
            )
        else:
            candidate_run = build_walk_forward_model_candidate_run_artifact(
                validation_run_id=validation_run_id,
                feature_matrix=matrix_artifacts["pit_feature_matrix"],
                label_matrix=matrix_artifacts["executable_label_matrix"],
                model_spec_registry=registry,
                min_train_dates=min_train_dates,
                test_window_dates=test_window_dates,
                selected_model_spec_ids=selected_model_spec_ids,
            )
    finally:
        if gc_was_enabled:
            gc.enable()
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
        if not matrix_artifacts_reused:
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
        "matrix_artifacts_reused": matrix_artifacts_reused,
        "stream_matrix_replay": stream_matrix_replay,
        "matrix_artifact_ids": {
            key: matrix_artifacts[key].get("artifact_id")
            for key in REQUIRED_MATRIX_ARTIFACT_KEYS
        },
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
