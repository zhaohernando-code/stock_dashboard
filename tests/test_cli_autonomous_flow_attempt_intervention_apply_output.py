from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.research_artifact_store import read_phase5_scheduler_diagnostic_artifact
from ashare_evidence.scheduler_attempt_run_artifact_store import write_phase5_scheduler_attempt_run_artifact
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_attempt_intervention_apply_output_records_diagnostic_for_blocked_latest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _start_cycle(artifact_root, "cycle-intervention")
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(
            run_id="run-blocked",
            issued_at="2026-05-21T10:00:00Z",
            attempt_status="blocked",
            apply_status="blocked",
        ),
        root=artifact_root,
    )

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-intervention",
            "--runner-id",
            "runner-cc1",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-intervention-apply",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostic = read_phase5_scheduler_diagnostic_artifact(payload["diagnostic_id"], root=artifact_root)
    assert exit_code == 0
    assert payload["execution_status"] == "applied"
    assert payload["applied_output"] == "diagnostic"
    assert payload["observed_at"] == "2026-05-21T10:00:00Z"
    assert payload["cycle_event_recorded"] is True
    assert diagnostic.scheduler_action == "open_recovery_ticket"
    assert diagnostic.evidence_refs == ["run-blocked"]


def test_attempt_intervention_apply_output_skips_empty_store_without_writing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-empty",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-intervention-apply",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["execution_status"] == "skipped"
    assert payload["applied_output"] == "none"
    assert not artifact_root.exists()


def test_attempt_intervention_apply_output_records_intervention_run_when_enabled(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _start_cycle(artifact_root, "cycle-intervention")
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(run_id="run-blocked", attempt_status="blocked", apply_status="blocked"),
        root=artifact_root,
    )

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-intervention",
            "--runner-id",
            "runner-cc1",
            "--issued-at",
            "2026-05-21T12:05:00Z",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-intervention-apply",
            "--record-intervention-run",
            "--intervention-run-id",
            "intervention-run-cli",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    artifact = payload["intervention_run_artifact"]
    assert exit_code == 0
    assert payload["intervention_run_record_status"] == "recorded"
    assert payload["apply_result"]["execution_status"] == "applied"
    assert artifact["intervention_run_id"] == "intervention-run-cli"
    assert artifact["runner_id"] == "runner-cc1"
    assert artifact["issued_at"] == "2026-05-21T12:05:00Z"


def test_attempt_intervention_apply_output_record_blocks_missing_context(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-empty",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-intervention-apply",
            "--record-intervention-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["intervention_run_record_status"] == "blocked"
    assert payload["intervention_run_artifact"] is None
    assert payload["intervention_run_record_missing_arguments"] == ["issued_at", "runner_id"]
    assert not artifact_root.exists()


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-intervention-apply must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _attempt_run(**overrides) -> Phase5SchedulerAttemptRunArtifact:
    payload = {
        "run_id": "run-cc1",
        "attempt_id": "attempt-cc1",
        "cycle_id": "cycle-intervention",
        "runner_id": "runner-cc1",
        "issued_at": "2026-05-21T09:00:00Z",
        "attempt_status": "ready",
        "route_type": "execution_output",
        "preflight_status": "ready",
        "apply_status": "applied",
        "applied_output": "execution",
        "required_arguments": ["execution_id", "idempotency_key", "created_at"],
        "missing_arguments": [],
        "diagnostic_id": None,
        "execution_id": "execution-cc1",
        "idempotency_key": "cycle:cycle-intervention:retry_failed_step",
        "cycle_event_recorded": True,
        "reason": "captured scheduler attempt route apply result",
        "error_type": None,
        "blocking_reasons": [],
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunArtifact(**payload)
