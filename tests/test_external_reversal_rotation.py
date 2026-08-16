from __future__ import annotations

import copy

from ashare_evidence.external_reversal_rotation import (
    _event_metrics,
    build_past_only_reversal_events,
    select_reversal_rotation_day,
)


def _state(*, breadth_5d: float, breadth_20d: float, return_5d: float, return_20d: float) -> dict:
    return {
        "breadth_5d": breadth_5d,
        "breadth_20d": breadth_20d,
        "mean_return_5d": return_5d,
        "mean_return_20d": return_20d,
        "by_sector_name": {},
    }


def test_reversal_event_detection_is_past_only() -> None:
    days = [f"2026-01-{index:02d}" for index in range(1, 9)]
    states = {
        day: _state(
            breadth_5d=0.4 + index * 0.01,
            breadth_20d=0.4,
            return_5d=0.01 + index * 0.002,
            return_20d=0.01,
        )
        for index, day in enumerate(days)
    }
    _, active_before, audit_before = build_past_only_reversal_events(
        signal_days=days,
        sector_states=states,
        minimum_history=3,
        event_threshold=0.0,
        cooldown_signal_days=2,
        active_window_signal_days=2,
    )
    changed_future = copy.deepcopy(states)
    changed_future[days[-1]] = _state(
        breadth_5d=-100.0,
        breadth_20d=100.0,
        return_5d=-100.0,
        return_20d=100.0,
    )
    _, active_after, audit_after = build_past_only_reversal_events(
        signal_days=days,
        sector_states=changed_future,
        minimum_history=3,
        event_threshold=0.0,
        cooldown_signal_days=2,
        active_window_signal_days=2,
    )

    assert active_before.get(days[4]) == active_after.get(days[4])
    assert audit_before[days[4]] == audit_after[days[4]]


def test_event_grouping_uses_cooldown_and_fixed_active_window() -> None:
    days = [f"2026-02-{index:02d}" for index in range(1, 13)]
    states = {
        day: _state(
            breadth_5d=0.5 + (0.2 if index in {4, 5, 10} else index * 0.001),
            breadth_20d=0.5,
            return_5d=0.02 + (0.1 if index in {4, 5, 10} else index * 0.001),
            return_20d=0.02,
        )
        for index, day in enumerate(days)
    }
    events, active, _ = build_past_only_reversal_events(
        signal_days=days,
        sector_states=states,
        minimum_history=3,
        event_threshold=0.5,
        cooldown_signal_days=3,
        active_window_signal_days=2,
    )

    assert all(len(event["active_days"]) == 2 for event in events)
    assert len(active) == len(events) * 2
    assert all(event["start_day"] in active for event in events)


def test_rotation_preserves_rank1_and_allows_at_most_one_new_symbol() -> None:
    day = "2026-01-05"
    original = [
        {"as_of_date": day, "symbol": symbol, "rank": rank, "score": score, "industry_name": industry}
        for rank, (symbol, score, industry) in enumerate(
            [("A", 1.0, "银行"), ("B", 0.9, "银行"), ("C", 0.8, "银行")], start=1
        )
    ]
    inventory = original + [
        {"as_of_date": day, "symbol": "D", "rank": 4, "score": 0.79, "industry_name": "半导体"},
        {"as_of_date": day, "symbol": "E", "rank": 5, "score": 0.78, "industry_name": "半导体"},
    ]
    state = {
        "by_sector_name": {
            "银行": {"relative_5d": -0.1, "relative_20d": 0.0},
            "电子": {"relative_5d": 0.5, "relative_20d": -0.5},
        }
    }

    selected, audit = select_reversal_rotation_day(
        original=original,
        inventory=inventory,
        sector_state=state,
        weight=0.15,
        active_event_id="event-1",
    )

    assert selected[0]["symbol"] == "A"
    assert audit["rank1_preserved"]
    assert len({row["symbol"] for row in selected[1:]} - {"B", "C"}) <= 1


def test_lambda_zero_reproduces_original_rows() -> None:
    original = [
        {"as_of_date": "2026-01-05", "symbol": symbol, "rank": rank, "score": 1.0 - rank / 10}
        for rank, symbol in enumerate(("A", "B", "C"), start=1)
    ]
    selected, audit = select_reversal_rotation_day(
        original=original,
        inventory=original,
        sector_state={"by_sector_name": {}},
        weight=0.0,
        active_event_id="event-1",
    )

    assert selected == original
    assert not audit["changed"]


def test_unchanged_day_uses_frozen_baseline_buy_symbols_when_instrumented() -> None:
    original = [
        {"as_of_date": "2026-01-05", "symbol": symbol, "rank": rank, "score": 1.0 - rank / 10}
        for rank, symbol in enumerate(("A", "B", "C"), start=1)
    ]
    selected, _ = select_reversal_rotation_day(
        original=original,
        inventory=original,
        sector_state={"by_sector_name": {}},
        weight=0.1,
        active_event_id=None,
        baseline_buy_symbols_by_slot={
            ("2026-01-05", 1): {"A"},
            ("2026-01-05", 2): set(),
            ("2026-01-05", 3): {"C"},
        },
    )

    assert [row["shadow_baseline_buy_symbols"] for row in selected] == [["A"], [], ["C"]]


def test_event_metrics_do_not_attribute_inherited_account_path_to_unchanged_event() -> None:
    events = [{"event_id": "event-1", "start_day": "2026-01-01", "trigger_days": ["2026-01-01"]}]
    baseline = {
        "nav_rows": [
            {"day": f"2026-01-{index:02d}", "nav_cny": 100.0}
            for index in range(1, 12)
        ]
    }
    candidate = {
        "nav_rows": [
            {"day": f"2026-01-{index:02d}", "nav_cny": 101.0 + index}
            for index in range(1, 12)
        ]
    }

    rows, summaries = _event_metrics(candidate, baseline, events, changed_event_ids=set())

    assert rows[0]["incremental_return_10d"] != 0.0
    assert summaries["extended"]["observed_event_count_10d"] == 0
    assert summaries["extended"]["mean_incremental_return_10d"] == 0.0
