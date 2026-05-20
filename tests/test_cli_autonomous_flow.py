from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from tests.helpers_cli_autonomous_flow import (
    _args,
    _error_tick_result,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_tick_result,
)


def test_phase5_local_cycle_step_parser_is_registered() -> None:
    parser = cli_module.build_parser()

    args = parser.parse_args(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-1",
            "--artifact-root",
            "tmp/artifacts",
        ]
    )

    assert args.command == "phase5-local-cycle-step"
    assert args.cycle_id == "cycle-1"
    assert args.artifact_root == Path("tmp/artifacts")
    assert args.apply_closeout is False
    assert args.output == "status"


def test_phase5_local_cycle_step_parser_accepts_plan_output() -> None:
    parser = cli_module.build_parser()

    args = parser.parse_args(["phase5-local-cycle-step", "--cycle-id", "cycle-1", "--output", "plan"])

    assert args.command == "phase5-local-cycle-step"
    assert args.output == "plan"


def test_phase5_local_cycle_step_parser_accepts_dry_run_output() -> None:
    parser = cli_module.build_parser()

    args = parser.parse_args(["phase5-local-cycle-step", "--cycle-id", "cycle-1", "--output", "dry-run"])

    assert args.command == "phase5-local-cycle-step"
    assert args.output == "dry-run"


def test_phase5_local_cycle_step_parser_accepts_diagnostic_output() -> None:
    parser = cli_module.build_parser()

    args = parser.parse_args(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-1",
            "--output",
            "diagnostic",
            "--diagnostic-id",
            "diagnostic-1",
            "--observed-at",
            "2026-05-20T10:00:00Z",
        ]
    )

    assert args.command == "phase5-local-cycle-step"
    assert args.output == "diagnostic"
    assert args.diagnostic_id == "diagnostic-1"
    assert args.observed_at == "2026-05-20T10:00:00Z"


def test_phase5_local_cycle_step_default_calls_tick_without_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("default status output should call tick, not service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args())

    assert exit_code == 0
    assert calls == [
        {
            "cycle_id": "cycle-1",
            "gate_id": None,
            "recovery_ticket_id": None,
            "projection_id": None,
            "finished_at": None,
            "apply_closeout": False,
            "require_publish_verification": False,
            "root": None,
        }
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["tick_status"] == "ok"
    assert payload["exit_code"] == 0
    assert payload["status"]["cycle_id"] == "cycle-1"
    assert payload["recommended_next_action"] == "continue_tracking"
    assert payload["summary_status"] == "completed"
    assert payload["error"] is None
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "input_bundle" not in serialized
    assert "runner_result" not in serialized
    assert "release-manifest:" not in serialized
    assert "sha256:" not in serialized


def test_phase5_local_cycle_step_default_arguments_are_passed_to_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            cycle_id="cycle-apply",
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
            "cycle_id": "cycle-apply",
            "gate_id": "gate-1",
            "recovery_ticket_id": "ticket-1",
            "projection_id": "projection-1",
            "finished_at": "2026-05-20T10:00:00Z",
            "apply_closeout": True,
            "require_publish_verification": True,
            "root": artifact_root,
        }
    ]
    assert isinstance(calls[0]["root"], Path)


def test_phase5_local_cycle_step_default_returns_tick_exit_code_and_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        return _error_tick_result(kwargs["cycle_id"])

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("default failure output should come from tick envelope")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(apply_closeout=True))

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == _error_tick_result("cycle-1").payload


def test_phase5_local_cycle_step_main_does_not_initialize_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_init_database(_database_url: str | None = None) -> None:
        raise AssertionError("init_database should not be called")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        return _ok_tick_result(kwargs["cycle_id"])

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)

    exit_code = cli_module.main(["phase5-local-cycle-step", "--cycle-id", "cycle-1"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tick_status"] == "ok"
    assert payload["status"]["cycle_id"] == "cycle-1"
