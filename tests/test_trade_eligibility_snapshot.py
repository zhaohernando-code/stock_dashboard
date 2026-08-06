from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ashare_evidence.market_rules import (
    ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    account_trade_eligibility,
    build_trade_eligibility_snapshot,
    summarize_trade_eligibility_snapshots,
)
from ashare_evidence.shortpick_market_factor_study import _Bar, _build_strategy_selections, _Series


def _snapshot(symbol: str, price: float, *, observed_at: datetime | None = None) -> dict:
    return build_trade_eligibility_snapshot(
        symbol,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        as_of=date(2026, 8, 6),
        decision_cutoff=datetime(2026, 8, 6, 15, 0, tzinfo=UTC),
        price_cny=price,
        price_observed_at=observed_at or datetime(2026, 8, 6, 15, 0, tzinfo=UTC),
        price_source="test_unadjusted_close",
        price_adjustment="unadjusted",
        profile_is_point_in_time=True,
    )


def test_conservative_profile_allows_main_a_share_at_200_cny() -> None:
    snapshot = _snapshot("600519.SH", 200.0)

    assert snapshot["eligible_before_scoring"] is True
    assert snapshot["exclusion_reason_codes"] == []
    assert snapshot["price"]["maximum_cny"] == 200.0


def test_price_over_200_is_excluded_before_scoring() -> None:
    snapshot = _snapshot("600519.SH", 200.01)

    assert snapshot["eligible_before_scoring"] is False
    assert snapshot["exclusion_reason_codes"] == ["price_above_profile_maximum"]


def test_non_a_share_and_permission_boards_are_explicitly_excluded() -> None:
    assert "non_a_share_security" in _snapshot("900901.SH", 1.0)["exclusion_reason_codes"]
    assert "account_board_permission_required" in _snapshot("688981.SH", 50.0)["exclusion_reason_codes"]
    assert "account_board_permission_required" in _snapshot("300750.SZ", 150.0)["exclusion_reason_codes"]
    assert "account_board_permission_required" in _snapshot("920001.BJ", 10.0)["exclusion_reason_codes"]


def test_future_or_adjusted_price_is_not_pit_safe() -> None:
    snapshot = build_trade_eligibility_snapshot(
        "600519.SH",
        as_of=date(2026, 8, 6),
        decision_cutoff=datetime(2026, 8, 6, 15, 0, tzinfo=UTC),
        price_cny=100.0,
        price_observed_at=datetime(2026, 8, 7, 15, 0, tzinfo=UTC),
        price_source="test_adjusted_close",
        price_adjustment="forward_adjusted",
    )

    assert snapshot["eligible_before_scoring"] is False
    assert set(snapshot["exclusion_reason_codes"]) == {
        "price_adjustment_not_unadjusted",
        "price_not_available_at_decision_cutoff",
    }


def test_historical_profile_does_not_use_current_st_name() -> None:
    eligibility = account_trade_eligibility(
        "600000.SH",
        stock_profile={"name": "*ST当前名称", "status": "delisted"},
        as_of=date(2020, 1, 2),
        profile_is_point_in_time=False,
    )

    assert eligibility["tradable"] is True
    assert eligibility["board"] == "main"
    assert eligibility["pit_risk_status_verified"] is False


def test_snapshot_summary_records_each_exclusion_reason_type() -> None:
    summary = summarize_trade_eligibility_snapshots(
        [_snapshot("600519.SH", 200.01), _snapshot("688981.SH", 50.0), _snapshot("600000.SH", 10.0)]
    )

    assert summary["evaluated_count"] == 3
    assert summary["eligible_before_scoring_count"] == 1
    assert summary["exclusion_reason_counts"] == {
        "account_board_permission_required": 1,
        "price_above_profile_maximum": 1,
    }


def test_historical_strategy_excludes_over_200_before_pool_sort_and_rank() -> None:
    start = date(2026, 6, 1)

    def series(symbol: str, close: float) -> _Series:
        bars = [
            _Bar(
                day=start + timedelta(days=index),
                open=close,
                high=close,
                low=close,
                close=close,
                amount=100_000_000.0 + index,
                turnover=1.0,
            )
            for index in range(23)
        ]
        return _Series(
            symbol=symbol,
            name=symbol,
            industry="test",
            bars=bars,
            by_day={bar.day: index for index, bar in enumerate(bars)},
        )

    signal_day = start + timedelta(days=20)
    snapshots: list[dict] = []
    selections = _build_strategy_selections(
        {
            "600000.SH": series("600000.SH", 100.0),
            "600001.SH": series("600001.SH", 201.0),
        },
        signal_days=[signal_day],
        strategy="base",
        pool_limit=40,
        rank_limit=6,
        eligibility_snapshots=snapshots,
    )

    assert selections[signal_day] == ["600000.SH"]
    assert summarize_trade_eligibility_snapshots(snapshots)["exclusion_reason_counts"] == {
        "price_above_profile_maximum": 1
    }
