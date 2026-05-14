from datetime import date, timedelta

from ashare_evidence.shortpick_strategy_slices import _regime_winner_rows, _sample_adequacy


def test_strategy_slice_sample_adequacy_marks_broad_window_ready():
    signal_days = [date(2023, 4, 13) + timedelta(days=index) for index in range(760)]
    coverage = [
        {"market_regime_tag": f"regime_{index}", "signal_day_count": 25}
        for index in range(4)
    ]

    payload = _sample_adequacy(
        signal_days=signal_days,
        regime_coverage_rows=coverage,
        min_regime_trade_count=30,
    )

    assert payload["status"] == "ready"
    assert payload["broad_window_ready"] is True
    assert payload["regime_slice_ready"] is True


def test_strategy_slice_regime_winner_keeps_frozen_rank_separate():
    rows = [
        {
            "entry_price_source": "next_close",
            "market_regime_tag": "range_bound:normal_volatility:balanced_size",
            "strategy": "base",
            "label": "基础动量",
            "trade_count": 50,
            "mean_net_return": 0.02,
            "mean_net_excess_return": 0.03,
            "positive_net_excess_rate": 0.6,
        },
        {
            "entry_price_source": "next_close",
            "market_regime_tag": "range_bound:normal_volatility:balanced_size",
            "strategy": "low_turnover_20d_uptrend_liquid_top120",
            "label": "低换手上升趋势",
            "trade_count": 80,
            "mean_net_return": 0.01,
            "mean_net_excess_return": 0.02,
            "positive_net_excess_rate": 0.55,
        },
    ]

    winners = _regime_winner_rows(rows, min_trade_count=30)

    assert winners[0]["winner_strategy"] == "base"
    assert winners[0]["frozen_rank"] == 2
    assert winners[0]["frozen_is_winner"] is False
