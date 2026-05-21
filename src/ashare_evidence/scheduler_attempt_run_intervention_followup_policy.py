from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction
from ashare_evidence.scheduler_attempt_run_followup_policy import AttemptRunFollowupConfidence
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    Phase5SchedulerAttemptInterventionRunReadout,
)

InterventionFollowupDecisionStatus = Literal["ready", "blocked"]
InterventionFollowupReasonCode = Literal[
    "no_intervention_runs_recorded",
    "latest_intervention_applied_diagnostic",
    "latest_intervention_blocked",
    "latest_intervention_skipped",
    "latest_intervention_status_unknown",
]


class Phase5SchedulerAttemptInterventionFollowupDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_status: InterventionFollowupDecisionStatus
    recommended_action: Phase5SchedulerAction
    reason_code: InterventionFollowupReasonCode
    source_latest_intervention_run_id: str | None = None
    source_latest_diagnostic_id: str | None = None
    source_total_runs: int = Field(ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)
    confidence: AttemptRunFollowupConfidence


def decide_phase5_scheduler_attempt_intervention_followup(
    readout: Phase5SchedulerAttemptInterventionRunReadout,
) -> Phase5SchedulerAttemptInterventionFollowupDecision:
    if readout.total_runs == 0:
        return _decision(
            readout,
            recommended_action="continue_tracking",
            reason_code="no_intervention_runs_recorded",
            confidence="medium",
        )
    if readout.latest_execution_status == "applied" and readout.latest_applied_output == "diagnostic":
        return _decision(
            readout,
            recommended_action="open_recovery_ticket",
            reason_code="latest_intervention_applied_diagnostic",
            confidence="high",
        )
    if readout.latest_execution_status == "blocked":
        return _decision(
            readout,
            recommended_action="retry_failed_step",
            reason_code="latest_intervention_blocked",
            confidence="medium",
            blocking_reasons=[_blocked_reason(readout)],
        )
    if readout.latest_execution_status == "skipped":
        return _decision(
            readout,
            recommended_action="continue_tracking",
            reason_code="latest_intervention_skipped",
            confidence="medium",
        )
    return _decision(
        readout,
        decision_status="blocked",
        recommended_action="block_cycle",
        reason_code="latest_intervention_status_unknown",
        confidence="low",
        blocking_reasons=["latest intervention run status is unavailable"],
    )


def _decision(
    readout: Phase5SchedulerAttemptInterventionRunReadout,
    *,
    recommended_action: Phase5SchedulerAction,
    reason_code: InterventionFollowupReasonCode,
    confidence: AttemptRunFollowupConfidence,
    decision_status: InterventionFollowupDecisionStatus = "ready",
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerAttemptInterventionFollowupDecision:
    return Phase5SchedulerAttemptInterventionFollowupDecision(
        decision_status=decision_status,
        recommended_action=recommended_action,
        reason_code=reason_code,
        source_latest_intervention_run_id=readout.latest_intervention_run_id,
        source_latest_diagnostic_id=readout.latest_diagnostic_id,
        source_total_runs=readout.total_runs,
        blocking_reasons=blocking_reasons or [],
        confidence=confidence,
    )


def _blocked_reason(readout: Phase5SchedulerAttemptInterventionRunReadout) -> str:
    if readout.latest_intervention_run_id:
        return f"latest intervention run is blocked: {readout.latest_intervention_run_id}"
    return "latest intervention run is blocked"
