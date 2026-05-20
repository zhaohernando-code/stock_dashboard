from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path

import ashare_evidence.autonomous_flow_scheduler_action_router as action_router
from ashare_evidence.autonomous_flow_scheduler_action_executor import Phase5SchedulerActionExecutionResult
from ashare_evidence.autonomous_flow_scheduler_action_router import route_phase5_scheduler_action_result


def test_action_router_routes_continue_hint_to_wait_route() -> None:
    route = route_phase5_scheduler_action_result(_result("continue_scheduler_tracking"))

    assert route.route_type == "wait_for_next_tick"
    assert route.required_arguments == ()


def test_action_router_routes_terminal_hint_without_required_arguments() -> None:
    route = route_phase5_scheduler_action_result(
        _result("finish_without_followup", action="none", execution_status="completed")
    )

    assert route.route_type == "terminal"
    assert route.required_arguments == ()


def test_action_router_routes_diagnostic_hint_to_required_arguments() -> None:
    route = route_phase5_scheduler_action_result(
        _result("record_scheduler_diagnostic", action="open_recovery_ticket", execution_status="blocked")
    )

    assert route.route_type == "diagnostic_output"
    assert route.required_arguments == ("diagnostic_id", "observed_at")


def test_action_router_routes_execution_hint_to_required_arguments() -> None:
    route = route_phase5_scheduler_action_result(
        _result("record_scheduler_execution_intent", action="rebuild_projection", execution_status="blocked")
    )

    assert route.route_type == "execution_output"
    assert route.required_arguments == ("execution_id", "idempotency_key", "created_at")


def test_action_router_preserves_source_metadata() -> None:
    result = _result(
        "record_scheduler_execution_intent",
        cycle_id="cycle-20260521-router",
        action="retry_failed_step",
        execution_status="blocked",
        reason="executor deferred retry to an external execution writer",
    )

    route = route_phase5_scheduler_action_result(result)

    assert route.cycle_id == "cycle-20260521-router"
    assert route.action == "retry_failed_step"
    assert route.source_status == "blocked"
    assert route.recommended_next_action == "record_scheduler_execution_intent"
    assert route.reason == "executor deferred retry to an external execution writer"


def test_action_router_does_not_modify_input_object() -> None:
    result = _result("record_scheduler_diagnostic")
    before = deepcopy(result.model_dump(mode="json"))

    route_phase5_scheduler_action_result(result)

    assert result.model_dump(mode="json") == before


def test_action_router_has_no_runtime_io_clock_network_or_cli_dependencies() -> None:
    source = inspect.getsource(action_router)

    for token in (
        "datetime",
        "time.",
        "Path(",
        "open(",
        "mkdir(",
        "read_text(",
        "write_text(",
        "requests",
        "httpx",
        "sqlite",
        "subprocess",
        "ashare_evidence.cli",
    ):
        assert token not in source


def test_action_router_does_not_create_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before_files = _files_under(tmp_path)

    route_phase5_scheduler_action_result(_result("record_scheduler_execution_intent"))

    assert _files_under(tmp_path) == before_files


def _result(
    recommended_next_action,
    *,
    cycle_id: str = "cycle-20260521-001",
    action: str = "continue_tracking",
    execution_status: str = "completed",
    reason: str = "scheduler action result reason",
) -> Phase5SchedulerActionExecutionResult:
    return Phase5SchedulerActionExecutionResult(
        cycle_id=cycle_id,
        execution_status=execution_status,
        action=action,
        preflight_status="ready",
        recommended_next_action=recommended_next_action,
        reason=reason,
    )


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
