from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.shortpick_strategy_lab_v3_projection import (
    V3BenchmarkDataUnavailableError,
    _require_projection_benchmark_features,
    ensure_v3_benchmark_data,
)


def _seed_benchmark_history(session, *, signal_date: date, day_count: int = 20) -> Stock:
    benchmark = Stock(
        symbol="000300.SH",
        ticker="000300",
        exchange="SH",
        name="沪深300",
        provider_symbol="000300.SH",
        listed_date=date(2005, 4, 8),
        status="active",
        profile_payload={"industry": "benchmark"},
        license_tag="test",
        usage_scope="internal-test",
        redistribution_scope="none",
        source_uri="test://stock/000300.SH",
        lineage_hash=compute_lineage_hash({"symbol": "000300.SH"}),
    )
    session.add(benchmark)
    session.flush()
    for offset in range(day_count, 0, -1):
        trade_day = signal_date - timedelta(days=offset)
        close_price = 100.0 + day_count - offset
        session.add(
            MarketBar(
                bar_key=f"bar-000300-1d-{trade_day:%Y%m%d}",
                stock_id=benchmark.id,
                timeframe="1d",
                observed_at=datetime(trade_day.year, trade_day.month, trade_day.day, 15, 0, tzinfo=UTC),
                open_price=close_price,
                high_price=close_price + 1,
                low_price=close_price - 1,
                close_price=close_price,
                volume=1_000.0,
                amount=2_000.0,
                raw_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://bar/000300.SH/{trade_day:%Y%m%d}",
                lineage_hash=compute_lineage_hash({"symbol": "000300.SH", "trade_day": trade_day.isoformat()}),
            )
        )
    session.flush()
    return benchmark


def test_missing_signal_day_benchmark_is_fetched_automatically(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'v3-projection.db'}"
    init_database(database_url)
    signal_date = date(2026, 1, 21)

    with session_scope(database_url) as session:
        benchmark = _seed_benchmark_history(session, signal_date=signal_date)

        def sync_benchmarks(active_session, *, required_through):
            assert required_through == signal_date
            active_session.add(
                MarketBar(
                    bar_key=f"bar-000300-1d-{signal_date:%Y%m%d}",
                    stock_id=benchmark.id,
                    timeframe="1d",
                    observed_at=datetime(
                        signal_date.year,
                        signal_date.month,
                        signal_date.day,
                        15,
                        0,
                        tzinfo=UTC,
                    ),
                    open_price=120.0,
                    high_price=121.0,
                    low_price=119.0,
                    close_price=120.0,
                    volume=1_000.0,
                    amount=2_000.0,
                    raw_payload={"provider_name": "test-auto-sync"},
                    license_tag="test",
                    usage_scope="internal-test",
                    redistribution_scope="none",
                    source_uri=f"test://bar/000300.SH/{signal_date:%Y%m%d}",
                    lineage_hash=compute_lineage_hash(
                        {"symbol": "000300.SH", "trade_day": signal_date.isoformat()}
                    ),
                )
            )
            return {"status": "ok", "primary_ready": True}

        monkeypatch.setattr(
            "ashare_evidence.shortpick_strategy_lab_v3_projection.sync_benchmark_index_bars",
            sync_benchmarks,
        )
        payload = ensure_v3_benchmark_data(session, signal_date=signal_date)

        stored = session.scalar(
            select(MarketBar).where(
                MarketBar.stock_id == benchmark.id,
                MarketBar.observed_at
                == datetime(signal_date.year, signal_date.month, signal_date.day, 15, 0, tzinfo=UTC),
            )
        )

    assert payload["status"] == "auto_repaired"
    assert payload["ready"] is True
    assert payload["sync_attempt_count"] == 1
    assert payload["bar_count_at_or_before_signal"] == 21
    assert stored is not None


def test_benchmark_missing_after_automatic_retries_blocks_projection(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'v3-projection.db'}"
    init_database(database_url)
    signal_date = date(2026, 1, 21)

    monkeypatch.setattr(
        "ashare_evidence.shortpick_strategy_lab_v3_projection.sync_benchmark_index_bars",
        lambda session, *, required_through: {"status": "error", "primary_ready": False},
    )
    with session_scope(database_url) as session:
        _seed_benchmark_history(session, signal_date=signal_date)
        with pytest.raises(V3BenchmarkDataUnavailableError, match="benchmark_signal_day_missing"):
            ensure_v3_benchmark_data(session, signal_date=signal_date, sync_attempts=1)


def test_projection_never_coerces_missing_benchmark_return_to_zero() -> None:
    missing = {
        "symbol": "600001.SH",
        "feature_values": {"regime": {"benchmark_return_20d": None}},
    }
    actual_zero = {
        "symbol": "600002.SH",
        "feature_values": {"regime": {"benchmark_return_20d": 0.0}},
    }

    with pytest.raises(V3BenchmarkDataUnavailableError, match="affected_rows=1"):
        _require_projection_benchmark_features([missing, actual_zero], signal_date=date(2026, 1, 21))
    _require_projection_benchmark_features([actual_zero], signal_date=date(2026, 1, 21))
