from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from tests.helpers_cli_autonomous_flow import (
    _args,
    _assert_no_nested_flow_payload,
    _assert_rich_tick_args,
    _error_tick_result,
    _FakeDiagnosticResult,
    _FakeDryRunResult,
    _FakePlanResult,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_tick_result,
    _plan_result,
)
from tests.helpers_cli_autonomous_flow_execution import (
    _assert_execution_conflict_cli_returns_typed_json,
    _execution_result,
    _FakeExecutionResult,
)


def test_phase5_local_cycle_step_execution_missing_args_fail_before_tick(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_tick(**_kwargs: Any) -> _FakeTickResult:
        raise AssertionError("execution output must validate required args before tick")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(output="execution"))

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "error",
        "command": "phase5-local-cycle-step",
        "error_type": "MissingRequiredExecutionArgument",
        "message": "--execution-id, --idempotency-key and --created-at are required for execution output.",
        "missing_arguments": ["--execution-id", "--idempotency-key", "--created-at"],
    }


def test_phase5_local_cycle_step_execution_conflict_returns_typed_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _assert_execution_conflict_cli_returns_typed_json(monkeypatch, capsys)


def test_phase5_local_cycle_step_execution_calls_tick_plan_and_execution_recorder_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tick_calls: list[dict[str, Any]] = []
    planner_inputs: list[_FakeTickResult] = []
    recorder_inputs: list[dict[str, Any]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        planner_inputs.append(tick_result)
        return _plan_result(cycle_id=tick_result.payload["cycle_id"], action="retry_failed_step")

    def fake_record(plan: _FakePlanResult, **kwargs: Any) -> _FakeExecutionResult:
        recorder_inputs.append({"plan": plan, **kwargs})
        return _execution_result(
            cycle_id=plan.payload["cycle_id"],
            execution_id=kwargs["execution_id"],
            idempotency_key=kwargs["idempotency_key"],
            action=plan.payload["action"],
            diagnostic_refs=kwargs["diagnostic_refs"],
        )

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("execution output should not call service")

    def fail_dry_run(_plan: _FakePlanResult) -> _FakeDryRunResult:
        raise AssertionError("execution output should not call dry-run executor")

    def fail_diagnostic(_plan: _FakePlanResult, **_kwargs: Any) -> _FakeDiagnosticResult:
        raise AssertionError("execution output should not call diagnostic recorder")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_execution", fake_record)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fail_dry_run)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_diagnostic", fail_diagnostic)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="execution",
            cycle_id="cycle-execution",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
            execution_id="execution-1",
            idempotency_key="idempotency:execution-1",
            created_at="2026-05-20T10:01:00Z",
            diagnostic_id="diagnostic-1",
        )
    )

    assert exit_code == 0
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-execution", root=artifact_root)
    assert planner_inputs[0].payload["tick_status"] == "ok"
    assert recorder_inputs[0]["plan"].payload["action"] == "retry_failed_step"
    assert recorder_inputs[0]["execution_id"] == "execution-1"
    assert recorder_inputs[0]["idempotency_key"] == "idempotency:execution-1"
    assert recorder_inputs[0]["created_at"] == "2026-05-20T10:01:00Z"
    assert recorder_inputs[0]["diagnostic_refs"] == ["diagnostic-1"]
    assert recorder_inputs[0]["root"] == artifact_root
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_mode"] == "ledger_record"
    assert payload["action"] == "retry_failed_step"
    _assert_no_nested_flow_payload(payload)


def test_phase5_local_cycle_step_execution_error_tick_records_ledger(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder_inputs: list[_FakePlanResult] = []

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        return _error_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        return _plan_result(
            cycle_id=tick_result.payload["cycle_id"],
            source_tick_status="error",
            action="open_recovery_ticket",
        )

    def fake_record(plan: _FakePlanResult, **kwargs: Any) -> _FakeExecutionResult:
        recorder_inputs.append(plan)
        return _execution_result(
            cycle_id=plan.payload["cycle_id"],
            execution_id=kwargs["execution_id"],
            idempotency_key=kwargs["idempotency_key"],
            action=plan.payload["action"],
            execution_status="planned",
            blocking_reasons=["tick failure_class is artifact-missing"],
        )

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("execution output should not call service for error ticks")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_execution", fake_record)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="execution",
            apply_closeout=True,
            execution_id="execution-error",
            idempotency_key="idempotency:execution-error",
            created_at="2026-05-20T10:01:00Z",
        )
    )

    assert exit_code == 0
    assert recorder_inputs[0].payload["source_tick_status"] == "error"
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_id"] == "execution-error"
    assert payload["action"] == "open_recovery_ticket"
    assert payload["would_execute"] is False
    _assert_no_nested_flow_payload(payload)
