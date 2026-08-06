from __future__ import annotations

import hashlib
import html
import io
import json
import math
import re
import sqlite3
import zipfile
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import requests

from ashare_evidence.market_rules import build_trade_eligibility_snapshot, summarize_trade_eligibility_snapshots

CNINFO_POC_VERSION = "external_context_cninfo_public_poc.v1"
GDELT_POC_VERSION = "external_context_gdelt_daily_public_poc.v1"
CNINFO_CANARY_VERSION = "external_context_cninfo_historical_eligibility_canary.v1"
GDELT_EVENT_CODEBOOK_URL = "https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf"
GDELT_DAILY_ARCHIVE_MAX_BYTES = 16 * 1024 * 1024
GDELT_DAILY_UNCOMPRESSED_MAX_BYTES = 160 * 1024 * 1024
GDELT_DAILY_MAX_ROWS = 500_000
GDELT_DAILY_SELECTED_LIMIT = 12
GDELT_RELEVANCE_RULE_VERSION = "gdelt_headline_relevance.v2"
GDELT_TOPIC_SELECTED_LIMITS = {
    "semiconductor": 4,
    "telecommunications": 2,
    "trade_restriction": 4,
    "us_macro_policy": 2,
}
CNINFO_MAX_QUERY_DAYS = 366
CNINFO_MAX_PAGES = 100
CNINFO_RELEVANCE_RULE_VERSION = "cninfo_title_materiality.v1"
CNINFO_GROUP_MAX_TITLES = 6

_CNINFO_STOCK_MAP_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
_CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
_CNINFO_REFERER = "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search"
_CNINFO_DETAIL_URL = "https://www.cninfo.com.cn/new/disclosure/detail"
_GDELT_ARCHIVE_ROOT = "https://storage.googleapis.com/data.gdeltproject.org/events"
_GDELT_ASIA_US_GEO_CODES = {"CH", "CHN", "HK", "HKG", "JA", "JPN", "KS", "KOR", "TW", "TWN", "US", "USA"}
_CNINFO_ROUTINE_TITLE_PATTERN = re.compile(
    r"英文版|会议资料|法律意见书|述职报告|履职情况|审计报告|内控|内部控制|"
    r"环境、社会及治理|ESG|业绩说明会|召开.*股东大会|股东大会.*决议|"
    r"董事会.*(?:会议)?决议|监事会.*(?:会议)?决议|审计委员会|核查意见|"
    r"差异对比|修订说明|跟踪评级|受托管理事务报告"
)
_CNINFO_MATERIAL_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "financial_performance_and_distribution",
        re.compile(r"年度报告|半年度报告|季度报告|业绩预告|业绩快报|主要经营数据|利润分配|权益分派|现金分红"),
    ),
    (
        "risk_enforcement_and_correction",
        re.compile(
            r"风险提示|风险评估|立案|调查|处罚|诉讼|仲裁|退市|特别处理|停牌|异常波动|"
            r"债务|违约|资金占用|更正|补充(?:公告|说明|披露)|澄清|修正"
        ),
    ),
    (
        "capital_and_ownership",
        re.compile(r"回购|增持|减持|质押|解禁|股权激励|权益变动|实际控制人|控股股东|控制权"),
    ),
    (
        "management_change",
        re.compile(r"董事长.*辞职|总经理.*辞职|高级管理人员.*辞职|变更会计师事务所"),
    ),
    (
        "financing_and_mna",
        re.compile(r"重组|收购|并购|定增|增发|可转债|公司债|融资|发行股份.*购买资产"),
    ),
    (
        "material_operations",
        re.compile(r"中标|重大合同|重大订单|重大项目|投产|产能|合作协议|重大交易|关联交易"),
    ),
)

_GDELT_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    (
        "semiconductor",
        re.compile(
            r"(?:^|[^a-z0-9])(?:semiconductors?|microchips?|chipmakers?|chip[-_]?making|tsmc|smic|"
            r"nvidia|advanced[-_]?micro[-_]?devices|huawei)(?:[^a-z0-9]|$)"
        ),
        ("semiconductor",),
    ),
    (
        "telecommunications",
        re.compile(
            r"(?:^|[^a-z0-9])(?:telecom(?:munications?)?|5g|wireless[-_]?network|fiber[-_]?optic)"
            r"(?:[^a-z0-9]|$)"
        ),
        ("telecommunications",),
    ),
    (
        "trade_restriction",
        re.compile(
            r"(?:^|[^a-z0-9])(?:export[-_]?(?:controls?|restrictions?|bans?)|import[-_]?ban|"
            r"trade[-_]?war|tariffs?|embargo|rare[-_]?earth)(?:[^a-z0-9]|$)"
        ),
        ("semiconductor", "industrial_supply_chain"),
    ),
    (
        "us_macro_policy",
        re.compile(
            r"(?:^|[^a-z0-9])(?:federal[-_]?reserve|fed[-_]?(?:rate|policy)|fomc|"
            r"us[-_]?(?:inflation|recession|jobs[-_]?report))(?:[^a-z0-9]|$)"
        ),
        ("global_macro",),
    ),
)

_GDELT_TOPIC_EXCLUSION_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "semiconductor": (
        (
            "investment_promotion_or_price_speculation",
            re.compile(
                r"\b(?:buy|sell)\b.{0,45}\b(?:stock|shares?)\b|"
                r"\b(?:stock|shares?)\b.{0,45}\b(?:buy|sell)\b|"
                r"\b(?:outperform(?:ed|ing)?|hedge funds?|etf investors?|kiwisaver investors?)\b|"
                r"\bwill\b.{0,60}\b(?:hit|reach)\b.{0,30}\b(?:trillion|price|target)\b|"
                r"\bstill (?:the )?king\b",
                re.IGNORECASE,
            ),
        ),
    ),
    "telecommunications": (
        (
            "consumer_device_or_review",
            re.compile(
                r"\b(?:review|hands[- ]?on|now available|smartphone|phone|pixel|oneplus|oppo|"
                r"redmagic|consumer router)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "crime_or_weapons_not_sector_state",
            re.compile(r"\b(?:fraud|scam|gang|arrest|cybercrime|drone deal|drones? with fiber)\b", re.IGNORECASE),
        ),
    ),
    "trade_restriction": (
        (
            "private_litigation_or_refund_marketing",
            re.compile(r"\b(?:class action|lawsuit|legal claim|tariff refunds?)\b", re.IGNORECASE),
        ),
        (
            "non_market_poll_or_food_quarantine",
            re.compile(r"\b(?:approval rating|potato wart|potato import ban)\b", re.IGNORECASE),
        ),
    ),
}


def _canonical_hash(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.isoformat()


def _parse_basic_date(value: str, *, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYYMMDD") from exc


def _retrieved_at(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return resolved


def _clean_cninfo_title(value: Any) -> str:
    without_markup = re.sub(r"</?em>", "", str(value or ""), flags=re.IGNORECASE)
    return " ".join(html.unescape(without_markup).split())


def _cninfo_materiality_category(title: str) -> str | None:
    if _CNINFO_ROUTINE_TITLE_PATTERN.search(title):
        return None
    for category, pattern in _CNINFO_MATERIAL_TITLE_PATTERNS:
        if pattern.search(title):
            return category
    return None


def _cninfo_stock_org_id(stock_map: dict[str, Any], symbol: str) -> str:
    rows = stock_map.get("stockList")
    if not isinstance(rows, list):
        raise ValueError("CNINFO stock map is missing stockList")
    for row in rows:
        if isinstance(row, dict) and str(row.get("code") or "") == symbol:
            org_id = str(row.get("orgId") or "").strip()
            if org_id:
                return org_id
    raise ValueError(f"CNINFO stock map does not contain symbol: {symbol}")


def _cninfo_published_at(value: Any) -> datetime:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("CNINFO announcementTime must be epoch milliseconds") from exc
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).astimezone(ZoneInfo("Asia/Shanghai"))


def _cninfo_records(
    announcements: Iterable[dict[str, Any]],
    *,
    retrieved_at: datetime,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for announcement in announcements:
        announcement_id = str(announcement.get("announcementId") or "").strip()
        symbol = str(announcement.get("secCode") or "").strip()
        org_id = str(announcement.get("orgId") or "").strip()
        title = _clean_cninfo_title(announcement.get("announcementTitle"))
        if not announcement_id or not symbol or not org_id or not title or announcement_id in seen_ids:
            continue
        materiality_category = _cninfo_materiality_category(title)
        if materiality_category is None:
            continue
        published_at = _cninfo_published_at(announcement.get("announcementTime"))
        if published_at > retrieved_at:
            raise ValueError(f"CNINFO announcement timestamp is after retrieval: {announcement_id}")
        seen_ids.add(announcement_id)
        available_from = datetime.combine(
            published_at.date(),
            time(23, 59, 59, 999999),
            tzinfo=ZoneInfo("Asia/Shanghai"),
        )
        source_url = (
            f"{_CNINFO_DETAIL_URL}?stockCode={symbol}&announcementId={announcement_id}&orgId={org_id}"
            f"&announcementTime={published_at.date().isoformat()}"
        )
        raw_payload = {
            "announcement_id": announcement_id,
            "announcement_title": title,
            "org_id": org_id,
            "sec_code": symbol,
            "sec_name": str(announcement.get("secName") or "").strip(),
            "source_url": source_url,
        }
        content_hash = _canonical_hash(raw_payload)
        records.append(
            {
                "provider_item_id": f"cninfo:{announcement_id}",
                "normalized_event_id": f"cninfo:{symbol}:{announcement_id}",
                "revision_id": f"document:{announcement_id}:{content_hash[:16]}",
                "provider_published_at": _iso_datetime(published_at),
                "provider_updated_at": None,
                "first_seen_at": _iso_datetime(retrieved_at),
                "available_from": _iso_datetime(available_from),
                "availability_basis": "provider_published_at_documented",
                "availability_evidence_ref": source_url,
                "event_type": "official_company_announcement",
                "source_authority": "official_exchange_designated_disclosure_platform",
                "entities": [symbol],
                "sectors": [],
                "geographies": ["CN"],
                "raw_payload": raw_payload,
                "normalized_payload": {
                    **raw_payload,
                    "content_hash": content_hash,
                    "content_retention_mode": "title_and_metadata_only_no_announcement_body",
                    "materiality_category": materiality_category,
                    "materiality_rule_version": CNINFO_RELEVANCE_RULE_VERSION,
                },
            }
        )
    return _collapse_cninfo_records(records)


def _collapse_cninfo_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        payload = record["normalized_payload"]
        key = (
            str(payload["sec_code"]),
            str(record["available_from"])[:10],
            str(payload["materiality_category"]),
        )
        grouped.setdefault(key, []).append(record)
    collapsed: list[dict[str, Any]] = []
    for (symbol, available_date, category), members in grouped.items():
        if len(members) == 1:
            collapsed.append(members[0])
            continue
        members.sort(key=lambda row: row["provider_item_id"])
        primary = members[0]
        retained = members[:CNINFO_GROUP_MAX_TITLES]
        raw_payload = dict(primary["raw_payload"])
        raw_payload.update(
            {
                "announcement_group_size": len(members),
                "announcement_ids": [row["raw_payload"]["announcement_id"] for row in retained],
                "announcement_titles": [row["raw_payload"]["announcement_title"] for row in retained],
                "retained_announcement_count": len(retained),
            }
        )
        content_hash = _canonical_hash(raw_payload)
        collapsed.append(
            {
                **primary,
                "provider_item_id": f"cninfo-group:{symbol}:{available_date}:{category}",
                "normalized_event_id": f"cninfo-group:{symbol}:{available_date}:{category}",
                "revision_id": f"group:{content_hash[:24]}",
                "raw_payload": raw_payload,
                "normalized_payload": {
                    **raw_payload,
                    "content_hash": content_hash,
                    "content_retention_mode": "title_and_metadata_only_no_announcement_body",
                    "materiality_category": category,
                    "materiality_rule_version": CNINFO_RELEVANCE_RULE_VERSION,
                },
            }
        )
    return sorted(collapsed, key=lambda row: (row["available_from"], row["provider_item_id"]), reverse=True)


def fetch_cninfo_announcement_poc(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    retrieved_at: datetime | None = None,
    session: requests.Session | None = None,
    timeout_seconds: float = 20.0,
    max_pages: int = CNINFO_MAX_PAGES,
    request_gate: Callable[[], None] | None = None,
    stock_map_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch compact official announcement metadata without downloading announcement bodies."""
    start = _parse_basic_date(start_date, field="start_date")
    end = _parse_basic_date(end_date, field="end_date")
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    if (end - start).days + 1 > CNINFO_MAX_QUERY_DAYS:
        raise ValueError(f"CNINFO query cannot exceed {CNINFO_MAX_QUERY_DAYS} calendar days")
    if not re.fullmatch(r"\d{6}", symbol):
        raise ValueError("symbol must be a six-digit A-share code")
    if max_pages < 1 or max_pages > CNINFO_MAX_PAGES:
        raise ValueError(f"max_pages must be between 1 and {CNINFO_MAX_PAGES}")

    observed_at = _retrieved_at(retrieved_at)
    client = session or requests.Session()
    headers = {
        "Referer": _CNINFO_REFERER,
        "User-Agent": "hernando_zhao-personal-research/1.0 summary-only-no-redistribution",
    }
    stock_map = stock_map_cache.get("payload") if stock_map_cache is not None else None
    if stock_map is None:
        if request_gate is not None:
            request_gate()
        stock_response = client.get(_CNINFO_STOCK_MAP_URL, headers=headers, timeout=timeout_seconds)
        stock_response.raise_for_status()
        stock_map = stock_response.json()
        if stock_map_cache is not None:
            stock_map_cache["payload"] = stock_map
    org_id = _cninfo_stock_org_id(stock_map, symbol)
    payload = {
        "pageNum": 1,
        "pageSize": 30,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{symbol},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": f"{start.isoformat()}~{end.isoformat()}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    if request_gate is not None:
        request_gate()
    first_response = client.post(_CNINFO_QUERY_URL, data=payload, headers=headers, timeout=timeout_seconds)
    first_response.raise_for_status()
    first_page = first_response.json()
    total = int(first_page.get("totalAnnouncement") or 0)
    page_count = max(int(first_page.get("totalpages") or 0), math.ceil(total / 30)) if total else 0
    if page_count > max_pages:
        raise ValueError(f"CNINFO result requires {page_count} pages, above max_pages={max_pages}")
    announcements = list(first_page.get("announcements") or [])
    for page_number in range(2, page_count + 1):
        payload["pageNum"] = page_number
        if request_gate is not None:
            request_gate()
        response = client.post(_CNINFO_QUERY_URL, data=payload, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()
        announcements.extend(response.json().get("announcements") or [])
    records = _cninfo_records(announcements, retrieved_at=observed_at)
    relevant_announcement_count = sum(
        1
        for announcement in announcements
        if _cninfo_materiality_category(_clean_cninfo_title(announcement.get("announcementTitle"))) is not None
    )
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"cninfo-{symbol}-{start_date}-{end_date}",
        "provider_id": "cninfo_public_announcements",
        "content_class": "official_fact",
        "source_endpoint": _CNINFO_QUERY_URL,
        "license_tier": "personal_internal_research_user_authorized_no_redistribution",
        "attribution": "hernando_zhao",
        "retrieved_at": _iso_datetime(observed_at),
        "records": records,
    }
    return {
        "artifact_type": "external_context_public_source_poc",
        "schema_version": CNINFO_POC_VERSION,
        "source": "cninfo",
        "query": {"symbol": symbol, "start_date": start_date, "end_date": end_date},
        "transport_security": "official_https",
        "announcement_body_downloaded": False,
        "reported_total": total,
        "fetched_announcement_count": len(announcements),
        "irrelevant_or_routine_title_excluded_count": len(announcements) - relevant_announcement_count,
        "relevant_announcement_count_before_grouping": relevant_announcement_count,
        "same_day_category_collapsed_count": relevant_announcement_count - len(records),
        "page_count": page_count,
        "record_count": len(records),
        "timestamp_resolution": "provider_calendar_day_conservative_end_of_shanghai_day",
        "pit_candidate_status": "sample_ready" if records else "empty_sample",
        "pilot_input": pilot_input,
        "sample_digest": _canonical_hash(pilot_input),
    }


def run_cninfo_historical_eligibility_canary(
    *,
    database_path: str | Path,
    signal_dates: Iterable[str],
    symbols_per_date: int = 6,
    window_days: int = 31,
    fetcher: Any = None,
) -> dict[str, Any]:
    """Select deterministic PIT-price-eligible symbols and fetch bounded surrounding announcement windows."""
    if symbols_per_date < 1 or symbols_per_date > 25:
        raise ValueError("symbols_per_date must be between 1 and 25")
    if window_days < 1 or window_days > 61 or window_days % 2 == 0:
        raise ValueError("window_days must be an odd number between 1 and 61")
    parsed_dates = [date.fromisoformat(value) for value in signal_dates]
    if not parsed_dates:
        raise ValueError("at least one signal date is required")
    resolved_path = Path(database_path).expanduser().resolve()
    if not resolved_path.is_file():
        raise ValueError(f"database_path does not exist: {resolved_path}")
    client_fetcher = fetcher or fetch_cninfo_announcement_poc
    connection = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    selected_symbols: set[str] = set()
    selections: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    source_samples: list[dict[str, Any]] = []
    half_window = window_days // 2
    try:
        for signal_day in parsed_dates:
            rows = connection.execute(
                """
                SELECT s.symbol, m.close_price, m.observed_at
                FROM market_bars AS m
                JOIN stocks AS s ON s.id = m.stock_id
                WHERE m.timeframe = '1d' AND date(m.observed_at) = ?
                ORDER BY s.symbol
                """,
                (signal_day.isoformat(),),
            ).fetchall()
            eligible: list[tuple[str, dict[str, Any]]] = []
            for row in rows:
                symbol = str(row["symbol"])
                snapshot = build_trade_eligibility_snapshot(
                    symbol,
                    stock_profile=None,
                    as_of=signal_day,
                    decision_cutoff=f"{signal_day.isoformat()}T15:00:00+08:00",
                    price_cny=float(row["close_price"]),
                    price_observed_at=str(row["observed_at"]),
                    price_source="runtime_market_bars_historical_unadjusted_close",
                    price_adjustment="unadjusted",
                    profile_is_point_in_time=False,
                )
                snapshots.append(snapshot)
                if snapshot["eligible_before_scoring"] and symbol not in selected_symbols:
                    eligible.append((symbol, snapshot))
            eligible.sort(key=lambda item: hashlib.sha256(f"{signal_day}:{item[0]}".encode()).hexdigest())
            chosen = eligible[:symbols_per_date]
            if len(chosen) < symbols_per_date:
                raise ValueError(
                    f"only {len(chosen)} unique eligible symbols for {signal_day}, need {symbols_per_date}"
                )
            start = signal_day - timedelta(days=half_window)
            end = signal_day + timedelta(days=half_window)
            for symbol, snapshot in chosen:
                selected_symbols.add(symbol)
                provider_symbol = symbol.split(".", 1)[0]
                sample = client_fetcher(
                    symbol=provider_symbol,
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                )
                all_records.extend(sample["pilot_input"]["records"])
                source_samples.append(
                    {
                        "signal_date": signal_day.isoformat(),
                        "symbol": symbol,
                        "provider_symbol": provider_symbol,
                        "window_start": start.isoformat(),
                        "window_end": end.isoformat(),
                        "reported_total": sample["reported_total"],
                        "fetched_announcement_count": sample["fetched_announcement_count"],
                        "material_before_grouping": sample["relevant_announcement_count_before_grouping"],
                        "retained_event_packages": sample["record_count"],
                        "sample_digest": sample["sample_digest"],
                    }
                )
                selections.append(
                    {
                        "signal_date": signal_day.isoformat(),
                        "symbol": symbol,
                        "eligibility_snapshot_id": snapshot["snapshot_id"],
                        "price_cny": snapshot["price"]["value_cny"],
                        "warnings": snapshot["warnings"],
                    }
                )
    finally:
        connection.close()
    deduplicated = {record["provider_item_id"]: record for record in all_records}
    retrieved_values = [record["first_seen_at"] for record in deduplicated.values()]
    combined_retrieved_at = max(retrieved_values) if retrieved_values else datetime.now(UTC).isoformat()
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"cninfo-historical-eligibility-canary-{min(parsed_dates)}-{max(parsed_dates)}",
        "provider_id": "cninfo_public_announcements",
        "content_class": "official_fact",
        "source_endpoint": _CNINFO_QUERY_URL,
        "license_tier": "personal_internal_research_user_authorized_no_redistribution",
        "attribution": "hernando_zhao",
        "retrieved_at": combined_retrieved_at,
        "records": list(deduplicated.values()),
    }
    eligibility_summary = summarize_trade_eligibility_snapshots(snapshots)
    return {
        "artifact_type": "external_context_public_source_canary",
        "schema_version": CNINFO_CANARY_VERSION,
        "database_source": str(resolved_path),
        "database_open_mode": "read_only",
        "signal_dates": [value.isoformat() for value in parsed_dates],
        "symbols_per_date": symbols_per_date,
        "window_days": window_days,
        "selected_symbol_count": len(selected_symbols),
        "selected_symbols": selections,
        "historical_current_profile_fields_used": False,
        "pit_risk_status_verified": False,
        "eligibility_warning": "pit_risk_status_unverified_current_static_name_not_used",
        "eligibility_summary": eligibility_summary,
        "request_count": len(source_samples),
        "all_requests_complete": all(
            row["reported_total"] == row["fetched_announcement_count"] for row in source_samples
        ),
        "reported_announcement_count": sum(row["reported_total"] for row in source_samples),
        "material_announcement_count_before_grouping": sum(
            row["material_before_grouping"] for row in source_samples
        ),
        "retained_event_package_count": len(deduplicated),
        "source_samples": source_samples,
        "pilot_input": pilot_input,
        "sample_digest": _canonical_hash(pilot_input),
        "claim_ceiling": "bounded_public_source_canary_no_external_alpha_validation",
        "v3_signal_changed": False,
    }


def _download_bounded_archive(
    client: requests.Session,
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
) -> bytes:
    response = client.get(
        url,
        headers={"User-Agent": "hernando_zhao-personal-research/1.0 GDELT-attributed"},
        stream=True,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > max_bytes:
        raise ValueError(f"GDELT archive Content-Length exceeds {max_bytes} bytes")
    chunks: list[bytes] = []
    used = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        used += len(chunk)
        if used > max_bytes:
            raise ValueError(f"GDELT archive exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _gdelt_topic(source_url: str) -> tuple[str, tuple[str, ...]] | None:
    # Directory names and publisher domains often contain words such as "telecom" even when the
    # linked story is unrelated. Requiring the topic in the headline slug materially reduces that noise.
    searchable = _gdelt_headline(source_url).lower()
    for topic, pattern, sectors in _GDELT_TOPIC_PATTERNS:
        if pattern.search(searchable):
            return topic, sectors
    return None


def _gdelt_headline(source_url: str) -> str:
    path = unquote(urlparse(source_url).path).rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"\.(?:html?|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    cleaned = " ".join(re.sub(r"[-_]+", " ", slug).split())
    alpha_characters = sum(character.isalpha() for character in cleaned)
    if alpha_characters < 12 or len(cleaned.split()) < 3:
        return ""
    return cleaned[:300]


def _normalized_gdelt_headline(headline: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", headline.lower()).split())


def _gdelt_relevance_exclusion(topic: str, headline: str) -> str | None:
    for reason, pattern in _GDELT_TOPIC_EXCLUSION_PATTERNS.get(topic, ()):
        if pattern.search(headline):
            return reason
    return None


def _gdelt_geographies(row: list[str]) -> list[str]:
    values = {row[index].strip() for index in (7, 17, 37, 44, 51) if row[index].strip()}
    return sorted(values)


def _gdelt_candidate_priority(row: list[str]) -> tuple[float, int, int, str]:
    try:
        impact = abs(float(row[30]))
    except ValueError:
        impact = 0.0
    try:
        sources = int(row[32])
    except ValueError:
        sources = 0
    try:
        mentions = int(row[31])
    except ValueError:
        mentions = 0
    return (impact, sources, mentions, row[0])


def _gdelt_record(
    row: list[str],
    *,
    topic: str,
    sectors: tuple[str, ...],
    retrieved_at: datetime,
    available_from: datetime,
) -> dict[str, Any]:
    source_url = row[57].strip()
    domain = (urlparse(source_url).hostname or "").lower()
    headline = _gdelt_headline(source_url)
    actor1 = row[6].strip() or row[5].strip() or "unspecified actor"
    actor2 = row[16].strip() or row[15].strip() or "unspecified counterpart"
    summary = (
        f"GDELT event metadata links {actor1} and {actor2}; event code {row[26].strip() or 'unknown'}, "
        f"Goldstein scale {row[30].strip() or 'unknown'}. This is discovery metadata, not an article-body summary."
    )
    metadata = {
        "gdelt_event_id": row[0],
        "date_added": row[56],
        "event_code": row[26],
        "goldstein_scale": row[30],
        "source_url": source_url,
        "topic": topic,
    }
    content_hash = _canonical_hash(metadata)
    raw_payload = {
        "content_hash": content_hash,
        "headline": headline,
        "language": "und",
        "source_name": domain,
        "source_url": source_url,
        "summary": summary,
        "summary_method": "extractive",
        "summary_model_version": None,
    }
    geographies = _gdelt_geographies(row)
    return {
        "provider_item_id": f"gdelt:{row[0]}",
        "normalized_event_id": (
            "gdelt-headline:"
            f"{hashlib.sha256(f'{topic}|{_normalized_gdelt_headline(headline)}'.encode()).hexdigest()[:24]}"
        ),
        "revision_id": f"event:{row[0]}:{content_hash[:16]}",
        "provider_published_at": _iso_datetime(available_from),
        "provider_updated_at": None,
        "first_seen_at": _iso_datetime(retrieved_at),
        "available_from": _iso_datetime(available_from),
        "availability_basis": "provider_effective_at_documented",
        "availability_evidence_ref": GDELT_EVENT_CODEBOOK_URL,
        "event_type": "gdelt_public_discovery_metadata",
        "source_authority": "public_news_metadata_aggregator",
        "entities": [],
        "sectors": list(sectors),
        "geographies": geographies,
        "raw_payload": raw_payload,
        "normalized_payload": {
            **raw_payload,
            "affected_symbols": [],
            "channel_scope": "global_state",
            "relevance_components": {
                "global_topic_match": 0.95,
                "source_quality": 0.55,
                "novelty": 1.0,
                "time_lineage": 0.8,
            },
            "sector_ids": list(sectors),
            "topic_tags": [topic],
        },
    }


def probe_gdelt_daily_public_discovery(
    *,
    archive_date: str,
    retrieved_at: datetime | None = None,
    session: requests.Session | None = None,
    timeout_seconds: float = 30.0,
    max_archive_bytes: int = GDELT_DAILY_ARCHIVE_MAX_BYTES,
    max_rows: int = GDELT_DAILY_MAX_ROWS,
    selected_limit: int = GDELT_DAILY_SELECTED_LIMIT,
) -> dict[str, Any]:
    """Stream one daily GDELT event archive in memory and retain compact relevant metadata only."""
    archive_day = _parse_basic_date(archive_date, field="archive_date")
    observed_at = _retrieved_at(retrieved_at)
    available_from = datetime.combine(archive_day + timedelta(days=2), time.min, tzinfo=UTC)
    if observed_at < available_from:
        raise ValueError("daily GDELT archive is not PIT-eligible until the second following UTC day")
    if max_archive_bytes < 1 or max_archive_bytes > GDELT_DAILY_ARCHIVE_MAX_BYTES:
        raise ValueError(f"max_archive_bytes cannot exceed {GDELT_DAILY_ARCHIVE_MAX_BYTES}")
    if max_rows < 1 or max_rows > GDELT_DAILY_MAX_ROWS:
        raise ValueError(f"max_rows cannot exceed {GDELT_DAILY_MAX_ROWS}")
    if selected_limit < 1 or selected_limit > GDELT_DAILY_SELECTED_LIMIT:
        raise ValueError(f"selected_limit cannot exceed {GDELT_DAILY_SELECTED_LIMIT}")

    client = session or requests.Session()
    archive_url = f"{_GDELT_ARCHIVE_ROOT}/{archive_date}.export.CSV.zip"
    archive = _download_bounded_archive(
        client,
        archive_url,
        timeout_seconds=timeout_seconds,
        max_bytes=max_archive_bytes,
    )
    archive_hash = hashlib.sha256(archive).hexdigest()
    candidates_by_headline: dict[str, tuple[list[str], str, tuple[str, ...]]] = {}
    row_count = 0
    malformed_row_count = 0
    topic_match_row_count = 0
    relevant_row_count = 0
    relevance_quality_exclusion_counts: dict[str, int] = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        members = [member for member in bundle.infolist() if not member.is_dir()]
        if len(members) != 1:
            raise ValueError("GDELT archive must contain exactly one event CSV")
        member = members[0]
        if member.file_size > GDELT_DAILY_UNCOMPRESSED_MAX_BYTES:
            raise ValueError("GDELT archive exceeds the uncompressed safety limit")
        with bundle.open(member) as handle:
            for raw_line in handle:
                row_count += 1
                if row_count > max_rows:
                    raise ValueError(f"GDELT archive exceeds max_rows={max_rows}")
                row = raw_line.decode("utf-8", errors="replace").rstrip("\r\n").split("\t")
                if len(row) != 58 or row[56] != archive_date:
                    malformed_row_count += 1
                    continue
                source_url = row[57].strip()
                if not source_url.startswith(("http://", "https://")):
                    malformed_row_count += 1
                    continue
                if not _gdelt_headline(source_url):
                    continue
                topic_match = _gdelt_topic(source_url)
                if topic_match is None:
                    continue
                topic, sectors = topic_match
                topic_match_row_count += 1
                headline = _gdelt_headline(source_url)
                exclusion = _gdelt_relevance_exclusion(topic, headline)
                if exclusion is not None:
                    key = f"{topic}:{exclusion}"
                    relevance_quality_exclusion_counts[key] = relevance_quality_exclusion_counts.get(key, 0) + 1
                    continue
                if topic in {"trade_restriction", "us_macro_policy"}:
                    if not set(_gdelt_geographies(row)) & _GDELT_ASIA_US_GEO_CODES:
                        continue
                relevant_row_count += 1
                headline_key = f"{topic}|{_normalized_gdelt_headline(headline)}"
                previous = candidates_by_headline.get(headline_key)
                if previous is None or _gdelt_candidate_priority(row) > _gdelt_candidate_priority(previous[0]):
                    candidates_by_headline[headline_key] = (row, topic, sectors)
    selected: list[tuple[list[str], str, tuple[str, ...]]] = []
    selected_topic_counts: dict[str, int] = {}
    for topic, topic_limit in GDELT_TOPIC_SELECTED_LIMITS.items():
        ranked_topic = sorted(
            (item for item in candidates_by_headline.values() if item[1] == topic),
            key=lambda item: (_gdelt_candidate_priority(item[0]), item[0][57]),
            reverse=True,
        )[: min(topic_limit, selected_limit - len(selected))]
        selected.extend(ranked_topic)
        selected_topic_counts[topic] = len(ranked_topic)
        if len(selected) >= selected_limit:
            break
    ranked = sorted(
        selected,
        key=lambda item: (_gdelt_candidate_priority(item[0]), item[0][57]),
        reverse=True,
    )
    records = [
        _gdelt_record(
            row,
            topic=topic,
            sectors=sectors,
            retrieved_at=observed_at,
            available_from=available_from,
        )
        for row, topic, sectors in ranked
    ]
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"gdelt-daily-public-discovery-{archive_date}",
        "provider_id": "gdelt_daily_public_discovery",
        "content_class": "news_summary",
        "source_endpoint": archive_url,
        "license_tier": "gdelt_unrestricted_use_with_attribution_summary_only",
        "attribution": "GDELT Project; personal analysis by hernando_zhao",
        "retrieved_at": _iso_datetime(observed_at),
        "records": records,
    }
    return {
        "artifact_type": "external_context_public_source_poc",
        "schema_version": GDELT_POC_VERSION,
        "source": "gdelt_daily_events",
        "archive_date": archive_date,
        "archive_url": archive_url,
        "transport_security": "https_google_cloud_storage_official_gdelt_bucket",
        "archive_persisted": False,
        "archive_bytes_read_in_memory": len(archive),
        "archive_sha256": archive_hash,
        "row_count": row_count,
        "malformed_or_date_mismatch_row_count": malformed_row_count,
        "topic_match_row_count": topic_match_row_count,
        "relevance_quality_exclusion_counts": dict(sorted(relevance_quality_exclusion_counts.items())),
        "relevance_rule_version": GDELT_RELEVANCE_RULE_VERSION,
        "relevant_row_count_before_url_dedup": relevant_row_count,
        "unique_relevant_url_count": len(candidates_by_headline),
        "unique_relevant_headline_count": len(candidates_by_headline),
        "selected_record_count": len(records),
        "selected_topic_counts": selected_topic_counts,
        "selected_limit": selected_limit,
        "article_body_downloaded": False,
        "timestamp_resolution": "DATEADDED_day_conservative_second_following_utc_day",
        "pit_candidate_status": "sample_ready" if records else "empty_sample",
        "historical_backfill_transport_status": "https_and_archive_sha256_manifest_ready",
        "pilot_input": pilot_input,
        "sample_digest": _canonical_hash(pilot_input),
    }
