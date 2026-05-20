from __future__ import annotations

import json
from pathlib import Path

import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.research_artifact_store import (
    read_phase5_scheduler_diagnostic_artifact,
)
from tests.helpers_cli_autonomous_flow_smoke import (
    _assert_no_nested_scheduler_payload,
    _guard_init_database,
    _write_happy_path_artifacts,
)


def test_action_route_auto_apply_smoke_happy_path_skips_without_scheduler_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    before_files = _files_under(artifact_root)
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_auto_apply(
        artifact_root=artifact_root,
        cycle_id="cycle-20260520-smoke",
        attempt_id="attempt-happy-smoke",
        issued_at="2026-05-20T10:01:00Z",
    )

    assert exit_code == 0
    assert init_database_calls == []
    assert _files_under(artifact_root) == before_files
    assert _scheduler_files_under(artifact_root) == ()
    payload = json.loads(capsys.readouterr().out)
    assert payload["route_type"] == "wait_for_next_tick"
    assert payload["execution_status"] == "skipped"
    assert payload["preflight_status"] == "ready"
    assert payload["applied_output"] == "none"
    assert payload["execution_id"] is None
    assert payload["idempotency_key"] is None
    assert payload["cycle_event_recorded"] is False
    _assert_no_nested_scheduler_payload(payload)


def test_action_route_auto_apply_smoke_missing_cycle_records_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_auto_apply(
        artifact_root=artifact_root,
        cycle_id="cycle-missing-auto-apply-smoke",
        attempt_id="attempt-recovery-smoke",
        issued_at="2026-05-20T10:02:00Z",
    )

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    diagnostic_id = payload["diagnostic_id"]
    assert payload["route_type"] == "diagnostic_output"
    assert payload["execution_status"] == "applied"
    assert payload["preflight_status"] == "ready"
    assert payload["applied_output"] == "diagnostic"
    assert diagnostic_id.startswith(
        "diagnostic-cycle-missing-auto-apply-smoke-open_recovery_ticket-"
        "attempt-recovery-smoke-"
    )
    assert payload["execution_id"] is None
    assert payload["idempotency_key"] is None
    assert payload["cycle_event_recorded"] is False
    diagnostic = read_phase5_scheduler_diagnostic_artifact(diagnostic_id, root=artifact_root)
    assert diagnostic.cycle_id == "cycle-missing-auto-apply-smoke"
    assert diagnostic.observed_at == "2026-05-20T10:02:00Z"
    assert diagnostic.scheduler_action == "open_recovery_ticket"
    assert diagnostic.severity == "error"
    assert diagnostic.failure_class == "execution-precondition-failed"
    assert diagnostic.recommended_recovery_action == "open_recovery_ticket"
    assert _execution_files_under(artifact_root) == ()
    _assert_no_nested_scheduler_payload(payload)


@pytest.mark.parametrize(
    ("attempt_id", "issued_at", "missing_arguments"),
    [
        (None, "2026-05-20T10:03:00Z", ["attempt_id"]),
        ("attempt-fail-closed-smoke", None, ["diagnostic_id", "observed_at"]),
    ],
)
def test_action_route_auto_apply_smoke_fail_closed_missing_scheduler_binding_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    attempt_id: str | None,
    issued_at: str | None,
    missing_arguments: list[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = _run_cli_auto_apply(
        artifact_root=artifact_root,
        cycle_id="cycle-missing-auto-apply-smoke",
        attempt_id=attempt_id,
        issued_at=issued_at,
    )

    assert exit_code == 4
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_status"] == "blocked"
    assert payload["preflight_status"] == "blocked"
    assert payload["applied_output"] == "none"
    assert payload["missing_arguments"] == missing_arguments
    _assert_no_nested_scheduler_payload(payload)


def _run_cli_auto_apply(
    *,
    artifact_root: Path,
    cycle_id: str,
    attempt_id: str | None,
    issued_at: str | None,
) -> int:
    argv = [
        "phase5-local-cycle-step",
        "--cycle-id",
        cycle_id,
        "--artifact-root",
        str(artifact_root),
        "--output",
        "action-route-auto-apply",
    ]
    if attempt_id is not None:
        argv.extend(["--attempt-id", attempt_id])
    if issued_at is not None:
        argv.extend(["--issued-at", issued_at])
    return cli_module.main(argv)


def _scheduler_files_under(root: Path) -> tuple[str, ...]:
    return tuple(path for path in _files_under(root) if path.startswith("autonomous_flow/phase5_scheduler_"))


def _execution_files_under(root: Path) -> tuple[str, ...]:
    return tuple(path for path in _files_under(root) if "/phase5_scheduler_execution_" in f"/{path}")


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
