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


class _FakeTickResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.exit_code = int(payload["exit_code"])

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
        "output": "status",
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def _ok_service_result(cycle_id: str = "cycle-1") -> _FakeServiceResult:
    return _FakeServiceResult(
        {
            "cycle_id": cycle_id,
            "input_bundle": {"cycle": {"cycle_id": cycle_id}},
            "runner_result": {"status": "dry_run"},
            "release_manifest_ref": "release-manifest:phase5:20260520",
            "digest": "sha256:abc123",
            "missing_refs": [],
        }
    )


def _ok_tick_result(cycle_id: str = "cycle-1") -> _FakeTickResult:
    return _FakeTickResult(
        {
            "cycle_id": cycle_id,
            "tick_status": "ok",
            "exit_code": 0,
            "status": {
                "cycle_id": cycle_id,
                "cycle_status": "running",
                "decision_status": "completed",
                "next_action": "continue_tracking",
                "claim_ceiling": "paper_tracking_candidate",
                "decision_reason": "all planner inputs are fresh and unblocked",
                "missing_refs": [],
                "blocking_reasons": [],
                "source_refs": [cycle_id],
                "closeout_applied": False,
                "finished_at": None,
                "publish_verification_status": "not_required",
                "staleness_status": "fresh",
                "summary_status": "completed",
            },
            "error": None,
            "recommended_next_action": "continue_tracking",
            "summary_status": "completed",
        }
    )


def _error_tick_result(cycle_id: str = "cycle-1") -> _FakeTickResult:
    return _FakeTickResult(
        {
            "cycle_id": cycle_id,
            "tick_status": "error",
            "exit_code": 1,
            "status": None,
            "error": {
                "error_type": "ValueError",
                "message": "phase5 local cycle service apply_closeout requires finished_at",
                "failure_class": "contract-violation",
                "recommended_recovery_action": "block_cycle",
            },
            "recommended_next_action": "blocked",
            "summary_status": "blocked",
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
    assert args.output == "status"


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

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)

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

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fake_service)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)

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
