from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ashare_evidence.autonomous_flow import Phase5SchedulerExecutionIdempotencyConflictError
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRoutePreflightStatus,
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
    preflight_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_execution_executor import record_phase5_scheduler_plan_execution
from ashare_evidence.autonomous_flow_scheduler_executor import record_phase5_scheduler_plan_diagnostic
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerFollowupPlan

ApplyStatus = Literal["applied", "blocked", "skipped"]
AppliedOutput = Literal["none", "diagnostic", "execution"]


class Phase5SchedulerActionRouteApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    execution_mode: Literal["route_apply"] = "route_apply"
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


def apply_phase5_scheduler_action_route(
    plan: Phase5SchedulerFollowupPlan,
    route: Phase5SchedulerActionRouteResult,
    *,
    diagnostic_id: str | None = None,
    observed_at: str | None = None,
    execution_id: str | None = None,
    idempotency_key: str | None = None,
    created_at: str | None = None,
    diagnostic_refs: Iterable[str] | None = None,
    root: Path | None = None,
) -> Phase5SchedulerActionRouteApplyResult:
    preflight = preflight_phase5_scheduler_action_route(
        route,
        _provided(
            diagnostic_id=diagnostic_id,
            observed_at=observed_at,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            created_at=created_at,
        ),
    )
    if not preflight.ready:
        return _result(route, preflight.status, "blocked", preflight.reason, missing=preflight.missing_arguments)

    mismatch = _mismatch_reason(plan, route)
    if mismatch:
        return _result(route, preflight.status, "blocked", mismatch)
    if route.route_type in {"wait_for_next_tick", "terminal"}:
        return _result(route, preflight.status, "skipped", route.reason)

    if route.route_type == "diagnostic_output":
        diagnostic = record_phase5_scheduler_plan_diagnostic(
            plan,
            diagnostic_id=diagnostic_id,
            observed_at=observed_at,
            root=root,
        )
        return _result(route, preflight.status, "applied", diagnostic.reason, "diagnostic",
                       diagnostic_id=diagnostic.diagnostic_id, cycle_event_recorded=diagnostic.cycle_event_recorded)

    try:
        execution = record_phase5_scheduler_plan_execution(
            plan,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            created_at=created_at,
            diagnostic_refs=list(diagnostic_refs or []),
            root=root,
        )
    except Phase5SchedulerExecutionIdempotencyConflictError as exc:
        return _result(
            route,
            preflight.status,
            "blocked",
            str(exc),
            execution_id=exc.requested_execution_id,
            idempotency_key=exc.idempotency_key,
            error_type=type(exc).__name__,
        )
    return _result(route, preflight.status, "applied", execution.reason, "execution",
                   execution_id=execution.execution_id, idempotency_key=execution.idempotency_key,
                   cycle_event_recorded=execution.cycle_event_recorded)


def _provided(**values: str | None) -> tuple[str, ...]:
    return tuple(name for name, value in values.items() if value)


def _mismatch_reason(plan: Phase5SchedulerFollowupPlan, route: Phase5SchedulerActionRouteResult) -> str | None:
    if plan.cycle_id != route.cycle_id:
        return f"plan/route cycle_id mismatch: plan={plan.cycle_id} route={route.cycle_id}"
    if plan.action != route.action:
        return f"plan/route action mismatch: plan={plan.action} route={route.action}"
    return None


def _result(
    route: Phase5SchedulerActionRouteResult,
    preflight_status: Phase5SchedulerActionRoutePreflightStatus,
    status: ApplyStatus,
    reason: str,
    output: AppliedOutput = "none",
    *,
    missing: tuple[str, ...] = (),
    diagnostic_id: str | None = None,
    execution_id: str | None = None,
    idempotency_key: str | None = None,
    cycle_event_recorded: bool = False,
    error_type: str | None = None,
) -> Phase5SchedulerActionRouteApplyResult:
    return Phase5SchedulerActionRouteApplyResult(
        cycle_id=route.cycle_id,
        route_type=route.route_type,
        execution_status=status,
        preflight_status=preflight_status,
        applied_output=output,
        required_arguments=route.required_arguments,
        missing_arguments=missing,
        diagnostic_id=diagnostic_id,
        execution_id=execution_id,
        idempotency_key=idempotency_key,
        cycle_event_recorded=cycle_event_recorded,
        reason=reason,
        error_type=error_type,
    )
