from __future__ import annotations

import copy
from datetime import date, timedelta

from ashare_evidence.hotspot_secondary_start import (
    RecoveryVariant,
    secondary_start_stock_features,
    select_secondary_start_candidate,
)


def _crash_then_restart() -> list[dict[str, object]]:
    closes = [100.0 + index * 0.1 for index in range(40)]
    closes += [95.0, 88.0, 82.0, 80.0, 81.0, 84.0, 89.0]
    start = date(2026, 1, 1)
    return [
        {"day": (start + timedelta(days=index)).isoformat(), "close": value}
        for index, value in enumerate(closes)
    ]


def test_secondary_start_features_ignore_future_bars() -> None:
    rows = _crash_then_restart()
    signal_day = str(rows[-1]["day"])
    before = secondary_start_stock_features(rows=rows, signal_day=signal_day)
    changed = copy.deepcopy(rows)
    changed.append({"day": "2026-03-01", "close": 1000.0})
    after = secondary_start_stock_features(rows=changed, signal_day=signal_day)
    assert before == after
    assert before is not None
    assert before["shock_drawdown"] < -0.15
    assert before["return_1d"] > 0.0
    assert before["prior_return_1d"] > 0.0


def test_one_day_bounce_is_not_a_secondary_start() -> None:
    rows = _crash_then_restart()
    rows[-2]["close"] = 78.0
    features = secondary_start_stock_features(rows=rows, signal_day=str(rows[-1]["day"]))
    assert features is not None
    assert features["prior_return_1d"] < 0.0


def test_selection_requires_stock_and_sector_confirmation_and_strips_outcomes() -> None:
    rows = _crash_then_restart()
    day = str(rows[-1]["day"])
    memory_row = {
        "symbol": "600001.SH",
        "stock_name": "example",
        "industry_name": "银行",
        "rank": 8,
        "score": 1.0,
        "net_excess_return": 9.0,
        "weighted_net_excess_return": 9.0,
    }
    registry = {
        "600001.SH": {
            "row": memory_row,
            "best_rank": 8,
            "last_seen_day": day,
            "last_seen_signal_index": 20,
        }
    }
    variant = RecoveryVariant("test", -0.15, 0.05, 0.20, 0.55, 0.70)
    selected, _ = select_secondary_start_candidate(
        signal_day=day,
        signal_index=20,
        registry=registry,
        original_top3=[],
        sector_states={
            "银行": {
                "member_count": 10.0,
                "current_positive_breadth": 0.8,
                "prior_positive_breadth": 0.7,
                "mean_two_day_return": 0.08,
                "median_two_day_return": 0.07,
                "two_day_return_percentile": 0.9,
            }
        },
        market_bars_by_symbol={"600001.SH": rows},
        bar_indices_by_symbol={"600001.SH": {str(row["day"]): index for index, row in enumerate(rows)}},
        variant=variant,
        last_selected_signal_index={},
    )
    assert selected is not None
    assert selected["symbol"] == "600001.SH"
    assert "net_excess_return" not in selected
    assert "weighted_net_excess_return" not in selected

    rejected, audit = select_secondary_start_candidate(
        signal_day=day,
        signal_index=20,
        registry=registry,
        original_top3=[],
        sector_states={},
        market_bars_by_symbol={"600001.SH": rows},
        bar_indices_by_symbol={"600001.SH": {str(row["day"]): index for index, row in enumerate(rows)}},
        variant=variant,
        last_selected_signal_index={},
    )
    assert rejected is None
    assert audit["rejection_counts"]["sector_state_missing"] == 1
