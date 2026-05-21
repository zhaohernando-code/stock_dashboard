from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.scheduler_attempt_run_followup_policy import decide_phase5_scheduler_attempt_run_followup
from ashare_evidence.scheduler_attempt_run_intervention_followup_policy import (
    decide_phase5_scheduler_attempt_intervention_followup,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import plan_phase5_scheduler_attempt_run_intervention
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    read_phase5_scheduler_attempt_intervention_run_readout,
)
from ashare_evidence.scheduler_attempt_run_readout import read_phase5_scheduler_attempt_run_readout
from ashare_evidence.scheduler_attempt_run_recovery_ticket_intent import (
    build_phase5_scheduler_recovery_ticket_intent,
)
from ashare_evidence.scheduler_recovery_followup_intent import (
    read_phase5_scheduler_recovery_followup_intent,
)

AutoProgressPlanStatus = Literal["ready", "blocked", "idle"]
AutoProgressPhase = Literal[
    "recovery_followup_apply",
    "recovery_ticket_apply",
    "intervention_apply",
    "wait_for_next_tick",
]


class Phase5SchedulerAutoProgressPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_status: AutoProgressPlanStatus
    phase: AutoProgressPhase
    cycle_id: str | None = None
    runner_id: str | None = None
    recommended_output: str | None = None
    recommended_flags: list[str] = Field(default_factory=list)
    required_arguments: tuple[str, ...] = Field(default_factory=tuple)
    missing_arguments: tuple[str, ...] = Field(default_factory=tuple)
    blocking_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_status: str | None = None
    source_reason: str | None = None
    notes: str


def read_phase5_scheduler_auto_progress_plan(
    *,
    cycle_id: str,
    runner_id: str | None = None,
    created_at: str | None = None,
    issued_at: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAutoProgressPlan:
    followup = read_phase5_scheduler_recovery_followup_intent(cycle_id=cycle_id, root=root)
    if followup.intent_status == "ready":
        return _plan(
            plan_status="ready",
            phase="recovery_followup_apply",
            cycle_id=cycle_id,
            runner_id=runner_id,
            recommended_output="attempt-run-recovery-followup-apply",
            required_arguments=("created_at",),
            provided_arguments={"created_at": created_at},
            evidence_refs=followup.evidence_refs,
            source_status=followup.intent_status,
            source_reason=followup.notes,
            notes="ready recovery follow-up intent should be applied next",
        )
    if followup.intent_status == "blocked":
        return _blocked(
            "recovery_followup_apply",
            cycle_id,
            runner_id,
            followup.blocking_reasons,
            source_status=followup.intent_status,
            source_reason=followup.notes,
        )

    intervention_readout = read_phase5_scheduler_attempt_intervention_run_readout(
        cycle_id=cycle_id,
        runner_id=runner_id,
        root=root,
    )
    intervention_decision = decide_phase5_scheduler_attempt_intervention_followup(intervention_readout)
    ticket_intent = build_phase5_scheduler_recovery_ticket_intent(intervention_readout, intervention_decision)
    if ticket_intent.intent_status == "ready":
        return _plan(
            plan_status="ready",
            phase="recovery_ticket_apply",
            cycle_id=cycle_id,
            runner_id=runner_id,
            recommended_output="attempt-run-recovery-ticket-apply",
            evidence_refs=ticket_intent.evidence_refs,
            source_status=ticket_intent.intent_status,
            source_reason=ticket_intent.notes,
            notes="ready recovery ticket intent should be applied next",
        )
    if ticket_intent.intent_status == "blocked":
        return _blocked(
            "recovery_ticket_apply",
            cycle_id,
            runner_id,
            ticket_intent.blocking_reasons,
            evidence_refs=ticket_intent.evidence_refs,
            source_status=ticket_intent.intent_status,
            source_reason=ticket_intent.notes,
        )

    attempt_readout = read_phase5_scheduler_attempt_run_readout(cycle_id=cycle_id, runner_id=runner_id, root=root)
    attempt_decision = decide_phase5_scheduler_attempt_run_followup(attempt_readout)
    intervention_plan = plan_phase5_scheduler_attempt_run_intervention(attempt_readout, attempt_decision)
    if intervention_plan.next_step == "record_recovery_diagnostic":
        return _plan(
            plan_status="ready",
            phase="intervention_apply",
            cycle_id=cycle_id,
            runner_id=runner_id,
            recommended_output="attempt-run-intervention-apply",
            recommended_flags=["--record-intervention-run"],
            required_arguments=("issued_at", "runner_id"),
            provided_arguments={"issued_at": issued_at, "runner_id": runner_id},
            evidence_refs=[ref for ref in [intervention_plan.source_latest_run_id] if ref],
            source_status=intervention_plan.plan_status,
            source_reason=intervention_plan.reason,
            notes="blocked attempt run should record an intervention diagnostic",
        )
    if intervention_plan.plan_status == "blocked":
        return _blocked(
            "intervention_apply",
            cycle_id,
            runner_id,
            intervention_plan.blocking_reasons,
            evidence_refs=[ref for ref in [intervention_plan.source_latest_run_id] if ref],
            source_status=intervention_plan.plan_status,
            source_reason=intervention_plan.reason,
        )

    return Phase5SchedulerAutoProgressPlan(
        plan_status="idle",
        phase="wait_for_next_tick",
        cycle_id=cycle_id,
        runner_id=runner_id,
        source_status=intervention_plan.plan_status,
        source_reason=intervention_plan.reason,
        notes="no auto-progress action is needed",
    )


def _plan(
    *,
    plan_status: AutoProgressPlanStatus,
    phase: AutoProgressPhase,
    cycle_id: str | None,
    runner_id: str | None,
    recommended_output: str | None,
    notes: str,
    recommended_flags: list[str] | None = None,
    required_arguments: tuple[str, ...] = (),
    provided_arguments: dict[str, str | None] | None = None,
    evidence_refs: list[str] | None = None,
    source_status: str | None = None,
    source_reason: str | None = None,
) -> Phase5SchedulerAutoProgressPlan:
    missing = _missing_arguments(required_arguments, provided_arguments or {})
    effective_status: AutoProgressPlanStatus = "blocked" if missing else plan_status
    return Phase5SchedulerAutoProgressPlan(
        plan_status=effective_status,
        phase=phase,
        cycle_id=cycle_id,
        runner_id=runner_id,
        recommended_output=recommended_output,
        recommended_flags=recommended_flags or [],
        required_arguments=required_arguments,
        missing_arguments=missing,
        blocking_reasons=[f"missing required auto-progress argument: {argument}" for argument in missing],
        evidence_refs=_dedupe(evidence_refs or []),
        source_status=source_status,
        source_reason=source_reason,
        notes=notes,
    )


def _blocked(
    phase: AutoProgressPhase,
    cycle_id: str | None,
    runner_id: str | None,
    blocking_reasons: list[str],
    *,
    evidence_refs: list[str] | None = None,
    source_status: str | None = None,
    source_reason: str | None = None,
) -> Phase5SchedulerAutoProgressPlan:
    return Phase5SchedulerAutoProgressPlan(
        plan_status="blocked",
        phase=phase,
        cycle_id=cycle_id,
        runner_id=runner_id,
        blocking_reasons=blocking_reasons,
        evidence_refs=_dedupe(evidence_refs or []),
        source_status=source_status,
        source_reason=source_reason,
        notes="auto-progress is blocked by upstream state",
    )


def _missing_arguments(
    required_arguments: tuple[str, ...],
    provided_arguments: dict[str, str | None],
) -> tuple[str, ...]:
    return tuple(argument for argument in required_arguments if not provided_arguments.get(argument))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
