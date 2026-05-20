from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    PublishVerificationRef,
)
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact_if_exists,
    write_frontend_projection_manifest_artifact,
    write_phase5_cycle_ledger_artifact,
    write_phase5_gate_readout_artifact,
    write_phase5_recovery_ticket_artifact,
)

PHASE5_CYCLE_STARTED_EVENT = "phase5.cycle.started.v1"
PHASE5_ARTIFACT_PRODUCED_EVENT = "phase5.artifact.produced.v1"
PHASE5_GATE_EVALUATED_EVENT = "phase5.gate.evaluated.v1"
PHASE5_PROJECTION_REFRESHED_EVENT = "phase5.projection.refreshed.v1"
PHASE5_RECOVERY_RECORDED_EVENT = "phase5.recovery.recorded.v1"
RUNTIME_PUBLISH_VERIFIED_EVENT = "runtime.publish.verified.v1"


class Phase5CycleNotFoundError(LookupError):
    """Raised when an update targets a cycle ledger that has not been created."""


def start_phase5_cycle(
    *,
    cycle_id: str,
    trigger: str,
    started_at: str,
    scope: dict[str, Any] | None = None,
    input_contract_versions: dict[str, str] | None = None,
    status: str = "running",
    next_action: str = "continue_tracking",
    root: Path | None = None,
) -> Phase5CycleLedgerArtifact:
    cycle = Phase5CycleLedgerArtifact(
        cycle_id=cycle_id,
        trigger=trigger,
        scope=dict(scope or {}),
        status=status,
        started_at=started_at,
        input_contract_versions=dict(input_contract_versions or {}),
        event_refs=[PHASE5_CYCLE_STARTED_EVENT],
        next_action=next_action,
    )
    write_phase5_cycle_ledger_artifact(cycle, root=root)
    return cycle


def record_phase5_artifact(
    *,
    cycle_id: str,
    artifact_ref: str,
    root: Path | None = None,
) -> Phase5CycleLedgerArtifact:
    cycle = _require_cycle(cycle_id, root=root)
    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, PHASE5_ARTIFACT_PRODUCED_EVENT),
            "artifact_refs": _append_unique(cycle.artifact_refs, artifact_ref),
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated


def record_phase5_gate_readout(
    *,
    cycle_id: str,
    gate_id: str,
    gate_status: str,
    claim_ceiling: str,
    next_action: str,
    evaluated_at: str,
    failing_gate_ids: list[str] | None = None,
    incomplete_gate_ids: list[str] | None = None,
    source_artifact_ids: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    root: Path | None = None,
) -> tuple[Phase5CycleLedgerArtifact, Phase5GateReadoutArtifact]:
    cycle = _require_cycle(cycle_id, root=root)
    readout = Phase5GateReadoutArtifact(
        gate_id=gate_id,
        cycle_id=cycle_id,
        gate_status=gate_status,
        failing_gate_ids=_dedupe(failing_gate_ids or []),
        incomplete_gate_ids=_dedupe(incomplete_gate_ids or []),
        claim_ceiling=claim_ceiling,
        source_artifact_ids=_dedupe(source_artifact_ids or []),
        blocking_reasons=_dedupe(blocking_reasons or []),
        next_action=next_action,
        evaluated_at=evaluated_at,
    )
    write_phase5_gate_readout_artifact(readout, root=root)
    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, PHASE5_GATE_EVALUATED_EVENT),
            "gate_readout_refs": _append_unique(cycle.gate_readout_refs, gate_id),
            "next_action": next_action,
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated, readout


def record_phase5_recovery_ticket(
    *,
    cycle_id: str,
    ticket_id: str,
    failed_step: str,
    failure_class: str,
    failure_observed_at: str,
    recovery_action: str,
    final_status: str,
    claim_ceiling_effect: str,
    evidence_refs: list[str] | None = None,
    retry_count: int = 0,
    notes: str = "",
    root: Path | None = None,
) -> tuple[Phase5CycleLedgerArtifact, Phase5RecoveryTicketArtifact]:
    cycle = _require_cycle(cycle_id, root=root)
    ticket = Phase5RecoveryTicketArtifact(
        ticket_id=ticket_id,
        cycle_id=cycle_id,
        failed_step=failed_step,
        failure_class=failure_class,
        failure_observed_at=failure_observed_at,
        evidence_refs=_dedupe(evidence_refs or []),
        recovery_action=recovery_action,
        retry_count=retry_count,
        final_status=final_status,
        claim_ceiling_effect=claim_ceiling_effect,
        notes=notes,
    )
    write_phase5_recovery_ticket_artifact(ticket, root=root)
    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, PHASE5_RECOVERY_RECORDED_EVENT),
            "recovery_ticket_refs": _append_unique(cycle.recovery_ticket_refs, ticket_id),
            "status": _cycle_status_after_recovery(cycle.status, final_status),
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated, ticket


def record_phase5_projection_refreshed(
    *,
    cycle_id: str,
    projection_id: str,
    projection_name: str,
    projection_family: str,
    version: str,
    generated_at: str,
    freshness_at: str,
    source_artifact_ids: list[str] | None = None,
    row_count: int = 0,
    staleness_status: str = "fresh",
    fallback_reason: str | None = None,
    event_refs: list[str] | None = None,
    root: Path | None = None,
) -> tuple[Phase5CycleLedgerArtifact, FrontendProjectionManifestArtifact]:
    cycle = _require_cycle(cycle_id, root=root)
    manifest = FrontendProjectionManifestArtifact(
        projection_id=projection_id,
        cycle_id=cycle_id,
        projection_name=projection_name,
        projection_family=projection_family,
        version=version,
        generated_at=generated_at,
        freshness_at=freshness_at,
        source_artifact_ids=_dedupe(source_artifact_ids or []),
        row_count=row_count,
        staleness_status=staleness_status,
        fallback_reason=fallback_reason,
        event_refs=_append_unique(_dedupe(event_refs or []), PHASE5_PROJECTION_REFRESHED_EVENT),
    )
    write_frontend_projection_manifest_artifact(manifest, root=root)
    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, PHASE5_PROJECTION_REFRESHED_EVENT),
            "artifact_refs": _append_unique(cycle.artifact_refs, _frontend_projection_manifest_ref(projection_id)),
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated, manifest


def attach_publish_verification(
    *,
    cycle_id: str,
    release_manifest_path: Path,
    release_manifest_ref: str,
    event_ref: str = RUNTIME_PUBLISH_VERIFIED_EVENT,
    root: Path | None = None,
) -> Phase5CycleLedgerArtifact:
    cycle = _require_cycle(cycle_id, root=root)
    digest = _sha256_digest(Path(release_manifest_path))
    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, event_ref),
            "publish_verification_ref": PublishVerificationRef(
                release_manifest_ref=release_manifest_ref,
                digest=digest,
                event_ref=event_ref,
            ),
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated


def _require_cycle(cycle_id: str, *, root: Path | None = None) -> Phase5CycleLedgerArtifact:
    cycle = read_phase5_cycle_ledger_artifact_if_exists(cycle_id, root=root)
    if cycle is None:
        raise Phase5CycleNotFoundError(f"phase5 cycle ledger does not exist: {cycle_id}")
    return cycle


def _append_unique(values: list[str], value: str) -> list[str]:
    if value in values:
        return list(values)
    return [*values, value]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _frontend_projection_manifest_ref(projection_id: str) -> str:
    return f"frontend_projection_manifest:{projection_id}"


def _cycle_status_after_recovery(current_status: str, final_status: str) -> str:
    if final_status == "blocked":
        return "blocked"
    if final_status == "degraded" and current_status not in {"blocked", "completed"}:
        return "degraded"
    return current_status


def _sha256_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
