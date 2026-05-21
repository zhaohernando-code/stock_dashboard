from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import PHASE5_RECOVERY_RECORDED_EVENT, start_phase5_cycle
from ashare_evidence.autonomous_flow_artifacts import Phase5RecoveryTicketArtifact
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    read_phase5_recovery_ticket_artifact,
    write_phase5_recovery_ticket_artifact,
)
from ashare_evidence.scheduler_attempt_run_recovery_ticket_executor import (
    apply_phase5_scheduler_recovery_ticket_intent,
)
from ashare_evidence.scheduler_attempt_run_recovery_ticket_intent import (
    Phase5SchedulerRecoveryTicketIntent,
)


def test_recovery_ticket_apply_records_ready_intent(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ch1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )

    result = apply_phase5_scheduler_recovery_ticket_intent(_intent(), root=tmp_path)

    stored_ticket = read_phase5_recovery_ticket_artifact("recovery-ticket-cycle-ch1-a1", root=tmp_path)
    stored_cycle = read_phase5_cycle_ledger_artifact("cycle-ch1", root=tmp_path)
    assert result.apply_status == "recorded"
    assert result.ticket_id == "recovery-ticket-cycle-ch1-a1"
    assert result.recovery_ticket_artifact == stored_ticket
    assert result.cycle_recovery_ticket_refs == ["recovery-ticket-cycle-ch1-a1"]
    assert stored_cycle.recovery_ticket_refs == ["recovery-ticket-cycle-ch1-a1"]
    assert stored_cycle.event_refs.count(PHASE5_RECOVERY_RECORDED_EVENT) == 1


def test_recovery_ticket_apply_is_idempotent_for_recorded_ticket(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ch1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )

    first = apply_phase5_scheduler_recovery_ticket_intent(_intent(), root=tmp_path)
    second = apply_phase5_scheduler_recovery_ticket_intent(_intent(), root=tmp_path)

    stored_cycle = read_phase5_cycle_ledger_artifact("cycle-ch1", root=tmp_path)
    assert first.apply_status == "recorded"
    assert second.apply_status == "already_recorded"
    assert stored_cycle.recovery_ticket_refs == ["recovery-ticket-cycle-ch1-a1"]
    assert stored_cycle.event_refs.count(PHASE5_RECOVERY_RECORDED_EVENT) == 1


def test_recovery_ticket_apply_blocks_when_cycle_is_missing(tmp_path: Path) -> None:
    result = apply_phase5_scheduler_recovery_ticket_intent(_intent(), root=tmp_path)

    assert result.apply_status == "blocked"
    assert result.recovery_ticket_artifact is None
    assert result.blocking_reasons == ["cycle ledger not found: cycle-ch1"]


def test_recovery_ticket_apply_skips_skipped_intent(tmp_path: Path) -> None:
    result = apply_phase5_scheduler_recovery_ticket_intent(
        _intent(intent_status="skipped", ticket_id=None),
        root=tmp_path,
    )

    assert result.apply_status == "skipped"
    assert result.ticket_id is None


def test_recovery_ticket_apply_blocks_existing_conflict(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ch1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    write_phase5_recovery_ticket_artifact(
        _ticket(notes="different existing content"),
        root=tmp_path,
    )

    result = apply_phase5_scheduler_recovery_ticket_intent(_intent(), root=tmp_path)

    assert result.apply_status == "blocked"
    assert result.blocking_reasons == [
        "existing recovery ticket conflicts with intent: recovery-ticket-cycle-ch1-a1"
    ]


def _intent(**overrides) -> Phase5SchedulerRecoveryTicketIntent:
    payload = {
        "intent_status": "ready",
        "ticket_id": "recovery-ticket-cycle-ch1-a1",
        "cycle_id": "cycle-ch1",
        "failure_observed_at": "2026-05-21T10:00:00Z",
        "evidence_refs": [
            "phase5_scheduler_diagnostic:diagnostic-ch1",
            "phase5_scheduler_attempt_intervention_run:intervention-run-ch1",
        ],
        "notes": "scheduler recovery ticket intent built from intervention diagnostic",
        "source_intervention_run_id": "intervention-run-ch1",
        "source_diagnostic_id": "diagnostic-ch1",
        "required_arguments": ("cycle_id", "diagnostic_id", "failure_observed_at"),
    }
    payload.update(overrides)
    return Phase5SchedulerRecoveryTicketIntent(**payload)


def _ticket(**overrides) -> Phase5RecoveryTicketArtifact:
    payload = {
        "ticket_id": "recovery-ticket-cycle-ch1-a1",
        "cycle_id": "cycle-ch1",
        "failed_step": "replay_schedule",
        "failure_class": "contract_violation",
        "failure_observed_at": "2026-05-21T10:00:00Z",
        "evidence_refs": [
            "phase5_scheduler_diagnostic:diagnostic-ch1",
            "phase5_scheduler_attempt_intervention_run:intervention-run-ch1",
        ],
        "recovery_action": "open_followup_cycle",
        "retry_count": 0,
        "final_status": "degraded",
        "claim_ceiling_effect": "unchanged",
        "notes": "scheduler recovery ticket intent built from intervention diagnostic",
    }
    payload.update(overrides)
    return Phase5RecoveryTicketArtifact(**payload)
