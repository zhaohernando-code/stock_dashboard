from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ashare_evidence.scheduler_attempt_run_intervention_artifact_queries import (
    list_phase5_scheduler_attempt_intervention_run_artifacts,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_executor import AttemptRunInterventionApplyStatus

InterventionRunReadoutStatus = Literal["current", "blocked", "degraded"]


class Phase5SchedulerAttemptInterventionRunReadout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str | None = None
    runner_id: str | None = None
    total_runs: int
    latest_intervention_run_id: str | None = None
    latest_execution_status: AttemptRunInterventionApplyStatus | None = None
    latest_applied_output: str | None = None
    latest_issued_at: str | None = None
    latest_diagnostic_id: str | None = None
    latest_source_run_id: str | None = None
    applied_count: int = 0
    blocked_count: int = 0
    skipped_count: int = 0
    latest_blocked_run_id: str | None = None
    latest_applied_run_id: str | None = None
    readout_status: InterventionRunReadoutStatus
    intervention_run_refs: list[str]


def build_phase5_scheduler_attempt_intervention_run_readout(
    artifacts: Iterable[Phase5SchedulerAttemptInterventionRunArtifact],
) -> Phase5SchedulerAttemptInterventionRunReadout:
    runs = sorted(artifacts, key=lambda artifact: (artifact.issued_at, artifact.intervention_run_id), reverse=True)
    if not runs:
        return Phase5SchedulerAttemptInterventionRunReadout(
            total_runs=0,
            readout_status="degraded",
            intervention_run_refs=[],
        )

    latest = runs[0]
    latest_blocked = _first_run_with_status(runs, "blocked")
    latest_applied = _first_run_with_status(runs, "applied")
    return Phase5SchedulerAttemptInterventionRunReadout(
        cycle_id=_single_value(run.cycle_id for run in runs if run.cycle_id is not None),
        runner_id=_single_value(run.runner_id for run in runs),
        total_runs=len(runs),
        latest_intervention_run_id=latest.intervention_run_id,
        latest_execution_status=latest.execution_status,
        latest_applied_output=latest.applied_output,
        latest_issued_at=latest.issued_at,
        latest_diagnostic_id=latest.diagnostic_id,
        latest_source_run_id=latest.source_latest_run_id,
        applied_count=sum(1 for run in runs if run.execution_status == "applied"),
        blocked_count=sum(1 for run in runs if run.execution_status == "blocked"),
        skipped_count=sum(1 for run in runs if run.execution_status == "skipped"),
        latest_blocked_run_id=latest_blocked.intervention_run_id if latest_blocked else None,
        latest_applied_run_id=latest_applied.intervention_run_id if latest_applied else None,
        readout_status=_readout_status(latest),
        intervention_run_refs=[run.intervention_run_id for run in runs],
    )


def read_phase5_scheduler_attempt_intervention_run_readout(
    *,
    cycle_id: str | None = None,
    runner_id: str | None = None,
    root: Path | None = None,
) -> Phase5SchedulerAttemptInterventionRunReadout:
    return build_phase5_scheduler_attempt_intervention_run_readout(
        list_phase5_scheduler_attempt_intervention_run_artifacts(
            cycle_id=cycle_id,
            runner_id=runner_id,
            root=root,
        )
    )


def _first_run_with_status(
    runs: list[Phase5SchedulerAttemptInterventionRunArtifact],
    status: AttemptRunInterventionApplyStatus,
) -> Phase5SchedulerAttemptInterventionRunArtifact | None:
    return next((run for run in runs if run.execution_status == status), None)


def _single_value(values: Iterable[str]) -> str | None:
    unique = set(values)
    return next(iter(unique)) if len(unique) == 1 else None


def _readout_status(artifact: Phase5SchedulerAttemptInterventionRunArtifact) -> InterventionRunReadoutStatus:
    if artifact.execution_status == "blocked":
        return "blocked"
    return "current"
