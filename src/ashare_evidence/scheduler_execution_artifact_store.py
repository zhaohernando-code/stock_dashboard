from __future__ import annotations

import json
from pathlib import Path

from ashare_evidence.artifact_store_core import DEFAULT_ARTIFACT_ROOT, PROJECT_ROOT, _ensure_artifact_write_allowed
from ashare_evidence.autonomous_flow_artifacts import Phase5SchedulerExecutionLedgerArtifact

SCHEDULER_EXECUTION_LEDGER_FOLDER = "autonomous_flow/phase5_scheduler_execution_ledger"


def write_phase5_scheduler_execution_ledger_artifact(
    artifact: Phase5SchedulerExecutionLedgerArtifact,
    *,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    target = _scheduler_execution_ledger_path(
        artifact.execution_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
    _ensure_artifact_write_allowed(target, project_root=_project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def read_phase5_scheduler_execution_ledger_artifact(
    execution_id: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerExecutionLedgerArtifact:
    target = _scheduler_execution_ledger_path(
        execution_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    return Phase5SchedulerExecutionLedgerArtifact.model_validate(payload)


def read_phase5_scheduler_execution_ledger_artifact_if_exists(
    execution_id: str | None,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerExecutionLedgerArtifact | None:
    if not execution_id:
        return None
    target = _scheduler_execution_ledger_path(
        execution_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    return Phase5SchedulerExecutionLedgerArtifact.model_validate(payload)


def _scheduler_execution_ledger_path(
    execution_id: str,
    *,
    root: Path | None = None,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    artifact_root = Path(root) if root is not None else default_artifact_root
    return artifact_root / SCHEDULER_EXECUTION_LEDGER_FOLDER / f"{execution_id}.json"
