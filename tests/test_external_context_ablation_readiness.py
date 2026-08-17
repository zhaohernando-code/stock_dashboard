from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ashare_evidence.cli import NO_DB_COMMANDS, build_parser
from ashare_evidence.external_context_ablation_readiness import audit_external_context_ablation_readiness
from ashare_evidence.external_context_replay import materialize_external_context_pilot


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pilot(provider_id: str, event_id: str, revision_id: str) -> dict[str, object]:
    now = datetime(2026, 5, 26, 16, tzinfo=UTC).isoformat()
    return {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"test-{provider_id}",
        "provider_id": provider_id,
        "content_class": "official_fact" if "global" not in provider_id else "market_data",
        "source_endpoint": "https://example.invalid/source",
        "license_tier": "test",
        "attribution": "test",
        "retrieved_at": now,
        "records": [
            {
                "provider_item_id": event_id,
                "normalized_event_id": event_id,
                "revision_id": revision_id,
                "provider_published_at": "2024-01-02T16:00:00+00:00",
                "provider_updated_at": None,
                "first_seen_at": "2024-01-02T16:00:00+00:00",
                "available_from": "2024-01-02T16:00:00+00:00",
                "availability_basis": "provider_published_at_documented",
                "availability_evidence_ref": "test",
                "event_type": "test",
                "source_authority": "test",
                "entities": [],
                "sectors": [],
                "geographies": [],
                "raw_payload": {"value": 1},
                "normalized_payload": {"value": 1},
            }
        ],
    }


def _curation(path: Path, exclusions: list[dict[str, str]], *, completed: int, total: int) -> Path:
    payload = {
        "schema_version": "cninfo_personal_curation_audit.v1",
        "active_relevance_policy_version": "cninfo_title_materiality.v8",
        "completed_task_count": completed,
        "total_task_count": total,
        "partial_symbol_count": 0,
        "manifest_count": 1,
        "source_record_count": 1,
        "curated_record_count": 1 - len(exclusions),
        "excluded_event_versions": exclusions,
        "excluded_event_versions_sha256": _digest(exclusions),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_ablation_readiness_scopes_cninfo_to_incremental_plan_manifests(tmp_path: Path) -> None:
    first = materialize_external_context_pilot(
        _pilot("cninfo_public_announcements", "cninfo:old", "document:old"), artifact_root=tmp_path
    )
    materialize_external_context_pilot(
        _pilot("cninfo_public_announcements", "cninfo:new", "document:new"), artifact_root=tmp_path
    )
    manifest_ids = [str(first["manifest"]["manifest_id"])]
    curation = _curation(tmp_path / "curation.json", [], completed=1, total=1)
    payload = json.loads(curation.read_text())
    payload.update(
        {
            "plan_start_date": "2026-05-27",
            "plan_end_date": "2026-08-14",
            "manifest_ids": manifest_ids,
            "manifest_ids_sha256": _digest(manifest_ids),
        }
    )
    curation.write_text(json.dumps(payload), encoding="utf-8")

    result = audit_external_context_ablation_readiness(
        artifact_root=tmp_path,
        curation_audit_path=curation,
        decision_cutoff="2026-08-15T00:00:00+00:00",
    )

    assert result["provider_manifest_counts"]["cninfo_public_announcements"] == 1
    assert result["provider_selected_record_counts"]["cninfo_public_announcements"] == 1
    assert result["channel_gates"]["cninfo_plan_ready"] is True
    assert result["channel_gates"]["cninfo_full713_window_ready"] is False
    assert result["channel_gates"]["cninfo_full713_ready"] is False
    assert "cninfo_full713_window_incomplete" in result["blockers"]


def test_ablation_readiness_accepts_frozen_full713_cninfo_window(tmp_path: Path) -> None:
    pilot = materialize_external_context_pilot(
        _pilot("cninfo_public_announcements", "cninfo:full713", "document:full713"), artifact_root=tmp_path
    )
    manifest_ids = [str(pilot["manifest"]["manifest_id"])]
    curation = _curation(tmp_path / "curation.json", [], completed=1, total=1)
    payload = json.loads(curation.read_text())
    payload.update(
        {
            "plan_start_date": "2023-06-13",
            "plan_end_date": "2026-05-26",
            "manifest_ids": manifest_ids,
            "manifest_ids_sha256": _digest(manifest_ids),
        }
    )
    curation.write_text(json.dumps(payload), encoding="utf-8")

    result = audit_external_context_ablation_readiness(
        artifact_root=tmp_path,
        curation_audit_path=curation,
        decision_cutoff="2026-05-27T00:00:00+00:00",
    )

    assert result["channel_gates"]["cninfo_plan_ready"] is True
    assert result["channel_gates"]["cninfo_full713_window_ready"] is True
    assert result["channel_gates"]["cninfo_full713_ready"] is True


def test_ablation_readiness_replays_hashes_and_remains_blocked_without_full_layers(tmp_path: Path) -> None:
    for provider, event_id, revision in (
        ("federal_reserve_official_archive", "fed:1", "1"),
        ("federal_register_policy_metadata", "fr:1", "1"),
        ("cninfo_public_announcements", "cninfo:1", "document:1"),
    ):
        materialize_external_context_pilot(_pilot(provider, event_id, revision), artifact_root=tmp_path)
    curation = _curation(
        tmp_path / "curation.json",
        [{"normalized_event_id": "cninfo:1", "revision_id": "document:1", "reason": "test"}],
        completed=1,
        total=3,
    )

    result = audit_external_context_ablation_readiness(
        artifact_root=tmp_path,
        curation_audit_path=curation,
        decision_cutoff="2026-05-27T00:00:00+00:00",
    )

    assert result["network_used"] is False
    assert result["hash_verification_status"] == "passed"
    assert result["channel_gates"]["official_policy_sample_ready"] is True
    assert result["provider_curated_record_counts"]["cninfo_public_announcements"] == 0
    assert result["full713_weight_backtest_allowed"] is False
    assert result["blockers"] == [
        "cninfo_full713_task_coverage_incomplete",
        "qualified_global_market_full_window_export_missing",
    ]


def test_ablation_readiness_rejects_tampered_curation_digest(tmp_path: Path) -> None:
    materialize_external_context_pilot(
        _pilot("federal_reserve_official_archive", "fed:1", "1"), artifact_root=tmp_path
    )
    curation = _curation(tmp_path / "curation.json", [], completed=0, total=1)
    payload = json.loads(curation.read_text())
    payload["excluded_event_versions_sha256"] = "0" * 64
    curation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="curation exclusion digest mismatch"):
        audit_external_context_ablation_readiness(
            artifact_root=tmp_path,
            curation_audit_path=curation,
            decision_cutoff="2026-05-27T00:00:00+00:00",
        )


def test_cli_registers_ablation_readiness_as_no_database_command() -> None:
    args = build_parser().parse_args(
        [
            "research-external-context-ablation-readiness",
            "--artifact-root",
            "/tmp/root",
            "--curation-audit-json",
            "/tmp/curation.json",
            "--decision-cutoff",
            "2026-05-27T00:00:00+00:00",
            "--output-json",
            "/tmp/readiness.json",
        ]
    )

    assert args.command == "research-external-context-ablation-readiness"
    assert args.command in NO_DB_COMMANDS
