from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.external_context_global_market_research import _response_rows, stable_digest
from ashare_evidence.intraday_market import DEFAULT_TUSHARE_BASE_URL, _post_tushare
from ashare_evidence.models import ProviderCredential

SCHEMA_VERSION = "external_context_sector_market_research_snapshot.v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
CLASSIFICATION_FIELDS = "index_code,industry_name,level,industry_code,is_pub,parent_code,src"
DAILY_FIELDS = "ts_code,trade_date,name,open,low,high,close,change,pct_change,vol,amount,pe,pb,float_mv,total_mv"
SUBINDUSTRY_TO_SW_L1 = {
    "农林牧渔": {"饲料", "农业综合", "种植业", "林业", "渔业"},
    "基础化工": {"化工原料", "化纤", "农药化肥", "染料涂料", "塑料", "橡胶", "日用化工"},
    "钢铁": {"普钢", "钢加工", "特种钢"},
    "有色金属": {"小金属", "铜", "铝", "黄金", "铅锌"},
    "电子": {"元器件", "半导体"},
    "家用电器": {"家用电器"},
    "食品饮料": {"食品", "白酒", "软饮料", "乳制品", "红黄酒", "啤酒"},
    "纺织服饰": {"服饰", "纺织"},
    "轻工制造": {"家居用品", "造纸", "文教休闲", "广告包装"},
    "医药生物": {"化学制药", "中成药", "医疗保健", "生物制药", "医药商业"},
    "公用事业": {"水力发电", "供气供热", "新型电力", "火力发电", "水务"},
    "交通运输": {"港口", "路桥", "铁路", "仓储物流", "航空", "空运", "水运", "机场", "公共交通", "公路"},
    "房地产": {"园区开发", "区域地产", "全国地产", "房产服务"},
    "商贸零售": {"百货", "商品城", "超市连锁", "商贸代理", "其他商业", "批发业", "电器连锁"},
    "社会服务": {"旅游服务", "旅游景点", "酒店餐饮"},
    "综合": {"综合类"},
    "建筑材料": {"水泥", "玻璃", "其他建材", "陶瓷", "矿物制品"},
    "建筑装饰": {"建筑工程", "装修装饰"},
    "电力设备": {"电气设备"},
    "国防军工": {"船舶"},
    "计算机": {"软件服务", "IT设备"},
    "传媒": {"影视音像", "出版业", "互联网"},
    "通信": {"通信设备", "电信运营"},
    "银行": {"银行"},
    "非银金融": {"证券", "多元金融", "保险"},
    "汽车": {"汽车配件", "汽车整车", "摩托车", "汽车服务"},
    "机械设备": {
        "专用机械", "机械基件", "工程机械", "运输设备", "纺织机械", "机床制造", "化工机械", "农用机械",
        "轻工机械", "电器仪表",
    },
    "煤炭": {"煤炭开采", "焦炭加工"},
    "石油石化": {"石油加工", "石油开采", "石油贸易"},
    "环保": {"环境保护"},
}
SW_L1_BY_SUBINDUSTRY = {
    subindustry: sector for sector, subindustries in SUBINDUSTRY_TO_SW_L1.items() for subindustry in subindustries
}


def _date_chunks(start: date, end: date, *, days: int = 10) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def build_sector_research_snapshot(
    *,
    classification_response: dict[str, Any],
    daily_responses: list[dict[str, Any]],
    daily_requests: list[dict[str, str]],
    requested_start: date,
    requested_end: date,
    retrieved_at: datetime,
    source_endpoint: str,
) -> dict[str, Any]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    classifications = _response_rows(classification_response)
    code_to_name = {
        str(row["index_code"]): str(row["industry_name"])
        for row in classifications
        if str(row.get("level") or "") == "L1" and str(row.get("src") or "") == "SW2021"
    }
    if len(code_to_name) < 30:
        raise ValueError("SW2021 L1 classification coverage is incomplete")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    out_of_bounds_open = 0
    for response in daily_responses:
        for row in _response_rows(response):
            code = str(row.get("ts_code") or "")
            if code not in code_to_name:
                continue
            trade_day = datetime.strptime(str(row.get("trade_date") or ""), "%Y%m%d").date()
            key = (code, trade_day.isoformat())
            if key in seen:
                raise ValueError(f"duplicate SW L1 sector date: {key}")
            seen.add(key)
            values = {field: float(row[field]) for field in ("open", "low", "high", "close")}
            if min(values.values()) <= 0 or not values["low"] <= values["close"] <= values["high"]:
                raise ValueError(f"invalid SW L1 OHLC row: {key}")
            open_outside = not values["low"] <= values["open"] <= values["high"]
            out_of_bounds_open += int(open_outside)
            available_at = datetime.combine(trade_day, time(18, 0), tzinfo=SHANGHAI)
            if available_at.astimezone(UTC) > retrieved_at.astimezone(UTC):
                raise ValueError(f"future SW L1 observation returned by provider: {key}")
            records.append(
                {
                    "sector_code": code,
                    "sector_name": code_to_name[code],
                    "trade_date": trade_day.isoformat(),
                    "available_at": available_at.isoformat(),
                    "availability_basis": "same_calendar_day_1800_asia_shanghai_after_a_share_close",
                    **values,
                    "pct_change": None if row.get("pct_change") is None else float(row["pct_change"]),
                    "volume": None if row.get("vol") is None else float(row["vol"]),
                    "amount": None if row.get("amount") is None else float(row["amount"]),
                    "open_outside_high_low": open_outside,
                }
            )
    records.sort(key=lambda row: (row["sector_code"], row["trade_date"]))
    counts: dict[str, int] = defaultdict(int)
    dates: dict[str, list[str]] = defaultdict(list)
    for row in records:
        code = str(row["sector_code"])
        counts[code] += 1
        dates[code].append(str(row["trade_date"]))
    missing_codes = sorted(set(code_to_name) - set(counts))
    if missing_codes:
        raise ValueError(f"SW L1 daily coverage missing sectors: {missing_codes}")
    coverage_failures: list[str] = []
    max_gap_days = 0
    for code, values in sorted(dates.items()):
        parsed = [date.fromisoformat(value) for value in sorted(values)]
        if parsed[0] > requested_start + timedelta(days=21):
            coverage_failures.append(f"{code}:late_start:{parsed[0].isoformat()}")
        if parsed[-1] < requested_end - timedelta(days=7):
            coverage_failures.append(f"{code}:early_end:{parsed[-1].isoformat()}")
        code_max_gap = max(
            ((current - previous).days for previous, current in zip(parsed, parsed[1:], strict=False)),
            default=0,
        )
        max_gap_days = max(max_gap_days, code_max_gap)
        if code_max_gap > 21:
            coverage_failures.append(f"{code}:max_gap_days:{code_max_gap}")
    if coverage_failures:
        raise ValueError(f"SW L1 daily temporal coverage failed: {coverage_failures[:8]}")
    raw_layer = {
        "classification": {
            "api_name": "index_classify",
            "params": {"level": "L1", "src": "SW2021"},
            "fields": CLASSIFICATION_FIELDS,
            "response": classification_response,
        },
        "daily_batches": [
            {
                "api_name": "sw_daily",
                "params": request,
                "fields": DAILY_FIELDS,
                "response": response,
            }
            for request, response in zip(daily_requests, daily_responses, strict=True)
        ],
    }
    material = {
        "artifact_type": "external_context_sector_market_research_snapshot",
        "schema_version": SCHEMA_VERSION,
        "provider_id": "tushare_sw_daily_sw2021_l1",
        "retrieved_at": retrieved_at.isoformat(),
        "requested_range": {"start": requested_start.isoformat(), "end": requested_end.isoformat()},
        "source_endpoint": source_endpoint,
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": "hernando_zhao / Tushare / Shenwan Hongyuan Research",
        "provider_revision_id_available": False,
        "promotion_blocker": "provider_revision_lineage_missing_requires_qualified_vendor_reproduction",
        "claim_ceiling": "provisional_personal_research_input_not_production_pit_vendor_data",
        "raw": raw_layer,
        "normalized": {"records": records},
        "quality": {
            "classification_count": len(code_to_name),
            "record_count": len(records),
            "sector_counts": dict(sorted(counts.items())),
            "sector_names": dict(sorted(code_to_name.items())),
            "sector_date_ranges": {
                code: {"min": min(values), "max": max(values)} for code, values in sorted(dates.items())
            },
            "duplicate_sector_date_count": 0,
            "future_available_at_count": 0,
            "open_outside_high_low_count": out_of_bounds_open,
            "raw_batch_count": len(daily_responses) + 1,
            "maximum_consecutive_trade_date_gap_days": max_gap_days,
        },
    }
    return {**material, "content_digest": stable_digest(material)}


def acquire_tushare_sector_market_research_snapshot(
    session: Session,
    *,
    start: date,
    end: date,
    retrieved_at: datetime | None = None,
    request_fn: Callable[..., dict[str, Any] | None] = _post_tushare,
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

    def request(api_name: str, params: dict[str, str], fields: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(max(1, max_attempts)):
            try:
                response = request_fn(
                    base_url=base_url,
                    token=credential.access_token.strip(),
                    api_name=api_name,
                    params=params,
                    fields=fields,
                )
                _response_rows(response)
                return response  # type: ignore[return-value]
            except (OSError, ValueError) as exc:
                last_error = exc
        raise ValueError(f"failed to acquire {api_name} {params}: {last_error}") from last_error

    classification = request("index_classify", {"level": "L1", "src": "SW2021"}, CLASSIFICATION_FIELDS)
    daily_requests = [
        {"start_date": chunk_start.strftime("%Y%m%d"), "end_date": chunk_end.strftime("%Y%m%d")}
        for chunk_start, chunk_end in _date_chunks(start, end)
    ]
    daily_responses = [request("sw_daily", params, DAILY_FIELDS) for params in daily_requests]
    return build_sector_research_snapshot(
        classification_response=classification,
        daily_responses=daily_responses,
        daily_requests=daily_requests,
        requested_start=start,
        requested_end=end,
        retrieved_at=retrieved_at or datetime.now(UTC),
        source_endpoint=base_url,
    )


def write_sector_research_snapshot(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("sector-market snapshot content digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"immutable sector research snapshot already exists with different content: {path}")
        return
    path.write_text(rendered, encoding="utf-8")


def load_sector_research_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported sector-market research snapshot schema")
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("sector-market snapshot content digest mismatch")
    return payload


def sector_mapping_coverage(industry_names: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for name in industry_names:
        counts[str(name)] += 1
    mapped = sum(count for name, count in counts.items() if name in SW_L1_BY_SUBINDUSTRY)
    total = sum(counts.values())
    return {
        "row_count": total,
        "mapped_row_count": mapped,
        "mapped_row_rate": mapped / total if total else 0.0,
        "unique_industry_count": len(counts),
        "unmapped_industries": dict(sorted((name, count) for name, count in counts.items() if name not in SW_L1_BY_SUBINDUSTRY)),
    }


def sector_state_by_decision_date(
    records: list[dict[str, Any]],
    *,
    decision_dates: list[date],
) -> dict[str, dict[str, Any]]:
    by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_sector[str(record["sector_name"])].append(record)
    for rows in by_sector.values():
        rows.sort(key=lambda row: str(row["available_at"]))
    result: dict[str, dict[str, Any]] = {}
    for decision_day in sorted(set(decision_dates)):
        cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
        sectors: dict[str, dict[str, float | str]] = {}
        for sector_name, rows in sorted(by_sector.items()):
            available = [row for row in rows if datetime.fromisoformat(str(row["available_at"])) <= cutoff]
            if len(available) < 21:
                continue
            closes = [float(row["close"]) for row in available]
            sectors[sector_name] = {
                "observation_date": str(available[-1]["trade_date"]),
                "available_at": str(available[-1]["available_at"]),
                "return_5d": closes[-1] / closes[-6] - 1.0,
                "return_20d": closes[-1] / closes[-21] - 1.0,
                "drawdown_20d": closes[-1] / max(closes[-20:]) - 1.0,
            }
        if len(sectors) < 30:
            continue
        mean_5d = sum(float(row["return_5d"]) for row in sectors.values()) / len(sectors)
        mean_20d = sum(float(row["return_20d"]) for row in sectors.values()) / len(sectors)
        enriched = {
            name: {
                **row,
                "relative_5d": float(row["return_5d"]) - mean_5d,
                "relative_20d": float(row["return_20d"]) - mean_20d,
            }
            for name, row in sectors.items()
        }
        result[decision_day.isoformat()] = {
            "sector_count": len(enriched),
            "breadth_5d": sum(float(row["return_5d"]) > 0.0 for row in enriched.values()) / len(enriched),
            "breadth_20d": sum(float(row["return_20d"]) > 0.0 for row in enriched.values()) / len(enriched),
            "mean_return_5d": mean_5d,
            "mean_return_20d": mean_20d,
            "by_sector_name": enriched,
        }
    return result


def merge_sector_research_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if len(snapshots) < 2:
        raise ValueError("sector snapshot merge requires at least two inputs")
    records_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    source_refs: list[dict[str, Any]] = []
    for snapshot in snapshots:
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("sector snapshot merge received an incompatible schema")
        source_refs.append(
            {
                "content_digest": snapshot["content_digest"],
                "requested_range": snapshot["requested_range"],
                "retrieved_at": snapshot["retrieved_at"],
                "raw": snapshot["raw"],
            }
        )
        for row in snapshot["normalized"]["records"]:
            key = (str(row["sector_code"]), str(row["trade_date"]))
            existing = records_by_key.get(key)
            if existing is not None and existing != row:
                raise ValueError(f"sector snapshot merge conflict: {key}")
            records_by_key[key] = row
    records = sorted(records_by_key.values(), key=lambda row: (row["sector_code"], row["trade_date"]))
    counts: dict[str, int] = defaultdict(int)
    dates: dict[str, list[str]] = defaultdict(list)
    names: dict[str, str] = {}
    for row in records:
        code = str(row["sector_code"])
        counts[code] += 1
        dates[code].append(str(row["trade_date"]))
        names[code] = str(row["sector_name"])
    requested_start = min(str(snapshot["requested_range"]["start"]) for snapshot in snapshots)
    requested_end = max(str(snapshot["requested_range"]["end"]) for snapshot in snapshots)
    maximum_gap = max(
        (date.fromisoformat(current) - date.fromisoformat(previous)).days
        for values in dates.values()
        for previous, current in zip(sorted(values), sorted(values)[1:], strict=False)
    )
    material = {
        "artifact_type": "external_context_sector_market_research_snapshot",
        "schema_version": SCHEMA_VERSION,
        "provider_id": "tushare_sw_daily_sw2021_l1_composite",
        "retrieved_at": max(str(snapshot["retrieved_at"]) for snapshot in snapshots),
        "requested_range": {"start": requested_start, "end": requested_end},
        "source_endpoint": snapshots[0]["source_endpoint"],
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": "hernando_zhao / Tushare / Shenwan Hongyuan Research",
        "provider_revision_id_available": False,
        "promotion_blocker": "provider_revision_lineage_missing_requires_qualified_vendor_reproduction",
        "claim_ceiling": "provisional_personal_research_input_not_production_pit_vendor_data",
        "raw": {"composite_sources": source_refs},
        "normalized": {"records": records},
        "quality": {
            "classification_count": len(names),
            "record_count": len(records),
            "sector_counts": dict(sorted(counts.items())),
            "sector_names": dict(sorted(names.items())),
            "sector_date_ranges": {
                code: {"min": min(values), "max": max(values)} for code, values in sorted(dates.items())
            },
            "duplicate_sector_date_count": 0,
            "future_available_at_count": 0,
            "open_outside_high_low_count": sum(bool(row["open_outside_high_low"]) for row in records),
            "raw_batch_count": sum(int(snapshot["quality"]["raw_batch_count"]) for snapshot in snapshots),
            "maximum_consecutive_trade_date_gap_days": maximum_gap,
            "composite_source_count": len(snapshots),
        },
    }
    return {**material, "content_digest": stable_digest(material)}
