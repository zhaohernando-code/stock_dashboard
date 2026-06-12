# ruff: noqa: F403,F405
from __future__ import annotations

from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    write_shortpick_control_inventory_archive_artifact_record,
    write_shortpick_strategy_retirement_artifact_record,
)
from tests.shortpick_lab_test_support import *


class ShortpickLabTests(ShortpickLabTestCase):
    def test_market_factor_overlay_inserts_p3_true_forward_filter_reselect_controls(self) -> None:
        now = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)
        contexts = [
            {
                "symbol": "600001.SH",
                "name": "测试一",
                "industry": "测试行业",
                "latest_trade_day": "2026-06-11",
                "close": 10.0,
                "amount": 1_000_000_000.0,
                "turnover_rate": 0.10,
                "return_1d": 0.01,
                "return_5d": 0.05,
                "return_10d": 0.10,
                "return_20d": 0.30,
                "abs_return_1d": 0.01,
                "recent_drawdown_return": -0.12,
                "short_window_return": -0.04,
                "price_vs_ma20": -0.02,
                "high_level_reversal_return": -0.12,
                "golden_cross_10_200": False,
                "ma10": 11.0,
                "ma200": 10.0,
                "previous_ma10": 9.5,
                "previous_ma200": 10.0,
            },
            {
                "symbol": "600002.SH",
                "name": "测试二",
                "industry": "测试行业",
                "latest_trade_day": "2026-06-11",
                "close": 20.0,
                "amount": 900_000_000.0,
                "turnover_rate": 0.12,
                "return_1d": 0.01,
                "return_5d": 0.04,
                "return_10d": 0.09,
                "return_20d": 0.25,
                "abs_return_1d": 0.01,
                "recent_drawdown_return": -0.01,
                "short_window_return": 0.02,
                "price_vs_ma20": 0.03,
                "high_level_reversal_return": -0.01,
                "golden_cross_10_200": False,
                "ma10": 21.0,
                "ma200": 18.0,
                "previous_ma10": 20.5,
                "previous_ma200": 18.0,
            },
            {
                "symbol": "600003.SH",
                "name": "测试三",
                "industry": "测试行业",
                "latest_trade_day": "2026-06-11",
                "close": 30.0,
                "amount": 800_000_000.0,
                "turnover_rate": 0.14,
                "return_1d": 0.01,
                "return_5d": 0.03,
                "return_10d": 0.08,
                "return_20d": 0.20,
                "abs_return_1d": 0.01,
                "recent_drawdown_return": -0.01,
                "short_window_return": 0.01,
                "price_vs_ma20": 0.02,
                "high_level_reversal_return": -0.01,
                "golden_cross_10_200": False,
                "ma10": 31.0,
                "ma200": 28.0,
                "previous_ma10": 30.5,
                "previous_ma200": 28.0,
            },
        ]
        with session_scope(self.database_url) as session:
            for item in contexts:
                ticker, _, exchange = item["symbol"].partition(".")
                session.add(
                    Stock(
                        symbol=item["symbol"],
                        ticker=ticker,
                        exchange=exchange,
                        name=item["name"],
                        provider_symbol=item["symbol"],
                        listed_date=date(2020, 1, 1),
                        status="active",
                        profile_payload={"industry": item["industry"]},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://stock/{item['symbol']}",
                        lineage_hash=compute_lineage_hash({"symbol": item["symbol"]}),
                    )
                )
            run = ShortpickExperimentRun(
                run_key="shortpick:2026-06-11:p3-true-forward-controls",
                run_date=date(2026, 6, 11),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="running",
                trigger_source="scheduled_cli",
                triggered_by="test",
                started_at=now,
                completed_at=None,
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            run_id = run.id

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_market_factor_universe", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._shortpick_market_factor_contexts", return_value=(contexts, {})):
                with session_scope(self.database_url) as session:
                    run = session.get(ShortpickExperimentRun, run_id)
                    assert run is not None
                    overlay = insert_shortpick_market_factor_overlay_candidates(session, run)
                    candidates = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()

        p3_summary = overlay["p3_true_forward_controls"]
        self.assertEqual(p3_summary["status"], "ready")
        self.assertEqual(p3_summary["evidence_basis"], SHORTPICK_P3_CONTROL_EVIDENCE_BASIS)
        self.assertEqual(p3_summary["selection_policy"], SHORTPICK_P3_CONTROL_SELECTION_POLICY)
        self.assertEqual(p3_summary["inserted_candidate_count"], 3)

        by_role = {item["tracking_role"]: item for item in overlay["candidates"]}
        self.assertEqual(overlay["current_generation_scope"]["decision_policy"], "current_paper_tracking_generation_role_allowlist")
        self.assertGreaterEqual(overlay["current_generation_scope"]["excluded_count"], 1)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE, by_role)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE, by_role)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE, by_role)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE, by_role)
        self.assertIn(SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE, by_role)
        self.assertEqual(by_role[SHORTPICK_MARKET_FACTOR_SAME_SYMBOL_COOLDOWN_LOW_TURNOVER_CONTROL_ROLE]["symbol"], "600001.SH")
        self.assertEqual(by_role[SHORTPICK_MARKET_FACTOR_REPEATED_EXPOSURE_LOW_TURNOVER_CONTROL_ROLE]["symbol"], "600001.SH")
        drawdown_summary = by_role[SHORTPICK_MARKET_FACTOR_DRAWDOWN_REVERSAL_LOW_TURNOVER_CONTROL_ROLE]
        self.assertEqual(drawdown_summary["symbol"], "600002.SH")
        self.assertEqual(drawdown_summary["source_rank"], 2)
        self.assertEqual(drawdown_summary["blocked_higher_ranked_count"], 1)

        payload_by_role = {candidate.candidate_payload["tracking_role"]: candidate.candidate_payload for candidate in candidates}
        drawdown_payload = payload_by_role[SHORTPICK_MARKET_FACTOR_DRAWDOWN_REVERSAL_LOW_TURNOVER_CONTROL_ROLE]
        self.assertEqual(drawdown_payload["paper_tracking_evidence_basis"], SHORTPICK_P3_CONTROL_EVIDENCE_BASIS)
        self.assertEqual(drawdown_payload["p3_control"]["selected_source_rank"], 2)
        self.assertEqual(drawdown_payload["p3_control"]["blocked_higher_ranked_candidates"][0]["symbol"], "600001.SH")
        self.assertEqual(drawdown_payload["market_factor_overlay"]["p3_control"]["selection_policy"], SHORTPICK_P3_CONTROL_SELECTION_POLICY)

    def test_p3_true_forward_controls_use_same_control_post_rule_state_only(self) -> None:
        contexts = [
            {
                "symbol": "600001.SH",
                "name": "测试一",
                "industry": "测试行业",
                "latest_trade_day": "2026-06-12",
                "close": 10.0,
                "amount": 1_000_000_000.0,
                "turnover_rate": 0.10,
                "return_1d": 0.01,
                "return_5d": 0.05,
                "return_10d": 0.10,
                "return_20d": 0.30,
                "abs_return_1d": 0.01,
                "recent_drawdown_return": -0.01,
                "short_window_return": 0.02,
                "price_vs_ma20": 0.03,
                "high_level_reversal_return": -0.01,
                "golden_cross_10_200": False,
                "ma10": 11.0,
                "ma200": 10.0,
                "previous_ma10": 9.5,
                "previous_ma200": 10.0,
            },
            {
                "symbol": "600002.SH",
                "name": "测试二",
                "industry": "测试行业",
                "latest_trade_day": "2026-06-12",
                "close": 20.0,
                "amount": 900_000_000.0,
                "turnover_rate": 0.12,
                "return_1d": 0.01,
                "return_5d": 0.04,
                "return_10d": 0.09,
                "return_20d": 0.25,
                "abs_return_1d": 0.01,
                "recent_drawdown_return": -0.01,
                "short_window_return": 0.02,
                "price_vs_ma20": 0.03,
                "high_level_reversal_return": -0.01,
                "golden_cross_10_200": False,
                "ma10": 21.0,
                "ma200": 18.0,
                "previous_ma10": 20.5,
                "previous_ma200": 18.0,
            },
        ]

        def add_prior_candidate(
            session: Session,
            *,
            run: ShortpickExperimentRun,
            role: str,
            key_suffix: str,
            with_loss: bool = False,
        ) -> ShortpickCandidate:
            candidate = ShortpickCandidate(
                run_id=run.id,
                round_id=None,
                candidate_key=f"fixture:{run.run_date}:{role}:{key_suffix}",
                symbol="600001.SH",
                name="测试一",
                normalized_theme="策略候选：fixture",
                horizon_trading_days=10,
                confidence=1.0,
                thesis="fixture",
                catalysts=[],
                invalidation=[],
                risks=[],
                sources_payload=[],
                novelty_note=None,
                limitations=[],
                convergence_group="market_factor",
                research_priority="fixture",
                parse_status="parsed",
                is_system_external=False,
                candidate_payload={
                    "tracking_role": role,
                    "market_factor_overlay": {"tracking_role": role, "source_rank": 1},
                },
            )
            session.add(candidate)
            session.flush()
            if with_loss:
                session.add(
                    ShortpickValidationSnapshot(
                        candidate_id=candidate.id,
                        horizon_days=10,
                        status="completed",
                        entry_at=datetime(2026, 6, 10, 7, 0, tzinfo=UTC),
                        exit_at=datetime(2026, 6, 11, 7, 0, tzinfo=UTC),
                        entry_close=10.0,
                        exit_close=9.5,
                        stock_return=-0.05,
                        benchmark_return=0.0,
                        excess_return=-0.05,
                        validation_payload={},
                    )
                )
            return candidate

        with session_scope(self.database_url) as session:
            for item in contexts:
                ticker, _, exchange = item["symbol"].partition(".")
                session.add(
                    Stock(
                        symbol=item["symbol"],
                        ticker=ticker,
                        exchange=exchange,
                        name=item["name"],
                        provider_symbol=item["symbol"],
                        listed_date=date(2020, 1, 1),
                        status="active",
                        profile_payload={"industry": item["industry"]},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://stock/{item['symbol']}",
                        lineage_hash=compute_lineage_hash({"symbol": item["symbol"]}),
                    )
                )
            pre_rule_run = ShortpickExperimentRun(
                run_key="shortpick:2026-06-09:p3-state-pre-rule",
                run_date=date(2026, 6, 9),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="fixture",
                triggered_by="test",
                started_at=datetime(2026, 6, 9, 7, 0, tzinfo=UTC),
                completed_at=datetime(2026, 6, 9, 7, 5, tzinfo=UTC),
                model_config={},
                summary_payload={},
            )
            cooldown_run = ShortpickExperimentRun(
                run_key="shortpick:2026-06-10:p3-state-cooldown",
                run_date=date(2026, 6, 10),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="fixture",
                triggered_by="test",
                started_at=datetime(2026, 6, 10, 7, 0, tzinfo=UTC),
                completed_at=datetime(2026, 6, 10, 7, 5, tzinfo=UTC),
                model_config={},
                summary_payload={},
            )
            exposure_run = ShortpickExperimentRun(
                run_key="shortpick:2026-06-11:p3-state-exposure",
                run_date=date(2026, 6, 11),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="fixture",
                triggered_by="test",
                started_at=datetime(2026, 6, 11, 7, 0, tzinfo=UTC),
                completed_at=datetime(2026, 6, 11, 7, 5, tzinfo=UTC),
                model_config={},
                summary_payload={},
            )
            current_run = ShortpickExperimentRun(
                run_key="shortpick:2026-06-12:p3-state-current",
                run_date=date(2026, 6, 12),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="running",
                trigger_source="scheduled_cli",
                triggered_by="test",
                started_at=datetime(2026, 6, 12, 7, 0, tzinfo=UTC),
                completed_at=None,
                model_config={},
                summary_payload={},
            )
            session.add_all([pre_rule_run, cooldown_run, exposure_run, current_run])
            session.flush()
            add_prior_candidate(
                session,
                run=pre_rule_run,
                role=SHORTPICK_MARKET_FACTOR_SAME_SYMBOL_COOLDOWN_LOW_TURNOVER_CONTROL_ROLE,
                key_suffix="ignored-pre-rule-loss",
                with_loss=True,
            )
            add_prior_candidate(
                session,
                run=cooldown_run,
                role=SHORTPICK_MARKET_FACTOR_SAME_SYMBOL_COOLDOWN_LOW_TURNOVER_CONTROL_ROLE,
                key_suffix="post-rule-loss",
                with_loss=True,
            )
            add_prior_candidate(
                session,
                run=cooldown_run,
                role=SHORTPICK_MARKET_FACTOR_REPEATED_EXPOSURE_LOW_TURNOVER_CONTROL_ROLE,
                key_suffix="exposure-1",
            )
            add_prior_candidate(
                session,
                run=exposure_run,
                role=SHORTPICK_MARKET_FACTOR_REPEATED_EXPOSURE_LOW_TURNOVER_CONTROL_ROLE,
                key_suffix="exposure-2",
            )
            current_run_id = current_run.id

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_market_factor_universe", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._shortpick_market_factor_contexts", return_value=(contexts, {})):
                with session_scope(self.database_url) as session:
                    run = session.get(ShortpickExperimentRun, current_run_id)
                    assert run is not None
                    overlay = insert_shortpick_market_factor_overlay_candidates(session, run)

        by_role = {item["tracking_role"]: item for item in overlay["candidates"]}
        cooldown_summary = by_role[SHORTPICK_MARKET_FACTOR_SAME_SYMBOL_COOLDOWN_LOW_TURNOVER_CONTROL_ROLE]
        exposure_summary = by_role[SHORTPICK_MARKET_FACTOR_REPEATED_EXPOSURE_LOW_TURNOVER_CONTROL_ROLE]
        drawdown_summary = by_role[SHORTPICK_MARKET_FACTOR_DRAWDOWN_REVERSAL_LOW_TURNOVER_CONTROL_ROLE]
        self.assertEqual(cooldown_summary["symbol"], "600002.SH")
        self.assertEqual(cooldown_summary["source_rank"], 2)
        self.assertEqual(cooldown_summary["blocked_higher_ranked_count"], 1)
        self.assertEqual(exposure_summary["symbol"], "600002.SH")
        self.assertEqual(exposure_summary["source_rank"], 2)
        self.assertEqual(exposure_summary["blocked_higher_ranked_count"], 1)
        self.assertEqual(drawdown_summary["symbol"], "600001.SH")

    def test_market_factor_overlay_excludes_retired_generation_strategy(self) -> None:
        now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        contexts = [
            {
                "symbol": f"60000{index}.SH",
                "name": f"测试{index}",
                "latest_trade_day": "2026-05-14",
                "close": 10.0 + index,
                "amount": 500000000.0 - index * 1000000,
                "turnover_rate": 0.4 + index * 0.01,
                "return_1d": 0.01,
                "return_5d": 0.03 + index * 0.001,
                "return_10d": 0.08 + index * 0.001,
                "return_20d": 0.12 + index * 0.001,
                "abs_return_1d": 0.01,
                "golden_cross_10_200": False,
                "ma10": 11.0,
                "ma200": 10.0,
                "previous_ma10": 9.5,
                "previous_ma200": 10.0,
            }
            for index in range(1, 6)
        ]
        with session_scope(self.database_url) as session:
            for item in contexts:
                ticker, _, exchange = item["symbol"].partition(".")
                session.add(
                    Stock(
                        symbol=item["symbol"],
                        ticker=ticker,
                        exchange=exchange,
                        name=item["name"],
                        provider_symbol=item["symbol"],
                        listed_date=date(2020, 1, 1),
                        status="active",
                        profile_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://stock/{item['symbol']}",
                        lineage_hash=compute_lineage_hash({"symbol": item["symbol"]}),
                    )
                )
            run = ShortpickExperimentRun(
                run_key="shortpick:2026-05-14:governance-filter",
                run_date=date(2026, 5, 14),
                prompt_version="test",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="running",
                trigger_source="scheduled_cli",
                triggered_by="test",
                started_at=now,
                completed_at=None,
                model_config={},
                summary_payload={},
            )
            session.add(run)
            session.flush()
            run_id = run.id

        write_shortpick_strategy_retirement_artifact_record(
            {
                "artifact_id": "shortpick-retirement:generation-filter-fixture",
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "schema_version": "v1",
                "strategy_id": "frozen_strategy__frozen_paper_primary__frozen_paper_low_turnover_uptrend_v4__next_close__1",
                "decision_log_ref": "DECISIONS.md#generation-filter-fixture",
            },
            root=artifact_root_from_database_url(self.database_url),
        )
        write_shortpick_strategy_retirement_artifact_record(
            {
                "artifact_id": "shortpick-retirement:generation-observe-fixture",
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "schema_version": "v1",
                "strategy_id": "market_factor_control__market_factor_control_offensive_top1__momentum_10d_turnover_rank__next_close__1",
                "recommended_status": "observe",
                "decision_log_ref": "DECISIONS.md#generation-observe-fixture",
            },
            root=artifact_root_from_database_url(self.database_url),
        )
        write_shortpick_strategy_retirement_artifact_record(
            {
                "artifact_id": "shortpick-retirement:generation-retire-candidate-fixture",
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "schema_version": "v1",
                "strategy_id": "market_factor_control__market_factor_control_cooldown_top1__momentum_10d_turnover_cooldown_rank__next_close__1",
                "recommended_status": "retire_candidate",
                "decision_log_ref": "DECISIONS.md#generation-retire-candidate-fixture",
            },
            root=artifact_root_from_database_url(self.database_url),
        )
        write_shortpick_control_inventory_archive_artifact_record(
            {
                "artifact_id": "shortpick-control-inventory-archive:generation-fixture",
                "artifact_type": "shortpick_control_inventory_archive",
                "status": "ready",
                "decision_basis": "inventory_diagnostic_value",
                "decision_log_ref": "DECISIONS.md#generation-inventory-archive-fixture",
                "archive_decisions": [
                    {
                        "strategy_id": (
                            "market_factor_control"
                            "__market_factor_control_legacy_second_candidate"
                            "__momentum_10d_turnover_legacy_second_candidate"
                            "__next_close"
                            "__2"
                        ),
                        "tracking_group": "market_factor_control",
                        "role": "market_factor_control_legacy_second_candidate",
                        "family": "momentum_10d_turnover_legacy_second_candidate",
                        "entry_price_source": "next_close",
                        "source_rank": 2,
                        "archive_reason_code": "dormant_legacy_control",
                    }
                ],
            },
            root=artifact_root_from_database_url(self.database_url),
        )

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_market_factor_universe", return_value={"status": "skipped"}):
            with patch("ashare_evidence.shortpick_lab._shortpick_market_factor_contexts", return_value=(contexts, {})):
                with session_scope(self.database_url) as session:
                    run = session.get(ShortpickExperimentRun, run_id)
                    assert run is not None
                    overlay = insert_shortpick_market_factor_overlay_candidates(session, run)
                    rows = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()

        self.assertGreaterEqual(overlay["current_generation_scope"]["excluded_count"], 1)
        current_scope_roles = {item["tracking_role"] for item in overlay["current_generation_scope"]["excluded_items"]}
        self.assertIn(SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE, current_scope_roles)
        self.assertIn(SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE, current_scope_roles)
        self.assertIn(SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE, current_scope_roles)
        self.assertEqual(overlay["generation_governance"]["excluded_count"], 1)
        self.assertEqual(overlay["generation_governance"]["retirement_artifact_source"]["artifact_count"], 3)
        self.assertEqual(overlay["generation_governance"]["inventory_archive_artifact_source"]["artifact_count"], 1)
        self.assertEqual(overlay["generation_governance"]["inventory_archive_decision_count"], 1)
        excluded_strategy_ids = {item["strategy_id"] for item in overlay["generation_governance"]["excluded_items"]}
        self.assertEqual(
            excluded_strategy_ids,
            {
                "frozen_strategy__frozen_paper_primary__frozen_paper_low_turnover_uptrend_v4__next_close__1",
            },
        )
        tracking_roles = [item["tracking_role"] for item in overlay["candidates"]]
        self.assertNotIn("frozen_paper_primary", tracking_roles)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE, tracking_roles)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE, tracking_roles)
        self.assertNotIn(SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE, tracking_roles)
        self.assertTrue(rows)
        self.assertNotIn("market_factor_frozen_paper", [row.research_priority for row in rows])

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

    def test_tushare_stock_basic_empty_response_uses_full_local_stock_cache(self) -> None:
        self._seed_stock_bars("600001.SH", "测试主板A", [10 + index for index in range(8)])
        self._seed_stock_bars("000001.SZ", "测试主板B", [12 + index for index in range(8)])
        self._seed_stock_bars("688001.SH", "测试科创", [14 + index for index in range(8)])
        with session_scope(self.database_url) as session:
            session.add(
                ProviderCredential(
                    provider_name="tushare",
                    display_name="Tushare",
                    access_token="test-token",
                    base_url="http://api.tushare.pro",
                    enabled=True,
                    notes=None,
                    config_payload={},
                )
            )
            session.commit()

        with patch("ashare_evidence.shortpick_lab.SHORTPICK_MARKET_FACTOR_MIN_FULL_UNIVERSE_SIZE", 2):
            with patch("ashare_evidence.shortpick_lab._tushare_rows", return_value=[]) as rows_call:
                with session_scope(self.database_url) as session:
                    eligible, summary = _sync_shortpick_tushare_stock_master(session, date(2026, 5, 12))

        self.assertEqual(rows_call.call_count, 2)
        self.assertEqual([stock.symbol for stock in eligible], ["000001.SZ", "600001.SH"])
        self.assertEqual(summary["stock_master_source"], "local_stock_cache_after_empty_tushare_stock_basic")
        self.assertEqual(summary["tushare_stock_basic_rows"], 0)
        self.assertEqual(summary["local_stock_cache_rows"], 3)
        self.assertEqual(summary["account_eligible_symbol_count"], 2)

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
        list_item = list_response.json()["items"][0]
        self.assertEqual(list_item["rounds"], [])
        self.assertEqual(list_item["consensus"], None)

        detail_response = client.get(f"/shortpick-lab/runs/{list_item['id']}", headers=member_headers)
        self.assertEqual(detail_response.status_code, 200)
        first_round = detail_response.json()["rounds"][0]
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
                    include_round_details=False,
                    include_consensus=False,
                )

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["candidates"], [])
        self.assertEqual(item["consensus"], None)
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
