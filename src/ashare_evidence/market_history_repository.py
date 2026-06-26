from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ashare_evidence.db import get_market_history_database_url
from ashare_evidence.sqlite_hot_cold_split import MARKET_HISTORY_TABLE, sqlite_path_from_url


@dataclass(frozen=True)
class MarketHistoryBar:
    symbol: str
    timeframe: str
    observed_at: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    amount: float
    source_market_bar_id: int
    bar_key: str


class MarketHistoryRepository:
    """Read-only adapter for the denormalized cold market-history SQLite store."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or get_market_history_database_url()
        self.database_path = sqlite_path_from_url(self.database_url)

    def list_bars(
        self,
        *,
        symbol: str,
        timeframe: str = "1d",
        start_at: datetime | str | None = None,
        end_at: datetime | str | None = None,
        limit: int | None = None,
    ) -> list[MarketHistoryBar]:
        clauses = ["symbol = ?", "timeframe = ?"]
        params: list[object] = [symbol.upper(), timeframe]
        if start_at is not None:
            clauses.append("observed_at >= ?")
            params.append(_datetime_param(start_at))
        if end_at is not None:
            clauses.append("observed_at <= ?")
            params.append(_datetime_param(end_at))
        sql = (
            f"SELECT source_market_bar_id, bar_key, symbol, timeframe, observed_at, open_price, high_price, "
            f"low_price, close_price, volume, amount FROM {MARKET_HISTORY_TABLE} "
            f"WHERE {' AND '.join(clauses)} ORDER BY observed_at"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with _readonly_connection(self.database_path) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            MarketHistoryBar(
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                observed_at=row["observed_at"],
                open_price=float(row["open_price"]),
                high_price=float(row["high_price"]),
                low_price=float(row["low_price"]),
                close_price=float(row["close_price"]),
                volume=float(row["volume"]),
                amount=float(row["amount"]),
                source_market_bar_id=int(row["source_market_bar_id"]),
                bar_key=row["bar_key"],
            )
            for row in rows
        ]

    def foreign_key_tables(self) -> dict[str, list[dict[str, object]]]:
        with _readonly_connection(self.database_path) as connection:
            tables = [
                row["name"]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            ]
            return {table: [dict(row) for row in connection.execute(f"PRAGMA foreign_key_list({table})")] for table in tables}


@contextmanager
def _readonly_connection(path: Path) -> Iterator[sqlite3.Connection]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


def _datetime_param(value: datetime | str) -> str:
    return value.isoformat() if isinstance(value, datetime) else value
