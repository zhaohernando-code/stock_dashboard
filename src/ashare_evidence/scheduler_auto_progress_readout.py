from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.scheduler_auto_progress_artifact_queries import (
    list_phase5_scheduler_auto_progress_run_artifacts,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact

AutoProgressReadoutStatus = Literal["current", "blocked", "degraded"]


class Phase5SchedulerAutoProgressRunReadout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str | None = None
    runner_id: str | None = None
    total_runs: int = Field(ge=0)
    latest_auto_progress_run_id: str | None = None
    latest_phase: str | None = None
    latest_plan_status: str | None = None
    latest_apply_status: str | None = None
    latest_applied_output: str | None = None
    latest_issued_at: str | None = None
    latest_recommended_output: str | None = None
    applied_count: int = 0
    blocked_count: int = 0
    idle_count: int = 0
    latest_blocked_run_id: str | None = None
    latest_applied_run_id: str | None = None
    result_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    readout_status: AutoProgressReadoutStatus
    auto_progress_run_refs: list[str]


def build_phase5_scheduler_auto_progress_run_readout(
    artifacts: Iterable[Phase5SchedulerAutoProgressRunArtifact],
) -> Phase5SchedulerAutoProgressRunReadout:
    runs = sorted(artifacts, key=lambda artifact: (artifact.issued_at, artifact.auto_progress_run_id), reverse=True)
    if not runs:
        return Phase5SchedulerAutoProgressRunReadout(
            total_runs=0,
            readout_status="degraded",
            auto_progress_run_refs=[],
        )

    latest = runs[0]
    latest_blocked = _first_run_with_status(runs, "blocked")
    latest_applied = _first_run_with_status(runs, "applied")
    return Phase5SchedulerAutoProgressRunReadout(
        cycle_id=_single_value(run.cycle_id for run in runs if run.cycle_id is not None),
        runner_id=_single_value(run.runner_id for run in runs),
        total_runs=len(runs),
        latest_auto_progress_run_id=latest.auto_progress_run_id,
        latest_phase=latest.phase,
        latest_plan_status=latest.plan_status,
        latest_apply_status=latest.apply_status,
        latest_applied_output=latest.applied_output,
        latest_issued_at=latest.issued_at,
        latest_recommended_output=latest.recommended_output,
        applied_count=sum(1 for run in runs if run.apply_status == "applied"),
        blocked_count=sum(1 for run in runs if run.apply_status == "blocked"),
        idle_count=sum(1 for run in runs if run.apply_status == "idle"),
        latest_blocked_run_id=latest_blocked.auto_progress_run_id if latest_blocked else None,
        latest_applied_run_id=latest_applied.auto_progress_run_id if latest_applied else None,
        result_refs=_dedupe(ref for run in runs for ref in run.result_refs),
        evidence_refs=_dedupe(ref for run in runs for ref in run.evidence_refs),
        readout_status=_readout_status(latest),
        auto_progress_run_refs=[run.auto_progress_run_id for run in runs],
    )


def read_phase5_scheduler_auto_progress_run_readout(
    *,
    cycle_id: str | None = None,
    runner_id: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAutoProgressRunReadout:
    return build_phase5_scheduler_auto_progress_run_readout(
        list_phase5_scheduler_auto_progress_run_artifacts(
            cycle_id=cycle_id,
            runner_id=runner_id,
            root=root,
        )
    )


def _first_run_with_status(
    runs: list[Phase5SchedulerAutoProgressRunArtifact],
    status: str,
) -> Phase5SchedulerAutoProgressRunArtifact | None:
    return next((run for run in runs if run.apply_status == status), None)


def _single_value(values: Iterable[str]) -> str | None:
    unique = set(values)
    return next(iter(unique)) if len(unique) == 1 else None


def _readout_status(artifact: Phase5SchedulerAutoProgressRunArtifact) -> AutoProgressReadoutStatus:
    if artifact.apply_status == "blocked":
        return "blocked"
    return "current"


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
