from __future__ import annotations

import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import (
    MarketBar,
    NewsEntityLink,
    NewsItem,
    ShortpickCandidate,
    ShortpickExperimentRun,
    ShortpickModelRound,
    ShortpickValidationSnapshot,
    Stock,
)
from ashare_evidence.shortpick_lab import SHORTPICK_INFORMATION_MODE, list_shortpick_runs
from ashare_evidence.shortpick_replay import (
    _build_universe,
    _replay_regime_stability_projection,
    _replay_return_attribution,
    build_shortpick_replay_feedback,
    get_shortpick_replay_sources,
    list_shortpick_replay_runs,
    run_shortpick_historical_replay,
    run_shortpick_historical_replay_concurrent,
    run_shortpick_replay_distillation,
    run_shortpick_replay_distillation_concurrent,
    run_shortpick_replay_rejection,
)


def _lineage(payload: object, uri: str) -> dict[str, str]:
    return {
        "license_tag": "test",
        "usage_scope": "internal-test",
        "redistribution_scope": "none",
        "source_uri": uri,
        "lineage_hash": compute_lineage_hash(payload),
    }


def _seed_replay_fixture(database_url: str) -> None:
    as_of = date(2026, 5, 5)
    symbols = [
        ("600001.SH", "测试银行", "银行", 120.0),
        ("600002.SH", "测试能源", "能源", 95.0),
        ("600003.SH", "测试半导体", "半导体", 180.0),
        ("600004.SH", "测试软件", "软件", 155.0),
        ("600005.SH", "测试消费", "消费", 80.0),
        ("600006.SH", "测试医药", "医药", 110.0),
        ("688001.SH", "测试科创", "科创", 130.0),
        ("000300.SH", "沪深300", "benchmark", 200.0),
        ("000852.SH", "中证1000", "benchmark", 300.0),
    ]
    with session_scope(database_url) as session:
        stocks: dict[str, Stock] = {}
        for symbol, name, industry, base_price in symbols:
            ticker, _, exchange = symbol.partition(".")
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange,
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={"industry": industry},
                **_lineage({"symbol": symbol}, f"test://stock/{symbol}"),
            )
            session.add(stock)
            session.flush()
            stocks[symbol] = stock
            for index in range(12):
                observed_day = as_of - timedelta(days=2) + timedelta(days=index)
                close_price = base_price + index * (1.0 if symbol.endswith(".SH") else 0.6)
                session.add(
                    MarketBar(
                        bar_key=f"replay-bar-{symbol}-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(observed_day.year, observed_day.month, observed_day.day, 7, 0, tzinfo=UTC),
                        open_price=close_price - 0.5,
                        high_price=close_price + 1.0,
                        low_price=close_price - 1.0,
                        close_price=close_price,
                        volume=100000 + index,
                        amount=(100000 + index) * close_price,
                        turnover_rate=0.8 + index * 0.01,
                        total_mv=1_000_000_000 + index * 100_000 + base_price * 1_000_000,
                        circ_mv=900_000_000 + index * 100_000,
                        raw_payload={},
                        **_lineage({"symbol": symbol, "index": index}, f"test://bar/{symbol}/{index}"),
                    )
                )

        official_news = NewsItem(
            news_key="news-before-cutoff",
            provider_name="fixture",
            external_id="before-cutoff",
            headline="测试半导体获得订单",
            summary="测试半导体在回放日收盘前披露订单进展。",
            content_excerpt="测试半导体订单进展，发布时间早于 sealed packet cutoff。",
            published_at=datetime(2026, 5, 5, 8, 30, tzinfo=UTC),
            event_scope="stock",
            dedupe_key="before-cutoff",
            raw_payload={"url": "https://example.test/before"},
            **_lineage({"news": "before"}, "https://example.test/before"),
        )
        future_news = NewsItem(
            news_key="news-after-cutoff",
            provider_name="fixture",
            external_id="after-cutoff",
            headline="测试软件次日涨停",
            summary="这条新闻晚于 as_of_cutoff，必须进入 rejected source。",
            content_excerpt="未来涨停结果不能进入 official packet。",
            published_at=datetime(2026, 5, 6, 8, 30, tzinfo=UTC),
            event_scope="stock",
            dedupe_key="after-cutoff",
            raw_payload={"url": "https://example.test/after"},
            **_lineage({"news": "after"}, "https://example.test/after"),
        )
        session.add_all([official_news, future_news])
        session.flush()
        session.add(
            NewsEntityLink(
                news_id=official_news.id,
                entity_type="stock",
                stock_id=stocks["600003.SH"].id,
                sector_id=None,
                market_tag="A",
                relevance_score=0.9,
                impact_direction="positive",
                effective_at=official_news.published_at,
                decay_half_life_hours=72.0,
                mapping_payload={},
                **_lineage({"link": "before"}, "test://news-link/before"),
            )
        )
        session.add(
            NewsEntityLink(
                news_id=future_news.id,
                entity_type="stock",
                stock_id=stocks["600004.SH"].id,
                sector_id=None,
                market_tag="A",
                relevance_score=0.9,
                impact_direction="positive",
                effective_at=future_news.published_at,
                decay_half_life_hours=72.0,
                mapping_payload={},
                **_lineage({"link": "after"}, "test://news-link/after"),
            )
        )


def test_historical_replay_creates_isolated_candidates_and_rejected_sources(monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "proxy")
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=2,
                candidate_limit=2,
                triggered_by="test",
            )
            run_id = payload["runs"][0]["id"]
            run = session.get(ShortpickExperimentRun, run_id)
            assert run is not None
            assert run.information_mode == "historical_replay"
            assert run.summary_payload["boundary"] == "historical_replay_no_main_pool_write"

            candidates = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
            families = {candidate.candidate_payload["baseline_family"] for candidate in candidates}
            assert {"llm", "random_same_tradeable_universe", "random_same_market_cap_bucket", "momentum_volume_baseline"} <= families
            assert all(candidate.candidate_payload["source_packet_hash"] for candidate in candidates)
            assert all(candidate.candidate_payload["leakage_audit_status"] == "pass" for candidate in candidates)
            assert all(candidate.candidate_payload["tradeability"]["is_tradeable"] for candidate in candidates)
            assert all(candidate.candidate_payload["market_cap_bucket"] for candidate in candidates)
            assert all(candidate.candidate_payload["industry"] for candidate in candidates)
            assert all("limitations" in candidate.candidate_payload for candidate in candidates)

            snapshots = [
                snapshot
                for candidate in candidates
                for snapshot in session.scalars(
                    select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id == candidate.id)
                ).all()
            ]
            assert snapshots
            assert all(snapshot.validation_payload["market_sync_status"] == "historical_replay_existing_only" for snapshot in snapshots)
            assert all(snapshot.validation_payload["benchmark_sync_status"] == "historical_replay_existing_only" for snapshot in snapshots)
            assert all(snapshot.validation_payload["benchmark_dimensions"]["sector_equal_weight"]["status"] == "historical_replay_existing_only" for snapshot in snapshots)

            sources = get_shortpick_replay_sources(session, run_id)
            assert sources["official_sources"]
            assert sources["rejected_sources"]
            assert sources["rejected_sources"][0]["reject_reason"] == "source_after_cutoff"
            assert sources["tradable_universe"]["tradeable_count"] >= 6


def test_replay_evidence_projection_builds_market_regime_and_industry_artifacts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay-evidence.db'}"
        init_database(database_url)
        with session_scope(database_url) as session:
            for symbol, name, base, step in (
                ("000300.SH", "沪深300", 100.0, 1.0),
                ("000852.SH", "中证1000", 100.0, 2.0),
            ):
                stock = Stock(
                    symbol=symbol,
                    ticker=symbol.split(".")[0],
                    exchange=symbol.split(".")[1],
                    name=name,
                    provider_symbol=symbol,
                    listed_date=date(2020, 1, 1),
                    status="active",
                    profile_payload={"industry": "benchmark"},
                    **_lineage({"symbol": symbol}, f"test://stock/{symbol}"),
                )
                session.add(stock)
                session.flush()
                for index in range(10):
                    observed_day = date(2026, 5, 1) + timedelta(days=index)
                    close_price = base + index * step
                    session.add(
                        MarketBar(
                            bar_key=f"regime-{symbol}-{index}",
                            stock_id=stock.id,
                            timeframe="1d",
                            observed_at=datetime(observed_day.year, observed_day.month, observed_day.day, 7, 0, tzinfo=UTC),
                            open_price=close_price - 0.2,
                            high_price=close_price + 0.5,
                            low_price=close_price - 0.5,
                            close_price=close_price,
                            volume=100000 + index,
                            amount=(100000 + index) * close_price,
                            raw_payload={},
                            **_lineage({"symbol": symbol, "index": index}, f"test://bar/{symbol}/{index}"),
                        )
                    )
            rows = [
                {
                    "candidate_id": 1,
                    "symbol": "600001.SH",
                    "industry": "半导体",
                    "horizon_days": 5,
                    "status": "completed",
                    "excess_return": 0.04,
                    "stock_return": 0.06,
                    "baseline_family": "llm",
                    "official_sample_eligible": True,
                    "tradable_sample_eligible": True,
                    "run_id": 1,
                    "run_date": date(2026, 5, 8),
                },
                {
                    "candidate_id": 2,
                    "symbol": "600002.SH",
                    "industry": "银行",
                    "horizon_days": 5,
                    "status": "completed",
                    "excess_return": -0.02,
                    "stock_return": -0.01,
                    "baseline_family": "momentum_10d_turnover_cooldown_rank",
                    "official_sample_eligible": True,
                    "tradable_sample_eligible": True,
                    "run_id": 2,
                    "run_date": date(2026, 5, 9),
                },
            ]

            regime = _replay_regime_stability_projection(rows, session=session)
            attribution = _replay_return_attribution(rows)

            assert regime["market_regime"]["status"] == "ready"
            assert regime["market_regime"]["coverage"]["tagged_date_count"] == 2
            assert regime["market_regime"]["rows"][0]["market_regime_tag"]
            assert regime["industry_theme"]["status"] == "ready"
            assert regime["industry_theme"]["rows"][0]["industry"] in {"半导体", "银行"}
            assert attribution["industry_theme"]["status"] == "ready"
            assert attribution["industry_theme"]["best_industry"] == "半导体"
            assert attribution["industry_theme"]["worst_industry"] == "银行"


def test_replay_feedback_compares_llm_and_baselines_without_live_pollution(monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "proxy")
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=2,
                candidate_limit=2,
            )
            run_id = payload["runs"][0]["id"]
            feedback = build_shortpick_replay_feedback(session, run_id=run_id)
            families = {family["baseline_family"] for family in feedback["families"]}
            assert {"diagnostic_proxy_llm", "random_same_tradeable_universe", "random_same_market_cap_bucket", "momentum_volume_baseline"} <= families
            for family in feedback["families"]:
                assert family["candidate_count"] == 2
                assert family["official_sample_count"] == 2
                assert family["completed_official_sample_count"] <= 2
            assert feedback["overall"]["run_count"] == 1
            assert feedback["overall"]["unique_replay_date_count"] == 1
            assert feedback["overall"]["validation_by_horizon"]
            assert [group["group_key"] for group in feedback["overall"]["validation_by_horizon"]] == ["1", "3", "5", "10", "20"]
            assert feedback["overall"]["statistical_gate"]["status"] in {"exploratory", "ready"}
            assert feedback["overall"]["factor_ic_gate"]["status"] == "blocked"
            assert feedback["overall"]["news_calibration"]["status"] == "diagnostic_only"

            aggregate_feedback = build_shortpick_replay_feedback(session, run_id=None)
            assert aggregate_feedback["run_id"] is None
            assert aggregate_feedback["overall"]["run_count"] == 0
            assert aggregate_feedback["overall"]["validation_by_horizon"] == []


def test_historical_replay_uses_real_sealed_packet_llm_executor(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            assert "sealed source packet" in prompt
            assert "src-001" in prompt
            assert "禁止联网" in (system or "")
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": {
                        "symbol": "600003.SH",
                        "name": "测试半导体",
                        "theme": "半导体订单",
                        "thesis": "测试半导体在 sealed packet 中有订单进展来源支持。",
                        "catalysts": ["订单进展"],
                        "risks": ["样本 fixture 有限"],
                        "invalidation": ["来源失效"],
                        "sources_used": ["src-001"],
                        "evidence_mapping": {"thesis": ["src-001"]},
                        "limitations": ["fixture response"],
                    },
                    "candidates": [],
                    "limitations": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=2,
                candidate_limit=2,
            )
            run_id = payload["runs"][0]["id"]
            run = session.get(ShortpickExperimentRun, run_id)
            assert run is not None
            assert run.summary_payload["llm_executor_kind"] == "historical_replay_sealed_packet_llm"
            assert run.summary_payload["model_family"] == "deepseek:deepseek-fixture"
            llm_candidates = [
                candidate
                for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
                if candidate.candidate_payload["baseline_family"] == "llm"
            ]
            assert [candidate.symbol for candidate in llm_candidates] == ["600003.SH"]
            assert llm_candidates[0].thesis == "测试半导体在 sealed packet 中有订单进展来源支持。"
            assert llm_candidates[0].candidate_payload["sources_used"] == ["src-001"]
            run_list = list_shortpick_replay_runs(session, limit=10)
            assert run_list["total"] == 1
            listed = run_list["items"][0]
            assert listed["candidates"] == []
            assert "replay_feedback" not in listed["summary"]
            source_packet = listed["summary"]["source_packet"]
            assert "official_sources" not in source_packet
            assert "rejected_sources" not in source_packet
            live_list = list_shortpick_runs(session, information_mode=SHORTPICK_INFORMATION_MODE, limit=10)
            assert live_list["total"] == 0


def test_historical_replay_default_universe_uses_new_retail_account_filter(monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "proxy")
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            universe = _build_universe(session, as_of_date=date(2026, 5, 5))
            symbols = set(universe["by_symbol"])
            assert "600003.SH" in symbols
            assert "688001.SH" not in symbols
            assert universe["summary"]["account_profile"] == "new_retail_cash_account"
            assert universe["summary"]["excluded_counts"]["account_excluded_star"] == 1


def test_historical_replay_concurrent_runs_llm_in_parallel_but_writes_valid_runs(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            assert "新开户普通现金账户" in prompt
            assert "688001.SH" not in prompt
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": {
                        "symbol": "600003.SH",
                        "name": "测试半导体",
                        "theme": "半导体订单",
                        "thesis": "测试半导体在 sealed packet 中有订单进展来源支持。",
                        "catalysts": ["订单进展"],
                        "risks": ["样本 fixture 有限"],
                        "invalidation": ["来源失效"],
                        "sources_used": ["src-001"],
                        "evidence_mapping": {"thesis": ["src-001"]},
                        "limitations": ["fixture response"],
                    },
                    "candidates": [],
                    "limitations": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay_concurrent(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 6),
                rounds=1,
                candidate_limit=1,
                max_workers=2,
            )
            assert payload["execution_mode"] == "concurrent_llm_serial_db_writer"
            assert payload["llm_max_workers"] == 2
            assert payload["run_count"] == 2
            assert payload["failed_llm_count"] == 0
            runs = session.scalars(select(ShortpickExperimentRun).order_by(ShortpickExperimentRun.run_date.asc())).all()
            assert [run.status for run in runs] == ["completed", "completed"]
            assert all(run.model_config["account_profile"] == "new_retail_cash_account" for run in runs)
            rounds = session.scalars(select(ShortpickModelRound).order_by(ShortpickModelRound.run_id.asc())).all()
            assert len(rounds) == 2
            assert all(round_row.executor_kind == "historical_replay_sealed_packet_llm" for round_row in rounds)


def test_replay_distillation_adds_self_and_momentum_filter_families(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            if "sealed distillation packet:" in prompt:
                packet = json.loads(prompt.split("sealed distillation packet:", 1)[1].strip())
                assert packet["candidate_pool"]
                limit = 1 if packet["distillation_mode"] == "llm_self_distillation" else 2
                picks = []
                for item in packet["candidate_pool"][:limit]:
                    source_ids = list(item.get("source_ids") or [])[:1]
                    picks.append(
                        {
                            "symbol": item["symbol"],
                            "name": item["name"],
                            "theme": item.get("industry") or "蒸馏",
                            "thesis": "候选在封闭池中经 LLM 蒸馏保留。",
                            "catalysts": ["封闭来源与行情快照共同支持"],
                            "risks": ["样本 fixture 有限"],
                            "invalidation": ["封闭来源支持减弱"],
                            "sources_used": source_ids,
                            "evidence_mapping": {"thesis": source_ids},
                            "limitations": ["fixture distillation response"],
                        }
                    )
                return json.dumps(
                    {
                        "as_of_date": "2026-05-05",
                        "information_mode": "historical_replay",
                        "distillation_mode": packet["distillation_mode"],
                        "source_family": packet["source_family"],
                        "output_family": packet["output_family"],
                        "primary_pick": picks[0],
                        "candidates": picks[1:],
                        "limitations": [],
                    },
                    ensure_ascii=False,
                )
            assert "sealed source packet" in prompt
            picks = [
                {
                    "symbol": "600003.SH",
                    "name": "测试半导体",
                    "theme": "半导体订单",
                    "thesis": "测试半导体在 sealed packet 中有订单进展来源支持。",
                    "catalysts": ["订单进展"],
                    "risks": ["样本 fixture 有限"],
                    "invalidation": ["来源失效"],
                    "sources_used": ["src-001"],
                    "evidence_mapping": {"thesis": ["src-001"]},
                    "limitations": ["fixture response"],
                },
                {
                    "symbol": "600004.SH",
                    "name": "测试软件",
                    "theme": "软件",
                    "thesis": "测试软件仅基于封闭行情快照进入原始 LLM 池。",
                    "catalysts": ["行情快照"],
                    "risks": ["缺少直接来源"],
                    "invalidation": ["动量减弱"],
                    "sources_used": [],
                    "evidence_mapping": {},
                    "limitations": ["market snapshot only"],
                },
            ]
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": picks[0],
                    "candidates": picks[1:],
                    "limitations": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=2,
                candidate_limit=2,
            )
            run_id = payload["runs"][0]["id"]
            distill_payload = run_shortpick_replay_distillation(
                session,
                run_id=run_id,
                momentum_pool_limit=4,
                self_distill_limit=1,
                momentum_distill_limit=2,
            )
            assert distill_payload["run_count"] == 1
            assert distill_payload["runs"][0]["candidate_counts"] == {
                "llm_self_distilled": 1,
                "llm_momentum_distilled": 2,
                "momentum_volume_expanded_pool": 4,
            }
            candidates = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
            by_family = {}
            for candidate in candidates:
                by_family.setdefault(candidate.candidate_payload["baseline_family"], []).append(candidate)
            assert len(by_family["llm"]) == 2
            assert len(by_family["llm_self_distilled"]) == 1
            assert len(by_family["llm_momentum_distilled"]) == 2
            assert len(by_family["momentum_volume_expanded_pool"]) == 4
            assert all(candidate.round_id is not None for candidate in by_family["llm_self_distilled"])
            assert all(candidate.round_id is not None for candidate in by_family["llm_momentum_distilled"])

            feedback = build_shortpick_replay_feedback(session, run_id=run_id)
            families = {family["baseline_family"]: family for family in feedback["families"]}
            assert families["llm_self_distilled"]["label"] == "LLM自选蒸馏"
            assert families["llm_momentum_distilled"]["label"] == "LLM动量池蒸馏"
            assert families["momentum_volume_expanded_pool"]["label"] == "扩大动量池"

            rounds = session.scalars(
                select(ShortpickModelRound).where(ShortpickModelRound.run_id == run_id).order_by(ShortpickModelRound.round_index.asc())
            ).all()
            assert [round_row.round_index for round_row in rounds] == [1, 2, 3]


def test_replay_distillation_concurrent_writes_distilled_families(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            if "sealed distillation packet:" in prompt:
                packet = json.loads(prompt.split("sealed distillation packet:", 1)[1].strip())
                picks = []
                for item in packet["candidate_pool"][:1]:
                    picks.append(
                        {
                            "symbol": item["symbol"],
                            "name": item["name"],
                            "theme": item.get("industry") or "蒸馏",
                            "thesis": "并发蒸馏保留候选。",
                            "catalysts": ["封闭池支持"],
                            "risks": ["样本 fixture 有限"],
                            "invalidation": ["来源支持减弱"],
                            "sources_used": list(item.get("source_ids") or [])[:1],
                            "evidence_mapping": {},
                            "limitations": ["fixture concurrent distillation response"],
                        }
                    )
                return json.dumps(
                    {
                        "as_of_date": "2026-05-05",
                        "information_mode": "historical_replay",
                        "distillation_mode": packet["distillation_mode"],
                        "source_family": packet["source_family"],
                        "output_family": packet["output_family"],
                        "primary_pick": picks[0],
                        "candidates": [],
                        "limitations": [],
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": {
                        "symbol": "600003.SH",
                        "name": "测试半导体",
                        "theme": "半导体订单",
                        "thesis": "测试半导体在 sealed packet 中有订单进展来源支持。",
                        "catalysts": ["订单进展"],
                        "risks": ["样本 fixture 有限"],
                        "invalidation": ["来源失效"],
                        "sources_used": ["src-001"],
                        "evidence_mapping": {"thesis": ["src-001"]},
                        "limitations": ["fixture response"],
                    },
                    "candidates": [],
                    "limitations": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=1,
                candidate_limit=1,
            )
            run_id = payload["runs"][0]["id"]
            distill_payload = run_shortpick_replay_distillation_concurrent(
                session,
                run_id=run_id,
                momentum_pool_limit=4,
                self_distill_limit=1,
                momentum_distill_limit=1,
                max_workers=2,
            )
            assert distill_payload["execution_mode"] == "concurrent_llm_serial_db_writer"
            assert distill_payload["llm_max_workers"] == 2
            assert distill_payload["runs"][0]["candidate_counts"] == {
                "llm_self_distilled": 1,
                "llm_momentum_distilled": 1,
                "momentum_volume_expanded_pool": 4,
            }


def test_replay_rejection_adds_rejector_and_random_control_families(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            if "sealed rejection packet:" in prompt:
                packet = json.loads(prompt.split("sealed rejection packet:", 1)[1].strip())
                assert packet["candidate_pool"]
                decisions = []
                for index, item in enumerate(packet["candidate_pool"]):
                    source_ids = list(item.get("source_ids") or [])[:1]
                    decisions.append(
                        {
                            "symbol": item["symbol"],
                            "decision": "reject" if index == 1 else "keep",
                            "reason_category": "weak_source" if index == 1 else "other",
                            "reason": "fixture reject decision" if index == 1 else "fixture keep decision",
                            "sources_used": source_ids,
                            "evidence_mapping": {"reason": source_ids},
                            "limitations": ["fixture rejection response"],
                        }
                    )
                return json.dumps(
                    {
                        "as_of_date": "2026-05-05",
                        "information_mode": "historical_replay",
                        "rejection_mode": "momentum_pool_reject_only",
                        "source_family": "momentum_volume_expanded_pool",
                        "decisions": decisions,
                        "limitations": [],
                    },
                    ensure_ascii=False,
                )
            assert "sealed source packet" in prompt
            picks = [
                {
                    "symbol": "600003.SH",
                    "name": "测试半导体",
                    "theme": "半导体订单",
                    "thesis": "测试半导体在 sealed packet 中有订单进展来源支持。",
                    "catalysts": ["订单进展"],
                    "risks": ["样本 fixture 有限"],
                    "invalidation": ["来源失效"],
                    "sources_used": ["src-001"],
                    "evidence_mapping": {"thesis": ["src-001"]},
                    "limitations": ["fixture response"],
                }
            ]
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": picks[0],
                    "candidates": [],
                    "limitations": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=1,
                candidate_limit=1,
            )
            run_id = payload["runs"][0]["id"]
            reject_payload = run_shortpick_replay_rejection(
                session,
                run_id=run_id,
                momentum_pool_limit=4,
                rank_limit=2,
                reject_max_ratio=0.5,
            )
            assert reject_payload["run_count"] == 1
            assert reject_payload["runs"][0]["candidate_counts"] == {
                "momentum_volume_expanded_pool": 4,
                "llm_reject_only": 3,
                "llm_reject_then_momentum_rank": 2,
                "random_reject_then_momentum_rank": 2,
            }

            candidates = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
            by_family = {}
            for candidate in candidates:
                by_family.setdefault(candidate.candidate_payload["baseline_family"], []).append(candidate)
            assert len(by_family["momentum_volume_expanded_pool"]) == 4
            assert len(by_family["llm_reject_only"]) == 3
            assert len(by_family["llm_reject_then_momentum_rank"]) == 2
            assert len(by_family["random_reject_then_momentum_rank"]) == 2
            assert all(candidate.round_id is not None for candidate in by_family["llm_reject_only"])
            assert all(candidate.round_id is not None for candidate in by_family["llm_reject_then_momentum_rank"])
            assert all(candidate.round_id is None for candidate in by_family["random_reject_then_momentum_rank"])
            assert by_family["llm_reject_only"][0].candidate_payload["rejection_design"] == "llm_reject_only_then_mechanical_momentum_rank"

            feedback = build_shortpick_replay_feedback(session, run_id=run_id)
            families = {family["baseline_family"]: family for family in feedback["families"]}
            assert families["llm_reject_only"]["label"] == "LLM只剔除保留池"
            assert families["llm_reject_then_momentum_rank"]["label"] == "LLM剔除后动量排序"
            assert families["random_reject_then_momentum_rank"]["label"] == "随机剔除后动量排序"

            rounds = session.scalars(
                select(ShortpickModelRound).where(ShortpickModelRound.run_id == run_id).order_by(ShortpickModelRound.round_index.asc())
            ).all()
            assert [round_row.round_index for round_row in rounds] == [1, 4]


def test_real_replay_llm_failure_does_not_fallback_to_diagnostic_proxy(monkeypatch) -> None:
    class FailingTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            raise RuntimeError("fixture LLM unavailable")

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FailingTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=2,
                candidate_limit=2,
            )
            run_id = payload["runs"][0]["id"]
            run = session.get(ShortpickExperimentRun, run_id)
            assert run is not None
            assert run.summary_payload["llm_executor_kind"] == "historical_replay_sealed_packet_llm"
            assert run.summary_payload["model_family"] == "deepseek:deepseek-fixture"
            rounds = session.scalars(select(ShortpickModelRound).where(ShortpickModelRound.run_id == run_id)).all()
            assert len(rounds) == 1
            assert rounds[0].status == "failed"
            assert rounds[0].executor_kind == "historical_replay_sealed_packet_llm"
            candidates = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
            assert candidates
            assert all(candidate.candidate_payload["baseline_family"] != "llm" for candidate in candidates)
            feedback = build_shortpick_replay_feedback(session, run_id=None)
            assert "diagnostic_proxy_llm" not in {family["baseline_family"] for family in feedback["families"]}


def test_replay_llm_prompt_excludes_rejected_future_sources(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            assert "测试半导体获得订单" in prompt
            assert "测试软件次日涨停" not in prompt
            assert "https://example.test/after" not in prompt
            assert "rej-001" not in prompt
            assert '"rejected_source_count": 1' in prompt
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": {
                        "symbol": "600003.SH",
                        "name": "测试半导体",
                        "theme": "半导体订单",
                        "thesis": "测试半导体在 sealed packet 中有订单进展来源支持。",
                        "sources_used": ["src-001"],
                        "evidence_mapping": {"thesis": ["src-001"]},
                    },
                    "candidates": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=1,
                candidate_limit=1,
            )


def test_replay_llm_rejected_or_packet_external_source_fails_audit(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": {
                        "symbol": "600004.SH",
                        "name": "测试软件",
                        "theme": "未来结果污染",
                        "thesis": "测试软件在 2026-05-06 出现涨停。",
                        "sources_used": ["rej-001", "src-999"],
                        "evidence_mapping": {"thesis": ["rej-001", "src-999"]},
                    },
                    "candidates": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=1,
                candidate_limit=1,
            )
            run_id = payload["runs"][0]["id"]
            llm_candidate = session.scalars(
                select(ShortpickCandidate).where(
                    ShortpickCandidate.run_id == run_id,
                    ShortpickCandidate.convergence_group == "llm",
                )
            ).one()
            reasons = set(llm_candidate.candidate_payload["leakage_audit_reasons"])
            assert llm_candidate.candidate_payload["leakage_audit_status"] == "fail"
            assert llm_candidate.candidate_payload["official_sample_eligible"] is False
            assert "source_after_cutoff" in reasons
            assert "source_not_in_packet" in reasons
            assert "unverified_source_time" in reasons
            assert "future_leakage_suspected" in reasons
            assert llm_candidate.candidate_payload["sources_used"] == ["rej-001", "src-999"]
            assert llm_candidate.sources_payload[0]["credibility_status"] == "rejected"


def test_replay_feedback_separates_strict_source_and_tradable_samples(monkeypatch) -> None:
    class FakeTransport:
        def complete(self, *, base_url, api_key, model_name, prompt, system=None, enable_search=False):
            assert enable_search is False
            return json.dumps(
                {
                    "as_of_date": "2026-05-05",
                    "information_mode": "historical_replay",
                    "primary_pick": {
                        "symbol": "600003.SH",
                        "name": "测试半导体",
                        "theme": "半导体订单",
                        "thesis": "测试半导体盘口走强，先作为行情快照候选。",
                        "sources_used": ["src-001"],
                        "evidence_mapping": {"thesis": ["src-001"]},
                    },
                    "candidates": [],
                },
                ensure_ascii=False,
            )

    monkeypatch.setenv("ASHARE_SHORTPICK_REPLAY_LLM_MODE", "real")
    monkeypatch.setattr(
        "ashare_evidence.shortpick_replay.route_model",
        lambda task: (FakeTransport(), "https://api.deepseek.test/anthropic", "test-key", "deepseek-fixture"),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'replay.db'}"
        init_database(database_url)
        _seed_replay_fixture(database_url)

        with session_scope(database_url) as session:
            payload = run_shortpick_historical_replay(
                session,
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                rounds=1,
                candidate_limit=1,
            )
            run_id = payload["runs"][0]["id"]
            llm_candidate = session.scalars(
                select(ShortpickCandidate).where(
                    ShortpickCandidate.run_id == run_id,
                    ShortpickCandidate.convergence_group == "llm",
                )
            ).one()
            candidate_payload = dict(llm_candidate.candidate_payload)
            candidate_payload["official_sample_eligible"] = False
            candidate_payload["leakage_audit_status"] = "fail"
            candidate_payload["leakage_audit_reasons"] = ["unsupported_claim"]
            llm_candidate.candidate_payload = candidate_payload
            session.flush()

            feedback = build_shortpick_replay_feedback(session, run_id=run_id)
            llm_family = next(family for family in feedback["families"] if family["baseline_family"] == "llm")
            five_day = next(group for group in llm_family["validation_by_horizon"] if str(group["group_key"]) == "5")

            assert llm_family["official_sample_count"] == 0
            assert llm_family["tradable_sample_count"] == 1
            assert five_day["completed_official_sample_count"] == 0
            assert five_day["completed_tradable_sample_count"] == 1
            assert five_day["mean_excess_return"] is None
            assert five_day["tradable_mean_excess_return"] is not None
