from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply import (
    Phase5SchedulerAttemptRouteApplyResult,
)
from ashare_evidence.scheduler_attempt_run_artifact_store import (
    write_phase5_scheduler_attempt_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact


class Phase5SchedulerAttemptRunRecordResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: Phase5SchedulerAttemptRunArtifact
    path: Path


def build_phase5_scheduler_attempt_run_id(
    result: Phase5SchedulerAttemptRouteApplyResult,
    *,
    runner_id: str,
    issued_at: str,
) -> str:
    raw = "|".join(
        (
            "phase5_scheduler_attempt_run",
            result.cycle_id,
            result.attempt_id or "",
            runner_id,
            issued_at,
            result.route_type,
            result.attempt_context_status,
            result.preflight_status,
            result.execution_status,
            result.applied_output,
            result.diagnostic_id or "",
            result.execution_id or "",
            result.idempotency_key or "",
            ",".join(result.required_arguments),
            ",".join(result.missing_arguments),
            result.error_type or "",
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(("attempt-run", _slug(result.cycle_id), _slug(runner_id), digest))


def build_phase5_scheduler_attempt_run_artifact(
    result: Phase5SchedulerAttemptRouteApplyResult,
    *,
    runner_id: str,
    issued_at: str,
    run_id: str | None = None,
    blocking_reasons: Sequence[str] = (),
) -> Phase5SchedulerAttemptRunArtifact:
    return Phase5SchedulerAttemptRunArtifact(
        run_id=run_id
        or build_phase5_scheduler_attempt_run_id(
            result,
            runner_id=runner_id,
            issued_at=issued_at,
        ),
        attempt_id=result.attempt_id,
        cycle_id=result.cycle_id,
        runner_id=runner_id,
        issued_at=issued_at,
        attempt_status=result.attempt_context_status,
        route_type=result.route_type,
        preflight_status=result.preflight_status,
        apply_status=result.execution_status,
        applied_output=result.applied_output,
        required_arguments=list(result.required_arguments),
        missing_arguments=list(result.missing_arguments),
        diagnostic_id=result.diagnostic_id,
        execution_id=result.execution_id,
        idempotency_key=result.idempotency_key,
        cycle_event_recorded=result.cycle_event_recorded,
        reason=result.reason,
        error_type=result.error_type,
        blocking_reasons=list(blocking_reasons) or _blocking_reasons_from_missing(result.missing_arguments),
    )


def record_phase5_scheduler_attempt_run_artifact(
    result: Phase5SchedulerAttemptRouteApplyResult,
    *,
    runner_id: str,
    issued_at: str,
    run_id: str | None = None,
    blocking_reasons: Sequence[str] = (),
    root: Path | None = None,
) -> Phase5SchedulerAttemptRunRecordResult:
    artifact = build_phase5_scheduler_attempt_run_artifact(
        result,
        runner_id=runner_id,
        issued_at=issued_at,
        run_id=run_id,
        blocking_reasons=blocking_reasons,
    )
    path = write_phase5_scheduler_attempt_run_artifact(artifact, root=root)
    return Phase5SchedulerAttemptRunRecordResult(artifact=artifact, path=path)


def _blocking_reasons_from_missing(missing_arguments: Sequence[str]) -> list[str]:
    if not missing_arguments:
        return []
    return ["missing required arguments: " + ", ".join(missing_arguments)]


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"
