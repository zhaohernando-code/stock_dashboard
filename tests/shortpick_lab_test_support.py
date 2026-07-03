# ruff: noqa: F401,F403,F405
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
from ashare_evidence.models import *  # noqa: F403
from ashare_evidence.shortpick_lab import *  # noqa: F403
from ashare_evidence.shortpick_lab import (
    _is_shortpick_no_limit_chase_risk,
    _normalize_shortpick_topic,
    _shortpick_entry_execution_price,
    _shortpick_entry_tradeability,
    _shortpick_frozen_exit_track_results,
    _sync_shortpick_tushare_stock_master,
    _upsert_shortpick_market_factor_candidate,
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

class ShortpickLabTestCase(unittest.TestCase):
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

    def _check_openai_compatible_shortpick_executor_is_blocked_for_shortpick_web_search(self) -> None:
        executor = OpenAICompatibleShortpickExecutor(
            key_id=1,
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
        )

        with self.assertRaisesRegex(RuntimeError, "does not provide web search"):
            executor.complete("prompt")

    def _check_deepseek_executor_uses_lobechat_searxng_search_results(self) -> None:
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

    def _check_deepseek_executor_fails_closed_when_search_results_stay_insufficient(self) -> None:
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

    def _check_search_fallback_chain_uses_public_fallback_when_searxng_is_empty(self) -> None:
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

    def _check_sogou_search_result_parser_extracts_real_results(self) -> None:
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

    def _check_deepseek_executor_rejects_final_sources_outside_search_results(self) -> None:
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

    def _check_default_deepseek_executor_uses_lobechat_search_not_official_native_api(self) -> None:
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

    def _check_intraday_same_day_control_skips_limit_up_entry_candidate(self) -> None:
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


__all__ = [name for name in globals() if not name.startswith("__")]
