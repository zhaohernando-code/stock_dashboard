from __future__ import annotations

import calendar
import json
import random
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    INDEX_SYMBOLS,
    LOW_TURNOVER_UPTREND_STRATEGY,
    QUIET_BREAKOUT_BASE_STRATEGY,
    _benchmark_note,
    _benchmark_return,
    _context_for_signal_day,
    _industry_diversified_rank,
    _load_daily_series,
    _mean,
    _strategy_score,
    _trimmed_mean,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    BASE_STRATEGY_BY_VARIANT,
    DEFAULT_PORTFOLIO_STRATEGIES,
    LEADING_PAPER_MODE,
    LEADING_PAPER_STRATEGY,
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
    _apply_strategy_regime_filter,
    _apply_strategy_selection_transform,
    _build_trade_intents,
    _close_on,
    _eligible_signal_days,
    _entry_price_on,
    _strategy_label,
)
from ashare_evidence.shortpick_replay import _market_regime_tags_by_date, benchmark_close_maps

SHORTPICK_STRATEGY_SLICE_EVIDENCE_VERSION = "shortpick-strategy-slice-evidence-v1"


def build_shortpick_strategy_slice_evidence_from_staged_artifacts(
    session: Session,
    *,
    entry_artifact_paths: dict[str, str | Path],
    min_regime_period_count: int = 2,
) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    for entry_price_source, path_value in entry_artifact_paths.items():
        path = Path(path_value)
        payload = json.loads(path.read_text(encoding="utf-8"))
        artifacts[entry_price_source] = {"path": str(path), "payload": payload}

    month_dates = sorted(
        {
            _month_end_date(str(item.get("period")))
            for artifact in artifacts.values()
            for strategy_payload in ((artifact["payload"].get("results") or {}).get(LEADING_PAPER_MODE) or {}).values()
            for item in strategy_payload.get("monthly", [])
            if item.get("period")
        }
    )
    regime_tags = _market_regime_tags_by_date(month_dates, benchmark_close_maps(session))

    overall_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    monthly_regime_inputs: list[dict[str, Any]] = []
    data_scopes: list[dict[str, Any]] = []
    for entry_price_source, artifact in artifacts.items():
        payload = artifact["payload"]
        data_scope = dict(payload.get("data_scope") or {})
        data_scopes.append(data_scope)
        strategies = (payload.get("results") or {}).get(LEADING_PAPER_MODE) or {}
        for strategy, strategy_payload in sorted(strategies.items()):
            label = strategy_payload.get("label") or _strategy_label(str(strategy))
            summary = dict(strategy_payload.get("summary") or {})
            overall_rows.append(
                {
                    "entry_price_source": entry_price_source,
                    "strategy": strategy,
                    "label": label,
                    "trade_count": summary.get("trade_count"),
                    "signal_date_count": data_scope.get("signal_day_count"),
                    "mean_net_return": summary.get("total_return"),
                    "mean_net_excess_return": summary.get("excess_total_return"),
                    "positive_net_excess_rate": summary.get("trade_win_rate"),
                    "max_drawdown": summary.get("max_drawdown"),
                    "basis": "full_window_portfolio_summary",
                }
            )
            for period_kind in ("yearly", "monthly"):
                for item in strategy_payload.get(period_kind, []):
                    period = str(item.get("period") or "")
                    row = {
                        "entry_price_source": entry_price_source,
                        "strategy": strategy,
                        "label": label,
                        "period_kind": "year" if period_kind == "yearly" else "month",
                        "period": period,
                        "return": item.get("return"),
                        "benchmark_return": item.get("benchmark_return"),
                        "excess_return": item.get("excess_return"),
                        "basis": "full_window_portfolio_period",
                    }
                    period_rows.append(row)
                    if period_kind == "monthly":
                        month_date = _month_end_date(period)
                        tag = regime_tags.get(month_date) or {}
                        monthly_regime_inputs.append(
                            {
                                **row,
                                "market_regime_tag": tag.get("market_regime_tag") or "missing_regime",
                                "trend_regime": tag.get("trend_regime") or "missing",
                                "volatility_regime": tag.get("volatility_regime") or "missing",
                                "size_style_regime": tag.get("size_style_regime") or "missing",
                            }
                        )

    regime_rows = _portfolio_regime_rows(monthly_regime_inputs)
    confidence_intervals = _portfolio_confidence_intervals(period_rows)
    stability = _portfolio_stability_rows(period_rows, regime_rows)
    attribution = _portfolio_return_attribution(period_rows, regime_rows)
    signal_from = min((scope.get("signal_date_from") for scope in data_scopes if scope.get("signal_date_from")), default=None)
    signal_to = max((scope.get("signal_date_to") for scope in data_scopes if scope.get("signal_date_to")), default=None)
    signal_days = max((int(scope.get("signal_day_count") or 0) for scope in data_scopes), default=0)
    stock_like = max((int(scope.get("stock_like_series_count") or 0) for scope in data_scopes), default=0)
    regime_coverage_rows = _portfolio_regime_coverage_rows(monthly_regime_inputs)
    return {
        "experiment": "shortpick_strategy_slice_evidence",
        "version": SHORTPICK_STRATEGY_SLICE_EVIDENCE_VERSION,
        "status": "ready" if overall_rows else "missing_artifact",
        "basis": "offline_full_window_staged_portfolio_artifacts",
        "config": {
            "entry_artifact_paths": {entry: artifact["path"] for entry, artifact in artifacts.items()},
            "min_regime_period_count": min_regime_period_count,
            "mode": LEADING_PAPER_MODE,
            "frozen_strategy": LEADING_PAPER_STRATEGY,
            "regime_slice_basis": "monthly portfolio excess grouped by offline index-derived month-end regime",
        },
        "data_scope": {
            "signal_day_count": signal_days,
            "signal_date_from": signal_from,
            "signal_date_to": signal_to,
            "year_count": len({str(row["period"])[:4] for row in period_rows if row.get("period_kind") == "year"}),
            "stock_like_series_count": stock_like,
            "benchmark_note": "Full-window staged portfolio artifacts; regime labels use local CSI300/CSI1000 daily bars at month end.",
        },
        "sample_adequacy": {
            "status": "ready" if signal_days >= 500 and len(regime_coverage_rows) >= 4 else "partial_ready",
            "broad_window_ready": signal_days >= 500,
            "regime_slice_ready": len([row for row in regime_coverage_rows if int(row.get("period_count") or 0) >= min_regime_period_count]) >= 4,
            "signal_day_count": signal_days,
            "year_count": len({str(row["period"])[:4] for row in period_rows if row.get("period_kind") == "year"}),
            "useful_regime_count": len([row for row in regime_coverage_rows if int(row.get("period_count") or 0) >= min_regime_period_count]),
            "min_regime_period_count": min_regime_period_count,
            "limitations": [
                "This artifact expands deterministic staged portfolio strategy evidence, not historical LLM free-pick replay.",
                "Regime slices are monthly portfolio-path slices, so they answer capital-curve stability by environment rather than per-candidate LLM alpha.",
            ],
        },
        "overall_strategy_rows": overall_rows,
        "period_strategy_rows": period_rows,
        "regime_strategy_rows": regime_rows,
        "regime_winner_rows": _portfolio_regime_winner_rows(regime_rows, min_period_count=min_regime_period_count),
        "regime_coverage_rows": regime_coverage_rows,
        "portfolio_confidence_intervals": confidence_intervals,
        "portfolio_stability": stability,
        "portfolio_return_attribution": attribution,
    }


def build_shortpick_strategy_slice_evidence(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    entry_price_sources: tuple[str, ...] = (ENTRY_PRICE_SOURCE_NEXT_CLOSE,),
    pool_limit: int = 40,
    rank_limit: int = 6,
    horizon_days: int = 5,
    cost_bps: float = 20.0,
    benchmark_mode: str = "csi300",
    min_signal_symbol_count: int = 1000,
    min_regime_trade_count: int = 30,
    strategies: tuple[str, ...] = DEFAULT_PORTFOLIO_STRATEGIES,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
) -> dict[str, Any]:
    """Build offline long-window strategy slices for Short Pick Lab history analysis.

    The output is an artifact projection. It deliberately does not call LLMs,
    fetch current market data, or mutate research tables.
    """
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    invalid_entries = [entry for entry in entry_price_sources if entry not in ENTRY_PRICE_SOURCES]
    if invalid_entries:
        raise ValueError(f"entry_price_sources contains unsupported values: {invalid_entries}")

    raw_series_by_symbol = _load_daily_series(session)
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    benchmark = series_by_symbol.get("000300.SH")
    signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=start_date,
        end_date=end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    regime_tags = _market_regime_tags_by_date(signal_days, benchmark_close_maps(session))
    contexts_by_day = _contexts_by_signal_day(series_by_symbol, signal_days=signal_days)
    regime_features = _regime_features_from_contexts(contexts_by_day, pool_limit=pool_limit)
    base_selections = {
        strategy: _build_strategy_selections_from_contexts(
            contexts_by_day,
            strategy=strategy,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
        for strategy in sorted({BASE_STRATEGY_BY_VARIANT.get(strategy, strategy) for strategy in strategies})
    }
    selections = {
        strategy: base_selections.get(BASE_STRATEGY_BY_VARIANT.get(strategy, strategy), {})
        for strategy in strategies
    }
    selections = {
        strategy: _apply_strategy_regime_filter(
            strategy,
            _apply_strategy_selection_transform(strategy, strategy_selections),
            regime_features,
        )
        for strategy, strategy_selections in selections.items()
    }

    trade_rows: list[dict[str, Any]] = []
    for entry_price_source in entry_price_sources:
        for strategy in strategies:
            intents = _build_trade_intents(
                series_by_symbol,
                selections.get(strategy, {}),
                strategy=strategy,
                mode=LEADING_PAPER_MODE,
                horizon_days=horizon_days,
                apply_limit_up_filter=True,
                entry_price_source=entry_price_source,
            )
            for intent in intents:
                series = series_by_symbol.get(intent.symbol)
                entry_price = _entry_price_on(series_by_symbol, intent.symbol, intent.entry_day, entry_price_source)
                exit_close = _close_on(series_by_symbol, intent.symbol, intent.exit_day)
                if entry_price is None or exit_close is None or entry_price <= 0:
                    continue
                gross_return = float(exit_close) / float(entry_price) - 1.0
                net_return = gross_return - float(cost_bps) / 10000.0
                benchmark_return, benchmark_status = _benchmark_return(
                    series_by_symbol=series_by_symbol,
                    benchmark=benchmark,
                    benchmark_mode=benchmark_mode,
                    entry_day=intent.entry_day,
                    exit_day=intent.exit_day,
                    entry_price_source=entry_price_source,
                )
                tag = regime_tags.get(intent.signal_day) or {}
                trade_rows.append(
                    {
                        "entry_price_source": entry_price_source,
                        "mode": LEADING_PAPER_MODE,
                        "strategy": strategy,
                        "label": _strategy_label(strategy),
                        "signal_day": intent.signal_day,
                        "entry_day": intent.entry_day,
                        "exit_day": intent.exit_day,
                        "symbol": intent.symbol,
                        "name": series.name if series is not None else intent.symbol,
                        "industry": series.industry if series is not None else "unknown",
                        "gross_return": gross_return,
                        "net_return": net_return,
                        "benchmark_return": benchmark_return,
                        "net_excess_return": None if benchmark_return is None else net_return - float(benchmark_return),
                        "benchmark_status": benchmark_status,
                        "market_regime_tag": tag.get("market_regime_tag") or "missing_regime",
                        "trend_regime": tag.get("trend_regime") or "missing",
                        "volatility_regime": tag.get("volatility_regime") or "missing",
                        "size_style_regime": tag.get("size_style_regime") or "missing",
                        "year": intent.signal_day.strftime("%Y"),
                        "quarter": f"{intent.signal_day.year}Q{((intent.signal_day.month - 1) // 3) + 1}",
                        "month": intent.signal_day.strftime("%Y-%m"),
                    }
                )

    regime_rows = _slice_rows(
        trade_rows,
        group_keys=("entry_price_source", "strategy", "market_regime_tag"),
        extra_keys=("label", "trend_regime", "volatility_regime", "size_style_regime"),
    )
    period_rows = []
    for period_kind, key in (("year", "year"), ("quarter", "quarter"), ("month", "month")):
        for row in _slice_rows(
            trade_rows,
            group_keys=("entry_price_source", "strategy", key),
            extra_keys=("label",),
        ):
            row["period_kind"] = period_kind
            row["period"] = row.pop(key)
            period_rows.append(row)
    overall_rows = _slice_rows(
        trade_rows,
        group_keys=("entry_price_source", "strategy"),
        extra_keys=("label",),
    )
    regime_coverage_rows = _regime_coverage_rows(signal_days, regime_tags)
    winners = _regime_winner_rows(regime_rows, min_trade_count=min_regime_trade_count)
    trade_attribution = _trade_level_attribution(trade_rows)

    return {
        "experiment": "shortpick_strategy_slice_evidence",
        "version": SHORTPICK_STRATEGY_SLICE_EVIDENCE_VERSION,
        "status": "ready" if trade_rows else "missing_artifact",
        "basis": "offline_full_window_market_factor_strategy_slices",
        "config": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "entry_price_sources": list(entry_price_sources),
            "pool_limit": pool_limit,
            "rank_limit": rank_limit,
            "horizon_days": horizon_days,
            "cost_bps": cost_bps,
            "benchmark_mode": benchmark_mode,
            "min_signal_symbol_count": min_signal_symbol_count,
            "min_regime_trade_count": min_regime_trade_count,
            "mode": LEADING_PAPER_MODE,
            "strategies": list(strategies),
            "frozen_strategy": LEADING_PAPER_STRATEGY,
            "full_trade_rows_included": True,
        },
        "data_scope": {
            "signal_day_count": len(signal_days),
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "year_count": len({day.year for day in signal_days}),
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "raw_stock_like_series_count": len([symbol for symbol in raw_series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "account_eligibility": account_eligibility,
            "benchmark_note": _benchmark_note(series_by_symbol, benchmark_mode),
        },
        "sample_adequacy": _sample_adequacy(
            signal_days=signal_days,
            regime_coverage_rows=regime_coverage_rows,
            min_regime_trade_count=min_regime_trade_count,
        ),
        "overall_strategy_rows": overall_rows,
        "regime_strategy_rows": regime_rows,
        "period_strategy_rows": period_rows,
        "regime_winner_rows": winners,
        "regime_coverage_rows": regime_coverage_rows,
        "trade_attribution": trade_attribution,
        "trade_rows": [_json_safe_row(row) for row in trade_rows],
    }


def _trade_level_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if row.get("net_excess_return") is not None]
    attribution_rows = _trade_attribution_strategy_rows(usable)
    return {
        "status": "ready" if usable else "missing_artifact",
        "basis": "full_trade_rows_grouped_by_symbol_industry_signal_day_and_regime",
        "sample_trade_count": len(usable),
        "note": "逐笔交易级归因来自完整离线 strategy-slice trade_rows，不使用 staged portfolio trades_sample 外推。",
        "rows": attribution_rows,
        "top_symbol_rows": _trade_group_attribution_rows(
            usable,
            group_keys=("entry_price_source", "strategy", "symbol"),
            extra_keys=("label", "name", "industry"),
            limit_per_strategy=8,
        ),
        "top_industry_rows": _trade_group_attribution_rows(
            usable,
            group_keys=("entry_price_source", "strategy", "industry"),
            extra_keys=("label",),
            limit_per_strategy=8,
        ),
        "top_signal_day_rows": _trade_group_attribution_rows(
            usable,
            group_keys=("entry_price_source", "strategy", "signal_day"),
            extra_keys=("label",),
            limit_per_strategy=8,
        ),
        "top_regime_rows": _trade_group_attribution_rows(
            usable,
            group_keys=("entry_price_source", "strategy", "market_regime_tag"),
            extra_keys=("label", "trend_regime", "volatility_regime", "size_style_regime"),
            limit_per_strategy=8,
        ),
        **({} if usable else {"reason": "完整逐笔交易行为空，无法生成股票/行业归因。"}),
    }


def _trade_attribution_strategy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)
    output = []
    for (entry_price_source, strategy), values in sorted(grouped.items(), key=lambda item: item[0]):
        sample = values[0]
        best_symbol = _trade_best_group(values, "symbol")
        worst_symbol = _trade_worst_group(values, "symbol")
        best_industry = _trade_best_group(values, "industry")
        worst_industry = _trade_worst_group(values, "industry")
        best_day = _trade_best_group(values, "signal_day")
        worst_day = _trade_worst_group(values, "signal_day")
        total_excess = _sum_metric(values, "net_excess_return")
        output.append(
            _json_safe_row(
                {
                    "entry_price_source": entry_price_source,
                    "strategy": strategy,
                    "label": sample.get("label") or _strategy_label(strategy),
                    "trade_count": len(values),
                    "symbol_count": len({row.get("symbol") for row in values}),
                    "industry_count": len({row.get("industry") for row in values}),
                    "mean_net_excess_return": _round(_mean([float(row["net_excess_return"]) for row in values])),
                    "positive_net_excess_rate": _positive_rate([float(row["net_excess_return"]) for row in values]),
                    "sum_net_excess_return": _round(total_excess),
                    "best_symbol": best_symbol.get("group_value") if best_symbol else None,
                    "best_symbol_name": best_symbol.get("name") if best_symbol else None,
                    "best_symbol_sum_net_excess_return": best_symbol.get("sum_net_excess_return") if best_symbol else None,
                    "worst_symbol": worst_symbol.get("group_value") if worst_symbol else None,
                    "worst_symbol_name": worst_symbol.get("name") if worst_symbol else None,
                    "worst_symbol_sum_net_excess_return": worst_symbol.get("sum_net_excess_return") if worst_symbol else None,
                    "best_industry": best_industry.get("group_value") if best_industry else None,
                    "best_industry_sum_net_excess_return": best_industry.get("sum_net_excess_return") if best_industry else None,
                    "worst_industry": worst_industry.get("group_value") if worst_industry else None,
                    "worst_industry_sum_net_excess_return": worst_industry.get("sum_net_excess_return") if worst_industry else None,
                    "best_signal_day": best_day.get("group_value") if best_day else None,
                    "best_signal_day_sum_net_excess_return": best_day.get("sum_net_excess_return") if best_day else None,
                    "worst_signal_day": worst_day.get("group_value") if worst_day else None,
                    "worst_signal_day_sum_net_excess_return": worst_day.get("sum_net_excess_return") if worst_day else None,
                }
            )
        )
    output.sort(
        key=lambda item: (
            str(item["entry_price_source"]) != ENTRY_PRICE_SOURCE_NEXT_CLOSE,
            -float(item.get("sum_net_excess_return") if item.get("sum_net_excess_return") is not None else -999.0),
        )
    )
    return output


def _trade_group_attribution_rows(
    rows: list[dict[str, Any]],
    *,
    group_keys: tuple[str, ...],
    extra_keys: tuple[str, ...],
    limit_per_strategy: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in group_keys)].append(row)
    all_rows: list[dict[str, Any]] = []
    for key_values, values in grouped.items():
        sample = values[0]
        result: dict[str, Any] = {key: value for key, value in zip(group_keys, key_values)}
        for key in extra_keys:
            result[key] = sample.get(key)
        excess = [float(row["net_excess_return"]) for row in values if row.get("net_excess_return") is not None]
        result.update(
            {
                "group_value": key_values[-1],
                "trade_count": len(values),
                "symbol_count": len({row.get("symbol") for row in values}),
                "sum_net_excess_return": _round(_sum_metric(values, "net_excess_return")),
                "mean_net_excess_return": _round(_mean(excess)),
                "positive_net_excess_rate": _positive_rate(excess),
            }
        )
        all_rows.append(_json_safe_row(result))

    bucketed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        bucketed[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)
    output: list[dict[str, Any]] = []
    for _, values in sorted(bucketed.items(), key=lambda item: item[0]):
        ranked = sorted(
            values,
            key=lambda item: (
                abs(float(item.get("sum_net_excess_return") if item.get("sum_net_excess_return") is not None else 0.0)),
                int(item.get("trade_count") or 0),
            ),
            reverse=True,
        )
        output.extend(ranked[:limit_per_strategy])
    return output


def _trade_best_group(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    grouped = _trade_group_attribution_rows(rows, group_keys=(key,), extra_keys=("name", "industry"), limit_per_strategy=100000)
    values = [row for row in grouped if row.get("sum_net_excess_return") is not None]
    return None if not values else max(values, key=lambda item: float(item.get("sum_net_excess_return") or 0.0))


def _trade_worst_group(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    grouped = _trade_group_attribution_rows(rows, group_keys=(key,), extra_keys=("name", "industry"), limit_per_strategy=100000)
    values = [row for row in grouped if row.get("sum_net_excess_return") is not None]
    return None if not values else min(values, key=lambda item: float(item.get("sum_net_excess_return") or 0.0))


def _sum_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return None if not values else sum(values)


def _slice_rows(
    rows: list[dict[str, Any]],
    *,
    group_keys: tuple[str, ...],
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in group_keys)].append(row)

    output: list[dict[str, Any]] = []
    for key_values, values in sorted(grouped.items(), key=lambda item: item[0]):
        net_returns = [float(item["net_return"]) for item in values if item.get("net_return") is not None]
        net_excess = [float(item["net_excess_return"]) for item in values if item.get("net_excess_return") is not None]
        result = {key: value for key, value in zip(group_keys, key_values)}
        sample = values[0]
        for key in extra_keys:
            result[key] = sample.get(key)
        result.update(
            {
                "trade_count": len(values),
                "signal_date_count": len({item["signal_day"] for item in values}),
                "symbol_count": len({item["symbol"] for item in values}),
                "mean_net_return": _round(_mean(net_returns)),
                "trimmed_mean_net_return": _round(_trimmed_mean(net_returns)),
                "positive_net_return_rate": _positive_rate(net_returns),
                "mean_net_excess_return": _round(_mean(net_excess)),
                "trimmed_mean_net_excess_return": _round(_trimmed_mean(net_excess)),
                "positive_net_excess_rate": _positive_rate(net_excess),
            }
        )
        output.append(_json_safe_row(result))
    return output


def _month_end_date(period: str) -> date:
    year_text, month_text = period.split("-", 1)
    year = int(year_text)
    month = int(month_text)
    return date(year, month, calendar.monthrange(year, month)[1])


def _portfolio_regime_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["entry_price_source"]), str(row["strategy"]), str(row["market_regime_tag"]))].append(row)
    output: list[dict[str, Any]] = []
    for (entry_price_source, strategy, tag), values in sorted(grouped.items(), key=lambda item: item[0]):
        excess = [float(item["excess_return"]) for item in values if item.get("excess_return") is not None]
        returns = [float(item["return"]) for item in values if item.get("return") is not None]
        sample = values[0]
        output.append(
            {
                "entry_price_source": entry_price_source,
                "strategy": strategy,
                "label": sample.get("label") or _strategy_label(strategy),
                "market_regime_tag": tag,
                "trend_regime": sample.get("trend_regime"),
                "volatility_regime": sample.get("volatility_regime"),
                "size_style_regime": sample.get("size_style_regime"),
                "period_count": len(values),
                "trade_count": len(values),
                "signal_date_count": len(values),
                "periods": sorted(str(item["period"]) for item in values if item.get("period")),
                "mean_net_return": _round(_mean(returns)),
                "mean_net_excess_return": _round(_mean(excess)),
                "positive_net_excess_rate": _positive_rate(excess),
                "basis": "monthly_portfolio_periods_grouped_by_market_regime",
            }
        )
    return output


def _portfolio_regime_coverage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_periods: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row["market_regime_tag"]), str(row["period"]))
        if key in seen_periods:
            continue
        seen_periods.add(key)
        grouped[str(row["market_regime_tag"])].append(row)
    output = []
    for tag, values in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        sample = values[0]
        output.append(
            {
                "market_regime_tag": tag,
                "trend_regime": sample.get("trend_regime"),
                "volatility_regime": sample.get("volatility_regime"),
                "size_style_regime": sample.get("size_style_regime"),
                "period_count": len(values),
                "date_from": min(str(item["period"]) for item in values),
                "date_to": max(str(item["period"]) for item in values),
            }
        )
    return output


def _portfolio_regime_winner_rows(rows: list[dict[str, Any]], *, min_period_count: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row.get("period_count") or 0) >= min_period_count:
            grouped[(str(row.get("entry_price_source")), str(row.get("market_regime_tag")))].append(row)
    output = []
    for (entry_price_source, tag), values in sorted(grouped.items(), key=lambda item: item[0]):
        ranked = sorted(
            values,
            key=lambda item: (
                float(item.get("mean_net_excess_return") if item.get("mean_net_excess_return") is not None else -999.0),
                float(item.get("mean_net_return") if item.get("mean_net_return") is not None else -999.0),
            ),
            reverse=True,
        )
        if not ranked:
            continue
        winner = ranked[0]
        frozen_index = next(
            (
                index
                for index, item in enumerate(ranked, start=1)
                if item.get("strategy") in {LEADING_PAPER_STRATEGY, LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY}
            ),
            None,
        )
        frozen = ranked[frozen_index - 1] if frozen_index is not None else None
        output.append(
            {
                "entry_price_source": entry_price_source,
                "market_regime_tag": tag,
                "eligible_strategy_count": len(ranked),
                "winner_strategy": winner.get("strategy"),
                "winner_label": winner.get("label"),
                "winner_trade_count": winner.get("period_count"),
                "winner_sample_count": winner.get("period_count"),
                "winner_mean_net_excess_return": winner.get("mean_net_excess_return"),
                "winner_positive_net_excess_rate": winner.get("positive_net_excess_rate"),
                "frozen_rank": frozen_index,
                "frozen_strategy": frozen.get("strategy") if frozen else LEADING_PAPER_STRATEGY,
                "frozen_label": frozen.get("label") if frozen else _strategy_label(LEADING_PAPER_STRATEGY),
                "frozen_trade_count": frozen.get("period_count") if frozen else None,
                "frozen_sample_count": frozen.get("period_count") if frozen else None,
                "frozen_mean_net_excess_return": frozen.get("mean_net_excess_return") if frozen else None,
                "frozen_is_winner": frozen_index == 1,
            }
        )
    return output


def _portfolio_confidence_intervals(period_rows: list[dict[str, Any]]) -> dict[str, Any]:
    monthly_rows = [
        row
        for row in period_rows
        if row.get("period_kind") == "month"
        and row.get("excess_return") is not None
        and row.get("period")
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in monthly_rows:
        grouped[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)

    rows: list[dict[str, Any]] = []
    for (entry_price_source, strategy), values in sorted(grouped.items(), key=lambda item: item[0]):
        excess = [float(item["excess_return"]) for item in values if item.get("excess_return") is not None]
        if len(excess) < 2:
            continue
        rng = random.Random(f"shortpick-strategy-slice-ci:{entry_price_source}:{strategy}")
        bootstrap_means = []
        for _ in range(1000):
            sample = [excess[rng.randrange(len(excess))] for _ in excess]
            bootstrap_means.append(_mean(sample))
        lower = _percentile(bootstrap_means, 0.025)
        upper = _percentile(bootstrap_means, 0.975)
        mean_value = _mean(excess)
        lower_positive = lower is not None and lower > 0
        sample = values[0]
        rows.append(
            {
                "id": f"{entry_price_source}_{strategy}_monthly_portfolio",
                "entry_price_source": entry_price_source,
                "strategy": strategy,
                "label": sample.get("label") or _strategy_label(strategy),
                "method": "monthly_portfolio_clustered_bootstrap",
                "mean_excess_return": _round(mean_value),
                "lower_excess_return": _round(lower),
                "upper_excess_return": _round(upper),
                "lower_bound_positive": lower_positive,
                "promotion_decision": "eligible_by_ci_lower_bound" if lower_positive else "blocked_by_ci_lower_bound",
                "sample_period_count": len(excess),
                "sample_date_count": len(excess),
                "sample_count": len(excess),
                "basis": "monthly_portfolio_excess_return",
            }
        )
    rows.sort(
        key=lambda item: (
            str(item["entry_price_source"]) != ENTRY_PRICE_SOURCE_NEXT_CLOSE,
            -float(item.get("lower_excess_return") if item.get("lower_excess_return") is not None else -999.0),
            -float(item.get("mean_excess_return") if item.get("mean_excess_return") is not None else -999.0),
        )
    )
    return {
        "status": "ready" if rows else "missing_artifact",
        "method": "monthly_portfolio_clustered_bootstrap",
        "basis": "full_window_staged_portfolio_monthly_excess",
        "note": "非 LLM 组合策略晋级只看月度组合超额 bootstrap 下沿是否为正；不使用短窗口候选均值替代。",
        "rows": rows,
        **({} if rows else {"reason": "staged portfolio artifact 缺少可用月度组合收益。"}),
    }


def _portfolio_stability_rows(
    period_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    monthly = [
        row
        for row in period_rows
        if row.get("period_kind") == "month"
        and row.get("period")
        and row.get("excess_return") is not None
    ]
    quarter_rows = _portfolio_period_group_rows(monthly, period_kind="quarter")
    year_rows = [row for row in period_rows if row.get("period_kind") == "year" and row.get("excess_return") is not None]
    summary_rows: list[dict[str, Any]] = []
    for period_kind, rows in (
        ("month", monthly),
        ("quarter", quarter_rows),
        ("year", year_rows),
    ):
        summary_rows.extend(_portfolio_period_summary_rows(rows, period_kind=period_kind))
    return {
        "status": "ready" if summary_rows or regime_rows else "missing_artifact",
        "basis": "full_window_staged_portfolio_period_and_regime_rows",
        "time_slices": {
            "month": monthly,
            "quarter": quarter_rows,
            "year": year_rows,
        },
        "period_summary_rows": summary_rows,
        "market_regime": {
            "status": "ready" if regime_rows else "missing_artifact",
            "basis": "monthly_portfolio_periods_grouped_by_market_regime",
            "rows": regime_rows,
            **({} if regime_rows else {"reason": "缺少月度行情标签或组合月度收益。"}),
        },
    }


def _portfolio_period_group_rows(rows: list[dict[str, Any]], *, period_kind: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        period = str(row.get("period") or "")
        if len(period) < 7:
            continue
        year = int(period[:4])
        month = int(period[5:7])
        if period_kind == "quarter":
            period_key = f"{year}-Q{((month - 1) // 3) + 1}"
        else:
            period_key = str(year)
        grouped[(str(row.get("entry_price_source")), str(row.get("strategy")), period_key)].append(row)
    output: list[dict[str, Any]] = []
    for (entry_price_source, strategy, period), values in sorted(grouped.items(), key=lambda item: item[0]):
        returns = [float(item["return"]) for item in values if item.get("return") is not None]
        benchmark = [float(item["benchmark_return"]) for item in values if item.get("benchmark_return") is not None]
        excess = [float(item["excess_return"]) for item in values if item.get("excess_return") is not None]
        sample = values[0]
        output.append(
            {
                "entry_price_source": entry_price_source,
                "strategy": strategy,
                "label": sample.get("label") or _strategy_label(strategy),
                "period_kind": period_kind,
                "period": period,
                "return": _round(_compound_returns(returns)),
                "benchmark_return": _round(_compound_returns(benchmark)),
                "excess_return": _round(_mean(excess)),
                "period_count": len(values),
                "basis": "monthly_portfolio_periods_grouped",
            }
        )
    return output


def _portfolio_period_summary_rows(rows: list[dict[str, Any]], *, period_kind: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)
    output: list[dict[str, Any]] = []
    for (entry_price_source, strategy), values in sorted(grouped.items(), key=lambda item: item[0]):
        excess = [float(item["excess_return"]) for item in values if item.get("excess_return") is not None]
        if not excess:
            continue
        best = max(values, key=lambda item: float(item.get("excess_return") if item.get("excess_return") is not None else -999.0))
        worst = min(values, key=lambda item: float(item.get("excess_return") if item.get("excess_return") is not None else 999.0))
        sample = values[0]
        output.append(
            {
                "entry_price_source": entry_price_source,
                "strategy": strategy,
                "label": sample.get("label") or _strategy_label(strategy),
                "period_kind": period_kind,
                "period_count": len(excess),
                "mean_excess_return": _round(_mean(excess)),
                "positive_excess_period_rate": _positive_rate(excess),
                "best_period": best.get("period"),
                "best_period_excess_return": best.get("excess_return"),
                "worst_period": worst.get("period"),
                "worst_period_excess_return": worst.get("excess_return"),
            }
        )
    return output


def _portfolio_return_attribution(
    period_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    monthly = [
        row
        for row in period_rows
        if row.get("period_kind") == "month"
        and row.get("period")
        and row.get("excess_return") is not None
    ]
    quarter = _portfolio_period_group_rows(monthly, period_kind="quarter")
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    regimes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    quarters: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in monthly:
        grouped[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)
    for row in regime_rows:
        regimes[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)
    for row in quarter:
        quarters[(str(row.get("entry_price_source")), str(row.get("strategy")))].append(row)

    for key, values in sorted(grouped.items(), key=lambda item: item[0]):
        entry_price_source, strategy = key
        excess = [float(item["excess_return"]) for item in values if item.get("excess_return") is not None]
        if not excess:
            continue
        best_month = max(values, key=lambda item: float(item.get("excess_return") if item.get("excess_return") is not None else -999.0))
        worst_month = min(values, key=lambda item: float(item.get("excess_return") if item.get("excess_return") is not None else 999.0))
        regime_values = regimes.get(key) or []
        quarter_values = quarters.get(key) or []
        best_regime = _best_row(regime_values, "mean_net_excess_return")
        worst_regime = _worst_row(regime_values, "mean_net_excess_return")
        best_quarter = _best_row(quarter_values, "excess_return")
        worst_quarter = _worst_row(quarter_values, "excess_return")
        sample = values[0]
        rows.append(
            {
                "entry_price_source": entry_price_source,
                "strategy": strategy,
                "label": sample.get("label") or _strategy_label(strategy),
                "mean_excess_return": _round(_mean(excess)),
                "sample_count": len(excess),
                "best_month": best_month.get("period"),
                "best_month_mean_excess_return": best_month.get("excess_return"),
                "worst_month": worst_month.get("period"),
                "worst_month_mean_excess_return": worst_month.get("excess_return"),
                "best_quarter": best_quarter.get("period") if best_quarter else None,
                "best_quarter_excess_return": best_quarter.get("excess_return") if best_quarter else None,
                "worst_quarter": worst_quarter.get("period") if worst_quarter else None,
                "worst_quarter_excess_return": worst_quarter.get("excess_return") if worst_quarter else None,
                "best_regime": best_regime.get("market_regime_tag") if best_regime else None,
                "best_regime_mean_excess_return": best_regime.get("mean_net_excess_return") if best_regime else None,
                "worst_regime": worst_regime.get("market_regime_tag") if worst_regime else None,
                "worst_regime_mean_excess_return": worst_regime.get("mean_net_excess_return") if worst_regime else None,
                "drop_best_month_mean_excess_return": _round(_mean([
                    float(item["excess_return"])
                    for item in values
                    if item.get("period") != best_month.get("period") and item.get("excess_return") is not None
                ])),
                "drop_worst_month_mean_excess_return": _round(_mean([
                    float(item["excess_return"])
                    for item in values
                    if item.get("period") != worst_month.get("period") and item.get("excess_return") is not None
                ])),
                "drop_best_regime_mean_excess_return": _drop_regime_mean(values, regime_values, best_regime),
                "symbol_industry_attribution_status": "missing_artifact",
                "symbol_industry_attribution_reason": "当前 staged portfolio artifact 只保留组合期度和少量 trades_sample，不足以证明完整股票/行业贡献；页面不得用样本片段外推。",
                "basis": "monthly_portfolio_periods_and_regime_rows",
            }
        )
    rows.sort(
        key=lambda item: (
            str(item["entry_price_source"]) != ENTRY_PRICE_SOURCE_NEXT_CLOSE,
            -float(item.get("mean_excess_return") if item.get("mean_excess_return") is not None else -999.0),
        )
    )
    return {
        "status": "ready" if rows else "missing_artifact",
        "basis": "full_window_staged_portfolio_period_and_regime_rows",
        "horizon_days": 5,
        "rows": rows,
        "symbol_industry": {
            "status": "missing_artifact",
            "reason": "完整股票/行业归因需要全量逐笔交易 artifact；当前仅使用组合期度归因，不用 trades_sample 外推。",
        },
        **({} if rows else {"reason": "staged portfolio artifact 缺少组合期度收益。"}),
    }


def _drop_regime_mean(
    period_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
    best_regime: dict[str, Any] | None,
) -> float | None:
    if not best_regime:
        return None
    tag = best_regime.get("market_regime_tag")
    excluded_periods = set()
    for row in regime_rows:
        if row.get("market_regime_tag") != tag:
            continue
        excluded_periods.update(str(period) for period in row.get("periods") or [])
    remaining = [
        float(row["excess_return"])
        for row in period_rows
        if row.get("excess_return") is not None and str(row.get("period")) not in excluded_periods
    ]
    return _round(_mean(remaining))


def _best_row(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    values = [row for row in rows if row.get(field) is not None]
    return None if not values else max(values, key=lambda item: float(item.get(field) or 0.0))


def _worst_row(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    values = [row for row in rows if row.get(field) is not None]
    return None if not values else min(values, key=lambda item: float(item.get(field) or 0.0))


def _compound_returns(values: list[float]) -> float | None:
    if not values:
        return None
    total = 1.0
    for value in values:
        total *= 1.0 + value
    return total - 1.0


def _percentile(values: list[float | None], pct: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    fraction = position - lower
    return clean[lower] + (clean[upper] - clean[lower]) * fraction


def _contexts_by_signal_day(series_by_symbol: dict[str, Any], *, signal_days: list[date]) -> dict[date, list[dict[str, Any]]]:
    output: dict[date, list[dict[str, Any]]] = {day: [] for day in signal_days}
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        for signal_day in signal_days:
            context = _context_for_signal_day(series, signal_day)
            if context is not None:
                output[signal_day].append(context)
    return output


def _regime_features_from_contexts(
    contexts_by_day: dict[date, list[dict[str, Any]]],
    *,
    pool_limit: int,
) -> dict[date, dict[str, float]]:
    features_by_day: dict[date, dict[str, float]] = {}
    for signal_day, contexts in contexts_by_day.items():
        if not contexts:
            continue
        pool = sorted(
            contexts,
            key=lambda item: (
                float(item["return_1d"]),
                float(item["amount"]),
                float(item["turnover_rate"]),
            ),
            reverse=True,
        )[:pool_limit]
        if not pool:
            continue
        features_by_day[signal_day] = {
            "universe_ret10_mean": _mean([float(item["return_10d"]) for item in contexts]) or 0.0,
            "universe_breadth10": sum(1 for item in contexts if float(item["return_10d"]) > 0) / len(contexts),
            "pool_ret1_mean": _mean([float(item["return_1d"]) for item in pool]) or 0.0,
            "pool_ret10_mean": _mean([float(item["return_10d"]) for item in pool]) or 0.0,
        }
    return features_by_day


def _build_strategy_selections_from_contexts(
    contexts_by_day: dict[date, list[dict[str, Any]]],
    *,
    strategy: str,
    pool_limit: int,
    rank_limit: int,
) -> dict[date, list[str]]:
    selections: dict[date, list[str]] = {}
    for signal_day, contexts in contexts_by_day.items():
        effective_pool_limit = pool_limit

        def pool_sort_key(item: dict[str, Any]) -> tuple[float, float, float] | tuple[float, float]:
            return (
                float(item["return_1d"]),
                float(item["amount"]),
                float(item["turnover_rate"]),
            )

        if strategy == LOW_TURNOVER_UPTREND_STRATEGY:
            effective_pool_limit = max(pool_limit, 120)

            def pool_sort_key(item: dict[str, Any]) -> tuple[float, float]:
                return (float(item["amount"]), float(item["turnover_rate"]))

        elif strategy == QUIET_BREAKOUT_BASE_STRATEGY:
            effective_pool_limit = max(pool_limit, 80)

            def pool_sort_key(item: dict[str, Any]) -> tuple[float, float]:
                return (-abs(float(item["return_1d"])), float(item["amount"]))

        pool = sorted(contexts, key=pool_sort_key, reverse=True)[:effective_pool_limit]
        if not pool:
            selections[signal_day] = []
            continue
        if strategy == "base":
            ranked = pool
        elif strategy == "momentum_volume_golden_cross_10_200":
            ranked = [item for item in pool if item.get("golden_cross_10_200")]
        else:
            ranked = sorted(pool, key=lambda item, current_strategy=strategy: _strategy_score(pool, item, current_strategy), reverse=True)
        if strategy == LOW_TURNOVER_UPTREND_STRATEGY:
            ranked = [item for item in ranked if float(item.get("return_20d") or 0.0) > 0.0]
        elif strategy == QUIET_BREAKOUT_BASE_STRATEGY:
            quiet_pick = ranked[1] if len(ranked) >= 2 else None
            if (
                quiet_pick is None
                or float(quiet_pick.get("return_10d") or 0.0) < 0.0
                or float(quiet_pick.get("return_1d") or 0.0) > 0.04
            ):
                ranked = []
        if strategy == "ret10_turnover_cooldown_diversified":
            ranked = _industry_diversified_rank(ranked, rank_limit=rank_limit, max_per_industry=2)
        selections[signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections


def _regime_coverage_rows(signal_days: list[date], regime_tags: dict[date, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[date]] = defaultdict(list)
    for day in signal_days:
        tag = regime_tags.get(day, {}).get("market_regime_tag") or "missing_regime"
        grouped[str(tag)].append(day)
    rows: list[dict[str, Any]] = []
    for tag, days in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        sample = regime_tags.get(days[0], {})
        rows.append(
            {
                "market_regime_tag": tag,
                "trend_regime": sample.get("trend_regime") or "missing",
                "volatility_regime": sample.get("volatility_regime") or "missing",
                "size_style_regime": sample.get("size_style_regime") or "missing",
                "signal_day_count": len(days),
                "date_from": days[0].isoformat(),
                "date_to": days[-1].isoformat(),
            }
        )
    return rows


def _regime_winner_rows(rows: list[dict[str, Any]], *, min_trade_count: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row.get("trade_count") or 0) >= min_trade_count:
            grouped[(str(row.get("entry_price_source")), str(row.get("market_regime_tag")))].append(row)

    output: list[dict[str, Any]] = []
    for (entry_price_source, market_regime_tag), values in sorted(grouped.items(), key=lambda item: item[0]):
        ranked = sorted(
            values,
            key=lambda item: (
                float(item.get("mean_net_excess_return") if item.get("mean_net_excess_return") is not None else -999.0),
                float(item.get("mean_net_return") if item.get("mean_net_return") is not None else -999.0),
                int(item.get("trade_count") or 0),
            ),
            reverse=True,
        )
        winner = ranked[0]
        frozen_index = next(
            (
                index
                for index, item in enumerate(ranked, start=1)
                if item.get("strategy") in {LEADING_PAPER_STRATEGY, LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY}
            ),
            None,
        )
        frozen = ranked[frozen_index - 1] if frozen_index is not None else None
        output.append(
            {
                "entry_price_source": entry_price_source,
                "market_regime_tag": market_regime_tag,
                "eligible_strategy_count": len(ranked),
                "winner_strategy": winner.get("strategy"),
                "winner_label": winner.get("label"),
                "winner_trade_count": winner.get("trade_count"),
                "winner_mean_net_excess_return": winner.get("mean_net_excess_return"),
                "winner_positive_net_excess_rate": winner.get("positive_net_excess_rate"),
                "frozen_rank": frozen_index,
                "frozen_strategy": frozen.get("strategy") if frozen else LEADING_PAPER_STRATEGY,
                "frozen_label": frozen.get("label") if frozen else _strategy_label(LEADING_PAPER_STRATEGY),
                "frozen_trade_count": frozen.get("trade_count") if frozen else None,
                "frozen_mean_net_excess_return": frozen.get("mean_net_excess_return") if frozen else None,
                "frozen_is_winner": frozen_index == 1,
            }
        )
    return output


def _sample_adequacy(
    *,
    signal_days: list[date],
    regime_coverage_rows: list[dict[str, Any]],
    min_regime_trade_count: int,
) -> dict[str, Any]:
    years = sorted({day.year for day in signal_days})
    broad_window_ready = len(years) >= 3 and len(signal_days) >= 500
    useful_regime_count = sum(1 for row in regime_coverage_rows if int(row.get("signal_day_count") or 0) >= 20)
    sparse_regimes = [row["market_regime_tag"] for row in regime_coverage_rows if int(row.get("signal_day_count") or 0) < 20]
    return {
        "status": "ready" if broad_window_ready and useful_regime_count >= 4 else "partial_ready",
        "broad_window_ready": broad_window_ready,
        "regime_slice_ready": useful_regime_count >= 4,
        "signal_day_count": len(signal_days),
        "year_count": len(years),
        "years": years,
        "useful_regime_count": useful_regime_count,
        "sparse_regimes": sparse_regimes,
        "min_regime_trade_count": min_regime_trade_count,
        "limitations": [
            "This long-window artifact covers deterministic market-factor strategy families, not historical LLM free-pick replay.",
            "Regime labels are offline index-derived slices; they support comparison, but do not by themselves prove live execution quality.",
        ],
    }


def _positive_rate(values: list[float]) -> float | None:
    return None if not values else round(sum(1 for value in values if value > 0) / len(values), 6)


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, date):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output
