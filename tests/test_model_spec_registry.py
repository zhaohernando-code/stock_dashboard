from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ashare_evidence.model_spec_registry import (
    build_model_spec_registry_artifact,
    validate_model_spec_registry_payload,
    write_model_spec_registry_artifact,
)


class ModelSpecRegistryTests(unittest.TestCase):
    def test_default_registry_has_stable_bounded_specs(self) -> None:
        artifact = build_model_spec_registry_artifact(
            validation_run_id="unit-run",
            source_input_snapshot_id="model-exploration-input-snapshot-unit",
        )

        self.assertEqual(artifact["artifact_type"], "model_spec_registry")
        self.assertEqual(artifact["promotion_status"], "blocked_from_production")
        self.assertEqual(artifact["validation"]["status"], "passed")
        self.assertEqual(
            artifact["model_spec_ids"],
            [
                "baseline_momentum_10d_turnover_cooldown_v1",
                "ranked_feature_linear_v1",
                "ranked_tree_shallow_v1",
                "regime_conditioned_linear_v1",
                "pullback_reversal_5d_v1",
                "liquidity_breakout_5d_v1",
                "trend_quality_20d_v1",
                "concentrated_liquidity_momentum_20d_v1",
                "anchor_liquidity_concentrated_top5_20d_v1",
                "breakout_amount_confirmation_top1_20d_v1",
                "breakout_amount_expansion_top1_20d_v1",
                "breakout_amount_confirmation_top2_20d_v1",
                "regime_adaptive_breakout_defensive_top1_20d_v1",
                "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                "momentum_confirmed_regime_adaptive_breakout_defensive_top1_20d_v1",
                "regime_exposure_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                "conditional_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                "adaptive_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                "tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1",
                "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1",
                "stress_cash_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1",
                "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1",
                "transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1",
                "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1",
                "industry_diversified_transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1",
                "confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1",
                "top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1",
                "overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1",
                "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1",
                "high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1",
                "path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1",
                "weak_low_liquidity_tail_cash_path_tail_overheat_high_confidence_top3_20d_v1",
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1",
                "limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1",
                "regime_adaptive_breakout_defensive_tighter_top1_20d_v1",
                "confirmed_concentrated_liquidity_momentum_20d_v1",
                "confirmed_concentrated_liquidity_momentum_10d_v1",
                "balanced_confirmed_concentrated_liquidity_momentum_20d_v1",
                "balanced_confirmed_concentrated_liquidity_momentum_10d_v1",
                "regime_gated_balanced_concentrated_liquidity_momentum_20d_v1",
                "risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1",
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_scaled_v1",
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_replacement_v1",
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1",
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_date_scale_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_scale_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_"
                    "defensive_crowding_weak_overheated_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_"
                    "defensive_crowding_weak_overheated_underfilled_feature_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_shallow_drawdown_lowvol_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_low5d_high20d_candidate_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_weak_benchmark_lowturn_candidate_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_high_turnover_amount_candidate_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_lowturn_midmomentum_candidate_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_lowret_lowadv_candidate_replacement_v1"
                ),
                (
                    "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                    "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_"
                    "weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1"
                ),
                "exhaustion_aware_medium_industry_pullback_v3_top3_20d_v1",
                "selected_exhaustion_date_scaled_v3_top3_20d_v1",
            ],
        )
        for spec in artifact["model_specs"]:
            self.assertLessEqual(spec["max_trials"], 16)
            self.assertEqual(spec["production_effect"], "forbidden")
            self.assertTrue(spec["allowed_feature_groups"])
        horizons = {spec["model_spec_id"]: spec["prediction_horizon_days"] for spec in artifact["model_specs"]}
        self.assertEqual(horizons["pullback_reversal_5d_v1"], 5)
        self.assertEqual(horizons["liquidity_breakout_5d_v1"], 5)
        self.assertEqual(horizons["trend_quality_20d_v1"], 20)
        self.assertEqual(horizons["concentrated_liquidity_momentum_20d_v1"], 20)
        self.assertEqual(horizons["anchor_liquidity_concentrated_top5_20d_v1"], 20)
        self.assertEqual(horizons["breakout_amount_confirmation_top1_20d_v1"], 20)
        self.assertEqual(horizons["breakout_amount_expansion_top1_20d_v1"], 20)
        self.assertEqual(horizons["breakout_amount_confirmation_top2_20d_v1"], 20)
        self.assertEqual(horizons["regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(horizons["risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(horizons["momentum_confirmed_regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(horizons["regime_exposure_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(horizons["conditional_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(horizons["adaptive_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(horizons["tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"], 20)
        self.assertEqual(
            horizons["rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["stress_cash_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons[
                "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
            ],
            20,
        )
        self.assertEqual(horizons["transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1"], 20)
        self.assertEqual(horizons["transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1"], 20)
        self.assertEqual(
            horizons["industry_diversified_transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1"],
            20,
        )
        self.assertEqual(horizons["confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1"], 20)
        self.assertEqual(
            horizons["top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["weak_low_liquidity_tail_cash_path_tail_overheat_high_confidence_top3_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1"],
            20,
        )
        self.assertEqual(
            horizons["limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1"],
            20,
        )
        self.assertEqual(horizons["regime_adaptive_breakout_defensive_tighter_top1_20d_v1"], 20)
        self.assertEqual(horizons["confirmed_concentrated_liquidity_momentum_20d_v1"], 20)
        self.assertEqual(horizons["confirmed_concentrated_liquidity_momentum_10d_v1"], 10)
        self.assertEqual(horizons["balanced_confirmed_concentrated_liquidity_momentum_20d_v1"], 20)
        self.assertEqual(horizons["balanced_confirmed_concentrated_liquidity_momentum_10d_v1"], 10)
        self.assertEqual(horizons["regime_gated_balanced_concentrated_liquidity_momentum_20d_v1"], 20)
        self.assertEqual(horizons["risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1"], 20)
        self.assertEqual(
            horizons["weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_scaled_v1"],
            20,
        )
        self.assertEqual(
            horizons[
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_replacement_v1"
            ],
            20,
        )
        self.assertEqual(
            horizons[
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1"
            ],
            20,
        )
        concentrated = next(
            spec for spec in artifact["model_specs"] if spec["model_spec_id"] == "concentrated_liquidity_momentum_20d_v1"
        )
        self.assertEqual(concentrated["selection_policy"]["mode"], "concentrated_top_k")
        self.assertEqual(concentrated["selection_policy"]["evaluation_return_metric"], "top_5_net_excess_mean")
        anchor = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "anchor_liquidity_concentrated_top5_20d_v1"
        )
        self.assertEqual(anchor["max_trials"], 1)
        self.assertEqual(anchor["selection_policy"]["screening_policy"], "single_trial_liquidity_anchor_before_full_grid")
        breakout = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "breakout_amount_confirmation_top1_20d_v1"
        )
        self.assertEqual(breakout["max_trials"], 1)
        self.assertEqual(breakout["selection_policy"]["top_k"], 1)
        self.assertEqual(breakout["selection_policy"]["evaluation_return_metric"], "selected_top_k_net_excess_mean")
        self.assertEqual(breakout["hyperparameter_grid"]["amount_10d_vs_20d_percentile_weight"], [0.8])
        self.assertEqual(breakout["hyperparameter_grid"]["liquidity_percentile_weight"], [1.2])
        self.assertEqual(breakout["hyperparameter_grid"]["one_day_overheat_penalty"], [0.5])
        self.assertEqual(breakout["selection_policy"]["feature_gate"]["max_volatility_20d_percentile"], 0.85)
        self.assertEqual(breakout["selection_policy"]["feature_gate"]["max_turnover_rate_percentile"], 0.90)
        self.assertNotIn("min_amount_10d_vs_20d", breakout["selection_policy"]["feature_gate"])
        self.assertGreater(breakout["selection_policy"]["screening_evidence"]["proxy_total_return"], 2.0)
        self.assertLess(abs(breakout["selection_policy"]["screening_evidence"]["proxy_max_drawdown"]), 0.25)
        amount_expansion = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "breakout_amount_expansion_top1_20d_v1"
        )
        self.assertEqual(amount_expansion["max_trials"], 1)
        self.assertEqual(amount_expansion["selection_policy"]["top_k"], 1)
        self.assertEqual(amount_expansion["selection_policy"]["feature_gate"]["min_amount_10d_vs_20d"], 0.15)
        self.assertGreater(amount_expansion["selection_policy"]["screening_evidence"]["proxy_total_return"], 3.0)
        self.assertEqual(
            amount_expansion["selection_policy"]["screening_evidence"]["formal_160_comparison"],
            "worse_than_breakout_amount_confirmation_top1_20d_v1_on_latest_160_date_formal_replay",
        )
        breakout_top2 = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "breakout_amount_confirmation_top2_20d_v1"
        )
        self.assertEqual(breakout_top2["max_trials"], 1)
        self.assertEqual(breakout_top2["selection_policy"]["top_k"], 2)
        self.assertGreater(breakout_top2["selection_policy"]["screening_evidence"]["proxy_total_return"], 1.75)
        self.assertLess(abs(breakout_top2["selection_policy"]["screening_evidence"]["proxy_max_drawdown"]), 0.25)
        self.assertEqual(
            breakout_top2["selection_policy"]["screening_evidence"]["formal_160_comparison"],
            "worse_than_breakout_amount_confirmation_top1_20d_v1_on_latest_160_date_formal_replay",
        )
        regime_adaptive = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(regime_adaptive["max_trials"], 16)
        self.assertEqual(regime_adaptive["selection_policy"]["top_k"], 1)
        self.assertEqual(regime_adaptive["selection_policy"]["trial_selection_policy"]["mode"], "stability_adjusted")
        self.assertEqual(
            regime_adaptive["selection_policy"]["trial_selection_policy"][
                "minimum_selected_top_k_net_excess_mean"
            ],
            0.065,
        )
        self.assertEqual(
            regime_adaptive["selection_policy"]["trial_selection_policy"][
                "minimum_period_count_for_total_return_floor"
            ],
            500,
        )
        self.assertEqual(
            regime_adaptive["selection_policy"]["trial_selection_policy"]["minimum_portfolio_total_return"],
            1.45,
        )
        self.assertEqual(
            regime_adaptive["selection_policy"]["trial_selection_policy"]["minimum_portfolio_max_drawdown"],
            -0.18,
        )
        self.assertEqual(regime_adaptive["hyperparameter_grid"]["defensive_benchmark_return_20d_threshold"], [-0.01, 0.0])
        self.assertEqual(regime_adaptive["hyperparameter_grid"]["defensive_low_volatility_percentile_weight"], [0.8, 1.2])
        self.assertEqual(regime_adaptive["hyperparameter_grid"]["defensive_low_turnover_percentile_weight"], [1.2, 1.5])
        self.assertEqual(regime_adaptive["hyperparameter_grid"]["defensive_return_5d_percentile_weight"], [0.0, 0.3])
        self.assertGreater(regime_adaptive["selection_policy"]["screening_evidence"]["proxy_total_return"], 2.0)
        self.assertLess(abs(regime_adaptive["selection_policy"]["screening_evidence"]["proxy_max_drawdown"]), 0.12)
        self.assertEqual(
            regime_adaptive["selection_policy"]["screening_evidence"]["formal_160_winner_dependency_status"],
            "ready",
        )
        self.assertGreater(
            regime_adaptive["selection_policy"]["screening_evidence"]["formal_160_deflated_sharpe_confidence"],
            0.60,
        )
        self.assertEqual(regime_adaptive["selection_policy"]["screening_evidence"]["formal_160_trial_count"], 16)
        self.assertEqual(regime_adaptive["selection_policy"]["screening_evidence"]["formal_160_pbo_proxy"], 0.0)
        self.assertEqual(
            regime_adaptive["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-db3ea613abee7082",
        )
        self.assertGreater(
            regime_adaptive["selection_policy"]["screening_evidence"]["formal_full713_portfolio_total_return"],
            1.45,
        )
        self.assertLess(
            abs(regime_adaptive["selection_policy"]["screening_evidence"]["formal_full713_portfolio_max_drawdown"]),
            0.13,
        )
        risk_scaled_regime = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(risk_scaled_regime["max_trials"], 4)
        self.assertEqual(risk_scaled_regime["selection_policy"]["top_k"], 1)
        self.assertTrue(risk_scaled_regime["selection_policy"]["position_weighting"]["enabled"])
        self.assertEqual(
            risk_scaled_regime["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-db3ea613abee7082",
        )
        self.assertEqual(
            risk_scaled_regime["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-6eaec6fb4a32e5d8",
        )
        momentum_confirmed_regime = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "momentum_confirmed_regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(momentum_confirmed_regime["max_trials"], 4)
        self.assertEqual(momentum_confirmed_regime["selection_policy"]["top_k"], 1)
        self.assertEqual(
            momentum_confirmed_regime["hyperparameter_grid"]["defensive_return_20d_percentile_weight"],
            [0.2, 0.4, 0.6, 0.8],
        )
        self.assertEqual(
            momentum_confirmed_regime["selection_policy"]["screening_evidence"]["formal_full713_status"],
            "downgraded_weaker_than_parent",
        )
        regime_exposure_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "regime_exposure_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(regime_exposure_scaled["max_trials"], 4)
        self.assertEqual(regime_exposure_scaled["selection_policy"]["top_k"], 1)
        self.assertEqual(
            regime_exposure_scaled["selection_policy"]["position_weighting"]["mode"],
            "volatility_turnover_regime_scaled",
        )
        self.assertEqual(
            regime_exposure_scaled["hyperparameter_grid"]["regime_min_position_weight"],
            [0.55, 0.70],
        )
        self.assertEqual(
            regime_exposure_scaled["selection_policy"]["screening_evidence"]["formal_full713_status"],
            "downgraded_market_exposure_scaled_too_much_return_loss",
        )
        conditional_risk_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "conditional_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(conditional_risk_scaled["max_trials"], 4)
        self.assertEqual(
            conditional_risk_scaled["selection_policy"]["position_weighting"]["mode"],
            "conditional_regime_stock_risk_scaled",
        )
        self.assertEqual(
            conditional_risk_scaled["hyperparameter_grid"]["weak_full_weight_max_volatility_20d_percentile"],
            [0.65, 0.75],
        )
        self.assertEqual(
            conditional_risk_scaled["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-cadd53fd6a3cb1e6",
        )
        adaptive_exit = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "adaptive_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(adaptive_exit["max_trials"], 4)
        self.assertTrue(adaptive_exit["selection_policy"]["exit_policy"]["enabled"])
        self.assertEqual(
            adaptive_exit["hyperparameter_grid"]["weak_regime_exit_horizon_days"],
            [5, 10],
        )
        self.assertEqual(
            adaptive_exit["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-95421910943186f3",
        )
        self.assertEqual(
            adaptive_exit["selection_policy"]["screening_evidence"]["formal_full713_status"],
            "downgraded_adaptive_exit_too_much_return_loss",
        )
        tail_risk_exit = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1"
        )
        self.assertEqual(tail_risk_exit["max_trials"], 4)
        self.assertTrue(tail_risk_exit["selection_policy"]["exit_policy"]["enabled"])
        self.assertEqual(
            tail_risk_exit["hyperparameter_grid"]["weak_regime_exit_horizon_days"],
            [20],
        )
        self.assertEqual(
            tail_risk_exit["hyperparameter_grid"]["risk_exit_horizon_days"],
            [5, 10],
        )
        self.assertEqual(
            tail_risk_exit["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-c4d96d7b0d1f5d0a",
        )
        self.assertEqual(
            tail_risk_exit["selection_policy"]["screening_evidence"]["formal_full713_status"],
            "observe_blocked_return_frontier_but_stability_unresolved",
        )
        rank_weighted_tail_risk = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
        )
        self.assertEqual(rank_weighted_tail_risk["max_trials"], 4)
        self.assertEqual(rank_weighted_tail_risk["selection_policy"]["top_k"], 2)
        self.assertTrue(rank_weighted_tail_risk["selection_policy"]["rank_weighting"]["enabled"])
        self.assertEqual(
            rank_weighted_tail_risk["hyperparameter_grid"]["rank_weight_profile"],
            ["top2_95_05", "top2_90_10", "top2_85_15", "top2_80_20"],
        )
        self.assertEqual(
            rank_weighted_tail_risk["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-baea5b17cd06ef3c",
        )
        self.assertEqual(
            rank_weighted_tail_risk["selection_policy"]["screening_evidence"]["formal_full713_stability_preferred_profile"],
            "top2_90_10",
        )
        stress_cash_rank_weighted = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "stress_cash_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
        )
        self.assertEqual(stress_cash_rank_weighted["max_trials"], 8)
        self.assertEqual(stress_cash_rank_weighted["selection_policy"]["top_k"], 2)
        self.assertEqual(stress_cash_rank_weighted["selection_policy"]["cash_switch"]["condition_mode"], "all")
        self.assertEqual(stress_cash_rank_weighted["hyperparameter_grid"]["rank_weight_profile"], ["top2_90_10"])
        self.assertEqual(
            stress_cash_rank_weighted["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-2711575202ad0e38",
        )
        self.assertEqual(
            stress_cash_rank_weighted["selection_policy"]["screening_evidence"]["formal_full713_status"],
            "downgraded_cash_switch_no_incremental_edge",
        )
        transition_defensive = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1"
        )
        self.assertEqual(transition_defensive["max_trials"], 8)
        self.assertEqual(transition_defensive["selection_policy"]["top_k"], 2)
        self.assertEqual(
            transition_defensive["hyperparameter_grid"]["defensive_condition_mode"],
            ["benchmark_20d_or_transition_stress"],
        )
        self.assertEqual(transition_defensive["hyperparameter_grid"]["rank_weight_profile"], ["top2_90_10"])
        self.assertEqual(
            transition_defensive["selection_policy"]["screening_evidence"]["source"],
            "full713_formal_replay_reused_matrices",
        )
        self.assertEqual(
            transition_defensive["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-115676e844c4526b",
        )
        transition_frontier = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1"
        )
        self.assertEqual(transition_frontier["max_trials"], 4)
        self.assertEqual(transition_frontier["selection_policy"]["top_k"], 2)
        self.assertEqual(
            transition_frontier["hyperparameter_grid"]["transition_benchmark_return_10d_threshold"],
            [-0.015],
        )
        self.assertEqual(
            transition_frontier["hyperparameter_grid"]["transition_benchmark_volatility_20d_threshold"],
            [0.04],
        )
        self.assertEqual(
            transition_frontier["hyperparameter_grid"]["rank_weight_profile"],
            ["top2_95_05", "top2_90_10"],
        )
        self.assertEqual(
            transition_frontier["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-05032fe21ce33845",
        )
        self.assertEqual(
            transition_frontier["selection_policy"]["screening_evidence"]["formal_full713_status"],
            "observe_blocked_dsr_near_miss",
        )
        transition_sleeve_scan = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1"
        )
        self.assertEqual(transition_sleeve_scan["max_trials"], 4)
        self.assertEqual(transition_sleeve_scan["selection_policy"]["top_k"], 2)
        self.assertEqual(
            transition_sleeve_scan["hyperparameter_grid"]["rank_weight_profile"],
            ["top2_90_10", "top2_91_09", "top2_92_08", "top2_93_07"],
        )
        self.assertEqual(
            transition_sleeve_scan["hyperparameter_grid"]["transition_benchmark_return_20d_ceiling"],
            [0.02],
        )
        self.assertEqual(
            transition_sleeve_scan["selection_policy"]["screening_evidence"]["formal_full713_artifact_id"],
            "model-comparison-report-d464f8ef856be002",
        )
        self.assertEqual(
            transition_sleeve_scan["selection_policy"]["screening_evidence"]["formal_full713_best_profile"],
            "top2_91_09",
        )
        industry_diversified = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "industry_diversified_transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1"
        )
        self.assertEqual(industry_diversified["max_trials"], 3)
        self.assertEqual(industry_diversified["selection_policy"]["top_k"], 2)
        self.assertEqual(industry_diversified["hyperparameter_grid"]["max_same_industry_picks"], [1])
        self.assertEqual(
            industry_diversified["hyperparameter_grid"]["rank_weight_profile"],
            ["top2_90_10", "top2_91_09", "top2_92_08"],
        )
        self.assertTrue(industry_diversified["selection_policy"]["portfolio_constraints"]["enabled"])
        self.assertEqual(
            industry_diversified["selection_policy"]["portfolio_constraints"]["mode"],
            "per_signal_date_industry_cap",
        )
        self.assertEqual(
            industry_diversified["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-d464f8ef856be002",
        )
        confidence_shifted = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1"
        )
        self.assertEqual(confidence_shifted["max_trials"], 4)
        self.assertEqual(confidence_shifted["selection_policy"]["top_k"], 2)
        self.assertEqual(
            confidence_shifted["selection_policy"]["rank_weighting"]["mode"],
            "conditional_first_rank_risk_shift",
        )
        self.assertEqual(
            confidence_shifted["hyperparameter_grid"]["conditional_rank_weight_profile"],
            ["top2_50_50", "top2_60_40"],
        )
        self.assertEqual(confidence_shifted["hyperparameter_grid"]["rank1_shift_max_score_margin"], [0.05, 0.07])
        self.assertEqual(
            confidence_shifted["selection_policy"]["screening_evidence"]["proxy_negative_month_count"],
            11,
        )
        self.assertEqual(
            confidence_shifted["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-d464f8ef856be002",
        )
        top3_tail_blended = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
        )
        self.assertEqual(top3_tail_blended["max_trials"], 4)
        self.assertEqual(top3_tail_blended["selection_policy"]["top_k"], 3)
        self.assertEqual(
            top3_tail_blended["hyperparameter_grid"]["conditional_rank_weight_profile"],
            ["top3_50_30_20"],
        )
        self.assertEqual(top3_tail_blended["hyperparameter_grid"]["rank1_shift_min_volatility_20d_percentile"], [0.78])
        self.assertEqual(top3_tail_blended["hyperparameter_grid"]["rank1_shift_max_score_margin"], [0.07, 0.09, 0.12, 0.15])
        self.assertEqual(
            top3_tail_blended["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-91f1cfae6d8334f7",
        )
        self.assertLess(
            top3_tail_blended["selection_policy"]["screening_evidence"]["proxy_path_drawdown_sum"],
            0,
        )
        self.assertGreater(
            top3_tail_blended["selection_policy"]["screening_evidence"]["proxy_path_drawdown_sum"],
            top3_tail_blended["selection_policy"]["screening_evidence"]["proxy_parent_path_drawdown_sum"],
        )
        overheat_cash = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1"
        )
        self.assertEqual(overheat_cash["max_trials"], 4)
        self.assertEqual(overheat_cash["selection_policy"]["top_k"], 3)
        self.assertEqual(
            overheat_cash["selection_policy"]["signal_cash_switch"]["mode"],
            "rank1_overheat_reversal_cash",
        )
        self.assertEqual(
            overheat_cash["hyperparameter_grid"]["rank1_overheat_min_return_5d_percentile"],
            [0.85, 0.90, 0.95, 0.98],
        )
        self.assertEqual(
            overheat_cash["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-e0d817a563cb53cf",
        )
        self.assertEqual(overheat_cash["selection_policy"]["screening_evidence"]["proxy_negative_month_count"], 10)
        self.assertGreater(
            overheat_cash["selection_policy"]["screening_evidence"]["proxy_path_drawdown_sum"],
            overheat_cash["selection_policy"]["screening_evidence"]["proxy_parent_path_drawdown_sum"],
        )
        weak_low_vol_cash = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1"
        )
        self.assertEqual(weak_low_vol_cash["max_trials"], 4)
        self.assertEqual(weak_low_vol_cash["selection_policy"]["top_k"], 3)
        self.assertEqual(
            weak_low_vol_cash["selection_policy"]["signal_cash_switch"]["mode"],
            "rank1_overheat_or_weak_regime_low_volatility_cash",
        )
        self.assertEqual(
            weak_low_vol_cash["hyperparameter_grid"]["weak_low_vol_min_benchmark_volatility_20d"],
            [0.03, 0.035, 0.04, 0.045],
        )
        self.assertEqual(
            weak_low_vol_cash["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-773d4ba2fda17834",
        )
        self.assertEqual(
            weak_low_vol_cash["selection_policy"]["screening_evidence"]["proxy_negative_month_count"],
            9,
        )
        high_confidence_tail_cash = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1"
        )
        self.assertEqual(high_confidence_tail_cash["max_trials"], 4)
        self.assertEqual(high_confidence_tail_cash["selection_policy"]["top_k"], 3)
        self.assertEqual(
            high_confidence_tail_cash["selection_policy"]["signal_cash_switch"]["mode"],
            "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_cash",
        )
        self.assertEqual(
            high_confidence_tail_cash["hyperparameter_grid"]["rank1_high_confidence_min_score_margin"],
            [0.10, 0.12, 0.15, 0.20],
        )
        self.assertEqual(
            high_confidence_tail_cash["selection_policy"]["screening_evidence"]["parent_label_version"],
            "shortpick_model_executable_label_matrix:v3",
        )
        self.assertGreater(
            high_confidence_tail_cash["selection_policy"]["screening_evidence"]["proxy_path_drawdown_sum"],
            high_confidence_tail_cash["selection_policy"]["screening_evidence"]["proxy_parent_path_drawdown_sum"],
        )
        path_tail_cash = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1"
        )
        self.assertEqual(path_tail_cash["max_trials"], 4)
        self.assertEqual(path_tail_cash["selection_policy"]["top_k"], 3)
        self.assertEqual(
            path_tail_cash["selection_policy"]["signal_cash_switch"]["mode"],
            (
                "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_"
                "market_euphoric_volume_tail_cash"
            ),
        )
        self.assertEqual(
            path_tail_cash["hyperparameter_grid"]["rank1_tail_min_benchmark_return_20d"],
            [0.04, 0.05],
        )
        self.assertEqual(
            path_tail_cash["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-9169bed0e1736fe2",
        )
        self.assertGreater(
            path_tail_cash["selection_policy"]["screening_evidence"]["proxy_portfolio_total_return"],
            path_tail_cash["selection_policy"]["screening_evidence"]["proxy_parent_portfolio_total_return"],
        )
        weak_low_liquidity_tail_cash = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "weak_low_liquidity_tail_cash_path_tail_overheat_high_confidence_top3_20d_v1"
        )
        self.assertEqual(weak_low_liquidity_tail_cash["max_trials"], 4)
        self.assertEqual(weak_low_liquidity_tail_cash["selection_policy"]["top_k"], 3)
        self.assertEqual(
            weak_low_liquidity_tail_cash["selection_policy"]["signal_cash_switch"]["mode"],
            (
                "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                "weak_low_liquidity_tail_cash"
            ),
        )
        self.assertEqual(
            weak_low_liquidity_tail_cash["hyperparameter_grid"][
                "rank1_weak_tail_max_benchmark_return_20d"
            ],
            [-0.04, -0.02],
        )
        self.assertEqual(
            weak_low_liquidity_tail_cash["selection_policy"]["screening_evidence"][
                "parent_full713_artifact_id"
            ],
            "model-comparison-report-00602b973c354176",
        )
        self.assertGreater(
            weak_low_liquidity_tail_cash["selection_policy"]["screening_evidence"]["proxy_path_drawdown_sum"],
            weak_low_liquidity_tail_cash["selection_policy"]["screening_evidence"][
                "proxy_parent_path_drawdown_sum"
            ],
        )
        congested_tail_cash = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1"
        )
        self.assertEqual(congested_tail_cash["max_trials"], 4)
        self.assertEqual(congested_tail_cash["selection_policy"]["top_k"], 3)
        self.assertEqual(
            congested_tail_cash["selection_policy"]["signal_cash_switch"]["mode"],
            (
                "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                "weak_low_liquidity_or_congested_momentum_or_high_turnover_momentum_tail_cash"
            ),
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["signal_cash_switch"][
                "rank1_high_turnover_momentum_tail_cash"
            ]["enabled"]
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_high_turnover_tail_min_turnover_rate_percentile"],
            [0.85],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_high_turnover_tail_max_avg_amount_20d"],
            [300_000_000],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["signal_position_scaling"]["mode"],
            "rank1_weak_defensive_grind_scale",
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["signal_position_scaling"][
                "rank1_residual_momentum_amount_tail_scale"
            ]["enabled"]
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_residual_momentum_position_scale"],
            [0.3],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_rank_scale_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_rank_scale_max_avg_amount_20d"],
            [100_000_000],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_extreme_rank_scale_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_extreme_rank_scale_max_avg_amount_20d"],
            [600_000_000],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_neutral_chop_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_neutral_chop_max_drawdown_20d"],
            [-0.003],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_no_drawdown_min_max_drawdown_20d"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_no_drawdown_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_high_position_pullback_min_max_drawdown_40d"],
            [-0.04386677497969138],
        )
        exposure_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_scaled_v1"
        )
        self.assertEqual(exposure_scaled["max_trials"], 4)
        self.assertEqual(exposure_scaled["selection_policy"]["top_k"], 3)
        self.assertEqual(exposure_scaled["hyperparameter_grid"]["date_gross_exposure_floor"], [0.3])
        self.assertEqual(
            exposure_scaled["selection_policy"]["date_exposure_scaling"]["mode"],
            "gross_exposure_floor_linear_scale",
        )
        self.assertEqual(
            exposure_scaled["selection_policy"]["date_exposure_scaling"]["source_proxy_result"][
                "low_exposure_active_date_count"
            ],
            76,
        )
        replacement_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_replacement_v1"
        )
        self.assertEqual(replacement_scaled["max_trials"], 4)
        self.assertEqual(replacement_scaled["hyperparameter_grid"]["rank1_replacement_max_score"], [3.1])
        self.assertEqual(
            replacement_scaled["selection_policy"]["slot_replacement"]["mode"],
            "rank1_low_score_low_amount_full_fill_topn_substitute",
        )
        self.assertEqual(
            replacement_scaled["selection_policy"]["slot_replacement"]["source_proxy_result"]["replacement_count"],
            6,
        )
        liquidity_replacement_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1"
        )
        self.assertEqual(liquidity_replacement_scaled["max_trials"], 4)
        self.assertEqual(
            liquidity_replacement_scaled["hyperparameter_grid"][
                "rank1_very_low_liquidity_replacement_max_score"
            ],
            [3.2],
        )
        self.assertEqual(
            liquidity_replacement_scaled["hyperparameter_grid"][
                "rank1_very_low_liquidity_replacement_min_replacement_avg_amount_20d"
            ],
            [100_000_000.0],
        )
        additional_rules = liquidity_replacement_scaled["selection_policy"]["slot_replacement"][
            "additional_rank1_replacement_rules"
        ]
        self.assertEqual(
            additional_rules[-1]["reason"],
            "rank1_very_low_liquidity_top20_high_amount_substitute",
        )
        self.assertEqual(additional_rules[-1]["source_proxy_result"]["replacement_count"], 9)
        self.assertEqual(additional_rules[-1]["source_proxy_result"]["capacity_below_full_fill_after"], 16)
        neutral_chop_date_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == (
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                "rank1_liquidity_replacement_neutral_chop_date_scale_v1"
            )
        )
        self.assertEqual(neutral_chop_date_scaled["max_trials"], 4)
        self.assertEqual(
            neutral_chop_date_scaled["hyperparameter_grid"]["rank1_neutral_chop_date_position_scale"],
            [0.0],
        )
        neutral_chop_date_scale = neutral_chop_date_scaled["selection_policy"]["signal_position_scaling"][
            "rank1_neutral_chop_date_scale"
        ]
        self.assertEqual(neutral_chop_date_scale["source_proxy_result"]["negative_month_count_after"], 2)
        self.assertAlmostEqual(
            neutral_chop_date_scale["source_proxy_result"]["positive_date_rate_after"],
            0.450229709035222,
        )
        segment_risk_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == (
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                "rank1_liquidity_replacement_neutral_chop_segment_risk_scale_v1"
            )
        )
        self.assertEqual(segment_risk_scaled["max_trials"], 4)
        self.assertIn("segment_risk_scale", segment_risk_scaled["allowed_feature_groups"])
        segment_rules = segment_risk_scaled["selection_policy"]["rank_position_scaling"][
            "segment_risk_scale_rules"
        ]
        self.assertEqual(
            [rule["reason"] for rule in segment_rules],
            [
                "rank2_high_turnover_segment_risk_position_scale",
                "rank3_high_score_segment_risk_position_scale",
                "rank1_high_amount_segment_risk_position_scale",
            ],
        )
        self.assertEqual(
            segment_risk_scaled["hyperparameter_grid"]["rank2_high_turnover_segment_risk_position_scale"],
            [0.5],
        )
        self.assertAlmostEqual(
            segment_risk_scaled["selection_policy"]["rank_position_scaling"][
                "source_segment_risk_scale_combo_result"
            ]["portfolio_total_return_after"],
            2.5441379707456706,
        )
        defensive_crowding_replacement = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == (
                "weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_"
                "rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_replacement_v1"
            )
        )
        self.assertEqual(defensive_crowding_replacement["max_trials"], 4)
        crowding_rules = defensive_crowding_replacement["selection_policy"]["slot_replacement"][
            "additional_rank1_replacement_rules"
        ]
        self.assertEqual(crowding_rules[-1]["reason"], "rank1_defensive_crowding_top50_substitute")
        self.assertEqual(crowding_rules[-1]["max_return_5d_percentile"], 0.1)
        self.assertEqual(crowding_rules[-1]["min_candidate_return_5d_percentile"], 0.1)
        self.assertEqual(
            crowding_rules[-1]["source_proxy_result"]["negative_month_count_after"],
            1,
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_high_position_pullback_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_low_score_high_position_max_score"],
            [3.3878779420277896],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"][
                "rank1_low_score_high_position_min_distance_from_40d_high"
            ],
            [-0.0020618556701030855],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_low_score_high_position_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank2_rank_scale_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank2_rank_scale_max_avg_amount_20d"],
            [800_000_000],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank3_rank_scale_position_scale"],
            [0.0],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank3_rank_scale_max_avg_amount_20d"],
            [800_000_000],
        )
        self.assertEqual(
            congested_tail_cash["hyperparameter_grid"]["rank1_weak_grind_min_low_volatility_percentile"],
            [0.97, 0.98],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["rank_position_scaling"]["mode"],
            "rank1_high_momentum_low_liquidity_turnover_scale",
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"]["enabled"],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"][
                "rank1_extreme_momentum_turnover_scale"
            ]["enabled"],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"][
                "rank2_high_momentum_turnover_scale"
            ]["enabled"],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"][
                "rank3_high_momentum_turnover_scale"
            ]["enabled"],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"]["rank1_neutral_chop_scale"][
                "enabled"
            ],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"]["rank1_no_drawdown_scale"][
                "enabled"
            ],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"]["rank1_high_position_pullback_scale"][
                "enabled"
            ],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"]["rank1_low_score_high_position_scale"][
                "enabled"
            ],
        )
        self.assertTrue(
            congested_tail_cash["selection_policy"]["rank_position_scaling"][
                "rank1_benchmark_momentum_pullback_scale"
            ]["enabled"],
        )
        self.assertIn(
            "source_rank1_extreme_frontier_targeted_single_rule_proxy_scan",
            congested_tail_cash["selection_policy"]["screening_evidence"],
        )
        self.assertIn(
            "source_rank2_frontier_remaining_negative_month_diagnostic",
            congested_tail_cash["selection_policy"]["screening_evidence"],
        )
        self.assertIn(
            "source_rank2_frontier_combo_proxy_scan",
            congested_tail_cash["selection_policy"]["screening_evidence"],
        )
        self.assertIn(
            "source_rank3_frontier_manual_negative_month_proxy_scan",
            congested_tail_cash["selection_policy"]["screening_evidence"],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_neutral_chop_frontier_low_adv_capacity_proxy_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_neutral_chop_frontier_low_adv_capacity_proxy_scan_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_rank2_low_adv_capacity_formal_rejection"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_rank2_low_adv_capacity_formal_rejection_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_neutral_chop_frontier_adv_capacity_diagnostic"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_neutral_chop_frontier_adv_capacity_diagnostic_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_neutral_chop_frontier_capacity_adjusted_net_proxy"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_neutral_chop_frontier_capacity_adjusted_net_proxy_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_neutral_chop_frontier_negative_month_expanded_proxy_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_neutral_chop_frontier_negative_month_expanded_proxy_scan_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_no_drawdown_frontier_capacity_feature_proxy_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_no_drawdown_frontier_capacity_feature_proxy_scan_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_rank1_low_adv_turnover_capacity_formal_rejection"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_rank1_low_adv_turnover_capacity_formal_rejection_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_no_drawdown_frontier_total_curve_proxy_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_no_drawdown_frontier_two_stage_total_curve_proxy_scan_20260707.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_high_momentum_turnover_scale_proxy_negative_month_count"
            ],
            6,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_high_momentum_turnover_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-e3c25f696d53e504",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_high_momentum_turnover_scale_formal_full713_negative_month_count"
            ],
            6,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank3_high_momentum_turnover_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-0c77a38610312156",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank3_high_momentum_turnover_scale_formal_full713_negative_month_count"
            ],
            6,
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank3_high_momentum_turnover_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_high_momentum_turnover_scale_formal_full713_total_return"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_proxy_negative_month_count"
            ],
            5,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-3c8b5ce0286183c6",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_formal_full713_negative_month_count"
            ],
            5,
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank3_high_momentum_turnover_scale_formal_full713_total_return"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_fee_gate_refresh_report_id"
            ],
            "model-comparison-report-74afadcd87fa8bab",
        )
        self.assertIn(
            "fees_slippage_stamp_tax",
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_fee_gate_refresh_covered_execution_gate_ids"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_fee_gate_refresh_remaining_execution_blockers"
            ],
            ["adv_capacity_fill_rate"],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_adv_capacity_active_pick_count"
            ],
            998,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_adv_capacity_below_full_fill_count"
            ],
            27,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_adv_capacity_status"
            ],
            "blocked_adv_capacity_fill_rate",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_status"
            ],
            "rejected_mean_down_negative_months_up",
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_mean"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_parent_mean"
            ],
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_capacity_adjusted_net_proxy_parent_negative_month_count"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_proxy_triggered_rank2_picks"
            ],
            36,
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_proxy_selected_pick_mean"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_proxy_parent_selected_pick_mean"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_proxy_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_proxy_parent_negative_month_count"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_formal_full713_status"
            ],
            "rejected_total_and_annualized_return_below_neutral_chop_frontier",
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank2_low_adv_capacity_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_formal_full713_total_return"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_triggered_rank1_picks"
            ],
            17,
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_selected_pick_mean"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_parent_selected_pick_mean"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_parent_negative_month_count"
            ],
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_path_drawdown_sum"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_proxy_parent_path_drawdown_sum"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_status"
            ],
            "current_frontier_blocked",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-481e82b0595596c8",
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_formal_full713_total_return"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_neutral_chop_scale_formal_full713_negative_month_count"
            ],
        )
        self.assertIn(
            "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_remaining_execution_blockers"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_adv_turnover_capacity_scale_proxy_triggered_rank1_picks"
            ],
            15,
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_adv_turnover_capacity_scale_proxy_active_below_full_fill_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_adv_turnover_capacity_scale_proxy_parent_active_below_full_fill_count"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_adv_turnover_capacity_scale_formal_full713_status"
            ],
            "rejected_total_and_annualized_return_below_no_drawdown_frontier",
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_adv_turnover_capacity_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_total_return"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_proxy_negative_month_count"
            ],
            3,
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_proxy_selected_pick_mean"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_proxy_parent_selected_pick_mean"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_formal_full713_status"
            ],
            "previous_frontier_blocked",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-ece4ed12a79d221d",
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_total_return"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_formal_full713_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_no_drawdown_scale_formal_full713_negative_month_count"
            ],
        )
        self.assertIn(
            "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_remaining_execution_blockers"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_proxy_negative_month_count"
            ],
            3,
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_proxy_selected_pick_mean"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_proxy_parent_selected_pick_mean"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_status"
            ],
            "previous_frontier_blocked",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-3c83db6385250480",
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_formal_full713_total_return"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_high_position_pullback_scale_formal_full713_negative_month_count"
            ],
        )
        self.assertIn(
            "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_remaining_execution_blockers"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_formal_full713_status"
            ],
            "current_frontier_blocked",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-efb1ccc40019b51b",
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_total_return"
            ],
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_formal_full713_worst_month"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_worst_month"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_formal_full713_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_negative_month_count"
            ],
        )
        self.assertIn(
            "execution_stress:capacity:adv_capacity_fill_rate_below_floor",
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_remaining_execution_blockers"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_capacity_contract_status"
            ],
            "lower_capital_research_contract_ready",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_capacity_contract_max_ready_notional_cny"
            ],
            100_000.0,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_capacity_contract_configured_governance_status"
            ],
            "blocked",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_status"
            ],
            "rejected_total_and_annualized_return_below_current_frontier",
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_weak_benchmark_low_score_high_position_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_formal_full713_total_return"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_weak_benchmark_low_score_high_position_scale_adv_capacity_below_full_fill_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_adv_capacity_below_full_fill_count"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_weak_liquidity_capacity_scale_formal_full713_status"
            ],
            "rejected_total_and_annualized_return_below_current_frontier",
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_weak_liquidity_capacity_scale_formal_full713_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_formal_full713_total_return"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_weak_liquidity_capacity_scale_adv_capacity_below_full_fill_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_benchmark_momentum_pullback_scale_adv_capacity_below_full_fill_count"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_adv_capacity_all_full_fill_notional_cny"
            ],
            1_000_000,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_adv_capacity_100k_below_full_fill_count"
            ],
            0,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_adv_capacity_1m_below_full_fill_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank1_low_score_high_position_scale_adv_capacity_below_full_fill_count"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-91c4df75fc20764d",
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"]["proxy_path_drawdown_sum"],
            congested_tail_cash["selection_policy"]["screening_evidence"]["proxy_parent_path_drawdown_sum"],
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "residual_momentum_proxy_portfolio_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "residual_momentum_proxy_parent_portfolio_total_return"
            ],
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "high_turnover_momentum_tail_proxy_portfolio_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "high_turnover_momentum_tail_proxy_parent_portfolio_total_return"
            ],
        )
        self.assertGreater(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank_level_scale_proxy_portfolio_total_return"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank_level_scale_proxy_parent_portfolio_total_return"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank_level_scale_proxy_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "rank_level_scale_proxy_parent_negative_month_count"
            ],
        )
        self.assertLess(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "extreme_rank_level_scale_proxy_negative_month_count"
            ],
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "extreme_rank_level_scale_proxy_parent_negative_month_count"
            ],
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "extreme_rank_level_scale_formal_full713_artifact_id"
            ],
            "model-comparison-report-e13ac319e2fc2c94",
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "extreme_rank_level_scale_formal_full713_negative_month_count"
            ],
            7,
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_residual_frontier_high_risk_tail_proxy_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_residual_momentum_frontier_high_risk_tail_proxy_scan_20260706.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_high_turnover_frontier_rank_level_scaling_proxy_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_high_turnover_frontier_rank_level_scaling_proxy_scan_20260706.json"
            ),
        )
        self.assertEqual(
            congested_tail_cash["selection_policy"]["screening_evidence"][
                "source_rank1_scaled_frontier_remaining_negative_month_rank_scale_scan"
            ],
            (
                "/tmp/stock_dashboard_retained_reports_20260706/"
                "stock_dashboard_v3_rank1_scaled_frontier_remaining_negative_month_rank_scale_scan_20260706.json"
            ),
        )
        limit_aware = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"]
            == "limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1"
        )
        self.assertEqual(limit_aware["max_trials"], 4)
        self.assertEqual(limit_aware["selection_policy"]["top_k"], 3)
        self.assertTrue(limit_aware["selection_policy"]["feature_gate"]["block_limit_up_like_entry"])
        self.assertTrue(limit_aware["selection_policy"]["feature_gate"]["block_suspension_or_stale_proxy"])
        self.assertEqual(
            limit_aware["hyperparameter_grid"]["min_avg_amount_20d"],
            [0.0, 50_000_000.0, 100_000_000.0, 200_000_000.0],
        )
        self.assertEqual(
            limit_aware["selection_policy"]["screening_evidence"]["parent_full713_artifact_id"],
            "model-comparison-report-993b0e970e7f74e7",
        )
        self.assertEqual(limit_aware["selection_policy"]["screening_evidence"]["selected_pick_limit_up_like_count"], 73)
        tighter_regime = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "regime_adaptive_breakout_defensive_tighter_top1_20d_v1"
        )
        self.assertEqual(tighter_regime["max_trials"], 16)
        self.assertEqual(tighter_regime["selection_policy"]["feature_gate"]["max_volatility_20d_percentile"], 0.80)
        self.assertEqual(tighter_regime["hyperparameter_grid"]["defensive_benchmark_return_20d_threshold"], [0.01])
        self.assertEqual(tighter_regime["hyperparameter_grid"]["defensive_return_20d_percentile_weight"], [0.0, 0.2])
        self.assertGreater(tighter_regime["selection_policy"]["screening_evidence"]["proxy_total_return"], 2.30)
        self.assertLess(abs(tighter_regime["selection_policy"]["screening_evidence"]["proxy_max_drawdown"]), 0.08)
        self.assertEqual(
            tighter_regime["selection_policy"]["screening_evidence"]["formal_160_status"],
            "observe_blocked_but_weaker_than_regime_adaptive_default",
        )
        confirmed = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "confirmed_concentrated_liquidity_momentum_20d_v1"
        )
        self.assertEqual(confirmed["selection_policy"]["mode"], "concentrated_top_k")
        self.assertEqual(confirmed["selection_policy"]["confirmation_policy"], "pit_momentum_industry_strength_filter")
        confirmed_10d = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "confirmed_concentrated_liquidity_momentum_10d_v1"
        )
        self.assertEqual(confirmed_10d["selection_policy"]["exit_policy"], "fixed_10_trading_day_horizon")
        balanced = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "balanced_confirmed_concentrated_liquidity_momentum_20d_v1"
        )
        self.assertEqual(balanced["selection_policy"]["mode"], "concentrated_top_k")
        self.assertEqual(
            balanced["selection_policy"]["confirmation_policy"],
            "pit_momentum_industry_strength_turnover_volatility_filter",
        )
        balanced_10d = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "balanced_confirmed_concentrated_liquidity_momentum_10d_v1"
        )
        self.assertEqual(balanced_10d["selection_policy"]["exit_policy"], "fixed_10_trading_day_horizon")
        regime_gated = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "regime_gated_balanced_concentrated_liquidity_momentum_20d_v1"
        )
        self.assertEqual(regime_gated["selection_policy"]["mode"], "concentrated_top_k")
        self.assertTrue(regime_gated["selection_policy"]["cash_switch"]["enabled"])
        risk_scaled = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1"
        )
        self.assertEqual(risk_scaled["selection_policy"]["mode"], "concentrated_top_k")
        self.assertTrue(risk_scaled["selection_policy"]["position_weighting"]["enabled"])
        self.assertEqual(risk_scaled["selection_policy"]["position_weighting"]["mode"], "volatility_turnover_scaled")
        exhaustion_aware = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "exhaustion_aware_medium_industry_pullback_v3_top3_20d_v1"
        )
        self.assertEqual(exhaustion_aware["model_type"], "exhaustion_aware_regime_breakout_ranker")
        self.assertEqual(exhaustion_aware["max_trials"], 8)
        self.assertEqual(exhaustion_aware["hyperparameter_grid"]["exhaustion_min_return_20d_percentile"], [0.95])
        self.assertEqual(exhaustion_aware["hyperparameter_grid"]["exhaustion_min_return_5d_percentile"], [0.95, 0.98])
        self.assertEqual(exhaustion_aware["hyperparameter_grid"]["exhaustion_max_benchmark_return_20d"], [0.03])
        self.assertEqual(
            exhaustion_aware["hyperparameter_grid"]["exhaustion_max_industry_return_20d_excess"],
            [0.25, 0.30],
        )
        self.assertEqual(exhaustion_aware["hyperparameter_grid"]["exhaustion_max_distance_from_20d_high"], [-0.020])
        self.assertEqual(exhaustion_aware["hyperparameter_grid"]["exhaustion_reference_date_scan_top_n"], [3])
        self.assertEqual(exhaustion_aware["hyperparameter_grid"]["exhaustion_reference_date_position_scale"], [0.0, 0.3])
        self.assertTrue(
            exhaustion_aware["selection_policy"]["signal_position_scaling"]["exhaustion_reference_date_scale"]["enabled"]
        )
        self.assertTrue(exhaustion_aware["selection_policy"]["screening_evidence"]["trigger_not_goal"])
        selected_exhaustion = next(
            spec
            for spec in artifact["model_specs"]
            if spec["model_spec_id"] == "selected_exhaustion_date_scaled_v3_top3_20d_v1"
        )
        self.assertEqual(selected_exhaustion["model_type"], "regime_adaptive_breakout_defensive_ranker")
        self.assertEqual(selected_exhaustion["max_trials"], 4)
        self.assertTrue(selected_exhaustion["selection_policy"]["selected_exhaustion_date_scale"]["enabled"])
        self.assertEqual(
            selected_exhaustion["hyperparameter_grid"]["selected_exhaustion_max_industry_return_20d_excess"],
            [0.19747611716278968],
        )
        self.assertEqual(selected_exhaustion["hyperparameter_grid"]["selected_exhaustion_date_position_scale"], [0.01])
        self.assertEqual(selected_exhaustion["hyperparameter_grid"]["rank3_weak_benchmark_gate_threshold"], [0.03])
        self.assertEqual(
            selected_exhaustion["selection_policy"]["rank_position_scaling"]["rank3_weak_benchmark_gate"][
                "position_scale"
            ],
            0.0,
        )
        screening_evidence = selected_exhaustion["selection_policy"]["screening_evidence"]
        self.assertEqual(
            screening_evidence["capacity_scope_status"],
            "requires_200k_or_lower_execution_capacity_contract",
        )
        self.assertEqual(screening_evidence["legacy_capacity_stress_notional_cny"], 1_000_000.0)
        self.assertEqual(screening_evidence["practical_capital_pool_notional_cny_max"], 200_000.0)
        self.assertEqual(screening_evidence["execution_mode_constraint"], "rolling_tranche_only")
        self.assertEqual(screening_evidence["forbidden_execution_mode"], "monthly_full_capital_rotation")
        self.assertEqual(
            screening_evidence["required_rolling_execution_contract"],
            "docs/contracts/SHORTPICK_V3_ROLLING_TRANCHE_EXECUTION_CONTRACT_2026-07-08.md",
        )
        self.assertEqual(screening_evidence["rolling_account_replay_status"], "completed_research_only_candidate_gate_passed")
        self.assertEqual(
            screening_evidence["rolling_account_full713_best_balance_config"],
            "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1",
        )
        self.assertEqual(screening_evidence["rolling_account_execution_min_order_notional_cny"], 2_250.0)
        self.assertEqual(screening_evidence["rolling_account_execution_budget_mode"], "current_nav_fraction")
        self.assertEqual(
            screening_evidence["rolling_account_exit_policy"],
            "rank3_pullback_rank1_quick_fail_guard",
        )
        self.assertGreater(screening_evidence["rolling_account_full713_best_balance_annualized_return"], 0.60)
        self.assertEqual(screening_evidence["rolling_account_full713_best_balance_negative_month_count"], 4)
        self.assertLess(screening_evidence["rolling_account_full713_best_balance_skipped_order_rate"], 0.5)

    def test_dynamic_weight_spec_requires_oos_and_governance(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        dynamic_spec = next(
            spec for spec in artifact["model_specs"] if spec["model_spec_id"] == "regime_conditioned_linear_v1"
        )

        self.assertTrue(dynamic_spec["dynamic_weight_policy"]["enabled"])
        self.assertTrue(dynamic_spec["dynamic_weight_policy"]["requires_oos_gate_pass"])
        self.assertTrue(dynamic_spec["dynamic_weight_policy"]["requires_governance_approval"])
        self.assertEqual(dynamic_spec["dynamic_weight_policy"]["multiplier_clip"], [0.5, 1.5])

    def test_rejected_capacity_v3_scorers_are_not_in_default_registry(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        spec_ids = set(artifact["model_spec_ids"])

        self.assertNotIn("capacity_aware_v3_regime_breakout_top3_20d_v1", spec_ids)
        self.assertNotIn("fillable_weak_turnaround_v3_top3_20d_v1", spec_ids)
        self.assertNotIn("learned_fillable_rank_linear_v3_top3_20d_v1", spec_ids)
        self.assertNotIn("tail_capture_fillable_rank_linear_v3_top3_20d_v1", spec_ids)

    def test_registry_validation_rejects_unbounded_search_space(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        artifact["model_specs"][0]["hyperparameter_grid"]["top_k"] = list(range(20))
        artifact["model_specs"][0]["max_trials"] = 20

        validation = validate_model_spec_registry_payload(artifact)

        self.assertEqual(validation["status"], "failed")
        self.assertIn("baseline_momentum_10d_turnover_cooldown_v1:unbounded_search_space", validation["failures"])

    def test_registry_writes_to_research_validation_namespace(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_model_spec_registry_artifact(artifact, artifact_root=Path(temp_dir))

            self.assertEqual(path.parent, Path(temp_dir) / "research_validation" / "model_spec_registries")


if __name__ == "__main__":
    unittest.main()
