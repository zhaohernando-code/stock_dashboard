from __future__ import annotations

import inspect

import ashare_evidence.scheduler_attempt_run_intervention_plan as intervention_plan
from ashare_evidence.scheduler_attempt_run_followup_policy import (
    decide_phase5_scheduler_attempt_run_followup,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import (
    plan_phase5_scheduler_attempt_run_intervention,
)
from ashare_evidence.scheduler_attempt_run_readout import Phase5SchedulerAttemptRunReadout


def test_intervention_plan_records_recovery_diagnostic_for_blocked_latest() -> None:
    readout = _readout(
        latest_run_id="run-blocked",
        latest_apply_status="blocked",
        latest_attempt_status="blocked",
        blocked_count=1,
        staleness_status="blocked",
    )
    decision = decide_phase5_scheduler_attempt_run_followup(readout)

    plan = plan_phase5_scheduler_attempt_run_intervention(readout, decision)

    assert plan.plan_status == "ready"
    assert plan.action == "open_recovery_ticket"
    assert plan.next_step == "record_recovery_diagnostic"
    assert plan.execution_boundary == "route_apply_required"
    assert plan.planned_side_effect == "scheduler_diagnostic"
    assert plan.reason_code == "latest_attempt_blocked"
    assert plan.source_latest_run_id == "run-blocked"
    assert plan.source_latest_issued_at == "2026-05-21T12:00:00Z"
    assert plan.required_arguments == ("cycle_id", "diagnostic_id", "observed_at")
    assert plan.missing_arguments == ()
    assert plan.blocking_reasons == ["latest attempt run is blocked: run-blocked"]


def test_intervention_plan_waits_for_empty_readout() -> None:
    readout = _readout(total_runs=0)
    decision = decide_phase5_scheduler_attempt_run_followup(readout)

    plan = plan_phase5_scheduler_attempt_run_intervention(readout, decision)

    assert plan.cycle_id is None
    assert plan.runner_id is None
    assert plan.plan_status == "ready"
    assert plan.action == "continue_tracking"
    assert plan.next_step == "wait_for_next_tick"
    assert plan.execution_boundary == "observe_only"
    assert plan.planned_side_effect == "none"
    assert plan.reason_code == "no_attempt_runs_recorded"
    assert plan.required_arguments == ()
    assert plan.missing_arguments == ()


def test_intervention_plan_blocks_unknown_latest_status() -> None:
    readout = _readout(latest_apply_status=None, latest_attempt_status=None, staleness_status="degraded")
    decision = decide_phase5_scheduler_attempt_run_followup(readout)

    plan = plan_phase5_scheduler_attempt_run_intervention(readout, decision)

    assert plan.plan_status == "blocked"
    assert plan.action == "block_cycle"
    assert plan.next_step == "block_cycle"
    assert plan.execution_boundary == "blocked"
    assert plan.planned_side_effect == "cycle_block"
    assert plan.reason_code == "latest_attempt_status_unknown"
    assert plan.required_arguments == ("cycle_id",)
    assert plan.missing_arguments == ()
    assert plan.blocking_reasons == ["latest attempt run status is unavailable"]


def test_intervention_plan_blocks_recovery_when_cycle_id_is_missing() -> None:
    readout = _readout(
        cycle_id=None,
        latest_run_id="run-blocked",
        latest_apply_status="blocked",
        latest_attempt_status="blocked",
        blocked_count=1,
        staleness_status="blocked",
    )
    decision = decide_phase5_scheduler_attempt_run_followup(readout)

    plan = plan_phase5_scheduler_attempt_run_intervention(readout, decision)

    assert plan.plan_status == "blocked"
    assert plan.execution_boundary == "blocked"
    assert plan.missing_arguments == ("cycle_id",)
    assert "missing required intervention argument: cycle_id" in plan.blocking_reasons


def test_intervention_plan_module_has_no_runtime_io_clock_random_or_artifact_writes() -> None:
    source = inspect.getsource(intervention_plan)

    for token in ("datetime", "time.", "random", "Path(", "open(", "mkdir(", "write_"):
        assert token not in source


def _readout(**overrides) -> Phase5SchedulerAttemptRunReadout:
    payload = {
        "cycle_id": "cycle-cb1",
        "runner_id": "runner-cb1",
        "total_runs": 1,
        "latest_run_id": "run-cb1",
        "latest_apply_status": "applied",
        "latest_attempt_status": "ready",
        "latest_issued_at": "2026-05-21T12:00:00Z",
        "applied_count": 1,
        "blocked_count": 0,
        "skipped_count": 0,
        "latest_blocked_run_id": None,
        "latest_applied_run_id": "run-cb1",
        "staleness_status": "current",
        "run_refs": ["run-cb1"],
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
