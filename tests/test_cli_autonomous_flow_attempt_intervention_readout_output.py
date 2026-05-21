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


def test_attempt_intervention_readout_output_reads_recorded_runs_without_scheduler_handlers(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    for artifact in [
        _intervention_run(intervention_run_id="run-old", issued_at="2026-05-21T09:00:00Z"),
        _intervention_run(intervention_run_id="run-new", issued_at="2026-05-21T10:00:00Z", execution_status="blocked", applied_output="none"),
    ]:
        write_phase5_scheduler_attempt_intervention_run_artifact(artifact, root=artifact_root)
    before_files = _files_under(artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-readout",
            "--runner-id",
            "runner-ce1",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-intervention-readout",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["total_runs"] == 2
    assert payload["latest_intervention_run_id"] == "run-new"
    assert payload["latest_execution_status"] == "blocked"
    assert payload["latest_blocked_run_id"] == "run-new"
    assert payload["latest_applied_run_id"] == "run-old"
    assert payload["readout_status"] == "blocked"
    assert _files_under(artifact_root) == before_files


def test_attempt_intervention_readout_output_handles_empty_store(tmp_path: Path, monkeypatch, capsys) -> None:
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
            "attempt-run-intervention-readout",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["total_runs"] == 0
    assert payload["latest_intervention_run_id"] is None
    assert payload["readout_status"] == "degraded"
    assert payload["intervention_run_refs"] == []
    assert not artifact_root.exists()


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-intervention-readout must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _intervention_run(**overrides) -> Phase5SchedulerAttemptInterventionRunArtifact:
    payload = {
        "intervention_run_id": "intervention-run-ce1",
        "cycle_id": "cycle-readout",
        "runner_id": "runner-ce1",
        "issued_at": "2026-05-21T09:00:00Z",
        "execution_status": "applied",
        "applied_output": "diagnostic",
        "action": "open_recovery_ticket",
        "diagnostic_id": "diagnostic-ce1",
        "observed_at": "2026-05-21T09:00:00Z",
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


def _files_under(root: Path) -> tuple[str, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
