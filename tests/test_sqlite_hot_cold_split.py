from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ashare_evidence.db import (
    get_market_history_database_url,
    get_research_archive_database_url,
    init_database,
    session_scope,
)
from ashare_evidence.lineage import build_lineage
from ashare_evidence.market_history_repository import MarketHistoryRepository
from ashare_evidence.models import MarketBar, ShortpickExperimentRun, Stock
from ashare_evidence.sqlite_hot_cold_split import migrate_sqlite_hot_cold_split


def _lineage(payload: object, source_uri: str) -> dict[str, str]:
    return build_lineage(
        payload,
        source_uri=source_uri,
        license_tag="test",
        usage_scope="internal",
        redistribution_scope="none",
    )


def test_cold_database_urls_default_to_source_sidecars(tmp_path) -> None:
    source_url = f"sqlite:///{tmp_path / 'ashare_dashboard.db'}"

    assert get_market_history_database_url(base_database_url=source_url).endswith("/ashare_market_history.db")
    assert get_research_archive_database_url(base_database_url=source_url).endswith("/ashare_research_archive.db")


def test_readonly_session_rejects_writes(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'readonly.db'}"
    init_database(database_url)

    with session_scope(database_url, readonly=True) as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
        with pytest.raises(OperationalError):
            session.execute(text("CREATE TABLE readonly_probe (id INTEGER)"))


def test_sqlite_hot_cold_split_migrates_and_verifies_idempotently(tmp_path) -> None:
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    market_history_url = f"sqlite:///{tmp_path / 'ashare_market_history.db'}"
    research_archive_url = f"sqlite:///{tmp_path / 'ashare_research_archive.db'}"
    init_database(source_url)
    with session_scope(source_url) as session:
        stock = Stock(
            symbol="600519.SH",
            ticker="600519",
            exchange="SH",
            name="贵州茅台",
            provider_symbol="600519.SH",
            listed_date=date(2001, 8, 27),
            status="active",
            profile_payload={},
            **_lineage({"symbol": "600519.SH"}, "test://stock/600519.SH"),
        )
        session.add(stock)
        session.flush()
        session.add_all(
            [
                MarketBar(
                    bar_key="bar-600519-1d",
                    stock_id=stock.id,
                    timeframe="1d",
                    observed_at=datetime(2026, 6, 24, 7, 0, tzinfo=UTC),
                    open_price=100.0,
                    high_price=102.0,
                    low_price=99.0,
                    close_price=101.0,
                    volume=1000.0,
                    amount=101000.0,
                    turnover_rate=1.0,
                    raw_payload={"source": "test"},
                    **_lineage({"bar": "1d"}, "test://bar/600519/1d"),
                ),
                MarketBar(
                    bar_key="bar-600519-5min",
                    stock_id=stock.id,
                    timeframe="5min",
                    observed_at=datetime(2026, 6, 24, 7, 5, tzinfo=UTC),
                    open_price=101.0,
                    high_price=102.0,
                    low_price=100.0,
                    close_price=101.5,
                    volume=100.0,
                    amount=10150.0,
                    turnover_rate=0.1,
                    raw_payload={"source": "test"},
                    **_lineage({"bar": "5min"}, "test://bar/600519/5min"),
                ),
                ShortpickExperimentRun(
                    run_key="shortpick-run-1",
                    run_date=date(2026, 6, 24),
                    prompt_version="test",
                    information_mode="sealed",
                    status="completed",
                    trigger_source="unit_test",
                    started_at=datetime(2026, 6, 24, 8, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 6, 24, 8, 1, tzinfo=UTC),
                    model_config={},
                    summary_payload={"picked": 1},
                ),
            ]
        )

    first = migrate_sqlite_hot_cold_split(
        source_database_url=source_url,
        market_history_database_url=market_history_url,
        research_archive_database_url=research_archive_url,
    )
    second = migrate_sqlite_hot_cold_split(
        source_database_url=source_url,
        market_history_database_url=market_history_url,
        research_archive_database_url=research_archive_url,
    )
    verify = migrate_sqlite_hot_cold_split(
        source_database_url=source_url,
        market_history_database_url=market_history_url,
        research_archive_database_url=research_archive_url,
        verify_only=True,
    )

    assert first["passed"] is True
    assert second["passed"] is True
    assert verify["passed"] is True
    assert verify["market_checks"]["1d"]["target_count"] == 1
    with sqlite3.connect((tmp_path / "ashare_market_history.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM market_bar_history").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM market_bar_history WHERE timeframe = '5min'").fetchone()[0] == 0
    repository = MarketHistoryRepository(market_history_url)
    bars = repository.list_bars(symbol="600519.SH")
    assert [bar.bar_key for bar in bars] == ["bar-600519-1d"]
    assert all(not foreign_keys for foreign_keys in repository.foreign_key_tables().values())
    with sqlite3.connect((tmp_path / "ashare_research_archive.db")) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM research_archive_rows WHERE source_table = 'shortpick_experiment_runs'"
            ).fetchone()[0]
            == 1
        )
