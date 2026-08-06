from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import os
import re
import time as time_module
from collections import Counter
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

from ashare_evidence.external_context_news_summary import NEWS_STORAGE_HARD_CAP_BYTES

FEDERAL_RESERVE_POC_VERSION = "external_context_federal_reserve_policy_poc.v2"
FEDERAL_REGISTER_POC_VERSION = "external_context_federal_register_policy_poc.v2"
OFFICIAL_POLICY_ATTRIBUTION = "hernando_zhao"
OFFICIAL_POLICY_LICENSE_TIER = "us_government_public_metadata_personal_research"
FEDERAL_RESERVE_ARCHIVE_URL = "https://www.federalreserve.gov/newsevents/pressreleases/{year}-press.htm"
FEDERAL_RESERVE_FEED_DIRECTORY_URL = "https://www.federalreserve.gov/feeds/feeds.htm"
FEDERAL_REGISTER_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
FEDERAL_REGISTER_API_DOCUMENTATION_URL = "https://www.federalregister.gov/developers/documentation/api/v1"
OFFICIAL_SOURCE_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
OFFICIAL_SOURCE_DEFAULT_REQUEST_INTERVAL_SECONDS = 0.5
OFFICIAL_SOURCE_MAX_ATTEMPTS = 4
FEDERAL_REGISTER_MAX_PAGES = 50
FEDERAL_REGISTER_MAX_TERMS = 8
FEDERAL_REGISTER_DEFAULT_TERMS = (
    "semiconductor",
    "advanced computing",
    "export control",
    "section 232 tariff",
    "telecommunications 5G",
)

_FED_ARCHIVE_EVENT_PATTERN = re.compile(
    r"<time>\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*</time>.*?"
    r"<a\s+href=[\"'](?P<href>/newsevents/pressreleases/[^\"']+\.htm)[\"']>"
    r"\s*<em>(?P<title>.*?)</em>\s*</a>.*?"
    r"<p\s+class=[\"']eventlist__press[\"']>\s*<em>\s*<strong>(?P<category>.*?)</strong>",
    re.IGNORECASE | re.DOTALL,
)
_FEDERAL_REGISTER_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "semiconductor_policy",
        re.compile(
            r"\b(?:semiconductors?|advanced computing|integrated circuits?|microelectronics|ai chips?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "trade_and_export_control",
        re.compile(
            r"\b(?:export controls?|export administration regulations?|entity list|section 232|tariffs?|"
            r"import restrictions?|rare earths?|outbound investment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "telecommunications_policy",
        re.compile(
            r"\b(?:telecommunications?|5g|wireless networks?|information and communications technology)\b",
            re.IGNORECASE,
        ),
    ),
)
_FEDERAL_REGISTER_SEMICONDUCTOR_AGENCIES = {
    "Commerce Department",
    "Defense Department",
    "Executive Office of the President",
    "Federal Procurement Policy Office",
    "Foreign-Trade Zones Board",
    "General Services Administration",
    "Industry and Security Bureau",
    "Internal Revenue Service",
    "Management and Budget Office",
    "National Aeronautics and Space Administration",
    "National Institute of Standards and Technology",
    "Trade Representative, Office of United States",
    "Treasury Department",
}
_FEDERAL_REGISTER_TELECOM_AGENCIES = {
    "Commerce Department",
    "Federal Communications Commission",
    "Foreign-Trade Zones Board",
    "Industry and Security Bureau",
    "National Telecommunications and Information Administration",
}
_FEDERAL_REGISTER_TRADE_AGENCIES = {
    "Commerce Department",
    "Executive Office of the President",
    "Homeland Security Department",
    "Industry and Security Bureau",
    "International Trade Administration",
    "Trade Representative, Office of United States",
    "Treasury Department",
    "U.S. Customs and Border Protection",
}
_FEDERAL_REGISTER_TELECOM_STRATEGIC_HEADLINE_PATTERN = re.compile(
    r"\b(?:5g|6g|wireless networks?|connected vehicles?|unmanned aircraft systems?|"
    r"information and communications technology|equipment authorization|certification bodies|"
    r"telecommunications equipment|supply chain)\b",
    re.IGNORECASE,
)
_FEDERAL_REGISTER_TRADE_CORE_HEADLINE_PATTERN = re.compile(
    r"\b(?:entity list|unverified list|export administration regulations?|export controls?|"
    r"foreign direct product rule|validated end[- ]user|section 301|section 232|outbound investment|"
    r"import restrictions?|tariff adjustments?|tariff offsets?|supply chain)\b",
    re.IGNORECASE,
)
_FEDERAL_REGISTER_STRATEGIC_PRODUCT_PATTERN = re.compile(
    r"\b(?:china|semiconductors?|advanced computing|integrated circuits?|artificial intelligence|ai chips?|"
    r"steel|aluminum|solar|critical minerals?|rare earths?|robotics|industrial machinery|automotive|"
    r"vehicles?|telecommunications?|5g|6g|batter(?:y|ies)|graphite)\b",
    re.IGNORECASE,
)
_FEDERAL_REGISTER_ADMINISTRATIVE_NOISE_PATTERN = re.compile(
    r"^(?:agency information collection activities|notice of receipt of complaint|"
    r"60-day notice of proposed information collection)",
    re.IGNORECASE,
)
_FEDERAL_REGISTER_OUT_OF_SCOPE_PRODUCT_PATTERN = re.compile(
    r"\b(?:agricultur(?:e|al)|chemical weapons?|medical devices?|pharmaceuticals?|"
    r"personal protective equipment|fish products?|firearms?|munitions?|arms export|"
    r"defense articles?|defense services?)\b",
    re.IGNORECASE,
)
_FEDERAL_REGISTER_SECTOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "semiconductor",
        re.compile(
            r"\b(?:semiconductors?|advanced computing|integrated circuits?|microelectronics|ai chips?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "telecommunications",
        re.compile(
            r"\b(?:telecommunications?|5g|6g|wireless networks?|information and communications technology)\b",
            re.IGNORECASE,
        ),
    ),
    ("strategic_materials", re.compile(r"\b(?:steel|aluminum|critical minerals?|rare earths?|graphite)\b", re.I)),
    ("clean_energy", re.compile(r"\b(?:solar|batter(?:y|ies))\b", re.I)),
    ("automotive", re.compile(r"\b(?:automotive|automobiles?|vehicles?|vehicle parts?)\b", re.I)),
)


def _canonical_hash(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _aware_retrieval(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return resolved


def _bounded_get(
    client: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout_seconds: float,
    max_response_bytes: int,
    max_attempts: int = OFFICIAL_SOURCE_MAX_ATTEMPTS,
    sleeper: Any = time_module.sleep,
) -> requests.Response:
    if max_response_bytes < 1 or max_response_bytes > OFFICIAL_SOURCE_MAX_RESPONSE_BYTES:
        raise ValueError(f"max_response_bytes cannot exceed {OFFICIAL_SOURCE_MAX_RESPONSE_BYTES}")
    if max_attempts < 1 or max_attempts > OFFICIAL_SOURCE_MAX_ATTEMPTS:
        raise ValueError(f"max_attempts cannot exceed {OFFICIAL_SOURCE_MAX_ATTEMPTS}")
    response: requests.Response | None = None
    for attempt in range(1, max_attempts + 1):
        response = client.get(
            url,
            params=params,
            headers={"User-Agent": "hernando_zhao-personal-research/1.0 summary-only-no-redistribution"},
            timeout=timeout_seconds,
        )
        try:
            response.raise_for_status()
            break
        except requests.HTTPError:
            retryable = response.status_code == 429 or 500 <= response.status_code < 600
            if not retryable or attempt == max_attempts:
                raise
            sleeper(float(attempt))
    if response is None:
        raise RuntimeError("official source request did not produce a response")
    if len(response.content) > max_response_bytes:
        raise ValueError(f"official source response exceeds {max_response_bytes} bytes")
    return response


def _clean_markup(value: Any, *, max_characters: int = 1500) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(without_tags).split())[:max_characters]


def _root_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0


def _federal_register_checkpoint_path(
    root: Path,
    *,
    start: date,
    end: date,
    term: str,
    page: int,
) -> Path:
    term_id = hashlib.sha256(term.encode("utf-8")).hexdigest()[:16]
    return root / "acquisition" / "federal-register" / f"{start}_{end}" / term_id / f"page-{page:04d}.json"


def _federal_reserve_checkpoint_path(root: Path, *, start: date, end: date, year: int) -> Path:
    return root / "acquisition" / "federal-reserve" / f"{start}_{end}" / f"year-{year}.json"


def _write_immutable_checkpoint(path: Path, payload: dict[str, Any], *, artifact_root: Path) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if path.exists():
        if path.read_bytes() != rendered:
            raise RuntimeError(f"immutable official-source checkpoint collision: {path}")
        return
    used = _root_bytes(artifact_root)
    if used + len(rendered) > NEWS_STORAGE_HARD_CAP_BYTES:
        raise ValueError("Federal Register checkpoint would exceed the shared external-context hard cap")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())


def _conservative_day_times(value: date) -> tuple[datetime, datetime]:
    timezone = ZoneInfo("America/New_York")
    published_at = datetime.combine(value, time.min, tzinfo=timezone)
    available_from = datetime.combine(value, time(23, 59, 59, 999999), tzinfo=timezone)
    return published_at, available_from


def fetch_federal_reserve_policy_poc(
    *,
    start_date: str,
    end_date: str,
    retrieved_at: datetime | None = None,
    session: requests.Session | None = None,
    timeout_seconds: float = 30.0,
    max_response_bytes: int = OFFICIAL_SOURCE_MAX_RESPONSE_BYTES,
    checkpoint_root: str | Path | None = None,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    if end.year - start.year > 10:
        raise ValueError("Federal Reserve PoC cannot exceed eleven calendar years")
    observed_at = _aware_retrieval(retrieved_at)
    client = session or requests.Session()
    resolved_checkpoint_root = Path(checkpoint_root).expanduser().resolve() if checkpoint_root is not None else None
    if resolved_checkpoint_root is not None:
        if resolved_checkpoint_root in {Path(resolved_checkpoint_root.anchor), Path.home()}:
            raise ValueError("checkpoint_root cannot be a filesystem root or the home directory")
        resolved_checkpoint_root.mkdir(parents=True, exist_ok=True)
        if _root_bytes(resolved_checkpoint_root) > NEWS_STORAGE_HARD_CAP_BYTES:
            raise ValueError("checkpoint_root already exceeds the shared external-context hard cap")
    records_by_url: dict[str, dict[str, Any]] = {}
    source_pages: list[dict[str, Any]] = []
    for year in range(start.year, end.year + 1):
        url = FEDERAL_RESERVE_ARCHIVE_URL.format(year=year)
        checkpoint_path = (
            _federal_reserve_checkpoint_path(resolved_checkpoint_root, start=start, end=end, year=year)
            if resolved_checkpoint_root is not None
            else None
        )
        if checkpoint_path is not None and checkpoint_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            content = base64.b64decode(str(checkpoint["response_body_base64"]), validate=True)
            transport_sha256 = str(checkpoint["response_sha256"])
            if hashlib.sha256(content).hexdigest() != transport_sha256:
                raise ValueError(f"Federal Reserve checkpoint hash mismatch: {checkpoint_path}")
            page_first_seen_at = datetime.fromisoformat(str(checkpoint["retrieved_at"]))
            encoding = str(checkpoint.get("response_encoding") or "utf-8")
            network_used = False
            checkpoint_resumed = True
        else:
            response = _bounded_get(
                client,
                url,
                timeout_seconds=timeout_seconds,
                max_response_bytes=max_response_bytes,
            )
            content = response.content
            transport_sha256 = hashlib.sha256(content).hexdigest()
            page_first_seen_at = observed_at
            encoding = str(getattr(response, "encoding", None) or "utf-8")
            network_used = True
            checkpoint_resumed = False
            if checkpoint_path is not None:
                _write_immutable_checkpoint(
                    checkpoint_path,
                    {
                        "artifact_type": "federal_reserve_archive_checkpoint",
                        "schema_version": "federal_reserve_archive_checkpoint.v1",
                        "year": year,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "retrieved_at": observed_at.isoformat(),
                        "source_url": url,
                        "response_encoding": encoding,
                        "response_sha256": transport_sha256,
                        "response_body_base64": base64.b64encode(content).decode("ascii"),
                    },
                    artifact_root=resolved_checkpoint_root,
                )
        page_records: list[dict[str, str]] = []
        page_text = content.decode(encoding, errors="replace")
        for match in _FED_ARCHIVE_EVENT_PATTERN.finditer(page_text):
            event_date = datetime.strptime(match.group("date"), "%m/%d/%Y").date()
            category = _clean_markup(match.group("category"), max_characters=120)
            if event_date < start or event_date > end or category != "Monetary Policy":
                continue
            title = _clean_markup(match.group("title"), max_characters=500)
            source_url = urljoin("https://www.federalreserve.gov", match.group("href"))
            published_at, available_from = _conservative_day_times(event_date)
            raw_payload = {
                "category": category,
                "headline": title,
                "publication_date": event_date.isoformat(),
                "publication_time_resolution": "calendar_day",
                "source_url": source_url,
            }
            page_records.append(raw_payload)
            content_hash = _canonical_hash(raw_payload)
            source_slug = Path(match.group("href")).stem
            records_by_url[source_url] = {
                "provider_item_id": f"federal-reserve:{source_slug}",
                "normalized_event_id": f"federal-reserve:{source_slug}",
                "revision_id": f"content:{content_hash[:24]}",
                "provider_published_at": published_at.isoformat(),
                "provider_updated_at": None,
                "first_seen_at": page_first_seen_at.isoformat(),
                "available_from": available_from.isoformat(),
                "availability_basis": "provider_published_at_documented",
                "availability_evidence_ref": FEDERAL_RESERVE_FEED_DIRECTORY_URL,
                "event_type": "official_us_monetary_policy_release",
                "source_authority": "official_us_central_bank",
                "entities": [],
                "sectors": ["global_macro"],
                "geographies": ["US"],
                "raw_payload": raw_payload,
                "normalized_payload": {
                    **raw_payload,
                    "affected_symbols": [],
                    "channel_scope": "global_state",
                    "sector_ids": ["global_macro"],
                    "topic_tags": ["us_monetary_policy"],
                },
            }
        source_pages.append(
            {
                "year": year,
                "url": url,
                "transport_bytes": len(content),
                "transport_sha256": transport_sha256,
                "selected_record_count": len(page_records),
                "selected_content_sha256": _canonical_hash(page_records),
                "network_used": network_used,
                "checkpoint_resumed": checkpoint_resumed,
            }
        )
    records = sorted(records_by_url.values(), key=lambda row: (row["available_from"], row["provider_item_id"]))
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"federal-reserve-policy-{start}-{end}",
        "provider_id": "federal_reserve_official_archive",
        "content_class": "official_fact",
        "source_endpoint": FEDERAL_RESERVE_ARCHIVE_URL,
        "license_tier": OFFICIAL_POLICY_LICENSE_TIER,
        "attribution": OFFICIAL_POLICY_ATTRIBUTION,
        "retrieved_at": observed_at.isoformat(),
        "records": records,
    }
    return {
        "artifact_type": "external_context_official_source_poc",
        "schema_version": FEDERAL_RESERVE_POC_VERSION,
        "source": "federal_reserve_official_archive",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "source_pages": source_pages,
        "record_count": len(records),
        "publication_time_resolution": "calendar_day_conservative_end_of_new_york_day",
        "article_body_downloaded": False,
        "checkpoint_root": str(resolved_checkpoint_root) if resolved_checkpoint_root is not None else None,
        "pilot_input": pilot_input,
        "sample_digest": _canonical_hash(pilot_input),
        "v3_signal_changed": False,
    }


def _federal_register_topics(
    title: str,
    abstract: str,
    agency_names: list[str],
) -> tuple[list[str], list[str], list[str]]:
    searchable = f"{title} {abstract}"
    topics: list[str] = []
    sectors: set[str] = set()
    exclusions: list[str] = []
    agencies = set(agency_names)
    administrative_noise = bool(_FEDERAL_REGISTER_ADMINISTRATIVE_NOISE_PATTERN.search(title))
    out_of_scope_product = bool(_FEDERAL_REGISTER_OUT_OF_SCOPE_PRODUCT_PATTERN.search(title))
    for topic, pattern in _FEDERAL_REGISTER_TOPIC_PATTERNS:
        if not pattern.search(searchable):
            continue
        allowed = False
        if topic == "semiconductor_policy":
            allowed = (
                bool(agencies & _FEDERAL_REGISTER_SEMICONDUCTOR_AGENCIES)
                and bool(pattern.search(title))
                and not administrative_noise
            )
        elif topic == "telecommunications_policy":
            allowed = (
                bool(agencies & _FEDERAL_REGISTER_TELECOM_AGENCIES)
                and bool(_FEDERAL_REGISTER_TELECOM_STRATEGIC_HEADLINE_PATTERN.search(title))
                and not administrative_noise
            )
        elif topic == "trade_and_export_control":
            allowed = (
                bool(agencies & _FEDERAL_REGISTER_TRADE_AGENCIES)
                and not administrative_noise
                and not out_of_scope_product
                and (
                    bool(_FEDERAL_REGISTER_TRADE_CORE_HEADLINE_PATTERN.search(title))
                    or bool(_FEDERAL_REGISTER_STRATEGIC_PRODUCT_PATTERN.search(title))
                )
            )
        if allowed:
            topics.append(topic)
        else:
            exclusions.append(f"{topic}:agency_or_headline_scope")
    if topics:
        if "trade_and_export_control" in topics:
            sectors.add("industrial_supply_chain")
        for sector, pattern in _FEDERAL_REGISTER_SECTOR_PATTERNS:
            if pattern.search(searchable):
                sectors.add(sector)
    return topics, sorted(sectors), exclusions


def fetch_federal_register_policy_poc(
    *,
    start_date: str,
    end_date: str,
    terms: tuple[str, ...] = FEDERAL_REGISTER_DEFAULT_TERMS,
    retrieved_at: datetime | None = None,
    session: requests.Session | None = None,
    timeout_seconds: float = 30.0,
    per_page: int = 100,
    max_pages_per_term: int = FEDERAL_REGISTER_MAX_PAGES,
    max_response_bytes: int = OFFICIAL_SOURCE_MAX_RESPONSE_BYTES,
    min_request_interval_seconds: float = OFFICIAL_SOURCE_DEFAULT_REQUEST_INTERVAL_SECONDS,
    sleeper: Any = time_module.sleep,
    checkpoint_root: str | Path | None = None,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    if not terms or len(terms) > FEDERAL_REGISTER_MAX_TERMS:
        raise ValueError(f"terms must contain between 1 and {FEDERAL_REGISTER_MAX_TERMS} values")
    if per_page < 1 or per_page > 1000:
        raise ValueError("per_page must be between 1 and 1000")
    if max_pages_per_term < 1 or max_pages_per_term > FEDERAL_REGISTER_MAX_PAGES:
        raise ValueError(f"max_pages_per_term cannot exceed {FEDERAL_REGISTER_MAX_PAGES}")
    if min_request_interval_seconds < 0 or min_request_interval_seconds > 60:
        raise ValueError("min_request_interval_seconds must be between 0 and 60")
    observed_at = _aware_retrieval(retrieved_at)
    client = session or requests.Session()
    resolved_checkpoint_root = Path(checkpoint_root).expanduser().resolve() if checkpoint_root is not None else None
    if resolved_checkpoint_root is not None:
        if resolved_checkpoint_root in {Path(resolved_checkpoint_root.anchor), Path.home()}:
            raise ValueError("checkpoint_root cannot be a filesystem root or the home directory")
        resolved_checkpoint_root.mkdir(parents=True, exist_ok=True)
        if _root_bytes(resolved_checkpoint_root) > NEWS_STORAGE_HARD_CAP_BYTES:
            raise ValueError("checkpoint_root already exceeds the shared external-context hard cap")
    records_by_document: dict[str, dict[str, Any]] = {}
    query_evidence: list[dict[str, Any]] = []
    relevance_exclusion_counts: Counter[str] = Counter()
    last_request_started_at: float | None = None

    def request_gate() -> None:
        nonlocal last_request_started_at
        current = time_module.monotonic()
        if last_request_started_at is not None:
            remaining = min_request_interval_seconds - (current - last_request_started_at)
            if remaining > 0:
                sleeper(remaining)
        last_request_started_at = time_module.monotonic()

    for term in terms:
        page = 1
        reported_count = 0
        fetched_count = 0
        network_page_count = 0
        checkpoint_resume_page_count = 0
        while True:
            params = {
                "per_page": per_page,
                "page": page,
                "order": "oldest",
                "conditions[term]": term,
                "conditions[publication_date][gte]": start.isoformat(),
                "conditions[publication_date][lte]": end.isoformat(),
            }
            checkpoint_path = (
                _federal_register_checkpoint_path(
                    resolved_checkpoint_root,
                    start=start,
                    end=end,
                    term=term,
                    page=page,
                )
                if resolved_checkpoint_root is not None
                else None
            )
            if checkpoint_path is not None and checkpoint_path.exists():
                payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                checkpoint_resume_page_count += 1
            else:
                request_gate()
                response = _bounded_get(
                    client,
                    FEDERAL_REGISTER_API_URL,
                    params=params,
                    timeout_seconds=timeout_seconds,
                    max_response_bytes=max_response_bytes,
                    sleeper=sleeper,
                )
                payload = response.json()
                network_page_count += 1
                if checkpoint_path is not None:
                    checkpoint_payload = {
                        "artifact_type": "federal_register_page_checkpoint",
                        "schema_version": "federal_register_page_checkpoint.v1",
                        "term": term,
                        "page": page,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "retrieved_at": observed_at.isoformat(),
                        "response": payload,
                    }
                    _write_immutable_checkpoint(
                        checkpoint_path,
                        checkpoint_payload,
                        artifact_root=resolved_checkpoint_root,
                    )
            page_first_seen_at = observed_at
            if payload.get("artifact_type") == "federal_register_page_checkpoint":
                page_first_seen_at = datetime.fromisoformat(str(payload["retrieved_at"]))
                payload = payload["response"]
            results = payload.get("results") or []
            if not isinstance(results, list):
                raise ValueError("Federal Register results must be a list")
            reported_count = int(payload.get("count") or 0)
            fetched_count += len(results)
            for item in results:
                if not isinstance(item, dict):
                    continue
                document_number = str(item.get("document_number") or "").strip()
                title = _clean_markup(item.get("title"), max_characters=700)
                abstract = _clean_markup(item.get("abstract"), max_characters=1500)
                publication_date = date.fromisoformat(str(item.get("publication_date")))
                source_url = str(item.get("html_url") or "").strip()
                if not document_number or not title or not source_url or not (start <= publication_date <= end):
                    continue
                agency_names = sorted(
                    {
                        str(agency.get("name") or "").strip()
                        for agency in item.get("agencies") or []
                        if isinstance(agency, dict) and str(agency.get("name") or "").strip()
                    }
                )
                topics, sectors, exclusion_reasons = _federal_register_topics(title, abstract, agency_names)
                relevance_exclusion_counts.update(exclusion_reasons)
                if not topics:
                    continue
                published_at, available_from = _conservative_day_times(publication_date)
                raw_payload = {
                    "abstract": abstract,
                    "agencies": agency_names,
                    "document_number": document_number,
                    "document_type": str(item.get("type") or "").strip(),
                    "headline": title,
                    "official_pdf_url": str(item.get("pdf_url") or "").strip(),
                    "publication_date": publication_date.isoformat(),
                    "publication_time_resolution": "calendar_day",
                    "source_url": source_url,
                }
                content_hash = _canonical_hash(raw_payload)
                record = {
                    "provider_item_id": f"federal-register:{document_number}",
                    "normalized_event_id": f"federal-register:{document_number}",
                    "revision_id": f"document:{document_number}:{content_hash[:16]}",
                    "provider_published_at": published_at.isoformat(),
                    "provider_updated_at": None,
                    "first_seen_at": page_first_seen_at.isoformat(),
                    "available_from": available_from.isoformat(),
                    "availability_basis": "provider_published_at_documented",
                    "availability_evidence_ref": FEDERAL_REGISTER_API_DOCUMENTATION_URL,
                    "event_type": "official_us_policy_document_metadata",
                    "source_authority": "nara_gpo_metadata_with_official_pdf_reference",
                    "entities": [],
                    "sectors": sectors,
                    "geographies": ["US"],
                    "raw_payload": raw_payload,
                    "normalized_payload": {
                        **raw_payload,
                        "affected_symbols": [],
                        "channel_scope": "sector_state",
                        "sector_ids": sectors,
                        "topic_tags": topics,
                    },
                }
                previous = records_by_document.get(document_number)
                if previous is not None and previous["revision_id"] != record["revision_id"]:
                    raise ValueError(f"Federal Register document changed within one acquisition: {document_number}")
                if previous is None or record["first_seen_at"] < previous["first_seen_at"]:
                    records_by_document[document_number] = record
            total_pages = math.ceil(reported_count / per_page) if reported_count else 0
            if page >= total_pages or not results:
                break
            if page >= max_pages_per_term:
                raise ValueError(f"Federal Register query for {term!r} exceeds max_pages_per_term")
            page += 1
        query_evidence.append(
            {
                "term": term,
                "reported_count": reported_count,
                "fetched_count": fetched_count,
                "page_count": page,
                "network_page_count": network_page_count,
                "checkpoint_resume_page_count": checkpoint_resume_page_count,
            }
        )
    records = sorted(records_by_document.values(), key=lambda row: (row["available_from"], row["provider_item_id"]))
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"federal-register-policy-{start}-{end}",
        "provider_id": "federal_register_policy_metadata",
        "content_class": "official_fact",
        "source_endpoint": FEDERAL_REGISTER_API_URL,
        "license_tier": OFFICIAL_POLICY_LICENSE_TIER,
        "attribution": OFFICIAL_POLICY_ATTRIBUTION,
        "retrieved_at": observed_at.isoformat(),
        "records": records,
    }
    return {
        "artifact_type": "external_context_official_source_poc",
        "schema_version": FEDERAL_REGISTER_POC_VERSION,
        "source": "federal_register_policy_metadata",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "terms": list(terms),
        "query_evidence": query_evidence,
        "record_count": len(records),
        "relevance_exclusion_counts": dict(sorted(relevance_exclusion_counts.items())),
        "publication_time_resolution": "calendar_day_conservative_end_of_new_york_day",
        "document_body_downloaded": False,
        "checkpoint_root": str(resolved_checkpoint_root) if resolved_checkpoint_root is not None else None,
        "pilot_input": pilot_input,
        "sample_digest": _canonical_hash(pilot_input),
        "v3_signal_changed": False,
    }
