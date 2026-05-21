from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket
from ashare_evidence.autonomous_flow_artifacts import Phase5CycleLedgerArtifact, Phase5RecoveryTicketArtifact
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact_if_exists,
    read_phase5_recovery_ticket_artifact_if_exists,
)
from ashare_evidence.scheduler_attempt_run_recovery_ticket_intent import (
    Phase5SchedulerRecoveryTicketIntent,
)

RecoveryTicketApplyStatus = Literal["recorded", "already_recorded", "blocked", "skipped"]


class Phase5SchedulerRecoveryTicketApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    apply_status: RecoveryTicketApplyStatus
    ticket_id: str | None = None
    cycle_id: str | None = None
    recovery_ticket_artifact: Phase5RecoveryTicketArtifact | None = None
    cycle_status: str | None = None
    cycle_recovery_ticket_refs: list[str] = Field(default_factory=list)
    source_intent_status: str
    source_evidence_refs: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: str


def apply_phase5_scheduler_recovery_ticket_intent(
    intent: Phase5SchedulerRecoveryTicketIntent,
    *,
    root: Path | None = None,
) -> Phase5SchedulerRecoveryTicketApplyResult:
    if intent.intent_status == "skipped":
        return _result(intent, apply_status="skipped", notes="recovery ticket intent skipped")
    if intent.intent_status == "blocked":
        return _result(
            intent,
            apply_status="blocked",
            blocking_reasons=intent.blocking_reasons or ["recovery ticket intent is blocked"],
            notes="recovery ticket intent blocked apply",
        )

    missing = _missing_ready_fields(intent)
    if missing:
        return _result(
            intent,
            apply_status="blocked",
            blocking_reasons=[f"missing required recovery ticket field: {field}" for field in missing],
            notes="ready recovery ticket intent is incomplete",
        )

    cycle = read_phase5_cycle_ledger_artifact_if_exists(intent.cycle_id, root=root)
    if cycle is None:
        return _result(
            intent,
            apply_status="blocked",
            blocking_reasons=[f"cycle ledger not found: {intent.cycle_id}"],
            notes="recovery ticket apply requires an existing cycle ledger",
        )

    expected = _ticket_from_intent(intent)
    existing = read_phase5_recovery_ticket_artifact_if_exists(intent.ticket_id, root=root)
    if existing is not None and _ticket_payload(existing) != _ticket_payload(expected):
        return _result(
            intent,
            apply_status="blocked",
            recovery_ticket_artifact=existing,
            cycle=cycle,
            blocking_reasons=[f"existing recovery ticket conflicts with intent: {intent.ticket_id}"],
            notes="recovery ticket apply blocked by idempotency conflict",
        )

    if existing is not None and intent.ticket_id in cycle.recovery_ticket_refs:
        return _result(
            intent,
            apply_status="already_recorded",
            recovery_ticket_artifact=existing,
            cycle=cycle,
            notes="recovery ticket already recorded for cycle",
        )

    updated_cycle, ticket = record_phase5_recovery_ticket(
        cycle_id=intent.cycle_id,
        ticket_id=intent.ticket_id,
        failed_step=intent.failed_step,
        failure_class=intent.failure_class,
        failure_observed_at=intent.failure_observed_at,
        evidence_refs=intent.evidence_refs,
        recovery_action=intent.recovery_action,
        retry_count=intent.retry_count,
        final_status=intent.final_status,
        claim_ceiling_effect=intent.claim_ceiling_effect,
        notes=intent.notes,
        root=root,
    )
    return _result(
        intent,
        apply_status="recorded",
        recovery_ticket_artifact=ticket,
        cycle=updated_cycle,
        notes="recovery ticket recorded from scheduler intent",
    )


def _result(
    intent: Phase5SchedulerRecoveryTicketIntent,
    *,
    apply_status: RecoveryTicketApplyStatus,
    notes: str,
    recovery_ticket_artifact: Phase5RecoveryTicketArtifact | None = None,
    cycle: Phase5CycleLedgerArtifact | None = None,
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerRecoveryTicketApplyResult:
    return Phase5SchedulerRecoveryTicketApplyResult(
        apply_status=apply_status,
        ticket_id=intent.ticket_id,
        cycle_id=intent.cycle_id,
        recovery_ticket_artifact=recovery_ticket_artifact,
        cycle_status=cycle.status if cycle else None,
        cycle_recovery_ticket_refs=cycle.recovery_ticket_refs if cycle else [],
        source_intent_status=intent.intent_status,
        source_evidence_refs=intent.evidence_refs,
        blocking_reasons=blocking_reasons or [],
        notes=notes,
    )


def _missing_ready_fields(intent: Phase5SchedulerRecoveryTicketIntent) -> list[str]:
    fields = {
        "ticket_id": intent.ticket_id,
        "cycle_id": intent.cycle_id,
        "failure_observed_at": intent.failure_observed_at,
    }
    return [field for field, value in fields.items() if not value]


def _ticket_from_intent(intent: Phase5SchedulerRecoveryTicketIntent) -> Phase5RecoveryTicketArtifact:
    return Phase5RecoveryTicketArtifact(
        ticket_id=intent.ticket_id or "",
        cycle_id=intent.cycle_id or "",
        failed_step=intent.failed_step,
        failure_class=intent.failure_class,
        failure_observed_at=intent.failure_observed_at or "",
        evidence_refs=intent.evidence_refs,
        recovery_action=intent.recovery_action,
        retry_count=intent.retry_count,
        final_status=intent.final_status,
        claim_ceiling_effect=intent.claim_ceiling_effect,
        notes=intent.notes,
    )


def _ticket_payload(ticket: Phase5RecoveryTicketArtifact) -> dict[str, object]:
    return ticket.model_dump(mode="json", exclude={"artifact_family", "schema_version"})
