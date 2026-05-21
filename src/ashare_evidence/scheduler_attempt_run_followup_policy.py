from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction
from ashare_evidence.scheduler_attempt_run_readout import Phase5SchedulerAttemptRunReadout

AttemptRunFollowupDecisionStatus = Literal["ready", "blocked"]
AttemptRunFollowupReasonCode = Literal[
    "no_attempt_runs_recorded",
    "latest_attempt_blocked",
    "latest_attempt_applied",
    "latest_attempt_skipped",
    "latest_attempt_status_unknown",
]
AttemptRunFollowupConfidence = Literal["high", "medium", "low"]


class Phase5SchedulerAttemptRunFollowupDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_status: AttemptRunFollowupDecisionStatus
    recommended_action: Phase5SchedulerAction
    reason_code: AttemptRunFollowupReasonCode
    source_latest_run_id: str | None = None
    source_total_runs: int = Field(ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)
    confidence: AttemptRunFollowupConfidence


def decide_phase5_scheduler_attempt_run_followup(
    readout: Phase5SchedulerAttemptRunReadout,
) -> Phase5SchedulerAttemptRunFollowupDecision:
    if readout.total_runs == 0:
        return _decision(
            recommended_action="continue_tracking",
            reason_code="no_attempt_runs_recorded",
            readout=readout,
            confidence="medium",
        )
    if readout.latest_apply_status == "blocked" or readout.latest_attempt_status == "blocked":
        return _decision(
            recommended_action="open_recovery_ticket",
            reason_code="latest_attempt_blocked",
            readout=readout,
            confidence="high",
            blocking_reasons=[_blocked_reason(readout)],
        )
    if readout.latest_apply_status == "applied":
        return _decision(
            recommended_action="continue_tracking",
            reason_code="latest_attempt_applied",
            readout=readout,
            confidence="high",
        )
    if readout.latest_apply_status == "skipped":
        return _decision(
            recommended_action="continue_tracking",
            reason_code="latest_attempt_skipped",
            readout=readout,
            confidence="medium",
        )
    return _decision(
        decision_status="blocked",
        recommended_action="block_cycle",
        reason_code="latest_attempt_status_unknown",
        readout=readout,
        confidence="low",
        blocking_reasons=["latest attempt run status is unavailable"],
    )


def _decision(
    *,
    recommended_action: Phase5SchedulerAction,
    reason_code: AttemptRunFollowupReasonCode,
    readout: Phase5SchedulerAttemptRunReadout,
    confidence: AttemptRunFollowupConfidence,
    decision_status: AttemptRunFollowupDecisionStatus = "ready",
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerAttemptRunFollowupDecision:
    return Phase5SchedulerAttemptRunFollowupDecision(
        decision_status=decision_status,
        recommended_action=recommended_action,
        reason_code=reason_code,
        source_latest_run_id=readout.latest_run_id,
        source_total_runs=readout.total_runs,
        blocking_reasons=blocking_reasons or [],
        confidence=confidence,
    )


def _blocked_reason(readout: Phase5SchedulerAttemptRunReadout) -> str:
    if readout.latest_run_id:
        return f"latest attempt run is blocked: {readout.latest_run_id}"
    return "latest attempt run is blocked"
