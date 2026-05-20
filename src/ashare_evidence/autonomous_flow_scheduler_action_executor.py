from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_action_contract import (
    Phase5SchedulerActionPreflightStatus,
    preflight_phase5_scheduler_action,
)
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction, Phase5SchedulerFollowupPlan

Phase5SchedulerActionExecutionStatus = Literal["completed", "blocked"]
Phase5SchedulerActionExecutionMode = Literal["contract_action"]
Phase5SchedulerActionRecommendedNextAction = Literal[
    "continue_scheduler_tracking",
    "finish_without_followup",
    "record_scheduler_diagnostic",
    "record_scheduler_execution_intent",
]

_NOOP_ACTION_EFFECTS: dict[Phase5SchedulerAction, tuple[str, ...]] = {
    "continue_tracking": ("keep_cycle_open_for_next_tick",),
    "none": ("no_op",),
}
_UNSUPPORTED_REASON = "scheduler action executor only supports no-op actions in this trial"


class Phase5SchedulerActionExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    execution_mode: Phase5SchedulerActionExecutionMode = "contract_action"
    execution_status: Phase5SchedulerActionExecutionStatus
    action: Phase5SchedulerAction
    preflight_status: Phase5SchedulerActionPreflightStatus
    recommended_next_action: Phase5SchedulerActionRecommendedNextAction
    performed_effects: tuple[str, ...] = Field(default_factory=tuple)
    skipped_reason: str | None = None
    durable_outputs: tuple[str, ...] = Field(default_factory=tuple)
    may_close_cycle: bool = False
    reason: str


def execute_phase5_scheduler_noop_action(
    plan: Phase5SchedulerFollowupPlan,
) -> Phase5SchedulerActionExecutionResult:
    preflight = preflight_phase5_scheduler_action(
        plan.action,
        provided_input_names=_provided_input_names_for_plan(),
        requested_side_effects=(),
    )
    if not preflight.ready:
        return Phase5SchedulerActionExecutionResult(
            cycle_id=plan.cycle_id,
            execution_status="blocked",
            action=plan.action,
            preflight_status=preflight.status,
            recommended_next_action="record_scheduler_diagnostic",
            skipped_reason=preflight.reason,
            durable_outputs=preflight.durable_outputs,
            may_close_cycle=preflight.may_close_cycle,
            reason=preflight.reason,
        )

    performed_effects = _NOOP_ACTION_EFFECTS.get(plan.action)
    if performed_effects is None:
        return Phase5SchedulerActionExecutionResult(
            cycle_id=plan.cycle_id,
            execution_status="blocked",
            action=plan.action,
            preflight_status=preflight.status,
            recommended_next_action="record_scheduler_execution_intent",
            skipped_reason=_UNSUPPORTED_REASON,
            durable_outputs=preflight.durable_outputs,
            may_close_cycle=preflight.may_close_cycle,
            reason=_UNSUPPORTED_REASON,
        )

    return Phase5SchedulerActionExecutionResult(
        cycle_id=plan.cycle_id,
        execution_status="completed",
        action=plan.action,
        preflight_status=preflight.status,
        recommended_next_action=_completed_next_action(plan.action),
        performed_effects=performed_effects,
        durable_outputs=preflight.durable_outputs,
        may_close_cycle=preflight.may_close_cycle,
        reason=plan.reason,
    )


def _completed_next_action(
    action: Phase5SchedulerAction,
) -> Phase5SchedulerActionRecommendedNextAction:
    if action == "none":
        return "finish_without_followup"
    return "continue_scheduler_tracking"


def _provided_input_names_for_plan() -> tuple[str, ...]:
    return (
        "cycle_id",
        "scheduler_followup_plan",
        "plan_status",
        "action",
        "reason",
        "source_tick_status",
        "summary_status",
        "claim_ceiling",
        "blocking_reasons",
    )
