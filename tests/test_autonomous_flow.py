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
    PHASE5_PROJECTION_REFRESHED_EVENT,
    PHASE5_RECOVERY_RECORDED_EVENT,
    PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT,
    RUNTIME_PUBLISH_VERIFIED_EVENT,
    Phase5CycleNotFoundError,
    attach_publish_verification,
    record_phase5_artifact,
    record_phase5_gate_readout,
    record_phase5_projection_refreshed,
    record_phase5_recovery_ticket,
    record_phase5_scheduler_diagnostic,
    start_phase5_cycle,
)
from ashare_evidence.research_artifact_store import (
    read_frontend_projection_manifest_artifact,
    read_phase5_cycle_ledger_artifact,
    read_phase5_gate_readout_artifact,
    read_phase5_recovery_ticket_artifact,
    read_phase5_scheduler_diagnostic_artifact,
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

    def test_record_phase5_scheduler_diagnostic_writes_artifact_and_only_appends_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                status="running",
                next_action="continue_tracking",
                root=root,
            )

            updated, diagnostic = record_phase5_scheduler_diagnostic(
                diagnostic_id="diagnostic-20260520-am",
                cycle_id="phase5-20260520-am",
                observed_at="2026-05-20T09:06:00Z",
                scheduler_action="open_recovery_ticket",
                severity="blocked",
                failure_class="execution-precondition-failed",
                recommended_recovery_action="open_recovery_ticket",
                blocking_reasons=["cycle precondition failed", "cycle precondition failed"],
                evidence_refs=["phase5_cycle_ledger:phase5-20260520-am"],
                notes="scheduler could not execute recovery action",
                root=root,
            )
            stored_cycle = read_phase5_cycle_ledger_artifact("phase5-20260520-am", root=root)
            stored_diagnostic = read_phase5_scheduler_diagnostic_artifact(diagnostic.diagnostic_id, root=root)

            self.assertIsNotNone(updated)
            self.assertEqual(stored_diagnostic.cycle_id, "phase5-20260520-am")
            self.assertEqual(stored_diagnostic.blocking_reasons, ["cycle precondition failed"])
            self.assertIn(PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT, stored_cycle.event_refs)
            self.assertEqual(stored_cycle.status, before.status)
            self.assertEqual(stored_cycle.next_action, before.next_action)
            self.assertEqual(stored_cycle.finished_at, before.finished_at)
            self.assertEqual(stored_cycle.recovery_ticket_refs, [])

    def test_record_phase5_scheduler_diagnostic_allows_missing_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            cycle, diagnostic = record_phase5_scheduler_diagnostic(
                diagnostic_id="diagnostic-missing-cycle",
                cycle_id="missing-cycle",
                observed_at="2026-05-20T09:06:00Z",
                scheduler_action="open_recovery_ticket",
                severity="blocked",
                failure_class="artifact-missing",
                recommended_recovery_action="open_recovery_ticket",
                blocking_reasons=["cycle ledger missing"],
                evidence_refs=["phase5_cycle_ledger:missing-cycle"],
                notes="scheduler recorded the missing ledger before recovery ticket creation",
                root=root,
            )
            stored = read_phase5_scheduler_diagnostic_artifact(diagnostic.diagnostic_id, root=root)

            self.assertIsNone(cycle)
            self.assertEqual(stored.cycle_id, "missing-cycle")
            self.assertEqual(stored.scheduler_action, "open_recovery_ticket")
            self.assertEqual(stored.failure_class, "artifact-missing")
            self.assertIn(PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT, stored.event_refs)

    def test_record_phase5_scheduler_diagnostic_redacts_sensitive_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            _cycle, diagnostic = record_phase5_scheduler_diagnostic(
                diagnostic_id="diagnostic-redacted",
                cycle_id=None,
                observed_at="2026-05-20T09:06:00Z",
                scheduler_action="block_cycle",
                severity="blocked",
                failure_class="unexpected-error",
                recommended_recovery_action="block_cycle",
                blocking_reasons=["runner_result included raw exception", "safe summary"],
                evidence_refs=["release-manifest:phase5:20260520", "phase5_gate_readout:gate-1", "sha256:abc123"],
                notes="Traceback from input_bundle should not persist",
                root=root,
            )
            persisted = json.loads(
                (
                    root
                    / "autonomous_flow"
                    / "phase5_scheduler_diagnostic"
                    / f"{diagnostic.diagnostic_id}.json"
                ).read_text(encoding="utf-8")
            )
            payload_text = json.dumps(persisted, ensure_ascii=False, sort_keys=True)

            self.assertEqual(persisted["blocking_reasons"], ["safe summary"])
            self.assertEqual(persisted["evidence_refs"], ["phase5_gate_readout:gate-1"])
            for forbidden in ("input_bundle", "runner_result", "release-manifest:", "sha256:", "Traceback"):
                self.assertNotIn(forbidden, payload_text)

    def test_record_phase5_projection_refreshed_writes_manifest_and_appends_cycle_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            updated, manifest = record_phase5_projection_refreshed(
                cycle_id="phase5-20260520-am",
                projection_id="projection-20260520-am",
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                source_artifact_ids=["phase5_horizon_study:20260520", "phase5_horizon_study:20260520"],
                row_count=4,
                staleness_status="fresh",
                event_refs=["frontend.projection.updated.v1", "frontend.projection.updated.v1"],
                root=root,
            )
            stored = read_frontend_projection_manifest_artifact(manifest.projection_id, root=root)

            self.assertEqual(stored.cycle_id, "phase5-20260520-am")
            self.assertEqual(stored.source_artifact_ids, ["phase5_horizon_study:20260520"])
            self.assertEqual(
                stored.event_refs,
                ["frontend.projection.updated.v1", PHASE5_PROJECTION_REFRESHED_EVENT],
            )
            self.assertEqual(updated.artifact_refs, ["frontend_projection_manifest:projection-20260520-am"])
            self.assertIn(PHASE5_PROJECTION_REFRESHED_EVENT, updated.event_refs)
            self.assertEqual(updated.status, "running")

    def test_record_phase5_projection_refreshed_dedupes_repeated_cycle_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            record_phase5_projection_refreshed(
                cycle_id="phase5-20260520-am",
                projection_id="projection-20260520-am",
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                row_count=4,
                staleness_status="fresh",
                root=root,
            )
            updated, _manifest = record_phase5_projection_refreshed(
                cycle_id="phase5-20260520-am",
                projection_id="projection-20260520-am",
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                row_count=4,
                staleness_status="fresh",
                root=root,
            )

            self.assertEqual(updated.artifact_refs, ["frontend_projection_manifest:projection-20260520-am"])
            self.assertEqual(updated.event_refs.count(PHASE5_PROJECTION_REFRESHED_EVENT), 1)

    def test_record_phase5_projection_refreshed_stores_no_full_payload_or_publish_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="manual",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            _updated, manifest = record_phase5_projection_refreshed(
                cycle_id="phase5-20260520-am",
                projection_id="projection-20260520-am",
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                source_artifact_ids=["phase5_horizon_study:20260520"],
                row_count=4,
                staleness_status="degraded",
                fallback_reason="projection source degraded",
                root=root,
            )
            persisted = json.loads(
                (root / "autonomous_flow" / "frontend_projection_manifest" / f"{manifest.projection_id}.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertFalse({"payload", "frontend_payload", "release_manifest", "release_manifest_details", "screenshot"} & set(persisted))
            self.assertEqual(persisted["fallback_reason"], "projection source degraded")

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
                record_phase5_projection_refreshed(
                    cycle_id="missing-cycle",
                    projection_id="projection-missing",
                    projection_name="operations_summary",
                    projection_family="operations",
                    version="frontend-projection-v1",
                    generated_at="2026-05-20T09:12:00Z",
                    freshness_at="2026-05-20T09:10:00Z",
                    row_count=0,
                    staleness_status="stale",
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
