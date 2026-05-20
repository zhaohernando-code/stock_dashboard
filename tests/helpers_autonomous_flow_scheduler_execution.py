from __future__ import annotations

from pathlib import Path

from ashare_evidence.autonomous_flow import start_phase5_cycle
from ashare_evidence.autonomous_flow_artifacts import Phase5SchedulerExecutionLedgerArtifact


def _execution_ledger(
    *,
    execution_id: str,
    idempotency_key: str | None = None,
    cycle_id: str | None = "phase5-20260521-am",
    notes: str = "",
) -> Phase5SchedulerExecutionLedgerArtifact:
    return Phase5SchedulerExecutionLedgerArtifact(
        execution_id=execution_id,
        idempotency_key=idempotency_key or f"idempotency:{execution_id}",
        cycle_id=cycle_id,
        created_at="2026-05-21T09:00:00Z",
        plan_action="retry_failed_step",
        execution_status="planned",
        would_execute=False,
        diagnostic_refs=["diagnostic-1"],
        blocking_reasons=[],
        notes=notes,
    )


def _start_cycle(root: Path, cycle_id: str):
    return start_phase5_cycle(
        cycle_id=cycle_id,
        trigger="scheduled",
        started_at="2026-05-21T09:00:00Z",
        status="running",
        next_action="retry_failed_step",
        root=root,
    )
