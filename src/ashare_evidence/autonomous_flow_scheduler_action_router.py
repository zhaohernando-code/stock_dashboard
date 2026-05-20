from __future__ import annotations

from collections.abc import Iterable
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
Phase5SchedulerActionRoutePreflightStatus = Literal["ready", "blocked"]


class Phase5SchedulerActionRouteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    action: Phase5SchedulerAction
    source_status: Phase5SchedulerActionExecutionStatus
    recommended_next_action: Phase5SchedulerActionRecommendedNextAction
    route_type: Phase5SchedulerActionRouteType
    required_arguments: tuple[str, ...] = Field(default_factory=tuple)
    reason: str


class Phase5SchedulerActionRoutePreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    status: Phase5SchedulerActionRoutePreflightStatus
    required_arguments: tuple[str, ...]
    missing_arguments: tuple[str, ...]
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "ready"


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


def preflight_phase5_scheduler_action_route(
    route: Phase5SchedulerActionRouteResult,
    provided_argument_names: Iterable[str],
) -> Phase5SchedulerActionRoutePreflightResult:
    required_arguments = route.required_arguments
    provided_arguments = set(provided_argument_names)
    missing_arguments = tuple(argument for argument in required_arguments if argument not in provided_arguments)
    status: Phase5SchedulerActionRoutePreflightStatus = "blocked" if missing_arguments else "ready"

    return Phase5SchedulerActionRoutePreflightResult(
        cycle_id=route.cycle_id,
        route_type=route.route_type,
        status=status,
        required_arguments=required_arguments,
        missing_arguments=missing_arguments,
        reason=_route_preflight_reason(
            route_type=route.route_type,
            required_arguments=required_arguments,
            missing_arguments=missing_arguments,
        ),
    )


def _route_preflight_reason(
    *,
    route_type: Phase5SchedulerActionRouteType,
    required_arguments: tuple[str, ...],
    missing_arguments: tuple[str, ...],
) -> str:
    if not required_arguments:
        return f"{route_type} route does not require scheduler-provided arguments"
    if missing_arguments:
        return "missing required action route arguments: " + ", ".join(missing_arguments)
    return "all required action route arguments are provided"
