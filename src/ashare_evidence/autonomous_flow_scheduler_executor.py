from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_plan import (
    Phase5SchedulerAction,
    Phase5SchedulerFollowupPlan,
)

Phase5SchedulerExecutionMode = Literal["dry_run"]
Phase5SchedulerExecutionStatus = Literal["planned", "blocked"]


class Phase5SchedulerDryRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    execution_mode: Phase5SchedulerExecutionMode = "dry_run"
    execution_status: Phase5SchedulerExecutionStatus
    planned_action: Phase5SchedulerAction
    would_execute: bool = False
    planned_effects: list[str] = Field(default_factory=list)
    reason: str
    blocking_reasons: list[str] = Field(default_factory=list)


def dry_run_phase5_scheduler_plan(
    plan: Phase5SchedulerFollowupPlan,
) -> Phase5SchedulerDryRunResult:
    return Phase5SchedulerDryRunResult(
        cycle_id=plan.cycle_id,
        execution_status="blocked" if plan.plan_status == "blocked" else "planned",
        planned_action=plan.action,
        planned_effects=_dedupe(_planned_effects_for_action(plan.action)),
        reason=_sanitize_reason(plan.reason),
        blocking_reasons=_dedupe([_sanitize_reason(reason) for reason in plan.blocking_reasons]),
    )


def _planned_effects_for_action(action: Phase5SchedulerAction) -> list[str]:
    if action == "continue_tracking":
        return ["keep_cycle_open_for_next_tick"]
    if action == "rebuild_projection":
        return ["schedule_projection_rebuild"]
    if action == "retry_failed_step":
        return ["schedule_retry"]
    if action == "open_recovery_ticket":
        return ["prepare_recovery_ticket"]
    if action == "block_cycle":
        return ["mark_cycle_blocked"]
    if action == "redesign":
        return ["schedule_redesign_review"]
    return ["no_op"]


def _sanitize_reason(reason: str) -> str:
    sanitized = re.sub(r"sha256:[A-Za-z0-9._:-]+", "[redacted-digest]", reason)
    return re.sub(r"release-manifest:[^\s,'\"}]+", "[redacted-release-manifest-ref]", sanitized)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
