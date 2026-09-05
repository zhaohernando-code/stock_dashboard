from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ashare_evidence.api import create_app
from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.dashboard_projection_registry import build_dashboard_projection_registry_artifact
from ashare_evidence.data_quality import build_data_quality_summary
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.factor_observation import build_factor_observations, sweep_weights
from ashare_evidence.governance_promotion import build_governance_promotion_decision_artifact
from ashare_evidence.lineage import build_lineage
from ashare_evidence.market_rules import account_trade_eligibility, board_rule
from ashare_evidence.models import FeatureSnapshot, NewsEntityLink, NewsItem, Stock
from ashare_evidence.multiple_testing_diagnostics import build_multiple_testing_diagnostics_artifact
from ashare_evidence.oos_validation import build_oos_validation_artifact
from ashare_evidence.operations import build_operations_detail, build_operations_summary
from ashare_evidence.schemas import StockDashboardResponse
from ashare_evidence.walk_forward_protocol import build_walk_forward_protocol_artifact
from tests.fixtures import seed_watchlist_fixture


class ProfessionalizationPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.temp_dir.name) / 'professionalization.db'}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_projection_registry_blocks_unapproved_governance(self) -> None:
        registry = build_dashboard_projection_registry_artifact(
            validation_run_id="projection-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
            candidate_kind="factor_ic_study",
            candidate_artifact={
                "schema_version": "factor_ic_study.v2",
                "artifact_id": "factor",
                "validation_run_id": "projection-test",
                "generated_at": "2026-07-03T00:00:00+00:00",
                "source_db_snapshot_id": "snapshot",
                "source_data_time_range": {},
                "feature_version": "legacy_recommendation_payload_factor_breakdown:v1",
                "label_version": "daily_close_forward_excess_return:v1",
                "code_version": "test",
                "config_version": "research_validation_protocol.v1",
                "validation_protocol": {"feature_source_status": "legacy_diagnostic_only"},
                "gate_readout": {"blocking_gate_ids": ["independent_feature_source"]},
                "claim_ceiling": "diagnostic_research_only",
                "promotion_status": "blocked_from_production",
                "lineage": {"feature_version": "legacy_recommendation_payload_factor_breakdown:v1"},
            },
            governance_decision={
                "schema_version": "governance_promotion_decision.v1",
                "artifact_id": "governance",
                "validation_run_id": "projection-test",
                "generated_at": "2026-07-03T00:00:00+00:00",
                "source_db_snapshot_id": "snapshot",
                "source_data_time_range": {},
                "feature_version": "legacy_recommendation_payload_factor_breakdown:v1",
                "label_version": "daily_close_forward_excess_return:v1",
                "code_version": "test",
                "config_version": "shortpick_governance_promotion_state_machine:v1",
                "validation_protocol": {"artifact_role": "governance_promotion_decision"},
                "gate_readout": {"blocking_gate_ids": ["legacy_recommendation_payload_diagnostic_only"]},
                "claim_ceiling": "diagnostic_research_only",
                "promotion_status": "blocked_from_production",
                "current_state": "diagnostic_only",
                "approved_for_dashboard_projection": False,
            },
        )

        self.assertEqual(registry["artifact_type"], "dashboard_approved_projection_registry")
        self.assertEqual(registry["approved_projection_count"], 0)
        self.assertEqual(registry["blocked_projection_count"], 1)
        self.assertEqual(registry["gate_readout"]["gate_status"], "blocked")
        self.assertEqual(registry["claim_ceiling"], "diagnostic_summary_only")
        self.assertIn(
            "governance_not_approved_for_dashboard_projection",
            registry["gate_readout"]["blocking_gate_ids"],
        )
        self.assertIn(
            "governance_lifecycle_not_production_eligible:diagnostic_only",
            registry["gate_readout"]["blocking_gate_ids"],
        )
        self.assertEqual(
            registry["dashboard_consumption_boundary"],
            "dashboard_reads_registry_summary_not_raw_validation_artifacts",
        )

    def test_governance_promotion_state_machine_fails_closed(self) -> None:
        decision = build_governance_promotion_decision_artifact(
            validation_run_id="governance-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
            candidate_kind="factor_ic_study",
            candidate_artifact={
                "artifact_id": "factor",
                "validation_protocol": {"feature_source_status": "legacy_diagnostic_only"},
                "gate_readout": {"blocking_gate_ids": ["independent_feature_source"]},
                "lineage": {"feature_version": "legacy_recommendation_payload_factor_breakdown:v1"},
            },
            objective_universe={
                "artifact_id": "objective",
                "gate_readout": {"gate_status": "objective_universe_ready", "blocking_gate_ids": []},
            },
            walk_forward_protocol={
                "artifact_id": "wf",
                "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": ["walk_forward_min_splits"]},
            },
            oos_validation={
                "artifact_id": "oos",
                "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": ["insufficient_oos_rows"]},
            },
        )

        self.assertEqual(decision["artifact_type"], "governance_promotion_decision")
        self.assertEqual(decision["current_state"], "diagnostic_only")
        self.assertEqual(decision["gate_readout"]["gate_status"], "blocked")
        self.assertEqual(decision["promotion_status"], "blocked_from_production")
        self.assertFalse(decision["approved_for_dashboard_projection"])
        self.assertEqual(decision["allowed_next_states"], ["research_candidate"])
        transitions = decision["validation_protocol"]["state_machine_transitions"]
        self.assertEqual(
            decision["validation_protocol"]["state_machine_states"],
            [
                "diagnostic_only",
                "research_candidate",
                "oos_candidate",
                "paper_tracking_candidate",
                "production_eligible",
            ],
        )
        self.assertEqual(transitions["research_candidate"], ["oos_candidate"])
        self.assertNotIn("paper_tracking_candidate", transitions["research_candidate"])
        self.assertNotIn("rejected", transitions["research_candidate"])
        self.assertNotIn("retired", decision["validation_protocol"]["state_machine_states"])
        self.assertIn("retired", decision["validation_protocol"]["terminal_dispositions"])
        self.assertEqual(decision["terminal_disposition"], "none")
        blockers = decision["gate_readout"]["blocking_gate_ids"]
        self.assertIn("legacy_recommendation_payload_diagnostic_only", blockers)
        self.assertIn("multiple_testing_diagnostics_missing", blockers)
        self.assertIn("execution:t_plus_1_execution_model", blockers)
        self.assertIn("factor_ic_study:independent_feature_source", blockers)
        self.assertIn("factor_ic_study_missing_required_field_schema_version", blockers)

    def test_governance_execution_gate_uses_label_contract_evidence(self) -> None:
        decision = build_governance_promotion_decision_artifact(
            validation_run_id="governance-execution-contract-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
            candidate_kind="model_comparison_report",
            candidate_artifact={
                "schema_version": "model_comparison_report.v1",
                "artifact_id": "report",
                "validation_run_id": "governance-execution-contract-test",
                "generated_at": "2026-01-31T00:00:00+00:00",
                "source_db_snapshot_id": "snapshot",
                "source_data_time_range": {"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
                "feature_version": "features:v1",
                "label_version": "shortpick_model_executable_label_matrix:v3",
                "code_version": "test",
                "config_version": "test",
                "validation_protocol": {"production_effect": "forbidden"},
                "gate_readout": {
                    "gate_status": "blocked",
                    "blocking_gate_ids": ["execution_stress:negative_monthly_mean_under_base_cost"],
                },
                "claim_ceiling": "comparison_report_only",
                "promotion_status": "blocked_from_production",
                "execution_label_contract": {
                    "covered_execution_gate_ids": [
                        "t_plus_1_execution_model",
                        "suspension_limit_buy_sellability",
                    ]
                },
            },
            objective_universe={
                "artifact_id": "objective",
                "gate_readout": {"gate_status": "objective_universe_ready", "blocking_gate_ids": []},
            },
            walk_forward_protocol={
                "artifact_id": "wf",
                "gate_readout": {"gate_status": "walk_forward_ready", "blocking_gate_ids": []},
            },
            oos_validation={
                "artifact_id": "oos",
                "gate_readout": {"gate_status": "oos_ready", "blocking_gate_ids": []},
            },
            multiple_testing_diagnostics={
                "artifact_id": "multiple",
                "gate_readout": {"gate_status": "multiple_testing_ready", "blocking_gate_ids": []},
            },
        )

        blockers = decision["gate_readout"]["blocking_gate_ids"]
        self.assertNotIn("execution:t_plus_1_execution_model", blockers)
        self.assertNotIn("execution:suspension_limit_buy_sellability", blockers)
        self.assertIn("execution:fees_slippage_stamp_tax", blockers)
        self.assertIn("execution:adv_capacity_fill_rate", blockers)
        self.assertIn("model_comparison_report:execution_stress:negative_monthly_mean_under_base_cost", blockers)

    def test_governance_execution_gate_uses_cost_stress_evidence_for_fees(self) -> None:
        decision = build_governance_promotion_decision_artifact(
            validation_run_id="governance-cost-stress-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
            candidate_kind="model_comparison_report",
            candidate_artifact={
                "schema_version": "model_comparison_report.v1",
                "artifact_id": "report",
                "validation_run_id": "governance-cost-stress-test",
                "generated_at": "2026-01-31T00:00:00+00:00",
                "source_db_snapshot_id": "snapshot",
                "source_data_time_range": {"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
                "feature_version": "features:v1",
                "label_version": "shortpick_model_executable_label_matrix:v3",
                "code_version": "test",
                "config_version": "test",
                "validation_protocol": {"production_effect": "forbidden"},
                "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": []},
                "claim_ceiling": "comparison_report_only",
                "promotion_status": "blocked_from_production",
                "execution_label_contract": {
                    "covered_execution_gate_ids": [
                        "t_plus_1_execution_model",
                        "suspension_limit_buy_sellability",
                    ]
                },
                "execution_diagnostics": {
                    "period_count": 120,
                    "blocking_gate_ids": [],
                    "thresholds": {"minimum_periods": 20},
                    "cost_stress": [
                        {"cost_multiplier": 1.0, "mean_net_excess_after_cost_stress": 0.030},
                        {"cost_multiplier": 2.0, "mean_net_excess_after_cost_stress": 0.029},
                        {"cost_multiplier": 3.0, "mean_net_excess_after_cost_stress": 0.028},
                    ],
                },
            },
            objective_universe={
                "artifact_id": "objective",
                "gate_readout": {"gate_status": "objective_universe_ready", "blocking_gate_ids": []},
            },
            walk_forward_protocol={
                "artifact_id": "wf",
                "gate_readout": {"gate_status": "walk_forward_ready", "blocking_gate_ids": []},
            },
            oos_validation={
                "artifact_id": "oos",
                "gate_readout": {"gate_status": "oos_ready", "blocking_gate_ids": []},
            },
            multiple_testing_diagnostics={
                "artifact_id": "multiple",
                "gate_readout": {"gate_status": "multiple_testing_ready", "blocking_gate_ids": []},
            },
        )

        execution_gate = decision["gate_readout"]["execution_gate_readout"]
        blockers = decision["gate_readout"]["blocking_gate_ids"]
        self.assertIn("fees_slippage_stamp_tax", execution_gate["covered_gate_ids"])
        self.assertNotIn("execution:fees_slippage_stamp_tax", blockers)
        self.assertIn("execution:adv_capacity_fill_rate", blockers)

    def test_governance_execution_gate_uses_capacity_stress_evidence_for_adv(self) -> None:
        decision = build_governance_promotion_decision_artifact(
            validation_run_id="governance-capacity-stress-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
            candidate_kind="model_comparison_report",
            candidate_artifact={
                "schema_version": "model_comparison_report.v1",
                "artifact_id": "report",
                "validation_run_id": "governance-capacity-stress-test",
                "generated_at": "2026-01-31T00:00:00+00:00",
                "source_db_snapshot_id": "snapshot",
                "source_data_time_range": {"as_of_start": "2026-01-01", "as_of_end": "2026-01-31"},
                "feature_version": "features:v1",
                "label_version": "shortpick_model_executable_label_matrix:v3",
                "code_version": "test",
                "config_version": "test",
                "validation_protocol": {"production_effect": "forbidden"},
                "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": []},
                "claim_ceiling": "comparison_report_only",
                "promotion_status": "blocked_from_production",
                "execution_label_contract": {
                    "covered_execution_gate_ids": [
                        "t_plus_1_execution_model",
                        "suspension_limit_buy_sellability",
                        "fees_slippage_stamp_tax",
                    ]
                },
                "execution_diagnostics": {
                    "period_count": 120,
                    "blocking_gate_ids": [],
                    "capacity_diagnostics": {
                        "status": "ready",
                        "blocking_gate_ids": [],
                        "active_pick_count": 120,
                        "active_pick_below_full_fill_count": 0,
                        "missing_avg_amount_20d_count": 0,
                    },
                },
            },
            objective_universe={
                "artifact_id": "objective",
                "gate_readout": {"gate_status": "objective_universe_ready", "blocking_gate_ids": []},
            },
            walk_forward_protocol={
                "artifact_id": "wf",
                "gate_readout": {"gate_status": "walk_forward_ready", "blocking_gate_ids": []},
            },
            oos_validation={
                "artifact_id": "oos",
                "gate_readout": {"gate_status": "oos_ready", "blocking_gate_ids": []},
            },
            multiple_testing_diagnostics={
                "artifact_id": "multiple",
                "gate_readout": {"gate_status": "multiple_testing_ready", "blocking_gate_ids": []},
            },
        )

        execution_gate = decision["gate_readout"]["execution_gate_readout"]
        blockers = decision["gate_readout"]["blocking_gate_ids"]
        self.assertIn("adv_capacity_fill_rate", execution_gate["covered_gate_ids"])
        self.assertNotIn("execution:adv_capacity_fill_rate", blockers)

    def test_walk_forward_protocol_blocks_false_ready_after_purge(self) -> None:
        rows = [
            {"as_of_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat()}
            for index in range(12)
        ]

        artifact = build_walk_forward_protocol_artifact(
            validation_run_id="wf-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            objective_universe={"artifact_id": "objective"},
            input_snapshot={"artifact_id": "snapshot"},
            pit_feature_store={"artifact_id": "pit", "feature_version": "pit:v1"},
            observation_rows=rows,
            horizons=[5],
        )

        self.assertGreaterEqual(artifact["split_count"], 3)
        self.assertEqual(artifact["ready_split_count"], 0)
        self.assertEqual(artifact["gate_readout"]["gate_status"], "blocked")
        self.assertTrue(all(split["purged_train_period_count"] < 6 for split in artifact["splits"]))

    def test_walk_forward_protocol_can_be_ready_with_enough_purged_training_periods(self) -> None:
        rows = [
            {"as_of_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat()}
            for index in range(18)
        ]

        artifact = build_walk_forward_protocol_artifact(
            validation_run_id="wf-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            objective_universe={"artifact_id": "objective"},
            input_snapshot={"artifact_id": "snapshot"},
            pit_feature_store={"artifact_id": "pit", "feature_version": "pit:v1"},
            observation_rows=rows,
            horizons=[1],
        )

        self.assertGreaterEqual(artifact["ready_split_count"], 3)
        self.assertEqual(artifact["gate_readout"]["gate_status"], "walk_forward_ready")
        self.assertTrue(
            all(
                split["purged_train_period_count"] >= 6 and split["test_period_count"] >= 2
                for split in artifact["splits"]
                if split["status"] == "ready"
            )
        )

    def test_multiple_testing_diagnostics_blocks_and_can_pass_when_inputs_are_sufficient(self) -> None:
        blocked = build_multiple_testing_diagnostics_artifact(
            validation_run_id="multi-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            weight_sweep={
                "artifact_id": "sweep-blocked",
                "sweep_results": [
                    {
                        "label": "baseline",
                        "horizon_metrics": {
                            "10d": {"ic_ir": None, "sample_count": 0, "snapshot_count": 0},
                        },
                    }
                ],
            },
        )
        self.assertEqual(blocked["gate_readout"]["gate_status"], "blocked")
        self.assertIn("insufficient_eligible_trials_for_pbo", blocked["gate_readout"]["blocking_gate_ids"])

        ready_trials = [
            {
                "label": f"trial_{index}",
                "horizon_metrics": {
                    "10d": {
                        "ic_ir": 1.1 + index * 0.05,
                        "sample_count": 800,
                        "snapshot_count": 24,
                        "mean_top_bottom_spread": 0.02,
                    }
                },
            }
            for index in range(4)
        ]
        ready = build_multiple_testing_diagnostics_artifact(
            validation_run_id="multi-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            weight_sweep={"artifact_id": "sweep-ready", "sweep_results": ready_trials},
        )
        self.assertEqual(ready["gate_readout"]["gate_status"], "multiple_testing_ready")
        self.assertGreaterEqual(ready["deflated_sharpe_confidence"], 0.95)
        self.assertLessEqual(ready["pbo"], 0.10)
        self.assertGreaterEqual(ready["alpha_t_stat_equivalent"], 3.0)

    def test_oos_validation_blocks_and_can_pass_with_holdout_rows(self) -> None:
        blocked = build_oos_validation_artifact(
            validation_run_id="oos-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            factor_study={"artifact_id": "factor", "lineage": {}, "observation_rows": []},
            walk_forward_protocol={"artifact_id": "wf", "splits": []},
        )
        self.assertEqual(blocked["gate_readout"]["gate_status"], "blocked")
        self.assertIn("insufficient_oos_rows", blocked["gate_readout"]["blocking_gate_ids"])

        one_day_multi_horizon_rows = []
        for horizon in (10, 20, 40):
            for rank in range(20):
                one_day_multi_horizon_rows.append(
                    {
                        "symbol": f"{rank:06d}.SH",
                        "recommendation_key": f"rec-one-day-{horizon}-{rank}",
                        "as_of_date": "2026-01-01",
                        "horizon_days": horizon,
                        "scores": {"fusion": float(rank)},
                        "dynamic_weights": {"fusion": 1.0},
                        "forward_excess_return": float(rank) / 100.0,
                    }
                )
        one_day = build_oos_validation_artifact(
            validation_run_id="oos-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            factor_study={"artifact_id": "factor", "lineage": {}, "observation_rows": one_day_multi_horizon_rows},
            walk_forward_protocol={
                "artifact_id": "wf",
                "splits": [
                    {
                        "status": "ready",
                        "test_range": {"start": "2026-01-01", "end": "2026-01-01"},
                    }
                ],
            },
        )
        self.assertEqual(one_day["gate_readout"]["gate_status"], "blocked")
        self.assertEqual(one_day["oos_period_count"], 1)
        self.assertIn("insufficient_oos_periods", one_day["gate_readout"]["blocking_gate_ids"])

        negative_top_rows = []
        for day_index in range(3):
            as_of = (date(2026, 1, 1) + timedelta(days=day_index)).isoformat()
            for rank in range(20):
                negative_top_rows.append(
                    {
                        "symbol": f"{rank:06d}.SH",
                        "recommendation_key": f"rec-negative-top-{day_index}-{rank}",
                        "as_of_date": as_of,
                        "horizon_days": 10,
                        "scores": {"fusion": float(rank)},
                        "dynamic_weights": {"fusion": 1.0},
                        "forward_excess_return": -0.20 + float(rank) / 1000.0,
                    }
                )
        negative_top = build_oos_validation_artifact(
            validation_run_id="oos-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            factor_study={"artifact_id": "factor", "lineage": {}, "observation_rows": negative_top_rows},
            walk_forward_protocol={
                "artifact_id": "wf",
                "splits": [
                    {
                        "status": "ready",
                        "test_range": {
                            "start": (date(2026, 1, 1) + timedelta(days=day_index)).isoformat(),
                            "end": (date(2026, 1, 1) + timedelta(days=day_index)).isoformat(),
                        },
                    }
                    for day_index in range(3)
                ],
            },
        )
        self.assertEqual(negative_top["gate_readout"]["gate_status"], "blocked")
        self.assertLessEqual(negative_top["top_quantile_mean_excess"], 0)
        self.assertIn("top_quantile_net_excess_not_positive", negative_top["gate_readout"]["blocking_gate_ids"])

        observation_rows = []
        for day_index in range(3):
            as_of = (date(2026, 1, 1) + timedelta(days=day_index)).isoformat()
            for rank in range(20):
                observation_rows.append(
                    {
                        "symbol": f"{rank:06d}.SH",
                        "recommendation_key": f"rec-{day_index}-{rank}",
                        "as_of_date": as_of,
                        "horizon_days": 10,
                        "scores": {"fusion": float(rank)},
                        "dynamic_weights": {"fusion": 1.0},
                        "forward_excess_return": float(rank) / 100.0,
                    }
                )
        ready = build_oos_validation_artifact(
            validation_run_id="oos-test",
            source_db_snapshot_id="snapshot",
            source_data_time_range={},
            factor_study={"artifact_id": "factor", "lineage": {}, "observation_rows": observation_rows},
            walk_forward_protocol={
                "artifact_id": "wf",
                "validation_protocol": {"protocol_version": "wf:v1"},
                "splits": [
                    {
                        "status": "ready",
                        "test_range": {
                            "start": (date(2026, 1, 1) + timedelta(days=day_index)).isoformat(),
                            "end": (date(2026, 1, 1) + timedelta(days=day_index)).isoformat(),
                        },
                    }
                    for day_index in range(3)
                ],
            },
        )
        self.assertEqual(ready["gate_readout"]["gate_status"], "oos_ready")
        self.assertGreater(ready["oos_rank_ic"], 0.02)
        self.assertGreater(ready["oos_icir"], 0.35)
        self.assertGreaterEqual(ready["positive_ic_rate"], 0.55)
        self.assertGreater(ready["top_quantile_mean_excess"], 0)
        self.assertTrue(ready["top_quantile_net_excess_positive"])

    def test_data_quality_snapshot_scores_and_missing_news_is_soft_gap(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            session.execute(delete(NewsEntityLink))
            session.execute(delete(NewsItem))
            session.commit()

        with session_scope(self.database_url) as session:
            summary = build_data_quality_summary(session, symbols=["600519.SH"])

        self.assertEqual(summary["symbol_count"], 1)
        item = summary["items"][0]
        self.assertIn(item["status"], {"pass", "warn"})
        self.assertIn("data_coverage_gap:news", item["degraded_sources"])
        self.assertEqual(item["news_coverage"]["status"], "warn")
        self.assertGreaterEqual(item["news_coverage"]["score"], 0.6)
        self.assertNotEqual(item["status"], "fail")

    def test_market_rules_cover_board_st_new_listing_and_unknown_status(self) -> None:
        self.assertEqual(board_rule("688981.SH")["board"], "star")
        self.assertEqual(board_rule("688981.SH")["lot"], 200)
        self.assertEqual(board_rule("688981.SH")["min_order_quantity"], 200)
        self.assertEqual(board_rule("688981.SH")["quantity_increment"], 1)
        self.assertEqual(board_rule("300750.SZ")["limit_pct"], 0.20)
        st_rule = board_rule("600000.SH", stock_profile={"name": "ST测试", "is_st": True})
        self.assertEqual(st_rule["board"], "st")
        self.assertEqual(st_rule["limit_pct"], 0.05)
        new_rule = board_rule(
            "600000.SH",
            stock_profile={"listed_date": "20260427", "board": "main"},
            as_of=date(2026, 4, 30),
        )
        self.assertTrue(new_rule["new_listing_no_limit"])
        self.assertIsNone(new_rule["limit_pct"])
        self.assertEqual(board_rule("123456.SH")["rule_status"], "wip_unknown")
        self.assertTrue(account_trade_eligibility("600519.SH")["tradable"])
        self.assertFalse(account_trade_eligibility("688981.SH")["tradable"])
        self.assertFalse(account_trade_eligibility("300750.SZ")["tradable"])

    def test_data_quality_uses_profile_financial_snapshot_and_board_payload_fallbacks(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            stock = session.scalar(select(Stock).where(Stock.symbol == "600519.SH"))
            assert stock is not None
            session.execute(delete(FeatureSnapshot).where(FeatureSnapshot.stock_id == stock.id))
            stock.profile_payload = {
                **stock.profile_payload,
                "board": "main",
                "board_name": "主板",
                "financial_snapshot": {
                    "provider_name": "tushare_fina_indicator",
                    "ann_date": "20260425",
                    "report_period": "2026一季报",
                },
            }
            session.commit()

        with session_scope(self.database_url) as session:
            summary = build_data_quality_summary(
                session, symbols=["600519.SH"], as_of=datetime(2026, 4, 30, tzinfo=UTC)
            )

        item = summary["items"][0]
        self.assertEqual(item["financial_freshness"]["status"], "pass")
        self.assertEqual(item["financial_freshness"]["latest_as_of"], "2026-04-25T00:00:00+00:00")
        self.assertEqual(item["profile_completeness"]["status"], "pass")
        self.assertNotIn("financial_data_stale", item["degraded_sources"])
        self.assertNotIn("profile_incomplete", item["degraded_sources"])

    def test_data_quality_accepts_verified_board_rule_as_profile_fallback(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            stock = session.scalar(select(Stock).where(Stock.symbol == "600519.SH"))
            assert stock is not None
            session.execute(delete(FeatureSnapshot).where(FeatureSnapshot.stock_id == stock.id))
            stock.profile_payload = {
                key: value
                for key, value in stock.profile_payload.items()
                if key not in {"board", "market_board", "board_name"}
            }
            stock.profile_payload["financial_snapshot"] = {
                "provider_name": "tushare_fina_indicator",
                "ann_date": "20260425",
                "report_period": "2026一季报",
            }
            session.commit()

        with session_scope(self.database_url) as session:
            item = build_data_quality_summary(session, symbols=["600519.SH"])["items"][0]

        self.assertEqual(item["profile_completeness"]["status"], "pass")
        self.assertNotIn("profile_incomplete", item["degraded_sources"])

    def test_factor_ic_and_weight_sweep_emit_insufficient_sample_not_fake_precision(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ", "601318.SH", "002594.SZ"))
            session.add(
                Stock(
                    symbol="000001.SZ",
                    ticker="000001",
                    exchange="SZSE",
                    name="平安银行",
                    provider_symbol="000001.SZ",
                    status="active",
                    profile_payload={},
                    **build_lineage(
                        {"symbol": "000001.SZ", "purpose": "objective_universe_missing_bar_fixture"},
                        source_uri="fixture://objective-universe/missing-bars/000001.SZ",
                        license_tag="fixture",
                        usage_scope="internal_test",
                        redistribution_scope="none",
                    ),
                )
            )
            session.flush()
            study = build_factor_observations(session, artifact_root=self.temp_dir.name, persist=True)
            sweep = sweep_weights(session, artifact_root=self.temp_dir.name, persist=True)

        self.assertEqual(study["artifact_type"], "factor_ic_study")
        self.assertEqual(study["schema_version"], "factor_ic_study.v2")
        self.assertEqual(study["status"], "insufficient_sample")
        self.assertEqual(study["benchmark_context"]["primary_benchmark"], "CSI300")
        self.assertEqual(study["benchmark_context"]["status"], "missing_primary_benchmark_bars")
        self.assertEqual(study["benchmark_context"]["fallback_policy"], "block_ic_rows_when_primary_benchmark_unavailable")
        self.assertEqual(study["validation_protocol"]["feature_source_status"], "legacy_diagnostic_only")
        self.assertEqual(study["validation_protocol"]["walk_forward_status"], "artifact_implemented")
        self.assertEqual(study["validation_protocol"]["purge_embargo_status"], "artifact_implemented")
        self.assertEqual(study["promotion_status"], "blocked_from_production")
        self.assertEqual(study["claim_ceiling"], "diagnostic_research_only")
        self.assertEqual(study["gate_readout"]["promotion_status"], "blocked_from_production")
        self.assertEqual(study["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(study["objective_universe"]["promotion_status"], "blocked_from_production")
        self.assertGreaterEqual(study["objective_universe"]["eligible_symbol_count"], 1)
        self.assertGreater(study["objective_universe"]["db_stock_count"], study["objective_universe"]["eligible_symbol_count"])
        objective_check = next(
            check
            for check in study["gate_readout"]["checks"]
            if check["gate_id"] == "objective_research_universe"
        )
        self.assertEqual(objective_check["status"], "pass")
        self.assertNotIn("objective_universe_artifact", study)
        self.assertNotIn("members", json.dumps(study["objective_universe"], ensure_ascii=False))
        self.assertEqual(study["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(study["research_input_snapshot"]["claim_ceiling"], "input_boundary_only")
        self.assertEqual(study["research_input_snapshot"]["promotion_status"], "blocked_from_production")
        self.assertEqual(
            study["research_input_snapshot_artifact"]["validation_protocol"]["snapshot_policy"],
            "freeze_runtime_db_read_only_inputs_before_validation",
        )
        required_snapshot_fields = {
            "schema_version",
            "artifact_id",
            "validation_run_id",
            "generated_at",
            "source_db_snapshot_id",
            "source_data_time_range",
            "feature_version",
            "label_version",
            "code_version",
            "config_version",
            "validation_protocol",
            "gate_readout",
            "claim_ceiling",
            "promotion_status",
            "input_content_digest",
            "recommendation_source",
            "market_bar_source",
            "benchmark_bar_source",
            "news_source",
        }
        self.assertTrue(required_snapshot_fields.issubset(study["research_input_snapshot_artifact"]))
        self.assertEqual(len(study["research_input_snapshot_artifact"]["source_db_snapshot_id"]), 16)
        self.assertEqual(len(study["research_input_snapshot_artifact"]["input_content_digest"]), 64)
        self.assertGreater(study["research_input_snapshot_artifact"]["recommendation_source"]["row_count"], 0)
        self.assertGreater(study["research_input_snapshot_artifact"]["market_bar_source"]["row_count"], 0)
        recommendation_source_rows = study["research_input_snapshot_artifact"]["recommendation_source"]["rows"]
        self.assertGreater(len(recommendation_source_rows), 0)
        self.assertIn("factor_score_input", recommendation_source_rows[0])
        self.assertIn("factor_breakdown", recommendation_source_rows[0]["factor_score_input"])
        self.assertIn("evidence_factor_cards", recommendation_source_rows[0]["factor_score_input"])
        self.assertIn("rows", study["research_input_snapshot_artifact"]["market_bar_source"])
        self.assertIn("rows", study["research_input_snapshot_artifact"]["benchmark_bar_source"])
        self.assertIn("rows", study["research_input_snapshot_artifact"]["news_source"])
        self.assertEqual(study["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(study["pit_feature_store"]["promotion_status"], "blocked_from_production")
        self.assertGreater(study["pit_feature_store"]["feature_row_count"], 0)
        self.assertEqual(study["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
        self.assertEqual(study["walk_forward_protocol"]["promotion_status"], "blocked_from_production")
        self.assertEqual(study["walk_forward_protocol"]["claim_ceiling"], "walk_forward_protocol_only")
        self.assertNotIn("walk_forward_protocol_artifact", study)
        self.assertNotIn("splits", study["walk_forward_protocol"])
        self.assertEqual(study["oos_validation"]["artifact_type"], "oos_validation")
        self.assertEqual(study["oos_validation"]["promotion_status"], "blocked_from_production")
        self.assertEqual(study["oos_validation"]["claim_ceiling"], "oos_validation_only")
        self.assertNotIn("oos_validation_artifact", study)
        self.assertNotIn("oos_rows", study["oos_validation"])
        self.assertNotIn("period_metrics", study["oos_validation"])
        self.assertEqual(study["governance_promotion"]["artifact_type"], "governance_promotion_decision")
        self.assertEqual(study["governance_promotion"]["current_state"], "diagnostic_only")
        self.assertEqual(study["governance_promotion"]["gate_readout"]["gate_status"], "blocked")
        self.assertEqual(study["governance_promotion"]["promotion_status"], "blocked_from_production")
        self.assertFalse(study["governance_promotion"]["approved_for_dashboard_projection"])
        self.assertNotIn("transition_log", study["governance_promotion"])
        self.assertEqual(study["dashboard_projection_registry"]["artifact_type"], "dashboard_approved_projection_registry")
        self.assertEqual(study["dashboard_projection_registry"]["approved_projection_count"], 0)
        self.assertEqual(study["dashboard_projection_registry"]["blocked_projection_count"], 1)
        self.assertEqual(study["dashboard_projection_registry"]["claim_ceiling"], "diagnostic_summary_only")
        self.assertNotIn("approved_projection_entries", study["dashboard_projection_registry"])
        self.assertNotIn("pit_feature_store_artifact", study)
        self.assertNotIn("governance_promotion_artifact", study)
        self.assertNotIn("dashboard_projection_registry_artifact", study)
        self.assertNotIn("feature_rows", json.dumps(study, ensure_ascii=False))
        self.assertEqual(
            study["lineage"]["research_input_snapshot_id"],
            study["research_input_snapshot"]["artifact_id"],
        )
        self.assertEqual(study["lineage"]["pit_feature_store_id"], study["pit_feature_store"]["artifact_id"])
        self.assertEqual(study["lineage"]["objective_universe_id"], study["objective_universe"]["artifact_id"])
        self.assertEqual(study["lineage"]["walk_forward_protocol_id"], study["walk_forward_protocol"]["artifact_id"])
        self.assertEqual(study["lineage"]["oos_validation_id"], study["oos_validation"]["artifact_id"])
        self.assertEqual(
            study["lineage"]["governance_promotion_decision_id"],
            study["governance_promotion"]["artifact_id"],
        )
        self.assertEqual(
            study["lineage"]["dashboard_projection_registry_id"],
            study["dashboard_projection_registry"]["artifact_id"],
        )
        self.assertIn("benchmark_availability", study["gate_readout"]["blocking_gate_ids"])
        self.assertNotIn("objective_research_universe", study["gate_readout"]["blocking_gate_ids"])
        self.assertIn("walk_forward_purged_cv", study["gate_readout"]["blocking_gate_ids"])
        self.assertIn("independent_feature_source", study["gate_readout"]["blocking_gate_ids"])
        self.assertEqual(study["lineage"]["feature_version"], "legacy_recommendation_payload_factor_breakdown:v1")
        self.assertEqual(study["observation_count"], 0)
        self.assertEqual(sweep["artifact_type"], "weight_sweep_study")
        self.assertEqual(sweep["schema_version"], "weight_sweep_study.v2")
        self.assertEqual(sweep["status"], "insufficient_sample")
        self.assertEqual(sweep["promotion_status"], "blocked_from_production")
        self.assertEqual(sweep["claim_ceiling"], "diagnostic_research_only")
        self.assertEqual(sweep["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(sweep["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(sweep["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(sweep["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
        self.assertEqual(sweep["oos_validation"]["artifact_type"], "oos_validation")
        self.assertEqual(sweep["multiple_testing_diagnostics"]["artifact_type"], "pbo_dsr_multiple_comparison")
        self.assertEqual(sweep["multiple_testing_diagnostics"]["promotion_status"], "blocked_from_production")
        self.assertEqual(sweep["governance_promotion"]["artifact_type"], "governance_promotion_decision")
        self.assertEqual(sweep["governance_promotion"]["current_state"], "diagnostic_only")
        self.assertEqual(sweep["governance_promotion"]["gate_readout"]["gate_status"], "blocked")
        self.assertEqual(sweep["governance_promotion"]["promotion_status"], "blocked_from_production")
        self.assertFalse(sweep["governance_promotion"]["approved_for_dashboard_projection"])
        self.assertEqual(sweep["dashboard_projection_registry"]["artifact_type"], "dashboard_approved_projection_registry")
        self.assertEqual(sweep["dashboard_projection_registry"]["approved_projection_count"], 0)
        self.assertEqual(sweep["dashboard_projection_registry"]["blocked_projection_count"], 1)
        self.assertNotIn("approved_projection_entries", sweep["dashboard_projection_registry"])
        self.assertEqual(
            sweep["validation_protocol"]["multiple_testing_status"],
            "artifact_implemented",
        )
        self.assertNotIn("trials", sweep["multiple_testing_diagnostics"])
        self.assertEqual(sweep["validation_protocol"]["weight_sweep_policy"], "diagnostic_only_no_auto_promotion")
        self.assertIn("不自动修改生产权重", sweep["note"])
        artifact_root = Path(self.temp_dir.name)
        snapshot_path = (
            artifact_root
            / "research_validation"
            / "input_snapshots"
            / f"{study['research_input_snapshot']['artifact_id']}.json"
        )
        universe_path = (
            artifact_root
            / "research_validation"
            / "objective_universes"
            / f"{study['objective_universe']['artifact_id']}.json"
        )
        factor_path = artifact_root / "research_validation" / "factor_ic_studies" / f"{study['artifact_id']}.json"
        pit_path = artifact_root / "research_validation" / "pit_feature_store" / f"{study['pit_feature_store']['artifact_id']}.json"
        walk_forward_path = (
            artifact_root
            / "research_validation"
            / "walk_forward_protocols"
            / f"{study['walk_forward_protocol']['artifact_id']}.json"
        )
        oos_path = (
            artifact_root
            / "research_validation"
            / "oos_validations"
            / f"{study['oos_validation']['artifact_id']}.json"
        )
        governance_path = (
            artifact_root
            / "research_validation"
            / "governance_promotion_decisions"
            / f"{study['governance_promotion']['artifact_id']}.json"
        )
        projection_registry_path = (
            artifact_root
            / "research_validation"
            / "dashboard_approved_projection_registries"
            / f"{study['dashboard_projection_registry']['artifact_id']}.json"
        )
        multiple_testing_path = (
            artifact_root
            / "research_validation"
            / "multiple_testing_diagnostics"
            / f"{sweep['multiple_testing_diagnostics']['artifact_id']}.json"
        )
        sweep_governance_path = (
            artifact_root
            / "research_validation"
            / "governance_promotion_decisions"
            / f"{sweep['governance_promotion']['artifact_id']}.json"
        )
        sweep_projection_registry_path = (
            artifact_root
            / "research_validation"
            / "dashboard_approved_projection_registries"
            / f"{sweep['dashboard_projection_registry']['artifact_id']}.json"
        )
        sweep_path = artifact_root / "research_validation" / "weight_sweep_studies" / f"{sweep['artifact_id']}.json"
        self.assertTrue(universe_path.exists())
        self.assertTrue(snapshot_path.exists())
        self.assertTrue(pit_path.exists())
        self.assertTrue(walk_forward_path.exists())
        self.assertTrue(oos_path.exists())
        self.assertTrue(governance_path.exists())
        self.assertTrue(projection_registry_path.exists())
        self.assertTrue(multiple_testing_path.exists())
        self.assertTrue(sweep_governance_path.exists())
        self.assertTrue(sweep_projection_registry_path.exists())
        self.assertTrue(factor_path.exists())
        self.assertTrue(sweep_path.exists())
        universe_payload = json.loads(universe_path.read_text(encoding="utf-8"))
        self.assertEqual(universe_payload["artifact_type"], "objective_frozen_universe")
        self.assertGreater(len(universe_payload["members"]), 0)
        missing_bar_member = next(member for member in universe_payload["members"] if member["symbol"] == "000001.SZ")
        self.assertEqual(missing_bar_member["membership_status"], "excluded")
        self.assertIn("insufficient_daily_bars", missing_bar_member["exclusion_reasons"])
        self.assertFalse(missing_bar_member["has_recommendation_sample"])
        self.assertEqual(universe_payload["db_stock_count"], len(universe_payload["members"]))
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(snapshot_payload["artifact_type"], "research_input_snapshot")
        self.assertEqual(snapshot_payload["objective_universe"]["artifact_id"], study["objective_universe"]["artifact_id"])
        self.assertEqual(snapshot_payload["input_content_digest"], study["research_input_snapshot_artifact"]["input_content_digest"])
        pit_payload = json.loads(pit_path.read_text(encoding="utf-8"))
        self.assertEqual(pit_payload["artifact_type"], "pit_feature_store")
        self.assertEqual(pit_payload["source_input_snapshot"]["artifact_id"], study["research_input_snapshot"]["artifact_id"])
        walk_forward_payload = json.loads(walk_forward_path.read_text(encoding="utf-8"))
        self.assertEqual(walk_forward_payload["artifact_type"], "walk_forward_purge_embargo")
        self.assertEqual(
            walk_forward_payload["source_artifacts"]["pit_feature_store_id"],
            study["pit_feature_store"]["artifact_id"],
        )
        self.assertIn("splits", walk_forward_payload)
        oos_payload = json.loads(oos_path.read_text(encoding="utf-8"))
        self.assertEqual(oos_payload["artifact_type"], "oos_validation")
        self.assertIn("oos_rows", oos_payload)
        self.assertIn("period_metrics", oos_payload)
        self.assertIn("insufficient_oos_rows", oos_payload["gate_readout"]["blocking_gate_ids"])
        governance_payload = json.loads(governance_path.read_text(encoding="utf-8"))
        self.assertEqual(governance_payload["artifact_type"], "governance_promotion_decision")
        self.assertEqual(governance_payload["current_state"], "diagnostic_only")
        self.assertIn("transition_log", governance_payload)
        self.assertIn(
            "legacy_recommendation_payload_diagnostic_only",
            governance_payload["gate_readout"]["blocking_gate_ids"],
        )
        projection_registry_payload = json.loads(projection_registry_path.read_text(encoding="utf-8"))
        self.assertEqual(projection_registry_payload["artifact_type"], "dashboard_approved_projection_registry")
        self.assertEqual(projection_registry_payload["approved_projection_count"], 0)
        self.assertIn("approved_projection_entries", projection_registry_payload)
        self.assertIn("blocked_projection_entries", projection_registry_payload)
        self.assertIn(
            "governance_not_approved_for_dashboard_projection",
            projection_registry_payload["gate_readout"]["blocking_gate_ids"],
        )
        multiple_testing_payload = json.loads(multiple_testing_path.read_text(encoding="utf-8"))
        self.assertEqual(multiple_testing_payload["artifact_type"], "pbo_dsr_multiple_comparison")
        self.assertIn("trials", multiple_testing_payload)
        self.assertIn("insufficient_eligible_trials_for_pbo", multiple_testing_payload["gate_readout"]["blocking_gate_ids"])
        sweep_governance_payload = json.loads(sweep_governance_path.read_text(encoding="utf-8"))
        self.assertEqual(sweep_governance_payload["artifact_type"], "governance_promotion_decision")
        self.assertIn("multiple_testing_not_ready", sweep_governance_payload["gate_readout"]["blocking_gate_ids"])
        sweep_projection_registry_payload = json.loads(sweep_projection_registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sweep_projection_registry_payload["artifact_type"],
            "dashboard_approved_projection_registry",
        )
        self.assertEqual(sweep_projection_registry_payload["approved_projection_count"], 0)
        pit_feature_row = pit_payload["feature_rows"][0]
        self.assertIn("price_baseline", pit_feature_row["features"])
        self.assertIn("liquidity", pit_feature_row["features"])
        self.assertIn("risk_trading_constraints", pit_feature_row["features"])
        self.assertIn("news_text", pit_feature_row["features"])
        self.assertNotIn("factor_breakdown", json.dumps(pit_feature_row, ensure_ascii=False))
        factor_payload = json.loads(factor_path.read_text(encoding="utf-8"))
        self.assertEqual(factor_payload["claim_ceiling"], "diagnostic_research_only")
        self.assertTrue(
            {
                "source_db_snapshot_id",
                "source_data_time_range",
                "feature_version",
                "label_version",
                "code_version",
                "config_version",
                "claim_ceiling",
            }.issubset(factor_payload)
        )
        self.assertNotIn("pit_feature_store_artifact", factor_payload)
        self.assertNotIn("objective_universe_artifact", factor_payload)
        self.assertNotIn("walk_forward_protocol_artifact", factor_payload)
        self.assertNotIn("governance_promotion_artifact", factor_payload)
        self.assertNotIn("feature_rows", json.dumps(factor_payload, ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(factor_payload.get("objective_universe", {}), ensure_ascii=False))
        self.assertNotIn("splits", factor_payload.get("walk_forward_protocol", {}))
        self.assertNotIn("oos_rows", factor_payload.get("oos_validation", {}))
        self.assertNotIn("period_metrics", factor_payload.get("oos_validation", {}))
        self.assertNotIn("transition_log", factor_payload.get("governance_promotion", {}))
        self.assertNotIn("approved_projection_entries", factor_payload.get("dashboard_projection_registry", {}))
        sweep_payload = json.loads(sweep_path.read_text(encoding="utf-8"))
        self.assertEqual(sweep_payload["claim_ceiling"], "diagnostic_research_only")
        self.assertNotIn("trials", sweep_payload["multiple_testing_diagnostics"])
        self.assertNotIn("oos_rows", sweep_payload["oos_validation"])
        self.assertNotIn("transition_log", sweep_payload["governance_promotion"])
        self.assertNotIn("approved_projection_entries", sweep_payload["dashboard_projection_registry"])

    def test_operations_summary_is_light_and_details_are_sectioned(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            summary = build_operations_summary(session, sample_symbol="600519.SH")
            portfolios = build_operations_detail(session, section="portfolios", sample_symbol="600519.SH")
            factor_detail = build_operations_detail(session, section="factor_observation", sample_symbol="600519.SH")

        payload_kb = len(json.dumps(summary, ensure_ascii=False, default=str).encode("utf-8")) / 1024
        self.assertLessEqual(payload_kb, 250)
        self.assertEqual(summary["portfolios"], [])
        self.assertEqual(summary["recommendation_replay"], [])
        self.assertIn("today_at_a_glance", summary)
        self.assertIn("data_quality_summary", summary)
        self.assertGreaterEqual(len(portfolios["portfolios"]), 1)
        self.assertIn("factor_observation_summary", factor_detail)
        factor_summary = factor_detail["factor_observation_summary"]
        self.assertEqual(factor_summary["promotion_status"], "blocked_from_production")
        self.assertEqual(factor_summary["claim_ceiling"], "diagnostic_research_only")
        self.assertEqual(factor_summary["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(factor_summary["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(factor_summary["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(factor_summary["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
        self.assertEqual(factor_summary["oos_validation"]["artifact_type"], "oos_validation")
        self.assertEqual(factor_summary["governance_promotion"]["artifact_type"], "governance_promotion_decision")
        self.assertEqual(factor_summary["governance_promotion"]["current_state"], "diagnostic_only")
        self.assertEqual(
            factor_summary["dashboard_projection_registry"]["artifact_type"],
            "dashboard_approved_projection_registry",
        )
        self.assertEqual(factor_summary["dashboard_projection_registry"]["approved_projection_count"], 0)
        self.assertNotIn("feature_rows", json.dumps(factor_summary, ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(factor_summary, ensure_ascii=False))
        self.assertNotIn("splits", factor_summary["walk_forward_protocol"])
        self.assertNotIn("oos_rows", factor_summary["oos_validation"])
        self.assertNotIn("transition_log", factor_summary["governance_promotion"])
        self.assertNotIn("approved_projection_entries", factor_summary["dashboard_projection_registry"])
        self.assertEqual(factor_summary["validation_protocol"]["feature_source_status"], "legacy_diagnostic_only")
        self.assertIn("independent_feature_source", factor_summary["gate_readout"]["blocking_gate_ids"])
        self.assertEqual(factor_summary["lineage"]["feature_version"], "legacy_recommendation_payload_factor_breakdown:v1")

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        operations_response = client.get(
            "/dashboard/operations/details",
            params={"section": "factor_observation", "sample_symbol": "600519.SH"},
        )
        self.assertEqual(operations_response.status_code, 200)
        operations_payload = operations_response.json()
        self.assertEqual(
            operations_payload["factor_observation_summary"]["objective_universe"]["artifact_type"],
            "objective_frozen_universe",
        )
        self.assertEqual(
            operations_payload["factor_observation_summary"]["research_input_snapshot"]["artifact_type"],
            "research_input_snapshot",
        )
        self.assertEqual(
            operations_payload["factor_observation_summary"]["pit_feature_store"]["artifact_type"],
            "pit_feature_store",
        )
        self.assertEqual(
            operations_payload["factor_observation_summary"]["walk_forward_protocol"]["artifact_type"],
            "walk_forward_purge_embargo",
        )
        self.assertEqual(
            operations_payload["factor_observation_summary"]["oos_validation"]["artifact_type"],
            "oos_validation",
        )
        self.assertEqual(
            operations_payload["factor_observation_summary"]["governance_promotion"]["artifact_type"],
            "governance_promotion_decision",
        )
        self.assertEqual(
            operations_payload["factor_observation_summary"]["dashboard_projection_registry"]["artifact_type"],
            "dashboard_approved_projection_registry",
        )
        self.assertNotIn("feature_rows", json.dumps(operations_payload["factor_observation_summary"], ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(operations_payload["factor_observation_summary"], ensure_ascii=False))
        self.assertNotIn("splits", operations_payload["factor_observation_summary"]["walk_forward_protocol"])
        self.assertNotIn("oos_rows", operations_payload["factor_observation_summary"]["oos_validation"])
        self.assertNotIn("transition_log", operations_payload["factor_observation_summary"]["governance_promotion"])
        self.assertNotIn(
            "approved_projection_entries",
            operations_payload["factor_observation_summary"]["dashboard_projection_registry"],
        )

        dashboard_response = client.get("/stocks/600519.SH/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = dashboard_response.json()
        self.assertEqual(dashboard_payload["factor_validation"]["claim_ceiling"], "diagnostic_research_only")
        self.assertEqual(
            dashboard_payload["factor_validation"]["objective_universe"]["artifact_type"],
            "objective_frozen_universe",
        )
        self.assertEqual(
            dashboard_payload["factor_validation"]["research_input_snapshot"]["artifact_type"],
            "research_input_snapshot",
        )
        self.assertEqual(
            dashboard_payload["factor_validation"]["pit_feature_store"]["artifact_type"],
            "pit_feature_store",
        )
        self.assertEqual(
            dashboard_payload["factor_validation"]["walk_forward_protocol"]["artifact_type"],
            "walk_forward_purge_embargo",
        )
        self.assertEqual(
            dashboard_payload["factor_validation"]["oos_validation"]["artifact_type"],
            "oos_validation",
        )
        self.assertEqual(
            dashboard_payload["factor_validation"]["governance_promotion"]["artifact_type"],
            "governance_promotion_decision",
        )
        self.assertEqual(
            dashboard_payload["factor_validation"]["dashboard_projection_registry"]["artifact_type"],
            "dashboard_approved_projection_registry",
        )
        self.assertNotIn("feature_rows", json.dumps(dashboard_payload["factor_validation"], ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(dashboard_payload["factor_validation"], ensure_ascii=False))
        self.assertNotIn("splits", dashboard_payload["factor_validation"]["walk_forward_protocol"])
        self.assertNotIn("oos_rows", dashboard_payload["factor_validation"]["oos_validation"])
        self.assertNotIn("transition_log", dashboard_payload["factor_validation"]["governance_promotion"])
        self.assertNotIn("approved_projection_entries", dashboard_payload["factor_validation"]["dashboard_projection_registry"])

    def test_stock_dashboard_schema_accepts_string_horizon_readout_and_new_fields(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))

        with session_scope(self.database_url) as session:
            payload = get_stock_dashboard(session, "600519.SH")
        payload["research_horizon_readout"] = payload.get("research_horizon_readout") or "主周期尚未批准。"

        parsed = StockDashboardResponse.model_validate(payload)
        self.assertIsNotNone(parsed.research_horizon_readout)
        self.assertEqual(parsed.data_quality["symbol"], "600519.SH")
        self.assertIn("benchmark_context", parsed.factor_validation)
        self.assertEqual(parsed.factor_validation["promotion_status"], "blocked_from_production")
        self.assertEqual(parsed.factor_validation["claim_ceiling"], "diagnostic_research_only")
        self.assertEqual(parsed.factor_validation["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(parsed.factor_validation["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(parsed.factor_validation["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(parsed.factor_validation["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
        self.assertEqual(parsed.factor_validation["oos_validation"]["artifact_type"], "oos_validation")
        self.assertEqual(parsed.factor_validation["governance_promotion"]["artifact_type"], "governance_promotion_decision")
        self.assertEqual(
            parsed.factor_validation["dashboard_projection_registry"]["artifact_type"],
            "dashboard_approved_projection_registry",
        )
        self.assertEqual(parsed.factor_validation["validation_protocol"]["feature_source_status"], "legacy_diagnostic_only")


if __name__ == "__main__":
    unittest.main()
