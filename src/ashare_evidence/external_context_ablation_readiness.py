from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ashare_evidence.external_context_global_market_import import GLOBAL_MARKET_SUPPORTED_PROVIDERS
from ashare_evidence.external_context_replay import replay_external_context_offline

OFFICIAL_POLICY_PROVIDERS = {
    "federal_reserve_official_archive",
    "federal_register_policy_metadata",
}
CNINFO_PROVIDER = "cninfo_public_announcements"
ABLATION_READINESS_SCHEMA_VERSION = "external_context_ablation_readiness.v1"
CNINFO_FULL713_START_DATE = "2023-06-13"
CNINFO_FULL713_END_DATE = "2026-05-26"


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: str | Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return payload


def audit_external_context_ablation_readiness(
    *,
    artifact_root: str | Path,
    curation_audit_path: str | Path,
    decision_cutoff: str,
    global_import_audit_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root).resolve()
    manifests = sorted((root / "manifests").glob("external-context-manifest-*.json"))
    if not manifests:
        raise ValueError("artifact root contains no external-context replay manifests")
    curation = _load_object(curation_audit_path, label="CNINFO curation audit")
    if curation.get("schema_version") != "cninfo_personal_curation_audit.v1":
        raise ValueError("unsupported CNINFO curation audit schema")
    excluded_versions = {
        (str(row.get("normalized_event_id") or ""), str(row.get("revision_id") or ""))
        for row in curation.get("excluded_event_versions") or []
    }
    if any(not event_id or not revision_id for event_id, revision_id in excluded_versions):
        raise ValueError("CNINFO curation exclusions require normalized_event_id and revision_id")
    expected_exclusion_hash = curation.get("excluded_event_versions_sha256")
    if expected_exclusion_hash != _digest(curation.get("excluded_event_versions") or []):
        raise ValueError("CNINFO curation exclusion digest mismatch")
    scoped_cninfo_manifest_ids = {
        str(manifest_id) for manifest_id in curation.get("manifest_ids") or [] if str(manifest_id)
    }
    if scoped_cninfo_manifest_ids:
        expected_manifest_scope_hash = curation.get("manifest_ids_sha256")
        if expected_manifest_scope_hash != _digest(sorted(scoped_cninfo_manifest_ids)):
            raise ValueError("CNINFO curation manifest scope digest mismatch")

    provider_manifest_counts: Counter[str] = Counter()
    provider_selected_counts: Counter[str] = Counter()
    provider_curated_counts: Counter[str] = Counter()
    replay_rows: list[dict[str, Any]] = []
    replayed_cninfo_manifest_ids: set[str] = set()
    for manifest_path in manifests:
        manifest = _load_object(manifest_path, label="external-context manifest")
        provider_id = str(manifest.get("provider_id") or "").strip()
        if not provider_id:
            raise ValueError(f"manifest is missing provider_id: {manifest_path}")
        manifest_id = str(manifest.get("manifest_id") or "")
        if provider_id == CNINFO_PROVIDER and scoped_cninfo_manifest_ids:
            if manifest_id not in scoped_cninfo_manifest_ids:
                continue
            replayed_cninfo_manifest_ids.add(manifest_id)
        replay = replay_external_context_offline(manifest_path, decision_cutoff=decision_cutoff)
        selected = replay["selected_records"]
        curated_count = len(selected)
        if provider_id == CNINFO_PROVIDER:
            curated_count = sum(
                (str(row.get("normalized_event_id") or ""), str(row.get("knowledge_version") or ""))
                not in excluded_versions
                for row in selected
            )
        provider_manifest_counts[provider_id] += 1
        provider_selected_counts[provider_id] += len(selected)
        provider_curated_counts[provider_id] += curated_count
        replay_rows.append(
            {
                "manifest_id": manifest["manifest_id"],
                "provider_id": provider_id,
                "verified_file_count": replay["verified_file_count"],
                "selected_record_count": len(selected),
                "curated_record_count": curated_count,
                "replay_digest": replay["replay_digest"],
            }
        )
    if scoped_cninfo_manifest_ids and replayed_cninfo_manifest_ids != scoped_cninfo_manifest_ids:
        missing_ids = sorted(scoped_cninfo_manifest_ids - replayed_cninfo_manifest_ids)
        raise ValueError(f"CNINFO curation manifest scope is missing from replay root: {missing_ids}")

    available_providers = set(provider_manifest_counts)
    expected_cninfo_manifest_count = int(curation.get("manifest_count") or 0)
    expected_cninfo_source_count = int(curation.get("source_record_count") or 0)
    expected_cninfo_curated_count = int(curation.get("curated_record_count") or 0)
    if provider_manifest_counts[CNINFO_PROVIDER] != expected_cninfo_manifest_count:
        raise ValueError("CNINFO curation manifest count does not match the replay root")
    if provider_selected_counts[CNINFO_PROVIDER] != expected_cninfo_source_count:
        raise ValueError("CNINFO curation source count does not match the replay root")
    if provider_curated_counts[CNINFO_PROVIDER] != expected_cninfo_curated_count:
        raise ValueError("CNINFO curation curated count does not match the replay overlay")
    policy_providers_missing = sorted(OFFICIAL_POLICY_PROVIDERS - available_providers)
    policy_sample_ready = not policy_providers_missing and all(
        provider_curated_counts[provider] > 0 for provider in OFFICIAL_POLICY_PROVIDERS
    )
    completed_tasks = int(curation.get("completed_task_count") or 0)
    total_tasks = int(curation.get("total_task_count") or 0)
    partial_symbols = int(curation.get("partial_symbol_count") or 0)
    cninfo_plan_ready = (
        total_tasks > 0
        and completed_tasks == total_tasks
        and partial_symbols == 0
        and provider_curated_counts[CNINFO_PROVIDER] > 0
    )
    plan_start_date = str(curation.get("plan_start_date") or "")
    plan_end_date = str(curation.get("plan_end_date") or "")
    cninfo_full713_window_ready = (
        plan_start_date <= CNINFO_FULL713_START_DATE and plan_end_date >= CNINFO_FULL713_END_DATE
        if plan_start_date and plan_end_date
        else True
    )
    cninfo_full_ready = cninfo_plan_ready and cninfo_full713_window_ready

    global_providers = sorted(set(GLOBAL_MARKET_SUPPORTED_PROVIDERS) & available_providers)
    global_import_audit = (
        _load_object(global_import_audit_path, label="global-market import audit")
        if global_import_audit_path
        else None
    )
    global_window_envelope_ready = False
    if global_import_audit is not None:
        if global_import_audit.get("schema_version") != "external_context_global_market_import_audit.v1":
            raise ValueError("unsupported global-market import audit schema")
        audit_provider = str(global_import_audit.get("provider_id") or "")
        date_ranges = global_import_audit.get("instrument_date_ranges") or {}
        global_window_envelope_ready = (
            audit_provider in global_providers
            and not (global_import_audit.get("frozen_basket_missing_instruments") or [])
            and bool(date_ranges)
            and all(
                str(row.get("min") or "") <= "2023-05-01"
                and str(row.get("max") or "") >= "2026-05-26"
                for row in date_ranges.values()
            )
        )

    full_weight_backtest_ready = policy_sample_ready and cninfo_full_ready and global_window_envelope_ready
    blockers: list[str] = []
    if not policy_sample_ready:
        blockers.append("official_policy_manifest_or_record_missing")
    if not cninfo_plan_ready:
        blockers.append("cninfo_full713_task_coverage_incomplete")
    elif not cninfo_full713_window_ready:
        blockers.append("cninfo_full713_window_incomplete")
    if not global_window_envelope_ready:
        blockers.append("qualified_global_market_full_window_export_missing")
    bundle_identity = {
        "decision_cutoff": decision_cutoff,
        "curation_exclusion_digest": expected_exclusion_hash,
        "replays": replay_rows,
        "global_import_audit": global_import_audit,
    }
    return {
        "artifact_type": "external_context_ablation_readiness",
        "schema_version": ABLATION_READINESS_SCHEMA_VERSION,
        "bundle_id": f"external-context-ablation-bundle-{_digest(bundle_identity)[:24]}",
        "decision_cutoff": decision_cutoff,
        "network_used": False,
        "hash_verification_status": "passed",
        "manifest_count": len(replay_rows),
        "verified_file_count": sum(row["verified_file_count"] for row in replay_rows),
        "provider_manifest_counts": dict(sorted(provider_manifest_counts.items())),
        "provider_selected_record_counts": dict(sorted(provider_selected_counts.items())),
        "provider_curated_record_counts": dict(sorted(provider_curated_counts.items())),
        "cninfo_curation": {
            "policy_version": curation.get("active_relevance_policy_version"),
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "partial_symbols": partial_symbols,
            "exclusion_count": len(excluded_versions),
            "exclusion_digest": expected_exclusion_hash,
            "manifest_scope_count": len(scoped_cninfo_manifest_ids) or expected_cninfo_manifest_count,
            "manifest_scope_digest": curation.get("manifest_ids_sha256"),
            "plan_start_date": plan_start_date or None,
            "plan_end_date": plan_end_date or None,
        },
        "channel_gates": {
            "official_policy_sample_ready": policy_sample_ready,
            "official_policy_providers_missing": policy_providers_missing,
            "cninfo_plan_ready": cninfo_plan_ready,
            "cninfo_full713_window_ready": cninfo_full713_window_ready,
            "cninfo_full713_ready": cninfo_full_ready,
            "global_market_providers_present": global_providers,
            "global_market_window_envelope_ready": global_window_envelope_ready,
            "professional_news_status": "deferred_challenger_not_required_for_official_plus_global_ablation",
        },
        "ablation_ladder": [
            {"ablation": "stock_only_lambda_zero", "status": "permanent_baseline"},
            {
                "ablation": "official_policy_sample_only",
                "status": "ready_for_data_quality_research_only" if policy_sample_ready else "blocked",
            },
            {
                "ablation": "official_facts_full713",
                "status": "ready" if policy_sample_ready and cninfo_full_ready else "blocked",
            },
            {
                "ablation": "official_facts_plus_global_market_full713",
                "status": "ready" if full_weight_backtest_ready else "blocked",
            },
            {"ablation": "professional_news_increment", "status": "deferred_pending_qualified_feed"},
        ],
        "full713_weight_backtest_allowed": full_weight_backtest_ready,
        "blockers": blockers,
        "replay_digest": _digest(bundle_identity),
        "v3_signal_changed": False,
        "claim_ceiling": "offline_ablation_data_readiness_only_not_strategy_value",
    }
