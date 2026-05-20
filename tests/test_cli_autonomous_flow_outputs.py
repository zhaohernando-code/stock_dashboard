from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from tests.helpers_cli_autonomous_flow import (
    _args,
    _error_tick_result,
    _FakePlanResult,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_service_result,
    _ok_tick_result,
    _plan_result,
)


def test_phase5_local_cycle_step_plan_calls_tick_and_followup_planner_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tick_calls: list[dict[str, Any]] = []
    planner_inputs: list[_FakeTickResult] = []

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        planner_inputs.append(tick_result)
        return _plan_result(cycle_id=tick_result.payload["cycle_id"])

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("plan output should call tick and planner, not service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(output="plan"))

    assert exit_code == 0
    assert len(tick_calls) == 1
    assert len(planner_inputs) == 1
    assert planner_inputs[0].payload["tick_status"] == "ok"
    payload = json.loads(capsys.readouterr().out)
    assert payload == _plan_result().payload
    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"status":' not in serialized
    assert '"error":' not in serialized
    assert "input_bundle" not in serialized
    assert "runner_result" not in serialized
    assert "release-manifest:" not in serialized
    assert "sha256:" not in serialized


def test_phase5_local_cycle_step_plan_arguments_are_passed_to_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        return _plan_result(cycle_id=tick_result.payload["cycle_id"])

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="plan",
            cycle_id="cycle-plan",
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
    assert calls == [
        {
            "cycle_id": "cycle-plan",
            "gate_id": "gate-1",
            "recovery_ticket_id": "ticket-1",
            "projection_id": "projection-1",
            "finished_at": "2026-05-20T10:00:00Z",
            "apply_closeout": True,
            "require_publish_verification": True,
            "root": artifact_root,
        }
    ]


def test_phase5_local_cycle_step_plan_error_tick_returns_zero_with_plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    planner_inputs: list[_FakeTickResult] = []

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        return _error_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        planner_inputs.append(tick_result)
        return _plan_result(
            cycle_id=tick_result.payload["cycle_id"],
            source_tick_status="error",
            action="open_recovery_ticket",
        )

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("plan output should not call service for error ticks")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(output="plan", apply_closeout=True)
    )

    assert exit_code == 0
    assert planner_inputs[0].payload["tick_status"] == "error"
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-1"
    assert payload["source_tick_status"] == "error"
    assert payload["action"] == "open_recovery_ticket"


def test_phase5_local_cycle_step_full_output_preserves_service_result_without_tick(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service_calls: list[dict[str, Any]] = []

    def fake_service(**kwargs: Any) -> _FakeServiceResult:
        service_calls.append(kwargs)
        return _ok_service_result(kwargs["cycle_id"])

    def fail_tick(**_kwargs: Any) -> _FakeTickResult:
        raise AssertionError("full output should call service, not tick")

    def fail_plan(_tick_result: _FakeTickResult) -> _FakePlanResult:
        raise AssertionError("full output should not call follow-up planner")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail_plan)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(output="full"))

    assert exit_code == 0
    assert service_calls[0]["cycle_id"] == "cycle-1"
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-1"
    assert payload["input_bundle"] == {"cycle": {"cycle_id": "cycle-1"}}
    assert payload["runner_result"] == {"status": "dry_run"}
    assert payload["release_manifest_ref"] == "release-manifest:phase5:20260520"
    assert payload["digest"] == "sha256:abc123"


def test_phase5_local_cycle_step_full_output_service_error_returns_cli_error_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_service(**_kwargs: Any) -> _FakeServiceResult:
        raise ValueError("phase5 local cycle service apply_closeout requires finished_at")

    def fail_tick(**_kwargs: Any) -> _FakeTickResult:
        raise AssertionError("full output should not call tick")

    def fail_plan(_tick_result: _FakeTickResult) -> _FakePlanResult:
        raise AssertionError("full output should not call follow-up planner")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail_plan)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(output="full", apply_closeout=True)
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "error",
        "command": "phase5-local-cycle-step",
        "error_type": "ValueError",
        "message": "phase5 local cycle service apply_closeout requires finished_at",
    }
