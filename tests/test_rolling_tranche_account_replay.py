from __future__ import annotations

from datetime import date

from ashare_evidence.rolling_tranche_account_replay import (
    _Bar,
    _Position,
    _process_core_liquidity_substitution,
    build_shortpick_v3_rolling_account_replay_artifact,
    rank5_replacement_quality_rejection_reason,
)


def test_core_liquidity_substitution_sells_weak_ordinary_position_before_external_winner() -> None:
    winner = _Position(
        signal_day=date(2026, 1, 1),
        entry_day=date(2026, 1, 2),
        planned_exit_day=date(2026, 2, 2),
        symbol="WINNER",
        stock_name="WINNER",
        rank=1,
        shares=200,
        entry_price=10.0,
        cost_basis=2000.0,
        target_notional=2000.0,
        last_price=12.0,
        peak_price=12.0,
        entry_features={"pit_external_deferred_exit_day": "2026-02-02"},
    )
    loser = _Position(
        signal_day=date(2026, 1, 1),
        entry_day=date(2026, 1, 2),
        planned_exit_day=date(2026, 1, 20),
        symbol="LOSER",
        stock_name="LOSER",
        rank=2,
        shares=200,
        entry_price=10.0,
        cost_basis=2000.0,
        target_notional=2000.0,
        last_price=8.0,
        peak_price=10.0,
        entry_features={},
    )

    cash, rows, positions = _process_core_liquidity_substitution(
        date(2026, 1, 10),
        cash=0.0,
        required_entry_cash=1000.0,
        open_positions=[winner, loser],
        bars_by_symbol={"WINNER": [_Bar(date(2026, 1, 10), 12.0)], "LOSER": [_Bar(date(2026, 1, 10), 8.0)]},
        sell_cost_rate=0.0,
        board_lot_size=100,
    )

    assert cash == 1600.0
    assert rows[0]["symbol"] == "LOSER"
    assert rows[0]["reason"] == "pit_external_core_position_liquidity_substitution"
    assert [position.symbol for position in positions] == ["WINNER"]


def test_rolling_account_replay_uses_tranches_not_full_capital() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=1, multiplier=2.73),
                    _pick("2026-01-02", "BBB", rank=2, multiplier=0.27),
                    _pick("2026-01-05", "AAA", rank=1, multiplier=2.73),
                ],
            }
        ],
    }
    bars = {
        "AAA": [{"day": f"2026-01-{day:02d}", "close": 10.0 + day / 100} for day in range(2, 31)],
        "BBB": [{"day": f"2026-01-{day:02d}", "close": 10.0} for day in range(2, 31)],
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
    )

    daily = next(row for row in artifact["results"] if row["config_id"] == "daily_20_tranche_rank_weighted_v1")
    assert daily["summary"]["max_single_signal_deployment_pct"] == 0.05
    assert daily["summary"]["buy_order_count"] == 2
    assert daily["summary"]["skip_order_count"] == 1
    assert daily["reason_counts"]["below_min_order_notional"] == 1


def test_rolling_account_replay_rejects_price_too_high_slots() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=2.73)],
            }
        ],
    }
    bars = {"AAA": [{"day": f"2026-01-{day:02d}", "close": 200.0} for day in range(2, 31)]}

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
    )

    daily = next(row for row in artifact["results"] if row["config_id"] == "daily_20_tranche_rank_weighted_v1")
    assert daily["summary"]["buy_order_count"] == 0
    assert daily["reason_counts"]["price_too_high_for_slot"] == 1


def test_rolling_account_replay_enforces_shadow_baseline_buy_eligibility() -> None:
    pick = _pick("2026-01-02", "AAA", rank=1, multiplier=2.73)
    pick["shadow_baseline_buy_eligible"] = False
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [pick],
            }
        ],
    }
    bars = {"AAA": [{"day": f"2026-01-{day:02d}", "close": 10.0} for day in range(2, 31)]}

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
    )

    daily = next(row for row in artifact["results"] if row["config_id"] == "daily_20_tranche_rank_weighted_v1")
    assert daily["summary"]["buy_order_count"] == 0
    assert daily["reason_counts"]["shadow_baseline_not_buy_eligible"] == 1


def test_rolling_account_replay_enforces_shadow_actual_symbol_allowlist() -> None:
    pick = _pick("2026-01-02", "AAA", rank=1, multiplier=2.73)
    pick["shadow_baseline_buy_symbols"] = ["BBB"]
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [pick],
            }
        ],
    }
    bars = {"AAA": [{"day": f"2026-01-{day:02d}", "close": 10.0} for day in range(2, 31)]}

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
    )

    daily = next(row for row in artifact["results"] if row["config_id"] == "daily_20_tranche_rank_weighted_v1")
    assert daily["summary"]["buy_order_count"] == 0
    assert daily["reason_counts"]["shadow_baseline_not_buy_eligible"] == 1


def test_rolling_account_replay_treats_zero_weight_as_no_order_not_skip() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=3, multiplier=0.0)],
            }
        ],
    }
    bars = {"AAA": [{"day": f"2026-01-{day:02d}", "close": 10.0} for day in range(2, 31)]}

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
    )

    daily = next(row for row in artifact["results"] if row["config_id"] == "daily_20_tranche_rank_weighted_v1")
    assert daily["summary"]["buy_order_count"] == 0
    assert daily["summary"]["skip_order_count"] == 0
    assert daily["summary"]["no_order_count"] == 1
    assert daily["sample_orders"][0]["reason"] == "zero_target_allocation"


def test_rolling_account_replay_keeps_position_open_when_exit_bar_is_not_available() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=2.73)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-02", "close": 10.0},
            {"day": "2026-01-03", "close": 10.0},
            {"day": "2026-01-04", "close": 11.0},
        ]
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
    )

    daily = next(row for row in artifact["results"] if row["config_id"] == "daily_20_tranche_rank_weighted_v1")
    assert daily["summary"]["buy_order_count"] == 1
    assert daily["summary"]["sell_order_count"] == 0
    assert daily["summary"]["skip_order_count"] == 0
    assert daily["nav_tail"][-1]["open_position_count"] == 1


def test_rolling_account_replay_compound_budget_uses_current_nav() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=1, multiplier=2.73, horizon=1),
                    _pick("2026-01-04", "BBB", rank=1, multiplier=2.73, horizon=1),
                ],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-02", "close": 10.0},
            {"day": "2026-01-03", "close": 10.0},
            {"day": "2026-01-04", "close": 20.0},
            {"day": "2026-01-05", "close": 20.0},
        ],
        "BBB": [
            {"day": "2026-01-04", "close": 10.0},
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.0},
        ],
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    compound = next(
        row
        for row in artifact["results"]
        if row["config_id"] == "daily_14_tranche_rank_weighted_compound_min2500_v1"
    )
    buys = [row for row in compound["order_ledger"] if row["action"] == "buy"]
    assert len(buys) == 2
    assert buys[1]["target_notional_cny"] > buys[0]["target_notional_cny"]


def test_rolling_account_replay_dynamic_profit_guard_exits_before_horizon() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=2.73, horizon=20)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-02", "close": 10.0},
            {"day": "2026-01-03", "close": 10.0},
            {"day": "2026-01-04", "close": 12.0},
            {"day": "2026-01-05", "close": 10.9},
            *[{"day": f"2026-01-{day:02d}", "close": 11.0} for day in range(6, 31)],
        ]
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    dynamic = next(
        row
        for row in artifact["results"]
        if row["config_id"] == "daily_14_tranche_rank_weighted_compound_min2500_profit_guard_v1"
    )
    sells = [row for row in dynamic["order_ledger"] if row["action"] == "sell"]
    assert sells[0]["trade_day"] == "2026-01-05"
    assert sells[0]["reason"] == "dynamic_profit_guard_giveback"


def test_rolling_account_replay_late_trend_loss_guard_exits_after_confirmation() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=2.73, horizon=20)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-02", "close": 10.0},
            {"day": "2026-01-03", "close": 10.0},
            *[{"day": f"2026-01-{day:02d}", "close": 9.8} for day in range(4, 13)],
            {"day": "2026-01-13", "close": 8.9},
            *[{"day": f"2026-01-{day:02d}", "close": 8.8} for day in range(14, 31)],
        ]
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    dynamic = next(
        row
        for row in artifact["results"]
        if row["config_id"] == "daily_14_tranche_rank_weighted_compound_min2500_late_trend_loss_guard_v1"
    )
    sells = [row for row in dynamic["order_ledger"] if row["action"] == "sell"]
    assert sells[0]["trade_day"] == "2026-01-13"
    assert sells[0]["reason"] == "dynamic_late_trend_loss_guard"


def test_rolling_account_replay_rank23_late_trend_loss_guard_does_not_exit_rank1() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=2.73, horizon=20)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-02", "close": 10.0},
            {"day": "2026-01-03", "close": 10.0},
            *[{"day": f"2026-01-{day:02d}", "close": 8.8} for day in range(4, 31)],
        ]
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    dynamic = next(
        row
        for row in artifact["results"]
        if row["config_id"] == "daily_14_tranche_rank_weighted_compound_min2500_rank23_late_trend_loss_guard_v1"
    )
    sells = [row for row in dynamic["order_ledger"] if row["action"] == "sell"]
    assert sells[0]["reason"] == "mechanical_horizon"


def test_rolling_account_replay_feature_gated_exit_uses_entry_features() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [
                    _pick(
                        "2026-01-02",
                        "AAA",
                        rank=2,
                        multiplier=2.73,
                        horizon=20,
                        benchmark_return_20d=0.07,
                        distance_from_20d_high=-0.05,
                    ),
                    _pick(
                        "2026-01-02",
                        "BBB",
                        rank=2,
                        multiplier=2.73,
                        horizon=20,
                        benchmark_return_20d=0.02,
                        distance_from_20d_high=-0.05,
                    ),
                ],
            }
        ],
    }
    falling_bars = [
        {"day": "2026-01-02", "close": 10.0},
        {"day": "2026-01-03", "close": 10.0},
        *[{"day": f"2026-01-{day:02d}", "close": 8.8} for day in range(4, 31)],
    ]
    bars = {"AAA": falling_bars, "BBB": falling_bars}

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    dynamic = next(
        row
        for row in artifact["results"]
        if row["config_id"] == "daily_14_tranche_rank_weighted_compound_min2500_rank23_strong_benchmark_pullback_exit_v1"
    )
    sells = sorted(
        [row for row in dynamic["order_ledger"] if row["action"] == "sell"],
        key=lambda row: row["symbol"],
    )
    assert sells[0]["symbol"] == "AAA"
    assert sells[0]["reason"] == "dynamic_rank23_strong_benchmark_pullback_late_loss_guard"
    assert sells[1]["symbol"] == "BBB"
    assert sells[1]["reason"] == "mechanical_horizon"


def test_rolling_account_replay_rank3_pullback_guard_requires_entry_pullback() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=3, multiplier=2.73, horizon=20, distance_from_20d_high=-0.02),
                    _pick("2026-01-02", "BBB", rank=3, multiplier=2.73, horizon=20, distance_from_20d_high=0.0),
                ],
            }
        ],
    }
    falling_bars = [
        {"day": "2026-01-02", "close": 10.0},
        {"day": "2026-01-03", "close": 10.0},
        *[{"day": f"2026-01-{day:02d}", "close": 8.8} for day in range(4, 31)],
    ]

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol={"AAA": falling_bars, "BBB": falling_bars},
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    dynamic = next(
        row
        for row in artifact["results"]
        if row["config_id"] == "daily_14_tranche_rank_weighted_compound_min2500_rank3_pullback_late_trend_loss_guard_v1"
    )
    sells = sorted(
        [row for row in dynamic["order_ledger"] if row["action"] == "sell"],
        key=lambda row: row["symbol"],
    )
    assert sells[0]["symbol"] == "AAA"
    assert sells[0]["reason"] == "dynamic_rank3_entry_pullback_late_trend_loss_guard"
    assert sells[1]["symbol"] == "BBB"
    assert sells[1]["reason"] == "mechanical_horizon"


def test_rolling_account_replay_layered_guard_applies_quick_fail_only_to_rank1() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=1, multiplier=2.73, horizon=20),
                    _pick("2026-01-02", "BBB", rank=2, multiplier=2.73, horizon=20),
                ],
            }
        ],
    }
    quick_fail_bars = [
        {"day": "2026-01-02", "close": 10.0},
        {"day": "2026-01-03", "close": 10.0},
        {"day": "2026-01-04", "close": 10.8},
        {"day": "2026-01-05", "close": 9.7},
        *[{"day": f"2026-01-{day:02d}", "close": 9.6} for day in range(6, 31)],
    ]

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol={"AAA": quick_fail_bars, "BBB": quick_fail_bars},
        buy_cost_bps=0,
        sell_cost_bps=0,
        min_order_notional_cny=1_000.0,
    )

    dynamic = next(
        row
        for row in artifact["results"]
        if row["config_id"]
        == "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1"
    )
    sells = sorted(
        [row for row in dynamic["order_ledger"] if row["action"] == "sell"],
        key=lambda row: row["symbol"],
    )
    assert sells[0]["symbol"] == "AAA"
    assert sells[0]["reason"] == "dynamic_rank1_quick_spike_failed"
    assert sells[1]["symbol"] == "BBB"
    assert sells[1]["reason"] == "mechanical_horizon"


def test_r14_replay_applies_rank1_quality_scale_to_the_signal_budget() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "negative-month-rank-adjusted",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [
                    {
                        **_pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=5),
                        "return_20d_percentile": 0.99,
                        "return_5d_percentile": 0.99,
                        "industry_return_20d_excess": 0.2,
                    }
                ],
            }
        ],
    }
    bars = {"AAA": [{"day": f"2026-01-{day:02d}", "close": 10.0} for day in range(2, 15)]}
    plain = _research_config("plain")
    scaled = {
        **_research_config("scaled"),
        "rank1_quality_overlay": {
            "strong_return_20d_percentile_min": 0.95,
            "strong_return_5d_percentile_min": 0.93,
            "strong_benchmark_return_20d_min": 0.0,
            "strong_industry_return_20d_excess_max": 0.5,
            "strong_distance_from_20d_high_min": -0.08,
            "strong_scale": 1.5,
        },
    }
    weak_scaled = {
        **_research_config("weak-scaled"),
        "rank1_quality_overlay": {
            **scaled["rank1_quality_overlay"],
            "weak_benchmark_return_20d_lt": 0.01,
            "weak_scale": 0.8,
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[plain, scaled, weak_scaled],
    )

    plain_buy = artifact["results"][0]["order_ledger"][0]
    scaled_buy = artifact["results"][1]["order_ledger"][0]
    weak_scaled_buy = artifact["results"][2]["order_ledger"][0]
    assert scaled_buy["target_notional_cny"] == plain_buy["target_notional_cny"] * 1.5
    assert weak_scaled_buy["target_notional_cny"] == plain_buy["target_notional_cny"] * 0.8


def test_r14_replay_replaces_an_unaffordable_slot_from_rank4_inventory() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "negative-month-rank-adjusted",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [
                    {
                        **_pick("2026-01-02", "AAA", rank=1, multiplier=1.0),
                        "score": 3.0,
                        "shadow_baseline_buy_symbols": ["BBB"],
                    }
                ],
            }
        ],
    }
    bars = {
        "AAA": [{"day": f"2026-01-{day:02d}", "close": 200.0} for day in range(2, 15)],
        "BBB": [{"day": f"2026-01-{day:02d}", "close": 100.0} for day in range(2, 15)],
    }
    config = {
        **_research_config("replacement"),
        "affordable_replacement_policy": {
            "trigger_reason": "price_too_high_for_slot",
            "inventory_rank_min": 4,
            "inventory_rank_max": 5,
            "max_score_gap": 0.1,
            "min_fill_ratio": 0.75,
            "min_order_notional_cny": 250.0,
            "board_lot_size": 100,
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_inventory_rows=[
            {"as_of_date": "2026-01-02", "rank": 4, "symbol": "BBB", "stock_name": "BBB", "score": 2.95}
        ],
        candidate_configurations=[config],
    )

    result = artifact["results"][0]
    buy = next(row for row in result["order_ledger"] if row["action"] == "buy")
    assert buy["symbol"] == "BBB"
    assert buy["reason"] == "bought_affordable_rank4_5_replacement"
    assert buy["replacement_original_symbol"] == "AAA"
    assert result["summary"]["skip_order_count"] == 0


def test_rank5_replacement_quality_filter_is_fail_closed_and_does_not_filter_rank4() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "negative-month-rank-adjusted",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [
                    {**_pick("2026-01-02", "AAA", rank=1, multiplier=1.0), "score": 3.0}
                ],
            }
        ],
    }
    bars = {
        "AAA": [{"day": f"2026-01-{day:02d}", "close": 200.0} for day in range(2, 15)],
        "R4": [{"day": f"2026-01-{day:02d}", "close": 100.0} for day in range(2, 15)],
        "R5": [{"day": f"2026-01-{day:02d}", "close": 100.0} for day in range(2, 15)],
    }
    config = {
        **_research_config("replacement-quality"),
        "affordable_replacement_policy": {
            "trigger_reason": "price_too_high_for_slot",
            "inventory_rank_min": 4,
            "inventory_rank_max": 5,
            "max_score_gap": 0.1,
            "min_fill_ratio": 0.75,
            "min_order_notional_cny": 250.0,
            "board_lot_size": 100,
            "rank5_quality_policy": {"min_avg_amount_20d": 50_000_000.0},
        },
    }

    rank5_only = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_inventory_rows=[
            {"as_of_date": "2026-01-02", "rank": 5, "symbol": "R5", "score": 2.95}
        ],
        candidate_configurations=[config],
    )
    assert not [row for row in rank5_only["results"][0]["order_ledger"] if row["action"] == "buy"]

    rank4_available = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_inventory_rows=[
            {"as_of_date": "2026-01-02", "rank": 4, "symbol": "R4", "score": 2.95}
        ],
        candidate_configurations=[config],
    )
    buy = next(row for row in rank4_available["results"][0]["order_ledger"] if row["action"] == "buy")
    assert buy["symbol"] == "R4"


def test_rank5_path_quality_thresholds_are_fail_closed_and_bounded() -> None:
    candidate = {
        "path_realized_volatility_20d": 0.03,
        "path_downside_semivolatility_20d": 0.02,
        "path_max_drawdown_20d": -0.08,
        "path_up_day_ratio_20d": 0.55,
        "path_trend_efficiency_20d": 0.3,
    }
    policy = {
        "max_path_realized_volatility_20d": 0.04,
        "max_path_downside_semivolatility_20d": 0.03,
        "min_path_max_drawdown_20d": -0.12,
        "min_path_up_day_ratio_20d": 0.45,
        "min_path_trend_efficiency_20d": 0.2,
    }

    assert rank5_replacement_quality_rejection_reason(
        candidate, inventory_rank=5, original_score=3.0, policy=policy
    ) is None
    assert (
        rank5_replacement_quality_rejection_reason(
            {**candidate, "path_realized_volatility_20d": 0.05},
            inventory_rank=5,
            original_score=3.0,
            policy=policy,
        )
        == "rank5_quality_path_volatility_above_max"
    )
    assert rank5_replacement_quality_rejection_reason(
        {}, inventory_rank=5, original_score=3.0, policy=policy
    ) == "rank5_quality_missing_path_realized_volatility_20d"
    assert rank5_replacement_quality_rejection_reason(
        {}, inventory_rank=4, original_score=3.0, policy=policy
    ) is None


def test_r14_replay_trims_market_value_exposure_after_entries() -> None:
    signal_days = [f"2026-01-{day:02d}" for day in range(2, 7)]
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "negative-month-rank-adjusted",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [
                    _pick(signal_day, "AAA", rank=1, multiplier=1.0, horizon=20) for signal_day in signal_days
                ],
            }
        ],
    }
    bars = {"AAA": [{"day": f"2026-01-{day:02d}", "close": 10.0} for day in range(2, 31)]}
    config = {
        **_research_config("rebalance"),
        "max_single_symbol_cost_basis_pct": 1.0,
        "market_value_concentration_rebalance": {
            "threshold": 0.25,
            "sell_cost_bps": 0.0,
            "board_lot_size": 100,
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    result = artifact["results"][0]
    rebalance_sells = [
        row for row in result["order_ledger"] if row.get("reason") == "market_value_concentration_rebalance"
    ]
    assert rebalance_sells
    assert result["summary"]["max_single_symbol_exposure_pct"] <= 0.25


def test_dynamic_budget_uses_configured_single_signal_deployment_cap() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 3,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=1),
                    _pick("2026-01-02", "BBB", rank=2, multiplier=1.0, horizon=1),
                    _pick("2026-01-02", "CCC", rank=3, multiplier=1.0, horizon=1),
                ],
            }
        ],
    }
    bars = {
        symbol: [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.0},
        ]
        for symbol in ("AAA", "BBB", "CCC")
    }
    baseline = _research_config("baseline")
    higher_cap = {
        **baseline,
        "config_id": "higher-cap",
        "target_active_tranche_count": 12,
        "max_single_signal_deployment_pct": 0.08,
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        initial_cash_cny=200_000.0,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[baseline, higher_cap],
    )

    baseline_spend = sum(
        row.get("cash_spent_cny", 0.0)
        for row in artifact["results"][0]["order_ledger"]
        if row["action"] == "buy"
    )
    higher_spend = sum(
        row.get("cash_spent_cny", 0.0)
        for row in artifact["results"][1]["order_ledger"]
        if row["action"] == "buy"
    )
    assert higher_spend > baseline_spend
    assert artifact["results"][1]["summary"]["max_single_signal_deployment_pct"] == 0.08


def test_pit_external_position_exit_signal_executes_only_on_named_next_trade_day() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=4)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.4},
            {"day": "2026-01-08", "close": 10.3},
            {"day": "2026-01-09", "close": 10.2},
        ]
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-exit"),
        "exit_policy": "mechanical_horizon",
        "pit_external_position_exit_signals": {
            "2026-01-07": {position_key: "pit_external_event_confirmed_risk_exit"}
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    sells = [row for row in artifact["results"][0]["order_ledger"] if row["action"] == "sell"]
    assert [(row["trade_day"], row["reason"]) for row in sells] == [
        ("2026-01-07", "pit_external_event_confirmed_risk_exit")
    ]


def test_pit_external_position_exit_deferral_extends_replay_and_holding_day() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=2)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.6},
            {"day": "2026-01-08", "close": 11.0},
        ]
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-deferral"),
        "exit_policy": "mechanical_horizon",
        "pit_external_position_exit_deferrals": {
            "2026-01-07": {
                position_key: {
                    "deferred_exit_day": "2026-01-08",
                    "reason": "pit_external_event_confirmed_rebound_extension",
                }
            }
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    sells = [row for row in artifact["results"][0]["order_ledger"] if row["action"] == "sell"]
    assert [(row["trade_day"], row["price"]) for row in sells] == [("2026-01-08", 11.0)]
    assert artifact["results"][0]["nav_rows"][-1]["day"] == "2026-01-08"


def test_pit_external_position_exit_deferral_fails_closed_below_cash_reserve() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=2)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.6},
            {"day": "2026-01-08", "close": 11.0},
        ]
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-deferral-reserve"),
        "exit_policy": "mechanical_horizon",
        "pit_external_position_exit_deferrals": {
            "2026-01-07": {
                position_key: {
                    "deferred_exit_day": "2026-01-08",
                    "reason": "pit_external_event_confirmed_rebound_extension",
                    "minimum_cash_reserve_cny": 1_000_000.0,
                }
            }
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    sells = [row for row in artifact["results"][0]["order_ledger"] if row["action"] == "sell"]
    assert [(row["trade_day"], row["reason"]) for row in sells] == [("2026-01-07", "mechanical_horizon")]


def test_pit_external_deferral_stop_uses_prior_close_and_next_day_execution() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=2)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.6},
            {"day": "2026-01-08", "close": 9.0},
            {"day": "2026-01-09", "close": 8.8},
            {"day": "2026-01-12", "close": 8.7},
        ]
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-deferral-stop"),
        "exit_policy": "mechanical_horizon",
        "pit_external_position_exit_deferrals": {
            "2026-01-07": {
                position_key: {
                    "deferred_exit_day": "2026-01-12",
                    "reason": "pit_external_event_confirmed_rebound_extension",
                    "deferral_stop_loss_pct": 0.05,
                }
            }
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    sells = [row for row in artifact["results"][0]["order_ledger"] if row["action"] == "sell"]
    assert [(row["trade_day"], row["price"], row["reason"]) for row in sells] == [
        ("2026-01-09", 8.8, "pit_external_deferral_next_day_stop_loss")
    ]


def test_pit_external_deferral_partially_sells_whole_lots_to_restore_cash_reserve() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [_pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=2)],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.6},
            {"day": "2026-01-08", "close": 11.0},
        ]
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-partial-deferral"),
        "exit_policy": "mechanical_horizon",
        "pit_external_position_exit_deferrals": {
            "2026-01-07": {
                position_key: {
                    "deferred_exit_day": "2026-01-08",
                    "reason": "pit_external_event_confirmed_rebound_extension",
                    "minimum_cash_reserve_cny": 190_000.0,
                }
            }
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    sells = [row for row in artifact["results"][0]["order_ledger"] if row["action"] == "sell"]
    assert sells[0]["trade_day"] == "2026-01-07"
    assert sells[0]["reason"] == "pit_external_deferral_partial_liquidity_reserve"
    assert sells[0]["shares"] % 100 == 0
    assert sells[-1]["trade_day"] == "2026-01-08"
    assert sells[-1]["shares"] > 0


def test_pit_external_deferral_recalls_only_when_same_day_entry_needs_cash() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 4,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=1, multiplier=1.0, horizon=2),
                    _pick("2026-01-02", "CCC", rank=2, multiplier=1.0, horizon=10),
                    _pick("2026-01-02", "DDD", rank=3, multiplier=1.0, horizon=10),
                    _pick("2026-01-02", "EEE", rank=4, multiplier=1.0, horizon=10),
                    _pick("2026-01-06", "BBB", rank=1, multiplier=1.0, horizon=1),
                ],
            }
        ],
    }
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.6},
            {"day": "2026-01-08", "close": 11.0},
        ],
        "BBB": [
            {"day": "2026-01-07", "close": 10.0},
            {"day": "2026-01-08", "close": 10.2},
        ],
        "CCC": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.0},
            {"day": "2026-01-07", "close": 10.0},
            {"day": "2026-01-08", "close": 10.0},
        ],
        "DDD": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.0},
            {"day": "2026-01-07", "close": 10.0},
            {"day": "2026-01-08", "close": 10.0},
        ],
        "EEE": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.0},
            {"day": "2026-01-07", "close": 10.0},
            {"day": "2026-01-08", "close": 10.0},
        ],
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-entry-liquidity-recall"),
        "exit_policy": "mechanical_horizon",
        "target_active_tranche_count": 1,
        "max_single_signal_deployment_pct": 1.0,
        "max_single_symbol_cost_basis_pct": 1.0,
        "pit_external_entry_liquidity_recall": True,
        "pit_external_position_exit_deferrals": {
            "2026-01-07": {
                position_key: {
                    "deferred_exit_day": "2026-01-08",
                    "reason": "pit_external_event_confirmed_rebound_extension",
                    "extension_priority": 0.1,
                }
            }
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    ledger = artifact["results"][0]["order_ledger"]
    recall = [row for row in ledger if row.get("reason") == "pit_external_deferral_entry_liquidity_recall"]
    assert len(recall) == 1, ledger
    assert recall[0]["trade_day"] == "2026-01-07"
    assert recall[0]["shares"] % 100 == 0
    assert any(row.get("action") == "buy" and row.get("symbol") == "BBB" for row in ledger)
    assert not any(row.get("reason") == "insufficient_cash" for row in ledger)


def test_pit_external_deferral_cash_fits_new_entry_without_selling_winner() -> None:
    candidate_run = {
        "artifact_id": "candidate-run",
        "trial_diagnostics": [
            {
                "trial_id": "trial-1",
                "model_spec_id": "unit-model",
                "selected_top_k": 4,
                "selected_top_k_picks_by_date": [
                    _pick("2026-01-02", "AAA", rank=1, multiplier=0.8, horizon=2),
                    _pick("2026-01-02", "CCC", rank=2, multiplier=0.8, horizon=10),
                    _pick("2026-01-02", "DDD", rank=3, multiplier=0.8, horizon=10),
                    _pick("2026-01-02", "EEE", rank=4, multiplier=0.8, horizon=10),
                    _pick("2026-01-06", "BBB", rank=1, multiplier=1.0, horizon=1),
                ],
            }
        ],
    }
    flat = [
        {"day": "2026-01-05", "close": 10.0},
        {"day": "2026-01-06", "close": 10.0},
        {"day": "2026-01-07", "close": 10.0},
        {"day": "2026-01-08", "close": 10.0},
    ]
    bars = {
        "AAA": [
            {"day": "2026-01-05", "close": 10.0},
            {"day": "2026-01-06", "close": 10.5},
            {"day": "2026-01-07", "close": 10.6},
            {"day": "2026-01-08", "close": 11.0},
        ],
        "BBB": [
            {"day": "2026-01-07", "close": 10.0},
            {"day": "2026-01-08", "close": 10.2},
        ],
        "CCC": flat,
        "DDD": flat,
        "EEE": flat,
    }
    position_key = "2026-01-02|2026-01-05|AAA|1"
    config = {
        **_research_config("pit-entry-cash-fit"),
        "exit_policy": "mechanical_horizon",
        "target_active_tranche_count": 1,
        "max_single_signal_deployment_pct": 1.0,
        "pit_external_entry_cash_fit": True,
        "pit_external_position_exit_deferrals": {
            "2026-01-07": {
                position_key: {
                    "deferred_exit_day": "2026-01-08",
                    "reason": "pit_external_event_confirmed_rebound_extension",
                    "extension_priority": 0.1,
                }
            }
        },
    }

    artifact = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id="trial-1",
        market_bars_by_symbol=bars,
        buy_cost_bps=0,
        sell_cost_bps=0,
        candidate_configurations=[config],
    )

    ledger = artifact["results"][0]["order_ledger"]
    bbb_buy = next(row for row in ledger if row.get("action") == "buy" and row.get("symbol") == "BBB")
    assert bbb_buy["shares"] == 4_000
    assert not any(str(row.get("reason") or "").endswith("liquidity_recall") for row in ledger)
    aaa_sells = [row for row in ledger if row.get("action") == "sell" and row.get("symbol") == "AAA"]
    assert [(row["trade_day"], row["shares"]) for row in aaa_sells] == [("2026-01-08", 4_000)]


def _research_config(config_id: str) -> dict[str, object]:
    return {
        "config_id": config_id,
        "signal_cadence_trade_days": 1,
        "target_active_tranche_count": 15,
        "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
        "budget_mode": "current_nav_fraction",
        "min_order_notional_cny": 250.0,
        "max_single_symbol_cost_basis_pct": 0.35,
        "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
        "per_signal_target_budget_cny": 200_000 / 15,
        "per_signal_target_budget_pct": 1 / 15,
    }


def _pick(
    as_of_date: str,
    symbol: str,
    *,
    rank: int,
    multiplier: float,
    horizon: int = 5,
    benchmark_return_20d: float = 0.0,
    distance_from_20d_high: float = 0.0,
) -> dict[str, object]:
    return {
        "as_of_date": as_of_date,
        "symbol": symbol,
        "stock_name": symbol,
        "rank": rank,
        "portfolio_weight": 1.0,
        "rank_weight_multiplier": multiplier,
        "target_horizon_days": horizon,
        "benchmark_return_20d": benchmark_return_20d,
        "distance_from_20d_high": distance_from_20d_high,
    }
