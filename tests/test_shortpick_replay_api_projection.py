from __future__ import annotations

from ashare_evidence.api import _slim_shortpick_strategy_slice_evidence


def test_strategy_slice_response_projection_keeps_ui_fields_and_drops_heavy_detail() -> None:
    payload = {
        "experiment": "shortpick_strategy_slice_evidence",
        "status": "ready",
        "data_scope": {"signal_day_count": 717},
        "sample_adequacy": {"status": "broad_enough_for_controls"},
        "artifact_path": "output/shortpick-strategy-slice-evidence.json",
        "overall_strategy_rows": [{"strategy": "low_turnover"}],
        "regime_winner_rows": [{"regime": "up"}],
        "regime_coverage_rows": [{"regime": "up", "month_count": 3}],
        "period_strategy_rows": [{"heavy": True}],
        "regime_strategy_rows": [{"heavy": True}],
        "portfolio_confidence_intervals": {
            "status": "ready",
            "method": "bootstrap",
            "rows": [{"strategy": "low_turnover", "ci_lower": 0.01}],
            "raw_samples": [{"heavy": True}],
        },
        "portfolio_stability": {
            "status": "ready",
            "period_summary_rows": [{"period_kind": "month"}],
            "time_slices": [{"heavy": True}],
            "market_regime": {
                "status": "ready",
                "basis": "monthly_index_proxy",
                "rows": [{"heavy": True}],
            },
        },
        "portfolio_return_attribution": {
            "status": "ready",
            "rows": [{"strategy": "low_turnover"}],
            "symbol_industry": {"status": "missing_artifact", "reason": "trades_sample only"},
            "raw_trades": [{"heavy": True}],
        },
        "portfolio_forward_tracking_alignment": {"status": "insufficient_forward_sample"},
    }

    slim = _slim_shortpick_strategy_slice_evidence(payload)

    assert slim["data_scope"] == {"signal_day_count": 717}
    assert slim["overall_strategy_rows"] == [{"strategy": "low_turnover"}]
    assert slim["regime_winner_rows"] == [{"regime": "up"}]
    assert slim["regime_coverage_rows"] == [{"regime": "up", "month_count": 3}]
    assert slim["portfolio_forward_tracking_alignment"] == {"status": "insufficient_forward_sample"}
    assert slim["portfolio_confidence_intervals"] == {
        "status": "ready",
        "method": "bootstrap",
        "rows": [{"strategy": "low_turnover", "ci_lower": 0.01}],
    }
    assert slim["portfolio_stability"] == {
        "status": "ready",
        "period_summary_rows": [{"period_kind": "month"}],
        "market_regime": {"status": "ready", "basis": "monthly_index_proxy"},
    }
    assert slim["portfolio_return_attribution"] == {
        "status": "ready",
        "rows": [{"strategy": "low_turnover"}],
        "symbol_industry": {"status": "missing_artifact", "reason": "trades_sample only"},
    }
    assert "period_strategy_rows" not in slim
    assert "regime_strategy_rows" not in slim
    assert "time_slices" not in slim["portfolio_stability"]
    assert "raw_trades" not in slim["portfolio_return_attribution"]
