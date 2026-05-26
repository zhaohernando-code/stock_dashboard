from __future__ import annotations

import re
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from ashare_evidence.db import utcnow
from ashare_evidence.http_client import urlopen

SHORTPICK_SOURCE_CHECK_TIMEOUT_SECONDS = 3
SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS = 2

SUSPICIOUS_SOURCE_PATTERNS = (
    re.compile(r"(?:123456|234567|345678|456789|987654|876543)"),
    re.compile(r"(.)\1{5,}"),
    re.compile(r"(?:xxxx|abc123|example|placeholder|dummy)", re.IGNORECASE),
)


def source_credibility(url: str | None) -> dict[str, Any]:
    normalized = (url or "").strip()
    checked_at = utcnow().isoformat()
    authority_class = source_authority_class(normalized)
    if not normalized:
        return {
            "credibility_status": "missing_url",
            "credibility_reason": "source omitted url",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "invalid url format",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    if looks_like_placeholder_url(normalized):
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "placeholder-like url pattern",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    if parsed.hostname and parsed.hostname.endswith(".example"):
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "reserved example domain",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    result = probe_source_url(normalized, checked_at=checked_at)
    result["authority_class"] = authority_class
    return result


def source_authority_class(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return "aggregator_or_unknown"
    if hostname.endswith(("sse.com.cn", "szse.cn", "bse.cn", "cninfo.com.cn")):
        return "exchange_or_company_disclosure"
    if hostname.endswith(("cs.com.cn", "stcn.com", "cnstock.com", "zqrb.cn")):
        return "designated_disclosure_media"
    if hostname.endswith(("eastmoney.com", "hexun.com", "cls.cn", "yicai.com", "21jingji.com", "caixin.com")):
        return "mainstream_financial_media"
    if hostname.endswith(("mysteel.com", "smm.cn", "cinn.cn", "ofweek.com", "gg-lb.com")):
        return "vertical_industry_media"
    if hostname.endswith(("pdf.dfcfw.com", "research.cicc.com", "cmschina.com")):
        return "broker_research_or_pdf"
    if hostname.endswith(("xueqiu.com", "guba.eastmoney.com", "weibo.com")):
        return "community_or_forum"
    return "aggregator_or_unknown"


def source_support_check(
    source: dict[str, Any],
    *,
    theme: str | None,
    thesis: str | None,
    catalysts: list[str],
) -> dict[str, Any]:
    source_text = " ".join(
        item
        for item in [
            coerce_text(source.get("title")),
            coerce_text(source.get("why_it_matters")),
            coerce_text(source.get("url")),
        ]
        if item
    )
    claim_text = " ".join(item for item in [theme, thesis, *catalysts] if item)
    source_terms = support_terms(source_text)
    claim_terms = support_terms(claim_text)
    overlap = sorted(source_terms & claim_terms)
    if overlap:
        return {
            "support_status": "supported_by_source_text",
            "support_evidence_terms": overlap[:12],
        }
    return {
        "support_status": "weak_or_unverified_source_support",
        "support_evidence_terms": [],
    }


def support_terms(text: str) -> set[str]:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text.lower())
    terms = {item for item in normalized.split() if len(item) >= 2}
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    for phrase in chinese:
        terms.add(phrase)
        terms.update(phrase[index : index + 2] for index in range(max(len(phrase) - 1, 0)))
        terms.update(phrase[index : index + 3] for index in range(max(len(phrase) - 2, 0)))
    return terms


def looks_like_placeholder_url(url: str) -> bool:
    return any(pattern.search(url) for pattern in SUSPICIOUS_SOURCE_PATTERNS)


def probe_source_url(url: str, *, checked_at: str) -> dict[str, Any]:
    for method in ("HEAD", "GET"):
        for attempt in range(1, SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS + 1):
            http_request = request.Request(
                url,
                headers={
                    "User-Agent": "ashare-shortpick-lab-source-check/1.0",
                    **({"Range": "bytes=0-0"} if method == "GET" else {}),
                },
                method=method,
            )
            try:
                with urlopen(
                    http_request,
                    timeout=SHORTPICK_SOURCE_CHECK_TIMEOUT_SECONDS,
                    disable_proxies=True,
                ) as response:
                    status = int(getattr(response, "status", 200) or 200)
                return {
                    "credibility_status": "verified" if status < 400 else "unreachable",
                    "credibility_reason": f"{method} HTTP {status}",
                    "http_status": status,
                    "attempt_count": attempt,
                    "checked_at": checked_at,
                }
            except HTTPError as exc:
                if method == "HEAD" and exc.code in {403, 405}:
                    break
                if exc.code in {401, 403}:
                    return {
                        "credibility_status": "reachable_restricted",
                        "credibility_reason": f"{method} HTTP {exc.code}",
                        "http_status": exc.code,
                        "attempt_count": attempt,
                        "checked_at": checked_at,
                    }
                return {
                    "credibility_status": "unreachable",
                    "credibility_reason": f"{method} HTTP {exc.code}",
                    "http_status": exc.code,
                    "attempt_count": attempt,
                    "checked_at": checked_at,
                }
            except (TimeoutError, URLError, OSError) as exc:
                if attempt < SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS:
                    continue
                if method == "HEAD":
                    break
                return {
                    "credibility_status": "unreachable",
                    "credibility_reason": str(getattr(exc, "reason", exc))[:160],
                    "attempt_count": attempt,
                    "checked_at": checked_at,
                }
    return {
        "credibility_status": "unchecked",
        "credibility_reason": "source check skipped",
        "attempt_count": SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS,
        "checked_at": checked_at,
    }


def host_from_url(url: str) -> str:
    stripped = url.replace("https://", "").replace("http://", "")
    return stripped.split("/", 1)[0].lower()


def coerce_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
