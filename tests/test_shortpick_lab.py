# ruff: noqa: F403,F405
from __future__ import annotations

from tests.shortpick_lab_test_support import *


class ShortpickLabTests(ShortpickLabTestCase):
    def test_run_builds_consensus_and_validation_without_polluting_main_pools(self) -> None:
        self._seed_daily_bars()
        executors = [
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("600519.SH", "贵州茅台", "消费龙头修复", "https://a.example/news")),
            StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("600519.SH", "贵州茅台", "消费龙头修复", "https://b.example/news")),
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

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["summary"]["completed_round_count"], 2)
        self.assertEqual(payload["consensus"]["research_priority"], "cross_model_same_symbol")
        self.assertEqual(payload["consensus"]["summary"]["leader_symbols"], ["600519.SH"])
        self.assertEqual(payload["consensus"]["summary"]["cross_model_symbols"], ["600519.SH"])
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertTrue(all(item["research_priority"] == "cross_model_same_symbol" for item in payload["candidates"]))
        self.assertEqual(payload["summary"]["llm_paper_control"]["status"], "selected")
        self.assertEqual(payload["summary"]["llm_paper_control"]["symbol"], "600519.SH")
        self.assertEqual(
            sum(1 for item in payload["candidates"] if item.get("tracking_role") == "llm_paper_control_primary"),
            1,
        )
        self.assertTrue(any(v["status"] == "completed" for v in payload["candidates"][0]["validations"]))

        with session_scope(self.database_url) as session:
            self.assertEqual(session.scalar(select(WatchlistFollow).where(WatchlistFollow.symbol == "600519.SH")), None)
            self.assertEqual(session.scalar(select(Recommendation).limit(1)), None)

    def test_validate_recent_shortpick_runs_refreshes_completed_runs(self) -> None:
        self._seed_daily_bars()
        fixture_run_date = date(2026, 5, 5)
        lookback_days = max(10, (datetime.now(UTC).date() - fixture_run_date).days + 1)
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
                    payload = validate_recent_shortpick_runs(session, days=lookback_days, limit=5, horizons=[1])

        self.assertEqual(payload["refreshed_run_count"], 1)
        self.assertEqual(payload["runs"][0]["updated_validation_count"], 1)
        self.assertEqual(payload["runs"][0]["summary"]["completed_validation_count"], 3)

    def test_parse_failure_keeps_research_lab_artifact_and_candidate_boundary(self) -> None:
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", "not-json")]

        with session_scope(self.database_url) as session:
            payload = run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=executors,
            )
            candidate = session.scalar(select(ShortpickCandidate))

        self.assertEqual(payload["status"], "failed")
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.parse_status, "parse_failed")
        self.assertEqual(candidate.symbol, "PARSE_FAILED")

    def test_sources_are_credibility_marked(self) -> None:
        executors = [
            StaticShortpickExecutor(
                "deepseek",
                "deepseek-test",
                "fake",
                _answer("688981.SH", "中芯国际", "半导体国产替代", "https://finance.eastmoney.com/a/2026050523456789.html"),
            )
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

        source = payload["rounds"][0]["sources"][0]
        self.assertEqual(source["credibility_status"], "suspicious")
        self.assertIn("placeholder-like", source["credibility_reason"])

    def test_openai_compatible_shortpick_executor_is_blocked_for_shortpick_web_search(self) -> None:
        self._check_openai_compatible_shortpick_executor_is_blocked_for_shortpick_web_search()

    def test_deepseek_executor_uses_lobechat_searxng_search_results(self) -> None:
        self._check_deepseek_executor_uses_lobechat_searxng_search_results()

    def test_deepseek_executor_fails_closed_when_search_results_stay_insufficient(self) -> None:
        self._check_deepseek_executor_fails_closed_when_search_results_stay_insufficient()

    def test_search_fallback_chain_uses_public_fallback_when_searxng_is_empty(self) -> None:
        self._check_search_fallback_chain_uses_public_fallback_when_searxng_is_empty()

    def test_sogou_search_result_parser_extracts_real_results(self) -> None:
        self._check_sogou_search_result_parser_extracts_real_results()

    def test_deepseek_executor_rejects_final_sources_outside_search_results(self) -> None:
        self._check_deepseek_executor_rejects_final_sources_outside_search_results()

    def test_default_deepseek_executor_uses_lobechat_search_not_official_native_api(self) -> None:
        self._check_default_deepseek_executor_uses_lobechat_search_not_official_native_api()

    def test_run_is_committed_before_long_executor_work(self) -> None:
        observed_counts: list[int] = []

        class InspectingExecutor:
            provider_name = "openai"
            model_name = "gpt-test"
            executor_kind = "fake"

            def complete(self, prompt: str) -> str:
                with session_scope(self_database_url) as other_session:
                    observed_counts.append(other_session.query(ShortpickExperimentRun).count())
                return _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")

        self_database_url = self.database_url
        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                with session_scope(self.database_url) as session:
                    run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 5),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=[InspectingExecutor()],
                    )

        self.assertEqual(observed_counts, [1])

    def test_intraday_same_day_control_inserts_same_day_candidate(self) -> None:
        trading_days = [date(2026, 4, 14) + timedelta(days=index) for index in range(20)]
        self._seed_stock_bars(
            "600001.SH",
            "测试主板",
            [10.0 + index * 0.1 for index in range(20)],
            dates=trading_days,
            profile_payload={"industry": "测试行业"},
        )
        full_snapshot = {
            "status": "ok",
            "generated_at": "2026-05-12T05:55:00+00:00",
            "source_kind": "test_spot",
            "quotes": {
                "600001.SH": {
                    "symbol": "600001.SH",
                    "name": "测试主板",
                    "price": 12.20,
                    "open": 12.00,
                    "high": 12.30,
                    "low": 11.90,
                    "amount": 200000000.0,
                    "volume": 1000000.0,
                    "turnover_rate": 1.2,
                    "captured_at": "2026-05-12T05:55:00+00:00",
                }
            },
            "summary": {"status": "ok", "quote_count": 1},
        }
        entry_snapshot = {
            **full_snapshot,
            "generated_at": "2026-05-12T05:56:00+00:00",
            "quotes": {
                "600001.SH": {
                    **full_snapshot["quotes"]["600001.SH"],
                    "price": 12.25,
                    "captured_at": "2026-05-12T05:56:00+00:00",
                }
            },
        }

        with patch("ashare_evidence.shortpick_lab._fetch_shortpick_intraday_spot_quotes", side_effect=[full_snapshot, entry_snapshot]):
            with session_scope(self.database_url) as session:
                payload = run_shortpick_intraday_same_day_control(session, run_date=date(2026, 5, 12), triggered_by="test")

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["summary"]["market_factor_overlay"]["inserted_candidate_count"], 1)
        quote_artifact = payload["summary"]["market_factor_overlay"]["quote_snapshot_artifact"]
        self.assertEqual(quote_artifact["quote_count"], 1)
        quote_payload = json.loads(Path(quote_artifact["artifact_path"]).read_text(encoding="utf-8"))
        self.assertEqual(quote_payload["quotes"]["600001.SH"]["price"], 12.2)
        self.assertIn("不能用日线 proxy 回填成真实14:00成交", quote_payload["note"])
        self.assertEqual(payload["candidates"][0]["tracking_role"], SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE)
        self.assertEqual(payload["candidates"][0]["baseline_family"], SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY)
        with session_scope(self.database_url) as session:
            candidate = session.scalar(select(ShortpickCandidate).where(ShortpickCandidate.run_id == payload["id"]))
            self.assertIsNotNone(candidate)
            candidate_payload = candidate.candidate_payload
        self.assertEqual(candidate_payload["paper_tracking_entry_date"], "2026-05-12")
        self.assertEqual(candidate_payload["paper_tracking_entry_price"], 12.25)

    def test_intraday_same_day_control_skips_limit_up_entry_candidate(self) -> None:
        self._check_intraday_same_day_control_skips_limit_up_entry_candidate()

    def test_intraday_same_day_control_fails_when_quote_source_unavailable(self) -> None:
        trading_days = [date(2026, 4, 14) + timedelta(days=index) for index in range(20)]
        self._seed_stock_bars(
            "600001.SH",
            "测试主板",
            [10.0 + index * 0.1 for index in range(20)],
            dates=trading_days,
            profile_payload={"industry": "测试行业"},
        )
        quote_error = {
            "status": "error",
            "generated_at": "2026-05-12T05:55:00+00:00",
            "source_kind": "test_spot",
            "quotes": {},
            "summary": {"status": "error", "reason": "spot quote unavailable"},
        }

        with patch("ashare_evidence.shortpick_lab._fetch_shortpick_intraday_spot_quotes", return_value=quote_error):
            with session_scope(self.database_url) as session:
                payload = run_shortpick_intraday_same_day_control(session, run_date=date(2026, 5, 12), triggered_by="test")

        self.assertEqual(payload["status"], "failed")
        self.assertIn("intraday_quote_unavailable", payload["summary"]["error"])
        with session_scope(self.database_url) as session:
            candidate_count = session.query(ShortpickCandidate).filter_by(run_id=payload["id"]).count()
        self.assertEqual(candidate_count, 0)

    def test_no_limit_chase_control_filters_limit_up_chase_risk(self) -> None:
        self.assertTrue(_is_shortpick_no_limit_chase_risk({"return_1d": 0.095}))
        self.assertTrue(_is_shortpick_no_limit_chase_risk({"return_1d": 0.1002838}))
        self.assertFalse(_is_shortpick_no_limit_chase_risk({"return_1d": 0.0949}))
        self.assertFalse(_is_shortpick_no_limit_chase_risk({"return_1d": None}))

    def test_open_entry_paper_control_uses_open_price_for_exit_tracks(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-market-factor:1:open-entry:1",
            symbol="000001.SZ",
            name="测试银行",
            research_priority="market_factor_default",
            candidate_payload={
                "tracking_role": SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
                "paper_tracking_entry_price_source": "next_open",
            },
        )
        start = datetime(2026, 5, 6, 7, 0, tzinfo=UTC)
        bars = [
            MarketBar(
                bar_key=f"open-entry-{index}",
                stock_id=1,
                timeframe="1d",
                observed_at=start + timedelta(days=index),
                open_price=100 + index,
                high_price=112 + index,
                low_price=99 + index,
                close_price=110 + index,
                volume=1000,
                amount=(110 + index) * 1000,
                raw_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://open-entry/{index}",
                lineage_hash=compute_lineage_hash({"open_entry_index": index}),
            )
            for index in range(11)
        ]

        tracks = _shortpick_frozen_exit_track_results(
            candidate=candidate,
            window=bars,
            benchmark_maps={},
        )

        mechanical_5d = next(item for item in tracks if item["key"] == "mechanical_5d")
        self.assertEqual(mechanical_5d["entry_price_source"], "next_open")
        self.assertEqual(mechanical_5d["entry_price"], 100)
        self.assertEqual(mechanical_5d["entry_close"], 110)
        self.assertAlmostEqual(mechanical_5d["stock_return"], 115 / 100 - 1)

    def test_open_entry_tradeability_blocks_limit_up_open(self) -> None:
        candidate = ShortpickCandidate(
            run_id=1,
            candidate_key="shortpick-market-factor:1:open-entry-limit-up:1",
            symbol="001234.SZ",
            name="测试股份",
            research_priority="market_factor_default",
            candidate_payload={
                "tracking_role": SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
                "paper_tracking_entry_price_source": "next_open",
            },
        )
        previous = MarketBar(
            bar_key="previous",
            stock_id=1,
            timeframe="1d",
            observed_at=datetime(2026, 5, 5, 7, 0, tzinfo=UTC),
            open_price=9.8,
            high_price=10.2,
            low_price=9.7,
            close_price=10,
            volume=1000,
            amount=10000,
            raw_payload={},
            license_tag="test",
            usage_scope="internal-test",
            redistribution_scope="none",
            source_uri="test://previous",
            lineage_hash=compute_lineage_hash({"bar": "previous"}),
        )
        entry = MarketBar(
            bar_key="entry",
            stock_id=1,
            timeframe="1d",
            observed_at=datetime(2026, 5, 6, 7, 0, tzinfo=UTC),
            open_price=11,
            high_price=11,
            low_price=10.5,
            close_price=10.8,
            volume=1000,
            amount=10800,
            raw_payload={},
            license_tag="test",
            usage_scope="internal-test",
            redistribution_scope="none",
            source_uri="test://entry",
            lineage_hash=compute_lineage_hash({"bar": "entry"}),
        )

        evidence = _shortpick_entry_tradeability(candidate=candidate, bars=[previous, entry], entry_index=1)

        self.assertEqual(evidence["tradeability_status"], "entry_unfillable_limit_up")
        self.assertEqual(evidence["entry_price_source"], "next_open")
        self.assertEqual(evidence["entry_price"], 11)
        self.assertAlmostEqual(evidence["entry_open_return"], 0.1)

    def test_api_redacts_raw_output_for_member_and_blocks_mutation(self) -> None:
        executors = [StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"))]
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

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        member_headers = {"X-HZ-User-Login": "member-a", "X-HZ-User-Role": "member"}
        list_response = client.get("/shortpick-lab/runs", headers=member_headers)
        self.assertEqual(list_response.status_code, 200)
        first_round = list_response.json()["items"][0]["rounds"][0]
        self.assertIsNone(first_round["raw_answer"])

        create_response = client.post(
            "/shortpick-lab/runs",
            headers=member_headers,
            json={"rounds_per_model": 1},
        )
        self.assertEqual(create_response.status_code, 403)
        self.assertIn("root role required", create_response.json()["detail"])

    def test_scheduled_shortpick_run_reuses_completed_same_day_run(self) -> None:
        now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        with session_scope(self.database_url) as session:
            existing = ShortpickExperimentRun(
                run_key="shortpick:2026-05-14:already-completed",
                run_date=date(2026, 5, 14),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="scheduled_cli",
                triggered_by="scheduled_cli",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={"completed_round_count": 1},
            )
            session.add(existing)
            session.flush()
            payload = run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 14),
                rounds_per_model=1,
                triggered_by="scheduled_cli",
                trigger_source="scheduled_cli",
                executors=[StaticShortpickExecutor("openai", "gpt-test", "fake", "not-json")],
            )
            runs = session.scalars(select(ShortpickExperimentRun)).all()

        self.assertEqual(payload["id"], existing.id)
        self.assertEqual(len(runs), 1)

    def test_run_list_supports_pagination_filters_and_retryable_summary(self) -> None:
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
                    run_shortpick_experiment(
                        session,
                        run_date=date(2026, 5, 6),
                        rounds_per_model=1,
                        triggered_by="root",
                        executors=[StaticShortpickExecutor("openai", "gpt-test", "fake", "not-json")],
                    )
                    payload = list_shortpick_runs(
                        session,
                        status="completed",
                        date_from=date(2026, 5, 5),
                        date_to=date(2026, 5, 5),
                        limit=1,
                        offset=0,
                        include_raw=True,
                    )

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["offset"], 0)
        self.assertEqual(payload["items"][0]["run_date"], date(2026, 5, 5))
        self.assertIn("validation_completion_rate", payload["items"][0]["summary"])

    def test_run_list_hides_running_runs_by_default(self) -> None:
        now = datetime(2026, 6, 3, 3, 0, tzinfo=UTC)
        with session_scope(self.database_url) as session:
            completed = ShortpickExperimentRun(
                run_key="shortpick:2026-06-02:completed",
                run_date=date(2026, 6, 2),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="scheduled_cli",
                triggered_by="scheduled_cli",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={},
            )
            running = ShortpickExperimentRun(
                run_key="shortpick:2026-06-03:running",
                run_date=date(2026, 6, 3),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="running",
                trigger_source="scheduled_cli",
                triggered_by="scheduled_cli",
                started_at=now,
                model_config={},
                summary_payload={},
            )
            session.add_all([completed, running])
            session.flush()

            payload = list_shortpick_runs(session, information_mode=SHORTPICK_INFORMATION_MODE, limit=10)
            running_payload = list_shortpick_runs(
                session,
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="running",
                limit=10,
            )

        self.assertEqual([item["id"] for item in payload["items"]], [completed.id])
        self.assertEqual([item["id"] for item in running_payload["items"]], [running.id])

    def test_run_list_without_candidates_uses_lightweight_summary(self) -> None:
        now = datetime(2026, 6, 2, 8, 30, tzinfo=UTC)
        with session_scope(self.database_url) as session:
            run = ShortpickExperimentRun(
                run_key="shortpick:2026-06-02:lightweight",
                run_date=date(2026, 6, 2),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="scheduled_cli",
                triggered_by="scheduled_cli",
                started_at=now,
                completed_at=now,
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            round_record = ShortpickModelRound(
                run_id=run.id,
                round_key="shortpick-round:2026-06-02:lightweight",
                provider_name="openai",
                model_name="gpt-test",
                executor_kind="fake",
                round_index=1,
                status="completed",
                raw_answer="large raw answer must not be required by list mode",
                parsed_payload={"primary_pick": {"symbol": "688981.SH", "name": "中芯国际"}},
                sources_payload=[],
                started_at=now,
                completed_at=now,
            )
            session.add(round_record)
            session.flush()
            candidate = ShortpickCandidate(
                run_id=run.id,
                round_id=round_record.id,
                candidate_key="shortpick-candidate:lightweight",
                symbol="688981.SH",
                name="中芯国际",
                normalized_theme="半导体",
                confidence=0.7,
                thesis="large candidate text must not be required by list mode",
                catalysts=[],
                invalidation=[],
                risks=[],
                sources_payload=[],
                limitations=[],
                research_priority="cross_model_same_symbol",
                parse_status="parsed",
                is_system_external=False,
                candidate_payload={"large": "x" * 1024},
            )
            session.add(candidate)
            session.flush()
            session.add(
                ShortpickValidationSnapshot(
                    candidate_id=candidate.id,
                    horizon_days=1,
                    status="completed",
                    validation_payload={
                        "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
                        "official_validation": True,
                        "tradeability_status": SHORTPICK_OFFICIAL_TRADEABILITY_STATUS,
                    },
                )
            )
            session.flush()

            with patch(
                "ashare_evidence.shortpick_lab._run_operational_summary",
                side_effect=AssertionError("heavy summary must not be used for run lists"),
            ):
                payload = list_shortpick_runs(
                    session,
                    information_mode=SHORTPICK_INFORMATION_MODE,
                    limit=10,
                    include_candidates=False,
                    compact_summary=True,
                )

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["candidates"], [])
        self.assertEqual(item["summary"]["parsed_candidate_count"], 1)
        self.assertEqual(item["summary"]["normal_candidate_count"], 1)
        self.assertEqual(item["summary"]["validation_total_count"], 1)
        self.assertEqual(item["summary"]["official_validation_completed_count"], 1)

    def test_retry_failed_rounds_replaces_only_retryable_rounds_and_keeps_failure_history(self) -> None:
        self._seed_daily_bars()
        failing_executor = StaticShortpickExecutor("openai", "gpt-test", "fake", "not-json")
        retry_executor = StaticShortpickExecutor(
            "openai",
            "gpt-test",
            "fake",
            _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news"),
        )

        with session_scope(self.database_url) as session:
            failed_payload = run_shortpick_experiment(
                session,
                run_date=date(2026, 5, 5),
                rounds_per_model=1,
                triggered_by="root",
                executors=[failing_executor],
            )
            run_id = failed_payload["id"]

        with patch("ashare_evidence.shortpick_lab.default_shortpick_executors", return_value=[retry_executor]):
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks", return_value={"status": "skipped"}):
                with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data", return_value={"status": "skipped"}):
                    with patch("ashare_evidence.shortpick_lab._source_credibility", return_value={"credibility_status": "verified", "credibility_reason": "test"}):
                        with session_scope(self.database_url) as session:
                            payload = retry_failed_shortpick_rounds(session, run_id)

        self.assertEqual(payload["retried_round_count"], 1)
        self.assertEqual(payload["run"]["status"], "completed")
        self.assertEqual(payload["run"]["summary"]["failed_round_count"], 0)
        self.assertEqual(payload["run"]["summary"]["normal_candidate_count"], 1)
        self.assertEqual(payload["run"]["summary"]["failed_candidate_count"], 0)
        self.assertFalse(any(item["parse_status"] == "parse_failed" for item in payload["run"]["candidates"]))
        self.assertEqual(payload["retried"][0]["failure_category"], "retryable_parse_failure")
        retry_history = payload["run"]["rounds"][0]["retry_history"]
        self.assertEqual(retry_history[0]["failure_category"], "retryable_parse_failure")
        self.assertIn("shortpick-round:", retry_history[0]["artifact_id"])
