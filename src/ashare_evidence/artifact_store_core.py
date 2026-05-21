from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"
ARTIFACT_FOLDERS = {
    "rolling_validation": "manifests",
    "validation_metrics": "validation",
    "portfolio_backtest": "backtests",
    "replay_alignment": "replays",
    "manual_review": "manual_reviews",
    "phase5_horizon_study": "studies",
    "phase5_holding_policy_study": "studies",
    "phase5_holding_policy_experiment": "studies",
    "phase5_producer_contract_study": "studies",
    "shortpick_lab": "shortpick_lab",
    "phase5_cycle_ledger": "autonomous_flow/phase5_cycle_ledger",
    "phase5_recovery_ticket": "autonomous_flow/phase5_recovery_ticket",
    "phase5_scheduler_diagnostic": "autonomous_flow/phase5_scheduler_diagnostic",
    "phase5_scheduler_attempt_run": "autonomous_flow/phase5_scheduler_attempt_run",
    "phase5_gate_readout": "autonomous_flow/phase5_gate_readout",
    "frontend_projection_manifest": "autonomous_flow/frontend_projection_manifest",
}

ArtifactModel = TypeVar("ArtifactModel", bound=BaseModel)


def _source_artifact_roots(*, project_root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    if not (project_root / ".git").exists():
        return ()
    return (
        project_root / "artifacts",
        project_root / "data" / "artifacts",
    )


def _artifact_root(
    root: Path | None = None,
    *,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv("ASHARE_ARTIFACT_ROOT")
    return Path(configured) if configured else default_artifact_root


def artifact_root_from_database_url(
    database_url: str | None,
    *,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    configured = os.getenv("ASHARE_ARTIFACT_ROOT")
    if configured:
        return Path(configured)
    if database_url == "sqlite:///:memory:":
        return Path(tempfile.gettempdir()) / "ashare-evidence-artifacts" / f"memory-{os.getpid()}"
    if database_url and database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///")).resolve()
        return db_path.parent / "artifacts"
    return _artifact_root(default_artifact_root=default_artifact_root)


def artifact_path(
    artifact_type: str,
    artifact_id: str,
    *,
    root: Path | None = None,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    folder = ARTIFACT_FOLDERS[artifact_type]
    return _artifact_root(root, default_artifact_root=default_artifact_root) / folder / f"{artifact_id}.json"


def _ensure_artifact_write_allowed(
    target: Path,
    *,
    project_root: Path = PROJECT_ROOT,
) -> None:
    if os.getenv("ASHARE_ALLOW_REPO_ARTIFACT_WRITES") == "1":
        return
    resolved_target = target.resolve()
    for repo_root in _source_artifact_roots(project_root=project_root):
        resolved_root = repo_root.resolve()
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError:
            continue
        raise RuntimeError(
            "Refusing to write generated research artifact into the source checkout. "
            f"target={resolved_target}. Set ASHARE_ARTIFACT_ROOT to a runtime/output data directory, "
            "or set ASHARE_ALLOW_REPO_ARTIFACT_WRITES=1 only for an intentional fixture refresh."
        )


def _write_model(
    model: BaseModel,
    artifact_type: str,
    artifact_id: str,
    *,
    root: Path | None = None,
    project_root: Path = PROJECT_ROOT,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    target = artifact_path(artifact_type, artifact_id, root=root, default_artifact_root=default_artifact_root)
    _ensure_artifact_write_allowed(target, project_root=project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json")
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _read_model(  # noqa: UP047 - keep Python 3.10-compatible generic syntax.
    model_type: type[ArtifactModel],
    artifact_type: str,
    artifact_id: str,
    *,
    root: Path | None = None,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> ArtifactModel:
    target = artifact_path(artifact_type, artifact_id, root=root, default_artifact_root=default_artifact_root)
    payload = json.loads(target.read_text(encoding="utf-8"))
    return model_type.model_validate(payload)


def _read_model_if_exists(  # noqa: UP047 - keep Python 3.10-compatible generic syntax.
    model_type: type[ArtifactModel],
    artifact_type: str,
    artifact_id: str | None,
    *,
    root: Path | None = None,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> ArtifactModel | None:
    if not artifact_id:
        return None
    target = artifact_path(artifact_type, artifact_id, root=root, default_artifact_root=default_artifact_root)
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    return model_type.model_validate(payload)
