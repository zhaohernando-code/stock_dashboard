# ruff: noqa: F403,F405
from __future__ import annotations

from tests.shortpick_lab_test_support import *


class ShortpickLabPaperTrackingTests(ShortpickLabTestCase):
    def test_frozen_paper_contract_tracks_three_trading_day_exit_windows(self) -> None:
        contract = shortpick_frozen_paper_strategy_contract()
        tracks = contract["monitoring_tracks"]
        paper_tracking_config = SHORTPICK_FROZEN_STRATEGY_CONFIG["paper_tracking"]

        self.assertEqual([item["key"] for item in tracks], [
            "mechanical_5d",
            "mechanical_10d",
            "take_profit_stop_loss",
        ])
        self.assertTrue(all(item["uses_trading_days"] for item in tracks))
        self.assertIn("交易日", contract["mode"])
        self.assertIn("低换手上升趋势", contract["label"])
        self.assertIn("成交额和换手率", contract["pool_rule"])
        self.assertIn("20日趋势向上", contract["selection_rule"])
        self.assertNotIn("第2名", contract["selection_rule"])
        risk_track = next(item for item in tracks if item["key"] == "take_profit_stop_loss")
        self.assertEqual(risk_track["stop_loss_pct"], paper_tracking_config["stop_loss_pct"])
        self.assertEqual(risk_track["take_profit_pct"], paper_tracking_config["take_profit_pct"])
        self.assertEqual(contract["version"], SHORTPICK_FROZEN_STRATEGY_CONFIG["version"])

    def test_market_factor_paper_controls_get_same_exit_tracks(self) -> None:
        contract = shortpick_market_factor_paper_control_contracts()
        self.assertEqual(
            [item["role"] for item in contract["controls"]],
            [
                SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
                SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
            ],
        )
        for role in (
            SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
            SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
        ):
            candidate = ShortpickCandidate(
                run_id=1,
                candidate_key=f"shortpick-market-factor:1:{role}:1",
                symbol="000001.SZ",
                name="测试银行",
                research_priority="market_factor_default",
                candidate_payload={"tracking_role": role},
            )
            start = datetime(2026, 5, 6, 7, 0, tzinfo=UTC)
            bars = [
                MarketBar(
                    bar_key=f"{role}-{index}",
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
                    source_uri=f"test://{role}/{index}",
                    lineage_hash=compute_lineage_hash({"role": role, "index": index}),
                )
                for index in range(11)
            ]

            tracks = _shortpick_frozen_exit_track_results(
                candidate=candidate,
                window=bars,
                benchmark_maps={},
            )

            self.assertEqual(
                [item["key"] for item in tracks],
                ["mechanical_5d", "mechanical_10d", "take_profit_stop_loss"],
            )

    def test_intraday_same_day_control_uses_captured_entry_price(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-market-factor:1:intraday-entry:1",
            symbol="000001.SZ",
            name="测试银行",
            research_priority="market_factor_intraday_same_day_low_turnover_uptrend",
            candidate_payload={
                "tracking_role": SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
                "paper_tracking_entry_price_source": "same_day_intraday_current",
                "paper_tracking_entry_price": 10.25,
            },
        )
        entry = MarketBar(
            bar_key="intraday-entry",
            stock_id=1,
            timeframe="1d",
            observed_at=datetime(2026, 5, 12, 7, 0, tzinfo=UTC),
            open_price=10.0,
            high_price=10.8,
            low_price=9.9,
            close_price=10.6,
            volume=1000,
            amount=10600,
            raw_payload={},
            license_tag="test",
            usage_scope="internal-test",
            redistribution_scope="none",
            source_uri="test://intraday-entry",
            lineage_hash=compute_lineage_hash({"bar": "intraday-entry"}),
        )

        self.assertEqual(_shortpick_entry_execution_price(candidate=candidate, entry=entry), 10.25)

    def test_market_factor_paper_controls_use_ten_day_display_horizon(self) -> None:
        self._seed_stock_bars("000001.SZ", "测试银行", [10 + index for index in range(22)])
        with session_scope(self.database_url) as session:
            run = ShortpickExperimentRun(
                run_key="shortpick:test:paper-control-horizon",
                run_date=date(2026, 5, 9),
                prompt_version="test",
                information_mode="native_web_open_discovery",
                status="completed",
                trigger_source="test",
                started_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 9, 8, 1, tzinfo=UTC),
            )
            session.add(run)
            session.flush()
            item = {
                "symbol": "000001.SZ",
                "name": "测试银行",
                "latest_trade_day": "2026-05-09",
                "return_1d": 0.01,
                "return_5d": 0.05,
                "return_10d": 0.1,
                "amount": 100000000.0,
                "turnover_rate": 3.0,
                "_market_factor_score": 1.2,
                "_ret10_rank_percentile": 1.0,
                "_turnover_rank_percentile": 1.0,
                "_ret1_rank_percentile": 0.5,
            }

            tracked = _upsert_shortpick_market_factor_candidate(
                session,
                run=run,
                item=item,
                family=SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY,
                rank=1,
                pool=[item],
                regime={},
                tracking_role=SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
            )
            untracked = _upsert_shortpick_market_factor_candidate(
                session,
                run=run,
                item=item,
                family=SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY,
                rank=2,
                pool=[item],
                regime={},
                tracking_role="control",
            )

            self.assertEqual(tracked.horizon_trading_days, 10)
            self.assertEqual(untracked.horizon_trading_days, 5)

    def test_paper_tracking_includes_prefreeze_seed_dates(self) -> None:
        now = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
        with session_scope(self.database_url) as session:
            seed_run = ShortpickExperimentRun(
                run_key="shortpick-prefreeze-paper-seed-test",
                run_date=date(2026, 5, 8),
                prompt_version="prefreeze-paper-seed-test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="manual_prefreeze_seed",
                triggered_by="root",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={
                    "market_factor_overlay": {
                        "frozen_paper_strategy": {
                            "inserted": True,
                            "gate_pass": True,
                            "symbol": "601138.SH",
                            "name": "工业富联",
                        }
                    }
                },
            )
            latest_run = ShortpickExperimentRun(
                run_key="shortpick-native-web-20260511-test",
                run_date=date(2026, 5, 11),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="scheduled_postmarket",
                triggered_by="root",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={"market_factor_overlay": {"frozen_paper_strategy": {"inserted": True}}},
            )
            session.add_all([seed_run, latest_run])
            session.flush()
            candidate = ShortpickCandidate(
                run_id=seed_run.id,
                candidate_key="shortpick-prefreeze-paper-seed-test:frozen",
                symbol="601138.SH",
                name="工业富联",
                normalized_theme="低换手上升趋势",
                horizon_trading_days=10,
                confidence=None,
                thesis="5月8日收盘后生成，5月11日入场。",
                catalysts=[],
                invalidation=[],
                risks=[],
                sources_payload=[],
                novelty_note=None,
                limitations=[],
                convergence_group="frozen",
                research_priority="market_factor_frozen_paper",
                parse_status="parsed",
                is_system_external=False,
                candidate_payload={
                    "tracking_role": "frozen_paper_primary",
                    "paper_tracking_signal_date": "2026-05-08",
                    "paper_tracking_entry_date": "2026-05-11",
                    "market_factor_overlay": {"source_rank": 1},
                },
            )
            session.add(candidate)
            session.flush()
            session.add(
                ShortpickValidationSnapshot(
                    candidate_id=candidate.id,
                    horizon_days=5,
                    status="completed",
                    entry_at=datetime(2026, 5, 11, 7, 0, tzinfo=UTC),
                    exit_at=datetime(2026, 5, 18, 7, 0, tzinfo=UTC),
                    entry_close=100,
                    exit_close=108,
                    stock_return=0.08,
                    benchmark_return=0.01,
                    excess_return=0.07,
                    max_favorable_return=0.09,
                    max_drawdown=-0.01,
                    validation_payload={
                        "paper_tracking_exit_tracks": [
                            {
                                "key": "mechanical_5d",
                                "label": "机械5日",
                                "exit_trade_day": "2026-05-18",
                                "stock_return": 0.08,
                            }
                        ]
                    },
                )
            )
            open_candidate = ShortpickCandidate(
                run_id=seed_run.id,
                candidate_key="shortpick-prefreeze-paper-seed-test:frozen-v2-open",
                symbol="600000.SH",
                name="浦发银行",
                normalized_theme="低换手上升趋势",
                horizon_trading_days=10,
                confidence=None,
                thesis="v2 沿用冻结选股，次日开盘入场。",
                catalysts=[],
                invalidation=[],
                risks=[],
                sources_payload=[],
                novelty_note=None,
                limitations=[],
                convergence_group="frozen-v2",
                research_priority="market_factor_open_entry_low_turnover_uptrend",
                parse_status="parsed",
                is_system_external=False,
                candidate_payload={
                    "tracking_role": SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
                    "paper_tracking_signal_date": "2026-05-08",
                    "paper_tracking_entry_date": "2026-05-11",
                    "paper_tracking_entry_price_source": "next_open",
                    "market_factor_overlay": {"source_rank": 1},
                },
            )
            session.add(open_candidate)
            session.flush()
            session.add(
                ShortpickValidationSnapshot(
                    candidate_id=open_candidate.id,
                    horizon_days=5,
                    status="completed",
                    entry_at=datetime(2026, 5, 11, 1, 30, tzinfo=UTC),
                    exit_at=datetime(2026, 5, 18, 7, 0, tzinfo=UTC),
                    entry_close=100,
                    exit_close=111,
                    stock_return=0.11,
                    benchmark_return=0.01,
                    excess_return=0.10,
                    max_favorable_return=0.12,
                    max_drawdown=-0.01,
                    validation_payload={
                        "paper_tracking_exit_tracks": [
                            {
                                "key": "mechanical_5d",
                                "label": "机械5日",
                                "exit_trade_day": "2026-05-18",
                                "stock_return": 0.11,
                            }
                        ]
                    },
                )
            )

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        response = client.get("/shortpick-lab/paper-tracking")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["latest_run"]["run_date"], "2026-05-11")
        by_symbol = {item["symbol"]: item for item in payload["items"]}
        self.assertEqual(by_symbol["601138.SH"]["signal_date"], "2026-05-08")
        self.assertEqual(by_symbol["601138.SH"]["entry_date"], "2026-05-11")
        self.assertEqual(by_symbol["601138.SH"]["tracking_group"], "frozen_strategy")
        self.assertEqual(by_symbol["601138.SH"]["validation_status"], "completed")
        self.assertEqual(by_symbol["601138.SH"]["paper_tracking_exit_tracks"][0]["key"], "mechanical_5d")
        self.assertEqual(by_symbol["600000.SH"]["tracking_group"], "frozen_strategy_v2")
        self.assertEqual(by_symbol["600000.SH"]["selection_label"], "冻结候选 v2：次日开盘买入")
        self.assertEqual(by_symbol["600000.SH"]["exit_rule"], "与 v1 使用同一组选股和三轨退出；入场价格源为次一交易日开盘。")
        self.assertEqual(payload["summary"]["tracked_signal_count"], 1)
        self.assertEqual(payload["summary"]["frozen_v2_signal_count"], 1)

    def test_paper_tracking_dedupes_repeated_scheduled_runs(self) -> None:
        now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        with session_scope(self.database_url) as session:
            runs = [
                ShortpickExperimentRun(
                    run_key=f"shortpick:2026-05-14:test-duplicate-{index}",
                    run_date=date(2026, 5, 14),
                    prompt_version="test",
                    information_mode=SHORTPICK_INFORMATION_MODE,
                    status="completed",
                    trigger_source="scheduled_cli",
                    triggered_by="scheduled_cli",
                    started_at=now + timedelta(minutes=index),
                    completed_at=now + timedelta(minutes=index + 1),
                    model_config={},
                    summary_payload={"market_factor_overlay": {"frozen_paper_strategy": {"inserted": True, "gate_pass": True}}},
                )
                for index in range(2)
            ]
            session.add_all(runs)
            session.flush()
            for run in runs:
                candidate = ShortpickCandidate(
                    run_id=run.id,
                    candidate_key=f"shortpick-market-factor:{run.id}:frozen_paper_low_turnover_uptrend_v4:1",
                    symbol="600183.SH",
                    name="生益科技",
                    normalized_theme="低换手上升趋势",
                    horizon_trading_days=10,
                    confidence=1.0,
                    thesis="同一交易日重复调度产生的同义冻结纸面策略候选。",
                    catalysts=[],
                    invalidation=[],
                    risks=[],
                    sources_payload=[],
                    novelty_note=None,
                    limitations=[],
                    convergence_group="market_factor",
                    research_priority="market_factor_frozen_paper",
                    parse_status="parsed",
                    is_system_external=False,
                    candidate_payload={
                        "tracking_role": "frozen_paper_primary",
                        "baseline_family": "frozen_paper_low_turnover_uptrend_v4",
                        "market_factor_overlay": {
                            "family": "frozen_paper_low_turnover_uptrend_v4",
                            "source_rank": 1,
                            "entry_price_source": "next_close",
                        },
                    },
                )
                session.add(candidate)
                session.flush()
                session.add(
                    ShortpickValidationSnapshot(
                        candidate_id=candidate.id,
                        horizon_days=5,
                        status="completed",
                        entry_at=datetime(2026, 5, 15, 7, 0, tzinfo=UTC),
                        exit_at=datetime(2026, 5, 22, 7, 0, tzinfo=UTC),
                        entry_close=89.95,
                        exit_close=108.01,
                        stock_return=0.200778,
                        benchmark_return=0.01,
                        excess_return=0.190778,
                        max_favorable_return=0.21,
                        max_drawdown=0.0,
                        validation_payload={
                            "paper_tracking_exit_tracks": [
                                {
                                    "key": "mechanical_5d",
                                    "entry_trade_day": "2026-05-15",
                                    "exit_trade_day": "2026-05-22",
                                }
                            ]
                        },
                    )
                )

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        payload = client.get("/shortpick-lab/paper-tracking").json()
        matching = [
            item
            for item in payload["items"]
            if item["signal_date"] == "2026-05-14"
            and item["symbol"] == "600183.SH"
            and item["tracking_role"] == "frozen_paper_primary"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(payload["summary"]["tracked_signal_count"], 1)

        # Round 29: governance partition is attached additively (non-breaking).
        governance = payload["strategy_governance"]
        self.assertEqual(governance["status"], "ready")
        self.assertEqual(governance["deprecated_status_set"], ["retire_candidate", "retired"])
        # The live ledger path passes no historical after-cost evidence, and the
        # retire_candidate gate requires it, so nothing is deprecated yet by design.
        self.assertEqual(governance["deprecated_count"], 0)
        self.assertEqual(governance["deprecated_strategy_ids"], [])
        for item in payload["items"]:
            self.assertIn("governance_status", item)
            self.assertIn("governance_strategy_id", item)
            self.assertEqual(item["governance_view_section"], "primary")
