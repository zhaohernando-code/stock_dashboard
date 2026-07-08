from __future__ import annotations

from ashare_evidence.order_level_capacity_proxy import (
    build_capacity_contract_tier_scan,
    build_capacity_soft_rerank_proxy,
    build_exposure_floor_stability_proxy,
    build_order_level_capacity_proxy,
)


def test_order_level_capacity_proxy_matches_full_fill_when_capacity_is_sufficient() -> None:
    selected_picks = [
        {
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.09,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 10.0,
        },
        {
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.03,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.7,
        },
    ]

    proxy = build_order_level_capacity_proxy(selected_picks, selected_top_k=2)

    baseline = proxy["baseline_full_fill_reference"]
    cash_mode = proxy["mode_summaries"][0]
    assert cash_mode["mode"] == "adv_cap_cash"
    assert cash_mode["base_underfilled_pick_count"] == 0
    assert cash_mode["mean_daily_net_excess_return"] == baseline["mean_daily_net_excess_return"]
    assert cash_mode["horizon_normalized_total_return_proxy"] == baseline["horizon_normalized_total_return_proxy"]
    assert proxy["non_degrading_modes"][0]["mode"] == "adv_cap_cash"


def test_capacity_contract_tier_scan_identifies_supported_notional_limit() -> None:
    selected_picks = [
        {
            "symbol": "LOW",
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.20,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 2_400_000.0,
            "score": 10.0,
        },
        {
            "symbol": "HIGH",
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.03,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.0,
        },
    ]

    scan = build_capacity_contract_tier_scan(
        selected_picks,
        selected_top_k=2,
        notional_tiers_cny=(100_000.0, 240_000.0, 1_000_000.0),
    )

    assert scan["artifact_type"] == "capacity_contract_tier_scan"
    assert scan["full_fill_notional_limit_cny"] == 240_000.0
    assert scan["first_scanned_full_fill_tier_cny"] == 100_000.0
    by_tier = {row["portfolio_notional_cny"]: row for row in scan["tier_summaries"]}
    assert by_tier[100_000.0]["underfilled_pick_count"] == 0
    assert by_tier[240_000.0]["underfilled_pick_count"] == 0
    assert by_tier[1_000_000.0]["underfilled_pick_count"] == 1
    assert by_tier[1_000_000.0]["min_fill_rate"] == 0.24
    assert scan["binding_picks_at_largest_tier"][0]["symbol"] == "LOW"


def test_order_level_capacity_proxy_leaves_unfilled_capital_as_cash() -> None:
    selected_picks = [
        {
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.12,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 1_000_000.0,
            "score": 10.0,
        },
        {
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.04,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.0,
        },
    ]

    proxy = build_order_level_capacity_proxy(selected_picks, selected_top_k=2)

    cash_mode = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_cash")
    redistribute = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_rank_redistribute")
    assert cash_mode["base_underfilled_pick_count"] == 1
    assert cash_mode["mean_daily_net_excess_return"] < proxy["baseline_full_fill_reference"]["mean_daily_net_excess_return"]
    assert redistribute["mean_daily_net_excess_return"] > cash_mode["mean_daily_net_excess_return"]
    assert redistribute["mean_final_capital_weight"] > cash_mode["mean_final_capital_weight"]


def test_order_level_capacity_proxy_can_try_ranked_top5_substitute() -> None:
    selected_picks = [
        {
            "symbol": "A",
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.12,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 1_000_000.0,
            "score": 10.0,
        },
        {
            "symbol": "B",
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.04,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.7,
        },
    ]
    top_candidates = [
        *selected_picks,
        {
            "symbol": "C",
            "as_of_date": "2026-01-02",
            "rank": 3,
            "net_excess_return": 0.08,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 8.0,
        },
    ]

    proxy = build_order_level_capacity_proxy(
        selected_picks,
        selected_top_k=2,
        top_candidate_picks=top_candidates,
    )

    substitute = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_top5_substitute")
    cash_mode = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_cash")
    assert substitute["substituted_pick_count"] == 1
    assert substitute["mean_daily_net_excess_return"] > cash_mode["mean_daily_net_excess_return"]
    assert proxy["top_candidate_pick_count"] == 3


def test_order_level_capacity_proxy_can_fill_residual_after_partial_low_adv_order() -> None:
    selected_picks = [
        {
            "symbol": "A",
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.12,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 1_000_000.0,
            "score": 10.0,
        },
        {
            "symbol": "B",
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.04,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.7,
        },
    ]
    top_candidates = [
        *selected_picks,
        {
            "symbol": "C",
            "as_of_date": "2026-01-02",
            "rank": 3,
            "net_excess_return": 0.08,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 8.0,
        },
    ]

    proxy = build_order_level_capacity_proxy(
        selected_picks,
        selected_top_k=2,
        top_candidate_picks=top_candidates,
    )

    residual = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_residual_top5_fill")
    substitute = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_top5_substitute")
    cash_mode = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_cash")
    assert residual["substituted_pick_count"] == 1
    assert residual["mean_cash_weight"] == 0.0
    assert residual["mean_daily_net_excess_return"] > cash_mode["mean_daily_net_excess_return"]
    assert residual["mean_daily_net_excess_return"] > substitute["mean_daily_net_excess_return"]


def test_order_level_capacity_proxy_can_select_capacity_aware_topn_before_ordering() -> None:
    selected_picks = [
        {
            "symbol": "A",
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.12,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 1_000_000.0,
            "score": 10.0,
        },
        {
            "symbol": "B",
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.04,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.0,
        },
    ]
    top_candidates = [
        *selected_picks,
        {
            "symbol": "C",
            "as_of_date": "2026-01-02",
            "rank": 3,
            "net_excess_return": 0.08,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 8.0,
        },
    ]

    proxy = build_order_level_capacity_proxy(
        selected_picks,
        selected_top_k=2,
        top_candidate_picks=top_candidates,
    )

    selection = next(
        row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_topn_capacity_aware_selection"
    )
    cash_mode = next(row for row in proxy["mode_summaries"] if row["mode"] == "adv_cap_cash")
    assert selection["substituted_pick_count"] == 2
    assert selection["mean_cash_weight"] == 0.0
    assert selection["mean_daily_net_excess_return"] > cash_mode["mean_daily_net_excess_return"]


def test_capacity_soft_rerank_proxy_scans_liquidity_weight_without_order_rows() -> None:
    selected_picks = [
        {
            "symbol": "A",
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.12,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 1_000_000.0,
            "score": 10.0,
        },
        {
            "symbol": "B",
            "as_of_date": "2026-01-02",
            "rank": 2,
            "net_excess_return": 0.04,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.7,
        },
    ]
    top_candidates = [
        *selected_picks,
        {
            "symbol": "C",
            "as_of_date": "2026-01-02",
            "rank": 3,
            "net_excess_return": 0.13,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
            "score": 9.9,
        },
    ]

    proxy = build_capacity_soft_rerank_proxy(
        selected_picks,
        selected_top_k=2,
        top_candidate_picks=top_candidates,
        liquidity_weights=(0.4,),
    )

    scan = proxy["scan_summaries"][0]
    assert proxy["artifact_type"] == "capacity_soft_rerank_proxy"
    assert "daily_rows" not in scan
    assert scan["changed_pick_count"] == 1
    assert scan["base_underfilled_pick_count"] == 0
    assert scan["mean_daily_net_excess_return"] > proxy["baseline_full_fill_reference"]["mean_daily_net_excess_return"]
    assert proxy["non_degrading_scans"][0]["liquidity_weight"] == 0.4


def test_exposure_floor_stability_proxy_gates_low_exposure_dates() -> None:
    selected_returns_by_date = [
        {
            "as_of_date": "2026-01-02",
            "month": "2026-01",
            "mean_net_excess_return": -0.05,
            "gross_exposure": 0.1,
            "pick_count": 1,
        },
        {
            "as_of_date": "2026-01-03",
            "month": "2026-01",
            "mean_net_excess_return": 0.08,
            "gross_exposure": 0.8,
            "pick_count": 2,
        },
        {
            "as_of_date": "2026-01-04",
            "month": "2026-01",
            "mean_net_excess_return": 0.0,
            "gross_exposure": 0.0,
            "pick_count": 0,
        },
    ]

    proxy = build_exposure_floor_stability_proxy(
        selected_returns_by_date,
        floor_quantiles=(1.0,),
        overlay_modes=("cash_floor",),
    )

    scan = proxy["scan_summaries"][0]
    assert proxy["artifact_type"] == "exposure_floor_stability_proxy"
    assert scan["mode"] == "gross_exposure_cash_floor_overlay"
    assert scan["gross_exposure_floor"] == 0.8
    assert scan["gated_active_date_count"] == 1
    assert scan["mean_daily_net_excess_return"] > proxy["baseline_full_exposure_reference"]["mean_daily_net_excess_return"]
    assert proxy["non_degrading_scans"][0]["gross_exposure_floor"] == 0.8
    assert "daily_rows" not in scan


def test_exposure_floor_stability_proxy_can_scale_without_reducing_positive_date_rate() -> None:
    selected_returns_by_date = [
        {
            "as_of_date": "2026-01-02",
            "month": "2026-01",
            "mean_net_excess_return": -0.05,
            "gross_exposure": 0.1,
            "pick_count": 1,
        },
        {
            "as_of_date": "2026-01-03",
            "month": "2026-01",
            "mean_net_excess_return": 0.08,
            "gross_exposure": 0.8,
            "pick_count": 2,
        },
        {
            "as_of_date": "2026-01-04",
            "month": "2026-01",
            "mean_net_excess_return": 0.01,
            "gross_exposure": 0.1,
            "pick_count": 1,
        },
    ]

    proxy = build_exposure_floor_stability_proxy(
        selected_returns_by_date,
        floor_quantiles=(1.0,),
        overlay_modes=("linear_scale",),
    )

    scan = proxy["scan_summaries"][0]
    baseline = proxy["baseline_full_exposure_reference"]
    assert scan["mode"] == "gross_exposure_linear_scale_overlay"
    assert scan["low_exposure_active_date_count"] == 2
    assert scan["gated_active_date_count"] == 0
    assert scan["positive_date_rate"] == baseline["positive_date_rate"]
    assert scan["mean_daily_net_excess_return"] > baseline["mean_daily_net_excess_return"]
    assert proxy["non_degrading_scans"][0]["mode"] == "gross_exposure_linear_scale_overlay"
    assert "mean_daily_net_excess_return" in proxy["non_degrading_scans"][0]
    assert "horizon_normalized_annualized_return_proxy" in proxy["non_degrading_scans"][0]
    assert "path_drawdown_sum" in proxy["non_degrading_scans"][0]


def test_order_level_capacity_proxy_rejects_unknown_mode() -> None:
    selected_picks = [
        {
            "as_of_date": "2026-01-02",
            "rank": 1,
            "net_excess_return": 0.01,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 20_000_000.0,
        }
    ]

    try:
        build_order_level_capacity_proxy(selected_picks, selected_top_k=1, modes=("unknown",))
    except ValueError as exc:
        assert "unsupported order-level capacity proxy mode" in str(exc)
    else:
        raise AssertionError("unknown mode should fail")
