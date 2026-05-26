# ruff: noqa: F403,F405
from __future__ import annotations

from tests.shortpick_lab_test_support import *


class ShortpickLabFeedbackTests(ShortpickLabTestCase):
    def test_llm_paper_control_excludes_non_mainboard_for_new_retail_account(self) -> None:
        with session_scope(self.database_url) as session:
            run = ShortpickExperimentRun(
                run_key="shortpick:test:llm-paper-account-filter",
                run_date=date(2026, 5, 11),
                prompt_version="test",
                information_mode="native_web_open_discovery",
                status="completed",
                trigger_source="test",
                started_at=datetime(2026, 5, 11, 8, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 11, 8, 1, tzinfo=UTC),
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            rounds = [
                ShortpickModelRound(
                    run_id=run.id,
                    round_key=f"shortpick:test:llm-paper-account-filter:{provider}",
                    provider_name=provider,
                    model_name="test-model",
                    executor_kind="test",
                    round_index=index,
                    status="completed",
                    raw_answer="{}",
                    parsed_payload={},
                    sources_payload=[],
                    started_at=datetime(2026, 5, 11, 8, index, tzinfo=UTC),
                    completed_at=datetime(2026, 5, 11, 8, index + 1, tzinfo=UTC),
                )
                for index, provider in enumerate(("deepseek", "openai"), start=1)
            ]
            session.add_all(rounds)
            session.flush()
            session.add_all(
                [
                    ShortpickCandidate(
                        run_id=run.id,
                        round_id=rounds[0].id,
                        candidate_key="shortpick-candidate:test:300604",
                        symbol="300604.SZ",
                        name="长川科技",
                        normalized_theme="半导体设备",
                        confidence=0.9,
                        research_priority="cross_model_same_symbol",
                        parse_status="parsed",
                        sources_payload=[{"credibility_status": "verified"}],
                        candidate_payload={},
                    ),
                    ShortpickCandidate(
                        run_id=run.id,
                        round_id=rounds[1].id,
                        candidate_key="shortpick-candidate:test:688981",
                        symbol="688981.SH",
                        name="中芯国际",
                        normalized_theme="半导体设备",
                        confidence=0.88,
                        research_priority="same_model_repeat_symbol",
                        parse_status="parsed",
                        sources_payload=[{"credibility_status": "verified"}],
                        candidate_payload={},
                    ),
                    ShortpickCandidate(
                        run_id=run.id,
                        round_id=rounds[1].id,
                        candidate_key="shortpick-candidate:test:600519",
                        symbol="600519.SH",
                        name="贵州茅台",
                        normalized_theme="消费修复",
                        confidence=0.6,
                        research_priority="single_model_high_conviction",
                        parse_status="parsed",
                        sources_payload=[{"credibility_status": "verified"}],
                        candidate_payload={},
                    ),
                ]
            )
            session.flush()

            result = select_shortpick_llm_paper_control_candidate(session, run)

            self.assertEqual(result["status"], "selected")
            self.assertEqual(result["symbol"], "600519.SH")
            self.assertEqual(result["eligible_candidate_count"], 1)
            self.assertEqual(result["excluded_candidate_count"], 2)
            excluded = {item["symbol"]: item["board_label"] for item in result["excluded_examples"]}
            self.assertEqual(excluded["300604.SZ"], "创业板")
            self.assertEqual(excluded["688981.SH"], "科创板")
            selected_candidates = session.scalars(
                select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id)
            ).all()
            tracking_by_symbol = {
                candidate.symbol: (candidate.candidate_payload or {}).get("tracking_role")
                for candidate in selected_candidates
            }
            self.assertEqual(tracking_by_symbol["600519.SH"], "llm_paper_control_primary")
            self.assertIsNone(tracking_by_symbol["300604.SZ"])
            self.assertIsNone(tracking_by_symbol["688981.SH"])

    def test_ai_topic_normalization_clusters_cross_model_topic_without_string_match(self) -> None:
        self._seed_stock_bars("000831.SZ", "中国稀土", [40 + index for index in range(8)])
        self._seed_stock_bars("600111.SH", "北方稀土", [30 + index * 0.5 for index in range(8)])
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index * 1.5 for index in range(8)])
        executors = [
            StaticShortpickExecutor(
                "openai",
                "gpt-test",
                "fake",
                _answer(
                    "000831.SZ",
                    "中国稀土",
                    "稀土价格上行与战略资源约束",
                    "https://a.example/rare-earth-price",
                    topic_cluster_id="rare_earth_price_security",
                    topic_label="稀土价格与战略资源安全",
                ),
            ),
            StaticShortpickExecutor(
                "deepseek",
                "deepseek-test",
                "fake",
                _answer(
                    "600111.SH",
                    "北方稀土",
                    "央企稀土整合预期",
                    "https://b.example/rare-earth-soe",
                    topic_cluster_id="rare_earth_price_security",
                    topic_label="稀土价格与战略资源安全",
                ),
            ),
        ]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    payload = run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )
                    feedback = build_shortpick_model_feedback(session)

        self.assertEqual(payload["consensus"]["research_priority"], "cross_model_same_topic")
        self.assertEqual(payload["consensus"]["summary"]["cross_model_themes"], ["rare_earth_price_security"])
        self.assertEqual(payload["consensus"]["summary"]["cross_model_theme_labels"]["rare_earth_price_security"], "稀土价格与战略资源安全")
        self.assertEqual(payload["consensus"]["summary"]["topic_registry"][0]["status"], "active")
        self.assertTrue(all(item["research_priority"] == "cross_model_same_topic" for item in payload["candidates"]))
        self.assertEqual(payload["candidates"][0]["topic_normalization"]["topic_cluster_id"], "rare_earth_price_security")
        openai_feedback = next(item for item in feedback["models"] if item["provider_name"] == "openai")
        topic_group = next(group for group in openai_feedback["validation_by_theme"] if group["group_key"] == "rare_earth_price_security")
        self.assertEqual(topic_group["label"], "稀土价格与战略资源安全")
        self.assertGreater(topic_group["official_sample_count"], 0)

    def test_ai_topic_backfill_repairs_missing_model_topic_output(self) -> None:
        self._seed_stock_bars("600673.SH", "东阳光", [20 + index for index in range(8)])
        self._seed_stock_bars("002156.SZ", "通富微电", [30 + index for index in range(8)])
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index for index in range(8)])
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("600673.SH", "东阳光", "AI算力服务大额合同", "https://a.example/compute")),
            StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("002156.SZ", "通富微电", "先进封测与AI算力链扩散", "https://b.example/compute")),
        ]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    payload = run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )
                    run = session.get(ShortpickExperimentRun, payload["id"])
                    assert run is not None

                    def classifier(_packet: dict[str, object]) -> dict[str, object]:
                        return {
                            "topic_cluster_id": "ai_compute_hardware",
                            "label_zh": "AI 算力硬件",
                            "topic_confidence": 0.86,
                            "normalization_method": "ai_backfill_v1",
                            "status": "classified",
                            "reason": "测试夹具模拟 AI 归类。",
                        }

                    result = normalize_shortpick_candidate_topics(session, run_id=run.id, force=True, classifier=classifier)
                    consensus = build_shortpick_consensus(session, run)
                    feedback = build_shortpick_model_feedback(session)

        self.assertEqual(result["updated_count"], 2)
        self.assertEqual(consensus.theme_convergence, 1.0)
        self.assertEqual(consensus.research_priority, "cross_model_same_topic")
        openai_feedback = next(item for item in feedback["models"] if item["provider_name"] == "openai")
        self.assertEqual(openai_feedback["validation_by_theme"][0]["group_key"], "ai_compute_hardware")
        self.assertEqual(openai_feedback["validation_by_theme"][0]["label"], "AI 算力硬件")

    def test_ai_topic_normalization_fixture_clusters_without_keyword_rules(self) -> None:
        cases = [
            ("通航订单与低空基础设施", "low_altitude_economy", "低空经济"),
            ("国产算力芯片服务器交付", "ai_compute_hardware", "AI 算力硬件"),
            ("卫星互联网发射服务", "commercial_space", "商业航天"),
            ("特高压设备招标放量", "grid_equipment", "电网设备"),
        ]
        for theme, topic_id, label in cases:
            parsed = json.loads(
                _answer(
                    "001234.SZ",
                    "测试股份",
                    theme,
                    "https://news.cn/topic",
                    topic_cluster_id=topic_id,
                    topic_label=label,
                )
            )
            topic = _normalize_shortpick_topic(parsed)
            self.assertEqual(topic["topic_cluster_id"], topic_id)
            self.assertEqual(topic["label_zh"], label)
            self.assertEqual(topic["status"], "classified")

    def test_frozen_exit_tracks_are_computed_on_ten_trading_day_window(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-market-factor:1:frozen:1",
            symbol="000001.SZ",
            name="测试银行",
            research_priority="market_factor_frozen_paper",
            candidate_payload={"tracking_role": "frozen_paper_primary", "frozen_paper_strategy": {}},
        )
        start = datetime(2026, 5, 6, 7, 0, tzinfo=UTC)
        closes = [100, 102, 104, 106, 108, 109, 107, 106, 105, 104, 103]
        bars = [
            MarketBar(
                bar_key=f"track-{index}",
                stock_id=1,
                timeframe="1d",
                observed_at=start + timedelta(days=index),
                open_price=close - 1,
                high_price=111 if index == 5 else close + 1,
                low_price=close - 2,
                close_price=close,
                volume=1000,
                amount=close * 1000,
                raw_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://track/{index}",
                lineage_hash=compute_lineage_hash({"index": index}),
            )
            for index, close in enumerate(closes)
        ]
        benchmark_maps = {
            "000300.SH": {
                (start + timedelta(days=index)).date(): 200 + index
                for index in range(len(closes))
            }
        }

        tracks = _shortpick_frozen_exit_track_results(
            candidate=candidate,
            window=bars,
            benchmark_maps=benchmark_maps,
        )
        by_key = {item["key"]: item for item in tracks}

        self.assertEqual(set(by_key), {"mechanical_5d", "mechanical_10d", "take_profit_stop_loss"})
        self.assertEqual(by_key["mechanical_5d"]["holding_trading_days"], 5)
        self.assertEqual(by_key["mechanical_10d"]["holding_trading_days"], 10)
        self.assertEqual(by_key["take_profit_stop_loss"]["exit_reason"], "take_profit_10pct_touched")
        self.assertEqual(by_key["take_profit_stop_loss"]["exit_trade_day"], "2026-05-11")
        self.assertAlmostEqual(by_key["take_profit_stop_loss"]["stock_return"], 0.10)

    def test_frozen_stop_loss_can_trigger_before_five_day_window(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-market-factor:1:frozen:early-stop",
            symbol="000001.SZ",
            name="测试银行",
            research_priority="market_factor_frozen_paper",
            candidate_payload={"tracking_role": "frozen_paper_primary", "frozen_paper_strategy": {}},
        )
        start = datetime(2026, 5, 6, 7, 0, tzinfo=UTC)
        bars = [
            MarketBar(
                bar_key=f"early-stop-{index}",
                stock_id=1,
                timeframe="1d",
                observed_at=start + timedelta(days=index),
                open_price=100,
                high_price=101,
                low_price=91 if index == 2 else 99,
                close_price=99,
                volume=1000,
                amount=99000,
                raw_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://early-stop/{index}",
                lineage_hash=compute_lineage_hash({"index": index}),
            )
            for index in range(4)
        ]

        tracks = _shortpick_frozen_exit_track_results(candidate=candidate, window=bars, benchmark_maps={})
        by_key = {item["key"]: item for item in tracks}

        self.assertEqual(set(by_key), {"take_profit_stop_loss"})
        self.assertEqual(by_key["take_profit_stop_loss"]["exit_reason"], "stop_loss_8pct_touched")
        self.assertEqual(by_key["take_profit_stop_loss"]["exit_trade_day"], "2026-05-08")
        self.assertAlmostEqual(by_key["take_profit_stop_loss"]["stock_return"], -0.08)

    def test_frozen_exit_tracks_include_mechanical_5d_before_ten_day_window(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-market-factor:1:frozen:5d",
            symbol="000001.SZ",
            name="测试银行",
            research_priority="market_factor_frozen_paper",
            candidate_payload={"tracking_role": "frozen_paper_primary", "frozen_paper_strategy": {}},
        )
        start = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)
        bars = [
            MarketBar(
                bar_key=f"track-5d-{index}",
                stock_id=1,
                timeframe="1d",
                observed_at=start + timedelta(days=index),
                open_price=100 + index,
                high_price=102 + index,
                low_price=99 + index,
                close_price=100 + index,
                volume=1000,
                amount=(100 + index) * 1000,
                raw_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://track-5d/{index}",
                lineage_hash=compute_lineage_hash({"index": index}),
            )
            for index in range(6)
        ]

        tracks = _shortpick_frozen_exit_track_results(candidate=candidate, window=bars, benchmark_maps={})

        self.assertEqual([item["key"] for item in tracks], ["mechanical_5d"])
        self.assertEqual(tracks[0]["exit_trade_day"], "2026-05-16")
        self.assertEqual(tracks[0]["holding_trading_days"], 5)

    def test_llm_paper_control_candidate_gets_same_exit_tracks(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-candidate:1:llm",
            symbol="688981.SH",
            name="中芯国际",
            research_priority="cross_model_same_symbol",
            candidate_payload={"tracking_role": "llm_paper_control_primary"},
        )
        start = datetime(2026, 5, 6, 7, 0, tzinfo=UTC)
        bars = [
            MarketBar(
                bar_key=f"llm-track-{index}",
                stock_id=1,
                timeframe="1d",
                observed_at=start + timedelta(days=index),
                open_price=100 + index,
                high_price=101 + index,
                low_price=99 + index,
                close_price=100 + index,
                volume=1000,
                amount=(100 + index) * 1000,
                raw_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://llm-track/{index}",
                lineage_hash=compute_lineage_hash({"llm_index": index}),
            )
            for index in range(11)
        ]

        tracks = _shortpick_frozen_exit_track_results(
            candidate=candidate,
            window=bars,
            benchmark_maps={},
        )

        self.assertEqual([item["key"] for item in tracks], ["mechanical_5d", "mechanical_10d", "take_profit_stop_loss"])

    def test_model_feedback_aggregates_round_quality_sources_and_horizons(self) -> None:
        self._seed_daily_bars()
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")),
            StaticShortpickExecutor("deepseek", "deepseek-test", "fake", "not-json"),
        ]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with patch("ashare_evidence.shortpick_lab._source_credibility", return_value={"credibility_status": "verified", "credibility_reason": "test"}):
                    with session_scope(self.database_url) as session:
                        run_shortpick_experiment(
                            session,
                            run_date=date(2026, 5, 5),
                            rounds_per_model=1,
                            triggered_by="root",
                            executors=executors,
                        )
                        payload = build_shortpick_model_feedback(session)

        self.assertEqual(payload["overall"]["round_count"], 2)
        self.assertEqual(payload["overall"]["display_model_group_count"], 2)
        openai_feedback = next(item for item in payload["models"] if item["provider_name"] == "openai")
        deepseek_feedback = next(item for item in payload["models"] if item["provider_name"] == "deepseek")
        chatgpt_group = next(item for item in payload["model_groups"] if item["model_group_key"] == "chatgpt_5_5")
        deepseek_group = next(item for item in payload["model_groups"] if item["model_group_key"] == "deepseek_v4_pro_1m")
        self.assertEqual(openai_feedback["completed_round_count"], 1)
        self.assertEqual(openai_feedback["display_model_label"], "ChatGPT 5.5")
        self.assertEqual(openai_feedback["channel_label"], "实验通道")
        self.assertEqual(openai_feedback["source_credibility_counts"]["verified"], 1)
        self.assertTrue(any(group["group_key"] == "1" for group in openai_feedback["validation_by_horizon"]))
        one_day_group = next(group for group in openai_feedback["validation_by_horizon"] if group["group_key"] == "1")
        self.assertEqual(one_day_group["tradable_sample_count"], 1)
        self.assertEqual(one_day_group["completed_tradable_sample_count"], 1)
        self.assertGreaterEqual(openai_feedback["tradable_sample_count"], openai_feedback["official_sample_count"])
        self.assertGreaterEqual(openai_feedback["completed_tradable_sample_count"], openai_feedback["completed_official_sample_count"])
        self.assertTrue(openai_feedback["validation_by_industry"])
        self.assertNotIn("C 制造业", [group["label"] for group in openai_feedback["validation_by_theme"]])
        self.assertTrue(any(group["label"] == "单模型高置信" for group in openai_feedback["validation_by_priority"]))
        self.assertEqual(chatgpt_group["display_model_label"], "ChatGPT 5.5")
        self.assertEqual(chatgpt_group["round_count"], 1)
        self.assertEqual(len(chatgpt_group["channels"]), 1)
        self.assertGreaterEqual(chatgpt_group["channels"][0]["tradable_sample_count"], chatgpt_group["channels"][0]["official_sample_count"])
        self.assertEqual(deepseek_group["display_model_label"], "DeepSeek V4 Pro 1M")
        self.assertEqual(deepseek_feedback["failed_round_count"], 1)
        self.assertEqual(deepseek_feedback["parse_failed_candidate_count"], 1)
