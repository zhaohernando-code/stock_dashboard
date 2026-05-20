from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ashare_evidence.autonomous_flow_artifacts import (
    PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT_ID,
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID,
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    Phase5SchedulerDiagnosticArtifact,
    Phase5SchedulerExecutionLedgerArtifact,
    PublishVerificationRef,
)
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact_if_exists,
    write_frontend_projection_manifest_artifact,
    write_phase5_cycle_ledger_artifact,
    write_phase5_gate_readout_artifact,
    write_phase5_recovery_ticket_artifact,
    write_phase5_scheduler_diagnostic_artifact,
)
from ashare_evidence.scheduler_execution_artifact_store import (
    create_phase5_scheduler_execution_reservation_artifact,
    find_phase5_scheduler_execution_ledger_by_idempotency_key,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
    write_phase5_scheduler_execution_ledger_artifact,
)

PHASE5_CYCLE_STARTED_EVENT = "phase5.cycle.started.v1"
PHASE5_ARTIFACT_PRODUCED_EVENT = "phase5.artifact.produced.v1"
PHASE5_GATE_EVALUATED_EVENT = "phase5.gate.evaluated.v1"
PHASE5_PROJECTION_REFRESHED_EVENT = "phase5.projection.refreshed.v1"
PHASE5_RECOVERY_RECORDED_EVENT = "phase5.recovery.recorded.v1"
PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT = PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT_ID
PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT = PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID
RUNTIME_PUBLISH_VERIFIED_EVENT = "runtime.publish.verified.v1"
PHASE5_CLOSEOUT_STATUSES = {"completed", "degraded", "blocked"}
PHASE5_NEXT_ACTIONS = {"continue_tracking", "rebuild_projection", "retry_failed_step", "redesign", "blocked", "none"}


class Phase5CycleNotFoundError(LookupError):
    """Raised when an update targets a cycle ledger that has not been created."""


class Phase5SchedulerExecutionIdempotencyConflictError(RuntimeError):
    """Raised when an idempotency key is reused for a different scheduler execution."""

    def __init__(
        self,
        *,
        idempotency_key: str,
        existing_execution_id: str,
        requested_execution_id: str,
    ) -> None:
        self.idempotency_key = idempotency_key
        self.existing_execution_id = existing_execution_id
        self.requested_execution_id = requested_execution_id
        super().__init__("phase5 scheduler execution idempotency conflict")


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


def record_phase5_scheduler_diagnostic(
    *,
    diagnostic_id: str,
    observed_at: str,
    scheduler_action: str,
    severity: str,
    failure_class: str,
    recommended_recovery_action: str,
    cycle_id: str | None = None,
    blocking_reasons: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    notes: str = "",
    root: Path | None = None,
) -> tuple[Phase5CycleLedgerArtifact | None, Phase5SchedulerDiagnosticArtifact]:
    diagnostic = Phase5SchedulerDiagnosticArtifact(
        diagnostic_id=diagnostic_id,
        cycle_id=cycle_id,
        observed_at=observed_at,
        severity=severity,
        scheduler_action=scheduler_action,
        failure_class=failure_class,
        recommended_recovery_action=recommended_recovery_action,
        blocking_reasons=_dedupe(blocking_reasons or []),
        evidence_refs=_dedupe(evidence_refs or []),
        notes=notes,
        event_refs=[PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT],
    )
    write_phase5_scheduler_diagnostic_artifact(diagnostic, root=root)

    cycle = read_phase5_cycle_ledger_artifact_if_exists(cycle_id, root=root)
    if cycle is None:
        return None, diagnostic

    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT),
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated, diagnostic


def record_phase5_scheduler_execution_ledger(
    *,
    execution_id: str,
    idempotency_key: str,
    created_at: str,
    plan_action: str,
    execution_status: str,
    would_execute: bool,
    cycle_id: str | None = None,
    diagnostic_refs: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    notes: str = "",
    root: Path | None = None,
) -> tuple[Phase5CycleLedgerArtifact | None, Phase5SchedulerExecutionLedgerArtifact]:
    existing_by_key = find_phase5_scheduler_execution_ledger_by_idempotency_key(idempotency_key, root=root)
    reservation_execution_id = existing_by_key.execution_id if existing_by_key is not None else execution_id
    reservation_cycle_id = existing_by_key.cycle_id if existing_by_key is not None else cycle_id
    reservation_created_at = existing_by_key.created_at if existing_by_key is not None else created_at
    reservation = create_phase5_scheduler_execution_reservation_artifact(
        idempotency_key=idempotency_key,
        execution_id=reservation_execution_id,
        cycle_id=reservation_cycle_id,
        created_at=reservation_created_at,
        root=root,
    )
    if existing_by_key is not None and existing_by_key.execution_id != execution_id:
        raise Phase5SchedulerExecutionIdempotencyConflictError(
            idempotency_key=idempotency_key,
            existing_execution_id=existing_by_key.execution_id,
            requested_execution_id=execution_id,
        )
    if reservation.execution_id != execution_id:
        raise Phase5SchedulerExecutionIdempotencyConflictError(
            idempotency_key=idempotency_key,
            existing_execution_id=reservation.execution_id,
            requested_execution_id=execution_id,
        )

    existing = read_phase5_scheduler_execution_ledger_artifact_if_exists(execution_id, root=root)
    if existing is not None:
        if existing.idempotency_key != idempotency_key:
            raise RuntimeError("phase5 scheduler execution ledger idempotency mismatch")
        cycle = _append_scheduler_execution_event_if_cycle_exists(existing.cycle_id, root=root)
        return cycle, existing

    ledger = Phase5SchedulerExecutionLedgerArtifact(
        execution_id=execution_id,
        idempotency_key=idempotency_key,
        cycle_id=cycle_id,
        created_at=created_at,
        plan_action=plan_action,
        execution_status=execution_status,
        would_execute=would_execute,
        diagnostic_refs=_dedupe(diagnostic_refs or []),
        blocking_reasons=_dedupe(blocking_reasons or []),
        notes=notes,
        event_refs=[PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT],
    )
    write_phase5_scheduler_execution_ledger_artifact(ledger, root=root)

    cycle = _append_scheduler_execution_event_if_cycle_exists(cycle_id, root=root)
    return cycle, ledger


def _append_scheduler_execution_event_if_cycle_exists(
    cycle_id: str | None,
    *,
    root: Path | None = None,
) -> Phase5CycleLedgerArtifact | None:
    if cycle_id is None:
        return None

    cycle = read_phase5_cycle_ledger_artifact_if_exists(cycle_id, root=root)
    if cycle is None:
        return None
    if PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT in cycle.event_refs:
        return cycle

    updated = cycle.model_copy(
        update={
            "event_refs": _append_unique(cycle.event_refs, PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT),
        }
    )
    write_phase5_cycle_ledger_artifact(updated, root=root)
    return updated


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


def finish_phase5_cycle(
    *,
    cycle_id: str,
    status: str,
    finished_at: str,
    next_action: str,
    root: Path | None = None,
) -> Phase5CycleLedgerArtifact:
    _validate_cycle_closeout(status=status, finished_at=finished_at, next_action=next_action)
    cycle = _require_cycle(cycle_id, root=root)
    updated = cycle.model_copy(
        update={
            "status": status,
            "finished_at": finished_at,
            "next_action": next_action,
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


def _validate_cycle_closeout(*, status: str, finished_at: str, next_action: str) -> None:
    if status not in PHASE5_CLOSEOUT_STATUSES:
        allowed = ", ".join(sorted(PHASE5_CLOSEOUT_STATUSES))
        raise ValueError(f"phase5 closeout status must be one of: {allowed}")
    if next_action not in PHASE5_NEXT_ACTIONS:
        allowed = ", ".join(sorted(PHASE5_NEXT_ACTIONS))
        raise ValueError(f"phase5 closeout next_action must be one of: {allowed}")
    if not finished_at:
        raise ValueError("phase5 closeout finished_at must be provided by the caller")
    if status == "blocked" and next_action != "blocked":
        raise ValueError('phase5 blocked closeout requires next_action="blocked"')
    if status == "completed" and next_action in {"blocked", "retry_failed_step"}:
        raise ValueError("phase5 completed closeout cannot use blocked or retry_failed_step next_action")
    if status == "degraded" and next_action == "none":
        raise ValueError('phase5 degraded closeout cannot use next_action="none"')


def _sha256_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
