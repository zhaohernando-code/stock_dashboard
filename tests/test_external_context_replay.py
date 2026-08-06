from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest

from ashare_evidence.cli import build_parser
from ashare_evidence.external_context_replay import (
    NEWS_STORAGE_HARD_CAP_BYTES,
    NEWS_STORAGE_TARGET_BYTES,
    NEWS_SUMMARY_MAX_BYTES,
    NEWS_SUMMARY_MAX_CHARS,
    materialize_external_context_pilot,
    replay_external_context_offline,
)


def _pilot_input() -> dict:
    common = {
        "normalized_event_id": "sec-edgar:0001045810:sample-event",
        "event_type": "company_filing_fact",
        "source_authority": "official_regulator",
        "entities": ["NVDA"],
        "sectors": ["semiconductor"],
        "geographies": ["US"],
        "availability_basis": "provider_published_at_documented",
        "availability_evidence_ref": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    }
    return {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": "sec-edgar-revision-fixture",
        "provider_id": "sec_edgar",
        "content_class": "official_fact",
        "source_endpoint": "data.sec.gov/submissions",
        "license_tier": "public_api_fair_access",
        "retrieved_at": "2026-08-06T17:00:00+08:00",
        "records": [
            {
                **common,
                "provider_item_id": "0001045810-sample-v1",
                "revision_id": "1",
                "provider_published_at": "2024-01-01T12:00:00-05:00",
                "provider_updated_at": None,
                "first_seen_at": "2026-08-06T16:50:00+08:00",
                "available_from": "2024-01-01T12:00:00-05:00",
                "raw_payload": {"accessionNumber": "sample-v1", "value": 100},
                "normalized_payload": {"fact_name": "sample", "value": 100},
            },
            {
                **common,
                "provider_item_id": "0001045810-sample-v2",
                "revision_id": "2",
                "provider_published_at": "2024-01-03T12:00:00-05:00",
                "provider_updated_at": "2024-01-03T12:00:00-05:00",
                "first_seen_at": "2026-08-06T16:51:00+08:00",
                "available_from": "2024-01-03T12:00:00-05:00",
                "raw_payload": {"accessionNumber": "sample-v2", "value": 110},
                "normalized_payload": {"fact_name": "sample", "value": 110},
            },
        ],
    }


def _news_summary_input() -> dict:
    raw_payload = {
        "headline": "US updates semiconductor export-control rules",
        "summary": "The rule changes restrictions affecting advanced semiconductor supply chains.",
        "source_url": "https://example.gov/semiconductor-rule",
        "source_name": "Example Government",
        "language": "en",
        "content_hash": hashlib.sha256(b"example-public-document").hexdigest(),
        "summary_method": "source_provided",
        "summary_model_version": None,
    }
    return {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": "public-news-summary-fixture",
        "provider_id": "public_news_discovery",
        "content_class": "news_summary",
        "source_endpoint": "https://example.gov/news",
        "license_tier": "public_metadata_summary_only",
        "retrieved_at": "2026-08-06T17:00:00+08:00",
        "records": [
            {
                "provider_item_id": "public-news-1",
                "normalized_event_id": "public-news:semiconductor-rule:1",
                "revision_id": "sha256-v1",
                "provider_published_at": "2026-08-06T16:50:00+08:00",
                "provider_updated_at": None,
                "first_seen_at": "2026-08-06T16:55:00+08:00",
                "available_from": "2026-08-06T16:55:00+08:00",
                "availability_basis": "first_seen_at",
                "availability_evidence_ref": "local-poll:2026-08-06T16:55:00+08:00",
                "event_type": "semiconductor_export_control",
                "source_authority": "official_government",
                "entities": [],
                "sectors": ["semiconductor"],
                "geographies": ["US", "CN"],
                "raw_payload": raw_payload,
                "normalized_payload": {
                    **raw_payload,
                    "channel_scope": "global_state",
                    "relevance_components": {
                        "global_topic_match": 0.95,
                        "source_quality": 1.0,
                        "novelty": 0.8,
                        "time_lineage": 1.0,
                    },
                    "affected_symbols": [],
                    "sector_ids": ["semiconductor"],
                    "topic_tags": ["export_control", "semiconductor"],
                },
            }
        ],
    }


def test_materialize_and_offline_replay_selects_only_visible_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = materialize_external_context_pilot(_pilot_input(), artifact_root=tmp_path)
    repeated = materialize_external_context_pilot(_pilot_input(), artifact_root=tmp_path)

    assert repeated["manifest"]["manifest_id"] == result["manifest"]["manifest_id"]
    assert result["manifest"]["record_count"] == 2
    assert result["manifest"]["network_required"] is False
    assert len(result["manifest"]["artifact_files"]) == 6

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: pytest.fail("offline replay attempted network access"),
    )
    first = replay_external_context_offline(
        result["manifest_path"],
        decision_cutoff="2024-01-02T12:00:00-05:00",
    )
    second = replay_external_context_offline(
        result["manifest_path"],
        decision_cutoff="2024-01-04T12:00:00-05:00",
    )
    revision_boundary = replay_external_context_offline(
        result["manifest_path"],
        decision_cutoff="2024-01-03T12:00:00-05:00",
    )
    before = replay_external_context_offline(
        result["manifest_path"],
        decision_cutoff="2023-12-31T12:00:00-05:00",
    )

    assert first["hash_verification_status"] == "passed"
    assert first["network_used"] is False
    assert first["selected_records"][0]["knowledge_version"] == "1"
    assert first["selected_records"][0]["feature_value"]["value"] == 100
    assert second["selected_records"][0]["knowledge_version"] == "2"
    assert second["selected_records"][0]["feature_value"]["value"] == 110
    assert revision_boundary["selected_records"][0]["knowledge_version"] == "2"
    assert before["selected_record_count"] == 0


def test_offline_replay_rejects_tampered_artifact(tmp_path: Path) -> None:
    result = materialize_external_context_pilot(_pilot_input(), artifact_root=tmp_path)
    raw_file = next(
        row
        for row in result["manifest"]["artifact_files"]
        if row["artifact_kind"] == "raw"
    )
    target = tmp_path / raw_file["relative_path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["raw_payload"]["value"] = 999
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact hash mismatch"):
        replay_external_context_offline(
            result["manifest_path"],
            decision_cutoff="2024-01-04T12:00:00-05:00",
        )


def test_materializer_rejects_backdated_first_seen_and_secret_fields(tmp_path: Path) -> None:
    first_seen_payload = _pilot_input()
    first_seen_payload["records"] = [dict(first_seen_payload["records"][0])]
    first_seen_payload["records"][0]["availability_basis"] = "first_seen_at"

    with pytest.raises(ValueError, match="first_seen_at availability cannot be backdated"):
        materialize_external_context_pilot(first_seen_payload, artifact_root=tmp_path / "first-seen")

    secret_payload = _pilot_input()
    secret_payload["records"] = [dict(secret_payload["records"][0])]
    secret_payload["records"][0]["raw_payload"] = {"authorization": "Bearer secret"}

    with pytest.raises(ValueError, match="secret-bearing field"):
        materialize_external_context_pilot(secret_payload, artifact_root=tmp_path / "secret")


def test_materializer_blocks_news_raw_until_content_rights_pass(tmp_path: Path) -> None:
    payload = _pilot_input()
    payload["provider_id"] = "tushare_major_news"

    with pytest.raises(ValueError, match="pending content rights"):
        materialize_external_context_pilot(payload, artifact_root=tmp_path)


def test_news_summary_materialization_is_relevant_compact_and_body_free(tmp_path: Path) -> None:
    result = materialize_external_context_pilot(_news_summary_input(), artifact_root=tmp_path)
    repeated = materialize_external_context_pilot(_news_summary_input(), artifact_root=tmp_path)

    assert repeated["manifest"]["manifest_id"] == result["manifest"]["manifest_id"]
    assert result["manifest"]["content_class"] == "news_summary"
    assert result["manifest"]["input_record_count"] == 1
    assert result["manifest"]["record_count"] == 1
    assert result["manifest"]["curation_counts"] == {
        "relevance_excluded_count": 0,
        "duplicate_excluded_count": 0,
        "quota_excluded_count": 0,
    }
    assert result["manifest"]["news_storage_contract"]["hard_cap_bytes"] < 2 * 1024**3
    assert result["storage_budget_observation"]["hard_cap_respected"] is True

    raw_row = next(
        row for row in result["manifest"]["artifact_files"] if row["artifact_kind"] == "raw"
    )
    raw_path = tmp_path / raw_row["relative_path"]
    raw_document = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw_document["content_retention_mode"] == "summary_only_no_article_body"
    assert raw_document["raw_payload"]["summary"]
    assert "body" not in raw_document["raw_payload"]
    assert "full_text" not in raw_document["raw_payload"]
    assert "\n  " not in raw_path.read_text(encoding="utf-8")

    replay = replay_external_context_offline(
        result["manifest_path"],
        decision_cutoff="2026-08-06T17:00:00+08:00",
    )
    assert replay["selected_record_count"] == 1
    feature = replay["selected_records"][0]["feature_value"]
    assert feature["relevance_gate"]["gate_passed"] is True
    assert feature["relevance_gate"]["score"] >= feature["relevance_gate"]["threshold"]


def test_news_summary_filters_low_relevance_and_duplicate_before_storage(tmp_path: Path) -> None:
    payload = _news_summary_input()
    duplicate = json.loads(json.dumps(payload["records"][0]))
    duplicate["provider_item_id"] = "public-news-duplicate"
    duplicate["normalized_event_id"] = "public-news:semiconductor-rule:duplicate"
    low_relevance = json.loads(json.dumps(payload["records"][0]))
    low_relevance["provider_item_id"] = "public-news-low"
    low_relevance["normalized_event_id"] = "public-news:unrelated:1"
    low_relevance["raw_payload"]["source_url"] = "https://example.gov/unrelated"
    low_relevance["normalized_payload"]["source_url"] = "https://example.gov/unrelated"
    low_relevance["raw_payload"]["content_hash"] = hashlib.sha256(b"unrelated").hexdigest()
    low_relevance["normalized_payload"]["content_hash"] = low_relevance["raw_payload"]["content_hash"]
    low_relevance["normalized_payload"]["relevance_components"] = {
        "global_topic_match": 0.1,
        "source_quality": 1.0,
        "novelty": 0.8,
        "time_lineage": 1.0,
    }
    payload["records"] = [payload["records"][0], duplicate, low_relevance]

    result = materialize_external_context_pilot(payload, artifact_root=tmp_path)

    assert result["manifest"]["input_record_count"] == 3
    assert result["manifest"]["record_count"] == 1
    assert result["manifest"]["curation_counts"]["relevance_excluded_count"] == 1
    assert result["manifest"]["curation_counts"]["duplicate_excluded_count"] == 1


def test_news_summary_applies_daily_channel_quota_before_storage(tmp_path: Path) -> None:
    payload = _news_summary_input()
    records = []
    for index in range(13):
        record = json.loads(json.dumps(payload["records"][0]))
        record["provider_item_id"] = f"public-news-{index:02d}"
        record["normalized_event_id"] = f"public-news:global:{index:02d}"
        source_url = f"https://example.gov/global/{index:02d}"
        content_hash = hashlib.sha256(f"global-{index:02d}".encode()).hexdigest()
        record["raw_payload"]["source_url"] = source_url
        record["normalized_payload"]["source_url"] = source_url
        record["raw_payload"]["content_hash"] = content_hash
        record["normalized_payload"]["content_hash"] = content_hash
        records.append(record)
    payload["records"] = records

    result = materialize_external_context_pilot(payload, artifact_root=tmp_path)

    assert result["manifest"]["input_record_count"] == 13
    assert result["manifest"]["record_count"] == 12
    assert result["manifest"]["curation_counts"]["quota_excluded_count"] == 1
    assert len(result["manifest"]["artifact_files"]) == 36


def test_news_summary_rejects_article_body_and_oversized_summary(tmp_path: Path) -> None:
    body_payload = _news_summary_input()
    body_payload["records"][0]["raw_payload"]["body"] = "full article body"
    with pytest.raises(ValueError, match="summary-only"):
        materialize_external_context_pilot(body_payload, artifact_root=tmp_path / "body")

    oversized = _news_summary_input()
    oversized_summary = "芯" * 1_001
    oversized["records"][0]["raw_payload"]["summary"] = oversized_summary
    oversized["records"][0]["normalized_payload"]["summary"] = oversized_summary
    with pytest.raises(ValueError, match="summary exceeds"):
        materialize_external_context_pilot(oversized, artifact_root=tmp_path / "oversized")


def test_news_summary_hard_cap_fails_before_exceeding_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ashare_evidence.external_context_replay.NEWS_STORAGE_HARD_CAP_BYTES",
        100,
    )
    with pytest.raises(ValueError, match="hard cap would be exceeded"):
        materialize_external_context_pilot(_news_summary_input(), artifact_root=tmp_path)

    assert sum(path.stat().st_size for path in tmp_path.rglob("*") if path.is_file()) <= 100


def test_public_news_storage_contract_matches_runtime_limits() -> None:
    contract_path = (
        Path(__file__).parents[1]
        / "docs"
        / "contracts"
        / "SHORTPICK_V3_PUBLIC_NEWS_SUMMARY_STORAGE_2026-08-06.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    assert contract["retention_contract"]["summary_max_characters"] == NEWS_SUMMARY_MAX_CHARS
    assert contract["retention_contract"]["summary_max_utf8_bytes"] == NEWS_SUMMARY_MAX_BYTES
    assert contract["storage_budget"]["target_bytes"] == NEWS_STORAGE_TARGET_BYTES
    assert contract["storage_budget"]["hard_cap_bytes"] == NEWS_STORAGE_HARD_CAP_BYTES
    assert NEWS_STORAGE_HARD_CAP_BYTES < 2 * 1024**3


def test_cli_registers_materialize_and_offline_replay_commands() -> None:
    parser = build_parser()
    materialize = parser.parse_args(
        [
            "research-external-context-materialize-pilot",
            "--input-json",
            "input.json",
            "--artifact-root",
            "/tmp/external-context-pilot",
        ]
    )
    replay = parser.parse_args(
        [
            "research-external-context-offline-replay",
            "--manifest-json",
            "manifest.json",
            "--decision-cutoff",
            "2024-01-01T00:00:00+08:00",
        ]
    )

    assert materialize.command == "research-external-context-materialize-pilot"
    assert replay.command == "research-external-context-offline-replay"
