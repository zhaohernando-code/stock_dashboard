from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.scheduler_attempt_run_followup_policy import decide_phase5_scheduler_attempt_run_followup
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    apply_phase5_scheduler_attempt_run_intervention,
)
from ashare_evidence.scheduler_attempt_run_intervention_followup_policy import (
    decide_phase5_scheduler_attempt_intervention_followup,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import plan_phase5_scheduler_attempt_run_intervention
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    read_phase5_scheduler_attempt_intervention_run_readout,
)
from ashare_evidence.scheduler_attempt_run_intervention_recorder import (
    record_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_readout import read_phase5_scheduler_attempt_run_readout
from ashare_evidence.scheduler_attempt_run_recovery_ticket_executor import (
    apply_phase5_scheduler_recovery_ticket_intent,
)
from ashare_evidence.scheduler_attempt_run_recovery_ticket_intent import (
    build_phase5_scheduler_recovery_ticket_intent,
)
from ashare_evidence.scheduler_auto_progress_plan import (
    Phase5SchedulerAutoProgressPlan,
    read_phase5_scheduler_auto_progress_plan,
)
from ashare_evidence.scheduler_recovery_followup_executor import (
    apply_phase5_scheduler_recovery_followup_intent,
)
from ashare_evidence.scheduler_recovery_followup_intent import (
    read_phase5_scheduler_recovery_followup_intent,
)

AutoProgressApplyStatus = Literal["applied", "blocked", "idle"]
AutoProgressAppliedOutput = Literal["none", "intervention_run", "recovery_ticket", "followup_cycle"]


class Phase5SchedulerAutoProgressApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    apply_status: AutoProgressApplyStatus
    applied_output: AutoProgressAppliedOutput
    plan: Phase5SchedulerAutoProgressPlan
    result_payload: dict[str, Any] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: str


def apply_phase5_scheduler_auto_progress_step(
    *,
    cycle_id: str,
    runner_id: str | None = None,
    created_at: str | None = None,
    issued_at: str | None = None,
    intervention_run_id: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAutoProgressApplyResult:
    plan = read_phase5_scheduler_auto_progress_plan(
        cycle_id=cycle_id,
        runner_id=runner_id,
        created_at=created_at,
        issued_at=issued_at,
        root=root,
    )
    if plan.plan_status == "blocked":
        return _result(plan, "blocked", "none", blocking_reasons=plan.blocking_reasons, notes="plan is blocked")
    if plan.plan_status == "idle":
        return _result(plan, "idle", "none", notes="plan has no auto-progress action")
    if plan.phase == "intervention_apply":
        return _apply_intervention_step(
            plan,
            runner_id=runner_id,
            issued_at=issued_at,
            intervention_run_id=intervention_run_id,
            root=root,
        )
    if plan.phase == "recovery_ticket_apply":
        return _apply_recovery_ticket_step(plan, runner_id=runner_id, root=root)
    return _apply_recovery_followup_step(plan, created_at=created_at, root=root)


def _apply_intervention_step(
    plan: Phase5SchedulerAutoProgressPlan,
    *,
    runner_id: str | None,
    issued_at: str | None,
    intervention_run_id: str | None,
    root: Path | None,
) -> Phase5SchedulerAutoProgressApplyResult:
    readout = read_phase5_scheduler_attempt_run_readout(cycle_id=plan.cycle_id, runner_id=runner_id, root=root)
    decision = decide_phase5_scheduler_attempt_run_followup(readout)
    intervention_plan = plan_phase5_scheduler_attempt_run_intervention(readout, decision)
    apply_result = apply_phase5_scheduler_attempt_run_intervention(intervention_plan, root=root)
    if apply_result.execution_status == "blocked":
        return _result(
            plan,
            "blocked",
            "none",
            result_payload={"apply_result": apply_result.model_dump(mode="json")},
            blocking_reasons=list(apply_result.missing_arguments),
            notes=apply_result.reason,
        )
    recorded = record_phase5_scheduler_attempt_intervention_run_artifact(
        apply_result,
        runner_id=runner_id or "",
        issued_at=issued_at or "",
        intervention_run_id=intervention_run_id,
        root=root,
    )
    return _result(
        plan,
        "applied",
        "intervention_run",
        result_payload={
            "apply_result": apply_result.model_dump(mode="json"),
            "intervention_run_artifact": recorded.artifact.model_dump(mode="json"),
            "intervention_run_artifact_path": str(recorded.path),
        },
        notes="auto-progress recorded intervention run",
    )


def _apply_recovery_ticket_step(
    plan: Phase5SchedulerAutoProgressPlan,
    *,
    runner_id: str | None,
    root: Path | None,
) -> Phase5SchedulerAutoProgressApplyResult:
    readout = read_phase5_scheduler_attempt_intervention_run_readout(
        cycle_id=plan.cycle_id,
        runner_id=runner_id,
        root=root,
    )
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)
    intent = build_phase5_scheduler_recovery_ticket_intent(readout, decision)
    result = apply_phase5_scheduler_recovery_ticket_intent(intent, root=root)
    return _result(
        plan,
        "blocked" if result.apply_status == "blocked" else "applied",
        "none" if result.apply_status == "blocked" else "recovery_ticket",
        result_payload={"recovery_ticket_apply_result": result.model_dump(mode="json")},
        blocking_reasons=result.blocking_reasons,
        notes=result.notes,
    )


def _apply_recovery_followup_step(
    plan: Phase5SchedulerAutoProgressPlan,
    *,
    created_at: str | None,
    root: Path | None,
) -> Phase5SchedulerAutoProgressApplyResult:
    intent = read_phase5_scheduler_recovery_followup_intent(cycle_id=plan.cycle_id or "", root=root)
    result = apply_phase5_scheduler_recovery_followup_intent(intent, created_at=created_at, root=root)
    return _result(
        plan,
        "blocked" if result.apply_status == "blocked" else "applied",
        "none" if result.apply_status == "blocked" else "followup_cycle",
        result_payload={"recovery_followup_apply_result": result.model_dump(mode="json")},
        blocking_reasons=result.blocking_reasons,
        notes=result.notes,
    )


def _result(
    plan: Phase5SchedulerAutoProgressPlan,
    apply_status: AutoProgressApplyStatus,
    applied_output: AutoProgressAppliedOutput,
    *,
    notes: str,
    result_payload: dict[str, Any] | None = None,
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerAutoProgressApplyResult:
    return Phase5SchedulerAutoProgressApplyResult(
        apply_status=apply_status,
        applied_output=applied_output,
        plan=plan,
        result_payload=result_payload or {},
        blocking_reasons=blocking_reasons or [],
        notes=notes,
    )
