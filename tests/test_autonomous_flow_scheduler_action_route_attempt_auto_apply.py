from __future__ import annotations

from pathlib import Path

import ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply as attempt_auto_apply
from ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply import (
    build_attempt_context_and_apply_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_action_route_executor import Phase5SchedulerActionRouteApplyResult
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
)
from ashare_evidence.autonomous_flow_scheduler_attempt import build_phase5_scheduler_attempt_context
from ashare_evidence.research_artifact_store import read_phase5_scheduler_diagnostic_artifact
from tests.helpers_autonomous_flow_scheduler import _plan
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle


def test_attempt_route_auto_apply_blocks_missing_context_before_bind_or_apply(monkeypatch, tmp_path: Path) -> None:
    def fail_bind(*args, **kwargs):
        raise AssertionError("bind/apply must not be called without scheduler attempt context")

    monkeypatch.setattr(attempt_auto_apply, "bind_and_apply_phase5_scheduler_action_route", fail_bind)

    cases = (
        (None, "runner-bl1", ("issued_at",)),
        ("2026-05-21T10:00:00Z", None, ("runner_id",)),
        (None, None, ("issued_at", "runner_id")),
    )

    for issued_at, runner_id, missing_arguments in cases:
        result = build_attempt_context_and_apply_phase5_scheduler_action_route(
            _plan(cycle_id="cycle-no-context", action="retry_failed_step"),
            _route(
                "execution_output",
                ("execution_id", "idempotency_key", "created_at"),
                cycle_id="cycle-no-context",
            ),
            issued_at=issued_at,
            runner_id=runner_id,
            root=tmp_path / "artifacts",
        )

        assert result.attempt_id is None
        assert (result.attempt_context_status, result.execution_status, result.preflight_status) == (
            "blocked",
            "blocked",
            "blocked",
        )
        assert result.applied_output == "none"
        assert result.required_arguments == ("cycle_id", "issued_at", "runner_id")
        assert result.missing_arguments == missing_arguments
        assert result.error_type is None

    assert _files_under(tmp_path) == ()


def test_attempt_route_auto_apply_passes_generated_attempt_id_to_bind(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def capture_bind(*args, **kwargs):
        calls.append(kwargs)
        return Phase5SchedulerActionRouteApplyResult(
            cycle_id="cycle-ready",
            route_type="execution_output",
            execution_status="applied",
            preflight_status="ready",
            applied_output="execution",
            required_arguments=("execution_id", "idempotency_key", "created_at"),
            missing_arguments=(),
            execution_id="execution-001",
            idempotency_key="idempotency:execution-001",
            cycle_event_recorded=True,
            reason="captured apply result",
            error_type=None,
        )

    monkeypatch.setattr(attempt_auto_apply, "bind_and_apply_phase5_scheduler_action_route", capture_bind)

    result = build_attempt_context_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-ready", action="retry_failed_step"),
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), cycle_id="cycle-ready"),
        issued_at="2026-05-21T10:00:00Z",
        runner_id="runner-bl1",
    )
    expected_attempt = build_phase5_scheduler_attempt_context(
        cycle_id="cycle-ready",
        issued_at="2026-05-21T10:00:00Z",
        runner_id="runner-bl1",
    ).attempt_id

    assert calls[0]["attempt_id"] == expected_attempt
    assert calls[0]["issued_at"] == "2026-05-21T10:00:00Z"
    assert result.attempt_id == expected_attempt
    assert result.attempt_context_status == "ready"
    assert (result.execution_status, result.applied_output) == ("applied", "execution")
    assert result.execution_id == "execution-001"
    assert result.idempotency_key == "idempotency:execution-001"
    assert result.cycle_event_recorded is True


def test_attempt_route_auto_apply_records_diagnostic_after_context_ready(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-diagnostic")

    result = build_attempt_context_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-diagnostic", action="open_recovery_ticket"),
        _route("diagnostic_output", ("diagnostic_id", "observed_at"), action="open_recovery_ticket"),
        issued_at="2026-05-21T10:00:00Z",
        runner_id="runner-bl1",
        root=root,
    )
    diagnostic = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id or "", root=root)

    assert result.attempt_id is not None
    assert (result.attempt_context_status, result.execution_status, result.preflight_status) == (
        "ready",
        "applied",
        "ready",
    )
    assert result.applied_output == "diagnostic"
    assert diagnostic.observed_at == "2026-05-21T10:00:00Z"


def _route(
    route_type: Phase5SchedulerActionRouteType,
    required_arguments: tuple[str, ...],
    *,
    cycle_id: str = "cycle-diagnostic",
    action: str = "retry_failed_step",
) -> Phase5SchedulerActionRouteResult:
    return Phase5SchedulerActionRouteResult(
        cycle_id=cycle_id,
        action=action,
        source_status="blocked",
        recommended_next_action=_recommended_next_action(route_type),
        route_type=route_type,
        required_arguments=required_arguments,
        reason="route reason from action executor",
    )


def _recommended_next_action(route_type: Phase5SchedulerActionRouteType) -> str:
    return {
        "wait_for_next_tick": "continue_scheduler_tracking",
        "terminal": "finish_without_followup",
        "diagnostic_output": "record_scheduler_diagnostic",
        "execution_output": "record_scheduler_execution_intent",
    }[route_type]


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())) if root.exists() else ()
