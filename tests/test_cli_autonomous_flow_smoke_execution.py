from __future__ import annotations

import json
from pathlib import Path

import pytest

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
