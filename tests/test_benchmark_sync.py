from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from ashare_evidence.benchmark import sync_benchmark_index_bars
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import MarketBar, Stock


def test_benchmark_sync_uses_tushare_before_akshare(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'benchmark.db'}"
    init_database(database_url)
    trade_day = datetime.now(UTC).date()

    monkeypatch.setattr(
        "ashare_evidence.benchmark._tushare_index_rows",
        lambda *args, **kwargs: [
            {
                "date": trade_day.strftime("%Y%m%d"),
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 1_000.0,
                "amount": 2_000.0,
            }
        ],
    )
    monkeypatch.setattr("ashare_evidence.benchmark.akshare_runtime_ready", lambda: False)

    with session_scope(database_url) as session:
        payload = sync_benchmark_index_bars(session)

    with session_scope(database_url) as session:
        benchmark = session.scalar(select(Stock).where(Stock.symbol == "000300.SH"))
        assert benchmark is not None
        bar = session.scalar(
            select(MarketBar).where(
                MarketBar.stock_id == benchmark.id,
                MarketBar.timeframe == "1d",
            )
        )

    assert payload["status"] == "ok"
    assert payload["primary_ready"] is True
    assert payload["symbols"]["000300.SH"]["provider_name"] == "tushare"
    assert payload["symbols"]["000300.SH"]["attempts"] == [
        {
            "provider_name": "tushare",
            "status": "ok",
            "row_count": 1,
            "latest_trade_day": trade_day.isoformat(),
        }
    ]
    assert bar is not None
    assert bar.observed_at.date() == trade_day
    assert bar.close_price == 101.0
    assert bar.raw_payload["provider_name"] == "tushare"
    assert bar.raw_payload["dataset"] == "index_daily"


def test_benchmark_sync_falls_back_to_akshare_after_tushare_error(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'benchmark.db'}"
    init_database(database_url)
    trade_day = datetime.now(UTC).date()

    def fail_tushare(*args, **kwargs):
        raise RuntimeError("temporary Tushare failure")

    monkeypatch.setattr("ashare_evidence.benchmark._tushare_index_rows", fail_tushare)
    monkeypatch.setattr(
        "ashare_evidence.benchmark._akshare_index_rows",
        lambda *args, **kwargs: [
            {
                "date": trade_day.strftime("%Y%m%d"),
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 1_000.0,
                "amount": 2_000.0,
            }
        ],
    )

    with session_scope(database_url) as session:
        payload = sync_benchmark_index_bars(session)

    primary = payload["symbols"]["000300.SH"]
    assert payload["primary_ready"] is True
    assert primary["provider_name"] == "akshare"
    assert primary["attempts"][0]["provider_name"] == "tushare"
    assert primary["attempts"][0]["status"] == "error"
    assert primary["attempts"][1] == {
        "provider_name": "akshare",
        "status": "ok",
        "row_count": 1,
        "latest_trade_day": trade_day.isoformat(),
    }


def test_benchmark_sync_falls_back_when_tushare_rows_are_stale(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'benchmark.db'}"
    init_database(database_url)
    trade_day = datetime.now(UTC).date()
    stale_day = trade_day - timedelta(days=1)
    row = {
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1_000.0,
        "amount": 2_000.0,
    }

    monkeypatch.setattr(
        "ashare_evidence.benchmark._tushare_index_rows",
        lambda *args, **kwargs: [{**row, "date": stale_day.strftime("%Y%m%d")}],
    )
    monkeypatch.setattr(
        "ashare_evidence.benchmark._akshare_index_rows",
        lambda *args, **kwargs: [{**row, "date": trade_day.strftime("%Y%m%d")}],
    )

    with session_scope(database_url) as session:
        payload = sync_benchmark_index_bars(session, required_through=trade_day)

    primary = payload["symbols"]["000300.SH"]
    assert primary["status"] == "ok"
    assert primary["provider_name"] == "akshare"
    assert primary["latest_trade_day"] == trade_day.isoformat()
