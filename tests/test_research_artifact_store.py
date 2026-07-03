from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from ashare_evidence.research_artifact_store import (
    PROJECT_ROOT,
    artifact_root_from_database_url,
    portfolio_backtest_artifact_id,
    read_backtest_artifact,
    read_manifest,
    read_phase5_holding_policy_experiment_artifact,
    read_phase5_holding_policy_study_artifact,
    read_phase5_horizon_study_artifact,
    read_phase5_producer_contract_study_artifact,
    read_replay_alignment_artifact,
    read_shortpick_combined_ledger_backfill_artifacts,
    read_shortpick_control_inventory_archive_artifacts,
    read_shortpick_strategy_retirement_artifacts,
    read_validation_metrics,
    resolve_backtest_artifact,
    write_backtest_artifact,
    write_manifest,
    write_phase5_holding_policy_experiment_artifact,
    write_phase5_holding_policy_study_artifact,
    write_phase5_horizon_study_artifact,
    write_phase5_producer_contract_study_artifact,
    write_replay_alignment_artifact,
    write_research_validation_artifact,
    write_shortpick_combined_ledger_backfill_artifact_record,
    write_shortpick_control_inventory_archive_artifact_record,
    write_shortpick_lab_artifact,
    write_shortpick_strategy_retirement_artifact_record,
    write_validation_metrics,
)
from ashare_evidence.research_artifacts import (
    ArtifactSplitView,
    BacktestArtifactView,
    Phase5HoldingPolicyExperimentArtifactView,
    Phase5HoldingPolicyStudyArtifactView,
    Phase5HorizonStudyArtifactView,
    Phase5ProducerContractStudyArtifactView,
    ReplayAlignmentArtifactView,
    ResearchArtifactManifestView,
    ValidationMetricsArtifactView,
)


class ResearchArtifactStoreTests(unittest.TestCase):
    def test_artifact_root_env_overrides_sqlite_database_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            configured_root = Path(temp_dir) / "runtime-artifacts"
            database_url = f"sqlite:///{Path(temp_dir) / 'db' / 'ashare_dashboard.db'}"

            with patch.dict("os.environ", {"ASHARE_ARTIFACT_ROOT": str(configured_root)}):
                self.assertEqual(artifact_root_from_database_url(database_url), configured_root)

    def test_in_memory_sqlite_artifact_root_uses_temp_directory(self) -> None:
        root = artifact_root_from_database_url("sqlite:///:memory:")

        self.assertTrue(root.is_absolute())
        self.assertNotEqual(root, PROJECT_ROOT / "artifacts")
        self.assertNotEqual(root, PROJECT_ROOT / "data" / "artifacts")
        self.assertIn("ashare-evidence-artifacts", root.parts)

    def test_repo_artifact_writes_require_explicit_allow(self) -> None:
        target_root = PROJECT_ROOT / "data" / "artifacts"

        with self.assertRaisesRegex(RuntimeError, "Refusing to write generated research artifact"):
            write_shortpick_lab_artifact(
                artifact_id="unit-test-guard",
                payload={"status": "should_not_write_to_repo"},
                root=target_root,
            )

    def test_runtime_data_artifact_root_is_writable_without_project_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "ashare-dashboard"
            target_root = runtime_root / "data" / "artifacts"

            with patch("ashare_evidence.research_artifact_store.PROJECT_ROOT", runtime_root):
                artifact_path = write_shortpick_lab_artifact(
                    artifact_id="unit-test-runtime-artifact",
                    payload={"status": "runtime_write_allowed"},
                    root=target_root,
                )

            self.assertEqual(artifact_path.parent, target_root / "shortpick_lab")
            self.assertTrue(artifact_path.exists())

    def test_research_validation_artifacts_write_to_isolated_validation_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            universe_path = write_research_validation_artifact(
                "objective_frozen_universe",
                "objective-frozen-universe-unit",
                {
                    "artifact_type": "objective_frozen_universe",
                    "claim_ceiling": "universe_definition_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            snapshot_path = write_research_validation_artifact(
                "research_input_snapshot",
                "research-input-snapshot-unit",
                {
                    "artifact_type": "research_input_snapshot",
                    "claim_ceiling": "input_boundary_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            factor_path = write_research_validation_artifact(
                "factor_ic_study",
                "factor-ic-study-unit",
                {
                    "artifact_type": "factor_ic_study",
                    "promotion_status": "blocked_from_production",
                    "validation_protocol": {"feature_source_status": "legacy_diagnostic_only"},
                },
                root=root,
            )
            pit_path = write_research_validation_artifact(
                "pit_feature_store",
                "pit-feature-store-unit",
                {
                    "artifact_type": "pit_feature_store",
                    "claim_ceiling": "feature_store_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            walk_forward_path = write_research_validation_artifact(
                "walk_forward_purge_embargo",
                "walk-forward-protocol-unit",
                {
                    "artifact_type": "walk_forward_purge_embargo",
                    "claim_ceiling": "walk_forward_protocol_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            multiple_testing_path = write_research_validation_artifact(
                "pbo_dsr_multiple_comparison",
                "pbo-dsr-unit",
                {
                    "artifact_type": "pbo_dsr_multiple_comparison",
                    "claim_ceiling": "multiple_testing_diagnostic_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            oos_path = write_research_validation_artifact(
                "oos_validation",
                "oos-validation-unit",
                {
                    "artifact_type": "oos_validation",
                    "claim_ceiling": "oos_validation_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            governance_path = write_research_validation_artifact(
                "governance_promotion_decision",
                "governance-promotion-decision-unit",
                {
                    "artifact_type": "governance_promotion_decision",
                    "claim_ceiling": "diagnostic_research_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            projection_registry_path = write_research_validation_artifact(
                "dashboard_approved_projection_registry",
                "dashboard-approved-projection-registry-unit",
                {
                    "artifact_type": "dashboard_approved_projection_registry",
                    "claim_ceiling": "diagnostic_summary_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            model_snapshot_path = write_research_validation_artifact(
                "model_exploration_input_snapshot",
                "model-exploration-input-snapshot-unit",
                {
                    "artifact_type": "model_exploration_input_snapshot",
                    "claim_ceiling": "data_coverage_blocked",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            universe_date_matrix_path = write_research_validation_artifact(
                "universe_date_matrix",
                "universe-date-matrix-unit",
                {
                    "artifact_type": "universe_date_matrix",
                    "claim_ceiling": "data_coverage_blocked",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            feature_matrix_path = write_research_validation_artifact(
                "pit_feature_matrix",
                "pit-feature-matrix-unit",
                {
                    "artifact_type": "pit_feature_matrix",
                    "claim_ceiling": "feature_matrix_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            label_matrix_path = write_research_validation_artifact(
                "executable_label_matrix",
                "executable-label-matrix-unit",
                {
                    "artifact_type": "executable_label_matrix",
                    "claim_ceiling": "label_matrix_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            spec_registry_path = write_research_validation_artifact(
                "model_spec_registry",
                "model-spec-registry-unit",
                {
                    "artifact_type": "model_spec_registry",
                    "claim_ceiling": "registry_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            candidate_run_path = write_research_validation_artifact(
                "walk_forward_model_candidate_run",
                "walk-forward-model-candidate-run-unit",
                {
                    "artifact_type": "walk_forward_model_candidate_run",
                    "claim_ceiling": "candidate_run_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            comparison_report_path = write_research_validation_artifact(
                "model_comparison_report",
                "model-comparison-report-unit",
                {
                    "artifact_type": "model_comparison_report",
                    "claim_ceiling": "comparison_report_only",
                    "promotion_status": "blocked_from_production",
                },
                root=root,
            )
            sweep_path = write_research_validation_artifact(
                "weight_sweep_study",
                "weight-sweep-study-unit",
                {"artifact_type": "weight_sweep_study", "promotion_status": "blocked_from_production"},
                root=root,
            )

            self.assertEqual(universe_path.parent, root / "research_validation" / "objective_universes")
            self.assertEqual(snapshot_path.parent, root / "research_validation" / "input_snapshots")
            self.assertEqual(pit_path.parent, root / "research_validation" / "pit_feature_store")
            self.assertEqual(walk_forward_path.parent, root / "research_validation" / "walk_forward_protocols")
            self.assertEqual(multiple_testing_path.parent, root / "research_validation" / "multiple_testing_diagnostics")
            self.assertEqual(oos_path.parent, root / "research_validation" / "oos_validations")
            self.assertEqual(governance_path.parent, root / "research_validation" / "governance_promotion_decisions")
            self.assertEqual(
                projection_registry_path.parent,
                root / "research_validation" / "dashboard_approved_projection_registries",
            )
            self.assertEqual(
                model_snapshot_path.parent,
                root / "research_validation" / "model_exploration_input_snapshots",
            )
            self.assertEqual(universe_date_matrix_path.parent, root / "research_validation" / "universe_date_matrices")
            self.assertEqual(feature_matrix_path.parent, root / "research_validation" / "pit_feature_matrices")
            self.assertEqual(label_matrix_path.parent, root / "research_validation" / "executable_label_matrices")
            self.assertEqual(spec_registry_path.parent, root / "research_validation" / "model_spec_registries")
            self.assertEqual(
                candidate_run_path.parent,
                root / "research_validation" / "walk_forward_model_candidate_runs",
            )
            self.assertEqual(comparison_report_path.parent, root / "research_validation" / "model_comparison_reports")
            self.assertEqual(factor_path.parent, root / "research_validation" / "factor_ic_studies")
            self.assertEqual(sweep_path.parent, root / "research_validation" / "weight_sweep_studies")
            self.assertFalse((root / "studies" / factor_path.name).exists())
            self.assertEqual(json.loads(factor_path.read_text(encoding="utf-8"))["promotion_status"], "blocked_from_production")

    def test_research_validation_artifact_rejects_unknown_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "unsupported research validation artifact type"):
                write_research_validation_artifact(
                    "phase5_horizon_study",
                    "not-validation",
                    {"artifact_type": "phase5_horizon_study"},
                    root=Path(temp_dir),
                )

    def test_shortpick_retirement_artifact_source_reads_only_ready_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ready = {
                "artifact_id": "shortpick-retirement:fixture",
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "schema_version": "v1",
                "strategy_id": "strategy-fixture",
                "decision_log_ref": "DECISIONS.md#fixture",
            }
            write_shortpick_strategy_retirement_artifact_record(ready, root=root)
            blocked = root / "shortpick_strategy_retirements" / "blocked.json"
            blocked.write_text(
                json.dumps(
                    {
                        "artifact_id": "blocked-fixture",
                        "status": "blocked",
                        "artifact_family": "shortpick_strategy_retirement",
                        "strategy_id": "strategy-fixture",
                    }
                ),
                encoding="utf-8",
            )
            duplicate = root / "shortpick_strategy_retirements" / "duplicate-ready.json"
            duplicate.write_text(json.dumps(ready), encoding="utf-8")

            source = read_shortpick_strategy_retirement_artifacts(root=root)

            self.assertEqual(source["status"], "ready")
            self.assertEqual(source["artifact_count"], 1)
            self.assertEqual(source["ignored_count"], 2)
            self.assertEqual(source["artifacts"][0]["artifact_id"], "shortpick-retirement:fixture")

    def test_shortpick_control_inventory_archive_source_reads_only_ready_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ready = {
                "artifact_id": "shortpick-control-inventory-archive:fixture",
                "artifact_type": "shortpick_control_inventory_archive",
                "status": "ready",
                "decision_basis": "inventory_diagnostic_value",
                "decision_log_ref": "DECISIONS.md#inventory-fixture",
                "archive_decisions": [
                    {
                        "strategy_id": "market_factor_control__legacy__family__next_close__2",
                        "tracking_group": "market_factor_control",
                        "role": "legacy",
                        "family": "family",
                        "entry_price_source": "next_close",
                        "source_rank": 2,
                        "archive_reason_code": "dormant_legacy_control",
                    }
                ],
            }
            write_shortpick_control_inventory_archive_artifact_record(ready, root=root)
            blocked = root / "shortpick_control_inventory_archives" / "blocked.json"
            blocked.write_text(
                json.dumps(
                    {
                        "artifact_id": "blocked-fixture",
                        "artifact_type": "shortpick_control_inventory_archive",
                        "status": "blocked",
                        "decision_basis": "inventory_diagnostic_value",
                        "archive_decisions": [],
                    }
                ),
                encoding="utf-8",
            )
            duplicate = root / "shortpick_control_inventory_archives" / "duplicate-ready.json"
            duplicate.write_text(json.dumps(ready), encoding="utf-8")

            source = read_shortpick_control_inventory_archive_artifacts(root=root)

            self.assertEqual(source["status"], "ready")
            self.assertEqual(source["artifact_count"], 1)
            self.assertEqual(source["ignored_count"], 2)
            self.assertEqual(source["artifacts"][0]["artifact_id"], "shortpick-control-inventory-archive:fixture")

    def test_shortpick_combined_ledger_source_reads_only_ready_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ready = {
                "artifact_id": "shortpick-combined-ledger-backfill:fixture",
                "artifact_type": "shortpick_combined_ledger_backfill",
                "status": "ready",
                "ledger_mode": "combined_paper_tracking_ledger",
                "selection_policy": "filter_ranked_pool_select_first_allowed",
                "headline_metric_filter_policy": "true_forward_queries_must_filter_evidence_basis_true_forward_tracking",
                "combined_rows": [
                    {
                        "combined_ledger_row_id": "row-retro-1",
                        "evidence_basis": "retrospective_forward_replay",
                        "retrospective": True,
                        "symbol": "600001.SH",
                        "signal_date": "2026-05-10",
                    }
                ],
            }
            write_shortpick_combined_ledger_backfill_artifact_record(ready, root=root)
            blocked = root / "shortpick_combined_ledgers" / "blocked.json"
            blocked.write_text(
                json.dumps(
                    {
                        "artifact_id": "blocked-fixture",
                        "artifact_type": "shortpick_combined_ledger_backfill",
                        "status": "blocked",
                        "combined_rows": ready["combined_rows"],
                    }
                ),
                encoding="utf-8",
            )
            duplicate = root / "shortpick_combined_ledgers" / "duplicate-ready.json"
            duplicate.write_text(json.dumps(ready), encoding="utf-8")
            missing_row_id = root / "shortpick_combined_ledgers" / "missing-row-id.json"
            missing_row_id.write_text(
                json.dumps({**ready, "artifact_id": "missing-row-id", "combined_rows": [{"evidence_basis": "retrospective_forward_replay"}]}),
                encoding="utf-8",
            )
            missing_basis = root / "shortpick_combined_ledgers" / "missing-basis.json"
            missing_basis.write_text(
                json.dumps({**ready, "artifact_id": "missing-basis", "combined_rows": [{"combined_ledger_row_id": "row-missing-basis"}]}),
                encoding="utf-8",
            )
            unknown_basis = root / "shortpick_combined_ledgers" / "unknown-basis.json"
            unknown_basis.write_text(
                json.dumps(
                    {
                        **ready,
                        "artifact_id": "unknown-basis",
                        "combined_rows": [
                            {
                                "combined_ledger_row_id": "row-unknown-basis",
                                "evidence_basis": "historical_backtest",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            source = read_shortpick_combined_ledger_backfill_artifacts(root=root)

            self.assertEqual(source["status"], "ready")
            self.assertEqual(source["artifact_count"], 1)
            self.assertEqual(source["ignored_count"], 5)
            self.assertEqual(source["artifacts"][0]["artifact_id"], "shortpick-combined-ledger-backfill:fixture")
            ignored_reasons = [item["reason"] for item in source["ignored"]]
            self.assertEqual(ignored_reasons.count("duplicate_artifact_id"), 1)
            self.assertEqual(ignored_reasons.count("not_ready_shortpick_combined_ledger_backfill_artifact"), 4)

    def test_resolve_backtest_artifact_falls_back_to_canonical_portfolio_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = BacktestArtifactView(
                artifact_id="portfolio-backtest:sim-20260427122709-8da19b-model",
                manifest_id="rolling-validation:phase2-portfolio-backtests",
                strategy_definition="topk_drop",
                position_limit_definition="single_name_le_20pct",
                execution_assumptions="paper_fills_only",
                benchmark_definition="active_watchlist_equal_weight_proxy",
                cost_definition="35 bps",
                annualized_return=0.0,
                annualized_excess_return=0.0024,
                max_drawdown=0.0,
                sharpe_like_ratio=0.24,
                turnover=0.0,
                win_rate_definition="positive_excess_nav_point_ratio_against_phase2_proxy",
                win_rate=1.0,
                capacity_note="fixture",
            )
            write_backtest_artifact(artifact, root=root)

            resolved_id, resolved_artifact = resolve_backtest_artifact(
                configured_artifact_id="portfolio-backtest:portfolio-auto-live",
                portfolio_key="sim-20260427122709-8da19b-model",
                root=root,
            )

            self.assertEqual(
                resolved_id,
                portfolio_backtest_artifact_id("sim-20260427122709-8da19b-model"),
            )
            assert resolved_artifact is not None
            self.assertEqual(resolved_artifact.artifact_id, artifact.artifact_id)

    def test_artifact_store_uses_phase2_contract_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            generated_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
            manifest = ResearchArtifactManifestView(
                artifact_id="rolling-validation-fixture",
                artifact_type="rolling_validation",
                generated_at=generated_at,
                experiment_version="exp-v1",
                model_version="lgbm-ranker-v1",
                policy_version="policy-v1",
                data_snapshot_id="snapshot-20260425",
                universe_definition="watchlist_plus_sector_peers",
                availability_rule="t_plus_1_disclosure_aligned",
                feature_set_version="features-v1",
                label_definition="forward_20d_excess_return",
                benchmark_definition="CSI300_total_return",
                cost_definition="12 bps",
                rebalance_definition="weekly_rebalance",
                split_plan=[
                    ArtifactSplitView(
                        slice_label="2024H1",
                        train_start=datetime(2021, 1, 1, tzinfo=UTC),
                        train_end=datetime(2023, 12, 31, tzinfo=UTC),
                        validation_start=datetime(2024, 1, 1, tzinfo=UTC),
                        validation_end=datetime(2024, 3, 31, tzinfo=UTC),
                        test_start=datetime(2024, 4, 1, tzinfo=UTC),
                        test_end=datetime(2024, 6, 30, tzinfo=UTC),
                        market_regime_tag="risk_on",
                    )
                ],
            )
            validation = ValidationMetricsArtifactView(
                artifact_id="validation-fixture",
                manifest_id=manifest.artifact_id,
                status="research_candidate",
                sample_count=96,
                rank_ic_mean=0.041,
                rank_ic_std=0.09,
                rank_ic_ir=0.46,
                ic_mean=0.038,
                bucket_spread_mean=0.028,
                bucket_spread_std=0.071,
                positive_excess_rate=0.57,
                turnover_mean=0.18,
                coverage_ratio=0.92,
            )
            backtest = BacktestArtifactView(
                artifact_id="backtest-fixture",
                manifest_id=manifest.artifact_id,
                strategy_definition="topk_drop",
                position_limit_definition="single_name_le_15pct",
                execution_assumptions="T+1, 涨跌停, 停牌, 100-share lot, slippage, fees",
                benchmark_definition="CSI300_total_return",
                cost_definition="12 bps",
                annualized_return=0.18,
                annualized_excess_return=0.07,
                max_drawdown=-0.12,
                sharpe_like_ratio=1.1,
                turnover=0.23,
                win_rate_definition="monthly_excess_positive_rate",
                win_rate=0.61,
                capacity_note="watchlist-scoped demo",
            )
            replay = ReplayAlignmentArtifactView(
                artifact_id="replay-fixture",
                manifest_id=manifest.artifact_id,
                recommendation_id=1,
                recommendation_key="reco-fixture",
                label_definition="forward_20d_excess_return",
                review_window_definition="20_trade_days_post_signal",
                entry_rule="next_trade_day_close",
                exit_rule="20_trade_days_close",
                benchmark_definition="CSI300_total_return",
                hit_definition="excess_return_gt_0",
                stock_return=0.09,
                benchmark_return=0.03,
                excess_return=0.06,
                validation_status="research_candidate",
            )
            study = Phase5HorizonStudyArtifactView(
                artifact_id="phase5-horizon-study:latest:2026-04-25:3symbols",
                generated_at=generated_at,
                scope={"symbols": ["600519.SH", "300750.SZ", "601318.SH"], "include_history": False},
                contract_version="phase5-validation-policy-contract-v1",
                required_benchmark_definition="active_watchlist_equal_weight_proxy",
                primary_horizon_status="pending_phase5_selection",
                summary={"included_record_count": 3, "included_as_of_date_count": 1},
                decision={"approval_state": "split_leadership", "candidate_frontier": [10, 20], "lagging_horizons": [40]},
            )
            holding_policy = Phase5HoldingPolicyStudyArtifactView(
                artifact_id="phase5-holding-policy-study:auto_model:2026-04-25:1portfolios",
                generated_at=generated_at,
                scope={"portfolio_keys": ["portfolio-auto-live"], "mode": "auto_model"},
                contract_version="phase5-validation-policy-contract-v1",
                policy_type="phase5_simulation_topk_equal_weight_v1",
                action_definition="delta_to_constrained_target_weight_portfolio",
                quantity_definition="board_lot_delta_to_target_weight",
                required_benchmark_definition="active_watchlist_equal_weight_proxy",
                summary={"included_portfolio_count": 1, "mean_turnover": 0.23},
                cost_sensitivity={"baseline_round_trip_cost_bps": 35.0},
                holding_stability={"portfolio_count": 1, "mean_rebalance_day_ratio": 0.12},
                decision={"approval_state": "research_candidate_only"},
            )
            holding_policy_experiment = Phase5HoldingPolicyExperimentArtifactView(
                artifact_id="phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:2026-04-01_to_2026-04-25:4symbols:3variants",
                generated_at=generated_at,
                scope={"symbols": ["600519.SH", "300750.SZ", "601318.SH", "002594.SZ"]},
                contract_version="phase5-validation-policy-contract-v1",
                policy_type="phase5_simulation_topk_equal_weight_v1",
                action_definition="delta_to_constrained_target_weight_portfolio",
                quantity_definition="board_lot_delta_to_target_weight",
                required_benchmark_definition="active_watchlist_equal_weight_proxy",
                experiment_id="profitability_signal_threshold_sweep_v1",
                experiment_version="phase5-holding-policy-experiment-v1",
                experiment_definition={"focus_area": "after_cost_profitability"},
                summary={"trade_day_count": 18, "variant_count": 3, "included_variant_count": 3},
                decision={"baseline_variant_id": "baseline_top5_weight20_conf0"},
                variants=[
                    {
                        "variant_id": "baseline_top5_weight20_conf0",
                        "summary": {"annualized_excess_return_after_baseline_cost": -0.02},
                    }
                ],
            )
            producer_contract_study = Phase5ProducerContractStudyArtifactView(
                artifact_id="phase5-producer-contract-study:history:2026-04-20_to_2026-04-25:3symbols",
                generated_at=generated_at,
                scope={"symbols": ["600519.SH", "300750.SZ", "601318.SH"], "include_history": True},
                contract_version="phase5-producer-contract-study-draft-v1",
                summary={"included_record_count": 6, "missing_news_only_record_count": 2},
                variants=[{"variant_id": "watch_ceiling_keep_penalty", "long_count": 4}],
                symbol_analysis=[{"symbol": "600519.SH", "record_count": 2}],
                focus_records=[{"symbol": "600519.SH", "as_of_date": "2026-04-25"}],
                decision={"recommended_variant_id": "watch_ceiling_keep_penalty"},
            )

            manifest_path = write_manifest(manifest, root=root)
            validation_path = write_validation_metrics(validation, root=root)
            backtest_path = write_backtest_artifact(backtest, root=root)
            replay_path = write_replay_alignment_artifact(replay, root=root)
            study_path = write_phase5_horizon_study_artifact(study, root=root)
            holding_policy_path = write_phase5_holding_policy_study_artifact(holding_policy, root=root)
            holding_policy_experiment_path = write_phase5_holding_policy_experiment_artifact(
                holding_policy_experiment,
                root=root,
            )
            producer_contract_study_path = write_phase5_producer_contract_study_artifact(
                producer_contract_study,
                root=root,
            )

            self.assertEqual(manifest_path, root / "manifests" / "rolling-validation-fixture.json")
            self.assertEqual(validation_path, root / "validation" / "validation-fixture.json")
            self.assertEqual(backtest_path, root / "backtests" / "backtest-fixture.json")
            self.assertEqual(replay_path, root / "replays" / "replay-fixture.json")
            self.assertEqual(study_path, root / "studies" / "phase5-horizon-study:latest:2026-04-25:3symbols.json")
            self.assertEqual(
                holding_policy_path,
                root / "studies" / "phase5-holding-policy-study:auto_model:2026-04-25:1portfolios.json",
            )
            self.assertEqual(
                holding_policy_experiment_path,
                root
                / "studies"
                / "phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:2026-04-01_to_2026-04-25:4symbols:3variants.json",
            )
            self.assertEqual(
                producer_contract_study_path,
                root / "studies" / "phase5-producer-contract-study:history:2026-04-20_to_2026-04-25:3symbols.json",
            )

            self.assertEqual(read_manifest("rolling-validation-fixture", root=root).artifact_id, manifest.artifact_id)
            self.assertEqual(read_validation_metrics("validation-fixture", root=root).manifest_id, manifest.artifact_id)
            self.assertEqual(read_backtest_artifact("backtest-fixture", root=root).strategy_definition, "topk_drop")
            self.assertEqual(
                read_replay_alignment_artifact("replay-fixture", root=root).review_window_definition,
                "20_trade_days_post_signal",
            )
            self.assertEqual(
                read_phase5_horizon_study_artifact(study.artifact_id, root=root).decision["approval_state"],
                "split_leadership",
            )
            self.assertEqual(
                read_phase5_holding_policy_study_artifact(holding_policy.artifact_id, root=root).decision["approval_state"],
                "research_candidate_only",
            )
            self.assertEqual(
                read_phase5_holding_policy_experiment_artifact(
                    holding_policy_experiment.artifact_id,
                    root=root,
                ).experiment_id,
                "profitability_signal_threshold_sweep_v1",
            )
            self.assertEqual(
                read_phase5_producer_contract_study_artifact(
                    producer_contract_study.artifact_id,
                    root=root,
                ).decision["recommended_variant_id"],
                "watch_ceiling_keep_penalty",
            )


if __name__ == "__main__":
    unittest.main()
