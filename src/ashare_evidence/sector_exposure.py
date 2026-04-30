from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.dashboard import list_candidate_recommendations


def build_sector_exposure(session: Session) -> dict[str, Any]:
    candidates = list_candidate_recommendations(session, limit=20)
    items = candidates.get("items", [])
    sectors: dict[str, dict[str, Any]] = {}
    total_count = 0
    for item in items:
        sector_tags = item.get("sector_tags", [])
        if not sector_tags and item.get("sector"):
            sector_tags = [item["sector"]]
        for sector in sector_tags:
            entry = sectors.setdefault(sector, {"count": 0, "symbols": [], "directions": []})
            entry["count"] += 1
            entry["symbols"].append(item.get("symbol", "?"))
            entry["directions"].append(item.get("display_direction_label", item.get("direction_label", "?")))
            total_count += 1
    result: dict[str, Any] = {
        "total_candidates": len(items),
        "sector_count": len(sectors),
        "sectors": {},
    }
    for sector, data in sorted(sectors.items(), key=lambda x: x[1]["count"], reverse=True):
        buy_count = sum(1 for d in data["directions"] if d in ("可建仓", "可加仓"))
        watch_count = sum(1 for d in data["directions"] if d == "继续观察")
        result["sectors"][sector] = {
            "count": data["count"],
            "buy_ratio": round(buy_count / data["count"], 3) if data["count"] else 0,
            "watch_ratio": round(watch_count / data["count"], 3) if data["count"] else 0,
            "symbols": data["symbols"],
        }
    return result
