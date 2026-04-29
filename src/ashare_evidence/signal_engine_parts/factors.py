from __future__ import annotations

from math import log, sqrt, tanh
from statistics import mean
from typing import Any

from ashare_evidence.phase2 import PHASE2_MANUAL_REVIEW_NOTE
from ashare_evidence.signal_engine_parts.base import (
    MANUAL_REVIEW_PLACEHOLDER,
    clip,
    factor_direction,
    pct_change,
    safe_pstdev,
    score_scale,
)


def primary_sector_membership(
    sector_memberships: list[dict[str, Any]],
    as_of_data_time,
) -> dict[str, Any] | None:
    effective = [
        item
        for item in sector_memberships
        if item["effective_from"] <= as_of_data_time
        and (item.get("effective_to") is None or item["effective_to"] >= as_of_data_time)
    ]
    effective.sort(key=lambda item: (not item["is_primary"], item["effective_from"]))
    return effective[0] if effective else None


def active_sector_codes(
    sector_memberships: list[dict[str, Any]],
    as_of_data_time,
) -> set[str]:
    return {
        item["sector_code"]
        for item in sector_memberships
        if item["effective_from"] <= as_of_data_time
        and (item.get("effective_to") is None or item["effective_to"] >= as_of_data_time)
    }


def _lagged_return(closes: list[float], horizon: int) -> tuple[float, int]:
    lag = min(horizon, max(len(closes) - 1, 1))
    return pct_change(closes[-1], closes[-(lag + 1)]), lag


# Default scale parameters used as fallback when cross-sectional context unavailable.
# These are calibrated on typical A-share daily return distributions (2015-2025).
_DEFAULT_RET_SCALE = {"ret_10d": 0.08, "ret_20d": 0.12, "ret_40d": 0.18}
_DEFAULT_VOL_MEDIAN = 0.28  # typical A-share annualized vol ~28%
_DEFAULT_VOL_MAD = 0.10


def compute_price_factor(
    market_bars: list[dict[str, Any]],
    *,
    cross_sectional_stats: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Compute price baseline factor from daily market bars.

    Args:
        market_bars: Sorted list of daily OHLCV bars (ascending observed_at).
        cross_sectional_stats: Optional dict mapping feature_name -> {median, mad}
            for cross-sectional normalization. When provided, features are z-scored
            against the watchlist universe instead of using hardcoded scale params.
    """
    cs = cross_sectional_stats or {}
    closes = [float(item["close_price"]) for item in market_bars]
    highs = [float(item["high_price"]) for item in market_bars]
    volumes = [float(item["volume"]) for item in market_bars]
    turnovers = [float(item.get("turnover_rate") or 0.0) for item in market_bars]
    returns = [pct_change(closes[idx], closes[idx - 1]) for idx in range(1, len(closes))]

    ret_10d, lookback_10d = _lagged_return(closes, 10)
    ret_20d, lookback_20d = _lagged_return(closes, 20)
    ret_40d, lookback_40d = _lagged_return(closes, 40)
    vol_20d = safe_pstdev(returns[-20:]) * sqrt(20)
    avg_volume_5d = mean(volumes[-5:])
    avg_volume_20d = mean(volumes[-20:])
    volume_zscore_5d = (avg_volume_5d - avg_volume_20d) / (safe_pstdev(volumes[-20:]) or 1.0)
    turnover_5d = mean(turnovers[-5:])
    turnover_20d = mean(turnovers[-20:])
    turnover_gap_5d = turnover_5d - turnover_20d
    close_vs_40d_high = closes[-1] / max(highs[-40:]) - 1
    up_day_ratio_10d = sum(1 for value in returns[-10:] if value > 0) / 10
    drawdown_20d = closes[-1] / max(closes[-20:]) - 1

    # Trend component: use cross-sectional stats when available, else hardcoded defaults
    ret_10d_scale = cs.get("ret_10d", {}).get("mad", 0) * 1.5 or _DEFAULT_RET_SCALE["ret_10d"]
    ret_20d_scale = cs.get("ret_20d", {}).get("mad", 0) * 1.5 or _DEFAULT_RET_SCALE["ret_20d"]
    ret_40d_scale = cs.get("ret_40d", {}).get("mad", 0) * 1.5 or _DEFAULT_RET_SCALE["ret_40d"]
    trend_component = clip(
        0.25 * score_scale(ret_10d, ret_10d_scale)
        + 0.45 * score_scale(ret_20d, ret_20d_scale)
        + 0.30 * score_scale(ret_40d, ret_40d_scale),
    )

    confirmation_component = clip(
        0.35 * score_scale(volume_zscore_5d, 1.5)
        + 0.25 * score_scale(turnover_gap_5d, cs.get("turnover_gap_5d", {}).get("mad", 0) * 1.5 or 0.02)
        + 0.20 * score_scale(up_day_ratio_10d - 0.5, 0.18)
        + 0.20 * score_scale(close_vs_40d_high, cs.get("close_vs_40d_high", {}).get("mad", 0) * 1.5 or 0.03),
    )

    # Risk pressure: use cross-sectional median volatility instead of hardcoded 0.08
    vol_median = cs.get("volatility_20d", {}).get("median", 0) or _DEFAULT_VOL_MEDIAN
    vol_mad = cs.get("volatility_20d", {}).get("mad", 0) or _DEFAULT_VOL_MAD
    vol_excess = max(vol_20d - vol_median, 0.0)
    risk_pressure = clip(
        0.55 * score_scale(vol_excess, vol_mad * 1.5 or 0.05)
        + 0.45 * score_scale(abs(min(drawdown_20d, 0.0)), 0.08),
        0.0,
        1.0,
    )
    price_score = clip(0.60 * trend_component + 0.25 * confirmation_component - 0.15 * risk_pressure)

    drivers: list[str] = []
    risks: list[str] = []
    if ret_20d > 0.05:
        drivers.append(f"20 日收益提升至 {ret_20d:.1%}，中枢趋势仍偏多。")
    if ret_40d > 0.10:
        drivers.append(f"40 日累计收益达到 {ret_40d:.1%}，中期趋势延续。")
    if volume_zscore_5d > 0.8:
        drivers.append(f"近 5 日量能相对 20 日均值抬升 {volume_zscore_5d:.2f}σ。")
    if up_day_ratio_10d >= 0.6:
        drivers.append(f"近 10 个交易日上涨占比 {up_day_ratio_10d:.0%}，短期确认仍在。")

    if vol_20d > vol_median + vol_mad * 0.5:
        risks.append(f"20 日波动率 {vol_20d:.1%} 高于截面中位数 {vol_median:.1%}，回撤容忍度要收紧。")
    if drawdown_20d < -0.06:
        risks.append("价格已明显跌离近 20 日中枢，趋势延续概率下降。")
    if close_vs_40d_high < -0.05:
        risks.append("收盘价偏离近 40 日高点较大，追价性价比下降。")
    if turnover_gap_5d < -0.01:
        risks.append("换手率回落，若量能不能延续，价格基线会优先转弱。")
    if not risks:
        risks.append("若 10 日与 20 日动量同时回落至零轴下方，价格基线会先行降级。")

    feature_values = {
        "ret_10d": round(ret_10d, 4),
        "ret_10d_lookback_days": lookback_10d,
        "ret_20d": round(ret_20d, 4),
        "ret_20d_lookback_days": lookback_20d,
        "ret_40d": round(ret_40d, 4),
        "ret_40d_lookback_days": lookback_40d,
        "volatility_20d": round(vol_20d, 4),
        "volume_zscore_5d": round(volume_zscore_5d, 4),
        "turnover_gap_5d": round(turnover_gap_5d, 4),
        "close_vs_40d_high": round(close_vs_40d_high, 4),
        "up_day_ratio_10d": round(up_day_ratio_10d, 4),
        "drawdown_20d": round(drawdown_20d, 4),
        "trend_component": round(trend_component, 4),
        "confirmation_component": round(confirmation_component, 4),
        "risk_pressure": round(risk_pressure, 4),
        "price_baseline_score": round(price_score, 4),
    }

    # Confidence: based on trend-confirmation agreement + volatility regime + data sufficiency.
    # No longer a linear transform of abs(score) — this provides orthogonal information.
    trend_confirm_agree = 0.0
    if trend_component > 0 and confirmation_component > 0:
        trend_confirm_agree = 0.12
    elif trend_component < 0 and confirmation_component < 0:
        trend_confirm_agree = 0.08
    low_vol_bonus = 0.08 if vol_20d < vol_median else 0.0
    data_suff = 0.05 if len(market_bars) >= 40 else 0.0
    confidence_score = clip(0.4 + trend_confirm_agree + low_vol_bonus + data_suff, 0.15, 0.85)

    return {
        "score": round(price_score, 4),
        "direction": factor_direction(price_score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[-(lookback_40d + 1)]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(market_bars),
        "latest_bar_key": market_bars[-1]["bar_key"],
    }


def _llm_summary_for_key(news_key: str, item_by_key: dict[str, dict[str, Any]]) -> str | None:
    item = item_by_key.get(news_key)
    if not item:
        return None
    llm = (item.get("raw_payload") or {}).get("llm_analysis")
    if isinstance(llm, dict) and not llm.get("_fallback"):
        summary = llm.get("summary_sentence", "").strip()
        if summary:
            return summary
    return None


def _news_driver_texts(
    events: list[dict[str, Any]],
    item_by_key: dict[str, dict[str, Any]],
) -> list[str]:
    texts: list[str] = []
    for event in events:
        llm_summary = _llm_summary_for_key(event["news_key"], item_by_key)
        if llm_summary:
            texts.append(f"公告解读：{llm_summary}")
        else:
            texts.append(f"{event['headline']} 提供正向事件证据。")
    return texts


def _news_risk_texts(
    events: list[dict[str, Any]],
    item_by_key: dict[str, dict[str, Any]],
) -> list[str]:
    texts: list[str] = []
    for event in events:
        llm_summary = _llm_summary_for_key(event["news_key"], item_by_key)
        if llm_summary:
            texts.append(f"风险公告：{llm_summary}")
        else:
            texts.append(f"{event['headline']} 仍是潜在反向事件。")
    return texts


def compute_news_factor(
    *,
    symbol: str,
    as_of_data_time,
    news_items: list[dict[str, Any]],
    news_links: list[dict[str, Any]],
    sector_codes: set[str],
) -> dict[str, Any]:
    item_by_key = {item["news_key"]: item for item in news_items}
    deduped: dict[str, dict[str, Any]] = {}
    for item in sorted(news_items, key=lambda value: value["published_at"], reverse=True):
        deduped.setdefault(item["dedupe_key"], item)

    link_groups: dict[str, list[dict[str, Any]]] = {}
    for link in news_links:
        if link["effective_at"] > as_of_data_time:
            continue
        item = item_by_key.get(link["news_key"])
        if item is None or deduped.get(item["dedupe_key"], {}).get("news_key") != link["news_key"]:
            continue
        if link["entity_type"] == "stock" and link.get("stock_symbol") == symbol:
            link_groups.setdefault(link["news_key"], []).append(link)
        elif link["entity_type"] == "sector" and link.get("sector_code") in sector_codes:
            link_groups.setdefault(link["news_key"], []).append(link)
        elif link["entity_type"] == "market":
            link_groups.setdefault(link["news_key"], []).append(link)

    event_contributions: list[dict[str, Any]] = []
    for news_key, links in link_groups.items():
        item = item_by_key[news_key]
        total = 0.0
        for link in links:
            age_hours = max((as_of_data_time - link["effective_at"]).total_seconds() / 3600, 0.0)
            decay = 0.5 ** (age_hours / max(float(link["decay_half_life_hours"]), 1.0))
            scope_weight = {"stock": 1.0, "sector": 0.7, "market": 0.35}.get(link["entity_type"], 0.0)
            direction_sign = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}.get(link["impact_direction"], 0.0)
            total += direction_sign * float(link["relevance_score"]) * scope_weight * decay
        event_contributions.append(
            {
                "news_key": news_key,
                "headline": item["headline"],
                "published_at": item["published_at"],
                "score": round(total, 4),
            }
        )

    event_contributions.sort(key=lambda item: abs(item["score"]), reverse=True)
    positive_total = sum(item["score"] for item in event_contributions if item["score"] > 0)
    negative_total = -sum(item["score"] for item in event_contributions if item["score"] < 0)
    gross_total = positive_total + negative_total
    conflict_ratio = round(min(positive_total, negative_total) / gross_total, 4) if gross_total else 0.0
    freshness_hours = (
        min((as_of_data_time - item["published_at"]).total_seconds() / 3600 for item in deduped.values())
        if deduped
        else 999.0
    )
    # Score scale 0.45 aligns with price factor's typical output range.
    # At net_contribution=0.3: tanh(0.3/0.45) ≈ 0.58 (vs price ~0.40-0.70).
    # Bonuses are now sign-aware: neutral net direction -> no bonus.
    net_dir = 1 if positive_total > negative_total else (-1 if negative_total > positive_total else 0)
    freshness_bonus = (0.08 if freshness_hours <= 72 else 0.0) * net_dir
    coverage_bonus = min(len(event_contributions), 4) * 0.03 * net_dir
    news_score = clip(
        score_scale(positive_total - negative_total, 0.45)
        + freshness_bonus
        + coverage_bonus
        - conflict_ratio * 0.28,
    )

    positive_events = [item for item in event_contributions if item["score"] > 0]
    negative_events = [item for item in event_contributions if item["score"] < 0]
    drivers = _news_driver_texts(positive_events[:2], item_by_key)
    risks = _news_risk_texts(negative_events[:2], item_by_key)
    if conflict_ratio >= 0.25:
        risks.append(f"正负事件冲突度 {conflict_ratio:.0%}，新闻因子不能单独抬高建议强度。")
    if not drivers:
        drivers.append("近 7 日缺少高相关正向事件，新闻因子暂未形成加分。")
    if not risks:
        risks.append("若 7 日内出现负向公告或行业监管扰动，新闻因子会优先转负。")

    feature_values = {
        "news_event_score": round(news_score, 4),
        "deduped_event_count": len(event_contributions),
        "positive_decay_total": round(positive_total, 4),
        "negative_decay_total": round(negative_total, 4),
        "conflict_ratio": conflict_ratio,
        "freshness_hours": round(freshness_hours, 2),
        "event_keys": [item["news_key"] for item in event_contributions[:4]],
    }
    # Confidence: based on evidence quantity, recency, consensus, not on abs(score).
    coverage_c = min(len(event_contributions), 6) / 6 * 0.20  # more events = more confidence (up to 0.20)
    recency_c = max(0.0, (1.0 - freshness_hours / 168)) * 0.15  # fresher = more confidence (up to 0.15)
    consensus_c = max(0.0, (1.0 - conflict_ratio * 2.0)) * 0.15  # less conflict = more confidence (up to 0.15)
    confidence_score = clip(0.30 + coverage_c + recency_c + consensus_c, 0.10, 0.80)
    return {
        "score": round(news_score, 4),
        "direction": factor_direction(news_score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": min(item["published_at"] for item in deduped.values()) if deduped else as_of_data_time,
        "window_end": as_of_data_time,
        "evidence_count": len(event_contributions),
        "primary_news_key": positive_events[0]["news_key"] if positive_events else (event_contributions[0]["news_key"] if event_contributions else None),
        "conflict_ratio": conflict_ratio,
    }


def compute_fundamental_factor(
    *,
    financial_snapshot: dict[str, Any] | None,
    financial_trends: dict[str, Any] | None,
    financial_llm: dict[str, Any] | None,
) -> dict[str, Any]:
    if not financial_trends or not financial_trends.get("available"):
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["基本面数据暂不可用，当前不参与评分。"],
            "risks": [],
            "feature_values": {"fundamental_score": 0.0, "available": False},
            "evidence_count": 0,
            "weight": 0.0,
        }

    composite = float(financial_trends["composite_score"])
    llm_verdict = None
    drivers: list[str] = []
    risks: list[str] = []

    if financial_llm and not financial_llm.get("_fallback"):
        llm_verdict = financial_llm.get("verdict")
        for d in (financial_llm.get("key_drivers") or [])[:2]:
            drivers.append(f"基本面亮点：{d}")
        for r in (financial_llm.get("key_risks") or [])[:2]:
            risks.append(f"基本面风险：{r}")
        summary = financial_llm.get("summary_sentence", "").strip()
        if summary and not drivers:
            drivers.append(f"基本面评估：{summary}")

    if not drivers:
        if composite > 0.15:
            drivers.append("财务趋势记分卡偏正面，营收、利润或ROE表现优于基准。")
        elif composite < -0.15:
            drivers.append("财务趋势记分卡偏负面，关注营收增速与现金流质量。")

    if not risks:
        if composite < 0.05:
            risks.append("财务指标存在改善空间，若持续恶化将拖累中期判断。")
        if financial_snapshot:
            cf = financial_snapshot.get("operating_cashflow_per_share") or financial_snapshot.get("operating_cashflow")
            eps = financial_snapshot.get("eps") or financial_snapshot.get("basic_eps")
            if cf and eps and float(cf) < float(eps) * 0.3:
                risks.append("经营现金流明显低于每股收益，盈利质量需关注。")

    if llm_verdict:
        verdict_score = {"positive": 0.5, "negative": -0.5, "mixed": 0.0, "neutral": 0.0}.get(llm_verdict, 0.0)
    else:
        verdict_score = 0.0
    adjusted_score = clip(composite * 0.7 + verdict_score * 0.3)

    feature_values = {
        "fundamental_score": round(adjusted_score, 4),
        "composite_trend_score": composite,
        "growth_quality": financial_trends.get("growth_quality", 0),
        "profitability_quality": financial_trends.get("profitability_quality", 0),
        "cash_flow_quality": financial_trends.get("cash_flow_quality", 0),
        "available": True,
        "llm_verdict": llm_verdict,
    }

    # Confidence: based on data availability + LLM validation, not abs(score).
    data_c = 0.15 if financial_trends.get("available") else 0.0
    llm_c = 0.15 if llm_verdict else 0.0
    composite_abs = abs(float(financial_trends.get("composite_score", 0)))
    trend_strength_c = min(composite_abs, 0.3) * 0.4  # stronger financial trend = more confidence
    confidence = clip(0.25 + data_c + llm_c + trend_strength_c, 0.10, 0.75)

    return {
        "score": round(adjusted_score, 4),
        "direction": factor_direction(adjusted_score),
        "confidence_score": round(confidence, 4),
        "drivers": drivers[:2],
        "risks": risks[:2],
        "feature_values": feature_values,
        "evidence_count": 1 if financial_trends.get("available") else 0,
        "weight": 0.20,
    }


def compute_manual_review_layer(price_factor: dict[str, Any], news_factor: dict[str, Any]) -> dict[str, Any]:
    feature_values = {
        "manual_review_score": 0.0,
        "status": MANUAL_REVIEW_PLACEHOLDER["status"],
        "note": MANUAL_REVIEW_PLACEHOLDER["note"],
        "input_evidence_count": price_factor["evidence_count"] + news_factor["evidence_count"],
    }
    return {
        "score": 0.0,
        "direction": "neutral",
        "confidence_score": 0.0,
        "drivers": [PHASE2_MANUAL_REVIEW_NOTE],
        "risks": ["当前未接入经验证的手动研究产物，系统不会把语言模型输出计入核心建议。"],
        "feature_values": feature_values,
        "evidence_count": price_factor["evidence_count"] + news_factor["evidence_count"],
        "weight": 0.0,
        "status": MANUAL_REVIEW_PLACEHOLDER["status"],
        "calibration": MANUAL_REVIEW_PLACEHOLDER,
    }


def compute_size_factor(
    market_bars: list[dict[str, Any]],
    *,
    cross_sectional_stats: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Compute size (market cap) factor based on Fama-French (1993) small-cap premium.

    Academic basis:
      - Fama & French (1993): Common risk factors in the returns on stocks and bonds.
      - Liu, Stambaugh & Yuan (2019): Size and value in China (A-share small-cap premium).

    NOTE: Size premium is a LONG-TERM factor. It takes months to years for the
    small-cap premium to materialize. DO NOT use this as a short-term timing signal.
    The score reflects a structural tilt, not a tactical call.
    """
    if not market_bars:
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["缺乏行情数据，市值因子暂不参与评分。"],
            "risks": [],
            "feature_values": {"size_score": 0.0, "available": False},
            "evidence_count": 0,
        }

    latest = market_bars[-1]
    total_mv = latest.get("total_mv")
    if total_mv is None:
        total_mv = latest.get("circ_mv")

    if total_mv is None or total_mv <= 0:
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["市值数据暂不可用，当前不参与评分。注意：市值因子是长期结构性因子，不适用于短线择时。"],
            "risks": ["若 tushare daily_basic 接口未覆盖该标的，市值数据将持续缺失。"],
            "feature_values": {"size_score": 0.0, "available": False, "total_mv": None, "circ_mv": None},
            "evidence_count": 0,
        }

    log_mcap = log(total_mv)

    cs = cross_sectional_stats or {}
    if "log_mcap" in cs:
        median = cs["log_mcap"].get("median", 0)
        mad = cs["log_mcap"].get("mad", 1) or 1
        normalized = (log_mcap - median) / mad
    else:
        # Without cross-sectional context, use hardcoded reference for A-shares.
        # Median log(market cap) for A-shares is approximately ln(50亿) ~ ln(500000万) = 13.12.
        # MAD is approximately 1.2 (one order of magnitude spread).
        median = 13.12
        mad = 1.2
        normalized = (log_mcap - median) / mad

    # Negative sign: smaller market cap -> positive score (small-cap premium)
    score = float(clip(-tanh(normalized)))
    confidence_score = clip(0.35 + abs(score) * 0.20, 0.0, 0.70)

    total_mv_label = _format_mv(total_mv)
    drivers: list[str] = []
    risks: list[str] = []
    if total_mv is not None:
        if score > 0.15:
            drivers.append(
                f"总市值 {total_mv_label}，相对 A 股中位数偏小，小市值溢价作为长期结构性加分。"
            )
        elif score < -0.15:
            drivers.append(
                f"总市值 {total_mv_label}，相对 A 股中位数偏大，大盘股长期溢价有限。"
            )
        else:
            drivers.append(
                f"总市值 {total_mv_label}，接近 A 股中位数水平，市值因子暂无明显倾斜。"
            )
    drivers.append("注意：市值因子是长期结构性因子，建议持仓期 6 个月以上才纳入考量，不适用于短线择时。")

    if total_mv is not None and total_mv < 100000:
        risks.append("小微市值标的流动性风险较高，波幅可能超出模型预期。")
    elif total_mv is not None and total_mv > 10000000:
        risks.append("超大市值标的弹性有限，趋势行情中超额收益空间可能受限。")
    else:
        risks.append("市值信号需要结合价格趋势和流动性判断才能转化为有效建议。")

    feature_values = {
        "size_score": round(score, 4),
        "available": True,
        "total_mv": total_mv,
        "circ_mv": latest.get("circ_mv"),
        "log_mcap": round(log_mcap, 4),
        "normalized_log_mcap": round(normalized, 4),
    }

    return {
        "score": round(score, 4),
        "direction": factor_direction(score),
        "confidence_score": round(confidence_score, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[0]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": 1,
        "weight": 0.10,
    }


def _format_mv(mv: float) -> str:
    """Format market cap value in 万元 to human-readable string."""
    if mv >= 10000:
        return f"{mv / 10000:.1f}亿"
    return f"{mv:.0f}万"


def compute_reversal_factor(market_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute short-term reversal factor from daily market bars.

    Academic basis: Jegadeesh (1990), Lehmann (1990).
    A-shares: Cheema & Nartea (2017) - A-shares exhibit strong short-term reversal
    rather than momentum. Losers bounce back, winners revert.

    Returns positive score when recent losers are expected to rebound.
    """
    closes = [float(item["close_price"]) for item in market_bars]

    ret_5d, lookback_5d = _lagged_return(closes, 5)
    ret_1d, lookback_1d = _lagged_return(closes, 1)

    ret5d_scale = 0.06
    ret1d_scale = 0.03
    signal_5d = score_scale(-ret_5d, ret5d_scale)
    signal_1d = score_scale(-ret_1d, ret1d_scale)
    score = clip(0.6 * signal_5d + 0.4 * signal_1d)
    direction = factor_direction(score)
    confidence = clip(0.3 + abs(score) * 0.25, 0.0, 0.75)

    drivers: list[str] = []
    risks: list[str] = []
    if ret_5d > 0.05:
        drivers.append(f"近 5 日涨幅 {ret_5d:.1%}，短线超买后反转压力增大。")
    elif ret_5d < -0.05:
        drivers.append(f"近 5 日跌幅 {ret_5d:.1%}，超卖后反弹动力增强。")
    if ret_1d > 0.03:
        drivers.append(f"昨日涨幅 {ret_1d:.1%}，日线级别反转观察信号。")
    elif ret_1d < -0.03:
        drivers.append(f"昨日跌幅 {ret_1d:.1%}，日线级别反弹观察信号。")
    if abs(ret_5d) < 0.02 and abs(ret_1d) < 0.01:
        risks.append("短期波动过窄，反转信号缺乏足够的价格空间。")
    if not drivers:
        drivers.append("短期涨跌幅度有限，反转因子暂未形成明显信号。")
    if not risks:
        risks.append("若短期趋势加速延续而非反转，因子将给出错误信号。")

    feature_values = {
        "ret_5d": round(ret_5d, 4),
        "ret_5d_lookback_days": lookback_5d,
        "ret_1d": round(ret_1d, 4),
        "ret_1d_lookback_days": lookback_1d,
        "signal_5d": round(signal_5d, 4),
        "signal_1d": round(signal_1d, 4),
        "reversal_score": round(score, 4),
    }

    return {
        "score": round(score, 4),
        "direction": direction,
        "confidence_score": round(confidence, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[-(lookback_5d + 1)]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(market_bars),
    }


def compute_liquidity_factor(market_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute liquidity factor based on Amihud (2002) ILLIQ measure.

    Higher ILLIQ = higher expected return (liquidity premium).
    The factor prefers liquid stocks over illiquid ones (practical for retail):
      positive score = liquid (low ILLIQ), negative score = illiquid (high ILLIQ).
    """
    closes = [float(item["close_price"]) for item in market_bars]

    illiq_values: list[float] = []
    for idx in range(1, len(closes)):
        ret = abs(pct_change(closes[idx], closes[idx - 1]))
        amount_raw = market_bars[idx].get("amount") or 0
        if float(amount_raw) <= 0:
            amount_raw = float(market_bars[idx]["volume"]) * float(market_bars[idx]["close_price"])
        amount_value = float(amount_raw)
        if amount_value > 0:
            illiq_values.append(ret / amount_value)

    if len(illiq_values) < 5:
        return {
            "score": 0.0,
            "direction": "neutral",
            "confidence_score": 0.0,
            "drivers": ["流动性数据不足（缺少成交额或观测天数 < 5），无法计算 ILLIQ 指标。"],
            "risks": [],
            "feature_values": {
                "avg_illiq_20d": 0.0, "log_illiq": 0.0, "log_illiq_zscore": 0.0,
                "illiq_obs_count": len(illiq_values), "liquidity_score": 0.0,
            },
            "evidence_count": 0,
        }

    avg_illiq_20d = mean(illiq_values[-20:]) if len(illiq_values) >= 20 else mean(illiq_values)
    log_illiq = log(max(avg_illiq_20d, 1e-12))

    # Self-normalization using full available ILLIQ history
    log_illiqs = [log(max(v, 1e-12)) for v in illiq_values]
    log_mean_val = mean(log_illiqs)
    log_std = safe_pstdev(log_illiqs) or 1.0
    log_illiq_zscore = (log_illiq - log_mean_val) / log_std

    # Score = -tanh(zscore): positive when more liquid than typical.
    # score_scale(zscore, 1.0) = tanh(zscore).
    score = clip(-score_scale(log_illiq_zscore, 1.0))
    direction = factor_direction(score)
    confidence = clip(0.35 + abs(score) * 0.2, 0.0, 0.75)

    drivers: list[str] = []
    risks: list[str] = []
    if score > 0.15:
        drivers.append("成交额充裕，流动性指标偏好，适合短线进出。")
    elif score < -0.15:
        drivers.append("流动性偏弱，ILLIQ 较高，需要注意交易成本。")
    if avg_illiq_20d > mean(illiq_values) * 1.5:
        risks.append("近 20 日 ILLIQ 高于历史均值，流动性在收缩。")
    if not drivers:
        drivers.append("流动性指标处于中性区间，暂未形成明显信号。")
    if not risks:
        risks.append("若成交额持续萎缩，ILLIQ 将走高并拖累流动性评分。")

    feature_values = {
        "avg_illiq_20d": round(avg_illiq_20d, 10),
        "log_illiq": round(log_illiq, 4),
        "log_illiq_zscore": round(log_illiq_zscore, 4),
        "illiq_obs_count": len(illiq_values),
        "liquidity_score": round(score, 4),
    }

    return {
        "score": round(score, 4),
        "direction": direction,
        "confidence_score": round(confidence, 4),
        "drivers": drivers[:3],
        "risks": risks[:3],
        "feature_values": feature_values,
        "window_start": market_bars[0]["observed_at"],
        "window_end": market_bars[-1]["observed_at"],
        "evidence_count": len(illiq_values),
    }


__all__ = [
    "active_sector_codes",
    "compute_fundamental_factor",
    "compute_liquidity_factor",
    "compute_manual_review_layer",
    "compute_news_factor",
    "compute_price_factor",
    "compute_reversal_factor",
    "compute_size_factor",
    "primary_sector_membership",
]
