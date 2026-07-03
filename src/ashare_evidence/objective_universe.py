from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.research_artifact_store import write_research_validation_artifact

OBJECTIVE_UNIVERSE_SCHEMA_VERSION = "objective_frozen_universe.v1"
OBJECTIVE_UNIVERSE_RULE_VERSION = "db_market_bar_coverage_frozen_pre_validation:v1"


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_st_profile(stock: Stock) -> bool:
    profile = stock.profile_payload or {}
    name = str(stock.name or profile.get("name") or "")
    return bool(profile.get("is_st")) or name.upper().startswith(("ST", "*ST"))


def build_objective_universe_artifact(
    session: Session,
    *,
    validation_run_id: str,
    recommended_symbols: list[str],
) -> dict[str, Any]:
    stocks = list(session.scalars(select(Stock).order_by(Stock.symbol.asc(), Stock.id.asc())).all())
    rows = session.execute(
        select(
            MarketBar.stock_id,
            MarketBar.bar_key,
            MarketBar.observed_at,
            MarketBar.close_price,
            MarketBar.volume,
            MarketBar.amount,
        )
        .where(MarketBar.timeframe == "1d")
        .order_by(MarketBar.stock_id.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    bars_by_stock_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for stock_id, bar_key, observed_at, close_price, volume, amount in rows:
        bars_by_stock_id[int(stock_id)].append(
            {
                "bar_key": bar_key,
                "observed_at": observed_at.isoformat() if observed_at else None,
                "close_price": close_price,
                "volume": volume,
                "amount": amount,
            }
        )

    recommended_set = set(recommended_symbols)
    members: list[dict[str, Any]] = []
    for stock in stocks:
        symbol = str(stock.symbol)
        symbol_bars = bars_by_stock_id.get(int(stock.id), [])
        days = sorted(str(row["observed_at"] or "")[:10] for row in symbol_bars if row.get("observed_at"))
        exclusion_reasons: list[str] = []
        if stock.status != "active":
            exclusion_reasons.append("stock_status_not_active")
        if _is_st_profile(stock):
            exclusion_reasons.append("st_or_special_treatment")
        if len(symbol_bars) < 2:
            exclusion_reasons.append("insufficient_daily_bars")
        if stock.delisted_date is not None:
            exclusion_reasons.append("delisted")
        member = {
            "symbol": symbol,
            "stock_id": stock.id,
            "ticker": stock.ticker,
            "exchange": stock.exchange,
            "name": stock.name,
            "listed_date": stock.listed_date.isoformat() if stock.listed_date else None,
            "delisted_date": stock.delisted_date.isoformat() if stock.delisted_date else None,
            "stock_status": stock.status,
            "membership_status": "eligible" if not exclusion_reasons else "excluded",
            "exclusion_reasons": exclusion_reasons,
            "first_bar_date": days[0] if days else None,
            "last_bar_date": days[-1] if days else None,
            "daily_bar_count": len(symbol_bars),
            "bar_rows_digest": _stable_digest(symbol_bars),
            "has_recommendation_sample": symbol in recommended_set,
        }
        member["member_digest"] = _stable_digest(member)
        members.append(member)

    eligible_members = [member for member in members if member["membership_status"] == "eligible"]
    eligible_symbols = [str(member["symbol"]) for member in eligible_members]
    recommended_in_universe = sorted(symbol for symbol in recommended_set if symbol in set(eligible_symbols))
    universe_digest = _stable_digest(
        {
            "rule_version": OBJECTIVE_UNIVERSE_RULE_VERSION,
            "eligible_symbols": eligible_symbols,
            "members": members,
        }
    )
    artifact_id = f"objective-frozen-universe-{universe_digest[:16]}"
    return {
        "artifact_type": "objective_frozen_universe",
        "schema_version": OBJECTIVE_UNIVERSE_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": universe_digest[:16],
        "source_data_time_range": {
            "daily_bar_start": min((member["first_bar_date"] for member in members if member["first_bar_date"]), default=None),
            "daily_bar_end": max((member["last_bar_date"] for member in members if member["last_bar_date"]), default=None),
        },
        "feature_version": "not_applicable_universe_only",
        "label_version": "not_applicable_universe_only",
        "code_version": "unresolved_local_checkout",
        "config_version": OBJECTIVE_UNIVERSE_RULE_VERSION,
        "validation_protocol": {
            "artifact_role": "objective_frozen_universe",
            "universe_rule": OBJECTIVE_UNIVERSE_RULE_VERSION,
            "selection_timing": "frozen_before_validation",
            "winner_dependency_policy": "no_post_hoc_winner_selection",
            "watchlist_policy": "recommendation/watchlist sample may be measured only as coverage subset",
        },
        "gate_readout": {
            "gate_status": "universe_frozen" if eligible_members else "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "universe_definition_only",
            "blocking_gate_ids": [] if eligible_members else ["empty_objective_universe"],
        },
        "claim_ceiling": "universe_definition_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "universe_rule": OBJECTIVE_UNIVERSE_RULE_VERSION,
        "db_stock_count": len(stocks),
        "covered_symbol_count": sum(1 for member in members if member["daily_bar_count"] > 0),
        "eligible_symbol_count": len(eligible_members),
        "member_count": len(members),
        "recommended_symbol_count": len(recommended_set),
        "recommended_symbols_in_universe": recommended_in_universe,
        "recommendation_coverage_ratio": round(len(recommended_in_universe) / max(len(eligible_members), 1), 6),
        "universe_content_digest": universe_digest,
        "members": members,
    }


def objective_universe_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "schema_version": payload.get("schema_version"),
        "artifact_id": payload.get("artifact_id"),
        "universe_rule": payload.get("universe_rule"),
        "db_stock_count": payload.get("db_stock_count"),
        "covered_symbol_count": payload.get("covered_symbol_count"),
        "eligible_symbol_count": payload.get("eligible_symbol_count"),
        "recommended_symbol_count": payload.get("recommended_symbol_count"),
        "recommendation_coverage_ratio": payload.get("recommendation_coverage_ratio"),
        "storage_boundary": payload.get("storage_boundary"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
    }


def write_objective_universe_artifact(payload: dict[str, Any], *, artifact_root: str) -> Path:
    return write_research_validation_artifact(
        "objective_frozen_universe",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
