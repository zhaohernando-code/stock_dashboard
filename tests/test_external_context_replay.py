from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from ashare_evidence.cli import build_parser
from ashare_evidence.external_context_replay import (
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
