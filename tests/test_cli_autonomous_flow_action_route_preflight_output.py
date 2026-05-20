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
    _FakeServiceResult,
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


def test_action_route_preflight_output_calls_handlers_in_order(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    tick_calls: list[dict[str, Any]] = []
    provided_argument_names: list[tuple[str, ...]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        calls.append("tick")
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        calls.append("plan")
        return _plan_result(cycle_id=tick_result.payload["cycle_id"])

    def fake_action(plan: _FakePlanResult) -> _FakeResult:
        calls.append("action")
        return _result(cycle_id=plan.payload["cycle_id"], status="completed")

    def fake_route(action_result: _FakeResult) -> _FakeResult:
        calls.append("route")
        return _result(cycle_id=action_result.payload["cycle_id"], route_type="diagnostic_output", status="blocked")

    def fake_preflight(route_result: _FakeResult, argument_names: tuple[str, ...]) -> _FakeResult:
        calls.append("preflight")
        provided_argument_names.append(argument_names)
        return _result(
            cycle_id=route_result.payload["cycle_id"],
            route_type=route_result.payload["route_type"],
            status="ready",
        )

    def fail_dry_run(_plan: _FakePlanResult) -> object:
        raise AssertionError("action-route-preflight output should not call dry-run executor")

    def fail_diagnostic(_plan: _FakePlanResult, **_kwargs: Any) -> object:
        raise AssertionError("action-route-preflight output should not call diagnostic recorder")

    def fail_execution(_plan: _FakePlanResult, **_kwargs: Any) -> object:
        raise AssertionError("action-route-preflight output should not call execution ledger recorder")

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("action-route-preflight output should not call full service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fake_action)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fake_route)
    monkeypatch.setattr(cli_autonomous_flow, "preflight_phase5_scheduler_action_route", fake_preflight)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fail_dry_run)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_diagnostic", fail_diagnostic)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_execution", fail_execution)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="action-route-preflight",
            cycle_id="cycle-route-preflight",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
            diagnostic_id="diagnostic-1",
            observed_at="2026-05-20T10:01:00Z",
        )
    )

    assert exit_code == 0
    assert calls == ["tick", "plan", "action", "route", "preflight"]
    assert provided_argument_names == [("diagnostic_id", "observed_at")]
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-route-preflight", root=artifact_root)
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


@pytest.mark.parametrize(
    ("cycle_id", "extra_args", "expected_exit_code", "expected_payload"),
    [
        (
            "cycle-missing-route-preflight",
            [],
            4,
            {
                "cycle_id": "cycle-missing-route-preflight",
                "route_type": "diagnostic_output",
                "status": "blocked",
                "required_arguments": ["diagnostic_id", "observed_at"],
                "missing_arguments": ["diagnostic_id", "observed_at"],
                "reason": "missing required action route arguments: diagnostic_id, observed_at",
            },
        ),
        (
            "cycle-ready-route-preflight",
            ["--diagnostic-id", "diagnostic-20260521-az1", "--observed-at", "2026-05-21T10:00:00Z"],
            0,
            {
                "cycle_id": "cycle-ready-route-preflight",
                "route_type": "diagnostic_output",
                "status": "ready",
                "required_arguments": ["diagnostic_id", "observed_at"],
                "missing_arguments": [],
                "reason": "all required action route arguments are provided",
            },
        ),
    ],
)
def test_action_route_preflight_output_blocks_missing_diagnostic_arguments_and_accepts_provided_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cycle_id: str,
    extra_args: list[str],
    expected_exit_code: int,
    expected_payload: dict[str, Any],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)
    command = [
        "phase5-local-cycle-step",
        "--cycle-id",
        cycle_id,
        "--artifact-root",
        str(artifact_root),
        *extra_args,
        "--output",
        "action-route-preflight",
    ]

    exit_code = cli_module.main(command)

    assert exit_code == expected_exit_code
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    payload = json.loads(capsys.readouterr().out)
    assert payload == expected_payload
    for generated_name in (
        "diagnostic_id",
        "observed_at",
        "execution_id",
        "idempotency_key",
        "created_at",
    ):
        assert generated_name not in payload


def _result(*, cycle_id: str, status: str, route_type: str = "diagnostic_output") -> _FakeResult:
    return _FakeResult(
        {"cycle_id": cycle_id, "execution_status": status, "route_type": route_type, "status": status}
    )


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
