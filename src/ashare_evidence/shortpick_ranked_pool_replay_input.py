from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.shortpick_lab import (
    SHORTPICK_FROZEN_PAPER_FAMILY,
    SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN,
    SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
    SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
    SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN,
    SHORTPICK_MARKET_FACTOR_RANK_LIMIT,
    _positive_rate,
    _rank_shortpick_market_factor_pool,
    _shortpick_market_factor_coarse_screen,
)
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    INDEX_SYMBOLS,
    _Bar,
    _benchmark_note,
    _context_for_signal_day,
    _entry_index_for_signal,
    _entry_price,
    _Series,
    _industry_from_profile_payload,
)

DEFAULT_REPLAY_HORIZONS = (1, 3, 5, 10, 20)
RANKED_POOL_RECONSTRUCTION_POLICY = "reconstruct_frozen_low_turnover_uptrend_ranked_pool_from_market_bars"


def enrich_shortpick_replay_paper_tracking_with_reconstructed_ranked_pools(
    session: Session,
    paper_tracking: dict[str, Any],
    *,
    requests: Iterable[dict[str, Any]] | None = None,
    rank_limit: int = SHORTPICK_MARKET_FACTOR_RANK_LIMIT,
    horizons: tuple[int, ...] = DEFAULT_REPLAY_HORIZONS,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
) -> dict[str, Any]:
    """Attach frozen-strategy ranked pools for retrospective control replays.

    The runtime candidate table only stores the frozen strategy's selected first
    candidate. This reconstructs the same low-turnover uptrend ranking pool from
    signal-date market bars, then emits replay-only candidate rows. It does not
    mutate database state or paper-tracking rows.
    """

    source_dates = _paper_tracking_signal_dates(paper_tracking)
    replay_dates = _dates_inside_request_windows(source_dates, requests)
    if not replay_dates:
        return {
            **paper_tracking,
            "ranked_candidate_pools": [],
            "ranked_candidate_pool_reconstruction": {
                "status": "blocked",
                "policy": RANKED_POOL_RECONSTRUCTION_POLICY,
                "blocker": "no_paper_tracking_signal_dates_inside_replay_windows",
                "source_signal_date_count": len(source_dates),
            },
        }

    raw_series_by_symbol = _load_daily_series_for_replay_window(
        session,
        start_date=min(replay_dates) - timedelta(days=120),
        end_date=max(replay_dates) + timedelta(days=max(horizons or (20,)) * 4 + 10),
    )
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        include_index_symbols=INDEX_SYMBOLS,
    )
    pools: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for signal_day in replay_dates:
        pool, blocker = _reconstructed_ranked_pool_for_signal_day(
            signal_day=signal_day,
            series_by_symbol=series_by_symbol,
            rank_limit=rank_limit,
            horizons=horizons,
            entry_price_source=entry_price_source,
        )
        if pool is not None:
            pools.append(pool)
        if blocker is not None:
            blockers.append(blocker)

    return {
        **paper_tracking,
        "ranked_candidate_pools": pools,
        "ranked_candidate_pool_reconstruction": {
            "status": "ready" if pools else "blocked",
            "policy": RANKED_POOL_RECONSTRUCTION_POLICY,
            "baseline_family": SHORTPICK_FROZEN_PAPER_FAMILY,
            "ranking_family": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
            "pool_limit": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
            "rank_limit": rank_limit,
            "horizons": list(horizons),
            "entry_price_source": entry_price_source,
            "source_signal_date_count": len(source_dates),
            "replay_signal_date_count": len(replay_dates),
            "pool_count": len(pools),
            "candidate_count": sum(len(pool.get("candidates") or []) for pool in pools),
            "blocked_signal_date_count": len(blockers),
            "blockers": blockers,
            "account_eligibility": account_eligibility,
            "benchmark_note": _benchmark_note(series_by_symbol, "universe_equal_weight"),
            "database_write_policy": "forbidden",
            "paper_tracking_write_policy": "forbidden",
        },
    }


def _reconstructed_ranked_pool_for_signal_day(
    *,
    signal_day: date,
    series_by_symbol: dict[str, Any],
    rank_limit: int,
    horizons: tuple[int, ...],
    entry_price_source: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    contexts, diagnostics = _market_factor_contexts_from_loaded_series(series_by_symbol, signal_day)
    if not contexts:
        return None, {"signal_date": signal_day.isoformat(), "blocker": "no_market_factor_contexts", **diagnostics}

    breadth10 = _positive_rate([float(item["return_10d"]) for item in contexts])
    if breadth10 is None or breadth10 < SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN:
        return None, {
            "signal_date": signal_day.isoformat(),
            "blocker": "frozen_low_turnover_gate_failed",
            "breadth10": breadth10,
            "breadth10_min": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN,
            **diagnostics,
        }

    low_turnover_pool = sorted(
        contexts,
        key=lambda item: (float(item["amount"]), float(item["turnover_rate"])),
        reverse=True,
    )[:SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT]
    ranked = [
        item
        for item in _rank_shortpick_market_factor_pool(
            low_turnover_pool,
            family=SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
        )
        if float(item.get("return_20d") or 0.0) > SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN
    ][:rank_limit]
    if not ranked:
        return None, {
            "signal_date": signal_day.isoformat(),
            "blocker": "no_ranked_candidates_after_return20_filter",
            "return_20d_min": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN,
            **diagnostics,
        }

    return (
        {
            "signal_date": signal_day.isoformat(),
            "pool_source": RANKED_POOL_RECONSTRUCTION_POLICY,
            "baseline_family": SHORTPICK_FROZEN_PAPER_FAMILY,
            "ranking_family": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
            "pool_limit": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
            "rank_limit": rank_limit,
            "pool_candidate_count": len(low_turnover_pool),
            "ranked_candidate_count": len(ranked),
            "source_feature_cutoff_policy": "signal_date_available_market_bars_only",
            "diagnostics": {**diagnostics, "breadth10": breadth10},
            "candidates": [
                _ranked_candidate_row(
                    item,
                    signal_day=signal_day,
                    candidate_rank=index,
                    series_by_symbol=series_by_symbol,
                    horizons=horizons,
                    entry_price_source=entry_price_source,
                )
                for index, item in enumerate(ranked, start=1)
            ],
        },
        None,
    )


def _market_factor_contexts_from_loaded_series(
    series_by_symbol: dict[str, Any],
    signal_day: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_symbol_count = len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    contexts: list[dict[str, Any]] = []
    stale_symbol_count = 0
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        context = _context_for_signal_day(series, signal_day, include_golden_cross=False)
        if context is None:
            stale_symbol_count += 1
            continue
        index = series.by_day.get(signal_day)
        latest_trade_day = series.bars[index].day.isoformat() if index is not None else signal_day.isoformat()
        contexts.append(
            {
                **context,
                "name": series.name,
                "latest_trade_day": latest_trade_day,
            }
        )
    screened_contexts, screen_summary = _shortpick_market_factor_coarse_screen(contexts)
    return screened_contexts, {
        "run_date": signal_day.isoformat(),
        "latest_trade_day": signal_day.isoformat(),
        "raw_symbol_count": raw_symbol_count,
        "eligible_symbol_count": len(screened_contexts),
        "full_eligible_symbol_count": len(contexts),
        "stale_symbol_count": stale_symbol_count,
        "coarse_screen": screen_summary,
    }


def _ranked_candidate_row(
    item: dict[str, Any],
    *,
    signal_day: date,
    candidate_rank: int,
    series_by_symbol: dict[str, Any],
    horizons: tuple[int, ...],
    entry_price_source: str,
) -> dict[str, Any]:
    symbol = str(item["symbol"])
    return {
        "candidate_id": f"reconstructed-frozen-ranked:{signal_day.isoformat()}:{candidate_rank}:{symbol}",
        "signal_date": signal_day.isoformat(),
        "symbol": symbol,
        "name": item.get("name"),
        "candidate_rank": candidate_rank,
        "source_rank": candidate_rank,
        "rank": candidate_rank,
        "baseline_family": SHORTPICK_FROZEN_PAPER_FAMILY,
        "ranking_family": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
        "tracking_role": "frozen_paper_reconstructed_ranked_candidate",
        "score": item.get("_market_factor_score"),
        "market_factor_overlay": _market_factor_overlay(item, candidate_rank=candidate_rank),
        "drawdown_reversal_features": _drawdown_reversal_features(series_by_symbol.get(symbol), signal_day),
        "validation_by_horizon": _validation_by_horizon(
            series_by_symbol.get(symbol),
            signal_day=signal_day,
            horizons=horizons,
            entry_price_source=entry_price_source,
        ),
    }


def _market_factor_overlay(item: dict[str, Any], *, candidate_rank: int) -> dict[str, Any]:
    fields = (
        "latest_trade_day",
        "return_1d",
        "return_5d",
        "return_10d",
        "return_20d",
        "abs_return_1d",
        "amount",
        "turnover_rate",
        "_market_factor_score",
        "_ret10_rank_percentile",
        "_ret20_rank_percentile",
        "_amount_rank_percentile",
        "_turnover_rank_percentile",
        "_ret1_rank_percentile",
        "_low_abs_ret1_rank_percentile",
    )
    overlay = {field.lstrip("_"): item.get(field) for field in fields if item.get(field) is not None}
    return {
        **overlay,
        "rank": candidate_rank,
        "source_rank": candidate_rank,
        "family": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
        "baseline_family": SHORTPICK_FROZEN_PAPER_FAMILY,
        "pool_limit": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
        "rank_limit": SHORTPICK_MARKET_FACTOR_RANK_LIMIT,
        "entry_price_source": ENTRY_PRICE_SOURCE_NEXT_CLOSE,
        "reconstruction_policy": RANKED_POOL_RECONSTRUCTION_POLICY,
    }


def _load_daily_series_for_replay_window(session: Session, *, start_date: date, end_date: date) -> dict[str, _Series]:
    start_at = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC)
    end_at = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=UTC)
    rows = session.execute(
        select(
            Stock.symbol,
            Stock.name,
            Stock.profile_payload,
            MarketBar.observed_at,
            MarketBar.open_price,
            MarketBar.high_price,
            MarketBar.low_price,
            MarketBar.close_price,
            MarketBar.amount,
            MarketBar.turnover_rate,
        )
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(MarketBar.timeframe == "1d", MarketBar.observed_at >= start_at, MarketBar.observed_at <= end_at)
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    )
    grouped: dict[str, tuple[str, str, list[_Bar]]] = {}
    for (
        symbol,
        name,
        profile_payload,
        observed_at,
        open_price,
        high_price,
        low_price,
        close_price,
        amount,
        turnover_rate,
    ) in rows:
        if not close_price:
            continue
        grouped.setdefault(symbol, (name, _industry_from_profile_payload(profile_payload), []))[2].append(
            _Bar(
                day=observed_at.date(),
                open=float(open_price),
                high=float(high_price),
                low=float(low_price),
                close=float(close_price),
                amount=float(amount or 0.0),
                turnover=None if turnover_rate is None else float(turnover_rate),
            )
        )
    output: dict[str, _Series] = {}
    for symbol, (name, industry, bars) in grouped.items():
        deduped: dict[date, _Bar] = {}
        for bar in bars:
            deduped[bar.day] = bar
        ordered = [deduped[day] for day in sorted(deduped)]
        output[symbol] = _Series(
            symbol=symbol,
            name=name,
            industry=industry,
            bars=ordered,
            by_day={bar.day: index for index, bar in enumerate(ordered)},
        )
    return output


def _validation_by_horizon(
    series: Any,
    *,
    signal_day: date,
    horizons: tuple[int, ...],
    entry_price_source: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if series is None:
        return [{"horizon_days": horizon, "status": "missing_market_series"} for horizon in horizons]
    for horizon in horizons:
        stock_only = _stock_only_validation(series, signal_day=signal_day, horizon=horizon, entry_price_source=entry_price_source)
        rows.append(stock_only or {"horizon_days": horizon, "status": "pending_forward_window"})
    return rows


def _stock_only_validation(series: Any, *, signal_day: date, horizon: int, entry_price_source: str) -> dict[str, Any] | None:
    signal_index = series.by_day.get(signal_day)
    if signal_index is None:
        return None
    entry_index = _entry_index_for_signal(signal_index, entry_price_source)
    exit_index = entry_index + horizon
    if exit_index >= len(series.bars):
        return None
    entry_bar = series.bars[entry_index]
    exit_bar = series.bars[exit_index]
    entry_price = _entry_price(entry_bar, entry_price_source)
    if not entry_price:
        return None
    return {
        "horizon_days": horizon,
        "status": "completed",
        "entry_date": entry_bar.day.isoformat(),
        "exit_date": exit_bar.day.isoformat(),
        "entry_price_source": entry_price_source,
        "stock_return": round(float(exit_bar.close) / float(entry_price) - 1.0, 6),
    }


def _drawdown_reversal_features(series: Any, signal_day: date) -> dict[str, Any]:
    if series is None:
        return {}
    index = series.by_day.get(signal_day)
    if index is None:
        return {}
    closes = [float(bar.close) for bar in series.bars[: index + 1] if float(bar.close) > 0]
    if not closes:
        return {}
    recent = closes[-10:]
    ma20_window = closes[-20:]
    high_window = closes[-60:]
    close = closes[-1]
    recent_high = max(recent) if recent else close
    short_start = closes[-4] if len(closes) >= 4 else closes[0]
    ma20 = sum(ma20_window) / len(ma20_window) if ma20_window else close
    high = max(high_window) if high_window else close
    return {
        "feature_date": signal_day.isoformat(),
        "recent_drawdown_return": round(close / recent_high - 1.0, 6) if recent_high else None,
        "short_window_return": round(close / short_start - 1.0, 6) if short_start else None,
        "price_vs_ma20": round(close / ma20 - 1.0, 6) if ma20 else None,
        "high_level_reversal_return": round(close / high - 1.0, 6) if high else None,
    }


def _paper_tracking_signal_dates(paper_tracking: dict[str, Any]) -> list[date]:
    items = [item for item in paper_tracking.get("items") or [] if isinstance(item, dict)]
    frozen_items = [
        item
        for item in items
        if str(item.get("tracking_role") or item.get("strategy_id") or "").startswith("frozen_paper")
        or str(item.get("baseline_family") or item.get("family") or "") == SHORTPICK_FROZEN_PAPER_FAMILY
    ]
    source_items = frozen_items or items
    dates = {
        parsed
        for item in source_items
        for parsed in [_parse_date(item.get("signal_date") or item.get("run_date"))]
        if parsed is not None
    }
    return sorted(dates)


def _dates_inside_request_windows(signal_dates: list[date], requests: Iterable[dict[str, Any]] | None) -> list[date]:
    request_list = [request for request in requests or [] if isinstance(request, dict)]
    if not request_list:
        return signal_dates
    output: list[date] = []
    for signal_day in signal_dates:
        for request in request_list:
            start = _parse_date(request.get("replay_start_date"))
            end = _parse_date(request.get("replay_end_date"))
            rule_defined_at = _parse_date(request.get("rule_defined_at"))
            if start is None or end is None or rule_defined_at is None:
                continue
            if start <= signal_day <= end and signal_day < rule_defined_at:
                output.append(signal_day)
                break
    return sorted(set(output))


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    text = value.split("T", 1)[0].split(" ", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
