from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.model_candidate_runner import (
    build_walk_forward_model_candidate_run_artifact,
    write_walk_forward_model_candidate_run_artifact,
)
from ashare_evidence.model_comparison_report import (
    build_model_comparison_report_artifact,
    write_model_comparison_report_artifact,
)
from ashare_evidence.model_exploration_snapshot import build_model_exploration_p1_artifacts
from ashare_evidence.model_governance_gate import (
    build_model_governance_and_projection_artifacts,
    write_model_governance_and_projection_artifacts,
)
from ashare_evidence.model_spec_registry import build_model_spec_registry_artifact
from ashare_evidence.models import MarketBar, Stock


class ModelCandidateWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.temp_dir.name) / 'candidate-workbench.db'}"
        init_database(self.database_url)

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

    def _build_inputs(self) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        days = [date(2026, 1, 11) + timedelta(days=index) for index in range(4)]
        self._seed_stock("600001.SH", "主板甲", [10 + index * 0.4 for index in range(28)])
        self._seed_stock("600002.SH", "主板乙", [20 + index * 0.15 for index in range(28)])
        self._seed_stock("000300.SH", "沪深300", [100 + index * 0.1 for index in range(28)], industry="benchmark")
        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=days,
                horizons=(10,),
                min_history_days=2,
            )
        registry = build_model_spec_registry_artifact(
            validation_run_id="unit-run",
            source_input_snapshot_id=str(artifacts["model_exploration_input_snapshot"]["artifact_id"]),
        )
        return artifacts["pit_feature_matrix"], artifacts["executable_label_matrix"], registry

    def test_candidate_runner_executes_registered_specs_only_and_blocks_promotion(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()

        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )

        self.assertEqual(run["artifact_type"], "walk_forward_model_candidate_run")
        self.assertEqual(run["promotion_status"], "blocked_from_production")
        self.assertEqual(run["trial_count"], 1)
        self.assertGreater(run["prediction_row_count"], 0)
        self.assertGreater(run["stored_prediction_row_count"], 0)
        self.assertEqual(run["evaluable_row_count"], run["joined_row_count"])
        self.assertGreater(len(run["trial_summaries"][0]["fit_summaries"]), 0)
        self.assertIn("top_5_net_excess_mean", run["trial_summaries"][0]["metrics"])
        self.assertIn("top_10_net_excess_mean", run["trial_summaries"][0]["metrics"])
        self.assertGreater(len(run["trial_diagnostics"][0]["date_rank_ics"]), 0)
        self.assertIn("fitted_model_digest", run["prediction_rows"][0])
        self.assertEqual(
            run["prediction_storage_policy"]["mode"],
            "bounded_inline_sample_with_full_trial_diagnostics",
        )
        self.assertEqual(run["validation_protocol"]["runner_policy"], "registered_model_specs_only")
        self.assertIn("governance_promotion_pending", run["gate_readout"]["blocking_gate_ids"])

    def test_candidate_runner_rejects_unregistered_specs(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()

        with self.assertRaisesRegex(ValueError, "unregistered model specs requested"):
            build_walk_forward_model_candidate_run_artifact(
                validation_run_id="unit-run",
                feature_matrix=feature_matrix,
                label_matrix=label_matrix,
                model_spec_registry=registry,
                min_train_dates=1,
                test_window_dates=2,
                selected_model_spec_ids=["not-registered"],
            )

    def test_comparison_report_summarizes_trials_and_remains_blocked(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )

        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        self.assertEqual(report["artifact_type"], "model_comparison_report")
        self.assertEqual(report["promotion_status"], "blocked_from_production")
        self.assertEqual(report["summary"]["candidate_run_id"], run["artifact_id"])
        self.assertEqual(len(report["candidate_leaderboard"]), 1)
        self.assertIn("top_5_net_excess_mean", report["candidate_leaderboard"][0])
        self.assertEqual(report["overfit_diagnostics"]["diagnostic_scope"], "candidate_run_trial_split_proxy")
        self.assertEqual(report["overfit_diagnostics"]["period_source"], "best_trial_as_of_date_rank_ic")
        self.assertIn(
            "overfit:insufficient_eligible_trials_for_pbo",
            report["gate_readout"]["blocking_gate_ids"],
        )
        self.assertIn(
            "overfit:insufficient_independent_walk_forward_splits_for_overfit",
            report["gate_readout"]["blocking_gate_ids"],
        )
        self.assertEqual(report["winner_dependency"]["best_trial_id"], "baseline_momentum_10d_turnover_cooldown_v1:trial-000")
        self.assertIn("removal_checks", report["winner_dependency"])

    def test_candidate_run_and_report_write_to_research_validation_namespace(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )
        root = Path(self.temp_dir.name) / "artifacts"

        run_path = write_walk_forward_model_candidate_run_artifact(run, artifact_root=root)
        report_path = write_model_comparison_report_artifact(report, artifact_root=root)

        self.assertEqual(
            run_path.parent,
            root / "research_validation" / "walk_forward_model_candidate_runs",
        )
        self.assertEqual(report_path.parent, root / "research_validation" / "model_comparison_reports")

    def test_governance_and_dashboard_projection_gate_model_report(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        artifacts = build_model_governance_and_projection_artifacts(
            validation_run_id="unit-run",
            candidate_run=run,
            comparison_report=report,
        )
        governance = artifacts["governance_promotion_decision"]
        projection = artifacts["dashboard_approved_projection_registry"]

        self.assertEqual(governance["artifact_type"], "governance_promotion_decision")
        self.assertEqual(governance["current_state"], "diagnostic_only")
        self.assertIn("multiple_testing_not_ready", governance["gate_readout"]["blocking_gate_ids"])
        self.assertEqual(projection["artifact_type"], "dashboard_approved_projection_registry")
        self.assertEqual(projection["approved_projection_count"], 0)
        self.assertEqual(
            governance["feature_version"],
            report["feature_version"],
        )
        self.assertEqual(
            projection["feature_version"],
            report["feature_version"],
        )
        self.assertNotIn(
            "governance_promotion_decision_missing_required_field_feature_version",
            projection["gate_readout"]["blocking_gate_ids"],
        )
        self.assertIn(
            "governance_not_approved_for_dashboard_projection",
            projection["gate_readout"]["blocking_gate_ids"],
        )

    def test_governance_and_projection_artifacts_write_to_research_validation_namespace(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )
        artifacts = build_model_governance_and_projection_artifacts(
            validation_run_id="unit-run",
            candidate_run=run,
            comparison_report=report,
        )
        root = Path(self.temp_dir.name) / "artifacts"

        written = write_model_governance_and_projection_artifacts(artifacts, artifact_root=root)

        self.assertEqual(
            written["governance_promotion_decision"].parent,
            root / "research_validation" / "governance_promotion_decisions",
        )
        self.assertEqual(
            written["dashboard_approved_projection_registry"].parent,
            root / "research_validation" / "dashboard_approved_projection_registries",
        )


if __name__ == "__main__":
    unittest.main()
