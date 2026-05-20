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
from tests.helpers_cli_autonomous_flow_smoke import (
    _assert_diagnostic_smoke_recorded,
    _run_cli_diagnostic,
    _write_happy_path_artifacts,
)


@pytest.mark.parametrize(
    ("diagnostic_id", "observed_at", "missing_arguments"),
    [
        (None, None, ["--diagnostic-id", "--observed-at"]),
        (None, "2026-05-20T10:00:00Z", ["--diagnostic-id"]),
        ("diagnostic-1", None, ["--observed-at"]),
    ],
)
def test_phase5_local_cycle_step_diagnostic_requires_explicit_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    diagnostic_id: str | None,
    observed_at: str | None,
    missing_arguments: list[str],
) -> None:
    def fail_tick(**_kwargs: Any) -> _FakeTickResult:
        raise AssertionError("diagnostic argument validation should happen before tick")

    def fail_service(**_kwargs: Any) -> _FakeServiceResult:
        raise AssertionError("diagnostic output should not call service")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_tick)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_service)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(output="diagnostic", diagnostic_id=diagnostic_id, observed_at=observed_at)
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["error_type"] == "MissingRequiredDiagnosticArgument"
    assert payload["message"] == "--diagnostic-id and --observed-at are required for diagnostic output."
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


@pytest.mark.parametrize(
    "case",
    [
        ("cycle-20260520-smoke", "diagnostic-20260520-cli", True, "continue_tracking", "info", True),
        ("cycle-missing-diagnostic", "diagnostic-missing-cli", False, "open_recovery_ticket", "error", False),
    ],
)
def test_phase5_local_cycle_step_diagnostic_smoke_records_real_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: tuple[str, str, bool, str, str, bool],
) -> None:
    cycle_id, diagnostic_id, write_artifacts, action, severity, cycle_event_recorded = case
    artifact_root = tmp_path / "artifacts"
    if write_artifacts:
        _write_happy_path_artifacts(artifact_root)
    monkeypatch.setattr(cli_module, "init_database", lambda _database_url=None: None)

    exit_code = _run_cli_diagnostic(
        artifact_root=artifact_root,
        cycle_id=cycle_id,
        diagnostic_id=diagnostic_id,
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    _assert_diagnostic_smoke_recorded(
        payload=payload,
        artifact_root=artifact_root,
        cycle_id=cycle_id,
        expected_action=action,
        expected_severity=severity,
        expected_cycle_event_recorded=cycle_event_recorded,
    )
    _assert_no_nested_flow_payload(payload)
