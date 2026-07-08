from __future__ import annotations

from ashare_evidence.capacity_underfilled_fallback_preflight import _adjust_underfilled_date_return


def test_underfilled_fallback_keeps_partial_original_fill_before_using_candidate() -> None:
    selected_rows = [
        {
            "symbol": "LOW",
            "rank": 1,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 2.0,
            "avg_amount_20d": 1_000_000.0,
            "net_excess_return": 0.50,
        },
        {
            "symbol": "HIGH",
            "rank": 2,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 0.0,
            "avg_amount_20d": 100_000_000.0,
            "net_excess_return": 0.01,
        },
    ]
    fallback_candidates = [
        {
            "symbol": "LIQUID",
            "name": "liquid fallback",
            "future_excess_return_20d": 0.20,
            "avg_amount_20d": 20_000_000.0,
            "max_fill_weight": 1.0,
            "model_score": 2.0,
        }
    ]

    adjusted = _adjust_underfilled_date_return(
        selected_rows,
        fallback_candidates=fallback_candidates,
        selected_top_k=2,
        portfolio_notional_cny=1_000_000.0,
        max_adv_participation_rate=0.05,
    )

    assert adjusted["underfilled_rows"][0]["filled_weight"] == 0.05
    assert adjusted["underfilled_rows"][0]["residual_weight"] == 0.95
    assert adjusted["fallback_rows"][0]["symbol"] == "LIQUID"
    assert adjusted["fallback_rows"][0]["filled_weight"] == 0.95
    assert adjusted["adjusted_net_excess_return"] == 0.05 * 0.50 + 0.95 * 0.20
