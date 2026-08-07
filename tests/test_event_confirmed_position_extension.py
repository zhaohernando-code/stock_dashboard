from __future__ import annotations

from ashare_evidence.event_confirmed_position_extension import (
    _deferrals_for_variant,
    _freeze_to_baseline_executed_buys,
)


def test_deferral_requires_event_external_increment_and_rebound_confirmation() -> None:
    row = {
        "position_key": "2026-01-01|2026-01-02|AAA|1",
        "decision_day": "2026-01-20",
        "effective_deferral_day": "2026-01-21",
        "deferred_exit_day": "2026-01-28",
        "symbol": "AAA",
        "rank": 1,
        "event_count": 1,
        "post_event_price_confirmation": 0.03,
        "position_return": 0.08,
        "global_breadth_5d": 0.75,
        "sector_relative_5d": 0.01,
    }
    predictions = {
        (row["position_key"], row["decision_day"]): {
            "core_prediction": 0.002,
            "full_prediction": 0.02,
            "external_increment": 0.018,
            "core_percentile": 0.6,
            "full_percentile": 0.96,
        }
    }
    variant = {
        "prediction_percentile_min": 0.95,
        "minimum_predicted_advantage": 0.01,
        "minimum_position_return": 0.05,
        "minimum_global_breadth_5d": 0.5,
        "minimum_sector_relative_5d": 0.0,
        "wide_protection_min_position_return": 0.05,
        "wide_deferral_stop_loss_pct": 0.10,
        "wide_deferral_trailing_activation_pct": 0.50,
        "wide_deferral_trailing_drawdown_pct": 0.15,
    }

    deferrals, triggers = _deferrals_for_variant(
        observations=[row], predictions=predictions, variant=variant
    )

    assert triggers[0]["symbol"] == "AAA"
    assert deferrals["2026-01-21"][row["position_key"]] == {
        "deferred_exit_day": "2026-01-28",
        "reason": "pit_external_event_confirmed_rebound_extension",
        "extension_priority": 0.02,
        "minimum_cash_reserve_cny": 0.0,
        "deferral_stop_loss_pct": 0.10,
        "deferral_trailing_activation_pct": 0.50,
        "deferral_trailing_drawdown_pct": 0.15,
    }


def test_deferral_rejects_negative_external_increment() -> None:
    row = {
        "position_key": "p1",
        "decision_day": "2026-01-20",
        "effective_deferral_day": "2026-01-21",
        "deferred_exit_day": "2026-01-28",
        "symbol": "AAA",
        "rank": 1,
        "event_count": 1,
        "post_event_price_confirmation": 0.03,
        "position_return": 0.08,
        "global_breadth_5d": 0.75,
        "sector_relative_5d": 0.01,
    }
    predictions = {
        ("p1", "2026-01-20"): {
            "core_prediction": 0.03,
            "full_prediction": 0.02,
            "external_increment": -0.01,
            "core_percentile": 0.99,
            "full_percentile": 0.99,
        }
    }
    variant = {
        "prediction_percentile_min": 0.9,
        "minimum_predicted_advantage": 0.0,
        "minimum_position_return": 0.0,
        "minimum_global_breadth_5d": 0.5,
        "minimum_sector_relative_5d": 0.0,
    }

    deferrals, triggers = _deferrals_for_variant(
        observations=[row], predictions=predictions, variant=variant
    )

    assert deferrals == {}
    assert triggers == []


def test_deferral_can_fail_closed_when_recent_official_event_conflicts() -> None:
    row = {
        "position_key": "p1",
        "decision_day": "2026-01-20",
        "effective_deferral_day": "2026-01-21",
        "deferred_exit_day": "2026-01-28",
        "symbol": "AAA",
        "rank": 1,
        "event_count": 1,
        "post_event_price_confirmation": 0.03,
        "position_return": 0.08,
        "global_breadth_5d": 0.75,
        "sector_relative_5d": 0.01,
    }
    predictions = {
        ("p1", "2026-01-20"): {
            "core_prediction": 0.01,
            "full_prediction": 0.03,
            "external_increment": 0.02,
            "core_percentile": 0.8,
            "full_percentile": 0.9,
        }
    }
    variant = {
        "require_recent_event": False,
        "maximum_event_count": 0,
        "prediction_percentile_min": 0.7,
        "minimum_predicted_advantage": 0.0,
        "minimum_position_return": 0.0,
        "minimum_global_breadth_5d": 0.5,
        "minimum_sector_relative_5d": 0.0,
    }

    deferrals, triggers = _deferrals_for_variant(
        observations=[row], predictions=predictions, variant=variant
    )

    assert deferrals == {}
    assert triggers == []


def test_freeze_to_baseline_executed_buys_preserves_replacement_symbol_allowlist() -> None:
    picks = [
        {"as_of_date": "2026-01-02", "symbol": "AAA", "rank": 1},
        {"as_of_date": "2026-01-02", "symbol": "BBB", "rank": 2},
    ]

    frozen = _freeze_to_baseline_executed_buys(
        picks,
        baseline_buy_symbols_by_signal_rank={("2026-01-02", 1): {"REPLACEMENT"}},
        baseline_buy_shares_by_signal_rank={("2026-01-02", 1): {"REPLACEMENT": 300}},
    )

    assert frozen[0]["shadow_baseline_buy_eligible"] is True
    assert frozen[0]["shadow_baseline_buy_symbols"] == ["REPLACEMENT"]
    assert frozen[0]["shadow_baseline_buy_shares_by_symbol"] == {"REPLACEMENT": 300}
    assert frozen[1]["shadow_baseline_buy_eligible"] is False
    assert frozen[1]["shadow_baseline_buy_symbols"] == []


def test_global_rebound_deferral_does_not_require_recent_event_when_disabled() -> None:
    row = {
        "position_key": "p1",
        "decision_day": "2026-01-20",
        "effective_deferral_day": "2026-01-21",
        "deferred_exit_day": "2026-02-04",
        "symbol": "AAA",
        "rank": 1,
        "event_count": 0,
        "post_event_price_confirmation": 0.0,
        "position_return": 0.03,
        "global_breadth_5d": 0.75,
        "global_mean_return_5d": 0.01,
        "sector_relative_5d": -0.01,
    }
    predictions = {
        ("p1", "2026-01-20"): {
            "core_prediction": 0.0,
            "full_prediction": 0.02,
            "external_increment": 0.02,
            "core_percentile": 0.5,
            "full_percentile": 0.9,
        }
    }
    variant = {
        "require_recent_event": False,
        "prediction_percentile_min": 0.8,
        "minimum_predicted_advantage": 0.0,
        "minimum_position_return": 0.0,
        "minimum_global_breadth_5d": 0.5,
        "minimum_global_mean_return_5d": 0.0,
        "minimum_sector_relative_5d": -1.0,
    }

    deferrals, triggers = _deferrals_for_variant(
        observations=[row], predictions=predictions, variant=variant
    )

    assert len(triggers) == 1
    assert "2026-01-21" in deferrals
