from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
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
    ShortpickValidationSnapshot,
    Stock,
    WatchlistFollow,
)
from ashare_evidence.shortpick_lab import (
    DeepseekLobeChatSearchShortpickExecutor,
    OpenAICompatibleShortpickExecutor,
    StaticShortpickExecutor,
    _normalize_shortpick_topic,
    build_shortpick_model_feedback,
    build_shortpick_consensus,
    default_shortpick_executors,
    list_shortpick_runs,
    list_shortpick_validation_queue,
    normalize_shortpick_candidate_topics,
    retry_failed_shortpick_rounds,
    run_shortpick_experiment,
    validate_recent_shortpick_runs,
)

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
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "shortpick.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
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
                        observed_at=datetime(observed_day.year, observed_day.month, observed_day.day, 7, 0, tzinfo=timezone.utc),
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
        start = datetime(2026, 5, 5, 7, 0, tzinfo=timezone.utc)
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
            StaticShortpickExecutor("openai", "gpt-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://a.example/news")),
            StaticShortpickExecutor("deepseek", "deepseek-test", "fake", _answer("688981.SH", "中芯国际", "半导体国产替代", "https://b.example/news")),
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
        self.assertEqual(payload["consensus"]["summary"]["leader_symbols"], ["688981.SH"])
        self.assertEqual(payload["consensus"]["summary"]["cross_model_symbols"], ["688981.SH"])
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertTrue(all(item["research_priority"] == "cross_model_same_symbol" for item in payload["candidates"]))
        self.assertTrue(any(v["status"] == "completed" for v in payload["candidates"][0]["validations"]))

        with session_scope(self.database_url) as session:
            self.assertEqual(session.scalar(select(WatchlistFollow).where(WatchlistFollow.symbol == "688981.SH")), None)
            self.assertEqual(session.scalar(select(Recommendation).limit(1)), None)

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
                    MarketBar.observed_at == datetime(2026, 5, 6, 7, 0, tzinfo=timezone.utc),
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
        openai_feedback = next(item for item in payload["models"] if item["provider_name"] == "openai")
        deepseek_feedback = next(item for item in payload["models"] if item["provider_name"] == "deepseek")
        self.assertEqual(openai_feedback["completed_round_count"], 1)
        self.assertEqual(openai_feedback["source_credibility_counts"]["verified"], 1)
        self.assertTrue(any(group["group_key"] == "1" for group in openai_feedback["validation_by_horizon"]))
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
