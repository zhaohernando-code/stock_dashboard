from __future__ import annotations

from pathlib import Path

from ashare_evidence.artifact_store_core import DEFAULT_ARTIFACT_ROOT, PROJECT_ROOT, _read_model, _write_model
from ashare_evidence.scheduler_attempt_run_intervention_artifact_queries import (
    find_latest_phase5_scheduler_attempt_intervention_run_artifact,
    list_phase5_scheduler_attempt_intervention_run_artifacts,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)

__all__ = [
    "find_latest_phase5_scheduler_attempt_intervention_run_artifact",
    "list_phase5_scheduler_attempt_intervention_run_artifacts",
    "read_phase5_scheduler_attempt_intervention_run_artifact",
    "write_phase5_scheduler_attempt_intervention_run_artifact",
]


def write_phase5_scheduler_attempt_intervention_run_artifact(
    artifact: Phase5SchedulerAttemptInterventionRunArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "phase5_scheduler_attempt_intervention_run",
        artifact.intervention_run_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_scheduler_attempt_intervention_run_artifact(
    intervention_run_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerAttemptInterventionRunArtifact:
    return _read_model(
        Phase5SchedulerAttemptInterventionRunArtifact,
        "phase5_scheduler_attempt_intervention_run",
        intervention_run_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
