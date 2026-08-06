from __future__ import annotations

import pytest

from ashare_evidence.external_context_residual_policy import (
    apply_bounded_external_residual,
    compute_external_residual,
    select_smallest_weight_within_one_standard_error,
)


def test_lambda_zero_permanently_preserves_v3_score_and_exposure() -> None:
    for channel in ("global_state", "sector_state", "individual_event"):
        result = apply_bounded_external_residual(
            channel=channel,
            core_score_z=1.25,
            external_residual_z=4.0,
            lambda_weight=0.0,
            cap=0.3,
            core_eligible=True,
        )
        assert result["final_score_z"] == 1.25
        assert result["gross_exposure_multiplier"] == 1.0
        assert result["v3_baseline_preserved"] is True


def test_three_channels_cannot_cross_scope_boundaries() -> None:
    global_result = apply_bounded_external_residual(
        channel="global_state",
        core_score_z=1.0,
        external_residual_z=2.0,
        lambda_weight=0.1,
        cap=0.3,
        core_eligible=True,
    )
    sector_result = apply_bounded_external_residual(
        channel="sector_state",
        core_score_z=1.0,
        external_residual_z=2.0,
        lambda_weight=0.1,
        cap=0.3,
        core_eligible=True,
    )
    individual_result = apply_bounded_external_residual(
        channel="individual_event",
        core_score_z=1.0,
        external_residual_z=2.0,
        lambda_weight=0.1,
        cap=0.3,
        core_eligible=True,
    )

    assert global_result["final_score_z"] == 1.0
    assert global_result["gross_exposure_multiplier"] == 0.8
    assert sector_result["final_score_z"] == 0.8
    assert sector_result["gross_exposure_multiplier"] == 1.0
    assert sector_result["score_scope"] == "within_sector_ranking_only"
    assert individual_result["final_score_z"] == 0.8
    assert individual_result["score_scope"] == "individual_incremental_score_only"


def test_positive_news_cannot_create_eligibility_and_official_negative_can_block() -> None:
    favorable = apply_bounded_external_residual(
        channel="individual_event",
        core_score_z=-1.0,
        external_residual_z=-5.0,
        lambda_weight=0.15,
        cap=0.3,
        core_eligible=False,
    )
    blocked = apply_bounded_external_residual(
        channel="individual_event",
        core_score_z=2.0,
        external_residual_z=2.0,
        lambda_weight=0.05,
        cap=0.3,
        core_eligible=True,
        official_major_negative_gate=True,
    )

    assert favorable["final_score_z"] > -1.0
    assert favorable["final_eligible"] is False
    assert favorable["positive_external_information_can_create_eligibility"] is False
    assert blocked["final_eligible"] is False
    assert blocked["official_major_negative_gate"] is True


def test_external_residual_requires_past_only_prediction_model() -> None:
    residual = compute_external_residual(
        external_signal=0.8,
        predicted_external_from_core=0.5,
        prediction_model_fit_end="2024-01-01T00:00:00+08:00",
        decision_cutoff="2024-01-02T14:00:00+08:00",
    )
    assert residual["external_residual"] == pytest.approx(0.3)
    assert residual["fit_is_past_only"] is True

    with pytest.raises(ValueError, match="strictly before"):
        compute_external_residual(
            external_signal=0.8,
            predicted_external_from_core=0.5,
            prediction_model_fit_end="2024-01-02T14:00:00+08:00",
            decision_cutoff="2024-01-02T14:00:00+08:00",
        )


def test_one_standard_error_rule_selects_smallest_stable_weight_not_peak() -> None:
    result = select_smallest_weight_within_one_standard_error(
        [
            {"lambda_weight": 0.0, "oos_mean": 0.09, "oos_standard_error": 0.01, "all_gates_passed": True},
            {"lambda_weight": 0.025, "oos_mean": 0.105, "oos_standard_error": 0.01, "all_gates_passed": True},
            {"lambda_weight": 0.05, "oos_mean": 0.11, "oos_standard_error": 0.015, "all_gates_passed": True},
            {"lambda_weight": 0.075, "oos_mean": 0.12, "oos_standard_error": 0.02, "all_gates_passed": True},
            {"lambda_weight": 0.1, "oos_mean": 0.125, "oos_standard_error": 0.01, "all_gates_passed": False},
        ]
    )

    assert result["best_lambda_weight"] == 0.075
    assert result["selected_lambda_weight"] == 0.025
    assert result["v3_lambda_zero_retained_in_comparison"] is True
