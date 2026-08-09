# ruff: noqa: F403,F405
from __future__ import annotations

from tests.shortpick_lab_test_support import *


class ShortpickLabValidationTests(ShortpickLabTestCase):
    def test_validate_recent_includes_pending_paper_windows_outside_latest_limit(self) -> None:
        now = datetime(2026, 5, 26, 8, 0, tzinfo=UTC)

        def add_run(session, run_date: date, index: int, *, pending: bool = False) -> int:
            run = ShortpickExperimentRun(
                run_key=f"shortpick:test:pending-refresh:{index}",
                run_date=run_date,
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="test",
                triggered_by="root",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            candidate = ShortpickCandidate(
                run_id=run.id,
                candidate_key=f"shortpick:test:pending-refresh:{index}:candidate",
                symbol=f"600{index:03d}.SH",
                name=f"测试{index}",
                research_priority="market_factor_frozen_paper",
                parse_status="parsed",
                candidate_payload={"tracking_role": "frozen_paper_primary"},
            )
            session.add(candidate)
            session.flush()
            if pending:
                session.add(
                    ShortpickValidationSnapshot(
                        candidate_id=candidate.id,
                        horizon_days=10,
                        status="pending_forward_window",
                        validation_payload={"required_forward_bars": 10},
                    )
                )
                session.flush()
            return run.id

        with session_scope(self.database_url) as session:
            old_pending_date = date(2026, 5, 8)
            lookback_days = max(30, (datetime.now(UTC).date() - old_pending_date).days + 1)
            old_pending_id = add_run(session, old_pending_date, 8, pending=True)
            add_run(session, date(2026, 5, 20), 20)
            add_run(session, date(2026, 5, 21), 21)
            latest_ids = [
                add_run(session, date(2026, 5, 22), 22),
                add_run(session, date(2026, 5, 25), 25),
            ]

            seen_run_ids: list[int] = []

            def fake_validate(_session, run_id: int, **_kwargs):
                seen_run_ids.append(run_id)
                return {"updated_validation_count": 0, "summary": {"run_id": run_id}}

            with patch("ashare_evidence.shortpick_lab.validate_shortpick_run", side_effect=fake_validate):
                payload = validate_recent_shortpick_runs(session, days=lookback_days, limit=2, horizons=[10])

        self.assertIn(old_pending_id, seen_run_ids)
        self.assertEqual(seen_run_ids[0], old_pending_id)
        self.assertTrue(set(latest_ids).issubset(seen_run_ids))
        self.assertEqual(payload["refreshed_run_count"], 5)

    def test_validate_recent_continues_past_old_no_progress_pending_slice(self) -> None:
        now = datetime(2026, 6, 12, 8, 0, tzinfo=UTC)

        def add_pending_run(session, run_date: date, index: int) -> int:
            run = ShortpickExperimentRun(
                run_key=f"shortpick:test:pending-slice:{index}",
                run_date=run_date,
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="test",
                triggered_by="root",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            candidate = ShortpickCandidate(
                run_id=run.id,
                candidate_key=f"shortpick:test:pending-slice:{index}:candidate",
                symbol=f"600{index:03d}.SH",
                name=f"测试{index}",
                research_priority="market_factor_frozen_paper",
                parse_status="parsed",
                candidate_payload={"tracking_role": "frozen_paper_primary"},
            )
            session.add(candidate)
            session.flush()
            session.add(
                ShortpickValidationSnapshot(
                    candidate_id=candidate.id,
                    horizon_days=10,
                    status="pending_forward_window",
                    validation_payload={"required_forward_bars": 10},
                )
            )
            session.flush()
            return run.id

        def add_latest_run(session, run_date: date, index: int) -> int:
            run = ShortpickExperimentRun(
                run_key=f"shortpick:test:latest-slice:{index}",
                run_date=run_date,
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="test",
                triggered_by="root",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            return run.id

        with session_scope(self.database_url) as session:
            stalled_ids = [
                add_pending_run(session, date(2026, 5, 20), 20),
                add_pending_run(session, date(2026, 5, 21), 21),
            ]
            mature_pending_id = add_pending_run(session, date(2026, 5, 26), 26)
            add_latest_run(session, date(2026, 6, 10), 110)
            add_latest_run(session, date(2026, 6, 11), 111)

            seen_run_ids: list[int] = []

            def fake_validate(inner_session, run_id: int, **_kwargs):
                seen_run_ids.append(run_id)
                completed = 0
                if run_id == mature_pending_id:
                    snapshot = (
                        inner_session.query(ShortpickValidationSnapshot)
                        .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
                        .filter(ShortpickCandidate.run_id == run_id)
                        .one()
                    )
                    snapshot.status = "completed"
                    inner_session.flush()
                    completed = 1
                return {"updated_validation_count": completed, "summary": {"run_id": run_id}}

            with patch("ashare_evidence.shortpick_lab.validate_shortpick_run", side_effect=fake_validate):
                lookback_days = max(30, (datetime.now(UTC).date() - date(2026, 5, 20)).days + 1)
                payload = validate_recent_shortpick_runs(session, days=lookback_days, limit=2, horizons=[10])

        self.assertLess(seen_run_ids.index(stalled_ids[0]), seen_run_ids.index(mature_pending_id))
        self.assertLess(seen_run_ids.index(stalled_ids[1]), seen_run_ids.index(mature_pending_id))
        self.assertIn(mature_pending_id, seen_run_ids)
        self.assertEqual(payload["refreshed_run_count"], 5)

    def test_validate_recent_can_use_existing_market_data_only(self) -> None:
        self._seed_daily_bars()
        fixture_run_date = date(2026, 5, 5)
        lookback_days = max(30, (datetime.now(UTC).date() - fixture_run_date).days + 1)
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")),
        ]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    run_shortpick_experiment(
                        session,
                        run_date=fixture_run_date,
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks") as sync_benchmarks:
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data") as sync_market:
                with session_scope(self.database_url) as session:
                    payload = validate_recent_shortpick_runs(
                        session,
                        days=lookback_days,
                        limit=5,
                        horizons=[1],
                        sync_market_data=False,
                        sync_benchmarks=False,
                    )

        sync_benchmarks.assert_not_called()
        sync_market.assert_not_called()
        self.assertEqual(payload["refreshed_run_count"], 1)
        with session_scope(self.database_url) as session:
            run = session.scalar(select(ShortpickExperimentRun))
            assert run is not None
            self.assertEqual(run.summary_payload["benchmark_sync"]["status"], "existing_market_data_only")

    def test_validation_uses_hs300_excess_return_and_updates_summary(self) -> None:
        self._seed_daily_bars()
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

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

        first_validation = payload["candidates"][0]["validations"][0]
        self.assertEqual(first_validation["status"], "completed")
        self.assertEqual(first_validation["benchmark_symbol"], "000300.SH")
        self.assertEqual(first_validation["benchmark_label"], "沪深300")
        self.assertEqual(first_validation["validation_mode"], "after_close_t_plus_1_close_entry_v1")
        self.assertTrue(first_validation["official_validation"])
        self.assertEqual(first_validation["tradeability_status"], "tradeable")
        self.assertAlmostEqual(first_validation["stock_return"], 104 / 102 - 1)
        self.assertAlmostEqual(first_validation["benchmark_return"], 202 / 201 - 1)
        self.assertAlmostEqual(first_validation["excess_return"], (104 / 102 - 1) - (202 / 201 - 1))
        self.assertIn("000852.SH", first_validation["benchmark_returns"])
        self.assertGreater(payload["summary"]["completed_validation_count"], 0)
        self.assertEqual(payload["summary"]["measured_candidate_count"], 1)
        self.assertEqual(payload["summary"]["official_validation_mode"], "after_close_t_plus_1_close_entry_v1")
        self.assertIn("1", payload["summary"]["validation_by_horizon"])

    def test_validation_persists_multi_benchmark_dimensions(self) -> None:
        self._seed_daily_bars()
        self._seed_semiconductor_peers()
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

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
                    queue = list_shortpick_validation_queue(session, horizon=1, status="completed")
                    feedback = build_shortpick_model_feedback(session)

        first_validation = payload["candidates"][0]["validations"][0]
        dimensions = first_validation["benchmark_dimensions"]
        self.assertEqual(dimensions["hs300"]["status"], "available")
        self.assertEqual(dimensions["csi1000"]["status"], "available")
        self.assertEqual(dimensions["sector_equal_weight"]["status"], "available")
        self.assertAlmostEqual(dimensions["csi1000"]["benchmark_return"], 303 / 301.5 - 1)
        peer_return = ((52 / 51 - 1) + (86 / 82 - 1)) / 2
        self.assertAlmostEqual(dimensions["sector_equal_weight"]["benchmark_return"], peer_return, places=6)
        self.assertAlmostEqual(
            dimensions["sector_equal_weight"]["excess_return"],
            (104 / 102 - 1) - peer_return,
            places=6,
        )
        self.assertIn("benchmark_dimensions", queue["items"][0])
        model = next(item for item in feedback["models"] if item["provider_name"] == "openai")
        horizon_group = next(group for group in model["validation_by_horizon"] if group["group_key"] == "1")
        self.assertIn("sector_equal_weight", horizon_group["benchmark_metrics"])
        self.assertAlmostEqual(
            horizon_group["benchmark_metrics"]["sector_equal_weight"]["mean_excess_return"],
            (104 / 102 - 1) - peer_return,
            places=6,
        )

    def test_validation_marks_sector_benchmark_pending_when_peers_missing(self) -> None:
        self._seed_daily_bars()
        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == "688981.SH"))
            if stock is not None:
                stock.profile_payload = {"industry": "冷门测试行业", "template_key": "rare_test"}
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "冷门测试题材", "https://a.example/news"))]

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

        sector_dimension = payload["candidates"][0]["validations"][0]["benchmark_dimensions"]["sector_equal_weight"]
        self.assertEqual(sector_dimension["status"], "pending_sector_peer_baseline")
        self.assertIn("可用同行样本", sector_dimension["reason"])

    def test_validation_bootstraps_representative_sector_peer_universe(self) -> None:
        self._seed_stock_bars("002384.SZ", "东山精密", [100 + index * 2 for index in range(8)], profile_payload={"industry": "C 制造业"})
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index * 1.5 for index in range(8)])
        executors = [StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("002384.SZ", "东山精密", "算力硬件", "https://a.example/news"))]

        def fake_profile(_session, *, symbol: str, preferred_name: str | None = None):
            return SimpleNamespace(
                name=preferred_name or symbol,
                industry="C 制造业",
                listed_date=date(2020, 1, 1),
                template_key=None,
                source="test",
            )

        def fake_fetch(_session, symbol: str):
            offset = int(symbol[:2]) % 7
            return self._fake_daily_fetch(symbol, [20 + offset + index for index in range(8)])

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with patch("ashare_evidence.shortpick_lab.resolve_stock_profile", side_effect=fake_profile):
                    with patch("ashare_evidence.shortpick_lab._fetch_shortpick_daily_market_data", side_effect=fake_fetch):
                        with session_scope(self.database_url) as session:
                            payload = run_shortpick_experiment(
                                session,
                                run_date=date(2026, 5, 5),
                                rounds_per_model=1,
                                triggered_by="root",
                                executors=executors,
                            )

        dimension = payload["candidates"][0]["validations"][0]["benchmark_dimensions"]["sector_equal_weight"]
        self.assertEqual(dimension["status"], "available")
        self.assertGreaterEqual(dimension["peer_symbol_count"], 10)
        self.assertGreaterEqual(dimension["contributing_peer_symbol_count"], 10)
        self.assertEqual(dimension["peer_universe_target_count"], 10)

    def test_candidate_market_sync_creates_only_stock_and_market_bars(self) -> None:
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index for index in range(8)])
        symbol = "001234.SZ"
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer(symbol, "测试股份", "短投题材", "https://a.example/news"))]
        profile = SimpleNamespace(name="测试股份", industry="测试行业", listed_date=date(2020, 1, 1), template_key=None, source="test")

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab.resolve_stock_profile", return_value=profile):
                with patch("ashare_evidence.shortpick_lab._fetch_shortpick_daily_market_data", return_value=self._fake_daily_fetch(symbol, [10 + index for index in range(8)])):
                    with session_scope(self.database_url) as session:
                        payload = run_shortpick_experiment(
                            session,
                            run_date=date(2026, 5, 5),
                            rounds_per_model=1,
                            triggered_by="root",
                            executors=executors,
                        )

        self.assertEqual(payload["candidates"][0]["validations"][0]["status"], "completed")
        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
            self.assertIsNotNone(stock)
            assert stock is not None
            self.assertEqual(
                session.scalar(select(MarketBar).where(MarketBar.stock_id == stock.id).limit(1)).raw_payload["shortpick_lab_only"],
                True,
            )
            self.assertEqual(session.scalar(select(Recommendation).limit(1)), None)
            self.assertEqual(session.scalar(select(ModelResult).limit(1)), None)
            self.assertEqual(session.scalar(select(WatchlistFollow).where(WatchlistFollow.symbol == symbol)), None)

    def test_validation_pending_forward_window_records_entry(self) -> None:
        self._seed_stock_bars("688981.SH", "中芯国际", [100])
        self._seed_stock_bars("000300.SH", "沪深300", [200])
        self._seed_stock_bars("000852.SH", "中证1000", [300])
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

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

        first_validation = payload["candidates"][0]["validations"][0]
        self.assertEqual(first_validation["status"], "pending_forward_window")
        self.assertIsNone(first_validation["entry_close"])
        self.assertIsNone(first_validation["available_forward_bars"])
        self.assertEqual(first_validation["required_forward_bars"], 1)
        self.assertIn("No completed tradeable entry close after signal day", first_validation["pending_reason"])
        self.assertFalse(first_validation["official_validation"])
        self.assertEqual(first_validation["tradeability_status"], "pending_market_data")

        with session_scope(self.database_url) as session:
            snapshot = session.scalar(select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.horizon_days == 1))
            assert snapshot is not None
            snapshot.validation_payload = {"available_forward_bars": 0, "market_data_sync": {"status": "existing_current"}}
            session.flush()
            queue = list_shortpick_validation_queue(session, horizon=1)

        legacy_item = queue["items"][0]
        self.assertEqual(legacy_item["required_forward_bars"], 1)
        self.assertIn("needs 1 forward trading-day close", legacy_item["pending_reason"])

    def test_validation_uses_next_trade_close_entry_for_holiday_run_date(self) -> None:
        trading_days = [date(2026, 4, 30), date(2026, 5, 6), date(2026, 5, 7)]
        self._seed_stock_bars("688981.SH", "中芯国际", [100, 110, 121], dates=trading_days)
        self._seed_stock_bars("000300.SH", "沪深300", [200, 210, 214.2], dates=trading_days)
        self._seed_stock_bars("000852.SH", "中证1000", [300, 315, 318], dates=trading_days)
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

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

        first_validation = payload["candidates"][0]["validations"][0]
        self.assertEqual(first_validation["status"], "completed")
        self.assertEqual(first_validation["entry_at"].date(), date(2026, 5, 6))
        self.assertEqual(first_validation["exit_at"].date(), date(2026, 5, 7))
        self.assertEqual(first_validation["entry_close"], 110)
        self.assertEqual(first_validation["exit_close"], 121)
        self.assertAlmostEqual(first_validation["stock_return"], 0.1)
        self.assertAlmostEqual(first_validation["benchmark_return"], 0.02)
        self.assertEqual(first_validation["validation_mode"], "after_close_t_plus_1_close_entry_v1")
        self.assertTrue(first_validation["official_validation"])

    def test_validation_excludes_unfillable_one_price_limit_up_entry(self) -> None:
        trading_days = [date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 7)]
        self._seed_stock_bars("001234.SZ", "测试股份", [10, 11, 12], dates=trading_days)
        self._seed_stock_bars("000300.SH", "沪深300", [200, 202, 204], dates=trading_days)
        self._seed_stock_bars("000852.SH", "中证1000", [300, 303, 306], dates=trading_days)
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("001234.SZ", "测试股份", "短投题材", "https://a.example/news"))]

        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == "001234.SZ"))
            assert stock is not None
            entry_bar = session.scalar(
                select(MarketBar).where(
                    MarketBar.stock_id == stock.id,
                    MarketBar.observed_at == datetime(2026, 5, 6, 7, 0, tzinfo=UTC),
                )
            )
            assert entry_bar is not None
            entry_bar.open_price = 11
            entry_bar.high_price = 11
            entry_bar.low_price = 11
            entry_bar.close_price = 11

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

        first_validation = payload["candidates"][0]["validations"][0]
        self.assertEqual(first_validation["status"], "entry_unfillable_limit_up")
        self.assertEqual(first_validation["tradeability_status"], "entry_unfillable_limit_up")
        self.assertFalse(first_validation["official_validation"])
        self.assertIsNone(first_validation["stock_return"])

    def test_suspended_or_no_current_bar_candidate_is_quarantined_from_research_pool(self) -> None:
        self._seed_stock_bars("600958.SH", "东方证券", [9.34], dates=[date(2026, 4, 17)])
        self._seed_stock_bars("000300.SH", "沪深300", [200, 202, 204], dates=[date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300, 303, 306], dates=[date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 8)])
        executors = [StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("600958.SH", "东方证券", "券商重组复牌", "https://a.example/news"))]

        with patch.dict(os.environ, {"SHORTPICK_MARKET_FACTOR_SYNC": "0"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
                with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                    with session_scope(self.database_url) as session:
                        payload = run_shortpick_experiment(
                            session,
                            run_date=date(2026, 5, 6),
                            rounds_per_model=1,
                            triggered_by="root",
                            executors=executors,
                        )

        candidate = payload["candidates"][0]
        statuses = {item["status"] for item in candidate["validations"]}
        self.assertEqual(statuses, {"suspended_or_no_current_bar"})
        self.assertEqual(candidate["display_bucket"], "diagnostic")
        self.assertEqual(candidate["research_priority"], "tradeability_blocked")
        self.assertIn("latest daily bar is 2026-04-17", candidate["diagnostic_reason"])
        self.assertEqual(payload["summary"]["normal_candidate_count"], 0)
        self.assertEqual(payload["summary"]["diagnostic_candidate_count"], 1)
        self.assertEqual(payload["summary"]["candidate_display_gate"]["blocked_symbols"], ["600958.SH"])

    def test_validation_pending_benchmark_when_primary_window_missing(self) -> None:
        self._seed_stock_bars("688981.SH", "中芯国际", [100 + index * 2 for index in range(8)])
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]

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

        statuses = {item["status"] for item in payload["candidates"][0]["validations"]}
        self.assertIn("pending_benchmark_data", statuses)

    def test_validation_queue_filters_candidate_horizon_rows(self) -> None:
        self._seed_daily_bars()
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")),
        ]

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=executors,
                    )
                    payload = list_shortpick_validation_queue(
                        session,
                        horizon=1,
                        status="completed",
                        model="gpt",
                        symbol="688981.SH",
                        limit=50,
                        offset=0,
                    )

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["run_date"], date(2026, 5, 5))
        self.assertEqual(item["symbol"], "688981.SH")
        self.assertEqual(item["provider_name"], "openai")
        self.assertEqual(item["model_name"], "gpt-test")
        self.assertEqual(item["horizon_days"], 1)
        self.assertEqual(item["status"], "completed")
        self.assertIn("excess_return", item)

    def _seed_pending_run(self, session, run_date: date, index: int) -> int:
        now = datetime(2026, 6, 4, 8, 0, tzinfo=UTC)
        run = ShortpickExperimentRun(
            run_key=f"shortpick:test:revalidate-loop:{index}",
            run_date=run_date,
            prompt_version="test",
            information_mode=SHORTPICK_INFORMATION_MODE,
            status="completed",
            trigger_source="test",
            triggered_by="root",
            started_at=now,
            completed_at=now,
            model_config={},
            summary_payload={},
        )
        session.add(run)
        session.flush()
        candidate = ShortpickCandidate(
            run_id=run.id,
            candidate_key=f"shortpick:test:revalidate-loop:{index}:candidate",
            symbol=f"600{index:03d}.SH",
            name=f"测试{index}",
            research_priority="market_factor_frozen_paper",
            parse_status="parsed",
            candidate_payload={"tracking_role": "frozen_paper_primary"},
        )
        session.add(candidate)
        session.flush()
        snapshot = ShortpickValidationSnapshot(
            candidate_id=candidate.id,
            horizon_days=5,
            status="pending_forward_window",
            validation_payload={"required_forward_bars": 5},
        )
        session.add(snapshot)
        session.flush()
        return snapshot.id

    def test_revalidation_loop_completes_pending_when_data_arrives(self) -> None:
        # Once forward-window data is available, the bounded loop must flip a
        # stranded pending_forward_window snapshot to completed.
        with session_scope(self.database_url) as session:
            snapshot_id = self._seed_pending_run(session, date(2026, 5, 26), 26)

            def fake_validate(inner_session, run_id: int, **_kwargs):
                snap = inner_session.get(ShortpickValidationSnapshot, snapshot_id)
                updated = 0
                if snap is not None and snap.status != "completed":
                    snap.status = "completed"
                    inner_session.flush()
                    updated = 1
                return {"updated_validation_count": updated, "summary": {"run_id": run_id}}

            with patch("ashare_evidence.shortpick_lab.validate_shortpick_run", side_effect=fake_validate):
                lookback_days = max(30, (datetime.now(UTC).date() - date(2026, 5, 26)).days + 1)
                payload = validate_recent_shortpick_runs(session, days=lookback_days, limit=20, horizons=[5])

            self.assertGreaterEqual(payload["refreshed_run_count"], 1)
            snap = session.get(ShortpickValidationSnapshot, snapshot_id)
            assert snap is not None
            self.assertEqual(snap.status, "completed")

    def test_revalidation_loop_terminates_when_no_data(self) -> None:
        # A snapshot the source cannot complete must not loop or re-fetch
        # forever: bounded by max_iter and the "no new completed" guard, each
        # run is processed at most once.
        call_count = {"n": 0}
        with session_scope(self.database_url) as session:
            self._seed_pending_run(session, date(2026, 6, 2), 2)
            self._seed_pending_run(session, date(2026, 6, 3), 3)

            def fake_validate(_session, run_id: int, **_kwargs):
                call_count["n"] += 1
                # Never completes anything (no data available).
                return {"updated_validation_count": 0, "summary": {"run_id": run_id}}

            with patch("ashare_evidence.shortpick_lab.validate_shortpick_run", side_effect=fake_validate):
                lookback_days = max(30, (datetime.now(UTC).date() - date(2026, 6, 2)).days + 1)
                payload = validate_recent_shortpick_runs(session, days=lookback_days, limit=20, horizons=[5])

        # Two runs, each processed exactly once (no infinite loop, no re-process).
        self.assertEqual(call_count["n"], 2)
        self.assertEqual(payload["refreshed_run_count"], 2)

    def test_analysis_only_refresh_syncs_benchmark_bars(self) -> None:
        # The daily refresh runs --analysis-only; benchmarks must still sync so
        # validation excess-return is not stranded at pending_benchmark_data.
        from ashare_evidence.cli import _refresh_runtime_data_output

        with patch("ashare_evidence.cli.sync_benchmark_index_bars", return_value={"status": "ok"}) as sync_bench:
            with patch("ashare_evidence.cli.active_watchlist_symbols", return_value=[]):
                with session_scope(self.database_url) as session:
                    _refresh_runtime_data_output(
                        session,
                        analysis_only=True,
                        ops_only=False,
                        skip_simulation=True,
                    )
        sync_bench.assert_called_once()
