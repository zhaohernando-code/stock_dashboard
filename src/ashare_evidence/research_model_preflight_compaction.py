from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ashare_evidence.model_candidate_runner import _load_artifact_metadata_without_rows


MODEL_PREFLIGHT_COMPACT_SUMMARY_VERSION = "model_preflight_compact_summary.v1"

_ARTIFACT_FOLDERS = {
    "model_exploration_input_snapshot": "model_exploration_input_snapshots",
    "universe_date_matrix": "universe_date_matrices",
    "pit_feature_matrix": "pit_feature_matrices",
    "executable_label_matrix": "executable_label_matrices",
    "model_spec_registry": "model_spec_registries",
    "walk_forward_model_candidate_run": "walk_forward_model_candidate_runs",
    "model_comparison_report": "model_comparison_reports",
    "governance_promotion_decision": "governance_promotion_decisions",
    "dashboard_approved_projection_registry": "dashboard_approved_projection_registries",
}
_MATRIX_ARTIFACT_TYPES = {
    "universe_date_matrix",
    "pit_feature_matrix",
    "executable_label_matrix",
}


def compact_model_preflight_root(
    *,
    preflight_root: str | Path,
    output_json: str | Path,
    delete_source_root: bool = False,
) -> dict[str, Any]:
    """Retain compact preflight evidence without keeping large matrix/candidate payloads."""

    source_root = Path(preflight_root)
    if not source_root.exists():
        raise FileNotFoundError(f"preflight root does not exist: {source_root}")
    output_path = Path(output_json)
    research_root = source_root / "research_validation"
    if not research_root.exists():
        raise FileNotFoundError(f"research_validation folder does not exist: {research_root}")

    artifacts = {
        artifact_type: _load_compact_artifact(source_root, artifact_type, folder)
        for artifact_type, folder in _ARTIFACT_FOLDERS.items()
    }
    present_artifacts = {key: value for key, value in artifacts.items() if value is not None}
    candidate_run = present_artifacts.get("walk_forward_model_candidate_run", {})
    comparison_report = present_artifacts.get("model_comparison_report", {})
    governance = present_artifacts.get("governance_promotion_decision", {})
    dashboard = present_artifacts.get("dashboard_approved_projection_registry", {})
    input_snapshot = present_artifacts.get("model_exploration_input_snapshot", {})
    feature_matrix = present_artifacts.get("pit_feature_matrix", {})
    label_matrix = present_artifacts.get("executable_label_matrix", {})
    source_size_bytes = _directory_size(source_root)
    payload = {
        "artifact_type": "model_preflight_compact_summary",
        "schema_version": MODEL_PREFLIGHT_COMPACT_SUMMARY_VERSION,
        "claim_ceiling": "bounded_preflight_summary_only_no_formal_acceptance_no_runtime_effect",
        "source_preflight_root": str(source_root),
        "source_root_size_bytes_before_cleanup": source_size_bytes,
        "cleanup_policy": "source_root_deleted_after_summary" if delete_source_root else "source_root_retained",
        "source_root_exists_after_cleanup": None,
        "validation_run_id": _first_present(
            input_snapshot.get("validation_run_id"),
            candidate_run.get("validation_run_id"),
            comparison_report.get("validation_run_id"),
        ),
        "feature_version": _first_present(
            input_snapshot.get("feature_version"),
            feature_matrix.get("feature_version"),
            candidate_run.get("feature_version"),
            comparison_report.get("feature_version"),
        ),
        "source_data_time_range": _first_present(
            input_snapshot.get("source_data_time_range"),
            candidate_run.get("source_data_time_range"),
            comparison_report.get("source_data_time_range"),
        ),
        "artifacts": {
            artifact_type: _artifact_readout(artifact)
            for artifact_type, artifact in present_artifacts.items()
        },
        "matrix_readout": {
            "eligible_symbol_count": input_snapshot.get("eligible_symbol_count"),
            "as_of_date_count": input_snapshot.get("as_of_date_count"),
            "universe_row_count": input_snapshot.get("universe_row_count"),
            "feature_row_count": feature_matrix.get("row_count"),
            "feature_groups": feature_matrix.get("feature_groups"),
            "label_row_count": label_matrix.get("row_count"),
            "label_ready_row_count": (label_matrix.get("gate_readout") or {}).get("ready_row_count"),
        },
        "candidate_run_readout": {
            "artifact_id": candidate_run.get("artifact_id"),
            "selected_model_spec_ids": candidate_run.get("selected_model_spec_ids"),
            "trial_count": candidate_run.get("trial_count"),
            "prediction_row_count": candidate_run.get("prediction_row_count"),
            "stored_prediction_row_count": candidate_run.get("stored_prediction_row_count"),
            "prediction_storage_policy": candidate_run.get("prediction_storage_policy"),
            "compact_trial_diagnostics": _compact_trial_diagnostics(candidate_run.get("trial_diagnostics") or []),
        },
        "blocking_gate_ids": sorted(
            set(
                _gate_ids(comparison_report)
                + [f"governance:{gate_id}" for gate_id in _gate_ids(governance)]
                + [f"dashboard:{gate_id}" for gate_id in _gate_ids(dashboard)]
            )
        ),
        "interpretation": [
            "This compact summary preserves preflight chain evidence without retaining large matrix rows.",
            "It is not a formal full-window acceptance replay and must not be used as a production or dashboard approval.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if delete_source_root:
        shutil.rmtree(source_root)
    payload["source_root_exists_after_cleanup"] = source_root.exists()
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _load_compact_artifact(source_root: Path, artifact_type: str, folder: str) -> dict[str, Any] | None:
    artifact_dir = source_root / "research_validation" / folder
    if not artifact_dir.exists():
        return None
    artifacts = sorted(path for path in artifact_dir.glob("*.json") if path.is_file())
    if not artifacts:
        return None
    path = artifacts[0]
    if artifact_type in _MATRIX_ARTIFACT_TYPES:
        payload = _load_artifact_metadata_without_rows(path)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    payload["_source_path"] = str(path)
    payload["_source_size_bytes"] = path.stat().st_size
    return payload


def _artifact_readout(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": artifact.get("artifact_id"),
        "artifact_type": artifact.get("artifact_type"),
        "path": artifact.get("_source_path"),
        "size_bytes": artifact.get("_source_size_bytes"),
        "promotion_status": artifact.get("promotion_status"),
        "claim_ceiling": artifact.get("claim_ceiling"),
        "gate_readout": artifact.get("gate_readout"),
    }


def _compact_trial_diagnostics(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for trial in trials[:8]:
        compact.append(
            {
                "trial_id": trial.get("trial_id"),
                "model_spec_id": trial.get("model_spec_id"),
                "trial_rank": trial.get("trial_rank"),
                "total_return": trial.get("total_return"),
                "annualized_return": trial.get("annualized_return"),
                "mean_selected_net_excess_return": trial.get("mean_selected_net_excess_return"),
                "positive_selected_top_k_rate": trial.get("positive_selected_top_k_rate"),
                "max_drawdown": trial.get("max_drawdown"),
                "negative_month_count": trial.get("negative_month_count"),
                "worst_monthly_mean": trial.get("worst_monthly_mean"),
                "path_drawdown_sum": trial.get("path_drawdown_sum"),
                "adv_capacity_full_fill_rate": trial.get("adv_capacity_full_fill_rate"),
                "active_underfilled_pick_count": trial.get("active_underfilled_pick_count"),
            }
        )
    return compact


def _gate_ids(artifact: dict[str, Any]) -> list[str]:
    gate_readout = artifact.get("gate_readout") if isinstance(artifact, dict) else None
    if not isinstance(gate_readout, dict):
        return []
    return [str(gate_id) for gate_id in gate_readout.get("blocking_gate_ids") or []]


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _directory_size(root: Path) -> int:
    if root.is_file():
        return root.stat().st_size
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total
