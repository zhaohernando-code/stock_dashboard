from __future__ import annotations

from datetime import date, timedelta

from ashare_evidence.external_rank_pair_allocation import _pair_labels


def test_pair_labels_use_later_twenty_bar_exit() -> None:
    start = date(2026, 1, 1)
    bars = [
        {"day": (start + timedelta(days=index)).isoformat(), "close": 10.0 + index}
        for index in range(30)
    ]
    snapshot = {"inputs": {"market_bars_by_symbol": {"AAA": bars, "BBB": bars}}}
    picks = {
        "2026-01-01": [
            {"rank": 1, "symbol": "AAA"},
            {"rank": 2, "symbol": "BBB"},
        ]
    }
    labels = _pair_labels(snapshot, picks_by_date=picks, signal_end=date(2026, 2, 1))
    assert labels["2026-01-01"]["available_day"] == "2026-01-22"
    assert labels["2026-01-01"]["rank2_advantage"] == 0.0
