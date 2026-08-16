from __future__ import annotations

from ashare_evidence.v3_rebound_exact_overlay import build_exact_v3_overlay_pick


def test_exact_overlay_pick_preserves_recipe_and_removes_future_results() -> None:
    source = {
        "as_of_date": "2026-01-07",
        "symbol": "600001.SH",
        "stock_name": "示例",
        "rank": 2,
        "score": 3.0,
        "portfolio_weight": 0.91,
        "rank_weight_multiplier": 18.2,
        "target_horizon_days": 20,
        "net_excess_return": 1.0,
        "weighted_net_excess_return": 1.0,
    }
    overlay = build_exact_v3_overlay_pick(source)

    assert overlay == {
        key: value
        for key, value in source.items()
        if key not in {"net_excess_return", "weighted_net_excess_return"}
    }
