from __future__ import annotations

from ashare_evidence.global_sector_state_account_ablation import (
    PastOnlyRidge,
    apply_negative_external_guard,
    apply_sector_near_tie_budget_shift,
    past_only_probability_percentiles,
    rerank_inventory_with_sector_residual,
    standardized_logistic_probability,
)
from ashare_evidence.rolling_tranche_account_replay import _rank1_quality_scale


def test_past_only_ridge_predicts_before_update() -> None:
    ridge = PastOnlyRidge(feature_count=1, alpha=1.0)
    assert ridge.predict_one([2.0]) == 0.0
    ridge.update_one([1.0], 3.0)
    assert ridge.row_count == 1
    assert ridge.predict_one([1.0]) > 0.0


def test_lambda_zero_keeps_core_order() -> None:
    rows = [
        {"rank": 1, "score": 3.0, "industry_name": "银行", "symbol": "A"},
        {"rank": 2, "score": 2.9, "industry_name": "半导体", "symbol": "B"},
        {"rank": 3, "score": 2.8, "industry_name": "元器件", "symbol": "C"},
    ]
    reranked = rerank_inventory_with_sector_residual(rows, external_residual_z=2.0, weight=0.0)
    assert [row["symbol"] for row in reranked] == ["A", "B", "C"]
    assert all(row["external_sector_contribution"] == 0.0 for row in reranked)


def test_positive_tech_residual_can_change_near_tie_without_overriding_large_core_gap() -> None:
    rows = [
        {"rank": 1, "score": 3.0, "industry_name": "银行", "symbol": "A"},
        {"rank": 2, "score": 2.99, "industry_name": "半导体", "symbol": "B"},
        {"rank": 3, "score": 1.0, "industry_name": "元器件", "symbol": "C"},
    ]
    reranked = rerank_inventory_with_sector_residual(rows, external_residual_z=2.0, weight=0.15)
    assert reranked[0]["symbol"] == "B"
    assert reranked[-1]["symbol"] == "C"
    assert max(abs(row["external_sector_contribution"]) for row in reranked) <= 0.30


def test_negative_guard_only_trims_rank1_and_never_increases_position() -> None:
    picks = [
        {"rank": 1, "symbol": "A", "industry_name": "半导体", "portfolio_weight": 1.0},
        {"rank": 2, "symbol": "B", "industry_name": "银行", "portfolio_weight": 1.0},
    ]
    guarded, audit = apply_negative_external_guard(
        picks,
        global_risk_z=-2.0,
        global_breadth_5d=0.0,
        tech_residual_z=-2.0,
        variant={
            "global_risk_z_max": -1.5,
            "global_breadth_5d_max": 0.25,
            "global_scale": 0.85,
            "tech_risk_z_max": -1.5,
            "tech_scale": 0.80,
        },
    )
    assert guarded[0]["portfolio_weight"] == 0.80
    assert guarded[1]["portfolio_weight"] == 1.0
    assert audit["triggered"] is True


def test_standardized_logistic_assigns_higher_loss_probability_to_loss_cluster() -> None:
    features = [[-2.0], [-1.5], [-1.0], [1.0], [1.5], [2.0]]
    labels = [0, 0, 0, 1, 1, 1]
    low = standardized_logistic_probability(features, labels, [-1.75], l2_penalty=1.0)
    high = standardized_logistic_probability(features, labels, [1.75], l2_penalty=1.0)
    assert low < 0.5 < high


def test_standardized_logistic_respects_positive_sample_weights() -> None:
    features = [[-2.0], [-1.0], [1.0], [2.0]]
    labels = [0, 0, 1, 0]
    unweighted = standardized_logistic_probability(features, labels, [1.0], l2_penalty=1.0)
    weighted = standardized_logistic_probability(
        features,
        labels,
        [1.0],
        l2_penalty=1.0,
        sample_weights=[1.0, 1.0, 8.0, 1.0],
    )
    assert weighted > unweighted


def test_probability_percentile_uses_only_strictly_prior_predictions() -> None:
    values = {"d1": 0.2, "d2": 0.4, "d3": 0.3}
    percentiles = past_only_probability_percentiles(values, minimum_prior_predictions=1)
    assert percentiles["d1"] is None
    assert percentiles["d2"] == 1.0
    assert percentiles["d3"] == 0.5


def test_rank1_quality_overlay_scale_identifies_only_core_strong_signal() -> None:
    overlay = {
        "strong_return_20d_percentile_min": 0.95,
        "strong_return_5d_percentile_min": 0.93,
        "strong_benchmark_return_20d_min": 0.0,
        "strong_industry_return_20d_excess_max": 0.50,
        "strong_distance_from_20d_high_min": -0.08,
        "strong_scale": 1.54,
    }
    strong = {
        "return_20d_percentile": 0.97,
        "return_5d_percentile": 0.96,
        "benchmark_return_20d": 0.02,
        "industry_return_20d_excess": 0.10,
        "distance_from_20d_high": -0.02,
    }
    assert _rank1_quality_scale(strong, overlay=overlay) == 1.54
    assert _rank1_quality_scale({**strong, "return_5d_percentile": 0.90}, overlay=overlay) == 1.0


def test_sector_near_tie_shift_conserves_effective_budget_and_requires_both_baseline_buys() -> None:
    picks = [
        {"rank": 1, "symbol": "A", "score": 1.00, "portfolio_weight": 1.0, "rank_weight_multiplier": 2.73},
        {"rank": 2, "symbol": "B", "score": 0.99, "portfolio_weight": 1.0, "rank_weight_multiplier": 0.27},
    ]
    adjusted, audit = apply_sector_near_tie_budget_shift(
        picks,
        residuals_by_symbol={"A": -1.0, "B": 1.0},
        baseline_buy_keys={("2025-01-01", "A", 1), ("2025-01-01", "B", 2)},
        signal_day="2025-01-01",
        score_gap_max=0.02,
        residual_advantage_min=1.0,
        transfer_fraction=0.10,
    )
    assert audit["triggered"] is True
    assert abs(audit["effective_budget_before"] - audit["effective_budget_after"]) < 1e-12
    blocked, blocked_audit = apply_sector_near_tie_budget_shift(
        picks,
        residuals_by_symbol={"A": -1.0, "B": 1.0},
        baseline_buy_keys={("2025-01-01", "A", 1)},
        signal_day="2025-01-01",
        score_gap_max=0.02,
        residual_advantage_min=1.0,
        transfer_fraction=0.10,
    )
    assert blocked_audit["triggered"] is False
    assert blocked == picks
