from __future__ import annotations

import copy

from ashare_evidence.v3_rebound_deployment import (
    apply_rebound_deployment_boost,
    rebound_deployment_trigger,
)


def _accelerating_bars(symbols: tuple[str, ...]) -> dict[str, list[dict]]:
    return {
        symbol: [
            {"day": f"2026-01-{index:02d}", "close": 10.0 + index**2 + offset}
            for index in range(1, 8)
        ]
        for offset, symbol in enumerate(symbols)
    }


def test_rebound_trigger_requires_stock_and_sector_confirmation() -> None:
    day = "2026-01-07"
    picks = [{"symbol": symbol} for symbol in ("A", "B", "C")]
    sector_state = {
        "breadth_5d": 0.8,
        "breadth_20d": 0.4,
        "mean_return_5d": 0.10,
        "mean_return_20d": 0.02,
    }
    triggered, audit = rebound_deployment_trigger(
        picks=picks,
        signal_day=day,
        sector_state=sector_state,
        market_bars_by_symbol=_accelerating_bars(("A", "B", "C")),
    )

    assert triggered
    assert audit["median_v3_top3_return_5d"] > 0.0
    weak_sector = {**sector_state, "breadth_5d": 0.2}
    assert not rebound_deployment_trigger(
        picks=picks,
        signal_day=day,
        sector_state=weak_sector,
        market_bars_by_symbol=_accelerating_bars(("A", "B", "C")),
    )[0]


def test_rebound_trigger_is_unchanged_when_future_bars_change() -> None:
    day = "2026-01-07"
    picks = [{"symbol": symbol} for symbol in ("A", "B", "C")]
    bars = _accelerating_bars(("A", "B", "C"))
    for rows in bars.values():
        rows.append({"day": "2026-01-08", "close": 100.0})
    sector_state = {
        "breadth_5d": 0.8,
        "breadth_20d": 0.4,
        "mean_return_5d": 0.10,
        "mean_return_20d": 0.02,
    }
    before = rebound_deployment_trigger(
        picks=picks, signal_day=day, sector_state=sector_state, market_bars_by_symbol=bars
    )
    changed = copy.deepcopy(bars)
    for rows in changed.values():
        rows[-1]["close"] = 0.01
    after = rebound_deployment_trigger(
        picks=picks, signal_day=day, sector_state=sector_state, market_bars_by_symbol=changed
    )

    assert before == after


def test_deployment_boost_never_changes_symbols_ranks_or_zero_weight() -> None:
    picks = [
        {"symbol": symbol, "rank": rank, "portfolio_weight": 1.0}
        for rank, symbol in enumerate(("A", "B", "C"), start=1)
    ]
    assert apply_rebound_deployment_boost(picks, weight=0.0, triggered=True) == picks
    boosted = apply_rebound_deployment_boost(picks, weight=0.1, triggered=True)

    assert [(row["symbol"], row["rank"]) for row in boosted] == [
        (row["symbol"], row["rank"]) for row in picks
    ]
    assert all(abs(float(row["portfolio_weight"]) - 1.1) < 1e-12 for row in boosted)
    assert picks[0]["portfolio_weight"] == 1.0
