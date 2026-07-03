from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ashare_evidence.api import create_app
from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.data_quality import build_data_quality_summary
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.factor_observation import build_factor_observations, sweep_weights
from ashare_evidence.lineage import build_lineage
from ashare_evidence.market_rules import account_trade_eligibility, board_rule
from ashare_evidence.models import FeatureSnapshot, NewsEntityLink, NewsItem, Stock
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
            summary = build_data_quality_summary(session, symbols=["600519.SH"])

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
        self.assertNotIn("pit_feature_store_artifact", study)
        self.assertNotIn("feature_rows", json.dumps(study, ensure_ascii=False))
        self.assertEqual(
            study["lineage"]["research_input_snapshot_id"],
            study["research_input_snapshot"]["artifact_id"],
        )
        self.assertEqual(study["lineage"]["pit_feature_store_id"], study["pit_feature_store"]["artifact_id"])
        self.assertEqual(study["lineage"]["objective_universe_id"], study["objective_universe"]["artifact_id"])
        self.assertEqual(study["lineage"]["walk_forward_protocol_id"], study["walk_forward_protocol"]["artifact_id"])
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
        self.assertEqual(sweep["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(sweep["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(sweep["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(sweep["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
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
        sweep_path = artifact_root / "research_validation" / "weight_sweep_studies" / f"{sweep['artifact_id']}.json"
        self.assertTrue(universe_path.exists())
        self.assertTrue(snapshot_path.exists())
        self.assertTrue(pit_path.exists())
        self.assertTrue(walk_forward_path.exists())
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
        pit_feature_row = pit_payload["feature_rows"][0]
        self.assertIn("price_baseline", pit_feature_row["features"])
        self.assertIn("liquidity", pit_feature_row["features"])
        self.assertIn("risk_trading_constraints", pit_feature_row["features"])
        self.assertIn("news_text", pit_feature_row["features"])
        self.assertNotIn("factor_breakdown", json.dumps(pit_feature_row, ensure_ascii=False))
        factor_payload = json.loads(factor_path.read_text(encoding="utf-8"))
        self.assertNotIn("pit_feature_store_artifact", factor_payload)
        self.assertNotIn("objective_universe_artifact", factor_payload)
        self.assertNotIn("walk_forward_protocol_artifact", factor_payload)
        self.assertNotIn("feature_rows", json.dumps(factor_payload, ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(factor_payload.get("objective_universe", {}), ensure_ascii=False))
        self.assertNotIn("splits", factor_payload.get("walk_forward_protocol", {}))

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
        self.assertEqual(factor_summary["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(factor_summary["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(factor_summary["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(factor_summary["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
        self.assertNotIn("feature_rows", json.dumps(factor_summary, ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(factor_summary, ensure_ascii=False))
        self.assertNotIn("splits", factor_summary["walk_forward_protocol"])
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
        self.assertNotIn("feature_rows", json.dumps(operations_payload["factor_observation_summary"], ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(operations_payload["factor_observation_summary"], ensure_ascii=False))
        self.assertNotIn("splits", operations_payload["factor_observation_summary"]["walk_forward_protocol"])

        dashboard_response = client.get("/stocks/600519.SH/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = dashboard_response.json()
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
        self.assertNotIn("feature_rows", json.dumps(dashboard_payload["factor_validation"], ensure_ascii=False))
        self.assertNotIn('"members"', json.dumps(dashboard_payload["factor_validation"], ensure_ascii=False))
        self.assertNotIn("splits", dashboard_payload["factor_validation"]["walk_forward_protocol"])

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
        self.assertEqual(parsed.factor_validation["objective_universe"]["artifact_type"], "objective_frozen_universe")
        self.assertEqual(parsed.factor_validation["research_input_snapshot"]["artifact_type"], "research_input_snapshot")
        self.assertEqual(parsed.factor_validation["pit_feature_store"]["artifact_type"], "pit_feature_store")
        self.assertEqual(parsed.factor_validation["walk_forward_protocol"]["artifact_type"], "walk_forward_purge_embargo")
        self.assertEqual(parsed.factor_validation["validation_protocol"]["feature_source_status"], "legacy_diagnostic_only")


if __name__ == "__main__":
    unittest.main()
