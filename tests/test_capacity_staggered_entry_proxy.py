from __future__ import annotations

from datetime import datetime

from ashare_evidence.capacity_staggered_entry_proxy import (
    _apply_exposure_overlay,
    _evaluate_staggered_entry_option,
    _staggered_pick_replacement,
)


def test_staggered_pick_replacement_accumulates_under_adv_cap() -> None:
    pick = {
        "as_of_date": "2024-01-02",
        "symbol": "600000.SH",
        "rank": 1,
        "portfolio_weight": 1.0,
        "rank_weight_multiplier": 1.0,
        "net_excess_return": 0.30,
    }
    histories = {
        "600000.SH": [
            {"observed_at": datetime(2024, 1, 2, 15), "close_price": 10.0, "amount": 100.0},
            {"observed_at": datetime(2024, 1, 3, 15), "close_price": 11.0, "amount": 100.0},
            {"observed_at": datetime(2024, 1, 4, 15), "close_price": 12.0, "amount": 100.0},
            {"observed_at": datetime(2024, 1, 5, 15), "close_price": 15.0, "amount": 100.0},
        ],
        "000300.SH": [
            {"observed_at": datetime(2024, 1, 2, 15), "close_price": 100.0, "amount": 0.0},
            {"observed_at": datetime(2024, 1, 3, 15), "close_price": 100.0, "amount": 0.0},
            {"observed_at": datetime(2024, 1, 4, 15), "close_price": 100.0, "amount": 0.0},
            {"observed_at": datetime(2024, 1, 5, 15), "close_price": 100.0, "amount": 0.0},
        ],
    }

    replacement = _staggered_pick_replacement(
        pick,
        histories=histories,
        selected_top_k=1,
        target_horizon_days=3,
        portfolio_notional_cny=100.0,
        max_adv_participation_rate=0.5,
        entry_days=2,
        exit_policy="original_exit",
        benchmark_symbol="000300.SH",
    )

    assert replacement["staggered_fill_rate"] == 1.0
    assert len(replacement["entry_fills"]) == 2
    assert replacement["entry_fills"][0]["fill_notional_cny"] == 50.0
    assert replacement["entry_fills"][1]["fill_notional_cny"] == 50.0
    assert round(replacement["staggered_contribution"], 6) == round(0.5 * 0.5 + 0.5 * (15 / 11 - 1), 6)


def test_staggered_pick_replacement_supports_per_tranche_horizon_exit() -> None:
    pick = {
        "as_of_date": "2024-01-02",
        "symbol": "600000.SH",
        "rank": 1,
        "portfolio_weight": 1.0,
        "rank_weight_multiplier": 1.0,
        "net_excess_return": 0.20,
    }
    histories = {
        "600000.SH": [
            {"observed_at": datetime(2024, 1, 2, 15), "close_price": 10.0, "amount": 100.0},
            {"observed_at": datetime(2024, 1, 3, 15), "close_price": 10.0, "amount": 100.0},
            {"observed_at": datetime(2024, 1, 4, 15), "close_price": 12.0, "amount": 100.0},
            {"observed_at": datetime(2024, 1, 5, 15), "close_price": 20.0, "amount": 100.0},
        ],
        "000300.SH": [
            {"observed_at": datetime(2024, 1, 2, 15), "close_price": 100.0, "amount": 0.0},
            {"observed_at": datetime(2024, 1, 3, 15), "close_price": 100.0, "amount": 0.0},
            {"observed_at": datetime(2024, 1, 4, 15), "close_price": 100.0, "amount": 0.0},
            {"observed_at": datetime(2024, 1, 5, 15), "close_price": 100.0, "amount": 0.0},
        ],
    }

    original_exit = _staggered_pick_replacement(
        pick,
        histories=histories,
        selected_top_k=1,
        target_horizon_days=2,
        portfolio_notional_cny=100.0,
        max_adv_participation_rate=0.5,
        entry_days=2,
        exit_policy="original_exit",
        benchmark_symbol="000300.SH",
    )
    per_tranche_exit = _staggered_pick_replacement(
        pick,
        histories=histories,
        selected_top_k=1,
        target_horizon_days=2,
        portfolio_notional_cny=100.0,
        max_adv_participation_rate=0.5,
        entry_days=2,
        exit_policy="per_tranche_horizon",
        benchmark_symbol="000300.SH",
    )

    assert round(original_exit["staggered_contribution"], 6) == round(0.5 * 0.2 + 0.5 * 0.2, 6)
    assert round(per_tranche_exit["staggered_contribution"], 6) == round(0.5 * 0.2 + 0.5 * 1.0, 6)
    assert per_tranche_exit["last_exit_date"] == "2024-01-05"
    assert per_tranche_exit["entry_fills"][1]["exit_date"] == "2024-01-05"


def test_apply_exposure_overlay_scales_low_exposure_active_row() -> None:
    row = {
        "as_of_date": "2026-01-02",
        "month": "2026-01",
        "mean_net_excess_return": -0.04,
        "gross_exposure": 0.1,
        "pick_count": 1,
    }

    adjusted = _apply_exposure_overlay(row, exposure_overlay_mode="linear_scale", gross_exposure_floor=0.2)

    assert adjusted["exposure_overlay_applied"] is True
    assert adjusted["exposure_overlay_scale"] == 0.5
    assert adjusted["mean_net_excess_return"] == -0.02


def test_staggered_entry_option_can_combine_exposure_overlay_without_underfilled_rows() -> None:
    selected_returns = [
        {
            "as_of_date": "2026-01-02",
            "month": "2026-01",
            "mean_net_excess_return": -0.04,
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
    ]

    summary = _evaluate_staggered_entry_option(
        selected_returns,
        [],
        histories={},
        selected_top_k=1,
        target_horizon_days=1,
        portfolio_notional_cny=100.0,
        max_adv_participation_rate=0.5,
        entry_days=1,
        exit_policy="original_exit",
        exposure_overlay_mode="linear_scale",
        gross_exposure_floor=0.2,
        benchmark_symbol="000300.SH",
    )

    assert summary["low_exposure_active_date_count"] == 1
    assert summary["mean_daily_net_excess_return"] == 0.03
    assert summary["mode"].endswith(":exposure_linear_scale_0.200000")
