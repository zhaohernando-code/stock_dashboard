from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    INDEX_SYMBOLS,
    LOW_TURNOVER_UPTREND_STRATEGY,
    QUIET_BREAKOUT_BASE_STRATEGY,
    _benchmark_note,
    _benchmark_return,
    _build_strategy_selections,
    _context_for_signal_day,
    _entry_is_unfillable_limit_up,
    _limit_band,
    _load_daily_series,
    _mean,
    _near,
    _stddev,
    _trimmed_mean,
)
from ashare_evidence.shortpick_policy import SHORTPICK_FROZEN_STRATEGY_CONFIG

TRADING_DAYS_PER_YEAR = 252
SHORTPICK_PORTFOLIO_BACKTEST_VERSION = "shortpick-portfolio-backtest-v1"
LEADING_PAPER_STRATEGY = "low_turnover_20d_uptrend_liquid_top120"
LEADING_PAPER_MODE = "daily_rolling_5x10k"
TOP3_EQUAL_WEIGHT_STRATEGY = "ret10_turnover_top3_market_positive_cooldown_equal_weight"
GOLDEN_CROSS_STRATEGY = "momentum_volume_golden_cross_10_200"
_CONTROL_CONFIG = SHORTPICK_FROZEN_STRATEGY_CONFIG["controls"]
_STRONG_BREADTH_RANK2_CONFIG = _CONTROL_CONFIG["strong_breadth_rank2"]
STRONG_BREADTH_RANK2_STRATEGY = str(_STRONG_BREADTH_RANK2_CONFIG["strategy"])
_LOW_TURNOVER_UPTREND_CONFIG = _CONTROL_CONFIG["low_turnover_uptrend"]
_QUIET_BREAKOUT_RANK2_CONFIG = _CONTROL_CONFIG["quiet_breakout_rank2"]
LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY = str(_LOW_TURNOVER_UPTREND_CONFIG["strategy"])
QUIET_BREAKOUT_RANK2_STRATEGY = str(_QUIET_BREAKOUT_RANK2_CONFIG["strategy"])
DEFAULT_PORTFOLIO_STRATEGIES = (
    "base",
    "ret10",
    "ret10_turnover",
    "ret10_turnover_cooldown",
    "ret10_turnover_cooldown_market_positive",
    "ret10_turnover_cooldown_market_positive_cooldown",
    "ret10_turnover_strong_breadth_pool",
    "ret10_turnover_second_market_positive_cooldown",
    "ret10_turnover_second_market_positive_cooldown_stop8",
    STRONG_BREADTH_RANK2_STRATEGY,
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
    TOP3_EQUAL_WEIGHT_STRATEGY,
    GOLDEN_CROSS_STRATEGY,
    "turnover",
)
BASE_STRATEGY_BY_VARIANT = {
    "ret10_turnover_cooldown_market_positive": "ret10_turnover_cooldown",
    "ret10_turnover_cooldown_market_positive_cooldown": "ret10_turnover_cooldown",
    "ret10_turnover_strong_breadth_pool": "ret10_turnover",
    "ret10_turnover_second_market_positive_cooldown": "ret10_turnover",
    "ret10_turnover_second_market_positive_cooldown_stop8": "ret10_turnover",
    STRONG_BREADTH_RANK2_STRATEGY: "ret10_amount_turnover_cooldown",
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY: LOW_TURNOVER_UPTREND_STRATEGY,
    QUIET_BREAKOUT_RANK2_STRATEGY: QUIET_BREAKOUT_BASE_STRATEGY,
    TOP3_EQUAL_WEIGHT_STRATEGY: "ret10_turnover",
}
SECOND_PICK_VARIANTS = {
    "ret10_turnover_second_market_positive_cooldown",
    "ret10_turnover_second_market_positive_cooldown_stop8",
    STRONG_BREADTH_RANK2_STRATEGY,
    QUIET_BREAKOUT_RANK2_STRATEGY,
}
TOP3_EQUAL_WEIGHT_VARIANTS = {TOP3_EQUAL_WEIGHT_STRATEGY}
STOP_LOSS_BY_STRATEGY = {
    "ret10_turnover_second_market_positive_cooldown_stop8": 0.08,
    STRONG_BREADTH_RANK2_STRATEGY: float(_STRONG_BREADTH_RANK2_CONFIG["stop_loss_pct"]),
    QUIET_BREAKOUT_RANK2_STRATEGY: float(_QUIET_BREAKOUT_RANK2_CONFIG["stop_loss_pct"]),
    TOP3_EQUAL_WEIGHT_STRATEGY: 0.08,
}
INDEX_REFERENCE_LABELS = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
}


@dataclass(frozen=True)
class _TradeIntent:
    signal_day: date
    entry_day: date
    exit_day: date
    symbol: str
    strategy: str
    sleeve_weight: float = 1.0


@dataclass
class _OpenTrade:
    signal_day: date
    entry_day: date
    exit_day: date
    symbol: str
    strategy: str
    investment: float
    entry_close: float


def build_shortpick_portfolio_backtest(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    pool_limit: int = 40,
    rank_limit: int = 6,
    horizon_days: int = 5,
    initial_cash: float = 50_000.0,
    daily_sleeve_cash: float = 10_000.0,
    cost_bps: float = 20.0,
    benchmark_mode: str = "universe_equal_weight",
    apply_limit_up_filter: bool = True,
    apply_limit_down_exit_filter: bool = True,
    min_signal_symbol_count: int = 45,
    strategies: tuple[str, ...] = DEFAULT_PORTFOLIO_STRATEGIES,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
) -> dict[str, Any]:
    """Backtest the two short-line capital deployment modes on a long market-only sample."""
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
    trade_days = _trade_days(series_by_symbol, start_date=start_date, end_date=end_date, min_symbol_count=min_signal_symbol_count)
    selections = {
        strategy: _build_strategy_selections(
            series_by_symbol,
            signal_days=signal_days,
            strategy=BASE_STRATEGY_BY_VARIANT.get(strategy, strategy),
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
        for strategy in strategies
    }
    selections = {
        strategy: _apply_strategy_selection_transform(strategy, strategy_selections)
        for strategy, strategy_selections in selections.items()
    }
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    selections = {
        strategy: _apply_strategy_regime_filter(strategy, strategy_selections, regime_features)
        for strategy, strategy_selections in selections.items()
    }

    modes = ("daily_rolling_5x10k", "weekly_concentrated_1x50k")
    results: dict[str, dict[str, Any]] = {}
    for mode in modes:
        mode_results = {}
        for strategy in strategies:
            intents = _build_trade_intents(
                series_by_symbol=series_by_symbol,
                selections=selections.get(strategy, {}),
                strategy=strategy,
                mode=mode,
                horizon_days=horizon_days,
                apply_limit_up_filter=apply_limit_up_filter,
            )
            mode_results[strategy] = _simulate_portfolio(
                series_by_symbol,
                benchmark=benchmark,
                benchmark_mode=benchmark_mode,
                trade_days=trade_days,
                intents=intents,
                mode=mode,
                strategy=strategy,
                initial_cash=initial_cash,
                daily_sleeve_cash=daily_sleeve_cash,
                cost_bps=cost_bps,
                stop_loss_pct=STOP_LOSS_BY_STRATEGY.get(strategy),
                apply_limit_down_exit_filter=apply_limit_down_exit_filter,
            )
        results[mode] = mode_results
    comparison = _compare_results(results)
    production_evidence = _build_production_evidence(
        series_by_symbol,
        benchmark=benchmark,
        benchmark_mode=benchmark_mode,
        trade_days=trade_days,
        selections=selections,
        results=results,
        horizon_days=horizon_days,
        apply_limit_up_filter=apply_limit_up_filter,
        apply_limit_down_exit_filter=apply_limit_down_exit_filter,
        initial_cash=initial_cash,
        daily_sleeve_cash=daily_sleeve_cash,
    )
    benchmark_references = _benchmark_references(
        series_by_symbol,
        trade_days=trade_days,
        initial_cash=initial_cash,
    )

    return {
        "experiment": "shortpick_portfolio_backtest",
        "version": SHORTPICK_PORTFOLIO_BACKTEST_VERSION,
        "validation_mode": "market_only_after_close_t_plus_1_close_entry_portfolio",
        "config": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "pool_limit": pool_limit,
            "rank_limit": rank_limit,
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "daily_sleeve_cash": daily_sleeve_cash,
            "cost_bps": cost_bps,
            "benchmark_mode": benchmark_mode,
            "apply_limit_up_filter": apply_limit_up_filter,
            "apply_limit_down_exit_filter": apply_limit_down_exit_filter,
            "min_signal_symbol_count": min_signal_symbol_count,
            "account_profile": account_eligibility["account_profile"],
            "strategies": list(strategies),
            "strategy_variants": _strategy_variant_contract(),
        },
        "data_scope": {
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "raw_stock_like_series_count": len([symbol for symbol in raw_series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "account_eligibility": account_eligibility,
            "benchmark_note": _benchmark_note(series_by_symbol, benchmark_mode),
            "sample_concentration_note": _sample_concentration_note(signal_days),
        },
        "results": results,
        "comparison": comparison,
        "benchmark_references": benchmark_references,
        "production_evidence": production_evidence,
    }


def write_shortpick_portfolio_backtest(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    import json

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def _eligible_signal_days(
    series_by_symbol: dict[str, Any],
    *,
    start_date: date,
    end_date: date,
    min_signal_symbol_count: int,
) -> list[date]:
    counts: dict[date, int] = defaultdict(int)
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        for index, bar in enumerate(series.bars):
            if start_date <= bar.day <= end_date and index >= 20 and index + 6 < len(series.bars):
                if _context_for_signal_day(series, bar.day) is not None:
                    counts[bar.day] += 1
    return [day for day in sorted(counts) if counts[day] >= min_signal_symbol_count]


def _trade_days(
    series_by_symbol: dict[str, Any],
    *,
    start_date: date,
    end_date: date,
    min_symbol_count: int,
) -> list[date]:
    counts: dict[date, int] = defaultdict(int)
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        for bar in series.bars:
            if start_date <= bar.day <= end_date:
                counts[bar.day] += 1
    return [day for day in sorted(counts) if counts[day] >= min_symbol_count]


def _build_trade_intents(
    series_by_symbol: dict[str, Any],
    selections: dict[date, list[str]],
    *,
    strategy: str,
    mode: str,
    horizon_days: int,
    apply_limit_up_filter: bool,
) -> list[_TradeIntent]:
    signal_days = sorted(selections)
    if mode == "weekly_concentrated_1x50k":
        grouped: dict[tuple[int, int], list[date]] = defaultdict(list)
        for signal_day in signal_days:
            iso = signal_day.isocalendar()
            grouped[(iso.year, iso.week)].append(signal_day)
        signal_days = [max(days) for _, days in sorted(grouped.items())]

    intents: list[_TradeIntent] = []
    for signal_day in signal_days:
        symbols = selections.get(signal_day) or []
        if not symbols:
            continue
        selected_symbols = symbols[:3] if strategy in TOP3_EQUAL_WEIGHT_VARIANTS else symbols[:1]
        sleeve_weight = 1.0 / len(selected_symbols) if selected_symbols else 1.0
        for symbol in selected_symbols:
            series = series_by_symbol.get(symbol)
            if series is None:
                continue
            signal_index = series.by_day.get(signal_day)
            if signal_index is None:
                continue
            entry_index = signal_index + 1
            exit_index = entry_index + horizon_days
            if exit_index >= len(series.bars):
                continue
            if apply_limit_up_filter and _entry_is_unfillable_limit_up(series, entry_index):
                continue
            intents.append(
                _TradeIntent(
                    signal_day=signal_day,
                    entry_day=series.bars[entry_index].day,
                    exit_day=series.bars[exit_index].day,
                    symbol=symbol,
                    strategy=strategy,
                    sleeve_weight=sleeve_weight,
                )
            )
    return intents


def _apply_strategy_selection_transform(strategy: str, selections: dict[date, list[str]]) -> dict[date, list[str]]:
    if strategy not in SECOND_PICK_VARIANTS:
        if strategy not in TOP3_EQUAL_WEIGHT_VARIANTS:
            return selections
        return {
            signal_day: symbols[:3] if len(symbols) >= 3 else []
            for signal_day, symbols in selections.items()
        }
    return {
        signal_day: symbols[1:2] if len(symbols) >= 2 else []
        for signal_day, symbols in selections.items()
    }


def _regime_features_by_day(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
) -> dict[date, dict[str, float]]:
    features_by_day: dict[date, dict[str, float]] = {}
    for signal_day in signal_days:
        contexts = [
            context
            for symbol, series in series_by_symbol.items()
            if symbol not in INDEX_SYMBOLS
            for context in [_context_for_signal_day(series, signal_day)]
            if context is not None
        ]
        if not contexts:
            continue
        pool = sorted(
            contexts,
            key=lambda item: (
                item["return_1d"],
                item["amount"],
                item["turnover_rate"],
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


def _apply_strategy_regime_filter(
    strategy: str,
    selections: dict[date, list[str]],
    regime_features: dict[date, dict[str, float]],
) -> dict[date, list[str]]:
    if strategy not in BASE_STRATEGY_BY_VARIANT:
        return selections
    output: dict[date, list[str]] = {}
    for signal_day, symbols in selections.items():
        features = regime_features.get(signal_day) or {}
        output[signal_day] = symbols if _strategy_regime_allows(strategy, features) else []
    return output


def _strategy_regime_allows(strategy: str, features: dict[str, float]) -> bool:
    if strategy == "ret10_turnover_cooldown_market_positive":
        return float(features.get("universe_ret10_mean", -999.0)) >= 0.0
    if strategy == "ret10_turnover_cooldown_market_positive_cooldown":
        return (
            float(features.get("universe_ret10_mean", -999.0)) >= 0.0
            and float(features.get("pool_ret1_mean", 999.0)) <= 0.08
        )
    if strategy == "ret10_turnover_strong_breadth_pool":
        return (
            float(features.get("universe_breadth10", -999.0)) >= 0.55
            and float(features.get("pool_ret10_mean", -999.0)) >= 0.06
        )
    if strategy == STRONG_BREADTH_RANK2_STRATEGY:
        return (
            float(features.get("universe_breadth10", -999.0)) >= float(_STRONG_BREADTH_RANK2_CONFIG["breadth10_min"])
            and float(features.get("pool_ret1_mean", 999.0)) <= float(_STRONG_BREADTH_RANK2_CONFIG["pool_ret1_max"])
            and float(features.get("pool_ret10_mean", -999.0)) >= float(_STRONG_BREADTH_RANK2_CONFIG["pool_ret10_min"])
        )
    if strategy == LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY:
        return float(features.get("universe_breadth10", -999.0)) >= float(_LOW_TURNOVER_UPTREND_CONFIG["breadth10_min"])
    if strategy == QUIET_BREAKOUT_RANK2_STRATEGY:
        return True
    if strategy in SECOND_PICK_VARIANTS or strategy in TOP3_EQUAL_WEIGHT_VARIANTS:
        return (
            float(features.get("universe_ret10_mean", -999.0)) >= 0.0
            and float(features.get("pool_ret1_mean", 999.0)) <= 0.08
        )
    return True


def _simulate_portfolio(
    series_by_symbol: dict[str, Any],
    *,
    benchmark: Any,
    benchmark_mode: str,
    trade_days: list[date],
    intents: list[_TradeIntent],
    mode: str,
    strategy: str,
    initial_cash: float,
    daily_sleeve_cash: float,
    cost_bps: float,
    stop_loss_pct: float | None = None,
    apply_limit_down_exit_filter: bool = True,
) -> dict[str, Any]:
    intents_by_entry: dict[date, list[_TradeIntent]] = defaultdict(list)
    for intent in intents:
        intents_by_entry[intent.entry_day].append(intent)

    cash = float(initial_cash)
    cost_rate = float(cost_bps) / 10000.0
    open_trades: list[_OpenTrade] = []
    closed_trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked_exits: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    benchmark_nav = float(initial_cash)
    previous_day: date | None = None

    for current_day in trade_days:
        if previous_day is not None:
            daily_benchmark_return, _ = _benchmark_return(
                series_by_symbol=series_by_symbol,
                benchmark=benchmark,
                benchmark_mode=benchmark_mode,
                entry_day=previous_day,
                exit_day=current_day,
            )
            if daily_benchmark_return is not None:
                benchmark_nav *= 1.0 + float(daily_benchmark_return)

        still_open: list[_OpenTrade] = []
        for trade in open_trades:
            exit_close = _close_on(series_by_symbol, trade.symbol, current_day)
            early_exit_reason = None
            if (
                stop_loss_pct is not None
                and current_day != trade.entry_day
                and exit_close is not None
                and trade.entry_close > 0
                and exit_close / trade.entry_close - 1.0 <= -float(stop_loss_pct)
            ):
                early_exit_reason = "close_stop_loss"
            if trade.exit_day != current_day and early_exit_reason is None:
                still_open.append(trade)
                continue
            if exit_close is None:
                still_open.append(trade)
                continue
            current_series = series_by_symbol.get(trade.symbol)
            current_index = current_series.by_day.get(current_day) if current_series is not None else None
            if (
                apply_limit_down_exit_filter
                and current_series is not None
                and current_index is not None
                and _exit_is_unfillable_limit_down(current_series, current_index)
            ):
                blocked_exits.append(
                    {
                        "signal_day": trade.signal_day.isoformat(),
                        "intended_exit_day": trade.exit_day.isoformat(),
                        "blocked_day": current_day.isoformat(),
                        "symbol": trade.symbol,
                        "reason": "exit_unfillable_limit_down",
                        "trigger": early_exit_reason or "planned_horizon",
                    }
                )
                still_open.append(trade)
                continue
            stock_return = exit_close / trade.entry_close - 1.0 if trade.entry_close else 0.0
            net_return = stock_return - cost_rate
            proceeds = trade.investment * (1.0 + net_return)
            cash += proceeds
            closed_trades.append(
                {
                    "signal_day": trade.signal_day.isoformat(),
                    "entry_day": trade.entry_day.isoformat(),
                    "exit_day": current_day.isoformat(),
                    "intended_exit_day": trade.exit_day.isoformat(),
                    "symbol": trade.symbol,
                    "investment": round(trade.investment, 6),
                    "stock_return": round(stock_return, 6),
                    "net_return": round(net_return, 6),
                    "pnl": round(proceeds - trade.investment, 6),
                    "exit_reason": early_exit_reason or "planned_horizon",
                }
            )
        open_trades = still_open

        entry_intents = intents_by_entry.get(current_day, [])
        entry_base_cash = float(daily_sleeve_cash) if mode == "daily_rolling_5x10k" else cash
        for intent in entry_intents:
            entry_close = _close_on(series_by_symbol, intent.symbol, current_day)
            if entry_close is None:
                skipped.append({"signal_day": intent.signal_day.isoformat(), "symbol": intent.symbol, "reason": "missing_entry_close"})
                continue
            target_cash = entry_base_cash * max(float(intent.sleeve_weight), 0.0)
            investment = min(float(target_cash), cash)
            if investment <= 0:
                skipped.append({"signal_day": intent.signal_day.isoformat(), "symbol": intent.symbol, "reason": "insufficient_cash"})
                continue
            cash -= investment
            open_trades.append(
                _OpenTrade(
                    signal_day=intent.signal_day,
                    entry_day=intent.entry_day,
                    exit_day=intent.exit_day,
                    symbol=intent.symbol,
                    strategy=intent.strategy,
                    investment=investment,
                    entry_close=entry_close,
                )
            )

        market_value = sum(_marked_value(series_by_symbol, trade, current_day) for trade in open_trades)
        nav = cash + market_value
        timeline.append(
            {
                "date": current_day.isoformat(),
                "nav": round(nav, 6),
                "cash": round(cash, 6),
                "market_value": round(market_value, 6),
                "benchmark_nav": round(benchmark_nav, 6),
                "open_position_count": len(open_trades),
                "capital_deployed": round(market_value, 6),
            }
        )
        previous_day = current_day

    return {
        "mode": mode,
        "strategy": strategy,
        "label": _strategy_label(strategy),
        "summary": _portfolio_metrics(
            timeline,
            closed_trades=closed_trades,
            skipped=skipped,
            blocked_exits=blocked_exits,
            initial_cash=initial_cash,
        ),
        "monthly": _monthly_returns(timeline),
        "yearly": _yearly_returns(timeline),
        "trades_sample": closed_trades[:20],
        "skipped_sample": skipped[:20],
        "blocked_exit_sample": blocked_exits[:20],
    }


def _close_on(series_by_symbol: dict[str, Any], symbol: str, day: date) -> float | None:
    series = series_by_symbol.get(symbol)
    if series is None:
        return None
    index = series.by_day.get(day)
    if index is None:
        return None
    return float(series.bars[index].close)


def _marked_value(series_by_symbol: dict[str, Any], trade: _OpenTrade, day: date) -> float:
    close = _close_on(series_by_symbol, trade.symbol, day)
    if close is None or trade.entry_close <= 0:
        return trade.investment
    return trade.investment * close / trade.entry_close


def _exit_is_unfillable_limit_down(series: Any, exit_index: int) -> bool:
    exit_bar = series.bars[exit_index]
    previous = series.bars[exit_index - 1] if exit_index > 0 else None
    if previous is None or not previous.close:
        return True
    one_price = _near(exit_bar.open, exit_bar.high) and _near(exit_bar.high, exit_bar.low) and _near(exit_bar.low, exit_bar.close)
    limit_band = _limit_band(series.symbol, series.name)
    day_return = exit_bar.close / previous.close - 1
    return bool(one_price and day_return <= -limit_band * 0.95)


def _portfolio_metrics(
    timeline: list[dict[str, Any]],
    *,
    closed_trades: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    blocked_exits: list[dict[str, Any]],
    initial_cash: float,
) -> dict[str, Any]:
    navs = [float(point["nav"]) for point in timeline]
    benchmark_navs = [float(point["benchmark_nav"]) for point in timeline]
    returns = [float(trade["net_return"]) for trade in closed_trades]
    exit_reason_counts = _count_by([str(trade.get("exit_reason") or "unknown") for trade in closed_trades])
    final_nav = navs[-1] if navs else float(initial_cash)
    benchmark_final_nav = benchmark_navs[-1] if benchmark_navs else float(initial_cash)
    total_return = final_nav / float(initial_cash) - 1.0 if initial_cash else 0.0
    benchmark_return = benchmark_final_nav / float(initial_cash) - 1.0 if initial_cash else 0.0
    day_count = len(timeline)
    return {
        "trade_count": len(closed_trades),
        "skipped_count": len(skipped),
        "blocked_exit_count": len(blocked_exits),
        "day_count": day_count,
        "final_nav": round(final_nav, 6),
        "total_return": round(total_return, 6),
        "benchmark_total_return": round(benchmark_return, 6),
        "excess_total_return": round(total_return - benchmark_return, 6),
        "annualized_return": _annualized(total_return, day_count),
        "annualized_excess_return": _annualized(total_return, day_count, benchmark_return=benchmark_return),
        "max_drawdown": _max_drawdown(navs),
        "benchmark_max_drawdown": _max_drawdown(benchmark_navs),
        "mean_trade_net_return": _mean(returns),
        "trimmed_mean_trade_net_return": _trimmed_mean(returns),
        "trade_win_rate": sum(1 for value in returns if value > 0) / len(returns) if returns else None,
        "trade_return_volatility": _stddev(returns),
        "exit_reason_counts": exit_reason_counts,
        "max_open_position_count": max((int(point["open_position_count"]) for point in timeline), default=0),
        "max_capital_deployed": max((float(point["capital_deployed"]) for point in timeline), default=0.0),
        "evidence_grade": _evidence_grade(closed_trades, timeline),
    }


def _annualized(total_return: float, day_count: int, *, benchmark_return: float | None = None) -> float | None:
    if day_count <= 0:
        return None
    annualized = (1.0 + float(total_return)) ** (TRADING_DAYS_PER_YEAR / float(day_count)) - 1.0
    if benchmark_return is None:
        return round(annualized, 6)
    benchmark_annualized = (1.0 + float(benchmark_return)) ** (TRADING_DAYS_PER_YEAR / float(day_count)) - 1.0
    return round(annualized - benchmark_annualized, 6)


def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            drawdown = min(drawdown, value / peak - 1.0)
    return round(drawdown, 6)


def _count_by(values: list[str]) -> dict[str, int]:
    output: dict[str, int] = {}
    for value in values:
        output[value] = output.get(value, 0) + 1
    return output


def _monthly_returns(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in timeline:
        grouped[str(point["date"])[:7]].append(point)
    return [_period_return(month, points) for month, points in sorted(grouped.items())]


def _yearly_returns(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in timeline:
        grouped[str(point["date"])[:4]].append(point)
    return [_period_return(year, points) for year, points in sorted(grouped.items())]


def _period_return(label: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {"period": label, "return": None, "benchmark_return": None, "excess_return": None}
    start_nav = float(points[0]["nav"])
    end_nav = float(points[-1]["nav"])
    start_benchmark = float(points[0]["benchmark_nav"])
    end_benchmark = float(points[-1]["benchmark_nav"])
    strategy_return = end_nav / start_nav - 1.0 if start_nav else None
    benchmark_return = end_benchmark / start_benchmark - 1.0 if start_benchmark else None
    return {
        "period": label,
        "return": None if strategy_return is None else round(strategy_return, 6),
        "benchmark_return": None if benchmark_return is None else round(benchmark_return, 6),
        "excess_return": None if strategy_return is None or benchmark_return is None else round(strategy_return - benchmark_return, 6),
    }


def _evidence_grade(closed_trades: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> str:
    years = {str(point["date"])[:4] for point in timeline}
    if len(closed_trades) >= 180 and len(years) >= 3:
        return "long_sample"
    if len(closed_trades) >= 80 and len(years) >= 2:
        return "medium_sample"
    return "exploratory"


def _compare_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for mode, strategies in results.items():
        for strategy, payload in strategies.items():
            summary = payload.get("summary") or {}
            rows.append(
                {
                    "mode": mode,
                    "strategy": strategy,
                    "label": payload.get("label") or strategy,
                    "trade_count": summary.get("trade_count"),
                    "total_return": summary.get("total_return"),
                    "excess_total_return": summary.get("excess_total_return"),
                    "max_drawdown": summary.get("max_drawdown"),
                    "evidence_grade": summary.get("evidence_grade"),
                }
            )
    ranked = sorted(
        rows,
        key=lambda row: (
            float(row["excess_total_return"] if row["excess_total_return"] is not None else -999.0),
            float(row["total_return"] if row["total_return"] is not None else -999.0),
            -abs(float(row["max_drawdown"] if row["max_drawdown"] is not None else -999.0)),
        ),
        reverse=True,
    )
    return {
        "ranked": ranked,
        "recommended": ranked[0] if ranked else None,
        "decision_note": (
            "Long-sample market-factor evidence only; LLM replay remains a separate short-window overlay until sealed historical LLM samples cover multiple regimes."
        ),
    }


def _benchmark_references(
    series_by_symbol: dict[str, Any],
    *,
    trade_days: list[date],
    initial_cash: float,
) -> dict[str, dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for symbol, label in INDEX_REFERENCE_LABELS.items():
        series = series_by_symbol.get(symbol)
        if series is None:
            references[symbol] = {"label": label, "available": False, "reason": "missing_series"}
            continue
        navs: list[float] = []
        first_close: float | None = None
        used_days = 0
        for day in trade_days:
            index = series.by_day.get(day)
            if index is None:
                continue
            close = float(series.bars[index].close)
            if close <= 0:
                continue
            first_close = first_close or close
            navs.append(float(initial_cash) * close / first_close)
            used_days += 1
        if not navs:
            references[symbol] = {"label": label, "available": False, "reason": "no_overlapping_trade_days"}
            continue
        references[symbol] = {
            "label": label,
            "available": True,
            "day_count": used_days,
            "total_return": round(navs[-1] / float(initial_cash) - 1.0, 6),
            "max_drawdown": _max_drawdown(navs),
        }
    return references


def _build_production_evidence(
    series_by_symbol: dict[str, Any],
    *,
    benchmark: Any,
    benchmark_mode: str,
    trade_days: list[date],
    selections: dict[str, dict[date, list[str]]],
    results: dict[str, dict[str, Any]],
    horizon_days: int,
    apply_limit_up_filter: bool,
    apply_limit_down_exit_filter: bool,
    initial_cash: float,
    daily_sleeve_cash: float,
) -> dict[str, Any]:
    leading = (results.get(LEADING_PAPER_MODE) or {}).get(LEADING_PAPER_STRATEGY)
    if leading is None:
        return {
            "status": "not_evaluated",
            "reason": "leading paper strategy is not present in this backtest payload",
        }
    summary = dict(leading.get("summary") or {})
    yearly = list(leading.get("yearly") or [])
    cost_stress = _cost_stress_results(
        series_by_symbol,
        benchmark=benchmark,
        benchmark_mode=benchmark_mode,
        trade_days=trade_days,
        selections=selections,
        horizon_days=horizon_days,
        apply_limit_up_filter=apply_limit_up_filter,
        apply_limit_down_exit_filter=apply_limit_down_exit_filter,
        initial_cash=initial_cash,
        daily_sleeve_cash=daily_sleeve_cash,
    )
    year_excess_values = [
        float(item["excess_return"])
        for item in yearly
        if item.get("excess_return") is not None
    ]
    positive_year_count = sum(1 for value in year_excess_values if value > 0)
    positive_year_rate = positive_year_count / len(year_excess_values) if year_excess_values else None
    worst_year_excess = min(year_excess_values) if year_excess_values else None
    checks = [
        _gate_check(
            "long_sample_trade_count",
            actual=summary.get("trade_count"),
            threshold=180,
            passed=float(summary.get("trade_count") or 0) >= 180,
            note="交易次数足够，避免只靠少数大赚样本。",
        ),
        _gate_check(
            "positive_excess_total_return",
            actual=summary.get("excess_total_return"),
            threshold=0.0,
            passed=float(summary.get("excess_total_return") or 0.0) > 0.0,
            note="扣默认成本后仍跑赢同期等权基准。",
        ),
        _gate_check(
            "max_drawdown_within_30pct",
            actual=summary.get("max_drawdown"),
            threshold=-0.30,
            passed=summary.get("max_drawdown") is not None and float(summary["max_drawdown"]) >= -0.30,
            note="最大回撤控制在短线纸面跟踪可接受区间内。",
        ),
        _gate_check(
            "positive_excess_year_rate",
            actual=positive_year_rate,
            threshold=0.75,
            passed=positive_year_rate is not None and positive_year_rate >= 0.75,
            note="至少四分之三年份跑赢基准，避免单一年份贡献过大。",
        ),
        _gate_check(
            "worst_year_excess_floor",
            actual=worst_year_excess,
            threshold=-0.10,
            passed=worst_year_excess is not None and worst_year_excess >= -0.10,
            note="最弱年份不能明显拖累；否则仍需风险降档。",
        ),
        _gate_check(
            "conservative_cost_100bps_positive",
            actual=(cost_stress.get("100") or {}).get("excess_total_return"),
            threshold=0.0,
            passed=float((cost_stress.get("100") or {}).get("excess_total_return") or 0.0) > 0.0,
            note="把总交易成本抬到 100 bps 后仍应为正超额。",
        ),
        _gate_check(
            "frozen_forward_tracking",
            actual=0,
            threshold=40,
            passed=False,
            note="从规则冻结日起至少需要 40 个后续真实交易日纸面跟踪，当前尚未开始。",
        ),
    ]
    failed = [check for check in checks if not check["passed"]]
    if not failed:
        status = "production_evidence_passed"
    elif len(failed) <= 2 and all(check["check_id"] in {"positive_excess_year_rate", "frozen_forward_tracking"} for check in failed):
        status = "near_production_needs_forward_tracking"
    else:
        status = "paper_tracking_candidate"
    return {
        "status": status,
        "leading_mode": LEADING_PAPER_MODE,
        "leading_strategy": LEADING_PAPER_STRATEGY,
        "leading_label": leading.get("label"),
        "checks": checks,
        "failed_check_ids": [check["check_id"] for check in failed],
        "cost_stress": cost_stress,
        "control_comparison": _control_comparison(results),
        "yearly_excess": yearly,
        "decision_note": (
            "The v2 rule is strong enough for paper tracking, but production proof requires frozen forward tracking and better weak-year robustness."
        ),
    }


def _control_comparison(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    daily = results.get(LEADING_PAPER_MODE) or {}
    controls = {}
    for strategy in (
        "ret10",
        "ret10_turnover",
        "ret10_turnover_cooldown",
        LEADING_PAPER_STRATEGY,
        STRONG_BREADTH_RANK2_STRATEGY,
        LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
        QUIET_BREAKOUT_RANK2_STRATEGY,
        TOP3_EQUAL_WEIGHT_STRATEGY,
        GOLDEN_CROSS_STRATEGY,
    ):
        summary = dict((daily.get(strategy) or {}).get("summary") or {})
        controls[strategy] = {
            "label": (daily.get(strategy) or {}).get("label") or strategy,
            "trade_count": summary.get("trade_count"),
            "total_return": summary.get("total_return"),
            "excess_total_return": summary.get("excess_total_return"),
            "max_drawdown": summary.get("max_drawdown"),
            "blocked_exit_count": summary.get("blocked_exit_count"),
        }
    return {
        "purpose": "Compare the leading rule against simple momentum controls before treating added gates as incremental edge.",
        "daily_rolling_controls": controls,
    }


def _cost_stress_results(
    series_by_symbol: dict[str, Any],
    *,
    benchmark: Any,
    benchmark_mode: str,
    trade_days: list[date],
    selections: dict[str, dict[date, list[str]]],
    horizon_days: int,
    apply_limit_up_filter: bool,
    apply_limit_down_exit_filter: bool,
    initial_cash: float,
    daily_sleeve_cash: float,
) -> dict[str, dict[str, Any]]:
    intents = _build_trade_intents(
        series_by_symbol,
        selections.get(LEADING_PAPER_STRATEGY, {}),
        strategy=LEADING_PAPER_STRATEGY,
        mode=LEADING_PAPER_MODE,
        horizon_days=horizon_days,
        apply_limit_up_filter=apply_limit_up_filter,
    )
    output: dict[str, dict[str, Any]] = {}
    for cost_bps in (20.0, 50.0, 100.0, 150.0):
        payload = _simulate_portfolio(
            series_by_symbol,
            benchmark=benchmark,
            benchmark_mode=benchmark_mode,
            trade_days=trade_days,
            intents=intents,
            mode=LEADING_PAPER_MODE,
            strategy=LEADING_PAPER_STRATEGY,
            initial_cash=initial_cash,
            daily_sleeve_cash=daily_sleeve_cash,
            cost_bps=cost_bps,
            stop_loss_pct=STOP_LOSS_BY_STRATEGY.get(LEADING_PAPER_STRATEGY),
            apply_limit_down_exit_filter=apply_limit_down_exit_filter,
        )
        summary = dict(payload.get("summary") or {})
        output[str(int(cost_bps))] = {
            "cost_bps": cost_bps,
            "trade_count": summary.get("trade_count"),
            "total_return": summary.get("total_return"),
            "excess_total_return": summary.get("excess_total_return"),
            "max_drawdown": summary.get("max_drawdown"),
        }
    return output


def _gate_check(
    check_id: str,
    *,
    actual: Any,
    threshold: Any,
    passed: bool,
    note: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "actual": actual,
        "threshold": threshold,
        "note": note,
    }


def _strategy_variant_contract() -> dict[str, dict[str, Any]]:
    return {
        "ret10_turnover_cooldown_market_positive": {
            "base_strategy": "ret10_turnover_cooldown",
            "gate": "全市场可交易样本 10 日平均收益 >= 0",
            "intent": "只在市场整体短线中枢不弱时启动默认动量策略。",
        },
        "ret10_turnover_cooldown_market_positive_cooldown": {
            "base_strategy": "ret10_turnover_cooldown",
            "gate": "全市场可交易样本 10 日平均收益 >= 0，且扩大动量池 1 日平均涨幅 <= 8%",
            "intent": "保留顺势环境，同时避开单日集体过热后的追高。",
        },
        "ret10_turnover_strong_breadth_pool": {
            "base_strategy": "ret10_turnover",
            "gate": "全市场 10 日上涨占比 >= 55%，且扩大动量池 10 日平均收益 >= 6%",
            "intent": "进攻型对照，只在强广度和强动量池共振时交易。",
        },
        "ret10_turnover_second_market_positive_cooldown": {
            "base_strategy": "ret10_turnover",
            "candidate_rank": 2,
            "gate": "全市场可交易样本 10 日平均收益 >= 0，且扩大动量池 1 日平均涨幅 <= 8%",
            "intent": "避开最拥挤的第一名，验证第二候选是否减少追高和拥挤交易。",
        },
        "ret10_turnover_second_market_positive_cooldown_stop8": {
            "base_strategy": "ret10_turnover",
            "candidate_rank": 2,
            "stop_loss_pct": 0.08,
            "gate": "全市场可交易样本 10 日平均收益 >= 0，且扩大动量池 1 日平均涨幅 <= 8%；持仓期间收盘亏损达到 8% 提前退出。",
            "intent": "去拥挤后增加轻量风险控制，降低深回撤月份对资金曲线的拖累。",
        },
        STRONG_BREADTH_RANK2_STRATEGY: {
            "base_strategy": "ret10_amount_turnover_cooldown",
            "candidate_rank": int(_STRONG_BREADTH_RANK2_CONFIG["source_rank"]),
            "stop_loss_pct": float(_STRONG_BREADTH_RANK2_CONFIG["stop_loss_pct"]),
            "gate": "全市场10日上涨占比 >= 55%，扩大动量池10日平均收益 >= 6%，且扩大动量池1日平均涨幅 <= 6%；持仓期间收盘亏损达到12%提前退出。",
            "intent": "把历史上更强的广度和动量共振窗口单独进入真实纸面跟踪，验证较严入场条件能否降低无效交易。",
        },
        LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY: {
            "base_strategy": LOW_TURNOVER_UPTREND_STRATEGY,
            "candidate_rank": int(_LOW_TURNOVER_UPTREND_CONFIG["source_rank"]),
            "gate": "全市场10日上涨占比 >= 45%，在成交额/换手靠前的120只流动性池中，选择20日趋势向上但换手率相对更低的第1名。",
            "intent": "验证非拥挤趋势是否比短线追涨更适合当前主板样本；该规则是本轮搜索中历史超额最高的候选。",
        },
        QUIET_BREAKOUT_RANK2_STRATEGY: {
            "base_strategy": QUIET_BREAKOUT_BASE_STRATEGY,
            "candidate_rank": int(_QUIET_BREAKOUT_RANK2_CONFIG["source_rank"]),
            "stop_loss_pct": float(_QUIET_BREAKOUT_RANK2_CONFIG["stop_loss_pct"]),
            "gate": "在当日波动较小且成交额靠前的80只池中，要求10日收益非负、当日涨幅 <= 4%，按20日趋势、5日趋势、当日安静程度和成交额排序取第2名。",
            "intent": "作为次级对照，验证安静突破是否能降低追涨噪声并保留足够信号密度。",
        },
        TOP3_EQUAL_WEIGHT_STRATEGY: {
            "base_strategy": "ret10_turnover",
            "candidate_rank": "top3_equal_weight",
            "stop_loss_pct": 0.08,
            "gate": "全市场可交易样本 10 日平均收益 >= 0，且扩大动量池 1 日平均涨幅 <= 8%；每日1万元资金在前三名中等权分配。",
            "intent": "降低单票偶然性和第一名拥挤交易风险，验证同一市场状态下的多票分散是否改善资金曲线。",
        },
        GOLDEN_CROSS_STRATEGY: {
            "base_strategy": "base",
            "technical_filter": "10日均线当日上穿200日均线",
            "gate": "按原动量成交量候选顺序寻找第一个触发10/200日金叉的标的；没有触发则当日不交易。",
            "intent": "用长期趋势确认过滤短线动量候选，检验减少伪突破是否值得牺牲信号数量。",
        },
    }


def _sample_concentration_note(signal_days: list[date]) -> str:
    years = sorted({day.year for day in signal_days})
    months = sorted({f"{day.year:04d}-{day.month:02d}" for day in signal_days})
    return f"样本覆盖 {len(years)} 个年份、{len(months)} 个月；用于降低 2026-03/04 单一行情窗口带来的误判。"


def _strategy_label(strategy: str) -> str:
    labels = {
        "base": "动量成交额原始池首位",
        "turnover": "换手确认首位",
        "ret10": "10日动量首位",
        "ret10_turnover": "10日动量换手首位",
        "ret10_turnover_cooldown": "10日动量换手降追高首位",
        "ret10_turnover_cooldown_market_positive": "市场转正后启用降追高",
        "ret10_turnover_cooldown_market_positive_cooldown": "市场转正且不过热时启用降追高",
        "ret10_turnover_strong_breadth_pool": "强广度动量共振",
        "ret10_turnover_second_market_positive_cooldown": "市场转正不过热时取第二候选",
        "ret10_turnover_second_market_positive_cooldown_stop8": "第二候选加8%收盘止损",
        STRONG_BREADTH_RANK2_STRATEGY: "强广度低追高二候选",
        LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY: "低换手上升趋势",
        QUIET_BREAKOUT_RANK2_STRATEGY: "安静突破二候选",
        TOP3_EQUAL_WEIGHT_STRATEGY: "市场转正不过热时前三名等权",
        GOLDEN_CROSS_STRATEGY: "动量池10/200日金叉首位",
        "ret10_turnover_cooldown_diversified": "10日动量换手降追高分散首位",
        "combo": "短动量换手复合首位",
    }
    return labels.get(strategy, strategy)
