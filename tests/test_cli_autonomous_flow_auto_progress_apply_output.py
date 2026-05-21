from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_auto_progress_apply_output_starts_followup_cycle(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_ticket(artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-cl-cli",
            "--runner-id",
            "runner-cl-cli",
            "--created-at",
            "2026-05-21T10:10:00Z",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-auto-progress-apply",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    apply_payload = payload["result_payload"]["recovery_followup_apply_result"]
    stored = read_phase5_cycle_ledger_artifact(apply_payload["followup_cycle_id"], root=artifact_root)
    assert exit_code == 0
    assert payload["apply_status"] == "applied"
    assert payload["applied_output"] == "followup_cycle"
    assert stored.scope["source_ticket_id"] == "ticket-cl-cli"


def test_auto_progress_apply_output_blocks_missing_created_at(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_ticket(artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-cl-cli",
            "--runner-id",
            "runner-cl-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-auto-progress-apply",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert payload["apply_status"] == "blocked"
    assert payload["blocking_reasons"] == ["missing required auto-progress argument: created_at"]


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-auto-progress-apply must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _record_ticket(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cl-cli",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-cl-cli",
        ticket_id="ticket-cl-cli",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cl-cli"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
