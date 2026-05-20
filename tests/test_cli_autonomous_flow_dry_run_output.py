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
    _dry_run_result,
    _error_tick_result,
    _FakeDryRunResult,
    _FakePlanResult,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_tick_result,
    _plan_result,
)


def test_phase5_local_cycle_step_dry_run_calls_tick_plan_and_executor_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tick_calls: list[dict[str, Any]] = []
    planner_inputs: list[_FakeTickResult] = []
    dry_run_inputs: list[_FakePlanResult] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        planner_inputs.append(tick_result)
        return _plan_result(cycle_id=tick_result.payload["cycle_id"])

    def fake_dry_run(plan: _FakePlanResult) -> _FakeDryRunResult:
        dry_run_inputs.append(plan)
        return _dry_run_result(cycle_id=plan.payload["cycle_id"])

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("dry-run output should not call service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fake_dry_run)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="dry-run",
            cycle_id="cycle-dry-run",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
        )
    )

    assert exit_code == 0
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-dry-run", root=artifact_root)
    assert planner_inputs[0].payload["tick_status"] == "ok"
    assert dry_run_inputs[0].payload["action"] == "continue_tracking"
    payload = json.loads(capsys.readouterr().out)
    assert payload == _dry_run_result(cycle_id="cycle-dry-run").payload
    _assert_no_nested_flow_payload(payload)


def test_phase5_local_cycle_step_dry_run_error_tick_returns_zero_with_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        return _error_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        return _plan_result(
            cycle_id=tick_result.payload["cycle_id"],
            source_tick_status="error",
            action="open_recovery_ticket",
        )

    def fake_dry_run(plan: _FakePlanResult) -> _FakeDryRunResult:
        return _dry_run_result(
            cycle_id=plan.payload["cycle_id"],
            planned_action=plan.payload["action"],
            planned_effects=["prepare_recovery_ticket"],
        )

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("dry-run output should not call service for error ticks")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fake_dry_run)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(output="dry-run", apply_closeout=True)
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-1"
    assert payload["execution_status"] == "planned"
    assert payload["planned_action"] == "open_recovery_ticket"
    assert payload["planned_effects"] == ["prepare_recovery_ticket"]

