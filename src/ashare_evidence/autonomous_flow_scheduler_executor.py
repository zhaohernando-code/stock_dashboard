from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow import record_phase5_scheduler_diagnostic
from ashare_evidence.autonomous_flow_scheduler_action_contract import get_phase5_scheduler_action_contract
from ashare_evidence.autonomous_flow_scheduler_execution_executor import (
    Phase5SchedulerExecutionRecordResult as Phase5SchedulerExecutionRecordResult,
)
from ashare_evidence.autonomous_flow_scheduler_execution_executor import (
    record_phase5_scheduler_plan_execution as record_phase5_scheduler_plan_execution,
)
from ashare_evidence.autonomous_flow_scheduler_plan import (
    Phase5SchedulerAction,
    Phase5SchedulerFollowupPlan,
)

Phase5SchedulerExecutionMode = Literal["dry_run"]
Phase5SchedulerExecutionStatus = Literal["planned", "blocked"]
Phase5SchedulerDiagnosticExecutionMode = Literal["diagnostic_record"]
Phase5SchedulerDiagnosticExecutionStatus = Literal["recorded"]
Phase5SchedulerDiagnosticSeverity = Literal["info", "warning", "error", "blocked"]
Phase5SchedulerDiagnosticFailureClass = Literal[
    "blocked-plan",
    "execution-precondition-failed",
    "none",
]
Phase5SchedulerDiagnosticRecoveryAction = Literal[
    "open_recovery_ticket",
    "retry_with_backoff",
    "block_cycle",
    "none",
]


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


class Phase5SchedulerDiagnosticRecordResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    diagnostic_id: str
    execution_mode: Phase5SchedulerDiagnosticExecutionMode = "diagnostic_record"
    execution_status: Phase5SchedulerDiagnosticExecutionStatus = "recorded"
    action: Phase5SchedulerAction
    severity: Phase5SchedulerDiagnosticSeverity
    diagnostic_recorded: bool = True
    cycle_event_recorded: bool
    reason: str
    blocking_reasons: list[str] = Field(default_factory=list)


def dry_run_phase5_scheduler_plan(
    plan: Phase5SchedulerFollowupPlan,
) -> Phase5SchedulerDryRunResult:
    return Phase5SchedulerDryRunResult(
        cycle_id=plan.cycle_id,
        execution_status="blocked" if plan.plan_status == "blocked" else "planned",
        planned_action=plan.action,
        planned_effects=_dedupe(list(get_phase5_scheduler_action_contract(plan.action).planned_effects)),
        reason=_sanitize_reason(plan.reason),
        blocking_reasons=_dedupe([_sanitize_reason(reason) for reason in plan.blocking_reasons]),
    )

def record_phase5_scheduler_plan_diagnostic(
    plan: Phase5SchedulerFollowupPlan,
    *,
    diagnostic_id: str,
    observed_at: str,
    root: Path | None = None,
) -> Phase5SchedulerDiagnosticRecordResult:
    severity = _diagnostic_severity_for_plan(plan)
    blocking_reasons = _dedupe([_sanitize_diagnostic_text(reason) for reason in plan.blocking_reasons])
    reason = _sanitize_diagnostic_text(plan.reason)
    cycle, _diagnostic = record_phase5_scheduler_diagnostic(
        diagnostic_id=diagnostic_id,
        cycle_id=plan.cycle_id,
        observed_at=observed_at,
        scheduler_action=plan.action,
        severity=severity,
        failure_class=_diagnostic_failure_class_for_plan(plan),
        recommended_recovery_action=_diagnostic_recovery_action_for_plan(plan.action),
        blocking_reasons=blocking_reasons,
        notes=reason,
        root=root,
    )
    return Phase5SchedulerDiagnosticRecordResult(
        cycle_id=plan.cycle_id,
        diagnostic_id=diagnostic_id,
        action=plan.action,
        severity=severity,
        cycle_event_recorded=cycle is not None,
        reason=reason,
        blocking_reasons=blocking_reasons,
    )


def _diagnostic_severity_for_plan(plan: Phase5SchedulerFollowupPlan) -> Phase5SchedulerDiagnosticSeverity:
    if plan.plan_status == "blocked" or plan.action == "block_cycle":
        return "blocked"
    if plan.action in {"open_recovery_ticket", "retry_failed_step"}:
        return "error"
    if plan.action in {"rebuild_projection", "redesign"}:
        return "warning"
    return "info"


def _diagnostic_recovery_action_for_plan(
    action: Phase5SchedulerAction,
) -> Phase5SchedulerDiagnosticRecoveryAction:
    if action == "open_recovery_ticket":
        return "open_recovery_ticket"
    if action == "retry_failed_step":
        return "retry_with_backoff"
    if action == "block_cycle":
        return "block_cycle"
    return "none"


def _diagnostic_failure_class_for_plan(
    plan: Phase5SchedulerFollowupPlan,
) -> Phase5SchedulerDiagnosticFailureClass:
    if plan.plan_status == "blocked" or plan.action == "block_cycle":
        return "blocked-plan"
    if plan.action in {"open_recovery_ticket", "retry_failed_step", "rebuild_projection", "redesign"}:
        return "execution-precondition-failed"
    return "none"


def _sanitize_reason(reason: str) -> str:
    sanitized = re.sub(r"sha256:[A-Za-z0-9._:-]+", "[redacted-digest]", reason)
    return re.sub(r"release-manifest:[^\s,'\"}]+", "[redacted-release-manifest-ref]", sanitized)


def _sanitize_diagnostic_text(value: str) -> str:
    sanitized = _sanitize_reason(value)
    if any(token in sanitized for token in ("input_bundle", "runner_result", "Traceback")):
        return "[redacted sensitive diagnostic detail]"
    return sanitized


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
