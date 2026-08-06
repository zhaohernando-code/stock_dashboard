from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.cli import build_parser
from ashare_evidence.external_context_acquisition import (
    CNINFO_PERSONAL_ATTRIBUTION,
    build_cninfo_personal_acquisition_plan,
    execute_cninfo_personal_acquisition,
    run_gdelt_multiday_relevance_canary,
)
from ashare_evidence.external_context_replay import materialize_external_context_pilot


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE stocks (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL);
        CREATE TABLE market_bars (
            id INTEGER PRIMARY KEY,
            stock_id INTEGER NOT NULL,
            timeframe TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            close_price REAL NOT NULL
        );
        INSERT INTO stocks(id, symbol) VALUES
            (1, '600001.SH'), (2, '000001.SZ'), (3, '300001.SZ'), (4, '600002.SH');
        INSERT INTO market_bars(stock_id, timeframe, observed_at, close_price) VALUES
            (1, '1d', '2024-01-02 15:00:00', 10.0),
            (2, '1d', '2024-01-02 15:00:00', 20.0),
            (3, '1d', '2024-01-02 15:00:00', 10.0),
            (4, '1d', '2024-01-02 15:00:00', 250.0);
        """
    )
    connection.commit()
    connection.close()


def _sample(symbol: str, start_date: str) -> dict[str, Any]:
    published_at = "2024-01-02T00:00:00+08:00"
    available_from = "2024-01-02T23:59:59.999999+08:00"
    retrieved_at = datetime(2026, 8, 6, tzinfo=UTC).isoformat()
    record = {
        "provider_item_id": f"cninfo:{symbol}:{start_date}",
        "normalized_event_id": f"cninfo:{symbol}:{start_date}",
        "revision_id": f"document:{symbol}:{start_date}",
        "provider_published_at": published_at,
        "provider_updated_at": None,
        "first_seen_at": retrieved_at,
        "available_from": available_from,
        "availability_basis": "provider_published_at_documented",
        "availability_evidence_ref": "https://www.cninfo.com.cn/",
        "event_type": "official_company_announcement",
        "source_authority": "official_exchange_designated_disclosure_platform",
        "entities": [symbol],
        "sectors": [],
        "geographies": ["CN"],
        "raw_payload": {"announcement_title": "年度报告", "sec_code": symbol},
        "normalized_payload": {"announcement_title": "年度报告", "sec_code": symbol},
    }
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"sample-{symbol}-{start_date}",
        "provider_id": "cninfo_public_announcements",
        "content_class": "official_fact",
        "source_endpoint": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        "license_tier": "placeholder",
        "retrieved_at": retrieved_at,
        "records": [record],
    }
    return {"pilot_input": pilot_input}


def test_personal_plan_uses_historical_unadjusted_price_and_main_board_only(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _database(database)

    plan = build_cninfo_personal_acquisition_plan(
        database_path=database,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )

    assert plan["symbol_count"] == 2
    assert plan["task_count"] == 2
    assert {row["symbol"] for row in plan["symbols"]} == {"600001.SH", "000001.SZ"}
    assert plan["historical_current_profile_fields_used"] is False
    assert plan["pit_risk_status_verified"] is False
    assert plan["usage_contract"] == {
        "use": "personal_internal_research_only",
        "authorized_by_user": True,
        "attribution": "hernando_zhao",
        "redistribution": "forbidden",
        "announcement_body_retained": False,
        "license_tier": "personal_internal_research_user_authorized_no_redistribution",
    }


def test_personal_acquisition_resumes_frozen_input_without_second_network_fetch(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _database(database)
    plan = build_cninfo_personal_acquisition_plan(
        database_path=database,
        start_date="2024-01-01",
        end_date="2024-12-31",
        max_symbols=1,
    )
    fetch_count = 0

    def fetcher(*, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        nonlocal fetch_count
        fetch_count += 1
        return _sample(symbol, start_date)

    def interrupted_materializer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("simulated interruption after frozen input")

    first = execute_cninfo_personal_acquisition(
        plan,
        artifact_root=tmp_path / "artifacts",
        max_tasks_this_run=1,
        min_request_interval_seconds=0,
        fetcher=fetcher,
        materializer=interrupted_materializer,
    )
    second = execute_cninfo_personal_acquisition(
        plan,
        artifact_root=tmp_path / "artifacts",
        max_tasks_this_run=1,
        min_request_interval_seconds=0,
        fetcher=fetcher,
    )

    assert first["failure_count"] == 1
    assert first["network_fetch_count"] == 1
    assert second["failure_count"] == 0
    assert second["processed_count"] == 1
    assert second["network_fetch_count"] == 0
    assert second["checkpoint_resume_count"] == 1
    assert second["run_status"] == "complete"
    assert second["storage_hard_cap_respected"] is True
    assert second["attribution"] == CNINFO_PERSONAL_ATTRIBUTION
    assert fetch_count == 1


def test_personal_acquisition_reuses_one_incremental_storage_budget_per_run(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _database(database)
    plan = build_cninfo_personal_acquisition_plan(
        database_path=database,
        start_date="2024-01-01",
        end_date="2025-01-01",
        max_symbols=1,
    )
    observed_budget_ids: list[int] = []

    def fetcher(*, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        return _sample(symbol, start_date)

    def materializer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        observed_budget_ids.append(id(kwargs["storage_budget"]))
        return materialize_external_context_pilot(*args, **kwargs)

    artifact_root = tmp_path / "artifacts"
    result = execute_cninfo_personal_acquisition(
        plan,
        artifact_root=artifact_root,
        max_tasks_this_run=2,
        min_request_interval_seconds=0,
        fetcher=fetcher,
        materializer=materializer,
    )

    actual_bytes = sum(path.stat().st_size for path in artifact_root.rglob("*") if path.is_file())
    assert len(observed_budget_ids) == 2
    assert len(set(observed_budget_ids)) == 1
    assert result["artifact_root_bytes"] == actual_bytes


def test_cli_registers_personal_acquisition_commands() -> None:
    parser = build_parser()
    plan = parser.parse_args(
        [
            "research-external-context-cninfo-acquisition-plan",
            "--database-path",
            "/tmp/source.db",
            "--start-date",
            "2023-06-13",
            "--end-date",
            "2026-05-26",
            "--output-json",
            "/tmp/plan.json",
        ]
    )
    run = parser.parse_args(
        [
            "research-external-context-cninfo-acquisition-run",
            "--plan-json",
            "/tmp/plan.json",
            "--artifact-root",
            "/tmp/artifacts",
        ]
    )
    gdelt = parser.parse_args(
        [
            "research-external-context-gdelt-multiday-canary",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-07",
        ]
    )

    assert plan.command == "research-external-context-cninfo-acquisition-plan"
    assert run.command == "research-external-context-cninfo-acquisition-run"
    assert run.max_tasks == 25
    assert run.min_request_interval_seconds == 1.0
    assert gdelt.command == "research-external-context-gdelt-multiday-canary"


def test_gdelt_multiday_canary_aggregates_and_deduplicates_without_archive_retention() -> None:
    def probe(*, archive_date: str) -> dict[str, Any]:
        record = {
            "normalized_event_id": "gdelt-url:shared",
            "first_seen_at": f"{archive_date[:4]}-{archive_date[4:6]}-{archive_date[6:]}T12:00:00+00:00",
            "normalized_payload": {"topic_tags": ["semiconductor"]},
        }
        return {
            "archive_date": archive_date,
            "archive_bytes_read_in_memory": 100,
            "row_count": 10,
            "relevant_row_count_before_url_dedup": 2,
            "unique_relevant_url_count": 1,
            "selected_record_count": 1,
            "selected_topic_counts": {"semiconductor": 1},
            "archive_sha256": f"hash-{archive_date}",
            "sample_digest": f"digest-{archive_date}",
            "pilot_input": {"records": [record]},
        }

    result = run_gdelt_multiday_relevance_canary(
        start_date="2026-05-01",
        end_date="2026-05-02",
        probe=probe,
    )

    assert result["day_count"] == 2
    assert result["days_completed"] == 2
    assert result["archive_bytes_read_in_memory_total"] == 200
    assert result["rows_scanned_total"] == 20
    assert result["selected_record_daily_sum"] == 2
    assert result["deduplicated_record_count"] == 1
    assert result["selected_topic_daily_counts"] == {"semiconductor": 2}
    assert result["selected_topic_counts"] == {"semiconductor": 1}
    assert result["archive_persisted"] is False
    assert result["article_body_downloaded"] is False
