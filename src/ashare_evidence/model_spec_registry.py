from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.model_exploration_snapshot import (
    DEFAULT_HORIZONS,
    MODEL_EXPLORATION_ACCOUNT_PROFILE,
    MODEL_EXPLORATION_PROTOCOL_VERSION,
)
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_SPEC_REGISTRY_SCHEMA_VERSION = "model_spec_registry.v1"
MODEL_SPEC_REGISTRY_ID = "shortpick-model-spec-registry-v1"


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _grid_trial_count(grid: dict[str, list[Any]]) -> int:
    count = 1
    for values in grid.values():
        count *= max(len(values), 1)
    return count


def _promotion_gates() -> dict[str, Any]:
    return {
        "oos_rank_ic_min": 0.02,
        "icir_min": 0.35,
        "positive_ic_month_rate_min": 0.55,
        "deflated_sharpe_confidence_min": 0.95,
        "pbo_max": 0.10,
        "alpha_t_stat_min": 3.0,
        "cost_stress_multiplier": 2.0,
        "winner_dependency_policy": "top_symbol_day_month_removal_must_not_collapse",
    }


def _base_spec(
    *,
    model_spec_id: str,
    model_type: str,
    purpose: str,
    feature_groups: list[str],
    hyperparameter_grid: dict[str, list[Any]],
    training_window_days: list[int],
    prediction_horizon_days: int = 10,
    dynamic_weight_policy: dict[str, Any] | None = None,
    selection_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    max_trials = _grid_trial_count(hyperparameter_grid)
    return {
        "model_spec_id": model_spec_id,
        "model_type": model_type,
        "purpose": purpose,
        "status": "research_candidate_spec",
        "account_profile": MODEL_EXPLORATION_ACCOUNT_PROFILE,
        "allowed_feature_groups": feature_groups,
        "prediction_horizon_days": prediction_horizon_days,
        "training_window_days": training_window_days,
        "purge_days": max(DEFAULT_HORIZONS),
        "embargo_days": max(DEFAULT_HORIZONS),
        "hyperparameter_grid": hyperparameter_grid,
        "max_trials": max_trials,
        "monotonic_or_sign_constraints": {},
        "dynamic_weight_policy": dynamic_weight_policy
        or {
            "enabled": False,
            "reason": "static_or_baseline_spec",
        },
        "cost_model": {
            "round_trip_cost": 0.001,
            "stress_multiplier": 2.0,
        },
        "selection_policy": selection_policy
        or {
            "mode": "broad_rank_top_quantile",
            "evaluation_return_metric": "top_quantile_net_excess_mean",
        },
        "promotion_gates": _promotion_gates(),
        "production_effect": "forbidden",
        "claim_ceiling": "research_spec_only",
    }


def default_model_specs() -> list[dict[str, Any]]:
    specs = [
        _base_spec(
            model_spec_id="baseline_momentum_10d_turnover_cooldown_v1",
            model_type="deterministic_baseline",
            purpose="Recreate the current momentum-volume family as a controlled baseline, not a promoted strategy.",
            feature_groups=["price_momentum", "liquidity", "execution", "crowding"],
            training_window_days=[120],
            hyperparameter_grid={
                "top_k": [5],
                "momentum_horizon_days": [10],
                "turnover_rank_weight": [1.0],
                "cooldown_days": [10],
            },
        ),
        _base_spec(
            model_spec_id="ranked_feature_linear_v1",
            model_type="regularized_rank_linear",
            purpose="Combine PIT feature groups with bounded coefficients and fixed walk-forward windows.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "crowding",
            ],
            training_window_days=[120, 240],
            hyperparameter_grid={
                "regularization_alpha": [0.1, 1.0],
                "rank_normalization": ["cross_sectional_percentile"],
                "winsorize_quantile": [0.01, 0.05],
            },
        ),
        _base_spec(
            model_spec_id="ranked_tree_shallow_v1",
            model_type="shallow_tree_ranker",
            purpose="Test bounded nonlinear feature interactions without opening a broad search.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "crowding",
            ],
            training_window_days=[240],
            hyperparameter_grid={
                "max_depth": [2, 3],
                "min_samples_leaf": [50, 100],
                "learning_rate": [0.03],
            },
        ),
        _base_spec(
            model_spec_id="regime_conditioned_linear_v1",
            model_type="bounded_regime_conditioned_linear",
            purpose="Allow slow regime-conditioned weights only after enough independent windows exist.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "crowding",
            ],
            training_window_days=[240],
            hyperparameter_grid={
                "regularization_alpha": [0.5, 1.0],
                "regime_bucket": ["benchmark_trend_volatility"],
                "weight_multiplier_clip": [(0.5, 1.5)],
            },
            dynamic_weight_policy={
                "enabled": True,
                "function_family": "slow_regime_conditioned_multiplier",
                "min_independent_windows": 20,
                "min_rolling_ic_periods": 60,
                "sensitivity_max": 0.3,
                "multiplier_clip": [0.5, 1.5],
                "requires_oos_gate_pass": True,
                "requires_governance_approval": True,
            },
        ),
        _base_spec(
            model_spec_id="pullback_reversal_5d_v1",
            model_type="pullback_reversal_ranker",
            purpose="Search for short-horizon recoveries after mild pullbacks without chasing one-day overheated names.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
            ],
            prediction_horizon_days=5,
            training_window_days=[60, 120],
            hyperparameter_grid={
                "pullback_weight": [1.0, 1.2],
                "trend_context_weight": [0.25, 0.35],
                "volatility_penalty": [0.35],
            },
        ),
        _base_spec(
            model_spec_id="liquidity_breakout_5d_v1",
            model_type="liquidity_breakout_ranker",
            purpose="Search for short-horizon momentum names with liquidity confirmation and overheat penalty.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "crowding",
                "regime",
            ],
            prediction_horizon_days=5,
            training_window_days=[60, 120],
            hyperparameter_grid={
                "momentum_weight": [0.5, 0.7],
                "liquidity_confirmation_weight": [0.25, 0.35],
                "overheat_penalty": [0.25],
            },
        ),
        _base_spec(
            model_spec_id="trend_quality_20d_v1",
            model_type="trend_quality_ranker",
            purpose="Search for longer-horizon trend quality after controlling volatility and distance from recent highs.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
            ],
            prediction_horizon_days=20,
            training_window_days=[120, 240],
            hyperparameter_grid={
                "trend_weight": [0.8, 1.0],
                "high_distance_weight": [0.4, 0.5],
                "volatility_penalty": [0.35, 0.45],
            },
        ),
        _base_spec(
            model_spec_id="concentrated_liquidity_momentum_20d_v1",
            model_type="concentrated_liquidity_momentum_ranker",
            purpose="Test whether the diagnostic top5 liquidity/momentum seed can survive walk-forward gates as a concentrated strategy candidate.",
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.0, 0.25],
                "industry_relative_weight": [0.0, 0.25],
                "volatility_penalty": [0.0, 0.25],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
            },
        ),
        _base_spec(
            model_spec_id="anchor_liquidity_concentrated_top5_20d_v1",
            model_type="concentrated_liquidity_momentum_ranker",
            purpose=(
                "Fixed single-trial anchor check for the strongest short-window concentrated liquidity top5 line. "
                "This is a screening spec for same-contract three-year comparison, not a promoted model."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.0],
                "industry_relative_weight": [0.0],
                "volatility_penalty": [0.0],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "screening_policy": "single_trial_liquidity_anchor_before_full_grid",
            },
        ),
        _base_spec(
            model_spec_id="breakout_amount_confirmation_top1_20d_v1",
            model_type="breakout_amount_confirmation_ranker",
            purpose=(
                "Screen a multi-factor breakout and amount-confirmation model discovered from three-year next-close "
                "lightweight replay: 20d relative trend, 10d/20d amount expansion, liquidity, one-day overheat penalty, "
                "and volatility/turnover risk gates. This is not a V1 single-source rule and remains research-only."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "screening_evidence": {
                    "source": "lightweight_next_close_replay_cache",
                    "as_of_start": "2023-06-13",
                    "as_of_end": "2026-05-26",
                    "evaluated_signal_days": 713,
                    "proxy_total_return": 2.4529,
                    "proxy_annualized_return": 0.5496,
                    "proxy_max_drawdown": -0.2413,
                    "proxy_positive_signal_day_rate": 0.512,
                    "proxy_negative_month_count": 15,
                    "formal_160_artifact_id": "model-comparison-report-f80b77e8f82e26dd",
                    "formal_160_selected_top_k_net_excess_mean": 0.0408,
                    "formal_160_positive_selected_top_k_rate": 0.43,
                    "weaker_regime_note": "2023 partial-year proxy return remained negative at about -20.5%; full artifact validation is still required.",
                },
            },
        ),
        _base_spec(
            model_spec_id="breakout_amount_expansion_top1_20d_v1",
            model_type="breakout_amount_confirmation_ranker",
            purpose=(
                "Challenge the breakout/amount-confirmation finalist with a stricter raw amount-expansion gate. "
                "It improves the three-year lightweight curve but worsens the latest 160-date formal replay, "
                "so it is a challenger branch rather than the default finalist."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.6],
                "liquidity_percentile_weight": [1.4],
                "one_day_overheat_penalty": [0.3],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                    "min_amount_10d_vs_20d": 0.15,
                },
                "screening_evidence": {
                    "source": "lightweight_next_close_replay_cache",
                    "as_of_start": "2023-06-13",
                    "as_of_end": "2026-05-26",
                    "evaluated_signal_days": 713,
                    "proxy_total_return": 3.4378,
                    "proxy_annualized_return": 0.6933,
                    "proxy_max_drawdown": -0.1999,
                    "proxy_positive_signal_day_rate": 0.523,
                    "proxy_negative_month_count": 14,
                    "formal_160_artifact_id": "model-comparison-report-837a0761bccaf56c",
                    "formal_160_selected_top_k_net_excess_mean": 0.0099,
                    "formal_160_positive_selected_top_k_rate": 0.38,
                    "formal_160_comparison": "worse_than_breakout_amount_confirmation_top1_20d_v1_on_latest_160_date_formal_replay",
                    "weaker_regime_note": "2023 partial-year proxy return remained negative at about -19.1%; full artifact validation is still required.",
                },
            },
        ),
        _base_spec(
            model_spec_id="breakout_amount_confirmation_top2_20d_v1",
            model_type="breakout_amount_confirmation_ranker",
            purpose=(
                "Diversify the default breakout/amount-confirmation finalist from top1 to top2. "
                "This sacrifices long-window upside but targets lower winner dependency and stronger recent formal stability."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "screening_evidence": {
                    "source": "lightweight_next_close_replay_cache",
                    "as_of_start": "2023-06-13",
                    "as_of_end": "2026-05-26",
                    "evaluated_signal_days": 713,
                    "proxy_total_return": 1.8300,
                    "proxy_annualized_return": 0.4440,
                    "proxy_max_drawdown": -0.2370,
                    "proxy_positive_signal_day_rate": 0.534,
                    "proxy_negative_month_count": 15,
                    "lightweight_recent_100_selected_top_k_excess_mean": 0.0728,
                    "lightweight_recent_100_positive_selected_top_k_rate": 0.66,
                    "formal_160_artifact_id": "model-comparison-report-13765e72fea137ca",
                    "formal_160_selected_top_k_net_excess_mean": 0.0057,
                    "formal_160_positive_selected_top_k_rate": 0.44,
                    "formal_160_comparison": "worse_than_breakout_amount_confirmation_top1_20d_v1_on_latest_160_date_formal_replay",
                    "weaker_regime_note": "Top2 diversification reduces concentration but sacrifices long-window upside; formal replay is required before treating it as a stability improvement.",
                },
            },
        ),
        _base_spec(
            model_spec_id="regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Switch from breakout/amount-confirmation to a defensive low-turnover and low-volatility ranker "
                "when the benchmark 20d return is negative. This targets the latest formal weak-regime failures "
                "without using symbol or month blacklists."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [-0.01, 0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [0.8, 1.2],
                "defensive_low_turnover_percentile_weight": [1.2, 1.5],
                "defensive_return_5d_percentile_weight": [0.0, 0.3],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.065,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.18,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The goal is not the highest isolated mean trial. On short windows, require selected top-k "
                        "excess return before stability tie-breaks; on full windows, require portfolio total-return "
                        "and drawdown floors before preferring fewer weak months and better worst-month behavior."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "screening_evidence": {
                    "source": "lightweight_next_close_replay_cache_plus_runtime_benchmark_20d",
                    "as_of_start": "2023-06-13",
                    "as_of_end": "2026-05-26",
                    "evaluated_signal_days": 713,
                    "proxy_total_return": 2.1964,
                    "proxy_annualized_return": 0.5079,
                    "proxy_max_drawdown": -0.1103,
                    "proxy_positive_signal_day_rate": 0.586,
                    "proxy_negative_month_count": 13,
                    "formal_matrix_best_params": {
                        "defensive_benchmark_return_20d_threshold": 0.0,
                        "defensive_low_volatility_percentile_weight": 0.8,
                        "defensive_low_turnover_percentile_weight": 1.5,
                        "defensive_return_5d_percentile_weight": 0.0,
                    },
                    "formal_matrix_estimate_selected_top_k_net_excess_mean": 0.0729,
                    "formal_matrix_estimate_positive_selected_top_k_rate": 0.53,
                    "formal_160_artifact_id": "model-comparison-report-e7cea6d36d8b6918",
                    "formal_160_trial_count": 16,
                    "formal_160_best_trial_id": "regime_adaptive_breakout_defensive_top1_20d_v1:trial-012",
                    "formal_160_selection_policy": "stability_adjusted_after_return_floor",
                    "formal_160_decision": "observe_blocked",
                    "formal_160_selected_top_k_net_excess_mean": 0.0717,
                    "formal_160_positive_selected_top_k_rate": 0.52,
                    "formal_160_negative_months": ["2026-03"],
                    "formal_160_winner_dependency_status": "ready",
                    "formal_160_pbo_proxy": 0.0,
                    "formal_160_deflated_sharpe_confidence": 0.6057,
                    "formal_160_alpha_t_stat": 2.6231,
                    "formal_full713_artifact_id": "model-comparison-report-db3ea613abee7082",
                    "formal_full713_trial_count": 16,
                    "formal_full713_best_trial_id": "regime_adaptive_breakout_defensive_top1_20d_v1:trial-010",
                    "formal_full713_selection_policy": "stability_adjusted_full_window_portfolio_floor",
                    "formal_full713_decision": "observe_blocked",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0186,
                    "formal_full713_positive_selected_top_k_rate": 0.5130,
                    "formal_full713_portfolio_total_return": 1.4676,
                    "formal_full713_portfolio_annualized_return": 0.4170,
                    "formal_full713_portfolio_max_drawdown": -0.1204,
                    "formal_full713_negative_month_count": 13,
                    "formal_full713_result_anchor_status": "anchor_floor_passed",
                    "formal_full713_pbo_proxy": 0.0,
                    "formal_full713_deflated_sharpe_confidence": 0.7514,
                    "formal_full713_alpha_t_stat": 3.0336,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "weaker_regime_note": "Defensive branch concentrates in large low-turnover stocks in weak benchmark regimes; full artifact and capacity checks are required.",
                },
            },
        ),
        _base_spec(
            model_spec_id="risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the regime-adaptive top1 selector, but scale exposure with PIT volatility and turnover risk "
                "so weak-regime defensive picks can reduce left-tail damage without symbol, date or month filters."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.75, 0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.65, 0.80],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Risk scaling can lower mean excess return, so full-window selection uses portfolio return "
                        "and drawdown floors first, then stability. This tests whether dynamic exposure can improve "
                        "the current finalist's path without changing its stock-selection formula."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.80,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.80,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.65,
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-db3ea613abee7082",
                    "formal_full713_artifact_id": "model-comparison-report-6eaec6fb4a32e5d8",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-92a2b5d491d89526",
                    "formal_full713_best_trial_id": "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1:trial-003",
                    "formal_full713_status": "observe_blocked_not_replacement",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0184,
                    "formal_full713_positive_selected_top_k_rate": 0.5130,
                    "formal_full713_portfolio_total_return": 1.4551,
                    "formal_full713_portfolio_annualized_return": 0.4143,
                    "formal_full713_portfolio_max_drawdown": -0.1183,
                    "formal_full713_negative_month_count": 14,
                    "formal_full713_deflated_sharpe_confidence": 0.9186,
                    "formal_full713_alpha_t_stat": 3.0606,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "design_reason": (
                        "Parent finalist passes result anchors and has strong drawdown, but remains blocked by "
                        "DSR and monthly/path stress. This challenger tests dynamic PIT exposure rather than "
                        "symbol/date/month exclusions."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="momentum_confirmed_regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the regime-adaptive top1 framework, but require the weak-regime defensive branch to retain "
                "some 20-day relative-strength confirmation instead of ranking only by low-risk/liquidity factors."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "defensive_return_20d_percentile_weight": [0.2, 0.4, 0.6, 0.8],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.16,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The parent model's weak-regime branch reduced drawdown but still bought too many "
                        "left-tail losers. This bounded challenger tests whether adding defensive momentum "
                        "confirmation improves stability without lowering the full-window return bar."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-db3ea613abee7082",
                    "formal_full713_artifact_id": "model-comparison-report-58b8998c054627a0",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-7a56a1c270d3226c",
                    "formal_full713_best_trial_id": "momentum_confirmed_regime_adaptive_breakout_defensive_top1_20d_v1:trial-000",
                    "formal_full713_status": "downgraded_weaker_than_parent",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0147,
                    "formal_full713_positive_selected_top_k_rate": 0.4855,
                    "formal_full713_portfolio_total_return": 1.1759,
                    "formal_full713_portfolio_annualized_return": 0.3499,
                    "formal_full713_portfolio_max_drawdown": -0.1240,
                    "formal_full713_negative_month_count": 14,
                    "formal_full713_deflated_sharpe_confidence": 0.7797,
                    "formal_full713_alpha_t_stat": 2.4364,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "overfit:alpha_t_stat_below_multiple_testing_threshold",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "design_reason": (
                        "Parent finalist has strong return/drawdown but many weak months. The hypothesis is that "
                        "defensive low-risk picks still need 20d trend confirmation to avoid value-trap style losers."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="regime_exposure_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Combine the regime-adaptive top1 selector with PIT stock-risk scaling and continuous market-regime "
                "exposure scaling. This tests whether weak/high-volatility benchmark states can reduce path stress "
                "without a hard cash switch or symbol/date/month exclusions."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "min_weight_benchmark_return_20d": [-0.04, -0.06],
                "regime_min_position_weight": [0.55, 0.70],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.40,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The risk-scaled challenger nearly clears DSR but still has too many weak months. This "
                        "variant adds continuous benchmark-regime exposure scaling while preserving the parent "
                        "selector and avoiding hard cash switches."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_regime_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.80,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.80,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                    "full_weight_min_benchmark_return_20d": 0.0,
                    "min_weight_benchmark_return_20d": -0.06,
                    "full_weight_max_benchmark_volatility_20d": 0.04,
                    "min_weight_benchmark_volatility_20d": 0.08,
                    "regime_min_position_weight": 0.55,
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-6eaec6fb4a32e5d8",
                    "formal_full713_artifact_id": "model-comparison-report-d3a1596a97fafd20",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-ccf6c109f1822c55",
                    "formal_full713_best_trial_id": "regime_exposure_scaled_regime_adaptive_breakout_defensive_top1_20d_v1:trial-003",
                    "formal_full713_status": "downgraded_market_exposure_scaled_too_much_return_loss",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0167,
                    "formal_full713_positive_selected_top_k_rate": 0.5130,
                    "formal_full713_portfolio_total_return": 1.1915,
                    "formal_full713_portfolio_annualized_return": 0.3536,
                    "formal_full713_portfolio_max_drawdown": -0.1180,
                    "formal_full713_negative_month_count": 13,
                    "formal_full713_deflated_sharpe_confidence": 0.8954,
                    "formal_full713_alpha_t_stat": 2.9208,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "overfit:alpha_t_stat_below_multiple_testing_threshold",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "design_reason": (
                        "Risk scaling improved DSR to 0.9186 but left monthly/path stress unresolved. This spec "
                        "tests whether market-regime exposure scaling can close that gap without losing the "
                        "return level that made the parent meaningful."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="conditional_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Preserve full exposure for low-risk picks, but tighten volatility and turnover scaling only when "
                "the benchmark regime is weak or volatile. This targets path stress without broad market-level "
                "cash switching."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "weak_full_weight_max_volatility_20d_percentile": [0.65, 0.75],
                "weak_regime_min_position_weight": [0.65, 0.80],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Broad market exposure scaling cut too much return. This challenger only tightens "
                        "single-stock risk scaling in weak regimes, preserving full weight for low-risk winners."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "conditional_regime_stock_risk_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "weak_full_weight_max_volatility_20d_percentile": 0.75,
                    "weak_full_weight_max_turnover_rate_percentile": 0.80,
                    "weak_regime_min_position_weight": 0.65,
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-6eaec6fb4a32e5d8",
                    "formal_full713_artifact_id": "model-comparison-report-cadd53fd6a3cb1e6",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-8f2765b88249da5e",
                    "formal_full713_best_trial_id": "conditional_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1:trial-003",
                    "formal_full713_status": "observe_blocked_near_risk_scaled_but_not_replacement",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0184,
                    "formal_full713_positive_selected_top_k_rate": 0.5130,
                    "formal_full713_portfolio_total_return": 1.4476,
                    "formal_full713_portfolio_annualized_return": 0.4126,
                    "formal_full713_portfolio_max_drawdown": -0.1183,
                    "formal_full713_negative_month_count": 14,
                    "formal_full713_deflated_sharpe_confidence": 0.9170,
                    "formal_full713_alpha_t_stat": 3.0505,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "design_reason": (
                        "Independent market exposure scaling reduced return too much. This spec tests a more "
                        "conditional rule: only weak-regime high-risk picks are scaled down."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="adaptive_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the risk-scaled regime-adaptive top1 selector, but choose a PIT 5/10/20 trading-day exit "
                "horizon from market regime and single-stock risk. This tests holding-period logic rather than "
                "more exposure-only scaling."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75, 0.85],
                "weak_regime_exit_horizon_days": [5, 10],
                "risk_exit_horizon_days": [5],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Exposure-only controls did not clear the stability gap. This bounded candidate tests "
                        "whether shortening exits in weak/high-risk states improves path stability while preserving "
                        "the risk-scaled return frontier."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.80,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 10,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-6eaec6fb4a32e5d8",
                    "formal_full713_artifact_id": "model-comparison-report-95421910943186f3",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-52b133e7583961ed",
                    "formal_full713_best_trial_id": (
                        "adaptive_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1:trial-001"
                    ),
                    "formal_full713_status": "downgraded_adaptive_exit_too_much_return_loss",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0156,
                    "formal_full713_positive_selected_top_k_rate": 0.5145,
                    "formal_full713_portfolio_total_return": 1.3279,
                    "formal_full713_portfolio_annualized_return": 0.3855,
                    "formal_full713_portfolio_max_drawdown": -0.1408,
                    "formal_full713_negative_month_count": 13,
                    "formal_full713_deflated_sharpe_confidence": 0.6971,
                    "formal_full713_alpha_t_stat": 2.1812,
                    "formal_full713_mean_target_horizon_days": 14.65,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "design_reason": (
                        "Risk-scaled frontier is close on DSR but fails monthly/path stress. This spec changes "
                        "holding period by PIT risk state instead of further reducing exposure."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the risk-scaled regime-adaptive selector and 20-day holding period by default, but exit early "
                "only for high-stock-risk picks inside weak or high-volatility benchmark regimes."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75, 0.85],
                "risk_exit_horizon_days": [5, 10],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The first adaptive-exit candidate shortened too many weak-regime low-risk winners. This "
                        "variant only exits early on weak-regime high-stock-risk picks."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.80,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-6eaec6fb4a32e5d8",
                    "formal_full713_artifact_id": "model-comparison-report-c4d96d7b0d1f5d0a",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-295411d5af9db144",
                    "formal_full713_best_trial_id": (
                        "tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1:trial-000"
                    ),
                    "formal_full713_status": "observe_blocked_return_frontier_but_stability_unresolved",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0184,
                    "formal_full713_positive_selected_top_k_rate": 0.5130,
                    "formal_full713_portfolio_total_return": 1.5402,
                    "formal_full713_portfolio_annualized_return": 0.4330,
                    "formal_full713_portfolio_max_drawdown": -0.1183,
                    "formal_full713_negative_month_count": 14,
                    "formal_full713_deflated_sharpe_confidence": 0.9183,
                    "formal_full713_alpha_t_stat": 3.0589,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "design_reason": (
                        "Adaptive exit reduced too many weak-regime winners. This narrower spec tests only tail-risk "
                        "early exit while preserving 20d holding for lower-risk picks."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the same multi-factor regime-adaptive scorer, risk-scaled position sizing, and tail-risk exit, "
                "but allocate a small sleeve to the second-ranked pick. This tests whether rank-weighted "
                "portfolio construction can reduce single-stock path risk without reverting to v1-style heuristics."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_95_05", "top2_90_10", "top2_85_15", "top2_80_20"],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.10,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Tail-risk exit recovered return but still had 14 negative months and DSR below 95%. "
                        "A rank-weighted top2 sleeve targets single-stock path risk while preserving the top1 signal."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "fixed_share_profile",
                    "profile": "top2_90_10",
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-c4d96d7b0d1f5d0a",
                    "formal_full713_artifact_id": "model-comparison-report-baea5b17cd06ef3c",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-4b97fee69f4a40a0",
                    "formal_full713_best_trial_id": (
                        "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-000"
                    ),
                    "formal_full713_best_profile": "top2_95_05",
                    "formal_full713_status": "observe_blocked_stability_improved_but_dsr_unresolved",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0177,
                    "formal_full713_positive_selected_top_k_rate": 0.5161,
                    "formal_full713_portfolio_total_return": 1.5240,
                    "formal_full713_portfolio_annualized_return": 0.4295,
                    "formal_full713_portfolio_max_drawdown": -0.1151,
                    "formal_full713_negative_month_count": 13,
                    "formal_full713_deflated_sharpe_confidence": 0.9214,
                    "formal_full713_alpha_t_stat": 3.0796,
                    "formal_full713_stability_preferred_trial_id": (
                        "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-001"
                    ),
                    "formal_full713_stability_preferred_profile": "top2_90_10",
                    "formal_full713_stability_preferred_total_return": 1.4697,
                    "formal_full713_stability_preferred_max_drawdown": -0.1119,
                    "formal_full713_stability_preferred_negative_month_count": 12,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "diagnostic_top2_90_10_negative_month_count": 12,
                    "diagnostic_top2_90_10_net_excess_proxy_max_drawdown": -0.0996,
                    "design_reason": (
                        "Formal tail-risk top1 passed the anchor return floor but failed DSR/monthly stability. "
                        "Top2 rank-weight diagnostics improved negative months and drawdown without changing the scorer."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="stress_cash_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Add a conjunctive market-stress cash switch to the rank-weighted tail-risk top2 sleeve. The switch "
                "only blocks new selections when short-term benchmark return, 20-day benchmark return, and benchmark "
                "volatility all indicate stress, targeting negative-month stability without broad market de-risking."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "market_stress_filter",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.0],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_90_10"],
                "min_benchmark_return_10d": [-0.015, -0.025],
                "min_benchmark_return_20d": [-0.03, -0.05],
                "max_benchmark_volatility_20d": [0.07, 0.09],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Rank-weighted top2 improved negative months but still failed path/DSR gates. This candidate "
                        "skips only conjunctive benchmark stress states instead of applying broad exposure cuts."
                    ),
                },
                "cash_switch": {
                    "enabled": True,
                    "condition_mode": "all",
                    "cash_return": 0.0,
                    "min_benchmark_return_10d": -0.015,
                    "min_benchmark_return_20d": -0.03,
                    "max_benchmark_volatility_20d": 0.08,
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "fixed_share_profile",
                    "profile": "top2_90_10",
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": (
                        "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                    ),
                    "parent_full713_artifact_id": "model-comparison-report-baea5b17cd06ef3c",
                    "formal_full713_artifact_id": "model-comparison-report-2711575202ad0e38",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-4b737ec3e214f4d1",
                    "formal_full713_best_trial_id": (
                        "stress_cash_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-004"
                    ),
                    "formal_full713_status": "downgraded_cash_switch_no_incremental_edge",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0171,
                    "formal_full713_positive_selected_top_k_rate": 0.5161,
                    "formal_full713_portfolio_total_return": 1.4697,
                    "formal_full713_portfolio_annualized_return": 0.4175,
                    "formal_full713_portfolio_max_drawdown": -0.1119,
                    "formal_full713_negative_month_count": 12,
                    "formal_full713_deflated_sharpe_confidence": 0.8547,
                    "formal_full713_alpha_t_stat": 3.0963,
                    "formal_full713_cash_trigger_observation": (
                        "0.09 volatility threshold produced no cash dates; 0.07 threshold reduced negative months "
                        "to 11 but cut total return below the 1.45 floor."
                    ),
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "parent_stability_preferred_trial_id": (
                        "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-001"
                    ),
                    "parent_stability_preferred_total_return": 1.4697,
                    "parent_stability_preferred_negative_month_count": 12,
                    "parent_stability_preferred_portfolio_max_drawdown": -0.1119,
                    "design_reason": (
                        "The 90/10 sleeve preserved the return floor with fewer negative months. This spec tests "
                        "whether skipping only multi-condition benchmark stress dates can clear remaining path gates."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Change the selected opportunity set by switching into the defensive branch before benchmark 20d "
                "return turns negative, but only when short-term benchmark return weakens, 20d benchmark return is "
                "not strong, and benchmark volatility is elevated. This tests richer regime-transition features on "
                "top of the current rank-weighted tail-risk frontier."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.005, -0.015],
                "transition_benchmark_return_20d_ceiling": [0.02, 0.04],
                "transition_benchmark_volatility_20d_threshold": [0.04, 0.06],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_90_10"],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.45,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Prior exposure, cash, and exit controls did not clear DSR/monthly/path gates. This candidate "
                        "changes which stocks are selected during early benchmark-transition stress."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "fixed_share_profile",
                    "profile": "top2_90_10",
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": (
                        "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                    ),
                    "parent_full713_artifact_id": "model-comparison-report-baea5b17cd06ef3c",
                    "formal_full713_artifact_id": "model-comparison-report-115676e844c4526b",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-b25ec0b716584c64",
                    "formal_full713_best_trial_id": (
                        "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-004"
                    ),
                    "formal_full713_status": "observe_blocked_frontier_improved_but_dsr_unresolved",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0177,
                    "formal_full713_positive_selected_top_k_rate": 0.5207,
                    "formal_full713_portfolio_total_return": 1.5197,
                    "formal_full713_portfolio_annualized_return": 0.4285,
                    "formal_full713_portfolio_max_drawdown": -0.1119,
                    "formal_full713_negative_month_count": 12,
                    "formal_full713_deflated_sharpe_confidence": 0.8807,
                    "formal_full713_alpha_t_stat": 3.2179,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "parent_stability_preferred_trial_id": (
                        "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-001"
                    ),
                    "parent_stability_preferred_total_return": 1.4697,
                    "parent_stability_preferred_negative_month_count": 12,
                    "parent_stability_preferred_portfolio_max_drawdown": -0.1119,
                    "design_reason": (
                        "The remaining gap appears to come from selected opportunity set instability, not only from "
                        "holding period, exposure, or cash gating. Transition stress changes the branch used to rank "
                        "candidates before the benchmark fully turns negative."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Narrow the transition-defensive family to the threshold region that improved both return and "
                "negative-month stability, then arbitrate only between 95/5 and 90/10 rank-weighted sleeves."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02, 0.04],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_95_05", "top2_90_10"],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.50,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "portfolio_total_return_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The broader transition-defensive family improved the frontier but was penalized by an "
                        "8-trial search. This finalist replay limits comparison to the robust transition region."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "fixed_share_profile",
                    "profile": "top2_90_10",
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": (
                        "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                    ),
                    "parent_full713_artifact_id": "model-comparison-report-115676e844c4526b",
                    "formal_full713_artifact_id": "model-comparison-report-05032fe21ce33845",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-d0b72f8a2b7e9173",
                    "formal_full713_best_trial_id": (
                        "transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1:trial-002"
                    ),
                    "formal_full713_status": "observe_blocked_dsr_near_miss",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0177,
                    "formal_full713_positive_selected_top_k_rate": 0.5207,
                    "formal_full713_portfolio_total_return": 1.5197,
                    "formal_full713_portfolio_annualized_return": 0.4285,
                    "formal_full713_portfolio_max_drawdown": -0.1119,
                    "formal_full713_negative_month_count": 12,
                    "formal_full713_deflated_sharpe_confidence": 0.9398,
                    "formal_full713_alpha_t_stat": 3.2179,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "parent_full713_best_trial_id": (
                        "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
                        ":trial-004"
                    ),
                    "parent_full713_total_return": 1.5197,
                    "parent_full713_negative_month_count": 12,
                    "parent_full713_portfolio_max_drawdown": -0.1119,
                    "parent_full713_deflated_sharpe_confidence": 0.8807,
                    "design_reason": (
                        "This is not a new broad search. It replays the transition region that outperformed the "
                        "rank-weighted 90/10 baseline on return while keeping the same 12 negative months."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Scan the narrow 90-93% first-rank sleeve range inside the validated transition-defensive region. "
                "The intent is to find a return/stability balance between the 90/10 12-negative-month profile and "
                "the higher-return 95/5 profile that reintroduced a 13th negative month."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_90_10", "top2_91_09", "top2_92_08", "top2_93_07"],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.50,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_total_return_desc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Use negative-month count as the first stability guard, then choose the higher-return sleeve "
                        "among profiles with the same negative-month count."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "fixed_share_profile",
                    "profile": "top2_91_09",
                },
                "screening_evidence": {
                    "source": "full713_formal_replay_reused_matrices",
                    "parent_model_spec_id": "transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-05032fe21ce33845",
                    "formal_full713_artifact_id": "model-comparison-report-d464f8ef856be002",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-792a4b62a3bfa5ae",
                    "formal_full713_best_trial_id": (
                        "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1:trial-001"
                    ),
                    "formal_full713_best_profile": "top2_91_09",
                    "formal_full713_status": "observe_blocked_current_frontier_dsr_near_miss",
                    "formal_full713_selected_top_k_net_excess_mean": 0.0178,
                    "formal_full713_positive_selected_top_k_rate": 0.5222,
                    "formal_full713_portfolio_total_return": 1.5309,
                    "formal_full713_portfolio_annualized_return": 0.4310,
                    "formal_full713_portfolio_max_drawdown": -0.1125,
                    "formal_full713_negative_month_count": 12,
                    "formal_full713_deflated_sharpe_confidence": 0.9393,
                    "formal_full713_alpha_t_stat": 3.2144,
                    "formal_full713_blockers": [
                        "overfit:deflated_sharpe_confidence_below_95pct",
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                    ],
                    "formal_full713_superseded_report_id": "model-comparison-report-4825310a84b2616e",
                    "formal_full713_superseded_reason": (
                        "Original report was built before declared tie_break_order was enforced by the comparison "
                        "report sorter; candidate run is unchanged."
                    ),
                    "parent_full713_best_trial_id": "transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1:trial-002",
                    "parent_full713_total_return": 1.5197,
                    "parent_full713_negative_month_count": 12,
                    "parent_full713_deflated_sharpe_confidence": 0.9398,
                    "diagnostic_reason": (
                        "Inline diagnostics suggested 91/9 may preserve the 12-negative-month profile with slightly "
                        "higher return than 90/10; this spec requires formal replay before accepting that inference."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="industry_diversified_transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the current transition-defensive multi-factor frontier, but apply an ex-ante portfolio "
                "construction constraint that prevents the two rank-weighted sleeves from coming from the same "
                "industry on a signal date. This tests concentration stability without symbol, date, month, or "
                "industry blacklists."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "industry_concentration",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_90_10", "top2_91_09", "top2_92_08"],
                "max_same_industry_picks": [1],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.50,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_total_return_desc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The current frontier still fails monthly/path stress. This challenger keeps the model "
                        "score intact and tests only whether portfolio concentration control improves stability."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "fixed_share_profile",
                    "profile": "top2_91_09",
                },
                "portfolio_constraints": {
                    "enabled": True,
                    "mode": "per_signal_date_industry_cap",
                    "max_same_industry_picks": 1,
                    "fallback": "allow_lower_rank_cross_industry",
                },
                "screening_evidence": {
                    "source": "pending_full713_formal_replay",
                    "parent_model_spec_id": "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-d464f8ef856be002",
                    "parent_full713_best_trial_id": (
                        "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1:trial-001"
                    ),
                    "parent_full713_total_return": 1.5309,
                    "parent_full713_negative_month_count": 12,
                    "parent_full713_deflated_sharpe_confidence": 0.9393,
                    "design_reason": (
                        "Industry metadata is now PIT-carried into prediction diagnostics. This candidate uses that "
                        "metadata only for portfolio construction, not for fitting to known strong stocks."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the transition-defensive multi-factor scorer, but make rank allocation a bounded function of "
                "first-rank stock risk and score margin. When the first-ranked pick is high-volatility and barely "
                "ahead of the second-ranked pick, shift from a 91/9 sleeve to a more balanced sleeve instead of "
                "blindly concentrating in the top score."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top2_50_50", "top2_60_40"],
                "rank1_shift_min_volatility_20d_percentile": [0.80],
                "rank1_shift_max_score_margin": [0.05, 0.07],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 2,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.50,
                    "minimum_portfolio_max_drawdown": -0.12,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_total_return_desc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Proxy diagnostics on the current full713 frontier showed the unresolved tail comes mainly "
                        "from high-volatility first-rank crashes when the top score has weak separation. The formal "
                        "candidate must validate that a bounded confidence-weight function improves stability."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top2_50_50",
                    "rank1_shift_min_volatility_20d_percentile": 0.80,
                    "rank1_shift_max_score_margin": 0.05,
                },
                "screening_evidence": {
                    "source": "selected_top2_proxy_from_current_full713_frontier_pending_formal_replay",
                    "parent_model_spec_id": "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-d464f8ef856be002",
                    "parent_full713_best_trial_id": (
                        "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1:trial-001"
                    ),
                    "proxy_rule": "rank1_volatility_20d_percentile_ge_0_80_and_score_margin_le_0_05_shift_91_9_to_50_50",
                    "proxy_triggered_signal_dates": 86,
                    "proxy_negative_month_count": 11,
                    "proxy_parent_negative_month_count": 12,
                    "proxy_min_monthly_mean_net_excess": -0.0613,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0640,
                    "design_reason": (
                        "Industry concentration diagnostics did not explain the negative months. The next plausible "
                        "gap is overconfidence in high-risk first-ranked picks when rank separation is weak."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Keep the current confidence-shifted transition-defensive scorer, but test whether high-risk weak-"
                "margin dates should spread the sleeve across the top three ranked names instead of only balancing "
                "the first two ranks. Non-triggered dates keep the same effective 91/9 top2 allocation by assigning "
                "zero weight to rank 3 under the base top2 profile."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07, 0.09, 0.12, 0.15],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.63,
                    "minimum_portfolio_max_drawdown": -0.11,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "portfolio_total_return_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Compact top5 feature diagnostics on the current full713 frontier suggested that, when rank "
                        "1 is volatile and only weakly separated, adding a small rank3 sleeve improves path drawdown "
                        "and worst-month behavior without reducing the proxy edge."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "screening_evidence": {
                    "source": "compact_selected_top5_feature_join_from_current_full713_frontier",
                    "source_compact_join": "/tmp/stock_dashboard_confidence_frontier_top5_features_20260706.json",
                    "parent_model_spec_id": "confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1",
                    "parent_full713_artifact_id": "model-comparison-report-91f1cfae6d8334f7",
                    "parent_full713_best_trial_id": (
                        "confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1:trial-001"
                    ),
                    "proxy_rule": (
                        "rank1_volatility_20d_percentile_ge_0_78_and_score_margin_le_0_07_shift_91_9_to_50_30_20"
                    ),
                    "proxy_triggered_signal_dates": 130,
                    "proxy_negative_month_count": 11,
                    "proxy_parent_negative_month_count": 11,
                    "proxy_path_drawdown_sum": -1.9825,
                    "proxy_parent_path_drawdown_sum": -2.1352,
                    "proxy_min_monthly_mean_net_excess": -0.0544,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0626,
                    "proxy_mean_net_excess": 0.02024,
                    "proxy_parent_mean_net_excess": 0.01911,
                    "formal_full713_artifact_id": "model-comparison-report-e0d817a563cb53cf",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-0b21e799e5ee3c29",
                    "formal_full713_status": "current_frontier_blocked",
                    "formal_full713_best_trial_id": (
                        "top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1:trial-002"
                    ),
                    "formal_full713_portfolio_total_return": 1.7028,
                    "formal_full713_annualized_return": 0.4677,
                    "formal_full713_portfolio_max_drawdown": -0.0969,
                    "formal_full713_negative_month_count": 11,
                    "formal_full713_min_monthly_mean_net_excess": -0.0490,
                    "formal_full713_path_drawdown_sum": -1.9876,
                    "formal_full713_deflated_sharpe_confidence": 0.9837,
                    "formal_full713_alpha_t_stat": 3.8011,
                    "formal_full713_pbo_proxy": 0.0,
                    "formal_full713_remaining_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                        "governance_promotion_pending",
                    ],
                    "design_reason": (
                        "The previous confidence shift reduced overconcentration in rank 1, but the remaining "
                        "tail-risk dates still benefit from giving rank 3 a bounded sleeve when rank confidence is "
                        "weak. This must be confirmed by same-contract streaming full713 replay before acceptance."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Extend the current top3 tail-blended frontier with a signal-level cash switch for dates where "
                "the top-ranked name is already in an extreme 5d/20d overheat state, the market is still positive, "
                "and rank confidence is weak. The design targets the remaining path-stress dates without reverting "
                "to single-source v1-style momentum anchoring."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85, 0.90, 0.95, 0.98],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.70,
                    "minimum_portfolio_max_drawdown": -0.10,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "portfolio_total_return_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Compact top5 feature diagnostics on the blocked full713 frontier showed the worst path "
                        "stress concentrated on positive-benchmark dates where rank1 had extreme 5d/20d momentum "
                        "and only weak score separation; a narrow cash switch improved proxy path drawdown without "
                        "reducing total edge."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": "rank1_overheat_reversal_cash",
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.90,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                },
                "screening_evidence": {
                    "source": "compact_selected_top5_feature_join_from_current_full713_frontier",
                    "source_compact_join": "/tmp/stock_dashboard_confidence_frontier_top5_features_20260706.json",
                    "parent_model_spec_id": (
                        "top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
                    ),
                    "parent_full713_artifact_id": "model-comparison-report-e0d817a563cb53cf",
                    "parent_full713_best_trial_id": (
                        "top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1:trial-002"
                    ),
                    "proxy_rule": "cash_overheat_m0.03_ret200.98_ret50.85_bm20_gt_0.04",
                    "proxy_triggered_signal_dates": 20,
                    "proxy_negative_month_count": 10,
                    "proxy_parent_negative_month_count": 11,
                    "proxy_path_drawdown_sum": -1.6967,
                    "proxy_parent_path_drawdown_sum": -1.9825,
                    "proxy_min_monthly_mean_net_excess": -0.0480,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0544,
                    "proxy_mean_net_excess": 0.02119,
                    "proxy_parent_mean_net_excess": 0.02024,
                    "proxy_deflated_sharpe_confidence": 0.9911,
                    "proxy_parent_deflated_sharpe_confidence": 0.9832,
                    "formal_full713_artifact_id": "model-comparison-report-773d4ba2fda17834",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-15c92007b2e7ac5e",
                    "formal_full713_status": "return_frontier_blocked",
                    "formal_full713_best_trial_id": (
                        "overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
                        ":trial-000"
                    ),
                    "formal_full713_portfolio_total_return": 1.7712,
                    "formal_full713_annualized_return": 0.4819,
                    "formal_full713_portfolio_max_drawdown": -0.0923,
                    "formal_full713_negative_month_count": 11,
                    "formal_full713_min_monthly_mean_net_excess": -0.0470,
                    "formal_full713_path_drawdown_sum": -1.6164,
                    "formal_full713_deflated_sharpe_confidence": 0.9914,
                    "formal_full713_alpha_t_stat": 4.0470,
                    "formal_full713_pbo_proxy": 0.0,
                    "formal_full713_remaining_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                        "governance_promotion_pending",
                    ],
                    "design_reason": (
                        "The trigger is based on ranked signal state after model scoring, not on known strong-stock "
                        "identity. It is intentionally narrow and must beat the current top3 full713 frontier on "
                        "return, max drawdown, DSR/PBO, negative-month count, and path-stress before promotion."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Test whether the remaining drawdown after the overheat-cash challenger comes from weak-market "
                "dates where the scorer retreats into very low-volatility, low-beta rank1 names that still lose "
                "during broad market stress. This keeps the same scorer and top3 tail blend, adding only a "
                "post-score weak-regime cash switch."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
                "weak_regime_low_volatility_cash",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
                "weak_low_vol_max_benchmark_return_10d": [-0.02],
                "weak_low_vol_min_benchmark_volatility_20d": [0.03, 0.035, 0.04, 0.045],
                "weak_low_vol_min_low_volatility_percentile": [0.95],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.77,
                    "minimum_portfolio_max_drawdown": -0.10,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "portfolio_total_return_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "After overheat-cash replay, the remaining maximum drawdown concentrated in weak benchmark "
                        "periods where rank1 had very high low-volatility percentile. Compact replay suggested "
                        "that a weak-market low-volatility cash switch can reduce negative months and improve "
                        "path drawdown while preserving the return floor."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": "rank1_overheat_or_weak_regime_low_volatility_cash",
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.85,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                    "weak_regime_low_volatility_cash": {
                        "enabled": True,
                        "max_benchmark_return_10d": -0.02,
                        "min_benchmark_volatility_20d": 0.035,
                        "min_low_volatility_percentile": 0.95,
                    },
                },
                "screening_evidence": {
                    "source": "compact_selected_top5_feature_join_after_overheat_cash_frontier",
                    "source_compact_join": "/tmp/stock_dashboard_confidence_frontier_top5_features_20260706.json",
                    "parent_model_spec_id": (
                        "overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
                    ),
                    "parent_full713_artifact_id": "model-comparison-report-773d4ba2fda17834",
                    "parent_full713_best_trial_id": (
                        "overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
                        ":trial-000"
                    ),
                    "proxy_rule": "cash_bm10_lt_minus_0.02_and_bvol_gt_0.035_and_rank1_low_vol_gt_0.95",
                    "proxy_triggered_signal_dates": 69,
                    "proxy_negative_month_count": 9,
                    "proxy_parent_negative_month_count": 10,
                    "proxy_path_drawdown_sum": -1.5036,
                    "proxy_parent_path_drawdown_sum": -1.6967,
                    "proxy_min_monthly_mean_net_excess": -0.0480,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0480,
                    "proxy_mean_net_excess": 0.02325,
                    "proxy_parent_mean_net_excess": 0.02119,
                    "formal_full713_artifact_id": "model-comparison-report-993b0e970e7f74e7",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-972a82e6882ee40c",
                    "formal_full713_status": "stability_frontier_blocked",
                    "formal_full713_best_trial_id": (
                        "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
                        ":trial-001"
                    ),
                    "formal_full713_portfolio_total_return": 1.7040,
                    "formal_full713_annualized_return": 0.4680,
                    "formal_full713_portfolio_max_drawdown": -0.0927,
                    "formal_full713_negative_month_count": 9,
                    "formal_full713_min_monthly_mean_net_excess": -0.0470,
                    "formal_full713_path_drawdown_sum": -1.4874,
                    "formal_full713_deflated_sharpe_confidence": 0.9977,
                    "formal_full713_alpha_t_stat": 4.4956,
                    "formal_full713_pbo_proxy": 0.0,
                    "formal_full713_remaining_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                        "governance_promotion_pending",
                    ],
                    "post_replay_diagnostic": (
                        "Compact broad cash scan found no one-to-four-condition simple signal rule that cleared "
                        "path drawdown greater than -1.0 while preserving the Top3 proxy return floor; remaining "
                        "blockers should move to execution labels, sellability, fill and capacity constraints."
                    ),
                    "design_reason": (
                        "This is not a symbol/date filter: it tests a ranked-signal failure mode where the model "
                        "selects very low-volatility names during deteriorating benchmark conditions. It must pass "
                        "same-contract full713 replay before replacing the overheat-cash frontier."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Test whether the v3 path-stress tail is partly an overconfident Rank1 concentration failure. "
                "The candidate keeps the v3 stability-preferred multi-factor scorer, weak-regime cash switch, "
                "adaptive exits and top3 tail blending, then adds a narrow post-score cash switch when Rank1's "
                "score margin over Rank2 is unusually large."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
                "weak_regime_low_volatility_cash",
                "high_confidence_tail_cash",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
                "weak_low_vol_max_benchmark_return_10d": [-0.02],
                "weak_low_vol_min_benchmark_volatility_20d": [0.035],
                "weak_low_vol_min_low_volatility_percentile": [0.95],
                "rank1_high_confidence_min_score_margin": [0.10, 0.12, 0.15, 0.20],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.60,
                    "minimum_portfolio_max_drawdown": -0.09,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "portfolio_total_return_desc",
                        "portfolio_path_drawdown_sum_desc",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The v3 strict-label proxy scan found that cashing out unusually large Rank1/Rank2 "
                        "score-margin dates can improve path drawdown without hurting return. Full replay is "
                        "required because the scan only used selected picks."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_cash",
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.85,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                    "weak_regime_low_volatility_cash": {
                        "enabled": True,
                        "max_benchmark_return_10d": -0.02,
                        "min_benchmark_volatility_20d": 0.035,
                        "min_low_volatility_percentile": 0.95,
                    },
                    "rank1_high_confidence_cash": {
                        "enabled": True,
                        "min_score_margin": 0.10,
                    },
                },
                "screening_evidence": {
                    "source": "v3_stability_selected_pick_feature_join_and_path_stress_proxy_scan",
                    "source_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_stability_selected_pick_feature_join_20260706.json"
                    ),
                    "source_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_stability_path_stress_proxy_scan_20260706.json"
                    ),
                    "parent_model_spec_id": (
                        "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
                    ),
                    "parent_label_version": "shortpick_model_executable_label_matrix:v3",
                    "parent_full713_artifact_id": "model-comparison-report-13f09aeca20a8b0d",
                    "parent_full713_best_trial_id": (
                        "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
                        ":trial-001"
                    ),
                    "proxy_rule": "cash_when_rank1_score_margin_ge_0_10",
                    "proxy_triggered_signal_dates": 12,
                    "proxy_portfolio_total_return": 1.7083,
                    "proxy_parent_portfolio_total_return": 1.6349,
                    "proxy_portfolio_max_drawdown": -0.0868,
                    "proxy_parent_portfolio_max_drawdown": -0.0844,
                    "proxy_negative_month_count": 11,
                    "proxy_parent_negative_month_count": 10,
                    "proxy_path_drawdown_sum": -1.4874,
                    "proxy_parent_path_drawdown_sum": -1.5563,
                    "proxy_min_monthly_mean_net_excess": -0.0306,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0385,
                    "design_reason": (
                        "This is a model-output confidence-tail control, not a known-winner or single-source "
                        "stock filter. It tests whether unusually large Rank1 separation is an overconfidence "
                        "state that hurts path stability under v3 execution labels."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Test the label-v3 path-tail diagnosis that the largest remaining drawdown is driven by "
                "euphoric market windows where Rank1 is extremely strong on 5d/20d momentum, volume expansion "
                "and volatility while absolute liquidity remains modest. This extends the high-confidence "
                "tail-cash frontier with a narrow market-euphoric volume-tail cash switch."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
                "weak_regime_low_volatility_cash",
                "high_confidence_tail_cash",
                "market_euphoric_volume_tail_cash",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
                "weak_low_vol_max_benchmark_return_10d": [-0.02],
                "weak_low_vol_min_benchmark_volatility_20d": [0.035],
                "weak_low_vol_min_low_volatility_percentile": [0.95],
                "rank1_high_confidence_min_score_margin": [0.10],
                "rank1_tail_min_benchmark_return_20d": [0.04, 0.05],
                "rank1_tail_min_return_5d_percentile": [0.98],
                "rank1_tail_min_return_20d_percentile": [0.94],
                "rank1_tail_min_amount_10d_vs_20d_percentile": [0.90],
                "rank1_tail_min_volatility_20d_percentile": [0.55],
                "rank1_tail_max_avg_amount_20d": [200_000_000, 300_000_000],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.70,
                    "minimum_portfolio_max_drawdown": -0.09,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "portfolio_total_return_desc",
                        "portfolio_path_drawdown_sum_desc",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The retained v3 selected-pick proxy scan found a narrow market-euphoric volume-tail "
                        "state that improves total return and path drawdown versus the current high-confidence "
                        "tail-cash frontier. Full replay is still required because the scan is selected-pick only."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": (
                        "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_"
                        "market_euphoric_volume_tail_cash"
                    ),
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.85,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                    "weak_regime_low_volatility_cash": {
                        "enabled": True,
                        "max_benchmark_return_10d": -0.02,
                        "min_benchmark_volatility_20d": 0.035,
                        "min_low_volatility_percentile": 0.95,
                    },
                    "rank1_high_confidence_cash": {
                        "enabled": True,
                        "min_score_margin": 0.10,
                    },
                    "rank1_market_euphoric_volume_tail_cash": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.04,
                        "min_return_5d_percentile": 0.98,
                        "min_return_20d_percentile": 0.94,
                        "min_amount_10d_vs_20d_percentile": 0.90,
                        "min_volatility_20d_percentile": 0.55,
                        "max_avg_amount_20d": 300_000_000,
                    },
                },
                "screening_evidence": {
                    "source": "v3_high_confidence_selected_pick_feature_join_and_path_tail_proxy_scan",
                    "source_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_high_confidence_selected_pick_feature_join_20260706.json"
                    ),
                    "source_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_high_confidence_path_tail_proxy_scan_20260706.json"
                    ),
                    "parent_model_spec_id": (
                        "high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1"
                    ),
                    "parent_label_version": "shortpick_model_executable_label_matrix:v3",
                    "parent_full713_artifact_id": "model-comparison-report-9169bed0e1736fe2",
                    "parent_full713_best_trial_id": (
                        "high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1:trial-000"
                    ),
                    "proxy_rule": (
                        "cash_when_rank1_market_20d_ge_0_04_return5_ge_0_98_return20_ge_0_94_"
                        "amount_expansion_ge_0_90_volatility_ge_0_55_avg_amount20_le_300m"
                    ),
                    "proxy_triggered_signal_dates": 20,
                    "proxy_portfolio_total_return": 1.8088,
                    "proxy_parent_portfolio_total_return": 1.7083,
                    "proxy_portfolio_max_drawdown": -0.0868,
                    "proxy_parent_portfolio_max_drawdown": -0.0868,
                    "proxy_negative_month_count": 11,
                    "proxy_parent_negative_month_count": 11,
                    "proxy_path_drawdown_sum": -1.4519,
                    "proxy_parent_path_drawdown_sum": -1.4874,
                    "proxy_min_monthly_mean_net_excess": -0.0306,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0306,
                    "design_reason": (
                        "This condition is a path-tail state diagnosis from the v3 high-confidence frontier: "
                        "strong benchmark tape plus overheated, volume-expanding, moderately illiquid Rank1 names. "
                        "It is not a known-winner rule and remains blocked unless same-contract replay clears gates."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "weak_low_liquidity_tail_cash_path_tail_overheat_high_confidence_top3_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Test the next label-v3 path blocker after market-euphoric tail cash: low-volatility, "
                "low-turnover, low-absolute-liquidity Rank1 defensive names during weak benchmark conditions. "
                "This is a stability challenger for the current path-tail frontier, not a replacement unless "
                "same-contract replay preserves the return/DSR floor while improving path and negative months."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
                "weak_regime_low_volatility_cash",
                "high_confidence_tail_cash",
                "market_euphoric_volume_tail_cash",
                "weak_low_liquidity_tail_cash",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
                "weak_low_vol_max_benchmark_return_10d": [-0.02],
                "weak_low_vol_min_benchmark_volatility_20d": [0.035],
                "weak_low_vol_min_low_volatility_percentile": [0.95],
                "rank1_high_confidence_min_score_margin": [0.10],
                "rank1_tail_min_benchmark_return_20d": [0.04],
                "rank1_tail_min_return_5d_percentile": [0.98],
                "rank1_tail_min_return_20d_percentile": [0.94],
                "rank1_tail_min_amount_10d_vs_20d_percentile": [0.90],
                "rank1_tail_min_volatility_20d_percentile": [0.55],
                "rank1_tail_max_avg_amount_20d": [300_000_000],
                "rank1_weak_tail_max_benchmark_return_20d": [-0.04, -0.02],
                "rank1_weak_tail_max_benchmark_return_10d": [-0.005],
                "rank1_weak_tail_min_low_volatility_percentile": [0.97],
                "rank1_weak_tail_max_turnover_rate_percentile": [0.05],
                "rank1_weak_tail_max_avg_amount_20d": [50_000_000, 80_000_000],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.70,
                    "minimum_portfolio_max_drawdown": -0.09,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "portfolio_path_drawdown_sum_desc",
                        "negative_month_count_asc",
                        "portfolio_total_return_desc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "The current label-v3 return frontier still fails path stress. A retained selected-pick "
                        "proxy scan found a weak-market, low-volatility, low-liquidity Rank1 tail that improves "
                        "path drawdown and negative-month count while preserving a +170% return floor."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": (
                        "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                        "weak_low_liquidity_tail_cash"
                    ),
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.85,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                    "weak_regime_low_volatility_cash": {
                        "enabled": True,
                        "max_benchmark_return_10d": -0.02,
                        "min_benchmark_volatility_20d": 0.035,
                        "min_low_volatility_percentile": 0.95,
                    },
                    "rank1_high_confidence_cash": {
                        "enabled": True,
                        "min_score_margin": 0.10,
                    },
                    "rank1_market_euphoric_volume_tail_cash": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.04,
                        "min_return_5d_percentile": 0.98,
                        "min_return_20d_percentile": 0.94,
                        "min_amount_10d_vs_20d_percentile": 0.90,
                        "min_volatility_20d_percentile": 0.55,
                        "max_avg_amount_20d": 300_000_000,
                    },
                    "rank1_weak_low_liquidity_tail_cash": {
                        "enabled": True,
                        "max_benchmark_return_20d": -0.04,
                        "max_benchmark_return_10d": -0.005,
                        "min_low_volatility_percentile": 0.97,
                        "max_turnover_rate_percentile": 0.05,
                        "max_avg_amount_20d": 50_000_000,
                    },
                },
                "screening_evidence": {
                    "source": "v3_path_tail_frontier_weak_low_liquidity_proxy_scan",
                    "source_rank1_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_path_tail_frontier_aug_sep_2024_rank1_feature_join_20260706.json"
                    ),
                    "source_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_path_tail_frontier_weak_low_liquidity_proxy_scan_20260706.json"
                    ),
                    "parent_model_spec_id": (
                        "path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1"
                    ),
                    "parent_label_version": "shortpick_model_executable_label_matrix:v3",
                    "parent_full713_artifact_id": "model-comparison-report-00602b973c354176",
                    "parent_full713_best_trial_id": (
                        "path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1:trial-002"
                    ),
                    "proxy_rule": (
                        "cash_when_rank1_benchmark20_le_minus_0_04_benchmark10_le_minus_0_005_"
                        "low_vol_ge_0_97_turnover_le_0_05_avg_amount20_le_50m"
                    ),
                    "proxy_triggered_signal_dates": 9,
                    "proxy_portfolio_total_return": 1.7494,
                    "proxy_parent_portfolio_total_return": 1.8088,
                    "proxy_portfolio_max_drawdown": -0.0868,
                    "proxy_parent_portfolio_max_drawdown": -0.0868,
                    "proxy_negative_month_count": 10,
                    "proxy_parent_negative_month_count": 11,
                    "proxy_path_drawdown_sum": -1.3019,
                    "proxy_parent_path_drawdown_sum": -1.4519,
                    "proxy_min_monthly_mean_net_excess": -0.0302,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0306,
                    "design_reason": (
                        "This is a second-stage path-tail diagnosis. It deliberately trades part of the new "
                        "return frontier for path/month stability, and should remain downgraded unless formal "
                        "v3 replay materially reduces the remaining blockers without falling below the floor."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Test the full-window label-v3 proxy diagnosis after the weak-low-liquidity stability frontier: "
                "Rank1 names with very low absolute liquidity but crowded short/medium momentum, strong amount "
                "expansion and elevated volatility can hurt monthly/path stability, while the remaining path "
                "blocker is a weak-market low-volatility/low-turnover defensive grind. This is a bounded "
                "combination challenger and must remain blocked unless same-contract replay preserves the "
                "frontier floors while materially improving path/month stress."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
                "weak_regime_low_volatility_cash",
                "high_confidence_tail_cash",
                "market_euphoric_volume_tail_cash",
                "weak_low_liquidity_tail_cash",
                "congested_low_liquidity_momentum_tail_cash",
                "high_turnover_momentum_tail_cash",
                "weak_defensive_grind_tail_cash",
                "residual_momentum_amount_tail_scale",
                "rank_position_scaling",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
                "weak_low_vol_max_benchmark_return_10d": [-0.02],
                "weak_low_vol_min_benchmark_volatility_20d": [0.035],
                "weak_low_vol_min_low_volatility_percentile": [0.95],
                "rank1_high_confidence_min_score_margin": [0.10],
                "rank1_tail_min_benchmark_return_20d": [0.04],
                "rank1_tail_min_return_5d_percentile": [0.98],
                "rank1_tail_min_return_20d_percentile": [0.94],
                "rank1_tail_min_amount_10d_vs_20d_percentile": [0.90],
                "rank1_tail_min_volatility_20d_percentile": [0.55],
                "rank1_tail_max_avg_amount_20d": [300_000_000],
                "rank1_weak_tail_max_benchmark_return_20d": [-0.04],
                "rank1_weak_tail_max_benchmark_return_10d": [-0.005],
                "rank1_weak_tail_min_low_volatility_percentile": [0.97],
                "rank1_weak_tail_max_turnover_rate_percentile": [0.05],
                "rank1_weak_tail_max_avg_amount_20d": [50_000_000],
                "rank1_congested_tail_min_benchmark_return_20d": [-0.02],
                "rank1_congested_tail_max_benchmark_return_10d": [0.01],
                "rank1_congested_tail_min_return_5d_percentile": [0.94],
                "rank1_congested_tail_min_return_20d_percentile": [0.90],
                "rank1_congested_tail_min_amount_10d_vs_20d_percentile": [0.88],
                "rank1_congested_tail_min_volatility_20d_percentile": [0.55],
                "rank1_congested_tail_max_avg_amount_20d": [100_000_000],
                "rank1_high_turnover_tail_min_benchmark_return_20d": [0.0],
                "rank1_high_turnover_tail_max_benchmark_return_10d": [0.02],
                "rank1_high_turnover_tail_min_return_5d_percentile": [0.98],
                "rank1_high_turnover_tail_min_return_20d_percentile": [0.94],
                "rank1_high_turnover_tail_min_amount_10d_vs_20d_percentile": [0.95],
                "rank1_high_turnover_tail_min_volatility_20d_percentile": [0.65],
                "rank1_high_turnover_tail_min_turnover_rate_percentile": [0.85],
                "rank1_high_turnover_tail_max_avg_amount_20d": [300_000_000],
                "rank1_weak_grind_max_benchmark_return_20d": [-0.04],
                "rank1_weak_grind_max_benchmark_return_10d": [0.01],
                "rank1_weak_grind_max_benchmark_volatility_20d": [None],
                "rank1_weak_grind_min_low_volatility_percentile": [0.97, 0.98],
                "rank1_weak_grind_max_turnover_rate_percentile": [0.07],
                "rank1_weak_grind_max_avg_amount_20d": [80_000_000],
                "rank1_weak_grind_position_scale": [0.2, 0.3],
                "rank1_residual_momentum_min_benchmark_return_20d": [0.03],
                "rank1_residual_momentum_max_benchmark_return_10d": [0.04],
                "rank1_residual_momentum_min_return_5d_percentile": [0.98],
                "rank1_residual_momentum_min_return_20d_percentile": [0.96],
                "rank1_residual_momentum_min_amount_10d_vs_20d_percentile": [0.95],
                "rank1_residual_momentum_min_volatility_20d_percentile": [0.30],
                "rank1_residual_momentum_max_avg_amount_20d": [600_000_000],
                "rank1_residual_momentum_position_scale": [0.3],
                "rank1_rank_scale_min_benchmark_return_20d": [0.0],
                "rank1_rank_scale_max_benchmark_return_10d": [0.04],
                "rank1_rank_scale_min_return_5d_percentile": [0.90],
                "rank1_rank_scale_min_return_20d_percentile": [0.94],
                "rank1_rank_scale_min_amount_10d_vs_20d_percentile": [0.90],
                "rank1_rank_scale_min_volatility_20d_percentile": [0.55],
                "rank1_rank_scale_min_turnover_rate_percentile": [0.85],
                "rank1_rank_scale_max_avg_amount_20d": [100_000_000],
                "rank1_rank_scale_position_scale": [0.0],
                "rank1_extreme_rank_scale_min_benchmark_return_20d": [0.03],
                "rank1_extreme_rank_scale_max_benchmark_return_10d": [0.06],
                "rank1_extreme_rank_scale_min_return_5d_percentile": [0.98],
                "rank1_extreme_rank_scale_min_return_20d_percentile": [0.96],
                "rank1_extreme_rank_scale_min_amount_10d_vs_20d_percentile": [0.88],
                "rank1_extreme_rank_scale_min_volatility_20d_percentile": [0.30],
                "rank1_extreme_rank_scale_min_turnover_rate_percentile": [0.75],
                "rank1_extreme_rank_scale_max_avg_amount_20d": [600_000_000],
                "rank1_extreme_rank_scale_position_scale": [0.0],
                "rank1_neutral_chop_min_benchmark_return_20d": [-0.01],
                "rank1_neutral_chop_max_benchmark_return_20d": [0.03],
                "rank1_neutral_chop_max_benchmark_return_10d": [0.03],
                "rank1_neutral_chop_min_benchmark_volatility_20d": [0.04],
                "rank1_neutral_chop_min_return_5d_percentile": [0.64],
                "rank1_neutral_chop_max_return_20d_percentile": [0.97],
                "rank1_neutral_chop_min_amount_10d_vs_20d_percentile": [0.59],
                "rank1_neutral_chop_max_drawdown_20d": [-0.003],
                "rank1_neutral_chop_max_avg_amount_20d": [2_300_000_000],
                "rank1_neutral_chop_position_scale": [0.0],
                "rank1_no_drawdown_min_max_drawdown_20d": [0.0],
                "rank1_no_drawdown_position_scale": [0.0],
                "rank1_high_position_pullback_min_max_drawdown_40d": [-0.04386677497969138],
                "rank1_high_position_pullback_max_return_1d": [-0.0166975881261594],
                "rank1_high_position_pullback_position_scale": [0.0],
                "rank1_low_score_high_position_max_score": [3.3878779420277896],
                "rank1_low_score_high_position_min_distance_from_40d_high": [-0.0020618556701030855],
                "rank1_low_score_high_position_position_scale": [0.0],
                "rank2_rank_scale_min_benchmark_return_20d": [0.0],
                "rank2_rank_scale_max_benchmark_return_10d": [0.02],
                "rank2_rank_scale_min_return_5d_percentile": [0.94],
                "rank2_rank_scale_min_return_20d_percentile": [0.90],
                "rank2_rank_scale_min_amount_10d_vs_20d_percentile": [0.94],
                "rank2_rank_scale_min_volatility_20d_percentile": [0.55],
                "rank2_rank_scale_min_turnover_rate_percentile": [0.85],
                "rank2_rank_scale_max_avg_amount_20d": [800_000_000],
                "rank2_rank_scale_position_scale": [0.0],
                "rank3_rank_scale_min_benchmark_return_20d": [0.03],
                "rank3_rank_scale_max_benchmark_return_10d": [0.06],
                "rank3_rank_scale_min_return_5d_percentile": [0.96],
                "rank3_rank_scale_min_return_20d_percentile": [0.90],
                "rank3_rank_scale_min_amount_10d_vs_20d_percentile": [0.90],
                "rank3_rank_scale_min_volatility_20d_percentile": [0.75],
                "rank3_rank_scale_min_turnover_rate_percentile": [0.75],
                "rank3_rank_scale_max_avg_amount_20d": [800_000_000],
                "rank3_rank_scale_position_scale": [0.0],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.70,
                    "minimum_portfolio_max_drawdown": -0.09,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "portfolio_path_drawdown_sum_desc",
                        "negative_month_count_asc",
                        "portfolio_total_return_desc",
                        "portfolio_max_drawdown_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "A full-window selected-pick proxy scan found a low-absolute-liquidity, high-momentum, "
                        "high-amount-expansion Rank1 tail that improves return and monthly/path stability versus "
                        "the weak-low-liquidity stability frontier. A follow-up scan found the remaining path "
                        "blocker in a weak-market defensive-grind tail. Full replay is required before candidate "
                        "status because both scans are selected-pick only."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": (
                        "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                        "weak_low_liquidity_or_congested_momentum_or_high_turnover_momentum_tail_cash"
                    ),
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.85,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                    "weak_regime_low_volatility_cash": {
                        "enabled": True,
                        "max_benchmark_return_10d": -0.02,
                        "min_benchmark_volatility_20d": 0.035,
                        "min_low_volatility_percentile": 0.95,
                    },
                    "rank1_high_confidence_cash": {
                        "enabled": True,
                        "min_score_margin": 0.10,
                    },
                    "rank1_market_euphoric_volume_tail_cash": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.04,
                        "min_return_5d_percentile": 0.98,
                        "min_return_20d_percentile": 0.94,
                        "min_amount_10d_vs_20d_percentile": 0.90,
                        "min_volatility_20d_percentile": 0.55,
                        "max_avg_amount_20d": 300_000_000,
                    },
                    "rank1_weak_low_liquidity_tail_cash": {
                        "enabled": True,
                        "max_benchmark_return_20d": -0.04,
                        "max_benchmark_return_10d": -0.005,
                        "min_low_volatility_percentile": 0.97,
                        "max_turnover_rate_percentile": 0.05,
                        "max_avg_amount_20d": 50_000_000,
                    },
                    "rank1_congested_low_liquidity_momentum_tail_cash": {
                        "enabled": True,
                        "min_benchmark_return_20d": -0.02,
                        "max_benchmark_return_10d": 0.01,
                        "min_return_5d_percentile": 0.94,
                        "min_return_20d_percentile": 0.90,
                        "min_amount_10d_vs_20d_percentile": 0.88,
                        "min_volatility_20d_percentile": 0.55,
                        "max_avg_amount_20d": 100_000_000,
                    },
                    "rank1_high_turnover_momentum_tail_cash": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.0,
                        "max_benchmark_return_10d": 0.02,
                        "min_return_5d_percentile": 0.98,
                        "min_return_20d_percentile": 0.94,
                        "min_amount_10d_vs_20d_percentile": 0.95,
                        "min_volatility_20d_percentile": 0.65,
                        "min_turnover_rate_percentile": 0.85,
                        "max_avg_amount_20d": 300_000_000,
                    },
                    "rank1_weak_defensive_grind_tail_cash": {
                        "enabled": False,
                        "max_benchmark_return_20d": -0.04,
                        "max_benchmark_return_10d": 0.01,
                        "max_benchmark_volatility_20d": None,
                        "min_low_volatility_percentile": 0.98,
                        "max_turnover_rate_percentile": 0.07,
                        "max_avg_amount_20d": 80_000_000,
                    },
                },
                "signal_position_scaling": {
                    "enabled": True,
                    "mode": "rank1_weak_defensive_grind_scale",
                    "max_benchmark_return_20d": -0.04,
                    "max_benchmark_return_10d": 0.01,
                    "min_low_volatility_percentile": 0.98,
                    "max_turnover_rate_percentile": 0.07,
                    "max_avg_amount_20d": 80_000_000,
                    "position_scale": 0.2,
                    "rank1_residual_momentum_amount_tail_scale": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.03,
                        "max_benchmark_return_10d": 0.04,
                        "min_return_5d_percentile": 0.98,
                        "min_return_20d_percentile": 0.96,
                        "min_amount_10d_vs_20d_percentile": 0.95,
                        "min_volatility_20d_percentile": 0.30,
                        "max_avg_amount_20d": 600_000_000,
                        "position_scale": 0.3,
                    },
                },
                "rank_position_scaling": {
                    "enabled": True,
                    "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                    "min_benchmark_return_20d": 0.0,
                    "max_benchmark_return_10d": 0.04,
                    "min_return_5d_percentile": 0.90,
                    "min_return_20d_percentile": 0.94,
                    "min_amount_10d_vs_20d_percentile": 0.90,
                    "min_volatility_20d_percentile": 0.55,
                    "min_turnover_rate_percentile": 0.85,
                    "max_avg_amount_20d": 100_000_000,
                    "position_scale": 0.0,
                    "rank1_extreme_momentum_turnover_scale": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.03,
                        "max_benchmark_return_10d": 0.06,
                        "min_return_5d_percentile": 0.98,
                        "min_return_20d_percentile": 0.96,
                        "min_amount_10d_vs_20d_percentile": 0.88,
                        "min_volatility_20d_percentile": 0.30,
                        "min_turnover_rate_percentile": 0.75,
                        "max_avg_amount_20d": 600_000_000,
                        "position_scale": 0.0,
                    },
                    "rank1_neutral_chop_scale": {
                        "enabled": True,
                        "min_benchmark_return_20d": -0.01,
                        "max_benchmark_return_20d": 0.03,
                        "max_benchmark_return_10d": 0.03,
                        "min_benchmark_volatility_20d": 0.04,
                        "min_return_5d_percentile": 0.64,
                        "max_return_20d_percentile": 0.97,
                        "min_amount_10d_vs_20d_percentile": 0.59,
                        "max_drawdown_20d": -0.003,
                        "max_avg_amount_20d": 2_300_000_000,
                        "position_scale": 0.0,
                    },
                    "rank1_no_drawdown_scale": {
                        "enabled": True,
                        "min_max_drawdown_20d": 0.0,
                        "position_scale": 0.0,
                    },
                    "rank1_high_position_pullback_scale": {
                        "enabled": True,
                        "min_max_drawdown_40d": -0.04386677497969138,
                        "max_return_1d": -0.0166975881261594,
                        "position_scale": 0.0,
                    },
                    "rank1_low_score_high_position_scale": {
                        "enabled": True,
                        "max_score": 3.3878779420277896,
                        "min_distance_from_40d_high": -0.0020618556701030855,
                        "position_scale": 0.0,
                    },
                    "rank1_benchmark_momentum_pullback_scale": {
                        "enabled": True,
                        "min_benchmark_return_10d": 0.020298683992506783,
                        "min_return_20d_percentile": 0.9818865345181135,
                        "max_return_1d": -0.014409221902017322,
                        "position_scale": 0.0,
                    },
                    "rank2_high_momentum_turnover_scale": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.0,
                        "max_benchmark_return_10d": 0.02,
                        "min_return_5d_percentile": 0.94,
                        "min_return_20d_percentile": 0.90,
                        "min_amount_10d_vs_20d_percentile": 0.94,
                        "min_volatility_20d_percentile": 0.55,
                        "min_turnover_rate_percentile": 0.85,
                        "max_avg_amount_20d": 800_000_000,
                        "position_scale": 0.0,
                    },
                    "rank3_high_momentum_turnover_scale": {
                        "enabled": True,
                        "min_benchmark_return_20d": 0.03,
                        "max_benchmark_return_10d": 0.06,
                        "min_return_5d_percentile": 0.96,
                        "min_return_20d_percentile": 0.90,
                        "min_amount_10d_vs_20d_percentile": 0.90,
                        "min_volatility_20d_percentile": 0.75,
                        "min_turnover_rate_percentile": 0.75,
                        "max_avg_amount_20d": 800_000_000,
                        "position_scale": 0.0,
                    },
                },
                "screening_evidence": {
                    "source": "v3_current_frontier_negative_month_extra_scale_proxy_scan",
                    "source_selected_pick_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_stability_frontier_full_selected_pick_feature_join_20260706.json"
                    ),
                    "source_congested_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_stability_frontier_full_congested_momentum_proxy_scan_20260706.json"
                    ),
                    "source_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_congested_frontier_weak_defensive_grind_proxy_scan_20260706.json"
                    ),
                    "source_negative_month_extra_scale_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_current_frontier_negative_month_extra_scale_proxy_scan_20260706.json"
                    ),
                    "source_residual_frontier_selected_pick_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_residual_momentum_frontier_selected_pick_feature_join_20260706.json"
                    ),
                    "source_residual_frontier_high_risk_tail_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_residual_momentum_frontier_high_risk_tail_proxy_scan_20260706.json"
                    ),
                    "source_high_turnover_frontier_rank_level_scaling_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_high_turnover_frontier_rank_level_scaling_proxy_scan_20260706.json"
                    ),
                    "source_rank1_scaled_frontier_remaining_negative_month_rank_scale_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank1_scaled_frontier_remaining_negative_month_rank_scale_scan_20260706.json"
                    ),
                    "source_rank1_extreme_frontier_targeted_single_rule_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank1_extreme_frontier_targeted_single_rule_proxy_scan_20260706.json"
                    ),
                    "source_rank2_frontier_remaining_negative_month_diagnostic": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank2_frontier_remaining_negative_month_diagnostic_20260706.json"
                    ),
                    "source_rank2_frontier_combo_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank2_frontier_combo_proxy_scan_20260706.json"
                    ),
                    "source_rank3_frontier_manual_negative_month_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank3_frontier_manual_negative_month_proxy_scan_20260706.json"
                    ),
                    "source_neutral_chop_frontier_remaining_negative_month_diagnostic": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_neutral_chop_frontier_remaining_negative_month_diagnostic_20260707.json"
                    ),
                    "source_neutral_chop_frontier_bounded_negative_month_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_neutral_chop_frontier_bounded_negative_month_proxy_scan_20260707.json"
                    ),
                    "source_neutral_chop_frontier_low_adv_capacity_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_neutral_chop_frontier_low_adv_capacity_proxy_scan_20260707.json"
                    ),
                    "source_rank2_low_adv_capacity_formal_rejection": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank2_low_adv_capacity_formal_rejection_20260707.json"
                    ),
                    "source_neutral_chop_frontier_adv_capacity_diagnostic": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_neutral_chop_frontier_adv_capacity_diagnostic_20260707.json"
                    ),
                    "source_neutral_chop_frontier_capacity_adjusted_net_proxy": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_neutral_chop_frontier_capacity_adjusted_net_proxy_20260707.json"
                    ),
                    "source_neutral_chop_frontier_negative_month_expanded_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_neutral_chop_frontier_negative_month_expanded_proxy_scan_20260707.json"
                    ),
                    "source_no_drawdown_frontier_capacity_feature_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_no_drawdown_frontier_capacity_feature_proxy_scan_20260707.json"
                    ),
                    "source_rank1_low_adv_turnover_capacity_formal_rejection": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_rank1_low_adv_turnover_capacity_formal_rejection_20260707.json"
                    ),
                    "source_no_drawdown_frontier_selected_pick_feature_label_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_no_drawdown_frontier_selected_pick_feature_label_join_20260707.json"
                    ),
                    "source_no_drawdown_frontier_total_curve_proxy_scan": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_v3_no_drawdown_frontier_two_stage_total_curve_proxy_scan_20260707.json"
                    ),
                    "parent_model_spec_id": (
                        "congested_low_liquidity_momentum_tail_cash_weak_low_liquidity_top3_20d_v1"
                    ),
                    "parent_label_version": "shortpick_model_executable_label_matrix:v3",
                    "parent_full713_artifact_id": "model-comparison-report-91c4df75fc20764d",
                    "parent_full713_best_trial_id": (
                        "congested_low_liquidity_momentum_tail_cash_weak_low_liquidity_top3_20d_v1:trial-001"
                    ),
                    "proxy_rule": (
                        "also_cash_when_rank1_benchmark20_le_minus_0_04_benchmark10_le_0_01_"
                        "low_vol_ge_0_98_turnover_le_0_07_avg_amount20_le_80m"
                    ),
                    "proxy_triggered_signal_dates": 7,
                    "proxy_portfolio_total_return": 2.0488,
                    "proxy_parent_portfolio_total_return": 2.0385,
                    "proxy_portfolio_max_drawdown": -0.0433,
                    "proxy_parent_portfolio_max_drawdown": -0.0433,
                    "proxy_negative_month_count": 9,
                    "proxy_parent_negative_month_count": 9,
                    "proxy_path_drawdown_sum": -0.9661,
                    "proxy_parent_path_drawdown_sum": -1.2166,
                    "proxy_min_monthly_mean_net_excess": -0.0268,
                    "proxy_parent_min_monthly_mean_net_excess": -0.0268,
                    "residual_momentum_proxy_rule": (
                        "also_scale_rank1_benchmark20_ge_0_03_benchmark10_le_0_04_"
                        "return5_ge_0_98_return20_ge_0_96_amount_expansion_ge_0_95_"
                        "volatility_ge_0_30_avg_amount20_le_600m_to_0_3"
                    ),
                    "residual_momentum_proxy_triggered_signal_dates": 12,
                    "residual_momentum_proxy_portfolio_total_return": 2.0846,
                    "residual_momentum_proxy_parent_portfolio_total_return": 2.0488,
                    "residual_momentum_proxy_path_drawdown_sum": -0.8905,
                    "residual_momentum_proxy_parent_path_drawdown_sum": -0.9661,
                    "residual_momentum_proxy_negative_month_count": 9,
                    "residual_momentum_proxy_parent_negative_month_count": 9,
                    "high_turnover_momentum_tail_proxy_rule": (
                        "also_cash_rank1_benchmark20_ge_0_benchmark10_le_0_02_return5_ge_0_98_"
                        "return20_ge_0_94_amount_expansion_ge_0_95_volatility_ge_0_65_"
                        "turnover_ge_0_85_avg_amount20_le_300m"
                    ),
                    "high_turnover_momentum_tail_proxy_triggered_signal_dates": 6,
                    "high_turnover_momentum_tail_proxy_portfolio_total_return": 2.1709,
                    "high_turnover_momentum_tail_proxy_parent_portfolio_total_return": 2.0846,
                    "high_turnover_momentum_tail_proxy_portfolio_max_drawdown": -0.0369,
                    "high_turnover_momentum_tail_proxy_parent_portfolio_max_drawdown": -0.0371,
                    "high_turnover_momentum_tail_proxy_path_drawdown_sum": -0.8905,
                    "high_turnover_momentum_tail_proxy_parent_path_drawdown_sum": -0.8905,
                    "high_turnover_momentum_tail_proxy_negative_month_count": 9,
                    "high_turnover_momentum_tail_proxy_parent_negative_month_count": 9,
                    "rank_level_scale_proxy_rule": (
                        "scale_rank1_to_0_when_benchmark20_ge_0_benchmark10_le_0_04_return5_ge_0_90_"
                        "return20_ge_0_94_amount_expansion_ge_0_90_volatility_ge_0_55_"
                        "turnover_ge_0_85_avg_amount20_le_100m"
                    ),
                    "rank_level_scale_proxy_triggered_rank1_picks": 6,
                    "rank_level_scale_proxy_portfolio_total_return": 2.2023,
                    "rank_level_scale_proxy_parent_portfolio_total_return": 2.1709,
                    "rank_level_scale_proxy_portfolio_max_drawdown": -0.0339,
                    "rank_level_scale_proxy_parent_portfolio_max_drawdown": -0.0369,
                    "rank_level_scale_proxy_path_drawdown_sum": -0.8905,
                    "rank_level_scale_proxy_parent_path_drawdown_sum": -0.8905,
                    "rank_level_scale_proxy_negative_month_count": 8,
                    "rank_level_scale_proxy_parent_negative_month_count": 9,
                    "extreme_rank_level_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_benchmark20_ge_0_03_benchmark10_le_0_06_"
                        "return5_ge_0_98_return20_ge_0_96_amount_expansion_ge_0_88_"
                        "volatility_ge_0_30_turnover_ge_0_75_avg_amount20_le_600m"
                    ),
                    "extreme_rank_level_scale_proxy_triggered_rank1_picks": 14,
                    "extreme_rank_level_scale_proxy_portfolio_total_return": 2.2758,
                    "extreme_rank_level_scale_proxy_parent_portfolio_total_return": 2.2110,
                    "extreme_rank_level_scale_proxy_portfolio_max_drawdown": -0.0328,
                    "extreme_rank_level_scale_proxy_parent_portfolio_max_drawdown": -0.0329,
                    "extreme_rank_level_scale_proxy_path_drawdown_sum": -0.8905,
                    "extreme_rank_level_scale_proxy_parent_path_drawdown_sum": -0.8905,
                    "extreme_rank_level_scale_proxy_negative_month_count": 7,
                    "extreme_rank_level_scale_proxy_parent_negative_month_count": 8,
                    "extreme_rank_level_scale_formal_full713_artifact_id": (
                        "model-comparison-report-e13ac319e2fc2c94"
                    ),
                    "extreme_rank_level_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-273a8a8a8c2dee63"
                    ),
                    "extreme_rank_level_scale_formal_full713_total_return": 2.2786,
                    "extreme_rank_level_scale_formal_full713_annualized_return": 0.5813,
                    "extreme_rank_level_scale_formal_full713_max_drawdown": -0.0328,
                    "extreme_rank_level_scale_formal_full713_negative_month_count": 7,
                    "extreme_rank_level_scale_formal_full713_path_drawdown_sum": -0.8905,
                    "extreme_rank_level_scale_formal_full713_dsr": 0.999999,
                    "extreme_rank_level_scale_formal_full713_pbo": 0.0,
                    "rank2_high_momentum_turnover_scale_proxy_rule": (
                        "also_scale_rank2_to_0_when_benchmark20_ge_0_benchmark10_le_0_02_"
                        "return5_ge_0_94_return20_ge_0_90_amount_expansion_ge_0_94_"
                        "volatility_ge_0_55_turnover_ge_0_85_avg_amount20_le_800m"
                    ),
                    "rank2_high_momentum_turnover_scale_proxy_triggered_rank2_picks": 24,
                    "rank2_high_momentum_turnover_scale_proxy_portfolio_total_return": 2.3021,
                    "rank2_high_momentum_turnover_scale_proxy_parent_portfolio_total_return": 2.2786,
                    "rank2_high_momentum_turnover_scale_proxy_portfolio_max_drawdown": -0.0328,
                    "rank2_high_momentum_turnover_scale_proxy_parent_portfolio_max_drawdown": -0.0328,
                    "rank2_high_momentum_turnover_scale_proxy_path_drawdown_sum": -0.8905,
                    "rank2_high_momentum_turnover_scale_proxy_parent_path_drawdown_sum": -0.8905,
                    "rank2_high_momentum_turnover_scale_proxy_negative_month_count": 6,
                    "rank2_high_momentum_turnover_scale_proxy_parent_negative_month_count": 7,
                    "rank2_high_momentum_turnover_scale_formal_full713_artifact_id": (
                        "model-comparison-report-e3c25f696d53e504"
                    ),
                    "rank2_high_momentum_turnover_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-c2b9db7e29b74f5d"
                    ),
                    "rank2_high_momentum_turnover_scale_formal_full713_total_return": 2.3029,
                    "rank2_high_momentum_turnover_scale_formal_full713_annualized_return": 0.5858,
                    "rank2_high_momentum_turnover_scale_formal_full713_max_drawdown": -0.0328,
                    "rank2_high_momentum_turnover_scale_formal_full713_negative_month_count": 6,
                    "rank2_high_momentum_turnover_scale_formal_full713_path_drawdown_sum": -0.8905,
                    "rank2_high_momentum_turnover_scale_formal_full713_dsr": 0.999999,
                    "rank2_high_momentum_turnover_scale_formal_full713_pbo": 0.0,
                    "rank3_high_momentum_turnover_scale_proxy_rule": (
                        "also_scale_rank3_to_0_when_benchmark20_ge_0_03_benchmark10_le_0_06_"
                        "return5_ge_0_96_return20_ge_0_90_amount_expansion_ge_0_90_"
                        "volatility_ge_0_75_turnover_ge_0_75_avg_amount20_le_800m"
                    ),
                    "rank3_high_momentum_turnover_scale_proxy_triggered_rank3_picks": 26,
                    "rank3_high_momentum_turnover_scale_proxy_portfolio_mean_return": 0.030248880014731187,
                    "rank3_high_momentum_turnover_scale_proxy_parent_portfolio_mean_return": 0.030009103683360346,
                    "rank3_high_momentum_turnover_scale_proxy_negative_month_count": 6,
                    "rank3_high_momentum_turnover_scale_proxy_parent_negative_month_count": 6,
                    "rank3_high_momentum_turnover_scale_proxy_worst_month": -0.026820168196028824,
                    "rank3_high_momentum_turnover_scale_proxy_positive_date_rate": 0.45788667687595713,
                    "rank3_high_momentum_turnover_scale_formal_full713_artifact_id": (
                        "model-comparison-report-0c77a38610312156"
                    ),
                    "rank3_high_momentum_turnover_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-91205683e19b48a5"
                    ),
                    "rank3_high_momentum_turnover_scale_formal_full713_total_return": 2.3253,
                    "rank3_high_momentum_turnover_scale_formal_full713_annualized_return": 0.5899,
                    "rank3_high_momentum_turnover_scale_formal_full713_max_drawdown": -0.0328,
                    "rank3_high_momentum_turnover_scale_formal_full713_negative_month_count": 6,
                    "rank3_high_momentum_turnover_scale_formal_full713_path_drawdown_sum": -0.8905,
                    "rank3_high_momentum_turnover_scale_formal_full713_dsr": 0.999999,
                    "rank3_high_momentum_turnover_scale_formal_full713_pbo": 0.0,
                    "rank1_neutral_chop_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_benchmark20_between_minus_0_01_and_0_03_"
                        "benchmark10_le_0_03_benchmark_vol20_ge_0_04_return5_ge_0_64_"
                        "return20_le_0_97_amount_expansion_ge_0_59_max_drawdown20_le_minus_0_003_"
                        "avg_amount20_le_2300m"
                    ),
                    "rank1_neutral_chop_scale_proxy_triggered_rank1_picks": 28,
                    "rank1_neutral_chop_scale_proxy_negative_month_count": 5,
                    "rank1_neutral_chop_scale_proxy_parent_negative_month_count": 6,
                    "rank1_neutral_chop_scale_proxy_selected_pick_mean": 0.040382808443793765,
                    "rank1_neutral_chop_scale_proxy_parent_selected_pick_mean": 0.040229162219184246,
                    "rank1_neutral_chop_scale_proxy_worst_month": -0.036572956630948394,
                    "rank1_neutral_chop_scale_formal_full713_artifact_id": (
                        "model-comparison-report-3c8b5ce0286183c6"
                    ),
                    "rank1_neutral_chop_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-5bd0a8b3d768a339"
                    ),
                    "rank1_neutral_chop_scale_formal_full713_total_return": 2.3615,
                    "rank1_neutral_chop_scale_formal_full713_annualized_return": 0.5966,
                    "rank1_neutral_chop_scale_formal_full713_max_drawdown": -0.0328,
                    "rank1_neutral_chop_scale_formal_full713_negative_month_count": 5,
                    "rank1_neutral_chop_scale_formal_full713_path_drawdown_sum": -0.8905,
                    "rank1_neutral_chop_scale_formal_full713_dsr": 0.9999996,
                    "rank1_neutral_chop_scale_formal_full713_pbo": 0.0,
                    "rank1_neutral_chop_scale_fee_gate_refresh_report_id": (
                        "model-comparison-report-74afadcd87fa8bab"
                    ),
                    "rank1_neutral_chop_scale_fee_gate_refresh_governance_id": (
                        "governance-promotion-decision-835b37ab25b1a90b"
                    ),
                    "rank1_neutral_chop_scale_fee_gate_refresh_dashboard_registry_id": (
                        "dashboard-approved-projection-registry-50154c659adf9898"
                    ),
                    "rank1_neutral_chop_scale_fee_gate_refresh_covered_execution_gate_ids": [
                        "t_plus_1_execution_model",
                        "suspension_limit_buy_sellability",
                        "fees_slippage_stamp_tax",
                    ],
                    "rank1_neutral_chop_scale_fee_gate_refresh_remaining_execution_blockers": [
                        "adv_capacity_fill_rate",
                    ],
                    "rank1_neutral_chop_scale_adv_capacity_active_pick_count": 998,
                    "rank1_neutral_chop_scale_adv_capacity_below_full_fill_count": 27,
                    "rank1_neutral_chop_scale_adv_capacity_full_fill_rate": 0.9729458917835672,
                    "rank1_neutral_chop_scale_adv_capacity_min_fill_rate": 0.11855528021978023,
                    "rank1_neutral_chop_scale_adv_capacity_status": "blocked_adv_capacity_fill_rate",
                    "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_status": (
                        "rejected_mean_down_negative_months_up"
                    ),
                    "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_mean": 0.03708872265190931,
                    "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_parent_mean": 0.04038280844379376,
                    "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_negative_month_count": 6,
                    "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_parent_negative_month_count": 5,
                    "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_path_drawdown_sum": -0.735295829156255,
                    "rank2_low_adv_capacity_scale_proxy_rule": (
                        "also_scale_rank2_to_0_when_avg_amount20_lt_20m"
                    ),
                    "rank2_low_adv_capacity_scale_proxy_triggered_rank2_picks": 36,
                    "rank2_low_adv_capacity_scale_proxy_selected_pick_mean": 0.04062003339354903,
                    "rank2_low_adv_capacity_scale_proxy_parent_selected_pick_mean": 0.040382808443793765,
                    "rank2_low_adv_capacity_scale_proxy_negative_month_count": 5,
                    "rank2_low_adv_capacity_scale_proxy_parent_negative_month_count": 5,
                    "rank2_low_adv_capacity_scale_proxy_positive_date_rate": 0.6089613034623218,
                    "rank2_low_adv_capacity_scale_formal_full713_status": (
                        "rejected_total_and_annualized_return_below_neutral_chop_frontier"
                    ),
                    "rank2_low_adv_capacity_scale_formal_full713_artifact_id": (
                        "model-comparison-report-0faf6038b64791dc"
                    ),
                    "rank2_low_adv_capacity_scale_formal_full713_total_return": 2.3507,
                    "rank2_low_adv_capacity_scale_formal_full713_annualized_return": 0.5946,
                    "rank2_low_adv_capacity_scale_formal_full713_max_drawdown": -0.0328,
                    "rank2_low_adv_capacity_scale_formal_full713_negative_month_count": 5,
                    "rank1_no_drawdown_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_max_drawdown20_ge_0"
                    ),
                    "rank1_no_drawdown_scale_proxy_triggered_rank1_picks": 17,
                    "rank1_no_drawdown_scale_proxy_selected_pick_mean": 0.04064071259928586,
                    "rank1_no_drawdown_scale_proxy_parent_selected_pick_mean": 0.04038280844379376,
                    "rank1_no_drawdown_scale_proxy_negative_month_count": 4,
                    "rank1_no_drawdown_scale_proxy_parent_negative_month_count": 5,
                    "rank1_no_drawdown_scale_proxy_positive_date_rate": 0.615071283095723,
                    "rank1_no_drawdown_scale_proxy_path_drawdown_sum": -0.8877464748505162,
                    "rank1_no_drawdown_scale_proxy_parent_path_drawdown_sum": -0.8904722307472728,
                    "rank1_no_drawdown_scale_proxy_worst_month": -0.036572956630948394,
                    "rank1_no_drawdown_scale_formal_full713_status": "current_frontier_blocked",
                    "rank1_no_drawdown_scale_formal_full713_artifact_id": (
                        "model-comparison-report-481e82b0595596c8"
                    ),
                    "rank1_no_drawdown_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-3a5ae65140f49b02"
                    ),
                    "rank1_no_drawdown_scale_formal_full713_governance_id": (
                        "governance-promotion-decision-0205285afc980732"
                    ),
                    "rank1_no_drawdown_scale_formal_full713_dashboard_registry_id": (
                        "dashboard-approved-projection-registry-dd39a792b014227e"
                    ),
                    "rank1_no_drawdown_scale_formal_full713_total_return": 2.3683,
                    "rank1_no_drawdown_scale_formal_full713_annualized_return": 0.5978,
                    "rank1_no_drawdown_scale_formal_full713_max_drawdown": -0.0328,
                    "rank1_no_drawdown_scale_formal_full713_negative_month_count": 4,
                    "rank1_no_drawdown_scale_formal_full713_path_drawdown_sum": -0.8877,
                    "rank1_no_drawdown_scale_formal_full713_dsr": 0.9999997,
                    "rank1_no_drawdown_scale_formal_full713_pbo": 0.0,
                    "rank1_no_drawdown_scale_adv_capacity_active_pick_count": 985,
                    "rank1_no_drawdown_scale_adv_capacity_below_full_fill_count": 26,
                    "rank1_no_drawdown_scale_adv_capacity_full_fill_rate": 0.9736040609137055,
                    "rank1_no_drawdown_scale_adv_capacity_min_fill_rate": 0.11855528021978023,
                    "rank1_no_drawdown_scale_remaining_execution_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
                        "governance_promotion_pending",
                    ],
                    "rank1_low_adv_turnover_capacity_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_avg_amount20_lt_15m_and_turnover_percentile_gt_0_02"
                    ),
                    "rank1_low_adv_turnover_capacity_scale_proxy_triggered_rank1_picks": 15,
                    "rank1_low_adv_turnover_capacity_scale_proxy_selected_pick_mean": 0.04081895919587783,
                    "rank1_low_adv_turnover_capacity_scale_proxy_parent_selected_pick_mean": 0.04064071259928586,
                    "rank1_low_adv_turnover_capacity_scale_proxy_negative_month_count": 4,
                    "rank1_low_adv_turnover_capacity_scale_proxy_parent_negative_month_count": 4,
                    "rank1_low_adv_turnover_capacity_scale_proxy_path_drawdown_sum": -0.7758714812423868,
                    "rank1_low_adv_turnover_capacity_scale_proxy_parent_path_drawdown_sum": -0.8877464748505162,
                    "rank1_low_adv_turnover_capacity_scale_proxy_active_below_full_fill_count": 13,
                    "rank1_low_adv_turnover_capacity_scale_proxy_parent_active_below_full_fill_count": 26,
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_status": (
                        "rejected_total_and_annualized_return_below_no_drawdown_frontier"
                    ),
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_artifact_id": (
                        "model-comparison-report-66c772ffff0a9c05"
                    ),
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_total_return": 2.2319,
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_annualized_return": 0.5726,
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_max_drawdown": -0.0328,
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_path_drawdown_sum": -0.7759,
                    "rank1_low_adv_turnover_capacity_scale_formal_full713_negative_month_count": 4,
                    "rank1_high_position_pullback_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_max_drawdown40_ge_minus_0_04386677497969138_"
                        "and_return1d_le_minus_0_0166975881261594"
                    ),
                    "rank1_high_position_pullback_scale_proxy_triggered_rank1_picks": 11,
                    "rank1_high_position_pullback_scale_proxy_selected_pick_mean": 0.04117083303597417,
                    "rank1_high_position_pullback_scale_proxy_parent_selected_pick_mean": 0.04064071259928586,
                    "rank1_high_position_pullback_scale_proxy_negative_month_count": 3,
                    "rank1_high_position_pullback_scale_proxy_parent_negative_month_count": 4,
                    "rank1_high_position_pullback_scale_proxy_total_return_delta": 0.057580466388817086,
                    "rank1_high_position_pullback_scale_proxy_path_drawdown_sum": -0.8877464748505162,
                    "rank1_high_position_pullback_scale_proxy_parent_path_drawdown_sum": -0.8877464748505162,
                    "rank1_high_position_pullback_scale_formal_full713_status": "previous_frontier_blocked",
                    "rank1_high_position_pullback_scale_formal_full713_artifact_id": (
                        "model-comparison-report-ece4ed12a79d221d"
                    ),
                    "rank1_high_position_pullback_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-b04ea56d86886270"
                    ),
                    "rank1_high_position_pullback_scale_formal_full713_governance_id": (
                        "governance-promotion-decision-f3c05a5ce8d1da4b"
                    ),
                    "rank1_high_position_pullback_scale_formal_full713_dashboard_registry_id": (
                        "dashboard-approved-projection-registry-6522c02eca82dbec"
                    ),
                    "rank1_high_position_pullback_scale_formal_full713_total_return": 2.4259,
                    "rank1_high_position_pullback_scale_formal_full713_annualized_return": 0.6083,
                    "rank1_high_position_pullback_scale_formal_full713_max_drawdown": -0.0328,
                    "rank1_high_position_pullback_scale_formal_full713_negative_month_count": 3,
                    "rank1_high_position_pullback_scale_formal_full713_path_drawdown_sum": -0.8877,
                    "rank1_high_position_pullback_scale_formal_full713_dsr": 0.9999998,
                    "rank1_high_position_pullback_scale_formal_full713_pbo": 0.0,
                    "rank1_high_position_pullback_scale_adv_capacity_active_pick_count": 975,
                    "rank1_high_position_pullback_scale_adv_capacity_below_full_fill_count": 26,
                    "rank1_high_position_pullback_scale_adv_capacity_full_fill_rate": 0.9733333333333334,
                    "rank1_high_position_pullback_scale_adv_capacity_min_fill_rate": 0.11855528021978023,
                    "rank1_high_position_pullback_scale_remaining_execution_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
                        "governance_promotion_pending",
                    ],
                    "rank1_low_score_high_position_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_score_le_3_3878779420277896_"
                        "and_distance_from_40d_high_ge_minus_0_0020618556701030855"
                    ),
                    "rank1_low_score_high_position_scale_proxy_triggered_rank1_picks": 24,
                    "rank1_low_score_high_position_scale_proxy_selected_pick_mean": 0.042004955291576,
                    "rank1_low_score_high_position_scale_proxy_parent_selected_pick_mean": 0.04117083303597417,
                    "rank1_low_score_high_position_scale_proxy_negative_month_count": 3,
                    "rank1_low_score_high_position_scale_proxy_parent_negative_month_count": 3,
                    "rank1_low_score_high_position_scale_proxy_worst_month": -0.027646086882058652,
                    "rank1_low_score_high_position_scale_proxy_parent_worst_month": -0.036572956630948394,
                    "rank1_low_score_high_position_scale_proxy_total_return_delta": 0.039855405136022704,
                    "rank1_low_score_high_position_scale_proxy_path_drawdown_sum": -0.8877464748505162,
                    "rank1_low_score_high_position_scale_proxy_parent_path_drawdown_sum": -0.8877464748505162,
                    "rank1_low_score_high_position_scale_formal_full713_status": "previous_frontier_blocked",
                    "rank1_low_score_high_position_scale_formal_full713_artifact_id": (
                        "model-comparison-report-3c83db6385250480"
                    ),
                    "rank1_low_score_high_position_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-833ef57c7cef942c"
                    ),
                    "rank1_low_score_high_position_scale_formal_full713_governance_id": (
                        "governance-promotion-decision-b9879707fc0c0bf8"
                    ),
                    "rank1_low_score_high_position_scale_formal_full713_dashboard_registry_id": (
                        "dashboard-approved-projection-registry-54e5511b22125181"
                    ),
                    "rank1_low_score_high_position_scale_formal_full713_total_return": 2.4665,
                    "rank1_low_score_high_position_scale_formal_full713_annualized_return": 0.6157,
                    "rank1_low_score_high_position_scale_formal_full713_max_drawdown": -0.0306,
                    "rank1_low_score_high_position_scale_formal_full713_negative_month_count": 3,
                    "rank1_low_score_high_position_scale_formal_full713_worst_month": -0.0203,
                    "rank1_low_score_high_position_scale_formal_full713_path_drawdown_sum": -0.8877,
                    "rank1_low_score_high_position_scale_formal_full713_dsr": 0.9999999,
                    "rank1_low_score_high_position_scale_formal_full713_pbo": 0.0,
                    "rank1_low_score_high_position_scale_adv_capacity_active_pick_count": 964,
                    "rank1_low_score_high_position_scale_adv_capacity_below_full_fill_count": 26,
                    "rank1_low_score_high_position_scale_adv_capacity_full_fill_rate": 0.9730290456431535,
                    "rank1_low_score_high_position_scale_adv_capacity_min_fill_rate": 0.11855528021978023,
                    "rank1_low_score_high_position_scale_adv_capacity_all_full_fill_notional_cny": (
                        118555.28021978022
                    ),
                    "rank1_low_score_high_position_scale_adv_capacity_100k_below_full_fill_count": 0,
                    "rank1_low_score_high_position_scale_adv_capacity_1m_below_full_fill_count": 26,
                    "rank1_low_score_high_position_scale_remaining_execution_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
                        "governance_promotion_pending",
                    ],
                    "rank1_benchmark_momentum_pullback_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_benchmark_return10_ge_0_020298683992506783_"
                        "return20_percentile_ge_0_9818865345181135_and_return1d_le_minus_0_014409221902017322"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_proxy_triggered_rank1_picks": 4,
                    "rank1_benchmark_momentum_pullback_scale_proxy_selected_pick_mean": 0.042562486648346005,
                    "rank1_benchmark_momentum_pullback_scale_proxy_parent_selected_pick_mean": 0.04225590785568852,
                    "rank1_benchmark_momentum_pullback_scale_proxy_negative_month_count": 3,
                    "rank1_benchmark_momentum_pullback_scale_proxy_parent_negative_month_count": 3,
                    "rank1_benchmark_momentum_pullback_scale_proxy_worst_month": -0.013734435329340683,
                    "rank1_benchmark_momentum_pullback_scale_proxy_parent_worst_month": -0.027646086882058652,
                    "rank1_benchmark_momentum_pullback_scale_proxy_path_drawdown_sum": -0.8877464748505162,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_status": "current_frontier_blocked",
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_artifact_id": (
                        "model-comparison-report-efb1ccc40019b51b"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_candidate_run_id": (
                        "walk-forward-model-candidate-run-fc76091e8cb864f3"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_governance_id": (
                        "governance-promotion-decision-b608bf5baad5603f"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_dashboard_registry_id": (
                        "dashboard-approved-projection-registry-d19e31f40989755b"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_total_return": 2.4700,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_annualized_return": 0.6163,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_max_drawdown": -0.0306,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_negative_month_count": 3,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_worst_month": -0.0097,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_path_drawdown_sum": -0.8877,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_dsr": 0.99999996,
                    "rank1_benchmark_momentum_pullback_scale_formal_full713_pbo": 0.0,
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_active_pick_count": 960,
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_below_full_fill_count": 26,
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_full_fill_rate": 0.9729166666666667,
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_min_fill_rate": 0.11855528021978023,
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_all_full_fill_notional_cny": (
                        118555.28021978022
                    ),
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_100k_below_full_fill_count": 0,
                    "rank1_benchmark_momentum_pullback_scale_adv_capacity_1m_below_full_fill_count": 26,
                    "rank1_benchmark_momentum_pullback_scale_capacity_contract_status": (
                        "lower_capital_research_contract_ready"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_capacity_contract_max_ready_notional_cny": (
                        100_000.0
                    ),
                    "rank1_benchmark_momentum_pullback_scale_capacity_contract_claim_ceiling": (
                        "research_only_lower_capital_capacity_diagnostic"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_capacity_contract_configured_governance_status": (
                        "blocked"
                    ),
                    "rank1_benchmark_momentum_pullback_scale_remaining_execution_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
                        "governance_promotion_pending",
                    ],
                    "rank1_weak_liquidity_capacity_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_benchmark_return10_le_minus_0_012530569470406094_"
                        "avg_amount20_le_67166197_6_and_max_drawdown20_ge_minus_0_011458333333333237"
                    ),
                    "rank1_weak_liquidity_capacity_scale_proxy_below_full_delta": -4,
                    "rank1_weak_liquidity_capacity_scale_formal_full713_status": (
                        "rejected_total_and_annualized_return_below_current_frontier"
                    ),
                    "rank1_weak_liquidity_capacity_scale_formal_full713_artifact_id": (
                        "model-comparison-report-c3a8fcfc8dc603f0"
                    ),
                    "rank1_weak_liquidity_capacity_scale_formal_full713_total_return": 2.3673,
                    "rank1_weak_liquidity_capacity_scale_formal_full713_annualized_return": 0.5977,
                    "rank1_weak_liquidity_capacity_scale_formal_full713_worst_month": -0.0111,
                    "rank1_weak_liquidity_capacity_scale_formal_full713_path_drawdown_sum": -0.5971,
                    "rank1_weak_liquidity_capacity_scale_adv_capacity_below_full_fill_count": 22,
                    "rank1_weak_benchmark_low_score_high_position_scale_proxy_rule": (
                        "also_scale_rank1_to_0_when_score_le_3_231715652768284_"
                        "benchmark_return10_le_minus_0_012530569470406094_"
                        "and_distance_from_40d_high_ge_minus_0_01782531194295911"
                    ),
                    "rank1_weak_benchmark_low_score_high_position_scale_proxy_worst_month_delta": (
                        0.01343822800147485
                    ),
                    "rank1_weak_benchmark_low_score_high_position_scale_proxy_below_full_delta": -2,
                    "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_status": (
                        "rejected_total_and_annualized_return_below_current_frontier"
                    ),
                    "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_artifact_id": (
                        "model-comparison-report-33ecdf5d41f26420"
                    ),
                    "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_total_return": 2.3964,
                    "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_annualized_return": (
                        0.6030
                    ),
                    "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_worst_month": -0.0104,
                    "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_path_drawdown_sum": (
                        -0.7611
                    ),
                    "rank1_weak_benchmark_low_score_high_position_scale_adv_capacity_below_full_fill_count": 24,
                    "design_reason": (
                        "This is a full-window selected-pick hypothesis, not a known-winner filter. It combines "
                        "two independently diagnosed tail states: crowded small-liquidity momentum tails and "
                        "weak-market defensive grinds. A follow-up focused scan found no non-degrading rule that "
                        "reduces negative months below 9, but a narrow residual high-momentum amount-expansion "
                        "scale improves path/return without increasing the grid. The latest compact scan on the "
                        "residual frontier still found that negative-month reducers degrade return, but a very "
                        "narrow high-turnover momentum tail cash rule improves return/max drawdown without "
                        "worsening path or negative-month count. A later rank-level compact scan found a "
                        "non-degrading rank1-only scale that improves proxy return, max drawdown, and negative "
                        "month count without expanding the trial grid. A follow-up scan on the accepted rank1 "
                        "scaled frontier found a second fixed Rank1 extreme-momentum turnover scale that reduces "
                        "negative months to seven in proxy while preserving return/drawdown floors. A targeted "
                        "single-rule residual scan then found the next non-degrading blocker in Rank2 "
                        "high-momentum, high-amount-expansion, high-turnover tails; formal full-window replay "
                        "preserved return/drawdown floors and reduced negative months to six. A later Rank3-only "
                        "high-momentum turnover replay improved total return and DSR without worsening drawdown, "
                        "path, PBO, or negative-month count. A bounded selected-pick proxy then found a Rank1 "
                        "neutral-chop exposure candidate, and formal replay confirmed that it improves return while "
                        "reducing negative months from six to five. A capacity-focused proxy found that removing very "
                        "low-ADV Rank2 exposure improves selected-pick mean without worsening negative months, but "
                        "formal replay was rejected because total and annualized return fell below the current "
                        "neutral-chop frontier. A fee-gate governance refresh then used the comparison report's "
                        "positive 1x/2x/3x cost-stress evidence to cover fees, slippage and stamp tax. The candidate "
                        "remains blocked by negative monthly mean and ADV/capacity/fill-rate governance gates; a "
                        "selected-pick ADV diagnostic found 27 active picks below full fill under the 1M CNY / 5pct "
                        "ADV proxy. Capacity-adjusted net-return proxy improved path but lowered mean and increased "
                        "negative months, so it is rejected without formal replay. An expanded negative-month proxy "
                        "scan then found a Rank1 no-20d-drawdown exposure rule that improves selected-pick mean, "
                        "positive-date rate, path drawdown sum, and negative-month count without worsening worst "
                        "monthly mean. Formal full713 replay accepted it as the next blocked research frontier: "
                        "return, drawdown, path, DSR, and PBO all passed the neutral-chop non-degradation floor, "
                        "and negative months fell from five to four. It still cannot be promoted because negative "
                        "monthly mean and ADV/capacity/fill-rate gates remain blocked."
                        " A follow-up capacity-feature proxy on the no-drawdown frontier found a Rank1 low-ADV "
                        "turnover exposure rule that halves below-full-fill active picks while preserving selected "
                        "mean and negative-month count in proxy, but formal replay rejected it because total and "
                        "annualized return fell below the no-drawdown frontier. A total-curve-aligned selected-pick "
                        "scan then found a Rank1 high-position pullback rule that reduces proxy negative months from "
                        "four to three without lowering selected-pick mean, total-return proxy, or path drawdown. "
                        "Formal full713 replay accepted it as the next blocked research frontier: return, DSR, PBO, "
                        "and negative-month count improved while drawdown/path floors held. It remains blocked by "
                        "negative monthly mean and ADV/capacity/fill-rate gates. A follow-up total-curve-aligned "
                        "scan on that frontier found a Rank1 low-score/high-position exposure rule that improves "
                        "proxy selected-pick mean, worst month, total-return proxy, and drawdown without increasing "
                        "negative months or path drawdown. Formal full713 replay accepted it as the next blocked "
                        "research frontier: return, annualized return, max drawdown, worst month, DSR, and PBO "
                        "improved while negative-month count and path drawdown held. It still does not clear the "
                        "negative monthly mean or ADV/capacity/fill-rate gates. A later stress-loser scan found a "
                        "weak-benchmark low-score/high-position Rank1 rule that materially improved proxy worst "
                        "month and capacity count, and formal replay confirmed the stability/capacity direction, "
                        "but it is rejected because total and annualized return fell below the active frontier. "
                        "A narrower benchmark-momentum pullback Rank1 rule from the same stress-loser scan was "
                        "then formally accepted because it improved total return, annualized return, selected mean, "
                        "worst month, alpha and DSR without worsening max drawdown, path, negative-month count or "
                        "PBO. It is now the blocked research frontier, with negative monthly mean and the 1M "
                        "ADV/capacity/fill-rate stress still unresolved. A follow-up weak-liquidity capacity "
                        "shortcut improved below-full-fill count and path in formal replay, but it is rejected "
                        "because total return, annualized return and worst month degraded below the active frontier."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id=(
                "limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1"
            ),
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Move the remaining blocker from generic signal tuning into the execution contract by excluding "
                "limit-up-like entry candidates and stale/suspended proxies before ranking. This keeps the "
                "stability-preferred scorer and cash switches intact, then tests whether executable replacement "
                "candidates preserve return while reducing path stress."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "regime_transition",
                "cross_sectional",
                "position_sizing",
                "exit_policy",
                "portfolio_construction",
                "confidence_weighting",
                "tail_blending",
                "signal_cash_switch",
                "weak_regime_low_volatility_cash",
                "execution_tradability_gate",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
                "defensive_benchmark_return_20d_threshold": [0.0],
                "transition_benchmark_return_10d_threshold": [-0.015],
                "transition_benchmark_return_20d_ceiling": [0.02],
                "transition_benchmark_volatility_20d_threshold": [0.04],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [1.0],
                "defensive_low_volatility_percentile_weight": [1.2],
                "defensive_low_turnover_percentile_weight": [1.2],
                "defensive_return_5d_percentile_weight": [0.0],
                "full_weight_max_volatility_20d_percentile": [0.85],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.80],
                "exit_stock_risk_volatility_20d_percentile": [0.75],
                "risk_exit_horizon_days": [5],
                "weak_regime_exit_horizon_days": [20],
                "strong_regime_exit_horizon_days": [20],
                "neutral_regime_exit_horizon_days": [20],
                "rank_weight_profile": ["top2_91_09"],
                "conditional_rank_weight_profile": ["top3_50_30_20"],
                "rank1_shift_min_volatility_20d_percentile": [0.78],
                "rank1_shift_max_score_margin": [0.07],
                "rank1_overheat_max_score_margin": [0.03],
                "rank1_overheat_min_return_20d_percentile": [0.98],
                "rank1_overheat_min_return_5d_percentile": [0.85],
                "rank1_overheat_min_benchmark_return_20d": [0.04],
                "weak_low_vol_max_benchmark_return_10d": [-0.02],
                "weak_low_vol_min_benchmark_volatility_20d": [0.035],
                "weak_low_vol_min_low_volatility_percentile": [0.95],
                "min_avg_amount_20d": [0.0, 50_000_000.0, 100_000_000.0, 200_000_000.0],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 3,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "trial_selection_policy": {
                    "mode": "stability_adjusted",
                    "minimum_selected_top_k_net_excess_mean": 0.045,
                    "minimum_period_count_for_total_return_floor": 500,
                    "minimum_portfolio_total_return": 1.70,
                    "minimum_portfolio_max_drawdown": -0.10,
                    "tie_break_order": [
                        "portfolio_total_return_floor_first_after_500_periods",
                        "negative_month_count_asc",
                        "portfolio_max_drawdown_desc",
                        "portfolio_total_return_desc",
                        "min_monthly_mean_net_excess_desc",
                        "selected_top_k_net_excess_mean_desc",
                    ],
                    "reason": (
                        "Selected-pick execution enrichment found 73 limit-up-like selected rows and one "
                        "limit-down-like row. Limit-up-like rows had negative aggregate contribution, so this "
                        "challenger tests the real pre-ranking tradability gate instead of post-hoc deletion."
                    ),
                },
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.85,
                    "max_turnover_rate_percentile": 0.90,
                    "block_limit_up_like_entry": True,
                    "block_suspension_or_stale_proxy": True,
                    "min_avg_amount_20d": 0.0,
                },
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.85,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.85,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.80,
                },
                "exit_policy": {
                    "enabled": True,
                    "mode": "regime_stock_risk_adaptive_5_10_20",
                    "weak_regime_benchmark_return_20d_threshold": 0.0,
                    "high_regime_benchmark_volatility_20d_threshold": 0.08,
                    "exit_stock_risk_volatility_20d_percentile": 0.75,
                    "exit_stock_risk_turnover_rate_percentile": 0.90,
                    "risk_exit_horizon_days": 5,
                    "weak_regime_exit_horizon_days": 20,
                    "strong_regime_exit_horizon_days": 20,
                    "neutral_regime_exit_horizon_days": 20,
                },
                "rank_weighting": {
                    "enabled": True,
                    "mode": "conditional_first_rank_risk_shift",
                    "profile": "top2_91_09",
                    "conditional_profile": "top3_50_30_20",
                    "rank1_shift_min_volatility_20d_percentile": 0.78,
                    "rank1_shift_max_score_margin": 0.07,
                },
                "signal_cash_switch": {
                    "enabled": True,
                    "mode": "rank1_overheat_or_weak_regime_low_volatility_cash",
                    "rank1_overheat_max_score_margin": 0.03,
                    "rank1_overheat_min_return_20d_percentile": 0.98,
                    "rank1_overheat_min_return_5d_percentile": 0.85,
                    "rank1_overheat_min_benchmark_return_20d": 0.04,
                    "weak_regime_low_volatility_cash": {
                        "enabled": True,
                        "max_benchmark_return_10d": -0.02,
                        "min_benchmark_volatility_20d": 0.035,
                        "min_low_volatility_percentile": 0.95,
                    },
                },
                "screening_evidence": {
                    "source": "selected_pick_execution_enriched_join_from_stability_frontier",
                    "source_enriched_join": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_selected_pick_execution_enriched_join_20260706.json"
                    ),
                    "source_tradability_diagnostic": (
                        "/tmp/stock_dashboard_retained_reports_20260706/"
                        "stock_dashboard_selected_pick_execution_tradability_diagnostic_20260706.json"
                    ),
                    "parent_model_spec_id": (
                        "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
                    ),
                    "parent_full713_artifact_id": "model-comparison-report-993b0e970e7f74e7",
                    "parent_full713_best_trial_id": (
                        "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
                        ":trial-001"
                    ),
                    "selected_pick_limit_up_like_count": 73,
                    "selected_pick_limit_down_like_count": 1,
                    "selected_pick_limit_state_weighted_net_excess_sum": -1.0531,
                    "proxy_rule": "block_limit_up_like_entry_and_suspension_or_stale_proxy_pre_ranking",
                    "proxy_negative_month_count": 9,
                    "proxy_parent_negative_month_count": 9,
                    "proxy_path_drawdown_sum": -1.3967,
                    "proxy_parent_path_drawdown_sum": -1.4874,
                    "proxy_mean_net_excess": 0.02716,
                    "proxy_parent_mean_net_excess": 0.02654,
                    "formal_full713_artifact_id": "model-comparison-report-84ab19a0a021cdef",
                    "formal_full713_candidate_run_id": "walk-forward-model-candidate-run-059ca269699beb50",
                    "formal_full713_status": "execution_diagnostic_blocked_not_stability_replacement",
                    "formal_full713_best_trial_id": (
                        "limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1"
                        ":trial-000"
                    ),
                    "formal_full713_portfolio_total_return": 1.7143,
                    "formal_full713_annualized_return": 0.4701,
                    "formal_full713_portfolio_max_drawdown": -0.0960,
                    "formal_full713_negative_month_count": 10,
                    "formal_full713_min_monthly_mean_net_excess": -0.0328,
                    "formal_full713_path_drawdown_sum": -1.4877,
                    "formal_full713_deflated_sharpe_confidence": 0.9979,
                    "formal_full713_alpha_t_stat": 4.5350,
                    "formal_full713_pbo_proxy": 0.0,
                    "formal_full713_remaining_blockers": [
                        "execution_stress:negative_monthly_mean_under_base_cost",
                        "execution_stress:portfolio_path_drawdown_sum_below_minus_1",
                        "governance_promotion_pending",
                    ],
                    "formal_full713_interpretation": (
                        "The tradability gate preserves the broad return/DSR floor and improves worst-month mean, "
                        "but it increases negative months versus the stability frontier and does not improve path "
                        "drawdown. Min average amount variants materially degrade return, so simple capacity floors "
                        "are diagnostic-only until richer fill labels exist."
                    ),
                    "design_reason": (
                        "The proxy only removed already-selected rows and did not re-rank replacements. Full713 "
                        "stream replay is required because the actual runner will filter unfillable rows before "
                        "ranking and can choose the next eligible candidate."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="regime_adaptive_breakout_defensive_tighter_top1_20d_v1",
            model_type="regime_adaptive_breakout_defensive_ranker",
            purpose=(
                "Test whether earlier defensive-regime activation plus a tighter volatility cap can preserve the "
                "regime-adaptive top1 upside while reducing recent weak-month and path-drawdown failures."
            ),
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "defensive_benchmark_return_20d_threshold": [0.01],
                "momentum_20d_percentile_weight": [1.5],
                "amount_10d_vs_20d_percentile_weight": [0.8],
                "liquidity_percentile_weight": [1.2],
                "one_day_overheat_penalty": [0.5],
                "defensive_liquidity_percentile_weight": [0.8, 1.2],
                "defensive_low_volatility_percentile_weight": [1.0, 1.5],
                "defensive_low_turnover_percentile_weight": [1.5, 1.8],
                "defensive_return_5d_percentile_weight": [0.0],
                "defensive_return_20d_percentile_weight": [0.0, 0.2],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 1,
                "evaluation_return_metric": "selected_top_k_net_excess_mean",
                "feature_gate": {
                    "max_volatility_20d_percentile": 0.80,
                    "max_turnover_rate_percentile": 0.90,
                },
                "screening_evidence": {
                    "source": "lightweight_next_close_replay_cache_plus_runtime_benchmark_20d",
                    "as_of_start": "2023-06-13",
                    "as_of_end": "2026-05-26",
                    "evaluated_signal_days": 713,
                    "proxy_total_return": 2.3720,
                    "proxy_annualized_return": 0.5370,
                    "proxy_max_drawdown": -0.0740,
                    "proxy_positive_signal_day_rate": 0.578,
                    "proxy_negative_month_count": 9,
                    "proxy_excess_mean": 0.0268,
                    "proxy_excess_positive_signal_day_rate": 0.564,
                    "proxy_selected_params": {
                        "defensive_benchmark_return_20d_threshold": 0.01,
                        "max_volatility_20d_percentile": 0.80,
                        "max_turnover_rate_percentile": 0.90,
                        "defensive_liquidity_percentile_weight": 1.2,
                        "defensive_low_volatility_percentile_weight": 1.5,
                        "defensive_low_turnover_percentile_weight": 1.8,
                        "defensive_return_20d_percentile_weight": 0.2,
                    },
                    "formal_160_artifact_id": "model-comparison-report-144e86dfb11ccd4e",
                    "formal_160_status": "observe_blocked_but_weaker_than_regime_adaptive_default",
                    "formal_160_best_trial_id": "regime_adaptive_breakout_defensive_tighter_top1_20d_v1:trial-004",
                    "formal_160_selected_top_k_net_excess_mean": 0.0437,
                    "formal_160_positive_selected_top_k_rate": 0.54,
                    "formal_160_negative_months": ["2026-03", "2026-04"],
                    "formal_160_deflated_sharpe_confidence": 0.3519,
                    "formal_160_alpha_t_stat": 1.9746,
                    "weaker_regime_note": (
                        "This challenger improves the lightweight total-return curve and drawdown by activating "
                        "the defensive branch before the benchmark turns negative, but its formal 160-date replay "
                        "sacrifices too much selected top1 net excess and does not fix the monthly/path blockers."
                    ),
                },
            },
        ),
        _base_spec(
            model_spec_id="confirmed_concentrated_liquidity_momentum_20d_v1",
            model_type="confirmed_concentrated_liquidity_momentum_ranker",
            purpose=(
                "Test whether PIT momentum confirmation, industry-relative strength and volume expansion "
                "can improve the concentrated liquidity/momentum top5 candidate without hardcoding symbols or industries."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.25],
                "industry_relative_weight": [0.0, 0.25],
                "min_return_20d_percentile": [0.85, 0.92],
                "min_industry_return_20d_excess": [0.0, 0.12],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "confirmation_policy": "pit_momentum_industry_strength_filter",
            },
        ),
        _base_spec(
            model_spec_id="confirmed_concentrated_liquidity_momentum_10d_v1",
            model_type="confirmed_concentrated_liquidity_momentum_ranker",
            purpose=(
                "Test whether the confirmed concentrated top5 entry logic has better path stability "
                "with a 10-trading-day exit horizon."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=10,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.25],
                "industry_relative_weight": [0.0, 0.25],
                "min_return_20d_percentile": [0.85, 0.92],
                "min_industry_return_20d_excess": [0.0, 0.12],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "confirmation_policy": "pit_momentum_industry_strength_filter",
                "exit_policy": "fixed_10_trading_day_horizon",
            },
        ),
        _base_spec(
            model_spec_id="balanced_confirmed_concentrated_liquidity_momentum_20d_v1",
            model_type="confirmed_concentrated_liquidity_momentum_ranker",
            purpose=(
                "Test whether adding bounded turnover and volatility caps reduces tail losses in the "
                "confirmed concentrated top5 candidate without symbol or industry blacklists."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.25],
                "industry_relative_weight": [0.0],
                "min_return_20d_percentile": [0.85, 0.92],
                "min_industry_return_20d_excess": [0.0, 0.12],
                "max_turnover_rate_percentile": [0.93],
                "max_volatility_20d_percentile": [0.94, 0.96],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "confirmation_policy": "pit_momentum_industry_strength_turnover_volatility_filter",
            },
        ),
        _base_spec(
            model_spec_id="balanced_confirmed_concentrated_liquidity_momentum_10d_v1",
            model_type="confirmed_concentrated_liquidity_momentum_ranker",
            purpose=(
                "Test whether the balanced concentrated top5 entry logic has better path stability "
                "with a 10-trading-day exit horizon."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=10,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.25],
                "industry_relative_weight": [0.0],
                "min_return_20d_percentile": [0.85, 0.92],
                "min_industry_return_20d_excess": [0.0, 0.12],
                "max_turnover_rate_percentile": [0.93],
                "max_volatility_20d_percentile": [0.94, 0.96],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "confirmation_policy": "pit_momentum_industry_strength_turnover_volatility_filter",
                "exit_policy": "fixed_10_trading_day_horizon",
            },
        ),
        _base_spec(
            model_spec_id="regime_gated_balanced_concentrated_liquidity_momentum_20d_v1",
            model_type="confirmed_concentrated_liquidity_momentum_ranker",
            purpose=(
                "Test whether a soft PIT benchmark-regime cash switch can reduce the balanced top5 candidate path drawdown "
                "without adding symbol or industry-specific rules."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.25],
                "industry_relative_weight": [0.0],
                "min_return_20d_percentile": [0.85],
                "min_industry_return_20d_excess": [0.0],
                "max_turnover_rate_percentile": [0.93],
                "max_volatility_20d_percentile": [0.94],
                "min_benchmark_return_10d": [-0.004, 0.0],
                "min_benchmark_return_20d": [-1.0],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "confirmation_policy": "pit_momentum_industry_strength_turnover_volatility_filter",
                "cash_switch": {
                    "enabled": True,
                    "cash_return": 0.0,
                    "min_benchmark_return_10d": -0.004,
                    "min_benchmark_return_20d": -1.0,
                    "max_benchmark_volatility_20d": 999.0,
                },
            },
        ),
        _base_spec(
            model_spec_id="risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1",
            model_type="confirmed_concentrated_liquidity_momentum_ranker",
            purpose=(
                "Test whether PIT volatility/turnover position scaling can keep the balanced top5 signal's "
                "20-trading-day return edge while reducing portfolio path drawdown without date, symbol or industry filters."
            ),
            feature_groups=[
                "price_momentum",
                "volatility_risk",
                "liquidity",
                "regime",
                "cross_sectional",
            ],
            prediction_horizon_days=20,
            training_window_days=[120],
            hyperparameter_grid={
                "liquidity_weight": [1.0],
                "momentum_weight": [0.25],
                "industry_relative_weight": [0.0],
                "min_return_20d_percentile": [0.85],
                "min_industry_return_20d_excess": [0.0],
                "max_turnover_rate_percentile": [0.93],
                "max_volatility_20d_percentile": [0.96],
                "full_weight_max_volatility_20d_percentile": [0.85, 0.90],
                "full_weight_max_turnover_rate_percentile": [0.85],
                "min_position_weight": [0.50, 0.65, 0.80],
            },
            selection_policy={
                "mode": "concentrated_top_k",
                "top_k": 5,
                "evaluation_return_metric": "top_5_net_excess_mean",
                "broad_top_quantile_metric": "diagnostic_only_not_promotion_gate_for_this_spec",
                "confirmation_policy": "pit_momentum_industry_strength_turnover_volatility_filter",
                "position_weighting": {
                    "enabled": True,
                    "mode": "volatility_turnover_scaled",
                    "cash_return": 0.0,
                    "full_weight_max_volatility_20d_percentile": 0.80,
                    "min_weight_volatility_20d_percentile": 0.96,
                    "full_weight_max_turnover_rate_percentile": 0.80,
                    "min_weight_turnover_rate_percentile": 0.93,
                    "min_position_weight": 0.35,
                },
            },
        ),
    ]
    _append_gross_exposure_scaled_frontier_spec(specs)
    _append_low_score_low_amount_replacement_frontier_spec(specs)
    _append_very_low_liquidity_replacement_frontier_spec(specs)
    _append_neutral_chop_date_scale_frontier_spec(specs)
    _append_segment_risk_scale_frontier_spec(specs)
    _append_defensive_crowding_replacement_frontier_spec(specs)
    _append_weak_overheated_replacement_frontier_spec(specs)
    _append_underfilled_feature_replacement_frontier_spec(specs)
    _append_underfilled_shallow_drawdown_lowvol_replacement_frontier_spec(specs)
    _append_underfilled_low5d_high20d_candidate_replacement_frontier_spec(specs)
    _append_underfilled_weak_benchmark_lowturn_candidate_replacement_frontier_spec(specs)
    _append_underfilled_high_turnover_amount_candidate_replacement_frontier_spec(specs)
    _append_underfilled_lowturn_midmomentum_candidate_replacement_frontier_spec(specs)
    _append_underfilled_lowret_lowadv_candidate_replacement_frontier_spec(specs)
    _append_underfilled_capacity_cluster_candidate_replacement_frontier_spec(specs)
    _append_negative_month_rank_weight_adjusted_frontier_spec(specs)
    _append_exhaustion_aware_medium_industry_pullback_frontier_spec(specs)
    _append_selected_exhaustion_date_scaled_frontier_spec(specs)
    return specs


def _append_gross_exposure_scaled_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1"
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    scaled = deepcopy(base_spec)
    scaled["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_scaled_v1"
    )
    scaled["purpose"] = (
        "Formally replay the current benchmark-momentum-pullback frontier with a date-level gross-exposure "
        "stability overlay found by bounded current-frontier proxy. Low gross-exposure dates are linearly "
        "scaled by gross_exposure / floor instead of being fully cashed out. This is a fixed single-value "
        "overlay candidate and must remain blocked unless same-contract replay preserves the current frontier "
        "return, positive-date-rate, drawdown, DSR/PBO and monthly-stress floors."
    )
    grid = deepcopy(scaled.get("hyperparameter_grid") or {})
    grid["date_gross_exposure_floor"] = [0.3]
    scaled["hyperparameter_grid"] = grid
    scaled["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(scaled.get("selection_policy") or {})
    selection_policy["date_exposure_scaling"] = {
        "enabled": True,
        "mode": "gross_exposure_floor_linear_scale",
        "gross_exposure_floor": 0.3,
        "source_proxy_artifact": (
            "/tmp/stock_dashboard_retained_reports_20260706/"
            "stock_dashboard_v3_benchmark_momentum_pullback_exposure_floor_stability_proxy_20260707.json"
        ),
        "source_proxy_result": {
            "total_return_proxy_before": 1.7932276030643308,
            "total_return_proxy_after": 1.8006840651644525,
            "annualized_return_proxy_before": 0.48647434445167326,
            "annualized_return_proxy_after": 0.48800442982318337,
            "max_drawdown_proxy_before": -0.04356411241364777,
            "max_drawdown_proxy_after": -0.042787742675985396,
            "mean_net_excess_before": 0.031814645077118904,
            "mean_net_excess_after": 0.031896063027882386,
            "positive_date_rate_before": 0.4670750382848392,
            "positive_date_rate_after": 0.4670750382848392,
            "negative_month_count_before": 3,
            "negative_month_count_after": 3,
            "worst_monthly_mean_before": -0.009711853356037263,
            "worst_monthly_mean_after": -0.008823810636057021,
            "path_drawdown_sum_before": -0.8877464748505162,
            "path_drawdown_sum_after": -0.8715418379317716,
            "low_exposure_active_date_count": 76,
            "gated_active_date_count": 0,
        },
    }
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "The current frontier remains blocked on monthly/path and capacity stress. This fixed overlay is "
            "included only because the compact proxy improved return, max drawdown, worst month and path while "
            "keeping positive-date rate and negative-month count unchanged; formal replay must reject it if any "
            "current-frontier floor degrades."
        ),
    }
    scaled["selection_policy"] = selection_policy
    specs.append(scaled)


def _append_low_score_low_amount_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_scaled_v1"
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the gross-exposure-scaled frontier with a fixed Rank1 slot-replacement rule. "
        "When Rank1 has low model score and low liquidity, replace that slot with the highest-score same-date "
        "Top20 candidate that satisfies a minimum liquidity floor. This tests replacement rather than deletion, "
        "and must remain blocked unless same-contract replay preserves current-frontier return, drawdown, DSR/PBO, "
        "monthly-stress and capacity floors."
    )
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    grid["rank1_replacement_max_score"] = [3.1]
    grid["rank1_replacement_max_avg_amount_20d"] = [150_000_000.0]
    grid["rank1_replacement_min_replacement_avg_amount_20d"] = [20_000_000.0]
    grid["rank1_replacement_pool_top_n"] = [20]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    selection_policy["slot_replacement"] = {
        "enabled": True,
        "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
        "max_score": 3.1,
        "max_avg_amount_20d": 150_000_000.0,
        "min_replacement_avg_amount_20d": 20_000_000.0,
        "pool_top_n": 20,
        "source_proxy_artifact": (
            "/tmp/stock_dashboard_retained_reports_20260706/"
            "stock_dashboard_v3_gross_exposure_top20_deterministic_replacement_scan_20260707.json"
        ),
        "source_proxy_result": {
            "diagnostic_scope": "top20_deterministic_replacement_scan",
            "replacement_count": 6,
            "total_return_before": 2.4730761027166235,
            "total_return_after": 2.5314696484061807,
            "annualized_return_before": 0.6168424128111523,
            "annualized_return_after": 0.6272794673935482,
            "max_drawdown_before": -0.030583249431552106,
            "max_drawdown_after": -0.030583249431551773,
            "mean_net_excess_before": 0.031896063027882386,
            "mean_net_excess_after": 0.032409560478266305,
            "positive_date_rate_before": 0.4670750382848392,
            "positive_date_rate_after": 0.4686064318529862,
            "negative_month_count_before": 3,
            "negative_month_count_after": 3,
            "worst_monthly_mean_before": -0.008823810636057021,
            "worst_monthly_mean_after": -0.008624635687025848,
            "path_drawdown_sum_before": -0.8715418379317716,
            "path_drawdown_sum_after": -0.7366944079598614,
            "capacity_below_full_fill_before": 29,
            "capacity_below_full_fill_after": 27,
        },
    }
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "Simple deletion and underfilled-slot substitution degraded formal or proxy return. This fixed rule "
            "tests whether replacing only low-score low-liquidity Rank1 slots with same-date high-score liquid "
            "alternatives preserves the current gross-exposure frontier while improving stability/capacity proxies."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_very_low_liquidity_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the current Rank1 replacement frontier with an additional fixed Rank1 slot-replacement "
        "rule for very low liquidity picks. The rule keeps the existing low-score/low-amount replacement intact, "
        "then replaces Rank1 again only when the selected Rank1 still has score <= 3.2, avg_amount_20d <= 20M, "
        "turnover_rate_percentile <= 0.2 and amount_10d_vs_20d_percentile <= 0.85, using the highest-score same-date "
        "Top20 candidate with avg_amount_20d >= 100M. It targets the remaining ADV/capacity and path-stress blockers "
        "without changing the model into a simple liquidity floor."
    )
    prefix = "rank1_very_low_liquidity_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    grid[f"{prefix}_max_score"] = [3.2]
    grid[f"{prefix}_max_avg_amount_20d"] = [20_000_000.0]
    grid[f"{prefix}_max_turnover_rate_percentile"] = [0.2]
    grid[f"{prefix}_max_amount_10d_vs_20d_percentile"] = [0.85]
    grid[f"{prefix}_min_replacement_avg_amount_20d"] = [100_000_000.0]
    grid[f"{prefix}_pool_top_n"] = [20]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_very_low_liquidity_top20_high_amount_substitute",
            "max_score": 3.2,
            "max_avg_amount_20d": 20_000_000.0,
            "max_turnover_rate_percentile": 0.2,
            "max_amount_10d_vs_20d_percentile": 0.85,
            "min_replacement_avg_amount_20d": 100_000_000.0,
            "pool_top_n": 20,
            "source_proxy_artifact": (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_rank1_replacement_frontier_targeted_top20_replacement_proxy_scan_20260707.json"
            ),
            "source_proxy_result": {
                "diagnostic_scope": "rank1_replacement_frontier_targeted_top20_replacement_proxy_scan",
                "replacement_count": 9,
                "total_return_before": 2.5293514445596124,
                "total_return_after": 2.5302352714923306,
                "annualized_return_before": 0.6269027273531775,
                "annualized_return_after": 0.6270599401456325,
                "max_drawdown_before": -0.030583249431551884,
                "max_drawdown_after": -0.030583249431551995,
                "mean_net_excess_before": 0.03239119124144251,
                "mean_net_excess_after": 0.03239665069057023,
                "positive_date_rate_before": 0.4670750382848392,
                "positive_date_rate_after": 0.4686064318529862,
                "negative_month_count_before": 3,
                "negative_month_count_after": 3,
                "worst_monthly_mean_before": -0.008624635687025848,
                "worst_monthly_mean_after": -0.008624635687025848,
                "path_drawdown_sum_before": -0.7366944079598614,
                "path_drawdown_sum_after": -0.5966418262105186,
                "capacity_below_full_fill_before": 24,
                "capacity_below_full_fill_after": 16,
                "proxy_claim_ceiling": "proxy_scan_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "The added very-low-liquidity replacement is promoted from a bounded proxy only because it preserves "
            "the current Rank1 replacement frontier floor while reducing ADV/capacity underfilled picks and "
            "improving path drawdown. Formal full713 replay remains required before any frontier claim."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_neutral_chop_date_scale_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    neutral = deepcopy(base_spec)
    neutral["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_date_scale_v1"
    )
    neutral["purpose"] = (
        "Formally replay the current Rank1 liquidity-replacement frontier with a fixed date-level neutral-chop "
        "signal scale. The rule cashes only narrow neutral benchmark/choppy Rank1 dates found by feature-rich "
        "scale-aware proxy, aiming to reduce negative-month stress without degrading current return, drawdown, "
        "path, DSR/PBO, or capacity floors. It remains research-only and blocked unless same-contract replay "
        "confirms the proxy."
    )
    grid = deepcopy(neutral.get("hyperparameter_grid") or {})
    grid["rank1_neutral_chop_date_min_benchmark_return_20d"] = [-0.02]
    grid["rank1_neutral_chop_date_max_benchmark_return_20d"] = [0.01]
    grid["rank1_neutral_chop_date_min_benchmark_volatility_20d"] = [0.03]
    grid["rank1_neutral_chop_date_max_return_20d_percentile"] = [0.95]
    grid["rank1_neutral_chop_date_min_return_5d_percentile"] = [0.80]
    grid["rank1_neutral_chop_date_max_drawdown_20d"] = [-0.003]
    grid["rank1_neutral_chop_date_position_scale"] = [0.0]
    neutral["hyperparameter_grid"] = grid
    neutral["max_trials"] = _grid_trial_count(grid)
    allowed_feature_groups = list(neutral.get("allowed_feature_groups") or [])
    if "neutral_chop_date_scale" not in allowed_feature_groups:
        allowed_feature_groups.append("neutral_chop_date_scale")
    neutral["allowed_feature_groups"] = allowed_feature_groups
    selection_policy = deepcopy(neutral.get("selection_policy") or {})
    signal_scaling = deepcopy(selection_policy.get("signal_position_scaling") or {})
    signal_scaling["rank1_neutral_chop_date_scale"] = {
        "enabled": True,
        "min_benchmark_return_20d": -0.02,
        "max_benchmark_return_20d": 0.01,
        "min_benchmark_volatility_20d": 0.03,
        "max_return_20d_percentile": 0.95,
        "min_return_5d_percentile": 0.80,
        "max_drawdown_20d": -0.003,
        "position_scale": 0.0,
        "source_proxy_artifact": (
            "/tmp/stock_dashboard_retained_reports_20260706/"
            "stock_dashboard_v3_rank1_feature_rich_date_extra_scale_scan_20260707.json"
        ),
        "source_proxy_result": {
            "diagnostic_scope": "feature_rich_date_extra_scale_proxy",
            "triggered_date_count": 36,
            "portfolio_total_return_before": 2.5310706789295234,
            "portfolio_total_return_after": 2.531146755742594,
            "annualized_return_before": 0.6272085179877025,
            "annualized_return_after": 0.6272220472337862,
            "max_drawdown_before": -0.030583249431551995,
            "max_drawdown_after": -0.030583249431551884,
            "positive_date_rate_before": 0.4686064318529862,
            "positive_date_rate_after": 0.450229709035222,
            "negative_month_count_before": 3,
            "negative_month_count_after": 2,
            "negative_months_after": ["2024-02", "2024-08"],
            "worst_monthly_mean_before": -0.008624635687025848,
            "worst_monthly_mean_after": -0.008624635687025848,
            "path_drawdown_sum_before": -0.5966418262105186,
            "path_drawdown_sum_after": -0.5966418262105186,
            "proxy_caveat": (
                "Positive-date rate drops to 45.02%, so formal replay must confirm this remains above the "
                "promotion gate and does not degrade capacity or execution evidence."
            ),
        },
    }
    selection_policy["signal_position_scaling"] = signal_scaling
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "Feature-rich scale-aware proxy found a fixed neutral-chop date scale that reduces negative months "
            "from three to two while preserving return/drawdown/path floors, but it lowers positive-date rate. "
            "Formal replay must reject it if the positive-rate, capacity, return, drawdown, DSR/PBO or worst-month "
            "floors degrade."
        ),
    }
    neutral["selection_policy"] = selection_policy
    specs.append(neutral)


def _append_segment_risk_scale_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_date_scale_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    segment = deepcopy(base_spec)
    segment["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_scale_v1"
    )
    segment["purpose"] = (
        "Formally replay the neutral-chop date-scale challenger with a fixed three-rule segment risk scale overlay. "
        "The overlay is learned from a compact Top50 selected-pick segment scan, and lightly reduces exposure for "
        "specific ex-ante risk segments instead of changing the candidate universe or using known winner stocks. It "
        "must remain research-only unless same-contract replay preserves the neutral-chop candidate's return, drawdown, "
        "path, DSR/PBO, positive-date, monthly-stress and capacity floors."
    )
    rules = [
        {
            "prefix": "rank2_high_turnover_segment_risk",
            "reason": "rank2_high_turnover_segment_risk_position_scale",
            "scope": "rank2",
            "feature": "turnover_rate_percentile",
            "op": ">=",
            "threshold": 0.8888137884420412,
            "position_scale": 0.5,
        },
        {
            "prefix": "rank3_high_score_segment_risk",
            "reason": "rank3_high_score_segment_risk_position_scale",
            "scope": "rank3",
            "feature": "score",
            "op": ">=",
            "threshold": 3.381482156586441,
            "position_scale": 0.5,
        },
        {
            "prefix": "rank1_high_amount_segment_risk",
            "reason": "rank1_high_amount_segment_risk_position_scale",
            "scope": "rank1",
            "feature": "avg_amount_20d",
            "op": ">=",
            "threshold": 1_619_280_193.75,
            "position_scale": 0.75,
        },
    ]
    grid = deepcopy(segment.get("hyperparameter_grid") or {})
    for rule in rules:
        prefix = rule["prefix"]
        grid[f"{prefix}_threshold"] = [rule["threshold"]]
        grid[f"{prefix}_position_scale"] = [rule["position_scale"]]
    segment["hyperparameter_grid"] = grid
    segment["max_trials"] = _grid_trial_count(grid)
    allowed_feature_groups = list(segment.get("allowed_feature_groups") or [])
    if "segment_risk_scale" not in allowed_feature_groups:
        allowed_feature_groups.append("segment_risk_scale")
    segment["allowed_feature_groups"] = allowed_feature_groups
    selection_policy = deepcopy(segment.get("selection_policy") or {})
    rank_scaling = deepcopy(selection_policy.get("rank_position_scaling") or {})
    rank_scaling["segment_risk_scale_rules"] = [
        {
            "enabled": True,
            "param_prefix": rule["prefix"],
            "reason": rule["reason"],
            "scope": rule["scope"],
            "feature": rule["feature"],
            "op": rule["op"],
            "threshold": rule["threshold"],
            "position_scale": rule["position_scale"],
        }
        for rule in rules
    ]
    rank_scaling["source_segment_risk_scale_combo_scan"] = (
        "/tmp/stock_dashboard_retained_reports_20260706/"
        "stock_dashboard_v3_neutral_chop_segment_risk_scale_small_combo_scan_20260707.json"
    )
    rank_scaling["source_segment_risk_scale_combo_result"] = {
        "diagnostic_scope": "neutral_chop_segment_risk_scale_small_combo_scan",
        "scaled_candidate_rows": 97,
        "portfolio_total_return_before": 2.531146755742594,
        "portfolio_total_return_after": 2.5441379707456706,
        "annualized_return_before": 0.6272220472337862,
        "annualized_return_after": 0.6295297415690551,
        "max_drawdown_before": -0.030583249431551884,
        "max_drawdown_after": -0.030583249431551884,
        "positive_date_rate_before": 0.450229709035222,
        "positive_date_rate_after": 0.45176110260336905,
        "negative_month_count_before": 2,
        "negative_month_count_after": 2,
        "negative_months_after": ["2024-02", "2024-08"],
        "worst_monthly_mean_before": -0.008624635687025848,
        "worst_monthly_mean_after": -0.00860491361397271,
        "path_drawdown_sum_before": -0.5966418262105186,
        "path_drawdown_sum_after": -0.5966418262105186,
        "capacity_below_full_fill_before": 14,
        "capacity_below_full_fill_after": 14,
        "proxy_claim_ceiling": "compact_top50_proxy_only_formal_replay_required",
    }
    selection_policy["rank_position_scaling"] = rank_scaling
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "The compact Top50 segment scan found a fixed three-rule overlay that improves total/annualized return, "
            "positive-date rate and worst month while preserving max drawdown, path, negative-month count and ADV "
            "capacity floors. It does not clear the remaining negative-month or 1M capacity blockers, so formal replay "
            "may at most promote it to a stronger research challenger."
        ),
    }
    segment["selection_policy"] = selection_policy
    specs.append(segment)


def _append_defensive_crowding_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_scale_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the segment-risk challenger with a fixed Rank1 defensive-crowding replacement rule. The "
        "rule replaces low 5d-relative-strength and low-turnover Rank1 picks with same-date Top10 candidates that "
        "meet minimum liquidity, minimum 5d percentile and low-turnover constraints. It tests opportunity-set "
        "construction rather than cashing exposure, and remains research-only unless same-contract full713 replay "
        "preserves the segment-risk return, drawdown, path, DSR/PBO, positive-date and capacity floors."
    )
    prefix = "rank1_defensive_crowding_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 10_000_000_000.0,
        f"{prefix}_max_turnover_rate_percentile": 0.1,
        f"{prefix}_max_return_5d_percentile": 0.1,
        f"{prefix}_min_replacement_avg_amount_20d": 100_000_000.0,
        f"{prefix}_min_candidate_return_5d_percentile": 0.1,
        f"{prefix}_max_candidate_turnover_rate_percentile": 0.1,
        f"{prefix}_min_candidate_score": 0.0,
        f"{prefix}_pool_top_n": 10,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_defensive_crowding_top50_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "max_turnover_rate_percentile": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
            "max_return_5d_percentile": fixed_params[f"{prefix}_max_return_5d_percentile"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "min_candidate_return_5d_percentile": fixed_params[f"{prefix}_min_candidate_return_5d_percentile"],
            "max_candidate_turnover_rate_percentile": fixed_params[f"{prefix}_max_candidate_turnover_rate_percentile"],
            "min_candidate_score": fixed_params[f"{prefix}_min_candidate_score"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_proxy_result": {
                "diagnostic_scope": "rank1_low_return_low_turnover_same_date_top50_replacement_proxy",
                "source_scan": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_segment_risk_defensive_crowding_top50_replacement_scan_20260707.json"
                ),
                "trigger_date_count": 8,
                "replacement_count": 7,
                "horizon_normalized_total_return_proxy_before": 1.9011950149612273,
                "horizon_normalized_total_return_proxy_after": 1.9731201512164507,
                "positive_date_rate_before": 0.45176110260336905,
                "positive_date_rate_after": 0.45329249617151607,
                "negative_month_count_before": 2,
                "negative_month_count_after": 1,
                "worst_monthly_mean_before": -0.00860491361397271,
                "worst_monthly_mean_after": -0.00860491361397271,
                "path_drawdown_sum_before": -0.5966418262105186,
                "path_drawdown_sum_after": -0.5966418262105186,
                "proxy_claim_ceiling": "incremental_top50_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 replacement proxy suggests that replacing Rank1 low-return/low-turnover defensive "
            "crowding picks may reduce negative months without cashing exposure. Full stream replay is required; "
            "the proxy does not clear production, dashboard, paper or policy gates."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_weak_overheated_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_"
        "defensive_crowding_weak_overheated_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the defensive-crowding replacement frontier with an additional generic Rank1 "
        "weak-market overheated/low-turnover replacement rule. The rule is feature-state based, not month or symbol "
        "based: in weak, volatile benchmark regimes it replaces Rank1 picks with strong short/medium relative "
        "strength, high low-volatility percentile and low turnover using same-date Top20 candidates that are liquid, "
        "not 20d-overheated and not high-turnover. It remains research-only unless same-contract full713 replay "
        "preserves or improves return, drawdown, path, DSR/PBO, positive-date, monthly-stress and capacity floors."
    )
    prefix = "rank1_weak_overheated_low_turnover_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 500_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 50_000_000.0,
        f"{prefix}_pool_top_n": 20,
        f"{prefix}_max_benchmark_return_20d": -0.01,
        f"{prefix}_min_benchmark_volatility_20d": 0.035,
        f"{prefix}_min_low_volatility_percentile": 0.90,
        f"{prefix}_min_return_5d_percentile": 0.85,
        f"{prefix}_min_return_20d_percentile": 0.90,
        f"{prefix}_max_turnover_rate_percentile": 0.10,
        f"{prefix}_max_candidate_return_20d_percentile": 0.80,
        f"{prefix}_max_candidate_turnover_rate_percentile": 0.30,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_weak_overheated_low_turnover_generic_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "benchmark_return_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_benchmark_return_20d"],
                    "param_key": "max_benchmark_return_20d",
                },
                {
                    "feature": "benchmark_volatility_20d",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_benchmark_volatility_20d"],
                    "param_key": "min_benchmark_volatility_20d",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_low_volatility_percentile"],
                    "param_key": "min_low_volatility_percentile",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_5d_percentile"],
                    "param_key": "min_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_20d_percentile"],
                    "param_key": "min_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
                    "param_key": "max_turnover_rate_percentile",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_return_20d_percentile"],
                    "param_key": "max_candidate_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_turnover_rate_percentile"],
                    "param_key": "max_candidate_turnover_rate_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "replacement_frontier_weak_overheated_low_turnover_generic_proxy",
                "source_top_candidate_inventory": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_neutral_chop_top50_candidate_inventory_feature_rich_20260707.json"
                ),
                "replacement_count": 5,
                "replacement_dates": [
                    "2024-02-01",
                    "2026-03-05",
                    "2026-03-06",
                    "2026-04-03",
                    "2026-04-07",
                ],
                "horizon_normalized_total_return_proxy_before": 1.9732279344338841,
                "horizon_normalized_total_return_proxy_after": 2.0176495158046244,
                "mean_daily_net_excess_return_before": 0.03371690269380826,
                "mean_daily_net_excess_return_after": 0.03417075232176321,
                "positive_date_rate_before": 0.45329249617151607,
                "positive_date_rate_after": 0.45788667687595713,
                "negative_month_count_before": 1,
                "negative_month_count_after": 0,
                "worst_monthly_mean_before": -0.008604913613972708,
                "worst_monthly_mean_after": 0.0010150198816239596,
                "path_drawdown_sum_before": -1.770695010846484,
                "path_drawdown_sum_after": -1.5906520251568441,
                "proxy_claim_ceiling": "selected_pick_plus_top20_replacement_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded feature-state replacement proxy suggests weak-market Rank1 overheated/low-turnover "
            "substitution may clear the remaining negative month while preserving return/path. Full stream replay "
            "must reject it if total return, annualized return, drawdown, path, DSR/PBO, positive-date or capacity "
            "floors degrade versus the current defensive-crowding replacement frontier."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_feature_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_"
        "defensive_crowding_weak_overheated_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_"
        "defensive_crowding_weak_overheated_underfilled_feature_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the weak-overheated frontier with a narrow Rank1 capacity-separating replacement rule. "
        "The rule targets low-ADV Rank1 slots that are short-term strong, medium-term capped, amount-expanding and "
        "nonzero-turnover, then substitutes a same-date Top20 candidate with sufficient ADV and bounded "
        "overheated/turnover state. It is a research-only capacity blocker reducer and must be rejected if formal "
        "full713 replay degrades return, drawdown, path, DSR/PBO, positive-date, zero-negative-month or capacity "
        "floors versus the weak-overheated frontier."
    )
    prefix = "rank1_underfilled_feature_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 4_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 50_000_000.0,
        f"{prefix}_pool_top_n": 20,
        f"{prefix}_min_return_5d_percentile": 0.60,
        f"{prefix}_max_return_20d_percentile": 0.52,
        f"{prefix}_min_amount_10d_vs_20d_percentile": 0.55,
        f"{prefix}_min_turnover_rate_percentile": 0.04,
        f"{prefix}_max_candidate_return_20d_percentile": 0.80,
        f"{prefix}_max_candidate_turnover_rate_percentile": 0.30,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_feature_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_5d_percentile"],
                    "param_key": "min_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_20d_percentile"],
                    "param_key": "max_return_20d_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_amount_10d_vs_20d_percentile"],
                    "param_key": "min_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_turnover_rate_percentile"],
                    "param_key": "min_turnover_rate_percentile",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_return_20d_percentile"],
                    "param_key": "max_candidate_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_turnover_rate_percentile"],
                    "param_key": "max_candidate_turnover_rate_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "weak_overheated_top50_underfilled_feature_replacement",
                "source_scan": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_weak_overheated_underfilled_feature_replacement_scan_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2023-11-09"],
                "source_symbol": "603117.SH",
                "replacement_symbol": "601766.SH",
                "underfilled_active_picks_before": 14,
                "underfilled_active_picks_after": 13,
                "horizon_normalized_total_return_proxy_before": 2.00054266368704,
                "horizon_normalized_total_return_proxy_after": 2.0125058697762936,
                "mean_daily_net_excess_return_before": 0.033996135085880154,
                "mean_daily_net_excess_return_after": 0.03411800361983384,
                "positive_date_rate_before": 0.4563552833078101,
                "positive_date_rate_after": 0.45788667687595713,
                "negative_month_count_before": 0,
                "negative_month_count_after": 0,
                "worst_monthly_mean_before": 0.0008524689561126046,
                "worst_monthly_mean_after": 0.0008524689561126046,
                "proxy_claim_ceiling": "top50_underfilled_feature_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 underfilled-feature proxy suggests one Rank1 low-capacity losing slot can be replaced "
            "without sacrificing the weak-overheated frontier's return or zero-negative-month floors. Full stream "
            "replay is required; the proxy does not clear production, dashboard, paper or policy gates."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_shallow_drawdown_lowvol_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_"
        "defensive_crowding_weak_overheated_underfilled_feature_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_shallow_drawdown_lowvol_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the underfilled-feature frontier with a narrow Rank1 shallow-drawdown low-volatility "
        "capacity replacement rule. The rule targets one feature-state family of weak-benchmark, high "
        "amount-expansion, low-ADV Rank1 picks and remains research-only unless full713 replay preserves or "
        "improves all active frontier floors."
    )
    prefix = "rank1_underfilled_shallow_drawdown_lowvol_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 8_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 50_000_000.0,
        f"{prefix}_pool_top_n": 20,
        f"{prefix}_min_low_volatility_percentile": 0.99,
        f"{prefix}_max_benchmark_return_20d": -0.015,
        f"{prefix}_min_max_drawdown_20d": -0.02,
        f"{prefix}_min_amount_10d_vs_20d_percentile": 0.80,
        f"{prefix}_min_return_20d_percentile": 0.60,
        f"{prefix}_max_turnover_rate_percentile": 0.03,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_shallow_drawdown_lowvol_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_low_volatility_percentile"],
                    "param_key": "min_low_volatility_percentile",
                },
                {
                    "feature": "benchmark_return_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_benchmark_return_20d"],
                    "param_key": "max_benchmark_return_20d",
                },
                {
                    "feature": "max_drawdown_20d",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_max_drawdown_20d"],
                    "param_key": "min_max_drawdown_20d",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_amount_10d_vs_20d_percentile"],
                    "param_key": "min_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_20d_percentile"],
                    "param_key": "min_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
                    "param_key": "max_turnover_rate_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "underfilled_frontier_shallow_drawdown_lowvol_rank1_replacement",
                "source_scan": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_underfilled_frontier_shallow_drawdown_lowvol_replacement_scan_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2024-09-02"],
                "source_symbol": "601686.SH",
                "replacement_symbol": "601018.SH",
                "underfilled_active_picks_before": 13,
                "underfilled_active_picks_after": 12,
                "horizon_normalized_total_return_proxy_before": 2.0125058697762936,
                "horizon_normalized_total_return_proxy_after": 2.015930980031071,
                "mean_daily_net_excess_return_before": 0.03411800361983384,
                "mean_daily_net_excess_return_after": 0.03415259656209287,
                "positive_date_rate_before": 0.45788667687595713,
                "positive_date_rate_after": 0.45788667687595713,
                "negative_month_count_before": 0,
                "negative_month_count_after": 0,
                "proxy_claim_ceiling": "top50_underfilled_shallow_drawdown_lowvol_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 shallow-drawdown low-volatility underfilled proxy suggests one additional Rank1 "
            "capacity slot can be replaced without degrading the underfilled-feature frontier. Full stream replay "
            "is required before treating it as the active research frontier."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_low5d_high20d_candidate_replacement_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_shallow_drawdown_lowvol_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_low5d_high20d_candidate_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the shallow-drawdown low-volatility frontier with a narrow Rank1 replacement rule for "
        "low-5d, decent-20d, weak-benchmark underfilled sources. Candidate selection requires high 20d relative "
        "strength, so this remains an ex-ante opportunity-set rule rather than outcome filtering."
    )
    prefix = "rank1_underfilled_low5d_high20d_candidate_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 8_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 50_000_000.0,
        f"{prefix}_pool_top_n": 20,
        f"{prefix}_min_low_volatility_percentile": 0.98,
        f"{prefix}_max_benchmark_return_20d": -0.02,
        f"{prefix}_max_return_5d_percentile": 0.30,
        f"{prefix}_min_return_20d_percentile": 0.50,
        f"{prefix}_max_amount_10d_vs_20d_percentile": 0.40,
        f"{prefix}_max_turnover_rate_percentile": 0.10,
        f"{prefix}_min_candidate_return_20d_percentile": 0.85,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_low5d_high20d_candidate_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_low_volatility_percentile"],
                    "param_key": "min_low_volatility_percentile",
                },
                {
                    "feature": "benchmark_return_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_benchmark_return_20d"],
                    "param_key": "max_benchmark_return_20d",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_5d_percentile"],
                    "param_key": "max_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_20d_percentile"],
                    "param_key": "min_return_20d_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_amount_10d_vs_20d_percentile"],
                    "param_key": "max_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
                    "param_key": "max_turnover_rate_percentile",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_return_20d_percentile"],
                    "param_key": "min_candidate_return_20d_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "shallow_lowvol_frontier_low5d_high20d_candidate_rank1_replacement",
                "source_scan": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_shallow_lowvol_frontier_low5d_high20d_candidate_replacement_scan_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2024-09-04"],
                "source_symbol": "600569.SH",
                "replacement_symbol": "601628.SH",
                "underfilled_active_picks_before": 12,
                "underfilled_active_picks_after": 11,
                "horizon_normalized_total_return_proxy_before": 2.015930980031071,
                "horizon_normalized_total_return_proxy_after": 2.026506883635069,
                "mean_daily_net_excess_return_before": 0.03415259656209287,
                "mean_daily_net_excess_return_after": 0.03425990433749831,
                "positive_date_rate_before": 0.45788667687595713,
                "positive_date_rate_after": 0.45941807044410415,
                "negative_month_count_before": 0,
                "negative_month_count_after": 0,
                "proxy_claim_ceiling": "top50_underfilled_low5d_high20d_candidate_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 proxy suggests one low-5d/decent-20d underfilled Rank1 source can be replaced by a "
            "high-20d relative-strength liquid candidate without degrading the current frontier. Full stream replay "
            "is required before accepting it."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_weak_benchmark_lowturn_candidate_replacement_frontier_spec(
    specs: list[dict[str, Any]],
) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_low5d_high20d_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_weak_benchmark_lowturn_candidate_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the low5d/high20d frontier with a narrow Rank1 replacement rule for weak-benchmark, "
        "very-low-turnover, high-5d but capped-20d underfilled sources. Candidate selection requires liquid, "
        "moderate-20d and non-dead-turnover candidates."
    )
    prefix = "rank1_underfilled_weak_benchmark_lowturn_candidate_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 20_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 30_000_000.0,
        f"{prefix}_pool_top_n": 20,
        f"{prefix}_max_benchmark_return_20d": -0.035,
        f"{prefix}_min_return_5d_percentile": 0.70,
        f"{prefix}_max_return_20d_percentile": 0.50,
        f"{prefix}_max_turnover_rate_percentile": 0.01,
        f"{prefix}_min_amount_10d_vs_20d_percentile": 0.55,
        f"{prefix}_min_low_volatility_percentile": 0.96,
        f"{prefix}_max_candidate_return_20d_percentile": 0.40,
        f"{prefix}_min_candidate_turnover_rate_percentile": 0.035,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_weak_benchmark_lowturn_candidate_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "benchmark_return_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_benchmark_return_20d"],
                    "param_key": "max_benchmark_return_20d",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_5d_percentile"],
                    "param_key": "min_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_20d_percentile"],
                    "param_key": "max_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
                    "param_key": "max_turnover_rate_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_amount_10d_vs_20d_percentile"],
                    "param_key": "min_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_low_volatility_percentile"],
                    "param_key": "min_low_volatility_percentile",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_return_20d_percentile"],
                    "param_key": "max_candidate_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_turnover_rate_percentile"],
                    "param_key": "min_candidate_turnover_rate_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "low5d_high20d_frontier_weak_benchmark_lowturn_candidate_rank1_replacement",
                "source_scan": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_low5d_high20d_frontier_weak_benchmark_lowturn_candidate_replacement_scan_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2025-01-27"],
                "source_symbol": "600167.SH",
                "replacement_symbol": "600032.SH",
                "underfilled_active_picks_before": 11,
                "underfilled_active_picks_after": 10,
                "horizon_normalized_total_return_proxy_before": 2.026506883635069,
                "horizon_normalized_total_return_proxy_after": 2.028822447900527,
                "mean_daily_net_excess_return_before": 0.03425990433749831,
                "mean_daily_net_excess_return_after": 0.034283314632378235,
                "positive_date_rate_before": 0.45941807044410415,
                "positive_date_rate_after": 0.45941807044410415,
                "negative_month_count_before": 0,
                "negative_month_count_after": 0,
                "proxy_claim_ceiling": "top50_underfilled_weak_benchmark_lowturn_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 proxy suggests one weak-benchmark/very-low-turnover underfilled Rank1 source can be "
            "replaced by a moderate-20d, non-dead-turnover candidate without degrading the current frontier. Full "
            "stream replay is required before accepting it."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_high_turnover_amount_candidate_replacement_frontier_spec(
    specs: list[dict[str, Any]],
) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_weak_benchmark_lowturn_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_high_turnover_amount_candidate_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the weak-benchmark low-turn frontier with an additional narrow Rank1 replacement rule "
        "for underfilled, high-turnover, high-amount-expansion and high-5d/20d momentum sources. Candidate "
        "selection requires higher ADV and still-strong 20d momentum so the capacity repair does not simply "
        "downgrade into lower-quality liquidity."
    )
    prefix = "rank1_underfilled_high_turnover_amount_candidate_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 20_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 20_000_000.0,
        f"{prefix}_pool_top_n": 20,
        f"{prefix}_min_benchmark_return_20d": 0.0,
        f"{prefix}_min_return_5d_percentile": 0.90,
        f"{prefix}_min_return_20d_percentile": 0.90,
        f"{prefix}_min_turnover_rate_percentile": 0.50,
        f"{prefix}_min_amount_10d_vs_20d_percentile": 0.95,
        f"{prefix}_max_low_volatility_percentile": 0.30,
        f"{prefix}_min_candidate_return_20d_percentile": 0.80,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_high_turnover_amount_candidate_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "benchmark_return_20d",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_benchmark_return_20d"],
                    "param_key": "min_benchmark_return_20d",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_5d_percentile"],
                    "param_key": "min_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_20d_percentile"],
                    "param_key": "min_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_turnover_rate_percentile"],
                    "param_key": "min_turnover_rate_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_amount_10d_vs_20d_percentile"],
                    "param_key": "min_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_low_volatility_percentile"],
                    "param_key": "max_low_volatility_percentile",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_return_20d_percentile"],
                    "param_key": "min_candidate_return_20d_percentile",
                }
            ],
            "source_proxy_result": {
                "diagnostic_scope": "weak_benchmark_lowturn_frontier_high_turnover_amount_rank1_replacement",
                "source_scan": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_weak_benchmark_lowturn_frontier_"
                    "high_turnover_amount_replacement_scan_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2024-09-25"],
                "source_symbol": "600231.SH",
                "replacement_symbol": "000652.SZ",
                "underfilled_active_picks_before": 10,
                "underfilled_active_picks_after": 9,
                "horizon_normalized_total_return_proxy_before": 2.028822447900527,
                "horizon_normalized_total_return_proxy_after": 2.0598884057179294,
                "mean_daily_net_excess_return_before": 0.034283314632378235,
                "mean_daily_net_excess_return_after": 0.03459834383647621,
                "positive_date_rate_before": 0.45941807044410415,
                "positive_date_rate_after": 0.45941807044410415,
                "negative_month_count_before": 0,
                "negative_month_count_after": 0,
                "proxy_claim_ceiling": "top20_underfilled_high_turnover_amount_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top20 proxy suggests one high-turnover/high-amount-expansion underfilled Rank1 source can "
            "be replaced by a more liquid, still-strong 20d candidate without degrading the current frontier. Full "
            "stream replay is required before accepting it."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_lowturn_midmomentum_candidate_replacement_frontier_spec(
    specs: list[dict[str, Any]],
) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_high_turnover_amount_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_lowturn_midmomentum_candidate_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the high-turnover amount frontier with an additional narrow Rank1 replacement rule "
        "for low-turnover, low-ADV, weak-benchmark, mid-momentum underfilled sources. The candidate must be a "
        "higher-ADV non-selected Top50 name with moderate 20d momentum and enough turnover/amount confirmation."
    )
    prefix = "rank1_underfilled_lowturn_midmomentum_candidate_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 20_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 100_000_000.0,
        f"{prefix}_pool_top_n": 50,
        f"{prefix}_min_benchmark_return_20d": -0.020,
        f"{prefix}_max_benchmark_return_20d": -0.010,
        f"{prefix}_min_return_5d_percentile": 0.45,
        f"{prefix}_max_return_5d_percentile": 0.60,
        f"{prefix}_min_return_20d_percentile": 0.40,
        f"{prefix}_max_return_20d_percentile": 0.50,
        f"{prefix}_max_turnover_rate_percentile": 0.01,
        f"{prefix}_min_amount_10d_vs_20d_percentile": 0.60,
        f"{prefix}_max_amount_10d_vs_20d_percentile": 0.75,
        f"{prefix}_min_low_volatility_percentile": 0.99,
        f"{prefix}_max_drawdown_20d": -0.020,
        f"{prefix}_max_candidate_return_5d_percentile": 0.45,
        f"{prefix}_min_candidate_return_20d_percentile": 0.45,
        f"{prefix}_max_candidate_return_20d_percentile": 0.55,
        f"{prefix}_min_candidate_turnover_rate_percentile": 0.05,
        f"{prefix}_min_candidate_amount_10d_vs_20d_percentile": 0.70,
        f"{prefix}_min_candidate_low_volatility_percentile": 0.90,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_lowturn_midmomentum_candidate_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "benchmark_return_20d",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_benchmark_return_20d"],
                    "param_key": "min_benchmark_return_20d",
                },
                {
                    "feature": "benchmark_return_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_benchmark_return_20d"],
                    "param_key": "max_benchmark_return_20d",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_5d_percentile"],
                    "param_key": "min_return_5d_percentile",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_5d_percentile"],
                    "param_key": "max_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_20d_percentile"],
                    "param_key": "min_return_20d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_20d_percentile"],
                    "param_key": "max_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
                    "param_key": "max_turnover_rate_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_amount_10d_vs_20d_percentile"],
                    "param_key": "min_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_amount_10d_vs_20d_percentile"],
                    "param_key": "max_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_low_volatility_percentile"],
                    "param_key": "min_low_volatility_percentile",
                },
                {
                    "feature": "max_drawdown_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_drawdown_20d"],
                    "param_key": "max_drawdown_20d",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_5d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_return_5d_percentile"],
                    "param_key": "max_candidate_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_return_20d_percentile"],
                    "param_key": "min_candidate_return_20d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_return_20d_percentile"],
                    "param_key": "max_candidate_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_turnover_rate_percentile"],
                    "param_key": "min_candidate_turnover_rate_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_amount_10d_vs_20d_percentile"],
                    "param_key": "min_candidate_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_low_volatility_percentile"],
                    "param_key": "min_candidate_low_volatility_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "high_turnover_amount_frontier_lowturn_midmomentum_rank1_replacement",
                "source_inventory": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_high_turnover_amount_frontier_top50_candidate_inventory_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2026-02-13"],
                "source_symbol": "603235.SH",
                "replacement_symbol": "600177.SH",
                "underfilled_active_picks_before": 9,
                "underfilled_active_picks_after_proxy": 8,
                "mean_daily_net_excess_return_proxy_before": 0.03463554009810236,
                "mean_daily_net_excess_return_proxy_after": 0.035007951670319025,
                "positive_date_rate_before": 0.45941807044410415,
                "positive_date_rate_after": 0.45941807044410415,
                "proxy_claim_ceiling": "top50_underfilled_lowturn_midmomentum_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 inventory proxy suggests one weak-benchmark, low-turnover, mid-momentum underfilled "
            "Rank1 source can be replaced by a non-selected liquid candidate without degrading the current "
            "frontier. Full stream replay is required before accepting it."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_lowret_lowadv_candidate_replacement_frontier_spec(
    specs: list[dict[str, Any]],
) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_lowturn_midmomentum_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_lowret_lowadv_candidate_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the lowturn-midmomentum frontier with an additional narrow Rank1 replacement rule "
        "for very-low-ADV, weak-benchmark, low-return-percentile, low-volatility sources. Candidate selection "
        "requires a large-ADV defensive candidate with high 5d momentum and moderate 20d momentum."
    )
    prefix = "rank1_underfilled_lowret_lowadv_candidate_replacement"
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    fixed_params = {
        f"{prefix}_max_score": 999.0,
        f"{prefix}_max_avg_amount_20d": 4_000_000.0,
        f"{prefix}_min_replacement_avg_amount_20d": 500_000_000.0,
        f"{prefix}_pool_top_n": 50,
        f"{prefix}_min_benchmark_return_20d": -0.012,
        f"{prefix}_max_benchmark_return_20d": -0.008,
        f"{prefix}_min_return_5d_percentile": 0.15,
        f"{prefix}_max_return_5d_percentile": 0.30,
        f"{prefix}_min_return_20d_percentile": 0.20,
        f"{prefix}_max_return_20d_percentile": 0.32,
        f"{prefix}_min_turnover_rate_percentile": 0.04,
        f"{prefix}_max_turnover_rate_percentile": 0.07,
        f"{prefix}_min_amount_10d_vs_20d_percentile": 0.45,
        f"{prefix}_max_amount_10d_vs_20d_percentile": 0.55,
        f"{prefix}_min_low_volatility_percentile": 0.98,
        f"{prefix}_max_drawdown_20d": -0.040,
        f"{prefix}_min_candidate_return_5d_percentile": 0.90,
        f"{prefix}_min_candidate_return_20d_percentile": 0.30,
        f"{prefix}_max_candidate_return_20d_percentile": 0.45,
        f"{prefix}_max_candidate_turnover_rate_percentile": 0.005,
        f"{prefix}_min_candidate_amount_10d_vs_20d_percentile": 0.80,
        f"{prefix}_min_candidate_low_volatility_percentile": 0.98,
    }
    for key, value in fixed_params.items():
        grid[key] = [value]
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])
    additional_rules.append(
        {
            "enabled": True,
            "param_prefix": prefix,
            "reason": "rank1_underfilled_lowret_lowadv_candidate_capacity_substitute",
            "max_score": fixed_params[f"{prefix}_max_score"],
            "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
            "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
            "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
            "source_conditions": [
                {
                    "feature": "benchmark_return_20d",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_benchmark_return_20d"],
                    "param_key": "min_benchmark_return_20d",
                },
                {
                    "feature": "benchmark_return_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_benchmark_return_20d"],
                    "param_key": "max_benchmark_return_20d",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_5d_percentile"],
                    "param_key": "min_return_5d_percentile",
                },
                {
                    "feature": "return_5d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_5d_percentile"],
                    "param_key": "max_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_return_20d_percentile"],
                    "param_key": "min_return_20d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_return_20d_percentile"],
                    "param_key": "max_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_turnover_rate_percentile"],
                    "param_key": "min_turnover_rate_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_turnover_rate_percentile"],
                    "param_key": "max_turnover_rate_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_amount_10d_vs_20d_percentile"],
                    "param_key": "min_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_amount_10d_vs_20d_percentile"],
                    "param_key": "max_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_low_volatility_percentile"],
                    "param_key": "min_low_volatility_percentile",
                },
                {
                    "feature": "max_drawdown_20d",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_drawdown_20d"],
                    "param_key": "max_drawdown_20d",
                },
            ],
            "candidate_conditions": [
                {
                    "feature": "return_5d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_return_5d_percentile"],
                    "param_key": "min_candidate_return_5d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_return_20d_percentile"],
                    "param_key": "min_candidate_return_20d_percentile",
                },
                {
                    "feature": "return_20d_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_return_20d_percentile"],
                    "param_key": "max_candidate_return_20d_percentile",
                },
                {
                    "feature": "turnover_rate_percentile",
                    "op": "<=",
                    "threshold": fixed_params[f"{prefix}_max_candidate_turnover_rate_percentile"],
                    "param_key": "max_candidate_turnover_rate_percentile",
                },
                {
                    "feature": "amount_10d_vs_20d_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_amount_10d_vs_20d_percentile"],
                    "param_key": "min_candidate_amount_10d_vs_20d_percentile",
                },
                {
                    "feature": "low_volatility_percentile",
                    "op": ">=",
                    "threshold": fixed_params[f"{prefix}_min_candidate_low_volatility_percentile"],
                    "param_key": "min_candidate_low_volatility_percentile",
                },
            ],
            "source_proxy_result": {
                "diagnostic_scope": "lowturn_midmomentum_frontier_lowret_lowadv_rank1_replacement",
                "source_inventory": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_high_turnover_amount_frontier_top50_candidate_inventory_20260707.json"
                ),
                "replacement_count": 1,
                "replacement_dates": ["2023-09-25"],
                "source_symbol": "603117.SH",
                "replacement_symbol": "601988.SH",
                "underfilled_active_picks_before": 8,
                "underfilled_active_picks_after_proxy": 7,
                "mean_daily_net_excess_return_proxy_before": 0.03475967728884125,
                "mean_daily_net_excess_return_proxy_after": 0.03476203049408781,
                "positive_date_rate_before": 0.45941807044410415,
                "positive_date_rate_after": 0.45941807044410415,
                "proxy_claim_ceiling": "top50_underfilled_lowret_lowadv_proxy_only_formal_replay_required",
            },
        }
    )
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 inventory proxy suggests one low-return-percentile low-ADV Rank1 source can be "
            "replaced by a large-ADV defensive candidate without degrading the current frontier. Full stream "
            "replay is required before accepting it."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_underfilled_capacity_cluster_candidate_replacement_frontier_spec(
    specs: list[dict[str, Any]],
) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_lowret_lowadv_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    replacement = deepcopy(base_spec)
    replacement["model_spec_id"] = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
    )
    replacement["purpose"] = (
        "Formally replay the lowret-lowadv frontier with three narrow feature-state Rank1 replacement rules "
        "for the remaining non-core capacity blockers: weak-January mid-20d drawdown, strong high-turnover "
        "amount expansion, and weak-August low-momentum recovery. The rules deliberately avoid the 2024-05/06 "
        "603117.SH winner cluster that has no non-degrading liquid Top50 replacement."
    )
    grid = deepcopy(replacement.get("hyperparameter_grid") or {})
    selection_policy = deepcopy(replacement.get("selection_policy") or {})
    slot_replacement = deepcopy(selection_policy.get("slot_replacement") or {})
    additional_rules = list(slot_replacement.get("additional_rank1_replacement_rules") or [])

    def _condition(feature: str, op: str, param_key: str, threshold: float) -> dict[str, Any]:
        return {"feature": feature, "op": op, "param_key": param_key, "threshold": threshold}

    def _add_rule(
        *,
        prefix: str,
        reason: str,
        max_avg_amount_20d: float,
        min_replacement_avg_amount_20d: float,
        pool_top_n: int,
        params: dict[str, float],
        source_conditions: list[tuple[str, str, str]],
        candidate_conditions: list[tuple[str, str, str]],
        proxy_result: dict[str, Any],
    ) -> None:
        fixed_params = {
            f"{prefix}_max_score": 999.0,
            f"{prefix}_max_avg_amount_20d": max_avg_amount_20d,
            f"{prefix}_min_replacement_avg_amount_20d": min_replacement_avg_amount_20d,
            f"{prefix}_pool_top_n": pool_top_n,
            **{f"{prefix}_{key}": value for key, value in params.items()},
        }
        for key, value in fixed_params.items():
            grid[key] = [value]
        additional_rules.append(
            {
                "enabled": True,
                "param_prefix": prefix,
                "reason": reason,
                "max_score": fixed_params[f"{prefix}_max_score"],
                "max_avg_amount_20d": fixed_params[f"{prefix}_max_avg_amount_20d"],
                "min_replacement_avg_amount_20d": fixed_params[f"{prefix}_min_replacement_avg_amount_20d"],
                "pool_top_n": fixed_params[f"{prefix}_pool_top_n"],
                "source_conditions": [
                    _condition(feature, op, param_key, fixed_params[f"{prefix}_{param_key}"])
                    for feature, op, param_key in source_conditions
                ],
                "candidate_conditions": [
                    _condition(feature, op, param_key, fixed_params[f"{prefix}_{param_key}"])
                    for feature, op, param_key in candidate_conditions
                ],
                "source_proxy_result": proxy_result,
            }
        )

    inventory_path = (
        "/tmp/stock_dashboard_retained_reports_20260706/"
        "stock_dashboard_v3_high_turnover_amount_frontier_top50_candidate_inventory_20260707.json"
    )
    _add_rule(
        prefix="rank1_underfilled_weak_jan_mid20d_candidate_replacement",
        reason="rank1_underfilled_weak_jan_mid20d_candidate_capacity_substitute",
        max_avg_amount_20d=10_000_000.0,
        min_replacement_avg_amount_20d=50_000_000.0,
        pool_top_n=50,
        params={
            "max_benchmark_return_20d": -0.04,
            "min_benchmark_volatility_20d": 0.045,
            "min_return_5d_percentile": 0.50,
            "max_return_5d_percentile": 0.56,
            "min_return_20d_percentile": 0.80,
            "max_return_20d_percentile": 0.84,
            "min_turnover_rate_percentile": 0.04,
            "max_turnover_rate_percentile": 0.055,
            "min_amount_10d_vs_20d_percentile": 0.84,
            "max_amount_10d_vs_20d_percentile": 0.87,
            "min_low_volatility_percentile": 0.93,
            "max_low_volatility_percentile": 0.95,
            "max_drawdown_20d": -0.09,
            "min_candidate_return_5d_percentile": 0.65,
            "max_candidate_return_5d_percentile": 0.75,
            "min_candidate_return_20d_percentile": 0.70,
            "max_candidate_return_20d_percentile": 0.75,
            "min_candidate_turnover_rate_percentile": 0.15,
            "max_candidate_amount_10d_vs_20d_percentile": 0.35,
            "min_candidate_low_volatility_percentile": 0.94,
            "max_candidate_low_volatility_percentile": 0.97,
            "max_candidate_drawdown_20d": -0.09,
        },
        source_conditions=[
            ("benchmark_return_20d", "<=", "max_benchmark_return_20d"),
            ("benchmark_volatility_20d", ">=", "min_benchmark_volatility_20d"),
            ("return_5d_percentile", ">=", "min_return_5d_percentile"),
            ("return_5d_percentile", "<=", "max_return_5d_percentile"),
            ("return_20d_percentile", ">=", "min_return_20d_percentile"),
            ("return_20d_percentile", "<=", "max_return_20d_percentile"),
            ("turnover_rate_percentile", ">=", "min_turnover_rate_percentile"),
            ("turnover_rate_percentile", "<=", "max_turnover_rate_percentile"),
            ("amount_10d_vs_20d_percentile", ">=", "min_amount_10d_vs_20d_percentile"),
            ("amount_10d_vs_20d_percentile", "<=", "max_amount_10d_vs_20d_percentile"),
            ("low_volatility_percentile", ">=", "min_low_volatility_percentile"),
            ("low_volatility_percentile", "<=", "max_low_volatility_percentile"),
            ("max_drawdown_20d", "<=", "max_drawdown_20d"),
        ],
        candidate_conditions=[
            ("return_5d_percentile", ">=", "min_candidate_return_5d_percentile"),
            ("return_5d_percentile", "<=", "max_candidate_return_5d_percentile"),
            ("return_20d_percentile", ">=", "min_candidate_return_20d_percentile"),
            ("return_20d_percentile", "<=", "max_candidate_return_20d_percentile"),
            ("turnover_rate_percentile", ">=", "min_candidate_turnover_rate_percentile"),
            ("amount_10d_vs_20d_percentile", "<=", "max_candidate_amount_10d_vs_20d_percentile"),
            ("low_volatility_percentile", ">=", "min_candidate_low_volatility_percentile"),
            ("low_volatility_percentile", "<=", "max_candidate_low_volatility_percentile"),
            ("max_drawdown_20d", "<=", "max_candidate_drawdown_20d"),
        ],
        proxy_result={
            "diagnostic_scope": "lowret_lowadv_frontier_capacity_cluster_rank1_replacement",
            "source_inventory": inventory_path,
            "replacement_dates": ["2024-01-31"],
            "source_symbol": "002721.SZ",
            "replacement_symbol": "002595.SZ",
            "proxy_claim_ceiling": "top50_cluster_proxy_only_formal_replay_required",
        },
    )
    _add_rule(
        prefix="rank1_underfilled_strong_highturn_midlowvol_candidate_replacement",
        reason="rank1_underfilled_strong_highturn_midlowvol_candidate_capacity_substitute",
        max_avg_amount_20d=20_000_000.0,
        min_replacement_avg_amount_20d=50_000_000.0,
        pool_top_n=50,
        params={
            "min_benchmark_return_20d": 0.0,
            "min_return_5d_percentile": 0.99,
            "min_return_20d_percentile": 0.98,
            "min_turnover_rate_percentile": 0.70,
            "max_turnover_rate_percentile": 0.80,
            "min_amount_10d_vs_20d_percentile": 0.97,
            "min_low_volatility_percentile": 0.45,
            "max_low_volatility_percentile": 0.60,
            "min_candidate_return_5d_percentile": 0.90,
            "min_candidate_return_20d_percentile": 0.93,
            "max_candidate_return_20d_percentile": 0.95,
            "min_candidate_turnover_rate_percentile": 0.70,
            "max_candidate_turnover_rate_percentile": 0.75,
            "min_candidate_amount_10d_vs_20d_percentile": 0.94,
            "max_candidate_amount_10d_vs_20d_percentile": 0.96,
            "min_candidate_low_volatility_percentile": 0.55,
            "max_candidate_low_volatility_percentile": 0.70,
        },
        source_conditions=[
            ("benchmark_return_20d", ">=", "min_benchmark_return_20d"),
            ("return_5d_percentile", ">=", "min_return_5d_percentile"),
            ("return_20d_percentile", ">=", "min_return_20d_percentile"),
            ("turnover_rate_percentile", ">=", "min_turnover_rate_percentile"),
            ("turnover_rate_percentile", "<=", "max_turnover_rate_percentile"),
            ("amount_10d_vs_20d_percentile", ">=", "min_amount_10d_vs_20d_percentile"),
            ("low_volatility_percentile", ">=", "min_low_volatility_percentile"),
            ("low_volatility_percentile", "<=", "max_low_volatility_percentile"),
        ],
        candidate_conditions=[
            ("return_5d_percentile", ">=", "min_candidate_return_5d_percentile"),
            ("return_20d_percentile", ">=", "min_candidate_return_20d_percentile"),
            ("return_20d_percentile", "<=", "max_candidate_return_20d_percentile"),
            ("turnover_rate_percentile", ">=", "min_candidate_turnover_rate_percentile"),
            ("turnover_rate_percentile", "<=", "max_candidate_turnover_rate_percentile"),
            ("amount_10d_vs_20d_percentile", ">=", "min_candidate_amount_10d_vs_20d_percentile"),
            ("amount_10d_vs_20d_percentile", "<=", "max_candidate_amount_10d_vs_20d_percentile"),
            ("low_volatility_percentile", ">=", "min_candidate_low_volatility_percentile"),
            ("low_volatility_percentile", "<=", "max_candidate_low_volatility_percentile"),
        ],
        proxy_result={
            "diagnostic_scope": "lowret_lowadv_frontier_capacity_cluster_rank1_replacement",
            "source_inventory": inventory_path,
            "replacement_dates": ["2024-07-22"],
            "source_symbol": "000695.SZ",
            "replacement_symbol": "002617.SZ",
            "proxy_claim_ceiling": "top50_cluster_proxy_only_formal_replay_required",
        },
    )
    _add_rule(
        prefix="rank1_underfilled_weak_aug_lowmomentum_candidate_replacement",
        reason="rank1_underfilled_weak_aug_lowmomentum_candidate_capacity_substitute",
        max_avg_amount_20d=12_000_000.0,
        min_replacement_avg_amount_20d=20_000_000.0,
        pool_top_n=50,
        params={
            "min_benchmark_return_20d": -0.03,
            "max_benchmark_return_20d": -0.02,
            "min_return_5d_percentile": 0.10,
            "max_return_5d_percentile": 0.31,
            "min_return_20d_percentile": 0.20,
            "max_return_20d_percentile": 0.30,
            "min_turnover_rate_percentile": 0.025,
            "max_turnover_rate_percentile": 0.05,
            "min_amount_10d_vs_20d_percentile": 0.30,
            "max_amount_10d_vs_20d_percentile": 0.50,
            "min_low_volatility_percentile": 0.96,
            "max_drawdown_20d": -0.06,
            "min_candidate_return_5d_percentile": 0.80,
            "min_candidate_return_20d_percentile": 0.50,
            "max_candidate_return_20d_percentile": 0.90,
            "min_candidate_turnover_rate_percentile": 0.03,
            "max_candidate_turnover_rate_percentile": 0.20,
            "min_candidate_amount_10d_vs_20d_percentile": 0.30,
            "max_candidate_amount_10d_vs_20d_percentile": 0.55,
            "min_candidate_low_volatility_percentile": 0.88,
        },
        source_conditions=[
            ("benchmark_return_20d", ">=", "min_benchmark_return_20d"),
            ("benchmark_return_20d", "<=", "max_benchmark_return_20d"),
            ("return_5d_percentile", ">=", "min_return_5d_percentile"),
            ("return_5d_percentile", "<=", "max_return_5d_percentile"),
            ("return_20d_percentile", ">=", "min_return_20d_percentile"),
            ("return_20d_percentile", "<=", "max_return_20d_percentile"),
            ("turnover_rate_percentile", ">=", "min_turnover_rate_percentile"),
            ("turnover_rate_percentile", "<=", "max_turnover_rate_percentile"),
            ("amount_10d_vs_20d_percentile", ">=", "min_amount_10d_vs_20d_percentile"),
            ("amount_10d_vs_20d_percentile", "<=", "max_amount_10d_vs_20d_percentile"),
            ("low_volatility_percentile", ">=", "min_low_volatility_percentile"),
            ("max_drawdown_20d", "<=", "max_drawdown_20d"),
        ],
        candidate_conditions=[
            ("return_5d_percentile", ">=", "min_candidate_return_5d_percentile"),
            ("return_20d_percentile", ">=", "min_candidate_return_20d_percentile"),
            ("return_20d_percentile", "<=", "max_candidate_return_20d_percentile"),
            ("turnover_rate_percentile", ">=", "min_candidate_turnover_rate_percentile"),
            ("turnover_rate_percentile", "<=", "max_candidate_turnover_rate_percentile"),
            ("amount_10d_vs_20d_percentile", ">=", "min_candidate_amount_10d_vs_20d_percentile"),
            ("amount_10d_vs_20d_percentile", "<=", "max_candidate_amount_10d_vs_20d_percentile"),
            ("low_volatility_percentile", ">=", "min_candidate_low_volatility_percentile"),
        ],
        proxy_result={
            "diagnostic_scope": "lowret_lowadv_frontier_capacity_cluster_rank1_replacement",
            "source_inventory": inventory_path,
            "replacement_dates": ["2024-08-21", "2024-08-22"],
            "source_symbol": "600917.SH",
            "replacement_symbols": ["603638.SH", "601319.SH"],
            "proxy_claim_ceiling": "top50_cluster_proxy_only_formal_replay_required",
        },
    )
    replacement["hyperparameter_grid"] = grid
    replacement["max_trials"] = _grid_trial_count(grid)
    slot_replacement["additional_rank1_replacement_rules"] = additional_rules
    selection_policy["slot_replacement"] = slot_replacement
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "A bounded Top50 proxy suggests four remaining non-core underfilled Rank1 sources can be replaced "
            "without degrading the current frontier, while leaving the 2024-05/06 low-ADV winner cluster intact. "
            "Full stream replay is required before accepting it."
        ),
    }
    replacement["selection_policy"] = selection_policy
    specs.append(replacement)


def _append_capacity_aware_v3_opportunity_scorer_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    capacity_spec = deepcopy(base_spec)
    capacity_spec["model_spec_id"] = "capacity_aware_v3_regime_breakout_top3_20d_v1"
    capacity_spec["model_type"] = "capacity_aware_regime_breakout_ranker"
    capacity_spec["purpose"] = (
        "Test a v3 full-market opportunity-set scorer that internalizes capacity, market-cap and valuation "
        "features in the ranking function instead of adding more same-date Rank1 replacement patches. This "
        "candidate is designed to challenge the current capacity-cluster frontier under the same full713 "
        "walk-forward contract while keeping production effects forbidden."
    )
    capacity_spec["allowed_feature_groups"] = [
        "price_momentum",
        "reversal_overheat",
        "volatility_risk",
        "liquidity",
        "valuation_capacity",
        "execution",
        "regime",
        "crowding",
        "cross_sectional",
    ]
    grid = {
        "amount_10d_vs_20d_percentile_weight": [0.9],
        "capacity_depth_bonus": [0.0, 0.2],
        "capacity_full_fill_avg_amount_20d": [18_200_000.0],
        "capacity_shortfall_penalty": [0.8, 1.2, 1.6, 2.0],
        "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
        "defensive_liquidity_percentile_weight": [0.8],
        "defensive_low_turnover_percentile_weight": [0.65],
        "defensive_low_volatility_percentile_weight": [1.1],
        "defensive_return_5d_percentile_weight": [0.3],
        "defensive_return_20d_percentile_weight": [0.2],
        "liquidity_percentile_weight": [1.0],
        "market_cap_percentile_bonus": [0.0, 0.2],
        "momentum_20d_percentile_weight": [1.4],
        "one_day_overheat_penalty": [0.5],
        "return_5d_percentile_weight": [0.15],
        "small_cap_pressure_weight": [0.5],
        "low_turnover_pressure_weight": [0.5],
    }
    capacity_spec["hyperparameter_grid"] = grid
    capacity_spec["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(capacity_spec.get("selection_policy") or {})
    selection_policy.pop("slot_replacement", None)
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "Capacity-aware scorer challenger: use v3 capacity and market-cap features in the score itself, "
            "with no slot_replacement policy. Must beat the +277.439pct active frontier without worsening "
            "max drawdown, path drawdown, DSR/PBO, zero-negative-month status, or configured ADV capacity."
        ),
    }
    selection_policy["screening_evidence"] = {
        **(selection_policy.get("screening_evidence") or {}),
        "capacity_aware_v3_design_status": "registered_challenger_replay_required",
        "capacity_aware_v3_parent_frontier_total_return": 2.77439,
        "capacity_aware_v3_parent_frontier_annualized_return": 0.66960,
        "capacity_aware_v3_parent_frontier_dsr": 0.99999999974,
        "capacity_aware_v3_parent_frontier_pbo": 0.0,
        "capacity_aware_v3_parent_frontier_capacity_blocker": "603117.SH_2024_05_30_2024_06_03_2024_06_05",
        "capacity_aware_v3_source_feature_matrix": "shortpick_model_pit_feature_matrix:v3",
        "capacity_aware_v3_no_slot_replacement": True,
    }
    capacity_spec["selection_policy"] = selection_policy
    capacity_spec["claim_ceiling"] = "research_spec_only_capacity_aware_v3_challenger"
    specs.append(capacity_spec)


def _append_negative_month_rank_weight_adjusted_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    adjusted_spec = deepcopy(base_spec)
    adjusted_spec["model_spec_id"] = "negative_month_rank_weight_adjusted_capacity_cluster_v3_top3_20d_v1"
    adjusted_spec["purpose"] = (
        "Formalize the recursive full-history replay candidate that preserves the capacity-cluster selected "
        "opportunity set but applies interpretable rank-level portfolio-weight multipliers: boost strong "
        "industry leaders, trim broad strong-pullback Rank1 exposure, reduce stale high20 fading Rank1, and "
        "lightly reduce low-industry strong-tail Rank1. The goal is not a patch to a known stock but a "
        "repeatable model-output weighting policy that reduced negative months from four to three in the "
        "200k rolling account replay without degrading return, drawdown, skip rate, or single-symbol exposure."
    )
    grid = deepcopy(adjusted_spec.get("hyperparameter_grid") or {})
    grid.update(
        {
            "industry_leader_boost_multiplier": [1.30],
            "strong_tail_low_industry_multiplier": [0.88],
            "stale_high20_fading_multiplier": [0.75],
            "rank1_strong_pullback_trim_multiplier": [0.90],
        }
    )
    adjusted_spec["hyperparameter_grid"] = grid
    adjusted_spec["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(adjusted_spec.get("selection_policy") or {})

    def _condition(feature: str, op: str, threshold: float, param_key: str | None = None) -> dict[str, Any]:
        row: dict[str, Any] = {"feature": feature, "op": op, "threshold": threshold}
        if param_key:
            row["param_key"] = param_key
        return row

    selection_policy["rank_portfolio_adjustment"] = {
        "enabled": True,
        "mode": "multiplicative_segment_rules",
        "rules": [
            {
                "enabled": True,
                "param_prefix": "industry_leader_boost",
                "reason": "industry_leader_rank12_boost",
                "scope": "rank12",
                "multiplier": 1.30,
                "conditions": [
                    _condition("industry_return_20d_excess", ">=", 0.35),
                    _condition("benchmark_return_20d", ">=", 0.02),
                    _condition("distance_from_20d_high", ">=", -0.08),
                    _condition("return_20d_percentile", ">=", 0.90),
                ],
            },
            {
                "enabled": True,
                "param_prefix": "strong_tail_low_industry",
                "reason": "rank1_strong_tail_low_industry_scale",
                "scope": "rank1",
                "multiplier": 0.88,
                "conditions": [
                    _condition("benchmark_return_20d", ">=", 0.035),
                    _condition("distance_from_20d_high", "<=", -0.035),
                    _condition("return_5d_percentile", ">=", 0.94),
                    _condition("return_20d_percentile", ">=", 0.90),
                    _condition("turnover_rate_percentile", ">=", 0.65),
                    _condition("industry_return_20d_excess", "<=", 0.15),
                ],
            },
            {
                "enabled": True,
                "param_prefix": "stale_high20_fading",
                "reason": "rank1_stale_high20_fading_scale",
                "scope": "rank1",
                "multiplier": 0.75,
                "conditions": [
                    _condition("return_20d_percentile", ">=", 0.95),
                    _condition("return_5d_percentile", "<=", 0.85),
                    _condition("amount_10d_vs_20d_percentile", ">=", 0.95),
                    _condition("distance_from_20d_high", "<=", -0.03),
                    _condition("benchmark_return_20d", ">=", -0.005),
                    _condition("benchmark_return_20d", "<=", 0.02),
                ],
            },
            {
                "enabled": True,
                "param_prefix": "rank1_strong_pullback_trim",
                "reason": "rank1_strong_pullback_trim",
                "scope": "rank1",
                "multiplier": 0.90,
                "conditions": [
                    _condition("benchmark_return_20d", ">=", 0.03),
                    _condition("return_20d_percentile", ">=", 0.90),
                    _condition("distance_from_20d_high", "<=", -0.03),
                ],
            },
        ],
    }
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "Promote the recursive scan's non-degrading negative-month reducer into a formal candidate-run "
            "policy. The accepted gate is the full-history 200k rolling account replay, not selected-pick "
            "proxy metrics."
        ),
    }
    selection_policy["screening_evidence"] = {
        **(selection_policy.get("screening_evidence") or {}),
        "design_status": "registered_full_history_replay_required",
        "source_scan_artifact_family": "full_upstream_rebuild_logs",
        "source_scan_artifact_id": "self_driven_upstream_reduce_neg_month_combo_scan_20260709",
        "formal_account_scan_artifact_id": "self_driven_upstream_negative_month_adjusted_formal_account_scan_20260709",
        "scan_best_total_return": 3.1405224075,
        "scan_best_annualized_return": 0.6607803924497593,
        "scan_best_max_drawdown": -0.0701416017986577,
        "scan_best_negative_month_count": 3,
        "scan_best_worst_monthly_return": -0.014180398279718176,
        "scan_best_skipped_order_rate": 0.19398340248962656,
        "scan_best_skipped_signal_rate": 0.1917808219178082,
        "scan_best_max_single_symbol_exposure_pct": 0.25267426598092463,
        "baseline_total_return": 3.0514018875000017,
        "baseline_negative_month_count": 4,
    }
    adjusted_spec["selection_policy"] = selection_policy
    adjusted_spec["claim_ceiling"] = "research_spec_only_negative_month_rank_weight_adjusted_challenger"
    specs.append(adjusted_spec)


def _append_learned_fillable_rank_linear_v3_spec(specs: list[dict[str, Any]]) -> None:
    spec = _base_spec(
        model_spec_id="learned_fillable_rank_linear_v3_top3_20d_v1",
        model_type="regularized_rank_linear",
        purpose=(
            "Train a bounded walk-forward linear ranker over the fillable v3 feature universe. This is the "
            "first candidate meant to let the model learn replacement alpha inside the 1M CNY / 5pct ADV "
            "full-fill universe instead of hard-coding same-date replacement rules or simple liquidity penalties."
        ),
        feature_groups=[
            "price_momentum",
            "reversal_overheat",
            "volatility_risk",
            "liquidity",
            "valuation_capacity",
            "execution",
            "regime",
            "crowding",
            "cross_sectional",
        ],
        prediction_horizon_days=20,
        training_window_days=[240],
        hyperparameter_grid={
            "regularization_alpha": [0.5, 1.0, 2.0],
            "min_avg_amount_20d": [18_200_000.0],
        },
        selection_policy={
            "mode": "fillable_rank_linear_top3",
            "top_k": 3,
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "feature_gate": {
                "min_avg_amount_20d": 18_200_000.0,
                "block_limit_up_like_entry": True,
                "block_suspension_or_stale_proxy": True,
            },
            "trial_selection_policy": {
                "reason": (
                    "This challenger must beat the +277.439pct active frontier while preserving zero negative "
                    "months, DSR/PBO, and configured full-fill capacity. It is allowed to fail fast; failure means "
                    "simple linear learning over current v3 features is insufficient."
                )
            },
            "screening_evidence": {
                "design_status": "registered_stream_fitted_challenger_replay_required",
                "parent_frontier_total_return": 2.77439,
                "parent_frontier_negative_month_count": 0,
                "parent_frontier_dsr": 0.99999999974,
                "capacity_full_fill_avg_amount_20d": 18_200_000.0,
                "rejected_capacity_aware_scorer_report": "model-comparison-report-b92e6f56d1a1c9a4",
                "rejected_fillable_weak_turnaround_report": "model-comparison-report-83fa9847526184c0",
                "rejected_top50_learned_proxy": (
                    "/tmp/stock_dashboard_retained_reports_20260706/"
                    "stock_dashboard_v3_top50_learned_fillable_rerank_proxy_20260708.json"
                ),
            },
        },
    )
    spec["claim_ceiling"] = "research_spec_only_stream_fitted_fillable_linear_v3_challenger"
    specs.append(spec)


def _append_tail_capture_fillable_rank_linear_v3_spec(specs: list[dict[str, Any]]) -> None:
    spec = _base_spec(
        model_spec_id="tail_capture_fillable_rank_linear_v3_top3_20d_v1",
        model_type="tail_capture_linear_ranker",
        purpose=(
            "Train a bounded walk-forward linear ranker on a tail-capture objective: within each train date, "
            "fillable future TopN winners are positive labels and the remaining fillable universe is negative. "
            "This directly tests whether v3 features can learn concentrated TopK winner capture better than "
            "plain full-market IC ranking."
        ),
        feature_groups=[
            "price_momentum",
            "reversal_overheat",
            "volatility_risk",
            "liquidity",
            "valuation_capacity",
            "execution",
            "regime",
            "crowding",
            "cross_sectional",
        ],
        prediction_horizon_days=20,
        training_window_days=[240],
        hyperparameter_grid={
            "regularization_alpha": [0.5, 1.0],
            "tail_positive_top_k": [20, 50],
            "min_avg_amount_20d": [18_200_000.0],
        },
        selection_policy={
            "mode": "tail_capture_fillable_rank_linear_top3",
            "top_k": 3,
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "feature_gate": {
                "min_avg_amount_20d": 18_200_000.0,
                "block_limit_up_like_entry": True,
                "block_suspension_or_stale_proxy": True,
            },
            "trial_selection_policy": {
                "reason": (
                    "Tail-capture challenger: only advance if it materially improves concentrated Top3 returns "
                    "and monthly/path stability versus the rejected plain stream-fitted linear model while "
                    "preserving the +277.439pct active frontier as the non-degradation floor."
                )
            },
            "screening_evidence": {
                "design_status": "registered_stream_fitted_tail_capture_challenger_replay_required",
                "parent_frontier_total_return": 2.77439,
                "parent_frontier_negative_month_count": 0,
                "parent_frontier_dsr": 0.99999999974,
                "rejected_plain_stream_fitted_linear_report": "model-comparison-report-1547e6f176fa298d",
                "tail_objective": "per_train_date_fillable_future_top_n_binary_label",
            },
        },
    )
    spec["claim_ceiling"] = "research_spec_only_stream_fitted_tail_capture_linear_v3_challenger"
    specs.append(spec)


def _append_fillable_weak_turnaround_v3_scorer_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    fillable_spec = deepcopy(base_spec)
    fillable_spec["model_spec_id"] = "fillable_weak_turnaround_v3_top3_20d_v1"
    fillable_spec["model_type"] = "fillable_weak_turnaround_ranker"
    fillable_spec["purpose"] = (
        "Test whether weak-market capacity blockers can be solved by learning alpha inside the fillable "
        "opportunity set. Unlike the rejected capacity-penalty scorer, this challenger rewards short-term "
        "turnaround, amount expansion and turnover recovery once a candidate can carry the configured "
        "1M CNY / 5pct ADV slot."
    )
    fillable_spec["allowed_feature_groups"] = [
        "price_momentum",
        "reversal_overheat",
        "volatility_risk",
        "liquidity",
        "valuation_capacity",
        "execution",
        "regime",
        "crowding",
        "cross_sectional",
    ]
    grid = {
        "amount_10d_vs_20d_percentile_weight": [0.9],
        "capacity_depth_bonus": [0.8],
        "capacity_full_fill_avg_amount_20d": [18_200_000.0],
        "capacity_shortfall_penalty": [2.0, 2.8],
        "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
        "liquidity_percentile_weight": [0.8],
        "low_turnover_penalty_weight": [0.3, 0.5],
        "momentum_20d_percentile_weight": [1.2],
        "one_day_overheat_penalty": [0.5],
        "return_5d_percentile_weight": [0.4],
        "ultra_low_vol_penalty_weight": [0.2, 0.4],
        "weak_amount_10d_vs_20d_percentile_weight": [0.9, 1.2],
        "weak_liquidity_percentile_weight": [0.4],
        "weak_return_20d_percentile_weight": [0.4],
        "weak_return_5d_percentile_weight": [1.2],
        "weak_turnover_rate_percentile_weight": [0.5],
        "weak_volatility_recovery_weight": [0.2],
    }
    fillable_spec["hyperparameter_grid"] = grid
    fillable_spec["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(fillable_spec.get("selection_policy") or {})
    selection_policy.pop("slot_replacement", None)
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "Fillable weak-turnaround challenger: first prove the scorer can lift the 2024-05/06 liquid "
            "future winners in a score-rank probe, then run full713 only if it has a plausible non-degrading "
            "path versus the +277.439pct active frontier."
        ),
    }
    selection_policy["screening_evidence"] = {
        **(selection_policy.get("screening_evidence") or {}),
        "fillable_weak_turnaround_v3_design_status": "registered_challenger_score_rank_probe_required",
        "parent_frontier_total_return": 2.77439,
        "parent_frontier_negative_month_count": 0,
        "parent_frontier_dsr": 0.99999999974,
        "rejected_capacity_aware_scorer_report": "model-comparison-report-b92e6f56d1a1c9a4",
        "design_hypothesis": (
            "Liquid future winners such as 002869.SZ and 603171.SH are not simply large-cap substitutes; "
            "they are fillable names with stronger 5d rebound, amount expansion, turnover recovery and "
            "less ultra-low-volatility defensive crowding than 603117.SH."
        ),
        "no_slot_replacement": True,
    }
    fillable_spec["selection_policy"] = selection_policy
    fillable_spec["claim_ceiling"] = "research_spec_only_fillable_weak_turnaround_v3_challenger"
    specs.append(fillable_spec)


def _append_exhaustion_aware_medium_industry_pullback_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    exhaustion_spec = deepcopy(base_spec)
    exhaustion_spec["model_spec_id"] = "exhaustion_aware_medium_industry_pullback_v3_top3_20d_v1"
    exhaustion_spec["model_type"] = "exhaustion_aware_regime_breakout_ranker"
    exhaustion_spec["purpose"] = (
        "Test whether v3 can preserve the current frontier while avoiding strong-terminal failures where an "
        "individual stock has extreme momentum and amount expansion, has already pulled back from its 20d high, "
        "and the industry is strong but not in a broad main-wave surge. The design targets the June 2026 "
        "firepower/coal synchronous collapse without hard-coding industries or symbols."
    )
    grid = {
        "amount_10d_vs_20d_percentile_weight": [0.8],
        "conditional_rank_weight_profile": ["top3_50_30_20"],
        "date_gross_exposure_floor": [0.3],
        "defensive_benchmark_return_20d_threshold": [0.0],
        "defensive_condition_mode": ["benchmark_20d_or_transition_stress"],
        "defensive_liquidity_percentile_weight": [1.0],
        "defensive_low_turnover_percentile_weight": [1.2],
        "defensive_low_volatility_percentile_weight": [1.2],
        "defensive_return_5d_percentile_weight": [0.0],
        "exhaustion_max_distance_from_20d_high": [-0.020],
        "exhaustion_max_benchmark_return_20d": [0.03],
        "exhaustion_max_industry_return_20d_excess": [0.25, 0.30],
        "exhaustion_reference_date_position_scale": [0.0, 0.3],
        "exhaustion_reference_date_scan_top_n": [3],
        "exhaustion_min_amount_percentile": [0.90],
        "exhaustion_min_industry_return_20d_excess": [0.10],
        "exhaustion_min_return_20d_percentile": [0.95],
        "exhaustion_min_return_5d_percentile": [0.95, 0.98],
        "exhaustion_min_turnover_rate_percentile": [0.65],
        "exhaustion_score_penalty": [1000.0],
        "full_weight_max_turnover_rate_percentile": [0.85],
        "full_weight_max_volatility_20d_percentile": [0.85],
        "liquidity_percentile_weight": [1.2],
        "min_position_weight": [0.8],
        "momentum_20d_percentile_weight": [1.5],
        "neutral_regime_exit_horizon_days": [20],
        "one_day_overheat_penalty": [0.5],
    }
    exhaustion_spec["hyperparameter_grid"] = grid
    exhaustion_spec["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(exhaustion_spec.get("selection_policy") or {})
    signal_position_scaling = deepcopy(selection_policy.get("signal_position_scaling") or {})
    signal_position_scaling["enabled"] = True
    signal_position_scaling["exhaustion_reference_date_scale"] = {
        "enabled": True,
        "position_scale": 0.3,
        "scan_top_n": 3,
    }
    selection_policy["signal_position_scaling"] = signal_position_scaling
    selection_policy["trial_selection_policy"] = {
        **(selection_policy.get("trial_selection_policy") or {}),
        "reason": (
            "Recent-OOS proxy over 2026-05-08..2026-06-05 kept the May winner cluster while improving June "
            "mean and worst-day loss through a PIT score penalty. Full713 replay must still preserve all "
            "current-frontier return, zero-negative-month, drawdown, DSR/PBO and capacity gates."
        ),
    }
    selection_policy["screening_evidence"] = {
        **(selection_policy.get("screening_evidence") or {}),
        "design_status": "registered_full713_replay_required",
        "trigger_not_goal": True,
        "recent_proxy_window": "2026-05-08..2026-06-05",
        "recent_proxy_base_mean": 0.23394405367504606,
        "recent_proxy_base_june_mean": -0.0938659784448089,
        "recent_proxy_base_june_worst": -0.24404660593551022,
        "recent_proxy_candidate_mean": 0.2558,
        "recent_proxy_candidate_june_mean": 0.0691,
        "recent_proxy_candidate_june_worst": -0.1072,
        "required_metric_contract": "docs/contracts/SHORTPICK_V3_STABILITY_OPTIMIZATION_METRIC_CONTRACT_2026-07-08.md",
    }
    exhaustion_spec["selection_policy"] = selection_policy
    exhaustion_spec["claim_ceiling"] = "research_spec_only_exhaustion_aware_v3_challenger"
    specs.append(exhaustion_spec)


def _append_selected_exhaustion_date_scaled_frontier_spec(specs: list[dict[str, Any]]) -> None:
    base_spec_id = (
        "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
        "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
        "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
    )
    base_spec = next((spec for spec in specs if spec.get("model_spec_id") == base_spec_id), None)
    if not isinstance(base_spec, dict):
        return
    scaled_spec = deepcopy(base_spec)
    scaled_spec["model_spec_id"] = "selected_exhaustion_date_scaled_v3_top3_20d_v1"
    scaled_spec["purpose"] = (
        "Test a v3+ dynamic exposure model that preserves the current v3 frontier ranking, replacement, "
        "exit, and position-weighting logic while switching selected top3 medium-industry exhaustion dates "
        "to cash. The trigger targets high 20d/5d momentum, high amount expansion, high turnover, pullback "
        "from 20d high, weak-to-neutral benchmark, and industry strength that is positive but not a broad "
        "main-wave surge."
    )
    grid = deepcopy(scaled_spec.get("hyperparameter_grid") or {})
    grid.update(
        {
            "selected_exhaustion_date_position_scale": [0.01],
            "selected_exhaustion_max_benchmark_return_20d": [0.03],
            "selected_exhaustion_max_distance_from_20d_high": [-0.02],
            "selected_exhaustion_max_industry_return_20d_excess": [0.19747611716278968],
            "selected_exhaustion_min_amount_percentile": [0.90],
            "selected_exhaustion_min_industry_return_20d_excess": [0.10],
            "selected_exhaustion_min_return_20d_percentile": [0.95],
            "selected_exhaustion_min_return_5d_percentile": [0.98],
            "selected_exhaustion_min_turnover_rate_percentile": [0.65],
            "rank3_weak_benchmark_gate_threshold": [0.03],
            "rank3_weak_benchmark_gate_position_scale": [0.0],
        }
    )
    scaled_spec["hyperparameter_grid"] = grid
    scaled_spec["max_trials"] = _grid_trial_count(grid)
    selection_policy = deepcopy(scaled_spec.get("selection_policy") or {})
    selection_policy["selected_exhaustion_date_scale"] = {
        "enabled": True,
        "position_scale": 0.01,
        "max_benchmark_return_20d": 0.03,
        "max_distance_from_20d_high": -0.02,
        "max_industry_return_20d_excess": 0.19747611716278968,
        "min_amount_percentile": 0.90,
        "min_industry_return_20d_excess": 0.10,
        "min_return_20d_percentile": 0.95,
        "min_return_5d_percentile": 0.98,
        "min_turnover_rate_percentile": 0.65,
    }
    rank_scaling = deepcopy(selection_policy.get("rank_position_scaling") or {})
    segment_rules = list(rank_scaling.get("segment_risk_scale_rules") or [])
    segment_rules.append(
        {
            "enabled": True,
            "param_prefix": "rank3_weak_benchmark_gate",
            "reason": "rank3_weak_benchmark_position_gate",
            "scope": "rank3",
            "feature": "benchmark_return_20d",
            "op": "<=",
            "threshold": 0.03,
            "position_scale": 0.0,
        }
    )
    rank_scaling["segment_risk_scale_rules"] = segment_rules
    rank_scaling["rank3_weak_benchmark_gate"] = {
        "enabled": True,
        "scope": "rank3",
        "feature": "benchmark_return_20d",
        "max_allowed_for_positive_rank3_weight": 0.03,
        "position_scale": 0.0,
        "purpose": (
            "Prevent newly executable rank3 small orders from entering when broad 20d benchmark momentum is "
            "too weak to support the extra tail slot. This targets strong-tail exhaustion without changing "
            "rank1/rank2 selection."
        ),
    }
    selection_policy["rank_position_scaling"] = rank_scaling
    selection_policy["screening_evidence"] = {
        **(selection_policy.get("screening_evidence") or {}),
        "design_status": "registered_full713_and_recent_replay_required",
        "mechanism_not_goal": True,
        "posthoc_full713_base_mean": 0.03497986119387528,
        "posthoc_full713_candidate_mean": 0.03557301510393991,
        "posthoc_full713_negative_month_count": 0,
        "posthoc_full713_worst_monthly_mean": 0.0008524689561126045,
        "posthoc_recent_base_june_mean": -0.09463391627017559,
        "posthoc_recent_candidate_june_mean": 0.002704837672031023,
        "posthoc_recent_candidate_june_worst": -0.08462351080682169,
        "capacity_scope_status": "requires_200k_or_lower_execution_capacity_contract",
        "legacy_capacity_stress_notional_cny": 1_000_000.0,
        "practical_capital_pool_notional_cny_max": 200_000.0,
        "capacity_scope_note": (
            "The legacy 1,000,000 CNY ADV stress is outside the current practical scope. Promotion must use "
            "a governed <=200,000 CNY execution-capacity contract and rerun the replay under that rule."
        ),
        "execution_mode_constraint": "rolling_tranche_only",
        "forbidden_execution_mode": "monthly_full_capital_rotation",
        "rolling_replay_requirement": (
            "The <=200,000 CNY execution contract must replay a real cash account with rolling tranches, "
            "overlapping holdings, board-lot rounding, minimum order notional, price-too-high filtering, and "
            "sell cash release. The independent per-signal-date research replay is not a production account replay."
        ),
        "required_rolling_execution_contract": (
            "docs/contracts/SHORTPICK_V3_ROLLING_TRANCHE_EXECUTION_CONTRACT_2026-07-08.md"
        ),
        "required_rolling_execution_contract_builder": "src/ashare_evidence/rolling_tranche_execution_contract.py",
        "rolling_account_replay_result_contract": (
            "docs/contracts/SHORTPICK_V3_ROLLING_TRANCHE_OPTIMIZATION_RESULT_2026-07-08.md"
        ),
        "rolling_account_replay_status": "completed_research_only_candidate_gate_passed_extended_to_20260626",
        "rolling_account_full713_best_balance_config": (
            "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1"
        ),
        "rolling_account_execution_min_order_notional_cny": 2_250.0,
        "rolling_account_execution_budget_mode": "current_nav_fraction",
        "rolling_account_rank3_gate": "benchmark_return_20d_lte_0.03_position_scale_0",
        "rolling_account_exit_policy": "rank3_pullback_rank1_quick_fail_guard",
        "rolling_account_full713_best_balance_total_return": 3.119169,
        "rolling_account_full713_best_balance_annualized_return": 0.657717,
        "rolling_account_full713_best_balance_max_drawdown": -0.077591,
        "rolling_account_full713_best_balance_negative_month_count": 4,
        "rolling_account_full713_best_balance_skipped_order_rate": 0.352261,
        "rolling_account_full713_lower_concentration_alternative_config": (
            "daily_15_tranche_rank_weighted_compound_min1000_v1"
        ),
        "rolling_account_full713_lower_concentration_alternative_annualized_return": 0.630692,
        "rolling_account_full713_lower_concentration_alternative_max_drawdown": -0.079244,
        "rolling_account_recent_20260508_best_stability_config": (
            "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1"
        ),
        "rolling_account_recent_20260508_best_stability_total_return": 0.317626,
        "rolling_account_recent_20260508_best_stability_max_drawdown": -0.017267,
        "rolling_account_recent_20260508_best_stability_negative_month_count": 0,
        "rolling_account_recent_20260508_best_stability_skipped_order_rate": 0.444444,
        "strict_adv_proxy_full_fill_notional_cny": 120_000.0,
        "strict_adv_proxy_200k_status": "not_fully_cleared_due_to_three_historical_603117_low_liquidity_picks",
        "required_metric_contract": "docs/contracts/SHORTPICK_V3_STABILITY_OPTIMIZATION_METRIC_CONTRACT_2026-07-08.md",
    }
    scaled_spec["selection_policy"] = selection_policy
    scaled_spec["claim_ceiling"] = "research_spec_only_selected_exhaustion_date_scaled_v3_challenger"
    specs.append(scaled_spec)


def validate_model_spec_registry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    specs = list(payload.get("model_specs") or [])
    spec_ids = [str(spec.get("model_spec_id") or "") for spec in specs]
    failures: list[str] = []
    if len(spec_ids) != len(set(spec_ids)):
        failures.append("duplicate_model_spec_id")
    for spec in specs:
        spec_id = str(spec.get("model_spec_id") or "")
        grid = spec.get("hyperparameter_grid")
        if not isinstance(grid, dict) or not grid:
            failures.append(f"{spec_id}:missing_hyperparameter_grid")
            continue
        declared_max_trials = int(spec.get("max_trials") or 0)
        actual_trials = _grid_trial_count({str(key): list(value) for key, value in grid.items() if isinstance(value, list)})
        if declared_max_trials != actual_trials:
            failures.append(f"{spec_id}:max_trials_mismatch")
        if actual_trials > 16:
            failures.append(f"{spec_id}:unbounded_search_space")
        if spec.get("production_effect") != "forbidden":
            failures.append(f"{spec_id}:production_effect_not_forbidden")
        if not spec.get("allowed_feature_groups"):
            failures.append(f"{spec_id}:missing_feature_groups")
    return {
        "status": "passed" if not failures else "failed",
        "failure_count": len(failures),
        "failures": failures,
    }


def build_model_spec_registry_artifact(
    *,
    validation_run_id: str,
    source_input_snapshot_id: str | None = None,
) -> dict[str, Any]:
    model_specs = default_model_specs()
    content_digest = _stable_digest(model_specs)
    artifact_id = f"model-spec-registry-{content_digest[:16]}"
    payload = {
        "artifact_type": "model_spec_registry",
        "schema_version": MODEL_SPEC_REGISTRY_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "registry_id": MODEL_SPEC_REGISTRY_ID,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_input_snapshot_id or "not_applicable_registry_only",
        "source_data_time_range": {"status": "not_applicable_registry_only"},
        "feature_version": "declared_by_candidate_runner",
        "label_version": "declared_by_candidate_runner",
        "code_version": "unresolved_local_checkout",
        "config_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
        "validation_protocol": {
            "protocol_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
            "primary_role": "governed_model_spec_registry",
            "runner_policy": "candidate_runner_may_only_execute_registered_specs",
            "broad_search_policy": "forbidden_outside_registered_hyperparameter_grid",
            "production_effect": "forbidden",
        },
        "gate_readout": {
            "gate_status": "registry_ready",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "research_spec_only",
            "blocking_gate_ids": ["candidate_runner_not_implemented", "oos_validation_not_run"],
        },
        "claim_ceiling": "research_spec_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_input_snapshot_id": source_input_snapshot_id,
        "model_spec_count": len(model_specs),
        "model_spec_ids": [str(spec["model_spec_id"]) for spec in model_specs],
        "model_specs": model_specs,
        "registry_content_digest": content_digest,
    }
    payload["validation"] = validate_model_spec_registry_payload(payload)
    return payload


def write_model_spec_registry_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> Path:
    return write_research_validation_artifact(
        "model_spec_registry",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
