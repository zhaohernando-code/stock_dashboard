from __future__ import annotations

from copy import deepcopy

import pytest

from ashare_evidence.round75_shadow_tracking import (
    ROUND75_SHADOW_STRATEGY_ID,
    advance_round75_signal_registry,
    build_round75_signal_registry,
    validate_round75_signal_registry,
)


def _tracking_artifact() -> dict[str, object]:
    return {
        "frozen_variant": {
            "wide_protection_min_position_return": 0.10,
            "deferral_stop_loss_pct": 0.05,
            "deferral_trailing_activation_pct": 0.15,
            "deferral_trailing_drawdown_pct": 0.05,
            "wide_deferral_stop_loss_pct": 0.10,
            "wide_deferral_trailing_activation_pct": 0.50,
            "wide_deferral_trailing_drawdown_pct": 0.15,
        },
        "historical_backfill": {
            "to": "2026-08-07",
            "triggers": [
                {
                    "position_key": "2026-01-20|2026-01-21|603115.SH|1",
                    "decision_day": "2026-02-25",
                    "effective_deferral_day": "2026-02-26",
                    "deferred_exit_day": "2026-04-24",
                    "symbol": "603115.SH",
                    "rank": 1,
                    "position_return": 0.18,
                    "retained_share_scale": 1.0,
                }
            ]
        },
        "source_lineage": {"round75_result_artifact_id": "round75-test"},
    }


def test_round75_signal_registry_labels_backfill_and_freezes_execution_parameters() -> None:
    registry = build_round75_signal_registry(_tracking_artifact())
    validation = validate_round75_signal_registry(registry)

    assert registry["strategy_id"] == ROUND75_SHADOW_STRATEGY_ID
    assert validation["signal_count"] == 1
    assert validation["true_forward_signal_count"] == 0
    signal = validation["signals"][0]
    assert signal["evidence_basis"] == "retrospective_pit_backfill"
    assert signal["available_at"] <= signal["decision_cutoff"]
    assert signal["execution"] == {
        "deferred_exit_day": "2026-04-24",
        "retained_share_scale": 1.0,
        "deferral_stop_loss_pct": 0.10,
        "deferral_trailing_activation_pct": 0.50,
        "deferral_trailing_drawdown_pct": 0.15,
    }


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"available_at": "2026-02-26T00:00:00+08:00"}, "available_after_decision_cutoff"),
        ({"decision_cutoff": "2026-02-26T23:59:59+08:00"}, "decision_cutoff_day_mismatch"),
        ({"effective_deferral_day": "2026-02-25"}, "non_forward_effective_day"),
        ({"execution": {"deferred_exit_day": "2026-02-26"}}, "non_forward_deferred_exit_day"),
    ],
)
def test_round75_signal_registry_rejects_future_or_non_forward_rows(
    mutation: dict[str, object],
    reason: str,
) -> None:
    registry = build_round75_signal_registry(_tracking_artifact())
    broken = deepcopy(registry)
    broken["signals"][0].update(mutation)

    with pytest.raises(ValueError, match=reason):
        validate_round75_signal_registry(broken)


def test_round75_signal_registry_advance_is_append_only() -> None:
    existing = build_round75_signal_registry(_tracking_artifact())
    candidate = deepcopy(existing)
    candidate["evaluated_through"] = "2026-08-10"
    candidate["signals"].append(
        {
            **deepcopy(candidate["signals"][0]),
            "position_key": "2026-07-10|2026-07-13|600030.SH|1",
            "decision_day": "2026-08-07",
            "effective_deferral_day": "2026-08-10",
            "deferred_exit_day": "2026-10-13",
            "available_at": "2026-08-07T23:59:59+08:00",
            "decision_cutoff": "2026-08-07T23:59:59+08:00",
            "evidence_basis": "retrospective_pit_backfill",
            "execution": {
                "deferred_exit_day": "2026-10-13",
                "retained_share_scale": 1.0,
                "deferral_stop_loss_pct": 0.05,
                "deferral_trailing_activation_pct": 0.15,
                "deferral_trailing_drawdown_pct": 0.05,
            },
        }
    )

    with pytest.raises(ValueError, match="late signal attempted"):
        advance_round75_signal_registry(existing, candidate)

    candidate["signals"].pop()
    candidate["signals"].append(
        {
            **deepcopy(candidate["signals"][0]),
            "position_key": "2026-07-13|2026-07-14|600030.SH|1",
            "decision_day": "2026-08-10",
            "effective_deferral_day": "2026-08-11",
            "deferred_exit_day": "2026-10-14",
            "available_at": "2026-08-10T23:59:59+08:00",
            "decision_cutoff": "2026-08-10T23:59:59+08:00",
            "evidence_basis": "true_forward_shadow",
            "execution": {
                "deferred_exit_day": "2026-10-14",
                "retained_share_scale": 1.0,
                "deferral_stop_loss_pct": 0.05,
                "deferral_trailing_activation_pct": 0.15,
                "deferral_trailing_drawdown_pct": 0.05,
            },
        }
    )
    advanced = advance_round75_signal_registry(existing, candidate)
    assert len(advanced["signals"]) == 2
