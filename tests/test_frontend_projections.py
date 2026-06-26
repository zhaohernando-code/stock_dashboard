from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from time import perf_counter, sleep
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from ashare_evidence.api import create_app
from ashare_evidence.db import get_engine, init_database, session_scope, utcnow
from ashare_evidence.frontend_projections import (
    SHORTPICK_MODEL_FEEDBACK_PROJECTION_KEY,
    get_ready_frontend_projection_payload,
    home_shell_projection_key,
    operations_summary_projection_key,
    refresh_frontend_projections,
    simulation_workspace_summary_projection_key,
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


def test_database_init_adds_operations_market_bar_covering_index() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)

    with get_engine(database_url).connect() as connection:
        rows = connection.execute(text("PRAGMA index_list('market_bars')")).mappings().all()

    assert any(row["name"] == "idx_market_bars_timeframe_stock_observed" for row in rows)


def test_background_operations_tick_does_not_block_event_loop() -> None:
    api_source = (Path(__file__).resolve().parents[1] / "src" / "ashare_evidence" / "api.py").read_text(
        encoding="utf-8"
    )

    assert "def run_background_operations_tick() -> None:" in api_source
    assert "await asyncio.to_thread(run_background_operations_tick)" in api_source
    assert "run_operations_tick(session)" in api_source
    assert "with session_factory() as session:" in api_source
    assert "OPERATIONS_RESPONSE_CACHE_STALE_GRACE_SECONDS" in api_source


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


def test_operations_summary_api_degrades_without_projection_and_does_not_write(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'projection-api.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with patch("ashare_evidence.api.build_operations_dashboard", side_effect=AssertionError("GET must not rebuild")):
        response = client.get(
            "/dashboard/operations/summary?sample_symbol=300750.SZ",
            headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
        )

    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert response.json()["reason"] == "operations_summary_projection_miss"
    with session_scope(database_url) as session:
        payload = get_ready_frontend_projection_payload(
            session,
            operations_summary_projection_key(target_login="root", sample_symbol="300750.SZ"),
            target_login="root",
        )
        stored = session.query(FrontendProjection).filter_by(
            projection_key=operations_summary_projection_key(target_login="root", sample_symbol="300750.SZ"),
            target_login="root",
        ).one_or_none()

    assert payload is None
    assert stored is None


def test_operations_legacy_get_does_not_run_operations_tick(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'operations-legacy.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with (
        patch("ashare_evidence.api.run_operations_tick", side_effect=AssertionError("GET must stay read-only")),
        patch("ashare_evidence.api.build_operations_dashboard", side_effect=AssertionError("GET must not rebuild")),
    ):
        response = client.get(
            "/dashboard/operations?sample_symbol=300750.SZ",
            headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
        )

    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert response.json()["reason"] == "operations_response_cache_miss"


def test_operations_portfolios_detail_uses_prewarmed_response_cache(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'operations-detail-cache.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with patch.dict("os.environ", {"ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE": "sync"}), client:
        with patch("ashare_evidence.api.build_operations_detail", side_effect=AssertionError("cache should satisfy request")):
            response = client.get(
                "/dashboard/operations/details?section=portfolios&sample_symbol=300750.SZ",
                headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
            )

    assert response.status_code == 200
    assert response.json()["section"] == "portfolios"


def test_operations_replay_detail_uses_prewarmed_response_cache(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'operations-replay-cache.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with patch.dict("os.environ", {"ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE": "sync"}), client:
        with patch("ashare_evidence.api.build_operations_detail", side_effect=AssertionError("cache should satisfy request")):
            response = client.get(
                "/dashboard/operations/details?section=replay&sample_symbol=600519.SH",
                headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
            )

    assert response.status_code == 200
    assert response.json()["section"] == "replay"
    assert "recommendation_replay" in response.json()


def test_operations_detail_hard_expiry_degrades_instead_of_sync_rebuild(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'operations-detail-cache-expiry.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with patch.dict("os.environ", {"ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE": "sync"}), client:
        with (
            patch("ashare_evidence.api.OPERATIONS_RESPONSE_CACHE_TTL_SECONDS", -2.0),
            patch("ashare_evidence.api.OPERATIONS_RESPONSE_CACHE_STALE_GRACE_SECONDS", 0.0),
            patch("ashare_evidence.api.build_operations_detail") as build_detail,
        ):
            response = client.get(
                "/dashboard/operations/details?section=replay&sample_symbol=600519.SH",
                headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
            )

    assert response.status_code == 200
    assert build_detail.call_count == 0
    assert response.json()["degraded"] is True
    assert response.json()["reason"] == "operations_response_cache_miss"


def test_operations_detail_soft_expiry_returns_stale_and_refreshes_in_background(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'operations-detail-soft-expiry.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    fresh_payload = {
        "section": "replay",
        "generated_at": "2026-06-13T00:00:00+08:00",
        "recommendation_replay": [{"summary": "fresh payload from background refresh"}],
    }

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with patch.dict("os.environ", {"ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE": "sync"}), client:
        with (
            patch("ashare_evidence.api.OPERATIONS_RESPONSE_CACHE_TTL_SECONDS", -1.0),
            patch("ashare_evidence.api.OPERATIONS_RESPONSE_CACHE_STALE_GRACE_SECONDS", 120.0),
            patch("ashare_evidence.api.build_operations_detail", return_value=fresh_payload) as build_detail,
        ):
            response = client.get(
                "/dashboard/operations/details?section=replay&sample_symbol=600519.SH",
                headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
            )
            assert response.status_code == 200
            assert response.json().get("recommendation_replay") != fresh_payload["recommendation_replay"]

            deadline = perf_counter() + 2
            refreshed_response = None
            while perf_counter() < deadline:
                refreshed_response = client.get(
                    "/dashboard/operations/details?section=replay&sample_symbol=600519.SH",
                    headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
                )
                if refreshed_response.json().get("recommendation_replay") == fresh_payload["recommendation_replay"]:
                    break
                sleep(0.01)

    assert build_detail.call_count >= 1
    assert refreshed_response is not None
    assert refreshed_response.json()["recommendation_replay"][0]["summary"] == "fresh payload from background refresh"


def test_operations_legacy_get_uses_prewarmed_response_cache(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'operations-legacy-cache.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    with patch.dict("os.environ", {"ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE": "sync"}), client:
        with patch("ashare_evidence.api.build_operations_dashboard", side_effect=AssertionError("cache should satisfy legacy request")):
            response = client.get(
                "/dashboard/operations?sample_symbol=300750.SZ",
                headers={"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"},
            )

    assert response.status_code == 200
    assert "portfolios" in response.json()


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


def test_dashboard_shell_overlays_live_watchlist_on_stale_projection(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'shell-projection.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))
        refresh_frontend_projections(session, projection="home_shell", target_login="root")
        session.commit()

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    headers = {"X-HZ-User-Login": "root", "X-HZ-User-Role": "root"}
    delete_response = client.delete("/watchlist/600519.SH", headers=headers)
    shell_response = client.get("/dashboard/shell", headers=headers)

    assert delete_response.status_code == 200
    assert shell_response.status_code == 200
    assert {item["symbol"] for item in shell_response.json()["watchlist"]["items"]} == {"300750.SZ"}

    with session_scope(database_url) as session:
        stale_payload = get_ready_frontend_projection_payload(
            session,
            home_shell_projection_key(target_login="root"),
            target_login="root",
        )

    assert stale_payload is not None
    assert {item["symbol"] for item in stale_payload["watchlist"]["items"]} == {"600519.SH", "300750.SZ"}


def test_shortpick_model_feedback_projection_materializes_empty_feedback_payload() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)

    with session_scope(database_url) as session:
        result = refresh_frontend_projections(session, projection="shortpick_model_feedback")
        session.flush()
        payload = get_ready_frontend_projection_payload(session, SHORTPICK_MODEL_FEEDBACK_PROJECTION_KEY)

    assert result["status"] == "ok"
    assert result["refreshed"][0]["projection_group"] == "shortpick"
    assert payload is not None
    assert payload["models"] == []
    assert payload["model_groups"] == []
    assert payload["overall"]["run_count"] == 0
    assert payload["overall"]["round_count"] == 0


def test_simulation_workspace_summary_projection_materializes_detail_payload() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    with session_scope(database_url) as session:
        seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))

    with session_scope(database_url) as session:
        result = refresh_frontend_projections(
            session,
            projection="simulation_workspace_summary",
            target_login="root",
        )
        session.flush()
        payload = get_ready_frontend_projection_payload(
            session,
            simulation_workspace_summary_projection_key(target_login="root"),
            target_login="root",
        )

    assert result["status"] == "ok"
    assert result["refreshed"][0]["projection_group"] == "simulation"
    assert payload is not None
    assert payload["section"] == "simulation_workspace"
    assert set(payload["simulation_workspace"]["session"]["watch_symbols"]) == {"600519.SH", "300750.SZ"}
    assert set(payload["simulation_workspace"]["configuration"]["watch_symbols"]) == {"600519.SH", "300750.SZ"}


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
