from __future__ import annotations

from math import isclose, sqrt
from statistics import pstdev

from ashare_evidence.rank5_path_quality import enrich_inventory_with_path_quality_features


def test_path_quality_features_match_frozen_formulas() -> None:
    closes = [100.0]
    daily_returns = [0.01, -0.02, 0.03, -0.01] * 5
    for daily_return in daily_returns:
        closes.append(closes[-1] * (1.0 + daily_return))
    bars = [
        {"day": f"2026-01-{index + 1:02d}", "close": close}
        for index, close in enumerate(closes)
    ]

    row = enrich_inventory_with_path_quality_features(
        [{"as_of_date": "2026-01-21", "symbol": "AAA"}],
        market_bars_by_symbol={"AAA": bars},
    )[0]

    assert row["path_feature_observation_count"] == 20
    assert isclose(row["path_realized_volatility_20d"], pstdev(daily_returns))
    assert isclose(
        row["path_downside_semivolatility_20d"],
        sqrt(sum(min(value, 0.0) ** 2 for value in daily_returns) / 20),
    )
    running_peak = closes[0]
    expected_drawdown = 0.0
    for close in closes:
        running_peak = max(running_peak, close)
        expected_drawdown = min(expected_drawdown, close / running_peak - 1.0)
    assert isclose(row["path_max_drawdown_20d"], expected_drawdown)
    assert row["path_up_day_ratio_20d"] == 0.5
    assert isclose(
        row["path_trend_efficiency_20d"],
        abs(sum(daily_returns)) / sum(abs(value) for value in daily_returns),
    )


def test_path_quality_never_uses_closes_after_signal_day() -> None:
    history = [{"day": f"2026-01-{index + 1:02d}", "close": 100.0 + index} for index in range(21)]
    baseline = enrich_inventory_with_path_quality_features(
        [{"as_of_date": "2026-01-21", "symbol": "AAA"}],
        market_bars_by_symbol={"AAA": history},
    )[0]
    with_future_crash = enrich_inventory_with_path_quality_features(
        [{"as_of_date": "2026-01-21", "symbol": "AAA"}],
        market_bars_by_symbol={
            "AAA": [*history, {"day": "2026-01-22", "close": 1.0}, {"day": "2026-01-23", "close": 500.0}]
        },
    )[0]

    for key, value in baseline.items():
        if key.startswith("path_"):
            assert with_future_crash[key] == value


def test_path_quality_fails_closed_with_insufficient_history() -> None:
    row = enrich_inventory_with_path_quality_features(
        [{"as_of_date": "2026-01-10", "symbol": "AAA"}],
        market_bars_by_symbol={
            "AAA": [{"day": f"2026-01-{index + 1:02d}", "close": 100.0 + index} for index in range(10)]
        },
    )[0]

    assert row["path_feature_observation_count"] == 9
    assert row["path_realized_volatility_20d"] is None
    assert row["path_downside_semivolatility_20d"] is None
    assert row["path_max_drawdown_20d"] is None
    assert row["path_up_day_ratio_20d"] is None
    assert row["path_trend_efficiency_20d"] is None
