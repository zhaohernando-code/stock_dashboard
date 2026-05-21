from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply as attempt_auto_apply
import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from tests.helpers_cli_autonomous_flow import (
    _args,
    _assert_rich_tick_args,
    _FakePlanResult,
    _FakeTickResult,
    _ok_tick_result,
    _plan_result,
)
from tests.helpers_cli_autonomous_flow_attempt_route import _apply_result, _FakeResult, _files_under, _result
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


@pytest.mark.parametrize(("status", "exit_code"), [("applied", 0), ("skipped", 0), ("blocked", 4)])
def test_attempt_route_auto_apply_output_builds_context_then_applies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    exit_code: int,
) -> None:
    calls: list[str] = []
    tick_calls: list[dict[str, Any]] = []
    apply_inputs: list[dict[str, Any]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        calls.append("tick")
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        calls.append("plan")
        return _plan_result(cycle_id=tick_result.payload["cycle_id"], action="retry_failed_step")

    def fake_action(plan: _FakePlanResult) -> _FakeResult:
        calls.append("action")
        return _result(cycle_id=plan.payload["cycle_id"], action=plan.payload["action"])

    def fake_route(action_result: _FakeResult) -> _FakeResult:
        calls.append("route")
        return _result(cycle_id=action_result.payload["cycle_id"], route_type="execution_output")

    def fake_attempt_apply(plan: _FakePlanResult, route: _FakeResult, **kwargs: Any) -> _FakeResult:
        calls.append("attempt-apply")
        apply_inputs.append({"plan": plan.payload, "route": route.payload, **kwargs})
        return _apply_result(cycle_id=route.payload["cycle_id"], status=status)

    def fail_unexpected(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-route-auto-apply output called an unexpected handler")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fake_action)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fake_route)
    monkeypatch.setattr(
        cli_autonomous_flow,
        "build_attempt_context_and_apply_phase5_scheduler_action_route",
        fake_attempt_apply,
    )
    monkeypatch.setattr(cli_autonomous_flow, "bind_and_apply_phase5_scheduler_action_route", fail_unexpected)

    result = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="attempt-route-auto-apply",
            cycle_id="cycle-attempt-apply",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            issued_at="2026-05-21T10:00:00Z",
            runner_id="runner-bm1",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
        )
    )

    assert result == exit_code
    assert calls == ["tick", "plan", "action", "route", "attempt-apply"]
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-attempt-apply", root=artifact_root)
    assert apply_inputs == [
        {
            "plan": _plan_result(cycle_id="cycle-attempt-apply", action="retry_failed_step").payload,
            "route": _result(cycle_id="cycle-attempt-apply", route_type="execution_output").payload,
            "issued_at": "2026-05-21T10:00:00Z",
            "runner_id": "runner-bm1",
            "root": artifact_root,
        }
    ]
    assert json.loads(capsys.readouterr().out)["execution_status"] == status


def test_attempt_route_auto_apply_output_blocks_missing_context_before_core_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    def fail_bind(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("bind/apply must not run without explicit attempt context")

    monkeypatch.setattr(attempt_auto_apply, "bind_and_apply_phase5_scheduler_action_route", fail_bind)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-missing-attempt-context",
            "--artifact-root",
            str(artifact_root),
            "--runner-id",
            "runner-bm1",
            "--output",
            "attempt-route-auto-apply",
        ]
    )

    assert exit_code == 4
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    payload = json.loads(capsys.readouterr().out)
    assert payload["attempt_context_status"] == "blocked"
    assert payload["execution_status"] == "blocked"
    assert payload["preflight_status"] == "blocked"
    assert payload["attempt_id"] is None
    assert payload["missing_arguments"] == ["issued_at"]
