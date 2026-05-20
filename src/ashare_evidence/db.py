from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path("data/ashare_dashboard.db")
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def utcnow() -> datetime:
    return datetime.now(UTC)


def align_datetime_timezone(value: datetime | None, *, reference: datetime) -> datetime | None:
    if value is None:
        return None
    if reference.tzinfo is None:
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    if value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo)
    return value.astimezone(reference.tzinfo)


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
        connect_args = {"check_same_thread": False, "timeout": 30} if resolved.startswith("sqlite") else {}
        engine = create_engine(resolved, future=True, connect_args=connect_args)
        if resolved.startswith("sqlite"):
            @event.listens_for(engine, "connect")
            def _set_sqlite_busy_timeout(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
                dbapi_connection.execute("PRAGMA busy_timeout=30000")

        _ENGINE_CACHE[resolved] = engine
    return engine


def preflight_database_writable(database_url: str | None = None) -> None:
    """Raise RuntimeError early if the SQLite database is not writable."""
    resolved_url = str(get_engine(database_url).url.render_as_string(hide_password=False))
    if not resolved_url.startswith("sqlite:///") or resolved_url == "sqlite:///:memory:":
        return
    try:
        with get_engine(database_url).connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            connection.exec_driver_sql("CREATE TABLE __ashare_write_preflight_probe (id INTEGER)")
            connection.exec_driver_sql("DROP TABLE __ashare_write_preflight_probe")
            connection.exec_driver_sql("ROLLBACK")
    except OperationalError as exc:
        raise RuntimeError(
            "database write preflight failed; this refresh needs a writable SQLite database and writable parent "
            f"directory. database_url={resolved_url!r}. Original error: {exc}"
        ) from exc


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    resolved = get_database_url(database_url)
    factory = _SESSION_FACTORY_CACHE.get(resolved)
    if factory is None:
        factory = sessionmaker(bind=get_engine(resolved), autoflush=False, autocommit=False, expire_on_commit=False)
        _SESSION_FACTORY_CACHE[resolved] = factory
    return factory


def init_database(database_url: str | None = None) -> Engine:
    from ashare_evidence import models  # noqa: F401
    from ashare_evidence.account_space import ROOT_ACCOUNT_LOGIN
    from ashare_evidence.models import (
        AccountSpace,
        AppSetting,
        WatchlistEntry,
        WatchlistFollow,
    )

    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    _run_schema_migrations(engine)
    with Session(engine) as session:
        marker = session.scalar(select(AppSetting).where(AppSetting.setting_key == "multi_account_isolation_v1_migration"))
        if marker is None:
            now = utcnow()
            root_space = session.get(AccountSpace, ROOT_ACCOUNT_LOGIN)
            if root_space is None:
                session.add(
                    AccountSpace(
                        account_login=ROOT_ACCOUNT_LOGIN,
                        role_snapshot="root",
                        first_seen_at=now,
                        last_seen_at=now,
                        last_acted_at=now,
                        created_by_root=False,
                        metadata_payload={"migration": "multi_account_isolation_v1"},
                    )
                )
            for entry in session.scalars(select(WatchlistEntry)).all():
                existing = session.scalar(
                    select(WatchlistFollow).where(
                        WatchlistFollow.account_login == ROOT_ACCOUNT_LOGIN,
                        WatchlistFollow.symbol == entry.symbol,
                    )
                )
                if existing is not None:
                    continue
                removed_at = entry.updated_at if entry.status != "active" else None
                session.add(
                    WatchlistFollow(
                        account_login=ROOT_ACCOUNT_LOGIN,
                        symbol=entry.symbol,
                        status=entry.status,
                        source_kind=entry.source_kind,
                        added_at=entry.created_at,
                        removed_at=removed_at,
                        last_actor_login=ROOT_ACCOUNT_LOGIN,
                        follow_payload={"migrated_from_watchlist_entries": True},
                        created_at=entry.created_at,
                        updated_at=entry.updated_at,
                    )
                )
            session.execute(
                text(
                    "UPDATE simulation_sessions SET owner_login = COALESCE(owner_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE paper_portfolios SET owner_login = COALESCE(owner_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE paper_orders SET owner_login = COALESCE(owner_login, :root), "
                    "actor_login = COALESCE(actor_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = '' OR actor_login IS NULL OR actor_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE paper_fills SET owner_login = COALESCE(owner_login, :root), "
                    "actor_login = COALESCE(actor_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = '' OR actor_login IS NULL OR actor_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.execute(
                text(
                    "UPDATE simulation_events SET owner_login = COALESCE(owner_login, :root), "
                    "actor_login = COALESCE(actor_login, :root) "
                    "WHERE owner_login IS NULL OR owner_login = '' OR actor_login IS NULL OR actor_login = ''"
                ),
                {"root": ROOT_ACCOUNT_LOGIN},
            )
            session.add(
                AppSetting(
                    setting_key="multi_account_isolation_v1_migration",
                    description="Marks the v1 watchlist/simulation account-space migration as applied.",
                    setting_value={"applied_at": now.isoformat(), "root_account_login": ROOT_ACCOUNT_LOGIN},
                )
            )
            session.commit()
    return engine


def _run_schema_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "frontend_projections" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS frontend_projections ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "projection_key VARCHAR(128) NOT NULL, "
                    "projection_group VARCHAR(64) NOT NULL, "
                    "target_login VARCHAR(128), "
                    "status VARCHAR(32) NOT NULL DEFAULT 'ready', "
                    "version VARCHAR(32) NOT NULL, "
                    "generated_at DATETIME NOT NULL, "
                    "expires_at DATETIME, "
                    "source_fingerprint VARCHAR(64) NOT NULL, "
                    "payload JSON NOT NULL, "
                    "metadata_payload JSON NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL, "
                    "CONSTRAINT uq_frontend_projection_key UNIQUE (projection_key)"
                    ")"
                )
            )
    if "model_api_keys" in existing_tables:
        existing_columns = {item["name"] for item in inspector.get_columns("model_api_keys")}
        if "account_login" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(text("ALTER TABLE model_api_keys RENAME TO model_api_keys_legacy_account_scope"))
                conn.execute(
                    text(
                        "CREATE TABLE model_api_keys ("
                        "id INTEGER NOT NULL PRIMARY KEY, "
                        "account_login VARCHAR(128) NOT NULL DEFAULT 'root', "
                        "name VARCHAR(64) NOT NULL, "
                        "provider_name VARCHAR(32) NOT NULL, "
                        "model_name VARCHAR(128) NOT NULL, "
                        "base_url VARCHAR(255) NOT NULL, "
                        "api_key TEXT NOT NULL, "
                        "enabled BOOLEAN NOT NULL, "
                        "is_default BOOLEAN NOT NULL, "
                        "priority INTEGER NOT NULL, "
                        "last_status VARCHAR(16) NOT NULL, "
                        "last_error TEXT, "
                        "last_checked_at DATETIME, "
                        "metadata_payload JSON NOT NULL, "
                        "created_at DATETIME NOT NULL, "
                        "updated_at DATETIME NOT NULL, "
                        "CONSTRAINT uq_model_api_key_account_name UNIQUE (account_login, name)"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO model_api_keys ("
                        "id, account_login, name, provider_name, model_name, base_url, api_key, enabled, "
                        "is_default, priority, last_status, last_error, last_checked_at, metadata_payload, "
                        "created_at, updated_at"
                        ") "
                        "SELECT id, 'root', name, provider_name, model_name, base_url, api_key, enabled, "
                        "is_default, priority, last_status, last_error, last_checked_at, metadata_payload, "
                        "created_at, updated_at "
                        "FROM model_api_keys_legacy_account_scope"
                    )
                )
                conn.execute(text("DROP TABLE model_api_keys_legacy_account_scope"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
    column_specs = {
        "paper_portfolios": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "paper_orders": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
            "actor_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "paper_fills": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
            "actor_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "simulation_sessions": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
        "simulation_events": {
            "owner_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
            "actor_login": "VARCHAR(128) NOT NULL DEFAULT 'root'",
        },
    }
    for table_name, columns in column_specs.items():
        existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
        for column_name, ddl in columns.items():
            if column_name not in existing_columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_model_api_keys_account_login ON model_api_keys(account_login)",
        "CREATE INDEX IF NOT EXISTS ix_model_api_keys_name ON model_api_keys(name)",
        "CREATE INDEX IF NOT EXISTS ix_model_api_keys_provider_name ON model_api_keys(provider_name)",
        "CREATE INDEX IF NOT EXISTS ix_model_api_keys_priority ON model_api_keys(priority)",
        "CREATE INDEX IF NOT EXISTS idx_paper_portfolios_owner_login ON paper_portfolios(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_orders_owner_login ON paper_orders(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_orders_actor_login ON paper_orders(actor_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_fills_owner_login ON paper_fills(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_paper_fills_actor_login ON paper_fills(actor_login)",
        "CREATE INDEX IF NOT EXISTS idx_simulation_sessions_owner_login ON simulation_sessions(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_simulation_events_owner_login ON simulation_events(owner_login)",
        "CREATE INDEX IF NOT EXISTS idx_simulation_events_actor_login ON simulation_events(actor_login)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_projection_key ON frontend_projections(projection_key)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_projection_group ON frontend_projections(projection_group)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_target_login ON frontend_projections(target_login)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_status ON frontend_projections(status)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_generated_at ON frontend_projections(generated_at)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_expires_at ON frontend_projections(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_frontend_projections_source_fingerprint ON frontend_projections(source_fingerprint)",
    ]
    with engine.begin() as conn:
        for statement in index_statements:
            conn.execute(text(statement))


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
