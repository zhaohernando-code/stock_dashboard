from __future__ import annotations

import sqlite3
import threading
import time

from sqlalchemy import text

from ashare_evidence.db import get_engine


def test_sqlite_engine_uses_busy_timeout(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'busy-timeout.db'}"
    engine = get_engine(database_url)

    with engine.connect() as connection:
        timeout_ms = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert timeout_ms >= 30000


def test_sqlite_engine_enables_wal(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'wal-mode.db'}"
    engine = get_engine(database_url)

    with engine.connect() as connection:
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        synchronous = connection.execute(text("PRAGMA synchronous")).scalar_one()
        autocheckpoint = connection.execute(text("PRAGMA wal_autocheckpoint")).scalar_one()

    assert str(journal_mode).lower() == "wal"
    # synchronous=NORMAL maps to 1
    assert int(synchronous) == 1
    assert int(autocheckpoint) == 1000


def test_wal_reader_not_blocked_by_open_writer(tmp_path) -> None:
    """A held write transaction must not block a concurrent reader under WAL.

    Reproduces the dashboard outage: under the default rollback journal a long
    refresh writer blocks every backend read with "database is locked". Under
    WAL the reader keeps reading a snapshot while the writer holds the lock.
    """
    db_file = tmp_path / "wal-concurrency.db"
    database_url = f"sqlite:///{db_file}"
    engine = get_engine(database_url)

    with engine.begin() as setup:
        setup.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, value INTEGER)"))
        setup.execute(text("INSERT INTO probe (id, value) VALUES (1, 100)"))

    writer_holding = threading.Event()
    reader_done = threading.Event()
    read_value: list[int] = []
    read_error: list[Exception] = []

    def hold_write_lock() -> None:
        # Raw sqlite3 connection so we fully control the open write transaction.
        conn = sqlite3.connect(db_file, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE probe SET value = 200 WHERE id = 1")
            writer_holding.set()
            # Hold the uncommitted write lock until the reader has finished.
            reader_done.wait(timeout=10)
            conn.commit()
        finally:
            conn.close()

    writer = threading.Thread(target=hold_write_lock)
    writer.start()
    try:
        assert writer_holding.wait(timeout=10), "writer never acquired the lock"
        # The reader must succeed quickly (well under busy_timeout) and see the
        # pre-write snapshot value, proving it was not blocked by the writer.
        started = time.monotonic()
        try:
            with engine.connect() as reader:
                read_value.append(int(reader.execute(text("SELECT value FROM probe WHERE id = 1")).scalar_one()))
        except Exception as exc:  # pragma: no cover - failure path
            read_error.append(exc)
        elapsed = time.monotonic() - started
    finally:
        reader_done.set()
        writer.join(timeout=10)

    assert not read_error, f"reader was blocked/errored under WAL: {read_error}"
    assert read_value == [100], "reader should see the committed snapshot, not the open write"
    assert elapsed < 5, f"reader took {elapsed:.2f}s, suggesting it was blocked by the writer"
