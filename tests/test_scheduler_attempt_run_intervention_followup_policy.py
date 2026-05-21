from __future__ import annotations

from ashare_evidence.scheduler_attempt_run_intervention_followup_policy import (
    decide_phase5_scheduler_attempt_intervention_followup,
)
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    Phase5SchedulerAttemptInterventionRunReadout,
)


def test_intervention_followup_recommends_tracking_for_empty_readout() -> None:
    decision = decide_phase5_scheduler_attempt_intervention_followup(_readout(total_runs=0))

    assert decision.decision_status == "ready"
    assert decision.recommended_action == "continue_tracking"
    assert decision.reason_code == "no_intervention_runs_recorded"
    assert decision.source_total_runs == 0
    assert decision.confidence == "medium"


def test_intervention_followup_recommends_recovery_ticket_after_applied_diagnostic() -> None:
    decision = decide_phase5_scheduler_attempt_intervention_followup(_readout())

    assert decision.decision_status == "ready"
    assert decision.recommended_action == "open_recovery_ticket"
    assert decision.reason_code == "latest_intervention_applied_diagnostic"
    assert decision.source_latest_intervention_run_id == "intervention-run-cf1"
    assert decision.source_latest_diagnostic_id == "diagnostic-cf1"
    assert decision.confidence == "high"


def test_intervention_followup_recommends_retry_for_blocked_latest() -> None:
    decision = decide_phase5_scheduler_attempt_intervention_followup(
        _readout(latest_execution_status="blocked", latest_applied_output="none")
    )

    assert decision.recommended_action == "retry_failed_step"
    assert decision.reason_code == "latest_intervention_blocked"
    assert decision.blocking_reasons == ["latest intervention run is blocked: intervention-run-cf1"]
    assert decision.confidence == "medium"


def test_intervention_followup_recommends_tracking_for_skipped_latest() -> None:
    decision = decide_phase5_scheduler_attempt_intervention_followup(
        _readout(latest_execution_status="skipped", latest_applied_output="none")
    )

    assert decision.recommended_action == "continue_tracking"
    assert decision.reason_code == "latest_intervention_skipped"
    assert decision.confidence == "medium"


def _readout(**overrides) -> Phase5SchedulerAttemptInterventionRunReadout:
    payload = {
        "cycle_id": "cycle-cf1",
        "runner_id": "runner-cf1",
        "total_runs": 1,
        "latest_intervention_run_id": "intervention-run-cf1",
        "latest_execution_status": "applied",
        "latest_applied_output": "diagnostic",
        "latest_issued_at": "2026-05-21T10:00:00Z",
        "latest_diagnostic_id": "diagnostic-cf1",
        "latest_source_run_id": "attempt-run-blocked",
        "applied_count": 1,
        "blocked_count": 0,
        "skipped_count": 0,
        "latest_blocked_run_id": None,
        "latest_applied_run_id": "intervention-run-cf1",
        "readout_status": "current",
        "intervention_run_refs": ["intervention-run-cf1"],
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
