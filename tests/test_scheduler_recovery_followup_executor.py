from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_recovery_followup_executor import (
    apply_phase5_scheduler_recovery_followup_intent,
)
from ashare_evidence.scheduler_recovery_followup_intent import (
    read_phase5_scheduler_recovery_followup_intent,
)


def test_recovery_followup_apply_starts_ready_followup_cycle(tmp_path: Path) -> None:
    intent = _ready_intent(tmp_path)

    result = apply_phase5_scheduler_recovery_followup_intent(
        intent,
        created_at="2026-05-21T10:05:00Z",
        root=tmp_path,
    )

    stored = read_phase5_cycle_ledger_artifact(result.followup_cycle_id, root=tmp_path)
    assert result.apply_status == "started"
    assert stored.trigger == "recovery_followup"
    assert stored.started_at == "2026-05-21T10:05:00Z"
    assert stored.scope == {
        "source_cycle_id": "cycle-cj1",
        "source_ticket_id": "ticket-cj1",
        "source_ticket_ref": "phase5_recovery_ticket:ticket-cj1",
        "source_evidence_refs": [
            "phase5_recovery_ticket:ticket-cj1",
            "phase5_scheduler_diagnostic:diagnostic-cj1",
        ],
    }


def test_recovery_followup_apply_is_idempotent(tmp_path: Path) -> None:
    intent = _ready_intent(tmp_path)

    first = apply_phase5_scheduler_recovery_followup_intent(
        intent,
        created_at="2026-05-21T10:05:00Z",
        root=tmp_path,
    )
    second = apply_phase5_scheduler_recovery_followup_intent(
        intent,
        created_at="2026-05-21T10:05:00Z",
        root=tmp_path,
    )

    assert first.apply_status == "started"
    assert second.apply_status == "already_started"
    assert second.followup_cycle == first.followup_cycle


def test_recovery_followup_apply_blocks_missing_created_at(tmp_path: Path) -> None:
    intent = _ready_intent(tmp_path)

    result = apply_phase5_scheduler_recovery_followup_intent(intent, created_at=None, root=tmp_path)

    assert result.apply_status == "blocked"
    assert result.blocking_reasons == ["missing required follow-up cycle field: created_at"]


def test_recovery_followup_apply_skips_skipped_intent(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cj1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    intent = read_phase5_scheduler_recovery_followup_intent(cycle_id="cycle-cj1", root=tmp_path)

    result = apply_phase5_scheduler_recovery_followup_intent(
        intent,
        created_at="2026-05-21T10:05:00Z",
        root=tmp_path,
    )

    assert result.apply_status == "skipped"
    assert result.followup_cycle_id is None


def _ready_intent(root: Path):
    start_phase5_cycle(
        cycle_id="cycle-cj1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-cj1",
        ticket_id="ticket-cj1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cj1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
    return read_phase5_scheduler_recovery_followup_intent(cycle_id="cycle-cj1", root=root)
