from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

BOARD_RULES: dict[str, dict[str, Any]] = {
    "main": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 100, "limit_pct": 0.10, "label": "主板"},
    "star": {"lot": 200, "min_order_quantity": 200, "quantity_increment": 1, "limit_pct": 0.20, "label": "科创板"},
    "chnext": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 100, "limit_pct": 0.20, "label": "创业板"},
    "bse": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 1, "limit_pct": 0.30, "label": "北交所"},
    "st": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 100, "limit_pct": 0.05, "label": "ST/风险警示"},
}

ACCOUNT_PROFILE_UNRESTRICTED = "unrestricted"
ACCOUNT_PROFILE_NEW_RETAIL_CASH = "new_retail_cash_account"

ACCOUNT_PROFILE_LABELS = {
    ACCOUNT_PROFILE_UNRESTRICTED: "不按账户权限过滤",
    ACCOUNT_PROFILE_NEW_RETAIL_CASH: "新开户普通现金账户",
}

ACCOUNT_PROFILE_ALLOWED_BOARDS = {
    ACCOUNT_PROFILE_UNRESTRICTED: {"main", "star", "chnext", "bse", "st"},
    ACCOUNT_PROFILE_NEW_RETAIL_CASH: {"main"},
}

BOARD_PERMISSION_NOTES = {
    "star": "科创板通常需要开通权限，个人投资者需满足资产与24个月交易经验等适当性要求。",
    "chnext": "创业板新增个人投资者通常需要前20个交易日日均资产10万元并具备24个月交易经验。",
    "bse": "北交所个人投资者通常需要开通权限，满足资产与24个月交易经验等适当性要求。",
    "st": "ST/退市风险类标的属于高风险交易范围，保守新开户口径不纳入策略可执行池。",
}


def _profile_value(stock_profile: Any, key: str) -> Any:
    if stock_profile is None:
        return None
    if isinstance(stock_profile, dict):
        return stock_profile.get(key)
    return getattr(stock_profile, key, None)


def _payload_value(stock_profile: Any, *keys: str) -> Any:
    payload = _profile_value(stock_profile, "profile_payload")
    if not isinstance(payload, dict):
        payload = stock_profile if isinstance(stock_profile, dict) else {}
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return payload[key]
    return None


def _listed_date(stock_profile: Any) -> date | None:
    value = _profile_value(stock_profile, "listed_date") or _payload_value(stock_profile, "listed_date", "list_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        cleaned = value.strip()
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
    return None


def _business_day_distance(start: date, end: date) -> int:
    if start > end:
        return 0
    cursor = start
    count = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def _infer_board(symbol: str, stock_profile: Any = None) -> tuple[str, str]:
    ticker = symbol.split(".", 1)[0]
    raw_board = str(_payload_value(stock_profile, "board", "market_board", "board_name") or "").lower()
    raw_name = str(_profile_value(stock_profile, "name") or _payload_value(stock_profile, "name", "stock_name") or "")
    is_st = bool(_payload_value(stock_profile, "is_st", "st")) or "st" in raw_name.lower() or raw_name.startswith(("*ST", "ST"))
    if is_st:
        return "st", "profile_st_flag"
    if any(token in raw_board for token in ("科创", "star", "sse star")) or ticker.startswith("688"):
        return "star", "profile_or_prefix"
    if any(token in raw_board for token in ("创业", "chinext", "创业板")) or ticker.startswith(("300", "301")):
        return "chnext", "profile_or_prefix"
    if any(token in raw_board for token in ("北交", "bse", "北证")) or ticker.startswith(("8", "4")):
        return "bse", "profile_or_prefix"
    if raw_board or ticker.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "main", "profile_or_prefix"
    return "main", "wip_unknown"


def board_rule(
    symbol: str,
    *,
    stock_profile: Any = None,
    as_of: date | datetime | None = None,
) -> dict[str, Any]:
    board_id, source = _infer_board(symbol, stock_profile)
    rule = dict(BOARD_RULES[board_id])
    rule["board"] = board_id
    rule["rule_source"] = source
    rule["rule_status"] = "verified" if source != "wip_unknown" else "wip_unknown"
    listed = _listed_date(stock_profile)
    as_of_day = as_of.date() if isinstance(as_of, datetime) else as_of
    if listed is not None and as_of_day is not None:
        trading_day_index = _business_day_distance(listed, as_of_day)
        if 1 <= trading_day_index <= 5:
            rule["limit_pct"] = None
            rule["new_listing_no_limit"] = True
            rule["new_listing_trading_day_index"] = trading_day_index
        else:
            rule["new_listing_no_limit"] = False
            rule["new_listing_trading_day_index"] = trading_day_index
    else:
        rule["new_listing_no_limit"] = False
        rule["new_listing_trading_day_index"] = None
    return rule


def account_trade_eligibility(
    symbol: str,
    *,
    stock_profile: Any = None,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    as_of: date | datetime | None = None,
) -> dict[str, Any]:
    normalized_profile = account_profile if account_profile in ACCOUNT_PROFILE_ALLOWED_BOARDS else ACCOUNT_PROFILE_NEW_RETAIL_CASH
    rule = board_rule(symbol, stock_profile=stock_profile, as_of=as_of)
    board = str(rule["board"])
    allowed = board in ACCOUNT_PROFILE_ALLOWED_BOARDS[normalized_profile]
    return {
        "account_profile": normalized_profile,
        "account_profile_label": ACCOUNT_PROFILE_LABELS[normalized_profile],
        "tradable": allowed,
        "board": board,
        "board_label": rule["label"],
        "reason": "eligible_for_account_profile" if allowed else BOARD_PERMISSION_NOTES.get(board, "账户权限不覆盖该板块。"),
        "rule": rule,
    }


def account_eligibility_summary(
    series_by_symbol: dict[str, Any],
    *,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
) -> dict[str, Any]:
    normalized_profile = account_profile if account_profile in ACCOUNT_PROFILE_ALLOWED_BOARDS else ACCOUNT_PROFILE_NEW_RETAIL_CASH
    by_board: dict[str, int] = {}
    excluded_by_board: dict[str, int] = {}
    included = 0
    excluded = 0
    for symbol, series in series_by_symbol.items():
        name = getattr(series, "name", "")
        eligibility = account_trade_eligibility(symbol, stock_profile={"name": name}, account_profile=normalized_profile)
        board = str(eligibility["board"])
        by_board[board] = by_board.get(board, 0) + 1
        if eligibility["tradable"]:
            included += 1
        else:
            excluded += 1
            excluded_by_board[board] = excluded_by_board.get(board, 0) + 1
    return {
        "account_profile": normalized_profile,
        "account_profile_label": ACCOUNT_PROFILE_LABELS[normalized_profile],
        "included_series_count": included,
        "excluded_series_count": excluded,
        "board_counts": by_board,
        "excluded_board_counts": excluded_by_board,
        "rule_note": "新开户普通现金账户口径仅纳入沪深主板普通A股；排除科创板、创业板、北交所、ST/退市风险类标的。",
    }


def filter_account_eligible_series(
    series_by_symbol: dict[str, Any],
    *,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    include_index_symbols: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    include_index_symbols = include_index_symbols or set()
    filtered: dict[str, Any] = {}
    excluded_examples: list[dict[str, Any]] = []
    for symbol, series in series_by_symbol.items():
        if symbol in include_index_symbols:
            filtered[symbol] = series
            continue
        eligibility = account_trade_eligibility(
            symbol,
            stock_profile={"name": getattr(series, "name", "")},
            account_profile=account_profile,
        )
        if eligibility["tradable"]:
            filtered[symbol] = series
        elif len(excluded_examples) < 12:
            excluded_examples.append(
                {
                    "symbol": symbol,
                    "name": getattr(series, "name", ""),
                    "board_label": eligibility["board_label"],
                    "reason": eligibility["reason"],
                }
            )
    summary = account_eligibility_summary(
        {symbol: series for symbol, series in series_by_symbol.items() if symbol not in include_index_symbols},
        account_profile=account_profile,
    )
    summary["excluded_examples"] = excluded_examples
    return filtered, summary
