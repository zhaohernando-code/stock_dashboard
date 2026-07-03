from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ashare_evidence import artifact_store_core as _core
from ashare_evidence import autonomous_flow_artifact_store as _autonomous_flow_store
from ashare_evidence.research_artifacts import (
    BacktestArtifactView,
    ManualResearchArtifactView,
    Phase5HoldingPolicyExperimentArtifactView,
    Phase5HoldingPolicyStudyArtifactView,
    Phase5HorizonStudyArtifactView,
    Phase5ProducerContractStudyArtifactView,
    ReplayAlignmentArtifactView,
    ResearchArtifactManifestView,
    ValidationMetricsArtifactView,
)

PROJECT_ROOT = _core.PROJECT_ROOT
DEFAULT_ARTIFACT_ROOT = _core.DEFAULT_ARTIFACT_ROOT
SHORTPICK_FILTER_RESELECT_SELECTION_POLICY = "filter_ranked_pool_select_first_allowed"

read_frontend_projection_manifest_artifact = _autonomous_flow_store.read_frontend_projection_manifest_artifact
read_frontend_projection_manifest_artifact_if_exists = (
    _autonomous_flow_store.read_frontend_projection_manifest_artifact_if_exists
)
read_phase5_cycle_ledger_artifact = _autonomous_flow_store.read_phase5_cycle_ledger_artifact
read_phase5_cycle_ledger_artifact_if_exists = _autonomous_flow_store.read_phase5_cycle_ledger_artifact_if_exists
read_phase5_gate_readout_artifact = _autonomous_flow_store.read_phase5_gate_readout_artifact
read_phase5_gate_readout_artifact_if_exists = _autonomous_flow_store.read_phase5_gate_readout_artifact_if_exists
read_phase5_recovery_ticket_artifact = _autonomous_flow_store.read_phase5_recovery_ticket_artifact
read_phase5_recovery_ticket_artifact_if_exists = _autonomous_flow_store.read_phase5_recovery_ticket_artifact_if_exists
read_phase5_scheduler_diagnostic_artifact = _autonomous_flow_store.read_phase5_scheduler_diagnostic_artifact
read_phase5_scheduler_diagnostic_artifact_if_exists = (
    _autonomous_flow_store.read_phase5_scheduler_diagnostic_artifact_if_exists
)
write_frontend_projection_manifest_artifact = _autonomous_flow_store.write_frontend_projection_manifest_artifact
write_phase5_cycle_ledger_artifact = _autonomous_flow_store.write_phase5_cycle_ledger_artifact
write_phase5_gate_readout_artifact = _autonomous_flow_store.write_phase5_gate_readout_artifact
write_phase5_recovery_ticket_artifact = _autonomous_flow_store.write_phase5_recovery_ticket_artifact
write_phase5_scheduler_diagnostic_artifact = _autonomous_flow_store.write_phase5_scheduler_diagnostic_artifact


def artifact_root_from_database_url(database_url: str | None) -> Path:
    return _core.artifact_root_from_database_url(database_url, default_artifact_root=DEFAULT_ARTIFACT_ROOT)


def artifact_path(artifact_type: str, artifact_id: str, *, root: Path | None = None) -> Path:
    return _core.artifact_path(artifact_type, artifact_id, root=root, default_artifact_root=DEFAULT_ARTIFACT_ROOT)


def _ensure_artifact_write_allowed(target: Path) -> None:
    _core._ensure_artifact_write_allowed(target, project_root=PROJECT_ROOT)


def _write_model(model, artifact_type: str, artifact_id: str, *, root: Path | None = None) -> Path:
    return _core._write_model(
        model,
        artifact_type,
        artifact_id,
        root=root,
        project_root=PROJECT_ROOT,
        default_artifact_root=DEFAULT_ARTIFACT_ROOT,
    )


def _read_model(model_type, artifact_type: str, artifact_id: str, *, root: Path | None = None):
    return _core._read_model(
        model_type,
        artifact_type,
        artifact_id,
        root=root,
        default_artifact_root=DEFAULT_ARTIFACT_ROOT,
    )


def _read_model_if_exists(model_type, artifact_type: str, artifact_id: str | None, *, root: Path | None = None):
    return _core._read_model_if_exists(
        model_type,
        artifact_type,
        artifact_id,
        root=root,
        default_artifact_root=DEFAULT_ARTIFACT_ROOT,
    )


def write_shortpick_lab_artifact(
    *,
    artifact_id: str,
    payload: dict,
    root: Path | None = None,
) -> Path:
    target = artifact_path("shortpick_lab", artifact_id, root=root)
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target


def write_research_validation_artifact(
    artifact_type: str,
    artifact_id: str,
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    if artifact_type not in {
        "objective_frozen_universe",
        "research_input_snapshot",
        "pit_feature_store",
        "walk_forward_purge_embargo",
        "pbo_dsr_multiple_comparison",
        "oos_validation",
        "governance_promotion_decision",
        "dashboard_approved_projection_registry",
        "model_exploration_input_snapshot",
        "universe_date_matrix",
        "pit_feature_matrix",
        "executable_label_matrix",
        "model_spec_registry",
        "walk_forward_model_candidate_run",
        "model_comparison_report",
        "factor_ic_study",
        "weight_sweep_study",
    }:
        raise ValueError(f"unsupported research validation artifact type: {artifact_type}")
    if not artifact_id.strip():
        raise ValueError("research validation artifact requires artifact_id")
    target = artifact_path(artifact_type, artifact_id, root=root)
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target


def read_shortpick_lab_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> dict | None:
    if not artifact_id:
        return None
    target = artifact_path("shortpick_lab", artifact_id, root=root)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def write_shortpick_strategy_retirement_artifact_record(
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("shortpick strategy retirement artifact requires artifact_id")
    target = artifact_path("shortpick_strategy_retirement", artifact_id, root=root)
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target


def read_shortpick_strategy_retirement_artifacts(
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    seen_artifact_ids: set[str] = set()
    source_dirs = _shortpick_strategy_retirement_artifact_dirs(root=root)
    for directory in source_dirs:
        if not directory.exists():
            continue
        for target in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                ignored.append({"path": str(target), "reason": f"unreadable_json:{type(exc).__name__}"})
                continue
            if not isinstance(payload, dict):
                ignored.append({"path": str(target), "reason": "payload_not_object"})
                continue
            if _is_ready_shortpick_strategy_retirement_artifact(payload):
                artifact_id = str(payload.get("artifact_id") or "")
                if artifact_id in seen_artifact_ids:
                    ignored.append({"path": str(target), "reason": "duplicate_artifact_id"})
                    continue
                seen_artifact_ids.add(artifact_id)
                artifacts.append(dict(payload))
            else:
                ignored.append({"path": str(target), "reason": "not_ready_strategy_retirement_artifact"})
    return {
        "status": "ready",
        "source": "shortpick_strategy_retirement_artifact_store",
        "source_dirs": [str(path) for path in source_dirs],
        "artifact_count": len(artifacts),
        "ignored_count": len(ignored),
        "ignored": ignored,
        "artifacts": artifacts,
    }


def _shortpick_strategy_retirement_artifact_dirs(*, root: Path | None = None) -> tuple[Path, ...]:
    if root is not None:
        return (artifact_path("shortpick_strategy_retirement", "__index__", root=root).parent,)
    return tuple(
        dict.fromkeys(
            path.parent
            for path in _core._read_paths(
                "shortpick_strategy_retirement",
                "__index__",
                default_artifact_root=DEFAULT_ARTIFACT_ROOT,
                project_root=PROJECT_ROOT,
            )
        )
    )


def _is_ready_shortpick_strategy_retirement_artifact(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("status") in {"ready", "recorded"}
        and payload.get("artifact_family") in {"strategy_retirement:v1", "shortpick_strategy_retirement"}
        and payload.get("artifact_id")
        and payload.get("strategy_id")
        and payload.get("decision_log_ref")
    )


def write_shortpick_control_inventory_archive_artifact_record(
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("shortpick control inventory archive artifact requires artifact_id")
    target = artifact_path("shortpick_control_inventory_archive", artifact_id, root=root)
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target


def read_shortpick_control_inventory_archive_artifacts(
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    seen_artifact_ids: set[str] = set()
    source_dirs = _shortpick_control_inventory_archive_artifact_dirs(root=root)
    for directory in source_dirs:
        if not directory.exists():
            continue
        for target in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                ignored.append({"path": str(target), "reason": f"unreadable_json:{type(exc).__name__}"})
                continue
            if not isinstance(payload, dict):
                ignored.append({"path": str(target), "reason": "payload_not_object"})
                continue
            if _is_ready_shortpick_control_inventory_archive_artifact(payload):
                artifact_id = str(payload.get("artifact_id") or "")
                if artifact_id in seen_artifact_ids:
                    ignored.append({"path": str(target), "reason": "duplicate_artifact_id"})
                    continue
                seen_artifact_ids.add(artifact_id)
                artifacts.append(dict(payload))
            else:
                ignored.append({"path": str(target), "reason": "not_ready_shortpick_control_inventory_archive_artifact"})
    return {
        "status": "ready",
        "source": "shortpick_control_inventory_archive_artifact_store",
        "source_dirs": [str(path) for path in source_dirs],
        "artifact_count": len(artifacts),
        "ignored_count": len(ignored),
        "ignored": ignored,
        "artifacts": artifacts,
    }


def _shortpick_control_inventory_archive_artifact_dirs(*, root: Path | None = None) -> tuple[Path, ...]:
    if root is not None:
        return (artifact_path("shortpick_control_inventory_archive", "__index__", root=root).parent,)
    return tuple(
        dict.fromkeys(
            path.parent
            for path in _core._read_paths(
                "shortpick_control_inventory_archive",
                "__index__",
                default_artifact_root=DEFAULT_ARTIFACT_ROOT,
                project_root=PROJECT_ROOT,
            )
        )
    )


def _is_ready_shortpick_control_inventory_archive_artifact(payload: dict[str, Any]) -> bool:
    decisions = payload.get("archive_decisions")
    return bool(
        payload.get("status") in {"ready", "recorded"}
        and payload.get("artifact_type") == "shortpick_control_inventory_archive"
        and payload.get("artifact_id")
        and payload.get("decision_basis") == "inventory_diagnostic_value"
        and isinstance(decisions, list)
        and all(isinstance(item, dict) and item.get("strategy_id") for item in decisions)
    )


def write_shortpick_combined_ledger_backfill_artifact_record(
    payload: dict[str, Any],
    *,
    root: Path | None = None,
) -> Path:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("shortpick combined ledger backfill artifact requires artifact_id")
    target = artifact_path("shortpick_combined_ledger_backfill", artifact_id, root=root)
    _ensure_artifact_write_allowed(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target


def read_shortpick_combined_ledger_backfill_artifacts(
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    seen_artifact_ids: set[str] = set()
    source_dirs = _shortpick_combined_ledger_backfill_artifact_dirs(root=root)
    for directory in source_dirs:
        if not directory.exists():
            continue
        for target in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                ignored.append({"path": str(target), "reason": f"unreadable_json:{type(exc).__name__}"})
                continue
            if not isinstance(payload, dict):
                ignored.append({"path": str(target), "reason": "payload_not_object"})
                continue
            if _is_ready_shortpick_combined_ledger_backfill_artifact(payload):
                artifact_id = str(payload.get("artifact_id") or "")
                if artifact_id in seen_artifact_ids:
                    ignored.append({"path": str(target), "reason": "duplicate_artifact_id"})
                    continue
                seen_artifact_ids.add(artifact_id)
                artifacts.append(dict(payload))
            else:
                ignored.append({"path": str(target), "reason": "not_ready_shortpick_combined_ledger_backfill_artifact"})
    return {
        "status": "ready",
        "source": "shortpick_combined_ledger_backfill_artifact_store",
        "source_dirs": [str(path) for path in source_dirs],
        "artifact_count": len(artifacts),
        "ignored_count": len(ignored),
        "ignored": ignored,
        "artifacts": artifacts,
    }


def _shortpick_combined_ledger_backfill_artifact_dirs(*, root: Path | None = None) -> tuple[Path, ...]:
    if root is not None:
        return (artifact_path("shortpick_combined_ledger_backfill", "__index__", root=root).parent,)
    return tuple(
        dict.fromkeys(
            path.parent
            for path in _core._read_paths(
                "shortpick_combined_ledger_backfill",
                "__index__",
                default_artifact_root=DEFAULT_ARTIFACT_ROOT,
                project_root=PROJECT_ROOT,
            )
        )
    )


def _is_ready_shortpick_combined_ledger_backfill_artifact(payload: dict[str, Any]) -> bool:
    combined_rows = payload.get("combined_rows")
    if not isinstance(combined_rows, list) or not combined_rows:
        return False
    allowed_evidence_bases = {"true_forward_tracking", "retrospective_forward_replay"}
    return bool(
        payload.get("status") == "ready"
        and payload.get("artifact_type") == "shortpick_combined_ledger_backfill"
        and payload.get("artifact_id")
        and payload.get("ledger_mode") == "combined_paper_tracking_ledger"
        and payload.get("selection_policy") == SHORTPICK_FILTER_RESELECT_SELECTION_POLICY
        and payload.get("headline_metric_filter_policy") == "true_forward_queries_must_filter_evidence_basis_true_forward_tracking"
        and all(
            isinstance(row, dict)
            and row.get("combined_ledger_row_id")
            and row.get("evidence_basis") in allowed_evidence_bases
            for row in combined_rows
        )
    )


def write_manifest(manifest: ResearchArtifactManifestView, *, root: Path | None = None) -> Path:
    return _write_model(manifest, "rolling_validation", manifest.artifact_id, root=root)


def read_manifest(artifact_id: str, *, root: Path | None = None) -> ResearchArtifactManifestView:
    return _read_model(ResearchArtifactManifestView, "rolling_validation", artifact_id, root=root)


def read_manifest_if_exists(artifact_id: str | None, *, root: Path | None = None) -> ResearchArtifactManifestView | None:
    return _read_model_if_exists(ResearchArtifactManifestView, "rolling_validation", artifact_id, root=root)


def write_validation_metrics(
    artifact: ValidationMetricsArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "validation_metrics", artifact.artifact_id, root=root)


def read_validation_metrics(artifact_id: str, *, root: Path | None = None) -> ValidationMetricsArtifactView:
    return _read_model(ValidationMetricsArtifactView, "validation_metrics", artifact_id, root=root)


def read_validation_metrics_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ValidationMetricsArtifactView | None:
    return _read_model_if_exists(ValidationMetricsArtifactView, "validation_metrics", artifact_id, root=root)


def write_backtest_artifact(artifact: BacktestArtifactView, *, root: Path | None = None) -> Path:
    return _write_model(artifact, "portfolio_backtest", artifact.artifact_id, root=root)


def portfolio_backtest_artifact_id(portfolio_key: str | None) -> str | None:
    normalized = str(portfolio_key or "").strip()
    if not normalized:
        return None
    return f"portfolio-backtest:{normalized}"


def read_backtest_artifact(artifact_id: str, *, root: Path | None = None) -> BacktestArtifactView:
    return _read_model(BacktestArtifactView, "portfolio_backtest", artifact_id, root=root)


def read_backtest_artifact_if_exists(artifact_id: str | None, *, root: Path | None = None) -> BacktestArtifactView | None:
    return _read_model_if_exists(BacktestArtifactView, "portfolio_backtest", artifact_id, root=root)


def resolve_backtest_artifact(
    *,
    configured_artifact_id: str | None,
    portfolio_key: str | None,
    root: Path | None = None,
) -> tuple[str | None, BacktestArtifactView | None]:
    normalized_configured = str(configured_artifact_id or "").strip() or None
    canonical_artifact_id = portfolio_backtest_artifact_id(portfolio_key)
    candidate_ids: list[str] = []
    if normalized_configured:
        candidate_ids.append(normalized_configured)
    if canonical_artifact_id and canonical_artifact_id not in candidate_ids:
        candidate_ids.append(canonical_artifact_id)
    for artifact_id in candidate_ids:
        artifact = read_backtest_artifact_if_exists(artifact_id, root=root)
        if artifact is not None:
            return artifact_id, artifact
    if candidate_ids:
        return candidate_ids[0], None
    return None, None


def write_replay_alignment_artifact(
    artifact: ReplayAlignmentArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "replay_alignment", artifact.artifact_id, root=root)


def read_replay_alignment_artifact(artifact_id: str, *, root: Path | None = None) -> ReplayAlignmentArtifactView:
    return _read_model(ReplayAlignmentArtifactView, "replay_alignment", artifact_id, root=root)


def read_replay_alignment_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ReplayAlignmentArtifactView | None:
    return _read_model_if_exists(ReplayAlignmentArtifactView, "replay_alignment", artifact_id, root=root)


def write_manual_research_artifact(
    artifact: ManualResearchArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "manual_review", artifact.artifact_id, root=root)


def read_manual_research_artifact(artifact_id: str, *, root: Path | None = None) -> ManualResearchArtifactView:
    return _read_model(ManualResearchArtifactView, "manual_review", artifact_id, root=root)


def read_manual_research_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> ManualResearchArtifactView | None:
    return _read_model_if_exists(ManualResearchArtifactView, "manual_review", artifact_id, root=root)


def write_phase5_horizon_study_artifact(
    artifact: Phase5HorizonStudyArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_horizon_study", artifact.artifact_id, root=root)


def read_phase5_horizon_study_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5HorizonStudyArtifactView:
    return _read_model(Phase5HorizonStudyArtifactView, "phase5_horizon_study", artifact_id, root=root)


def read_phase5_horizon_study_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5HorizonStudyArtifactView | None:
    return _read_model_if_exists(Phase5HorizonStudyArtifactView, "phase5_horizon_study", artifact_id, root=root)


def write_phase5_holding_policy_study_artifact(
    artifact: Phase5HoldingPolicyStudyArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_holding_policy_study", artifact.artifact_id, root=root)


def read_phase5_holding_policy_study_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyStudyArtifactView:
    return _read_model(Phase5HoldingPolicyStudyArtifactView, "phase5_holding_policy_study", artifact_id, root=root)


def read_phase5_holding_policy_study_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyStudyArtifactView | None:
    return _read_model_if_exists(
        Phase5HoldingPolicyStudyArtifactView,
        "phase5_holding_policy_study",
        artifact_id,
        root=root,
    )


def write_phase5_holding_policy_experiment_artifact(
    artifact: Phase5HoldingPolicyExperimentArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_holding_policy_experiment", artifact.artifact_id, root=root)


def read_phase5_holding_policy_experiment_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyExperimentArtifactView:
    return _read_model(Phase5HoldingPolicyExperimentArtifactView, "phase5_holding_policy_experiment", artifact_id, root=root)


def read_phase5_holding_policy_experiment_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5HoldingPolicyExperimentArtifactView | None:
    return _read_model_if_exists(
        Phase5HoldingPolicyExperimentArtifactView,
        "phase5_holding_policy_experiment",
        artifact_id,
        root=root,
    )


def write_phase5_producer_contract_study_artifact(
    artifact: Phase5ProducerContractStudyArtifactView,
    *,
    root: Path | None = None,
) -> Path:
    return _write_model(artifact, "phase5_producer_contract_study", artifact.artifact_id, root=root)


def read_phase5_producer_contract_study_artifact(
    artifact_id: str,
    *,
    root: Path | None = None,
) -> Phase5ProducerContractStudyArtifactView:
    return _read_model(Phase5ProducerContractStudyArtifactView, "phase5_producer_contract_study", artifact_id, root=root)


def read_phase5_producer_contract_study_artifact_if_exists(
    artifact_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5ProducerContractStudyArtifactView | None:
    return _read_model_if_exists(
        Phase5ProducerContractStudyArtifactView,
        "phase5_producer_contract_study",
        artifact_id,
        root=root,
    )
