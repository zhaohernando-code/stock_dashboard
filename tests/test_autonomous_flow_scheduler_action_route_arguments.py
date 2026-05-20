from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from ashare_evidence.autonomous_flow_scheduler_action_route_arguments import (
    bind_phase5_scheduler_action_route_arguments,
)
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
)


def test_route_argument_binding_marks_wait_and_terminal_ready_without_arguments() -> None:
    for route_type in ("wait_for_next_tick", "terminal"):
        result = bind_phase5_scheduler_action_route_arguments(
            _route(route_type, ()),
            attempt_id="attempt-001",
        )

        assert result.status == "ready"
        assert result.ready is True
        assert result.required_arguments == ()
        assert result.provided_arguments == {}
        assert result.missing_arguments == ()


def test_route_argument_binding_generates_diagnostic_arguments() -> None:
    result = bind_phase5_scheduler_action_route_arguments(
        _route("diagnostic_output", ("diagnostic_id", "observed_at")),
        attempt_id="attempt-001",
        issued_at="2026-05-21T10:00:00Z",
    )

    assert result.status == "ready"
    assert result.provided_arguments["observed_at"] == "2026-05-21T10:00:00Z"
    diagnostic_id = result.provided_arguments["diagnostic_id"]
    assert diagnostic_id.startswith("diagnostic-cycle-20260521-001-continue_tracking-attempt-001-")
    assert _filename_safe(diagnostic_id)


def test_route_argument_binding_generates_execution_arguments() -> None:
    result = bind_phase5_scheduler_action_route_arguments(
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), action="retry_failed_step"),
        attempt_id="attempt-002",
        issued_at="2026-05-21T10:00:00Z",
    )

    execution_id = result.provided_arguments["execution_id"]
    assert result.status == "ready"
    assert result.provided_arguments == {
        "execution_id": execution_id,
        "idempotency_key": f"idempotency:{execution_id}",
        "created_at": "2026-05-21T10:00:00Z",
    }
    assert execution_id.startswith("execution-cycle-20260521-001-retry_failed_step-attempt-002-")
    assert _filename_safe(execution_id)


def test_route_argument_binding_blocks_timestamped_routes_without_issued_at() -> None:
    for route_type, required_arguments in (
        ("diagnostic_output", ("diagnostic_id", "observed_at")),
        ("execution_output", ("execution_id", "idempotency_key", "created_at")),
    ):
        for issued_at in (None, ""):
            result = bind_phase5_scheduler_action_route_arguments(
                _route(route_type, required_arguments),
                attempt_id="attempt-003",
                issued_at=issued_at,
            )

            assert result.status == "blocked"
            assert result.ready is False
            assert result.provided_arguments == {}
            assert result.missing_arguments == required_arguments


def test_route_argument_binding_is_stable_and_traceable_with_unsafe_input() -> None:
    route = _route(
        "execution_output",
        ("execution_id", "idempotency_key", "created_at"),
        cycle_id="cycle/2026 05:21",
        action="retry_failed_step",
    )

    first = bind_phase5_scheduler_action_route_arguments(route, attempt_id="attempt:04/retry", issued_at="t1")
    second = bind_phase5_scheduler_action_route_arguments(route, attempt_id="attempt:04/retry", issued_at="t2")
    execution_id = first.provided_arguments["execution_id"]

    assert execution_id == second.provided_arguments["execution_id"]
    assert "cycle-2026-05-21" in execution_id
    assert "retry_failed_step" in execution_id
    assert "attempt-04-retry" in execution_id
    assert _filename_safe(execution_id)


def test_route_argument_binding_does_not_modify_input_or_create_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    route = _route("diagnostic_output", ("diagnostic_id", "observed_at"))
    before = deepcopy(route.model_dump(mode="json"))

    bind_phase5_scheduler_action_route_arguments(route, attempt_id="attempt-005", issued_at="now")

    assert route.model_dump(mode="json") == before
    assert _files_under(tmp_path) == ()


def _route(
    route_type: Phase5SchedulerActionRouteType,
    required_arguments: tuple[str, ...],
    *,
    cycle_id: str = "cycle-20260521-001",
    action: str = "continue_tracking",
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


def _filename_safe(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
