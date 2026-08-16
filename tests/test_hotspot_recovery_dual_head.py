from __future__ import annotations

from typing import Any

import pytest

from ashare_evidence.hotspot_recovery_dual_head import (
    ACTIVITY_FEATURE_NAMES,
    FEATURE_NAMES,
    activity_features,
    fit_dual_head,
    score_recent_shadow,
)
from ashare_evidence.recent_hotspot_pit import flatten_recovery_features, miss_stage


def test_flatten_recovery_features_uses_only_signal_day_groups() -> None:
    row = {
        "feature_values": {
            "price_momentum": {"return_3d": 0.03, "return_5d": 0.05, "return_10d": 0.1},
            "reversal_overheat": {"return_1d": 0.01, "distance_from_20d_high": -0.2},
            "volatility_risk": {"max_drawdown_20d": -0.2, "volatility_20d": 0.15},
            "liquidity": {"avg_amount_10d": 120.0, "avg_amount_20d": 100.0, "turnover_rate": 0.02},
            "crowding": {"amount_vs_20d_avg": 1.5},
            "cross_sectional": {"return_5d_percentile": 0.9, "amount_10d_vs_20d": 0.2},
            "regime": {"benchmark_return_20d": -0.01},
        },
        "future_return_5d": 9.9,
    }
    values = flatten_recovery_features(row)
    assert values["amount_1d_vs_20d"] == 0.5
    assert values["amount_10d_vs_20d_raw"] == pytest.approx(0.2)
    assert all("future" not in key for key in values)


def test_miss_stage_separates_cash_switch_rank_and_execution() -> None:
    base: dict[str, Any] = {
        "personally_eligible": True,
        "v3_market_cash_switch": False,
        "v3_top3_rank": None,
        "v3_top20_rank": None,
        "entry_status": "tradable_research_proxy",
    }
    assert miss_stage(base) == "outside_v3_top20"
    assert miss_stage({**base, "v3_top20_rank": 12}) == "v3_top20_but_below_top3"
    assert miss_stage({**base, "v3_top3_rank": 1}) == "captured_executable_v3_top3"
    assert miss_stage({**base, "v3_top3_rank": 1, "entry_status": "blocked"}) == (
        "v3_top3_execution_or_position_block"
    )
    assert miss_stage({**base, "v3_market_cash_switch": True}) == "v3_market_cash_switch"


def test_activity_features_are_past_and_same_day_only() -> None:
    rows = [
        {"day": f"2026-01-{index + 1:02d}", "amount": float(index + 1), "turnover": float(index + 2)}
        for index in range(21)
    ]
    first = activity_features(rows, index=19)
    changed_future = [dict(row) for row in rows]
    changed_future[20]["amount"] = 1_000_000.0
    changed_future[20]["turnover"] = 1_000_000.0
    assert activity_features(changed_future, index=19) == first
    assert set(first) == set(ACTIVITY_FEATURE_NAMES)


def _training_row(index: int, *, label_day: str = "2026-06-26") -> dict[str, Any]:
    row = {name: ((index % (position + 7)) - 3.0) / 10.0 for position, name in enumerate(FEATURE_NAMES)}
    row.update(
        {
            "net_return_10d": ((index % 11) - 5) / 100.0,
            "downside_label": index % 4 == 0,
            "label_available_day": label_day,
        }
    )
    return row


def test_dual_head_fit_excludes_future_available_labels() -> None:
    rows = [_training_row(index) for index in range(3000)]
    rows.append(_training_row(3001, label_day="2026-06-29"))
    model = fit_dual_head(rows, fit_day="2026-06-26")
    assert model.training_row_count == 3000
    assert model.maximum_label_available_day == "2026-06-26"


class _FakeModel:
    def predict(self, features: list[float]) -> tuple[float, float]:
        return features[0], features[1]


def _scoring_row(symbol: str, recovery: float, risk: float) -> dict[str, Any]:
    values = {name: 0.0 for name in FEATURE_NAMES}
    values[FEATURE_NAMES[0]] = recovery
    values[FEATURE_NAMES[1]] = risk
    return {
        "symbol": symbol,
        "stock_name": symbol,
        "industry_name": "test",
        **values,
        "recent_pit_row": {
            "entry_date": "2026-08-18",
            "entry_status": "tradable_research_proxy",
            "forward_return_5d": None,
            "forward_return_10d": None,
            "v3_top3_rank": None,
        },
    }


def test_shadow_selection_uses_relative_ranks_and_respects_activation_boundary() -> None:
    rows = {
        "2026-08-14": [
            _scoring_row("A", 0.9, 0.1),
            _scoring_row("B", 0.4, 0.5),
            _scoring_row("C", 0.1, 0.9),
        ],
        "2026-08-17": [
            _scoring_row("D", 0.8, 0.1),
            _scoring_row("E", 0.2, 0.8),
        ],
    }
    selected, daily = score_recent_shadow(rows, model=_FakeModel(), activation_date="2026-08-17")
    assert [row["symbol"] for row in selected] == ["A", "D"]
    assert daily[0]["evidence_basis"] == "retrospective_diagnostic"
    assert daily[1]["evidence_basis"] == "true_forward_shadow"
    assert all(row["same_day_v3_top3_overlap"] is False for row in selected)
    assert all("ranked_candidates" not in row for row in selected)
