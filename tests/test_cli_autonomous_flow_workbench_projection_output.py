from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.scheduler_auto_progress_artifact_store import (
    write_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_workbench_projection_output_reads_projection_manifest(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_cycle_and_ticket(artifact_root)
    write_phase5_scheduler_auto_progress_run_artifact(_run(), root=artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-co-cli",
            "--runner-id",
            "runner-co-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-workbench-projection",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["projection_name"] == "phase5_operations_workbench"
    assert payload["projection_status"] == "degraded"
    assert payload["cycle"]["cycle_id"] == "cycle-co-cli"
    assert payload["recovery"]["latest_ticket_id"] == "ticket-co-cli"
    assert payload["auto_progress"]["latest_run_id"] == "auto-progress-run-co-cli"


def test_workbench_projection_output_blocks_missing_cycle(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "missing-cycle",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-workbench-projection",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert payload["projection_status"] == "blocked"
    assert payload["missing_refs"] == ["phase5_cycle_ledger:missing-cycle"]


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-workbench-projection must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _record_cycle_and_ticket(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-co-cli",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-co-cli",
        ticket_id="ticket-co-cli",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-co-cli"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )


def _run(**overrides) -> Phase5SchedulerAutoProgressRunArtifact:
    payload = {
        "auto_progress_run_id": "auto-progress-run-co-cli",
        "cycle_id": "cycle-co-cli",
        "runner_id": "runner-co-cli",
        "issued_at": "2026-05-21T10:10:00Z",
        "plan_status": "ready",
        "phase": "recovery_followup_apply",
        "apply_status": "applied",
        "applied_output": "followup_cycle",
        "recommended_output": "attempt-run-recovery-followup-apply",
        "recommended_flags": [],
        "required_arguments": ["created_at"],
        "missing_arguments": [],
        "blocking_reasons": [],
        "evidence_refs": ["phase5_scheduler_diagnostic:diagnostic-co-cli"],
        "result_refs": ["phase5_cycle_ledger:followup-cycle-co-cli"],
        "notes": "recovery follow-up cycle started from intent",
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAutoProgressRunArtifact(**payload)
