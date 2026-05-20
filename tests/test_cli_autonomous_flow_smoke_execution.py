from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_execution_artifact_store import (
    create_phase5_scheduler_execution_reservation_artifact,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
)
from tests.helpers_cli_autonomous_flow_smoke import (
    _assert_execution_smoke_recorded,
    _assert_no_nested_scheduler_payload,
    _guard_init_database,
    _run_cli_execution,
    _write_happy_path_artifacts,
)


def test_phase5_local_cycle_step_execution_smoke_records_real_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_execution(
        artifact_root=artifact_root,
        cycle_id="cycle-20260520-smoke",
        execution_id="execution-20260520-smoke",
        idempotency_key="idempotency:execution-smoke",
        diagnostic_id="diagnostic-smoke",
    )

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-20260520-smoke"
    assert payload["execution_id"] == "execution-20260520-smoke"
    assert payload["idempotency_key"] == "idempotency:execution-smoke"
    assert payload["diagnostic_refs"] == ["diagnostic-smoke"]
    _assert_execution_smoke_recorded(
        payload=payload,
        artifact_root=artifact_root,
        cycle_id="cycle-20260520-smoke",
        expected_action="continue_tracking",
        expected_status="planned",
        expected_cycle_event_recorded=True,
    )
    _assert_no_nested_scheduler_payload(payload)


def test_phase5_local_cycle_step_execution_smoke_conflict_has_no_requested_ledger_or_cycle_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    before_cycle = read_phase5_cycle_ledger_artifact("cycle-20260520-smoke", root=artifact_root)
    create_phase5_scheduler_execution_reservation_artifact(
        idempotency_key="idempotency:execution-conflict-smoke",
        execution_id="execution-existing-smoke",
        cycle_id="cycle-20260520-smoke",
        created_at="2026-05-20T10:00:00Z",
        root=artifact_root,
    )
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_execution(
        artifact_root=artifact_root,
        cycle_id="cycle-20260520-smoke",
        execution_id="execution-requested-smoke",
        idempotency_key="idempotency:execution-conflict-smoke",
    )

    assert exit_code == 3
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["error_type"] == "Phase5SchedulerExecutionIdempotencyConflictError"
    assert payload["existing_execution_id"] == "execution-existing-smoke"
    assert payload["requested_execution_id"] == "execution-requested-smoke"
    assert payload["recommended_next_action"] == "reuse_existing_execution_id_or_retry_with_new_idempotency_key"
    requested_ledger = read_phase5_scheduler_execution_ledger_artifact_if_exists(
        "execution-requested-smoke",
        root=artifact_root,
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    assert requested_ledger is None
    assert read_phase5_cycle_ledger_artifact("cycle-20260520-smoke", root=artifact_root) == before_cycle
    assert "plan_status" not in serialized
    assert "source_tick_status" not in serialized
    assert "input_bundle" not in serialized
    assert "runner_result" not in serialized


def test_phase5_local_cycle_step_execution_smoke_missing_cycle_records_ledger_without_cycle_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_execution(
        artifact_root=artifact_root,
        cycle_id="cycle-missing-smoke",
        execution_id="execution-missing-smoke",
        idempotency_key="idempotency:execution-missing-smoke",
    )

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-missing-smoke"
    assert payload["execution_id"] == "execution-missing-smoke"
    assert payload["blocking_reasons"] == ["tick failure_class is artifact-missing"]
    _assert_execution_smoke_recorded(
        payload=payload,
        artifact_root=artifact_root,
        cycle_id="cycle-missing-smoke",
        expected_action="open_recovery_ticket",
        expected_status="planned",
        expected_cycle_event_recorded=False,
    )
    _assert_no_nested_scheduler_payload(payload)
