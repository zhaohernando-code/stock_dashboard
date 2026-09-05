from __future__ import annotations

import pytest

from ashare_evidence.daily_order_replay import replay_reserved_daily_orders, reserve_limit_order


def run_fixture(*, future_low=9.0, future_close=10.0, second_symbol=False, flat_exit=False):
    calendar = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    symbols = ["600001.SH", "600002.SH"] if second_symbol else ["600001.SH"]
    bars = {
        s: {d: {"open": 10.0, "close": 10.0, "low": 9.0, "high": 11.0, "volume": 1000} for d in calendar}
        for s in symbols
    }
    bars["600001.SH"]["2026-01-06"].update(low=future_low, close=future_close, high=max(11.0, future_close))
    if flat_exit:
        bars["600001.SH"]["2026-01-08"].update(open=10, close=10, high=10, low=10)
    inventory = [{"as_of_date": d, "symbol": s, "rank": i + 1} for d in calendar[:1] for i, s in enumerate(symbols)]
    return replay_reserved_daily_orders(
        calendar=calendar,
        decisions=inventory,
        bars=bars,
        initial_cash=10000,
        decision_nav_fraction=1,
        hold_sessions=2,
        max_symbol_nav=1,
        max_signal_price=200,
        lot_size=100,
        buy_cost=0.002,
        sell_cost=0.0025,
    )


def test_future_prices_do_not_change_reserved_shares_or_cash():
    first = run_fixture(future_low=9, future_close=10)
    changed = run_fixture(future_low=11, future_close=12)

    def plans(result):
        return [r for r in result["ledger"] if r["action"] == "plan"]

    assert plans(first) == plans(changed)
    assert first["summary"]["order_counts"]["buy"] == 1
    assert changed["summary"]["order_counts"]["cancel"] == 1
    assert changed["summary"]["final_nav"] == 10000


def test_reserved_cash_cannot_be_spent_twice_and_costs_reconcile():
    result = run_fixture(second_symbol=True)
    buys = [r for r in result["ledger"] if r["action"] == "buy"]
    assert len(buys) == 1 and buys[0]["shares"] == 900
    assert result["summary"]["final_nav"] == pytest.approx(10000 - 9000 * 0.0045)
    for row in result["nav_rows"]:
        assert row["cash"] >= 0
        assert row["nav"] == pytest.approx(row["cash"] + row["reserved_cash"] + row["invested"])


def test_flat_exit_cannot_be_counted_as_fill_and_is_delayed():
    result = run_fixture(flat_exit=True)
    exits = [r for r in result["ledger"] if r["action"] == "sell"]
    assert exits[0]["day"] == "2026-01-09"
    assert exits[0]["holding_sessions"] == 3
    assert result["summary"]["order_counts"]["defer_exit"] == 1


def test_cent_rounding_and_board_lots_are_fixed_at_decision():
    order = reserve_limit_order(
        symbol="600001.SH", signal_day="2026-01-05", limit=9.999, budget=10000, cash=10000, buy_cost=0.002, lot_size=100
    )
    assert order["limit"] == 9.99
    assert order["shares"] == 900
    assert order["reserved_cash"] <= 10000
