from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.scheduler_attempt_run_intervention_followup_policy import (
    Phase5SchedulerAttemptInterventionFollowupDecision,
)
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    Phase5SchedulerAttemptInterventionRunReadout,
)

RecoveryTicketIntentStatus = Literal["ready", "blocked", "skipped"]


class Phase5SchedulerRecoveryTicketIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_status: RecoveryTicketIntentStatus
    ticket_id: str | None = None
    cycle_id: str | None = None
    failed_step: Literal["replay_schedule"] = "replay_schedule"
    failure_class: Literal["contract_violation"] = "contract_violation"
    failure_observed_at: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    recovery_action: Literal["open_followup_cycle"] = "open_followup_cycle"
    retry_count: int = Field(default=0, ge=0)
    final_status: Literal["degraded"] = "degraded"
    claim_ceiling_effect: Literal["unchanged"] = "unchanged"
    notes: str
    source_intervention_run_id: str | None = None
    source_diagnostic_id: str | None = None
    required_arguments: tuple[str, ...] = Field(default_factory=tuple)
    missing_arguments: tuple[str, ...] = Field(default_factory=tuple)
    blocking_reasons: list[str] = Field(default_factory=list)


def build_phase5_scheduler_recovery_ticket_intent(
    readout: Phase5SchedulerAttemptInterventionRunReadout,
    decision: Phase5SchedulerAttemptInterventionFollowupDecision,
) -> Phase5SchedulerRecoveryTicketIntent:
    if decision.recommended_action != "open_recovery_ticket":
        return _intent(
            readout,
            decision,
            intent_status="skipped",
            notes=f"intervention follow-up decision {decision.reason_code} does not require recovery ticket",
        )

    required_arguments = ("cycle_id", "diagnostic_id", "failure_observed_at")
    missing_arguments = _missing_arguments(readout, required_arguments)
    if missing_arguments:
        return _intent(
            readout,
            decision,
            intent_status="blocked",
            required_arguments=required_arguments,
            missing_arguments=missing_arguments,
            blocking_reasons=[f"missing required recovery ticket argument: {argument}" for argument in missing_arguments],
            notes="recovery ticket intent is blocked by missing intervention context",
        )

    return _intent(
        readout,
        decision,
        intent_status="ready",
        ticket_id=_stable_ticket_id(readout),
        required_arguments=required_arguments,
        notes="scheduler recovery ticket intent built from intervention diagnostic",
    )


def _intent(
    readout: Phase5SchedulerAttemptInterventionRunReadout,
    decision: Phase5SchedulerAttemptInterventionFollowupDecision,
    *,
    intent_status: RecoveryTicketIntentStatus,
    notes: str,
    ticket_id: str | None = None,
    required_arguments: tuple[str, ...] = (),
    missing_arguments: tuple[str, ...] = (),
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerRecoveryTicketIntent:
    evidence_refs = []
    if readout.latest_diagnostic_id:
        evidence_refs.append(f"phase5_scheduler_diagnostic:{readout.latest_diagnostic_id}")
    if readout.latest_intervention_run_id:
        evidence_refs.append(f"phase5_scheduler_attempt_intervention_run:{readout.latest_intervention_run_id}")
    if decision.source_latest_intervention_run_id and decision.source_latest_intervention_run_id != readout.latest_intervention_run_id:
        evidence_refs.append(f"phase5_scheduler_attempt_intervention_run:{decision.source_latest_intervention_run_id}")

    return Phase5SchedulerRecoveryTicketIntent(
        intent_status=intent_status,
        ticket_id=ticket_id,
        cycle_id=readout.cycle_id,
        failure_observed_at=readout.latest_issued_at,
        evidence_refs=_dedupe(evidence_refs),
        notes=notes,
        source_intervention_run_id=readout.latest_intervention_run_id,
        source_diagnostic_id=readout.latest_diagnostic_id,
        required_arguments=required_arguments,
        missing_arguments=missing_arguments,
        blocking_reasons=blocking_reasons or [],
    )


def _missing_arguments(
    readout: Phase5SchedulerAttemptInterventionRunReadout,
    required_arguments: tuple[str, ...],
) -> tuple[str, ...]:
    values = {
        "cycle_id": readout.cycle_id,
        "diagnostic_id": readout.latest_diagnostic_id,
        "failure_observed_at": readout.latest_issued_at,
    }
    return tuple(argument for argument in required_arguments if not values.get(argument))


def _stable_ticket_id(readout: Phase5SchedulerAttemptInterventionRunReadout) -> str:
    raw = "|".join(
        (
            readout.cycle_id or "",
            readout.latest_intervention_run_id or "",
            readout.latest_diagnostic_id or "",
            readout.latest_issued_at or "",
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(("recovery-ticket", _slug(readout.cycle_id or "no-cycle"), digest))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
