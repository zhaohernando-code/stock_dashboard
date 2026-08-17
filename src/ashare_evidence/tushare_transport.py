from __future__ import annotations

import http.client
import json
from typing import Any
from urllib import error, parse, request

from ashare_evidence.http_client import urlopen

DEFAULT_TUSHARE_BASE_URL = "https://api.tushare.pro"
_LEGACY_TUSHARE_BASE_URL = "http://api.tushare.pro"


def secure_tushare_base_url(base_url: str | None) -> str:
    normalized = (base_url or DEFAULT_TUSHARE_BASE_URL).strip().rstrip("/")
    if normalized == _LEGACY_TUSHARE_BASE_URL:
        normalized = DEFAULT_TUSHARE_BASE_URL
    parsed = parse.urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.tushare.pro"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Tushare credentials may only be sent to the official HTTPS API endpoint")
    return DEFAULT_TUSHARE_BASE_URL


def post_tushare(
    *,
    base_url: str,
    token: str,
    api_name: str,
    params: dict[str, Any],
    fields: str | None = None,
    timeout_seconds: float = 8.0,
) -> dict[str, Any] | None:
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields or "",
    }
    req = request.Request(
        url=secure_tushare_base_url(base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=max(1, int(timeout_seconds))) as response:
            body = response.read()
    except (error.URLError, http.client.IncompleteRead, TimeoutError, OSError, ValueError):
        return None

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


__all__ = ["DEFAULT_TUSHARE_BASE_URL", "post_tushare", "secure_tushare_base_url"]
