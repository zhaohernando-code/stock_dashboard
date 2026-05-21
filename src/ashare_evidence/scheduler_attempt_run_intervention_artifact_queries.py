from __future__ import annotations

import json
from pathlib import Path

from ashare_evidence.artifact_store_core import DEFAULT_ARTIFACT_ROOT, artifact_path
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)


def list_phase5_scheduler_attempt_intervention_run_artifacts(
    *,
    cycle_id: str | None = None,
    runner_id: str | None = None,
    execution_status: str | None = None,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> list[Phase5SchedulerAttemptInterventionRunArtifact]:
    directory = artifact_path(
        "phase5_scheduler_attempt_intervention_run",
        "_",
        root=root,
        default_artifact_root=_default_artifact_root,
    ).parent
    if not directory.exists():
        return []
    filters = (
        ("cycle_id", cycle_id),
        ("runner_id", runner_id),
        ("execution_status", execution_status),
    )
    artifacts: list[Phase5SchedulerAttemptInterventionRunArtifact] = []
    for path in directory.glob("*.json"):
        if not path.is_file():
            continue
        artifact = Phase5SchedulerAttemptInterventionRunArtifact.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if all(expected is None or getattr(artifact, field) == expected for field, expected in filters):
            artifacts.append(artifact)
    return sorted(artifacts, key=lambda artifact: (artifact.issued_at, artifact.intervention_run_id), reverse=True)


def find_latest_phase5_scheduler_attempt_intervention_run_artifact(
    *,
    cycle_id: str | None = None,
    runner_id: str | None = None,
    execution_status: str | None = None,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerAttemptInterventionRunArtifact | None:
    artifacts = list_phase5_scheduler_attempt_intervention_run_artifacts(
        cycle_id=cycle_id,
        runner_id=runner_id,
        execution_status=execution_status,
        root=root,
        _default_artifact_root=_default_artifact_root,
    )
    return artifacts[0] if artifacts else None
