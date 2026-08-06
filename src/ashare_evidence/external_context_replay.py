from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ashare_evidence.external_context_news_summary import (
    NEWS_DAILY_CHANNEL_LIMITS,
    NEWS_RELEVANCE_POLICY_VERSION,
    NEWS_STORAGE_HARD_CAP_BYTES,
    NEWS_STORAGE_TARGET_BYTES,
    NEWS_SUMMARY_MAX_BYTES,
    NEWS_SUMMARY_MAX_CHARS,
    curate_news_records,
    validate_news_summary_payloads,
)

PILOT_INPUT_SCHEMA_VERSION = "external_context_pilot_input.v1"
RAW_SCHEMA_VERSION = "external_context_raw_record.v1"
SILVER_SCHEMA_VERSION = "external_context_silver_record.v1"
PIT_SCHEMA_VERSION = "external_context_pit_record.v1"
MANIFEST_SCHEMA_VERSION = "external_context_replay_manifest.v1"
REPLAY_SCHEMA_VERSION = "external_context_offline_replay.v1"
TRANSFORM_VERSION = "external_context_normalization.v1"
FEATURE_VERSION = "external_context_normalized_fact.v1"

ALLOWED_CONTENT_CLASSES = {"official_fact", "market_data", "news_summary"}
ALLOWED_AVAILABILITY_BASES = {
    "first_seen_at",
    "provider_published_at_documented",
    "provider_effective_at_documented",
}
FORBIDDEN_RAW_PROVIDER_IDS = {"tushare_major_news", "massive_benzinga_news"}
SECRET_FIELD_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}

@dataclass
class _StorageBudget:
    root: Path
    hard_cap_bytes: int
    used_bytes: int

    @classmethod
    def from_root(cls, root: Path, *, hard_cap_bytes: int) -> _StorageBudget:
        used_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0
        if used_bytes > hard_cap_bytes:
            raise ValueError(
                f"news artifact root already exceeds hard cap: {used_bytes} > {hard_cap_bytes} bytes"
            )
        return cls(root=root, hard_cap_bytes=hard_cap_bytes, used_bytes=used_bytes)

    def ensure_can_add(self, byte_size: int) -> None:
        projected = self.used_bytes + byte_size
        if projected > self.hard_cap_bytes:
            raise ValueError(
                "news storage hard cap would be exceeded: "
                f"projected={projected} hard_cap={self.hard_cap_bytes} bytes"
            )

    def record_addition(self, byte_size: int) -> None:
        self.used_bytes += byte_size


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _aware_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _assert_no_secret_fields(value: Any, *, path: str = "raw_payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in SECRET_FIELD_NAMES:
                raise ValueError(f"secret-bearing field is forbidden in immutable Raw: {path}.{key}")
            _assert_no_secret_fields(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_secret_fields(item, path=f"{path}[{index}]")


def _validate_input(payload: dict[str, Any]) -> tuple[str, str, str, datetime, list[dict[str, Any]]]:
    if payload.get("schema_version") != PILOT_INPUT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {PILOT_INPUT_SCHEMA_VERSION}")
    dataset_id = _required_text(payload, "dataset_id")
    provider_id = _required_text(payload, "provider_id")
    if provider_id in FORBIDDEN_RAW_PROVIDER_IDS:
        raise ValueError(f"Raw materialization is forbidden for provider pending content rights: {provider_id}")
    content_class = _required_text(payload, "content_class")
    if content_class not in ALLOWED_CONTENT_CLASSES:
        raise ValueError(f"unsupported content_class: {content_class}")
    retrieved_at = _aware_datetime(payload.get("retrieved_at"), field="retrieved_at")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty list")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("every record must be an object")
    return dataset_id, provider_id, content_class, retrieved_at, records


def _validate_record(
    record: dict[str, Any],
    *,
    provider_id: str,
    content_class: str,
    retrieved_at: datetime,
) -> dict[str, Any]:
    provider_item_id = _required_text(record, "provider_item_id")
    normalized_event_id = _required_text(record, "normalized_event_id")
    revision_id = _required_text(record, "revision_id")
    availability_basis = _required_text(record, "availability_basis")
    if availability_basis not in ALLOWED_AVAILABILITY_BASES:
        raise ValueError(f"unsupported availability_basis: {availability_basis}")
    availability_evidence_ref = _required_text(record, "availability_evidence_ref")
    provider_published_at = _aware_datetime(
        record.get("provider_published_at"),
        field="provider_published_at",
    )
    first_seen_at = _aware_datetime(record.get("first_seen_at"), field="first_seen_at")
    available_from = _aware_datetime(record.get("available_from"), field="available_from")
    provider_updated_raw = record.get("provider_updated_at")
    provider_updated_at = (
        _aware_datetime(provider_updated_raw, field="provider_updated_at")
        if provider_updated_raw is not None
        else None
    )
    if provider_published_at > first_seen_at:
        raise ValueError(f"provider_published_at cannot be after first_seen_at: {provider_item_id}")
    if first_seen_at > retrieved_at:
        raise ValueError(f"first_seen_at cannot be after retrieved_at: {provider_item_id}")
    if available_from < provider_published_at:
        raise ValueError(f"available_from cannot precede provider_published_at: {provider_item_id}")
    if availability_basis == "first_seen_at" and available_from < first_seen_at:
        raise ValueError(f"first_seen_at availability cannot be backdated: {provider_item_id}")
    if provider_updated_at is not None and provider_updated_at < provider_published_at:
        raise ValueError(f"provider_updated_at cannot precede provider_published_at: {provider_item_id}")
    if provider_updated_at is not None and provider_updated_at > first_seen_at:
        raise ValueError(f"provider_updated_at cannot be after first_seen_at: {provider_item_id}")
    raw_payload = record.get("raw_payload")
    normalized_payload = record.get("normalized_payload")
    if not isinstance(raw_payload, dict):
        raise ValueError(f"raw_payload must be an object: {provider_item_id}")
    if not isinstance(normalized_payload, dict):
        raise ValueError(f"normalized_payload must be an object: {provider_item_id}")
    _assert_no_secret_fields(raw_payload)
    news_curation: dict[str, Any] | None = None
    if content_class == "news_summary":
        raw_payload, normalized_payload, news_curation = validate_news_summary_payloads(
            raw_payload,
            dict(normalized_payload),
            provider_item_id=provider_item_id,
        )
    normalized_record = {
        "provider_id": provider_id,
        "provider_item_id": provider_item_id,
        "normalized_event_id": normalized_event_id,
        "revision_id": revision_id,
        "provider_published_at": provider_published_at.isoformat(),
        "provider_updated_at": provider_updated_at.isoformat() if provider_updated_at else None,
        "first_seen_at": first_seen_at.isoformat(),
        "available_from": available_from.isoformat(),
        "availability_basis": availability_basis,
        "availability_evidence_ref": availability_evidence_ref,
        "event_type": _required_text(record, "event_type"),
        "source_authority": _required_text(record, "source_authority"),
        "entities": sorted({str(value) for value in record.get("entities") or [] if str(value)}),
        "sectors": sorted({str(value) for value in record.get("sectors") or [] if str(value)}),
        "geographies": sorted({str(value) for value in record.get("geographies") or [] if str(value)}),
        "raw_payload": raw_payload,
        "normalized_payload": normalized_payload,
    }
    if news_curation is not None:
        normalized_record["_news_curation"] = news_curation
    return normalized_record


def _write_immutable_json(
    path: Path,
    payload: dict[str, Any],
    *,
    compact: bool = False,
    storage_budget: _StorageBudget | None = None,
) -> None:
    rendered = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        if compact
        else json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    rendered_bytes = rendered.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"immutable artifact collision: {path}")
        return
    if storage_budget is not None:
        storage_budget.ensure_can_add(len(rendered_bytes))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        if storage_budget is not None:
            storage_budget.record_addition(len(rendered_bytes))
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _artifact_file_row(root: Path, path: Path, *, artifact_kind: str) -> dict[str, Any]:
    return {
        "artifact_kind": artifact_kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": _file_digest(path),
        "byte_size": path.stat().st_size,
    }


def _manifest_identity_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "manifest_id"}


def materialize_external_context_pilot(
    input_payload: dict[str, Any],
    *,
    artifact_root: str | Path,
) -> dict[str, Any]:
    dataset_id, provider_id, content_class, retrieved_at, input_records = _validate_input(input_payload)
    root = Path(artifact_root).resolve()
    storage_budget = (
        _StorageBudget.from_root(root, hard_cap_bytes=NEWS_STORAGE_HARD_CAP_BYTES)
        if content_class == "news_summary"
        else None
    )
    normalized_records = [
        _validate_record(
            record,
            provider_id=provider_id,
            content_class=content_class,
            retrieved_at=retrieved_at,
        )
        for record in input_records
    ]
    curation_counts = {
        "relevance_excluded_count": 0,
        "duplicate_excluded_count": 0,
        "quota_excluded_count": 0,
    }
    if content_class == "news_summary":
        normalized_records, curation_counts = curate_news_records(normalized_records)
        if not normalized_records:
            raise ValueError("no news summaries passed relevance, deduplication, and daily quota gates")
    unique_versions = {
        (record["normalized_event_id"], record["revision_id"])
        for record in normalized_records
    }
    if len(unique_versions) != len(normalized_records):
        raise ValueError("normalized_event_id + revision_id must be unique")
    normalized_records.sort(
        key=lambda record: (
            record["normalized_event_id"],
            _aware_datetime(record["available_from"], field="available_from"),
            record["revision_id"],
        )
    )

    materialized: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []
    for record in normalized_records:
        raw_payload_bytes = _canonical_bytes(record["raw_payload"])
        raw_base = {
            "artifact_type": "external_context_raw_record",
            "schema_version": RAW_SCHEMA_VERSION,
            "provider_id": provider_id,
            "provider_item_id": record["provider_item_id"],
            "requested_at": retrieved_at.isoformat(),
            "first_seen_at": record["first_seen_at"],
            "provider_published_at": record["provider_published_at"],
            "provider_updated_at": record["provider_updated_at"],
            "received_at": retrieved_at.isoformat(),
            "source_endpoint": _required_text(input_payload, "source_endpoint"),
            "license_tier": _required_text(input_payload, "license_tier"),
            "content_bytes_sha256": hashlib.sha256(raw_payload_bytes).hexdigest(),
            "raw_payload": record["raw_payload"],
        }
        if content_class == "news_summary":
            raw_base["content_retention_mode"] = "summary_only_no_article_body"
        raw_id = f"raw-{_digest(raw_base)[:24]}"
        raw_document = {**raw_base, "raw_id": raw_id}
        raw_path = root / "raw" / "objects" / f"{raw_id}.json"
        _write_immutable_json(
            raw_path,
            raw_document,
            compact=content_class == "news_summary",
            storage_budget=storage_budget,
        )
        file_rows.append(_artifact_file_row(root, raw_path, artifact_kind="raw"))

        silver_base = {
            "artifact_type": "external_context_silver_record",
            "schema_version": SILVER_SCHEMA_VERSION,
            "normalized_event_id": record["normalized_event_id"],
            "revision_id": record["revision_id"],
            "canonical_timestamp": record["provider_published_at"],
            "available_from": record["available_from"],
            "availability_basis": record["availability_basis"],
            "availability_evidence_ref": record["availability_evidence_ref"],
            "source_authority": record["source_authority"],
            "event_type": record["event_type"],
            "entities": record["entities"],
            "sectors": record["sectors"],
            "geographies": record["geographies"],
            "normalized_payload": record["normalized_payload"],
            "raw_ids": [raw_id],
            "transform_version": TRANSFORM_VERSION,
        }
        silver_id = f"silver-{_digest(silver_base)[:24]}"
        silver_document = {**silver_base, "silver_id": silver_id}
        silver_path = root / "silver" / "records" / f"{silver_id}.json"
        _write_immutable_json(
            silver_path,
            silver_document,
            compact=content_class == "news_summary",
            storage_budget=storage_budget,
        )
        file_rows.append(_artifact_file_row(root, silver_path, artifact_kind="silver"))
        materialized.append({"record": record, "raw_id": raw_id, "silver_id": silver_id})

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in materialized:
        grouped.setdefault(row["record"]["normalized_event_id"], []).append(row)
    for event_rows in grouped.values():
        event_rows.sort(
            key=lambda row: _aware_datetime(row["record"]["available_from"], field="available_from")
        )
        available_times = [
            _aware_datetime(row["record"]["available_from"], field="available_from")
            for row in event_rows
        ]
        if len(set(available_times)) != len(available_times):
            raise ValueError("revisions for one normalized_event_id must have distinct available_from values")
        for index, row in enumerate(event_rows):
            record = row["record"]
            available_to = event_rows[index + 1]["record"]["available_from"] if index + 1 < len(event_rows) else None
            pit_base = {
                "artifact_type": "external_context_pit_record",
                "schema_version": PIT_SCHEMA_VERSION,
                "normalized_event_id": record["normalized_event_id"],
                "knowledge_version": record["revision_id"],
                "available_from": record["available_from"],
                "available_to": available_to,
                "availability_basis": record["availability_basis"],
                "availability_evidence_ref": record["availability_evidence_ref"],
                "raw_ids": [row["raw_id"]],
                "silver_ids": [row["silver_id"]],
                "feature_version": FEATURE_VERSION,
                "feature_value": record["normalized_payload"],
                "missingness_reason": None,
            }
            pit_id = f"pit-{_digest(pit_base)[:24]}"
            pit_document = {**pit_base, "pit_id": pit_id}
            pit_path = root / "pit" / "records" / f"{pit_id}.json"
            _write_immutable_json(
                pit_path,
                pit_document,
                compact=content_class == "news_summary",
                storage_budget=storage_budget,
            )
            file_rows.append(_artifact_file_row(root, pit_path, artifact_kind="pit"))

    file_rows.sort(key=lambda row: (row["artifact_kind"], row["relative_path"]))
    manifest = {
        "artifact_type": "external_context_replay_manifest",
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "provider_id": provider_id,
        "content_class": content_class,
        "retrieved_at": retrieved_at.isoformat(),
        "input_record_count": len(input_records),
        "record_count": len(normalized_records),
        "curation_counts": curation_counts,
        "artifact_files": file_rows,
        "temporal_contract": {
            "selection_rule": "available_from <= decision_cutoff < available_to",
            "historical_backdating_without_documented_evidence_forbidden": True,
            "latest_revision_backfill_forbidden": True,
        },
        "network_required": False,
        "v3_signal_changed": False,
        "claim_ceiling": "raw_silver_pit_replay_pilot_only",
    }
    if storage_budget is not None:
        manifest["news_storage_contract"] = {
            "content_retention_mode": "summary_only_no_article_body",
            "summary_max_chars": NEWS_SUMMARY_MAX_CHARS,
            "summary_max_bytes": NEWS_SUMMARY_MAX_BYTES,
            "target_bytes": NEWS_STORAGE_TARGET_BYTES,
            "hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
            "materialized_artifact_bytes": sum(row["byte_size"] for row in file_rows),
            "relevance_policy_version": NEWS_RELEVANCE_POLICY_VERSION,
            "daily_channel_limits": NEWS_DAILY_CHANNEL_LIMITS,
        }
    manifest_id = f"external-context-manifest-{_digest(_manifest_identity_payload(manifest))[:24]}"
    manifest = {**manifest, "manifest_id": manifest_id}
    manifest_path = root / "manifests" / f"{manifest_id}.json"
    _write_immutable_json(
        manifest_path,
        manifest,
        compact=content_class == "news_summary",
        storage_budget=storage_budget,
    )
    result = {"manifest_path": str(manifest_path), "manifest": manifest}
    if storage_budget is not None:
        result["storage_budget_observation"] = {
            "root_bytes_after_manifest": storage_budget.used_bytes,
            "target_bytes": NEWS_STORAGE_TARGET_BYTES,
            "hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
            "hard_cap_respected": storage_budget.used_bytes <= NEWS_STORAGE_HARD_CAP_BYTES,
        }
    return result


def _resolve_artifact_path(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manifest path escapes artifact root: {relative_path}") from exc
    return target


def replay_external_context_offline(
    manifest_path: str | Path,
    *,
    decision_cutoff: str,
) -> dict[str, Any]:
    cutoff = _aware_datetime(decision_cutoff, field="decision_cutoff")
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported manifest schema: {manifest.get('schema_version')}")
    expected_manifest_id = f"external-context-manifest-{_digest(_manifest_identity_payload(manifest))[:24]}"
    if manifest.get("manifest_id") != expected_manifest_id:
        raise ValueError("manifest identity digest mismatch")
    if manifest.get("network_required") is not False:
        raise ValueError("offline replay manifest must declare network_required=false")
    if manifest.get("v3_signal_changed") is not False:
        raise ValueError("research replay manifest cannot change the V3 signal")
    root = path.parent.parent.resolve()
    if manifest.get("content_class") == "news_summary":
        storage_contract = manifest.get("news_storage_contract")
        if not isinstance(storage_contract, dict):
            raise ValueError("news replay manifest must declare news_storage_contract")
        if storage_contract.get("hard_cap_bytes") != NEWS_STORAGE_HARD_CAP_BYTES:
            raise ValueError("news replay manifest storage hard cap does not match the active contract")
        if storage_contract.get("content_retention_mode") != "summary_only_no_article_body":
            raise ValueError("news replay manifest must remain summary-only")
        _StorageBudget.from_root(root, hard_cap_bytes=NEWS_STORAGE_HARD_CAP_BYTES)
    verified_files: list[dict[str, Any]] = []
    pit_documents: list[dict[str, Any]] = []
    for file_row in manifest.get("artifact_files") or []:
        relative_path = _required_text(file_row, "relative_path")
        target = _resolve_artifact_path(root, relative_path)
        if not target.is_file():
            raise ValueError(f"manifest artifact missing: {relative_path}")
        actual_digest = _file_digest(target)
        if actual_digest != file_row.get("sha256"):
            raise ValueError(f"artifact hash mismatch: {relative_path}")
        if target.stat().st_size != file_row.get("byte_size"):
            raise ValueError(f"artifact byte size mismatch: {relative_path}")
        verified_files.append({"relative_path": relative_path, "sha256": actual_digest})
        if file_row.get("artifact_kind") == "pit":
            pit_documents.append(json.loads(target.read_text(encoding="utf-8")))

    selected: list[dict[str, Any]] = []
    for record in pit_documents:
        available_from = _aware_datetime(record.get("available_from"), field="available_from")
        available_to_raw = record.get("available_to")
        available_to = (
            _aware_datetime(available_to_raw, field="available_to")
            if available_to_raw is not None
            else None
        )
        if available_from <= cutoff and (available_to is None or cutoff < available_to):
            selected.append(
                {
                    "pit_id": record.get("pit_id"),
                    "normalized_event_id": record.get("normalized_event_id"),
                    "knowledge_version": record.get("knowledge_version"),
                    "available_from": record.get("available_from"),
                    "available_to": record.get("available_to"),
                    "feature_version": record.get("feature_version"),
                    "feature_value": record.get("feature_value"),
                    "raw_ids": record.get("raw_ids") or [],
                    "silver_ids": record.get("silver_ids") or [],
                }
            )
    selected.sort(key=lambda row: (str(row["normalized_event_id"]), str(row["knowledge_version"])))
    if len({row["normalized_event_id"] for row in selected}) != len(selected):
        raise ValueError("PIT replay selected multiple visible revisions for one event")
    replay_identity = {
        "manifest_id": manifest["manifest_id"],
        "decision_cutoff": cutoff.isoformat(),
        "verified_files": verified_files,
        "selected_records": selected,
    }
    return {
        "artifact_type": "external_context_offline_replay",
        "schema_version": REPLAY_SCHEMA_VERSION,
        "manifest_id": manifest["manifest_id"],
        "decision_cutoff": cutoff.isoformat(),
        "network_used": False,
        "hash_verification_status": "passed",
        "verified_file_count": len(verified_files),
        "selected_record_count": len(selected),
        "selected_records": selected,
        "replay_digest": _digest(replay_identity),
        "v3_signal_changed": False,
        "claim_ceiling": "offline_replay_integrity_only",
    }


def write_replay_result(payload: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
