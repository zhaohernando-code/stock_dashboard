from __future__ import annotations

from datetime import timedelta

from ashare_evidence.db import init_database, session_scope, utcnow
from ashare_evidence.frontend_projections import (
    get_ready_frontend_projection_payload,
    operations_summary_projection_key,
    refresh_frontend_projections,
    stable_payload_fingerprint,
    upsert_frontend_projection,
)
from ashare_evidence.models import FrontendProjection
from tests.fixtures import seed_watchlist_fixture


def test_frontend_projection_upsert_and_ready_read() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    payload = {"items": [{"label": "历史分析结论", "value": 1}]}

    with session_scope(database_url) as session:
        projection = upsert_frontend_projection(
            session,
            "test_projection:v1",
            projection_group="test",
            payload=payload,
            metadata_payload={"source": "unit_test"},
        )
        session.flush()

        assert projection.source_fingerprint == stable_payload_fingerprint(payload)
        assert get_ready_frontend_projection_payload(session, "test_projection:v1") == payload

    with session_scope(database_url) as session:
        stored = session.query(FrontendProjection).filter_by(projection_key="test_projection:v1").one()
        assert stored.projection_group == "test"
        assert stored.metadata_payload == {"source": "unit_test"}


def test_expired_projection_is_not_returned() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    with session_scope(database_url) as session:
        upsert_frontend_projection(
            session,
            "expired_projection:v1",
            projection_group="test",
            payload={"stale": True},
            expires_at=utcnow() - timedelta(seconds=1),
        )
        assert get_ready_frontend_projection_payload(session, "expired_projection:v1") is None


def test_unsupported_frontend_projection_fails_closed() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    with session_scope(database_url) as session:
        try:
            refresh_frontend_projections(session, projection="missing")
        except ValueError as exc:
            assert "Unsupported frontend projection" in str(exc)
        else:
            raise AssertionError("unsupported projection should raise")


def test_operations_summary_projection_materializes_per_symbol_payload() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    with session_scope(database_url) as session:
        result = refresh_frontend_projections(
            session,
            projection="operations_summary",
            target_login="root",
            sample_symbols=["600519.SH"],
        )
        session.flush()
        payload = get_ready_frontend_projection_payload(
            session,
            operations_summary_projection_key(target_login="root", sample_symbol="600519.SH"),
            target_login="root",
        )

    assert result["status"] == "ok"
    assert result["refreshed"][0]["projection_group"] == "operations"
    assert result["refreshed"][0]["target_login"] == "root"
    assert payload is not None
    assert "today_at_a_glance" in payload
    assert "data_quality_summary" in payload
    assert payload["portfolios"] == []
    assert payload["recommendation_replay"] == []
