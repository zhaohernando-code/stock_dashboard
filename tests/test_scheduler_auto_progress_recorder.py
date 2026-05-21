from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.scheduler_auto_progress_artifact_store import (
    read_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_executor import apply_phase5_scheduler_auto_progress_step
from ashare_evidence.scheduler_auto_progress_recorder import (
    record_phase5_scheduler_auto_progress_run_artifact,
)


def test_auto_progress_recorder_writes_run_artifact(tmp_path: Path) -> None:
    _record_ticket(tmp_path)
    result = apply_phase5_scheduler_auto_progress_step(
        cycle_id="cycle-cm1",
        runner_id="runner-cm1",
        created_at="2026-05-21T10:10:00Z",
        root=tmp_path,
    )

    recorded = record_phase5_scheduler_auto_progress_run_artifact(
        result,
        runner_id="runner-cm1",
        issued_at="2026-05-21T10:11:00Z",
        auto_progress_run_id="auto-progress-run-cm1",
        root=tmp_path,
    )

    stored = read_phase5_scheduler_auto_progress_run_artifact("auto-progress-run-cm1", root=tmp_path)
    assert recorded.artifact == stored
    assert stored.plan_status == "ready"
    assert stored.phase == "recovery_followup_apply"
    assert stored.apply_status == "applied"
    assert stored.applied_output == "followup_cycle"
    assert stored.result_refs == [f"phase5_cycle_ledger:{result.result_payload['recovery_followup_apply_result']['followup_cycle_id']}"]


def _record_ticket(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cm1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-cm1",
        ticket_id="ticket-cm1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cm1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
