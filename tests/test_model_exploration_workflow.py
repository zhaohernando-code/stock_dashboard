from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.model_exploration_workflow import run_shortpick_model_exploration_workbench
from ashare_evidence.models import MarketBar, Stock


class ModelExplorationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "workflow.db"
        self.database_url = f"sqlite:///{self.database_path}"
        init_database(self.database_url)
        self._seed_stock("600001.SH", "主板甲", [10 + index * 0.4 for index in range(28)])
        self._seed_stock("600002.SH", "主板乙", [20 + index * 0.15 for index in range(28)])
        self._seed_stock("000300.SH", "沪深300", [100 + index * 0.1 for index in range(28)], industry="benchmark")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_stock(self, symbol: str, name: str, prices: list[float], *, industry: str = "制造业") -> None:
        ticker, _, exchange = symbol.partition(".")
        with session_scope(self.database_url) as session:
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange or "SH",
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={"industry": industry},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            for index, price in enumerate(prices):
                observed_day = date(2026, 1, 1) + timedelta(days=index)
                session.add(
                    MarketBar(
                        bar_key=f"bar-{symbol}-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(
                            observed_day.year,
                            observed_day.month,
                            observed_day.day,
                            7,
                            0,
                            tzinfo=UTC,
                        ),
                        open_price=price - 0.5,
                        high_price=price + 1.0,
                        low_price=price - 1.0,
                        close_price=price,
                        volume=2000 + index,
                        amount=price * (2000 + index),
                        turnover_rate=1.0,
                        raw_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://bar/{symbol}/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": symbol, "index": index}),
                    )
                )

    def test_workflow_writes_research_artifacts_without_production_effect(self) -> None:
        with session_scope(self.database_url) as session:
            payload = run_shortpick_model_exploration_workbench(
                session,
                database_url=self.database_url,
                validation_run_id="workflow-unit",
                as_of_dates=[date(2026, 1, 11), date(2026, 1, 12), date(2026, 1, 13)],
                selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
                min_train_dates=1,
                test_window_dates=1,
                artifact_root=Path(self.temp_dir.name) / "artifacts",
            )

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["production_effect"], "forbidden")
        self.assertEqual(payload["promotion_status"], "blocked_from_production")
        self.assertIn("model_comparison_report", payload["artifact_summaries"])
        self.assertEqual(
            payload["artifact_summaries"]["dashboard_approved_projection_registry"]["promotion_status"],
            "blocked_from_production",
        )

    def test_cli_runs_model_exploration_workflow_as_offline_research(self) -> None:
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-model-exploration-run",
                    "--database-url",
                    self.database_url,
                    "--validation-run-id",
                    "workflow-cli-unit",
                    "--as-of-date",
                    "2026-01-11",
                    "--as-of-date",
                    "2026-01-12",
                    "--model-spec-id",
                    "baseline_momentum_10d_turnover_cooldown_v1",
                    "--min-train-dates",
                    "1",
                    "--test-window-dates",
                    "1",
                    "--artifact-root",
                    str(Path(self.temp_dir.name) / "cli-artifacts"),
                    "--no-write-artifacts",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["workflow"], "shortpick_model_exploration_workbench_p1")
        self.assertFalse(payload["write_artifacts"])
        self.assertEqual(payload["runtime_db_write_policy"], "read_only_input_no_business_table_writes")
        self.assertEqual(payload["promotion_status"], "blocked_from_production")

    def test_cli_builds_input_snapshot_only_for_streaming_matrix_rebuild(self) -> None:
        stdout = io.StringIO()
        artifact_root = Path(self.temp_dir.name) / "input-snapshot-only-artifacts"

        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-model-input-snapshot-build",
                    "--database-url",
                    self.database_url,
                    "--validation-run-id",
                    "workflow-input-snapshot-only-unit",
                    "--as-of-start",
                    "2026-01-01",
                    "--as-of-end",
                    "2026-01-20",
                    "--artifact-root",
                    str(artifact_root),
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["artifact_type"], "model_exploration_input_snapshot")
        self.assertEqual(payload["build_mode"], "input_snapshot_only_streaming_matrix_rebuild_required")
        self.assertEqual(payload["storage_boundary"], "research_validation_artifact_store_only")
        self.assertEqual(payload["universe_row_count"], 0)
        self.assertEqual(payload["eligible_symbol_count"], 2)
        self.assertEqual(payload["as_of_date_count"], 20)
        self.assertTrue(Path(payload["path"]).exists())

    def test_workflow_can_reuse_existing_matrix_artifacts(self) -> None:
        artifact_root = Path(self.temp_dir.name) / "reuse-artifacts"
        with session_scope(self.database_url) as session:
            first = run_shortpick_model_exploration_workbench(
                session,
                database_url=self.database_url,
                validation_run_id="workflow-reuse-source",
                as_of_dates=[date(2026, 1, 11), date(2026, 1, 12), date(2026, 1, 13)],
                selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
                min_train_dates=1,
                test_window_dates=1,
                artifact_root=artifact_root,
            )
        input_path = first["artifact_summaries"]["model_exploration_input_snapshot"]["path"]
        feature_path = first["artifact_summaries"]["pit_feature_matrix"]["path"]
        label_path = first["artifact_summaries"]["executable_label_matrix"]["path"]

        with session_scope(self.database_url) as session:
            second = run_shortpick_model_exploration_workbench(
                session,
                database_url=self.database_url,
                validation_run_id="workflow-reuse-consumer",
                selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
                min_train_dates=1,
                test_window_dates=1,
                artifact_root=artifact_root,
                input_snapshot_artifact=input_path,
                feature_matrix_artifact=feature_path,
                label_matrix_artifact=label_path,
            )

        self.assertTrue(second["matrix_artifacts_reused"])
        self.assertIsNone(second["artifact_summaries"]["pit_feature_matrix"]["path"])
        self.assertEqual(
            second["matrix_artifact_ids"]["pit_feature_matrix"],
            first["artifact_summaries"]["pit_feature_matrix"]["artifact_id"],
        )

        with session_scope(self.database_url) as session:
            streamed = run_shortpick_model_exploration_workbench(
                session,
                database_url=self.database_url,
                validation_run_id="workflow-reuse-streamed-consumer",
                selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
                min_train_dates=1,
                test_window_dates=1,
                artifact_root=artifact_root,
                input_snapshot_artifact=input_path,
                feature_matrix_artifact=feature_path,
                label_matrix_artifact=label_path,
                stream_matrix_replay=True,
            )

        self.assertTrue(streamed["stream_matrix_replay"])
        self.assertEqual(
            streamed["matrix_artifact_ids"]["pit_feature_matrix"],
            first["artifact_summaries"]["pit_feature_matrix"]["artifact_id"],
        )
        self.assertEqual(
            streamed["matrix_artifact_ids"]["executable_label_matrix"],
            first["artifact_summaries"]["executable_label_matrix"]["artifact_id"],
        )
        governance_blockers = streamed["blocking_summary"]["governance"]["blocking_gate_ids"]
        self.assertFalse(
            any("missing_required_field_source" in blocker for blocker in governance_blockers),
            governance_blockers,
        )


if __name__ == "__main__":
    unittest.main()
