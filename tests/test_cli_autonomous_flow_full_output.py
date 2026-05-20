from __future__ import annotations

import json
from typing import Any

import pytest

import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from tests.helpers_cli_autonomous_flow import (
    _args,
    _FakePlanResult,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_service_result,
)


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

