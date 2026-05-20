from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from ashare_evidence.autonomous_flow import (
    PHASE5_CYCLE_STARTED_EVENT,
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT,
    record_phase5_scheduler_execution_ledger,
)
from ashare_evidence.autonomous_flow_artifacts import (
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID,
    Phase5SchedulerExecutionLedgerArtifact,
)
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_execution_artifact_store import (
    read_phase5_scheduler_execution_ledger_artifact,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
    write_phase5_scheduler_execution_ledger_artifact,
)
from tests.helpers_autonomous_flow_scheduler_execution import _execution_ledger, _start_cycle


class Phase5SchedulerExecutionLedgerTests(unittest.TestCase):
    def test_execution_ledger_model_dedupes_defaults_and_rejects_sensitive_identity(self) -> None:
        ledger = Phase5SchedulerExecutionLedgerArtifact(
            execution_id="execution-20260521-am",
            idempotency_key="cycle:phase5-20260521-am:retry_failed_step",
            cycle_id="phase5-20260521-am",
            created_at="2026-05-21T09:00:00Z",
            plan_action="retry_failed_step",
            execution_status="planned",
            would_execute=False,
            diagnostic_refs=["diagnostic-1", "diagnostic-1", "sha256:abc"],
            blocking_reasons=["missing artifact", "missing artifact", "Traceback raw"],
        )

        self.assertEqual(ledger.event_refs, [PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID])
        self.assertEqual(ledger.diagnostic_refs, ["diagnostic-1"])
        self.assertEqual(ledger.blocking_reasons, ["missing artifact"])

        with self.assertRaises(ValidationError):
            Phase5SchedulerExecutionLedgerArtifact(
                execution_id="sha256:abc",
                idempotency_key="cycle:phase5-20260521-am:retry_failed_step",
                created_at="2026-05-21T09:00:00Z",
                plan_action="retry_failed_step",
                execution_status="planned",
                would_execute=False,
            )

    def test_execution_ledger_store_writes_reads_and_returns_none_for_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ledger = _execution_ledger(execution_id="execution-store")

            write_phase5_scheduler_execution_ledger_artifact(ledger, root=root)

            stored = read_phase5_scheduler_execution_ledger_artifact("execution-store", root=root)
            maybe_stored = read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-store", root=root)
            missing = read_phase5_scheduler_execution_ledger_artifact_if_exists("missing", root=root)

            self.assertEqual(stored.execution_id, "execution-store")
            self.assertEqual(maybe_stored, stored)
            self.assertIsNone(missing)
            self.assertTrue((root / "autonomous_flow" / "phase5_scheduler_execution_ledger" / "execution-store.json").exists())

    def test_record_execution_ledger_writes_ledger_and_only_appends_cycle_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = _start_cycle(root, "phase5-20260521-am")

            updated, ledger = record_phase5_scheduler_execution_ledger(
                execution_id="execution-20260521-am",
                idempotency_key="cycle:phase5-20260521-am:retry_failed_step",
                cycle_id="phase5-20260521-am",
                created_at="2026-05-21T09:01:00Z",
                plan_action="retry_failed_step",
                execution_status="planned",
                would_execute=False,
                diagnostic_refs=["diagnostic-1", "diagnostic-1"],
                blocking_reasons=["waiting for explicit executor enablement"],
                notes="record intent before real scheduler execution",
                root=root,
            )
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260521-am", root=root)
            stored_ledger = read_phase5_scheduler_execution_ledger_artifact(ledger.execution_id, root=root)

            self.assertIsNotNone(updated)
            self.assertEqual(stored_ledger.idempotency_key, "cycle:phase5-20260521-am:retry_failed_step")
            self.assertEqual(stored_ledger.diagnostic_refs, ["diagnostic-1"])
            self.assertEqual(stored_cycle.event_refs, [PHASE5_CYCLE_STARTED_EVENT, PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT])
            self.assertEqual(stored_cycle.status, before.status)
            self.assertEqual(stored_cycle.next_action, before.next_action)
            self.assertEqual(stored_cycle.finished_at, before.finished_at)
            self.assertEqual(stored_cycle.recovery_ticket_refs, [])
            self.assertEqual(stored_cycle.artifact_refs, [])
            self.assertEqual(stored_cycle.gate_readout_refs, [])

    def test_record_execution_ledger_allows_missing_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            cycle, ledger = record_phase5_scheduler_execution_ledger(
                execution_id="execution-missing-cycle",
                idempotency_key="cycle:missing-cycle:block_cycle",
                cycle_id="missing-cycle",
                created_at="2026-05-21T09:01:00Z",
                plan_action="block_cycle",
                execution_status="blocked",
                would_execute=False,
                diagnostic_refs=["diagnostic-missing-cycle"],
                blocking_reasons=["cycle ledger missing"],
                notes="record the failed execution boundary",
                root=root,
            )
            stored = read_phase5_scheduler_execution_ledger_artifact(ledger.execution_id, root=root)

            self.assertIsNone(cycle)
            self.assertEqual(stored.cycle_id, "missing-cycle")
            self.assertEqual(stored.execution_status, "blocked")
            self.assertIn(PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT, stored.event_refs)

    def test_record_execution_ledger_redacts_sensitive_payload_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            _cycle, ledger = record_phase5_scheduler_execution_ledger(
                execution_id="execution-redacted",
                idempotency_key="cycle:none:block_cycle",
                created_at="2026-05-21T09:01:00Z",
                plan_action="block_cycle",
                execution_status="blocked",
                would_execute=False,
                diagnostic_refs=["diagnostic-safe", "release-manifest:phase5:20260521"],
                blocking_reasons=["runner_result raw detail", "safe reason"],
                notes="Traceback from input_bundle should not persist",
                root=root,
            )
            persisted = json.loads(
                (
                    root
                    / "autonomous_flow"
                    / "phase5_scheduler_execution_ledger"
                    / f"{ledger.execution_id}.json"
                ).read_text(encoding="utf-8")
            )
            payload_text = json.dumps(persisted, ensure_ascii=False, sort_keys=True)

            self.assertEqual(persisted["diagnostic_refs"], ["diagnostic-safe"])
            self.assertEqual(persisted["blocking_reasons"], ["safe reason"])
            self.assertEqual(persisted["notes"], "[redacted sensitive scheduler execution detail]")
            for forbidden in ("input_bundle", "runner_result", "release-manifest:", "sha256:", "Traceback"):
                self.assertNotIn(forbidden, payload_text)
