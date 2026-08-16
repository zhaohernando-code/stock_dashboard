from __future__ import annotations

import pytest

from ashare_evidence.v3_position_lifecycle import lifecycle_position_features, lifecycle_variant_triggered


def test_lifecycle_features_use_only_entry_through_decision_close() -> None:
    features = lifecycle_position_features(
        closes=[100.0, 102.0, 99.0, 97.0, 94.0, 200.0],
        entry_index=0,
        decision_index=4,
        top3_absence_streak=3,
    )

    assert features["holding_sessions"] == 4
    assert features["position_return"] == pytest.approx(-0.06)
    assert features["trailing_3_session_return"] == pytest.approx(94.0 / 102.0 - 1.0)
    assert features["drawdown_from_peak"] == pytest.approx(94.0 / 102.0 - 1.0)
    assert features["close_below_sma5"] is True
    assert features["top3_absence_streak"] == 3


def test_price_loss_acceleration_trigger_is_bounded_by_frozen_conditions() -> None:
    variant = {
        "minimum_holding_sessions": 4,
        "maximum_position_return": -0.04,
        "maximum_trailing_3_session_return": -0.025,
        "require_close_below_sma5": True,
    }
    features = {
        "holding_sessions": 4,
        "position_return": -0.05,
        "trailing_3_session_return": -0.03,
        "drawdown_from_peak": -0.06,
        "close_below_sma5": True,
        "top3_absence_streak": 0,
    }

    assert lifecycle_variant_triggered(features, variant) is True
    assert lifecycle_variant_triggered({**features, "position_return": -0.03}, variant) is False


def test_rank_decay_trigger_requires_absence_and_loss() -> None:
    variant = {
        "minimum_holding_sessions": 5,
        "minimum_consecutive_top3_absence_signal_days": 3,
        "maximum_position_return": -0.03,
        "require_close_below_sma5": True,
    }
    features = {
        "holding_sessions": 6,
        "position_return": -0.04,
        "trailing_3_session_return": 0.01,
        "drawdown_from_peak": -0.08,
        "close_below_sma5": True,
        "top3_absence_streak": 3,
    }

    assert lifecycle_variant_triggered(features, variant) is True
    assert lifecycle_variant_triggered({**features, "top3_absence_streak": 2}, variant) is False
