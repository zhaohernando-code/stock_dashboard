from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_status import Phase5ClaimCeiling, Phase5NextAction, Phase5SummaryStatus
from ashare_evidence.autonomous_flow_tick import (
    Phase5LocalCycleTickRecoveryAction,
    Phase5LocalCycleTickResult,
    Phase5LocalCycleTickStatus,
)

Phase5SchedulerPlanStatus = Literal["ready", "blocked"]
Phase5SchedulerAction = Literal[
    "continue_tracking",
    "rebuild_projection",
    "retry_failed_step",
    "open_recovery_ticket",
    "block_cycle",
    "redesign",
    "none",
]


class Phase5SchedulerFollowupPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    plan_status: Phase5SchedulerPlanStatus
    action: Phase5SchedulerAction
    reason: str
    source_tick_status: Phase5LocalCycleTickStatus
    summary_status: Phase5SummaryStatus
    claim_ceiling: Phase5ClaimCeiling | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


def plan_phase5_scheduler_followup(
    tick_result: Phase5LocalCycleTickResult,
) -> Phase5SchedulerFollowupPlan:
    if tick_result.tick_status == "ok":
        return _plan_ok_tick(tick_result)
    return _plan_error_tick(tick_result)


def _plan_ok_tick(tick_result: Phase5LocalCycleTickResult) -> Phase5SchedulerFollowupPlan:
    status = tick_result.status
    if status is None:
        return _plan(
            tick_result=tick_result,
            plan_status="blocked",
            action="block_cycle",
            reason="ok tick is missing its typed status projection",
            claim_ceiling=None,
            blocking_reasons=["typed status projection is missing"],
        )

    if tick_result.summary_status == "blocked" or tick_result.recommended_next_action == "blocked":
        return _plan(
            tick_result=tick_result,
            plan_status="blocked",
            action="block_cycle",
            reason=_sanitize_reason(status.decision_reason),
            claim_ceiling=status.claim_ceiling,
            blocking_reasons=_status_blocking_reasons(tick_result),
        )

    return _plan(
        tick_result=tick_result,
        plan_status="ready",
        action=_action_for_ok_next_action(tick_result.recommended_next_action),
        reason=_sanitize_reason(status.decision_reason),
        claim_ceiling=status.claim_ceiling,
        blocking_reasons=_status_blocking_reasons(tick_result),
    )


def _plan_error_tick(tick_result: Phase5LocalCycleTickResult) -> Phase5SchedulerFollowupPlan:
    error = tick_result.error
    if error is None:
        return _plan(
            tick_result=tick_result,
            plan_status="blocked",
            action="block_cycle",
            reason="error tick is missing its typed error payload",
            claim_ceiling=None,
            blocking_reasons=["typed error payload is missing"],
        )

    action = _action_for_recovery_action(error.recommended_recovery_action)
    return _plan(
        tick_result=tick_result,
        plan_status="blocked" if action == "block_cycle" else "ready",
        action=action,
        reason=(
            "tick failed with "
            f"failure_class={error.failure_class}; "
            f"recommended_recovery_action={error.recommended_recovery_action}"
        ),
        claim_ceiling=None,
        blocking_reasons=[f"tick failure_class is {error.failure_class}"],
    )


def _plan(
    *,
    tick_result: Phase5LocalCycleTickResult,
    plan_status: Phase5SchedulerPlanStatus,
    action: Phase5SchedulerAction,
    reason: str,
    claim_ceiling: Phase5ClaimCeiling | None,
    blocking_reasons: list[str],
) -> Phase5SchedulerFollowupPlan:
    return Phase5SchedulerFollowupPlan(
        cycle_id=tick_result.cycle_id,
        plan_status=plan_status,
        action=action,
        reason=reason,
        source_tick_status=tick_result.tick_status,
        summary_status=tick_result.summary_status,
        claim_ceiling=claim_ceiling,
        blocking_reasons=_dedupe(blocking_reasons),
    )


def _action_for_ok_next_action(next_action: Phase5NextAction) -> Phase5SchedulerAction:
    if next_action == "blocked":
        return "block_cycle"
    if next_action == "continue_tracking":
        return "continue_tracking"
    if next_action == "rebuild_projection":
        return "rebuild_projection"
    if next_action == "retry_failed_step":
        return "retry_failed_step"
    if next_action == "redesign":
        return "redesign"
    return "none"


def _action_for_recovery_action(recovery_action: Phase5LocalCycleTickRecoveryAction) -> Phase5SchedulerAction:
    if recovery_action == "open_recovery_ticket":
        return "open_recovery_ticket"
    if recovery_action == "retry_with_backoff":
        return "retry_failed_step"
    return "block_cycle"


def _status_blocking_reasons(tick_result: Phase5LocalCycleTickResult) -> list[str]:
    status = tick_result.status
    if status is None:
        return []

    reasons = list(status.blocking_reasons)
    if status.missing_refs:
        reasons.append("required input artifact reference is missing")
    return [_sanitize_reason(reason) for reason in reasons]


def _sanitize_reason(reason: str) -> str:
    sanitized = re.sub(r"sha256:[A-Za-z0-9._:-]+", "[redacted-digest]", reason)
    return re.sub(r"release-manifest:[^\s,'\"}]+", "[redacted-release-manifest-ref]", sanitized)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
