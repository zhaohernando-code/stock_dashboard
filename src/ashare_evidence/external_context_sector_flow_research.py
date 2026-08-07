from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.intraday_market import DEFAULT_TUSHARE_BASE_URL, _post_tushare
from ashare_evidence.models import ProviderCredential

SCHEMA_VERSION = "external_context_sector_flow_research_snapshot.v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
TECH_FLOW_KEYWORDS = ("半导体", "芯片", "通信", "光模块", "算力", "人工智能", "AI", "软件", "电子", "机器人")


def stable_digest(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _response_rows(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise ValueError("Tushare returned no sector-flow response")
    if int(response.get("code") or 0) != 0:
        raise ValueError(f"Tushare sector-flow request failed: {response.get('msg') or response.get('message')}")
    data = response.get("data") or {}
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not isinstance(fields, list) or not isinstance(items, list):
        raise ValueError("Tushare sector-flow response has an invalid data envelope")
    return [dict(zip(fields, item, strict=False)) for item in items]


def normalize_sector_flow_rows(
    rows_by_kind: dict[str, Iterable[dict[str, Any]]], *, retrieved_at: datetime
) -> list[dict[str, Any]]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for kind, rows in sorted(rows_by_kind.items()):
        if kind not in {"industry", "concept"}:
            raise ValueError(f"unsupported sector-flow kind: {kind}")
        for raw in rows:
            trade_day = datetime.strptime(str(raw["trade_date"]), "%Y%m%d").date()
            code = str(raw.get("ts_code") or "").strip()
            key = (kind, code, trade_day.isoformat())
            if key in seen:
                raise ValueError(f"duplicate sector-flow row: {key}")
            seen.add(key)
            name = str(raw.get("industry") if kind == "industry" else raw.get("name") or "").strip()
            available_at = datetime.combine(trade_day + timedelta(days=1), time(8, 0), tzinfo=SHANGHAI)
            if available_at.astimezone(UTC) > retrieved_at.astimezone(UTC):
                raise ValueError(f"future sector-flow row returned by provider: {key}")
            net_amount = float(raw.get("net_amount") or 0.0)
            buy_amount = float(raw.get("net_buy_amount") or 0.0)
            sell_amount = float(raw.get("net_sell_amount") or 0.0)
            records.append(
                {
                    "kind": kind,
                    "sector_code": code,
                    "sector_name": name,
                    "trade_date": trade_day.isoformat(),
                    "available_at": available_at.isoformat(),
                    "availability_basis": "next_calendar_day_0800_asia_shanghai_after_daily_post_close_update",
                    "net_amount": net_amount,
                    "net_buy_amount": buy_amount,
                    "net_sell_amount": sell_amount,
                    "net_flow_ratio": net_amount / max(abs(buy_amount) + abs(sell_amount), 1e-12),
                    "pct_change": float(raw.get("pct_change") or 0.0),
                    "company_num": int(float(raw.get("company_num") or 0)),
                    "tech_related": any(keyword.lower() in name.lower() for keyword in TECH_FLOW_KEYWORDS),
                }
            )
    return sorted(records, key=lambda row: (row["kind"], row["sector_code"], row["trade_date"]))


def build_sector_flow_snapshot(
    *, raw_batches: list[dict[str, Any]], retrieved_at: datetime, source_endpoint: str
) -> dict[str, Any]:
    rows_by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for batch in raw_batches:
        rows_by_kind[str(batch["kind"])].extend(batch["rows"])
    records = normalize_sector_flow_rows(rows_by_kind, retrieved_at=retrieved_at)
    counts: dict[str, int] = defaultdict(int)
    dates: dict[str, list[str]] = defaultdict(list)
    for row in records:
        counts[str(row["kind"])] += 1
        dates[str(row["kind"])].append(str(row["trade_date"]))
    material = {
        "artifact_type": "external_context_sector_flow_research_snapshot",
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved_at.isoformat(),
        "source_endpoint": source_endpoint,
        "provider_id": "tushare_moneyflow_ind_ths_and_moneyflow_cnt_ths",
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": "hernando_zhao / Tushare / THS-derived sector flow",
        "provider_revision_id_available": False,
        "promotion_blocker": "provider_revision_lineage_missing_requires_qualified_vendor_reproduction",
        "claim_ceiling": "provisional_pit_conservative_sector_flow_research_input_not_production_vendor_data",
        "raw": {"batches": raw_batches},
        "normalized": {"records": records},
        "quality": {
            "raw_batch_count": len(raw_batches),
            "record_count": len(records),
            "kind_counts": dict(sorted(counts.items())),
            "kind_date_ranges": {
                kind: {"min": min(values), "max": max(values)} for kind, values in sorted(dates.items())
            },
            "duplicate_kind_code_date_count": 0,
            "future_available_at_count": 0,
            "tech_related_record_count": sum(bool(row["tech_related"]) for row in records),
        },
    }
    return {**material, "content_digest": stable_digest(material)}


def acquire_sector_flow_snapshot(
    session: Session,
    *,
    start: date,
    end: date,
    retrieved_at: datetime | None = None,
    request_fn: Callable[..., dict[str, Any] | None] = _post_tushare,
    initial_window_days: int = 14,
    safe_row_limit: int = 4500,
    max_attempts: int = 3,
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
    raw_batches: list[dict[str, Any]] = []

    def fetch(kind: str, api_name: str, window_start: date, window_end: date) -> None:
        response = None
        for _attempt in range(max(1, max_attempts)):
            response = request_fn(
                base_url=base_url,
                token=credential.access_token.strip(),
                api_name=api_name,
                params={
                    "start_date": window_start.strftime("%Y%m%d"),
                    "end_date": window_end.strftime("%Y%m%d"),
                },
            )
            if response is not None:
                break
        rows = _response_rows(response)
        if len(rows) >= safe_row_limit and window_start < window_end:
            midpoint = window_start + (window_end - window_start) // 2
            fetch(kind, api_name, window_start, midpoint)
            fetch(kind, api_name, midpoint + timedelta(days=1), window_end)
            return
        if len(rows) >= safe_row_limit:
            raise ValueError(f"sector-flow density exceeds safe daily batch for {kind} {window_start}")
        raw_batches.append(
            {
                "kind": kind,
                "api_name": api_name,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "row_count": len(rows),
                "rows": rows,
            }
        )

    for kind, api_name in (("industry", "moneyflow_ind_ths"), ("concept", "moneyflow_cnt_ths")):
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=initial_window_days - 1), end)
            fetch(kind, api_name, cursor, window_end)
            cursor = window_end + timedelta(days=1)
    return build_sector_flow_snapshot(
        raw_batches=raw_batches,
        retrieved_at=retrieved_at or datetime.now(UTC),
        source_endpoint=base_url,
    )


def write_sector_flow_snapshot(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("sector-flow snapshot digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable sector-flow snapshot already exists: {path}")
    path.write_text(rendered, encoding="utf-8")


def load_sector_flow_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported sector-flow snapshot schema")
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("sector-flow snapshot digest mismatch")
    return payload


def sector_flow_state_by_decision_date(
    records: Iterable[dict[str, Any]], *, decision_dates: Iterable[date]
) -> dict[str, dict[str, float]]:
    by_available_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        available_day = datetime.fromisoformat(str(row["available_at"])).astimezone(SHANGHAI).date()
        by_available_day[available_day].append(row)
    result: dict[str, dict[str, float]] = {}
    for decision_day in sorted(set(decision_dates)):
        available_days = [day for day in by_available_day if day <= decision_day]
        if not available_days:
            continue
        latest_day = max(available_days)
        rows = by_available_day[latest_day]
        industry = [row for row in rows if row["kind"] == "industry"]
        concept = [row for row in rows if row["kind"] == "concept"]
        tech = [row for row in rows if row["tech_related"]]

        def average(values: list[dict[str, Any]], field: str) -> float:
            return mean(float(row[field]) for row in values) if values else 0.0

        result[decision_day.isoformat()] = {
            "industry_positive_flow_breadth": (
                sum(float(row["net_amount"]) > 0 for row in industry) / len(industry) if industry else 0.0
            ),
            "concept_positive_flow_breadth": (
                sum(float(row["net_amount"]) > 0 for row in concept) / len(concept) if concept else 0.0
            ),
            "industry_mean_net_flow_ratio": average(industry, "net_flow_ratio"),
            "concept_mean_net_flow_ratio": average(concept, "net_flow_ratio"),
            "tech_positive_flow_breadth": (
                sum(float(row["net_amount"]) > 0 for row in tech) / len(tech) if tech else 0.0
            ),
            "tech_mean_net_flow_ratio": average(tech, "net_flow_ratio"),
        }
    return result


def sector_flow_by_name_by_decision_date(
    records: Iterable[dict[str, Any]], *, decision_dates: Iterable[date]
) -> dict[str, dict[str, dict[str, Any]]]:
    by_available_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        available_day = datetime.fromisoformat(str(row["available_at"])).astimezone(SHANGHAI).date()
        by_available_day[available_day].append(row)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for decision_day in sorted(set(decision_dates)):
        available_days = [day for day in by_available_day if day <= decision_day]
        if not available_days:
            continue
        latest_day = max(available_days)
        rows = [row for row in by_available_day[latest_day] if row["kind"] == "industry"]
        result[decision_day.isoformat()] = {
            str(row["sector_name"]): {
                "trade_date": row["trade_date"],
                "available_at": row["available_at"],
                "net_flow_ratio": float(row["net_flow_ratio"]),
                "net_amount": float(row["net_amount"]),
                "pct_change": float(row["pct_change"]),
                "tech_related": bool(row["tech_related"]),
            }
            for row in rows
        }
    return result
