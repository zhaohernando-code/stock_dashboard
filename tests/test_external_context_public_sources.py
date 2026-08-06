from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ashare_evidence.cli import build_parser
from ashare_evidence.external_context_public_sources import (
    GDELT_DAILY_ARCHIVE_MAX_BYTES,
    fetch_cninfo_announcement_poc,
    probe_gdelt_daily_public_discovery,
    run_cninfo_historical_eligibility_canary,
)
from ashare_evidence.external_context_replay import (
    materialize_external_context_pilot,
    replay_external_context_offline,
)


class _FakeResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self._body = body
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise AssertionError("response has no JSON payload")
        return self._payload

    def iter_content(self, chunk_size: int) -> Any:
        for offset in range(0, len(self._body), chunk_size):
            yield self._body[offset : offset + chunk_size]


class _FakeSession:
    def __init__(self, *, get_responses: list[_FakeResponse], post_responses: list[_FakeResponse]) -> None:
        self.get_responses = list(get_responses)
        self.post_responses = list(post_responses)
        self.posts: list[dict[str, Any]] = []

    def get(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self.get_responses.pop(0)

    def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        self.posts.append(dict(kwargs.get("data") or {}))
        return self.post_responses.pop(0)


def _gdelt_row(
    *,
    event_id: str,
    source_url: str,
    date_added: str = "20260805",
    goldstein: str = "-5.0",
) -> str:
    row = [""] * 58
    row[0] = event_id
    row[1] = "20260805"
    row[5] = "CHN"
    row[6] = "CHINA"
    row[7] = "CHN"
    row[15] = "USA"
    row[16] = "UNITED STATES"
    row[17] = "USA"
    row[26] = "163"
    row[29] = "4"
    row[30] = goldstein
    row[31] = "8"
    row[32] = "3"
    row[37] = "CH"
    row[47] = "US"
    row[51] = "US"
    row[56] = date_added
    row[57] = source_url
    return "\t".join(row)


def _zip_rows(rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("20260805.export.CSV", ("\n".join(rows) + "\n").encode())
    return buffer.getvalue()


def test_cninfo_fetch_handles_empty_result_without_akshare_schema_failure() -> None:
    session = _FakeSession(
        get_responses=[
            _FakeResponse(payload={"stockList": [{"code": "600519", "orgId": "gssh0600519"}]})
        ],
        post_responses=[
            _FakeResponse(
                payload={
                    "totalAnnouncement": 0,
                    "totalpages": 0,
                    "announcements": None,
                }
            )
        ],
    )

    result = fetch_cninfo_announcement_poc(
        symbol="600519",
        start_date="20240101",
        end_date="20240131",
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
    )

    assert result["pit_candidate_status"] == "empty_sample"
    assert result["record_count"] == 0
    assert result["pilot_input"]["records"] == []
    assert result["announcement_body_downloaded"] is False


def test_cninfo_fetch_paginates_consistently_and_materializes_offline(tmp_path: Path) -> None:
    first = {
        "secCode": "600519",
        "secName": "贵州茅台",
        "announcementTitle": "<em>年度</em>报告摘要",
        "announcementTime": 1_704_067_200_000,
        "announcementId": "1219000001",
        "orgId": "gssh0600519",
    }
    second = {**first, "announcementId": "1219000002", "announcementTitle": "关于股份回购的公告"}
    routine = {**first, "announcementId": "1219000003", "announcementTitle": "董事会会议决议公告"}
    same_group = {**first, "announcementId": "1219000004", "announcementTitle": "年度报告"}
    routine_attachment = {
        **first,
        "announcementId": "1219000005",
        "announcementTitle": "关于补充流动资金的核查意见",
    }
    session = _FakeSession(
        get_responses=[
            _FakeResponse(payload={"stockList": [{"code": "600519", "orgId": "gssh0600519"}]})
        ],
        post_responses=[
            _FakeResponse(payload={"totalAnnouncement": 31, "totalpages": 2, "announcements": [first]}),
            _FakeResponse(
                payload={
                    "totalAnnouncement": 31,
                    "totalpages": 2,
                    "announcements": [second, routine, same_group, routine_attachment],
                }
            ),
        ],
    )

    result = fetch_cninfo_announcement_poc(
        symbol="600519",
        start_date="20240101",
        end_date="20241231",
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
    )

    assert result["record_count"] == 2
    assert result["irrelevant_or_routine_title_excluded_count"] == 2
    assert result["relevant_announcement_count_before_grouping"] == 3
    assert result["same_day_category_collapsed_count"] == 1
    assert session.posts[0]["pageNum"] == 1
    assert session.posts[1]["pageNum"] == 2
    assert "<em>" not in result["pilot_input"]["records"][0]["raw_payload"]["announcement_title"]
    assert result["pilot_input"]["records"][0]["provider_published_at"].endswith("+08:00")
    assert result["pilot_input"]["records"][0]["available_from"].endswith("23:59:59.999999+08:00")
    assert all(
        "body" not in record["raw_payload"] and "full_text" not in record["raw_payload"]
        for record in result["pilot_input"]["records"]
    )
    grouped = next(
        record for record in result["pilot_input"]["records"] if "announcement_group_size" in record["raw_payload"]
    )
    assert grouped["raw_payload"]["announcement_group_size"] == 2
    assert grouped["raw_payload"]["retained_announcement_count"] == 2

    materialized = materialize_external_context_pilot(result["pilot_input"], artifact_root=tmp_path)
    replay = replay_external_context_offline(
        materialized["manifest_path"],
        decision_cutoff="2024-01-02T00:00:00+08:00",
    )
    assert replay["network_used"] is False
    assert replay["selected_record_count"] == 2


def test_gdelt_probe_filters_in_memory_deduplicates_urls_and_materializes_summary_only(
    tmp_path: Path,
) -> None:
    relevant_url = "https://example.com/china-semiconductor-export-control"
    rows = [
        _gdelt_row(event_id="100", source_url=relevant_url, goldstein="-2.0"),
        _gdelt_row(event_id="101", source_url=relevant_url, goldstein="-8.0"),
        _gdelt_row(event_id="102", source_url="https://example.com/sports-result"),
        _gdelt_row(event_id="103", source_url="https://example.com/semiconductor/123456789"),
        "too\tshort",
    ]
    archive = _zip_rows(rows)
    session = _FakeSession(
        get_responses=[_FakeResponse(body=archive, headers={"Content-Length": str(len(archive))})],
        post_responses=[],
    )

    result = probe_gdelt_daily_public_discovery(
        archive_date="20260805",
        retrieved_at=datetime(2026, 8, 7, 1, tzinfo=UTC),
        session=session,
    )

    assert result["archive_persisted"] is False
    assert result["article_body_downloaded"] is False
    assert result["row_count"] == 5
    assert result["relevant_row_count_before_url_dedup"] == 2
    assert result["unique_relevant_url_count"] == 1
    assert result["selected_record_count"] == 1
    assert result["selected_topic_counts"]["semiconductor"] == 1
    record = result["pilot_input"]["records"][0]
    assert record["provider_item_id"] == "gdelt:101"
    assert "article-body summary" in record["raw_payload"]["summary"]
    assert record["available_from"] == "2026-08-07T00:00:00+00:00"

    materialized = materialize_external_context_pilot(result["pilot_input"], artifact_root=tmp_path)
    raw_file = next(
        row for row in materialized["manifest"]["artifact_files"] if row["artifact_kind"] == "raw"
    )
    stored = json.loads((tmp_path / raw_file["relative_path"]).read_text())
    assert set(stored["raw_payload"]) == {
        "content_hash",
        "headline",
        "language",
        "source_name",
        "source_url",
        "summary",
        "summary_method",
        "summary_model_version",
    }


def test_gdelt_probe_blocks_incomplete_day_and_oversized_archive() -> None:
    with pytest.raises(ValueError, match="second following UTC day"):
        probe_gdelt_daily_public_discovery(
            archive_date="20260806",
            retrieved_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
            session=_FakeSession(get_responses=[], post_responses=[]),
        )

    session = _FakeSession(
        get_responses=[
            _FakeResponse(body=b"", headers={"Content-Length": str(GDELT_DAILY_ARCHIVE_MAX_BYTES + 1)})
        ],
        post_responses=[],
    )
    with pytest.raises(ValueError, match="Content-Length exceeds"):
        probe_gdelt_daily_public_discovery(
            archive_date="20260805",
            retrieved_at=datetime(2026, 8, 7, 1, tzinfo=UTC),
            session=session,
        )


def test_cli_registers_public_source_poc_commands() -> None:
    parser = build_parser()
    cninfo = parser.parse_args(
        [
            "research-external-context-cninfo-public-poc",
            "--symbol",
            "600519",
            "--start-date",
            "20240101",
            "--end-date",
            "20241231",
        ]
    )
    gdelt = parser.parse_args(
        ["research-external-context-gdelt-public-poc", "--archive-date", "20260805"]
    )
    canary = parser.parse_args(
        [
            "research-external-context-cninfo-canary",
            "--database-path",
            "/tmp/sample.db",
            "--signal-date",
            "2024-01-02",
        ]
    )

    assert cninfo.command == "research-external-context-cninfo-public-poc"
    assert cninfo.max_pages == 100
    assert gdelt.command == "research-external-context-gdelt-public-poc"
    assert gdelt.selected_limit == 12
    assert canary.command == "research-external-context-cninfo-canary"
    assert canary.symbols_per_date == 6


def test_cninfo_canary_uses_historical_price_snapshot_without_current_profile_fields(
    tmp_path: Path,
) -> None:
    database = tmp_path / "canary.db"
    connection = sqlite3.connect(database)
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
        """
    )
    for day in ("2024-01-02", "2024-01-03"):
        connection.executemany(
            "INSERT INTO market_bars(stock_id, timeframe, observed_at, close_price) VALUES (?, '1d', ?, ?)",
            [
                (1, f"{day} 15:00:00", 10.0),
                (2, f"{day} 15:00:00", 20.0),
                (3, f"{day} 15:00:00", 10.0),
                (4, f"{day} 15:00:00", 250.0),
            ],
        )
    connection.commit()
    connection.close()

    def fake_fetcher(*, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        published = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}T23:59:59+08:00"
        record = {
            "provider_item_id": f"cninfo:{symbol}:{start_date}",
            "normalized_event_id": f"cninfo:{symbol}:{start_date}",
            "revision_id": f"document:{symbol}:{start_date}",
            "provider_published_at": published,
            "provider_updated_at": None,
            "first_seen_at": "2026-08-06T12:00:00+00:00",
            "available_from": published,
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
        return {
            "reported_total": 1,
            "fetched_announcement_count": 1,
            "relevant_announcement_count_before_grouping": 1,
            "record_count": 1,
            "sample_digest": f"digest-{symbol}-{start_date}",
            "pilot_input": {"records": [record]},
        }

    result = run_cninfo_historical_eligibility_canary(
        database_path=database,
        signal_dates=["2024-01-02", "2024-01-03"],
        symbols_per_date=1,
        window_days=31,
        fetcher=fake_fetcher,
    )

    assert result["database_open_mode"] == "read_only"
    assert result["selected_symbol_count"] == 2
    assert result["request_count"] == 2
    assert result["all_requests_complete"] is True
    assert result["retained_event_package_count"] == 2
    assert result["historical_current_profile_fields_used"] is False
    assert result["pit_risk_status_verified"] is False
    assert all(
        row["warnings"] == ["pit_risk_status_unverified_current_static_name_not_used"]
        for row in result["selected_symbols"]
    )
