from __future__ import annotations

from datetime import date, datetime

from ashare_evidence.pit_source_readiness_audit import _interpretation, _source_status, _stock_coverage_blocker


def test_source_status_blocks_empty_source() -> None:
    status, blockers = _source_status(
        row_count=0,
        min_observed_at=None,
        max_observed_at=None,
        observed_start=date(2023, 6, 13),
        observed_end=date(2026, 5, 26),
        min_coverage_ratio=0.9,
        known_existing=False,
    )

    assert status == "blocked_empty"
    assert blockers == ["pit_source_readiness:no_rows"]


def test_source_status_marks_new_full_window_source_ready() -> None:
    status, blockers = _source_status(
        row_count=100,
        min_observed_at=datetime(2023, 6, 1),
        max_observed_at=datetime(2026, 6, 1),
        observed_start=date(2023, 6, 13),
        observed_end=date(2026, 5, 26),
        min_coverage_ratio=0.9,
        known_existing=False,
    )

    assert status == "ready_new_pit_source"
    assert blockers == []


def test_interpretation_requires_additional_ready_source() -> None:
    message = _interpretation([])

    assert "No additional historical PIT source" in message
    assert "another recipe over existing fields" in message


def test_stock_coverage_blocker_requires_broad_cross_section() -> None:
    blocker = _stock_coverage_blocker(
        4 / 3262,
        min_coverage_ratio=0.9,
        blocker_id="pit_source_readiness:feature_snapshot_stock_coverage_below_gate",
    )

    assert blocker == "pit_source_readiness:feature_snapshot_stock_coverage_below_gate"
