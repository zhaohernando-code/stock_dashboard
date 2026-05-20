from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow import record_phase5_scheduler_execution_ledger
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction, Phase5SchedulerFollowupPlan

Phase5SchedulerLedgerExecutionMode = Literal["ledger_record"]
Phase5SchedulerLedgerExecutionStatus = Literal["planned", "skipped", "blocked"]


class Phase5SchedulerExecutionRecordResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    execution_id: str
    idempotency_key: str
    execution_mode: Phase5SchedulerLedgerExecutionMode = "ledger_record"
    execution_status: Phase5SchedulerLedgerExecutionStatus
    action: Phase5SchedulerAction
    would_execute: bool = False
    ledger_recorded: bool = True
    cycle_event_recorded: bool
    reason: str
    blocking_reasons: list[str] = Field(default_factory=list)
    diagnostic_refs: list[str] = Field(default_factory=list)


def record_phase5_scheduler_plan_execution(
    plan: Phase5SchedulerFollowupPlan,
    *,
    execution_id: str,
    idempotency_key: str,
    created_at: str,
    diagnostic_refs: list[str] | None = None,
    root: Path | None = None,
) -> Phase5SchedulerExecutionRecordResult:
    execution_status = _execution_status_for_plan(plan)
    blocking_reasons = _dedupe([_sanitize_execution_text(reason) for reason in plan.blocking_reasons])
    reason = _sanitize_execution_text(plan.reason)
    cycle, ledger = record_phase5_scheduler_execution_ledger(
        execution_id=execution_id,
        idempotency_key=idempotency_key,
        cycle_id=plan.cycle_id,
        created_at=created_at,
        plan_action=plan.action,
        execution_status=execution_status,
        would_execute=False,
        diagnostic_refs=_dedupe(diagnostic_refs or []),
        blocking_reasons=blocking_reasons,
        notes=reason,
        root=root,
    )
    return Phase5SchedulerExecutionRecordResult(
        cycle_id=plan.cycle_id,
        execution_id=ledger.execution_id,
        idempotency_key=ledger.idempotency_key,
        execution_status=ledger.execution_status,
        action=ledger.plan_action,
        cycle_event_recorded=cycle is not None,
        reason=ledger.notes,
        blocking_reasons=ledger.blocking_reasons,
        diagnostic_refs=ledger.diagnostic_refs,
    )


def _execution_status_for_plan(plan: Phase5SchedulerFollowupPlan) -> Phase5SchedulerLedgerExecutionStatus:
    if plan.plan_status == "blocked" or plan.action == "block_cycle":
        return "blocked"
    if plan.action == "none":
        return "skipped"
    return "planned"


def _sanitize_execution_text(value: str) -> str:
    sanitized = re.sub(r"sha256:[A-Za-z0-9._:-]+", "[redacted-digest]", value)
    sanitized = re.sub(r"release-manifest:[^\s,'\"}]+", "[redacted-release-manifest-ref]", sanitized)
    if any(token in sanitized for token in ("input_bundle", "runner_result", "Traceback")):
        return "[redacted sensitive diagnostic detail]"
    return sanitized


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
