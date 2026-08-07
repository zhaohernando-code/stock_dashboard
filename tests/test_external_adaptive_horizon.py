from __future__ import annotations

from datetime import date

import pytest

from ashare_evidence.external_adaptive_horizon import (
    _past_only_channel_percentiles,
    _rank1_horizon_labels,
    _standardized_ridge_prediction,
)


def test_standardized_ridge_prediction_keeps_feature_scale_from_dominating() -> None:
    features = [[float(index), float(index) * 1_000_000.0] for index in range(1, 11)]
    targets = [float(index) * 0.01 for index in range(1, 11)]
    prediction = _standardized_ridge_prediction(features, targets, [11.0, 11_000_000.0], alpha=1.0)
    assert prediction == pytest.approx(0.107380952, rel=1e-5)


def test_past_only_channel_percentiles_exclude_current_prediction() -> None:
    predictions = {
        "2026-01-01": {"short_advantage": 0.1, "long_advantage": 0.3},
        "2026-01-02": {"short_advantage": 0.2, "long_advantage": 0.2},
        "2026-01-03": {"short_advantage": 0.3, "long_advantage": 0.1},
    }
    rows = _past_only_channel_percentiles(predictions, minimum_prior_predictions=2)
    assert rows["2026-01-01"] is None
    assert rows["2026-01-02"] is None
    assert rows["2026-01-03"] == {"short_advantage": 1.0, "long_advantage": 0.0}


def test_rank1_horizon_labels_are_available_only_after_thirty_bars() -> None:
    bars = [
        {"day": date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + index).isoformat(), "close": 10 + index}
        for index in range(40)
    ]
    snapshot = {
        "inputs": {"market_bars_by_symbol": {"AAA": bars}},
        "baseline_output": {
            "order_ledger": [
                {
                    "action": "buy",
                    "rank": 1,
                    "signal_day": "2026-01-01",
                    "trade_day": "2026-01-02",
                    "symbol": "AAA",
                    "price": 11.0,
                }
            ]
        },
    }
    labels = _rank1_horizon_labels(snapshot, signal_end=date(2026, 2, 1))
    label = labels["2026-01-01"]
    assert label["available_day"] == "2026-02-01"
    assert label["short_advantage"] == pytest.approx(21 / 11 - 31 / 11)
    assert label["long_advantage"] == pytest.approx(41 / 11 - 31 / 11)
