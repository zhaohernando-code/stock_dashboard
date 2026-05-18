from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import (
    MarketBar,
    ModelApiKey,
    ModelResult,
    Recommendation,
    ShortpickCandidate,
    ShortpickExperimentRun,
    ShortpickModelRound,
    ShortpickValidationSnapshot,
    Stock,
    WatchlistFollow,
)
from ashare_evidence.shortpick_lab import (
    SHORTPICK_INFORMATION_MODE,
    SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY,
    SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY,
    SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
    DeepseekLobeChatSearchShortpickExecutor,
    OpenAICompatibleShortpickExecutor,
    StaticShortpickExecutor,
    _is_shortpick_no_limit_chase_risk,
    _normalize_shortpick_topic,
    _shortpick_entry_execution_price,
    _shortpick_entry_tradeability,
    _shortpick_frozen_exit_track_results,
    _upsert_shortpick_market_factor_candidate,
    build_shortpick_consensus,
    build_shortpick_model_feedback,
    default_shortpick_executors,
    list_shortpick_runs,
    list_shortpick_validation_queue,
    normalize_shortpick_candidate_topics,
    retry_failed_shortpick_rounds,
    run_shortpick_experiment,
    run_shortpick_intraday_same_day_control,
    select_shortpick_llm_paper_control_candidate,
    shortpick_frozen_paper_strategy_contract,
    shortpick_market_factor_paper_control_contracts,
    validate_recent_shortpick_runs,
)
from ashare_evidence.shortpick_policy import SHORTPICK_FROZEN_STRATEGY_CONFIG

pytestmark = pytest.mark.runtime_integration


def _answer(
    symbol: str,
    name: str,
    theme: str,
    url: str,
    *,
    topic_cluster_id: str | None = None,
    topic_label: str | None = None,
    topic_confidence: float = 0.82,
) -> str:
    payload = {
        "as_of_date": "2026-05-05",
        "information_mode": "native_web_open_discovery",
        "primary_pick": {
            "symbol": symbol,
            "name": name,
            "theme": theme,
            "horizon_trading_days": 5,
            "confidence": 0.66,
            "thesis": f"{theme} 催化下的短线研究候选。",
            "catalysts": [theme],
            "invalidation": ["题材热度回落"],
            "risks": ["短线拥挤"],
        },
        "sources_used": [
            {
                "title": "公开新闻",
                "url": url,
                "published_at": "2026-05-05",
                "why_it_matters": theme,
            }
        ],
        "alternative_picks": [],
        "novelty_note": "来自公开网络的旁路发现。",
        "limitations": ["只代表研究优先级"],
    }
    if topic_cluster_id is not None:
        payload["topic_analysis"] = {
            "primary_topic": {
                "topic_cluster_id": topic_cluster_id,
                "label_zh": topic_label or theme,
                "confidence": topic_confidence,
                "reason": f"{theme} 支撑 {topic_label or topic_cluster_id} 题材归类。",
                "supporting_evidence_refs": [0],
                "driver_types": ["price_change", "market_hotspot"],
                "topic_keywords": [theme],
            },
            "secondary_topics": [],
            "new_topic_proposal": None,
            "not_topic_reason": None,
        }
        payload["topic_verification"] = {
            "verdict": "supported",
            "confidence": topic_confidence,
            "unsupported_claims": [],
            "suggested_topic_cluster_id": None,
        }
    return json.dumps(
        payload,
        ensure_ascii=False,
    )


class ShortpickLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"SHORTPICK_MARKET_FACTOR_SYNC": "0"})
        self.env_patch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "shortpick.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _seed_stock_bars(
        self,
        symbol: str,
        name: str,
        prices: list[float],
        *,
        dates: list[date] | None = None,
        profile_payload: dict[str, object] | None = None,
    ) -> None:
        if dates is not None and len(dates) != len(prices):
            raise ValueError("dates must match prices length")
        with session_scope(self.database_url) as session:
            ticker, _, market = symbol.partition(".")
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=market or "SH",
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 7, 16),
                status="active",
                profile_payload=profile_payload or {},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            for index, price in enumerate(prices):
                observed_day = dates[index] if dates is not None else date(2026, 5, 5) + timedelta(days=index)
                session.add(
                    MarketBar(
                        bar_key=f"bar-{symbol.lower().replace('.', '-')}-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(observed_day.year, observed_day.month, observed_day.day, 7, 0, tzinfo=UTC),
                        open_price=price - 1,
                        high_price=price + 1,
                        low_price=price - 2,
                        close_price=price,
                        volume=1000,
                        amount=price * 1000,
                        raw_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://bar/{symbol}/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": symbol, "index": index}),
                    )
                )

    def _seed_daily_bars(self) -> None:
        self._seed_stock_bars("688981.SH", "中芯国际", [100 + index * 2 for index in range(8)])
        self._seed_stock_bars("600519.SH", "贵州茅台", [1500 + index * 2 for index in range(8)])
        self._seed_stock_bars("000300.SH", "沪深300", [200 + index for index in range(8)])
        self._seed_stock_bars("000852.SH", "中证1000", [300 + index * 1.5 for index in range(8)])

    def _seed_semiconductor_peers(self) -> None:
        profile = {"industry": "半导体", "template_key": "semiconductor"}
        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == "688981.SH"))
            if stock is not None:
                stock.profile_payload = profile
        self._seed_stock_bars("688012.SH", "中微公司", [50, 51, 52, 53, 54, 55, 56, 57], profile_payload=profile)
        self._seed_stock_bars("688008.SH", "澜起科技", [80, 82, 86, 87, 88, 89, 90, 91], profile_payload=profile)

    def _fake_daily_fetch(self, symbol: str, prices: list[float]) -> SimpleNamespace:
        start = datetime(2026, 5, 5, 7, 0, tzinfo=UTC)
        bars = []
        for index, price in enumerate(prices):
            bars.append(
                {
                    "bar_key": f"bar-{symbol.lower().replace('.', '-')}-shortpick-{index}",
                    "timeframe": "1d",
                    "observed_at": start + timedelta(days=index),
                    "open_price": price - 1,
                    "high_price": price + 1,
                    "low_price": price - 2,
                    "close_price": price,
                    "volume": 1000,
                    "amount": price * 1000,
                    "turnover_rate": None,
                    "adj_factor": None,
                    "total_mv": None,
                    "circ_mv": None,
                    "pe_ttm": None,
                    "pb": None,
                    "raw_payload": {"provider_name": "test"},
                    "source_uri": f"test://shortpick-bar/{symbol}/{index}",
                    "license_tag": "test",
                    "usage_scope": "internal-test",
                    "redistribution_scope": "none",
                    "lineage_hash": compute_lineage_hash({"symbol": symbol, "index": index}),
                }
            )
        return SimpleNamespace(provider_name="test_daily", bars=bars)

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

    def test_validate_recent_shortpick_runs_refreshes_completed_runs(self) -> None:
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
                    payload = validate_recent_shortpick_runs(session, days=10, limit=5, horizons=[1])

        self.assertEqual(payload["refreshed_run_count"], 1)
        self.assertEqual(payload["runs"][0]["updated_validation_count"], 1)
        self.assertEqual(payload["runs"][0]["summary"]["completed_validation_count"], 3)

    def test_validate_recent_can_use_existing_market_data_only(self) -> None:
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

        with patch("ashare_evidence.shortpick_lab._sync_shortpick_benchmarks") as sync_benchmarks:
            with patch("ashare_evidence.shortpick_lab._sync_shortpick_candidate_market_data") as sync_market:
                with session_scope(self.database_url) as session:
                    payload = validate_recent_shortpick_runs(
                        session,
                        days=30,
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
        executor = OpenAICompatibleShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
        )

        with self.assertRaisesRegex(RuntimeError, "does not provide web search"):
            executor.complete("prompt")

    def test_deepseek_executor_uses_lobechat_searxng_search_results(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_complete(self, **kwargs):
            calls.append(kwargs)
            prompt = str(kwargs["prompt"])
            if "只生成搜索计划" in prompt:
                return json.dumps(
                    {
                        "search_queries": ["A股 半导体 国产替代 短线 新闻"],
                        "search_intent": "寻找公开热点和催化。",
                    },
                    ensure_ascii=False,
                )
            return _answer("688981.SH", "中芯国际", "半导体国产替代", "https://news.cn/finance/test")

        class FakeSearchClient:
            def search(self, query: str):
                return [
                    {
                        "title": f"半导体公开新闻 {index}",
                        "url": "https://news.cn/finance/test" if index == 0 else f"https://news.cn/finance/test-{index}",
                        "published_at": "2026-05-05",
                        "why_it_matters": query,
                    }
                    for index in range(3)
                ]

        executor = DeepseekLobeChatSearchShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
            search_client=FakeSearchClient(),
        )
        with patch("ashare_evidence.shortpick_lab.OpenAICompatibleTransport.complete", new=fake_complete):
            with patch("ashare_evidence.shortpick_lab._source_credibility", return_value={"credibility_status": "verified", "credibility_reason": "test"}):
                raw = executor.complete("prompt")

        parsed = json.loads(raw)
        self.assertEqual(parsed["_executor_trace"]["search_backend"], "lobechat_searxng")
        self.assertEqual(parsed["_executor_trace"]["search_queries"], ["A股 半导体 国产替代 短线 新闻"])
        self.assertEqual(parsed["sources_used"][0]["url"], "https://news.cn/finance/test")
        self.assertEqual(parsed["_executor_trace"]["search_result_count"], 3)
        self.assertEqual([item.get("enable_search") for item in calls], [None, None])
        self.assertEqual(executor.executor_kind, "deepseek_tool_search_lobechat_searxng_v1")

    def test_deepseek_executor_fails_closed_when_search_results_stay_insufficient(self) -> None:
        def fake_complete(_self, **kwargs):
            prompt = str(kwargs["prompt"])
            if "只生成搜索计划" in prompt:
                return json.dumps({"search_queries": ["A股 稀土 新闻"]}, ensure_ascii=False)
            return _answer("000831.SZ", "中国稀土", "稀土价格", "https://news.cn/rare-earth")

        class SparseSearchClient:
            def search(self, query: str):
                return [
                    {
                        "title": "稀土公开新闻",
                        "url": "https://news.cn/rare-earth",
                        "published_at": "2026-05-05",
                        "why_it_matters": query,
                    }
                ]

        executor = DeepseekLobeChatSearchShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
            search_client=SparseSearchClient(),
        )
        with patch("ashare_evidence.shortpick_lab.OpenAICompatibleTransport.complete", new=fake_complete):
            with self.assertRaisesRegex(RuntimeError, "fail_closed_no_pure_reasoning_fallback"):
                executor.complete("prompt")

    def test_search_fallback_chain_uses_public_fallback_when_searxng_is_empty(self) -> None:
        from ashare_evidence.shortpick_lab import ShortpickSearchFallbackChain

        class EmptyPrimary:
            def search(self, query: str):
                return []

        class Fallback:
            def search(self, query: str):
                return [
                    {
                        "title": "5月8日A股热点",
                        "url": "https://www.sogou.com/link?url=real",
                        "published_at": "2026-05-08",
                        "why_it_matters": query,
                        "search_engine": "sogou_web_fallback",
                    }
                ]

        chain = ShortpickSearchFallbackChain(primary=EmptyPrimary(), fallbacks=(Fallback(),))

        results = chain.search("2026年5月8日 A股 热点板块 资金流入 短线")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["search_engine"], "sogou_web_fallback")

    def test_sogou_search_result_parser_extracts_real_results(self) -> None:
        from ashare_evidence.shortpick_lab import _parse_sogou_search_results

        html = """
        <div class="vrwrap">
          <h3><a href="/link?url=abc">5月8日A股热点板块_东方财富网</a></h3>
          <p>5月8日 A股 收红盘，通信设备板块资金流入。 东方财富网 2026-05-08</p>
        </div></div>
        <div class="vrwrap">
          <h3><a href="/sogou?query=A股">A股 短线 热点_相关资讯</a></h3>
        </div></div>
        """

        results = _parse_sogou_search_results(html, query="A股 热点", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://www.sogou.com/link?url=abc")
        self.assertEqual(results[0]["published_at"], "2026-05-08")
        self.assertEqual(results[0]["search_engine"], "sogou_web_fallback")

    def test_deepseek_executor_rejects_final_sources_outside_search_results(self) -> None:
        def fake_complete(_self, **kwargs):
            prompt = str(kwargs["prompt"])
            if "只生成搜索计划" in prompt:
                return json.dumps({"search_queries": ["A股 半导体 新闻"]}, ensure_ascii=False)
            return _answer("688981.SH", "中芯国际", "半导体国产替代", "https://fabricated.example/news")

        class SearchClient:
            def search(self, query: str):
                return [
                    {
                        "title": f"半导体公开新闻 {index}",
                        "url": f"https://news.cn/finance/real-{index}",
                        "published_at": "2026-05-05",
                        "why_it_matters": query,
                    }
                    for index in range(3)
                ]

        executor = DeepseekLobeChatSearchShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
            search_client=SearchClient(),
        )
        with patch("ashare_evidence.shortpick_lab.OpenAICompatibleTransport.complete", new=fake_complete):
            with self.assertRaisesRegex(RuntimeError, "final_source_not_in_search_results"):
                executor.complete("prompt")

    def test_default_deepseek_executor_uses_lobechat_search_not_official_native_api(self) -> None:
        with session_scope(self.database_url) as session:
            session.add(
                ModelApiKey(
                    name="deepseek",
                    provider_name="deepseek",
                    model_name="deepseek-v4-pro",
                    base_url="https://api.deepseek.com",
                    api_key="secret",
                    enabled=True,
                    is_default=True,
                    priority=1,
                )
            )
            session.flush()
            executors = default_shortpick_executors(session)

        deepseek_executor = next(item for item in executors if item.provider_name == "deepseek")
        self.assertEqual(deepseek_executor.executor_kind, "deepseek_tool_search_lobechat_searxng_v1")

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

    def test_frozen_paper_contract_tracks_four_trading_day_exit_windows(self) -> None:
        contract = shortpick_frozen_paper_strategy_contract()
        tracks = contract["monitoring_tracks"]
        paper_tracking_config = SHORTPICK_FROZEN_STRATEGY_CONFIG["paper_tracking"]

        self.assertEqual([item["key"] for item in tracks], [
            "mechanical_5d",
            "mechanical_10d",
            "conditional_5_to_10d",
            "take_profit_10pct",
        ])
        self.assertTrue(all(item["uses_trading_days"] for item in tracks))
        self.assertIn("交易日", contract["mode"])
        self.assertIn("低换手上升趋势", contract["label"])
        self.assertIn("成交额和换手率", contract["pool_rule"])
        self.assertIn("20日趋势向上", contract["selection_rule"])
        self.assertNotIn("第2名", contract["selection_rule"])
        conditional_track = next(item for item in tracks if item["key"] == "conditional_5_to_10d")
        self.assertEqual(conditional_track["peak_giveback_pct"], paper_tracking_config["peak_giveback_pct"])
        self.assertEqual(contract["version"], SHORTPICK_FROZEN_STRATEGY_CONFIG["version"])

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

        self.assertEqual(set(by_key), {"mechanical_5d", "mechanical_10d", "conditional_5_to_10d", "take_profit_10pct"})
        self.assertEqual(by_key["mechanical_5d"]["holding_trading_days"], 5)
        self.assertEqual(by_key["mechanical_10d"]["holding_trading_days"], 10)
        self.assertEqual(by_key["conditional_5_to_10d"]["exit_reason"], "trend_check_failed_after_day5")
        self.assertEqual(by_key["take_profit_10pct"]["exit_reason"], "take_profit_10pct_touched")
        self.assertAlmostEqual(by_key["take_profit_10pct"]["stock_return"], 0.10)

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

        self.assertEqual([item["key"] for item in tracks], ["mechanical_5d", "mechanical_10d", "conditional_5_to_10d", "take_profit_10pct"])

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
                ["mechanical_5d", "mechanical_10d", "conditional_5_to_10d", "take_profit_10pct"],
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
        trading_days = [date(2026, 4, 22) + timedelta(days=index) for index in range(20)]
        self._seed_stock_bars(
            "600001.SH",
            "测试涨停",
            [10.0 + index * 0.2 for index in range(20)],
            dates=trading_days,
            profile_payload={"industry": "测试行业"},
        )
        self._seed_stock_bars(
            "600002.SH",
            "测试可买",
            [9.8 + index * 0.18 for index in range(20)],
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
                    "name": "测试涨停",
                    "price": 15.18,
                    "open": 14.0,
                    "high": 15.18,
                    "low": 13.9,
                    "previous_close": 13.80,
                    "return_pct": 10.0,
                    "amount": 600000000.0,
                    "volume": 1000000.0,
                    "turnover_rate": 1.0,
                    "captured_at": "2026-05-12T05:55:00+00:00",
                },
                "600002.SH": {
                    "symbol": "600002.SH",
                    "name": "测试可买",
                    "price": 13.50,
                    "open": 13.10,
                    "high": 13.60,
                    "low": 13.00,
                    "previous_close": 13.22,
                    "return_pct": 2.12,
                    "amount": 500000000.0,
                    "volume": 1000000.0,
                    "turnover_rate": 1.0,
                    "captured_at": "2026-05-12T05:55:00+00:00",
                },
            },
            "summary": {"status": "ok", "quote_count": 2},
        }
        limit_entry_snapshot = {
            **full_snapshot,
            "generated_at": "2026-05-12T05:56:00+00:00",
            "quotes": {"600001.SH": full_snapshot["quotes"]["600001.SH"]},
        }
        tradable_entry_snapshot = {
            **full_snapshot,
            "generated_at": "2026-05-12T05:57:00+00:00",
            "quotes": {"600002.SH": full_snapshot["quotes"]["600002.SH"]},
        }

        with patch(
            "ashare_evidence.shortpick_lab._fetch_shortpick_intraday_spot_quotes",
            side_effect=[full_snapshot, limit_entry_snapshot, tradable_entry_snapshot],
        ):
            with session_scope(self.database_url) as session:
                payload = run_shortpick_intraday_same_day_control(session, run_date=date(2026, 5, 12), triggered_by="test")

        overlay = payload["summary"]["market_factor_overlay"]
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(overlay["inserted_candidate_count"], 1)
        self.assertEqual(overlay["excluded_entry_unfillable_count"], 1)
        self.assertEqual(overlay["excluded_entry_unfillable"][0]["symbol"], "600001.SH")
        self.assertEqual(payload["candidates"][0]["symbol"], "600002.SH")

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
        self.assertEqual(payload["summary"]["tracked_signal_count"], 1)
        self.assertEqual(payload["summary"]["frozen_v2_signal_count"], 1)

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


if __name__ == "__main__":
    unittest.main()
