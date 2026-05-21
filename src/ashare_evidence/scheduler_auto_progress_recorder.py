from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ashare_evidence.scheduler_auto_progress_artifact_store import (
    write_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact
from ashare_evidence.scheduler_auto_progress_executor import Phase5SchedulerAutoProgressApplyResult


class Phase5SchedulerAutoProgressRunRecordResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: Phase5SchedulerAutoProgressRunArtifact
    path: Path


def build_phase5_scheduler_auto_progress_run_id(
    result: Phase5SchedulerAutoProgressApplyResult,
    *,
    runner_id: str,
    issued_at: str,
) -> str:
    raw = "|".join(
        (
            "phase5_scheduler_auto_progress_run",
            result.plan.cycle_id or "",
            runner_id,
            issued_at,
            result.plan.phase,
            result.apply_status,
            result.applied_output,
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(("auto-progress-run", _slug(result.plan.cycle_id or "no-cycle"), _slug(runner_id), digest))


def build_phase5_scheduler_auto_progress_run_artifact(
    result: Phase5SchedulerAutoProgressApplyResult,
    *,
    runner_id: str,
    issued_at: str,
    auto_progress_run_id: str | None = None,
) -> Phase5SchedulerAutoProgressRunArtifact:
    plan = result.plan
    return Phase5SchedulerAutoProgressRunArtifact(
        auto_progress_run_id=auto_progress_run_id
        or build_phase5_scheduler_auto_progress_run_id(result, runner_id=runner_id, issued_at=issued_at),
        cycle_id=plan.cycle_id,
        runner_id=runner_id,
        issued_at=issued_at,
        plan_status=plan.plan_status,
        phase=plan.phase,
        apply_status=result.apply_status,
        applied_output=result.applied_output,
        recommended_output=plan.recommended_output,
        recommended_flags=plan.recommended_flags,
        required_arguments=list(plan.required_arguments),
        missing_arguments=list(plan.missing_arguments),
        blocking_reasons=_dedupe([*plan.blocking_reasons, *result.blocking_reasons]),
        evidence_refs=plan.evidence_refs,
        result_refs=_result_refs(result),
        notes=result.notes,
    )


def record_phase5_scheduler_auto_progress_run_artifact(
    result: Phase5SchedulerAutoProgressApplyResult,
    *,
    runner_id: str,
    issued_at: str,
    auto_progress_run_id: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAutoProgressRunRecordResult:
    artifact = build_phase5_scheduler_auto_progress_run_artifact(
        result,
        runner_id=runner_id,
        issued_at=issued_at,
        auto_progress_run_id=auto_progress_run_id,
    )
    path = write_phase5_scheduler_auto_progress_run_artifact(artifact, root=root)
    return Phase5SchedulerAutoProgressRunRecordResult(artifact=artifact, path=path)


def _result_refs(result: Phase5SchedulerAutoProgressApplyResult) -> list[str]:
    refs: list[str] = []
    payload = result.result_payload
    intervention = payload.get("intervention_run_artifact")
    if isinstance(intervention, dict) and intervention.get("intervention_run_id"):
        refs.append(f"phase5_scheduler_attempt_intervention_run:{intervention['intervention_run_id']}")
    ticket = payload.get("recovery_ticket_apply_result")
    if isinstance(ticket, dict) and ticket.get("ticket_id"):
        refs.append(f"phase5_recovery_ticket:{ticket['ticket_id']}")
    followup = payload.get("recovery_followup_apply_result")
    if isinstance(followup, dict) and followup.get("followup_cycle_id"):
        refs.append(f"phase5_cycle_ledger:{followup['followup_cycle_id']}")
    return _dedupe(refs)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
