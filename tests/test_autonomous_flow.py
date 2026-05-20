from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ashare_evidence.autonomous_flow import (
    PHASE5_ARTIFACT_PRODUCED_EVENT,
    PHASE5_CYCLE_STARTED_EVENT,
    PHASE5_GATE_EVALUATED_EVENT,
    PHASE5_RECOVERY_RECORDED_EVENT,
    RUNTIME_PUBLISH_VERIFIED_EVENT,
    Phase5CycleNotFoundError,
    attach_publish_verification,
    record_phase5_artifact,
    record_phase5_gate_readout,
    record_phase5_recovery_ticket,
    start_phase5_cycle,
)
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    read_phase5_gate_readout_artifact,
    read_phase5_recovery_ticket_artifact,
)


class AutonomousFlowCyclePrimitiveTests(unittest.TestCase):
    def test_start_phase5_cycle_writes_ledger_with_started_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            cycle = start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="manual",
                started_at="2026-05-20T09:00:00Z",
                scope={"portfolio": "short_pick_lab"},
                input_contract_versions={"registry": "autonomous_flow_registry.v1"},
                root=root,
            )

            stored = read_phase5_cycle_ledger_artifact(cycle.cycle_id, root=root)
            self.assertEqual(stored.status, "running")
            self.assertEqual(stored.event_refs, [PHASE5_CYCLE_STARTED_EVENT])
            self.assertEqual(stored.next_action, "continue_tracking")
            self.assertEqual(stored.scope, {"portfolio": "short_pick_lab"})

    def test_record_phase5_artifact_appends_ref_and_event_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            record_phase5_artifact(
                cycle_id="phase5-20260520-am",
                artifact_ref="phase5_horizon_study:20260520",
                root=root,
            )
            updated = record_phase5_artifact(
                cycle_id="phase5-20260520-am",
                artifact_ref="phase5_horizon_study:20260520",
                root=root,
            )

            self.assertEqual(updated.artifact_refs, ["phase5_horizon_study:20260520"])
            self.assertEqual(updated.event_refs.count(PHASE5_ARTIFACT_PRODUCED_EVENT), 1)

    def test_record_phase5_gate_readout_writes_artifact_and_appends_gate_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            updated, readout = record_phase5_gate_readout(
                cycle_id="phase5-20260520-am",
                gate_id="gate-20260520-am",
                gate_status="degraded",
                failing_gate_ids=["publish_verified", "publish_verified"],
                incomplete_gate_ids=[],
                claim_ceiling="paper_tracking_candidate",
                source_artifact_ids=["phase5_horizon_study:20260520", "phase5_horizon_study:20260520"],
                blocking_reasons=["runtime publish not verified"],
                next_action="rebuild_projection",
                evaluated_at="2026-05-20T09:05:00Z",
                root=root,
            )

            stored = read_phase5_gate_readout_artifact(readout.gate_id, root=root)
            self.assertEqual(stored.cycle_id, "phase5-20260520-am")
            self.assertEqual(stored.source_artifact_ids, ["phase5_horizon_study:20260520"])
            self.assertEqual(stored.failing_gate_ids, ["publish_verified"])
            self.assertEqual(updated.gate_readout_refs, ["gate-20260520-am"])
            self.assertIn(PHASE5_GATE_EVALUATED_EVENT, updated.event_refs)
            self.assertEqual(updated.next_action, "rebuild_projection")

    def test_record_phase5_recovery_ticket_writes_artifact_and_appends_ticket_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="retry",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            updated, ticket = record_phase5_recovery_ticket(
                cycle_id="phase5-20260520-am",
                ticket_id="ticket-20260520-am",
                failed_step="publish_verify",
                failure_class="publish_blocked",
                failure_observed_at="2026-05-20T09:06:00Z",
                evidence_refs=["release-manifest:phase5:20260520", "release-manifest:phase5:20260520"],
                recovery_action="mark_degraded",
                retry_count=1,
                final_status="degraded",
                claim_ceiling_effect="lowered",
                notes="publish verification failed closed",
                root=root,
            )

            stored = read_phase5_recovery_ticket_artifact(ticket.ticket_id, root=root)
            self.assertEqual(stored.evidence_refs, ["release-manifest:phase5:20260520"])
            self.assertEqual(updated.recovery_ticket_refs, ["ticket-20260520-am"])
            self.assertIn(PHASE5_RECOVERY_RECORDED_EVENT, updated.event_refs)
            self.assertEqual(updated.status, "degraded")

    def test_attach_publish_verification_stores_only_manifest_ref_digest_and_event_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "release-manifest.json"
            manifest_payload = {"commit_id": "abc123", "files": [{"path": "index.html", "status": "ok"}]}
            manifest_path.write_text(json.dumps(manifest_payload, sort_keys=True), encoding="utf-8")
            expected_digest = f"sha256:{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}"
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="manual",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            updated = attach_publish_verification(
                cycle_id="phase5-20260520-am",
                release_manifest_path=manifest_path,
                release_manifest_ref="release-manifest:phase5:20260520",
                root=root,
            )
            stored = read_phase5_cycle_ledger_artifact("phase5-20260520-am", root=root)

            self.assertEqual(updated.publish_verification_ref, stored.publish_verification_ref)
            self.assertIsNotNone(stored.publish_verification_ref)
            self.assertEqual(stored.publish_verification_ref.release_manifest_ref, "release-manifest:phase5:20260520")
            self.assertEqual(stored.publish_verification_ref.digest, expected_digest)
            self.assertEqual(stored.publish_verification_ref.event_ref, RUNTIME_PUBLISH_VERIFIED_EVENT)
            self.assertIn(RUNTIME_PUBLISH_VERIFIED_EVENT, stored.event_refs)
            self.assertEqual(
                set(stored.publish_verification_ref.model_dump(mode="json")),
                {"release_manifest_ref", "digest", "event_ref"},
            )

    def test_missing_cycle_updates_raise_explicit_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "release-manifest.json"
            manifest_path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(Phase5CycleNotFoundError, "does not exist: missing-cycle"):
                record_phase5_artifact(cycle_id="missing-cycle", artifact_ref="phase5_horizon_study:20260520", root=root)
            with self.assertRaisesRegex(Phase5CycleNotFoundError, "does not exist: missing-cycle"):
                record_phase5_gate_readout(
                    cycle_id="missing-cycle",
                    gate_id="gate-missing",
                    gate_status="blocked",
                    claim_ceiling="paper_tracking_candidate",
                    next_action="recover",
                    evaluated_at="2026-05-20T09:05:00Z",
                    root=root,
                )
            with self.assertRaisesRegex(Phase5CycleNotFoundError, "does not exist: missing-cycle"):
                record_phase5_recovery_ticket(
                    cycle_id="missing-cycle",
                    ticket_id="ticket-missing",
                    failed_step="publish_verify",
                    failure_class="publish_blocked",
                    failure_observed_at="2026-05-20T09:06:00Z",
                    recovery_action="mark_blocked",
                    final_status="blocked",
                    claim_ceiling_effect="lowered",
                    root=root,
                )
            with self.assertRaisesRegex(Phase5CycleNotFoundError, "does not exist: missing-cycle"):
                attach_publish_verification(
                    cycle_id="missing-cycle",
                    release_manifest_path=manifest_path,
                    release_manifest_ref="release-manifest:phase5:missing",
                    root=root,
                )


if __name__ == "__main__":
    unittest.main()
