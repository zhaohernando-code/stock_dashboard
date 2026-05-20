from __future__ import annotations

from pathlib import Path

from ashare_evidence.artifact_store_core import (
    DEFAULT_ARTIFACT_ROOT,
    PROJECT_ROOT,
    _read_model,
    _read_model_if_exists,
    _write_model,
)
from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    Phase5SchedulerDiagnosticArtifact,
)


def write_phase5_cycle_ledger_artifact(
    artifact: Phase5CycleLedgerArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "phase5_cycle_ledger",
        artifact.cycle_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_cycle_ledger_artifact(
    cycle_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5CycleLedgerArtifact:
    return _read_model(
        Phase5CycleLedgerArtifact,
        "phase5_cycle_ledger",
        cycle_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_cycle_ledger_artifact_if_exists(
    cycle_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5CycleLedgerArtifact | None:
    return _read_model_if_exists(
        Phase5CycleLedgerArtifact,
        "phase5_cycle_ledger",
        cycle_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def write_phase5_recovery_ticket_artifact(
    artifact: Phase5RecoveryTicketArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "phase5_recovery_ticket",
        artifact.ticket_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_recovery_ticket_artifact(
    ticket_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5RecoveryTicketArtifact:
    return _read_model(
        Phase5RecoveryTicketArtifact,
        "phase5_recovery_ticket",
        ticket_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_recovery_ticket_artifact_if_exists(
    ticket_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5RecoveryTicketArtifact | None:
    return _read_model_if_exists(
        Phase5RecoveryTicketArtifact,
        "phase5_recovery_ticket",
        ticket_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def write_phase5_scheduler_diagnostic_artifact(
    artifact: Phase5SchedulerDiagnosticArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "phase5_scheduler_diagnostic",
        artifact.diagnostic_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_scheduler_diagnostic_artifact(
    diagnostic_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerDiagnosticArtifact:
    return _read_model(
        Phase5SchedulerDiagnosticArtifact,
        "phase5_scheduler_diagnostic",
        diagnostic_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_scheduler_diagnostic_artifact_if_exists(
    diagnostic_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerDiagnosticArtifact | None:
    return _read_model_if_exists(
        Phase5SchedulerDiagnosticArtifact,
        "phase5_scheduler_diagnostic",
        diagnostic_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def write_phase5_gate_readout_artifact(
    artifact: Phase5GateReadoutArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "phase5_gate_readout",
        artifact.gate_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_gate_readout_artifact(
    gate_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5GateReadoutArtifact:
    return _read_model(
        Phase5GateReadoutArtifact,
        "phase5_gate_readout",
        gate_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_gate_readout_artifact_if_exists(
    gate_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5GateReadoutArtifact | None:
    return _read_model_if_exists(
        Phase5GateReadoutArtifact,
        "phase5_gate_readout",
        gate_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def write_frontend_projection_manifest_artifact(
    artifact: FrontendProjectionManifestArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "frontend_projection_manifest",
        artifact.projection_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_frontend_projection_manifest_artifact(
    projection_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> FrontendProjectionManifestArtifact:
    return _read_model(
        FrontendProjectionManifestArtifact,
        "frontend_projection_manifest",
        projection_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def read_frontend_projection_manifest_artifact_if_exists(
    projection_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> FrontendProjectionManifestArtifact | None:
    return _read_model_if_exists(
        FrontendProjectionManifestArtifact,
        "frontend_projection_manifest",
        projection_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
