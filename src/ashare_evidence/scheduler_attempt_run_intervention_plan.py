from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction
from ashare_evidence.scheduler_attempt_run_followup_policy import (
    AttemptRunFollowupConfidence,
    AttemptRunFollowupReasonCode,
    Phase5SchedulerAttemptRunFollowupDecision,
)
from ashare_evidence.scheduler_attempt_run_readout import Phase5SchedulerAttemptRunReadout

AttemptRunInterventionPlanStatus = Literal["ready", "blocked"]
AttemptRunInterventionNextStep = Literal[
    "wait_for_next_tick",
    "record_recovery_diagnostic",
    "block_cycle",
]
AttemptRunPlannedSideEffect = Literal["none", "scheduler_diagnostic", "cycle_block"]
AttemptRunExecutionBoundary = Literal["observe_only", "route_apply_required", "blocked"]


class Phase5SchedulerAttemptRunInterventionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str | None = None
    runner_id: str | None = None
    plan_status: AttemptRunInterventionPlanStatus
    action: Phase5SchedulerAction
    next_step: AttemptRunInterventionNextStep
    execution_boundary: AttemptRunExecutionBoundary
    planned_side_effect: AttemptRunPlannedSideEffect
    reason_code: AttemptRunFollowupReasonCode
    source_latest_run_id: str | None = None
    source_latest_issued_at: str | None = None
    source_total_runs: int = Field(ge=0)
    required_arguments: tuple[str, ...] = Field(default_factory=tuple)
    missing_arguments: tuple[str, ...] = Field(default_factory=tuple)
    blocking_reasons: list[str] = Field(default_factory=list)
    confidence: AttemptRunFollowupConfidence
    reason: str


def plan_phase5_scheduler_attempt_run_intervention(
    readout: Phase5SchedulerAttemptRunReadout,
    decision: Phase5SchedulerAttemptRunFollowupDecision,
) -> Phase5SchedulerAttemptRunInterventionPlan:
    if decision.decision_status == "blocked" or decision.recommended_action == "block_cycle":
        return _plan(
            readout=readout,
            decision=decision,
            plan_status="blocked",
            next_step="block_cycle",
            execution_boundary="blocked",
            planned_side_effect="cycle_block",
            required_arguments=("cycle_id",),
        )

    if decision.recommended_action == "open_recovery_ticket":
        return _plan(
            readout=readout,
            decision=decision,
            plan_status="ready",
            next_step="record_recovery_diagnostic",
            execution_boundary="route_apply_required",
            planned_side_effect="scheduler_diagnostic",
            required_arguments=("cycle_id", "diagnostic_id", "observed_at"),
        )

    return _plan(
        readout=readout,
        decision=decision,
        plan_status="ready",
        next_step="wait_for_next_tick",
        execution_boundary="observe_only",
        planned_side_effect="none",
    )


def _plan(
    *,
    readout: Phase5SchedulerAttemptRunReadout,
    decision: Phase5SchedulerAttemptRunFollowupDecision,
    plan_status: AttemptRunInterventionPlanStatus,
    next_step: AttemptRunInterventionNextStep,
    execution_boundary: AttemptRunExecutionBoundary,
    planned_side_effect: AttemptRunPlannedSideEffect,
    required_arguments: tuple[str, ...] = (),
) -> Phase5SchedulerAttemptRunInterventionPlan:
    missing_arguments = _missing_arguments(readout, required_arguments)
    effective_status: AttemptRunInterventionPlanStatus = "blocked" if missing_arguments else plan_status
    effective_boundary: AttemptRunExecutionBoundary = "blocked" if missing_arguments else execution_boundary
    blocking_reasons = list(decision.blocking_reasons)
    blocking_reasons.extend(f"missing required intervention argument: {argument}" for argument in missing_arguments)

    return Phase5SchedulerAttemptRunInterventionPlan(
        cycle_id=readout.cycle_id,
        runner_id=readout.runner_id,
        plan_status=effective_status,
        action=decision.recommended_action,
        next_step=next_step,
        execution_boundary=effective_boundary,
        planned_side_effect=planned_side_effect,
        reason_code=decision.reason_code,
        source_latest_run_id=decision.source_latest_run_id,
        source_latest_issued_at=readout.latest_issued_at,
        source_total_runs=decision.source_total_runs,
        required_arguments=required_arguments,
        missing_arguments=missing_arguments,
        blocking_reasons=blocking_reasons,
        confidence=decision.confidence,
        reason=f"attempt run decision {decision.reason_code} maps to {next_step}",
    )


def _missing_arguments(
    readout: Phase5SchedulerAttemptRunReadout,
    required_arguments: tuple[str, ...],
) -> tuple[str, ...]:
    available = {
        "cycle_id": readout.cycle_id,
    }
    plan_blocking_arguments = available.keys()
    return tuple(
        argument
        for argument in required_arguments
        if argument in plan_blocking_arguments and not available.get(argument)
    )
