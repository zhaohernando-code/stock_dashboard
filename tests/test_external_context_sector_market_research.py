from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from ashare_evidence.external_context_sector_market_research import (
    SUBINDUSTRY_TO_SW_L1,
    _date_chunks,
    acquire_tushare_sector_market_research_snapshot,
)


def test_date_chunks_are_non_overlapping_and_cover_bounds() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC).date()
    end = datetime(2025, 5, 1, tzinfo=UTC).date()
    chunks = _date_chunks(start, end, days=30)
    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert (current[0] - previous[1]).days == 1


def test_sector_acquisition_retries_empty_transport_response() -> None:
    session = SimpleNamespace(
        scalar=lambda _query: SimpleNamespace(access_token="token", base_url="https://example.test", enabled=True)
    )
    sectors = list(SUBINDUSTRY_TO_SW_L1)
    classification_rows = [
        [f"801{index:03d}.SI", name, "L1", f"801{index:03d}", "1", "0", "SW2021"]
        for index, name in enumerate(sectors)
    ]
    daily_rows = [
        [f"801{index:03d}.SI", "20260102", name, 100, 99, 102, 101, 1, 1, 10, 1000, 10, 1, 100, 200]
        for index, name in enumerate(sectors)
    ]
    calls = 0

    def request_fn(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        if kwargs["api_name"] == "index_classify":
            return {
                "code": 0,
                "data": {
                    "fields": ["index_code", "industry_name", "level", "industry_code", "is_pub", "parent_code", "src"],
                    "items": classification_rows,
                },
            }
        return {
            "code": 0,
            "data": {
                "fields": [
                    "ts_code", "trade_date", "name", "open", "low", "high", "close", "change", "pct_change",
                    "vol", "amount", "pe", "pb", "float_mv", "total_mv",
                ],
                "items": daily_rows,
            },
        }

    snapshot = acquire_tushare_sector_market_research_snapshot(
        session,  # type: ignore[arg-type]
        start=date(2026, 1, 2),
        end=date(2026, 1, 2),
        retrieved_at=datetime(2026, 1, 5, tzinfo=UTC),
        request_fn=request_fn,
    )
    assert calls == 3
    assert snapshot["quality"]["record_count"] == len(sectors)
