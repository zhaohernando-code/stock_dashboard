from __future__ import annotations

from datetime import UTC, datetime

from ashare_evidence.rolling_tranche_execution_contract import (
    build_shortpick_v3_rolling_tranche_execution_contract,
)


def test_shortpick_v3_rolling_contract_rejects_monthly_full_rotation() -> None:
    contract = build_shortpick_v3_rolling_tranche_execution_contract(
        generated_at=datetime(2026, 7, 8, tzinfo=UTC)
    )

    assert contract["artifact_type"] == "shortpick_v3_rolling_tranche_execution_contract"
    assert contract["status"] == "contract_ready_replay_not_yet_run"
    assert contract["account_profile"]["initial_cash_cny"] == 200_000.0
    assert contract["hard_constraints"]["execution_mode"] == "rolling_tranche_only"
    assert contract["forbidden_execution_modes"][0]["mode"] == "monthly_full_capital_rotation"
    assert contract["hard_constraints"]["same_cash_redeployment_across_overlapping_holds_allowed"] is False
    assert contract["hard_constraints"]["min_order_notional_cny"] == 4_000.0


def test_shortpick_v3_rolling_contract_bounds_single_signal_budget() -> None:
    contract = build_shortpick_v3_rolling_tranche_execution_contract()

    configs = {row["config_id"]: row for row in contract["candidate_configurations"]}
    assert configs["daily_20_tranche_rank_weighted_v1"]["per_signal_target_budget_cny"] == 10_000.0
    assert (
        configs["daily_14_tranche_rank_weighted_compound_min2500_v1"]["budget_mode"]
        == "current_nav_fraction"
    )
    assert configs["daily_14_tranche_rank_weighted_compound_min2500_v1"]["min_order_notional_cny"] == 2_500.0
    assert (
        configs["daily_14_tranche_rank_weighted_compound_min2250_rank3_pullback_late_trend_loss_guard_v1"][
            "exit_policy"
        ]
        == "rank3_entry_pullback_late_trend_loss_guard"
    )
    assert (
        configs["daily_14_tranche_rank_weighted_compound_min2250_rank3_pullback_late_trend_loss_guard_v1"][
            "min_order_notional_cny"
        ]
        == 2_250.0
    )
    assert (
        configs["daily_15_tranche_rank_weighted_compound_min1000_v1"]["budget_mode"]
        == "current_nav_fraction"
    )
    assert configs["daily_15_tranche_rank_weighted_compound_min1000_v1"]["min_order_notional_cny"] == 1_000.0
    assert (
        configs["daily_15_tranche_rank_weighted_compound_min1000_layered_rank1_quickfail_rank3_pullback_exit_v1"][
            "exit_policy"
        ]
        == "rank3_pullback_rank1_quick_fail_guard"
    )
    upstream_meta = configs[
        "daily_14_tranche_upstream_meta_signal_quality_min2250_weak100_strong165_lead135_low090_v1"
    ]
    assert upstream_meta["budget_mode"] == "current_nav_fraction"
    assert upstream_meta["target_active_tranche_count"] == 14
    assert upstream_meta["min_order_notional_cny"] == 2_250.0
    assert upstream_meta["exit_policy"] == "rank3_pullback_rank1_quick_fail_guard"
    assert upstream_meta["three_part_stability_overlay"]["weak_scale"] == 1.0
    assert upstream_meta["three_part_stability_overlay"]["strong_scale"] == 1.65
    assert upstream_meta["meta_signal_quality_overlay"]["industry_leadership_scale"] == 1.35
    assert upstream_meta["meta_signal_quality_overlay"]["low_quality_scale"] == 0.90
    assert configs["two_day_10_tranche_rank_weighted_v1"]["per_signal_target_budget_cny"] == 20_000.0
    assert configs["two_day_10_tranche_rank_weighted_offset1_v1"]["per_signal_target_budget_cny"] == 20_000.0
    assert configs["two_day_10_tranche_rank_weighted_offset1_v1"]["signal_cadence_offset_trade_days"] == 1
    assert configs["weekly_4_tranche_rank_weighted_v1"]["per_signal_target_budget_cny"] == 50_000.0
    assert all(row["per_signal_target_budget_pct"] <= 0.25 for row in configs.values())
    assert contract["promotion_gate"]["must_report_account_level_total_return"] is True
    assert contract["promotion_gate"]["must_pass_leakage_audit"] is True
