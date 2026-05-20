from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_action_executor import (
    Phase5SchedulerActionExecutionResult,
    Phase5SchedulerActionExecutionStatus,
    Phase5SchedulerActionRecommendedNextAction,
)
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction

Phase5SchedulerActionRouteType = Literal[
    "wait_for_next_tick",
    "terminal",
    "diagnostic_output",
    "execution_output",
]


class Phase5SchedulerActionRouteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    action: Phase5SchedulerAction
    source_status: Phase5SchedulerActionExecutionStatus
    recommended_next_action: Phase5SchedulerActionRecommendedNextAction
    route_type: Phase5SchedulerActionRouteType
    required_arguments: tuple[str, ...] = Field(default_factory=tuple)
    reason: str


_ROUTES: dict[
    Phase5SchedulerActionRecommendedNextAction,
    tuple[Phase5SchedulerActionRouteType, tuple[str, ...]],
] = {
    "continue_scheduler_tracking": ("wait_for_next_tick", ()),
    "finish_without_followup": ("terminal", ()),
    "record_scheduler_diagnostic": ("diagnostic_output", ("diagnostic_id", "observed_at")),
    "record_scheduler_execution_intent": (
        "execution_output",
        ("execution_id", "idempotency_key", "created_at"),
    ),
}


def route_phase5_scheduler_action_result(
    result: Phase5SchedulerActionExecutionResult,
) -> Phase5SchedulerActionRouteResult:
    route_type, required_arguments = _ROUTES[result.recommended_next_action]

    return Phase5SchedulerActionRouteResult(
        cycle_id=result.cycle_id,
        action=result.action,
        source_status=result.execution_status,
        recommended_next_action=result.recommended_next_action,
        route_type=route_type,
        required_arguments=required_arguments,
        reason=result.reason,
    )
