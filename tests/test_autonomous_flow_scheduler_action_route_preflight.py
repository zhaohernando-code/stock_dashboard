from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
    preflight_phase5_scheduler_action_route,
)


def test_action_route_preflight_marks_wait_and_terminal_ready_without_arguments() -> None:
    for route_type in ("wait_for_next_tick", "terminal"):
        result = preflight_phase5_scheduler_action_route(_route(route_type, ()), ())

        assert result.status == "ready"
        assert result.ready is True
        assert result.required_arguments == ()
        assert result.missing_arguments == ()
        assert result.reason


def test_action_route_preflight_blocks_missing_diagnostic_arguments() -> None:
    result = preflight_phase5_scheduler_action_route(
        _route("diagnostic_output", ("diagnostic_id", "observed_at")),
        ("diagnostic_id",),
    )

    assert result.status == "blocked"
    assert result.ready is False
    assert result.required_arguments == ("diagnostic_id", "observed_at")
    assert result.missing_arguments == ("observed_at",)
    assert result.reason == "missing required action route arguments: observed_at"


def test_action_route_preflight_blocks_missing_execution_arguments() -> None:
    result = preflight_phase5_scheduler_action_route(
        _route("execution_output", ("execution_id", "idempotency_key", "created_at")),
        ("execution_id",),
    )

    assert result.status == "blocked"
    assert result.missing_arguments == ("idempotency_key", "created_at")


def test_action_route_preflight_marks_ready_when_all_required_arguments_are_provided() -> None:
    result = preflight_phase5_scheduler_action_route(
        _route("execution_output", ("execution_id", "idempotency_key", "created_at")),
        ("created_at", "extra_argument", "execution_id", "idempotency_key"),
    )

    assert result.status == "ready"
    assert result.ready is True
    assert result.missing_arguments == ()
    assert result.reason == "all required action route arguments are provided"


def test_action_route_preflight_preserves_route_metadata() -> None:
    result = preflight_phase5_scheduler_action_route(
        _route(
            "diagnostic_output",
            ("diagnostic_id", "observed_at"),
            cycle_id="cycle-20260521-ay1",
        ),
        ("diagnostic_id", "observed_at"),
    )

    assert result.cycle_id == "cycle-20260521-ay1"
    assert result.route_type == "diagnostic_output"
    assert result.required_arguments == ("diagnostic_id", "observed_at")


def test_action_route_preflight_does_not_modify_input_object() -> None:
    route = _route("diagnostic_output", ("diagnostic_id", "observed_at"))
    before = deepcopy(route.model_dump(mode="json"))

    preflight_phase5_scheduler_action_route(route, ("diagnostic_id",))

    assert route.model_dump(mode="json") == before


def test_action_route_preflight_does_not_create_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before_files = _files_under(tmp_path)

    preflight_phase5_scheduler_action_route(
        _route("execution_output", ("execution_id", "idempotency_key", "created_at")),
        ("execution_id",),
    )

    assert _files_under(tmp_path) == before_files


def _route(
    route_type: Phase5SchedulerActionRouteType,
    required_arguments: tuple[str, ...],
    *,
    cycle_id: str = "cycle-20260521-001",
) -> Phase5SchedulerActionRouteResult:
    return Phase5SchedulerActionRouteResult(
        cycle_id=cycle_id,
        action="continue_tracking",
        source_status="blocked",
        recommended_next_action=_recommended_next_action(route_type),
        route_type=route_type,
        required_arguments=required_arguments,
        reason="route reason from executor",
    )


def _recommended_next_action(route_type: Phase5SchedulerActionRouteType) -> str:
    return {
        "wait_for_next_tick": "continue_scheduler_tracking",
        "terminal": "finish_without_followup",
        "diagnostic_output": "record_scheduler_diagnostic",
        "execution_output": "record_scheduler_execution_intent",
    }[route_type]


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
