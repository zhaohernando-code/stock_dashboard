from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow import record_phase5_scheduler_diagnostic
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction
from ashare_evidence.scheduler_attempt_run_intervention_diagnostics import (
    phase5_scheduler_attempt_run_intervention_failure_class,
    phase5_scheduler_attempt_run_intervention_recovery_action,
    phase5_scheduler_attempt_run_intervention_severity,
    stable_phase5_scheduler_attempt_run_intervention_diagnostic_id,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import Phase5SchedulerAttemptRunInterventionPlan

AttemptRunInterventionApplyStatus = Literal["applied", "blocked", "skipped"]
AttemptRunInterventionAppliedOutput = Literal["none", "diagnostic"]


class Phase5SchedulerAttemptRunInterventionApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str | None = None
    execution_status: AttemptRunInterventionApplyStatus
    applied_output: AttemptRunInterventionAppliedOutput
    action: Phase5SchedulerAction
    diagnostic_id: str | None = None
    observed_at: str | None = None
    required_arguments: tuple[str, ...] = Field(default_factory=tuple)
    missing_arguments: tuple[str, ...] = Field(default_factory=tuple)
    cycle_event_recorded: bool = False
    source_latest_run_id: str | None = None
    reason: str
    error_type: str | None = None


def apply_phase5_scheduler_attempt_run_intervention(
    plan: Phase5SchedulerAttemptRunInterventionPlan,
    *,
    diagnostic_id: str | None = None,
    observed_at: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAttemptRunInterventionApplyResult:
    if plan.execution_boundary == "observe_only":
        return _result(plan, "skipped", "none", reason=plan.reason)

    if plan.plan_status == "blocked" or plan.execution_boundary == "blocked":
        return _result(
            plan,
            "blocked",
            "none",
            missing_arguments=plan.missing_arguments,
            reason="intervention plan is blocked",
        )

    if plan.planned_side_effect != "scheduler_diagnostic":
        return _result(plan, "blocked", "none", reason="unsupported intervention side effect")

    effective_diagnostic_id = diagnostic_id or stable_phase5_scheduler_attempt_run_intervention_diagnostic_id(plan)
    effective_observed_at = observed_at or plan.source_latest_issued_at
    missing_arguments = _missing_apply_arguments(
        cycle_id=plan.cycle_id,
        diagnostic_id=effective_diagnostic_id,
        observed_at=effective_observed_at,
    )
    if missing_arguments:
        return _result(
            plan,
            "blocked",
            "none",
            diagnostic_id=effective_diagnostic_id,
            observed_at=effective_observed_at,
            missing_arguments=missing_arguments,
            reason="missing required intervention apply arguments: " + ", ".join(missing_arguments),
        )

    cycle, _diagnostic = record_phase5_scheduler_diagnostic(
        diagnostic_id=effective_diagnostic_id,
        cycle_id=plan.cycle_id,
        observed_at=effective_observed_at,
        scheduler_action=plan.action,
        severity=phase5_scheduler_attempt_run_intervention_severity(plan.action),
        failure_class=phase5_scheduler_attempt_run_intervention_failure_class(plan.action),
        recommended_recovery_action=phase5_scheduler_attempt_run_intervention_recovery_action(plan.action),
        blocking_reasons=plan.blocking_reasons,
        evidence_refs=[plan.source_latest_run_id] if plan.source_latest_run_id else [],
        notes=plan.reason,
        root=root,
    )
    return _result(
        plan,
        "applied",
        "diagnostic",
        diagnostic_id=effective_diagnostic_id,
        observed_at=effective_observed_at,
        cycle_event_recorded=cycle is not None,
        reason="attempt-run intervention diagnostic recorded",
    )


def _result(
    plan: Phase5SchedulerAttemptRunInterventionPlan,
    status: AttemptRunInterventionApplyStatus,
    output: AttemptRunInterventionAppliedOutput,
    *,
    diagnostic_id: str | None = None,
    observed_at: str | None = None,
    missing_arguments: tuple[str, ...] = (),
    cycle_event_recorded: bool = False,
    reason: str,
) -> Phase5SchedulerAttemptRunInterventionApplyResult:
    return Phase5SchedulerAttemptRunInterventionApplyResult(
        cycle_id=plan.cycle_id,
        execution_status=status,
        applied_output=output,
        action=plan.action,
        diagnostic_id=diagnostic_id,
        observed_at=observed_at,
        required_arguments=plan.required_arguments,
        missing_arguments=missing_arguments,
        cycle_event_recorded=cycle_event_recorded,
        source_latest_run_id=plan.source_latest_run_id,
        reason=reason,
    )


def _missing_apply_arguments(
    *,
    cycle_id: str | None,
    diagnostic_id: str | None,
    observed_at: str | None,
) -> tuple[str, ...]:
    values = {
        "cycle_id": cycle_id,
        "diagnostic_id": diagnostic_id,
        "observed_at": observed_at,
    }
    return tuple(name for name, value in values.items() if not value)
