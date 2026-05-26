# ruff: noqa: F403,F405
from __future__ import annotations

from tests.dashboard_views_test_support import *


class DashboardViewTests(DashboardViewTestCase):
    def test_seeded_watchlist_builds_multi_stock_candidates(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)

        self.assertEqual(len(candidates["items"]), 4)
        self.assertEqual([item["rank"] for item in candidates["items"]], [1, 2, 3, 4])
        candidate_symbols = {item["symbol"] for item in candidates["items"]}
        self.assertEqual(candidate_symbols, {"600519.SH", "300750.SZ", "601318.SH", "002594.SZ"})
        self.assertTrue(all(item["change_summary"] for item in candidates["items"]))
        first_candidate = candidates["items"][0]
        self.assertEqual(first_candidate["window_definition"], PHASE2_WINDOW_DEFINITION)
        self.assertEqual(first_candidate["target_horizon_label"], phase2_target_horizon_label())
        self.assertEqual(first_candidate["validation_status"], "pending_rebuild")
        self.assertTrue(first_candidate["validation_note"])
        self.assertTrue(first_candidate["validation_artifact_id"])
        self.assertTrue(first_candidate["validation_manifest_id"])
        self.assertEqual(first_candidate["validation_sample_count"], 3)
        self.assertIn("validation-metrics:", first_candidate["validation_artifact_id"])
        self.assertIn("rolling-validation:", first_candidate["validation_manifest_id"])
        self.assertIsNotNone(first_candidate["validation_rank_ic_mean"])
        self.assertIsNotNone(first_candidate["validation_positive_excess_rate"])
        self.assertEqual(first_candidate["source_classification"], "artifact_backed")
        self.assertEqual(first_candidate["validation_mode"], "migration_placeholder")
        self.assertEqual(first_candidate["claim_gate"]["status"], "observe_only")
        self.assertEqual(first_candidate["display_direction"], "watch")
        self.assertEqual(first_candidate["display_direction_label"], "继续观察")
        self.assertGreaterEqual(len(first_candidate["claim_gate"]["blocking_reasons"]), 1)

    def test_candidate_serialization_tolerates_null_factor_cards(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            recommendation = session.scalar(
                select(Recommendation).order_by(Recommendation.generated_at.desc())
            )
            assert recommendation is not None
            payload = dict(recommendation.recommendation_payload or {})
            evidence = dict(payload.get("evidence") or {})
            evidence["factor_cards"] = None
            evidence["degrade_flags"] = None
            payload["evidence"] = evidence
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertTrue(candidates["items"])
        first_candidate = candidates["items"][0]
        self.assertTrue(first_candidate["why_now"])
        self.assertTrue(first_candidate["primary_risk"])
        self.assertGreaterEqual(len(dashboard["recommendation"]["evidence"]["factor_cards"]), 1)
        self.assertIsInstance(dashboard["recommendation"]["evidence"]["degrade_flags"], list)
        fusion_card = next(
            card for card in dashboard["recommendation"]["evidence"]["factor_cards"] if card["factor_key"] == "fusion"
        )
        self.assertNotIn("用于汇总价格、事件与降级状态的融合层", fusion_card["headline"])
        self.assertNotEqual(first_candidate["why_now"], "用于汇总价格、事件与降级状态的融合层。")

    def test_candidate_primary_risk_prioritizes_specific_risk_over_news_template(self) -> None:
        generic_news_risk = "若 7 日内出现负向公告或行业监管扰动，新闻因子会优先转负。"

        risk = _candidate_primary_risk(
            {
                "historical_validation": {
                    "metrics": {
                        "rank_ic_mean": -0.147,
                        "positive_excess_rate": 0.758,
                    }
                },
                "risk": {
                    "risk_flags": [
                        generic_news_risk,
                        "基本面风险：现金流质量-0.70，经营现金流严重不足。",
                    ]
                },
            }
        )

        assert risk is not None
        self.assertIn("验证冲突", risk)
        self.assertIn("RankIC -0.147", risk)
        self.assertNotEqual(risk, generic_news_risk)

        fallback_risk = _candidate_primary_risk(
            {
                "historical_validation": {"metrics": {}},
                "risk": {
                    "risk_flags": [
                        generic_news_risk,
                        "基本面风险：盈利能力评分0.15，盈利水平极其孱弱。",
                    ]
                },
            }
        )

        self.assertEqual(fallback_risk, "基本面风险：盈利能力评分0.15，盈利水平极其孱弱。")

    def test_validation_conflict_is_serialized_and_promoted_to_research_packet(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            recommendation = session.scalar(
                select(Recommendation)
                .join(Stock)
                .where(Stock.symbol == "600519.SH")
                .order_by(Recommendation.generated_at.desc())
            )
            assert recommendation is not None
            payload = dict(recommendation.recommendation_payload or {})
            payload["validation_metrics_artifact_id"] = "manual-conflict-metrics"
            payload["historical_validation"] = {
                "status": "verified",
                "artifact_type": "rolling_validation",
                "artifact_id": "manual-conflict-metrics",
                "manifest_id": "manual-conflict-manifest",
                "label_definition": "phase2_forward_excess_return",
                "benchmark_definition": "watchlist_equal_weight_proxy",
                "cost_definition": "12 bps",
                "metrics": {
                    "sample_count": 149,
                    "rank_ic_mean": -0.147,
                    "positive_excess_rate": 0.758,
                    "coverage_ratio": 0.93,
                },
            }
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")
            candidates = list_candidate_recommendations(session, limit=8)

        conflict = dashboard["recommendation"]["historical_validation"]["validation_conflict"]
        self.assertIn("验证冲突", conflict)
        self.assertIn("排序能力尚未成立", conflict)
        self.assertEqual(dashboard["follow_up"]["research_packet"]["validation_conflict"], conflict)
        serialized = StockDashboardResponse.model_validate(dashboard).model_dump(mode="json")
        self.assertEqual(serialized["follow_up"]["research_packet"]["validation_conflict"], conflict)
        candidate = next(item for item in candidates["items"] if item["symbol"] == "600519.SH")
        self.assertIn("验证冲突", candidate["primary_risk"])

    def test_dashboard_normalizes_legacy_placeholder_explanations(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            recommendation = session.scalar(
                select(Recommendation)
                .join(Stock)
                .where(Stock.symbol == "600519.SH")
                .order_by(Recommendation.generated_at.desc())
            )
            assert recommendation is not None
            payload = dict(recommendation.recommendation_payload or {})
            evidence = dict(payload.get("evidence") or {})
            factor_cards = list(evidence.get("factor_cards") or [])
            for card in factor_cards:
                if card.get("factor_key") == "fusion":
                    card["headline"] = "用于汇总价格、事件与降级状态的融合层。"
                    card["risk_note"] = None
            evidence["primary_drivers"] = ["用于汇总价格、事件与降级状态的融合层。"]
            evidence["supporting_context"] = ["价格趋势、确认项和事件冲突共同构成当前 Phase 2 规则基线的结构化输入。"]
            evidence["conflicts"] = ["event_conflict_high", "missing_news_evidence"]
            evidence["degrade_flags"] = ["event_conflict_high", "missing_news_evidence", "market_data_stale"]
            evidence["factor_cards"] = factor_cards
            payload["evidence"] = evidence
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")
            candidates = list_candidate_recommendations(session, limit=8)

        dashboard_evidence = dashboard["recommendation"]["evidence"]
        fusion_card = next(card for card in dashboard_evidence["factor_cards"] if card["factor_key"] == "fusion")
        first_candidate = next(item for item in candidates["items"] if item["symbol"] == "600519.SH")

        self.assertNotIn("用于汇总价格、事件与降级状态的融合层", fusion_card["headline"])
        self.assertTrue(all("Phase 2 规则基线" not in item for item in dashboard_evidence["supporting_context"]))
        self.assertIn("价格与事件方向冲突较高，系统已主动下调对外表达。", dashboard_evidence["conflicts"])
        self.assertIn("近期缺少新增事件证据，当前更多依赖价格趋势观察。", dashboard_evidence["conflicts"])
        self.assertIn("最新行情刷新偏旧，短线结论需要谨慎使用。", dashboard_evidence["conflicts"])
        self.assertNotEqual(first_candidate["why_now"], "用于汇总价格、事件与降级状态的融合层。")
        self.assertTrue(all("用于汇总价格、事件与降级状态的融合层" not in item for item in dashboard_evidence["primary_drivers"]))

    def test_stock_dashboard_contains_change_trace_and_follow_up_context(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertEqual(dashboard["stock"]["symbol"], "600519.SH")
        self.assertTrue(dashboard["change"]["has_previous"])
        self.assertGreaterEqual(len(dashboard["price_chart"]), 24)
        self.assertGreaterEqual(len(dashboard["today_price_chart"]), 2)
        latest_chart_day = dashboard["today_price_chart"][-1]["observed_at"].date()
        self.assertGreater(
            sum(1 for point in dashboard["today_price_chart"] if point["observed_at"].date() == latest_chart_day),
            1,
        )
        self.assertGreaterEqual(len(dashboard["recent_news"]), 3)
        self.assertGreaterEqual(len(dashboard["glossary"]), 5)
        self.assertGreaterEqual(len(dashboard["follow_up"]["suggested_questions"]), 4)
        self.assertIn("请回答这个问题", dashboard["follow_up"]["copy_prompt"])
        self.assertIn(f"目标周期：{phase2_target_horizon_label()}", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("回测样本量：3", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("系统当前建议（仅供参考，不是必须采纳）", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("如果验证指标之间存在张力或冲突，必须先解释冲突", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("如果证据不足以支持买入/卖出/强化动作，要直接说明", dashboard["follow_up"]["copy_prompt"])
        self.assertTrue(dashboard["follow_up"]["research_packet"]["validation_artifact_id"])
        self.assertEqual(dashboard["follow_up"]["research_packet"]["validation_sample_count"], 3)
        self.assertEqual(dashboard["follow_up"]["research_packet"]["manual_review_trigger_mode"], "manual")
        self.assertIsNone(dashboard["follow_up"]["research_packet"]["manual_review_artifact_id"])

    def test_stock_dashboard_embeds_latest_event_deep_analysis(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        artifact_root = artifact_root_from_database_url(self.database_url)
        event_dir = artifact_root / "event_analysis" / "600519.SH"
        event_dir.mkdir(parents=True, exist_ok=True)
        filename = "20260430T090527_direction_switch.json"
        detail = {
            "symbol": "600519.SH",
            "trigger_type": "direction_switch",
            "trigger_detail": "方向从观察切换到风险提示，需要独立复核。",
            "triggered_at": "2026-04-30T09:05:27+08:00",
            "generated_at": "2026-04-30T09:06:10+08:00",
            "status": "completed",
            "independent_direction": "partial_agree",
            "confidence": 0.62,
            "key_evidence": [
                {"source": "内部因子", "content": "价格基线转弱但事件因子仍有支撑。"},
            ],
            "risks": ["验证样本不足，不能直接强化方向。"],
            "information_gaps": ["缺少最新公告全文。"],
            "next_checkpoint": "等待下一根日线确认。",
            "correction_suggestion": "维持研究候选，不提升为买入表达。",
            "model_used": "deepseek-flash",
        }
        (event_dir / filename).write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
        (event_dir / "index.json").write_text(
            json.dumps(
                [
                    {
                        "file": filename,
                        "trigger_type": detail["trigger_type"],
                        "triggered_at": detail["triggered_at"],
                        "generated_at": detail["generated_at"],
                        "status": detail["status"],
                        "independent_direction": detail["independent_direction"],
                        "confidence": detail["confidence"],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertEqual(len(dashboard["event_analyses"]), 1)
        analysis = dashboard["event_analyses"][0]
        self.assertEqual(analysis["trigger_type"], "direction_switch")
        self.assertEqual(analysis["independent_direction"], "partial_agree")
        self.assertEqual(analysis["confidence"], 0.62)
        self.assertEqual(analysis["key_evidence"][0]["source"], "内部因子")
        self.assertIn("维持研究候选", analysis["correction_suggestion"])

    def test_dashboard_candidates_operations_and_watchlist_ignore_stale_same_as_of_backfill(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            fresh, stale = inject_market_data_stale_backfill(session, "600519.SH")

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)
            dashboard = get_stock_dashboard(session, "600519.SH")
            build_operations_dashboard(session, sample_symbol="600519.SH")
            watchlist = list_watchlist_entries(session)

        self.assertEqual(candidates["items"][0]["as_of_data_time"], fresh.as_of_data_time)
        self.assertNotEqual(candidates["items"][0]["generated_at"], stale.generated_at)
        self.assertEqual(dashboard["recommendation"]["id"], fresh.id)
        self.assertNotEqual(dashboard["recommendation"]["id"], stale.id)
        watchlist_item = next(item for item in watchlist["items"] if item["symbol"] == "600519.SH")
        self.assertEqual(watchlist_item["latest_direction"], fresh.direction)
        self.assertIsNone(dashboard["follow_up"]["research_packet"]["manual_review_generated_at"])
        self.assertEqual(dashboard["recommendation"]["historical_validation"]["metrics"]["sample_count"], 3)
        self.assertIn("rank_ic_mean", dashboard["recommendation"]["historical_validation"]["metrics"])
        self.assertEqual(dashboard["recommendation"]["claim_gate"]["status"], "observe_only")
        self.assertEqual(dashboard["recommendation"]["claim_gate"]["public_direction"], "watch")
        self.assertGreaterEqual(len(dashboard["recommendation"]["claim_gate"]["blocking_reasons"]), 1)
        self.assertEqual(dashboard["hero"]["direction_label"], "继续观察")
        self.assertTrue(dashboard["risk_panel"]["disclaimer"])
        self.assertGreaterEqual(len(dashboard["evidence"]), 6)
        self.assertEqual(len(dashboard["simulation_orders"]), 2)
