from __future__ import annotations

from ashare_evidence.v3_rebound_timing_overlay import build_rebound_rank1_overlay_pick


def test_overlay_pick_preserves_v3_identity_and_removes_future_results() -> None:
    source = {
        "as_of_date": "2026-01-07",
        "symbol": "600001.SH",
        "stock_name": "示例",
        "rank": 1,
        "score": 3.0,
        "portfolio_weight": 9.0,
        "rank_weight_multiplier": 18.2,
        "target_horizon_days": 20,
        "net_excess_return": 1.0,
        "weighted_net_excess_return": 1.0,
    }
    overlay = build_rebound_rank1_overlay_pick(source)

    assert overlay["symbol"] == source["symbol"]
    assert overlay["score"] == source["score"]
    assert overlay["rank"] == 1
    assert overlay["portfolio_weight"] == 1.0
    assert overlay["rank_weight_multiplier"] == 1.0
    assert overlay["target_horizon_days"] == 10
    assert "net_excess_return" not in overlay
    assert "weighted_net_excess_return" not in overlay
