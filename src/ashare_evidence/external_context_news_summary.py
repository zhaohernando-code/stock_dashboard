from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

NEWS_RELEVANCE_POLICY_VERSION = "external_context_news_relevance.v1"
NEWS_SUMMARY_MAX_CHARS = 1_000
NEWS_SUMMARY_MAX_BYTES = 4_096
NEWS_HEADLINE_MAX_CHARS = 300
NEWS_SOURCE_URL_MAX_CHARS = 2_048
NEWS_RELEVANCE_MIN_SCORE = 0.65
NEWS_STORAGE_TARGET_BYTES = 1_610_612_736  # 1.5 GiB
NEWS_STORAGE_HARD_CAP_BYTES = 1_879_048_192  # 1.75 GiB; leaves headroom below 2 GiB.
NEWS_DAILY_CHANNEL_LIMITS = {
    "global_state": 12,
    "sector_state": 48,
    "individual_event": 90,
}
NEWS_RELEVANCE_WEIGHTS = {
    "global_state": {
        "global_topic_match": 0.45,
        "source_quality": 0.20,
        "novelty": 0.15,
        "time_lineage": 0.20,
    },
    "sector_state": {
        "sector_match": 0.35,
        "entity_match": 0.25,
        "source_quality": 0.15,
        "novelty": 0.15,
        "time_lineage": 0.10,
    },
    "individual_event": {
        "entity_match": 0.45,
        "sector_match": 0.15,
        "source_quality": 0.15,
        "novelty": 0.15,
        "time_lineage": 0.10,
    },
}
NEWS_RELEVANCE_COMPONENT_FLOORS = {
    "global_state": ("global_topic_match", 0.75),
    "sector_state": ("sector_match", 0.70),
    "individual_event": ("entity_match", 0.80),
}
NEWS_RAW_ALLOWED_FIELDS = {
    "content_hash",
    "headline",
    "language",
    "source_name",
    "source_url",
    "summary",
    "summary_method",
    "summary_model_version",
}
NEWS_NORMALIZED_ALLOWED_FIELDS = NEWS_RAW_ALLOWED_FIELDS | {
    "affected_symbols",
    "channel_scope",
    "relevance_components",
    "sector_ids",
    "topic_tags",
}
NEWS_SUMMARY_METHODS = {"source_provided", "extractive", "model_generated"}


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


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


def _bounded_text(
    payload: dict[str, Any],
    field: str,
    *,
    max_chars: int,
    max_bytes: int | None = None,
) -> str:
    value = _required_text(payload, field)
    if len(value) > max_chars:
        raise ValueError(f"{field} exceeds {max_chars} characters")
    encoded_size = len(value.encode())
    if max_bytes is not None and encoded_size > max_bytes:
        raise ValueError(f"{field} exceeds {max_bytes} UTF-8 bytes")
    return value


def _bounded_score(value: Any, *, field: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return score


def _validate_news_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    return value


def _news_relevance(
    normalized_payload: dict[str, Any],
    *,
    provider_item_id: str,
) -> dict[str, Any]:
    unexpected_fields = set(normalized_payload) - NEWS_NORMALIZED_ALLOWED_FIELDS
    if unexpected_fields:
        raise ValueError(
            f"news normalized_payload contains unsupported fields for {provider_item_id}: "
            f"{sorted(unexpected_fields)}"
        )
    channel_scope = _required_text(normalized_payload, "channel_scope")
    weights = NEWS_RELEVANCE_WEIGHTS.get(channel_scope)
    if weights is None:
        raise ValueError(f"unsupported news channel_scope: {channel_scope}")
    components_payload = normalized_payload.get("relevance_components")
    if not isinstance(components_payload, dict):
        raise ValueError(f"relevance_components must be an object: {provider_item_id}")
    unexpected_components = set(components_payload) - set(weights)
    if unexpected_components:
        raise ValueError(
            f"unexpected relevance components for {channel_scope}: {sorted(unexpected_components)}"
        )
    components = {
        component: _bounded_score(
            components_payload.get(component),
            field=f"relevance_components.{component}",
        )
        for component in weights
    }
    score = sum(components[component] * weight for component, weight in weights.items())
    floor_component, floor_value = NEWS_RELEVANCE_COMPONENT_FLOORS[channel_scope]
    floor_passed = components[floor_component] >= floor_value
    gate_passed = score >= NEWS_RELEVANCE_MIN_SCORE and floor_passed
    reasons = [
        component
        for component, component_score in sorted(
            components.items(),
            key=lambda row: (-row[1], row[0]),
        )
        if component_score >= 0.70
    ]
    return {
        "channel_scope": channel_scope,
        "components": components,
        "score": round(score, 8),
        "threshold": NEWS_RELEVANCE_MIN_SCORE,
        "floor_component": floor_component,
        "floor_value": floor_value,
        "floor_passed": floor_passed,
        "gate_passed": gate_passed,
        "reasons": reasons,
        "policy_version": NEWS_RELEVANCE_POLICY_VERSION,
    }


def validate_news_summary_payloads(
    raw_payload: dict[str, Any],
    normalized_payload: dict[str, Any],
    *,
    provider_item_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    unexpected_raw_fields = set(raw_payload) - NEWS_RAW_ALLOWED_FIELDS
    if unexpected_raw_fields:
        raise ValueError(
            f"news Raw must be summary-only for {provider_item_id}; unsupported fields: "
            f"{sorted(unexpected_raw_fields)}"
        )
    headline = _bounded_text(raw_payload, "headline", max_chars=NEWS_HEADLINE_MAX_CHARS)
    summary = _bounded_text(
        raw_payload,
        "summary",
        max_chars=NEWS_SUMMARY_MAX_CHARS,
        max_bytes=NEWS_SUMMARY_MAX_BYTES,
    )
    source_url = _validate_news_url(
        _bounded_text(raw_payload, "source_url", max_chars=NEWS_SOURCE_URL_MAX_CHARS)
    )
    source_name = _bounded_text(raw_payload, "source_name", max_chars=200)
    language = _bounded_text(raw_payload, "language", max_chars=32)
    content_hash = _required_text(raw_payload, "content_hash").lower()
    if len(content_hash) != 64 or any(character not in "0123456789abcdef" for character in content_hash):
        raise ValueError(f"content_hash must be a lowercase SHA-256 hex digest: {provider_item_id}")
    summary_method = _required_text(raw_payload, "summary_method")
    if summary_method not in NEWS_SUMMARY_METHODS:
        raise ValueError(f"unsupported summary_method: {summary_method}")
    summary_model_version = raw_payload.get("summary_model_version")
    if summary_method == "model_generated":
        if not isinstance(summary_model_version, str) or not summary_model_version.strip():
            raise ValueError("model_generated news summaries require summary_model_version")
    elif summary_model_version is not None:
        raise ValueError("summary_model_version is only allowed for model_generated summaries")

    for field, expected in {
        "content_hash": content_hash,
        "headline": headline,
        "language": language,
        "source_name": source_name,
        "source_url": source_url,
        "summary": summary,
        "summary_method": summary_method,
        "summary_model_version": summary_model_version,
    }.items():
        if normalized_payload.get(field) != expected:
            raise ValueError(f"news normalized_payload.{field} must match Raw: {provider_item_id}")

    for field in ("affected_symbols", "sector_ids", "topic_tags"):
        values = normalized_payload.get(field)
        if not isinstance(values, list):
            raise ValueError(f"news normalized_payload.{field} must be a list: {provider_item_id}")
        normalized_payload[field] = sorted({str(value).strip() for value in values if str(value).strip()})

    channel_scope = normalized_payload.get("channel_scope")
    if channel_scope == "individual_event" and not normalized_payload["affected_symbols"]:
        raise ValueError(f"individual_event news requires affected_symbols: {provider_item_id}")
    if channel_scope == "sector_state" and not normalized_payload["sector_ids"]:
        raise ValueError(f"sector_state news requires sector_ids: {provider_item_id}")
    if not normalized_payload["topic_tags"]:
        raise ValueError(f"news summary requires at least one topic tag: {provider_item_id}")

    relevance = _news_relevance(normalized_payload, provider_item_id=provider_item_id)
    normalized_payload = {**normalized_payload, "relevance_gate": relevance}
    dedupe_key = hashlib.sha256(
        f"{source_url}\n{content_hash}\n{headline}".encode()
    ).hexdigest()
    return raw_payload, normalized_payload, {"dedupe_key": dedupe_key, "relevance": relevance}


def curate_news_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    relevant = [record for record in records if record["_news_curation"]["relevance"]["gate_passed"]]
    relevance_excluded_count = len(records) - len(relevant)
    best_by_dedupe_key: dict[str, dict[str, Any]] = {}
    for record in relevant:
        dedupe_key = record["_news_curation"]["dedupe_key"]
        current = best_by_dedupe_key.get(dedupe_key)
        candidate_order = (
            -record["_news_curation"]["relevance"]["score"],
            record["available_from"],
            record["provider_item_id"],
        )
        if current is None:
            best_by_dedupe_key[dedupe_key] = record
            continue
        current_order = (
            -current["_news_curation"]["relevance"]["score"],
            current["available_from"],
            current["provider_item_id"],
        )
        if candidate_order < current_order:
            best_by_dedupe_key[dedupe_key] = record
    deduplicated = list(best_by_dedupe_key.values())
    duplicate_excluded_count = len(relevant) - len(deduplicated)

    daily_channel_counts: dict[tuple[str, str], int] = {}
    selected: list[dict[str, Any]] = []
    quota_excluded_count = 0
    deduplicated.sort(
        key=lambda record: (
            _aware_datetime(record["available_from"], field="available_from").astimezone(UTC).date(),
            record["_news_curation"]["relevance"]["channel_scope"],
            -record["_news_curation"]["relevance"]["score"],
            record["provider_item_id"],
        )
    )
    for record in deduplicated:
        decision_date = (
            _aware_datetime(record["available_from"], field="available_from")
            .astimezone(UTC)
            .date()
            .isoformat()
        )
        channel_scope = record["_news_curation"]["relevance"]["channel_scope"]
        count_key = (decision_date, channel_scope)
        used_count = daily_channel_counts.get(count_key, 0)
        if used_count >= NEWS_DAILY_CHANNEL_LIMITS[channel_scope]:
            quota_excluded_count += 1
            continue
        daily_channel_counts[count_key] = used_count + 1
        record = dict(record)
        record.pop("_news_curation", None)
        selected.append(record)
    return selected, {
        "relevance_excluded_count": relevance_excluded_count,
        "duplicate_excluded_count": duplicate_excluded_count,
        "quota_excluded_count": quota_excluded_count,
    }
