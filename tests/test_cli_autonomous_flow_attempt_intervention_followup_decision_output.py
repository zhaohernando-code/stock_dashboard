from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    write_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_attempt_intervention_followup_decision_output_recommends_recovery_ticket_after_diagnostic(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    write_phase5_scheduler_attempt_intervention_run_artifact(_intervention_run(), root=artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-followup",
            "--runner-id",
            "runner-cf1",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-intervention-followup-decision",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["decision_status"] == "ready"
    assert payload["recommended_action"] == "open_recovery_ticket"
    assert payload["reason_code"] == "latest_intervention_applied_diagnostic"
    assert payload["source_latest_diagnostic_id"] == "diagnostic-cf1"


def test_attempt_intervention_followup_decision_output_handles_empty_store(tmp_path: Path, monkeypatch, capsys) -> None:
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
            "attempt-run-intervention-followup-decision",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["recommended_action"] == "continue_tracking"
    assert payload["reason_code"] == "no_intervention_runs_recorded"
    assert payload["source_total_runs"] == 0
    assert not artifact_root.exists()


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-intervention-followup-decision must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _intervention_run(**overrides) -> Phase5SchedulerAttemptInterventionRunArtifact:
    payload = {
        "intervention_run_id": "intervention-run-cf1",
        "cycle_id": "cycle-followup",
        "runner_id": "runner-cf1",
        "issued_at": "2026-05-21T10:00:00Z",
        "execution_status": "applied",
        "applied_output": "diagnostic",
        "action": "open_recovery_ticket",
        "diagnostic_id": "diagnostic-cf1",
        "observed_at": "2026-05-21T10:00:00Z",
        "required_arguments": ["cycle_id", "diagnostic_id", "observed_at"],
        "missing_arguments": [],
        "cycle_event_recorded": True,
        "source_latest_run_id": "attempt-run-blocked",
        "reason": "attempt-run intervention diagnostic recorded",
        "error_type": None,
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptInterventionRunArtifact(**payload)
