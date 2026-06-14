from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import floor
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    INDEX_SYMBOLS,
    LOW_TURNOVER_UPTREND_STRATEGY,
    _build_strategy_selections,
    _entry_is_unfillable_for_source,
    _entry_price,
    _load_daily_series,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
    _apply_strategy_regime_filter,
    _eligible_signal_days,
    _exit_is_unfillable_limit_down,
    _max_drawdown,
    _regime_features_by_day,
    _trade_days,
)

SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY = "shortpick_v2_replay_artifact"
SHORTPICK_V2_REPLAY_SCHEMA_VERSION = "v1"
SHORTPICK_V2_REPLAY_SOURCE_PLAN_REF = (
    "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-3-replay-artifact-generation"
)
SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF = (
    "market_only_reconstruction:low_turnover_20d_uptrend_liquid_top120:v1"
)
DEFAULT_INITIAL_CASH = 200_000.0
DEFAULT_BOARD_LOT_SIZE = 100
DEFAULT_MAX_POSITION_COUNT = 5
DEFAULT_MAX_POSITION_PCT = 0.35
DEFAULT_COST_BPS = 20.0
DEFAULT_STAMP_TAX_BPS = 5.0
DEFAULT_DECISION_SAMPLE_LIMIT = 40
VALID_ACTIONS = {"buy_primary", "buy_fallback", "skip"}
DYNAMIC_EXIT_REASONS = {"stop_loss", "take_profit", "trailing_stop"}


@dataclass(frozen=True)
class ShortpickV2RuleConfig:
    config_id: str
    family: str
    candidate_rank_limit: int
    fallback_enabled: bool
    target_mode: str
    allowed_actions: tuple[str, ...]
    target_notional: float | None = None
    cash_reserve: float = 0.0
    max_position_count: int = DEFAULT_MAX_POSITION_COUNT
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT
    board_lot_size: int = DEFAULT_BOARD_LOT_SIZE
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    trailing_activation_pct: float | None = None

    @property
    def fallback_max_rank(self) -> int:
        return self.candidate_rank_limit if self.fallback_enabled else 1

    def to_artifact(self) -> dict[str, Any]:
        cash_policy: dict[str, Any] = {"target_mode": self.target_mode}
        if self.target_notional is not None:
            cash_policy["target_notional"] = self.target_notional
        if self.cash_reserve > 0:
            cash_policy["cash_reserve"] = self.cash_reserve
        return {
            "config_id": self.config_id,
            "family": self.family,
            "status": "candidate",
            "allowed_actions": list(self.allowed_actions),
            "candidate_rank_limit": self.candidate_rank_limit,
            "fallback_policy": {
                "enabled": self.fallback_enabled,
                "max_rank": self.fallback_max_rank,
            },
            "lot_policy": {
                "board_lot_size": self.board_lot_size,
                "rounding": "floor_to_board_lot",
            },
            "cash_policy": cash_policy,
            "position_policy": {
                "max_position_count": self.max_position_count,
                "max_position_pct": self.max_position_pct,
                "same_symbol_exposure_cap": True,
            },
            "exit_policy": {
                "mechanical_horizon_exit": True,
                "dynamic_exit_triggers": self.dynamic_exit_triggers,
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
                "trailing_stop_pct": self.trailing_stop_pct,
                "trailing_activation_pct": self.trailing_activation_pct,
                "price_basis": "daily_close",
            },
        }

    @property
    def dynamic_exit_triggers(self) -> list[str]:
        triggers: list[str] = []
        if self.stop_loss_pct is not None:
            triggers.append("stop_loss")
        if self.take_profit_pct is not None:
            triggers.append("take_profit")
        if self.trailing_stop_pct is not None:
            triggers.append("trailing_stop")
        return triggers


@dataclass(frozen=True)
class _Candidate:
    rank: int
    symbol: str
    entry_day: date
    exit_day: date
    entry_price: float
    entry_index: int


@dataclass(frozen=True)
class _SignalCandidates:
    signal_day: date
    candidates: tuple[_Candidate, ...]


@dataclass
class _OpenPosition:
    signal_day: date
    entry_day: date
    planned_exit_day: date
    symbol: str
    rank: int
    shares: int
    entry_price: float
    cost_basis: float
    peak_close: float


@dataclass(frozen=True)
class _BuyEvaluation:
    action: str
    reason: str
    selected_rank: int | None
    symbol: str | None
    shares: int
    cash_spent: float
    position: _OpenPosition | None
    rejected_reasons: tuple[str, ...]


DEFAULT_SHORTPICK_V2_RULE_CONFIGS: tuple[ShortpickV2RuleConfig, ...] = (
    ShortpickV2RuleConfig(
        config_id="top1_or_skip_v1",
        family="top1_or_skip",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="top3_fallback_v1",
        family="topn_fallback",
        candidate_rank_limit=3,
        fallback_enabled=True,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="position_cap_utilization_top5_v1",
        family="position_cap_utilization",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="conservative_cash_reserve_60k_top5_v1",
        family="conservative_cash_reserve",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="reserve_constrained",
        cash_reserve=60_000.0,
        max_position_pct=0.30,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)


def build_shortpick_v2_replay_artifact(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 5,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = 45,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    rule_configs: tuple[ShortpickV2RuleConfig, ...] = DEFAULT_SHORTPICK_V2_RULE_CONFIGS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the fixed Short Pick Lab v2 historical account replay artifact from existing daily bars."""
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    raw_series_by_symbol = _load_daily_series(session)
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=start_date,
        end_date=end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    trade_day_end = end_date + timedelta(days=max(30, horizon_days * 4))
    trade_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=trade_day_end,
        min_symbol_count=min_signal_symbol_count,
    )
    effective_rank_limit = max([rank_limit, *[config.candidate_rank_limit for config in rule_configs]])
    selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=selections,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        account_profile=str(account_eligibility["account_profile"]),
        stock_like_series_count=len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        coverage_notes=_coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        rule_configs=rule_configs,
        generated_at=generated_at,
    )


def build_shortpick_v2_replay_artifact_from_series(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    selections: dict[date, list[str]],
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 5,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    stock_like_series_count: int | None = None,
    coverage_notes: list[str] | None = None,
    rule_configs: tuple[ShortpickV2RuleConfig, ...] = DEFAULT_SHORTPICK_V2_RULE_CONFIGS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    _validate_rule_configs(rule_configs)

    signal_days = sorted(signal_days)
    trade_days = sorted(trade_days)
    generated_at = generated_at or datetime.now(UTC)
    stock_like_series_count = (
        stock_like_series_count
        if stock_like_series_count is not None
        else len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    )
    market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
    results = [
        _simulate_rule_config(
            series_by_symbol,
            signal_days=signal_days,
            trade_days=trade_days,
            selections=selections,
            config=config,
            initial_cash=initial_cash,
            entry_price_source=entry_price_source,
            horizon_days=horizon_days,
            cost_bps=cost_bps,
            stamp_tax_bps=stamp_tax_bps,
            market_reference_total_return=market_reference["total_return"],
        )
        for config in rule_configs
    ]
    status = "ready" if signal_days and results else "blocked"
    return {
        "artifact_family": SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_REPLAY_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, start_date, end_date, initial_cash),
        "generated_at": generated_at.isoformat(),
        "status": status,
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay",
        "source_plan_ref": SHORTPICK_V2_REPLAY_SOURCE_PLAN_REF,
        "data_scope": {
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "stock_like_series_count": stock_like_series_count,
            "account_profile": account_profile,
            "coverage_status": _coverage_status(signal_days, trade_days, stock_like_series_count),
            "coverage_notes": coverage_notes
            or ["Synthetic or caller-supplied fixed daily bars; no refresh performed."],
            "market_reference_mode": market_reference["mode"],
            "market_reference_date_from": market_reference["date_from"],
            "market_reference_date_to": market_reference["date_to"],
            "market_reference_sample_count": market_reference["sample_count"],
            "market_reference_total_return": market_reference["total_return"],
        },
        "input_contracts": {
            "candidate_source": {
                "source_family": "shortpick_v2_candidate_projection",
                "source_ref": SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
                "ranked_pool_required": True,
                "source_feature_cutoff_policy": (
                    "Candidate ranking uses signal-day-or-earlier daily-bar features; entry and exit bars are "
                    "used only by the execution replay."
                ),
                "allowed_evidence_basis": ["historical_backtest", "market_only_reconstruction"],
            },
            "market_data": {
                "source_ref": "existing_sqlite_daily_market_bars",
                "status": "ready" if trade_days else "partial",
                "read_policy": "read_only_existing_rows_no_refresh",
            },
            "account": {
                "initial_cash": initial_cash,
                "currency": "CNY",
                "board_lot_size": DEFAULT_BOARD_LOT_SIZE,
                "account_profile": account_profile,
                "max_position_count": max(config.max_position_count for config in rule_configs),
                "max_position_pct": max(config.max_position_pct for config in rule_configs),
            },
            "cost_model": {
                "cost_bps": cost_bps,
                "stamp_tax_bps": stamp_tax_bps,
                "description": (
                    "Cost bps are applied on both buy and sell notional; stamp tax bps apply on sell notional."
                ),
            },
            "entry_model": {
                "entry_price_source": entry_price_source,
                "entry_trade_day_policy": (
                    "For each signal, buy on the declared entry bar from the fixed entry source; if not executable, "
                    "use a predeclared fallback candidate or skip. No delayed entry action exists."
                ),
            },
            "exit_model": {
                "holding_days": horizon_days,
                "exit_tracks": _exit_tracks(rule_configs),
                "unfillable_exit_policy": (
                    "If a mechanical or dynamic close-based exit is a one-price limit-down bar, keep the "
                    "position open and retry exit evaluation on later trade days."
                ),
            },
        },
        "rule_matrix": [config.to_artifact() for config in rule_configs],
        "results": results,
        "promotion_gate": {
            "status": "not_evaluated",
            "claim_ceiling": "research_observation",
            "criteria": [
                "Historical replay artifact exists and validates against the v1 schema.",
                "A later phase must select a bounded governed subset before paper tracking.",
                "Forward v2 paper tracking is required before any paper_tracking_candidate claim.",
            ],
            "blocking_reasons": ["phase4_candidate_rule_selection_not_run"],
        },
        "leakage_audit": {
            "status": "passed",
            "source_feature_cutoff_policy": (
                "Buy, fallback, and skip decisions use only fixed ranked pools and account state available at the "
                "signal's declared entry point; future bars are used only for mechanical marking and exits."
            ),
            "used_only_signal_day_or_earlier_data": True,
            "notes": [
                "Candidate pools are reconstructed from signal-day-or-earlier market features.",
                "No delayed-entry, discretionary reselection, model call, refresh, or database write is performed.",
            ],
        },
        "event_refs": [
            "shortpick_v2.phase3.replay_artifact.generated",
            f"shortpick_v2.replay_window.{start_date.isoformat()}_{end_date.isoformat()}",
        ],
    }


def write_shortpick_v2_replay_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    import json

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _build_low_turnover_uptrend_candidate_pool(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> dict[date, list[str]]:
    selections = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=LOW_TURNOVER_UPTREND_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    return _apply_strategy_regime_filter(LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY, selections, regime_features)


def _simulate_rule_config(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    selections: dict[date, list[str]],
    config: ShortpickV2RuleConfig,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    cost_bps: float,
    stamp_tax_bps: float,
    market_reference_total_return: float | None,
) -> dict[str, Any]:
    entries_by_day, pre_entry_decisions, pre_entry_counts = _prepare_signal_entries(
        series_by_symbol,
            signal_days=signal_days,
            trade_days=trade_days,
            selections=selections,
            config=config,
            initial_cash=initial_cash,
            entry_price_source=entry_price_source,
        horizon_days=horizon_days,
    )
    active_days = sorted(set(trade_days) | set(entries_by_day))
    cash = float(initial_cash)
    buy_cost_rate = float(cost_bps) / 10000.0
    sell_cost_rate = float(cost_bps + stamp_tax_bps) / 10000.0
    open_positions: list[_OpenPosition] = []
    decisions = list(pre_entry_decisions)
    reason_counts = Counter(pre_entry_counts)
    timeline: list[dict[str, Any]] = []
    total_buy_value = 0.0
    total_sell_value = 0.0
    blocked_exit_count = 0
    exit_reason_counts: Counter[str] = Counter()

    for current_day in active_days:
        still_open: list[_OpenPosition] = []
        for position in open_positions:
            series = series_by_symbol.get(position.symbol)
            current_index = series.by_day.get(current_day) if series is not None else None
            if series is None or current_index is None:
                still_open.append(position)
                continue
            close = float(series.bars[current_index].close)
            position.peak_close = max(position.peak_close, close)
            exit_reason = (
                "mechanical_horizon"
                if current_day >= position.planned_exit_day
                else _dynamic_exit_reason(position, close=close, current_day=current_day, config=config)
            )
            if exit_reason is None:
                still_open.append(position)
                continue
            if _exit_is_unfillable_limit_down(series, current_index):
                blocked_exit_count += 1
                reason_counts["blocked_exit:limit_down"] += 1
                still_open.append(position)
                continue
            proceeds = position.shares * close * (1.0 - sell_cost_rate)
            cash += proceeds
            total_sell_value += proceeds
            reason_counts[f"exit:{exit_reason}"] += 1
            exit_reason_counts[exit_reason] += 1
        open_positions = still_open

        for signal_entry in sorted(entries_by_day.get(current_day, []), key=lambda item: item.signal_day):
            cash_before = cash
            evaluation = _evaluate_signal_entry(
                signal_entry,
                config=config,
                cash=cash,
                open_positions=open_positions,
                series_by_symbol=series_by_symbol,
                current_day=current_day,
                initial_cash=initial_cash,
                buy_cost_rate=buy_cost_rate,
                entry_price_source=entry_price_source,
            )
            reason_counts[f"action:{evaluation.action}"] += 1
            reason_counts[f"reason:{evaluation.reason}"] += 1
            for rejected_reason in evaluation.rejected_reasons:
                reason_counts[f"candidate_reject:{rejected_reason}"] += 1
            if evaluation.position is not None:
                cash -= evaluation.cash_spent
                total_buy_value += evaluation.cash_spent
                open_positions.append(evaluation.position)
            decisions.append(
                {
                    "signal_date": signal_entry.signal_day.isoformat(),
                    "action": evaluation.action,
                    "reason": evaluation.reason,
                    "selected_rank": evaluation.selected_rank,
                    "symbol": evaluation.symbol,
                    "cash_before": round(cash_before, 6),
                    "cash_after": round(cash, 6),
                    "quantity": evaluation.shares,
                }
            )

        nav, market_value = _nav_and_market_value(series_by_symbol, open_positions, current_day, cash)
        timeline.append(
            {
                "date": current_day.isoformat(),
                "nav": nav,
                "cash": cash,
                "market_value": market_value,
                "open_position_count": len(open_positions),
            }
        )

    final_day = active_days[-1] if active_days else None
    if final_day is None:
        final_nav = float(initial_cash)
        final_market_value = 0.0
    else:
        final_nav, final_market_value = _nav_and_market_value(series_by_symbol, open_positions, final_day, cash)
    buy_decisions = [decision for decision in decisions if decision["action"] in {"buy_primary", "buy_fallback"}]
    skip_count = sum(1 for decision in decisions if decision["action"] == "skip")
    fallback_trade_count = sum(1 for decision in decisions if decision["action"] == "buy_fallback")
    invested_ratios = [
        float(point["market_value"]) / float(point["nav"])
        for point in timeline
        if float(point["nav"]) > 0
    ]
    result_status = "ready" if signal_days else "blocked"
    total_return = round(final_nav / float(initial_cash) - 1.0, 6) if initial_cash else 0.0
    market_excess_total_return = (
        None
        if market_reference_total_return is None
        else round(total_return - market_reference_total_return, 6)
    )
    return {
        "config_id": config.config_id,
        "status": result_status,
        "summary": {
            "signal_count": len(signal_days),
            "trade_count": len(buy_decisions),
            "skip_count": skip_count,
            "fallback_trade_count": fallback_trade_count,
            "final_nav": round(final_nav, 6),
            "total_return": total_return,
            "annualization_trade_day_count": len(trade_days),
            "market_reference_total_return": market_reference_total_return,
            "market_excess_total_return": market_excess_total_return,
            "max_drawdown": _max_drawdown([float(point["nav"]) for point in timeline]) or 0.0,
            "mean_invested_ratio": round(sum(invested_ratios) / len(invested_ratios), 6) if invested_ratios else 0.0,
            "max_position_count": max((int(point["open_position_count"]) for point in timeline), default=0),
            "turnover": round(total_buy_value / float(initial_cash), 6) if initial_cash else 0.0,
            "final_cash": round(cash, 6),
            "final_market_value": round(final_market_value, 6),
            "open_position_count": len(open_positions),
            "blocked_exit_count": blocked_exit_count,
            "dynamic_exit_count": sum(
                count for reason, count in exit_reason_counts.items() if reason in DYNAMIC_EXIT_REASONS
            ),
            "exit_reason_counts": dict(sorted(exit_reason_counts.items())),
            "total_buy_value": round(total_buy_value, 6),
            "total_sell_value": round(total_sell_value, 6),
            "skipped_ratio": round(skip_count / len(signal_days), 6) if signal_days else 0.0,
        },
        "reason_counts": dict(sorted(reason_counts.items())),
        "decision_samples": sorted(decisions, key=lambda item: item["signal_date"])[:DEFAULT_DECISION_SAMPLE_LIMIT],
        "detail_refs": {
            "nav_timeline": "phase3-envelope-summary-only:nav_timeline_not_emitted",
            "trades": "phase3-envelope-summary-only:trade_table_not_emitted",
            "decisions": "phase3-envelope-summary-only:decision_samples_bounded",
        },
    }


def _prepare_signal_entries(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    selections: dict[date, list[str]],
    config: ShortpickV2RuleConfig,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
) -> tuple[dict[date, list[_SignalCandidates]], list[dict[str, Any]], Counter[str]]:
    entries_by_day: dict[date, list[_SignalCandidates]] = defaultdict(list)
    pre_entry_decisions: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    for signal_day in signal_days:
        candidates = _build_signal_candidates(
            series_by_symbol,
            signal_day=signal_day,
            trade_days=trade_days,
            symbols=(selections.get(signal_day) or [])[: config.candidate_rank_limit],
            entry_price_source=entry_price_source,
            horizon_days=horizon_days,
        )
        if candidates:
            entries_by_day[candidates[0].entry_day].append(
                _SignalCandidates(signal_day=signal_day, candidates=tuple(candidates))
            )
            continue
        reason = "no_ranked_candidates"
        reason_counts["action:skip"] += 1
        reason_counts[f"reason:{reason}"] += 1
        pre_entry_decisions.append(
            {
                "signal_date": signal_day.isoformat(),
                "action": "skip",
                "reason": reason,
                "selected_rank": None,
                "symbol": None,
                "cash_before": round(initial_cash, 6),
                "cash_after": round(initial_cash, 6),
                "quantity": 0,
            }
        )
    return entries_by_day, pre_entry_decisions, reason_counts


def _build_signal_candidates(
    series_by_symbol: dict[str, Any],
    *,
    signal_day: date,
    trade_days: list[date],
    symbols: list[str],
    entry_price_source: str,
    horizon_days: int,
) -> list[_Candidate]:
    entry_day, exit_day = _declared_entry_exit_days(
        signal_day,
        trade_days=trade_days,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
    )
    if entry_day is None or exit_day is None:
        return []
    candidates: list[_Candidate] = []
    for rank, symbol in enumerate(symbols, start=1):
        series = series_by_symbol.get(symbol)
        if series is None:
            continue
        signal_index = series.by_day.get(signal_day)
        entry_index = series.by_day.get(entry_day)
        if signal_index is None or entry_index is None or exit_day not in series.by_day:
            continue
        entry_price = _entry_price(series.bars[entry_index], entry_price_source)
        if not entry_price:
            continue
        candidates.append(
            _Candidate(
                rank=rank,
                symbol=symbol,
                entry_day=entry_day,
                exit_day=exit_day,
                entry_price=float(entry_price),
                entry_index=entry_index,
            )
        )
    return candidates


def _declared_entry_exit_days(
    signal_day: date,
    *,
    trade_days: list[date],
    entry_price_source: str,
    horizon_days: int,
) -> tuple[date | None, date | None]:
    if entry_price_source == "same_close_proxy":
        try:
            entry_trade_index = trade_days.index(signal_day)
        except ValueError:
            return None, None
    else:
        entry_trade_index = next((index for index, day in enumerate(trade_days) if day > signal_day), None)
        if entry_trade_index is None:
            return None, None
    exit_trade_index = entry_trade_index + horizon_days
    if exit_trade_index >= len(trade_days):
        return None, None
    return trade_days[entry_trade_index], trade_days[exit_trade_index]


def _evaluate_signal_entry(
    signal_entry: _SignalCandidates,
    *,
    config: ShortpickV2RuleConfig,
    cash: float,
    open_positions: list[_OpenPosition],
    series_by_symbol: dict[str, Any],
    current_day: date,
    initial_cash: float,
    buy_cost_rate: float,
    entry_price_source: str,
) -> _BuyEvaluation:
    rejected_reasons: list[str] = []
    candidates = signal_entry.candidates if config.fallback_enabled else signal_entry.candidates[:1]
    for candidate in candidates:
        reason = _candidate_reject_reason(
            candidate,
            config=config,
            cash=cash,
            open_positions=open_positions,
            series_by_symbol=series_by_symbol,
            current_day=current_day,
            initial_cash=initial_cash,
            buy_cost_rate=buy_cost_rate,
            entry_price_source=entry_price_source,
        )
        if reason is not None:
            rejected_reasons.append(reason)
            continue
        shares, cash_spent = _shares_and_cash_spent(
            candidate,
            config=config,
            cash=cash,
            open_positions=open_positions,
            series_by_symbol=series_by_symbol,
            current_day=current_day,
            initial_cash=initial_cash,
            buy_cost_rate=buy_cost_rate,
        )
        if shares <= 0:
            rejected_reasons.append("board_lot_minimum")
            continue
        action = "buy_primary" if candidate.rank == 1 else "buy_fallback"
        return _BuyEvaluation(
            action=action,
            reason="bought_primary" if action == "buy_primary" else "bought_fallback",
            selected_rank=candidate.rank,
            symbol=candidate.symbol,
            shares=shares,
            cash_spent=cash_spent,
            position=_OpenPosition(
                signal_day=signal_entry.signal_day,
                entry_day=candidate.entry_day,
                planned_exit_day=candidate.exit_day,
                symbol=candidate.symbol,
                rank=candidate.rank,
                shares=shares,
                entry_price=candidate.entry_price,
                cost_basis=cash_spent,
                peak_close=candidate.entry_price,
            ),
            rejected_reasons=tuple(rejected_reasons),
        )
    reason = rejected_reasons[0] if rejected_reasons else "no_executable_candidate"
    return _BuyEvaluation(
        action="skip",
        reason=reason,
        selected_rank=None,
        symbol=None,
        shares=0,
        cash_spent=0.0,
        position=None,
        rejected_reasons=tuple(rejected_reasons),
    )


def _candidate_reject_reason(
    candidate: _Candidate,
    *,
    config: ShortpickV2RuleConfig,
    cash: float,
    open_positions: list[_OpenPosition],
    series_by_symbol: dict[str, Any],
    current_day: date,
    initial_cash: float,
    buy_cost_rate: float,
    entry_price_source: str,
) -> str | None:
    if len(open_positions) >= config.max_position_count:
        return "position_count_cap"
    series = series_by_symbol.get(candidate.symbol)
    if series is None:
        return "missing_series"
    if _entry_is_unfillable_for_source(series, candidate.entry_index, entry_price_source):
        return "limit_up_unfillable"
    nav, _ = _nav_and_market_value(series_by_symbol, open_positions, current_day, cash)
    nav = nav if nav > 0 else float(initial_cash)
    existing_symbol_value = _symbol_market_value(series_by_symbol, open_positions, candidate.symbol, current_day)
    position_cap_remaining = max(nav * config.max_position_pct - existing_symbol_value, 0.0)
    if position_cap_remaining <= 0:
        return "position_value_cap"
    available_cash = max(cash - config.cash_reserve, 0.0)
    if available_cash <= 0:
        return "cash_reserve"
    target_notional = _target_notional(config, position_cap_remaining)
    investable_cash = min(available_cash, target_notional)
    per_lot_cost = candidate.entry_price * config.board_lot_size * (1.0 + buy_cost_rate)
    if investable_cash < per_lot_cost:
        return "insufficient_cash" if available_cash < per_lot_cost else "board_lot_minimum"
    shares, cash_spent = _shares_from_cash(candidate.entry_price, investable_cash, config.board_lot_size, buy_cost_rate)
    if shares < config.board_lot_size:
        return "board_lot_minimum"
    if cash_spent > cash:
        return "insufficient_cash"
    return None


def _shares_and_cash_spent(
    candidate: _Candidate,
    *,
    config: ShortpickV2RuleConfig,
    cash: float,
    open_positions: list[_OpenPosition],
    series_by_symbol: dict[str, Any],
    current_day: date,
    initial_cash: float,
    buy_cost_rate: float,
) -> tuple[int, float]:
    nav, _ = _nav_and_market_value(series_by_symbol, open_positions, current_day, cash)
    nav = nav if nav > 0 else float(initial_cash)
    existing_symbol_value = _symbol_market_value(series_by_symbol, open_positions, candidate.symbol, current_day)
    position_cap_remaining = max(nav * config.max_position_pct - existing_symbol_value, 0.0)
    available_cash = max(cash - config.cash_reserve, 0.0)
    investable_cash = min(available_cash, _target_notional(config, position_cap_remaining))
    return _shares_from_cash(candidate.entry_price, investable_cash, config.board_lot_size, buy_cost_rate)


def _target_notional(config: ShortpickV2RuleConfig, position_cap_remaining: float) -> float:
    if config.target_mode == "fixed_notional" and config.target_notional is not None:
        return min(config.target_notional, position_cap_remaining)
    return position_cap_remaining


def _shares_from_cash(
    entry_price: float,
    investable_cash: float,
    board_lot_size: int,
    buy_cost_rate: float,
) -> tuple[int, float]:
    if entry_price <= 0 or investable_cash <= 0:
        return 0, 0.0
    raw_shares = floor(investable_cash / (entry_price * (1.0 + buy_cost_rate)))
    shares = raw_shares - raw_shares % board_lot_size
    cash_spent = shares * entry_price * (1.0 + buy_cost_rate)
    return shares, cash_spent


def _dynamic_exit_reason(
    position: _OpenPosition,
    *,
    close: float,
    current_day: date,
    config: ShortpickV2RuleConfig,
) -> str | None:
    if current_day <= position.entry_day or position.entry_price <= 0 or close <= 0:
        return None
    return_since_entry = close / position.entry_price - 1.0
    if config.stop_loss_pct is not None and return_since_entry <= -float(config.stop_loss_pct):
        return "stop_loss"
    if config.take_profit_pct is not None and return_since_entry >= float(config.take_profit_pct):
        return "take_profit"
    if (
        config.trailing_stop_pct is not None
        and config.trailing_activation_pct is not None
        and position.peak_close > 0
        and position.peak_close / position.entry_price - 1.0 >= float(config.trailing_activation_pct)
        and close / position.peak_close - 1.0 <= -float(config.trailing_stop_pct)
    ):
        return "trailing_stop"
    return None


def _nav_and_market_value(
    series_by_symbol: dict[str, Any],
    open_positions: list[_OpenPosition],
    current_day: date,
    cash: float,
) -> tuple[float, float]:
    market_value = sum(_mark_position_value(series_by_symbol, position, current_day) for position in open_positions)
    return cash + market_value, market_value


def _symbol_market_value(
    series_by_symbol: dict[str, Any],
    open_positions: list[_OpenPosition],
    symbol: str,
    current_day: date,
) -> float:
    return sum(
        _mark_position_value(series_by_symbol, position, current_day)
        for position in open_positions
        if position.symbol == symbol
    )


def _mark_position_value(series_by_symbol: dict[str, Any], position: _OpenPosition, current_day: date) -> float:
    series = series_by_symbol.get(position.symbol)
    index = series.by_day.get(current_day) if series is not None else None
    if series is None or index is None:
        return position.shares * position.entry_price
    return position.shares * float(series.bars[index].close)


def _validate_rule_configs(rule_configs: tuple[ShortpickV2RuleConfig, ...]) -> None:
    if not rule_configs:
        raise ValueError("at least one Shortpick V2 rule config is required")
    for config in rule_configs:
        unknown_actions = set(config.allowed_actions) - VALID_ACTIONS
        if unknown_actions:
            raise ValueError(f"{config.config_id} contains invalid actions: {sorted(unknown_actions)}")
        if config.fallback_enabled and "buy_fallback" not in config.allowed_actions:
            raise ValueError(f"{config.config_id} enables fallback but does not allow buy_fallback")
        if not config.fallback_enabled and config.candidate_rank_limit != 1:
            raise ValueError(f"{config.config_id} disables fallback but has rank limit {config.candidate_rank_limit}")
        if config.board_lot_size < DEFAULT_BOARD_LOT_SIZE:
            raise ValueError(f"{config.config_id} board_lot_size must be at least {DEFAULT_BOARD_LOT_SIZE}")
        _validate_rule_config_exit_policy(config)


def _validate_rule_config_exit_policy(config: ShortpickV2RuleConfig) -> None:
    for field_name in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "trailing_activation_pct"):
        value = getattr(config, field_name)
        if value is not None and not 0.0 < float(value) < 1.0:
            raise ValueError(f"{config.config_id} {field_name} must be between 0 and 1")
    if (config.trailing_stop_pct is None) != (config.trailing_activation_pct is None):
        raise ValueError(f"{config.config_id} trailing exit requires both stop and activation pct")


def _exit_tracks(rule_configs: tuple[ShortpickV2RuleConfig, ...]) -> list[str]:
    tracks = ["mechanical_horizon_exit", "limit_down_blocked_exit"]
    trigger_to_track = {
        "stop_loss": "close_stop_loss_exit",
        "take_profit": "close_take_profit_exit",
        "trailing_stop": "close_trailing_stop_exit",
    }
    for trigger in sorted({trigger for config in rule_configs for trigger in config.dynamic_exit_triggers}):
        tracks.append(trigger_to_track[trigger])
    return tracks


def _market_reference_summary(series_by_symbol: dict[str, Any], *, signal_days: list[date]) -> dict[str, Any]:
    mode = "eligible_universe_equal_weight_close_to_close"
    if not signal_days:
        return {
            "mode": mode,
            "date_from": None,
            "date_to": None,
            "sample_count": 0,
            "total_return": None,
        }
    start_day = signal_days[0]
    end_day = signal_days[-1]
    returns: list[float] = []
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        start_close = _close_on_day(series, start_day)
        end_close = _close_on_day(series, end_day)
        if start_close is None or end_close is None or start_close <= 0:
            continue
        returns.append(end_close / start_close - 1.0)
    return {
        "mode": mode,
        "date_from": start_day.isoformat(),
        "date_to": end_day.isoformat(),
        "sample_count": len(returns),
        "total_return": round(sum(returns) / len(returns), 6) if returns else None,
    }


def _close_on_day(series: Any, day: date) -> float | None:
    index = series.by_day.get(day) if series is not None else None
    if index is None:
        return None
    close = getattr(series.bars[index], "close", None)
    return float(close) if close is not None else None


def _coverage_status(signal_days: list[date], trade_days: list[date], stock_like_series_count: int) -> str:
    if not signal_days or not trade_days or stock_like_series_count <= 0:
        return "blocked"
    return "complete"


def _coverage_notes(
    raw_series_by_symbol: dict[str, Any],
    series_by_symbol: dict[str, Any],
    account_eligibility: dict[str, Any],
) -> list[str]:
    raw_count = len([symbol for symbol in raw_series_by_symbol if symbol not in INDEX_SYMBOLS])
    filtered_count = len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    notes = [
        "Read-only daily bars from the existing SQLite database; no refresh or model call performed.",
        f"Account eligibility filtered stock-like series from {raw_count} to {filtered_count}.",
    ]
    excluded = account_eligibility.get("excluded_board_counts")
    if excluded:
        notes.append(f"Account eligibility excluded board counts: {excluded}.")
    return notes


def _artifact_id(generated_at: datetime, start_date: date, end_date: date, initial_cash: float) -> str:
    generated_day = generated_at.date().isoformat()
    cash_text = str(int(initial_cash)) if float(initial_cash).is_integer() else str(initial_cash)
    return f"shortpick_v2_replay_artifact:{start_date.isoformat()}:{end_date.isoformat()}:{cash_text}:{generated_day}"
