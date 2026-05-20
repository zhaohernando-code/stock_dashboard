from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


class _FakeResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


@pytest.mark.parametrize(("status", "exit_code"), [("applied", 0), ("skipped", 0), ("blocked", 4)])
def test_action_route_auto_apply_output_calls_bind_and_apply_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    exit_code: int,
) -> None:
    calls: list[str] = []
    tick_calls: list[dict[str, Any]] = []
    bind_inputs: list[dict[str, Any]] = []
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

    def fake_bind_and_apply(plan: _FakePlanResult, route: _FakeResult, **kwargs: Any) -> _FakeResult:
        calls.append("bind-and-apply")
        bind_inputs.append({"plan": plan.payload, "route": route.payload, **kwargs})
        return _apply_result(cycle_id=route.payload["cycle_id"], status=status)

    def fail_unexpected(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("action-route-auto-apply output called an unexpected handler")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fake_action)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fake_route)
    monkeypatch.setattr(cli_autonomous_flow, "bind_and_apply_phase5_scheduler_action_route", fake_bind_and_apply)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_diagnostic", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_execution", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "preflight_phase5_scheduler_action_route", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "apply_phase5_scheduler_action_route", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_unexpected)

    result = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="action-route-auto-apply",
            cycle_id="cycle-auto-apply",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            attempt_id="attempt-1",
            issued_at="2026-05-20T10:01:00Z",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
        )
    )

    assert result == exit_code
    assert calls == ["tick", "plan", "action", "route", "bind-and-apply"]
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-auto-apply", root=artifact_root)
    assert bind_inputs == [
        {
            "plan": _plan_result(cycle_id="cycle-auto-apply", action="retry_failed_step").payload,
            "route": _result(cycle_id="cycle-auto-apply", route_type="execution_output").payload,
            "attempt_id": "attempt-1",
            "issued_at": "2026-05-20T10:01:00Z",
            "root": artifact_root,
        }
    ]
    assert json.loads(capsys.readouterr().out)["execution_status"] == status


@pytest.mark.parametrize(
    ("extra_args", "missing_arguments"),
    [
        (["--issued-at", "2026-05-21T10:00:00Z"], ["attempt_id"]),
        (["--attempt-id", "attempt-1"], ["diagnostic_id", "observed_at"]),
    ],
)
def test_action_route_auto_apply_output_blocks_missing_scheduler_args_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
    missing_arguments: list[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-missing-auto-apply",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "action-route-auto-apply",
            *extra_args,
        ]
    )

    assert exit_code == 4
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_status"] == "blocked"
    assert payload["preflight_status"] == "blocked"
    assert payload["applied_output"] == "none"
    assert payload["missing_arguments"] == missing_arguments


def _result(
    *,
    cycle_id: str,
    action: str = "retry_failed_step",
    route_type: str = "execution_output",
) -> _FakeResult:
    return _FakeResult({"cycle_id": cycle_id, "action": action, "route_type": route_type})


def _apply_result(*, cycle_id: str, status: str) -> _FakeResult:
    return _FakeResult(
        {
            "cycle_id": cycle_id,
            "route_type": "execution_output",
            "execution_mode": "route_apply",
            "execution_status": status,
            "preflight_status": "ready" if status != "blocked" else "blocked",
            "applied_output": "execution" if status == "applied" else "none",
            "required_arguments": ["execution_id", "idempotency_key", "created_at"],
            "missing_arguments": [],
            "reason": "fake route apply result",
        }
    )


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
