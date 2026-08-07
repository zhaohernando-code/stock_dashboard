from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ashare_evidence.external_context_global_market_research import (
    build_research_snapshot,
    load_research_snapshot,
    market_state_by_decision_date,
    write_research_snapshot,
)


def _rows(code: str, closes: list[float], *, start_day: int = 1) -> list[dict[str, object]]:
    return [
        {
            "ts_code": code,
            "trade_date": f"202401{start_day + index:02d}",
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "vol": 100,
        }
        for index, close in enumerate(closes)
    ]


def test_research_snapshot_is_digest_verified_and_uses_conservative_availability(tmp_path: Path) -> None:
    rows = {code: _rows(code, [100.0, 101.0]) for code in ("SPX", "IXIC", "HSI", "HKTECH")}
    payload = build_research_snapshot(
        rows_by_instrument=rows,
        retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
        source_endpoint="https://example.invalid",
    )
    path = tmp_path / "snapshot.json"
    write_research_snapshot(path, payload)
    assert load_research_snapshot(path) == payload
    spx = next(row for row in payload["records"] if row["instrument_id"] == "SPX")
    hsi = next(row for row in payload["records"] if row["instrument_id"] == "HSI")
    assert spx["available_at"].startswith("2024-01-02T08:00:00")
    assert hsi["available_at"].startswith("2024-01-01T18:00:00")
    assert payload["provider_revision_id_available"] is False


def test_market_state_never_uses_same_day_us_close() -> None:
    rows = {code: _rows(code, [100.0 + index for index in range(22)]) for code in ("SPX", "HSI")}
    rows["IXIC"] = _rows("IXIC", [100.0 + 2 * index for index in range(22)])
    rows["HKTECH"] = _rows("HKTECH", [100.0 + 3 * index for index in range(22)])
    payload = build_research_snapshot(
        rows_by_instrument=rows,
        retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
        source_endpoint="https://example.invalid",
    )
    states = market_state_by_decision_date(payload["records"], decision_dates=[date(2024, 1, 22)])
    state = states["2024-01-22"]
    assert state["instruments"]["SPX"]["observation_date"] == "2024-01-21"
    assert state["instruments"]["HSI"]["observation_date"] == "2024-01-22"
    assert state["tech_relative_20d"] > 0


def test_snapshot_rejects_duplicate_instrument_dates() -> None:
    duplicate = _rows("SPX", [100.0])[0]
    with pytest.raises(ValueError, match="duplicate instrument date"):
        build_research_snapshot(
            rows_by_instrument={"SPX": [duplicate, duplicate]},
            retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
            source_endpoint="https://example.invalid",
        )


def test_snapshot_retains_but_flags_provider_open_anomaly_when_close_is_valid() -> None:
    row = _rows("SPX", [100.0])[0]
    row.update({"open": 90.0, "low": 99.0, "high": 101.0})
    payload = build_research_snapshot(
        rows_by_instrument={"SPX": [row]},
        retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
        source_endpoint="https://example.invalid",
    )
    assert payload["quality"]["open_outside_high_low_count"] == 1
    assert payload["records"][0]["open_outside_high_low"] is True
