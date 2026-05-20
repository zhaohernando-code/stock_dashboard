from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    PublishVerificationRef,
)
from ashare_evidence.research_artifact_store import (
    PROJECT_ROOT,
    read_frontend_projection_manifest_artifact,
    read_frontend_projection_manifest_artifact_if_exists,
    read_phase5_cycle_ledger_artifact,
    read_phase5_cycle_ledger_artifact_if_exists,
    read_phase5_gate_readout_artifact,
    read_phase5_gate_readout_artifact_if_exists,
    read_phase5_recovery_ticket_artifact,
    read_phase5_recovery_ticket_artifact_if_exists,
    write_frontend_projection_manifest_artifact,
    write_phase5_cycle_ledger_artifact,
    write_phase5_gate_readout_artifact,
    write_phase5_recovery_ticket_artifact,
)


class AutonomousFlowArtifactStoreTests(unittest.TestCase):
    def test_phase5_autonomous_flow_artifacts_round_trip_in_runtime_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cycle = Phase5CycleLedgerArtifact(
                cycle_id="cycle-20260520-001",
                trigger="manual",
                scope={"portfolio": "short_pick_lab"},
                status="completed",
                started_at="2026-05-20T09:00:00Z",
                finished_at="2026-05-20T09:15:00Z",
                input_contract_versions={"registry": "autonomous_flow_registry.v1"},
                event_refs=["phase5.cycle.started.v1"],
                artifact_refs=["phase5-horizon-study:latest"],
                gate_readout_refs=["gate-20260520-001"],
                recovery_ticket_refs=["ticket-20260520-001"],
                publish_verification_ref=PublishVerificationRef(
                    release_manifest_ref="release-manifest:phase5:20260520",
                    digest="sha256:abc123",
                    event_ref="runtime.publish.verified.v1",
                ),
                next_action="none",
            )
            ticket = Phase5RecoveryTicketArtifact(
                ticket_id="ticket-20260520-001",
                cycle_id=cycle.cycle_id,
                failed_step="publish_verify",
                failure_class="publish_blocked",
                failure_observed_at="2026-05-20T09:05:00Z",
                evidence_refs=["publish-log:20260520"],
                recovery_action="mark_degraded",
                retry_count=1,
                final_status="degraded",
                claim_ceiling_effect="lowered",
                notes="runtime publish verification failed closed",
            )
            readout = Phase5GateReadoutArtifact(
                gate_id="gate-20260520-001",
                cycle_id=cycle.cycle_id,
                gate_status="degraded",
                failing_gate_ids=["publish_verified"],
                incomplete_gate_ids=[],
                claim_ceiling="paper_tracking_candidate",
                source_artifact_ids=["phase5-horizon-study:latest"],
                blocking_reasons=["runtime publish not verified"],
                next_action="rebuild_projection",
                evaluated_at="2026-05-20T09:10:00Z",
            )
            projection = FrontendProjectionManifestArtifact(
                projection_id="projection-20260520-001",
                cycle_id=cycle.cycle_id,
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                source_artifact_ids=["phase5-horizon-study:latest"],
                row_count=3,
                staleness_status="degraded",
                fallback_reason="runtime publish not verified",
                event_refs=["phase5.projection.refreshed.v1"],
            )

            cycle_path = write_phase5_cycle_ledger_artifact(cycle, root=root)
            ticket_path = write_phase5_recovery_ticket_artifact(ticket, root=root)
            readout_path = write_phase5_gate_readout_artifact(readout, root=root)
            projection_path = write_frontend_projection_manifest_artifact(projection, root=root)

            self.assertEqual(cycle_path, root / "autonomous_flow" / "phase5_cycle_ledger" / f"{cycle.cycle_id}.json")
            self.assertEqual(
                ticket_path,
                root / "autonomous_flow" / "phase5_recovery_ticket" / f"{ticket.ticket_id}.json",
            )
            self.assertEqual(readout_path, root / "autonomous_flow" / "phase5_gate_readout" / f"{readout.gate_id}.json")
            self.assertEqual(
                projection_path,
                root / "autonomous_flow" / "frontend_projection_manifest" / f"{projection.projection_id}.json",
            )
            self.assertEqual(read_phase5_cycle_ledger_artifact(cycle.cycle_id, root=root).status, "completed")
            self.assertEqual(read_phase5_recovery_ticket_artifact(ticket.ticket_id, root=root).final_status, "degraded")
            self.assertEqual(read_phase5_gate_readout_artifact(readout.gate_id, root=root).claim_ceiling, "paper_tracking_candidate")
            self.assertEqual(
                read_frontend_projection_manifest_artifact(projection.projection_id, root=root).row_count,
                3,
            )

    def test_phase5_autonomous_flow_artifact_read_if_exists_returns_none_for_missing_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            self.assertIsNone(read_phase5_cycle_ledger_artifact_if_exists(None, root=root))
            self.assertIsNone(read_phase5_cycle_ledger_artifact_if_exists("missing-cycle", root=root))
            self.assertIsNone(read_phase5_recovery_ticket_artifact_if_exists(None, root=root))
            self.assertIsNone(read_phase5_recovery_ticket_artifact_if_exists("missing-ticket", root=root))
            self.assertIsNone(read_phase5_gate_readout_artifact_if_exists(None, root=root))
            self.assertIsNone(read_phase5_gate_readout_artifact_if_exists("missing-gate", root=root))
            self.assertIsNone(read_frontend_projection_manifest_artifact_if_exists(None, root=root))
            self.assertIsNone(read_frontend_projection_manifest_artifact_if_exists("missing-projection", root=root))

    def test_phase5_autonomous_flow_artifact_writes_reject_repo_artifact_root_by_default(self) -> None:
        target_root = PROJECT_ROOT / "artifacts"
        artifact = Phase5GateReadoutArtifact(
            gate_id="unit-test-gate",
            cycle_id="unit-test-cycle",
            gate_status="blocked",
            failing_gate_ids=["contract_registry"],
            incomplete_gate_ids=[],
            claim_ceiling="blocked",
            source_artifact_ids=[],
            blocking_reasons=["repo artifact write is not allowed"],
            next_action="blocked",
            evaluated_at="2026-05-20T09:20:00Z",
        )

        with self.assertRaisesRegex(RuntimeError, "Refusing to write generated research artifact"):
            write_phase5_gate_readout_artifact(artifact, root=target_root)

    def test_publish_verification_ref_does_not_accept_manifest_details(self) -> None:
        with self.assertRaises(ValidationError):
            PublishVerificationRef(
                release_manifest_ref="release-manifest:phase5:20260520",
                digest="sha256:abc123",
                manifest_payload={"files": ["index.html"]},
            )

    def test_frontend_projection_manifest_dedupes_refs_and_rejects_invalid_payload(self) -> None:
        manifest = FrontendProjectionManifestArtifact(
            projection_id="projection-20260520-001",
            cycle_id="cycle-20260520-001",
            projection_name="operations_summary",
            projection_family="operations",
            version="frontend-projection-v1",
            generated_at="2026-05-20T09:12:00Z",
            freshness_at="2026-05-20T09:10:00Z",
            source_artifact_ids=["phase5-horizon-study:latest", "phase5-horizon-study:latest"],
            row_count=1,
            staleness_status="fresh",
            event_refs=["phase5.projection.refreshed.v1", "phase5.projection.refreshed.v1"],
        )

        self.assertEqual(manifest.source_artifact_ids, ["phase5-horizon-study:latest"])
        self.assertEqual(manifest.event_refs, ["phase5.projection.refreshed.v1"])

        with self.assertRaises(ValidationError):
            FrontendProjectionManifestArtifact(
                projection_id="projection-20260520-negative",
                cycle_id="cycle-20260520-001",
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                row_count=-1,
                staleness_status="fresh",
            )

        with self.assertRaises(ValidationError):
            FrontendProjectionManifestArtifact(
                projection_id="projection-20260520-payload",
                cycle_id="cycle-20260520-001",
                projection_name="operations_summary",
                projection_family="operations",
                version="frontend-projection-v1",
                generated_at="2026-05-20T09:12:00Z",
                freshness_at="2026-05-20T09:10:00Z",
                row_count=1,
                staleness_status="fresh",
                payload={"rows": [{"symbol": "000001"}]},
            )


if __name__ == "__main__":
    unittest.main()
