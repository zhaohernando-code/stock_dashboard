from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import sqrt
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    GOLDEN_CROSS_STRATEGY,
    INDEX_SYMBOLS,
    LOW_TURNOVER_UPTREND_STRATEGY,
    QUIET_BREAKOUT_BASE_STRATEGY,
    _build_strategy_selections,
    _load_daily_series,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    QUIET_BREAKOUT_RANK2_STRATEGY,
    STRONG_BREADTH_RANK2_STRATEGY,
    _apply_strategy_regime_filter,
    _apply_strategy_selection_transform,
    _eligible_signal_days,
    _regime_features_by_day,
    _trade_days,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MAX_POSITION_COUNT,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_STAMP_TAX_BPS,
    DEFAULT_SHORTPICK_V2_RULE_CONFIGS,
    SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY,
    SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
    SHORTPICK_V2_REPLAY_SCHEMA_VERSION,
    SHORTPICK_V2_REPLAY_SOURCE_PLAN_REF,
    ShortpickV2RuleConfig,
    _build_low_turnover_uptrend_candidate_pool,
    _coverage_notes,
    build_shortpick_v2_replay_artifact_from_series,
    write_shortpick_v2_replay_artifact,
)

SHORTPICK_V2_STRATEGY_SEARCH_SOURCE_REF = "market_only_reconstruction:shortpick_v2_strategy_search_batch:v1"
SHORTPICK_V2_STRATEGY_SEARCH_EVENT_REF = "shortpick_v2.strategy_search.generated"
CONTROL_CANDIDATE_SOURCE_ID = LOW_TURNOVER_UPTREND_STRATEGY
DEFAULT_CANDIDATE_SOURCE_IDS = (
    CONTROL_CANDIDATE_SOURCE_ID,
    "quiet_breakout_rank2",
    "ret10_turnover_strong_breadth",
    "ret10_turnover_rank2_market_positive",
    "ret10_turnover_industry_diversified",
    "golden_cross_10_200",
)
STRATEGY_SEARCH_BATCH_INITIAL = "initial"
STRATEGY_SEARCH_BATCH_NEXT = "next"
STRATEGY_SEARCH_BATCH_REFINED = "refined"
STRATEGY_SEARCH_BATCH_H10_QUIET = "h10_quiet"
STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION = "h10_quiet_champion"
STRATEGY_SEARCH_BATCH_H10_ROBUST = "h10_robust"
STRATEGY_SEARCH_BATCH_H10_STRENGTH = "h10_strength"
STRATEGY_SEARCH_BATCH_H10_MA_ACCEL = "h10_ma_accel"
STRATEGY_SEARCH_BATCH_H10_MA_ACCEL_REFINE = "h10_ma_accel_refine"
STRATEGY_SEARCH_BATCH_H10_EXIT = "h10_exit"
STRATEGY_SEARCH_BATCH_H10_ENTRY_QUALITY = "h10_entry_quality"
STRATEGY_SEARCH_BATCHES = (
    STRATEGY_SEARCH_BATCH_INITIAL,
    STRATEGY_SEARCH_BATCH_NEXT,
    STRATEGY_SEARCH_BATCH_REFINED,
    STRATEGY_SEARCH_BATCH_H10_QUIET,
    STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION,
    STRATEGY_SEARCH_BATCH_H10_ROBUST,
    STRATEGY_SEARCH_BATCH_H10_STRENGTH,
    STRATEGY_SEARCH_BATCH_H10_MA_ACCEL,
    STRATEGY_SEARCH_BATCH_H10_MA_ACCEL_REFINE,
    STRATEGY_SEARCH_BATCH_H10_EXIT,
    STRATEGY_SEARCH_BATCH_H10_ENTRY_QUALITY,
)
NEXT_ROUND_CANDIDATE_SOURCE_IDS = (
    "trend_low_vol_breakout_v1",
    "leader_sector_pullback_v1",
    "relative_strength_low_vol_v1",
    "volume_absorption_breakout_v1",
    "low_turnover_sector_excess_v1",
    "breakout_retest_confirm_v1",
    "limit_up_followthrough_v1",
)
NEXT_ROUND_RULE_CONFIG_IDS = {
    "top1_or_skip_v1",
    "fixed_notional_40k_top5_v1",
    "conservative_cash_reserve_60k_top5_v1",
}
REFINED_ROUND_CANDIDATE_SOURCE_IDS = (
    "low_turnover_breadth65_v2",
    "low_turnover_rank2_breadth65_v2",
    "low_turnover_momentum15_v2",
    "low_turnover_red_day_momentum_v2",
    "low_turnover_high_price_momentum_v2",
    "low_turnover_ma_acceleration_v2",
    "low_turnover_vol_adjusted_v2",
)
REFINED_ROUND_RULE_CONFIG_IDS = NEXT_ROUND_RULE_CONFIG_IDS
H10_QUIET_CANDIDATE_SOURCE_IDS = (
    "quiet_breakout_rank2_poolhot10_mtw",
    "quiet_breakout_rank2to6_poolhot10_mtw",
    "quiet_breakout_rank2to6_mtw_or_breadth65",
    "quiet_breakout_rank2to6_poolhot10_not_thu",
    "quiet_breakout_rank2to6_poolhot10_mtw_ret5_0_10",
)
H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS = (
    "quiet_breakout_rank1_poolhot10_mtw",
    "quiet_breakout_rank2_poolhot10_mtw",
    "quiet_breakout_rank3_poolhot10_mtw",
    "quiet_breakout_rank4_poolhot10_mtw",
    "quiet_breakout_rank5_poolhot10_mtw",
    "quiet_breakout_rank2_poolhot09_mtw",
    "quiet_breakout_rank2_poolhot11_mtw",
    "quiet_breakout_rank2_poolhot12_mtw",
    "quiet_breakout_rank2_poolhot10_mt",
    "quiet_breakout_rank2_poolhot10_tw",
)
H10_ROBUST_CANDIDATE_SOURCE_IDS = (
    "relative_strength_low_vol_h10_v1",
    "low_turnover_breadth_rank2to5_h10_v1",
    "uptrend_red_day_pullback_h10_v1",
    "leader_pullback_sector_excess_h10_v1",
    "breakout_retest_confirm_h10_v1",
    "vol_adjusted_low_turnover_h10_v1",
    "ma_acceleration_low_vol_h10_v1",
    "quiet_breakout_robust_rank2to6_h10_v1",
    "volume_absorption_low_range_h10_v1",
)
H10_STRENGTH_CANDIDATE_SOURCE_IDS = (
    "h10_sector_rs_new_high_volume_v1",
    "h10_market_thrust_top_rs_v1",
    "h10_first_pullback_after_sector_breakout_v1",
    "h10_volume_acceleration_continuation_v1",
    "h10_limit_up_absorption_followthrough_v1",
    "h10_gap_strength_followthrough_v1",
    "uptrend_red_day_pullback_index_gated_h10_v2",
    "ma_acceleration_momentum_h10_v2",
)
H10_MA_ACCEL_CANDIDATE_SOURCE_IDS = (
    "ma_accel_momentum_loose_vol_h10_v3",
    "ma_accel_dense_rank_h10_v3",
    "ma_accel_red_day_entry_h10_v3",
    "ma_accel_sector_tailwind_h10_v3",
    "ma_accel_volume_confirm_h10_v3",
    "ma_accel_low_breadth_contrarian_h10_v3",
)
H10_MA_ACCEL_REFINE_CANDIDATE_SOURCE_IDS = (
    "ma_accel_volume_confirm_seed_h10_v4",
    "ma_accel_volume_confirm_dense_guard_h10_v4",
    "ma_accel_volume_confirm_quality_h10_v4",
    "ma_accel_volume_confirm_market_gated_h10_v4",
    "ma_accel_volume_confirm_rs_weighted_h10_v4",
    "ma_accel_volume_confirm_pullback_band_h10_v4",
)
H10_EXIT_CANDIDATE_SOURCE_IDS = (
    "ma_accel_volume_confirm_exit_seed_h10_v1",
)
H10_ENTRY_QUALITY_CANDIDATE_SOURCE_IDS = (
    "ma_accel_quality_rerank_h10_v5",
    "ma_accel_regime_fill_h10_v5",
    "ma_accel_early_inflection_h10_v5",
    "ma_accel_vol_squeeze_breakout_h10_v5",
    "ma_accel_volume_convergence_h10_v5",
    "ma_accel_industry_leader_h10_v5",
    "ma_accel_pullback_vol_calibrated_h10_v5",
    "ma_accel_range_contraction_h10_v5",
    "ma_accel_slope_acceleration_h10_v5",
    "ma_accel_gap_hold_h10_v5",
)
H10_QUIET_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_70k_top5_h10_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=70_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_75k_top5_h10_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=75_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_80k_top5_h10_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=80_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_85k_top5_h10_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=85_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_90k_top5_h10_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=90_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)
H10_ROBUST_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_h10_robust_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_50k_top5_h10_robust_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=50_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_60k_top5_h10_robust_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=60_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_70k_top5_h10_robust_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=70_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)
H10_STRENGTH_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_h10_strength_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_50k_top5_h10_strength_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=50_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_60k_top5_h10_strength_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=60_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_70k_top5_h10_strength_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=70_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)
H10_MA_ACCEL_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_30k_top5_h10_ma_accel_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=30_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_h10_ma_accel_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_50k_top5_h10_ma_accel_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=50_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_60k_top5_h10_ma_accel_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=60_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)
H10_MA_ACCEL_REFINE_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_35k_top5_h10_ma_accel_refine_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=35_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_h10_ma_accel_refine_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_45k_top5_h10_ma_accel_refine_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=45_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_50k_top5_h10_ma_accel_refine_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=50_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)
H10_EXIT_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_h10_exit_baseline_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_45k_top5_h10_exit_baseline_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=45_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_stop8_h10_exit_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        stop_loss_pct=0.08,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_45k_top5_stop8_h10_exit_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=45_000.0,
        stop_loss_pct=0.08,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_stop8_take12_h10_exit_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        stop_loss_pct=0.08,
        take_profit_pct=0.12,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_45k_top5_stop8_take12_h10_exit_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=45_000.0,
        stop_loss_pct=0.08,
        take_profit_pct=0.12,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_stop8_trail6_after10_h10_exit_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        stop_loss_pct=0.08,
        trailing_stop_pct=0.06,
        trailing_activation_pct=0.10,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_45k_top5_stop8_trail6_after10_h10_exit_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=45_000.0,
        stop_loss_pct=0.08,
        trailing_stop_pct=0.06,
        trailing_activation_pct=0.10,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)
H10_ENTRY_QUALITY_RULE_CONFIGS = (
    ShortpickV2RuleConfig(
        config_id="fixed_notional_35k_top5_h10_entry_quality_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=35_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_40k_top5_h10_entry_quality_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=40_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_45k_top5_h10_entry_quality_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=45_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
    ShortpickV2RuleConfig(
        config_id="fixed_notional_50k_top5_h10_entry_quality_v1",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=50_000.0,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    ),
)


@dataclass(frozen=True)
class StrategySearchCandidateSource:
    source_id: str
    source_ref: str
    selections: dict[date, list[str]]


def build_shortpick_v2_strategy_search_artifact(
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
    candidate_batch: str = STRATEGY_SEARCH_BATCH_INITIAL,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if candidate_batch not in STRATEGY_SEARCH_BATCHES:
        raise ValueError(f"candidate_batch must be one of {sorted(STRATEGY_SEARCH_BATCHES)}")
    _validate_strategy_search_batch_horizon(candidate_batch=candidate_batch, horizon_days=horizon_days)
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
    candidate_sources = _build_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        candidate_batch=candidate_batch,
    )
    return build_shortpick_v2_strategy_search_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=candidate_sources,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        account_profile=str(account_eligibility["account_profile"]),
        stock_like_series_count=len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        coverage_notes=_coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        candidate_batch=candidate_batch,
        generated_at=generated_at,
    )


def _build_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
    candidate_batch: str,
) -> tuple[StrategySearchCandidateSource, ...]:
    if candidate_batch == STRATEGY_SEARCH_BATCH_NEXT:
        return build_next_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_REFINED:
        return build_refined_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_QUIET:
        return build_h10_quiet_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION:
        return build_h10_quiet_champion_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_ROBUST:
        return build_h10_robust_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_STRENGTH:
        return build_h10_strength_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_MA_ACCEL:
        return build_h10_ma_accel_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_MA_ACCEL_REFINE:
        return build_h10_ma_accel_refine_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_EXIT:
        return build_h10_exit_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_ENTRY_QUALITY:
        return build_h10_entry_quality_strategy_search_candidate_sources(
            series_by_symbol,
            signal_days=signal_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    return build_default_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )


def build_default_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(
        rank_limit,
        max(config.candidate_rank_limit for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    ret10_turnover = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy="ret10_turnover",
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    quiet_breakout = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=_build_low_turnover_uptrend_candidate_pool(
                series_by_symbol,
                signal_days=signal_days,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="quiet_breakout_rank2",
            source_ref=f"market_only_reconstruction:{QUIET_BREAKOUT_RANK2_STRATEGY}:v1",
            selections=_apply_strategy_selection_transform(QUIET_BREAKOUT_RANK2_STRATEGY, quiet_breakout),
        ),
        StrategySearchCandidateSource(
            source_id="ret10_turnover_strong_breadth",
            source_ref="market_only_reconstruction:ret10_turnover_strong_breadth_pool:v1",
            selections=_apply_strategy_regime_filter(
                "ret10_turnover_strong_breadth_pool",
                ret10_turnover,
                regime_features,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="ret10_turnover_rank2_market_positive",
            source_ref=f"market_only_reconstruction:{STRONG_BREADTH_RANK2_STRATEGY}:v1",
            selections=_apply_strategy_regime_filter(
                STRONG_BREADTH_RANK2_STRATEGY,
                _apply_strategy_selection_transform(STRONG_BREADTH_RANK2_STRATEGY, ret10_turnover),
                regime_features,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="ret10_turnover_industry_diversified",
            source_ref="market_only_reconstruction:ret10_turnover_cooldown_diversified:v1",
            selections=_build_strategy_selections(
                series_by_symbol,
                signal_days=signal_days,
                strategy="ret10_turnover_cooldown_diversified",
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="golden_cross_10_200",
            source_ref=f"market_only_reconstruction:{GOLDEN_CROSS_STRATEGY}:v1",
            selections=_build_strategy_selections(
                series_by_symbol,
                signal_days=signal_days,
                strategy=GOLDEN_CROSS_STRATEGY,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
    )


def build_next_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(
        rank_limit,
        max(config.candidate_rank_limit for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS),
    )
    next_round_selections = _build_next_round_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=NEXT_ROUND_CANDIDATE_SOURCE_IDS,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=_build_low_turnover_uptrend_candidate_pool(
                series_by_symbol,
                signal_days=signal_days,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_next_round:{source_id}",
                selections=next_round_selections[source_id],
            )
            for source_id in NEXT_ROUND_CANDIDATE_SOURCE_IDS
        ),
    )


def build_refined_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(
        rank_limit,
        max(config.candidate_rank_limit for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS),
    )
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=max(effective_rank_limit, 6),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    refined_selections = _build_refined_round_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=REFINED_ROUND_CANDIDATE_SOURCE_IDS,
        control_selections=control_selections,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_refined_round:{source_id}",
                selections=refined_selections[source_id],
            )
            for source_id in REFINED_ROUND_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_quiet_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(rank_limit, max(config.candidate_rank_limit for config in H10_QUIET_RULE_CONFIGS))
    quiet_base = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=max(effective_rank_limit, 6),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    h10_quiet_selections = _build_h10_quiet_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_QUIET_CANDIDATE_SOURCE_IDS,
        quiet_base_selections=quiet_base,
        regime_features=regime_features,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=_build_low_turnover_uptrend_candidate_pool(
                series_by_symbol,
                signal_days=signal_days,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_quiet_round:{source_id}",
                selections=h10_quiet_selections[source_id],
            )
            for source_id in H10_QUIET_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_quiet_champion_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(rank_limit, max(config.candidate_rank_limit for config in H10_QUIET_RULE_CONFIGS))
    quiet_base = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=max(effective_rank_limit, 6),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    champion_selections = _build_h10_quiet_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS,
        quiet_base_selections=quiet_base,
        regime_features=regime_features,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=_build_low_turnover_uptrend_candidate_pool(
                series_by_symbol,
                signal_days=signal_days,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_quiet_champion_round:{source_id}",
                selections=champion_selections[source_id],
            )
            for source_id in H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_robust_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(rank_limit, max(config.candidate_rank_limit for config in H10_ROBUST_RULE_CONFIGS))
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=max(effective_rank_limit, 6),
    )
    quiet_base = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=max(effective_rank_limit, 6),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    h10_robust_selections = _build_h10_robust_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_ROBUST_CANDIDATE_SOURCE_IDS,
        control_selections=control_selections,
        quiet_base_selections=quiet_base,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_robust_round:{source_id}",
                selections=h10_robust_selections[source_id],
            )
            for source_id in H10_ROBUST_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_strength_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(rank_limit, max(config.candidate_rank_limit for config in H10_STRENGTH_RULE_CONFIGS))
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    h10_strength_selections = _build_h10_strength_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_STRENGTH_CANDIDATE_SOURCE_IDS,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_strength_round:{source_id}",
                selections=h10_strength_selections[source_id],
            )
            for source_id in H10_STRENGTH_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_ma_accel_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(rank_limit, max(config.candidate_rank_limit for config in H10_MA_ACCEL_RULE_CONFIGS))
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    h10_ma_accel_selections = _build_h10_ma_accel_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_MA_ACCEL_CANDIDATE_SOURCE_IDS,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_ma_accel_round:{source_id}",
                selections=h10_ma_accel_selections[source_id],
            )
            for source_id in H10_MA_ACCEL_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_ma_accel_refine_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(
        rank_limit,
        max(config.candidate_rank_limit for config in H10_MA_ACCEL_REFINE_RULE_CONFIGS),
    )
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    h10_ma_accel_selections = _build_h10_ma_accel_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_MA_ACCEL_REFINE_CANDIDATE_SOURCE_IDS,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_ma_accel_refine_round:{source_id}",
                selections=h10_ma_accel_selections[source_id],
            )
            for source_id in H10_MA_ACCEL_REFINE_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_exit_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(
        rank_limit,
        max(config.candidate_rank_limit for config in H10_EXIT_RULE_CONFIGS),
    )
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    h10_exit_selections = _build_h10_ma_accel_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_EXIT_CANDIDATE_SOURCE_IDS,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_exit_round:{source_id}",
                selections=h10_exit_selections[source_id],
            )
            for source_id in H10_EXIT_CANDIDATE_SOURCE_IDS
        ),
    )


def build_h10_entry_quality_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(
        rank_limit,
        max(config.candidate_rank_limit for config in H10_ENTRY_QUALITY_RULE_CONFIGS),
    )
    control_selections = _build_low_turnover_uptrend_candidate_pool(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    entry_quality_selections = _build_h10_ma_accel_batch_selections(
        series_by_symbol,
        signal_days=signal_days,
        source_ids=H10_ENTRY_QUALITY_CANDIDATE_SOURCE_IDS,
        regime_features=regime_features,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=control_selections,
        ),
        *(
            StrategySearchCandidateSource(
                source_id=source_id,
                source_ref=f"market_only_reconstruction:shortpick_v2_h10_entry_quality_round:{source_id}",
                selections=entry_quality_selections[source_id],
            )
            for source_id in H10_ENTRY_QUALITY_CANDIDATE_SOURCE_IDS
        ),
    )


def build_shortpick_v2_strategy_search_artifact_from_series(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    candidate_sources: tuple[StrategySearchCandidateSource, ...],
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
    candidate_batch: str = STRATEGY_SEARCH_BATCH_INITIAL,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if not candidate_sources:
        raise ValueError("candidate_sources must not be empty")
    _validate_strategy_search_batch_horizon(candidate_batch=candidate_batch, horizon_days=horizon_days)
    if CONTROL_CANDIDATE_SOURCE_ID not in {source.source_id for source in candidate_sources}:
        raise ValueError(f"candidate_sources must include {CONTROL_CANDIDATE_SOURCE_ID}")
    generated_at = generated_at or datetime.now(UTC)
    stock_like_series_count = (
        stock_like_series_count
        if stock_like_series_count is not None
        else len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    )
    child_artifacts = [
        _build_child_artifact(
            series_by_symbol,
            signal_days=signal_days,
            trade_days=trade_days,
            candidate_source=source,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            entry_price_source=entry_price_source,
            horizon_days=horizon_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
            cost_bps=cost_bps,
            stamp_tax_bps=stamp_tax_bps,
            account_profile=account_profile,
            stock_like_series_count=stock_like_series_count,
            coverage_notes=coverage_notes,
            generated_at=generated_at,
        )
        for source in candidate_sources
    ]
    return _merge_child_artifacts(
        child_artifacts,
        candidate_sources=candidate_sources,
        generated_at=generated_at,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        candidate_batch=candidate_batch,
    )


def write_shortpick_v2_strategy_search_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    return write_shortpick_v2_replay_artifact(payload, output_path=output_path)


def _build_child_artifact(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    candidate_source: StrategySearchCandidateSource,
    start_date: date,
    end_date: date,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    pool_limit: int,
    rank_limit: int,
    cost_bps: float,
    stamp_tax_bps: float,
    account_profile: str,
    stock_like_series_count: int,
    coverage_notes: list[str] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    return build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=candidate_source.selections,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        account_profile=account_profile,
        stock_like_series_count=stock_like_series_count,
        coverage_notes=coverage_notes,
        rule_configs=_rule_configs_for_source(candidate_source.source_id),
        generated_at=generated_at,
    )


def _rule_configs_for_source(source_id: str) -> tuple[ShortpickV2RuleConfig, ...]:
    if source_id == CONTROL_CANDIDATE_SOURCE_ID:
        return DEFAULT_SHORTPICK_V2_RULE_CONFIGS
    if source_id in NEXT_ROUND_CANDIDATE_SOURCE_IDS:
        return tuple(
            _prefixed_rule_config(source_id, config)
            for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS
            if config.config_id in NEXT_ROUND_RULE_CONFIG_IDS
        )
    if source_id in REFINED_ROUND_CANDIDATE_SOURCE_IDS:
        return tuple(
            _prefixed_rule_config(source_id, config)
            for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS
            if config.config_id in REFINED_ROUND_RULE_CONFIG_IDS
        )
    if source_id in H10_QUIET_CANDIDATE_SOURCE_IDS or source_id in H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_QUIET_RULE_CONFIGS)
    if source_id in H10_ROBUST_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_ROBUST_RULE_CONFIGS)
    if source_id in H10_STRENGTH_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_STRENGTH_RULE_CONFIGS)
    if source_id in H10_MA_ACCEL_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_MA_ACCEL_RULE_CONFIGS)
    if source_id in H10_MA_ACCEL_REFINE_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_MA_ACCEL_REFINE_RULE_CONFIGS)
    if source_id in H10_EXIT_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_EXIT_RULE_CONFIGS)
    if source_id in H10_ENTRY_QUALITY_CANDIDATE_SOURCE_IDS:
        return tuple(_prefixed_rule_config(source_id, config) for config in H10_ENTRY_QUALITY_RULE_CONFIGS)
    return tuple(_prefixed_rule_config(source_id, config) for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS)


def _prefixed_rule_config(source_id: str, config: ShortpickV2RuleConfig) -> ShortpickV2RuleConfig:
    return ShortpickV2RuleConfig(
        config_id=f"{source_id}__{config.config_id}",
        family=config.family,
        candidate_rank_limit=config.candidate_rank_limit,
        fallback_enabled=config.fallback_enabled,
        target_mode=config.target_mode,
        allowed_actions=config.allowed_actions,
        target_notional=config.target_notional,
        cash_reserve=config.cash_reserve,
        max_position_count=config.max_position_count,
        max_position_pct=config.max_position_pct,
        board_lot_size=config.board_lot_size,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        trailing_stop_pct=config.trailing_stop_pct,
        trailing_activation_pct=config.trailing_activation_pct,
    )


def _merge_child_artifacts(
    child_artifacts: list[dict[str, Any]],
    *,
    candidate_sources: tuple[StrategySearchCandidateSource, ...],
    generated_at: datetime,
    start_date: date,
    end_date: date,
    initial_cash: float,
    candidate_batch: str,
) -> dict[str, Any]:
    template = dict(child_artifacts[0])
    template["artifact_id"] = _strategy_search_artifact_id(
        generated_at,
        start_date,
        end_date,
        initial_cash,
        candidate_batch=candidate_batch,
    )
    template["source_plan_ref"] = SHORTPICK_V2_REPLAY_SOURCE_PLAN_REF
    template["rule_matrix"] = _unique_by_config_id(
        row for child in child_artifacts for row in child.get("rule_matrix") or []
    )
    template["results"] = _unique_by_config_id(
        row for child in child_artifacts for row in child.get("results") or []
    )
    input_contracts = dict(template.get("input_contracts") or {})
    input_contracts["candidate_source"] = {
        "source_family": "shortpick_v2_candidate_projection",
        "source_ref": _strategy_search_source_ref(candidate_batch),
        "ranked_pool_required": True,
        "source_feature_cutoff_policy": (
            "Strategy-search candidate pools are reconstructed from signal-day-or-earlier daily-bar features; "
            "entry and exit bars are used only by the execution replay."
        ),
        "allowed_evidence_basis": ["historical_backtest", "market_only_reconstruction"],
    }
    exit_model = dict(input_contracts.get("exit_model") or {})
    exit_model["exit_tracks"] = _merged_exit_tracks(child_artifacts)
    input_contracts["exit_model"] = exit_model
    template["input_contracts"] = input_contracts
    data_scope = dict(template.get("data_scope") or {})
    coverage_notes = list(data_scope.get("coverage_notes") or [])
    coverage_notes.append(
        "Strategy-search batch evaluated candidate sources: "
        + ", ".join(source.source_ref for source in candidate_sources)
        + "."
    )
    data_scope["coverage_notes"] = coverage_notes
    template["data_scope"] = data_scope
    template["event_refs"] = sorted(
        {
            *(str(ref) for child in child_artifacts for ref in child.get("event_refs") or []),
            f"{SHORTPICK_V2_STRATEGY_SEARCH_EVENT_REF}.{candidate_batch}",
        }
    )
    _validate_merged_artifact(template)
    return template


def _merged_exit_tracks(child_artifacts: list[dict[str, Any]]) -> list[str]:
    tracks: list[str] = []
    for child in child_artifacts:
        exit_model = (child.get("input_contracts") or {}).get("exit_model") or {}
        for track in exit_model.get("exit_tracks") or []:
            if track not in tracks:
                tracks.append(str(track))
    return tracks


def _build_h10_quiet_batch_selections(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    source_ids: tuple[str, ...],
    quiet_base_selections: dict[date, list[str]],
    regime_features: dict[date, dict[str, float]],
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    selections_by_source: dict[str, dict[date, list[str]]] = {source_id: {} for source_id in source_ids}
    for signal_day in signal_days:
        base_symbols = quiet_base_selections.get(signal_day) or []
        context_by_symbol = {
            str(context["symbol"]): context
            for symbol in base_symbols[: max(rank_limit + 1, 6)]
            for series in [series_by_symbol.get(symbol)]
            if series is not None
            for context in [_next_round_context(series, signal_day)]
            if context is not None
        }
        for source_id in source_ids:
            symbols = _h10_quiet_source_symbols(
                source_id,
                signal_day=signal_day,
                base_symbols=base_symbols,
                context_by_symbol=context_by_symbol,
                regime_features=regime_features.get(signal_day) or {},
                rank_limit=rank_limit,
            )
            selections_by_source[source_id][signal_day] = symbols
    return selections_by_source


def _h10_quiet_source_symbols(
    source_id: str,
    *,
    signal_day: date,
    base_symbols: list[str],
    context_by_symbol: dict[str, dict[str, Any]],
    regime_features: dict[str, float],
    rank_limit: int,
) -> list[str]:
    if source_id == "quiet_breakout_rank2to6_mtw_or_breadth65":
        if not (
            (_h10_pool_hot(regime_features) and signal_day.weekday() in {0, 1, 2})
            or (
                signal_day.weekday() != 3
                and float(regime_features.get("universe_breadth10", 0.0)) >= 0.65
                and float(regime_features.get("pool_ret10_mean", 0.0)) >= 0.06
            )
        ):
            return []
    elif not _h10_pool_hot(regime_features, threshold=_h10_pool_hot_threshold(source_id)):
        return []
    allowed_weekdays = _h10_quiet_allowed_weekdays(source_id)
    if allowed_weekdays is not None and signal_day.weekday() not in allowed_weekdays:
        return []
    elif source_id == "quiet_breakout_rank2to6_poolhot10_not_thu" and signal_day.weekday() == 3:
        return []

    rank_position = _h10_quiet_single_rank_position(source_id)
    if rank_position is not None:
        start = rank_position - 1
        return base_symbols[start:rank_position] if len(base_symbols) >= rank_position else []
    symbols = base_symbols[1 : 1 + rank_limit] if len(base_symbols) >= 2 else []
    if source_id == "quiet_breakout_rank2to6_poolhot10_mtw_ret5_0_10":
        return [
            symbol
            for symbol in symbols
            if symbol in context_by_symbol and 0.0 <= float(context_by_symbol[symbol]["return_5d"]) <= 0.10
        ]
    return symbols


def _h10_pool_hot(regime_features: dict[str, float], *, threshold: float = 0.10) -> bool:
    return float(regime_features.get("pool_ret1_mean", 0.0)) >= threshold


def _h10_pool_hot_threshold(source_id: str) -> float:
    if "poolhot09" in source_id:
        return 0.09
    if "poolhot11" in source_id:
        return 0.11
    if "poolhot12" in source_id:
        return 0.12
    return 0.10


def _h10_quiet_allowed_weekdays(source_id: str) -> set[int] | None:
    if source_id.endswith("_mt"):
        return {0, 1}
    if source_id.endswith("_tw"):
        return {1, 2}
    if source_id in {
        "quiet_breakout_rank1_poolhot10_mtw",
        "quiet_breakout_rank2_poolhot10_mtw",
        "quiet_breakout_rank3_poolhot10_mtw",
        "quiet_breakout_rank4_poolhot10_mtw",
        "quiet_breakout_rank5_poolhot10_mtw",
        "quiet_breakout_rank2_poolhot09_mtw",
        "quiet_breakout_rank2_poolhot11_mtw",
        "quiet_breakout_rank2_poolhot12_mtw",
        "quiet_breakout_rank2to6_poolhot10_mtw",
        "quiet_breakout_rank2to6_poolhot10_mtw_ret5_0_10",
    }:
        return {0, 1, 2}
    return None


def _h10_quiet_single_rank_position(source_id: str) -> int | None:
    prefix = "quiet_breakout_rank"
    if not source_id.startswith(prefix):
        return None
    suffix = source_id.removeprefix(prefix)
    rank_text, _, rest = suffix.partition("_")
    if not rest.startswith("poolhot"):
        return None
    try:
        rank = int(rank_text)
    except ValueError:
        return None
    return rank if rank >= 1 else None


def _build_h10_robust_batch_selections(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    source_ids: tuple[str, ...],
    control_selections: dict[date, list[str]],
    quiet_base_selections: dict[date, list[str]],
    regime_features: dict[date, dict[str, float]],
    pool_limit: int,
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    selections_by_source: dict[str, dict[date, list[str]]] = {source_id: {} for source_id in source_ids}
    for signal_day in signal_days:
        contexts = _next_round_contexts(series_by_symbol, signal_day)
        context_by_symbol = {str(context["symbol"]): context for context in contexts}
        industry_returns = _industry_return_map(contexts, "return_20d")
        index_context = (
            _next_round_context(series_by_symbol["000300.SH"], signal_day)
            if "000300.SH" in series_by_symbol
            else None
        )
        market_ret20 = float(index_context.get("return_20d") or 0.0) if index_context else 0.0
        market_ret60 = float(index_context.get("return_60d") or 0.0) if index_context else 0.0
        features = regime_features.get(signal_day) or {}
        control_symbols = [symbol for symbol in control_selections.get(signal_day, []) if symbol in context_by_symbol]
        quiet_symbols = [symbol for symbol in quiet_base_selections.get(signal_day, []) if symbol in context_by_symbol]
        for source_id in source_ids:
            ranked = _rank_h10_robust_contexts(
                contexts,
                context_by_symbol=context_by_symbol,
                control_symbols=control_symbols,
                quiet_symbols=quiet_symbols,
                source_id=source_id,
                regime_features=features,
                industry_returns=industry_returns,
                market_ret20=market_ret20,
                market_ret60=market_ret60,
                pool_limit=pool_limit,
            )
            selections_by_source[source_id][signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections_by_source


def _rank_h10_robust_contexts(
    contexts: list[dict[str, Any]],
    *,
    context_by_symbol: dict[str, dict[str, Any]],
    control_symbols: list[str],
    quiet_symbols: list[str],
    source_id: str,
    regime_features: dict[str, float],
    industry_returns: dict[str, float],
    market_ret20: float,
    market_ret60: float,
    pool_limit: int,
) -> list[dict[str, Any]]:
    if source_id == "low_turnover_breadth_rank2to5_h10_v1":
        pool = [context_by_symbol[symbol] for symbol in control_symbols[1:]]
    elif source_id == "quiet_breakout_robust_rank2to6_h10_v1":
        pool = [context_by_symbol[symbol] for symbol in quiet_symbols[1:]]
    else:
        pool = sorted(
            contexts,
            key=lambda item: (float(item["amount"]), float(item["return_20d"])),
            reverse=True,
        )[: max(pool_limit, 180)]
    candidates = [
        item
        for item in pool
        if _h10_robust_candidate_allows(
            item,
            source_id=source_id,
            regime_features=regime_features,
            industry_returns=industry_returns,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        )
    ]
    ranked = sorted(
        candidates,
        key=lambda item: _h10_robust_score(
            pool,
            item,
            source_id=source_id,
            regime_features=regime_features,
            industry_returns=industry_returns,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        ),
        reverse=True,
    )
    if source_id in {
        "leader_pullback_sector_excess_h10_v1",
        "relative_strength_low_vol_h10_v1",
    }:
        ranked = _dedupe_industry(ranked, max_per_industry=1)
    return ranked


def _h10_robust_candidate_allows(
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> bool:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    universe_ret10_mean = float(regime_features.get("universe_ret10_mean", 0.0))
    pool_ret1_mean = float(regime_features.get("pool_ret1_mean", 0.0))
    pool_ret10_mean = float(regime_features.get("pool_ret10_mean", 0.0))
    close = float(item["close"])
    ma20 = float(item["ma20"] or 0.0)
    ma50 = float(item["ma50"] or 0.0)
    ma60 = float(item["ma60"] or 0.0)
    ma120 = float(item["ma120"] or 0.0)
    ret1 = float(item["return_1d"])
    ret5 = float(item["return_5d"])
    ret10 = float(item["return_10d"])
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    drawdown20 = float(item["drawdown20"])
    volatility20 = float(item["volatility20"])
    volatility60 = float(item["volatility60"])
    amount_ratio20 = float(item["amount_ratio20"])
    amount_ratio60 = float(item["amount_ratio60"])
    turnover = float(item["turnover_rate"])
    industry_ret20 = industry_returns.get(str(item["industry"]), 0.0)
    if ret1 >= 0.095 or close <= 0 or float(item["amount"]) < 5_000_000.0:
        return False
    if source_id == "relative_strength_low_vol_h10_v1":
        return (
            universe_ret10_mean >= 0.0
            and close > ma50
            and ret60 > market_ret60 + 0.03
            and float(item["return_120d"]) > 0.0
            and float(item["drawdown60"]) > -0.22
            and drawdown20 > -0.10
            and volatility20 <= volatility60 * 1.05
            and ret5 < 0.12
            and turnover <= 2.5
        )
    if source_id == "low_turnover_breadth_rank2to5_h10_v1":
        return (
            breadth10 >= 0.55
            and pool_ret1_mean <= 0.08
            and close > ma50
            and ret20 > 0.0
            and ret60 > 0.0
            and drawdown20 > -0.10
            and volatility20 <= volatility60 * 1.10
            and turnover <= 1.5
        )
    if source_id == "uptrend_red_day_pullback_h10_v1":
        return (
            breadth10 >= 0.50
            and close > ma50
            and ma20 > ma50
            and ret20 >= 0.05
            and ret60 > 0.0
            and -0.05 <= ret1 <= 0.0
            and close >= ma20 * 0.96
            and drawdown20 > -0.08
            and float(item["amount_ratio5"]) >= 0.80
            and amount_ratio20 <= 1.6
        )
    if source_id == "leader_pullback_sector_excess_h10_v1":
        return (
            breadth10 >= 0.52
            and close > ma60
            and ret60 > market_ret60
            and industry_ret20 > market_ret20
            and -0.12 <= drawdown20 <= -0.015
            and close >= ma20 * 0.96
            and close <= float(item["ma30"] or ma20) * 1.08
            and ret1 > 0.0
            and amount_ratio20 <= 1.4
        )
    if source_id == "breakout_retest_confirm_h10_v1":
        return (
            breadth10 >= 0.50
            and close > ma20 > ma60
            and -0.06 <= ret5 <= 0.08
            and close >= float(item["high20"]) * 0.94
            and float(item["low10"]) >= ma20 * 0.94
            and ret1 > 0.0
            and amount_ratio20 >= 1.05
            and drawdown20 > -0.10
        )
    if source_id == "vol_adjusted_low_turnover_h10_v1":
        return (
            breadth10 >= 0.50
            and close > ma50
            and ret20 >= 0.05
            and ret60 > 0.0
            and drawdown20 > -0.10
            and volatility60 > 0.0
            and volatility20 <= volatility60 * 1.05
            and turnover <= 1.5
        )
    if source_id == "ma_acceleration_low_vol_h10_v1":
        return (
            breadth10 >= 0.50
            and close > ma20 > ma60 > ma120
            and ret20 >= 0.05
            and ret60 > 0.0
            and drawdown20 > -0.10
            and volatility20 <= volatility60 * 1.05
            and float(item["ma20_slope"]) > 0.0
            and float(item["ma50_slope"]) > 0.0
            and float(item["ma20_slope"]) >= float(item["ma50_slope"]) * 1.1
            and turnover <= 2.0
        )
    if source_id == "quiet_breakout_robust_rank2to6_h10_v1":
        return (
            (breadth10 >= 0.55 or pool_ret10_mean >= 0.06)
            and pool_ret1_mean <= 0.08
            and 0.0 <= ret5 <= 0.10
            and ret1 <= 0.04
            and ret10 > 0.02
            and drawdown20 > -0.10
            and volatility20 <= volatility60 * 1.05
        )
    if source_id == "volume_absorption_low_range_h10_v1":
        return (
            breadth10 >= 0.50
            and close > ma50
            and amount_ratio60 >= 2.0
            and float(item["range20"]) <= float(item["range60"]) * 0.90
            and float(item["close_position"]) >= 0.60
            and float(item["ma50_slope"]) >= -0.01
            and ret1 > -0.01
            and drawdown20 > -0.10
        )
    return False


def _h10_robust_score(
    pool: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> float:
    del regime_features
    industry_ret20 = industry_returns.get(str(item["industry"]), 0.0)
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    volatility20 = max(float(item["volatility20"]), 0.001)
    volatility60 = max(float(item["volatility60"]), 0.001)
    rs20 = ret20 - market_ret20
    rs60 = ret60 - market_ret60
    if source_id == "relative_strength_low_vol_h10_v1":
        return rs60 + 0.5 * rs20 + _inverse_percentile_by(pool, "volatility20", item)
    if source_id == "low_turnover_breadth_rank2to5_h10_v1":
        return ret60 / volatility60 + 0.5 * ret20 + _inverse_percentile_by(pool, "turnover_rate", item)
    if source_id == "uptrend_red_day_pullback_h10_v1":
        return ret20 + 0.5 * ret60 + _inverse_percentile_by(pool, "drawdown20", item)
    if source_id == "leader_pullback_sector_excess_h10_v1":
        return (
            _percentile_value([industry_returns.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
            + _percentile_by(pool, "return_60d", item)
            + _inverse_percentile_by(pool, "drawdown20", item)
            + max(float(item["return_1d"]), 0.0)
        )
    if source_id == "breakout_retest_confirm_h10_v1":
        return (
            _percentile_by(pool, "return_60d", item)
            + _inverse_percentile_by(pool, "drawdown20", item)
            + min(float(item["amount_ratio20"]) / 2.5, 1.2)
        )
    if source_id == "vol_adjusted_low_turnover_h10_v1":
        return ret60 / volatility60 + 0.5 * ret20 + _inverse_percentile_by(pool, "turnover_rate", item)
    if source_id == "ma_acceleration_low_vol_h10_v1":
        return (
            ret20 / volatility20
            + float(item["ma20_slope"]) * 10.0
            + _inverse_percentile_by(pool, "drawdown20", item)
        )
    if source_id == "quiet_breakout_robust_rank2to6_h10_v1":
        return (
            ret20
            + _inverse_percentile_by(pool, "return_1d", item)
            + _inverse_percentile_by(pool, "volatility20", item)
        )
    if source_id == "volume_absorption_low_range_h10_v1":
        return (
            min(float(item["amount_ratio60"]) / 4.0, 2.0)
            + float(item["close_position"])
            + _inverse_percentile_by(pool, "range20", item)
            + max(ret20, 0.0)
        )
    return 0.0


def _dedupe_industry(rows: list[dict[str, Any]], *, max_per_industry: int) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    output: list[dict[str, Any]] = []
    for row in rows:
        industry = str(row.get("industry") or "unknown")
        if counts.get(industry, 0) >= max_per_industry:
            continue
        counts[industry] = counts.get(industry, 0) + 1
        output.append(row)
    return output


def _build_h10_strength_batch_selections(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    source_ids: tuple[str, ...],
    regime_features: dict[date, dict[str, float]],
    pool_limit: int,
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    selections_by_source: dict[str, dict[date, list[str]]] = {source_id: {} for source_id in source_ids}
    for signal_day in signal_days:
        contexts = _next_round_contexts(series_by_symbol, signal_day)
        industry_returns20 = _industry_return_map(contexts, "return_20d")
        industry_returns60 = _industry_return_map(contexts, "return_60d")
        index_context = (
            _next_round_context(series_by_symbol["000300.SH"], signal_day)
            if "000300.SH" in series_by_symbol
            else None
        )
        market_ret20 = float(index_context.get("return_20d") or 0.0) if index_context else 0.0
        market_ret60 = float(index_context.get("return_60d") or 0.0) if index_context else 0.0
        market_above_ma60 = (
            bool(index_context)
            and float(index_context.get("ma60") or 0.0) > 0.0
            and float(index_context.get("close") or 0.0) > float(index_context.get("ma60") or 0.0)
        )
        features = regime_features.get(signal_day) or {}
        for source_id in source_ids:
            ranked = _rank_h10_strength_contexts(
                contexts,
                source_id=source_id,
                regime_features=features,
                industry_returns20=industry_returns20,
                industry_returns60=industry_returns60,
                market_ret20=market_ret20,
                market_ret60=market_ret60,
                market_above_ma60=market_above_ma60,
                pool_limit=pool_limit,
            )
            selections_by_source[source_id][signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections_by_source


def _rank_h10_strength_contexts(
    contexts: list[dict[str, Any]],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns20: dict[str, float],
    industry_returns60: dict[str, float],
    market_ret20: float,
    market_ret60: float,
    market_above_ma60: bool,
    pool_limit: int,
) -> list[dict[str, Any]]:
    pool = sorted(
        contexts,
        key=lambda item: (float(item["amount"]), float(item["return_20d"])),
        reverse=True,
    )[: max(pool_limit, 220)]
    candidates = [
        item
        for item in pool
        if _h10_strength_candidate_allows(
            item,
            source_id=source_id,
            regime_features=regime_features,
            industry_returns20=industry_returns20,
            industry_returns60=industry_returns60,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
            market_above_ma60=market_above_ma60,
        )
    ]
    ranked = sorted(
        candidates,
        key=lambda item: _h10_strength_score(
            pool,
            item,
            source_id=source_id,
            regime_features=regime_features,
            industry_returns20=industry_returns20,
            industry_returns60=industry_returns60,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        ),
        reverse=True,
    )
    if source_id in {
        "h10_sector_rs_new_high_volume_v1",
        "h10_first_pullback_after_sector_breakout_v1",
        "h10_gap_strength_followthrough_v1",
    }:
        ranked = _dedupe_industry(ranked, max_per_industry=2)
    return ranked


def _h10_strength_candidate_allows(
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns20: dict[str, float],
    industry_returns60: dict[str, float],
    market_ret20: float,
    market_ret60: float,
    market_above_ma60: bool,
) -> bool:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    universe_ret10_mean = float(regime_features.get("universe_ret10_mean", 0.0))
    pool_ret10_mean = float(regime_features.get("pool_ret10_mean", 0.0))
    close = float(item["close"])
    ma20 = float(item["ma20"] or 0.0)
    ma50 = float(item["ma50"] or 0.0)
    ma60 = float(item["ma60"] or 0.0)
    ma120 = float(item["ma120"] or 0.0)
    ret1 = float(item["return_1d"])
    ret3 = float(item["return_3d"])
    ret5 = float(item["return_5d"])
    ret10 = float(item["return_10d"])
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    drawdown20 = float(item["drawdown20"])
    volatility20 = float(item["volatility20"])
    volatility60 = float(item["volatility60"])
    amount_ratio5 = float(item["amount_ratio5"])
    amount_ratio20 = float(item["amount_ratio20"])
    turnover = float(item["turnover_rate"])
    close_position = float(item["close_position"])
    industry = str(item["industry"])
    industry_ret20 = industry_returns20.get(industry, 0.0)
    industry_ret60 = industry_returns60.get(industry, 0.0)
    if ret1 >= 0.095 or close <= 0.0 or ma20 <= 0.0 or ma60 <= 0.0 or float(item["amount"]) < 5_000_000.0:
        return False
    if source_id == "h10_sector_rs_new_high_volume_v1":
        return (
            breadth10 >= 0.48
            and market_ret20 >= -0.04
            and close > ma20 > ma60
            and ret20 >= max(0.08, market_ret20 + 0.05)
            and ret60 >= market_ret60 + 0.06
            and industry_ret20 >= market_ret20 + 0.03
            and industry_ret60 >= market_ret60 + 0.02
            and (close >= float(item["high20_prev"]) * 0.995 or drawdown20 > -0.025)
            and 1.20 <= amount_ratio20 <= 4.00
            and 0.0 < ret1 < 0.08
            and close_position >= 0.55
        )
    if source_id == "h10_market_thrust_top_rs_v1":
        return (
            breadth10 >= 0.60
            and universe_ret10_mean >= 0.01
            and pool_ret10_mean >= 0.03
            and market_ret20 >= -0.03
            and close > ma20
            and ret20 >= 0.10
            and ret60 >= max(0.08, market_ret60 + 0.05)
            and 0.0 < ret1 < 0.08
            and amount_ratio20 >= 0.90
            and drawdown20 > -0.12
        )
    if source_id == "h10_first_pullback_after_sector_breakout_v1":
        return (
            breadth10 >= 0.50
            and industry_ret20 >= market_ret20 + 0.04
            and industry_ret60 >= market_ret60
            and close > ma60
            and ret20 >= 0.10
            and ret60 >= 0.08
            and -0.04 <= ret1 <= 0.005
            and close >= ma20 * 0.98
            and -0.10 <= drawdown20 <= -0.005
            and amount_ratio5 >= 0.70
            and amount_ratio20 <= 2.20
        )
    if source_id == "h10_volume_acceleration_continuation_v1":
        return (
            breadth10 >= 0.50
            and close > ma20 > ma60
            and ret5 >= 0.03
            and ret10 >= 0.06
            and ret20 >= 0.12
            and ret60 > 0.0
            and 0.0 < ret1 < 0.08
            and amount_ratio5 >= 1.15
            and 1.10 <= amount_ratio20 <= 5.00
            and close_position >= 0.55
            and drawdown20 > -0.10
        )
    if source_id == "h10_limit_up_absorption_followthrough_v1":
        return (
            breadth10 >= 0.45
            and float(item["previous_return_1d"]) >= 0.085
            and -0.02 <= ret1 <= 0.08
            and close >= ma20 * 0.97
            and close_position >= 0.55
            and 1.10 <= amount_ratio20 <= 5.00
            and ret3 < 0.28
            and drawdown20 > -0.12
        )
    if source_id == "h10_gap_strength_followthrough_v1":
        return (
            breadth10 >= 0.48
            and float(item["open_gap"]) >= 0.015
            and 0.0 < ret1 < 0.08
            and close_position >= 0.65
            and 1.20 <= amount_ratio20 <= 5.00
            and close > ma20
            and ret20 >= 0.08
            and ret60 > 0.0
            and drawdown20 > -0.08
            and industry_ret20 > market_ret20
        )
    if source_id == "uptrend_red_day_pullback_index_gated_h10_v2":
        return (
            market_above_ma60
            and market_ret20 >= -0.03
            and breadth10 >= 0.52
            and close > ma50
            and ma20 > ma50
            and ret20 >= 0.05
            and ret60 > 0.0
            and -0.05 <= ret1 <= 0.0
            and close >= ma20 * 0.96
            and drawdown20 > -0.08
            and amount_ratio5 >= 0.80
            and amount_ratio20 <= 1.60
        )
    if source_id == "ma_acceleration_momentum_h10_v2":
        return (
            breadth10 >= 0.50
            and market_ret20 >= -0.05
            and close > ma20 > ma60 > ma120
            and ret20 >= 0.05
            and ret60 > 0.0
            and ret1 < 0.08
            and drawdown20 > -0.12
            and volatility20 <= volatility60 * 1.20
            and float(item["ma20_slope"]) > 0.0
            and float(item["ma50_slope"]) > 0.0
            and float(item["ma20_slope"]) >= float(item["ma50_slope"]) * 1.05
            and turnover <= 3.50
        )
    return False


def _h10_strength_score(
    pool: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns20: dict[str, float],
    industry_returns60: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> float:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    industry = str(item["industry"])
    industry_ret20 = industry_returns20.get(industry, 0.0)
    industry_ret60 = industry_returns60.get(industry, 0.0)
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    volatility20 = max(float(item["volatility20"]), 0.001)
    volatility60 = max(float(item["volatility60"]), 0.001)
    rs20 = ret20 - market_ret20
    rs60 = ret60 - market_ret60
    if source_id == "h10_sector_rs_new_high_volume_v1":
        return (
            _percentile_value([industry_returns20.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
            + _percentile_value([industry_returns60.get(str(row["industry"]), 0.0) for row in pool], industry_ret60)
            + _percentile_by(pool, "return_60d", item)
            + min(float(item["amount_ratio20"]) / 3.0, 1.5)
            + float(item["close_position"])
        )
    if source_id == "h10_market_thrust_top_rs_v1":
        return rs60 + rs20 + breadth10 + _percentile_by(pool, "return_20d", item) + float(item["close_position"])
    if source_id == "h10_first_pullback_after_sector_breakout_v1":
        return (
            _percentile_value([industry_returns20.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
            + rs60
            + _target_pullback_score(float(item["drawdown20"]), target=-0.04, width=0.08)
            + _inverse_percentile_by(pool, "amount_ratio20", item)
        )
    if source_id == "h10_volume_acceleration_continuation_v1":
        return (
            ret20
            + 0.5 * float(item["return_10d"])
            + min(float(item["amount_ratio5"]) / 2.0, 1.5)
            + float(item["close_position"])
        )
    if source_id == "h10_limit_up_absorption_followthrough_v1":
        return (
            float(item["previous_return_1d"])
            + max(float(item["return_1d"]), 0.0)
            + min(float(item["amount_ratio20"]) / 3.0, 1.5)
            + float(item["close_position"])
        )
    if source_id == "h10_gap_strength_followthrough_v1":
        return (
            min(float(item["open_gap"]) * 10.0, 1.0)
            + float(item["close_position"])
            + rs20
            + _percentile_value([industry_returns20.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
        )
    if source_id == "uptrend_red_day_pullback_index_gated_h10_v2":
        return ret20 + 0.5 * ret60 + _target_pullback_score(float(item["drawdown20"]), target=-0.035, width=0.08)
    if source_id == "ma_acceleration_momentum_h10_v2":
        return (
            ret20 / volatility20
            + 0.5 * ret60 / volatility60
            + float(item["ma20_slope"]) * 10.0
            + _percentile_by(pool, "return_20d", item)
        )
    return 0.0


def _target_pullback_score(value: float, *, target: float, width: float) -> float:
    if width <= 0.0:
        return 0.0
    return max(0.0, 1.0 - abs(value - target) / width)


def _build_h10_ma_accel_batch_selections(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    source_ids: tuple[str, ...],
    regime_features: dict[date, dict[str, float]],
    pool_limit: int,
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    selections_by_source: dict[str, dict[date, list[str]]] = {source_id: {} for source_id in source_ids}
    for signal_day in signal_days:
        contexts = _next_round_contexts(series_by_symbol, signal_day)
        industry_returns20 = _industry_return_map(contexts, "return_20d")
        industry_returns60 = _industry_return_map(contexts, "return_60d")
        index_context = (
            _next_round_context(series_by_symbol["000300.SH"], signal_day)
            if "000300.SH" in series_by_symbol
            else None
        )
        market_ret20 = float(index_context.get("return_20d") or 0.0) if index_context else 0.0
        market_ret60 = float(index_context.get("return_60d") or 0.0) if index_context else 0.0
        features = regime_features.get(signal_day) or {}
        for source_id in source_ids:
            ranked = _rank_h10_ma_accel_contexts(
                contexts,
                source_id=source_id,
                regime_features=features,
                industry_returns20=industry_returns20,
                industry_returns60=industry_returns60,
                market_ret20=market_ret20,
                market_ret60=market_ret60,
                pool_limit=pool_limit,
            )
            selections_by_source[source_id][signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections_by_source


def _rank_h10_ma_accel_contexts(
    contexts: list[dict[str, Any]],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns20: dict[str, float],
    industry_returns60: dict[str, float],
    market_ret20: float,
    market_ret60: float,
    pool_limit: int,
) -> list[dict[str, Any]]:
    pool = sorted(
        contexts,
        key=lambda item: (float(item["amount"]), float(item["return_20d"])),
        reverse=True,
    )[: max(pool_limit, 260)]
    candidates = [
        item
        for item in pool
        if _h10_ma_accel_candidate_allows(
            item,
            source_id=source_id,
            regime_features=regime_features,
            industry_returns20=industry_returns20,
            industry_returns60=industry_returns60,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        )
    ]
    ranked = sorted(
        candidates,
        key=lambda item: _h10_ma_accel_score(
            pool,
            item,
            source_id=source_id,
            regime_features=regime_features,
            industry_returns20=industry_returns20,
            industry_returns60=industry_returns60,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        ),
        reverse=True,
    )
    if source_id in {"ma_accel_sector_tailwind_h10_v3", "ma_accel_industry_leader_h10_v5"}:
        ranked = _dedupe_industry(ranked, max_per_industry=2)
    return ranked


def _h10_ma_accel_candidate_allows(
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns20: dict[str, float],
    industry_returns60: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> bool:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    universe_ret10_mean = float(regime_features.get("universe_ret10_mean", 0.0))
    pool_ret1_mean = float(regime_features.get("pool_ret1_mean", 0.0))
    pool_ret10_mean = float(regime_features.get("pool_ret10_mean", 0.0))
    close = float(item["close"])
    ma20 = float(item["ma20"] or 0.0)
    ma60 = float(item["ma60"] or 0.0)
    ma120 = float(item["ma120"] or 0.0)
    ret1 = float(item["return_1d"])
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    drawdown20 = float(item["drawdown20"])
    volatility20 = float(item["volatility20"])
    volatility60 = float(item["volatility60"])
    amount_ratio5 = float(item.get("amount_ratio5") or 0.0)
    amount_ratio20 = float(item["amount_ratio20"])
    amount_ratio60 = float(item.get("amount_ratio60") or 0.0)
    turnover = float(item["turnover_rate"])
    ma20_slope = float(item["ma20_slope"])
    ma20_slope_5d = float(item.get("ma20_slope_5d") or 0.0)
    ma20_slope_5d_prev = float(item.get("ma20_slope_5d_prev") or 0.0)
    ma50_slope = float(item["ma50_slope"])
    close_position = float(item.get("close_position") or 0.0)
    close_position_ma5 = float(item.get("close_position_ma5") or 0.0)
    range20 = float(item.get("range20") or 0.0)
    range60 = float(item.get("range60") or 0.0)
    low = float(item.get("low") or close)
    open_gap = float(item.get("open_gap") or 0.0)
    previous_return_1d = float(item.get("previous_return_1d") or 0.0)
    industry = str(item["industry"])
    industry_ret20 = industry_returns20.get(industry, 0.0)
    industry_ret60 = industry_returns60.get(industry, 0.0)
    if (
        ret1 >= 0.095
        or close <= 0.0
        or ma20 <= 0.0
        or ma60 <= 0.0
        or volatility60 <= 0.0
        or float(item["amount"]) < 5_000_000.0
    ):
        return False
    trend_base_allows = (
        breadth10 >= 0.45
        and market_ret20 >= -0.06
        and close > ma20 > ma60
        and ret20 >= 0.04
        and ret60 > 0.0
        and drawdown20 > -0.13
        and volatility20 <= volatility60 * 1.25
        and ma20_slope > 0.0
        and ma20_slope >= ma50_slope * 1.02
        and turnover <= 4.50
    )
    seed_base_allows = (
        trend_base_allows
        and -0.02 <= ret1 < 0.08
        and 1.00 <= amount_ratio20 <= 3.50
        and close_position >= 0.50
    )
    if source_id == "ma_accel_momentum_loose_vol_h10_v3":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.06
            and close > ma20 > ma60 > ma120
            and ret20 >= 0.04
            and ret60 > 0.0
            and ret1 < 0.08
            and drawdown20 > -0.15
            and volatility20 <= volatility60 * 1.30
            and ma20_slope > 0.0
            and ma50_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and turnover <= 5.0
        )
    if source_id == "ma_accel_dense_rank_h10_v3":
        return (
            breadth10 >= 0.40
            and market_ret20 >= -0.08
            and close > ma20 > ma60
            and ret20 >= 0.03
            and ret60 > -0.02
            and ret1 < 0.08
            and drawdown20 > -0.15
            and volatility20 <= volatility60 * 1.35
            and ma20_slope > 0.0
            and ma50_slope >= -0.005
            and 0.70 <= amount_ratio20 <= 4.50
            and turnover <= 5.50
        )
    if source_id == "ma_accel_red_day_entry_h10_v3":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.06
            and close > ma20 * 0.98
            and ma20 > ma60
            and ret20 >= 0.04
            and ret60 > 0.0
            and -0.03 <= ret1 <= 0.0
            and drawdown20 > -0.12
            and volatility20 <= volatility60 * 1.25
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and turnover <= 4.0
        )
    if source_id == "ma_accel_sector_tailwind_h10_v3":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.06
            and close > ma20 > ma60
            and ret20 >= 0.05
            and ret60 > 0.0
            and ret1 < 0.08
            and drawdown20 > -0.13
            and volatility20 <= volatility60 * 1.25
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and industry_ret20 >= market_ret20 + 0.02
            and industry_ret60 >= market_ret60
            and turnover <= 4.50
        )
    if source_id == "ma_accel_volume_confirm_h10_v3":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.06
            and close > ma20 > ma60
            and ret20 >= 0.04
            and ret60 > 0.0
            and -0.02 <= ret1 < 0.08
            and drawdown20 > -0.13
            and volatility20 <= volatility60 * 1.25
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and 1.00 <= amount_ratio20 <= 3.50
            and float(item["close_position"]) >= 0.50
            and turnover <= 4.50
        )
    if source_id in {"ma_accel_volume_confirm_seed_h10_v4", "ma_accel_volume_confirm_exit_seed_h10_v1"}:
        return seed_base_allows
    if source_id == "ma_accel_quality_rerank_h10_v5":
        return seed_base_allows
    if source_id == "ma_accel_regime_fill_h10_v5":
        return (
            breadth10 >= 0.58
            and pool_ret10_mean >= 0.04
            and pool_ret1_mean <= 0.08
            and universe_ret10_mean >= 0.0
            and market_ret20 >= -0.02
            and close > ma20 > ma60
            and 0.03 <= ret20 <= 0.14
            and ret60 > market_ret60
            and ret1 < 0.06
            and drawdown20 > -0.10
            and volatility20 <= volatility60 * 1.15
            and ma20_slope > 0.0
            and ma50_slope >= -0.003
            and 0.80 <= amount_ratio20 <= 2.80
            and turnover <= 3.50
        )
    if source_id == "ma_accel_early_inflection_h10_v5":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.05
            and close > ma20 * 0.99
            and ma20 > ma60 * 0.995
            and 0.015 <= ret20 <= 0.08
            and ret60 > -0.02
            and -0.015 <= ret1 <= 0.04
            and -0.10 <= drawdown20 <= -0.01
            and volatility20 <= volatility60 * 1.15
            and ma20_slope > 0.0
            and ma50_slope >= -0.003
            and 0.90 <= amount_ratio20 <= 2.50
            and turnover <= 4.0
        )
    if source_id == "ma_accel_vol_squeeze_breakout_h10_v5":
        return (
            seed_base_allows
            and volatility20 >= volatility60 * 0.45
            and volatility20 <= volatility60 * 0.95
            and range60 > 0.0
            and range20 <= range60 * 0.92
        )
    if source_id == "ma_accel_volume_convergence_h10_v5":
        amount_ratio_sync = _safe_ratio(amount_ratio5, amount_ratio20)
        return (
            seed_base_allows
            and amount_ratio5 >= 1.05
            and amount_ratio20 >= 1.10
            and amount_ratio60 >= 0.95
            and 0.65 <= amount_ratio_sync <= 1.75
        )
    if source_id == "ma_accel_industry_leader_h10_v5":
        return (
            seed_base_allows
            and industry_ret20 >= market_ret20 + 0.02
            and industry_ret60 >= market_ret60
            and ret20 >= industry_ret20 + 0.03
            and ret60 >= industry_ret60 + 0.02
        )
    if source_id == "ma_accel_pullback_vol_calibrated_h10_v5":
        return (
            trend_base_allows
            and -0.04 <= ret1 <= 0.025
            and close >= ma20 * 0.97
            and low <= ma20 * 1.015
            and close_position >= 0.55
            and abs(drawdown20) <= volatility20 * 3.20
            and 0.80 <= amount_ratio20 <= 3.50
            and amount_ratio5 <= 2.50
        )
    if source_id == "ma_accel_range_contraction_h10_v5":
        return (
            seed_base_allows
            and range60 > 0.0
            and range20 <= range60 * 0.90
            and close_position >= 0.60
            and close_position_ma5 >= 0.55
            and amount_ratio20 >= 1.00
        )
    if source_id == "ma_accel_slope_acceleration_h10_v5":
        return (
            seed_base_allows
            and ma20_slope_5d > 0.0
            and ma20_slope_5d_prev > 0.0
            and ma20_slope_5d >= ma20_slope_5d_prev * 1.03
        )
    if source_id == "ma_accel_gap_hold_h10_v5":
        return (
            trend_base_allows
            and previous_return_1d >= 0.06
            and open_gap >= 0.005
            and -0.02 <= ret1 <= 0.05
            and close_position >= 0.60
            and amount_ratio20 >= 1.00
        )
    if source_id == "ma_accel_volume_confirm_dense_guard_h10_v4":
        return (
            breadth10 >= 0.42
            and market_ret20 >= -0.06
            and close > ma20 > ma60
            and ret20 >= 0.035
            and ret60 > 0.0
            and -0.02 <= ret1 < 0.08
            and drawdown20 > -0.14
            and volatility20 <= volatility60 * 1.28
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.01
            and 0.90 <= amount_ratio20 <= 3.80
            and float(item["close_position"]) >= 0.48
            and turnover <= 4.80
        )
    if source_id == "ma_accel_volume_confirm_quality_h10_v4":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.06
            and close > ma20 > ma60
            and ret20 >= 0.05
            and ret60 > 0.02
            and -0.01 <= ret1 < 0.06
            and drawdown20 > -0.12
            and volatility20 <= volatility60 * 1.20
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.03
            and 1.10 <= amount_ratio20 <= 3.20
            and float(item["close_position"]) >= 0.60
            and turnover <= 4.20
        )
    if source_id == "ma_accel_volume_confirm_market_gated_h10_v4":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.03
            and close > ma20 > ma60
            and ret20 >= 0.04
            and ret60 > 0.0
            and -0.02 <= ret1 < 0.08
            and drawdown20 > -0.13
            and volatility20 <= volatility60 * 1.25
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and 1.00 <= amount_ratio20 <= 3.50
            and float(item["close_position"]) >= 0.50
            and turnover <= 4.50
        )
    if source_id == "ma_accel_volume_confirm_rs_weighted_h10_v4":
        return (
            breadth10 >= 0.42
            and market_ret20 >= -0.06
            and close > ma20 > ma60
            and ret20 >= 0.04
            and ret60 > 0.0
            and ret20 - market_ret20 >= 0.05
            and ret60 - market_ret60 >= 0.03
            and -0.02 <= ret1 < 0.08
            and drawdown20 > -0.13
            and volatility20 <= volatility60 * 1.25
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and 1.00 <= amount_ratio20 <= 3.50
            and float(item["close_position"]) >= 0.50
            and turnover <= 4.50
        )
    if source_id == "ma_accel_volume_confirm_pullback_band_h10_v4":
        return (
            breadth10 >= 0.45
            and market_ret20 >= -0.06
            and close > ma20 * 0.99
            and ma20 > ma60
            and ret20 >= 0.04
            and ret60 > 0.0
            and -0.025 <= ret1 <= 0.025
            and drawdown20 > -0.12
            and volatility20 <= volatility60 * 1.25
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.02
            and 1.00 <= amount_ratio20 <= 3.50
            and float(item["close_position"]) >= 0.45
            and turnover <= 4.50
        )
    if source_id == "ma_accel_low_breadth_contrarian_h10_v3":
        return (
            0.40 <= breadth10 <= 0.58
            and market_ret20 >= -0.03
            and close > ma20 > ma60
            and ret20 >= 0.06
            and ret60 > 0.0
            and ret1 < 0.06
            and drawdown20 > -0.10
            and volatility20 <= volatility60 * 1.20
            and ma20_slope > 0.0
            and ma20_slope >= ma50_slope * 1.05
            and turnover <= 4.0
        )
    return False


def _h10_ma_accel_score(
    pool: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
    industry_returns20: dict[str, float],
    industry_returns60: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> float:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    industry = str(item["industry"])
    industry_ret20 = industry_returns20.get(industry, 0.0)
    industry_ret60 = industry_returns60.get(industry, 0.0)
    ret1 = float(item.get("return_1d") or 0.0)
    ret20 = float(item.get("return_20d") or 0.0)
    ret60 = float(item.get("return_60d") or 0.0)
    base_score = _base_ma_accel_score(pool, item, market_ret20=market_ret20, market_ret60=market_ret60)
    amount_ratio5 = float(item.get("amount_ratio5") or 0.0)
    amount_ratio20 = float(item.get("amount_ratio20") or 0.0)
    amount_ratio60 = float(item.get("amount_ratio60") or 0.0)
    close_position = float(item.get("close_position") or 0.0)
    close_position_ma5 = float(item.get("close_position_ma5") or 0.0)
    range20 = max(float(item.get("range20") or 0.0), 0.001)
    range60 = max(float(item.get("range60") or 0.0), 0.001)
    volatility20 = max(float(item.get("volatility20") or 0.0), 0.001)
    volatility60 = max(float(item.get("volatility60") or 0.0), 0.001)
    ma20 = max(float(item.get("ma20") or 0.0), 0.001)
    close = float(item.get("close") or 0.0)
    ma20_slope_5d = float(item.get("ma20_slope_5d") or 0.0)
    ma20_slope_5d_prev = float(item.get("ma20_slope_5d_prev") or 0.0)
    open_gap = float(item.get("open_gap") or 0.0)
    if source_id == "ma_accel_momentum_loose_vol_h10_v3":
        return base_score + _percentile_by(pool, "drawdown20", item)
    if source_id == "ma_accel_dense_rank_h10_v3":
        return base_score + 0.5 * breadth10 + _percentile_by(pool, "drawdown20", item)
    if source_id == "ma_accel_red_day_entry_h10_v3":
        return base_score + _inverse_percentile_by(pool, "return_1d", item) + _percentile_by(pool, "drawdown20", item)
    if source_id == "ma_accel_sector_tailwind_h10_v3":
        return (
            base_score
            + _percentile_value([industry_returns20.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
            + _percentile_value([industry_returns60.get(str(row["industry"]), 0.0) for row in pool], industry_ret60)
        )
    if source_id == "ma_accel_volume_confirm_h10_v3":
        return base_score + min(float(item["amount_ratio20"]) / 2.5, 1.2) + float(item["close_position"])
    if source_id in {"ma_accel_volume_confirm_seed_h10_v4", "ma_accel_volume_confirm_exit_seed_h10_v1"}:
        return base_score + min(float(item["amount_ratio20"]) / 2.5, 1.2) + float(item["close_position"])
    if source_id == "ma_accel_quality_rerank_h10_v5":
        overheat_penalty = 0.0
        overheat_penalty += max(close / ma20 - 1.12, 0.0) * 4.0
        overheat_penalty += max(ret20 - 0.18, 0.0) * 3.0
        overheat_penalty += max(amount_ratio20 - 2.8, 0.0) * 0.25
        overheat_penalty += max(ret1 - 0.06, 0.0) * 4.0
        volume_target = _target_pullback_score(amount_ratio20, target=1.8, width=1.0)
        return base_score + volume_target + close_position + _inverse_percentile_by(pool, "return_1d", item) - overheat_penalty
    if source_id == "ma_accel_regime_fill_h10_v5":
        return (
            ret20 / volatility20
            + 0.5 * max(ret60 - market_ret60, 0.0)
            + _inverse_percentile_by(pool, "turnover_rate", item)
            + _inverse_percentile_by(pool, "return_1d", item)
            + close_position
        )
    if source_id == "ma_accel_early_inflection_h10_v5":
        return (
            min(float(item.get("ma20_slope") or 0.0) * 20.0, 1.5)
            + _target_pullback_score(float(item["drawdown20"]), target=-0.045, width=0.08)
            + _inverse_percentile_by(pool, "return_1d", item)
            + _inverse_percentile_by(pool, "volatility20", item)
        )
    if source_id == "ma_accel_vol_squeeze_breakout_h10_v5":
        squeeze_bonus = max(0.0, 1.0 - volatility20 / volatility60)
        range_bonus = max(0.0, 1.0 - range20 / range60)
        return base_score + 2.0 * squeeze_bonus + range_bonus + close_position
    if source_id == "ma_accel_volume_convergence_h10_v5":
        volume_floor = min(amount_ratio5, amount_ratio20, amount_ratio60)
        amount_sync = 1.0 - min(abs(amount_ratio5 - amount_ratio20) / max(amount_ratio5, amount_ratio20, 0.001), 1.0)
        return base_score + min(volume_floor / 2.8, 1.2) + amount_sync + close_position
    if source_id == "ma_accel_industry_leader_h10_v5":
        relative_rows20 = [
            float(row.get("return_20d") or 0.0) - industry_returns20.get(str(row.get("industry")), 0.0)
            for row in pool
        ]
        relative_rows60 = [
            float(row.get("return_60d") or 0.0) - industry_returns60.get(str(row.get("industry")), 0.0)
            for row in pool
        ]
        relative20 = ret20 - industry_ret20
        relative60 = ret60 - industry_ret60
        return base_score + _percentile_value(relative_rows20, relative20) + 0.5 * _percentile_value(
            relative_rows60, relative60
        )
    if source_id == "ma_accel_pullback_vol_calibrated_h10_v5":
        ma20_proximity = max(0.0, 1.0 - abs(close / ma20 - 1.0) / 0.035)
        drawdown_fit = max(0.0, 1.0 - abs(float(item["drawdown20"])) / max(volatility20 * 3.2, 0.001))
        return base_score + ma20_proximity + 0.5 * close_position + 0.5 * drawdown_fit
    if source_id == "ma_accel_range_contraction_h10_v5":
        range_compression = max(0.0, 1.0 - range20 / range60)
        return base_score + 1.5 * range_compression + close_position + 0.5 * close_position_ma5
    if source_id == "ma_accel_slope_acceleration_h10_v5":
        slope_delta = max(ma20_slope_5d - ma20_slope_5d_prev, 0.0)
        return base_score + min(slope_delta * 20.0, 1.5) + _percentile_by(pool, "ma20_slope_5d", item)
    if source_id == "ma_accel_gap_hold_h10_v5":
        return base_score + min(open_gap * 8.0, 1.5) + close_position + min(amount_ratio20 / 2.5, 1.2)
    if source_id == "ma_accel_volume_confirm_dense_guard_h10_v4":
        return (
            base_score
            + min(float(item["amount_ratio20"]) / 2.8, 1.2)
            + float(item["close_position"])
            + _percentile_by(pool, "drawdown20", item)
        )
    if source_id == "ma_accel_volume_confirm_quality_h10_v4":
        return (
            base_score
            + min(float(item["amount_ratio20"]) / 2.2, 1.2)
            + 1.2 * float(item["close_position"])
            + _percentile_by(pool, "return_20d", item)
        )
    if source_id == "ma_accel_volume_confirm_market_gated_h10_v4":
        return base_score + min(float(item["amount_ratio20"]) / 2.5, 1.2) + float(item["close_position"])
    if source_id == "ma_accel_volume_confirm_rs_weighted_h10_v4":
        return (
            base_score
            + min(float(item["amount_ratio20"]) / 2.5, 1.2)
            + float(item["close_position"])
            + max(float(item["return_20d"]) - market_ret20, 0.0)
            + 0.5 * max(float(item["return_60d"]) - market_ret60, 0.0)
        )
    if source_id == "ma_accel_volume_confirm_pullback_band_h10_v4":
        return (
            base_score
            + min(float(item["amount_ratio20"]) / 2.5, 1.2)
            + _inverse_percentile_by(pool, "return_1d", item)
            + _percentile_by(pool, "drawdown20", item)
        )
    if source_id == "ma_accel_low_breadth_contrarian_h10_v3":
        return (
            base_score
            + _percentile_by(pool, "drawdown20", item)
            + max(float(item["return_20d"]) - market_ret20, 0.0)
        )
    return base_score


def _base_ma_accel_score(
    pool: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    market_ret20: float,
    market_ret60: float,
) -> float:
    volatility20 = max(float(item["volatility20"]), 0.001)
    volatility60 = max(float(item["volatility60"]), 0.001)
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    return (
        ret20 / volatility20
        + 0.5 * ret60 / volatility60
        + max(ret20 - market_ret20, 0.0)
        + 0.5 * max(ret60 - market_ret60, 0.0)
        + float(item["ma20_slope"]) * 10.0
        + _percentile_by(pool, "return_20d", item)
    )


def _build_next_round_batch_selections(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    source_ids: tuple[str, ...],
    pool_limit: int,
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    selections_by_source: dict[str, dict[date, list[str]]] = {source_id: {} for source_id in source_ids}
    for signal_day in signal_days:
        contexts = _next_round_contexts(series_by_symbol, signal_day)
        industry_returns = _industry_return_map(contexts, "return_20d")
        index_context = (
            _next_round_context(series_by_symbol["000300.SH"], signal_day)
            if "000300.SH" in series_by_symbol
            else None
        )
        market_ret20 = float(index_context.get("return_20d") or 0.0) if index_context else 0.0
        market_ret60 = float(index_context.get("return_60d") or 0.0) if index_context else 0.0
        for source_id in source_ids:
            ranked = _rank_next_round_contexts(
                contexts,
                source_id=source_id,
                industry_returns=industry_returns,
                market_ret20=market_ret20,
                market_ret60=market_ret60,
                pool_limit=pool_limit,
            )
            selections_by_source[source_id][signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections_by_source


def _build_refined_round_batch_selections(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    source_ids: tuple[str, ...],
    control_selections: dict[date, list[str]],
    regime_features: dict[date, dict[str, float]],
    pool_limit: int,
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    selections_by_source: dict[str, dict[date, list[str]]] = {source_id: {} for source_id in source_ids}
    for signal_day in signal_days:
        contexts = _next_round_contexts(series_by_symbol, signal_day)
        context_by_symbol = {str(context["symbol"]): context for context in contexts}
        control_symbols = [symbol for symbol in control_selections.get(signal_day, []) if symbol in context_by_symbol]
        features = regime_features.get(signal_day) or {}
        for source_id in source_ids:
            ranked = _rank_refined_round_contexts(
                contexts,
                context_by_symbol=context_by_symbol,
                control_symbols=control_symbols,
                source_id=source_id,
                regime_features=features,
                pool_limit=pool_limit,
            )
            selections_by_source[source_id][signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections_by_source


def _rank_refined_round_contexts(
    contexts: list[dict[str, Any]],
    *,
    context_by_symbol: dict[str, dict[str, Any]],
    control_symbols: list[str],
    source_id: str,
    regime_features: dict[str, float],
    pool_limit: int,
) -> list[dict[str, Any]]:
    if source_id == "low_turnover_rank2_breadth65_v2":
        pool = [context_by_symbol[symbol] for symbol in control_symbols[1:]]
    elif source_id in {
        "low_turnover_breadth65_v2",
        "low_turnover_momentum15_v2",
        "low_turnover_red_day_momentum_v2",
        "low_turnover_high_price_momentum_v2",
    }:
        pool = [context_by_symbol[symbol] for symbol in control_symbols]
    else:
        pool = sorted(
            contexts,
            key=lambda item: (float(item["amount"]), float(item["return_20d"])),
            reverse=True,
        )[: max(pool_limit, 120)]
    candidates = [
        item
        for item in pool
        if _refined_round_candidate_allows(item, source_id=source_id, regime_features=regime_features)
    ]
    return sorted(
        candidates,
        key=lambda item: _refined_round_score(pool, item, source_id=source_id, regime_features=regime_features),
        reverse=True,
    )


def _refined_round_candidate_allows(
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
) -> bool:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    close = float(item["close"])
    ret1 = float(item["return_1d"])
    ret10 = float(item["return_10d"])
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    turnover = float(item["turnover_rate"])
    ma20 = float(item["ma20"] or 0.0)
    ma50 = float(item["ma50"] or 0.0)
    ma60 = float(item["ma60"] or 0.0)
    ma120 = float(item["ma120"] or 0.0)
    volatility20 = float(item["volatility20"])
    volatility60 = float(item["volatility60"])
    if ret1 >= 0.095:
        return False
    if source_id == "low_turnover_breadth65_v2":
        return breadth10 >= 0.65
    if source_id == "low_turnover_rank2_breadth65_v2":
        return breadth10 >= 0.65 and ret1 < 0.05
    if source_id == "low_turnover_momentum15_v2":
        return breadth10 >= 0.55 and ret10 >= 0.10 and ret20 >= 0.15 and ret1 < 0.05
    if source_id == "low_turnover_red_day_momentum_v2":
        return breadth10 >= 0.55 and ret1 < 0.0 and ret10 >= 0.10 and ret20 >= 0.15
    if source_id == "low_turnover_high_price_momentum_v2":
        return breadth10 >= 0.55 and close >= 50.0 and ret10 >= 0.10 and ret20 >= 0.15 and ret1 < 0.05
    if source_id == "low_turnover_ma_acceleration_v2":
        return (
            breadth10 >= 0.55
            and turnover <= 1.0
            and close > ma20 > ma60 > ma120
            and ret20 >= 0.08
            and ret60 > 0.0
            and float(item["ma20_slope"]) > 0.0
            and float(item["ma50_slope"]) > 0.0
            and float(item["ma20_slope"]) >= float(item["ma50_slope"]) * 1.1
            and volatility20 <= volatility60 * 1.1
        )
    if source_id == "low_turnover_vol_adjusted_v2":
        return (
            breadth10 >= 0.55
            and turnover <= 1.0
            and close > ma50
            and ret20 >= 0.05
            and ret60 > 0.0
            and float(item["drawdown20"]) > -0.10
            and volatility60 > 0.0
            and volatility20 <= volatility60 * 1.15
        )
    return False


def _refined_round_score(
    pool: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    source_id: str,
    regime_features: dict[str, float],
) -> float:
    breadth10 = float(regime_features.get("universe_breadth10", 0.0))
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    turnover = float(item["turnover_rate"])
    volatility60 = max(float(item["volatility60"]), 0.001)
    if source_id == "low_turnover_breadth65_v2":
        return _percentile_by(pool, "return_20d", item) + 0.5 * _percentile_by(pool, "return_10d", item) + breadth10
    if source_id == "low_turnover_rank2_breadth65_v2":
        return _percentile_by(pool, "return_20d", item) + _inverse_percentile_by(pool, "return_1d", item) + breadth10
    if source_id == "low_turnover_momentum15_v2":
        return ret20 + 0.5 * ret60 + _inverse_percentile_by(pool, "return_1d", item)
    if source_id == "low_turnover_red_day_momentum_v2":
        return ret20 + 0.5 * ret60 + _inverse_percentile_by(pool, "return_1d", item)
    if source_id == "low_turnover_high_price_momentum_v2":
        return ret20 + 0.5 * ret60 + _percentile_by(pool, "close", item)
    if source_id == "low_turnover_ma_acceleration_v2":
        return (
            _percentile_by(pool, "return_20d", item)
            + _percentile_by(pool, "ma20_slope", item)
            + _inverse_percentile_by(pool, "volatility20", item)
        )
    if source_id == "low_turnover_vol_adjusted_v2":
        return ret60 / volatility60 + 0.5 * ret20 + (1.0 - min(turnover, 1.0))
    return 0.0


def _next_round_contexts(series_by_symbol: dict[str, Any], signal_day: date) -> list[dict[str, Any]]:
    return [
        context
        for symbol, series in series_by_symbol.items()
        if symbol not in INDEX_SYMBOLS
        for context in [_next_round_context(series, signal_day)]
        if context is not None
    ]


def _next_round_context(series: Any, signal_day: date) -> dict[str, Any] | None:
    index = series.by_day.get(signal_day)
    if index is None or index < 120 or index + 2 >= len(series.bars):
        return None
    latest = series.bars[index]
    previous = series.bars[index - 1]
    if latest.close <= 0 or previous.close <= 0 or latest.amount <= 0:
        return None
    window_bars = series.bars[max(0, index - 120) : index + 1]
    closes = [float(bar.close) for bar in window_bars]
    highs = [float(bar.high) for bar in window_bars]
    lows = [float(bar.low) for bar in window_bars]
    amounts = [float(bar.amount or 0.0) for bar in window_bars]
    ranges = [
        (float(bar.high) - float(bar.low)) / float(bar.close)
        for bar in window_bars
        if float(bar.close) > 0
    ]
    ma20 = _mean_window(closes, 20)
    ma30 = _mean_window(closes, 30)
    ma50 = _mean_window(closes, 50)
    ma60 = _mean_window(closes, 60)
    ma120 = _mean_window(closes, 120)
    window_index = len(closes) - 1
    ma20_prev = _mean_at(closes, window_index - 1, 20)
    ma20_prev5 = _mean_at(closes, window_index - 5, 20)
    ma20_prev10 = _mean_at(closes, window_index - 10, 20)
    ma50_prev = _mean_at(closes, window_index - 5, 50)
    amount_ma5 = _mean_window(amounts, 5)
    amount_ma20 = _mean_window(amounts, 20)
    amount_ma60 = _mean_window(amounts, 60)
    high20 = max(highs[-20:])
    high60 = max(highs[-60:])
    high20_prev = max(highs[-21:-1])
    low10 = min(lows[-10:])
    low20 = min(lows[-20:])
    low60 = min(lows[-60:])
    range20 = _mean_window(ranges, 20)
    range60 = _mean_window(ranges, 60)
    return_1d = latest.close / previous.close - 1.0
    close_positions = [_close_position(bar.low, bar.high, bar.close) for bar in window_bars]
    ma20_slope_5d = 0.0 if ma20_prev5 is None or ma20 is None else ma20 / ma20_prev5 - 1.0
    ma20_slope_5d_prev = (
        0.0 if ma20_prev10 is None or ma20_prev5 is None else ma20_prev5 / ma20_prev10 - 1.0
    )
    return {
        "symbol": series.symbol,
        "industry": series.industry,
        "open": latest.open,
        "high": latest.high,
        "low": latest.low,
        "close": latest.close,
        "open_gap": latest.open / previous.close - 1.0 if previous.close > 0 else 0.0,
        "return_1d": return_1d,
        "return_3d": _return_window(closes, 3),
        "return_5d": _return_window(closes, 5),
        "return_10d": _return_window(closes, 10),
        "return_20d": _return_window(closes, 20),
        "return_60d": _return_window(closes, 60),
        "return_120d": _return_window(closes, 120),
        "ma20": ma20,
        "ma30": ma30,
        "ma50": ma50,
        "ma60": ma60,
        "ma120": ma120,
        "ma20_slope": 0.0 if ma20_prev is None or ma20 is None else ma20 / ma20_prev - 1.0,
        "ma20_slope_5d": ma20_slope_5d,
        "ma20_slope_5d_prev": ma20_slope_5d_prev,
        "ma50_slope": 0.0 if ma50_prev is None or ma50 is None else ma50 / ma50_prev - 1.0,
        "high20": high20,
        "high60": high60,
        "high20_prev": high20_prev,
        "low10": low10,
        "low20": low20,
        "low60": low60,
        "drawdown20": latest.close / high20 - 1.0 if high20 else 0.0,
        "drawdown60": latest.close / high60 - 1.0 if high60 else 0.0,
        "range20": range20,
        "range60": range60,
        "volatility20": _return_stddev(closes, 20),
        "volatility60": _return_stddev(closes, 60),
        "amount": latest.amount,
        "amount_ratio5": _safe_ratio(latest.amount, amount_ma5),
        "amount_ratio20": _safe_ratio(latest.amount, amount_ma20),
        "amount_ratio60": _safe_ratio(latest.amount, amount_ma60),
        "turnover_rate": latest.turnover or 0.0,
        "close_position": _close_position(latest.low, latest.high, latest.close),
        "close_position_ma5": _mean_window(close_positions, 5) or 0.0,
        "previous_return_1d": (
            previous.close / series.bars[index - 2].close - 1.0
            if index >= 2 and series.bars[index - 2].close
            else 0.0
        ),
    }


def _rank_next_round_contexts(
    contexts: list[dict[str, Any]],
    *,
    source_id: str,
    industry_returns: dict[str, float],
    market_ret20: float,
    market_ret60: float,
    pool_limit: int,
) -> list[dict[str, Any]]:
    pool = sorted(contexts, key=lambda item: (float(item["amount"]), float(item["return_20d"])), reverse=True)[
        : max(pool_limit, 120)
    ]
    candidates = [
        item
        for item in pool
        if _next_round_candidate_allows(
            item,
            source_id=source_id,
            industry_returns=industry_returns,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        )
    ]
    return sorted(
        candidates,
        key=lambda item: _next_round_score(
            pool,
            item,
            source_id=source_id,
            industry_returns=industry_returns,
            market_ret20=market_ret20,
            market_ret60=market_ret60,
        ),
        reverse=True,
    )


def _next_round_candidate_allows(
    item: dict[str, Any],
    *,
    source_id: str,
    industry_returns: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> bool:
    close = float(item["close"])
    ma20 = float(item["ma20"] or 0.0)
    ma30 = float(item["ma30"] or 0.0)
    ma50 = float(item["ma50"] or 0.0)
    ma60 = float(item["ma60"] or 0.0)
    ma120 = float(item["ma120"] or 0.0)
    ret1 = float(item["return_1d"])
    ret3 = float(item["return_3d"])
    ret5 = float(item["return_5d"])
    ret20 = float(item["return_20d"])
    ret60 = float(item["return_60d"])
    amount_ratio20 = float(item["amount_ratio20"])
    industry_ret20 = industry_returns.get(str(item["industry"]), 0.0)
    if ret1 >= 0.095:
        return False
    if source_id == "trend_low_vol_breakout_v1":
        return (
            close > ma60 > ma120
            and ret60 > max(0.04, market_ret60)
            and float(item["volatility20"]) <= float(item["volatility60"]) * 0.85
            and close >= float(item["high20_prev"]) * 1.005
            and 1.15 <= amount_ratio20 <= 4.5
            and 0.0 < ret1 < 0.08
        )
    if source_id == "leader_sector_pullback_v1":
        return (
            close > ma60
            and ret60 > market_ret60
            and industry_ret20 > market_ret20
            and -0.12 <= float(item["drawdown20"]) <= -0.015
            and close >= ma20 * 0.97
            and close <= ma30 * 1.08
            and ret1 > 0.0
            and amount_ratio20 <= 1.4
        )
    if source_id == "relative_strength_low_vol_v1":
        return (
            close > ma50
            and ret60 > market_ret60 + 0.03
            and float(item["return_120d"]) > 0.0
            and float(item["drawdown60"]) > -0.22
            and float(item["volatility20"]) <= float(item["volatility60"]) * 1.05
            and ret5 < 0.12
        )
    if source_id == "volume_absorption_breakout_v1":
        return (
            close > ma50
            and float(item["amount_ratio60"]) >= 2.2
            and float(item["range20"]) <= float(item["range60"]) * 0.9
            and float(item["close_position"]) >= 0.6
            and float(item["ma50_slope"]) >= -0.01
            and ret1 > -0.01
        )
    if source_id == "low_turnover_sector_excess_v1":
        return (
            close > ma20
            and ret20 > 0.0
            and ret60 > market_ret60
            and industry_ret20 > market_ret20
            and float(item["turnover_rate"]) <= 3.0
            and float(item["amount"]) >= 5_000_000.0
        )
    if source_id == "breakout_retest_confirm_v1":
        return (
            close > ma20 > ma60
            and -0.06 <= ret5 <= 0.08
            and close >= float(item["high20"]) * 0.94
            and float(item["low10"]) >= ma20 * 0.94
            and ret1 > 0.0
            and amount_ratio20 >= 1.05
        )
    if source_id == "limit_up_followthrough_v1":
        return (
            float(item["previous_return_1d"]) >= 0.093
            and -0.02 <= ret1 <= 0.08
            and close >= float(item["low"]) * 1.02
            and amount_ratio20 >= 1.2
            and ret3 < 0.28
        )
    return False


def _next_round_score(
    pool: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    source_id: str,
    industry_returns: dict[str, float],
    market_ret20: float,
    market_ret60: float,
) -> float:
    industry_ret20 = industry_returns.get(str(item["industry"]), 0.0)
    rs20 = float(item["return_20d"]) - market_ret20
    rs60 = float(item["return_60d"]) - market_ret60
    if source_id == "trend_low_vol_breakout_v1":
        return (
            _percentile_by(pool, "return_60d", item)
            + _inverse_percentile_by(pool, "volatility20", item)
            + min(float(item["amount_ratio20"]) / 3.0, 1.5)
            + rs60
        )
    if source_id == "leader_sector_pullback_v1":
        return (
            _percentile_value([industry_returns.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
            + _percentile_by(pool, "return_60d", item)
            + _inverse_percentile_by(pool, "drawdown20", item)
            + float(item["return_1d"])
        )
    if source_id == "relative_strength_low_vol_v1":
        return rs60 + 0.5 * rs20 + _inverse_percentile_by(pool, "volatility20", item)
    if source_id == "volume_absorption_breakout_v1":
        return (
            min(float(item["amount_ratio60"]) / 4.0, 2.0)
            + float(item["close_position"])
            + _inverse_percentile_by(pool, "range20", item)
            + max(float(item["return_20d"]), 0.0)
        )
    if source_id == "low_turnover_sector_excess_v1":
        return (
            rs60
            + 0.5 * rs20
            + _percentile_value([industry_returns.get(str(row["industry"]), 0.0) for row in pool], industry_ret20)
            + _inverse_percentile_by(pool, "turnover_rate", item)
        )
    if source_id == "breakout_retest_confirm_v1":
        return (
            _percentile_by(pool, "return_60d", item)
            + _inverse_percentile_by(pool, "drawdown20", item)
            + min(float(item["amount_ratio20"]) / 2.5, 1.2)
        )
    if source_id == "limit_up_followthrough_v1":
        return (
            min(float(item["amount_ratio20"]) / 3.0, 2.0)
            + float(item["previous_return_1d"])
            + float(item["return_1d"])
        )
    return 0.0


def _mean_window(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / float(window)


def _mean_at(values: list[float], index: int, window: int) -> float | None:
    if index - window + 1 < 0:
        return None
    subset = values[index - window + 1 : index + 1]
    return sum(subset) / float(window)


def _return_window(closes: list[float], window: int) -> float:
    if len(closes) <= window or closes[-window - 1] <= 0:
        return 0.0
    return closes[-1] / closes[-window - 1] - 1.0


def _return_stddev(closes: list[float], window: int) -> float:
    if len(closes) <= window:
        return 0.0
    returns = [
        closes[index] / closes[index - 1] - 1.0
        for index in range(len(closes) - window, len(closes))
        if closes[index - 1] > 0
    ]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    return sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))


def _safe_ratio(numerator: float | None, denominator: float | None) -> float:
    if denominator is None or denominator <= 0 or numerator is None:
        return 0.0
    return float(numerator) / float(denominator)


def _close_position(low: float, high: float, close: float) -> float:
    if high <= low:
        return 0.5
    return (close - low) / (high - low)


def _industry_return_map(contexts: list[dict[str, Any]], key: str) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for item in contexts:
        values.setdefault(str(item["industry"]), []).append(float(item.get(key) or 0.0))
    return {industry: sum(rows) / len(rows) for industry, rows in values.items() if rows}


def _percentile_by(pool: list[dict[str, Any]], key: str, item: dict[str, Any]) -> float:
    return _percentile_value([float(row.get(key) or 0.0) for row in pool], float(item.get(key) or 0.0))


def _inverse_percentile_by(pool: list[dict[str, Any]], key: str, item: dict[str, Any]) -> float:
    return 1.0 - _percentile_by(pool, key, item)


def _percentile_value(values: list[float], value: float) -> float:
    if len(values) <= 1:
        return 1.0
    ranked = sorted(values)
    lower_or_equal = sum(1 for candidate in ranked if candidate <= value)
    return (lower_or_equal - 1) / (len(ranked) - 1)


def _unique_by_config_id(rows: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        config_id = str(row.get("config_id") or "")
        if not config_id or config_id in seen:
            raise ValueError(f"duplicate or missing config_id in strategy search artifact: {config_id!r}")
        seen.add(config_id)
        output.append(row)
    return output


def _validate_merged_artifact(payload: dict[str, Any]) -> None:
    if payload.get("artifact_family") != SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY:
        raise ValueError("strategy search artifact must remain a shortpick_v2_replay_artifact")
    if payload.get("schema_version") != SHORTPICK_V2_REPLAY_SCHEMA_VERSION:
        raise ValueError("strategy search artifact must keep schema_version v1")
    result_ids = {str(row.get("config_id") or "") for row in payload.get("results") or []}
    missing_controls = [
        config.config_id for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS if config.config_id not in result_ids
    ]
    if missing_controls:
        raise ValueError(f"strategy search artifact is missing control configs: {missing_controls}")


def _validate_strategy_search_batch_horizon(*, candidate_batch: str, horizon_days: int) -> None:
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_QUIET and horizon_days != 10:
        raise ValueError("candidate_batch h10_quiet requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION and horizon_days != 10:
        raise ValueError("candidate_batch h10_quiet_champion requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_ROBUST and horizon_days != 10:
        raise ValueError("candidate_batch h10_robust requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_STRENGTH and horizon_days != 10:
        raise ValueError("candidate_batch h10_strength requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_MA_ACCEL and horizon_days != 10:
        raise ValueError("candidate_batch h10_ma_accel requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_MA_ACCEL_REFINE and horizon_days != 10:
        raise ValueError("candidate_batch h10_ma_accel_refine requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_EXIT and horizon_days != 10:
        raise ValueError("candidate_batch h10_exit requires horizon_days=10")
    if candidate_batch == STRATEGY_SEARCH_BATCH_H10_ENTRY_QUALITY and horizon_days != 10:
        raise ValueError("candidate_batch h10_entry_quality requires horizon_days=10")


def _strategy_search_artifact_id(
    generated_at: datetime,
    start_date: date,
    end_date: date,
    initial_cash: float,
    *,
    candidate_batch: str,
) -> str:
    generated_day = generated_at.date().isoformat()
    cash_text = str(int(initial_cash)) if float(initial_cash).is_integer() else str(initial_cash)
    batch_part = (
        "strategy_search"
        if candidate_batch == STRATEGY_SEARCH_BATCH_INITIAL
        else f"strategy_search_{candidate_batch}"
    )
    return (
        f"shortpick_v2_replay_artifact:{batch_part}:"
        f"{start_date.isoformat()}:{end_date.isoformat()}:{cash_text}:{generated_day}"
    )


def _strategy_search_source_ref(candidate_batch: str) -> str:
    if candidate_batch == STRATEGY_SEARCH_BATCH_INITIAL:
        return SHORTPICK_V2_STRATEGY_SEARCH_SOURCE_REF
    return f"{SHORTPICK_V2_STRATEGY_SEARCH_SOURCE_REF}:{candidate_batch}"
