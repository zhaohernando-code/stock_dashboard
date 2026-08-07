from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.intraday_market import DEFAULT_TUSHARE_BASE_URL, _post_tushare
from ashare_evidence.models import ProviderCredential

SCHEMA_VERSION = "external_context_global_market_research_snapshot.v1"
SUPPORTED_INSTRUMENTS = ("SPX", "IXIC", "HSI", "HKTECH")
US_INSTRUMENTS = frozenset({"SPX", "IXIC", "DJI"})
SHANGHAI = ZoneInfo("Asia/Shanghai")


def stable_digest(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _response_rows(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise ValueError("Tushare returned no response")
    if int(response.get("code") or 0) != 0:
        raise ValueError(f"Tushare request failed: {response.get('msg') or response.get('message')}")
    data = response.get("data") or {}
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not isinstance(fields, list) or not isinstance(items, list):
        raise ValueError("Tushare response has an invalid data envelope")
    return [dict(zip(fields, item, strict=False)) for item in items]


def _available_at(instrument_id: str, trade_day: date) -> datetime:
    if instrument_id in US_INSTRUMENTS:
        # The U.S. close for calendar day D is unavailable at the A-share D post-close
        # decision. Eight o'clock on D+1 is a conservative DST-independent boundary.
        return datetime.combine(trade_day + timedelta(days=1), time(8, 0), tzinfo=SHANGHAI)
    return datetime.combine(trade_day, time(18, 0), tzinfo=SHANGHAI)


def normalize_tushare_global_rows(
    rows_by_instrument: dict[str, Iterable[dict[str, Any]]],
    *,
    retrieved_at: datetime,
) -> list[dict[str, Any]]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_instrument, rows in sorted(rows_by_instrument.items()):
        instrument_id = raw_instrument.strip().upper()
        if instrument_id not in SUPPORTED_INSTRUMENTS:
            raise ValueError(f"unsupported research instrument: {instrument_id}")
        for raw in rows:
            raw_day = str(raw.get("trade_date") or "")
            try:
                trade_day = datetime.strptime(raw_day, "%Y%m%d").date()
            except ValueError as exc:
                raise ValueError(f"invalid trade_date for {instrument_id}: {raw_day}") from exc
            key = (instrument_id, trade_day.isoformat())
            if key in seen:
                raise ValueError(f"duplicate instrument date: {key}")
            seen.add(key)
            values = {name: float(raw[name]) for name in ("open", "high", "low", "close")}
            if min(values.values()) <= 0:
                raise ValueError(f"non-positive OHLC value: {key}")
            if values["high"] < values["close"] or values["low"] > values["close"]:
                raise ValueError(f"close violates high/low bounds: {key}")
            open_outside_high_low = not values["low"] <= values["open"] <= values["high"]
            available_at = _available_at(instrument_id, trade_day)
            if available_at.astimezone(UTC) > retrieved_at.astimezone(UTC):
                raise ValueError(f"future market observation returned by provider: {key}")
            normalized.append(
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_day.isoformat(),
                    "available_at": available_at.isoformat(),
                    "availability_basis": (
                        "next_calendar_day_0800_asia_shanghai_after_us_close"
                        if instrument_id in US_INSTRUMENTS
                        else "same_calendar_day_1800_asia_shanghai_after_hk_close"
                    ),
                    **values,
                    "volume": None if raw.get("vol") is None else float(raw["vol"]),
                    "open_outside_high_low": open_outside_high_low,
                }
            )
    return sorted(normalized, key=lambda row: (row["instrument_id"], row["trade_date"]))


def build_research_snapshot(
    *,
    rows_by_instrument: dict[str, Iterable[dict[str, Any]]],
    retrieved_at: datetime,
    source_endpoint: str,
) -> dict[str, Any]:
    records = normalize_tushare_global_rows(rows_by_instrument, retrieved_at=retrieved_at)
    counts: dict[str, int] = defaultdict(int)
    dates: dict[str, list[str]] = defaultdict(list)
    for record in records:
        instrument = str(record["instrument_id"])
        counts[instrument] += 1
        dates[instrument].append(str(record["trade_date"]))
    material = {
        "artifact_type": "external_context_global_market_research_snapshot",
        "schema_version": SCHEMA_VERSION,
        "provider_id": "tushare_index_global",
        "retrieved_at": retrieved_at.isoformat(),
        "source_endpoint": source_endpoint,
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": "hernando_zhao / Tushare",
        "provider_revision_id_available": False,
        "promotion_blocker": "provider_revision_lineage_missing_requires_qualified_vendor_reproduction",
        "claim_ceiling": "provisional_transport_stable_research_input_not_production_pit_vendor_data",
        "records": records,
        "quality": {
            "record_count": len(records),
            "instrument_counts": dict(sorted(counts.items())),
            "instrument_date_ranges": {
                instrument: {"min": min(values), "max": max(values)}
                for instrument, values in sorted(dates.items())
            },
            "duplicate_instrument_date_count": 0,
            "future_available_at_count": 0,
            "open_outside_high_low_count": sum(bool(row["open_outside_high_low"]) for row in records),
            "feature_price_field": "close_only_open_high_low_retained_for_quality_audit",
        },
    }
    return {**material, "content_digest": stable_digest(material)}


def acquire_tushare_global_market_research_snapshot(
    session: Session,
    *,
    start: date,
    end: date,
    instruments: tuple[str, ...] = SUPPORTED_INSTRUMENTS,
    retrieved_at: datetime | None = None,
    max_attempts: int = 3,
    request_fn: Callable[..., dict[str, Any] | None] = _post_tushare,
) -> dict[str, Any]:
    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )
    if credential is None or not credential.access_token:
        raise ValueError("enabled Tushare credential is not configured")
    base_url = (credential.base_url or DEFAULT_TUSHARE_BASE_URL).strip()
    rows_by_instrument: dict[str, list[dict[str, Any]]] = {}
    for raw_instrument in instruments:
        instrument = raw_instrument.strip().upper()
        response: dict[str, Any] | None = None
        last_error: Exception | None = None
        for _attempt in range(max(1, max_attempts)):
            try:
                response = request_fn(
                    base_url=base_url,
                    token=credential.access_token.strip(),
                    api_name="index_global",
                    params={
                        "ts_code": instrument,
                        "start_date": start.strftime("%Y%m%d"),
                        "end_date": end.strftime("%Y%m%d"),
                    },
                    fields="ts_code,trade_date,open,close,high,low,vol",
                )
                rows_by_instrument[instrument] = _response_rows(response)
                last_error = None
                break
            except (OSError, ValueError) as exc:
                last_error = exc
        if last_error is not None:
            raise ValueError(f"failed to acquire {instrument}: {last_error}") from last_error
    resolved_retrieved_at = retrieved_at or datetime.now(UTC)
    return build_research_snapshot(
        rows_by_instrument=rows_by_instrument,
        retrieved_at=resolved_retrieved_at,
        source_endpoint=base_url,
    )


def write_research_snapshot(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("global-market snapshot content digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != rendered:
            raise ValueError(f"immutable research snapshot already exists with different content: {path}")
        return
    path.write_text(rendered, encoding="utf-8")


def load_research_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported global-market research snapshot schema")
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("global-market snapshot content digest mismatch")
    return payload


def market_state_by_decision_date(
    records: Iterable[dict[str, Any]],
    *,
    decision_dates: Iterable[date],
) -> dict[str, dict[str, Any]]:
    by_instrument: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_instrument[str(record["instrument_id"])].append(record)
    for rows in by_instrument.values():
        rows.sort(key=lambda row: str(row["available_at"]))
    result: dict[str, dict[str, Any]] = {}
    for decision_day in sorted(set(decision_dates)):
        cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
        instrument_features: dict[str, dict[str, Any]] = {}
        for instrument, rows in sorted(by_instrument.items()):
            available = [row for row in rows if datetime.fromisoformat(str(row["available_at"])) <= cutoff]
            if not available:
                continue
            closes = [float(row["close"]) for row in available]
            latest = available[-1]

            def trailing_return(period: int) -> float | None:
                if len(closes) <= period:
                    return None
                return closes[-1] / closes[-period - 1] - 1.0

            instrument_features[instrument] = {
                "observation_date": latest["trade_date"],
                "available_at": latest["available_at"],
                "return_1d": trailing_return(1),
                "return_5d": trailing_return(5),
                "return_20d": trailing_return(20),
                "drawdown_20d": closes[-1] / max(closes[-20:]) - 1.0 if len(closes) >= 20 else None,
            }
        required = set(SUPPORTED_INSTRUMENTS)
        if not required.issubset(instrument_features):
            continue

        def value(instrument: str, field: str) -> float:
            raw = instrument_features[instrument][field]
            if raw is None:
                raise ValueError(f"insufficient warmup for {instrument} {field} on {decision_day}")
            return float(raw)

        returns_5d = [value(instrument, "return_5d") for instrument in SUPPORTED_INSTRUMENTS]
        returns_20d = [value(instrument, "return_20d") for instrument in SUPPORTED_INSTRUMENTS]
        result[decision_day.isoformat()] = {
            "decision_cutoff": cutoff.isoformat(),
            "instruments": instrument_features,
            "global_mean_return_5d": sum(returns_5d) / len(returns_5d),
            "global_mean_return_20d": sum(returns_20d) / len(returns_20d),
            "global_breadth_5d": sum(item > 0 for item in returns_5d) / len(returns_5d),
            "global_breadth_20d": sum(item > 0 for item in returns_20d) / len(returns_20d),
            "tech_relative_5d": 0.5
            * ((value("IXIC", "return_5d") - value("SPX", "return_5d"))
               + (value("HKTECH", "return_5d") - value("HSI", "return_5d"))),
            "tech_relative_20d": 0.5
            * ((value("IXIC", "return_20d") - value("SPX", "return_20d"))
               + (value("HKTECH", "return_20d") - value("HSI", "return_20d"))),
        }
    return result
