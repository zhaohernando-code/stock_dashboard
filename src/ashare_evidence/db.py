from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path("data/ashare_dashboard.db")
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_database_url(explicit: str | None = None) -> str:
    return explicit or os.getenv("ASHARE_DATABASE_URL") or DEFAULT_DB_URL


def _prepare_sqlite_parent(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str | None = None) -> Engine:
    resolved = get_database_url(database_url)
    engine = _ENGINE_CACHE.get(resolved)
    if engine is None:
        _prepare_sqlite_parent(resolved)
        connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
        engine = create_engine(resolved, future=True, connect_args=connect_args)
        _ENGINE_CACHE[resolved] = engine
    return engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    resolved = get_database_url(database_url)
    factory = _SESSION_FACTORY_CACHE.get(resolved)
    if factory is None:
        factory = sessionmaker(bind=get_engine(resolved), autoflush=False, autocommit=False)
        _SESSION_FACTORY_CACHE[resolved] = factory
    return factory


def init_database(database_url: str | None = None) -> Engine:
    from ashare_evidence import models  # noqa: F401

    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
