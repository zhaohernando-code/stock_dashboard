from __future__ import annotations

from datetime import timedelta
from time import perf_counter

from ashare_evidence.db import init_database, session_scope, utcnow
from ashare_evidence.frontend_projections import (
    get_ready_frontend_projection_payload,
    home_shell_projection_key,
    operations_summary_projection_key,
    refresh_frontend_projections,
    stable_payload_fingerprint,
    upsert_frontend_projection,
)
from ashare_evidence.models import FrontendProjection
from ashare_evidence.operations import annotate_operations_summary_endpoint_metrics
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


def test_home_shell_projection_materializes_account_shell_payload() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    with session_scope(database_url) as session:
        result = refresh_frontend_projections(
            session,
            projection="home_shell",
            target_login="root",
        )
        session.flush()
        payload = get_ready_frontend_projection_payload(
            session,
            home_shell_projection_key(target_login="root"),
            target_login="root",
        )

    assert result["status"] == "ok"
    assert result["refreshed"][0]["projection_group"] == "home"
    assert result["refreshed"][0]["target_login"] == "root"
    assert payload is not None
    assert {item["symbol"] for item in payload["watchlist"]["items"]} == {"600519.SH", "300750.SZ"}
    assert payload["candidates"]["items"]
    assert payload["glossary"]
    assert payload["scheduled_refresh_status"] is None


def test_operations_summary_endpoint_metrics_replace_full_dashboard_metrics() -> None:
    payload = {
        "overview": {
            "launch_readiness": {
                "status": "closed_beta_ready",
                "blocking_gate_count": 0,
                "warning_gate_count": 1,
                "recommended_next_gate": "刷新与性能预算",
            }
        },
        "launch_gates": [
            {
                "gate": "刷新与性能预算",
                "threshold": "stock <= 250ms，operations <= 320ms，payload 不超预算。",
                "current_value": "stock 90.1ms / ops 829.2ms / ops payload 2086.6kb",
                "status": "warn",
            }
        ],
        "performance_thresholds": [
            {
                "metric": "模拟交易运营面板构建延迟",
                "unit": "ms",
                "target": 320.0,
                "observed": 829.2,
                "status": "warn",
                "note": "full dashboard",
            }
        ],
    }

    annotated = annotate_operations_summary_endpoint_metrics(payload, started_at=perf_counter())

    assert [item["metric"] for item in annotated["performance_thresholds"]] == [
        "运营复盘 summary API 延迟",
        "运营复盘 summary payload 体积",
    ]
    assert "ops 829.2ms" not in annotated["launch_gates"][0]["current_value"]
    assert annotated["launch_gates"][0]["status"] == "pass"
    assert annotated["overview"]["launch_readiness"]["warning_gate_count"] == 0
