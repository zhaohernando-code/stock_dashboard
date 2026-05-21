from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.scheduler_attempt_run_artifact_store import write_phase5_scheduler_attempt_run_artifact
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_attempt_followup_decision_output_recommends_recovery_for_blocked_latest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)
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
            "cycle-decision",
            "--runner-id",
            "runner-bz1",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-followup-decision",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert init_database_calls == []
    assert payload["decision_status"] == "ready"
    assert payload["recommended_action"] == "open_recovery_ticket"
    assert payload["reason_code"] == "latest_attempt_blocked"
    assert payload["source_latest_run_id"] == "run-blocked"


def test_attempt_followup_decision_output_handles_empty_store(tmp_path: Path, monkeypatch, capsys) -> None:
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-empty",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--output",
            "attempt-run-followup-decision",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["recommended_action"] == "continue_tracking"
    assert payload["reason_code"] == "no_attempt_runs_recorded"
    assert payload["source_latest_run_id"] is None
    assert payload["source_total_runs"] == 0


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-followup-decision must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _attempt_run(**overrides) -> Phase5SchedulerAttemptRunArtifact:
    payload = {
        "run_id": "run-bz1",
        "attempt_id": "attempt-bz1",
        "cycle_id": "cycle-decision",
        "runner_id": "runner-bz1",
        "issued_at": "2026-05-21T09:00:00Z",
        "attempt_status": "ready",
        "route_type": "execution_output",
        "preflight_status": "ready",
        "apply_status": "applied",
        "applied_output": "execution",
        "required_arguments": ["execution_id", "idempotency_key", "created_at"],
        "missing_arguments": [],
        "diagnostic_id": None,
        "execution_id": "execution-bz1",
        "idempotency_key": "cycle:cycle-decision:retry_failed_step",
        "cycle_event_recorded": True,
        "reason": "captured scheduler attempt route apply result",
        "error_type": None,
        "blocking_reasons": [],
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunArtifact(**payload)
