from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
import ashare_evidence.cli_autonomous_flow_attempt_outputs as attempt_outputs
from ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply import (
    Phase5SchedulerAttemptRouteApplyResult,
)
from tests.helpers_cli_autonomous_flow import _args, _ok_tick_result, _plan_result
from tests.helpers_cli_autonomous_flow_attempt_route import _apply_result, _FakeResult, _result


def _attempt_record_handlers(apply_result: Phase5SchedulerAttemptRouteApplyResult) -> SimpleNamespace:
    return SimpleNamespace(
        plan_followup=lambda tick: _plan_result(cycle_id=tick.payload["cycle_id"]),
        execute_scheduler_noop_action=lambda plan: _result(cycle_id=plan.payload["cycle_id"]),
        route_scheduler_action_result=lambda action: _result(cycle_id=action.payload["cycle_id"]),
        build_attempt_context_and_apply_scheduler_action_route=lambda *_args, **_kwargs: apply_result,
    )


def _real_apply_result(*, cycle_id: str, status: str = "applied") -> Phase5SchedulerAttemptRouteApplyResult:
    blocked = status == "blocked"
    return Phase5SchedulerAttemptRouteApplyResult(
        cycle_id=cycle_id,
        route_type="execution_output",
        attempt_id=None if blocked else "attempt-bs1",
        attempt_context_status="blocked" if blocked else "ready",
        execution_status=status,
        preflight_status="blocked" if blocked else "ready",
        applied_output="none" if blocked else "execution",
        required_arguments=("cycle_id", "issued_at", "runner_id"),
        missing_arguments=("issued_at", "runner_id") if blocked else (),
        execution_id=None if blocked else "execution-bs1",
        idempotency_key=None if blocked else "cycle:cycle-record:record_execution",
        cycle_event_recorded=not blocked,
        reason="structured test result",
    )


def _run_default_attempt_route_auto_apply(monkeypatch: Any, artifact_root: Path, *, status: str) -> dict[str, Any]:
    calls: list[str] = []
    tick_calls: list[dict[str, Any]] = []
    apply_inputs: list[dict[str, Any]] = []

    def fake_tick(**kwargs: Any) -> Any:
        calls.append("tick")
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: Any) -> Any:
        calls.append("plan")
        return _plan_result(cycle_id=tick_result.payload["cycle_id"], action="retry_failed_step")

    def fake_action(plan: Any) -> _FakeResult:
        calls.append("action")
        return _result(cycle_id=plan.payload["cycle_id"], action=plan.payload["action"])

    def fake_route(action_result: _FakeResult) -> _FakeResult:
        calls.append("route")
        return _result(cycle_id=action_result.payload["cycle_id"], route_type="execution_output")

    def fake_attempt_apply(plan: Any, route: _FakeResult, **kwargs: Any) -> _FakeResult:
        calls.append("attempt-apply")
        apply_inputs.append({"plan": plan.payload, "route": route.payload, **kwargs})
        return _apply_result(cycle_id=route.payload["cycle_id"], status=status)

    def fail_unexpected(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-route-auto-apply output called an unexpected handler")

    def fail_record(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("default attempt-route-auto-apply must not record attempt run")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fake_action)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fake_route)
    monkeypatch.setattr(
        cli_autonomous_flow,
        "build_attempt_context_and_apply_phase5_scheduler_action_route",
        fake_attempt_apply,
    )
    monkeypatch.setattr(cli_autonomous_flow, "bind_and_apply_phase5_scheduler_action_route", fail_unexpected)
    monkeypatch.setattr(attempt_outputs, "record_phase5_scheduler_attempt_run_artifact", fail_record)

    result = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="attempt-route-auto-apply",
            cycle_id="cycle-attempt-apply",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            issued_at="2026-05-21T10:00:00Z",
            runner_id="runner-bm1",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
        )
    )
    return {"result": result, "calls": calls, "tick_calls": tick_calls, "apply_inputs": apply_inputs}
