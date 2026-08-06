from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

GLOBAL_MARKET_EXPORT_SCHEMA_VERSION = "external_context_global_market_vendor_export.v1"
GLOBAL_MARKET_IMPORT_AUDIT_VERSION = "external_context_global_market_import_audit.v1"
GLOBAL_MARKET_SUPPORTED_PROVIDERS = {
    "wind_global_market": "licensed_enterprise_market_data_vendor",
    "tushare_index_global": "low_cost_market_data_aggregator",
    "tiingo_eod": "low_cost_market_data_aggregator",
}
GLOBAL_MARKET_FROZEN_INSTRUMENTS = {
    "SPX",
    "IXIC",
    "SOX_OR_SEMICONDUCTOR_INDEX",
    "HKTECH",
    "HSI",
    "USD_CNH",
    "US10Y",
    "WTI",
}


def _text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _aware(payload: dict[str, Any], key: str) -> datetime:
    value = _text(payload, key)
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO-8601 datetime") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError(f"{key} must include a timezone")
    return resolved


def _number(payload: dict[str, Any], key: str, *, nullable: bool = False) -> float | None:
    value = payload.get(key)
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def build_global_market_pilot_from_vendor_export(envelope: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("schema_version") != GLOBAL_MARKET_EXPORT_SCHEMA_VERSION:
        raise ValueError("unsupported global-market vendor export schema")
    provider_id = _text(envelope, "provider_id")
    if provider_id not in GLOBAL_MARKET_SUPPORTED_PROVIDERS:
        raise ValueError(f"provider is outside the frozen V2 global-market candidate set: {provider_id}")
    if envelope.get("local_frozen_replay_approved") is not True:
        raise ValueError("local_frozen_replay_approved must be true with provider rights evidence")
    rights_evidence_ref = _text(envelope, "rights_evidence_ref")
    revision_semantics_evidence_ref = _text(envelope, "revision_semantics_evidence_ref")
    retrieved_at = _aware(envelope, "retrieved_at")
    records = envelope.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty list")
    seen_versions: set[tuple[str, str, str]] = set()
    pilot_records: list[dict[str, Any]] = []
    coverage: Counter[str] = Counter()
    observation_dates: dict[str, list[str]] = {}
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"record {index} must be an object")
        instrument_id = _text(row, "instrument_id").upper()
        if instrument_id not in GLOBAL_MARKET_FROZEN_INSTRUMENTS:
            raise ValueError(f"record {index} instrument is outside the frozen basket: {instrument_id}")
        if row.get("vendor_revision_is_provider_supplied") is not True:
            raise ValueError(f"record {index} lacks a provider-supplied revision identifier")
        provider_item_id = _text(row, "provider_item_id")
        revision_id = _text(row, "revision_id")
        observation_at = _aware(row, "observation_at")
        provider_published_at = _aware(row, "published_at")
        available_at = _aware(row, "available_at")
        first_seen_at = _aware(row, "first_seen_at")
        if not observation_at <= provider_published_at <= available_at <= first_seen_at <= retrieved_at:
            raise ValueError(
                f"record {index} must satisfy observation_at <= published_at <= available_at <= "
                "first_seen_at <= retrieved_at"
            )
        provider_updated_at = None
        if row.get("provider_updated_at") is not None:
            provider_updated_at = _aware(row, "provider_updated_at")
            if not provider_published_at <= provider_updated_at <= first_seen_at:
                raise ValueError(f"record {index} provider_updated_at is outside its valid lineage interval")
        open_value = _number(row, "open")
        high_value = _number(row, "high")
        low_value = _number(row, "low")
        close_value = _number(row, "close")
        volume_value = _number(row, "volume", nullable=True)
        if min(open_value, high_value, low_value, close_value) <= 0:
            raise ValueError(f"record {index} OHLC values must be positive")
        if high_value < max(open_value, close_value) or low_value > min(open_value, close_value):
            raise ValueError(f"record {index} violates OHLC bounds")
        version_key = (instrument_id, observation_at.isoformat(), revision_id)
        if version_key in seen_versions:
            raise ValueError(f"duplicate instrument observation revision: {version_key}")
        seen_versions.add(version_key)
        raw_payload = {
            "instrument_id": instrument_id,
            "observation_at": observation_at.isoformat(),
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close_value,
            "volume": volume_value,
            "currency": _text(row, "currency").upper(),
            "calendar": _text(row, "calendar"),
            "adjustment_status": _text(row, "adjustment_status"),
            "provider_item_id": provider_item_id,
            "revision_id": revision_id,
            "vendor_revision_is_provider_supplied": True,
        }
        normalized_event_id = f"global-market:{instrument_id}:{observation_at.isoformat()}"
        pilot_records.append(
            {
                "provider_item_id": provider_item_id,
                "normalized_event_id": normalized_event_id,
                "revision_id": revision_id,
                "provider_published_at": provider_published_at.isoformat(),
                "provider_updated_at": provider_updated_at.isoformat() if provider_updated_at else None,
                "first_seen_at": first_seen_at.isoformat(),
                "available_from": available_at.isoformat(),
                "availability_basis": "provider_effective_at_documented",
                "availability_evidence_ref": revision_semantics_evidence_ref,
                "event_type": "global_market_daily_observation",
                "source_authority": GLOBAL_MARKET_SUPPORTED_PROVIDERS[provider_id],
                "entities": [instrument_id],
                "sectors": ["global_market"],
                "geographies": [],
                "raw_payload": raw_payload,
                "normalized_payload": {
                    **raw_payload,
                    "affected_symbols": [],
                    "channel_scope": "global_state",
                    "sector_ids": ["global_market"],
                    "topic_tags": ["global_market_state"],
                },
            }
        )
        coverage[instrument_id] += 1
        observation_dates.setdefault(instrument_id, []).append(observation_at.date().isoformat())
    pilot_records.sort(key=lambda row: (row["available_from"], row["provider_item_id"], row["revision_id"]))
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": _text(envelope, "dataset_id"),
        "provider_id": provider_id,
        "content_class": "market_data",
        "source_endpoint": _text(envelope, "source_endpoint"),
        "license_tier": _text(envelope, "license_tier"),
        "attribution": _text(envelope, "attribution"),
        "retrieved_at": retrieved_at.isoformat(),
        "records": pilot_records,
    }
    audit = {
        "artifact_type": "external_context_global_market_import_audit",
        "schema_version": GLOBAL_MARKET_IMPORT_AUDIT_VERSION,
        "provider_id": provider_id,
        "dataset_id": pilot_input["dataset_id"],
        "record_count": len(pilot_records),
        "instrument_count": len(coverage),
        "instrument_counts": dict(sorted(coverage.items())),
        "instrument_date_ranges": {
            instrument: {"min": min(dates), "max": max(dates)}
            for instrument, dates in sorted(observation_dates.items())
        },
        "required_lineage_fields_complete": True,
        "provider_revision_ids_required": True,
        "provider_revision_semantics_evidence_ref": revision_semantics_evidence_ref,
        "local_frozen_replay_rights_evidence_ref": rights_evidence_ref,
        "frozen_basket_missing_instruments": sorted(GLOBAL_MARKET_FROZEN_INSTRUMENTS - set(coverage)),
        "full713_coverage_claimed": False,
        "v3_signal_changed": False,
        "claim_ceiling": "validated_vendor_export_import_only",
    }
    return {"audit": audit, "pilot_input": pilot_input}
