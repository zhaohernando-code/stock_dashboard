from __future__ import annotations

from ashare_evidence.scheduler_attempt_run_followup_policy import (
    decide_phase5_scheduler_attempt_run_followup,
)
from ashare_evidence.scheduler_attempt_run_readout import Phase5SchedulerAttemptRunReadout


def test_attempt_run_followup_policy_recommends_tracking_for_empty_readout() -> None:
    decision = decide_phase5_scheduler_attempt_run_followup(_readout(total_runs=0))

    assert decision.decision_status == "ready"
    assert decision.recommended_action == "continue_tracking"
    assert decision.reason_code == "no_attempt_runs_recorded"
    assert decision.source_latest_run_id is None
    assert decision.source_total_runs == 0
    assert decision.blocking_reasons == []
    assert decision.confidence == "medium"


def test_attempt_run_followup_policy_recommends_recovery_for_blocked_latest() -> None:
    decision = decide_phase5_scheduler_attempt_run_followup(
        _readout(
            latest_run_id="run-blocked",
            latest_apply_status="blocked",
            latest_attempt_status="blocked",
            blocked_count=1,
            staleness_status="blocked",
        )
    )

    assert decision.decision_status == "ready"
    assert decision.recommended_action == "open_recovery_ticket"
    assert decision.reason_code == "latest_attempt_blocked"
    assert decision.source_latest_run_id == "run-blocked"
    assert decision.blocking_reasons == ["latest attempt run is blocked: run-blocked"]
    assert decision.confidence == "high"


def test_attempt_run_followup_policy_recommends_tracking_for_applied_latest() -> None:
    decision = decide_phase5_scheduler_attempt_run_followup(_readout(latest_apply_status="applied"))

    assert decision.recommended_action == "continue_tracking"
    assert decision.reason_code == "latest_attempt_applied"
    assert decision.confidence == "high"


def test_attempt_run_followup_policy_recommends_tracking_for_skipped_latest() -> None:
    decision = decide_phase5_scheduler_attempt_run_followup(_readout(latest_apply_status="skipped", skipped_count=1))

    assert decision.recommended_action == "continue_tracking"
    assert decision.reason_code == "latest_attempt_skipped"
    assert decision.confidence == "medium"


def _readout(**overrides) -> Phase5SchedulerAttemptRunReadout:
    payload = {
        "cycle_id": "cycle-by1",
        "runner_id": "runner-by1",
        "total_runs": 1,
        "latest_run_id": "run-by1",
        "latest_apply_status": "applied",
        "latest_attempt_status": "ready",
        "latest_issued_at": "2026-05-21T12:00:00Z",
        "applied_count": 1,
        "blocked_count": 0,
        "skipped_count": 0,
        "latest_blocked_run_id": None,
        "latest_applied_run_id": "run-by1",
        "staleness_status": "current",
        "run_refs": ["run-by1"],
    }
    if overrides.get("total_runs") == 0:
        payload.update(
            {
                "cycle_id": None,
                "runner_id": None,
                "latest_run_id": None,
                "latest_apply_status": None,
                "latest_attempt_status": None,
                "latest_issued_at": None,
                "applied_count": 0,
                "latest_applied_run_id": None,
                "staleness_status": "degraded",
                "run_refs": [],
            }
        )
    payload.update(overrides)
    return Phase5SchedulerAttemptRunReadout(**payload)
