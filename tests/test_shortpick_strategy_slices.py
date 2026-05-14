from datetime import date, timedelta

from ashare_evidence.shortpick_strategy_slices import (
    _portfolio_confidence_intervals,
    _portfolio_return_attribution,
    _regime_winner_rows,
    _sample_adequacy,
)


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


def test_portfolio_confidence_intervals_are_strategy_portfolio_scoped():
    period_rows = [
        {
            "entry_price_source": "next_close",
            "strategy": "low_turnover_20d_uptrend_liquid_top120",
            "label": "低换手上升趋势",
            "period_kind": "month",
            "period": f"2025-{month:02d}",
            "excess_return": 0.01 + month / 1000,
        }
        for month in range(1, 7)
    ]

    payload = _portfolio_confidence_intervals(period_rows)

    assert payload["status"] == "ready"
    assert payload["basis"] == "full_window_staged_portfolio_monthly_excess"
    assert payload["rows"][0]["entry_price_source"] == "next_close"
    assert payload["rows"][0]["strategy"] == "low_turnover_20d_uptrend_liquid_top120"
    assert payload["rows"][0]["sample_period_count"] == 6
    assert payload["rows"][0]["lower_bound_positive"] is True


def test_portfolio_return_attribution_refuses_trades_sample_industry_extrapolation():
    period_rows = [
        {
            "entry_price_source": "next_close",
            "strategy": "low_turnover_20d_uptrend_liquid_top120",
            "label": "低换手上升趋势",
            "period_kind": "month",
            "period": "2025-01",
            "return": 0.03,
            "benchmark_return": 0.01,
            "excess_return": 0.02,
        },
        {
            "entry_price_source": "next_close",
            "strategy": "low_turnover_20d_uptrend_liquid_top120",
            "label": "低换手上升趋势",
            "period_kind": "month",
            "period": "2025-02",
            "return": -0.01,
            "benchmark_return": 0.01,
            "excess_return": -0.02,
        },
    ]
    regime_rows = [
        {
            "entry_price_source": "next_close",
            "strategy": "low_turnover_20d_uptrend_liquid_top120",
            "market_regime_tag": "range_bound:low_volatility:balanced_size",
            "periods": ["2025-01"],
            "mean_net_excess_return": 0.02,
        }
    ]

    payload = _portfolio_return_attribution(period_rows, regime_rows)

    assert payload["status"] == "ready"
    assert payload["rows"][0]["best_month"] == "2025-01"
    assert payload["rows"][0]["drop_best_regime_mean_excess_return"] == -0.02
    assert payload["symbol_industry"]["status"] == "missing_artifact"
    assert "不用 trades_sample 外推" in payload["symbol_industry"]["reason"]
