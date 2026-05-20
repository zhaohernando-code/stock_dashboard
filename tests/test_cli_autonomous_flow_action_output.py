from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from tests.helpers_cli_autonomous_flow import (
    _args,
    _assert_no_nested_flow_payload,
    _assert_rich_tick_args,
    _FakePlanResult,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_tick_result,
    _plan_result,
)
from tests.helpers_cli_autonomous_flow_smoke import (
    _assert_no_nested_scheduler_payload,
    _guard_init_database,
    _write_happy_path_artifacts,
)


class _FakeActionResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def test_phase5_local_cycle_step_action_output_calls_noop_executor_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    tick_calls: list[dict[str, Any]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        calls.append("tick")
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        calls.append("plan")
        return _plan_result(cycle_id=tick_result.payload["cycle_id"])

    def fake_action(plan: _FakePlanResult) -> _FakeActionResult:
        calls.append("action")
        return _action_result(cycle_id=plan.payload["cycle_id"], action=plan.payload["action"])

    def fail_dry_run(_plan: _FakePlanResult) -> object:
        raise AssertionError("action output should not call dry-run executor")

    def fail_diagnostic(_plan: _FakePlanResult, **_kwargs: Any) -> object:
        raise AssertionError("action output should not call diagnostic recorder")

    def fail_execution(_plan: _FakePlanResult, **_kwargs: Any) -> object:
        raise AssertionError("action output should not call execution ledger recorder")

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("action output should not call full service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fake_action)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fail_dry_run)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_diagnostic", fail_diagnostic)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_execution", fail_execution)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="action",
            cycle_id="cycle-action",
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
    assert calls == ["tick", "plan", "action"]
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-action", root=artifact_root)
    payload = json.loads(capsys.readouterr().out)
    assert payload == _action_result(cycle_id="cycle-action").payload
    _assert_no_nested_flow_payload(payload)


def test_phase5_local_cycle_step_action_smoke_completes_continue_tracking_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    before_files = _files_under(artifact_root)
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-20260520-smoke",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "action",
        ]
    )

    assert exit_code == 0
    assert init_database_calls == []
    assert _files_under(artifact_root) == before_files
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-20260520-smoke"
    assert payload["execution_mode"] == "contract_action"
    assert payload["execution_status"] == "completed"
    assert payload["action"] == "continue_tracking"
    assert payload["preflight_status"] == "ready"
    assert payload["performed_effects"] == ["keep_cycle_open_for_next_tick"]
    _assert_no_nested_scheduler_payload(payload)


def test_phase5_local_cycle_step_action_smoke_missing_cycle_blocks_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-missing-smoke",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "action",
        ]
    )

    assert exit_code == 4
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-missing-smoke"
    assert payload["execution_mode"] == "contract_action"
    assert payload["execution_status"] == "blocked"
    assert payload["action"] == "open_recovery_ticket"
    assert payload["preflight_status"] == "blocked"
    assert payload["performed_effects"] == []
    assert payload["durable_outputs"] == ["phase5_recovery_ticket"]
    assert payload["may_close_cycle"] is False
    assert payload["skipped_reason"] == "scheduler action preflight blocked by missing inputs"
    _assert_no_nested_scheduler_payload(payload)


def _action_result(*, cycle_id: str, action: str = "continue_tracking") -> _FakeActionResult:
    return _FakeActionResult(
        {
            "cycle_id": cycle_id,
            "execution_mode": "contract_action",
            "execution_status": "completed",
            "action": action,
            "preflight_status": "ready",
            "performed_effects": ["keep_cycle_open_for_next_tick"],
            "skipped_reason": None,
            "durable_outputs": [],
            "may_close_cycle": False,
            "reason": "scheduler action executed observe-only contract",
        }
    )


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
