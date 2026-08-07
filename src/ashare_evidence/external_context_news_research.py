from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.intraday_market import DEFAULT_TUSHARE_BASE_URL, _post_tushare
from ashare_evidence.models import ProviderCredential

SCHEMA_VERSION = "external_context_news_title_research_snapshot.v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_SOURCES = ("财联社", "华尔街见闻", "新华网", "中证网")
TOPIC_KEYWORDS = {
    "semiconductor": ("芯片", "半导体", "晶圆", "光刻", "存储器", "集成电路"),
    "telecommunications": ("通信", "电信", "5G", "6G", "光模块", "算力"),
    "global_equity": ("美股", "纳斯达克", "标普", "港股", "恒生", "科技股"),
    "monetary_policy": ("美联储", "加息", "降息", "利率", "国债收益率", "流动性"),
    "trade_policy": ("关税", "出口管制", "实体清单", "制裁", "禁令", "贸易战"),
    "currency": ("人民币", "美元", "汇率", "离岸人民币"),
    "commodity": ("原油", "石油", "黄金", "铜价", "大宗商品"),
    "ai": ("人工智能", "AI", "大模型", "数据中心", "机器人"),
}


def stable_digest(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _response_rows(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise ValueError("Tushare returned no news response")
    if int(response.get("code") or 0) != 0:
        raise ValueError(f"Tushare news request failed: {response.get('msg') or response.get('message')}")
    data = response.get("data") or {}
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not isinstance(fields, list) or not isinstance(items, list):
        raise ValueError("Tushare news response has an invalid data envelope")
    return [dict(zip(fields, item, strict=False)) for item in items]


def _relevance(
    title: str,
    *,
    company_names: Iterable[str],
    industry_names: Iterable[str],
) -> dict[str, list[str]]:
    matched_companies = sorted({name for name in company_names if len(name) >= 3 and name in title})
    matched_industries = sorted({name for name in industry_names if len(name) >= 2 and name in title})
    matched_topics = sorted(
        topic for topic, keywords in TOPIC_KEYWORDS.items() if any(keyword.lower() in title.lower() for keyword in keywords)
    )
    return {
        "company_names": matched_companies,
        "industry_names": matched_industries,
        "topics": matched_topics,
    }


def normalize_news_title_rows(
    rows: Iterable[dict[str, Any]],
    *,
    company_names: Iterable[str],
    industry_names: Iterable[str],
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    normalized: list[dict[str, Any]] = []
    duplicate_count = 0
    seen: set[tuple[str, str, str]] = set()
    for raw in rows:
        title = " ".join(str(raw.get("title") or "").split())
        source = str(raw.get("src") or "").strip()
        published = datetime.strptime(str(raw.get("pub_time") or ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
        key = (source, published.isoformat(), title)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        available_at = published + timedelta(hours=1)
        if available_at.astimezone(UTC) > retrieved_at.astimezone(UTC):
            raise ValueError(f"future news title returned by provider: {key}")
        relevance = _relevance(title, company_names=company_names, industry_names=industry_names)
        if not any(relevance.values()):
            continue
        normalized.append(
            {
                "news_id": stable_digest({"source": source, "published_at": published.isoformat(), "title": title})[:24],
                "source": source,
                "title_summary": title,
                "published_at": published.isoformat(),
                "available_at": available_at.isoformat(),
                "availability_basis": "provider_pub_time_plus_one_hour_conservative_research_lag",
                "url": str(raw.get("url") or "").strip() or None,
                "relevance": relevance,
            }
        )
    return sorted(normalized, key=lambda row: (row["available_at"], row["news_id"])), {
        "duplicate_raw_row_count": duplicate_count,
        "unique_raw_row_count": len(seen),
    }


def build_news_title_snapshot(
    *,
    raw_batches: list[dict[str, Any]],
    company_names: Iterable[str],
    industry_names: Iterable[str],
    retrieved_at: datetime,
    source_endpoint: str,
) -> dict[str, Any]:
    raw_rows = [row for batch in raw_batches for row in batch["rows"]]
    records, normalization_audit = normalize_news_title_rows(
        raw_rows,
        company_names=company_names,
        industry_names=industry_names,
        retrieved_at=retrieved_at,
    )
    source_counts: dict[str, int] = defaultdict(int)
    topic_counts: dict[str, int] = defaultdict(int)
    for row in records:
        source_counts[str(row["source"])] += 1
        for topic in row["relevance"]["topics"]:
            topic_counts[str(topic)] += 1
    material = {
        "artifact_type": "external_context_news_title_research_snapshot",
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved_at.isoformat(),
        "source_endpoint": source_endpoint,
        "provider_id": "tushare_major_news",
        "license_scope": "personal_noncommercial_research_no_redistribution",
        "attribution": "hernando_zhao / Tushare / original named news sources",
        "content_policy": "title_level_summaries_only_no_article_body",
        "provider_revision_id_available": False,
        "first_seen_at_available": False,
        "promotion_blocker": "provider_revision_and_first_seen_lineage_missing_requires_qualified_vendor_reproduction",
        "claim_ceiling": "provisional_pit_conservative_news_title_research_input_not_production_vendor_data",
        "raw": {"batches": raw_batches},
        "normalized": {"records": records},
        "quality": {
            "raw_batch_count": len(raw_batches),
            "raw_row_count": len(raw_rows),
            "unique_raw_row_count": normalization_audit["unique_raw_row_count"],
            "duplicate_raw_row_count": normalization_audit["duplicate_raw_row_count"],
            "relevant_record_count": len(records),
            "relevant_source_counts": dict(sorted(source_counts.items())),
            "relevant_topic_counts": dict(sorted(topic_counts.items())),
            "future_available_at_count": 0,
            "article_body_saved_count": 0,
        },
    }
    return {**material, "content_digest": stable_digest(material)}


def acquire_news_title_snapshot(
    session: Session,
    *,
    start: datetime,
    end: datetime,
    company_names: Iterable[str],
    industry_names: Iterable[str],
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    initial_window_days: int = 3,
    maximum_rows_per_batch: int = 350,
    retrieved_at: datetime | None = None,
    request_fn: Callable[..., dict[str, Any] | None] = _post_tushare,
) -> dict[str, Any]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("news acquisition bounds must include timezone")
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

    def fetch(source: str, window_start: datetime, window_end: datetime) -> None:
        response = request_fn(
            base_url=base_url,
            token=credential.access_token.strip(),
            api_name="major_news",
            params={
                "src": source,
                "start_date": window_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": window_end.strftime("%Y-%m-%d %H:%M:%S"),
            },
            fields="title,pub_time,src,url",
        )
        rows = _response_rows(response)
        duration = window_end - window_start
        if len(rows) > maximum_rows_per_batch and duration > timedelta(hours=1):
            midpoint = window_start + duration / 2
            fetch(source, window_start, midpoint)
            fetch(source, midpoint + timedelta(seconds=1), window_end)
            return
        if len(rows) > maximum_rows_per_batch:
            raise ValueError(f"news density exceeds safe one-hour batch for {source} at {window_start}")
        raw_batches.append(
            {
                "source": source,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "row_count": len(rows),
                "rows": rows,
            }
        )

    for source in sources:
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=initial_window_days) - timedelta(seconds=1), end)
            fetch(source, cursor, window_end)
            cursor = window_end + timedelta(seconds=1)
    return build_news_title_snapshot(
        raw_batches=raw_batches,
        company_names=company_names,
        industry_names=industry_names,
        retrieved_at=retrieved_at or datetime.now(UTC),
        source_endpoint=base_url,
    )


def write_news_title_snapshot(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key != "content_digest"}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("news title snapshot digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable news title snapshot already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
