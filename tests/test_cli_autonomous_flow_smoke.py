from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers_cli_autonomous_flow_smoke import (
    _assert_no_nested_scheduler_payload,
    _assert_no_sensitive_service_payload,
    _guard_init_database,
    _run_cli_tick,
    _write_happy_path_artifacts,
)


def test_phase5_local_cycle_step_default_smoke_reads_real_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_tick(artifact_root=artifact_root)

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-20260520-smoke"
    assert payload["tick_status"] == "ok"
    assert payload["exit_code"] == 0
    assert payload["error"] is None
    assert payload["recommended_next_action"] == "continue_tracking"
    assert payload["summary_status"] == "completed"
    assert payload["status"]["cycle_id"] == "cycle-20260520-smoke"
    assert payload["status"]["decision_status"] == "completed"
    assert payload["status"]["summary_status"] == "completed"
    assert payload["status"]["publish_verification_status"] == "present"
    assert payload["status"]["staleness_status"] == "fresh"
    _assert_no_sensitive_service_payload(payload)


def test_phase5_local_cycle_step_default_smoke_missing_cycle_returns_tick_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_tick(artifact_root=artifact_root, cycle_id="cycle-missing-smoke")

    assert exit_code == 1
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-missing-smoke"
    assert payload["tick_status"] == "error"
    assert payload["exit_code"] == 1
    assert payload["status"] is None
    assert payload["recommended_next_action"] == "retry_failed_step"
    assert payload["summary_status"] == "degraded"
    assert payload["error"]["error_type"] == "Phase5RunnerInputResolutionError"
    assert payload["error"]["failure_class"] == "artifact-missing"
    assert payload["error"]["recommended_recovery_action"] == "open_recovery_ticket"
    _assert_no_sensitive_service_payload(payload)


def test_phase5_local_cycle_step_plan_smoke_reads_real_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_tick(artifact_root=artifact_root, output="plan")

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-20260520-smoke"
    assert payload["plan_status"] == "ready"
    assert payload["action"] == "continue_tracking"
    assert payload["source_tick_status"] == "ok"
    assert payload["summary_status"] == "completed"
    assert payload["claim_ceiling"] == "paper_tracking_candidate"
    assert payload["blocking_reasons"] == []
    assert "status" not in payload
    assert "error" not in payload
    _assert_no_sensitive_service_payload(payload)


def test_phase5_local_cycle_step_plan_smoke_missing_cycle_returns_recovery_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_tick(
        artifact_root=artifact_root,
        cycle_id="cycle-missing-smoke",
        output="plan",
    )

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-missing-smoke"
    assert payload["plan_status"] == "ready"
    assert payload["action"] == "open_recovery_ticket"
    assert payload["source_tick_status"] == "error"
    assert payload["summary_status"] == "degraded"
    assert payload["claim_ceiling"] is None
    assert payload["blocking_reasons"] == ["tick failure_class is artifact-missing"]
    assert "status" not in payload
    assert "error" not in payload
    _assert_no_sensitive_service_payload(payload)


@pytest.mark.parametrize(
    (
        "cycle_id",
        "write_artifacts",
        "planned_action",
        "planned_effects",
        "blocking_reasons",
    ),
    [
        (
            "cycle-20260520-smoke",
            True,
            "continue_tracking",
            ["keep_cycle_open_for_next_tick"],
            [],
        ),
        (
            "cycle-missing-smoke",
            False,
            "open_recovery_ticket",
            ["prepare_recovery_ticket"],
            ["tick failure_class is artifact-missing"],
        ),
    ],
)
def test_phase5_local_cycle_step_dry_run_smoke_reads_real_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cycle_id: str,
    write_artifacts: bool,
    planned_action: str,
    planned_effects: list[str],
    blocking_reasons: list[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    if write_artifacts:
        _write_happy_path_artifacts(artifact_root)
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_tick(
        artifact_root=artifact_root,
        cycle_id=cycle_id,
        output="dry-run",
    )

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == cycle_id
    assert payload["execution_mode"] == "dry_run"
    assert payload["execution_status"] == "planned"
    assert payload["planned_action"] == planned_action
    assert payload["planned_effects"] == planned_effects
    assert payload["blocking_reasons"] == blocking_reasons
    _assert_no_nested_scheduler_payload(payload)
