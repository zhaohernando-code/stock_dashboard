from __future__ import annotations

from ashare_evidence.scheduler_attempt_run_intervention_followup_policy import (
    decide_phase5_scheduler_attempt_intervention_followup,
)
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    Phase5SchedulerAttemptInterventionRunReadout,
)
from ashare_evidence.scheduler_attempt_run_recovery_ticket_intent import (
    build_phase5_scheduler_recovery_ticket_intent,
)


def test_recovery_ticket_intent_ready_after_applied_diagnostic() -> None:
    readout = _readout()
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)

    intent = build_phase5_scheduler_recovery_ticket_intent(readout, decision)

    assert intent.intent_status == "ready"
    assert intent.ticket_id
    assert intent.ticket_id.startswith("recovery-ticket-cycle-cg1-")
    assert intent.cycle_id == "cycle-cg1"
    assert intent.failed_step == "replay_schedule"
    assert intent.failure_class == "contract_violation"
    assert intent.failure_observed_at == "2026-05-21T10:00:00Z"
    assert intent.recovery_action == "open_followup_cycle"
    assert intent.final_status == "degraded"
    assert intent.claim_ceiling_effect == "unchanged"
    assert intent.evidence_refs == [
        "phase5_scheduler_diagnostic:diagnostic-cg1",
        "phase5_scheduler_attempt_intervention_run:intervention-run-cg1",
    ]
    assert intent.required_arguments == ("cycle_id", "diagnostic_id", "failure_observed_at")
    assert intent.missing_arguments == ()


def test_recovery_ticket_intent_is_stable_for_same_readout() -> None:
    readout = _readout()
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)

    first = build_phase5_scheduler_recovery_ticket_intent(readout, decision)
    second = build_phase5_scheduler_recovery_ticket_intent(readout, decision)

    assert first.ticket_id == second.ticket_id


def test_recovery_ticket_intent_skips_when_followup_does_not_require_ticket() -> None:
    readout = _readout(total_runs=0)
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)

    intent = build_phase5_scheduler_recovery_ticket_intent(readout, decision)

    assert intent.intent_status == "skipped"
    assert intent.ticket_id is None
    assert intent.required_arguments == ()
    assert intent.missing_arguments == ()


def test_recovery_ticket_intent_blocks_when_ticket_arguments_are_missing() -> None:
    readout = _readout(latest_diagnostic_id=None)
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)

    intent = build_phase5_scheduler_recovery_ticket_intent(readout, decision)

    assert intent.intent_status == "blocked"
    assert intent.ticket_id is None
    assert intent.required_arguments == ("cycle_id", "diagnostic_id", "failure_observed_at")
    assert intent.missing_arguments == ("diagnostic_id",)
    assert intent.blocking_reasons == ["missing required recovery ticket argument: diagnostic_id"]


def _readout(**overrides) -> Phase5SchedulerAttemptInterventionRunReadout:
    payload = {
        "cycle_id": "cycle-cg1",
        "runner_id": "runner-cg1",
        "total_runs": 1,
        "latest_intervention_run_id": "intervention-run-cg1",
        "latest_execution_status": "applied",
        "latest_applied_output": "diagnostic",
        "latest_issued_at": "2026-05-21T10:00:00Z",
        "latest_diagnostic_id": "diagnostic-cg1",
        "latest_source_run_id": "attempt-run-blocked",
        "applied_count": 1,
        "blocked_count": 0,
        "skipped_count": 0,
        "latest_blocked_run_id": None,
        "latest_applied_run_id": "intervention-run-cg1",
        "readout_status": "current",
        "intervention_run_refs": ["intervention-run-cg1"],
    }
    if overrides.get("total_runs") == 0:
        payload.update(
            {
                "cycle_id": None,
                "runner_id": None,
                "latest_intervention_run_id": None,
                "latest_execution_status": None,
                "latest_applied_output": None,
                "latest_issued_at": None,
                "latest_diagnostic_id": None,
                "latest_source_run_id": None,
                "applied_count": 0,
                "latest_applied_run_id": None,
                "readout_status": "degraded",
                "intervention_run_refs": [],
            }
        )
    payload.update(overrides)
    return Phase5SchedulerAttemptInterventionRunReadout(**payload)
