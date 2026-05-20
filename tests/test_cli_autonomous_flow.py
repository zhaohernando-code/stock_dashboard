from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow


class _FakeServiceResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def _args(**overrides: Any) -> argparse.Namespace:
    payload = {
        "cycle_id": "cycle-1",
        "gate_id": None,
        "recovery_ticket_id": None,
        "projection_id": None,
        "finished_at": None,
        "apply_closeout": False,
        "require_publish_verification": False,
        "artifact_root": None,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def _ok_result(cycle_id: str = "cycle-1") -> _FakeServiceResult:
    return _FakeServiceResult(
        {
            "cycle_id": cycle_id,
            "runner_result": {"status": "dry_run"},
            "missing_refs": [],
        }
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


def test_phase5_local_cycle_step_dry_run_calls_service_without_apply_closeout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_service(**kwargs: Any) -> _FakeServiceResult:
        calls.append(kwargs)
        return _ok_result(kwargs["cycle_id"])

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)

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
    assert payload["cycle_id"] == "cycle-1"
    assert payload["runner_result"] == {"status": "dry_run"}
    assert payload["missing_refs"] == []


def test_phase5_local_cycle_step_apply_closeout_arguments_are_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_service(**kwargs: Any) -> _FakeServiceResult:
        calls.append(kwargs)
        return _ok_result(kwargs["cycle_id"])

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            cycle_id="cycle-apply",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            apply_closeout=True,
            require_publish_verification=True,
        )
    )

    assert exit_code == 0
    assert calls[0] == {
        "cycle_id": "cycle-apply",
        "gate_id": "gate-1",
        "recovery_ticket_id": "ticket-1",
        "projection_id": "projection-1",
        "finished_at": "2026-05-20T10:00:00Z",
        "apply_closeout": True,
        "require_publish_verification": True,
        "root": None,
    }


def test_phase5_local_cycle_step_artifact_root_is_passed_as_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    artifact_root = tmp_path / "artifacts"

    def fake_service(**kwargs: Any) -> _FakeServiceResult:
        calls.append(kwargs)
        return _ok_result(kwargs["cycle_id"])

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(artifact_root=artifact_root))

    assert exit_code == 0
    assert calls[0]["root"] == artifact_root
    assert isinstance(calls[0]["root"], Path)


def test_phase5_local_cycle_step_error_returns_nonzero_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_service(**_kwargs: Any) -> _FakeServiceResult:
        raise ValueError("phase5 local cycle service apply_closeout requires finished_at")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(apply_closeout=True))

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "error",
        "command": "phase5-local-cycle-step",
        "error_type": "ValueError",
        "message": "phase5 local cycle service apply_closeout requires finished_at",
    }


def test_phase5_local_cycle_step_main_does_not_initialize_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_init_database(_database_url: str | None = None) -> None:
        raise AssertionError("init_database should not be called")

    def fake_service(**kwargs: Any) -> _FakeServiceResult:
        return _ok_result(kwargs["cycle_id"])

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)

    exit_code = cli_module.main(["phase5-local-cycle-step", "--cycle-id", "cycle-1"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["cycle_id"] == "cycle-1"
