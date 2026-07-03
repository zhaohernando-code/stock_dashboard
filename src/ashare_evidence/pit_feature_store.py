from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from math import sqrt
from pathlib import Path
from typing import Any

from ashare_evidence.phase2.common import pct_change, safe_mean, safe_std
from ashare_evidence.research_artifact_store import write_research_validation_artifact

PIT_FEATURE_STORE_SCHEMA_VERSION = "pit_feature_store.v1"
PIT_FEATURE_VERSION = "independent_pit_feature_store:v1"


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _day(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _rows_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(row)
    for symbol_rows in grouped.values():
        symbol_rows.sort(key=lambda row: (str(row.get("observed_at") or ""), str(row.get("id") or "")))
    return grouped


def _news_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(row)
    for symbol_rows in grouped.values():
        symbol_rows.sort(key=lambda row: (str(row.get("effective_at") or row.get("published_at") or ""), str(row.get("id") or "")))
    return grouped


def _bars_until(rows: list[dict[str, Any]], as_of_day: date) -> list[dict[str, Any]]:
    return [row for row in rows if (row_day := _day(row.get("observed_at"))) is not None and row_day <= as_of_day]


def _news_until(rows: list[dict[str, Any]], as_of_day: date, *, lookback_days: int = 14) -> list[dict[str, Any]]:
    start_day = as_of_day - timedelta(days=lookback_days)
    active: list[dict[str, Any]] = []
    for row in rows:
        event_day = _day(row.get("effective_at") or row.get("published_at"))
        if event_day is not None and start_day <= event_day <= as_of_day:
            active.append(row)
    return active


def _window(values: list[float], size: int) -> list[float]:
    return values[-size:] if len(values) >= size else values[:]


def _market_features(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [_safe_float(row.get("close_price")) for row in bars]
    highs = [_safe_float(row.get("high_price")) for row in bars]
    amounts = [_safe_float(row.get("amount")) for row in bars]
    volumes = [_safe_float(row.get("volume")) for row in bars]
    turnovers = [_safe_float(row.get("turnover_rate")) for row in bars if row.get("turnover_rate") is not None]
    returns = [pct_change(closes[index], closes[index - 1]) for index in range(1, len(closes))]
    current = bars[-1] if bars else {}
    current_close = closes[-1] if closes else 0.0
    prior_close = closes[-2] if len(closes) >= 2 else current_close
    recent_amount = _window(amounts, 20)
    avg_amount_20d = safe_mean(recent_amount)
    daily_return = pct_change(current_close, prior_close) if len(closes) >= 2 else 0.0
    return {
        "price_baseline": {
            "status": "ready" if len(closes) >= 40 else "limited_history",
            "momentum_10d": round(pct_change(current_close, closes[-11]), 6) if len(closes) >= 11 else None,
            "momentum_20d": round(pct_change(current_close, closes[-21]), 6) if len(closes) >= 21 else None,
            "momentum_40d": round(pct_change(current_close, closes[-41]), 6) if len(closes) >= 41 else None,
            "volatility_20d": round(safe_std(_window(returns, 20)) * sqrt(20), 6),
            "drawdown_40d": round(current_close / max(_window(highs, 40) or [current_close]) - 1, 6)
            if current_close
            else None,
        },
        "liquidity": {
            "status": "ready" if amounts else "missing_amount",
            "avg_amount_20d": round(avg_amount_20d, 6),
            "amount_cv_20d": round(safe_std(recent_amount) / max(avg_amount_20d, 1.0), 6),
            "avg_volume_20d": round(safe_mean(_window(volumes, 20)), 6),
            "avg_turnover_rate_20d": round(safe_mean(_window(turnovers, 20)), 6) if turnovers else None,
        },
        "risk_trading_constraints": {
            "status": "ready",
            "daily_return": round(daily_return, 6),
            "suspension_like_zero_volume": _safe_float(current.get("volume")) <= 0,
            "limit_up_like_close": daily_return >= 0.095,
            "limit_down_like_close": daily_return <= -0.095,
            "t_plus_1_required": True,
        },
        "valuation": {
            "status": "ready"
            if current.get("pe_ttm") is not None or current.get("pb") is not None
            else "source_unavailable",
            "pe_ttm": current.get("pe_ttm"),
            "pb": current.get("pb"),
            "total_mv": current.get("total_mv"),
            "circ_mv": current.get("circ_mv"),
        },
        "crowding": {
            "status": "ready" if len(amounts) >= 20 else "limited_history",
            "amount_vs_20d_avg": round(_safe_float(current.get("amount")) / max(avg_amount_20d, 1.0), 6),
            "volume_vs_20d_avg": round(_safe_float(current.get("volume")) / max(safe_mean(_window(volumes, 20)), 1.0), 6),
        },
    }


def _news_features(news_rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive = sum(1 for row in news_rows if str(row.get("impact_direction")) == "positive")
    negative = sum(1 for row in news_rows if str(row.get("impact_direction")) == "negative")
    relevance = [_safe_float(row.get("relevance_score")) for row in news_rows]
    total = len(news_rows)
    return {
        "news_text": {
            "status": "ready" if total else "no_recent_linked_news",
            "linked_news_count_14d": total,
            "positive_event_count_14d": positive,
            "negative_event_count_14d": negative,
            "event_balance_14d": round((positive - negative) / max(total, 1), 6),
            "mean_relevance_score_14d": round(safe_mean(relevance), 6),
        }
    }


def _benchmark_features(benchmark_rows: list[dict[str, Any]], as_of_day: date) -> dict[str, Any]:
    bars = _bars_until(benchmark_rows, as_of_day)
    closes = [_safe_float(row.get("close_price")) for row in bars]
    returns = [pct_change(closes[index], closes[index - 1]) for index in range(1, len(closes))]
    current_close = closes[-1] if closes else 0.0
    return {
        "regime": {
            "status": "ready" if len(closes) >= 20 else "missing_or_limited_benchmark_history",
            "benchmark_momentum_20d": round(pct_change(current_close, closes[-21]), 6) if len(closes) >= 21 else None,
            "benchmark_volatility_20d": round(safe_std(_window(returns, 20)) * sqrt(20), 6),
        }
    }


def _static_placeholder_features() -> dict[str, Any]:
    return {
        "fundamental": {
            "status": "source_unavailable",
            "reason": "independent PIT financial statement availability calendar is not yet present in the frozen input snapshot",
        },
        "industry_diffusion": {
            "status": "source_unavailable",
            "reason": "frozen objective industry membership universe is not yet present in the input snapshot",
        },
        "dynamic_weight_context": {
            "status": "disabled_for_promotion",
            "reason": "dynamic weights require OOS, PBO/DSR, multiple-comparison and governance gates",
        },
    }


def build_pit_feature_store_artifact(input_snapshot: dict[str, Any]) -> dict[str, Any]:
    validation_run_id = str(input_snapshot.get("validation_run_id") or "unknown-validation-run")
    source_snapshot_ref = {
        "artifact_type": input_snapshot.get("artifact_type"),
        "schema_version": input_snapshot.get("schema_version"),
        "artifact_id": input_snapshot.get("artifact_id"),
        "input_content_digest": input_snapshot.get("input_content_digest"),
    }
    market_rows = list((input_snapshot.get("market_bar_source") or {}).get("rows") or [])
    benchmark_rows = list((input_snapshot.get("benchmark_bar_source") or {}).get("rows") or [])
    recommendation_rows = list((input_snapshot.get("recommendation_source") or {}).get("rows") or [])
    news_rows = list((input_snapshot.get("news_source") or {}).get("rows") or [])
    market_by_symbol = _rows_by_symbol(market_rows)
    news_rows_by_symbol = _news_by_symbol(news_rows)
    feature_rows: list[dict[str, Any]] = []
    for recommendation in recommendation_rows:
        symbol = str(recommendation.get("symbol") or "")
        as_of_day = _day(recommendation.get("as_of_data_time"))
        if not symbol or as_of_day is None:
            continue
        bars = _bars_until(market_by_symbol.get(symbol, []), as_of_day)
        if not bars:
            continue
        active_news = _news_until(news_rows_by_symbol.get(symbol, []), as_of_day)
        features = {
            **_market_features(bars),
            **_news_features(active_news),
            **_benchmark_features(benchmark_rows, as_of_day),
            **_static_placeholder_features(),
        }
        row = {
            "symbol": symbol,
            "recommendation_key": recommendation.get("recommendation_key"),
            "as_of_data_time": recommendation.get("as_of_data_time"),
            "feature_available_at": bars[-1].get("observed_at"),
            "feature_version": PIT_FEATURE_VERSION,
            "source_input_snapshot_id": source_snapshot_ref["artifact_id"],
            "features": features,
            "source_row_refs": {
                "market_bar_count": len(bars),
                "latest_market_bar_key": bars[-1].get("bar_key"),
                "linked_news_count_14d": len(active_news),
                "benchmark_bar_count": len(_bars_until(benchmark_rows, as_of_day)),
            },
        }
        row["row_digest"] = _stable_digest(row)
        feature_rows.append(row)

    feature_rows.sort(key=lambda row: (str(row.get("as_of_data_time") or ""), str(row.get("symbol") or "")))
    feature_digest = _stable_digest(
        {
            "source_input_snapshot": source_snapshot_ref,
            "feature_rows": feature_rows,
            "feature_version": PIT_FEATURE_VERSION,
        }
    )
    artifact_id = f"pit-feature-store-{feature_digest[:16]}"
    return {
        "artifact_type": "pit_feature_store",
        "schema_version": PIT_FEATURE_STORE_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_db_snapshot_id": input_snapshot.get("source_db_snapshot_id"),
        "source_data_time_range": input_snapshot.get("source_data_time_range"),
        "feature_version": PIT_FEATURE_VERSION,
        "label_version": "not_applicable_feature_store_only",
        "code_version": "unresolved_local_checkout",
        "config_version": "pit_feature_store_policy.v1",
        "validation_protocol": {
            "artifact_role": "pit_feature_store",
            "source_policy": "consume_research_input_snapshot_only",
            "feature_source_status": "independent_pit_features",
            "legacy_payload_usage": "forbidden_for_feature_computation",
        },
        "gate_readout": {
            "gate_status": "feature_store_ready" if feature_rows else "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "feature_store_only",
            "blocking_gate_ids": [] if feature_rows else ["missing_feature_rows"],
        },
        "claim_ceiling": "feature_store_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_input_snapshot": source_snapshot_ref,
        "feature_row_count": len(feature_rows),
        "feature_content_digest": feature_digest,
        "feature_groups": [
            "price_baseline",
            "liquidity",
            "risk_trading_constraints",
            "valuation",
            "crowding",
            "news_text",
            "regime",
            "fundamental",
            "industry_diffusion",
            "dynamic_weight_context",
        ],
        "feature_rows": feature_rows,
    }


def write_pit_feature_store_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str,
) -> Path:
    return write_research_validation_artifact(
        "pit_feature_store",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
