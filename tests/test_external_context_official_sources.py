from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.cli import build_parser
from ashare_evidence.external_context_official_sources import (
    fetch_federal_register_policy_poc,
    fetch_federal_reserve_policy_poc,
)
from ashare_evidence.external_context_replay import (
    materialize_external_context_pilot,
    replay_external_context_offline,
)


class _Response:
    def __init__(
        self,
        *,
        text: str = "",
        payload: dict[str, Any] | None = None,
        status_code: int = 200,
    ) -> None:
        self.text = text
        self._payload = payload
        self.status_code = status_code
        self.content = text.encode("utf-8") if payload is None else json.dumps(payload).encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise AssertionError("response has no JSON payload")
        return self._payload


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _fed_archive_html() -> str:
    return """
    <div class='row eventlist'>
      <div class='eventlist__time'><time>06/14/2023</time></div>
      <div class='eventlist__event'>
        <p><a href='/newsevents/pressreleases/monetary20230614a.htm'><em>Federal Reserve issues FOMC statement</em></a></p>
        <p class='eventlist__press'><em><strong>Monetary Policy</strong></em></p>
      </div>
      <div class='eventlist__time'><time>06/15/2023</time></div>
      <div class='eventlist__event'>
        <p><a href='/newsevents/pressreleases/enforcement20230615a.htm'><em>Enforcement action</em></a></p>
        <p class='eventlist__press'><em><strong>Enforcement Actions</strong></em></p>
      </div>
    </div>
    """


def _federal_register_document() -> dict[str, Any]:
    return {
        "title": "Export controls on advanced computing semiconductor items",
        "type": "Rule",
        "abstract": "The Bureau updates export controls for advanced computing and semiconductor manufacturing items.",
        "document_number": "2024-12345",
        "html_url": "https://www.federalregister.gov/documents/2024/01/05/2024-12345/example",
        "pdf_url": "https://www.govinfo.gov/content/pkg/FR-2024-01-05/pdf/2024-12345.pdf",
        "publication_date": "2024-01-05",
        "agencies": [{"name": "Industry and Security Bureau"}],
        "excerpts": "unused",
    }


def test_federal_reserve_archive_filters_monetary_policy_and_uses_conservative_day_end(tmp_path: Path) -> None:
    session = _Session([_Response(text=_fed_archive_html())])
    result = fetch_federal_reserve_policy_poc(
        start_date="2023-06-13",
        end_date="2023-12-31",
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
    )

    assert result["record_count"] == 1
    record = result["pilot_input"]["records"][0]
    assert record["provider_item_id"] == "federal-reserve:monetary20230614a"
    assert record["available_from"] == "2023-06-14T23:59:59.999999-04:00"
    assert record["normalized_payload"]["channel_scope"] == "global_state"
    assert result["article_body_downloaded"] is False

    materialized = materialize_external_context_pilot(result["pilot_input"], artifact_root=tmp_path)
    replay = replay_external_context_offline(
        materialized["manifest_path"],
        decision_cutoff="2023-06-15T00:00:00-04:00",
    )
    assert replay["selected_record_count"] == 1
    assert replay["hash_verification_status"] == "passed"
    assert replay["network_used"] is False


def test_federal_reserve_resumes_raw_page_checkpoint_without_network(tmp_path: Path) -> None:
    first_session = _Session([_Response(text=_fed_archive_html())])
    second_session = _Session([])
    checkpoint_root = tmp_path / "artifacts"

    first = fetch_federal_reserve_policy_poc(
        start_date="2023-06-13",
        end_date="2023-12-31",
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=first_session,
        checkpoint_root=checkpoint_root,
    )
    second = fetch_federal_reserve_policy_poc(
        start_date="2023-06-13",
        end_date="2023-12-31",
        retrieved_at=datetime(2026, 8, 7, tzinfo=UTC),
        session=second_session,
        checkpoint_root=checkpoint_root,
    )

    assert first["source_pages"][0]["network_used"] is True
    assert second["source_pages"][0]["network_used"] is False
    assert second["source_pages"][0]["checkpoint_resumed"] is True
    assert second["source_pages"][0]["transport_sha256"] == first["source_pages"][0]["transport_sha256"]
    assert second["source_pages"][0]["selected_content_sha256"] == first["source_pages"][0]["selected_content_sha256"]
    assert second["pilot_input"]["records"][0]["first_seen_at"] == first["pilot_input"]["records"][0]["first_seen_at"]
    assert second_session.requests == []


def test_federal_register_deduplicates_terms_and_retains_compact_official_metadata(tmp_path: Path) -> None:
    document = _federal_register_document()
    payload = {"count": 1, "results": [document]}
    session = _Session([_Response(payload=payload), _Response(payload=payload)])
    result = fetch_federal_register_policy_poc(
        start_date="2023-06-13",
        end_date="2026-05-26",
        terms=("semiconductor", "export control"),
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
        min_request_interval_seconds=0,
    )

    assert result["record_count"] == 1
    assert len(result["query_evidence"]) == 2
    record = result["pilot_input"]["records"][0]
    assert record["normalized_event_id"] == "federal-register:2024-12345"
    assert record["available_from"] == "2024-01-05T23:59:59.999999-05:00"
    assert record["normalized_payload"]["topic_tags"] == [
        "semiconductor_policy",
        "trade_and_export_control",
    ]
    assert record["raw_payload"]["agencies"] == ["Industry and Security Bureau"]
    assert "body" not in record["raw_payload"]
    assert result["document_body_downloaded"] is False

    materialized = materialize_external_context_pilot(result["pilot_input"], artifact_root=tmp_path)
    replay = replay_external_context_offline(
        materialized["manifest_path"],
        decision_cutoff="2024-01-06T00:00:00-05:00",
    )
    assert replay["selected_record_count"] == 1
    assert replay["network_used"] is False


def test_federal_register_retries_temporary_server_failure() -> None:
    document = _federal_register_document()
    session = _Session(
        [
            _Response(status_code=503),
            _Response(payload={"count": 1, "results": [document]}),
        ]
    )
    sleeps: list[float] = []

    result = fetch_federal_register_policy_poc(
        start_date="2023-06-13",
        end_date="2026-05-26",
        terms=("semiconductor",),
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
        min_request_interval_seconds=0,
        sleeper=sleeps.append,
    )

    assert result["record_count"] == 1
    assert sleeps == [1.0]
    assert len(session.requests) == 2


def test_federal_register_resumes_page_checkpoint_without_network(tmp_path: Path) -> None:
    document = _federal_register_document()
    first_session = _Session([_Response(payload={"count": 1, "results": [document]})])
    second_session = _Session([])
    checkpoint_root = tmp_path / "artifacts"

    first = fetch_federal_register_policy_poc(
        start_date="2023-06-13",
        end_date="2026-05-26",
        terms=("semiconductor",),
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=first_session,
        min_request_interval_seconds=0,
        checkpoint_root=checkpoint_root,
    )
    second = fetch_federal_register_policy_poc(
        start_date="2023-06-13",
        end_date="2026-05-26",
        terms=("semiconductor",),
        retrieved_at=datetime(2026, 8, 7, tzinfo=UTC),
        session=second_session,
        min_request_interval_seconds=0,
        checkpoint_root=checkpoint_root,
    )

    assert first["query_evidence"][0]["network_page_count"] == 1
    assert second["query_evidence"][0]["network_page_count"] == 0
    assert second["query_evidence"][0]["checkpoint_resume_page_count"] == 1
    assert second["record_count"] == first["record_count"] == 1
    assert second["pilot_input"]["records"][0]["first_seen_at"] == first["pilot_input"]["records"][0]["first_seen_at"]
    assert second_session.requests == []


def test_federal_register_rejects_agency_and_headline_scope_noise() -> None:
    faa = {
        **_federal_register_document(),
        "title": "Airworthiness Directives; The Boeing Company Airplanes",
        "abstract": "The directive addresses possible interference from 5G telecommunications systems.",
        "document_number": "2024-20001",
        "agencies": [{"name": "Federal Aviation Administration"}],
    }
    agriculture = {
        **_federal_register_document(),
        "title": "Regional Agricultural Promotion Program",
        "abstract": "The program supports agricultural export market development and tariff responses.",
        "document_number": "2024-20002",
        "agencies": [{"name": "Agriculture Department"}],
    }
    session = _Session([_Response(payload={"count": 2, "results": [faa, agriculture]})])

    result = fetch_federal_register_policy_poc(
        start_date="2023-06-13",
        end_date="2026-05-26",
        terms=("export control",),
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
        min_request_interval_seconds=0,
    )

    assert result["record_count"] == 0
    assert result["relevance_exclusion_counts"] == {
        "telecommunications_policy:agency_or_headline_scope": 1,
        "trade_and_export_control:agency_or_headline_scope": 1,
    }


def test_federal_register_rejects_patent_and_administrative_noise_and_maps_trade_sectors() -> None:
    patent = {
        **_federal_register_document(),
        "title": "Certain Semiconductor Devices and Products Containing the Same; Institution of Investigation",
        "abstract": "A private patent complaint under section 337 seeks an import restriction.",
        "document_number": "2024-30001",
        "agencies": [{"name": "International Trade Commission"}],
    }
    administrative = {
        **_federal_register_document(),
        "title": "Agency Information Collection Activities; Entity List and Unverified List Requests",
        "document_number": "2024-30002",
    }
    materials = {
        **_federal_register_document(),
        "title": "Section 232 Tariff Adjustments for Steel and Aluminum Imports",
        "abstract": "The rule adjusts tariffs for imported steel and aluminum.",
        "document_number": "2024-30003",
    }
    session = _Session([_Response(payload={"count": 3, "results": [patent, administrative, materials]})])

    result = fetch_federal_register_policy_poc(
        start_date="2023-06-13",
        end_date="2026-05-26",
        terms=("export control",),
        retrieved_at=datetime(2026, 8, 6, tzinfo=UTC),
        session=session,
        min_request_interval_seconds=0,
    )

    assert result["record_count"] == 1
    record = result["pilot_input"]["records"][0]
    assert record["raw_payload"]["document_number"] == "2024-30003"
    assert record["normalized_payload"]["sector_ids"] == ["industrial_supply_chain", "strategic_materials"]
    assert "semiconductor" not in record["normalized_payload"]["sector_ids"]


def test_cli_registers_official_policy_commands() -> None:
    parser = build_parser()
    fed = parser.parse_args(
        [
            "research-external-context-fed-policy-poc",
            "--start-date",
            "2023-06-13",
            "--end-date",
            "2026-05-26",
            "--checkpoint-root",
            "/tmp/fed-checkpoints",
        ]
    )
    register = parser.parse_args(
        [
            "research-external-context-federal-register-poc",
            "--start-date",
            "2023-06-13",
            "--end-date",
            "2026-05-26",
            "--term",
            "semiconductor",
        ]
    )

    assert fed.command == "research-external-context-fed-policy-poc"
    assert fed.checkpoint_root == "/tmp/fed-checkpoints"
    assert register.command == "research-external-context-federal-register-poc"
    assert register.term == ["semiconductor"]
