from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import ProviderCredential
from ashare_evidence.tushare_transport import DEFAULT_TUSHARE_BASE_URL, post_tushare, secure_tushare_base_url

SCHEMA_VERSION = "external_context_sector_membership_snapshot.v1"
PROVIDER_ID = "tushare_sw2021_index_member_all"
ATTRIBUTION = "hernando_zhao / Tushare / Shenwan Hongyuan Research"
CLASSIFICATION_FIELDS = "index_code,industry_name,level,industry_code,is_pub,parent_code,src"
MEMBERSHIP_FIELDS = "l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,ts_code,name,in_date,out_date,is_new"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _response_rows(response: dict[str, Any] | None, *, api_name: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise RuntimeError(f"Tushare {api_name} returned no response")
    if int(response.get("code") or 0) != 0:
        message = str(response.get("msg") or response.get("message") or "unknown provider error")
        raise RuntimeError(f"Tushare {api_name} failed: {message}")
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("fields"), list) or not isinstance(data.get("items"), list):
        raise RuntimeError(f"Tushare {api_name} returned an invalid data envelope")
    fields = [str(value) for value in data["fields"]]
    rows: list[dict[str, Any]] = []
    for item in data["items"]:
        if not isinstance(item, list) or len(item) != len(fields):
            raise RuntimeError(f"Tushare {api_name} returned a malformed row")
        rows.append(dict(zip(fields, item, strict=True)))
    return rows


def _parse_date(value: Any, *, required: bool) -> date | None:
    if value in {None, ""}:
        if required:
            raise ValueError("membership in_date is required")
        return None
    return datetime.strptime(str(value), "%Y%m%d").date()


def _normalize_memberships(
    rows: list[dict[str, Any]],
    *,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    normalized: dict[tuple[str, str, str], dict[str, Any]] = {}
    exclusions: dict[str, int] = {}
    for row in rows:
        symbol = str(row.get("ts_code") or "").upper()
        l1_code = str(row.get("l1_code") or "")
        if not symbol or not l1_code:
            exclusions["missing_symbol_or_l1_code"] = exclusions.get("missing_symbol_or_l1_code", 0) + 1
            continue
        try:
            effective_from_day = _parse_date(row.get("in_date"), required=True)
            effective_to_day = _parse_date(row.get("out_date"), required=False)
        except ValueError:
            exclusions["invalid_or_missing_effective_date"] = exclusions.get(
                "invalid_or_missing_effective_date", 0
            ) + 1
            continue
        assert effective_from_day is not None
        if effective_to_day is not None and effective_to_day <= effective_from_day:
            exclusions["non_positive_effective_interval"] = exclusions.get(
                "non_positive_effective_interval", 0
            ) + 1
            continue
        effective_from = datetime.combine(effective_from_day, datetime_time.min, tzinfo=SHANGHAI)
        effective_to = (
            datetime.combine(effective_to_day, datetime_time.min, tzinfo=SHANGHAI)
            if effective_to_day is not None
            else None
        )
        research_effective_available_at = datetime.combine(
            effective_from_day, datetime_time(23, 59, 59), tzinfo=SHANGHAI
        )
        material = {
            "symbol": symbol,
            "stock_name": str(row.get("name") or ""),
            "l1_code": l1_code,
            "l1_name": str(row.get("l1_name") or ""),
            "l2_code": str(row.get("l2_code") or ""),
            "l2_name": str(row.get("l2_name") or ""),
            "l3_code": str(row.get("l3_code") or ""),
            "l3_name": str(row.get("l3_name") or ""),
            "effective_from": effective_from.isoformat(),
            "effective_to_exclusive": effective_to.isoformat() if effective_to is not None else None,
            "provider_current_flag": str(row.get("is_new") or ""),
            "published_at": None,
            "first_seen_at": retrieved_at.astimezone(UTC).isoformat(),
            "available_at": retrieved_at.astimezone(UTC).isoformat(),
            "research_effective_available_at": research_effective_available_at.isoformat(),
            "availability_contract": {
                "strict_pit": "available_at <= decision_cutoff",
                "provisional_effective_date_research": (
                    "research_effective_available_at <= decision_cutoff; historical first_seen/revision lineage absent"
                ),
            },
        }
        material["row_digest"] = _digest(material)
        key = (symbol, l1_code, effective_from_day.isoformat())
        existing = normalized.get(key)
        if existing is not None and existing != material:
            raise ValueError(f"conflicting SW membership row: {key}")
        normalized[key] = material
    records = sorted(normalized.values(), key=lambda item: (item["symbol"], item["effective_from"], item["l1_code"]))
    return records, exclusions


def _overlap_count(records: list[dict[str, Any]]) -> int:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_symbol.setdefault(str(row["symbol"]), []).append(row)
    overlaps = 0
    for rows in by_symbol.values():
        ordered = sorted(rows, key=lambda item: (str(item["effective_from"]), str(item["l1_code"])))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            previous_to = previous.get("effective_to_exclusive")
            if previous_to is None or str(previous_to) > str(current["effective_from"]):
                overlaps += 1
    return overlaps


def build_sector_membership_snapshot(
    *,
    classification_response: dict[str, Any],
    membership_responses: list[dict[str, Any]],
    membership_requests: list[dict[str, str]],
    retrieved_at: datetime,
    source_endpoint: str,
) -> dict[str, Any]:
    classifications = _response_rows(classification_response, api_name="index_classify")
    l1_codes = {
        str(row.get("index_code") or ""): str(row.get("industry_name") or "")
        for row in classifications
        if str(row.get("level") or "") == "L1" and str(row.get("src") or "") == "SW2021"
    }
    if len(l1_codes) < 30:
        raise ValueError("SW2021 L1 classification coverage is incomplete")
    raw_rows: list[dict[str, Any]] = []
    for response in membership_responses:
        response_rows = _response_rows(response, api_name="index_member_all")
        if len(response_rows) >= 2_000:
            raise ValueError("SW membership response reached the documented single-call row ceiling")
        raw_rows.extend(response_rows)
    records, exclusions = _normalize_memberships(raw_rows, retrieved_at=retrieved_at)
    observed_l1 = {str(row["l1_code"]) for row in records}
    missing_l1_codes = sorted(set(l1_codes) - observed_l1)
    overlaps = _overlap_count(records)
    symbol_count = len({str(row["symbol"]) for row in records})
    quality = {
        "classification_l1_count": len(l1_codes),
        "raw_row_count": len(raw_rows),
        "normalized_row_count": len(records),
        "symbol_count": symbol_count,
        "current_row_count": sum(str(row["provider_current_flag"]) == "Y" for row in records),
        "historical_row_count": sum(str(row["provider_current_flag"]) == "N" for row in records),
        "effective_interval_overlap_count": overlaps,
        "missing_l1_codes": missing_l1_codes,
        "exclusion_counts": exclusions,
    }
    effective_ready = len(l1_codes) >= 30 and symbol_count >= 3_000 and not missing_l1_codes and overlaps == 0
    material = {
        "artifact_type": "external_context_sector_membership_snapshot",
        "schema_version": SCHEMA_VERSION,
        "provider_id": PROVIDER_ID,
        "retrieved_at": retrieved_at.astimezone(UTC).isoformat(),
        "source_endpoint": secure_tushare_base_url(source_endpoint),
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": ATTRIBUTION,
        "raw": {
            "classification_response": classification_response,
            "membership_responses": membership_responses,
            "classification_response_digest": _digest(classification_response),
            "membership_response_digests": [_digest(response) for response in membership_responses],
            "membership_requests": membership_requests,
            "raw_payload_retained": True,
            "credential_or_token_retained": False,
        },
        "normalized": {"records": records},
        "quality": quality,
        "readiness": {
            "effective_dated_research_ready": effective_ready,
            "strict_historical_pit_ready": False,
            "strict_blockers": [
                "provider_published_at_missing",
                "historical_first_seen_at_missing",
                "provider_revision_lineage_missing",
            ],
        },
        "claim_ceiling": "effective_dated_provisional_sector_research_not_strict_historical_pit_vendor_vintage",
        "v3_signal_changed": False,
    }
    return {**material, "content_digest": _digest(material)}


def acquire_tushare_sector_membership_snapshot(
    session: Session,
    *,
    retrieved_at: datetime | None = None,
    request_fn: Callable[..., dict[str, Any] | None] = post_tushare,
    sleeper: Callable[[float], None] = time.sleep,
    min_request_interval_seconds: float = 0.2,
    max_attempts: int = 3,
    progress_fn: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )
    if credential is None or not credential.access_token:
        raise ValueError("enabled Tushare credential is not configured")
    base_url = secure_tushare_base_url(credential.base_url or DEFAULT_TUSHARE_BASE_URL)
    token = credential.access_token.strip()

    def request(api_name: str, params: dict[str, str], fields: str) -> dict[str, Any]:
        for attempt in range(1, max_attempts + 1):
            response = request_fn(
                base_url=base_url,
                token=token,
                api_name=api_name,
                params=params,
                fields=fields,
                timeout_seconds=30.0,
            )
            try:
                _response_rows(response, api_name=api_name)
            except RuntimeError:
                if response is not None or attempt >= max_attempts:
                    raise
            else:
                assert response is not None
                return response
            sleeper(float(2 ** (attempt - 1)))
        raise RuntimeError(f"Tushare {api_name} exhausted retries")

    classification_response = request(
        "index_classify",
        {"level": "L1", "src": "SW2021"},
        CLASSIFICATION_FIELDS,
    )
    classifications = _response_rows(classification_response, api_name="index_classify")
    l1_codes = sorted(
        {
            str(row.get("index_code") or "")
            for row in classifications
            if str(row.get("level") or "") == "L1" and str(row.get("src") or "") == "SW2021"
        }
    )
    requests = [{"l1_code": code, "is_new": flag} for code in l1_codes for flag in ("Y", "N")]
    responses: list[dict[str, Any]] = []
    for index, params in enumerate(requests, start=1):
        if responses and min_request_interval_seconds > 0:
            sleeper(min_request_interval_seconds)
        response = request("index_member_all", params, MEMBERSHIP_FIELDS)
        responses.append(response)
        if progress_fn is not None:
            progress_fn(
                {
                    "completed_requests": index,
                    "total_requests": len(requests),
                    "l1_code": params["l1_code"],
                    "is_new": params["is_new"],
                    "row_count": len(_response_rows(response, api_name="index_member_all")),
                }
            )
    return build_sector_membership_snapshot(
        classification_response=classification_response,
        membership_responses=responses,
        membership_requests=requests,
        retrieved_at=retrieved_at or datetime.now(UTC),
        source_endpoint=base_url,
    )


def sector_memberships_as_of(
    snapshot: dict[str, Any],
    *,
    decision_cutoff: datetime,
    mode: str = "strict_pit",
) -> dict[str, dict[str, Any]]:
    if decision_cutoff.tzinfo is None or decision_cutoff.utcoffset() is None:
        raise ValueError("decision_cutoff must include a timezone")
    if mode not in {"strict_pit", "effective_date_research"}:
        raise ValueError("mode must be strict_pit or effective_date_research")
    cutoff = decision_cutoff.astimezone(UTC)
    selected: dict[str, dict[str, Any]] = {}
    for row in (snapshot.get("normalized") or {}).get("records") or []:
        availability_field = "available_at" if mode == "strict_pit" else "research_effective_available_at"
        available_at = datetime.fromisoformat(str(row[availability_field])).astimezone(UTC)
        effective_from = datetime.fromisoformat(str(row["effective_from"])).astimezone(UTC)
        effective_to = (
            datetime.fromisoformat(str(row["effective_to_exclusive"])).astimezone(UTC)
            if row.get("effective_to_exclusive")
            else None
        )
        if available_at > cutoff or effective_from > cutoff or (effective_to is not None and cutoff >= effective_to):
            continue
        symbol = str(row["symbol"])
        if symbol in selected:
            raise ValueError(f"multiple active SW L1 memberships for {symbol} at {decision_cutoff.isoformat()}")
        selected[symbol] = row
    return selected


def write_sector_membership_snapshot(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if _digest(material) != payload.get("content_digest"):
        raise ValueError("sector membership snapshot content digest mismatch")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable sector membership snapshot collision: {target}")
    if not target.exists():
        target.write_text(rendered, encoding="utf-8")
    return target


__all__ = [
    "SCHEMA_VERSION",
    "acquire_tushare_sector_membership_snapshot",
    "build_sector_membership_snapshot",
    "sector_memberships_as_of",
    "write_sector_membership_snapshot",
]
