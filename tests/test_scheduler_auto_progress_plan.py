from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.scheduler_attempt_run_artifact_store import write_phase5_scheduler_attempt_run_artifact
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact
from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    write_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)
from ashare_evidence.scheduler_auto_progress_plan import read_phase5_scheduler_auto_progress_plan


def test_auto_progress_plan_recommends_intervention_apply_for_blocked_attempt(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ck1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(attempt_status="blocked", apply_status="blocked"),
        root=tmp_path,
    )

    plan = read_phase5_scheduler_auto_progress_plan(
        cycle_id="cycle-ck1",
        runner_id="runner-ck1",
        issued_at="2026-05-21T10:05:00Z",
        root=tmp_path,
    )

    assert plan.plan_status == "ready"
    assert plan.phase == "intervention_apply"
    assert plan.recommended_output == "attempt-run-intervention-apply"
    assert plan.recommended_flags == ["--record-intervention-run"]
    assert plan.required_arguments == ("issued_at", "runner_id")
    assert plan.missing_arguments == ()
    assert plan.evidence_refs == ["run-ck1"]


def test_auto_progress_plan_blocks_intervention_apply_without_issued_at(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ck1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(attempt_status="blocked", apply_status="blocked"),
        root=tmp_path,
    )

    plan = read_phase5_scheduler_auto_progress_plan(cycle_id="cycle-ck1", runner_id="runner-ck1", root=tmp_path)

    assert plan.plan_status == "blocked"
    assert plan.phase == "intervention_apply"
    assert plan.missing_arguments == ("issued_at",)
    assert plan.blocking_reasons == ["missing required auto-progress argument: issued_at"]


def test_auto_progress_plan_prioritizes_recovery_ticket_apply(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ck1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_intervention_run_artifact(_intervention_run(), root=tmp_path)

    plan = read_phase5_scheduler_auto_progress_plan(cycle_id="cycle-ck1", runner_id="runner-ck1", root=tmp_path)

    assert plan.plan_status == "ready"
    assert plan.phase == "recovery_ticket_apply"
    assert plan.recommended_output == "attempt-run-recovery-ticket-apply"
    assert plan.evidence_refs == [
        "phase5_scheduler_diagnostic:diagnostic-ck1",
        "phase5_scheduler_attempt_intervention_run:intervention-run-ck1",
    ]


def test_auto_progress_plan_prioritizes_recovery_followup_apply(tmp_path: Path) -> None:
    _record_ticket(tmp_path)

    plan = read_phase5_scheduler_auto_progress_plan(
        cycle_id="cycle-ck1",
        runner_id="runner-ck1",
        created_at="2026-05-21T10:10:00Z",
        root=tmp_path,
    )

    assert plan.plan_status == "ready"
    assert plan.phase == "recovery_followup_apply"
    assert plan.recommended_output == "attempt-run-recovery-followup-apply"
    assert plan.required_arguments == ("created_at",)
    assert plan.missing_arguments == ()


def test_auto_progress_plan_blocks_recovery_followup_apply_without_created_at(tmp_path: Path) -> None:
    _record_ticket(tmp_path)

    plan = read_phase5_scheduler_auto_progress_plan(cycle_id="cycle-ck1", runner_id="runner-ck1", root=tmp_path)

    assert plan.plan_status == "blocked"
    assert plan.phase == "recovery_followup_apply"
    assert plan.missing_arguments == ("created_at",)


def _record_ticket(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-ck1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-ck1",
        ticket_id="ticket-ck1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-ck1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )


def _attempt_run(**overrides) -> Phase5SchedulerAttemptRunArtifact:
    payload = {
        "run_id": "run-ck1",
        "attempt_id": "attempt-ck1",
        "cycle_id": "cycle-ck1",
        "runner_id": "runner-ck1",
        "issued_at": "2026-05-21T10:00:00Z",
        "attempt_status": "ready",
        "route_type": "execution_output",
        "preflight_status": "ready",
        "apply_status": "applied",
        "applied_output": "execution",
        "required_arguments": ["execution_id", "idempotency_key", "created_at"],
        "missing_arguments": [],
        "diagnostic_id": None,
        "execution_id": "execution-ck1",
        "idempotency_key": "cycle:cycle-ck1:retry_failed_step",
        "cycle_event_recorded": True,
        "reason": "captured scheduler attempt route apply result",
        "error_type": None,
        "blocking_reasons": [],
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunArtifact(**payload)


def _intervention_run(**overrides) -> Phase5SchedulerAttemptInterventionRunArtifact:
    payload = {
        "intervention_run_id": "intervention-run-ck1",
        "cycle_id": "cycle-ck1",
        "runner_id": "runner-ck1",
        "issued_at": "2026-05-21T10:05:00Z",
        "execution_status": "applied",
        "applied_output": "diagnostic",
        "action": "open_recovery_ticket",
        "diagnostic_id": "diagnostic-ck1",
        "observed_at": "2026-05-21T10:05:00Z",
        "required_arguments": ["cycle_id", "diagnostic_id", "observed_at"],
        "missing_arguments": [],
        "cycle_event_recorded": True,
        "source_latest_run_id": "run-ck1",
        "reason": "attempt-run intervention diagnostic recorded",
        "error_type": None,
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptInterventionRunArtifact(**payload)
