from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    read_phase5_scheduler_diagnostic_artifact,
)
from tests.helpers_cli_autonomous_flow import (
    _args,
    _assert_no_nested_flow_payload,
    _assert_rich_tick_args,
    _diagnostic_result,
    _error_tick_result,
    _FakeDiagnosticResult,
    _FakeDryRunResult,
    _FakePlanResult,
    _FakeServiceResult,
    _FakeTickResult,
    _ok_tick_result,
    _plan_result,
)
from tests.test_cli_autonomous_flow_smoke import _write_happy_path_artifacts


def test_phase5_local_cycle_step_diagnostic_requires_explicit_id_and_observed_at(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_tick(**_kwargs: Any) -> _FakeTickResult:
        raise AssertionError("diagnostic argument validation should happen before tick")

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("diagnostic output should not call service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(_args(output="diagnostic"))

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "error",
        "command": "phase5-local-cycle-step",
        "error_type": "MissingRequiredDiagnosticArgument",
        "message": "--diagnostic-id and --observed-at are required for diagnostic output.",
        "missing_arguments": ["--diagnostic-id", "--observed-at"],
    }


@pytest.mark.parametrize(
    ("diagnostic_id", "observed_at", "missing_arguments"),
    [
        (None, "2026-05-20T10:00:00Z", ["--diagnostic-id"]),
        ("diagnostic-1", None, ["--observed-at"]),
    ],
)
def test_phase5_local_cycle_step_diagnostic_requires_each_diagnostic_argument(
    capsys: pytest.CaptureFixture[str],
    diagnostic_id: str | None,
    observed_at: str | None,
    missing_arguments: list[str],
) -> None:
    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(output="diagnostic", diagnostic_id=diagnostic_id, observed_at=observed_at)
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing_arguments"] == missing_arguments


def test_phase5_local_cycle_step_diagnostic_calls_tick_plan_and_recorder_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tick_calls: list[dict[str, Any]] = []
    planner_inputs: list[_FakeTickResult] = []
    recorder_calls: list[dict[str, Any]] = []
    artifact_root = Path("tmp/artifacts")

    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        tick_calls.append(kwargs)
        return _ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        planner_inputs.append(tick_result)
        return _plan_result(cycle_id=tick_result.payload["cycle_id"])

    def fake_record(
        plan: _FakePlanResult,
        *,
        diagnostic_id: str,
        observed_at: str,
        root: Path | None = None,
    ) -> _FakeDiagnosticResult:
        recorder_calls.append(
            {
                "plan": plan,
                "diagnostic_id": diagnostic_id,
                "observed_at": observed_at,
                "root": root,
            }
        )
        return _diagnostic_result(cycle_id=plan.payload["cycle_id"], diagnostic_id=diagnostic_id)

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("diagnostic output should not call service")

    def fail_dry_run(_plan: _FakePlanResult) -> _FakeDryRunResult:
        raise AssertionError("diagnostic output should not call dry-run executor")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_diagnostic", fake_record)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fail_dry_run)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="diagnostic",
            cycle_id="cycle-diagnostic",
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            diagnostic_id="diagnostic-1",
            observed_at="2026-05-20T10:01:00Z",
            apply_closeout=True,
            require_publish_verification=True,
            artifact_root=artifact_root,
        )
    )

    assert exit_code == 0
    _assert_rich_tick_args(tick_calls, cycle_id="cycle-diagnostic", root=artifact_root)
    assert planner_inputs[0].payload["tick_status"] == "ok"
    assert recorder_calls == [
        {
            "plan": recorder_calls[0]["plan"],
            "diagnostic_id": "diagnostic-1",
            "observed_at": "2026-05-20T10:01:00Z",
            "root": artifact_root,
        }
    ]
    assert recorder_calls[0]["plan"].payload["action"] == "continue_tracking"
    payload = json.loads(capsys.readouterr().out)
    assert payload == _diagnostic_result(cycle_id="cycle-diagnostic", diagnostic_id="diagnostic-1").payload
    _assert_no_nested_flow_payload(payload)


def test_phase5_local_cycle_step_diagnostic_error_tick_returns_zero_with_record_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_tick(**kwargs: Any) -> _FakeTickResult:
        return _error_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: _FakeTickResult) -> _FakePlanResult:
        return _plan_result(
            cycle_id=tick_result.payload["cycle_id"],
            source_tick_status="error",
            action="open_recovery_ticket",
        )

    def fake_record(
        plan: _FakePlanResult,
        *,
        diagnostic_id: str,
        observed_at: str,
        root: Path | None = None,
    ) -> _FakeDiagnosticResult:
        assert observed_at == "2026-05-20T10:01:00Z"
        assert root is None
        return _diagnostic_result(
            cycle_id=plan.payload["cycle_id"],
            diagnostic_id=diagnostic_id,
            action=plan.payload["action"],
            severity="error",
            cycle_event_recorded=False,
            blocking_reasons=["tick failure_class is contract-violation"],
        )

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("diagnostic output should not call service for error ticks")

    def fail_dry_run(_plan: _FakePlanResult) -> _FakeDryRunResult:
        raise AssertionError("diagnostic output should not call dry-run executor for error ticks")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_diagnostic", fake_record)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)
    monkeypatch.setattr(cli_autonomous_flow, "dry_run_phase5_scheduler_plan", fail_dry_run)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="diagnostic",
            diagnostic_id="diagnostic-error",
            observed_at="2026-05-20T10:01:00Z",
            apply_closeout=True,
        )
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "open_recovery_ticket"
    assert payload["severity"] == "error"
    assert payload["cycle_event_recorded"] is False
    _assert_no_nested_flow_payload(payload)


def test_phase5_local_cycle_step_diagnostic_smoke_records_real_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    monkeypatch.setattr(cli_module, "init_database", lambda _database_url=None: None)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-20260520-smoke",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "diagnostic",
            "--diagnostic-id",
            "diagnostic-20260520-cli",
            "--observed-at",
            "2026-05-20T10:01:00Z",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    stored = read_phase5_scheduler_diagnostic_artifact(payload["diagnostic_id"], root=artifact_root)
    stored_cycle = read_phase5_cycle_ledger_artifact(payload["cycle_id"], root=artifact_root)
    assert payload["execution_mode"] == "diagnostic_record"
    assert payload["action"] == "continue_tracking"
    assert payload["cycle_event_recorded"] is True
    assert stored.observed_at == "2026-05-20T10:01:00Z"
    assert stored.scheduler_action == "continue_tracking"
    assert PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT in stored_cycle.event_refs
    _assert_no_nested_flow_payload(payload)


def test_phase5_local_cycle_step_diagnostic_smoke_records_missing_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(cli_module, "init_database", lambda _database_url=None: None)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-missing-diagnostic",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "diagnostic",
            "--diagnostic-id",
            "diagnostic-missing-cli",
            "--observed-at",
            "2026-05-20T10:01:00Z",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    stored = read_phase5_scheduler_diagnostic_artifact(payload["diagnostic_id"], root=artifact_root)
    assert payload["action"] == "open_recovery_ticket"
    assert payload["severity"] == "error"
    assert payload["cycle_event_recorded"] is False
    assert stored.cycle_id == "cycle-missing-diagnostic"
    assert stored.scheduler_action == "open_recovery_ticket"
    _assert_no_nested_flow_payload(payload)
