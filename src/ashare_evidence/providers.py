from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol

from ashare_evidence.lineage import build_lineage


@dataclass(frozen=True)
class EvidenceBundle:
    provider_name: str
    symbol: str
    stock: dict[str, Any]
    sectors: list[dict[str, Any]]
    sector_memberships: list[dict[str, Any]]
    market_bars: list[dict[str, Any]]
    news_items: list[dict[str, Any]]
    news_links: list[dict[str, Any]]
    feature_snapshots: list[dict[str, Any]]
    model_registry: dict[str, Any]
    model_version: dict[str, Any]
    prompt_version: dict[str, Any]
    model_run: dict[str, Any]
    model_results: list[dict[str, Any]]
    recommendation: dict[str, Any]
    recommendation_evidence: list[dict[str, Any]]
    paper_portfolios: list[dict[str, Any]]
    paper_orders: list[dict[str, Any]]
    paper_fills: list[dict[str, Any]]


class EvidenceProvider(Protocol):
    provider_name: str

    def build_bundle(self, symbol: str) -> EvidenceBundle:
        ...


PLANNED_LOW_COST_ROUTE = {
    "market_and_master": "Tushare Pro",
    "news_and_disclosure": "巨潮资讯/交易所披露",
    "feature_and_model": "Qlib",
    "prototype_gap_fill": "AkShare",
    "upgrade_reserve": "商业行情/资讯授权接口通过同一适配层接入",
}


def with_lineage(
    record: dict[str, Any],
    *,
    payload_key: str,
    source_uri: str,
    license_tag: str,
    usage_scope: str = "internal_research",
    redistribution_scope: str = "none",
) -> dict[str, Any]:
    if payload_key not in record:
        raise KeyError(f"Expected payload key '{payload_key}' in record.")
    return {
        **record,
        **build_lineage(
            record,
            source_uri=source_uri,
            license_tag=license_tag,
            usage_scope=usage_scope,
            redistribution_scope=redistribution_scope,
        ),
    }


class DemoLowCostRouteProvider:
    provider_name = "demo-low-cost-route"

    def build_bundle(self, symbol: str = "600519.SH") -> EvidenceBundle:
        if symbol != "600519.SH":
            raise ValueError("Demo provider currently only seeds 600519.SH.")

        tz = timezone.utc
        day_1 = datetime(2026, 4, 10, 7, 0, tzinfo=tz)
        day_2 = datetime(2026, 4, 13, 7, 0, tzinfo=tz)
        day_3 = datetime(2026, 4, 14, 7, 0, tzinfo=tz)
        generated_at = datetime(2026, 4, 14, 8, 5, tzinfo=tz)

        stock = with_lineage(
            {
                "symbol": "600519.SH",
                "ticker": "600519",
                "exchange": "SSE",
                "name": "贵州茅台",
                "provider_symbol": "600519.SH",
                "listed_date": date(2001, 8, 27),
                "status": "active",
                "profile_payload": {
                    "industry": "白酒",
                    "watchlist_scope": "一期自选股池",
                    "provider": "Tushare Pro",
                },
            },
            payload_key="profile_payload",
            source_uri="tushare://stock_basic/600519.SH",
            license_tag="tushare-pro",
            redistribution_scope="limited-display",
        )

        sectors = [
            with_lineage(
                {
                    "sector_code": "sw-food-beverage",
                    "name": "食品饮料",
                    "level": "industry",
                    "definition_payload": {"taxonomy": "申万一级", "provider": "Tushare Pro"},
                },
                payload_key="definition_payload",
                source_uri="tushare://index_member/sw-food-beverage",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
            with_lineage(
                {
                    "sector_code": "concept-core-consumption",
                    "name": "核心消费",
                    "level": "concept",
                    "definition_payload": {"taxonomy": "概念板块", "provider": "Tushare Pro"},
                },
                payload_key="definition_payload",
                source_uri="tushare://concept/core-consumption",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
        ]

        sector_memberships = [
            with_lineage(
                {
                    "membership_key": "membership-600519-sw-food-beverage",
                    "stock_symbol": "600519.SH",
                    "sector_code": "sw-food-beverage",
                    "effective_from": datetime(2020, 1, 1, tzinfo=tz),
                    "effective_to": None,
                    "is_primary": True,
                    "membership_payload": {"weighting_hint": "primary-industry"},
                },
                payload_key="membership_payload",
                source_uri="tushare://index_member/600519.SH/sw-food-beverage",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
            with_lineage(
                {
                    "membership_key": "membership-600519-core-consumption",
                    "stock_symbol": "600519.SH",
                    "sector_code": "concept-core-consumption",
                    "effective_from": datetime(2023, 1, 1, tzinfo=tz),
                    "effective_to": None,
                    "is_primary": False,
                    "membership_payload": {"weighting_hint": "theme"},
                },
                payload_key="membership_payload",
                source_uri="tushare://concept_member/600519.SH/core-consumption",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
        ]

        market_bars = [
            with_lineage(
                {
                    "bar_key": "bar-600519-20260410",
                    "stock_symbol": "600519.SH",
                    "timeframe": "1d",
                    "observed_at": day_1,
                    "open_price": 1682.0,
                    "high_price": 1703.0,
                    "low_price": 1675.0,
                    "close_price": 1696.5,
                    "volume": 26234.0,
                    "amount": 4465200000.0,
                    "turnover_rate": 0.21,
                    "adj_factor": 1.0,
                    "raw_payload": {"trade_date": "20260410", "provider": "Tushare Pro"},
                },
                payload_key="raw_payload",
                source_uri="tushare://daily/600519.SH?trade_date=20260410",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
            with_lineage(
                {
                    "bar_key": "bar-600519-20260413",
                    "stock_symbol": "600519.SH",
                    "timeframe": "1d",
                    "observed_at": day_2,
                    "open_price": 1698.0,
                    "high_price": 1718.0,
                    "low_price": 1690.0,
                    "close_price": 1711.2,
                    "volume": 25480.0,
                    "amount": 4351000000.0,
                    "turnover_rate": 0.2,
                    "adj_factor": 1.0,
                    "raw_payload": {"trade_date": "20260413", "provider": "Tushare Pro"},
                },
                payload_key="raw_payload",
                source_uri="tushare://daily/600519.SH?trade_date=20260413",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
            with_lineage(
                {
                    "bar_key": "bar-600519-20260414",
                    "stock_symbol": "600519.SH",
                    "timeframe": "1d",
                    "observed_at": day_3,
                    "open_price": 1710.0,
                    "high_price": 1735.0,
                    "low_price": 1705.0,
                    "close_price": 1728.6,
                    "volume": 28102.0,
                    "amount": 4823000000.0,
                    "turnover_rate": 0.23,
                    "adj_factor": 1.0,
                    "raw_payload": {"trade_date": "20260414", "provider": "Tushare Pro"},
                },
                payload_key="raw_payload",
                source_uri="tushare://daily/600519.SH?trade_date=20260414",
                license_tag="tushare-pro",
                redistribution_scope="limited-display",
            ),
        ]

        news_items = [
            with_lineage(
                {
                    "news_key": "news-annual-report-20260412",
                    "provider_name": "cninfo",
                    "external_id": "cninfo-20260412-annual",
                    "headline": "贵州茅台披露年报，经营现金流延续高质量增长",
                    "summary": "年报显示收入和经营现金流维持稳健，机构关注高端白酒需求韧性。",
                    "content_excerpt": "公司公告提到渠道库存总体平稳，直营占比继续优化。",
                    "published_at": datetime(2026, 4, 12, 12, 0, tzinfo=tz),
                    "event_scope": "stock",
                    "dedupe_key": "600519-annual-report-2026",
                    "raw_payload": {"provider": "巨潮资讯", "announcement_type": "annual_report"},
                },
                payload_key="raw_payload",
                source_uri="cninfo://announcements/600519/20260412-annual",
                license_tag="cninfo-public-disclosure",
                redistribution_scope="source-link-only",
            ),
            with_lineage(
                {
                    "news_key": "news-roadshow-20260414",
                    "provider_name": "cninfo",
                    "external_id": "cninfo-20260414-roadshow",
                    "headline": "机构调研关注高端白酒提价预期与渠道动销",
                    "summary": "调研纪要显示市场更关注五一前动销与吨价改善节奏。",
                    "content_excerpt": "管理层强调供需平衡和渠道健康优先于短期放量。",
                    "published_at": datetime(2026, 4, 14, 5, 30, tzinfo=tz),
                    "event_scope": "stock",
                    "dedupe_key": "600519-roadshow-20260414",
                    "raw_payload": {"provider": "巨潮资讯", "announcement_type": "investor_relation"},
                },
                payload_key="raw_payload",
                source_uri="cninfo://announcements/600519/20260414-roadshow",
                license_tag="cninfo-public-disclosure",
                redistribution_scope="source-link-only",
            ),
        ]

        news_links = [
            with_lineage(
                {
                    "news_key": "news-annual-report-20260412",
                    "entity_type": "stock",
                    "stock_symbol": "600519.SH",
                    "sector_code": None,
                    "market_tag": None,
                    "relevance_score": 0.92,
                    "impact_direction": "positive",
                    "effective_at": datetime(2026, 4, 12, 12, 0, tzinfo=tz),
                    "decay_half_life_hours": 96.0,
                    "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                },
                payload_key="mapping_payload",
                source_uri="pipeline://news-link/news-annual-report-20260412/stock/600519.SH",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "news_key": "news-roadshow-20260414",
                    "entity_type": "stock",
                    "stock_symbol": "600519.SH",
                    "sector_code": None,
                    "market_tag": None,
                    "relevance_score": 0.88,
                    "impact_direction": "positive",
                    "effective_at": datetime(2026, 4, 14, 5, 30, tzinfo=tz),
                    "decay_half_life_hours": 72.0,
                    "mapping_payload": {"layer": "stock", "dedupe_stage": "post-entity-map"},
                },
                payload_key="mapping_payload",
                source_uri="pipeline://news-link/news-roadshow-20260414/stock/600519.SH",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "news_key": "news-roadshow-20260414",
                    "entity_type": "sector",
                    "stock_symbol": None,
                    "sector_code": "sw-food-beverage",
                    "market_tag": None,
                    "relevance_score": 0.61,
                    "impact_direction": "positive",
                    "effective_at": datetime(2026, 4, 14, 5, 30, tzinfo=tz),
                    "decay_half_life_hours": 48.0,
                    "mapping_payload": {"layer": "sector", "dedupe_stage": "post-entity-map"},
                },
                payload_key="mapping_payload",
                source_uri="pipeline://news-link/news-roadshow-20260414/sector/sw-food-beverage",
                license_tag="internal-derived",
            ),
        ]

        feature_snapshots = [
            with_lineage(
                {
                    "snapshot_key": "feature-600519-20260414-wave-v1",
                    "stock_symbol": "600519.SH",
                    "feature_set_name": "wave_baseline",
                    "feature_set_version": "v1",
                    "as_of": day_3,
                    "window_start": datetime(2026, 3, 3, 7, 0, tzinfo=tz),
                    "window_end": day_3,
                    "feature_values": {
                        "ret_20d": 0.074,
                        "volatility_20d": 0.129,
                        "volume_zscore_10d": 1.11,
                        "news_positive_decay_7d": 0.67,
                        "sector_strength_10d": 0.42,
                    },
                    "upstream_refs": [
                        {"type": "market_bar", "key": "bar-600519-20260414"},
                        {"type": "news_item", "key": "news-roadshow-20260414"},
                    ],
                },
                payload_key="feature_values",
                source_uri="qlib://features/600519.SH?as_of=2026-04-14",
                license_tag="qlib-derived",
            ),
        ]

        model_registry = with_lineage(
            {
                "name": "qlib_wave_gbdt",
                "family": "gradient_boosting",
                "description": "2-8 周波段基线模型，融合价格、量能、板块与新闻衰减特征。",
                "registry_payload": {"framework": "Qlib", "owner": "research"},
            },
            payload_key="registry_payload",
            source_uri="model://registry/qlib_wave_gbdt",
            license_tag="internal-derived",
        )

        model_version = with_lineage(
            {
                "version": "2026.04.14-r1",
                "validation_scheme": "rolling_time_window",
                "training_window_start": datetime(2022, 1, 1, tzinfo=tz),
                "training_window_end": datetime(2026, 3, 31, tzinfo=tz),
                "artifact_uri": "s3://artifacts/models/qlib_wave_gbdt/2026.04.14-r1",
                "config_payload": {
                    "horizon_days": [14, 28, 56],
                    "universe": "watchlist",
                    "feature_set": "wave_baseline:v1",
                },
            },
            payload_key="config_payload",
            source_uri="model://version/qlib_wave_gbdt/2026.04.14-r1",
            license_tag="internal-derived",
        )

        prompt_version = with_lineage(
            {
                "name": "balanced_advice_prompt",
                "version": "v1",
                "risk_disclaimer": "建议仅在证据充分且信号一致时输出，否则降级为风险提示。",
                "prompt_payload": {
                    "system_prompt": "你是一名审慎的 A 股波段研究助手，必须引用结构化证据。",
                    "user_template": "基于模型结果、新闻和板块证据，为股票生成方向与风险提示。",
                },
            },
            payload_key="prompt_payload",
            source_uri="prompt://balanced_advice_prompt/v1",
            license_tag="internal-prompt",
        )

        model_run = with_lineage(
            {
                "run_key": "run-qlib-wave-20260414-close",
                "started_at": datetime(2026, 4, 14, 7, 10, tzinfo=tz),
                "finished_at": datetime(2026, 4, 14, 7, 25, tzinfo=tz),
                "run_status": "completed",
                "target_scope": "watchlist",
                "metrics_payload": {
                    "direction_hit_rate": 0.59,
                    "max_drawdown": -0.13,
                    "cost_adjusted_return": 0.18,
                },
                "input_refs": [
                    {"type": "feature_snapshot", "key": "feature-600519-20260414-wave-v1"},
                    {"type": "news_item", "key": "news-roadshow-20260414"},
                ],
            },
            payload_key="metrics_payload",
            source_uri="model://run/qlib_wave_gbdt/run-qlib-wave-20260414-close",
            license_tag="internal-derived",
        )

        model_results = [
            with_lineage(
                {
                    "result_key": "result-600519-20260414-28d",
                    "stock_symbol": "600519.SH",
                    "as_of_data_time": day_3,
                    "valid_until": datetime(2026, 4, 28, 7, 0, tzinfo=tz),
                    "forecast_horizon_days": 28,
                    "predicted_direction": "buy",
                    "expected_return": 0.086,
                    "confidence_score": 0.72,
                    "confidence_bucket": "medium_high",
                    "driver_factors": [
                        "中期收益动量改善",
                        "新闻正向衰减得分抬升",
                        "板块相对强度转正",
                    ],
                    "risk_factors": ["估值仍偏高", "消费复苏若回落会削弱胜率"],
                    "result_payload": {"feature_snapshot_key": "feature-600519-20260414-wave-v1"},
                },
                payload_key="result_payload",
                source_uri="model://result/qlib_wave_gbdt/run-qlib-wave-20260414-close/600519.SH",
                license_tag="internal-derived",
            ),
        ]

        recommendation = with_lineage(
            {
                "recommendation_key": "reco-600519-20260414-balanced",
                "stock_symbol": "600519.SH",
                "as_of_data_time": day_3,
                "generated_at": generated_at,
                "direction": "buy",
                "confidence_score": 0.68,
                "confidence_label": "中高",
                "horizon_min_days": 14,
                "horizon_max_days": 56,
                "evidence_status": "sufficient",
                "summary": "量价趋势与公告/调研证据共振，维持 2-8 周波段偏积极建议。",
                "core_drivers": [
                    "20 日收益改善且量能放大",
                    "公告与调研纪要提供基本面和渠道证据",
                    "板块强度改善，未见明显冲突信号",
                ],
                "risk_flags": [
                    "高端消费复苏若低于预期，建议需降级",
                    "若后续公告证据不足，LLM 解释不得单独抬高建议强度",
                ],
                "degrade_reason": None,
                "recommendation_payload": {
                    "llm_summary_version": "balanced_advice_prompt:v1",
                    "policy": "evidence-first",
                },
            },
            payload_key="recommendation_payload",
            source_uri="recommendation://balanced_advice_prompt/v1/reco-600519-20260414-balanced",
            license_tag="internal-derived",
        )

        recommendation_evidence = [
            with_lineage(
                {
                    "evidence_type": "model_result",
                    "reference_key": "result-600519-20260414-28d",
                    "role": "primary_driver",
                    "rank": 1,
                    "evidence_label": "Qlib 28 日方向预测",
                    "snippet": "结构化模型输出为 buy，置信度 0.72。",
                    "reference_payload": {"evidence_key": "result-600519-20260414-28d"},
                },
                payload_key="reference_payload",
                source_uri="pipeline://recommendation-evidence/reco-600519-20260414-balanced/model_result/result-600519-20260414-28d",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "evidence_type": "feature_snapshot",
                    "reference_key": "feature-600519-20260414-wave-v1",
                    "role": "primary_driver",
                    "rank": 2,
                    "evidence_label": "波段特征快照",
                    "snippet": "ret_20d、量能 z-score 和新闻衰减分数同步改善。",
                    "reference_payload": {"evidence_key": "feature-600519-20260414-wave-v1"},
                },
                payload_key="reference_payload",
                source_uri="pipeline://recommendation-evidence/reco-600519-20260414-balanced/feature_snapshot/feature-600519-20260414-wave-v1",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "evidence_type": "news_item",
                    "reference_key": "news-roadshow-20260414",
                    "role": "supporting_context",
                    "rank": 3,
                    "evidence_label": "调研纪要",
                    "snippet": "渠道动销和供需平衡表述为积极信号，但仍需跟踪兑现。",
                    "reference_payload": {"evidence_key": "news-roadshow-20260414"},
                },
                payload_key="reference_payload",
                source_uri="pipeline://recommendation-evidence/reco-600519-20260414-balanced/news_item/news-roadshow-20260414",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "evidence_type": "market_bar",
                    "reference_key": "bar-600519-20260414",
                    "role": "supporting_context",
                    "rank": 4,
                    "evidence_label": "最新日线行情",
                    "snippet": "收盘价创近月新高，成交额同步放大。",
                    "reference_payload": {"evidence_key": "bar-600519-20260414"},
                },
                payload_key="reference_payload",
                source_uri="pipeline://recommendation-evidence/reco-600519-20260414-balanced/market_bar/bar-600519-20260414",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "evidence_type": "sector_membership",
                    "reference_key": "membership-600519-sw-food-beverage",
                    "role": "supporting_context",
                    "rank": 5,
                    "evidence_label": "行业归属",
                    "snippet": "食品饮料主行业映射用于板块强度聚合。",
                    "reference_payload": {"evidence_key": "membership-600519-sw-food-beverage"},
                },
                payload_key="reference_payload",
                source_uri="pipeline://recommendation-evidence/reco-600519-20260414-balanced/sector_membership/membership-600519-sw-food-beverage",
                license_tag="internal-derived",
            ),
        ]

        paper_portfolios = [
            with_lineage(
                {
                    "portfolio_key": "portfolio-manual-sandbox",
                    "name": "手动模拟仓",
                    "mode": "manual",
                    "benchmark_symbol": "000300.SH",
                    "base_currency": "CNY",
                    "cash_balance": 500000.0,
                    "status": "active",
                    "portfolio_payload": {"purpose": "manual-paper-trade"},
                },
                payload_key="portfolio_payload",
                source_uri="simulation://portfolio/manual-sandbox",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "portfolio_key": "portfolio-auto-wave",
                    "name": "模型自动持仓模拟仓",
                    "mode": "auto_model",
                    "benchmark_symbol": "000300.SH",
                    "base_currency": "CNY",
                    "cash_balance": 800000.0,
                    "status": "active",
                    "portfolio_payload": {"purpose": "auto-model-portfolio"},
                },
                payload_key="portfolio_payload",
                source_uri="simulation://portfolio/auto-wave",
                license_tag="internal-derived",
            ),
        ]

        paper_orders = [
            with_lineage(
                {
                    "order_key": "order-manual-600519-20260414",
                    "portfolio_key": "portfolio-manual-sandbox",
                    "stock_symbol": "600519.SH",
                    "recommendation_key": "reco-600519-20260414-balanced",
                    "order_source": "manual",
                    "side": "buy",
                    "requested_at": generated_at,
                    "quantity": 100,
                    "order_type": "limit",
                    "limit_price": 1730.0,
                    "status": "filled",
                    "notes": "研究员手动跟随建议建仓。",
                    "order_payload": {"execution_mode": "manual"},
                },
                payload_key="order_payload",
                source_uri="simulation://order/manual/600519/20260414",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "order_key": "order-auto-600519-20260414",
                    "portfolio_key": "portfolio-auto-wave",
                    "stock_symbol": "600519.SH",
                    "recommendation_key": "reco-600519-20260414-balanced",
                    "order_source": "model",
                    "side": "buy",
                    "requested_at": generated_at,
                    "quantity": 200,
                    "order_type": "market",
                    "limit_price": None,
                    "status": "filled",
                    "notes": "模型组合按目标权重自动调仓。",
                    "order_payload": {"execution_mode": "auto_model"},
                },
                payload_key="order_payload",
                source_uri="simulation://order/auto/600519/20260414",
                license_tag="internal-derived",
            ),
        ]

        paper_fills = [
            with_lineage(
                {
                    "fill_key": "fill-manual-600519-20260414",
                    "order_key": "order-manual-600519-20260414",
                    "stock_symbol": "600519.SH",
                    "filled_at": generated_at,
                    "price": 1729.5,
                    "quantity": 100,
                    "fee": 8.65,
                    "tax": 0.0,
                    "slippage_bps": 3.2,
                    "fill_payload": {"matching_rule": "t+1-paper"},
                },
                payload_key="fill_payload",
                source_uri="simulation://fill/manual/600519/20260414",
                license_tag="internal-derived",
            ),
            with_lineage(
                {
                    "fill_key": "fill-auto-600519-20260414",
                    "order_key": "order-auto-600519-20260414",
                    "stock_symbol": "600519.SH",
                    "filled_at": generated_at,
                    "price": 1731.1,
                    "quantity": 200,
                    "fee": 17.31,
                    "tax": 0.0,
                    "slippage_bps": 4.1,
                    "fill_payload": {"matching_rule": "t+1-paper"},
                },
                payload_key="fill_payload",
                source_uri="simulation://fill/auto/600519/20260414",
                license_tag="internal-derived",
            ),
        ]

        return EvidenceBundle(
            provider_name=self.provider_name,
            symbol=symbol,
            stock=stock,
            sectors=sectors,
            sector_memberships=sector_memberships,
            market_bars=market_bars,
            news_items=news_items,
            news_links=news_links,
            feature_snapshots=feature_snapshots,
            model_registry=model_registry,
            model_version=model_version,
            prompt_version=prompt_version,
            model_run=model_run,
            model_results=model_results,
            recommendation=recommendation,
            recommendation_evidence=recommendation_evidence,
            paper_portfolios=paper_portfolios,
            paper_orders=paper_orders,
            paper_fills=paper_fills,
        )
