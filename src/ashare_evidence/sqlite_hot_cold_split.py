from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.db import get_market_history_database_url, get_research_archive_database_url

MARKET_HISTORY_TABLE = "market_bar_history"
RESEARCH_ARCHIVE_TABLE = "research_archive_rows"
DEFAULT_ARCHIVE_TIMEFRAMES = ("1d",)
COPY_BATCH_SIZE = 10_000
RESEARCH_ARCHIVE_SOURCE_TABLES = (
    "shortpick_experiment_runs",
    "shortpick_model_rounds",
    "shortpick_candidates",
    "shortpick_consensus_snapshots",
    "shortpick_validation_snapshots",
)


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        raise ValueError(f"SQLite file URL required, got {database_url!r}")
    return Path(database_url.removeprefix("sqlite:///")).expanduser()


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    if readonly:
        connection.execute("PRAGMA query_only=ON")
    else:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def _create_market_history_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {MARKET_HISTORY_TABLE} (
            source_market_bar_id INTEGER NOT NULL PRIMARY KEY,
            bar_key TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL,
            ticker TEXT,
            exchange TEXT,
            stock_name TEXT,
            timeframe TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            open_price REAL NOT NULL,
            high_price REAL NOT NULL,
            low_price REAL NOT NULL,
            close_price REAL NOT NULL,
            volume REAL NOT NULL,
            amount REAL NOT NULL,
            turnover_rate REAL,
            adj_factor REAL,
            total_mv REAL,
            circ_mv REAL,
            pe_ttm REAL,
            pb REAL,
            raw_payload TEXT NOT NULL,
            archived_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_market_bar_history_symbol_time
            ON {MARKET_HISTORY_TABLE}(symbol, timeframe, observed_at);
        CREATE INDEX IF NOT EXISTS idx_market_bar_history_timeframe_observed
            ON {MARKET_HISTORY_TABLE}(timeframe, observed_at);
        CREATE INDEX IF NOT EXISTS idx_market_bar_history_bar_key
            ON {MARKET_HISTORY_TABLE}(bar_key);
        """
    )


def _create_research_archive_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {RESEARCH_ARCHIVE_TABLE} (
            source_table TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            logical_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            archived_at TEXT NOT NULL,
            PRIMARY KEY (source_table, source_id)
        );
        CREATE INDEX IF NOT EXISTS idx_research_archive_table_key
            ON {RESEARCH_ARCHIVE_TABLE}(source_table, logical_key);
        CREATE INDEX IF NOT EXISTS idx_research_archive_archived_at
            ON {RESEARCH_ARCHIVE_TABLE}(archived_at);
        """
    )


def _copy_market_history(
    *,
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    timeframes: Iterable[str],
) -> dict[str, Any]:
    _create_market_history_schema(target)
    archived_at = datetime.now(UTC).isoformat()
    copied_by_timeframe: dict[str, int] = {}
    for timeframe in timeframes:
        cursor = source.execute(
            """
            SELECT
                mb.id AS source_market_bar_id,
                mb.bar_key,
                s.symbol,
                s.ticker,
                s.exchange,
                s.name AS stock_name,
                mb.timeframe,
                mb.observed_at,
                mb.open_price,
                mb.high_price,
                mb.low_price,
                mb.close_price,
                mb.volume,
                mb.amount,
                mb.turnover_rate,
                mb.adj_factor,
                mb.total_mv,
                mb.circ_mv,
                mb.pe_ttm,
                mb.pb,
                mb.raw_payload
            FROM market_bars mb
            JOIN stocks s ON s.id = mb.stock_id
            WHERE mb.timeframe = ?
            """,
            (timeframe,),
        )
        copied_count = 0
        while rows := cursor.fetchmany(COPY_BATCH_SIZE):
            target.executemany(
                f"""
                INSERT OR REPLACE INTO {MARKET_HISTORY_TABLE} (
                    source_market_bar_id, bar_key, symbol, ticker, exchange, stock_name, timeframe, observed_at,
                    open_price, high_price, low_price, close_price, volume, amount, turnover_rate, adj_factor,
                    total_mv, circ_mv, pe_ttm, pb, raw_payload, archived_at
                )
                VALUES (
                    :source_market_bar_id, :bar_key, :symbol, :ticker, :exchange, :stock_name, :timeframe, :observed_at,
                    :open_price, :high_price, :low_price, :close_price, :volume, :amount, :turnover_rate, :adj_factor,
                    :total_mv, :circ_mv, :pe_ttm, :pb, :raw_payload, :archived_at
                )
                """,
                [dict(row) | {"archived_at": archived_at} for row in rows],
            )
            copied_count += len(rows)
        copied_by_timeframe[timeframe] = copied_count
    target.commit()
    return {"copied_by_timeframe": copied_by_timeframe, "archived_at": archived_at}


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _logical_key(table_name: str, row: sqlite3.Row) -> str:
    keys = {
        "shortpick_experiment_runs": "run_key",
        "shortpick_model_rounds": "round_key",
        "shortpick_candidates": "candidate_key",
        "shortpick_consensus_snapshots": "snapshot_key",
    }
    if table_name in keys and row[keys[table_name]]:
        return str(row[keys[table_name]])
    if table_name == "shortpick_validation_snapshots":
        return f"candidate:{row['candidate_id']}:horizon:{row['horizon_days']}"
    return str(row["id"])


def _copy_research_archive(*, source: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, Any]:
    _create_research_archive_schema(target)
    archived_at = datetime.now(UTC).isoformat()
    copied_by_table: dict[str, int] = {}
    for table_name in RESEARCH_ARCHIVE_SOURCE_TABLES:
        if not _table_exists(source, table_name):
            copied_by_table[table_name] = 0
            continue
        cursor = source.execute(f"SELECT * FROM {table_name}")
        copied_count = 0
        while rows := cursor.fetchmany(COPY_BATCH_SIZE):
            payloads = [
                {
                    "source_table": table_name,
                    "source_id": int(row["id"]),
                    "logical_key": _logical_key(table_name, row),
                    "payload_json": json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str),
                    "archived_at": archived_at,
                }
                for row in rows
            ]
            target.executemany(
                f"""
                INSERT OR REPLACE INTO {RESEARCH_ARCHIVE_TABLE}
                    (source_table, source_id, logical_key, payload_json, archived_at)
                VALUES
                    (:source_table, :source_id, :logical_key, :payload_json, :archived_at)
                """,
                payloads,
            )
            copied_count += len(payloads)
        copied_by_table[table_name] = copied_count
    target.commit()
    return {"copied_by_table": copied_by_table, "archived_at": archived_at}


def _market_history_verification(
    *,
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    timeframes: Iterable[str],
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for timeframe in timeframes:
        source_row = source.execute(
            """
            SELECT COUNT(*) AS row_count, MIN(observed_at) AS min_observed_at, MAX(observed_at) AS max_observed_at
            FROM market_bars
            WHERE timeframe = ?
            """,
            (timeframe,),
        ).fetchone()
        target_row = target.execute(
            f"""
            SELECT COUNT(*) AS row_count, MIN(observed_at) AS min_observed_at, MAX(observed_at) AS max_observed_at
            FROM {MARKET_HISTORY_TABLE}
            WHERE timeframe = ?
            """,
            (timeframe,),
        ).fetchone()
        checks[timeframe] = {
            "source_count": source_row["row_count"],
            "target_count": target_row["row_count"],
            "source_min_observed_at": source_row["min_observed_at"],
            "target_min_observed_at": target_row["min_observed_at"],
            "source_max_observed_at": source_row["max_observed_at"],
            "target_max_observed_at": target_row["max_observed_at"],
            "passed": dict(source_row) == dict(target_row),
        }
    return checks


def _research_archive_verification(*, source: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for table_name in RESEARCH_ARCHIVE_SOURCE_TABLES:
        source_count = 0
        if _table_exists(source, table_name):
            source_count = source.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()["row_count"]
        target_count = target.execute(
            f"SELECT COUNT(*) AS row_count FROM {RESEARCH_ARCHIVE_TABLE} WHERE source_table = ?",
            (table_name,),
        ).fetchone()["row_count"]
        checks[table_name] = {
            "source_count": source_count,
            "target_count": target_count,
            "passed": source_count == target_count,
        }
    return checks


def migrate_sqlite_hot_cold_split(
    *,
    source_database_url: str,
    market_history_database_url: str | None = None,
    research_archive_database_url: str | None = None,
    timeframes: Iterable[str] = DEFAULT_ARCHIVE_TIMEFRAMES,
    verify_only: bool = False,
) -> dict[str, Any]:
    source_path = sqlite_path_from_url(source_database_url)
    market_history_path = sqlite_path_from_url(
        market_history_database_url or get_market_history_database_url(base_database_url=source_database_url)
    )
    research_archive_path = sqlite_path_from_url(
        research_archive_database_url or get_research_archive_database_url(base_database_url=source_database_url)
    )
    selected_timeframes = tuple(dict.fromkeys(timeframes))
    with _connect(source_path, readonly=True) as source, _connect(market_history_path) as market_target, _connect(
        research_archive_path
    ) as research_target:
        if not verify_only:
            market_copy = _copy_market_history(source=source, target=market_target, timeframes=selected_timeframes)
            research_copy = _copy_research_archive(source=source, target=research_target)
        else:
            _create_market_history_schema(market_target)
            _create_research_archive_schema(research_target)
            market_copy = {"copied_by_timeframe": {}, "archived_at": None}
            research_copy = {"copied_by_table": {}, "archived_at": None}
        market_checks = _market_history_verification(
            source=source,
            target=market_target,
            timeframes=selected_timeframes,
        )
        research_checks = _research_archive_verification(source=source, target=research_target)
    passed = all(item["passed"] for item in market_checks.values()) and all(
        item["passed"] for item in research_checks.values()
    )
    return {
        "status": "ok" if passed else "failed",
        "passed": passed,
        "source_database": str(source_path),
        "market_history_database": str(market_history_path),
        "research_archive_database": str(research_archive_path),
        "market_copy": market_copy,
        "research_copy": research_copy,
        "market_checks": market_checks,
        "research_checks": research_checks,
    }
