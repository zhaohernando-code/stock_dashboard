from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply as attempt_auto_apply
import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow_attempt_outputs as attempt_outputs
from tests.helpers_cli_autonomous_flow import (
    _args,
    _assert_rich_tick_args,
    _ok_tick_result,
    _plan_result,
)
from tests.helpers_cli_autonomous_flow_attempt_recording import (
    _attempt_record_handlers,
    _real_apply_result,
    _run_default_attempt_route_auto_apply,
)
from tests.helpers_cli_autonomous_flow_attempt_route import _files_under, _result
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


@pytest.mark.parametrize(("status", "exit_code"), [("applied", 0), ("skipped", 0), ("blocked", 4)])
def test_attempt_route_auto_apply_output_default_does_not_record_attempt_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    exit_code: int,
) -> None:
    artifact_root = tmp_path / "artifacts"
    run = _run_default_attempt_route_auto_apply(monkeypatch, artifact_root, status=status)

    assert run["result"] == exit_code
    assert run["calls"] == ["tick", "plan", "action", "route", "attempt-apply"]
    _assert_rich_tick_args(run["tick_calls"], cycle_id="cycle-attempt-apply", root=artifact_root)
    assert run["apply_inputs"] == [
        {
            "plan": _plan_result(cycle_id="cycle-attempt-apply", action="retry_failed_step").payload,
            "route": _result(cycle_id="cycle-attempt-apply", route_type="execution_output").payload,
            "issued_at": "2026-05-21T10:00:00Z",
            "runner_id": "runner-bm1",
            "root": artifact_root,
        }
    ]
    assert json.loads(capsys.readouterr().out)["execution_status"] == status
    assert _files_under(artifact_root) == ()


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


def test_attempt_route_auto_apply_output_records_attempt_run_when_enabled(tmp_path: Path) -> None:
    printed: list[dict[str, Any]] = []
    apply_result = _real_apply_result(cycle_id="cycle-record-enabled")

    exit_code = attempt_outputs.handle_attempt_route_auto_apply_output(
        _args(
            output="attempt-route-auto-apply",
            artifact_root=tmp_path,
            issued_at="2026-05-21T10:00:00Z",
            runner_id="runner-bs1",
            record_attempt_run=True,
            attempt_run_id="run-bs1-explicit",
        ),
        _attempt_record_handlers(apply_result),
        run_tick_from_args=lambda args, _handlers: _ok_tick_result(args.cycle_id),
        print_json=printed.append,
    )

    artifact_path = tmp_path / "autonomous_flow" / "phase5_scheduler_attempt_run" / "run-bs1-explicit.json"
    assert exit_code == 0
    assert len(printed) == 1
    assert printed[0]["apply_result"] == apply_result.model_dump(mode="json")
    assert printed[0]["attempt_run_record_status"] == "recorded"
    assert printed[0]["attempt_run_artifact"]["run_id"] == "run-bs1-explicit"
    assert printed[0]["attempt_run_artifact_path"] == str(artifact_path)
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["run_id"] == "run-bs1-explicit"


def test_attempt_route_auto_apply_output_record_blocks_missing_precondition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printed: list[dict[str, Any]] = []
    apply_result = _real_apply_result(cycle_id="cycle-record-blocked", status="blocked")

    def fail_record(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("recorder must not run without required context")

    monkeypatch.setattr(attempt_outputs, "record_phase5_scheduler_attempt_run_artifact", fail_record)

    exit_code = attempt_outputs.handle_attempt_route_auto_apply_output(
        _args(output="attempt-route-auto-apply", artifact_root=tmp_path, record_attempt_run=True),
        _attempt_record_handlers(apply_result),
        run_tick_from_args=lambda args, _handlers: _ok_tick_result(args.cycle_id),
        print_json=printed.append,
    )

    assert exit_code == 4
    assert printed[0]["attempt_run_record_status"] == "blocked"
    assert printed[0]["attempt_run_artifact"] is None
    assert printed[0]["attempt_run_artifact_path"] is None
    assert printed[0]["attempt_run_record_missing_arguments"] == ["issued_at", "runner_id"]
    assert _files_under(tmp_path) == ()
