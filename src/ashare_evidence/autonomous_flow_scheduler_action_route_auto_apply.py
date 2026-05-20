from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow_scheduler_action_route_arguments import (
    bind_phase5_scheduler_action_route_arguments,
)
from ashare_evidence.autonomous_flow_scheduler_action_route_executor import (
    Phase5SchedulerActionRouteApplyResult,
    apply_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_action_router import Phase5SchedulerActionRouteResult
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerFollowupPlan


def bind_and_apply_phase5_scheduler_action_route(
    plan: Phase5SchedulerFollowupPlan,
    route: Phase5SchedulerActionRouteResult,
    *,
    attempt_id: str | None,
    issued_at: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerActionRouteApplyResult:
    if not attempt_id:
        return Phase5SchedulerActionRouteApplyResult(
            cycle_id=route.cycle_id,
            route_type=route.route_type,
            execution_status="blocked",
            preflight_status="blocked",
            applied_output="none",
            required_arguments=("attempt_id",),
            missing_arguments=("attempt_id",),
            reason="attempt_id is required to bind scheduler action route arguments",
        )

    binding = bind_phase5_scheduler_action_route_arguments(
        route,
        attempt_id=attempt_id,
        issued_at=issued_at,
    )
    if not binding.ready:
        return Phase5SchedulerActionRouteApplyResult(
            cycle_id=route.cycle_id,
            route_type=route.route_type,
            execution_status="blocked",
            preflight_status="blocked",
            applied_output="none",
            required_arguments=binding.required_arguments,
            missing_arguments=binding.missing_arguments,
            reason=binding.reason,
        )

    arguments = binding.provided_arguments
    return apply_phase5_scheduler_action_route(
        plan,
        route,
        diagnostic_id=arguments.get("diagnostic_id"),
        observed_at=arguments.get("observed_at"),
        execution_id=arguments.get("execution_id"),
        idempotency_key=arguments.get("idempotency_key"),
        created_at=arguments.get("created_at"),
        diagnostic_refs=(),
        root=root,
    )
