from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_attempt_recovery_followup_intent_output_reads_latest_ticket(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_ticket(artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-ci-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-recovery-followup-intent",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["intent_status"] == "ready"
    assert payload["next_action"] == "open_followup_cycle"
    assert payload["followup_cycle_id"].startswith("recovery-followup-cycle-ci-cli-")
    assert payload["source_ticket_ref"] == "phase5_recovery_ticket:ticket-ci-cli"


def test_attempt_recovery_followup_intent_output_skips_without_ticket_refs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    start_phase5_cycle(
        cycle_id="cycle-ci-cli",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=artifact_root,
    )

    exit_code = _run_followup_intent(artifact_root)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["intent_status"] == "skipped"
    assert payload["next_action"] == "continue_tracking"


def test_attempt_recovery_followup_intent_output_blocks_missing_cycle(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)

    exit_code = _run_followup_intent(artifact_root)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert payload["intent_status"] == "blocked"
    assert payload["blocking_reasons"] == ["cycle ledger not found: cycle-ci-cli"]


def _run_followup_intent(artifact_root: Path) -> int:
    return cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-ci-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-recovery-followup-intent",
        ]
    )


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-recovery-followup-intent must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _record_ticket(root: Path):
    start_phase5_cycle(
        cycle_id="cycle-ci-cli",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    return record_phase5_recovery_ticket(
        cycle_id="cycle-ci-cli",
        ticket_id="ticket-ci-cli",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-ci-cli"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
