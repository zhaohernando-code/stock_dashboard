from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any
from urllib import error, request

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import ProviderCredential

TUSHARE_STOCK_BASIC_FIELDS = "ts_code,symbol,name,industry,list_date"
DEFAULT_TUSHARE_BASE_URL = "http://api.tushare.pro"


@dataclass(frozen=True)
class StockProfileResolution:
    symbol: str
    name: str | None
    industry: str | None
    listed_date: date | None
    template_key: str | None
    source: str


LOCAL_STOCK_MASTER_OVERRIDES: dict[str, dict[str, Any]] = {
    "002028.SZ": {
        "name": "思源电气",
        "industry": "电力设备",
        "listed_date": date(2004, 8, 5),
        "template_key": "power_equipment",
    },
    "688981.SH": {
        "name": "中芯国际",
        "industry": "半导体",
        "listed_date": date(2020, 7, 16),
        "template_key": "electronics",
    },
}

INDUSTRY_TEMPLATE_RULES: tuple[tuple[str, str], ...] = (
    ("白酒", "food_beverage"),
    ("食品饮料", "food_beverage"),
    ("消费", "food_beverage"),
    ("电力设备", "power_equipment"),
    ("电气设备", "power_equipment"),
    ("电源设备", "power_equipment"),
    ("储能", "power_equipment"),
    ("锂电", "power_equipment"),
    ("保险", "nonbank_finance"),
    ("证券", "nonbank_finance"),
    ("非银", "nonbank_finance"),
    ("金融", "nonbank_finance"),
    ("半导体", "electronics"),
    ("电子", "electronics"),
    ("芯片", "electronics"),
    ("汽车", "auto"),
    ("整车", "auto"),
    ("新能源车", "auto"),
    ("医药", "pharmaceutical"),
    ("生物", "pharmaceutical"),
    ("创新药", "pharmaceutical"),
)


def _parse_list_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    value = raw.strip()
    if len(value) != 8 or not value.isdigit():
        return None
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def _infer_template_key(industry: str | None) -> str | None:
    if not industry:
        return None
    normalized = industry.strip()
    for keyword, template_key in INDUSTRY_TEMPLATE_RULES:
        if keyword in normalized:
            return template_key
    return None


def _tushare_credential(session: Session) -> ProviderCredential | None:
    return session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )


def _post_tushare(
    *,
    base_url: str,
    token: str,
    api_name: str,
    params: dict[str, Any],
    fields: str,
) -> dict[str, Any] | None:
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields,
    }
    req = request.Request(
        url=base_url.rstrip("/"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            body = response.read()
    except (error.URLError, TimeoutError, OSError, ValueError):
        return None

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload or payload.get("code") not in {0, None}:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, list) or len(first) != len(fields):
        return None
    return dict(zip(fields, first, strict=False))


def _query_tushare_stock_basic(session: Session, symbol: str) -> dict[str, Any] | None:
    credential = _tushare_credential(session)
    if credential is None or not credential.access_token:
        return None

    base_url = credential.base_url.strip() if credential.base_url else DEFAULT_TUSHARE_BASE_URL
    token = credential.access_token.strip()
    response = _post_tushare(
        base_url=base_url,
        token=token,
        api_name="stock_basic",
        params={"ts_code": symbol, "list_status": "L"},
        fields=TUSHARE_STOCK_BASIC_FIELDS,
    )
    row = _first_row(response)
    if row is not None:
        return row

    fallback = _post_tushare(
        base_url=base_url,
        token=token,
        api_name="stock_basic",
        params={"ts_code": symbol},
        fields=TUSHARE_STOCK_BASIC_FIELDS,
    )
    return _first_row(fallback)


def resolve_stock_profile(
    session: Session,
    *,
    symbol: str,
    preferred_name: str | None = None,
) -> StockProfileResolution:
    cleaned_name = preferred_name.strip() if preferred_name and preferred_name.strip() else None

    local = LOCAL_STOCK_MASTER_OVERRIDES.get(symbol)
    if local is not None:
        return StockProfileResolution(
            symbol=symbol,
            name=cleaned_name or local["name"],
            industry=local.get("industry"),
            listed_date=local.get("listed_date"),
            template_key=local.get("template_key"),
            source="local_override",
        )

    tushare_row = _query_tushare_stock_basic(session, symbol)
    if tushare_row is not None:
        industry = tushare_row.get("industry")
        name = cleaned_name or tushare_row.get("name")
        return StockProfileResolution(
            symbol=symbol,
            name=name.strip() if isinstance(name, str) and name.strip() else None,
            industry=industry.strip() if isinstance(industry, str) and industry.strip() else None,
            listed_date=_parse_list_date(tushare_row.get("list_date")),
            template_key=_infer_template_key(industry if isinstance(industry, str) else None),
            source="tushare_stock_basic",
        )

    return StockProfileResolution(
        symbol=symbol,
        name=cleaned_name,
        industry=None,
        listed_date=None,
        template_key=None,
        source="user_input" if cleaned_name else "unresolved",
    )
