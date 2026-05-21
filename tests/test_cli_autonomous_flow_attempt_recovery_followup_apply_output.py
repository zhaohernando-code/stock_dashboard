from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_attempt_recovery_followup_apply_output_starts_cycle(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_ticket(artifact_root)

    exit_code = _run_apply(artifact_root, created_at="2026-05-21T10:05:00Z")

    payload = json.loads(capsys.readouterr().out)
    stored = read_phase5_cycle_ledger_artifact(payload["followup_cycle_id"], root=artifact_root)
    assert exit_code == 0
    assert payload["apply_status"] == "started"
    assert stored.trigger == "recovery_followup"
    assert stored.scope["source_ticket_id"] == "ticket-cj-cli"


def test_attempt_recovery_followup_apply_output_is_idempotent(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_ticket(artifact_root)

    _run_apply(artifact_root, created_at="2026-05-21T10:05:00Z")
    capsys.readouterr()
    second_exit = _run_apply(artifact_root, created_at="2026-05-21T10:05:00Z")

    payload = json.loads(capsys.readouterr().out)
    assert second_exit == 0
    assert payload["apply_status"] == "already_started"


def test_attempt_recovery_followup_apply_output_blocks_without_created_at(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    _record_ticket(artifact_root)

    exit_code = _run_apply(artifact_root, created_at=None)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert payload["apply_status"] == "blocked"
    assert payload["blocking_reasons"] == ["missing required follow-up cycle field: created_at"]


def _run_apply(artifact_root: Path, *, created_at: str | None) -> int:
    args = [
        "phase5-local-cycle-step",
        "--cycle-id",
        "cycle-cj-cli",
        "--artifact-root",
        str(artifact_root),
        "--output",
        "attempt-run-recovery-followup-apply",
    ]
    if created_at:
        args.extend(["--created-at", created_at])
    return cli_module.main(args)


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-recovery-followup-apply must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _record_ticket(root: Path):
    start_phase5_cycle(
        cycle_id="cycle-cj-cli",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    return record_phase5_recovery_ticket(
        cycle_id="cycle-cj-cli",
        ticket_id="ticket-cj-cli",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cj-cli"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
