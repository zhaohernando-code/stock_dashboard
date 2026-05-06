from __future__ import annotations

from sqlalchemy import text

from ashare_evidence.db import get_engine


def test_sqlite_engine_uses_busy_timeout(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'busy-timeout.db'}"
    engine = get_engine(database_url)

    with engine.connect() as connection:
        timeout_ms = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert timeout_ms >= 30000
