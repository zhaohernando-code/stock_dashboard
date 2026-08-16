from __future__ import annotations

import copy
from datetime import date, timedelta

from ashare_evidence.hotspot_state_model import (
    attach_forward_label,
    past_only_percentile,
    stock_state_features,
)
from ashare_evidence.hotspot_state_model_replay import expanding_model_selections


def _bars(count: int = 90) -> list[dict[str, object]]:
    start = date(2025, 1, 1)
    return [
        {"day": (start + timedelta(days=index)).isoformat(), "close": 10.0 + index * 0.1}
        for index in range(count)
    ]


def test_stock_state_features_ignore_future_prices() -> None:
    rows = _bars()
    signal_day = str(rows[70]["day"])
    before = stock_state_features(rows, signal_day=signal_day)
    changed = copy.deepcopy(rows)
    changed[-1]["close"] = 10000.0
    after = stock_state_features(changed, signal_day=signal_day)
    assert before == after


def test_forward_label_is_available_only_on_exit_day() -> None:
    rows = _bars()
    signal_day = str(rows[65]["day"])
    candidate = {"signal_day": signal_day, "symbol": "600001.SH"}
    indices = {str(row["day"]): index for index, row in enumerate(rows)}
    labeled = attach_forward_label(
        candidate,
        market_bars_by_symbol={"600001.SH": rows},
        bar_indices_by_symbol={"600001.SH": indices},
    )
    assert labeled["label_available_day"] == rows[76]["day"]
    assert labeled["positive_label"] == 1


def test_past_only_percentile_needs_forty_prior_prediction_days() -> None:
    assert past_only_percentile(0.7, [0.5] * 39) is None
    assert past_only_percentile(0.7, [0.5] * 40) == 1.0


def test_expanding_model_never_uses_label_available_after_fit_day() -> None:
    rows_by_day = {}
    start = date(2025, 1, 1)
    for day_index in range(90):
        day = (start + timedelta(days=day_index)).isoformat()
        rows = []
        for symbol_index in range(50):
            positive = int(symbol_index % 2 == 0)
            row = {
                "signal_day": day,
                "symbol": f"600{symbol_index:03d}.SH",
                "memory_row": {"symbol": f"600{symbol_index:03d}.SH", "stock_name": "x"},
                "label_available_day": (start + timedelta(days=day_index + 11)).isoformat(),
                "positive_label": positive,
            }
            for name_index, name in enumerate(
                (
                    "memory_quality", "memory_recency", "current_core_present", "current_core_quality",
                    "return_2d", "return_5d", "return_10d", "return_20d", "return_5d_acceleration",
                    "distance_from_20d_high", "maximum_drawdown_20d", "volatility_20d", "close_vs_sma5",
                    "close_vs_sma10", "shock_drawdown_60d", "trough_age_60d",
                    "sector_current_positive_breadth", "sector_prior_positive_breadth",
                    "sector_mean_two_day_return", "sector_median_two_day_return",
                    "sector_two_day_return_percentile",
                )
            ):
                row[name] = float(positive) + name_index * 0.001
            rows.append(row)
        rows_by_day[day] = rows
    _, audit = expanding_model_selections(rows_by_day, feature_set="stock_only")
    assert audit["fit_count"] > 0
    assert audit["future_label_violation_count"] == 0
    assert all(row["maximum_label_available_day"] <= row["fit_day"] for row in audit["fit_rows"])
