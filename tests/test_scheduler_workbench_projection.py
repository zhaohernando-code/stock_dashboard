from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.scheduler_auto_progress_artifact_store import (
    write_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact
from ashare_evidence.scheduler_workbench_projection import read_phase5_workbench_projection_manifest


def test_workbench_projection_combines_cycle_recovery_and_auto_progress(tmp_path: Path) -> None:
    _record_cycle_and_ticket(tmp_path)
    write_phase5_scheduler_auto_progress_run_artifact(_run(), root=tmp_path)

    projection = read_phase5_workbench_projection_manifest(
        cycle_id="cycle-co1",
        runner_id="runner-co1",
        root=tmp_path,
    )

    assert projection.projection_status == "degraded"
    assert projection.cycle.cycle_id == "cycle-co1"
    assert projection.cycle.cycle_status == "degraded"
    assert projection.recovery.latest_ticket_id == "ticket-co1"
    assert projection.recovery.recovery_action == "open_followup_cycle"
    assert projection.auto_progress.total_runs == 1
    assert projection.auto_progress.latest_phase == "recovery_followup_apply"
    assert projection.auto_progress.result_refs == ["phase5_cycle_ledger:followup-cycle-co1"]
    assert projection.source_refs == [
        "phase5_cycle_ledger:cycle-co1",
        "auto-progress-run-co1",
        "phase5_recovery_ticket:ticket-co1",
    ]
    assert projection.recommended_next_action == "continue_tracking"


def test_workbench_projection_blocks_missing_cycle(tmp_path: Path) -> None:
    projection = read_phase5_workbench_projection_manifest(cycle_id="missing-cycle", root=tmp_path)

    assert projection.projection_status == "blocked"
    assert projection.cycle.cycle_id == "missing-cycle"
    assert projection.missing_refs == ["phase5_cycle_ledger:missing-cycle"]
    assert projection.blocking_reasons == ["cycle ledger not found: missing-cycle"]
    assert projection.recommended_next_action == "blocked"


def test_workbench_projection_degrades_empty_auto_progress_history(tmp_path: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-co1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )

    projection = read_phase5_workbench_projection_manifest(cycle_id="cycle-co1", root=tmp_path)

    assert projection.projection_status == "degraded"
    assert projection.auto_progress.total_runs == 0
    assert projection.auto_progress.readout_status == "degraded"
    assert projection.recommended_next_action == "run_auto_progress_plan"


def test_workbench_projection_blocks_missing_ticket_ref(tmp_path: Path) -> None:
    cycle = start_phase5_cycle(
        cycle_id="cycle-co1",
        trigger="manual",
        started_at="2026-05-21T10:00:00Z",
        root=tmp_path,
    )
    from ashare_evidence.research_artifact_store import write_phase5_cycle_ledger_artifact

    write_phase5_cycle_ledger_artifact(cycle.model_copy(update={"recovery_ticket_refs": ["missing-ticket"]}), root=tmp_path)
    write_phase5_scheduler_auto_progress_run_artifact(_run(), root=tmp_path)

    projection = read_phase5_workbench_projection_manifest(cycle_id="cycle-co1", root=tmp_path)

    assert projection.projection_status == "blocked"
    assert projection.missing_refs == ["phase5_recovery_ticket:missing-ticket"]
    assert projection.recommended_next_action == "inspect_blocking_reasons"


def _record_cycle_and_ticket(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-co1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-co1",
        ticket_id="ticket-co1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-co1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )


def _run(**overrides) -> Phase5SchedulerAutoProgressRunArtifact:
    payload = {
        "auto_progress_run_id": "auto-progress-run-co1",
        "cycle_id": "cycle-co1",
        "runner_id": "runner-co1",
        "issued_at": "2026-05-21T10:10:00Z",
        "plan_status": "ready",
        "phase": "recovery_followup_apply",
        "apply_status": "applied",
        "applied_output": "followup_cycle",
        "recommended_output": "attempt-run-recovery-followup-apply",
        "recommended_flags": [],
        "required_arguments": ["created_at"],
        "missing_arguments": [],
        "blocking_reasons": [],
        "evidence_refs": ["phase5_scheduler_diagnostic:diagnostic-co1"],
        "result_refs": ["phase5_cycle_ledger:followup-cycle-co1"],
        "notes": "recovery follow-up cycle started from intent",
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAutoProgressRunArtifact(**payload)
