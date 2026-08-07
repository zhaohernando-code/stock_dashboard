from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from ashare_evidence.external_context_macro_research import (
    build_macro_research_snapshot,
    macro_state_by_decision_date,
    normalize_macro_rows,
)


def _inputs() -> dict[str, object]:
    fx = [
        {"trade_date": f"202401{day:02d}", "bid_close": 7.0 + day / 1000, "ask_close": 7.002 + day / 1000}
        for day in range(1, 24)
    ]
    treasury = [
        {"date": f"202401{day:02d}", "y2": 4.0 + day / 100, "y10": 4.2 + day / 100}
        for day in range(1, 24)
    ]
    gold = [
        {"trade_date": f"202401{day:02d}", "close": 450.0 + day}
        for day in range(1, 24)
    ]
    fred = {
        "VIXCLS": "observation_date,VIXCLS\n2024-01-01,15.0\n2024-01-02,.\n2024-01-03,16.0\n",
        "DCOILWTICO": "observation_date,DCOILWTICO\n2024-01-01,70.0\n2024-01-03,71.0\n",
    }
    return {"fx_rows": fx, "treasury_rows": treasury, "gold_rows": gold, "fred_csv_by_series": fred}


def test_normalize_macro_rows_has_conservative_pit_availability() -> None:
    rows = normalize_macro_rows(**_inputs(), retrieved_at=datetime(2024, 2, 1, tzinfo=UTC))
    by_key = {(row["series_id"], row["observation_date"]): row for row in rows}
    assert by_key[("USDCNH_MID", "2024-01-01")]["available_at"] == "2024-01-02T08:00:00+08:00"
    assert by_key[("VIXCLS", "2024-01-01")]["available_at"] == "2024-01-03T18:00:00+08:00"
    assert ("VIXCLS", "2024-01-02") not in by_key
    assert by_key[("UST_10Y_MINUS_2Y", "2024-01-01")]["value"] == pytest.approx(0.2)


def test_macro_state_respects_available_at_and_builds_trailing_features() -> None:
    snapshot = build_macro_research_snapshot(
        **_inputs(),
        retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
        tushare_endpoint="https://example.invalid",
    )
    states = macro_state_by_decision_date(
        snapshot["records"], decision_dates=[date(2024, 1, 2), date(2024, 1, 24)]
    )
    assert "VIXCLS" not in states["2024-01-02"]
    assert states["2024-01-24"]["USDCNH_MID"]["return_20d"] is not None
    assert states["2024-01-24"]["SGE_AU9999"]["observation_date"] == "2024-01-23"
    assert snapshot["quality"]["future_available_at_count"] == 0


def test_future_macro_observation_is_rejected() -> None:
    values = _inputs()
    with pytest.raises(ValueError, match="future macro observation"):
        normalize_macro_rows(**values, retrieved_at=datetime(2024, 1, 1, tzinfo=UTC))
