from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_evidence.autonomous_flow import (
    Phase5CycleNotFoundError,
    attach_publish_verification,
    finish_phase5_cycle,
    record_phase5_artifact,
    record_phase5_gate_readout,
    record_phase5_projection_refreshed,
    record_phase5_recovery_ticket,
    start_phase5_cycle,
)
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact


class AutonomousFlowCycleCloseoutTests(unittest.TestCase):
    def test_finish_phase5_cycle_completed_preserves_refs_and_event_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "release-manifest.json"
            manifest_path.write_text(json.dumps({"commit_id": "abc123"}, sort_keys=True), encoding="utf-8")
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="manual",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )
            record_phase5_artifact(
                cycle_id="phase5-20260520-am",
                artifact_ref="phase5_horizon_study:20260520",
                root=root,
            )
            record_phase5_gate_readout(
                cycle_id="phase5-20260520-am",
                gate_id="gate-20260520-am",
                gate_status="passed",
                claim_ceiling="paper_tracking_candidate",
                next_action="continue_tracking",
                evaluated_at="2026-05-20T09:05:00Z",
                root=root,
            )
            record_phase5_recovery_ticket(
                cycle_id="phase5-20260520-am",
                ticket_id="ticket-20260520-am",
                failed_step="projection_refresh",
                failure_class="stale_projection",
                failure_observed_at="2026-05-20T09:06:00Z",
                recovery_action="rebuild_projection",
                final_status="resolved",
                claim_ceiling_effect="unchanged",
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
            before = attach_publish_verification(
                cycle_id="phase5-20260520-am",
                release_manifest_path=manifest_path,
                release_manifest_ref="release-manifest:phase5:20260520",
                root=root,
            )

            updated = finish_phase5_cycle(
                cycle_id="phase5-20260520-am",
                status="completed",
                finished_at="2026-05-20T09:20:00Z",
                next_action="none",
                root=root,
            )
            stored = read_phase5_cycle_ledger_artifact("phase5-20260520-am", root=root)

            self.assertEqual(updated.status, "completed")
            self.assertEqual(updated.finished_at, "2026-05-20T09:20:00Z")
            self.assertEqual(updated.next_action, "none")
            self.assertEqual(stored.event_refs, before.event_refs)
            self.assertEqual(stored.artifact_refs, before.artifact_refs)
            self.assertEqual(stored.gate_readout_refs, before.gate_readout_refs)
            self.assertEqual(stored.recovery_ticket_refs, before.recovery_ticket_refs)
            self.assertEqual(stored.publish_verification_ref, before.publish_verification_ref)

    def test_finish_phase5_cycle_degraded_allows_followup_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            updated = finish_phase5_cycle(
                cycle_id="phase5-20260520-am",
                status="degraded",
                finished_at="2026-05-20T09:20:00Z",
                next_action="rebuild_projection",
                root=root,
            )

            self.assertEqual(updated.status, "degraded")
            self.assertEqual(updated.finished_at, "2026-05-20T09:20:00Z")
            self.assertEqual(updated.next_action, "rebuild_projection")

    def test_finish_phase5_cycle_blocked_requires_blocked_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            updated = finish_phase5_cycle(
                cycle_id="phase5-20260520-am",
                status="blocked",
                finished_at="2026-05-20T09:20:00Z",
                next_action="blocked",
                root=root,
            )

            self.assertEqual(updated.status, "blocked")
            self.assertEqual(updated.next_action, "blocked")

            with self.assertRaisesRegex(ValueError, 'requires next_action="blocked"'):
                finish_phase5_cycle(
                    cycle_id="phase5-20260520-am",
                    status="blocked",
                    finished_at="2026-05-20T09:25:00Z",
                    next_action="continue_tracking",
                    root=root,
                )

    def test_finish_phase5_cycle_completed_rejects_blocked_or_retry_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            with self.assertRaisesRegex(ValueError, "cannot use blocked or retry_failed_step"):
                finish_phase5_cycle(
                    cycle_id="phase5-20260520-am",
                    status="completed",
                    finished_at="2026-05-20T09:20:00Z",
                    next_action="blocked",
                    root=root,
                )
            with self.assertRaisesRegex(ValueError, "cannot use blocked or retry_failed_step"):
                finish_phase5_cycle(
                    cycle_id="phase5-20260520-am",
                    status="completed",
                    finished_at="2026-05-20T09:20:00Z",
                    next_action="retry_failed_step",
                    root=root,
                )

    def test_finish_phase5_cycle_degraded_rejects_none_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            start_phase5_cycle(
                cycle_id="phase5-20260520-am",
                trigger="scheduled",
                started_at="2026-05-20T09:00:00Z",
                root=root,
            )

            with self.assertRaisesRegex(ValueError, 'cannot use next_action="none"'):
                finish_phase5_cycle(
                    cycle_id="phase5-20260520-am",
                    status="degraded",
                    finished_at="2026-05-20T09:20:00Z",
                    next_action="none",
                    root=root,
                )

    def test_finish_phase5_cycle_missing_cycle_raises_explicit_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with self.assertRaisesRegex(Phase5CycleNotFoundError, "does not exist: missing-cycle"):
                finish_phase5_cycle(
                    cycle_id="missing-cycle",
                    status="completed",
                    finished_at="2026-05-20T09:20:00Z",
                    next_action="none",
                    root=root,
                )


if __name__ == "__main__":
    unittest.main()
