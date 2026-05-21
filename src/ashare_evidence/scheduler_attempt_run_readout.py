from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ashare_evidence.autonomous_flow_scheduler_action_route_executor import ApplyStatus
from ashare_evidence.autonomous_flow_scheduler_attempt import Phase5SchedulerAttemptContextStatus
from ashare_evidence.scheduler_attempt_run_artifact_queries import list_phase5_scheduler_attempt_run_artifacts
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact

AttemptRunReadoutStalenessStatus = Literal["current", "blocked", "degraded"]


class Phase5SchedulerAttemptRunReadout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str | None = None
    runner_id: str | None = None
    total_runs: int
    latest_run_id: str | None = None
    latest_apply_status: ApplyStatus | None = None
    latest_attempt_status: Phase5SchedulerAttemptContextStatus | None = None
    latest_issued_at: str | None = None
    applied_count: int = 0
    blocked_count: int = 0
    skipped_count: int = 0
    latest_blocked_run_id: str | None = None
    latest_applied_run_id: str | None = None
    staleness_status: AttemptRunReadoutStalenessStatus
    run_refs: list[str]


def build_phase5_scheduler_attempt_run_readout(
    artifacts: Iterable[Phase5SchedulerAttemptRunArtifact],
) -> Phase5SchedulerAttemptRunReadout:
    runs = sorted(artifacts, key=lambda artifact: (artifact.issued_at, artifact.run_id), reverse=True)
    if not runs:
        return Phase5SchedulerAttemptRunReadout(
            total_runs=0,
            staleness_status="degraded",
            run_refs=[],
        )

    latest = runs[0]
    latest_blocked = _first_run_with_apply_status(runs, "blocked")
    latest_applied = _first_run_with_apply_status(runs, "applied")
    return Phase5SchedulerAttemptRunReadout(
        cycle_id=_single_value(run.cycle_id for run in runs),
        runner_id=_single_value(run.runner_id for run in runs),
        total_runs=len(runs),
        latest_run_id=latest.run_id,
        latest_apply_status=latest.apply_status,
        latest_attempt_status=latest.attempt_status,
        latest_issued_at=latest.issued_at,
        applied_count=sum(1 for run in runs if run.apply_status == "applied"),
        blocked_count=sum(1 for run in runs if run.apply_status == "blocked"),
        skipped_count=sum(1 for run in runs if run.apply_status == "skipped"),
        latest_blocked_run_id=latest_blocked.run_id if latest_blocked else None,
        latest_applied_run_id=latest_applied.run_id if latest_applied else None,
        staleness_status=_staleness_status(latest),
        run_refs=[run.run_id for run in runs],
    )


def read_phase5_scheduler_attempt_run_readout(
    *,
    cycle_id: str | None = None,
    runner_id: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAttemptRunReadout:
    return build_phase5_scheduler_attempt_run_readout(
        list_phase5_scheduler_attempt_run_artifacts(
            cycle_id=cycle_id,
            runner_id=runner_id,
            root=root,
        )
    )


def _first_run_with_apply_status(
    runs: list[Phase5SchedulerAttemptRunArtifact],
    status: ApplyStatus,
) -> Phase5SchedulerAttemptRunArtifact | None:
    return next((run for run in runs if run.apply_status == status), None)


def _single_value(values: Iterable[str]) -> str | None:
    unique = set(values)
    return next(iter(unique)) if len(unique) == 1 else None


def _staleness_status(artifact: Phase5SchedulerAttemptRunArtifact) -> AttemptRunReadoutStalenessStatus:
    if artifact.apply_status == "blocked" or artifact.attempt_status == "blocked":
        return "blocked"
    return "current"
