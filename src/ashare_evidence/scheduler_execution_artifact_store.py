from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ashare_evidence.artifact_store_core import DEFAULT_ARTIFACT_ROOT, PROJECT_ROOT, _ensure_artifact_write_allowed
from ashare_evidence.autonomous_flow_artifacts import (
    Phase5SchedulerExecutionLedgerArtifact,
    Phase5SchedulerExecutionReservationArtifact,
)

SCHEDULER_EXECUTION_LEDGER_FOLDER = "autonomous_flow/phase5_scheduler_execution_ledger"
SCHEDULER_EXECUTION_RESERVATION_FOLDER = "autonomous_flow/phase5_scheduler_execution_reservation"


class Phase5SchedulerExecutionReservationCollisionError(RuntimeError):
    """Raised when a reservation digest resolves to a payload for another key."""

    def __init__(self, *, reservation_id: str, requested_idempotency_key: str) -> None:
        self.reservation_id = reservation_id
        self.requested_idempotency_key = requested_idempotency_key
        super().__init__("phase5 scheduler execution reservation digest collision")


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


def phase5_scheduler_execution_reservation_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"scheduler-execution-reservation-{digest}"


def create_phase5_scheduler_execution_reservation_artifact(
    *,
    idempotency_key: str,
    execution_id: str,
    created_at: str,
    cycle_id: str | None = None,
    root: Path | None = None,
    _project_root: Path = PROJECT_ROOT,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerExecutionReservationArtifact:
    reservation = Phase5SchedulerExecutionReservationArtifact(
        reservation_id=phase5_scheduler_execution_reservation_id(idempotency_key),
        idempotency_key=idempotency_key,
        execution_id=execution_id,
        cycle_id=cycle_id,
        created_at=created_at,
    )
    target = _scheduler_execution_reservation_path(
        reservation.reservation_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
    _ensure_artifact_write_allowed(target, project_root=_project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(reservation.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return _read_existing_reservation_or_fail_closed(target, idempotency_key=idempotency_key)

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return reservation


def read_phase5_scheduler_execution_reservation_artifact(
    idempotency_key: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerExecutionReservationArtifact:
    reservation_id = phase5_scheduler_execution_reservation_id(idempotency_key)
    target = _scheduler_execution_reservation_path(
        reservation_id,
        root=root,
        default_artifact_root=_default_artifact_root,
    )
    return _read_existing_reservation_or_fail_closed(target, idempotency_key=idempotency_key)


def find_phase5_scheduler_execution_ledger_by_idempotency_key(
    idempotency_key: str,
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5SchedulerExecutionLedgerArtifact | None:
    artifact_root = Path(root) if root is not None else _default_artifact_root
    ledger_dir = artifact_root / SCHEDULER_EXECUTION_LEDGER_FOLDER
    if not ledger_dir.exists():
        return None
    for target in sorted(ledger_dir.glob("*.json")):
        payload = json.loads(target.read_text(encoding="utf-8"))
        ledger = Phase5SchedulerExecutionLedgerArtifact.model_validate(payload)
        if ledger.idempotency_key == idempotency_key:
            return ledger
    return None


def _scheduler_execution_ledger_path(
    execution_id: str,
    *,
    root: Path | None = None,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    artifact_root = Path(root) if root is not None else default_artifact_root
    return artifact_root / SCHEDULER_EXECUTION_LEDGER_FOLDER / f"{execution_id}.json"


def _scheduler_execution_reservation_path(
    reservation_id: str,
    *,
    root: Path | None = None,
    default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Path:
    artifact_root = Path(root) if root is not None else default_artifact_root
    return artifact_root / SCHEDULER_EXECUTION_RESERVATION_FOLDER / f"{reservation_id}.json"


def _read_existing_reservation_or_fail_closed(
    target: Path,
    *,
    idempotency_key: str,
) -> Phase5SchedulerExecutionReservationArtifact:
    payload = json.loads(target.read_text(encoding="utf-8"))
    reservation = Phase5SchedulerExecutionReservationArtifact.model_validate(payload)
    if reservation.idempotency_key != idempotency_key:
        raise Phase5SchedulerExecutionReservationCollisionError(
            reservation_id=reservation.reservation_id,
            requested_idempotency_key=idempotency_key,
        )
    return reservation
