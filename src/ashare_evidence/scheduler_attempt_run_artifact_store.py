from __future__ import annotations

from pathlib import Path

from ashare_evidence.artifact_store_core import (
    DEFAULT_ARTIFACT_ROOT,
    PROJECT_ROOT,
    _read_model,
    _read_model_if_exists,
    _write_model,
)
from ashare_evidence.scheduler_attempt_run_artifact_queries import (
    find_latest_phase5_scheduler_attempt_run_artifact,
    list_phase5_scheduler_attempt_run_artifacts,
)
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact

__all__ = [
    "find_latest_phase5_scheduler_attempt_run_artifact",
    "list_phase5_scheduler_attempt_run_artifacts",
    "read_phase5_scheduler_attempt_run_artifact",
    "read_phase5_scheduler_attempt_run_artifact_if_exists",
    "write_phase5_scheduler_attempt_run_artifact",
]


def write_phase5_scheduler_attempt_run_artifact(
    artifact: Phase5SchedulerAttemptRunArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    return _write_model(
        artifact,
        "phase5_scheduler_attempt_run",
        artifact.run_id,
        root=root,
        project_root=_project_root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_scheduler_attempt_run_artifact(
    run_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerAttemptRunArtifact:
    return _read_model(
        Phase5SchedulerAttemptRunArtifact,
        "phase5_scheduler_attempt_run",
        run_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )


def read_phase5_scheduler_attempt_run_artifact_if_exists(
    run_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerAttemptRunArtifact | None:
    return _read_model_if_exists(
        Phase5SchedulerAttemptRunArtifact,
        "phase5_scheduler_attempt_run",
        run_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
