from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_artifacts import Phase5CycleLedgerArtifact, Phase5RecoveryTicketArtifact
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact_if_exists,
    read_phase5_recovery_ticket_artifact_if_exists,
)

RecoveryFollowupIntentStatus = Literal["ready", "blocked", "skipped"]
RecoveryFollowupNextAction = Literal["open_followup_cycle", "continue_tracking", "block_cycle"]


class Phase5SchedulerRecoveryFollowupIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_status: RecoveryFollowupIntentStatus
    cycle_id: str | None = None
    ticket_id: str | None = None
    recovery_action: str | None = None
    next_action: RecoveryFollowupNextAction
    followup_cycle_id: str | None = None
    followup_trigger: Literal["recovery_followup"] | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    source_ticket_ref: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: str


def read_phase5_scheduler_recovery_followup_intent(
    *,
    cycle_id: str,
    root: Path | None = None,
) -> Phase5SchedulerRecoveryFollowupIntent:
    cycle = read_phase5_cycle_ledger_artifact_if_exists(cycle_id, root=root)
    if cycle is None:
        return Phase5SchedulerRecoveryFollowupIntent(
            intent_status="blocked",
            cycle_id=cycle_id,
            next_action="block_cycle",
            blocking_reasons=[f"cycle ledger not found: {cycle_id}"],
            notes="recovery follow-up intent requires an existing cycle ledger",
        )
    return build_phase5_scheduler_recovery_followup_intent(
        cycle,
        _latest_recovery_ticket(cycle, root=root),
    )


def build_phase5_scheduler_recovery_followup_intent(
    cycle: Phase5CycleLedgerArtifact,
    ticket: Phase5RecoveryTicketArtifact | None,
) -> Phase5SchedulerRecoveryFollowupIntent:
    latest_ref = cycle.recovery_ticket_refs[-1] if cycle.recovery_ticket_refs else None
    if latest_ref is None:
        return Phase5SchedulerRecoveryFollowupIntent(
            intent_status="skipped",
            cycle_id=cycle.cycle_id,
            next_action="continue_tracking",
            notes="cycle has no recovery ticket refs",
        )
    if ticket is None:
        return Phase5SchedulerRecoveryFollowupIntent(
            intent_status="blocked",
            cycle_id=cycle.cycle_id,
            ticket_id=latest_ref,
            next_action="block_cycle",
            source_ticket_ref=f"phase5_recovery_ticket:{latest_ref}",
            blocking_reasons=[f"recovery ticket artifact not found: {latest_ref}"],
            notes="latest recovery ticket ref cannot be resolved",
        )
    if ticket.recovery_action != "open_followup_cycle":
        return Phase5SchedulerRecoveryFollowupIntent(
            intent_status="skipped",
            cycle_id=cycle.cycle_id,
            ticket_id=ticket.ticket_id,
            recovery_action=ticket.recovery_action,
            next_action="continue_tracking",
            evidence_refs=_evidence_refs(ticket),
            source_ticket_ref=f"phase5_recovery_ticket:{ticket.ticket_id}",
            notes=f"recovery action {ticket.recovery_action} does not require follow-up cycle",
        )
    return Phase5SchedulerRecoveryFollowupIntent(
        intent_status="ready",
        cycle_id=cycle.cycle_id,
        ticket_id=ticket.ticket_id,
        recovery_action=ticket.recovery_action,
        next_action="open_followup_cycle",
        followup_cycle_id=_followup_cycle_id(cycle, ticket),
        followup_trigger="recovery_followup",
        evidence_refs=_evidence_refs(ticket),
        source_ticket_ref=f"phase5_recovery_ticket:{ticket.ticket_id}",
        notes="recovery ticket requests a follow-up cycle",
    )


def _latest_recovery_ticket(
    cycle: Phase5CycleLedgerArtifact,
    *,
    root: Path | None = None,
) -> Phase5RecoveryTicketArtifact | None:
    if not cycle.recovery_ticket_refs:
        return None
    return read_phase5_recovery_ticket_artifact_if_exists(cycle.recovery_ticket_refs[-1], root=root)


def _followup_cycle_id(cycle: Phase5CycleLedgerArtifact, ticket: Phase5RecoveryTicketArtifact) -> str:
    raw = "|".join((cycle.cycle_id, ticket.ticket_id, ticket.failure_observed_at))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(("recovery-followup", _slug(cycle.cycle_id), digest))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"


def _evidence_refs(ticket: Phase5RecoveryTicketArtifact) -> list[str]:
    refs = [f"phase5_recovery_ticket:{ticket.ticket_id}", *ticket.evidence_refs]
    result: list[str] = []
    for ref in refs:
        if ref not in result:
            result.append(ref)
    return result
