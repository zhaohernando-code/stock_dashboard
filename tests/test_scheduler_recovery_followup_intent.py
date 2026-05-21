from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_recovery_followup_intent import (
    build_phase5_scheduler_recovery_followup_intent,
    read_phase5_scheduler_recovery_followup_intent,
)


def test_recovery_followup_intent_ready_for_open_followup_cycle(tmp_path: Path) -> None:
    _record_ticket(tmp_path)
    cycle = read_phase5_cycle_ledger_artifact("cycle-ci1", root=tmp_path)

    intent = read_phase5_scheduler_recovery_followup_intent(cycle_id="cycle-ci1", root=tmp_path)

    assert intent.intent_status == "ready"
    assert intent.next_action == "open_followup_cycle"
    assert intent.followup_cycle_id
    assert intent.followup_cycle_id.startswith("recovery-followup-cycle-ci1-")
    assert intent.followup_trigger == "recovery_followup"
    assert intent.source_ticket_ref == "phase5_recovery_ticket:ticket-ci1"
    assert intent.evidence_refs == [
        "phase5_recovery_ticket:ticket-ci1",
        "phase5_scheduler_diagnostic:diagnostic-ci1",
    ]
    assert cycle.recovery_ticket_refs == ["ticket-ci1"]


def test_recovery_followup_intent_is_stable(tmp_path: Path) -> None:
    _record_ticket(tmp_path)

    first = read_phase5_scheduler_recovery_followup_intent(cycle_id="cycle-ci1", root=tmp_path)
    second = read_phase5_scheduler_recovery_followup_intent(cycle_id="cycle-ci1", root=tmp_path)

    assert first.followup_cycle_id == second.followup_cycle_id


def test_recovery_followup_intent_skips_without_ticket_refs(tmp_path: Path) -> None:
    cycle = start_phase5_cycle(
        cycle_id="cycle-ci1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )

    intent = build_phase5_scheduler_recovery_followup_intent(cycle, None)

    assert intent.intent_status == "skipped"
    assert intent.next_action == "continue_tracking"
    assert intent.followup_cycle_id is None


def test_recovery_followup_intent_blocks_missing_cycle(tmp_path: Path) -> None:
    intent = read_phase5_scheduler_recovery_followup_intent(cycle_id="missing-cycle", root=tmp_path)

    assert intent.intent_status == "blocked"
    assert intent.next_action == "block_cycle"
    assert intent.blocking_reasons == ["cycle ledger not found: missing-cycle"]


def test_recovery_followup_intent_blocks_missing_ticket_artifact(tmp_path: Path) -> None:
    updated, _ticket = _record_ticket(tmp_path)
    missing_ticket_cycle = updated.model_copy(update={"recovery_ticket_refs": ["missing-ticket"]})

    intent = build_phase5_scheduler_recovery_followup_intent(missing_ticket_cycle, None)

    assert intent.intent_status == "blocked"
    assert intent.ticket_id == "missing-ticket"
    assert intent.blocking_reasons == ["recovery ticket artifact not found: missing-ticket"]


def _record_ticket(root: Path):
    start_phase5_cycle(
        cycle_id="cycle-ci1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    return record_phase5_recovery_ticket(
        cycle_id="cycle-ci1",
        ticket_id="ticket-ci1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-ci1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
