from __future__ import annotations

from typing import Any

BOARD_RULES: dict[str, dict[str, Any]] = {
    "main": {"lot": 100, "limit_pct": 0.10, "label": "主板"},
    "star": {"lot": 200, "limit_pct": 0.20, "label": "科创板"},
    "chnext": {"lot": 100, "limit_pct": 0.20, "label": "创业板"},
    "bse": {"lot": 100, "limit_pct": 0.30, "label": "北交所"},
    "st": {"lot": 100, "limit_pct": 0.05, "label": "ST/风险警示"},
}


def board_rule(symbol: str) -> dict[str, Any]:
    if symbol.startswith("688"):
        return BOARD_RULES["star"]
    if symbol.startswith("300") or symbol.startswith("301"):
        return BOARD_RULES["chnext"]
    if symbol.startswith("8") or symbol.startswith("4"):
        return BOARD_RULES["bse"]
    if "ST" in symbol.upper():
        return BOARD_RULES["st"]
    return BOARD_RULES["main"]
