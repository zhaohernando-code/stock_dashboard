from __future__ import annotations

import copy

from ashare_evidence.stock_transition_sleeve import (
    _risk_budget_gate,
    build_blended_nav_account,
    select_stock_transition_candidate,
    stock_transition_features,
)


def test_stock_transition_features_ignore_future_bars() -> None:
    rows = [
        {"day": f"2026-01-{index:02d}", "close": 10.0 + index}
        for index in range(1, 10)
    ]
    bars = {"600001.SH": rows}
    before = stock_transition_features(
        symbol="600001.SH", signal_day="2026-01-07", market_bars_by_symbol=bars
    )
    changed = copy.deepcopy(bars)
    changed["600001.SH"][-1]["close"] = 1000.0
    after = stock_transition_features(
        symbol="600001.SH", signal_day="2026-01-07", market_bars_by_symbol=changed
    )

    assert before == after


def test_transition_candidate_excludes_v3_top3_and_future_result_fields() -> None:
    day = "2026-01-07"
    bars = {
        symbol: [
            {"day": f"2026-01-{index:02d}", "close": 10.0 + index**2 + offset}
            for index in range(1, 8)
        ]
        for offset, symbol in enumerate(("A", "B", "C", "D", "E"))
    }
    top3 = [
        {"as_of_date": day, "symbol": symbol, "rank": rank, "score": 3.0 - rank / 10}
        for rank, symbol in enumerate(("A", "B", "C"), start=1)
    ]
    inventory = [
        {
            "as_of_date": day,
            "symbol": symbol,
            "rank": rank,
            "score": 3.0 - rank / 10,
            "industry_name": "银行",
            "amount_10d_vs_20d_percentile": 0.5 + rank / 100,
            "net_excess_return": 9.9,
            "weighted_net_excess_return": 9.9,
            "_trade_eligibility_snapshot": {"eligible_before_scoring": True},
        }
        for rank, symbol in enumerate(("A", "B", "C", "D", "E"), start=1)
    ]
    selected, audit = select_stock_transition_candidate(
        signal_day=day,
        inventory=inventory,
        original_top3=top3,
        sector_state={"by_sector_name": {"银行": {"relative_5d": 0.1, "relative_20d": 0.0}}},
        market_bars_by_symbol=bars,
    )

    assert selected is not None
    assert selected["symbol"] in {"D", "E"}
    assert "net_excess_return" not in selected
    assert "weighted_net_excess_return" not in selected
    assert selected["rank"] == 1
    assert audit["qualified_candidate_count"] == 2


def test_sector_confirmation_cannot_create_candidate_without_stock_transition() -> None:
    day = "2026-01-07"
    falling = [
        {"day": f"2026-01-{index:02d}", "close": 20.0 - index}
        for index in range(1, 8)
    ]
    row = {
        "as_of_date": day,
        "symbol": "D",
        "rank": 4,
        "score": 2.0,
        "industry_name": "银行",
        "amount_10d_vs_20d_percentile": 0.9,
        "_trade_eligibility_snapshot": {"eligible_before_scoring": True},
    }
    selected, audit = select_stock_transition_candidate(
        signal_day=day,
        inventory=[row],
        original_top3=[],
        sector_state={"by_sector_name": {"银行": {"relative_5d": 1.0, "relative_20d": -1.0}}},
        market_bars_by_symbol={"D": falling},
    )

    assert selected is None
    assert audit["rejection_counts"]["stock_transition_not_ready"] == 1


def test_blended_nav_lambda_zero_is_exact_and_weight_is_bounded() -> None:
    baseline = {
        "summary": {"initial_cash_cny": 100.0},
        "nav_rows": [
            {"day": "2026-01-01", "nav_cny": 100.0, "invested_ratio": 0.8,
             "max_single_symbol_exposure_pct": 0.2},
            {"day": "2026-01-02", "nav_cny": 110.0, "invested_ratio": 0.8,
             "max_single_symbol_exposure_pct": 0.2},
        ],
        "order_ledger": [],
        "monthly_returns": [],
    }
    sleeve = {
        "summary": {"initial_cash_cny": 100.0},
        "nav_rows": [
            {"day": "2026-01-01", "nav_cny": 100.0, "invested_ratio": 0.5,
             "max_single_symbol_exposure_pct": 0.25},
            {"day": "2026-01-02", "nav_cny": 120.0, "invested_ratio": 0.5,
             "max_single_symbol_exposure_pct": 0.25},
        ],
    }

    assert build_blended_nav_account(baseline, sleeve, weight=0.0) == baseline
    blended = build_blended_nav_account(baseline, sleeve, weight=0.1)
    assert abs(blended["nav_rows"][-1]["nav_cny"] - 111.0) < 1e-12
    assert blended["nav_rows"][-1]["max_single_symbol_exposure_pct"] <= 0.25


def test_risk_budget_gate_enforces_return_and_bounded_risk_tolerances() -> None:
    baseline = {
        "total_return": 0.10,
        "annualized_return": 0.10,
        "max_drawdown": -0.05,
        "negative_month_count": 1,
        "worst_monthly_return": -0.02,
        "skipped_order_rate": 0.10,
        "skipped_signal_rate": 0.10,
        "max_single_symbol_exposure_pct": 0.24,
    }
    candidate = {
        **baseline,
        "total_return": 0.11,
        "annualized_return": 0.11,
        "max_drawdown": -0.054,
        "max_single_symbol_exposure_pct": 0.25,
    }
    assert _risk_budget_gate(candidate, baseline)["passed"]
    candidate["max_drawdown"] = -0.056
    assert _risk_budget_gate(candidate, baseline)["failed_metrics"] == ["max_drawdown"]
