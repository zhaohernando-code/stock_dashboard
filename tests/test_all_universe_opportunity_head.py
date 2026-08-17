from __future__ import annotations

from copy import deepcopy
from typing import Any

from ashare_evidence.all_universe_hotspot_classifier import fit_hotspot_classifier
from ashare_evidence.all_universe_opportunity_data import (
    _attach_label,
    _prefilter,
    invariant_main_board_symbol,
)
from ashare_evidence.all_universe_opportunity_head import FEATURE_NAMES, fit_opportunity_model


def test_invariant_main_board_symbol_excludes_benchmarks_and_restricted_boards() -> None:
    assert invariant_main_board_symbol("600183.SH") is True
    assert invariant_main_board_symbol("600584.SH") is True
    assert invariant_main_board_symbol("002475.SZ") is True
    assert invariant_main_board_symbol("000300.SH") is False
    assert invariant_main_board_symbol("300750.SZ") is False
    assert invariant_main_board_symbol("688981.SH") is False
    assert invariant_main_board_symbol("830799.BJ") is False


def _candidate(symbol: str, *, recovery: float, v3_quality: float = 0.0) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "return_1d": recovery,
        "return_3d_minus_return_5d": recovery,
        "distance_from_20d_high": -recovery,
        "amount_1d_vs_20d": recovery,
        "turnover_1d_vs_20d": recovery,
        "v3_soft_quality": v3_quality,
    }


def test_prefilter_uses_v3_as_bonus_not_identity_gate() -> None:
    rows = [
        _candidate("NO_V3", recovery=0.20),
        _candidate("WITH_V3", recovery=0.10, v3_quality=1.0),
    ]
    selected = _prefilter(rows, top_k=2)
    assert {row["symbol"] for row in selected} == {"NO_V3", "WITH_V3"}
    assert next(row for row in selected if row["symbol"] == "NO_V3")["prefilter_score"] > 0.0


def test_attach_label_requires_next_common_day_and_blocks_limit_up_entry() -> None:
    trading_days = [f"2026-08-{day:02d}" for day in range(1, 8)]
    bars = {
        "600000.SH": [
            {"day": day, "close": close}
            for day, close in zip(trading_days, [10.0, 11.0, 11.1, 11.2, 11.3, 11.4, 11.5], strict=True)
        ]
    }
    indices = {"600000.SH": {row["day"]: index for index, row in enumerate(bars["600000.SH"])}}
    row = {"signal_day": trading_days[0], "symbol": "600000.SH", "signal_close": 10.0}
    labeled = _attach_label(
        row,
        bars=bars,
        indices=indices,
        trading_days=trading_days,
        trading_day_indices={day: index for index, day in enumerate(trading_days)},
    )
    assert labeled["entry_status"] == "blocked_limit_up_like"
    assert labeled["net_return_5d"] is None


def _training_row(index: int, *, label_day: str) -> dict[str, Any]:
    row = {name: ((index % (position + 7)) - 3.0) / 10.0 for position, name in enumerate(FEATURE_NAMES)}
    row.update(
        {
            "signal_day": "2026-01-01",
            "entry_status": "tradable_research_proxy",
            "net_return_5d": ((index % 9) - 4) / 100.0,
            "downside_label": index % 4 == 0,
            "label_available_day": label_day,
        }
    )
    return row


def test_fit_excludes_labels_available_after_fit_day() -> None:
    design = {
        "model": {
            "minimum_training_rows": 1000,
            "maximum_training_rows": 30000,
            "recovery_head": {"l2_penalty": 10.0},
            "risk_head": {"l2_penalty": 10.0},
        }
    }
    rows = [_training_row(index, label_day="2026-06-25") for index in range(1000)]
    future = deepcopy(rows[0])
    future["label_available_day"] = "2026-06-27"
    rows.append(future)
    model = fit_opportunity_model(rows, fit_day="2026-06-26", design=design)
    assert model.training_row_count == 1000
    assert model.maximum_label_available_day == "2026-06-25"


def test_hotspot_classifier_uses_three_percent_tail_label_and_causal_rows() -> None:
    design = {
        "model": {
            "minimum_training_rows": 1000,
            "maximum_training_rows": 30000,
            "hotspot_head": {"l2_penalty": 10.0},
            "risk_head": {"l2_penalty": 10.0},
        }
    }
    rows = [_training_row(index, label_day="2026-06-25") for index in range(1000)]
    model = fit_hotspot_classifier(rows, fit_day="2026-06-26", design=design)
    expected_rate = sum(float(row["net_return_5d"]) >= 0.03 for row in rows) / len(rows)
    assert model.training_row_count == 1000
    assert model.hotspot_positive_rate == expected_rate
