from __future__ import annotations

from pathlib import Path

import ashare_evidence.autonomous_flow_scheduler_action_route_auto_apply as auto_apply
from ashare_evidence.autonomous_flow_scheduler_action_route_auto_apply import (
    bind_and_apply_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_action_route_executor import (
    Phase5SchedulerActionRouteApplyResult,
)
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
)
from ashare_evidence.research_artifact_store import read_phase5_scheduler_diagnostic_artifact
from ashare_evidence.scheduler_execution_artifact_store import read_phase5_scheduler_execution_ledger_artifact
from tests.helpers_autonomous_flow_scheduler import _plan
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle


def test_bind_and_apply_blocks_without_issued_at_before_apply(monkeypatch, tmp_path: Path) -> None:
    def fail_apply(*args, **kwargs):
        raise AssertionError("apply must not be called when binding is blocked")

    monkeypatch.setattr(auto_apply, "apply_phase5_scheduler_action_route", fail_apply)

    result = bind_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-blocked", action="open_recovery_ticket"),
        _route("diagnostic_output", ("diagnostic_id", "observed_at"), cycle_id="cycle-blocked", action="open_recovery_ticket"),
        attempt_id="attempt-001",
        root=tmp_path / "artifacts",
    )

    assert (result.execution_status, result.preflight_status, result.applied_output) == ("blocked", "blocked", "none")
    assert result.missing_arguments == ("diagnostic_id", "observed_at")
    assert _files_under(tmp_path) == ()


def test_bind_and_apply_blocks_without_attempt_id_before_binding(monkeypatch, tmp_path: Path) -> None:
    def fail_bind(*args, **kwargs):
        raise AssertionError("argument binding must not be called without attempt_id")

    def fail_apply(*args, **kwargs):
        raise AssertionError("apply must not be called without attempt_id")

    monkeypatch.setattr(auto_apply, "bind_phase5_scheduler_action_route_arguments", fail_bind)
    monkeypatch.setattr(auto_apply, "apply_phase5_scheduler_action_route", fail_apply)

    result = bind_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-no-attempt", action="retry_failed_step"),
        _route(
            "execution_output",
            ("execution_id", "idempotency_key", "created_at"),
            cycle_id="cycle-no-attempt",
            action="retry_failed_step",
        ),
        attempt_id=None,
        issued_at="2026-05-21T10:00:00Z",
        root=tmp_path / "artifacts",
    )

    assert (result.execution_status, result.preflight_status, result.applied_output) == ("blocked", "blocked", "none")
    assert result.required_arguments == ("attempt_id",)
    assert result.missing_arguments == ("attempt_id",)
    assert "attempt_id is required" in result.reason
    assert _files_under(tmp_path) == ()


def test_bind_and_apply_records_diagnostic_with_bound_arguments(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-diagnostic")

    result = bind_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-diagnostic", action="open_recovery_ticket"),
        _route("diagnostic_output", ("diagnostic_id", "observed_at"), action="open_recovery_ticket"),
        attempt_id="attempt-002",
        issued_at="2026-05-21T10:00:00Z",
        root=root,
    )
    diagnostic = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id or "", root=root)

    assert (result.execution_status, result.applied_output) == ("applied", "diagnostic")
    assert result.diagnostic_id is not None
    assert diagnostic.observed_at == "2026-05-21T10:00:00Z"


def test_bind_and_apply_execution_passes_empty_diagnostic_refs(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def capture_apply(*args, **kwargs):
        calls.append(kwargs)
        return Phase5SchedulerActionRouteApplyResult(
            cycle_id="cycle-execution",
            route_type="execution_output",
            execution_status="applied",
            preflight_status="ready",
            applied_output="execution",
            required_arguments=("execution_id", "idempotency_key", "created_at"),
            missing_arguments=(),
            execution_id=kwargs["execution_id"],
            idempotency_key=kwargs["idempotency_key"],
            reason="captured",
        )

    monkeypatch.setattr(auto_apply, "apply_phase5_scheduler_action_route", capture_apply)

    result = bind_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-execution", action="retry_failed_step"),
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), cycle_id="cycle-execution", action="retry_failed_step"),
        attempt_id="attempt-003",
        issued_at="2026-05-21T10:00:00Z",
    )

    assert result.execution_status == "applied"
    assert calls[0]["diagnostic_refs"] == ()
    assert calls[0]["created_at"] == "2026-05-21T10:00:00Z"
    assert str(calls[0]["execution_id"]).startswith("execution-cycle-execution-retry_failed_step-attempt-003-")


def test_bind_and_apply_records_execution_with_bound_arguments(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-execution")

    result = bind_and_apply_phase5_scheduler_action_route(
        _plan(cycle_id="cycle-execution", action="retry_failed_step"),
        _route("execution_output", ("execution_id", "idempotency_key", "created_at"), cycle_id="cycle-execution", action="retry_failed_step"),
        attempt_id="attempt-004",
        issued_at="2026-05-21T10:00:00Z",
        root=root,
    )
    ledger = read_phase5_scheduler_execution_ledger_artifact(result.execution_id or "", root=root)

    assert (result.execution_status, result.applied_output) == ("applied", "execution")
    assert ledger.created_at == "2026-05-21T10:00:00Z"
    assert ledger.diagnostic_refs == []


def test_bind_and_apply_skips_wait_and_terminal_without_writing(tmp_path: Path) -> None:
    for route_type in ("wait_for_next_tick", "terminal"):
        root = tmp_path / route_type
        action = "continue_tracking" if route_type == "wait_for_next_tick" else "none"
        result = bind_and_apply_phase5_scheduler_action_route(
            _plan(action=action),
            _route(route_type, (), cycle_id="cycle-20260520-001", action=action),
            attempt_id=f"attempt-{route_type}",
            root=root,
        )

        assert (result.execution_status, result.preflight_status, result.applied_output) == ("skipped", "ready", "none")
        assert _files_under(root) == ()


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
