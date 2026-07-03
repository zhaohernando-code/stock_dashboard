"""Validate factor IC computation and weight calibration."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_spearman_ic():
    """Rank IC should be +1 for monotonic positive relationship."""
    from ashare_evidence.phase2.factor_ic import compute_rank_ic

    # Perfect positive monotonic: scores [1,2,3,4,5] vs returns [1,2,3,4,5]
    scores = {"test_factor": [1.0, 2.0, 3.0, 4.0, 5.0]}
    returns = [0.01, 0.02, 0.03, 0.04, 0.05]
    results = compute_rank_ic(scores, returns, horizon_days=20)
    assert len(results) == 1
    assert results[0].ic_mean > 0.9, f"Expected IC ~1.0, got {results[0].ic_mean}"
    print("PASS: positive rank IC")


def test_spearman_ic_negative():
    """Rank IC should be -1 for perfect negative monotonic."""
    from ashare_evidence.phase2.factor_ic import compute_rank_ic

    scores = {"neg_factor": [5.0, 4.0, 3.0, 2.0, 1.0]}
    returns = [0.01, 0.02, 0.03, 0.04, 0.05]
    results = compute_rank_ic(scores, returns, horizon_days=20)
    assert results[0].ic_mean < -0.9
    print("PASS: negative rank IC")


def test_spearman_ic_noisy():
    """Random scores should yield IC near zero."""
    from ashare_evidence.phase2.factor_ic import compute_rank_ic

    scores = {"noise": [0.3, -0.5, 0.1, 0.9, -0.2, 0.0, -0.8, 0.4]}
    returns = [0.01, -0.02, 0.0, 0.03, -0.01, 0.02, -0.03, 0.01]
    results = compute_rank_ic(scores, returns, horizon_days=20)
    # Should be between -0.8 and 0.8 (not perfectly correlated)
    assert -0.9 < results[0].ic_mean < 0.9
    print("PASS: noisy rank IC")


def test_minimum_symbols():
    """Fewer than 5 symbols should return empty results."""
    from ashare_evidence.phase2.factor_ic import compute_rank_ic

    scores = {"f": [1.0, 2.0]}
    returns = [0.01, 0.02]
    results = compute_rank_ic(scores, returns, horizon_days=20)
    assert len(results) == 0
    print("PASS: minimum symbols check")


def test_aggregate_ic():
    """Aggregation should compute mean, std, IR correctly."""
    from ashare_evidence.phase2.factor_ic import FactorICResult, aggregate_ic_results

    results = [
        FactorICResult("f1", 20, 0.05, 0.0, 0.0, 0.8, 100, ""),
        FactorICResult("f1", 20, 0.08, 0.0, 0.0, 0.9, 100, ""),
        FactorICResult("f1", 20, 0.03, 0.0, 0.0, 0.7, 100, ""),
    ]
    agg = aggregate_ic_results(results, periods_per_year=20)
    assert "f1" in agg
    a = agg["f1"]
    assert abs(a.ic_mean - 0.053333) < 0.01
    assert a.ic_positive_rate == 1.0
    assert a.weighting_status == "blocked"
    assert a.weighting_reason == "requires_at_least_20_windows_and_600_cross_section_samples_with_positive_ic_ir"
    print("PASS: aggregate IC")


def test_ic_based_weights():
    """Factors with positive IC_IR should get non-zero weights."""
    from ashare_evidence.phase2.factor_ic import FactorICResult, ic_based_weights

    results = {
        "price": FactorICResult("price", 20, 0.04, 0.02, 8.94, 0.8, 600, "", period_count=20, weighting_status="eligible"),
        "news": FactorICResult("news", 20, 0.02, 0.02, 4.47, 0.7, 600, "", period_count=20, weighting_status="eligible"),
        "bad_factor": FactorICResult("bad", 20, -0.01, 0.02, -2.24, 0.3, 100, ""),
    }
    weights = ic_based_weights(results, default_weights={"price": 0.50, "news": 0.30, "bad_factor": 0.20})
    assert weights["price"] > weights["news"], f"Price should dominate: {weights}"
    assert weights.get("bad_factor", 0.0) == 0.0, f"Bad factor should have zero weight: {weights}"
    assert abs(sum(weights.values()) - 1.0) < 0.01
    print("PASS: IC-based weights")


def test_ic_based_weights_block_small_sample_gate():
    """Small-sample IC remains diagnostic and cannot dominate production weights."""
    from ashare_evidence.phase2.factor_ic import FactorICResult, ic_based_weights

    results = {
        "price": FactorICResult("price", 20, 0.04, 0.02, 8.94, 0.8, 100, ""),
        "news": FactorICResult("news", 20, 0.02, 0.02, 4.47, 0.7, 100, ""),
    }
    weights = ic_based_weights(results, default_weights={"price": 0.50, "news": 0.30})
    assert weights == {"price": 0.625, "news": 0.375}
    print("PASS: IC gate blocks small-sample weights")


def test_rolling_ic_decay_detection():
    """Decay detection should flag persistent low IC."""
    from ashare_evidence.phase2.factor_ic import RollingICSeries

    s = RollingICSeries("test", 20, 60, [], [])
    assert not s.is_decaying()  # no data

    s.ic_values = [0.05, 0.03, 0.04, 0.02, -0.01, 0.009, 0.0, 0.005, 0.003, 0.001]
    assert s.is_decaying(threshold=0.02, periods=5), "Last 5 values must all be < 0.02"
    assert not s.is_decaying(threshold=0.02, periods=10), "Not all 10 are below 0.02"
    print("PASS: rolling IC decay detection")


def test_rolling_ic_weights_require_long_history_before_adjustment():
    """Dynamic weight changes stay blocked until there is enough independent IC history."""
    from ashare_evidence.phase2.factor_ic import RollingICSeries, rolling_ic_weights

    base_weights = {"price": 0.6, "news": 0.4}
    short_price_series = RollingICSeries("price", 20, 60, [0.01] * 54 + [0.10] * 5, [])
    short_news_series = RollingICSeries("news", 20, 60, [0.10] * 54 + [0.01] * 5, [])

    weights = rolling_ic_weights(
        base_weights,
        {"price": short_price_series, "news": short_news_series},
    )

    assert weights == base_weights
    print("PASS: rolling IC adjustment gate requires long history")


if __name__ == "__main__":
    test_spearman_ic()
    test_spearman_ic_negative()
    test_spearman_ic_noisy()
    test_minimum_symbols()
    test_aggregate_ic()
    test_ic_based_weights()
    test_ic_based_weights_block_small_sample_gate()
    test_rolling_ic_decay_detection()
    test_rolling_ic_weights_require_long_history_before_adjustment()
    print("\nAll factor IC tests passed!")
