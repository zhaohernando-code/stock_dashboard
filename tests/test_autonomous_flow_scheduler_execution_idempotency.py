from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ashare_evidence.autonomous_flow import (
    PHASE5_CYCLE_STARTED_EVENT,
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT,
    Phase5SchedulerExecutionIdempotencyConflictError,
    record_phase5_scheduler_execution_ledger,
)
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_execution_artifact_store import (
    create_phase5_scheduler_execution_reservation_artifact,
    find_phase5_scheduler_execution_ledger_by_idempotency_key,
    read_phase5_scheduler_execution_ledger_artifact,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
    read_phase5_scheduler_execution_reservation_artifact,
    write_phase5_scheduler_execution_ledger_artifact,
)
from tests.helpers_autonomous_flow_scheduler_execution import _execution_ledger, _start_cycle


class Phase5SchedulerExecutionIdempotencyTests(unittest.TestCase):
    def test_store_finds_execution_ledger_by_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_phase5_scheduler_execution_ledger_artifact(
                _execution_ledger(execution_id="execution-a", idempotency_key="idempotency:a"),
                root=root,
            )
            write_phase5_scheduler_execution_ledger_artifact(
                _execution_ledger(execution_id="execution-b", idempotency_key="idempotency:b"),
                root=root,
            )

            found = find_phase5_scheduler_execution_ledger_by_idempotency_key("idempotency:b", root=root)
            missing = find_phase5_scheduler_execution_ledger_by_idempotency_key("idempotency:missing", root=root)

            self.assertIsNotNone(found)
            self.assertEqual(found.execution_id, "execution-b")
            self.assertIsNone(missing)

    def test_record_execution_ledger_replays_same_execution_without_rewriting_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _start_cycle(root, "phase5-20260521-replay")
            existing = _execution_ledger(
                execution_id="execution-replay",
                idempotency_key="idempotency:replay",
                cycle_id="phase5-20260521-replay",
                notes="original ledger survives replay",
            )
            write_phase5_scheduler_execution_ledger_artifact(existing, root=root)

            cycle, replayed = record_phase5_scheduler_execution_ledger(
                execution_id="execution-replay",
                idempotency_key="idempotency:replay",
                cycle_id="phase5-20260521-replay",
                created_at="2026-05-21T10:00:00Z",
                plan_action="block_cycle",
                execution_status="blocked",
                would_execute=True,
                notes="new request must not overwrite existing",
                root=root,
            )
            stored = read_phase5_scheduler_execution_ledger_artifact("execution-replay", root=root)
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260521-replay", root=root)

            self.assertEqual(replayed, existing)
            self.assertEqual(stored, existing)
            self.assertIsNotNone(cycle)
            self.assertEqual(
                stored_cycle.event_refs,
                [PHASE5_CYCLE_STARTED_EVENT, PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT],
            )

    def test_record_execution_ledger_replays_same_execution_when_cycle_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing = _execution_ledger(
                execution_id="execution-missing-replay",
                idempotency_key="idempotency:missing-replay",
                cycle_id="missing-cycle",
            )
            write_phase5_scheduler_execution_ledger_artifact(existing, root=root)

            cycle, replayed = record_phase5_scheduler_execution_ledger(
                execution_id="execution-missing-replay",
                idempotency_key="idempotency:missing-replay",
                cycle_id="missing-cycle",
                created_at="2026-05-21T10:00:00Z",
                plan_action="block_cycle",
                execution_status="blocked",
                would_execute=False,
                root=root,
            )

            self.assertIsNone(cycle)
            self.assertEqual(replayed, existing)

    def test_record_execution_ledger_rejects_idempotency_key_conflict_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = _start_cycle(root, "phase5-20260521-conflict")
            create_phase5_scheduler_execution_reservation_artifact(
                idempotency_key="idempotency:conflict",
                execution_id="execution-existing",
                cycle_id="phase5-20260521-conflict",
                created_at="2026-05-21T09:00:00Z",
                root=root,
            )

            with self.assertRaises(Phase5SchedulerExecutionIdempotencyConflictError) as raised:
                record_phase5_scheduler_execution_ledger(
                    execution_id="execution-requested",
                    idempotency_key="idempotency:conflict",
                    cycle_id="phase5-20260521-conflict",
                    created_at="2026-05-21T09:01:00Z",
                    plan_action="retry_failed_step",
                    execution_status="planned",
                    would_execute=False,
                    root=root,
                )
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260521-conflict", root=root)

            self.assertEqual(raised.exception.idempotency_key, "idempotency:conflict")
            self.assertEqual(raised.exception.existing_execution_id, "execution-existing")
            self.assertEqual(raised.exception.requested_execution_id, "execution-requested")
            self.assertIsNone(read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-requested", root=root))
            self.assertEqual(stored_cycle, before)

    def test_record_execution_ledger_rejects_legacy_ledger_conflict_before_new_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = _start_cycle(root, "phase5-20260521-legacy-conflict")
            write_phase5_scheduler_execution_ledger_artifact(
                _execution_ledger(
                    execution_id="execution-existing",
                    idempotency_key="idempotency:legacy-conflict",
                    cycle_id="phase5-20260521-legacy-conflict",
                ),
                root=root,
            )

            with self.assertRaises(Phase5SchedulerExecutionIdempotencyConflictError) as raised:
                record_phase5_scheduler_execution_ledger(
                    execution_id="execution-requested",
                    idempotency_key="idempotency:legacy-conflict",
                    cycle_id="phase5-20260521-legacy-conflict",
                    created_at="2026-05-21T09:01:00Z",
                    plan_action="retry_failed_step",
                    execution_status="planned",
                    would_execute=False,
                    root=root,
                )
            reservation = read_phase5_scheduler_execution_reservation_artifact("idempotency:legacy-conflict", root=root)
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260521-legacy-conflict", root=root)

            self.assertEqual(raised.exception.existing_execution_id, "execution-existing")
            self.assertEqual(raised.exception.requested_execution_id, "execution-requested")
            self.assertEqual(reservation.execution_id, "execution-existing")
            self.assertIsNone(read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-requested", root=root))
            self.assertEqual(stored_cycle, before)
