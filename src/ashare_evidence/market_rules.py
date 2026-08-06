from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

BOARD_RULES: dict[str, dict[str, Any]] = {
    "main": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 100, "limit_pct": 0.10, "label": "主板"},
    "star": {"lot": 200, "min_order_quantity": 200, "quantity_increment": 1, "limit_pct": 0.20, "label": "科创板"},
    "chnext": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 100, "limit_pct": 0.20, "label": "创业板"},
    "bse": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 1, "limit_pct": 0.30, "label": "北交所"},
    "st": {"lot": 100, "min_order_quantity": 100, "quantity_increment": 100, "limit_pct": 0.05, "label": "ST/风险警示"},
    "unknown": {
        "lot": 100,
        "min_order_quantity": 100,
        "quantity_increment": 100,
        "limit_pct": None,
        "label": "非A股或未知证券",
    },
}

ACCOUNT_PROFILE_UNRESTRICTED = "unrestricted"
ACCOUNT_PROFILE_NEW_RETAIL_CASH = "new_retail_cash_account"
ACCOUNT_ELIGIBILITY_SNAPSHOT_VERSION = "account_trade_eligibility_snapshot.v1"
NEW_RETAIL_MAX_UNADJUSTED_PRICE_CNY = 200.0

ACCOUNT_PROFILE_LABELS = {
    ACCOUNT_PROFILE_UNRESTRICTED: "不按账户权限过滤",
    ACCOUNT_PROFILE_NEW_RETAIL_CASH: "新开户普通现金账户",
}

ACCOUNT_PROFILE_ALLOWED_BOARDS = {
    ACCOUNT_PROFILE_UNRESTRICTED: {"main", "star", "chnext", "bse", "st"},
    ACCOUNT_PROFILE_NEW_RETAIL_CASH: {"main"},
}

ACCOUNT_PROFILE_SPECS: dict[str, dict[str, Any]] = {
    ACCOUNT_PROFILE_UNRESTRICTED: {
        "allowed_boards": sorted(ACCOUNT_PROFILE_ALLOWED_BOARDS[ACCOUNT_PROFILE_UNRESTRICTED]),
        "a_share_only": True,
        "max_unadjusted_price_cny": None,
        "allow_risk_warning": True,
        "allow_delisting": False,
        "permission_basis": "research_control_not_a_broker_permission_claim",
    },
    ACCOUNT_PROFILE_NEW_RETAIL_CASH: {
        "allowed_boards": sorted(ACCOUNT_PROFILE_ALLOWED_BOARDS[ACCOUNT_PROFILE_NEW_RETAIL_CASH]),
        "a_share_only": True,
        "max_unadjusted_price_cny": NEW_RETAIL_MAX_UNADJUSTED_PRICE_CNY,
        "allow_risk_warning": False,
        "allow_delisting": False,
        "permission_basis": "conservative_default_until_broker_permissions_are_confirmed",
    },
}

BOARD_PERMISSION_NOTES = {
    "star": "科创板通常需要开通权限，个人投资者需满足资产与24个月交易经验等适当性要求。",
    "chnext": "创业板新增个人投资者通常需要前20个交易日日均资产10万元并具备24个月交易经验。",
    "bse": "北交所个人投资者通常需要开通权限，满足资产与24个月交易经验等适当性要求。",
    "st": "ST/退市风险类标的属于高风险交易范围，保守新开户口径不纳入策略可执行池。",
}

ELIGIBILITY_REASON_MESSAGES = {
    "non_a_share_security": "仅允许A股，当前证券代码或交易所不属于A股范围。",
    "account_board_permission_required": "当前账户配置未开通该板块交易权限。",
    "risk_warning_not_allowed": "当前账户配置不买入ST或其他风险警示股票。",
    "delisting_or_inactive_security": "当前证券处于退市、终止上市或非正常上市状态。",
    "missing_unadjusted_price": "缺少决策时点可得的未复权成交价格。",
    "non_positive_price": "决策时点价格无效。",
    "price_not_available_at_decision_cutoff": "价格记录晚于决策截止时点，不能用于本次筛选。",
    "price_adjustment_not_unadjusted": "价格不是未复权可成交口径。",
    "price_above_profile_maximum": "决策时点未复权价格高于账户配置上限。",
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


def _symbol_exchange(symbol: str) -> tuple[str, str]:
    ticker, _, exchange = str(symbol or "").upper().partition(".")
    normalized_exchange = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange, exchange)
    return ticker, normalized_exchange


def _infer_security_scope(symbol: str) -> tuple[str, str]:
    ticker, exchange = _symbol_exchange(symbol)
    if exchange == "SH" and ticker.startswith("900"):
        return "b_share", "exchange_and_prefix"
    if exchange == "SZ" and ticker.startswith("200"):
        return "b_share", "exchange_and_prefix"
    if exchange == "SH" and ticker.startswith(("600", "601", "603", "605", "688", "689")):
        return "a_share", "exchange_and_prefix"
    if exchange == "SZ" and ticker.startswith(("000", "001", "002", "003", "300", "301")):
        return "a_share", "exchange_and_prefix"
    if exchange == "BJ" and ticker.startswith(("4", "8", "920")):
        return "a_share", "exchange_and_prefix"
    return "unknown", "unrecognized_symbol_scope"


def _infer_board(symbol: str, stock_profile: Any = None) -> tuple[str, str]:
    ticker = symbol.split(".", 1)[0]
    _, exchange = _symbol_exchange(symbol)
    raw_board = str(_payload_value(stock_profile, "board", "market_board", "board_name") or "").lower()
    raw_name = str(_profile_value(stock_profile, "name") or _payload_value(stock_profile, "name", "stock_name") or "")
    is_st = bool(_payload_value(stock_profile, "is_st", "st")) or "st" in raw_name.lower() or raw_name.startswith(("*ST", "ST"))
    if is_st:
        return "st", "profile_st_flag"
    if any(token in raw_board for token in ("科创", "star", "sse star")) or (
        exchange == "SH" and ticker.startswith(("688", "689"))
    ):
        return "star", "profile_or_prefix"
    if any(token in raw_board for token in ("创业", "chinext", "创业板")) or (
        exchange == "SZ" and ticker.startswith(("300", "301"))
    ):
        return "chnext", "profile_or_prefix"
    if any(token in raw_board for token in ("北交", "bse", "北证")) or exchange == "BJ" or ticker.startswith(
        ("8", "4", "920")
    ):
        return "bse", "profile_or_prefix"
    security_scope, _ = _infer_security_scope(symbol)
    if security_scope == "a_share" and (
        raw_board or ticker.startswith(("000", "001", "002", "003", "600", "601", "603", "605"))
    ):
        return "main", "profile_or_prefix"
    return "unknown", "wip_unknown"


def board_rule(
    symbol: str,
    *,
    stock_profile: Any = None,
    as_of: date | datetime | None = None,
) -> dict[str, Any]:
    board_id, source = _infer_board(symbol, stock_profile)
    rule = dict(BOARD_RULES.get(board_id, BOARD_RULES["unknown"]))
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
    profile_is_point_in_time: bool = True,
) -> dict[str, Any]:
    normalized_profile = account_profile if account_profile in ACCOUNT_PROFILE_ALLOWED_BOARDS else ACCOUNT_PROFILE_NEW_RETAIL_CASH
    effective_profile = stock_profile
    if not profile_is_point_in_time:
        # Historical decisions may use stable code/exchange inference, but must not
        # backfill today's name, status, or board labels into an earlier decision.
        effective_profile = {}
    rule = board_rule(symbol, stock_profile=effective_profile, as_of=as_of)
    board = str(rule["board"])
    security_scope, security_scope_source = _infer_security_scope(symbol)
    spec = ACCOUNT_PROFILE_SPECS[normalized_profile]
    reasons: list[str] = []
    if spec["a_share_only"] and security_scope != "a_share":
        reasons.append("non_a_share_security")
    if board not in ACCOUNT_PROFILE_ALLOWED_BOARDS[normalized_profile]:
        reasons.append("risk_warning_not_allowed" if board == "st" else "account_board_permission_required")
    status = str(_profile_value(stock_profile, "status") or _payload_value(stock_profile, "list_status") or "").lower()
    delisted_date = _profile_value(stock_profile, "delisted_date")
    as_of_day = as_of.date() if isinstance(as_of, datetime) else as_of
    delisted = bool(status and status not in {"active", "l"})
    if isinstance(delisted_date, datetime):
        delisted_date = delisted_date.date()
    if isinstance(delisted_date, date) and as_of_day is not None and delisted_date <= as_of_day:
        delisted = True
    if delisted and not spec["allow_delisting"] and profile_is_point_in_time:
        reasons.append("delisting_or_inactive_security")
    allowed = not reasons
    return {
        "account_profile": normalized_profile,
        "account_profile_label": ACCOUNT_PROFILE_LABELS[normalized_profile],
        "account_profile_spec": spec,
        "tradable": allowed,
        "board": board,
        "board_label": rule["label"],
        "security_scope": security_scope,
        "security_scope_source": security_scope_source,
        "reason_codes": reasons,
        "reason": (
            "eligible_for_account_profile"
            if allowed
            else ELIGIBILITY_REASON_MESSAGES.get(reasons[0], BOARD_PERMISSION_NOTES.get(board, "账户权限不覆盖该板块。"))
        ),
        "pit_risk_status_verified": profile_is_point_in_time,
        "rule": rule,
    }


def _coerce_datetime(value: date | datetime | str | None, *, end_of_day: bool = False) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        time_value = datetime.max.time() if end_of_day else datetime.min.time()
        return datetime.combine(value, time_value)
    if isinstance(value, str) and value.strip():
        cleaned = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        return parsed
    return None


def build_trade_eligibility_snapshot(
    symbol: str,
    *,
    stock_profile: Any = None,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    as_of: date | datetime,
    decision_cutoff: date | datetime | str | None,
    price_cny: float | None,
    price_observed_at: date | datetime | str | None,
    price_source: str,
    price_adjustment: str,
    profile_is_point_in_time: bool = True,
) -> dict[str, Any]:
    """Build the single pre-ranking account/price eligibility record used by live and replay paths."""

    normalized_profile = account_profile if account_profile in ACCOUNT_PROFILE_SPECS else ACCOUNT_PROFILE_NEW_RETAIL_CASH
    structural = account_trade_eligibility(
        symbol,
        stock_profile=stock_profile,
        account_profile=normalized_profile,
        as_of=as_of,
        profile_is_point_in_time=profile_is_point_in_time,
    )
    spec = ACCOUNT_PROFILE_SPECS[normalized_profile]
    reason_codes = list(structural["reason_codes"])
    observed_at = _coerce_datetime(price_observed_at)
    cutoff = _coerce_datetime(decision_cutoff or as_of, end_of_day=True)
    numeric_price = None if price_cny is None else float(price_cny)
    if numeric_price is None:
        reason_codes.append("missing_unadjusted_price")
    elif numeric_price <= 0:
        reason_codes.append("non_positive_price")
    if price_adjustment != "unadjusted":
        reason_codes.append("price_adjustment_not_unadjusted")
    if observed_at is None:
        reason_codes.append("missing_unadjusted_price")
    elif cutoff is not None:
        observed_cmp = observed_at
        cutoff_cmp = cutoff
        if observed_cmp.tzinfo is not None and cutoff_cmp.tzinfo is None:
            cutoff_cmp = cutoff_cmp.replace(tzinfo=observed_cmp.tzinfo)
        elif observed_cmp.tzinfo is None and cutoff_cmp.tzinfo is not None:
            observed_cmp = observed_cmp.replace(tzinfo=cutoff_cmp.tzinfo)
        if observed_cmp > cutoff_cmp:
            reason_codes.append("price_not_available_at_decision_cutoff")
    maximum = spec["max_unadjusted_price_cny"]
    if numeric_price is not None and maximum is not None and numeric_price > float(maximum):
        reason_codes.append("price_above_profile_maximum")
    reason_codes = list(dict.fromkeys(reason_codes))
    reason_details = [
        {"code": code, "message": ELIGIBILITY_REASON_MESSAGES.get(code, code)} for code in reason_codes
    ]
    warnings = []
    if not profile_is_point_in_time:
        warnings.append("pit_risk_status_unverified_current_static_name_not_used")
    payload = {
        "snapshot_version": ACCOUNT_ELIGIBILITY_SNAPSHOT_VERSION,
        "account_profile": normalized_profile,
        "account_profile_label": ACCOUNT_PROFILE_LABELS[normalized_profile],
        "account_profile_spec": spec,
        "symbol": str(symbol).upper(),
        "as_of": as_of.isoformat(),
        "decision_cutoff": cutoff.isoformat() if cutoff is not None else None,
        "eligible_before_scoring": not reason_codes,
        "exclusion_reason_codes": reason_codes,
        "exclusion_reasons": reason_details,
        "board": structural["board"],
        "board_label": structural["board_label"],
        "security_scope": structural["security_scope"],
        "price": {
            "value_cny": numeric_price,
            "observed_at": observed_at.isoformat() if observed_at is not None else None,
            "source": price_source,
            "adjustment": price_adjustment,
            "maximum_cny": maximum,
        },
        "pit_risk_status_verified": profile_is_point_in_time,
        "warnings": warnings,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["snapshot_id"] = f"eligibility:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"
    return payload


def account_eligibility_summary(
    series_by_symbol: dict[str, Any],
    *,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    profile_is_point_in_time: bool = True,
) -> dict[str, Any]:
    normalized_profile = account_profile if account_profile in ACCOUNT_PROFILE_ALLOWED_BOARDS else ACCOUNT_PROFILE_NEW_RETAIL_CASH
    by_board: dict[str, int] = {}
    excluded_by_board: dict[str, int] = {}
    included = 0
    excluded = 0
    for symbol, series in series_by_symbol.items():
        name = getattr(series, "name", "")
        eligibility = account_trade_eligibility(
            symbol,
            stock_profile={"name": name},
            account_profile=normalized_profile,
            profile_is_point_in_time=profile_is_point_in_time,
        )
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
        "pit_risk_status_verified": profile_is_point_in_time,
        "rule_note": (
            "新开户普通现金账户口径仅纳入沪深主板普通A股；排除科创板、创业板、北交所、"
            f"ST/退市风险类标的；决策时点未复权价格不得高于 {NEW_RETAIL_MAX_UNADJUSTED_PRICE_CNY:.0f} 元。"
        ),
    }


def filter_account_eligible_series(
    series_by_symbol: dict[str, Any],
    *,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    include_index_symbols: set[str] | None = None,
    profile_is_point_in_time: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Filter historical series without treating today's stock name/status as historical fact."""
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
            profile_is_point_in_time=profile_is_point_in_time,
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
        profile_is_point_in_time=profile_is_point_in_time,
    )
    summary["excluded_examples"] = excluded_examples
    return filtered, summary


def summarize_trade_eligibility_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    excluded_examples: list[dict[str, Any]] = []
    eligible_count = 0
    for snapshot in snapshots:
        if snapshot.get("eligible_before_scoring"):
            eligible_count += 1
        else:
            for code in snapshot.get("exclusion_reason_codes") or []:
                reason_counts[str(code)] = reason_counts.get(str(code), 0) + 1
            if len(excluded_examples) < 12:
                excluded_examples.append(
                    {
                        "symbol": snapshot.get("symbol"),
                        "board": snapshot.get("board"),
                        "price_cny": (snapshot.get("price") or {}).get("value_cny"),
                        "reason_codes": snapshot.get("exclusion_reason_codes") or [],
                        "snapshot_id": snapshot.get("snapshot_id"),
                    }
                )
        for warning in snapshot.get("warnings") or []:
            warning_counts[str(warning)] = warning_counts.get(str(warning), 0) + 1
    return {
        "snapshot_version": ACCOUNT_ELIGIBILITY_SNAPSHOT_VERSION,
        "evaluated_count": len(snapshots),
        "eligible_before_scoring_count": eligible_count,
        "excluded_before_scoring_count": len(snapshots) - eligible_count,
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "excluded_examples": excluded_examples,
    }
