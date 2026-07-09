from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

DEFAULT_INITIAL_CASH_CNY = 200_000.0
DEFAULT_BOARD_LOT_SIZE = 100
DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT = 0.25
DEFAULT_MAX_SINGLE_SYMBOL_COST_BASIS_PCT = 0.35
DEFAULT_MIN_ORDER_NOTIONAL_CNY = 4_000.0


def build_shortpick_v3_rolling_tranche_execution_contract(
    *,
    model_spec_id: str = "selected_exhaustion_date_scaled_v3_top3_20d_v1",
    initial_cash_cny: float = DEFAULT_INITIAL_CASH_CNY,
    board_lot_size: int = DEFAULT_BOARD_LOT_SIZE,
    max_single_signal_deployment_pct: float = DEFAULT_MAX_SINGLE_SIGNAL_DEPLOYMENT_PCT,
    max_single_symbol_cost_basis_pct: float = DEFAULT_MAX_SINGLE_SYMBOL_COST_BASIS_PCT,
    min_order_notional_cny: float = DEFAULT_MIN_ORDER_NOTIONAL_CNY,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return the governed execution contract required before v3 account replay promotion."""

    generated_at = generated_at or datetime.now(UTC)
    configs = _rolling_configurations(
        initial_cash_cny=initial_cash_cny,
        max_single_signal_deployment_pct=max_single_signal_deployment_pct,
    )
    return {
        "artifact_type": "shortpick_v3_rolling_tranche_execution_contract",
        "schema_version": "shortpick_v3_rolling_tranche_execution_contract.v1",
        "status": "contract_ready_replay_not_yet_run",
        "generated_at": generated_at.isoformat(),
        "model_spec_id": model_spec_id,
        "claim_ceiling": "execution_contract_only_no_account_performance_claim",
        "account_profile": {
            "initial_cash_cny": float(initial_cash_cny),
            "capital_pool_scope": "<=200000_cny_practical_pool",
            "board_lot_size": int(board_lot_size),
            "cash_account_only": True,
            "short_selling_allowed": False,
            "margin_allowed": False,
        },
        "forbidden_execution_modes": [
            {
                "mode": "monthly_full_capital_rotation",
                "reason": (
                    "Buying nearly the full capital pool on one signal date and waiting around 20 trading days "
                    "concentrates risk and is not an acceptable deployment path."
                ),
            }
        ],
        "hard_constraints": {
            "execution_mode": "rolling_tranche_only",
            "max_single_signal_deployment_pct": float(max_single_signal_deployment_pct),
            "max_single_symbol_cost_basis_pct": float(max_single_symbol_cost_basis_pct),
            "min_order_notional_cny": float(min_order_notional_cny),
            "board_lot_rounding": "round_down_to_100_share_lots",
            "delayed_discretionary_entry_allowed": False,
            "same_cash_redeployment_across_overlapping_holds_allowed": False,
            "entry_price_source_policy": "must_match_source_label_matrix_entry_price_source",
            "exit_cash_release_policy": "cash_released_only_after_recorded_sell_execution",
        },
        "candidate_configurations": configs,
        "order_evaluation_policy": {
            "rank_budget_source": "per_signal_tranche_budget_times_model_rank_weight",
            "rank_budget_rounding": "round_order_quantity_down_to_board_lot",
            "skip_when_board_lot_exceeds_rank_budget": True,
            "skip_when_order_notional_below_minimum": True,
            "price_too_high_policy": (
                "A candidate is price-too-high for a slot when one board lot costs more than that slot's "
                "available rank budget after cash and concentration caps."
            ),
            "fallback_policy": (
                "Fallback or substitution is allowed only if declared before replay and uses signal-day-or-earlier "
                "ranked candidates. No later-day manual replacement is allowed."
            ),
        },
        "required_replay_inputs": [
            "selected_top_k_picks_by_date with rank, symbol, score, model rank weight, target horizon, and risk scales",
            "daily market bars for entry, mark-to-market, exit, limit state, and board-lot price checks",
            "trading calendar to release cash after exits and to prevent overlapping cash reuse",
            "cost model with buy cost, sell cost, and stamp tax",
            "source lineage proving buy, skip, fallback, and sizing decisions use signal-day-or-earlier data",
        ],
        "required_replay_outputs": [
            "daily NAV and cash ledger",
            "order ledger with buy, skip, fallback, sell, quantity, price, cash before, and cash after",
            "open-position ledger with cost basis, current value, planned exit, actual exit, and exit reason",
            "reason counts for board-lot block, price-too-high, insufficient cash, concentration cap, and missing bar",
            "monthly account returns, max drawdown, invested ratio, turnover, and concentration metrics",
        ],
        "promotion_gate": {
            "must_not_use_monthly_full_rotation": True,
            "must_replay_all_candidate_configurations": True,
            "must_preserve_current_profitability_and_stability_gates": True,
            "must_report_account_level_total_return": True,
            "must_report_account_level_max_drawdown": True,
            "must_report_negative_month_count": True,
            "must_report_skipped_signal_rate": True,
            "must_report_mean_and_p95_invested_ratio": True,
            "must_report_max_single_symbol_exposure_pct": True,
            "must_pass_leakage_audit": True,
        },
        "next_producer_step": (
            "Implement and run a full historical account replay for this contract. Until that replay exists, "
            "the v3 candidate remains research-only and must not be projected as a production/dashboard strategy."
        ),
    }


def _rolling_configurations(
    *, initial_cash_cny: float, max_single_signal_deployment_pct: float
) -> list[dict[str, Any]]:
    candidates = [
        {
            "config_id": "daily_20_tranche_rank_weighted_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 20,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_profit_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "profit_guard_quick_fail_trend_break",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "stop_loss_12pct",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "late_trend_loss_guard",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_rank23_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "rank23_late_trend_loss_guard",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_rank3_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "rank3_late_trend_loss_guard",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_rank3_pullback_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "rank3_entry_pullback_late_trend_loss_guard",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2250_rank3_pullback_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_250.0,
            "exit_policy": "rank3_entry_pullback_late_trend_loss_guard",
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_250.0,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
        },
        {
            "config_id": (
                "daily_14_tranche_conditional_aggressive_ret20_98_benchmark_nonweak_industry35_dist8_scale14_11_v1"
            ),
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_250.0,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "conditional_aggressive_overlay": {
                "scale": 14 / 11,
                "rank": 1,
                "min_benchmark_return_20d": 0.0,
                "min_return_20d_percentile": 0.98,
                "max_industry_return_20d_excess": 0.35,
                "min_distance_from_20d_high": -0.08,
            },
        },
        {
            "config_id": "daily_14_tranche_three_part_stability_control_min1000_weak085_strong160_cap28_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "max_single_symbol_cost_basis_pct": 0.28,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "three_part_stability_overlay": {
                "weak_scale": 0.85,
                "weak_benchmark_return_20d_lt": -0.02,
                "weak_return_20d_percentile_lt": 1.01,
                "strong_scale": 1.60,
                "strong_benchmark_return_20d_min": 0.0,
                "strong_return_20d_percentile_min": 0.98,
                "strong_industry_return_20d_excess_max": 0.50,
                "strong_distance_from_20d_high_min": -0.08,
            },
        },
        {
            "config_id": "daily_14_tranche_rank_weighted_compound_min2500_rank23_strong_benchmark_pullback_exit_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 14,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2_500.0,
            "exit_policy": "rank23_strong_benchmark_pullback_late_loss_guard",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_profit_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "profit_guard_quick_fail_trend_break",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "stop_loss_12pct",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "late_trend_loss_guard",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_rank23_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "rank23_late_trend_loss_guard",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_rank3_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "rank3_late_trend_loss_guard",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_rank3_pullback_late_trend_loss_guard_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "rank3_entry_pullback_late_trend_loss_guard",
        },
        {
            "config_id": "daily_15_tranche_rank_weighted_compound_min1000_rank23_strong_benchmark_pullback_exit_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 15,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1_000.0,
            "exit_policy": "rank23_strong_benchmark_pullback_late_loss_guard",
        },
        {
            "config_id": "daily_20_tranche_consolidated_rank1_v1",
            "signal_cadence_trade_days": 1,
            "target_active_tranche_count": 20,
            "rank_allocation_mode": "consolidate_to_first_executable_rank",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "two_day_10_tranche_rank_weighted_v1",
            "signal_cadence_trade_days": 2,
            "signal_cadence_offset_trade_days": 0,
            "target_active_tranche_count": 10,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "two_day_10_tranche_rank_weighted_offset1_v1",
            "signal_cadence_trade_days": 2,
            "signal_cadence_offset_trade_days": 1,
            "target_active_tranche_count": 10,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "two_day_10_tranche_consolidated_rank1_v1",
            "signal_cadence_trade_days": 2,
            "target_active_tranche_count": 10,
            "rank_allocation_mode": "consolidate_to_first_executable_rank",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "weekly_4_tranche_rank_weighted_v1",
            "signal_cadence_trade_days": 5,
            "target_active_tranche_count": 4,
            "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
        {
            "config_id": "weekly_4_tranche_consolidated_rank1_v1",
            "signal_cadence_trade_days": 5,
            "target_active_tranche_count": 4,
            "rank_allocation_mode": "consolidate_to_first_executable_rank",
            "budget_mode": "fixed_initial_cash_fraction",
            "exit_policy": "mechanical_horizon",
        },
    ]
    max_single_signal_budget = float(initial_cash_cny) * float(max_single_signal_deployment_pct)
    configs: list[dict[str, Any]] = []
    for row in candidates:
        budget = float(initial_cash_cny) / float(row["target_active_tranche_count"])
        if budget > max_single_signal_budget:
            continue
        configs.append(
            {
                **row,
                "per_signal_target_budget_cny": budget,
                "per_signal_target_budget_pct": budget / float(initial_cash_cny) if initial_cash_cny else 0.0,
                "concentration_status": "allowed_rolling_tranche",
            }
        )
    return configs
