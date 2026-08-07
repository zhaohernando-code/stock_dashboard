from __future__ import annotations

import csv
import hashlib
import io
import json
import ssl
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib import parse, request
from zoneinfo import ZoneInfo

import certifi
from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.intraday_market import DEFAULT_TUSHARE_BASE_URL, _post_tushare
from ashare_evidence.models import ProviderCredential

SCHEMA_VERSION = "external_context_macro_research_snapshot.v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
FRED_CSV_ENDPOINT = "https://fred.stlouisfed.org/graph/fredgraph.csv"


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


def _fred_csv(*, series_id: str, start: date, end: date, timeout: int = 20) -> str:
    query = parse.urlencode({"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()})
    context = ssl.create_default_context(cafile=certifi.where())
    with request.urlopen(f"{FRED_CSV_ENDPOINT}?{query}", timeout=timeout, context=context) as response:
        return response.read().decode("utf-8")


def _next_day_0800(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time(8, 0), tzinfo=SHANGHAI)


def _fred_lagged_availability(day: date) -> datetime:
    # FRED is an archival transport, not a tick feed. A two-calendar-day lag prevents
    # a same-day or next-morning A-share decision from consuming a late U.S. release.
    return datetime.combine(day + timedelta(days=2), time(18, 0), tzinfo=SHANGHAI)


def _record(
    *,
    series_id: str,
    observation_day: date,
    value: float,
    available_at: datetime,
    source_provider: str,
    availability_basis: str,
) -> dict[str, Any]:
    if value <= 0 and series_id not in {"UST_10Y_MINUS_2Y"}:
        raise ValueError(f"non-positive macro value: {series_id} {observation_day}")
    return {
        "series_id": series_id,
        "observation_date": observation_day.isoformat(),
        "available_at": available_at.isoformat(),
        "value": value,
        "source_provider": source_provider,
        "availability_basis": availability_basis,
    }


def normalize_macro_rows(
    *,
    fx_rows: Iterable[dict[str, Any]],
    treasury_rows: Iterable[dict[str, Any]],
    gold_rows: Iterable[dict[str, Any]],
    fred_csv_by_series: dict[str, str],
    retrieved_at: datetime,
) -> list[dict[str, Any]]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    records: list[dict[str, Any]] = []
    for raw in fx_rows:
        day = datetime.strptime(str(raw["trade_date"]), "%Y%m%d").date()
        bid = float(raw["bid_close"])
        ask = float(raw["ask_close"])
        if bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError(f"invalid USDCNH quote on {day}")
        records.append(
            _record(
                series_id="USDCNH_MID",
                observation_day=day,
                value=(bid + ask) / 2.0,
                available_at=_next_day_0800(day),
                source_provider="tushare_fx_daily",
                availability_basis="next_calendar_day_0800_asia_shanghai_after_gmt_daily_bar",
            )
        )
    for raw in treasury_rows:
        day = datetime.strptime(str(raw["date"]), "%Y%m%d").date()
        y2, y10 = float(raw["y2"]), float(raw["y10"])
        available = _next_day_0800(day)
        basis = "next_calendar_day_0800_asia_shanghai_after_us_treasury_curve_release"
        records.extend(
            [
                _record(
                    series_id="UST_2Y",
                    observation_day=day,
                    value=y2,
                    available_at=available,
                    source_provider="tushare_us_tycr",
                    availability_basis=basis,
                ),
                _record(
                    series_id="UST_10Y",
                    observation_day=day,
                    value=y10,
                    available_at=available,
                    source_provider="tushare_us_tycr",
                    availability_basis=basis,
                ),
                _record(
                    series_id="UST_10Y_MINUS_2Y",
                    observation_day=day,
                    value=y10 - y2,
                    available_at=available,
                    source_provider="tushare_us_tycr",
                    availability_basis=basis,
                ),
            ]
        )
    for raw in gold_rows:
        day = datetime.strptime(str(raw["trade_date"]), "%Y%m%d").date()
        records.append(
            _record(
                series_id="SGE_AU9999",
                observation_day=day,
                value=float(raw["close"]),
                available_at=_next_day_0800(day),
                source_provider="tushare_sge_daily",
                availability_basis="next_calendar_day_0800_asia_shanghai_after_sge_daily_bar",
            )
        )
    for series_id, text in sorted(fred_csv_by_series.items()):
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames != ["observation_date", series_id]:
            raise ValueError(f"unexpected FRED columns for {series_id}: {reader.fieldnames}")
        for raw in reader:
            raw_value = str(raw.get(series_id) or "").strip()
            if not raw_value or raw_value == ".":
                continue
            day = date.fromisoformat(str(raw["observation_date"]))
            records.append(
                _record(
                    series_id=series_id,
                    observation_day=day,
                    value=float(raw_value),
                    available_at=_fred_lagged_availability(day),
                    source_provider="fred_public_csv",
                    availability_basis="observation_date_plus_two_calendar_days_1800_asia_shanghai",
                )
            )
    seen: set[tuple[str, str]] = set()
    for row in records:
        key = (str(row["series_id"]), str(row["observation_date"]))
        if key in seen:
            raise ValueError(f"duplicate macro series date: {key}")
        seen.add(key)
        if datetime.fromisoformat(str(row["available_at"])).astimezone(UTC) > retrieved_at.astimezone(UTC):
            raise ValueError(f"future macro observation returned by provider: {key}")
    return sorted(records, key=lambda row: (str(row["series_id"]), str(row["observation_date"])))


def build_macro_research_snapshot(
    *,
    fx_rows: Iterable[dict[str, Any]],
    treasury_rows: Iterable[dict[str, Any]],
    gold_rows: Iterable[dict[str, Any]],
    fred_csv_by_series: dict[str, str],
    retrieved_at: datetime,
    tushare_endpoint: str,
) -> dict[str, Any]:
    raw_fx = list(fx_rows)
    raw_treasury = list(treasury_rows)
    raw_gold = list(gold_rows)
    records = normalize_macro_rows(
        fx_rows=raw_fx,
        treasury_rows=raw_treasury,
        gold_rows=raw_gold,
        fred_csv_by_series=fred_csv_by_series,
        retrieved_at=retrieved_at,
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row["series_id"])].append(row)
    material = {
        "artifact_type": "external_context_macro_research_snapshot",
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved_at.isoformat(),
        "source_endpoints": {"tushare": tushare_endpoint, "fred": FRED_CSV_ENDPOINT},
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": "hernando_zhao / Tushare / FRED",
        "provider_revision_id_available": False,
        "promotion_blocker": "historical_revision_lineage_missing_requires_vintage_qualified_vendor_reproduction",
        "claim_ceiling": "provisional_pit_conservative_availability_research_input_not_production_vendor_data",
        "raw": {
            "tushare_fx_daily": raw_fx,
            "tushare_us_tycr": raw_treasury,
            "tushare_sge_daily": raw_gold,
            "fred_csv": fred_csv_by_series,
        },
        "records": records,
        "quality": {
            "record_count": len(records),
            "series_counts": {key: len(rows) for key, rows in sorted(grouped.items())},
            "series_date_ranges": {
                key: {"min": rows[0]["observation_date"], "max": rows[-1]["observation_date"]}
                for key, rows in sorted(grouped.items())
            },
            "duplicate_series_date_count": 0,
            "future_available_at_count": 0,
        },
    }
    return {**material, "content_digest": stable_digest(material)}


def acquire_macro_research_snapshot(
    session: Session,
    *,
    start: date,
    end: date,
    retrieved_at: datetime | None = None,
    tushare_request_fn: Callable[..., dict[str, Any] | None] = _post_tushare,
    fred_request_fn: Callable[..., str] = _fred_csv,
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
    common = {"start_date": start.strftime("%Y%m%d"), "end_date": end.strftime("%Y%m%d")}
    fx_rows = _response_rows(
        tushare_request_fn(
            base_url=base_url,
            token=credential.access_token.strip(),
            api_name="fx_daily",
            params={"ts_code": "USDCNH.FXCM", **common},
        )
    )
    treasury_rows = _response_rows(
        tushare_request_fn(
            base_url=base_url,
            token=credential.access_token.strip(),
            api_name="us_tycr",
            params=common,
        )
    )
    gold_rows = _response_rows(
        tushare_request_fn(
            base_url=base_url,
            token=credential.access_token.strip(),
            api_name="sge_daily",
            params={"ts_code": "Au99.99", **common},
        )
    )
    fred = {
        series_id: fred_request_fn(series_id=series_id, start=start, end=end)
        for series_id in ("DCOILWTICO", "VIXCLS")
    }
    return build_macro_research_snapshot(
        fx_rows=fx_rows,
        treasury_rows=treasury_rows,
        gold_rows=gold_rows,
        fred_csv_by_series=fred,
        retrieved_at=retrieved_at or datetime.now(UTC),
        tushare_endpoint=base_url,
    )


def write_macro_research_snapshot(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("macro snapshot content digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"immutable research snapshot already exists with different content: {path}")
        return
    path.write_text(rendered, encoding="utf-8")


def load_macro_research_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported macro research snapshot schema")
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("macro snapshot content digest mismatch")
    return payload


def macro_state_by_decision_date(
    records: Iterable[dict[str, Any]], *, decision_dates: Iterable[date]
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["series_id"])].append(record)
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row["available_at"]))
    result: dict[str, dict[str, Any]] = {}
    for decision_day in sorted(set(decision_dates)):
        cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
        state: dict[str, Any] = {}
        for series_id, rows in sorted(grouped.items()):
            available = [row for row in rows if datetime.fromisoformat(str(row["available_at"])) <= cutoff]
            if not available:
                continue
            values = [float(row["value"]) for row in available]
            latest = available[-1]
            state[series_id] = {
                "observation_date": latest["observation_date"],
                "available_at": latest["available_at"],
                "value": values[-1],
                "change_5d": values[-1] - values[-6] if len(values) > 5 else None,
                "return_5d": values[-1] / values[-6] - 1.0 if len(values) > 5 and values[-6] != 0 else None,
                "return_20d": values[-1] / values[-21] - 1.0 if len(values) > 20 and values[-21] != 0 else None,
            }
        if state:
            result[decision_day.isoformat()] = state
    return result
