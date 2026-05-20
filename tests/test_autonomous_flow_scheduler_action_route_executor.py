from __future__ import annotations

import json
from pathlib import Path

import ashare_evidence.autonomous_flow_scheduler_action_route_executor as route_executor
from ashare_evidence.autonomous_flow_scheduler_action_route_executor import apply_phase5_scheduler_action_route
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
)
from ashare_evidence.research_artifact_store import read_phase5_scheduler_diagnostic_artifact
from ashare_evidence.scheduler_execution_artifact_store import (
    create_phase5_scheduler_execution_reservation_artifact,
    read_phase5_scheduler_execution_ledger_artifact,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
)
from tests.helpers_autonomous_flow_scheduler import _plan
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle


def test_route_apply_blocks_missing_diagnostic_arguments_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    result = apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-diagnostic", action="open_recovery_ticket"),
        _route("diagnostic_output", ("diagnostic_id", "observed_at"), action="open_recovery_ticket"),
        diagnostic_id="diagnostic-1", observed_at="",
        root=root,
    )

    assert (result.execution_status, result.preflight_status, result.applied_output) == ("blocked", "blocked", "none")
    assert result.missing_arguments == ("observed_at",)
    assert _files_under(root) == ()


def test_route_apply_calls_preflight_before_writer(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    original_preflight = route_executor.preflight_phase5_scheduler_action_route
    original_writer = route_executor.record_phase5_scheduler_plan_diagnostic

    def tracking_preflight(*args, **kwargs):
        calls.append("preflight")
        return original_preflight(*args, **kwargs)

    def tracking_writer(*args, **kwargs):
        calls.append("writer")
        return original_writer(*args, **kwargs)

    monkeypatch.setattr(route_executor, "preflight_phase5_scheduler_action_route", tracking_preflight)
    monkeypatch.setattr(route_executor, "record_phase5_scheduler_plan_diagnostic", tracking_writer)

    apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-order", action="open_recovery_ticket"),
        _route("diagnostic_output", ("diagnostic_id", "observed_at"), cycle_id="cycle-order", action="open_recovery_ticket"),
        diagnostic_id="diagnostic-order",
        observed_at="2026-05-21T10:00:00Z",
        root=tmp_path / "artifacts",
    )

    assert calls == ["preflight", "writer"]


def test_route_apply_records_diagnostic_ready_route(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-diagnostic")

    result = apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-diagnostic", action="open_recovery_ticket", reason="cycle precondition failed"),
        _route("diagnostic_output", ("diagnostic_id", "observed_at"), action="open_recovery_ticket"),
        diagnostic_id="diagnostic-apply",
        observed_at="2026-05-21T10:00:00Z",
        root=root,
    )
    diagnostic = read_phase5_scheduler_diagnostic_artifact("diagnostic-apply", root=root)

    assert (result.execution_status, result.applied_output, result.diagnostic_id) == ("applied", "diagnostic", "diagnostic-apply")
    assert result.cycle_event_recorded is True
    assert diagnostic.scheduler_action == "open_recovery_ticket"


def test_route_apply_records_execution_ready_route(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-execution")

    result = apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-execution", action="retry_failed_step", reason="retryable failure"),
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), cycle_id="cycle-execution", action="retry_failed_step"),
        execution_id="execution-apply",
        idempotency_key="idempotency:execution-apply",
        created_at="2026-05-21T10:00:00Z",
        diagnostic_refs=["diagnostic-1", "diagnostic-1"],
        root=root,
    )
    ledger = read_phase5_scheduler_execution_ledger_artifact("execution-apply", root=root)

    assert (result.execution_status, result.applied_output, result.execution_id) == ("applied", "execution", "execution-apply")
    assert result.idempotency_key == "idempotency:execution-apply"
    assert result.cycle_event_recorded is True
    assert ledger.diagnostic_refs == ["diagnostic-1"]


def test_route_apply_skips_wait_and_terminal_without_writing(tmp_path: Path) -> None:
    for route_type in ("wait_for_next_tick", "terminal"):
        root = tmp_path / route_type
        action = "continue_tracking" if route_type == "wait_for_next_tick" else "none"
        result = apply_phase5_scheduler_action_route(
            _plan(action=action),
            _route(route_type, (), cycle_id="cycle-20260520-001", action=action),
            root=root,
        )

        assert (result.execution_status, result.preflight_status, result.applied_output) == ("skipped", "ready", "none")
        assert _files_under(root) == ()
        rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        for leaked_key in ('"plan_status":', '"source_tick_status":', '"action":'):
            assert leaked_key not in rendered


def test_route_apply_blocks_plan_route_mismatch_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    result = apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-plan", action="retry_failed_step"),
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), cycle_id="cycle-route"),
        execution_id="execution-mismatch",
        idempotency_key="idempotency:execution-mismatch",
        created_at="2026-05-21T10:00:00Z",
        root=root,
    )

    assert (result.execution_status, result.preflight_status) == ("blocked", "ready")
    assert "cycle_id mismatch" in result.reason
    assert read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-mismatch", root=root) is None


def test_route_apply_returns_typed_blocked_on_idempotency_conflict(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    create_phase5_scheduler_execution_reservation_artifact(
        idempotency_key="idempotency:conflict",
        execution_id="execution-existing",
        cycle_id="cycle-conflict",
        created_at="2026-05-21T09:00:00Z",
        root=root,
    )

    result = apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-conflict", action="retry_failed_step"),
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), cycle_id="cycle-conflict", action="retry_failed_step"),
        execution_id="execution-requested",
        idempotency_key="idempotency:conflict",
        created_at="2026-05-21T10:00:00Z",
        root=root,
    )

    assert (result.execution_status, result.preflight_status, result.applied_output) == ("blocked", "ready", "none")
    assert result.error_type == "Phase5SchedulerExecutionIdempotencyConflictError"
    assert result.execution_id == "execution-requested"
    assert result.idempotency_key == "idempotency:conflict"
    assert read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-requested", root=root) is None


def _route(
    route_type: Phase5SchedulerActionRouteType,
    required_arguments: tuple[str, ...],
    *,
    cycle_id: str = "cycle-diagnostic",
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


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())) if root.exists() else ()
