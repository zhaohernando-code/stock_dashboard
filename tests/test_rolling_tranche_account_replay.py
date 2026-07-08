from __future__ import annotations

from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact


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
