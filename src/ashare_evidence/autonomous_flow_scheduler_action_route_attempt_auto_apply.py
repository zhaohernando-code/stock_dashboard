from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ashare_evidence.autonomous_flow_scheduler_action_route_auto_apply import (
    bind_and_apply_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_action_route_executor import AppliedOutput, ApplyStatus
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRoutePreflightStatus,
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
)
from ashare_evidence.autonomous_flow_scheduler_attempt import (
    Phase5SchedulerAttemptContextStatus,
    build_phase5_scheduler_attempt_context,
)
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerFollowupPlan


class Phase5SchedulerAttemptRouteApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    execution_mode: str = "attempt_route_apply"
    attempt_id: str | None
    attempt_context_status: Phase5SchedulerAttemptContextStatus
    execution_status: ApplyStatus
    preflight_status: Phase5SchedulerActionRoutePreflightStatus
    applied_output: AppliedOutput
    required_arguments: tuple[str, ...]
    missing_arguments: tuple[str, ...]
    diagnostic_id: str | None = None
    execution_id: str | None = None
    idempotency_key: str | None = None
    cycle_event_recorded: bool = False
    reason: str
    error_type: str | None = None


def build_attempt_context_and_apply_phase5_scheduler_action_route(
    plan: Phase5SchedulerFollowupPlan,
    route: Phase5SchedulerActionRouteResult,
    *,
    issued_at: str | None,
    runner_id: str | None,
    root: Path | None = None,
) -> Phase5SchedulerAttemptRouteApplyResult:
    attempt = build_phase5_scheduler_attempt_context(
        cycle_id=route.cycle_id,
        issued_at=issued_at,
        runner_id=runner_id,
    )
    if not attempt.ready:
        return Phase5SchedulerAttemptRouteApplyResult(
            cycle_id=route.cycle_id,
            route_type=route.route_type,
            attempt_id=None,
            attempt_context_status=attempt.status,
            execution_status="blocked",
            preflight_status="blocked",
            applied_output="none",
            required_arguments=attempt.required_arguments,
            missing_arguments=attempt.missing_arguments,
            reason=attempt.reason,
        )

    apply_result = bind_and_apply_phase5_scheduler_action_route(
        plan,
        route,
        attempt_id=attempt.attempt_id,
        issued_at=issued_at,
        root=root,
    )
    return Phase5SchedulerAttemptRouteApplyResult(
        cycle_id=apply_result.cycle_id,
        route_type=apply_result.route_type,
        attempt_id=attempt.attempt_id,
        attempt_context_status=attempt.status,
        execution_status=apply_result.execution_status,
        preflight_status=apply_result.preflight_status,
        applied_output=apply_result.applied_output,
        required_arguments=apply_result.required_arguments,
        missing_arguments=apply_result.missing_arguments,
        diagnostic_id=apply_result.diagnostic_id,
        execution_id=apply_result.execution_id,
        idempotency_key=apply_result.idempotency_key,
        cycle_event_recorded=apply_result.cycle_event_recorded,
        reason=apply_result.reason,
        error_type=apply_result.error_type,
    )
