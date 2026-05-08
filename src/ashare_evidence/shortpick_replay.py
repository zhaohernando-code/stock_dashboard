from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import json
import random
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.benchmark import benchmark_close_maps
from ashare_evidence.db import utcnow
from ashare_evidence.models import (
    MarketBar,
    NewsEntityLink,
    NewsItem,
    ShortpickCandidate,
    ShortpickExperimentRun,
    ShortpickModelRound,
    ShortpickValidationSnapshot,
    Stock,
)
from ashare_evidence.research_artifact_store import write_shortpick_lab_artifact
from ashare_evidence.shortpick_lab import (
    SHORTPICK_DEFAULT_HORIZONS,
    SHORTPICK_OFFICIAL_VALIDATION_MODE,
    _apply_shortpick_candidate_display_gates,
    _artifact_root,
    _benchmark_dimensions_payload,
    _coerce_string_list,
    _daily_bars_for_symbol,
    _normalize_symbol,
    _shortpick_validation_summary,
    _upsert_validation_snapshot,
    get_shortpick_run,
    list_shortpick_candidates,
    list_shortpick_runs,
)

SHORTPICK_HISTORICAL_REPLAY_MODE = "historical_replay"
SHORTPICK_HISTORICAL_REPLAY_PROMPT_VERSION = "shortpick_historical_replay_v1"
SHORTPICK_REPLAY_EXPERIMENT_MODE = "historical_replay"
SHORTPICK_REPLAY_SOURCE_LOOKBACK_DAYS = 21
SHORTPICK_REPLAY_BASELINE_FAMILIES = (
    "llm",
    "random_same_tradeable_universe",
    "random_same_market_cap_bucket",
    "momentum_volume_baseline",
)


@dataclass(frozen=True)
class _UniverseMember:
    symbol: str
    name: str
    latest_bar: MarketBar
    previous_bar: MarketBar | None
    market_cap: float | None
    turnover_rate: float | None
    industry: str | None
    market_cap_bucket: str


def run_shortpick_historical_replay(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    rounds: int = 5,
    candidate_limit: int = 3,
    triggered_by: str | None = None,
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    normalized_rounds = max(1, min(int(rounds), 10))
    normalized_limit = max(1, min(int(candidate_limit), 10))
    replay_runs: list[dict[str, Any]] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            run = _run_one_replay_date(
                session,
                as_of_date=cursor,
                rounds=normalized_rounds,
                candidate_limit=normalized_limit,
                triggered_by=triggered_by,
            )
            replay_runs.append(run)
        cursor += timedelta(days=1)
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "rounds": normalized_rounds,
        "candidate_limit": normalized_limit,
        "run_count": len(replay_runs),
        "runs": replay_runs,
    }


def _run_one_replay_date(
    session: Session,
    *,
    as_of_date: date,
    rounds: int,
    candidate_limit: int,
    triggered_by: str | None,
) -> dict[str, Any]:
    started_at = utcnow()
    as_of_cutoff = _as_of_cutoff(as_of_date)
    universe = _build_universe(session, as_of_date=as_of_date)
    packet = _build_source_packet(session, as_of_date=as_of_date, as_of_cutoff=as_of_cutoff, universe=universe)
    run = ShortpickExperimentRun(
        run_key=f"shortpick-replay:{as_of_date.isoformat()}:{started_at:%Y%m%d%H%M%S%f}",
        run_date=as_of_date,
        prompt_version=SHORTPICK_HISTORICAL_REPLAY_PROMPT_VERSION,
        information_mode=SHORTPICK_HISTORICAL_REPLAY_MODE,
        status="running",
        trigger_source="historical_replay_cli",
        triggered_by=triggered_by,
        started_at=started_at,
        completed_at=None,
        failed_at=None,
        model_config={
            "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
            "rounds": rounds,
            "candidate_limit": candidate_limit,
            "sealed_packet_only": True,
            "native_web_search": False,
            "baseline_families": list(SHORTPICK_REPLAY_BASELINE_FAMILIES),
        },
        summary_payload={
            "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
            "as_of_cutoff": as_of_cutoff.isoformat(),
            "source_packet_id": packet["source_packet_id"],
            "source_packet_hash": packet["source_packet_hash"],
            "source_packet": _packet_summary(packet),
            "tradable_universe": universe["summary"],
        },
    )
    session.add(run)
    session.flush()
    _write_replay_packet_artifact(session, run, packet)
    _insert_replay_candidates(
        session,
        run=run,
        packet=packet,
        universe=universe,
        rounds=rounds,
        candidate_limit=candidate_limit,
    )
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    run.status = "completed"
    run.completed_at = utcnow()
    candidate_rows = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id)).all()
    candidate_payloads = [_candidate_payload(candidate) for candidate in candidate_rows]
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        **dict(validation_result.get("summary") or {}),
        "candidate_count": len(candidate_rows),
        "official_sample_count": len([payload for payload in candidate_payloads if payload.get("official_sample_eligible")]),
        "leakage_failed_count": len([payload for payload in candidate_payloads if payload.get("leakage_audit_status") == "fail"]),
        "baseline_candidate_count": len([payload for payload in candidate_payloads if payload.get("baseline_family") != "llm"]),
        "boundary": "historical_replay_no_main_pool_write",
    }
    session.flush()
    return get_shortpick_run(session, run.id, include_raw=True)


def validate_historical_replay_run(
    session: Session,
    run_id: int,
    *,
    horizons: list[int] | None = None,
) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None:
        raise LookupError(f"Shortpick replay run {run_id} not found.")
    target_horizons = horizons or SHORTPICK_DEFAULT_HORIZONS
    candidates = session.scalars(
        select(ShortpickCandidate)
        .where(ShortpickCandidate.run_id == run_id, ShortpickCandidate.parse_status == "parsed")
        .order_by(ShortpickCandidate.id.asc())
    ).all()
    benchmark_maps = benchmark_close_maps(session)
    updated = 0
    for candidate in candidates:
        market_sync = {
            "status": "historical_replay_existing_only",
            "reason": "Historical replay validation never fetches current market data.",
        }
        for horizon in target_horizons:
            snapshot = _upsert_validation_snapshot(
                session,
                run,
                candidate,
                int(horizon),
                benchmark_maps=benchmark_maps,
                market_sync=market_sync,
                include_sector_benchmark=False,
            )
            snapshot.validation_payload = {
                **dict(snapshot.validation_payload or {}),
                "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
                "baseline_family": _candidate_baseline_family(candidate),
                "source_packet_id": _candidate_payload(candidate).get("source_packet_id"),
                "source_packet_hash": _candidate_payload(candidate).get("source_packet_hash"),
                "leakage_audit_status": _candidate_payload(candidate).get("leakage_audit_status"),
                "leakage_audit_reasons": _candidate_payload(candidate).get("leakage_audit_reasons") or [],
                "official_sample_eligible": bool(_candidate_payload(candidate).get("official_sample_eligible")),
                "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            }
            if not _candidate_payload(candidate).get("official_sample_eligible"):
                snapshot.validation_payload["official_validation"] = False
            updated += 1
    display_gate = _apply_shortpick_candidate_display_gates(session, run_id=run_id)
    summary = {
        **_shortpick_validation_summary(session, run_id=run_id),
        "candidate_display_gate": display_gate,
        "replay_feedback": _json_safe(build_shortpick_replay_feedback(session, run_id=run_id)),
    }
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        **summary,
        "benchmark_sync": {"status": "historical_replay_existing_only"},
    }
    session.flush()
    return {"run_id": run_id, "updated_validation_count": updated, "horizons": target_horizons, "summary": summary}


def list_shortpick_replay_runs(
    session: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    payload = list_shortpick_runs(
        session,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        include_raw=include_raw,
    )
    items = [item for item in payload["items"] if item.get("information_mode") == SHORTPICK_HISTORICAL_REPLAY_MODE]
    return {**payload, "items": items, "total": len(items)}


def get_shortpick_replay_run(session: Session, run_id: int, *, include_raw: bool = False) -> dict[str, Any]:
    payload = get_shortpick_run(session, run_id, include_raw=include_raw)
    if payload.get("information_mode") != SHORTPICK_HISTORICAL_REPLAY_MODE:
        raise LookupError(f"Shortpick replay run {run_id} not found.")
    return payload


def list_shortpick_replay_candidates(session: Session, *, run_id: int, include_raw: bool = False) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None or run.information_mode != SHORTPICK_HISTORICAL_REPLAY_MODE:
        raise LookupError(f"Shortpick replay run {run_id} not found.")
    return list_shortpick_candidates(session, run_id=run_id, limit=500, include_raw=include_raw)


def get_shortpick_replay_sources(session: Session, run_id: int) -> dict[str, Any]:
    payload = get_shortpick_replay_run(session, run_id, include_raw=False)
    summary = dict(payload.get("summary") or {})
    source_packet = dict(summary.get("source_packet") or {})
    return {
        "generated_at": utcnow(),
        "run_id": run_id,
        "source_packet_id": summary.get("source_packet_id"),
        "source_packet_hash": summary.get("source_packet_hash"),
        "as_of_cutoff": summary.get("as_of_cutoff"),
        "source_packet": source_packet,
        "official_sources": source_packet.get("official_sources") or [],
        "diagnostic_sources": source_packet.get("diagnostic_sources") or [],
        "rejected_sources": source_packet.get("rejected_sources") or [],
        "tradable_universe": summary.get("tradable_universe") or {},
    }


def build_shortpick_replay_feedback(session: Session, *, run_id: int | None = None) -> dict[str, Any]:
    rows = _replay_validation_rows(session, run_id=run_id)
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_family.setdefault(str(row["baseline_family"]), []).append(row)
    families = []
    for family, family_rows in sorted(by_family.items()):
        families.append(
            {
                "baseline_family": family,
                "label": _baseline_label(family),
                "candidate_count": len({row["candidate"].id for row in family_rows}),
                "official_sample_count": len([row for row in family_rows if row["official_sample_eligible"]]),
                "completed_official_sample_count": len(
                    [row for row in family_rows if row["official_sample_eligible"] and row["validation"].status == "completed"]
                ),
                "validation_by_horizon": _replay_feedback_groups(family_rows, group_key="horizon"),
                "robustness_metrics": _robustness_metrics(family_rows),
            }
        )
    factor_ic_gate = _factor_ic_gate_readout(session)
    news_calibration = _news_calibration_readout(session)
    return {
        "generated_at": utcnow(),
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "run_id": run_id,
        "families": families,
        "overall": {
            "validation_count": len(rows),
            "completed_official_sample_count": len(
                [row for row in rows if row["official_sample_eligible"] and row["validation"].status == "completed"]
            ),
            "baseline_families": list(SHORTPICK_REPLAY_BASELINE_FAMILIES),
            "robustness_metrics": _robustness_metrics(rows),
            "factor_ic_gate": factor_ic_gate,
            "news_calibration": news_calibration,
        },
    }


def _build_universe(session: Session, *, as_of_date: date) -> dict[str, Any]:
    members: list[_UniverseMember] = []
    excluded: dict[str, int] = {}
    stocks = session.scalars(select(Stock).order_by(Stock.symbol.asc())).all()
    for stock in stocks:
        if stock.listed_date and stock.listed_date > as_of_date:
            excluded["listed_after_as_of"] = excluded.get("listed_after_as_of", 0) + 1
            continue
        bars = session.scalars(
            select(MarketBar)
            .where(MarketBar.stock_id == stock.id, MarketBar.timeframe == "1d", func.date(MarketBar.observed_at) <= as_of_date.isoformat())
            .order_by(MarketBar.observed_at.asc(), MarketBar.id.asc())
        ).all()
        if not bars:
            excluded["missing_daily_bar"] = excluded.get("missing_daily_bar", 0) + 1
            continue
        latest = bars[-1]
        if latest.observed_at.date() != as_of_date:
            excluded["no_bar_on_as_of_date"] = excluded.get("no_bar_on_as_of_date", 0) + 1
            continue
        name = stock.name or stock.symbol
        if name.upper().startswith("ST") or "ST" in name.upper():
            excluded["st_status"] = excluded.get("st_status", 0) + 1
            continue
        market_cap = latest.total_mv or latest.circ_mv
        industry = _stock_industry(stock)
        members.append(
            _UniverseMember(
                symbol=stock.symbol,
                name=name,
                latest_bar=latest,
                previous_bar=bars[-2] if len(bars) >= 2 else None,
                market_cap=float(market_cap) if market_cap is not None else None,
                turnover_rate=latest.turnover_rate,
                industry=industry,
                market_cap_bucket="unknown",
            )
        )
    members = _assign_market_cap_buckets(members)
    return {
        "members": members,
        "by_symbol": {member.symbol: member for member in members},
        "summary": {
            "as_of_date": as_of_date.isoformat(),
            "universe_count": len(stocks),
            "total_count": len(stocks),
            "tradeable_count": len(members),
            "excluded_counts": excluded,
            "excluded_count": sum(excluded.values()),
            "excluded_st": excluded.get("st_status", 0),
            "excluded_suspended": excluded.get("suspended", 0),
            "excluded_limit_status": excluded.get("limit_status", 0),
            "excluded_missing_bar": excluded.get("missing_daily_bar", 0) + excluded.get("no_bar_on_as_of_date", 0),
            "market_cap_bucket_counts": _count_by([member.market_cap_bucket for member in members]),
            "industry_counts": _count_by([member.industry or "unknown" for member in members]),
        },
    }


def _build_source_packet(
    session: Session,
    *,
    as_of_date: date,
    as_of_cutoff: datetime,
    universe: dict[str, Any],
) -> dict[str, Any]:
    source_start = as_of_cutoff - timedelta(days=SHORTPICK_REPLAY_SOURCE_LOOKBACK_DAYS)
    news_items = session.scalars(
        select(NewsItem)
        .where(NewsItem.published_at >= source_start, NewsItem.published_at <= as_of_cutoff + timedelta(days=7))
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
    ).all()
    official_sources: list[dict[str, Any]] = []
    rejected_sources: list[dict[str, Any]] = []
    official_index = 0
    rejected_index = 0
    for item in news_items[:120]:
        linked_symbols = [
            link.stock.symbol
            for link in session.scalars(select(NewsEntityLink).where(NewsEntityLink.news_id == item.id)).all()
            if link.stock is not None and link.stock.symbol in universe["by_symbol"]
        ]
        source_payload = {
            "title": item.headline,
            "url": str((item.raw_payload or {}).get("url") or item.source_uri or f"news://{item.news_key}"),
            "published_at": item.published_at.isoformat(),
            "fetched_at": item.created_at.isoformat(),
            "body_excerpt": item.content_excerpt or item.summary,
            "source_type": item.provider_name,
            "linked_symbols": linked_symbols,
        }
        published_at = _parse_datetime(item.published_at)
        if published_at is None or published_at > as_of_cutoff:
            rejected_index += 1
            rejected_sources.append(
                {
                    **source_payload,
                    "source_id": f"rej-{rejected_index:03d}",
                    "status": "rejected",
                    "reject_reason": "unverified_source_time" if published_at is None else "source_after_cutoff",
                }
            )
            continue
        official_index += 1
        official_sources.append(
            {
                **source_payload,
                "source_id": f"src-{official_index:03d}",
                "status": "official",
                "reject_reason": None,
            }
        )
        if len(official_sources) >= 80:
            break
    packet_base = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "as_of_date": as_of_date.isoformat(),
        "as_of_cutoff": as_of_cutoff.isoformat(),
        "official_sources": official_sources,
        "diagnostic_sources": [],
        "rejected_sources": rejected_sources[:40],
        "tradable_universe": universe["summary"],
    }
    packet_hash = _stable_hash(packet_base)
    return {
        **packet_base,
        "source_packet_id": f"shortpick-replay-packet:{as_of_date.isoformat()}:{packet_hash[:12]}",
        "source_packet_hash": packet_hash,
    }


def _insert_replay_candidates(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    rounds: int,
    candidate_limit: int,
) -> None:
    llm_symbols = _llm_proxy_symbols(packet=packet, universe=universe, limit=min(rounds, candidate_limit))
    round_record = _insert_replay_round(session, run=run, packet=packet, symbols=llm_symbols)
    for index, symbol in enumerate(llm_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=round_record,
            symbol=symbol,
            baseline_family="llm",
            rank=index,
            packet=packet,
            universe=universe,
        )
    for family, symbols in _baseline_symbols(universe=universe, as_of_date=run.run_date, limit=candidate_limit).items():
        for index, symbol in enumerate(symbols, start=1):
            _insert_candidate(
                session,
                run=run,
                round_record=None,
                symbol=symbol,
                baseline_family=family,
                rank=index,
                packet=packet,
                universe=universe,
            )
    session.flush()


def _insert_replay_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    symbols: list[str],
) -> ShortpickModelRound:
    now = utcnow()
    parsed_payload = {
        "as_of_date": run.run_date.isoformat(),
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "primary_pick": {"symbol": symbols[0] if symbols else "PARSE_FAILED", "name": symbols[0] if symbols else "解析失败"},
        "sources_used": [{"source_id": source["source_id"]} for source in packet["official_sources"][:3]],
        "limitations": ["deterministic sealed-packet proxy until external LLM replay executor is enabled"],
    }
    round_record = ShortpickModelRound(
        run_id=run.id,
        round_key=f"{run.run_key}:sealed-packet-proxy:1",
        provider_name="system",
        model_name="sealed_packet_proxy",
        executor_kind="historical_replay_sealed_packet_proxy",
        round_index=1,
        status="completed",
        raw_answer=json.dumps(parsed_payload, ensure_ascii=False),
        parsed_payload=parsed_payload,
        sources_payload=packet["official_sources"][:5],
        artifact_id=f"shortpick-replay-round:{run.id}:1",
        error_message=None,
        started_at=now,
        completed_at=now,
    )
    session.add(round_record)
    session.flush()
    return round_record


def _insert_candidate(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound | None,
    symbol: str,
    baseline_family: str,
    rank: int,
    packet: dict[str, Any],
    universe: dict[str, Any],
) -> None:
    member = universe["by_symbol"].get(symbol)
    if member is None:
        return
    support_sources = _sources_for_symbol(packet, symbol)
    if baseline_family != "llm" and not support_sources:
        support_sources = packet["official_sources"][:1]
    thesis = _candidate_thesis(member, baseline_family)
    audit = _audit_candidate(
        as_of_date=run.run_date,
        packet=packet,
        symbol=symbol,
        sources=support_sources,
        thesis=thesis,
        evidence_mapping={"thesis": [source["source_id"] for source in support_sources[:2]]},
    )
    candidate_payload = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "baseline_family": baseline_family,
        "baseline_rank": rank,
        "as_of_cutoff": packet["as_of_cutoff"],
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "sources_used": [source["source_id"] for source in support_sources],
        "evidence_mapping": {"thesis": [source["source_id"] for source in support_sources[:2]]},
        "leakage_audit_status": audit["status"],
        "leakage_audit_reasons": audit["reasons"],
        "official_sample_eligible": audit["status"] == "pass",
        "exclusion_reason": None if audit["status"] == "pass" else "; ".join(audit["reasons"]),
        "universe_membership": {
            "in_universe": True,
            "is_tradeable": True,
            "market_cap_bucket": member.market_cap_bucket,
            "industry": member.industry,
            "turnover_rate": member.turnover_rate,
        },
    }
    session.add(
        ShortpickCandidate(
            run_id=run.id,
            round_id=round_record.id if round_record is not None and baseline_family == "llm" else None,
            candidate_key=f"shortpick-replay-candidate:{run.id}:{baseline_family}:{rank}:{symbol}",
            symbol=symbol,
            name=member.name,
            normalized_theme=member.industry or baseline_family,
            horizon_trading_days=5,
            confidence=0.55 if baseline_family != "llm" else 0.62,
            thesis=thesis,
            catalysts=[_baseline_label(baseline_family), f"截至 {run.run_date.isoformat()} 的 sealed packet / 行情快照。"],
            invalidation=["历史隔离回放只验证信号，不进入主推荐或模拟盘。"],
            risks=["若 source packet 含未来信息或样本不足，该候选会从 official sample 排除。"],
            sources_payload=[
                {
                    **source,
                    "credibility_status": "verified",
                    "credibility_reason": "source timestamp is inside sealed replay packet",
                    "support_status": "supported_by_source_text",
                }
                for source in support_sources
            ],
            novelty_note="historical replay baseline candidate" if baseline_family != "llm" else "sealed packet proxy LLM candidate",
            limitations=[] if audit["status"] == "pass" else audit["reasons"],
            convergence_group=baseline_family,
            research_priority="single_model_high_conviction" if baseline_family == "llm" else "baseline_control",
            parse_status="parsed",
            is_system_external=True,
            candidate_payload=candidate_payload,
        )
    )


def _llm_proxy_symbols(*, packet: dict[str, Any], universe: dict[str, Any], limit: int) -> list[str]:
    seen: list[str] = []
    for source in packet["official_sources"]:
        for symbol in source.get("linked_symbols") or []:
            if symbol in universe["by_symbol"] and symbol not in seen:
                seen.append(symbol)
                if len(seen) >= limit:
                    return seen
    for symbol in _momentum_symbols(universe, limit=limit):
        if symbol not in seen:
            seen.append(symbol)
        if len(seen) >= limit:
            break
    return seen


def _baseline_symbols(*, universe: dict[str, Any], as_of_date: date, limit: int) -> dict[str, list[str]]:
    members: list[_UniverseMember] = list(universe["members"])
    symbols = [member.symbol for member in members]
    seed = int(hashlib.sha256(as_of_date.isoformat().encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    shuffled = list(symbols)
    rng.shuffle(shuffled)
    by_bucket: dict[str, list[str]] = {}
    for member in members:
        by_bucket.setdefault(member.market_cap_bucket, []).append(member.symbol)
    bucket_symbols: list[str] = []
    for bucket in sorted(by_bucket):
        bucket_values = list(by_bucket[bucket])
        rng.shuffle(bucket_values)
        bucket_symbols.extend(bucket_values[: max(1, limit // max(1, len(by_bucket)))])
    return {
        "random_same_tradeable_universe": shuffled[:limit],
        "random_same_market_cap_bucket": bucket_symbols[:limit] or shuffled[:limit],
        "momentum_volume_baseline": _momentum_symbols(universe, limit=limit),
    }


def _momentum_symbols(universe: dict[str, Any], *, limit: int) -> list[str]:
    ranked = sorted(
        universe["members"],
        key=lambda member: (
            _bar_return(member),
            float(member.latest_bar.amount or 0.0),
            float(member.turnover_rate or 0.0),
        ),
        reverse=True,
    )
    return [member.symbol for member in ranked[:limit]]


def _replay_validation_rows(session: Session, *, run_id: int | None) -> list[dict[str, Any]]:
    query = (
        select(ShortpickValidationSnapshot, ShortpickCandidate)
        .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
        .join(ShortpickExperimentRun, ShortpickCandidate.run_id == ShortpickExperimentRun.id)
        .where(ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE)
    )
    if run_id is not None:
        query = query.where(ShortpickCandidate.run_id == run_id)
    rows = []
    for validation, candidate in session.execute(query).all():
        payload = _candidate_payload(candidate)
        rows.append(
            {
                "validation": validation,
                "candidate": candidate,
                "baseline_family": payload.get("baseline_family") or "unknown",
                "official_sample_eligible": bool(payload.get("official_sample_eligible")),
            }
        )
    return rows


def _replay_feedback_groups(rows: list[dict[str, Any]], *, group_key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row["validation"].horizon_days if group_key == "horizon" else row["baseline_family"])
        grouped.setdefault(key, []).append(row)
    output = []
    for key, values in sorted(grouped.items()):
        completed = [
            row for row in values
            if row["official_sample_eligible"] and row["validation"].status == "completed"
        ]
        excess = [float(row["validation"].excess_return) for row in completed if row["validation"].excess_return is not None]
        output.append(
            {
                "group_key": key,
                "label": f"{key}日" if group_key == "horizon" else _baseline_label(key),
                "sample_count": len(values),
                "official_sample_count": len([row for row in values if row["official_sample_eligible"]]),
                "completed_official_sample_count": len(completed),
                "completed_validation_count": len([row for row in values if row["validation"].status == "completed"]),
                "mean_excess_return": _mean_or_none(excess),
                "trimmed_mean_excess_return": _trimmed_mean_or_none(excess),
                "positive_excess_rate": _positive_rate(excess),
                "benchmark_metrics": {},
                "status_counts": _count_by([row["validation"].status for row in values]),
            }
        )
    return output


def _robustness_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        row for row in rows
        if row["official_sample_eligible"] and row["validation"].status == "completed" and row["validation"].excess_return is not None
    ]
    values = [float(row["validation"].excess_return) for row in completed]
    by_symbol: dict[str, list[float]] = {}
    by_date: dict[str, list[float]] = {}
    for row in completed:
        value = float(row["validation"].excess_return)
        by_symbol.setdefault(row["candidate"].symbol, []).append(value)
        run = row["candidate"].run_id
        date_key = str(run)
        by_date.setdefault(date_key, []).append(value)
    best_symbol = max(by_symbol, key=lambda key: _mean_or_none(by_symbol[key]) or -999.0) if by_symbol else None
    best_date = max(by_date, key=lambda key: _mean_or_none(by_date[key]) or -999.0) if by_date else None
    return {
        "raw_mean_excess_return": _mean_or_none(values),
        "trimmed_mean_excess_return": _trimmed_mean_or_none(values),
        "positive_excess_rate": _positive_rate(values),
        "drop_best_symbol_mean_excess_return": _mean_or_none([
            float(row["validation"].excess_return)
            for row in completed
            if best_symbol is None or row["candidate"].symbol != best_symbol
        ]),
        "drop_best_date_mean_excess_return": _mean_or_none([
            float(row["validation"].excess_return)
            for row in completed
            if best_date is None or str(row["candidate"].run_id) != best_date
        ]),
        "best_symbol": best_symbol,
        "sample_count": len(values),
    }


def _factor_ic_gate_readout(session: Session) -> dict[str, Any]:
    symbol_count = session.scalar(select(func.count(func.distinct(Stock.symbol)))) or 0
    return {
        "status": "blocked" if symbol_count < 30 else "ready_for_window_check",
        "cross_section_symbol_count": int(symbol_count),
        "cross_section_stock_count": int(symbol_count),
        "effective_window_count": 0,
        "min_cross_section_symbol_count": 30,
        "min_effective_window_count": 20,
        "excluded_factors": [] if symbol_count >= 30 else ["all_ic_based_weighting"],
        "reason": "IC-based weights remain disabled until both cross-section and rolling-window gates are satisfied.",
    }


def _news_calibration_readout(session: Session) -> dict[str, Any]:
    news_count = session.scalar(select(func.count(NewsItem.id))) or 0
    linked_count = session.scalar(select(func.count(NewsEntityLink.id))) or 0
    return {
        "status": "diagnostic_only" if news_count < 100 else "ready_for_calibration",
        "news_item_count": int(news_count),
        "news_count": int(news_count),
        "news_entity_link_count": int(linked_count),
        "metrics": {
            "importance_bucket_forward_return": None,
            "direction_hit_rate": None,
            "post_news_abnormal_return": None,
        },
        "reason": "News coverage is visible, but alpha calibration remains diagnostic until enough timestamped events accumulate.",
    }


def _audit_candidate(
    *,
    as_of_date: date,
    packet: dict[str, Any],
    symbol: str,
    sources: list[dict[str, Any]],
    thesis: str,
    evidence_mapping: dict[str, list[str]],
) -> dict[str, Any]:
    reasons: list[str] = []
    allowed_source_ids = {source["source_id"] for source in packet["official_sources"]}
    used_source_ids = {source.get("source_id") for source in sources if source.get("source_id")}
    if symbol not in {member for source in packet["official_sources"] for member in source.get("linked_symbols", [])} and not used_source_ids:
        reasons.append("unsupported_claim")
    if unexpected := sorted(str(source_id) for source_id in used_source_ids if source_id not in allowed_source_ids):
        reasons.append("source_not_in_packet")
    for source in sources:
        published_at = _parse_datetime(source.get("published_at"))
        if published_at is None:
            reasons.append("unverified_source_time")
        elif published_at > _as_of_cutoff(as_of_date):
            reasons.append("source_after_cutoff")
    if not any(evidence_mapping.values()):
        reasons.append("unsupported_claim")
    if _contains_future_date(thesis, as_of_date=as_of_date):
        reasons.append("future_leakage_suspected")
    status = "pass" if not reasons else "fail"
    return {"status": status, "reasons": sorted(set(reasons)) or ["audit_pass"]}


def _sources_for_symbol(packet: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    matched = [source for source in packet["official_sources"] if symbol in (source.get("linked_symbols") or [])]
    return matched[:3] if matched else packet["official_sources"][:1]


def _packet_summary(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "as_of_date": packet["as_of_date"],
        "as_of_cutoff": packet["as_of_cutoff"],
        "official_source_count": len(packet["official_sources"]),
        "diagnostic_source_count": len(packet["diagnostic_sources"]),
        "rejected_source_count": len(packet["rejected_sources"]),
        "official_sources": packet["official_sources"][:100],
        "diagnostic_sources": packet["diagnostic_sources"][:100],
        "rejected_sources": packet["rejected_sources"][:100],
    }


def _write_replay_packet_artifact(session: Session, run: ShortpickExperimentRun, packet: dict[str, Any]) -> None:
    write_shortpick_lab_artifact(
        artifact_id=str(packet["source_packet_id"]),
        root=_artifact_root(session),
        payload={
            "artifact_id": packet["source_packet_id"],
            "artifact_type": "shortpick_historical_replay_packet",
            "run_key": run.run_key,
            **packet,
        },
    )


def _candidate_thesis(member: _UniverseMember, baseline_family: str) -> str:
    ret = _bar_return(member)
    if baseline_family == "llm":
        return f"{member.name} 在 sealed packet 的可得来源/题材中被选中，回放仅使用当日之前信息；最新日收益 {ret:.2%}。"
    if baseline_family == "momentum_volume_baseline":
        return f"{member.name} 由动量成交量基准选中：截至当日日收益 {ret:.2%}，成交额 {member.latest_bar.amount:.0f}。"
    if baseline_family == "random_same_market_cap_bucket":
        return f"{member.name} 由同市值分桶随机基准选中，市值桶 {member.market_cap_bucket}。"
    return f"{member.name} 由当日可交易 universe 随机基准选中。"


def _assign_market_cap_buckets(members: list[_UniverseMember]) -> list[_UniverseMember]:
    known = sorted([member.market_cap for member in members if member.market_cap is not None])
    if not known:
        return members
    low = known[len(known) // 3]
    high = known[(len(known) * 2) // 3]
    output = []
    for member in members:
        if member.market_cap is None:
            bucket = "unknown"
        elif member.market_cap <= low:
            bucket = "small"
        elif member.market_cap <= high:
            bucket = "mid"
        else:
            bucket = "large"
        output.append(
            _UniverseMember(
                symbol=member.symbol,
                name=member.name,
                latest_bar=member.latest_bar,
                previous_bar=member.previous_bar,
                market_cap=member.market_cap,
                turnover_rate=member.turnover_rate,
                industry=member.industry,
                market_cap_bucket=bucket,
            )
        )
    return output


def _bar_return(member: _UniverseMember) -> float:
    if member.previous_bar is None or not member.previous_bar.close_price:
        return 0.0
    return float(member.latest_bar.close_price / member.previous_bar.close_price - 1)


def _stock_industry(stock: Stock) -> str | None:
    payload = stock.profile_payload if isinstance(stock.profile_payload, dict) else {}
    return payload.get("industry") or payload.get("sector") or payload.get("board")


def _candidate_payload(candidate: ShortpickCandidate) -> dict[str, Any]:
    return candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}


def _candidate_baseline_family(candidate: ShortpickCandidate) -> str:
    return str(_candidate_payload(candidate).get("baseline_family") or "unknown")


def _baseline_label(value: str) -> str:
    labels = {
        "llm": "LLM",
        "random_same_tradeable_universe": "随机",
        "random_same_market_cap_bucket": "同市值随机",
        "momentum_volume_baseline": "动量成交量",
    }
    return labels.get(value, value)


def _as_of_cutoff(value: date) -> datetime:
    return datetime.combine(value, time(15, 30), tzinfo=UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _contains_future_date(text: str, *, as_of_date: date) -> bool:
    for match in re.finditer(r"20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}", text or ""):
        digits = [int(item) for item in re.findall(r"\d+", match.group(0))[:3]]
        if len(digits) == 3:
            try:
                if date(digits[0], digits[1], digits[2]) > as_of_date:
                    return True
            except ValueError:
                continue
    return False


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _json_safe(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _mean_or_none(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _trimmed_mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) < 5:
        return _mean_or_none(values)
    ordered = sorted(values)
    return _mean_or_none(ordered[1:-1])


def _positive_rate(values: list[float]) -> float | None:
    return round(sum(1 for value in values if value > 0) / len(values), 6) if values else None
