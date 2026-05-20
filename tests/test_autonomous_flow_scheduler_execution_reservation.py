from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_evidence.autonomous_flow import (
    PHASE5_CYCLE_STARTED_EVENT,
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT,
    Phase5SchedulerExecutionIdempotencyConflictError,
    record_phase5_scheduler_execution_ledger,
)
from ashare_evidence.autonomous_flow_artifacts import Phase5SchedulerExecutionReservationArtifact
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_execution_artifact_store import (
    SCHEDULER_EXECUTION_RESERVATION_FOLDER,
    Phase5SchedulerExecutionReservationCollisionError,
    create_phase5_scheduler_execution_reservation_artifact,
    phase5_scheduler_execution_reservation_id,
    read_phase5_scheduler_execution_ledger_artifact,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
)
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle


class Phase5SchedulerExecutionReservationTests(unittest.TestCase):
    def test_reservation_id_is_stable_digest_and_safe_for_path(self) -> None:
        key = "cycle:phase5/20260521 am:retry failed step"

        first = phase5_scheduler_execution_reservation_id(key)
        second = phase5_scheduler_execution_reservation_id(key)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("scheduler-execution-reservation-"))
        for forbidden in ("/", ":", " "):
            self.assertNotIn(forbidden, first)
        self.assertNotIn(key, first)

    def test_reservation_create_if_absent_returns_existing_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            created = create_phase5_scheduler_execution_reservation_artifact(
                idempotency_key="idempotency:reserve",
                execution_id="execution-first",
                cycle_id="phase5-20260521-reserve",
                created_at="2026-05-21T09:00:00Z",
                root=root,
            )
            repeated = create_phase5_scheduler_execution_reservation_artifact(
                idempotency_key="idempotency:reserve",
                execution_id="execution-second",
                cycle_id="phase5-20260521-other",
                created_at="2026-05-21T10:00:00Z",
                root=root,
            )
            persisted = _read_reservation_payload(root, created.reservation_id)

            self.assertEqual(repeated, created)
            self.assertEqual(persisted["execution_id"], "execution-first")
            self.assertEqual(persisted["cycle_id"], "phase5-20260521-reserve")
            self.assertEqual(persisted["created_at"], "2026-05-21T09:00:00Z")

    def test_existing_digest_payload_key_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reservation_id = phase5_scheduler_execution_reservation_id("idempotency:requested")
            target = root / SCHEDULER_EXECUTION_RESERVATION_FOLDER / f"{reservation_id}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = Phase5SchedulerExecutionReservationArtifact(
                reservation_id=reservation_id,
                idempotency_key="idempotency:other",
                execution_id="execution-other",
                created_at="2026-05-21T09:00:00Z",
            )
            target.write_text(
                json.dumps(existing.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(Phase5SchedulerExecutionReservationCollisionError):
                create_phase5_scheduler_execution_reservation_artifact(
                    idempotency_key="idempotency:requested",
                    execution_id="execution-requested",
                    created_at="2026-05-21T10:00:00Z",
                    root=root,
                )

    def test_record_execution_ledger_creates_reservation_before_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _start_cycle(root, "phase5-20260521-record")

            cycle, ledger = record_phase5_scheduler_execution_ledger(
                execution_id="execution-record",
                idempotency_key="idempotency:record",
                cycle_id="phase5-20260521-record",
                created_at="2026-05-21T09:00:00Z",
                plan_action="retry_failed_step",
                execution_status="planned",
                would_execute=False,
                root=root,
            )
            reservation = _read_reservation_payload(root, phase5_scheduler_execution_reservation_id("idempotency:record"))

            self.assertIsNotNone(cycle)
            self.assertEqual(reservation["execution_id"], "execution-record")
            self.assertEqual(reservation["idempotency_key"], "idempotency:record")
            self.assertEqual(read_phase5_scheduler_execution_ledger_artifact(ledger.execution_id, root=root), ledger)

    def test_existing_reservation_with_missing_ledger_recovers_same_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _start_cycle(root, "phase5-20260521-recover")
            create_phase5_scheduler_execution_reservation_artifact(
                idempotency_key="idempotency:recover",
                execution_id="execution-recover",
                cycle_id="phase5-20260521-recover",
                created_at="2026-05-21T09:00:00Z",
                root=root,
            )

            cycle, ledger = record_phase5_scheduler_execution_ledger(
                execution_id="execution-recover",
                idempotency_key="idempotency:recover",
                cycle_id="phase5-20260521-recover",
                created_at="2026-05-21T09:05:00Z",
                plan_action="retry_failed_step",
                execution_status="planned",
                would_execute=False,
                root=root,
            )
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260521-recover", root=root)

            self.assertIsNotNone(cycle)
            self.assertEqual(ledger.execution_id, "execution-recover")
            self.assertEqual(stored_cycle.event_refs, [PHASE5_CYCLE_STARTED_EVENT, PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT])

    def test_existing_reservation_conflict_has_no_ledger_or_cycle_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = _start_cycle(root, "phase5-20260521-reservation-conflict")
            create_phase5_scheduler_execution_reservation_artifact(
                idempotency_key="idempotency:reservation-conflict",
                execution_id="execution-existing",
                cycle_id="phase5-20260521-reservation-conflict",
                created_at="2026-05-21T09:00:00Z",
                root=root,
            )

            with self.assertRaises(Phase5SchedulerExecutionIdempotencyConflictError) as raised:
                record_phase5_scheduler_execution_ledger(
                    execution_id="execution-requested",
                    idempotency_key="idempotency:reservation-conflict",
                    cycle_id="phase5-20260521-reservation-conflict",
                    created_at="2026-05-21T09:05:00Z",
                    plan_action="retry_failed_step",
                    execution_status="planned",
                    would_execute=False,
                    root=root,
                )
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260521-reservation-conflict", root=root)

            self.assertEqual(raised.exception.existing_execution_id, "execution-existing")
            self.assertEqual(raised.exception.requested_execution_id, "execution-requested")
            self.assertIsNone(read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-requested", root=root))
            self.assertEqual(stored_cycle, before)


def _read_reservation_payload(root: Path, reservation_id: str) -> dict[str, object]:
    return json.loads((root / SCHEDULER_EXECUTION_RESERVATION_FOLDER / f"{reservation_id}.json").read_text(encoding="utf-8"))
