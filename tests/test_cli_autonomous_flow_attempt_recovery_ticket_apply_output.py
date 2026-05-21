from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import start_phase5_cycle
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    read_phase5_recovery_ticket_artifact,
    read_phase5_recovery_ticket_artifact_if_exists,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    write_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_attempt_recovery_ticket_apply_output_records_ticket(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    start_phase5_cycle(
        cycle_id="cycle-ch-cli",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=artifact_root,
    )
    write_phase5_scheduler_attempt_intervention_run_artifact(_intervention_run(), root=artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-ch-cli",
            "--runner-id",
            "runner-ch-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-recovery-ticket-apply",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    ticket_id = payload["ticket_id"]
    stored_ticket = read_phase5_recovery_ticket_artifact(ticket_id, root=artifact_root)
    stored_cycle = read_phase5_cycle_ledger_artifact("cycle-ch-cli", root=artifact_root)
    assert exit_code == 0
    assert payload["apply_status"] == "recorded"
    assert stored_ticket.ticket_id == ticket_id
    assert stored_cycle.recovery_ticket_refs == [ticket_id]


def test_attempt_recovery_ticket_apply_output_is_idempotent(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    start_phase5_cycle(
        cycle_id="cycle-ch-cli",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=artifact_root,
    )
    write_phase5_scheduler_attempt_intervention_run_artifact(_intervention_run(), root=artifact_root)

    _run_apply(artifact_root)
    capsys.readouterr()
    second_exit = _run_apply(artifact_root)

    payload = json.loads(capsys.readouterr().out)
    stored_cycle = read_phase5_cycle_ledger_artifact("cycle-ch-cli", root=artifact_root)
    assert second_exit == 0
    assert payload["apply_status"] == "already_recorded"
    assert stored_cycle.recovery_ticket_refs == [payload["ticket_id"]]


def test_attempt_recovery_ticket_apply_output_blocks_missing_cycle(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    write_phase5_scheduler_attempt_intervention_run_artifact(_intervention_run(), root=artifact_root)

    exit_code = _run_apply(artifact_root)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert payload["apply_status"] == "blocked"
    assert payload["blocking_reasons"] == ["cycle ledger not found: cycle-ch-cli"]
    assert read_phase5_recovery_ticket_artifact_if_exists(payload["ticket_id"], root=artifact_root) is None


def _run_apply(artifact_root: Path) -> int:
    return cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-ch-cli",
            "--runner-id",
            "runner-ch-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-recovery-ticket-apply",
        ]
    )


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-recovery-ticket-apply must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _intervention_run(**overrides) -> Phase5SchedulerAttemptInterventionRunArtifact:
    payload = {
        "intervention_run_id": "intervention-run-ch-cli",
        "cycle_id": "cycle-ch-cli",
        "runner_id": "runner-ch-cli",
        "issued_at": "2026-05-21T10:00:00Z",
        "execution_status": "applied",
        "applied_output": "diagnostic",
        "action": "open_recovery_ticket",
        "diagnostic_id": "diagnostic-ch-cli",
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
