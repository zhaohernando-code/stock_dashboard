from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    write_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    Phase5SchedulerAttemptRunInterventionApplyResult,
)


class Phase5SchedulerAttemptInterventionRunRecordResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: Phase5SchedulerAttemptInterventionRunArtifact
    path: Path


def build_phase5_scheduler_attempt_intervention_run_id(
    result: Phase5SchedulerAttemptRunInterventionApplyResult,
    *,
    runner_id: str,
    issued_at: str,
) -> str:
    raw = "|".join(
        (
            "phase5_scheduler_attempt_intervention_run",
            result.cycle_id or "",
            runner_id,
            issued_at,
            result.execution_status,
            result.applied_output,
            result.action,
            result.diagnostic_id or "",
            result.observed_at or "",
            result.source_latest_run_id or "",
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(("intervention-run", _slug(result.cycle_id or "no-cycle"), _slug(runner_id), digest))


def build_phase5_scheduler_attempt_intervention_run_artifact(
    result: Phase5SchedulerAttemptRunInterventionApplyResult,
    *,
    runner_id: str,
    issued_at: str,
    intervention_run_id: str | None = None,
) -> Phase5SchedulerAttemptInterventionRunArtifact:
    return Phase5SchedulerAttemptInterventionRunArtifact(
        intervention_run_id=intervention_run_id
        or build_phase5_scheduler_attempt_intervention_run_id(result, runner_id=runner_id, issued_at=issued_at),
        cycle_id=result.cycle_id,
        runner_id=runner_id,
        issued_at=issued_at,
        execution_status=result.execution_status,
        applied_output=result.applied_output,
        action=result.action,
        diagnostic_id=result.diagnostic_id,
        observed_at=result.observed_at,
        required_arguments=list(result.required_arguments),
        missing_arguments=list(result.missing_arguments),
        cycle_event_recorded=result.cycle_event_recorded,
        source_latest_run_id=result.source_latest_run_id,
        reason=result.reason,
        error_type=result.error_type,
    )


def record_phase5_scheduler_attempt_intervention_run_artifact(
    result: Phase5SchedulerAttemptRunInterventionApplyResult,
    *,
    runner_id: str,
    issued_at: str,
    intervention_run_id: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAttemptInterventionRunRecordResult:
    artifact = build_phase5_scheduler_attempt_intervention_run_artifact(
        result,
        runner_id=runner_id,
        issued_at=issued_at,
        intervention_run_id=intervention_run_id,
    )
    path = write_phase5_scheduler_attempt_intervention_run_artifact(artifact, root=root)
    return Phase5SchedulerAttemptInterventionRunRecordResult(artifact=artifact, path=path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"
