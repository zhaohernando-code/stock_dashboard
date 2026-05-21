from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_attempt_run_artifact_store import write_phase5_scheduler_attempt_run_artifact
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact
from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    read_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_executor import apply_phase5_scheduler_auto_progress_step


def test_auto_progress_apply_records_intervention_run_for_blocked_attempt(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cl1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(attempt_status="blocked", apply_status="blocked"),
        root=tmp_path,
    )

    result = apply_phase5_scheduler_auto_progress_step(
        cycle_id="cycle-cl1",
        runner_id="runner-cl1",
        issued_at="2026-05-21T10:05:00Z",
        intervention_run_id="intervention-run-cl1",
        root=tmp_path,
    )

    stored = read_phase5_scheduler_attempt_intervention_run_artifact("intervention-run-cl1", root=tmp_path)
    assert result.apply_status == "applied"
    assert result.applied_output == "intervention_run"
    assert result.plan.phase == "intervention_apply"
    assert stored.execution_status == "applied"
    assert stored.applied_output == "diagnostic"


def test_auto_progress_apply_blocks_when_plan_missing_arguments(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cl1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(attempt_status="blocked", apply_status="blocked"),
        root=tmp_path,
    )

    result = apply_phase5_scheduler_auto_progress_step(cycle_id="cycle-cl1", runner_id="runner-cl1", root=tmp_path)

    assert result.apply_status == "blocked"
    assert result.applied_output == "none"
    assert result.blocking_reasons == ["missing required auto-progress argument: issued_at"]


def test_auto_progress_apply_starts_followup_cycle(tmp_path: Path) -> None:
    _record_ticket(tmp_path)

    result = apply_phase5_scheduler_auto_progress_step(
        cycle_id="cycle-cl1",
        runner_id="runner-cl1",
        created_at="2026-05-21T10:10:00Z",
        root=tmp_path,
    )

    payload = result.result_payload["recovery_followup_apply_result"]
    stored = read_phase5_cycle_ledger_artifact(payload["followup_cycle_id"], root=tmp_path)
    assert result.apply_status == "applied"
    assert result.applied_output == "followup_cycle"
    assert stored.trigger == "recovery_followup"
    assert stored.scope["source_ticket_id"] == "ticket-cl1"


def _record_ticket(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cl1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-cl1",
        ticket_id="ticket-cl1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cl1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )


def _attempt_run(**overrides) -> Phase5SchedulerAttemptRunArtifact:
    payload = {
        "run_id": "run-cl1",
        "attempt_id": "attempt-cl1",
        "cycle_id": "cycle-cl1",
        "runner_id": "runner-cl1",
        "issued_at": "2026-05-21T10:00:00Z",
        "attempt_status": "ready",
        "route_type": "execution_output",
        "preflight_status": "ready",
        "apply_status": "applied",
        "applied_output": "execution",
        "required_arguments": ["execution_id", "idempotency_key", "created_at"],
        "missing_arguments": [],
        "diagnostic_id": None,
        "execution_id": "execution-cl1",
        "idempotency_key": "cycle:cycle-cl1:retry_failed_step",
        "cycle_event_recorded": True,
        "reason": "captured scheduler attempt route apply result",
        "error_type": None,
        "blocking_reasons": [],
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunArtifact(**payload)
