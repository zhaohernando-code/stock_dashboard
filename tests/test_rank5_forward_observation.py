from __future__ import annotations

from datetime import date, timedelta

import pytest

from ashare_evidence.rank5_forward_observation import (
    RANK5_FORWARD_BENCHMARK_SYMBOL,
    RANK5_FORWARD_CAPTURE_MODE,
    build_rank5_forward_observation_artifact,
    build_rank5_shadow_observation,
)
from ashare_evidence.rank5_path_quality import PATH_QUALITY_FEATURE_KEYS


def _observation(*, signal_day: date = date(2026, 7, 15), capture_mode: str = RANK5_FORWARD_CAPTURE_MODE):
    candidate = {
        "symbol": "600005.SH",
        "stock_name": "Rank5测试",
        "rank": 5,
        "score": 3.84,
        "path_feature_observation_count": 20,
        **dict.fromkeys(PATH_QUALITY_FEATURE_KEYS, 0.1),
    }
    row = build_rank5_shadow_observation(
        strategy_id="r14-test",
        signal_date=signal_day.isoformat(),
        planned_trade_date=(signal_day + timedelta(days=1)).isoformat(),
        original_pick={"symbol": "600001.SH", "rank": 1, "score": 3.9},
        candidate=candidate,
        inventory_sequence=5,
        shadow_base_eligible=True,
        base_eligibility_reason=None,
    )
    row["paper_source_capture_mode"] = capture_mode
    row["source_candidate_artifact_id"] = f"candidate-{signal_day.isoformat()}"
    return row


def _bars(*, start_day: date, count: int, first_close: float, step: float = 1.0):
    return [
        {"day": start_day + timedelta(days=index), "close": first_close + step * index}
        for index in range(count)
    ]


def test_shadow_observation_key_is_deterministic_and_outcomes_start_null() -> None:
    left = _observation()
    right = _observation()

    assert left["observation_key"] == right["observation_key"]
    assert left["path_feature_complete"] is True
    assert left["selected_by_current_r14"] is False
    assert left["candidate_return_20d"] is None
    assert left["benchmark_return_20d"] is None
    assert left["candidate_excess_return_20d"] is None


def test_pending_window_keeps_all_future_outcomes_null() -> None:
    signal_day = date(2026, 7, 15)
    candidate_bars = _bars(start_day=signal_day + timedelta(days=1), count=20, first_close=100.0)
    artifact = build_rank5_forward_observation_artifact(
        [_observation(signal_day=signal_day)],
        market_bars_by_symbol={
            "600005.SH": candidate_bars,
            RANK5_FORWARD_BENCHMARK_SYMBOL: _bars(
                start_day=signal_day + timedelta(days=1), count=20, first_close=200.0
            ),
        },
        paper_records=[],
        as_of_day=date(2026, 8, 3),
    )

    row = artifact["rows"][0]
    assert row["maturity_status"] == "pending_20d_window"
    assert row["entry_trade_date"] == "2026-07-16"
    assert row["exit_trade_date"] is None
    assert row["candidate_return_20d"] is None
    assert artifact["progress"]["pending_shadow_observation_count"] == 1
    assert artifact["progress"]["premature_future_outcome_count"] == 0


def test_full_window_resolves_candidate_benchmark_and_actual_link() -> None:
    signal_day = date(2026, 7, 15)
    candidate_bars = _bars(start_day=signal_day + timedelta(days=1), count=21, first_close=100.0)
    benchmark_bars = _bars(start_day=signal_day + timedelta(days=1), count=21, first_close=200.0, step=1.0)
    observation = _observation(signal_day=signal_day)
    key = observation["observation_key"]
    artifact = build_rank5_forward_observation_artifact(
        [observation],
        market_bars_by_symbol={
            "600005.SH": candidate_bars,
            RANK5_FORWARD_BENCHMARK_SYMBOL: benchmark_bars,
        },
        paper_records=[
            {"rank5_forward_observation_key": key, "action": "buy"},
            {"rank5_forward_observation_key": key, "action": "sell", "return": 0.12},
        ],
        as_of_day=date(2026, 8, 5),
    )

    row = artifact["rows"][0]
    assert row["maturity_status"] == "matured_20d"
    assert row["candidate_return_20d"] == pytest.approx(0.20)
    assert row["benchmark_return_20d"] == pytest.approx(0.10)
    assert row["candidate_excess_return_20d"] == pytest.approx(0.10)
    assert row["actual_executed"] is True
    assert row["actual_closed"] is True
    assert row["actual_return"] == pytest.approx(0.12)


def test_backfill_is_excluded_and_duplicate_keys_block_data_quality() -> None:
    observation = _observation(capture_mode="synchronized_start_backfill")
    backfill_artifact = build_rank5_forward_observation_artifact(
        [observation],
        market_bars_by_symbol={},
        paper_records=[],
        as_of_day=date(2026, 7, 15),
    )
    assert backfill_artifact["rows"][0]["maturity_status"] == "excluded_not_true_forward_capture"
    assert backfill_artifact["progress"]["forward_base_eligible_count"] == 0

    duplicate = _observation()
    duplicate_artifact = build_rank5_forward_observation_artifact(
        [duplicate, dict(duplicate)],
        market_bars_by_symbol={},
        paper_records=[],
        as_of_day=date(2026, 7, 15),
    )
    assert duplicate_artifact["status"] == "blocked_data_quality"
    assert duplicate_artifact["progress"]["duplicate_observation_key_count"] == 1
    assert duplicate_artifact["progress"]["data_quality_passed"] is False


def test_research_reopen_gate_requires_all_frozen_dimensions() -> None:
    signal_days = [date(2026, 7, day) for day in range(15, 29)]
    for month in range(8, 12):
        signal_days.extend(date(2026, month, day) for day in range(1, 15))
    signal_days.extend(date(2026, 12, day) for day in range(1, 11))
    observations = [_observation(signal_day=signal_day) for signal_day in signal_days]
    market_start = date(2026, 7, 16)
    artifact = build_rank5_forward_observation_artifact(
        observations,
        market_bars_by_symbol={
            "600005.SH": _bars(start_day=market_start, count=240, first_close=100.0, step=0.1),
            RANK5_FORWARD_BENCHMARK_SYMBOL: _bars(
                start_day=market_start,
                count=240,
                first_close=200.0,
                step=0.1,
            ),
        },
        paper_records=[],
        as_of_day=date(2027, 1, 15),
    )

    progress = artifact["progress"]
    assert progress["matured_shadow_observation_count"] == 80
    assert progress["distinct_matured_signal_month_count"] == 6
    assert progress["elapsed_calendar_days"] >= 120
    assert progress["research_reopen_ready"] is True
    assert progress["promotion_evidence_ready"] is False
    assert artifact["status"] == "research_reopen_gate_reached"
