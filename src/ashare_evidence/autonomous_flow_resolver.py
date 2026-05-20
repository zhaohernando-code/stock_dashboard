from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
)
from ashare_evidence.research_artifact_store import (
    read_frontend_projection_manifest_artifact_if_exists,
    read_phase5_cycle_ledger_artifact_if_exists,
    read_phase5_gate_readout_artifact_if_exists,
    read_phase5_recovery_ticket_artifact_if_exists,
)

GATE_READOUT_FAMILY = "phase5_gate_readout"
RECOVERY_TICKET_FAMILY = "phase5_recovery_ticket"
PROJECTION_MANIFEST_FAMILY = "frontend_projection_manifest"

Phase5RunnerInputFailureClass = Literal["artifact-missing", "contract-violation"]
Phase5RunnerInputRecoveryAction = Literal["open_recovery_ticket", "block_cycle"]
Phase5RunnerInputSummaryStatus = Literal["degraded", "blocked"]
Phase5RunnerInputNextAction = Literal["retry_failed_step", "blocked"]


class Phase5RunnerInputResolutionError(ValueError):
    """Raised when required runner input resolution must fail closed."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: Phase5RunnerInputFailureClass = "contract-violation",
        recommended_recovery_action: Phase5RunnerInputRecoveryAction = "block_cycle",
        summary_status: Phase5RunnerInputSummaryStatus = "blocked",
        recommended_next_action: Phase5RunnerInputNextAction = "blocked",
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.recommended_recovery_action = recommended_recovery_action
        self.summary_status = summary_status
        self.recommended_next_action = recommended_next_action


class Phase5RunnerInputBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle: Phase5CycleLedgerArtifact
    gate_readout: Phase5GateReadoutArtifact | None = None
    recovery_ticket: Phase5RecoveryTicketArtifact | None = None
    projection_manifest: FrontendProjectionManifestArtifact | None = None
    missing_refs: list[str] = Field(default_factory=list)


def resolve_phase5_runner_inputs(
    *,
    cycle_id: str,
    gate_id: str | None = None,
    recovery_ticket_id: str | None = None,
    projection_id: str | None = None,
    root: Path | None = None,
) -> Phase5RunnerInputBundle:
    cycle = read_phase5_cycle_ledger_artifact_if_exists(cycle_id, root=root)
    if cycle is None:
        raise Phase5RunnerInputResolutionError(
            f"phase5 cycle ledger artifact is missing: {cycle_id}",
            failure_class="artifact-missing",
            recommended_recovery_action="open_recovery_ticket",
            summary_status="degraded",
            recommended_next_action="retry_failed_step",
        )

    missing_refs: list[str] = []

    selected_gate_id = _selected_ref_id(
        explicit_id=gate_id,
        refs=cycle.gate_readout_refs,
        artifact_family=GATE_READOUT_FAMILY,
    )
    gate_readout = read_phase5_gate_readout_artifact_if_exists(selected_gate_id, root=root)
    if gate_readout is None:
        _append_missing_ref(missing_refs, _artifact_ref(GATE_READOUT_FAMILY, selected_gate_id))
    else:
        _ensure_cycle_match(
            cycle_id=cycle.cycle_id,
            artifact_family=GATE_READOUT_FAMILY,
            artifact_id=gate_readout.gate_id,
            artifact_cycle_id=gate_readout.cycle_id,
        )

    selected_recovery_ticket_id = _selected_ref_id(
        explicit_id=recovery_ticket_id,
        refs=cycle.recovery_ticket_refs,
        artifact_family=RECOVERY_TICKET_FAMILY,
    )
    recovery_ticket = read_phase5_recovery_ticket_artifact_if_exists(selected_recovery_ticket_id, root=root)
    if selected_recovery_ticket_id and recovery_ticket is None:
        _append_missing_ref(missing_refs, _artifact_ref(RECOVERY_TICKET_FAMILY, selected_recovery_ticket_id))
    if recovery_ticket is not None:
        _ensure_cycle_match(
            cycle_id=cycle.cycle_id,
            artifact_family=RECOVERY_TICKET_FAMILY,
            artifact_id=recovery_ticket.ticket_id,
            artifact_cycle_id=recovery_ticket.cycle_id,
        )

    selected_projection_id = _selected_projection_id(
        explicit_id=projection_id,
        artifact_refs=cycle.artifact_refs,
    )
    projection_manifest = read_frontend_projection_manifest_artifact_if_exists(selected_projection_id, root=root)
    if projection_manifest is None:
        _append_missing_ref(missing_refs, _artifact_ref(PROJECTION_MANIFEST_FAMILY, selected_projection_id))
    else:
        _ensure_cycle_match(
            cycle_id=cycle.cycle_id,
            artifact_family=PROJECTION_MANIFEST_FAMILY,
            artifact_id=projection_manifest.projection_id,
            artifact_cycle_id=projection_manifest.cycle_id,
        )

    return Phase5RunnerInputBundle(
        cycle=cycle,
        gate_readout=gate_readout,
        recovery_ticket=recovery_ticket,
        projection_manifest=projection_manifest,
        missing_refs=missing_refs,
    )


def _selected_projection_id(*, explicit_id: str | None, artifact_refs: list[str]) -> str | None:
    normalized_explicit = _normalize_artifact_id(explicit_id, PROJECTION_MANIFEST_FAMILY)
    if normalized_explicit:
        return normalized_explicit
    prefix = f"{PROJECTION_MANIFEST_FAMILY}:"
    for artifact_ref in reversed(artifact_refs):
        if artifact_ref.startswith(prefix):
            projection_id = artifact_ref.removeprefix(prefix)
            if projection_id:
                return projection_id
    return None


def _selected_ref_id(
    *,
    explicit_id: str | None,
    refs: list[str],
    artifact_family: str,
) -> str | None:
    normalized_explicit = _normalize_artifact_id(explicit_id, artifact_family)
    if normalized_explicit:
        return normalized_explicit
    if not refs:
        return None
    return _normalize_artifact_id(refs[-1], artifact_family)


def _normalize_artifact_id(value: str | None, artifact_family: str) -> str | None:
    if not value:
        return None
    prefix = f"{artifact_family}:"
    if value.startswith(prefix):
        artifact_id = value.removeprefix(prefix)
        return artifact_id or None
    return value


def _artifact_ref(artifact_family: str, artifact_id: str | None) -> str:
    if artifact_id:
        return f"{artifact_family}:{artifact_id}"
    return f"{artifact_family}:<missing>"


def _ensure_cycle_match(
    *,
    cycle_id: str,
    artifact_family: str,
    artifact_id: str,
    artifact_cycle_id: str,
) -> None:
    if artifact_cycle_id != cycle_id:
        raise Phase5RunnerInputResolutionError(
            f"{artifact_family} artifact cycle mismatch: artifact_id={artifact_id}, "
            f"artifact_cycle_id={artifact_cycle_id}, expected_cycle_id={cycle_id}"
        )


def _append_missing_ref(missing_refs: list[str], artifact_ref: str) -> None:
    if artifact_ref not in missing_refs:
        missing_refs.append(artifact_ref)
