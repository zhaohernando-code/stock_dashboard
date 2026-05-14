from __future__ import annotations

import hashlib
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import sleep
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ashare_evidence.benchmark import benchmark_close_maps
from ashare_evidence.db import utcnow
from ashare_evidence.llm_service import route_model
from ashare_evidence.market_rules import (
    ACCOUNT_PROFILE_LABELS,
    ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    account_trade_eligibility,
)
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
from ashare_evidence.research_artifact_store import read_shortpick_lab_artifact_if_exists, write_shortpick_lab_artifact
from ashare_evidence.shortpick_lab import (
    SHORTPICK_DEFAULT_HORIZONS,
    SHORTPICK_OFFICIAL_VALIDATION_MODE,
    _apply_shortpick_candidate_display_gates,
    _artifact_root,
    _shortpick_validation_summary,
    _upsert_validation_snapshot,
    extract_shortpick_json,
    get_shortpick_run,
    list_shortpick_candidates,
)

SHORTPICK_HISTORICAL_REPLAY_MODE = "historical_replay"
SHORTPICK_HISTORICAL_REPLAY_PROMPT_VERSION = "shortpick_historical_replay_v1"
SHORTPICK_REPLAY_EXPERIMENT_MODE = "historical_replay"
SHORTPICK_REPLAY_FEEDBACK_CACHE_VERSION = "shortpick-replay-feedback-cache-v1"
SHORTPICK_REPLAY_SOURCE_LOOKBACK_DAYS = 21
SHORTPICK_REPLAY_LLM_MODE_ENV = "ASHARE_SHORTPICK_REPLAY_LLM_MODE"
SHORTPICK_REPLAY_BASELINE_FAMILIES = (
    "llm",
    "llm_self_distilled",
    "llm_momentum_distilled",
    "random_same_tradeable_universe",
    "random_same_market_cap_bucket",
    "momentum_volume_baseline",
    "momentum_volume_expanded_pool",
    "llm_reject_only",
    "llm_reject_then_momentum_rank",
    "random_reject_then_momentum_rank",
    "llm_hard_veto_then_momentum_rank",
    "random_hard_veto_then_momentum_rank",
    "llm_strict_veto_then_momentum_rank",
    "random_strict_veto_then_momentum_rank",
    "momentum_turnover_rank",
    "momentum_10d_rank",
    "momentum_10d_turnover_rank",
    "momentum_10d_turnover_cooldown_rank",
    "momentum_continuity_turnover_rank",
)
SHORTPICK_REPLAY_HORIZON_ORDER = (1, 3, 5, 10, 20)
SHORTPICK_REPLAY_HARD_LEAKAGE_REASONS = {
    "source_not_in_packet",
    "source_after_cutoff",
    "unverified_source_time",
    "future_leakage_suspected",
}
SHORTPICK_REPLAY_DISTILL_FAMILIES = (
    "llm_self_distilled",
    "llm_momentum_distilled",
    "momentum_volume_expanded_pool",
)
SHORTPICK_REPLAY_DISTILL_EXECUTORS = (
    "historical_replay_llm_self_distiller",
    "historical_replay_momentum_pool_distiller",
)
SHORTPICK_REPLAY_REJECTION_FAMILIES = (
    "llm_reject_only",
    "llm_reject_then_momentum_rank",
    "random_reject_then_momentum_rank",
)
SHORTPICK_REPLAY_REJECTION_EXECUTORS = (
    "historical_replay_momentum_pool_rejector",
)
SHORTPICK_REPLAY_HARD_VETO_FAMILIES = (
    "llm_hard_veto_then_momentum_rank",
    "random_hard_veto_then_momentum_rank",
    "llm_strict_veto_then_momentum_rank",
    "random_strict_veto_then_momentum_rank",
)
SHORTPICK_REPLAY_HARD_VETO_EXECUTORS = (
    "historical_replay_momentum_pool_hard_veto",
)
SHORTPICK_REPLAY_FACTOR_RANK_FAMILIES = (
    "momentum_turnover_rank",
    "momentum_10d_rank",
    "momentum_10d_turnover_rank",
    "momentum_10d_turnover_cooldown_rank",
    "momentum_continuity_turnover_rank",
)
SHORTPICK_REPLAY_STRICT_VETO_CATEGORIES = {
    "source_mismatch",
    "future_source",
    "untradeable",
    "liquidity_abnormal",
    "negative_direct_conflict",
    "source_not_in_packet",
}


@dataclass(frozen=True)
class _UniverseMember:
    symbol: str
    name: str
    latest_bar: MarketBar
    previous_bar: MarketBar | None
    market_cap: float | None
    market_cap_source: str
    turnover_rate: float | None
    industry: str | None
    market_cap_bucket: str


@dataclass(frozen=True)
class _ReplayLlmTask:
    run_id: int
    run_date: date
    packet: dict[str, Any]
    prompt: str
    system: str
    limit: int


@dataclass(frozen=True)
class _ReplayLlmResult:
    task: _ReplayLlmTask
    parsed_json: dict[str, Any] | None
    raw_answer: str
    final_raw_answer: str
    provider_name: str
    model_name: str
    repair_used: bool
    error_message: str | None


@dataclass(frozen=True)
class _ReplayDistillationTask:
    run_id: int
    run_date: date
    packet: dict[str, Any]
    prompt: str | None
    source_family: str
    output_family: str
    executor_kind: str
    pool_symbols: list[str]
    limit: int
    round_index: int


@dataclass(frozen=True)
class _ReplayDistillationResult:
    task: _ReplayDistillationTask
    parsed_json: dict[str, Any] | None
    raw_answer: str
    final_raw_answer: str
    provider_name: str
    model_name: str
    repair_used: bool
    error_message: str | None


def run_shortpick_historical_replay(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    rounds: int = 5,
    candidate_limit: int = 3,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
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
                account_profile=account_profile,
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
        "account_profile": account_profile,
        "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
        "run_count": len(replay_runs),
        "runs": replay_runs,
    }


def run_shortpick_historical_replay_concurrent(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    rounds: int = 5,
    candidate_limit: int = 3,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    max_workers: int = 4,
    triggered_by: str | None = None,
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    normalized_rounds = max(1, min(int(rounds), 10))
    normalized_limit = max(1, min(int(candidate_limit), 10))
    worker_count = max(1, min(int(max_workers), 6))
    if worker_count <= 1 or os.getenv(SHORTPICK_REPLAY_LLM_MODE_ENV, "real").strip().lower() in {
        "proxy",
        "deterministic_proxy",
        "off",
        "disabled",
    }:
        return run_shortpick_historical_replay(
            session,
            start_date=start_date,
            end_date=end_date,
            rounds=normalized_rounds,
            candidate_limit=normalized_limit,
            account_profile=account_profile,
            triggered_by=triggered_by,
        )

    tasks: list[_ReplayLlmTask] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            tasks.append(
                _prepare_replay_llm_task(
                    session,
                    as_of_date=cursor,
                    rounds=normalized_rounds,
                    candidate_limit=normalized_limit,
                    account_profile=account_profile,
                    triggered_by=triggered_by,
                )
            )
        cursor += timedelta(days=1)
    session.commit()

    results: list[_ReplayLlmResult] = []
    with ThreadPoolExecutor(max_workers=min(worker_count, len(tasks) or 1)) as executor:
        futures = [executor.submit(_execute_replay_llm_task, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            _persist_replay_llm_result(
                session,
                result=result,
                rounds=normalized_rounds,
                candidate_limit=normalized_limit,
                account_profile=account_profile,
            )
            session.commit()

    run_ids = [result.task.run_id for result in sorted(results, key=lambda item: item.task.run_date)]
    replay_runs = [get_shortpick_run(session, run_id, include_raw=True) for run_id in run_ids]
    failed_count = len([result for result in results if result.error_message])
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "execution_mode": "concurrent_llm_serial_db_writer",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "rounds": normalized_rounds,
        "candidate_limit": normalized_limit,
        "account_profile": account_profile,
        "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
        "llm_max_workers": worker_count,
        "run_count": len(replay_runs),
        "failed_llm_count": failed_count,
        "runs": replay_runs,
    }


def _run_one_replay_date(
    session: Session,
    *,
    as_of_date: date,
    rounds: int,
    candidate_limit: int,
    account_profile: str,
    triggered_by: str | None,
) -> dict[str, Any]:
    started_at = utcnow()
    as_of_cutoff = _as_of_cutoff(as_of_date)
    universe = _build_universe(session, as_of_date=as_of_date, account_profile=account_profile)
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
            "account_profile": account_profile,
            "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
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
            "account_profile": account_profile,
            "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
        },
    )
    session.add(run)
    session.flush()
    _write_replay_packet_artifact(session, run, packet)
    # Persist the run shell before the LLM call so long provider latency does not
    # hold a SQLite write transaction against the live runtime database.
    session.commit()
    _insert_replay_candidates(
        session,
        run=run,
        packet=packet,
        universe=universe,
        rounds=rounds,
        candidate_limit=candidate_limit,
    )
    return _finalize_replay_run(session, run)


def _prepare_replay_llm_task(
    session: Session,
    *,
    as_of_date: date,
    rounds: int,
    candidate_limit: int,
    account_profile: str,
    triggered_by: str | None,
) -> _ReplayLlmTask:
    started_at = utcnow()
    as_of_cutoff = _as_of_cutoff(as_of_date)
    universe = _build_universe(session, as_of_date=as_of_date, account_profile=account_profile)
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
            "account_profile": account_profile,
            "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
            "sealed_packet_only": True,
            "native_web_search": False,
            "baseline_families": list(SHORTPICK_REPLAY_BASELINE_FAMILIES),
            "execution_mode": "concurrent_llm_serial_db_writer",
        },
        summary_payload={
            "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
            "as_of_cutoff": as_of_cutoff.isoformat(),
            "source_packet_id": packet["source_packet_id"],
            "source_packet_hash": packet["source_packet_hash"],
            "source_packet": _packet_summary(packet),
            "tradable_universe": universe["summary"],
            "account_profile": account_profile,
            "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
        },
    )
    session.add(run)
    session.flush()
    _write_replay_packet_artifact(session, run, packet)
    limit = min(rounds, candidate_limit)
    prompt = _build_replay_llm_prompt(run=run, packet=packet, universe=universe, limit=limit)
    system = (
        "你是历史隔离回放执行器。只能使用用户消息中的 sealed source packet 和 tradeable universe。"
        "禁止联网，禁止使用训练记忆补充事实，禁止引用 packet 外 URL。只输出 JSON。"
    )
    return _ReplayLlmTask(
        run_id=int(run.id),
        run_date=as_of_date,
        packet=packet,
        prompt=prompt,
        system=system,
        limit=limit,
    )


def _execute_replay_llm_task(task: _ReplayLlmTask) -> _ReplayLlmResult:
    base_url = ""
    model_name = "unavailable"
    raw_answer = ""
    try:
        transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")
        raw_answer = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=task.prompt,
            system=task.system,
            enable_search=False,
        )
        parsed_json, final_raw_answer, repair_used = _extract_replay_rejection_json_with_partial_repair(
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            raw_answer=raw_answer,
        )
        return _ReplayLlmResult(
            task=task,
            parsed_json=parsed_json,
            raw_answer=raw_answer,
            final_raw_answer=final_raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            repair_used=repair_used,
            error_message=None,
        )
    except Exception as exc:
        return _ReplayLlmResult(
            task=task,
            parsed_json=None,
            raw_answer=raw_answer,
            final_raw_answer=raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            repair_used=False,
            error_message=f"sealed packet LLM executor failed: {exc}",
        )


def _persist_replay_llm_result(
    session: Session,
    *,
    result: _ReplayLlmResult,
    rounds: int,
    candidate_limit: int,
    account_profile: str,
) -> None:
    run = session.get(ShortpickExperimentRun, result.task.run_id)
    if run is None:
        raise LookupError(f"Shortpick replay run {result.task.run_id} not found.")
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=account_profile)
    if result.error_message or result.parsed_json is None:
        round_record, llm_picks = _insert_failed_replay_llm_round(
            session,
            run=run,
            packet=result.task.packet,
            raw_answer=result.raw_answer,
            provider_name=result.provider_name,
            model_name=result.model_name,
            error_message=result.error_message or "sealed packet LLM executor failed",
            prompt=result.task.prompt,
        )
    else:
        parsed_payload = _normalize_replay_llm_payload(
            result.parsed_json,
            packet=result.task.packet,
            universe=universe,
            limit=result.task.limit,
        )
        parsed_payload["_json_repair_used"] = result.repair_used
        round_record = _insert_replay_round_record(
            session,
            run=run,
            packet=result.task.packet,
            parsed_payload=parsed_payload,
            raw_answer=result.final_raw_answer,
            provider_name=result.provider_name,
            model_name=result.model_name,
            executor_kind="historical_replay_sealed_packet_llm",
            error_message=None,
            prompt=result.task.prompt,
        )
        llm_picks = list(parsed_payload.get("candidates") or [])
    for index, pick in enumerate(llm_picks, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=round_record,
            symbol=str(pick["symbol"]),
            baseline_family="llm",
            rank=index,
            packet=result.task.packet,
            universe=universe,
            llm_pick=pick,
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
                packet=result.task.packet,
                universe=universe,
            )
    session.flush()
    _finalize_replay_run(session, run)


def _finalize_replay_run(session: Session, run: ShortpickExperimentRun) -> dict[str, Any]:
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    run.status = "completed"
    run.completed_at = utcnow()
    candidate_rows = session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id)).all()
    candidate_payloads = [_candidate_payload(candidate) for candidate in candidate_rows]
    round_rows = session.scalars(
        select(ShortpickModelRound).where(ShortpickModelRound.run_id == run.id).order_by(ShortpickModelRound.id.asc())
    ).all()
    llm_round = round_rows[0] if round_rows else None
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        **dict(validation_result.get("summary") or {}),
        "candidate_count": len(candidate_rows),
        "official_sample_count": len([payload for payload in candidate_payloads if payload.get("official_sample_eligible")]),
        "tradable_sample_count": len([payload for payload in candidate_payloads if _replay_tradable_sample_eligible(payload)]),
        "leakage_failed_count": len([payload for payload in candidate_payloads if payload.get("leakage_audit_status") == "fail"]),
        "baseline_candidate_count": len([payload for payload in candidate_payloads if payload.get("baseline_family") != "llm"]),
        "model_family": (
            f"{llm_round.provider_name}:{llm_round.model_name}" if llm_round and llm_round.provider_name != "system"
            else "diagnostic-sealed-packet-proxy"
        ),
        "llm_executor_kind": llm_round.executor_kind if llm_round else None,
        "boundary": "historical_replay_no_main_pool_write",
    }
    session.flush()
    session.commit()
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
        candidate_payload = _ensure_replay_candidate_contract(candidate)
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
                "source_packet_id": candidate_payload.get("source_packet_id"),
                "source_packet_hash": candidate_payload.get("source_packet_hash"),
                "leakage_audit_status": candidate_payload.get("leakage_audit_status"),
                "leakage_audit_reasons": candidate_payload.get("leakage_audit_reasons") or [],
                "official_sample_eligible": bool(candidate_payload.get("official_sample_eligible")),
                "tradable_sample_eligible": _replay_tradable_sample_eligible(candidate_payload),
                "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
                "market_sync_status": market_sync["status"],
                "benchmark_sync_status": "historical_replay_existing_only",
            }
            if "benchmark_dimensions" not in snapshot.validation_payload:
                reason = snapshot.validation_payload.get("pending_reason") or "Historical replay validation is not completed for this horizon."
                snapshot.validation_payload["benchmark_dimensions"] = _pending_replay_benchmark_dimensions(reason=reason)
                snapshot.validation_payload["available_benchmark_dimensions"] = []
            if not candidate_payload.get("official_sample_eligible"):
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


def run_shortpick_replay_distillation(
    session: Session,
    *,
    run_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    momentum_pool_limit: int = 20,
    self_distill_limit: int = 3,
    momentum_distill_limit: int = 5,
) -> dict[str, Any]:
    query = (
        select(ShortpickExperimentRun)
        .where(
            ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE,
            ShortpickExperimentRun.status == "completed",
        )
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
    )
    if run_id is not None:
        query = query.where(ShortpickExperimentRun.id == run_id)
    if start_date is not None:
        query = query.where(ShortpickExperimentRun.run_date >= start_date)
    if end_date is not None:
        query = query.where(ShortpickExperimentRun.run_date <= end_date)
    runs = [run for run in session.scalars(query).all() if not _is_diagnostic_replay_run(run)]
    outputs: list[dict[str, Any]] = []
    for run in runs:
        outputs.append(
            _distill_one_replay_run(
                session,
                run=run,
                momentum_pool_limit=max(1, min(int(momentum_pool_limit), 40)),
                self_distill_limit=max(1, min(int(self_distill_limit), 10)),
                momentum_distill_limit=max(1, min(int(momentum_distill_limit), 10)),
            )
        )
        session.commit()
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "distillation_mode": "llm_filtering",
        "run_count": len(outputs),
        "runs": outputs,
        "config": {
            "momentum_pool_limit": momentum_pool_limit,
            "self_distill_limit": self_distill_limit,
            "momentum_distill_limit": momentum_distill_limit,
            "families": list(SHORTPICK_REPLAY_DISTILL_FAMILIES),
        },
    }


def run_shortpick_replay_distillation_concurrent(
    session: Session,
    *,
    run_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    momentum_pool_limit: int = 20,
    self_distill_limit: int = 3,
    momentum_distill_limit: int = 5,
    max_workers: int = 4,
) -> dict[str, Any]:
    worker_count = max(1, min(int(max_workers), 6))
    if worker_count <= 1 or os.getenv(SHORTPICK_REPLAY_LLM_MODE_ENV, "real").strip().lower() in {
        "proxy",
        "deterministic_proxy",
        "off",
        "disabled",
    }:
        return run_shortpick_replay_distillation(
            session,
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            momentum_pool_limit=momentum_pool_limit,
            self_distill_limit=self_distill_limit,
            momentum_distill_limit=momentum_distill_limit,
        )

    runs = _completed_real_replay_runs(session, run_id=run_id, start_date=start_date, end_date=end_date)
    tasks: list[_ReplayDistillationTask] = []
    for run in runs:
        tasks.extend(
            _prepare_distillation_tasks_for_run(
                session,
                run=run,
                momentum_pool_limit=max(1, min(int(momentum_pool_limit), 40)),
                self_distill_limit=max(1, min(int(self_distill_limit), 10)),
                momentum_distill_limit=max(1, min(int(momentum_distill_limit), 10)),
            )
        )

    runs_by_id = {int(run.id): run for run in runs}
    expected_by_run: dict[int, int] = {}
    for task in tasks:
        expected_by_run[task.run_id] = expected_by_run.get(task.run_id, 0) + 1
    pending_by_run: dict[int, list[_ReplayDistillationResult]] = {}
    outputs: list[dict[str, Any]] = []
    failed_llm_count = 0
    with ThreadPoolExecutor(max_workers=min(worker_count, len(tasks) or 1)) as executor:
        futures = [executor.submit(_execute_replay_distillation_task, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            if result.error_message:
                failed_llm_count += 1
            run_results = pending_by_run.setdefault(result.task.run_id, [])
            run_results.append(result)
            if len(run_results) >= expected_by_run.get(result.task.run_id, 2):
                run = runs_by_id[result.task.run_id]
                outputs.append(
                    _persist_distillation_results_for_run(
                        session,
                        run=run,
                        results=run_results,
                        momentum_pool_limit=max(1, min(int(momentum_pool_limit), 40)),
                        self_distill_limit=max(1, min(int(self_distill_limit), 10)),
                        momentum_distill_limit=max(1, min(int(momentum_distill_limit), 10)),
                    )
                )
                session.commit()
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "execution_mode": "concurrent_llm_serial_db_writer",
        "distillation_mode": "llm_filtering",
        "llm_max_workers": worker_count,
        "run_count": len(outputs),
        "failed_llm_count": failed_llm_count,
        "runs": outputs,
        "config": {
            "momentum_pool_limit": momentum_pool_limit,
            "self_distill_limit": self_distill_limit,
            "momentum_distill_limit": momentum_distill_limit,
            "families": list(SHORTPICK_REPLAY_DISTILL_FAMILIES),
        },
    }


def run_shortpick_replay_rejection(
    session: Session,
    *,
    run_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    momentum_pool_limit: int = 40,
    rank_limit: int = 5,
    reject_max_ratio: float = 0.4,
) -> dict[str, Any]:
    query = (
        select(ShortpickExperimentRun)
        .where(
            ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE,
            ShortpickExperimentRun.status == "completed",
        )
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
    )
    if run_id is not None:
        query = query.where(ShortpickExperimentRun.id == run_id)
    if start_date is not None:
        query = query.where(ShortpickExperimentRun.run_date >= start_date)
    if end_date is not None:
        query = query.where(ShortpickExperimentRun.run_date <= end_date)
    runs = [run for run in session.scalars(query).all() if not _is_diagnostic_replay_run(run)]
    outputs: list[dict[str, Any]] = []
    normalized_pool_limit = max(1, min(int(momentum_pool_limit), 80))
    normalized_rank_limit = max(1, min(int(rank_limit), 20))
    normalized_reject_max_ratio = max(0.0, min(float(reject_max_ratio), 0.8))
    for run in runs:
        outputs.append(
            _reject_one_replay_run(
                session,
                run=run,
                momentum_pool_limit=normalized_pool_limit,
                rank_limit=normalized_rank_limit,
                reject_max_ratio=normalized_reject_max_ratio,
            )
        )
        session.commit()
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "rejection_mode": "llm_reject_then_mechanical_momentum_rank",
        "run_count": len(outputs),
        "runs": outputs,
        "config": {
            "momentum_pool_limit": normalized_pool_limit,
            "rank_limit": normalized_rank_limit,
            "reject_max_ratio": normalized_reject_max_ratio,
            "families": ["momentum_volume_expanded_pool", *SHORTPICK_REPLAY_REJECTION_FAMILIES],
        },
    }


def run_shortpick_replay_hard_veto_experiment(
    session: Session,
    *,
    run_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    momentum_pool_limit: int = 40,
    rank_limit: int = 6,
    veto_max_ratio: float = 0.15,
) -> dict[str, Any]:
    query = (
        select(ShortpickExperimentRun)
        .where(
            ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE,
            ShortpickExperimentRun.status == "completed",
        )
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
    )
    if run_id is not None:
        query = query.where(ShortpickExperimentRun.id == run_id)
    if start_date is not None:
        query = query.where(ShortpickExperimentRun.run_date >= start_date)
    if end_date is not None:
        query = query.where(ShortpickExperimentRun.run_date <= end_date)
    runs = [run for run in session.scalars(query).all() if not _is_diagnostic_replay_run(run)]
    outputs: list[dict[str, Any]] = []
    normalized_pool_limit = max(1, min(int(momentum_pool_limit), 80))
    normalized_rank_limit = max(1, min(int(rank_limit), 20))
    normalized_veto_max_ratio = max(0.0, min(float(veto_max_ratio), 0.4))
    for run in runs:
        outputs.append(
            _hard_veto_one_replay_run(
                session,
                run=run,
                momentum_pool_limit=normalized_pool_limit,
                rank_limit=normalized_rank_limit,
                veto_max_ratio=normalized_veto_max_ratio,
            )
        )
        session.commit()
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "rejection_mode": "llm_hard_veto_then_mechanical_momentum_rank",
        "run_count": len(outputs),
        "runs": outputs,
        "config": {
            "momentum_pool_limit": normalized_pool_limit,
            "rank_limit": normalized_rank_limit,
            "veto_max_ratio": normalized_veto_max_ratio,
            "families": list(SHORTPICK_REPLAY_HARD_VETO_FAMILIES),
            "strict_veto_categories": sorted(SHORTPICK_REPLAY_STRICT_VETO_CATEGORIES),
        },
    }


def run_shortpick_replay_factor_rank_experiment(
    session: Session,
    *,
    run_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    momentum_pool_limit: int = 40,
    rank_limit: int = 6,
) -> dict[str, Any]:
    query = (
        select(ShortpickExperimentRun)
        .where(
            ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE,
            ShortpickExperimentRun.status == "completed",
        )
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
    )
    if run_id is not None:
        query = query.where(ShortpickExperimentRun.id == run_id)
    if start_date is not None:
        query = query.where(ShortpickExperimentRun.run_date >= start_date)
    if end_date is not None:
        query = query.where(ShortpickExperimentRun.run_date <= end_date)
    runs = [run for run in session.scalars(query).all() if not _is_diagnostic_replay_run(run)]
    outputs: list[dict[str, Any]] = []
    normalized_pool_limit = max(6, min(int(momentum_pool_limit), 80))
    normalized_rank_limit = max(1, min(int(rank_limit), 20))
    for run in runs:
        outputs.append(
            _factor_rank_one_replay_run(
                session,
                run=run,
                momentum_pool_limit=normalized_pool_limit,
                rank_limit=normalized_rank_limit,
            )
        )
        session.commit()
    return {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "ranking_mode": "sealed_market_feature_rank",
        "run_count": len(outputs),
        "runs": outputs,
        "config": {
            "momentum_pool_limit": normalized_pool_limit,
            "rank_limit": normalized_rank_limit,
            "families": list(SHORTPICK_REPLAY_FACTOR_RANK_FAMILIES),
        },
    }


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
    normalized_limit = max(1, min(int(limit), 100))
    normalized_offset = max(0, int(offset))
    query = (
        select(ShortpickExperimentRun)
        .where(ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE)
        .order_by(ShortpickExperimentRun.run_date.desc(), ShortpickExperimentRun.id.desc())
    )
    if status:
        query = query.where(ShortpickExperimentRun.status == status)
    if date_from is not None:
        query = query.where(ShortpickExperimentRun.run_date >= date_from)
    if date_to is not None:
        query = query.where(ShortpickExperimentRun.run_date <= date_to)
    runs = [run for run in session.scalars(query).all() if not _is_diagnostic_replay_run(run)]
    items = [
        _serialize_replay_run_list_item(run, include_raw=include_raw)
        for run in runs[normalized_offset:normalized_offset + normalized_limit]
    ]
    return {"generated_at": utcnow(), "items": items, "total": len(runs), "limit": normalized_limit, "offset": normalized_offset}


def _serialize_replay_run_list_item(run: ShortpickExperimentRun, *, include_raw: bool) -> dict[str, Any]:
    summary = dict(run.summary_payload or {})
    source_packet = summary.get("source_packet")
    if isinstance(source_packet, dict):
        compact_packet = dict(source_packet)
        compact_packet.pop("official_sources", None)
        compact_packet.pop("diagnostic_sources", None)
        compact_packet.pop("rejected_sources", None)
        summary["source_packet"] = compact_packet
    summary.pop("replay_feedback", None)
    summary.setdefault("operational_status", run.status)
    return {
        "id": run.id,
        "run_key": run.run_key,
        "run_date": run.run_date,
        "prompt_version": run.prompt_version,
        "information_mode": run.information_mode,
        "status": run.status,
        "trigger_source": run.trigger_source,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "failed_at": run.failed_at,
        "model_config": dict(run.model_config or {}),
        "summary": summary,
        "rounds": [],
        "consensus": None,
        "candidates": [],
    }


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
    scope = _replay_feedback_scope(rows)
    horizon_groups = _replay_feedback_groups(rows, group_key="horizon")
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_family.setdefault(str(row["baseline_family"]), []).append(row)
    families = []
    for family, family_rows in sorted(by_family.items()):
        candidate_ids = {row["candidate_id"] for row in family_rows}
        official_candidate_ids = {row["candidate_id"] for row in family_rows if row["official_sample_eligible"]}
        tradable_candidate_ids = {row["candidate_id"] for row in family_rows if row["tradable_sample_eligible"]}
        completed_official_candidate_ids = {
            row["candidate_id"]
            for row in family_rows
            if row["official_sample_eligible"] and row["status"] == "completed"
        }
        completed_tradable_candidate_ids = {
            row["candidate_id"]
            for row in family_rows
            if row["tradable_sample_eligible"] and row["status"] == "completed"
        }
        families.append(
            {
                "baseline_family": family,
                "label": _baseline_label(family),
                "candidate_count": len(candidate_ids),
                "official_sample_count": len(official_candidate_ids),
                "tradable_sample_count": len(tradable_candidate_ids),
                "completed_official_sample_count": len(completed_official_candidate_ids),
                "completed_tradable_sample_count": len(completed_tradable_candidate_ids),
                "validation_by_horizon": _replay_feedback_groups(family_rows, group_key="horizon"),
                "robustness_metrics": _robustness_metrics(family_rows),
                "tradable_robustness_metrics": _robustness_metrics(
                    family_rows,
                    eligibility_key="tradable_sample_eligible",
                ),
            }
        )
    factor_ic_gate = _factor_ic_gate_readout(session)
    news_calibration = _news_calibration_readout(session)
    aggregate_projection = (
        {
            "regime_stability": _replay_regime_stability_projection(rows),
            "confidence_intervals": _replay_confidence_intervals(rows),
            "return_attribution": _replay_return_attribution(rows),
        }
        if run_id is None
        else {}
    )
    return {
        "generated_at": utcnow(),
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "run_id": run_id,
        "families": families,
        "overall": {
            **scope,
            "validation_count": len(rows),
            "completed_official_sample_count": len(
                [row for row in rows if row["official_sample_eligible"] and row["status"] == "completed"]
            ),
            "completed_tradable_sample_count": len(
                [row for row in rows if row["tradable_sample_eligible"] and row["status"] == "completed"]
            ),
            "baseline_families": list(SHORTPICK_REPLAY_BASELINE_FAMILIES),
            "validation_by_horizon": horizon_groups,
            "statistical_gate": _replay_statistical_gate(rows, horizon_groups),
            "robustness_metrics": _robustness_metrics(rows),
            "tradable_robustness_metrics": _robustness_metrics(rows, eligibility_key="tradable_sample_eligible"),
            "factor_ic_gate": factor_ic_gate,
            "news_calibration": news_calibration,
            **aggregate_projection,
        },
    }


def _account_profile_for_run(run: ShortpickExperimentRun) -> str:
    model_config = dict(run.model_config or {})
    summary = dict(run.summary_payload or {})
    profile = str(model_config.get("account_profile") or summary.get("account_profile") or ACCOUNT_PROFILE_NEW_RETAIL_CASH)
    return profile if profile in ACCOUNT_PROFILE_LABELS else ACCOUNT_PROFILE_NEW_RETAIL_CASH


def _build_universe(
    session: Session,
    *,
    as_of_date: date,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
) -> dict[str, Any]:
    members: list[_UniverseMember] = []
    excluded: dict[str, int] = {}
    excluded_account_examples: list[dict[str, Any]] = []
    stocks = session.scalars(select(Stock).order_by(Stock.symbol.asc())).all()
    for stock in stocks:
        if stock.listed_date and stock.listed_date > as_of_date:
            excluded["listed_after_as_of"] = excluded.get("listed_after_as_of", 0) + 1
            continue
        eligibility = account_trade_eligibility(stock.symbol, stock_profile=stock, account_profile=account_profile, as_of=as_of_date)
        if not eligibility["tradable"]:
            key = f"account_excluded_{eligibility['board']}"
            excluded[key] = excluded.get(key, 0) + 1
            if len(excluded_account_examples) < 12:
                excluded_account_examples.append(
                    {
                        "symbol": stock.symbol,
                        "name": stock.name,
                        "board_label": eligibility["board_label"],
                        "reason": eligibility["reason"],
                    }
                )
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
        market_cap, market_cap_source = _market_cap_for_universe_member(stock, latest)
        industry = _stock_industry(stock)
        members.append(
            _UniverseMember(
                symbol=stock.symbol,
                name=name,
                latest_bar=latest,
                previous_bar=bars[-2] if len(bars) >= 2 else None,
                market_cap=float(market_cap) if market_cap is not None else None,
                market_cap_source=market_cap_source,
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
            "account_profile": account_profile,
            "account_profile_label": ACCOUNT_PROFILE_LABELS.get(account_profile, account_profile),
            "universe_count": len(stocks),
            "total_count": len(stocks),
            "tradeable_count": len(members),
            "excluded_counts": excluded,
            "excluded_count": sum(excluded.values()),
            "excluded_account_examples": excluded_account_examples,
            "excluded_st": excluded.get("st_status", 0),
            "excluded_suspended": excluded.get("suspended", 0),
            "excluded_limit_status": excluded.get("limit_status", 0),
            "account_rule_note": "新开户普通现金账户口径仅纳入沪深主板普通A股；排除科创板、创业板、北交所、ST/退市风险类标的。",
            "excluded_missing_bar": excluded.get("missing_daily_bar", 0) + excluded.get("no_bar_on_as_of_date", 0),
            "market_cap_bucket_counts": _count_by([member.market_cap_bucket for member in members]),
            "market_cap_available_count": len([member for member in members if member.market_cap is not None]),
            "market_cap_source_counts": _count_by([member.market_cap_source for member in members]),
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
            "body_excerpt": _source_excerpt(item.content_excerpt or item.summary),
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
    llm_limit = min(rounds, candidate_limit)
    round_record, llm_picks = _insert_replay_llm_round(
        session,
        run=run,
        packet=packet,
        universe=universe,
        limit=llm_limit,
    )
    for index, pick in enumerate(llm_picks, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=round_record,
            symbol=str(pick["symbol"]),
            baseline_family="llm",
            rank=index,
            packet=packet,
            universe=universe,
            llm_pick=pick,
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


def _completed_real_replay_runs(
    session: Session,
    *,
    run_id: int | None,
    start_date: date | None,
    end_date: date | None,
) -> list[ShortpickExperimentRun]:
    query = (
        select(ShortpickExperimentRun)
        .where(
            ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE,
            ShortpickExperimentRun.status == "completed",
        )
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
    )
    if run_id is not None:
        query = query.where(ShortpickExperimentRun.id == run_id)
    if start_date is not None:
        query = query.where(ShortpickExperimentRun.run_date >= start_date)
    if end_date is not None:
        query = query.where(ShortpickExperimentRun.run_date <= end_date)
    return [run for run in session.scalars(query).all() if not _is_diagnostic_replay_run(run)]


def _prepare_distillation_tasks_for_run(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    momentum_pool_limit: int,
    self_distill_limit: int,
    momentum_distill_limit: int,
) -> list[_ReplayDistillationTask]:
    packet = _load_replay_packet(session, run)
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=_account_profile_for_run(run))
    llm_symbols = _candidate_symbols(session, run.id, family="llm")
    momentum_symbols = _momentum_symbols(universe, limit=momentum_pool_limit)
    specs = [
        (
            "llm",
            "llm_self_distilled",
            "historical_replay_llm_self_distiller",
            llm_symbols,
            min(self_distill_limit, len(llm_symbols)),
            2,
        ),
        (
            "momentum_volume_expanded_pool",
            "llm_momentum_distilled",
            "historical_replay_momentum_pool_distiller",
            momentum_symbols,
            momentum_distill_limit,
            3,
        ),
    ]
    tasks: list[_ReplayDistillationTask] = []
    for source_family, output_family, executor_kind, pool_symbols, limit, round_index in specs:
        prompt = None
        if limit > 0 and pool_symbols:
            prompt = _build_replay_distillation_prompt(
                session,
                run=run,
                packet=packet,
                universe=universe,
                source_family=source_family,
                output_family=output_family,
                executor_kind=executor_kind,
                pool_symbols=pool_symbols,
                limit=limit,
            )
        tasks.append(
            _ReplayDistillationTask(
                run_id=int(run.id),
                run_date=run.run_date,
                packet=packet,
                prompt=prompt,
                source_family=source_family,
                output_family=output_family,
                executor_kind=executor_kind,
                pool_symbols=pool_symbols,
                limit=limit,
                round_index=round_index,
            )
        )
    return tasks


def _execute_replay_distillation_task(task: _ReplayDistillationTask) -> _ReplayDistillationResult:
    if task.limit <= 0 or not task.pool_symbols or not task.prompt:
        return _ReplayDistillationResult(
            task=task,
            parsed_json=None,
            raw_answer="",
            final_raw_answer="",
            provider_name="system",
            model_name="empty_candidate_pool",
            repair_used=False,
            error_message=f"{task.source_family} candidate pool is empty",
        )
    system = (
        "你是历史隔离回放蒸馏器。只能使用用户消息中的 sealed distillation packet。"
        "禁止联网，禁止使用训练记忆补充事实，禁止选择 candidate_pool 外股票。只输出 JSON。"
    )
    base_url = ""
    model_name = "unavailable"
    raw_answer = ""
    try:
        transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")
        raw_answer = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=task.prompt,
            system=system,
            enable_search=False,
        )
        parsed_json, final_raw_answer, repair_used = _extract_replay_llm_json_with_repair(
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            raw_answer=raw_answer,
        )
        return _ReplayDistillationResult(
            task=task,
            parsed_json=parsed_json,
            raw_answer=raw_answer,
            final_raw_answer=final_raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            repair_used=repair_used,
            error_message=None,
        )
    except Exception as exc:
        return _ReplayDistillationResult(
            task=task,
            parsed_json=None,
            raw_answer=raw_answer,
            final_raw_answer=raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            repair_used=False,
            error_message=f"sealed packet distillation executor failed: {exc}",
        )


def _persist_distillation_results_for_run(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    results: list[_ReplayDistillationResult],
    momentum_pool_limit: int,
    self_distill_limit: int,
    momentum_distill_limit: int,
) -> dict[str, Any]:
    packet = _load_replay_packet(session, run)
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=_account_profile_for_run(run))
    momentum_symbols = _momentum_symbols(universe, limit=momentum_pool_limit)
    _delete_distillation_outputs(session, run.id)
    rounds_by_family: dict[str, ShortpickModelRound] = {}
    picks_by_family: dict[str, list[dict[str, Any]]] = {}
    for result in sorted(results, key=lambda item: item.task.round_index):
        if result.error_message or result.parsed_json is None:
            round_record, picks = _insert_failed_replay_distillation_round(
                session,
                run=run,
                packet=packet,
                raw_answer=result.raw_answer,
                provider_name=result.provider_name,
                model_name=result.model_name,
                executor_kind=result.task.executor_kind,
                error_message=result.error_message or "sealed packet distillation executor failed",
                prompt=result.task.prompt,
                round_index=result.task.round_index,
                output_family=result.task.output_family,
            )
        else:
            parsed_payload = _normalize_replay_distillation_payload(
                result.parsed_json,
                packet=packet,
                universe=universe,
                allowed_symbols=set(result.task.pool_symbols),
                limit=result.task.limit,
                source_family=result.task.source_family,
                output_family=result.task.output_family,
            )
            parsed_payload["_json_repair_used"] = result.repair_used
            round_record = _insert_replay_round_record(
                session,
                run=run,
                packet=packet,
                parsed_payload=parsed_payload,
                raw_answer=result.final_raw_answer,
                provider_name=result.provider_name,
                model_name=result.model_name,
                executor_kind=result.task.executor_kind,
                error_message=None,
                prompt=result.task.prompt,
                round_index=result.task.round_index,
            )
            picks = list(parsed_payload.get("candidates") or [])
        rounds_by_family[result.task.output_family] = round_record
        picks_by_family[result.task.output_family] = picks

    for index, symbol in enumerate(momentum_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=None,
            symbol=symbol,
            baseline_family="momentum_volume_expanded_pool",
            rank=index,
            packet=packet,
            universe=universe,
        )
    for family in ("llm_self_distilled", "llm_momentum_distilled"):
        for index, pick in enumerate(picks_by_family.get(family, []), start=1):
            _insert_candidate(
                session,
                run=run,
                round_record=rounds_by_family.get(family),
                symbol=str(pick["symbol"]),
                baseline_family=family,
                rank=index,
                packet=packet,
                universe=universe,
                llm_pick=pick,
            )

    session.flush()
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    candidate_counts = _distillation_candidate_counts(session, run.id)
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        "distillation": {
            "status": "completed",
            "momentum_pool_limit": momentum_pool_limit,
            "self_distill_limit": self_distill_limit,
            "momentum_distill_limit": momentum_distill_limit,
            "families": list(SHORTPICK_REPLAY_DISTILL_FAMILIES),
            "candidate_counts": candidate_counts,
            "execution_mode": "concurrent_llm_serial_db_writer",
            "completed_at": utcnow().isoformat(),
        },
    }
    session.flush()
    return {
        "run_id": run.id,
        "run_date": run.run_date.isoformat(),
        "self_distilled_count": len(picks_by_family.get("llm_self_distilled", [])),
        "momentum_distilled_count": len(picks_by_family.get("llm_momentum_distilled", [])),
        "expanded_momentum_count": len(momentum_symbols),
        "candidate_counts": candidate_counts,
        "validation": validation_result,
    }


def _distill_one_replay_run(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    momentum_pool_limit: int,
    self_distill_limit: int,
    momentum_distill_limit: int,
) -> dict[str, Any]:
    packet = _load_replay_packet(session, run)
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=_account_profile_for_run(run))
    llm_symbols = _candidate_symbols(session, run.id, family="llm")
    momentum_symbols = _momentum_symbols(universe, limit=momentum_pool_limit)

    self_round, self_picks = _insert_replay_distillation_round(
        session,
        run=run,
        packet=packet,
        universe=universe,
        source_family="llm",
        output_family="llm_self_distilled",
        executor_kind="historical_replay_llm_self_distiller",
        round_index=2,
        pool_symbols=llm_symbols,
        limit=min(self_distill_limit, len(llm_symbols)),
    )
    session.commit()

    momentum_round, momentum_picks = _insert_replay_distillation_round(
        session,
        run=run,
        packet=packet,
        universe=universe,
        source_family="momentum_volume_expanded_pool",
        output_family="llm_momentum_distilled",
        executor_kind="historical_replay_momentum_pool_distiller",
        round_index=3,
        pool_symbols=momentum_symbols,
        limit=momentum_distill_limit,
    )
    session.commit()

    _delete_distillation_outputs(session, run.id, preserve_round_ids=[self_round.id, momentum_round.id])
    session.commit()

    for index, symbol in enumerate(momentum_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=None,
            symbol=symbol,
            baseline_family="momentum_volume_expanded_pool",
            rank=index,
            packet=packet,
            universe=universe,
        )
    for index, pick in enumerate(self_picks, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=self_round,
            symbol=str(pick["symbol"]),
            baseline_family="llm_self_distilled",
            rank=index,
            packet=packet,
            universe=universe,
            llm_pick=pick,
        )
    for index, pick in enumerate(momentum_picks, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=momentum_round,
            symbol=str(pick["symbol"]),
            baseline_family="llm_momentum_distilled",
            rank=index,
            packet=packet,
            universe=universe,
            llm_pick=pick,
        )

    session.flush()
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    candidate_counts = _distillation_candidate_counts(session, run.id)
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        "distillation": {
            "status": "completed",
            "momentum_pool_limit": momentum_pool_limit,
            "self_distill_limit": self_distill_limit,
            "momentum_distill_limit": momentum_distill_limit,
            "families": list(SHORTPICK_REPLAY_DISTILL_FAMILIES),
            "candidate_counts": candidate_counts,
            "completed_at": utcnow().isoformat(),
        },
    }
    session.flush()
    return {
        "run_id": run.id,
        "run_date": run.run_date.isoformat(),
        "self_distilled_count": len(self_picks),
        "momentum_distilled_count": len(momentum_picks),
        "expanded_momentum_count": len(momentum_symbols),
        "candidate_counts": candidate_counts,
        "validation": validation_result,
    }


def _reject_one_replay_run(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    momentum_pool_limit: int,
    rank_limit: int,
    reject_max_ratio: float,
) -> dict[str, Any]:
    packet = _load_replay_packet(session, run)
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=_account_profile_for_run(run))
    momentum_symbols = _momentum_symbols(universe, limit=momentum_pool_limit)

    _delete_rejection_outputs(session, run.id, refresh_expanded_pool=True)
    session.commit()

    reject_round, decisions = _insert_replay_rejection_round(
        session,
        run=run,
        packet=packet,
        universe=universe,
        executor_kind="historical_replay_momentum_pool_rejector",
        round_index=4,
        pool_symbols=momentum_symbols,
        reject_max_ratio=reject_max_ratio,
    )
    session.commit()

    decision_by_symbol = {str(item["symbol"]): item for item in decisions}
    rejected_symbols = [symbol for symbol in momentum_symbols if decision_by_symbol.get(symbol, {}).get("decision") == "reject"]
    kept_symbols = [symbol for symbol in momentum_symbols if symbol not in set(rejected_symbols)]
    top_kept_symbols = kept_symbols[:rank_limit]
    random_rejected_symbols = _deterministic_random_rejections(
        run=run,
        symbols=momentum_symbols,
        reject_count=len(rejected_symbols),
    )
    random_kept_symbols = [symbol for symbol in momentum_symbols if symbol not in set(random_rejected_symbols)]
    random_top_symbols = random_kept_symbols[:rank_limit]

    for index, symbol in enumerate(momentum_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=None,
            symbol=symbol,
            baseline_family="momentum_volume_expanded_pool",
            rank=index,
            packet=packet,
            universe=universe,
        )
    for index, symbol in enumerate(kept_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=reject_round,
            symbol=symbol,
            baseline_family="llm_reject_only",
            rank=index,
            packet=packet,
            universe=universe,
            llm_pick=_rejection_pick_payload(
                universe=universe,
                symbol=symbol,
                family="llm_reject_only",
                decision=decision_by_symbol.get(symbol),
                original_rank=momentum_symbols.index(symbol) + 1,
                derived_rank=index,
            ),
        )
    for index, symbol in enumerate(top_kept_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=reject_round,
            symbol=symbol,
            baseline_family="llm_reject_then_momentum_rank",
            rank=index,
            packet=packet,
            universe=universe,
            llm_pick=_rejection_pick_payload(
                universe=universe,
                symbol=symbol,
                family="llm_reject_then_momentum_rank",
                decision=decision_by_symbol.get(symbol),
                original_rank=momentum_symbols.index(symbol) + 1,
                derived_rank=index,
            ),
        )
    for index, symbol in enumerate(random_top_symbols, start=1):
        _insert_candidate(
            session,
            run=run,
            round_record=None,
            symbol=symbol,
            baseline_family="random_reject_then_momentum_rank",
            rank=index,
            packet=packet,
            universe=universe,
            llm_pick=_random_rejection_pick_payload(
                universe=universe,
                symbol=symbol,
                original_rank=momentum_symbols.index(symbol) + 1,
                derived_rank=index,
                random_rejected_symbols=random_rejected_symbols,
            ),
        )

    session.flush()
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    candidate_counts = _rejection_candidate_counts(session, run.id)
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        "rejection_distillation": {
            "status": "completed",
            "momentum_pool_limit": momentum_pool_limit,
            "rank_limit": rank_limit,
            "reject_max_ratio": reject_max_ratio,
            "rejected_count": len(rejected_symbols),
            "random_rejected_count": len(random_rejected_symbols),
            "families": ["momentum_volume_expanded_pool", *SHORTPICK_REPLAY_REJECTION_FAMILIES],
            "candidate_counts": candidate_counts,
            "completed_at": utcnow().isoformat(),
        },
    }
    session.flush()
    return {
        "run_id": run.id,
        "run_date": run.run_date.isoformat(),
        "expanded_momentum_count": len(momentum_symbols),
        "llm_rejected_count": len(rejected_symbols),
        "llm_reject_only_count": len(kept_symbols),
        "llm_reject_then_momentum_rank_count": len(top_kept_symbols),
        "random_reject_then_momentum_rank_count": len(random_top_symbols),
        "candidate_counts": candidate_counts,
        "validation": validation_result,
    }


def _hard_veto_one_replay_run(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    momentum_pool_limit: int,
    rank_limit: int,
    veto_max_ratio: float,
) -> dict[str, Any]:
    packet = _load_replay_packet(session, run)
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=_account_profile_for_run(run))
    momentum_symbols = _momentum_symbols(universe, limit=momentum_pool_limit)

    _delete_hard_veto_outputs(session, run.id)
    session.commit()

    veto_round, decisions = _insert_replay_hard_veto_round(
        session,
        run=run,
        packet=packet,
        universe=universe,
        pool_symbols=momentum_symbols,
        veto_max_ratio=veto_max_ratio,
    )
    session.commit()

    decision_by_symbol = {str(item["symbol"]): item for item in decisions}
    hard_vetoed = [symbol for symbol in momentum_symbols if decision_by_symbol.get(symbol, {}).get("decision") == "reject"]
    strict_vetoed = [
        symbol
        for symbol in hard_vetoed
        if str(decision_by_symbol.get(symbol, {}).get("reason_category") or "") in SHORTPICK_REPLAY_STRICT_VETO_CATEGORIES
    ]
    hard_symbols = [symbol for symbol in momentum_symbols if symbol not in set(hard_vetoed)][:rank_limit]
    strict_symbols = [symbol for symbol in momentum_symbols if symbol not in set(strict_vetoed)][:rank_limit]
    random_hard_rejected = _deterministic_random_rejections(run=run, symbols=momentum_symbols, reject_count=len(hard_vetoed))
    random_strict_rejected = _deterministic_random_rejections(
        run=run,
        symbols=momentum_symbols,
        reject_count=len(strict_vetoed),
        salt="random_strict_veto_then_momentum_rank",
    )
    random_hard_symbols = [symbol for symbol in momentum_symbols if symbol not in set(random_hard_rejected)][:rank_limit]
    random_strict_symbols = [symbol for symbol in momentum_symbols if symbol not in set(random_strict_rejected)][:rank_limit]

    for family, symbols, random_rejected in (
        ("llm_hard_veto_then_momentum_rank", hard_symbols, None),
        ("random_hard_veto_then_momentum_rank", random_hard_symbols, random_hard_rejected),
        ("llm_strict_veto_then_momentum_rank", strict_symbols, None),
        ("random_strict_veto_then_momentum_rank", random_strict_symbols, random_strict_rejected),
    ):
        for index, symbol in enumerate(symbols, start=1):
            original_rank = momentum_symbols.index(symbol) + 1
            if random_rejected is None:
                decision = decision_by_symbol.get(symbol)
                if family == "llm_strict_veto_then_momentum_rank":
                    decision = _strict_veto_retained_decision(decision)
                pick = _rejection_pick_payload(
                    universe=universe,
                    symbol=symbol,
                    family=family,
                    decision=decision,
                    original_rank=original_rank,
                    derived_rank=index,
                )
                round_record = veto_round
            else:
                pick = _random_rejection_pick_payload(
                    universe=universe,
                    symbol=symbol,
                    original_rank=original_rank,
                    derived_rank=index,
                    random_rejected_symbols=random_rejected,
                )
                round_record = None
            _insert_candidate(
                session,
                run=run,
                round_record=round_record,
                symbol=symbol,
                baseline_family=family,
                rank=index,
                packet=packet,
                universe=universe,
                llm_pick=pick,
            )

    session.flush()
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    candidate_counts = _hard_veto_candidate_counts(session, run.id)
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        "hard_veto_experiment": {
            "status": "completed",
            "momentum_pool_limit": momentum_pool_limit,
            "rank_limit": rank_limit,
            "veto_max_ratio": veto_max_ratio,
            "hard_vetoed_count": len(hard_vetoed),
            "strict_vetoed_count": len(strict_vetoed),
            "families": list(SHORTPICK_REPLAY_HARD_VETO_FAMILIES),
            "candidate_counts": candidate_counts,
            "completed_at": utcnow().isoformat(),
        },
    }
    session.flush()
    return {
        "run_id": run.id,
        "run_date": run.run_date.isoformat(),
        "hard_vetoed_count": len(hard_vetoed),
        "strict_vetoed_count": len(strict_vetoed),
        "candidate_counts": candidate_counts,
        "validation": validation_result,
    }


def _factor_rank_one_replay_run(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    momentum_pool_limit: int,
    rank_limit: int,
) -> dict[str, Any]:
    packet = _load_replay_packet(session, run)
    universe = _build_universe(session, as_of_date=run.run_date, account_profile=_account_profile_for_run(run))
    momentum_symbols = _momentum_symbols(universe, limit=momentum_pool_limit)

    _delete_factor_rank_outputs(session, run.id)
    ranked = _factor_ranked_symbols(
        session,
        run=run,
        universe=universe,
        pool_symbols=momentum_symbols,
    )
    for family, symbols in ranked.items():
        for index, symbol in enumerate(symbols[:rank_limit], start=1):
            original_rank = momentum_symbols.index(symbol) + 1 if symbol in momentum_symbols else index
            pick = _factor_rank_pick_payload(
                session,
                run=run,
                universe=universe,
                symbol=symbol,
                family=family,
                original_rank=original_rank,
                derived_rank=index,
            )
            _insert_candidate(
                session,
                run=run,
                round_record=None,
                symbol=symbol,
                baseline_family=family,
                rank=index,
                packet=packet,
                universe=universe,
                llm_pick=pick,
            )

    session.flush()
    validation_result = validate_historical_replay_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    candidate_counts = _factor_rank_candidate_counts(session, run.id)
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        "factor_rank_experiment": {
            "status": "completed",
            "momentum_pool_limit": momentum_pool_limit,
            "rank_limit": rank_limit,
            "families": list(SHORTPICK_REPLAY_FACTOR_RANK_FAMILIES),
            "candidate_counts": candidate_counts,
            "completed_at": utcnow().isoformat(),
        },
    }
    session.flush()
    return {
        "run_id": run.id,
        "run_date": run.run_date.isoformat(),
        "candidate_counts": candidate_counts,
        "validation": validation_result,
    }


def _load_replay_packet(session: Session, run: ShortpickExperimentRun) -> dict[str, Any]:
    packet_id = str((run.summary_payload or {}).get("source_packet_id") or "")
    artifact = read_shortpick_lab_artifact_if_exists(packet_id, root=_artifact_root(session)) if packet_id else None
    if isinstance(artifact, dict) and artifact.get("official_sources") is not None:
        return artifact
    source_packet = dict((run.summary_payload or {}).get("source_packet") or {})
    if source_packet.get("official_sources") is not None:
        return {
            "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
            "as_of_date": run.run_date.isoformat(),
            "as_of_cutoff": (run.summary_payload or {}).get("as_of_cutoff"),
            "source_packet_id": source_packet.get("source_packet_id") or packet_id,
            "source_packet_hash": source_packet.get("source_packet_hash"),
            "official_sources": source_packet.get("official_sources") or [],
            "diagnostic_sources": source_packet.get("diagnostic_sources") or [],
            "rejected_sources": source_packet.get("rejected_sources") or [],
            "tradable_universe": (run.summary_payload or {}).get("tradable_universe") or {},
        }
    raise LookupError(f"Replay source packet artifact not found for run {run.id}.")


def _candidate_symbols(session: Session, run_id: int, *, family: str) -> list[str]:
    rows = session.scalars(
        select(ShortpickCandidate)
        .where(ShortpickCandidate.run_id == run_id)
        .order_by(ShortpickCandidate.id.asc())
    ).all()
    symbols: list[str] = []
    for candidate in rows:
        if _candidate_baseline_family(candidate) != family:
            continue
        if candidate.symbol not in symbols:
            symbols.append(candidate.symbol)
    return symbols


def _delete_distillation_outputs(session: Session, run_id: int, *, preserve_round_ids: list[int] | None = None) -> None:
    preserve_ids = set(preserve_round_ids or [])
    candidate_ids = [
        candidate.id
        for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
        if _candidate_baseline_family(candidate) in SHORTPICK_REPLAY_DISTILL_FAMILIES
    ]
    if candidate_ids:
        session.execute(delete(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids)))
        session.execute(delete(ShortpickCandidate).where(ShortpickCandidate.id.in_(candidate_ids)))
    round_delete = delete(ShortpickModelRound).where(
        ShortpickModelRound.run_id == run_id,
        ShortpickModelRound.executor_kind.in_(SHORTPICK_REPLAY_DISTILL_EXECUTORS),
    )
    if preserve_ids:
        round_delete = round_delete.where(ShortpickModelRound.id.not_in(preserve_ids))
    session.execute(round_delete)
    session.flush()


def _delete_rejection_outputs(session: Session, run_id: int, *, refresh_expanded_pool: bool) -> None:
    families = set(SHORTPICK_REPLAY_REJECTION_FAMILIES)
    if refresh_expanded_pool:
        families.add("momentum_volume_expanded_pool")
    candidate_ids = [
        candidate.id
        for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
        if _candidate_baseline_family(candidate) in families
    ]
    if candidate_ids:
        session.execute(delete(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids)))
        session.execute(delete(ShortpickCandidate).where(ShortpickCandidate.id.in_(candidate_ids)))
    session.execute(
        delete(ShortpickModelRound).where(
            ShortpickModelRound.run_id == run_id,
            ShortpickModelRound.executor_kind.in_(SHORTPICK_REPLAY_REJECTION_EXECUTORS),
        )
    )
    session.flush()


def _delete_hard_veto_outputs(session: Session, run_id: int) -> None:
    candidate_ids = [
        candidate.id
        for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
        if _candidate_baseline_family(candidate) in SHORTPICK_REPLAY_HARD_VETO_FAMILIES
    ]
    if candidate_ids:
        session.execute(delete(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids)))
        session.execute(delete(ShortpickCandidate).where(ShortpickCandidate.id.in_(candidate_ids)))
    session.execute(
        delete(ShortpickModelRound).where(
            ShortpickModelRound.run_id == run_id,
            ShortpickModelRound.executor_kind.in_(SHORTPICK_REPLAY_HARD_VETO_EXECUTORS),
        )
    )
    session.flush()


def _delete_factor_rank_outputs(session: Session, run_id: int) -> None:
    candidate_ids = [
        candidate.id
        for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all()
        if _candidate_baseline_family(candidate) in SHORTPICK_REPLAY_FACTOR_RANK_FAMILIES
    ]
    if candidate_ids:
        session.execute(delete(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids)))
        session.execute(delete(ShortpickCandidate).where(ShortpickCandidate.id.in_(candidate_ids)))
    session.flush()


def _distillation_candidate_counts(session: Session, run_id: int) -> dict[str, int]:
    counts = dict.fromkeys(SHORTPICK_REPLAY_DISTILL_FAMILIES, 0)
    for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all():
        family = _candidate_baseline_family(candidate)
        if family in counts:
            counts[family] += 1
    return counts


def _rejection_candidate_counts(session: Session, run_id: int) -> dict[str, int]:
    counts = dict.fromkeys(("momentum_volume_expanded_pool", *SHORTPICK_REPLAY_REJECTION_FAMILIES), 0)
    for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all():
        family = _candidate_baseline_family(candidate)
        if family in counts:
            counts[family] += 1
    return counts


def _hard_veto_candidate_counts(session: Session, run_id: int) -> dict[str, int]:
    counts = dict.fromkeys(SHORTPICK_REPLAY_HARD_VETO_FAMILIES, 0)
    for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all():
        family = _candidate_baseline_family(candidate)
        if family in counts:
            counts[family] += 1
    return counts


def _factor_rank_candidate_counts(session: Session, run_id: int) -> dict[str, int]:
    counts = dict.fromkeys(SHORTPICK_REPLAY_FACTOR_RANK_FAMILIES, 0)
    for candidate in session.scalars(select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id)).all():
        family = _candidate_baseline_family(candidate)
        if family in counts:
            counts[family] += 1
    return counts


def _insert_replay_llm_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    limit: int,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    mode = os.getenv(SHORTPICK_REPLAY_LLM_MODE_ENV, "real").strip().lower()
    if mode in {"proxy", "deterministic_proxy", "off", "disabled"}:
        return _insert_replay_proxy_round(
            session,
            run=run,
            packet=packet,
            universe=universe,
            limit=limit,
            reason=f"{SHORTPICK_REPLAY_LLM_MODE_ENV}={mode}",
        )
    prompt = _build_replay_llm_prompt(run=run, packet=packet, universe=universe, limit=limit)
    system = (
        "你是历史隔离回放执行器。只能使用用户消息中的 sealed source packet 和 tradeable universe。"
        "禁止联网，禁止使用训练记忆补充事实，禁止引用 packet 外 URL。只输出 JSON。"
    )
    base_url = ""
    model_name = "unavailable"
    raw_answer = ""
    try:
        transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")
        raw_answer = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            system=system,
            enable_search=False,
        )
        parsed_json, final_raw_answer, repair_used = _extract_replay_rejection_json_with_partial_repair(
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            raw_answer=raw_answer,
        )
        parsed_payload = _normalize_replay_llm_payload(
            parsed_json,
            packet=packet,
            universe=universe,
            limit=limit,
        )
        parsed_payload["_json_repair_used"] = repair_used
        round_record = _insert_replay_round_record(
            session,
            run=run,
            packet=packet,
            parsed_payload=parsed_payload,
            raw_answer=final_raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind="historical_replay_sealed_packet_llm",
            error_message=None,
            prompt=prompt,
        )
        return round_record, list(parsed_payload.get("candidates") or [])
    except Exception as exc:
        return _insert_failed_replay_llm_round(
            session,
            run=run,
            packet=packet,
            raw_answer=raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            error_message=f"sealed packet LLM executor failed: {exc}",
            prompt=prompt,
        )


def _insert_replay_distillation_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    source_family: str,
    output_family: str,
    executor_kind: str,
    round_index: int,
    pool_symbols: list[str],
    limit: int,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    if limit <= 0 or not pool_symbols:
        return _insert_failed_replay_distillation_round(
            session,
            run=run,
            packet=packet,
            raw_answer="",
            provider_name="system",
            model_name="empty_candidate_pool",
            executor_kind=executor_kind,
            error_message=f"{source_family} candidate pool is empty",
            prompt=None,
            round_index=round_index,
            output_family=output_family,
        )
    prompt = _build_replay_distillation_prompt(
        session,
        run=run,
        packet=packet,
        universe=universe,
        source_family=source_family,
        output_family=output_family,
        executor_kind=executor_kind,
        pool_symbols=pool_symbols,
        limit=limit,
    )
    system = (
        "你是历史隔离回放蒸馏器。只能使用用户消息中的 sealed distillation packet。"
        "禁止联网，禁止使用训练记忆补充事实，禁止选择 candidate_pool 外股票。只输出 JSON。"
    )
    base_url = ""
    model_name = "unavailable"
    raw_answer = ""
    try:
        transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")
        raw_answer = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            system=system,
            enable_search=False,
        )
        parsed_json, final_raw_answer, repair_used = _extract_replay_llm_json_with_repair(
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            raw_answer=raw_answer,
        )
        parsed_payload = _normalize_replay_distillation_payload(
            parsed_json,
            packet=packet,
            universe=universe,
            allowed_symbols=set(pool_symbols),
            limit=limit,
            source_family=source_family,
            output_family=output_family,
        )
        parsed_payload["_json_repair_used"] = repair_used
        round_record = _insert_replay_round_record(
            session,
            run=run,
            packet=packet,
            parsed_payload=parsed_payload,
            raw_answer=final_raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind=executor_kind,
            error_message=None,
            prompt=prompt,
            round_index=round_index,
        )
        return round_record, list(parsed_payload.get("candidates") or [])
    except Exception as exc:
        return _insert_failed_replay_distillation_round(
            session,
            run=run,
            packet=packet,
            raw_answer=raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind=executor_kind,
            error_message=f"sealed packet distillation executor failed: {exc}",
            prompt=prompt,
            round_index=round_index,
            output_family=output_family,
        )


def _insert_replay_rejection_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    executor_kind: str,
    round_index: int,
    pool_symbols: list[str],
    reject_max_ratio: float,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    if not pool_symbols:
        return _insert_failed_replay_distillation_round(
            session,
            run=run,
            packet=packet,
            raw_answer="",
            provider_name="system",
            model_name="empty_candidate_pool",
            executor_kind=executor_kind,
            error_message="momentum candidate pool is empty",
            prompt=None,
            round_index=round_index,
            output_family="llm_reject_only",
        )
    prompt = _build_replay_rejection_prompt(
        session,
        run=run,
        packet=packet,
        universe=universe,
        pool_symbols=pool_symbols,
        reject_max_ratio=reject_max_ratio,
    )
    system = (
        "你是历史隔离回放剔除器。只能使用用户消息中的 sealed rejection packet。"
        "禁止联网，禁止使用训练记忆补充事实，禁止输出 candidate_pool 外股票。只输出 JSON。"
    )
    base_url = ""
    model_name = "unavailable"
    raw_answer = ""
    try:
        transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")
        raw_answer = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            system=system,
            enable_search=False,
        )
        parsed_json, final_raw_answer, repair_used = _extract_replay_llm_json_with_repair(
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            raw_answer=raw_answer,
        )
        parsed_payload = _normalize_replay_rejection_payload(
            parsed_json,
            packet=packet,
            universe=universe,
            pool_symbols=pool_symbols,
            reject_max_ratio=reject_max_ratio,
        )
        parsed_payload["_json_repair_used"] = repair_used
        round_record = _insert_replay_round_record(
            session,
            run=run,
            packet=packet,
            parsed_payload=parsed_payload,
            raw_answer=final_raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind=executor_kind,
            error_message=None,
            prompt=prompt,
            round_index=round_index,
        )
        return round_record, list(parsed_payload.get("decisions") or [])
    except Exception as exc:
        return _insert_failed_replay_distillation_round(
            session,
            run=run,
            packet=packet,
            raw_answer=raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind=executor_kind,
            error_message=f"sealed packet rejection executor failed: {exc}",
            prompt=prompt,
            round_index=round_index,
            output_family="llm_reject_only",
        )


def _insert_replay_hard_veto_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    pool_symbols: list[str],
    veto_max_ratio: float,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    if not pool_symbols:
        return _insert_failed_replay_distillation_round(
            session,
            run=run,
            packet=packet,
            raw_answer="",
            provider_name="system",
            model_name="empty_candidate_pool",
            executor_kind="historical_replay_momentum_pool_hard_veto",
            error_message="momentum candidate pool is empty",
            prompt=None,
            round_index=5,
            output_family="llm_hard_veto_then_momentum_rank",
        )
    prompt = _build_replay_hard_veto_prompt(
        session,
        run=run,
        packet=packet,
        universe=universe,
        pool_symbols=pool_symbols,
        veto_max_ratio=veto_max_ratio,
    )
    system = (
        "你是历史隔离回放硬否决审计器。只能使用用户消息中的 sealed hard-veto packet。"
        "禁止联网，禁止使用训练记忆补充事实，禁止输出 candidate_pool 外股票。只输出 JSON。"
    )
    base_url = ""
    model_name = "unavailable"
    raw_answer = ""
    try:
        transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")
        raw_answer = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            system=system,
            enable_search=False,
        )
        parsed_json, final_raw_answer, repair_used = _extract_replay_rejection_json_with_partial_repair(
            transport=transport,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            raw_answer=raw_answer,
        )
        parsed_payload = _normalize_replay_rejection_payload(
            parsed_json,
            packet=packet,
            universe=universe,
            pool_symbols=pool_symbols,
            reject_max_ratio=veto_max_ratio,
        )
        parsed_payload["rejection_mode"] = "hard_veto_only"
        parsed_payload["_json_repair_used"] = repair_used
        round_record = _insert_replay_round_record(
            session,
            run=run,
            packet=packet,
            parsed_payload=parsed_payload,
            raw_answer=final_raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind="historical_replay_momentum_pool_hard_veto",
            error_message=None,
            prompt=prompt,
            round_index=5,
        )
        return round_record, list(parsed_payload.get("decisions") or [])
    except Exception as exc:
        return _insert_failed_replay_distillation_round(
            session,
            run=run,
            packet=packet,
            raw_answer=raw_answer,
            provider_name=_provider_name_from_base_url(base_url),
            model_name=model_name,
            executor_kind="historical_replay_momentum_pool_hard_veto",
            error_message=f"sealed packet hard-veto executor failed: {exc}",
            prompt=prompt,
            round_index=5,
            output_family="llm_hard_veto_then_momentum_rank",
        )


def _insert_failed_replay_distillation_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    raw_answer: str,
    provider_name: str,
    model_name: str,
    executor_kind: str,
    error_message: str,
    prompt: str | None,
    round_index: int,
    output_family: str,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    parsed_payload = {
        "as_of_date": run.run_date.isoformat(),
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "distillation_mode": "llm_filtering",
        "output_family": output_family,
        "primary_pick": None,
        "candidates": [],
        "sources_used": [],
        "limitations": [error_message],
        "llm_executor": "sealed_packet_distillation",
        "executor_failure": True,
    }
    round_record = _insert_replay_round_record(
        session,
        run=run,
        packet=packet,
        parsed_payload=parsed_payload,
        raw_answer=raw_answer or json.dumps(parsed_payload, ensure_ascii=False),
        provider_name=provider_name or "llm",
        model_name=model_name or "unavailable",
        executor_kind=executor_kind,
        error_message=error_message,
        prompt=prompt,
        status="failed",
        round_index=round_index,
    )
    return round_record, []


def _insert_failed_replay_llm_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    raw_answer: str,
    provider_name: str,
    model_name: str,
    error_message: str,
    prompt: str | None,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    parsed_payload = {
        "as_of_date": run.run_date.isoformat(),
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "primary_pick": None,
        "candidates": [],
        "sources_used": [],
        "limitations": [error_message],
        "llm_executor": "sealed_packet_only",
        "executor_failure": True,
    }
    round_record = _insert_replay_round_record(
        session,
        run=run,
        packet=packet,
        parsed_payload=parsed_payload,
        raw_answer=raw_answer or json.dumps(parsed_payload, ensure_ascii=False),
        provider_name=provider_name or "llm",
        model_name=model_name or "unavailable",
        executor_kind="historical_replay_sealed_packet_llm",
        error_message=error_message,
        prompt=prompt,
        status="failed",
    )
    return round_record, []


def _is_diagnostic_replay_payload(payload: dict[str, Any]) -> bool:
    summary = dict(payload.get("summary") or payload.get("summary_payload") or {})
    return (
        summary.get("llm_executor_kind") == "historical_replay_diagnostic_proxy"
        or summary.get("model_family") == "diagnostic-sealed-packet-proxy"
        or str(payload.get("model_family") or "").startswith("diagnostic-sealed-packet-proxy")
    )


def _is_diagnostic_replay_run(run: ShortpickExperimentRun) -> bool:
    return _is_diagnostic_replay_payload({"summary": dict(run.summary_payload or {})})


def _insert_replay_proxy_round(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    limit: int,
    reason: str,
) -> tuple[ShortpickModelRound, list[dict[str, Any]]]:
    symbols = _llm_proxy_symbols(packet=packet, universe=universe, limit=limit)
    picks = [_proxy_pick_payload(symbol=symbol, packet=packet, universe=universe, limitation=reason) for symbol in symbols]
    parsed_payload = {
        "as_of_date": run.run_date.isoformat(),
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "primary_pick": picks[0] if picks else {"symbol": "PARSE_FAILED", "name": "解析失败"},
        "candidates": picks,
        "sources_used": [{"source_id": source["source_id"]} for source in packet["official_sources"][:3]],
        "limitations": [
            "diagnostic deterministic proxy; not a real LLM replay recommendation",
            reason,
        ],
    }
    round_record = _insert_replay_round_record(
        session,
        run=run,
        packet=packet,
        parsed_payload=parsed_payload,
        raw_answer=json.dumps(parsed_payload, ensure_ascii=False),
        provider_name="system",
        model_name="diagnostic_sealed_packet_proxy",
        executor_kind="historical_replay_diagnostic_proxy",
        error_message=reason,
        prompt=None,
    )
    return round_record, picks


def _insert_replay_round_record(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    parsed_payload: dict[str, Any],
    raw_answer: str,
    provider_name: str,
    model_name: str,
    executor_kind: str,
    error_message: str | None,
    prompt: str | None,
    status: str = "completed",
    round_index: int = 1,
) -> ShortpickModelRound:
    run_id = int(run.id)
    run_key = str(run.run_key)
    sources_payload = _round_sources_from_payload(packet, parsed_payload)
    last_error: OperationalError | None = None
    for attempt in range(5):
        now = utcnow()
        round_record = ShortpickModelRound(
            run_id=run_id,
            round_key=f"{run_key}:{executor_kind}:{round_index}",
            provider_name=provider_name,
            model_name=model_name,
            executor_kind=executor_kind,
            round_index=round_index,
            status=status,
            raw_answer=raw_answer,
            parsed_payload=parsed_payload,
            sources_payload=sources_payload,
            artifact_id=f"shortpick-replay-round:{run_id}:{round_index}",
            error_message=error_message,
            started_at=now,
            completed_at=now,
        )
        session.add(round_record)
        try:
            session.flush()
        except OperationalError as exc:
            session.rollback()
            if "database is locked" not in str(exc).lower():
                raise
            last_error = exc
            sleep(0.5 * (attempt + 1))
            continue
        _write_replay_round_artifact(session, run, round_record, prompt=prompt)
        return round_record
    if last_error is not None:
        raise last_error
    raise RuntimeError("replay round insert failed without an OperationalError")


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
    llm_pick: dict[str, Any] | None = None,
) -> None:
    member = universe["by_symbol"].get(symbol)
    if member is None:
        return
    is_llm_family = _is_llm_replay_family(baseline_family)
    support_sources = _sources_for_pick(packet, llm_pick) if llm_pick else _sources_for_symbol(packet, symbol)
    if not is_llm_family and not support_sources:
        support_sources = packet["official_sources"][:1]
    thesis = str((llm_pick or {}).get("thesis") or _candidate_thesis(member, baseline_family))
    audit_text = " ".join(
        [
            thesis,
            *(_string_list((llm_pick or {}).get("catalysts"))),
            *(_string_list((llm_pick or {}).get("risks"))),
            *(_string_list((llm_pick or {}).get("invalidation"))),
        ]
    )
    evidence_mapping = _evidence_mapping_for_pick(llm_pick, support_sources)
    audit = _audit_candidate(
        as_of_date=run.run_date,
        packet=packet,
        symbol=symbol,
        sources=support_sources,
        thesis=audit_text,
        evidence_mapping=evidence_mapping,
    )
    limitations = list((llm_pick or {}).get("limitations") or [])
    if audit["status"] != "pass":
        limitations.extend(list(audit["reasons"]))
    tradeability = {
        "in_universe": True,
        "is_tradeable": True,
        "excluded_reason": None,
        "as_of_date": run.run_date.isoformat(),
        "latest_bar_at": member.latest_bar.observed_at.isoformat(),
        "close_price": member.latest_bar.close_price,
        "amount": member.latest_bar.amount,
        "turnover_rate": member.turnover_rate,
        "market_cap": member.market_cap,
        "market_cap_source": member.market_cap_source,
        "market_cap_bucket": member.market_cap_bucket,
        "industry": member.industry,
    }
    candidate_payload = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "baseline_family": baseline_family,
        "baseline_rank": rank,
        "as_of_cutoff": packet["as_of_cutoff"],
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "sources_used": [source["source_id"] for source in support_sources],
        "evidence_mapping": evidence_mapping,
        "leakage_audit_status": audit["status"],
        "leakage_audit_reasons": audit["reasons"],
        "official_sample_eligible": audit["status"] == "pass",
        "exclusion_reason": None if audit["status"] == "pass" else "; ".join(audit["reasons"]),
        "tradeability": tradeability,
        "market_cap_bucket": member.market_cap_bucket,
        "industry": member.industry or "unknown",
        "limitations": limitations,
        "universe_membership": {
            "in_universe": True,
            "is_tradeable": True,
            "market_cap_bucket": member.market_cap_bucket,
            "market_cap_source": member.market_cap_source,
            "industry": member.industry,
            "turnover_rate": member.turnover_rate,
        },
    }
    extra_candidate_payload = (llm_pick or {}).get("candidate_payload")
    if isinstance(extra_candidate_payload, dict):
        candidate_payload.update(extra_candidate_payload)
    session.add(
        ShortpickCandidate(
            run_id=run.id,
            round_id=round_record.id if round_record is not None else None,
            candidate_key=f"shortpick-replay-candidate:{run.id}:{baseline_family}:{rank}:{symbol}",
            symbol=symbol,
            name=member.name,
            normalized_theme=member.industry or baseline_family,
            horizon_trading_days=5,
            confidence=0.55 if not is_llm_family else 0.62,
            thesis=thesis,
            catalysts=_string_list((llm_pick or {}).get("catalysts")) or [_baseline_label(baseline_family), f"截至 {run.run_date.isoformat()} 的 sealed packet / 行情快照。"],
            invalidation=_string_list((llm_pick or {}).get("invalidation")) or ["历史隔离回放只验证信号，不进入主推荐或模拟盘。"],
            risks=_string_list((llm_pick or {}).get("risks")) or ["若 source packet 含未来信息或样本不足，该候选会从 official sample 排除。"],
            sources_payload=[_candidate_source_payload(source) for source in support_sources],
            novelty_note="sealed packet LLM candidate" if is_llm_family else "historical replay baseline candidate",
            limitations=limitations,
            convergence_group=baseline_family,
            research_priority="single_model_high_conviction" if is_llm_family else "baseline_control",
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


def _proxy_pick_payload(*, symbol: str, packet: dict[str, Any], universe: dict[str, Any], limitation: str) -> dict[str, Any]:
    member = universe["by_symbol"][symbol]
    source_ids = [source["source_id"] for source in _sources_for_symbol(packet, symbol)[:2]]
    return {
        "symbol": symbol,
        "name": member.name,
        "theme": member.industry or "historical_replay",
        "thesis": _candidate_thesis(member, "llm"),
        "catalysts": ["sealed packet diagnostic proxy"],
        "risks": ["真实 sealed-packet LLM executor 未产出可用 JSON，本候选仅用于诊断流水线。"],
        "invalidation": ["历史隔离回放只验证信号，不进入主推荐或模拟盘。"],
        "sources_used": source_ids,
        "evidence_mapping": {"thesis": source_ids[:2]},
        "limitations": [limitation, "diagnostic deterministic proxy; not a real LLM replay recommendation"],
    }


def _build_replay_llm_prompt(
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    limit: int,
) -> str:
    members = [
        {
            "symbol": member.symbol,
            "name": member.name,
            "industry": member.industry,
            "market_cap_bucket": member.market_cap_bucket,
            "market_cap_source": member.market_cap_source,
            "day_return": round(_bar_return(member), 6),
            "amount": member.latest_bar.amount,
            "turnover_rate": member.turnover_rate,
        }
        for member in universe["members"][:120]
    ]
    sources = [
        {
            "source_id": source["source_id"],
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "published_at": source.get("published_at"),
            "linked_symbols": source.get("linked_symbols") or [],
            "body_excerpt": _source_excerpt(source.get("body_excerpt"), limit=360),
        }
        for source in packet["official_sources"][:60]
    ]
    sealed_packet = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "as_of_date": packet["as_of_date"],
        "as_of_cutoff": packet["as_of_cutoff"],
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "account_profile": universe["summary"].get("account_profile"),
        "account_profile_label": universe["summary"].get("account_profile_label"),
        "account_rule_note": universe["summary"].get("account_rule_note"),
        "tradeable_universe": members,
        "official_sources": sources,
        "rejected_source_count": len(packet.get("rejected_sources") or []),
    }
    return f"""
你正在执行 A 股短投历史隔离回放。你只能使用下面 sealed source packet 中的信息，不能联网，不能使用训练记忆补充事实，不能引用 packet 外来源。

任务日期：{run.run_date.isoformat()}
as_of_cutoff：{packet["as_of_cutoff"]}
候选数量上限：{limit}
账户口径：{universe["summary"].get("account_profile_label") or universe["summary"].get("account_profile")}

输出 JSON，不要加代码块。`sources_used` 和 `evidence_mapping` 只能填写 packet 内的 `source_id`，不能填写 URL。
候选 symbol 必须来自 `tradeable_universe`，也就是当前账户可执行股票池；不要选择科创板、创业板、北交所、ST 或 packet 中不存在的股票。
`candidates` 是验收样本主体，必须尽量输出 {limit} 个不重复候选；`primary_pick` 必须等于 `candidates[0]`。
每个候选的 thesis / catalysts / risks / invalidation 保持短句，优先引用与 symbol 相关的 official source id；没有对应 source 时必须在 limitations 里说明仅基于行情快照。

输出格式：
{{
  "as_of_date": "{run.run_date.isoformat()}",
  "information_mode": "historical_replay",
  "source_packet_id": "{packet["source_packet_id"]}",
  "source_packet_hash": "{packet["source_packet_hash"]}",
  "primary_pick": {{
    "symbol": "000000.SZ",
    "name": "...",
    "theme": "...",
    "thesis": "...",
    "catalysts": ["..."],
    "risks": ["..."],
    "invalidation": ["..."],
    "sources_used": ["src-001"],
    "evidence_mapping": {{"thesis": ["src-001"], "catalyst_1": ["src-002"]}},
    "limitations": ["..."]
  }},
  "candidates": [
    {{
      "symbol": "000000.SZ",
      "name": "...",
      "theme": "...",
      "thesis": "...",
      "catalysts": ["..."],
      "risks": ["..."],
      "invalidation": ["..."],
      "sources_used": ["src-001"],
      "evidence_mapping": {{"thesis": ["src-001"]}},
      "limitations": ["..."]
    }}
  ],
  "limitations": []
}}

sealed source packet:
{json.dumps(sealed_packet, ensure_ascii=False, indent=2)}
""".strip()


def _build_replay_distillation_prompt(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    source_family: str,
    output_family: str,
    executor_kind: str,
    pool_symbols: list[str],
    limit: int,
) -> str:
    mode = "llm_self_distillation" if output_family == "llm_self_distilled" else "momentum_pool_distillation"
    candidate_pool = _distillation_candidate_contexts(session, run=run, packet=packet, universe=universe, symbols=pool_symbols)
    sources = [
        {
            "source_id": source["source_id"],
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "published_at": source.get("published_at"),
            "linked_symbols": source.get("linked_symbols") or [],
            "body_excerpt": _source_excerpt(source.get("body_excerpt"), limit=300),
        }
        for source in packet["official_sources"][:60]
    ]
    sealed_packet = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "distillation_mode": mode,
        "source_family": source_family,
        "output_family": output_family,
        "executor_kind": executor_kind,
        "as_of_date": packet["as_of_date"],
        "as_of_cutoff": packet["as_of_cutoff"],
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "candidate_pool": candidate_pool,
        "official_sources": sources,
        "rejected_source_count": len(packet.get("rejected_sources") or []),
    }
    return f"""
你正在执行 A 股短投历史隔离回放的 LLM 蒸馏。你只能使用下面 sealed distillation packet 中的信息，不能联网，不能使用训练记忆补充事实，不能引用 packet 外来源。

任务日期：{run.run_date.isoformat()}
as_of_cutoff：{packet["as_of_cutoff"]}
蒸馏模式：{mode}
输入池：{source_family}
输出组别：{output_family}
输出候选数量上限：{limit}

目标不是重新做全市场选股，而是在 candidate_pool 里做过滤、降噪、识别伪催化。
优先剔除只有价格动量、没有封闭来源支持、或者催化与股票关联弱的候选；也不要机械选择涨幅最高的股票。
候选 symbol 必须来自 `candidate_pool`，`sources_used` 和 `evidence_mapping` 只能填写 packet 内的 `source_id`。
`candidates` 必须尽量输出 {limit} 个不重复候选；`primary_pick` 必须等于 `candidates[0]`。

输出 JSON，不要加代码块：
{{
  "as_of_date": "{run.run_date.isoformat()}",
  "information_mode": "historical_replay",
  "distillation_mode": "{mode}",
  "source_family": "{source_family}",
  "output_family": "{output_family}",
  "primary_pick": {{
    "symbol": "000000.SZ",
    "name": "...",
    "theme": "...",
    "thesis": "...",
    "catalysts": ["..."],
    "risks": ["..."],
    "invalidation": ["..."],
    "sources_used": ["src-001"],
    "evidence_mapping": {{"thesis": ["src-001"]}},
    "limitations": ["..."]
  }},
  "candidates": [],
  "limitations": []
}}

sealed distillation packet:
{json.dumps(sealed_packet, ensure_ascii=False, indent=2)}
""".strip()


def _build_replay_rejection_prompt(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    pool_symbols: list[str],
    reject_max_ratio: float,
) -> str:
    candidate_pool = _distillation_candidate_contexts(session, run=run, packet=packet, universe=universe, symbols=pool_symbols)
    sources = [
        {
            "source_id": source["source_id"],
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "published_at": source.get("published_at"),
            "linked_symbols": source.get("linked_symbols") or [],
            "body_excerpt": _source_excerpt(source.get("body_excerpt"), limit=300),
        }
        for source in packet["official_sources"][:40]
    ]
    sealed_packet = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "rejection_mode": "momentum_pool_reject_only",
        "source_family": "momentum_volume_expanded_pool",
        "output_families": list(SHORTPICK_REPLAY_REJECTION_FAMILIES),
        "as_of_date": packet["as_of_date"],
        "as_of_cutoff": packet["as_of_cutoff"],
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "candidate_pool": candidate_pool,
        "official_sources": sources,
        "rejected_source_count": len(packet.get("rejected_sources") or []),
    }
    max_reject_count = int(len(pool_symbols) * reject_max_ratio)
    return f"""
你正在执行 A 股短投历史隔离回放的 LLM 只剔除实验。你只能使用下面 sealed rejection packet 中的信息，不能联网，不能使用训练记忆补充事实，不能引用 packet 外来源。

任务日期：{run.run_date.isoformat()}
as_of_cutoff：{packet["as_of_cutoff"]}
输入池：扩大动量成交量候选池
池子数量：{len(pool_symbols)}
最多剔除数量：{max_reject_count}（除非存在明确非候选池/封闭信息违规，否则不要超过）

目标不是重新排序、不是重新选股，而是判断 candidate_pool 中哪些应被剔除。后续排序会由系统按原始动量成交量顺序机械完成。
只在以下情况剔除：催化与股票关系弱、来源只证明行业不证明个股、像价格动量的事后叙事、来源时点/文本支持不足、流动性或交易属性异常、明显风险大于短投催化。
如果只是没有足够把握，不要剔除。`decisions` 主要输出需要 reject 的候选即可；不需要为每个 keep 候选写一条长理由。宁可少剔除，不要因为偏好而重排。
`symbol` 必须来自 `candidate_pool`；`sources_used` 和 `evidence_mapping` 只能填写 packet 内的 `source_id`。

输出 JSON，不要加代码块：
{{
  "as_of_date": "{run.run_date.isoformat()}",
  "information_mode": "historical_replay",
  "rejection_mode": "momentum_pool_reject_only",
  "source_family": "momentum_volume_expanded_pool",
  "decisions": [
    {{
      "symbol": "000000.SZ",
      "decision": "keep|reject|uncertain",
      "reason_category": "weak_source|pseudo_catalyst|already_priced|risk_disclosure|liquidity|weak_symbol_link|market_snapshot_only|other",
      "reason": "...",
      "sources_used": ["src-001"],
      "evidence_mapping": {{"reason": ["src-001"]}},
      "limitations": ["..."]
    }}
  ],
  "limitations": []
}}

sealed rejection packet:
{json.dumps(sealed_packet, ensure_ascii=False, indent=2)}
""".strip()


def _build_replay_hard_veto_prompt(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    pool_symbols: list[str],
    veto_max_ratio: float,
) -> str:
    candidate_pool = _distillation_candidate_contexts(session, run=run, packet=packet, universe=universe, symbols=pool_symbols)
    sources = [
        {
            "source_id": source["source_id"],
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "published_at": source.get("published_at"),
            "linked_symbols": source.get("linked_symbols") or [],
            "body_excerpt": _source_excerpt(source.get("body_excerpt"), limit=260),
        }
        for source in packet["official_sources"][:40]
    ]
    sealed_packet = {
        "experiment_mode": SHORTPICK_REPLAY_EXPERIMENT_MODE,
        "rejection_mode": "hard_veto_only",
        "source_family": "momentum_volume_expanded_pool",
        "output_families": list(SHORTPICK_REPLAY_HARD_VETO_FAMILIES),
        "as_of_date": packet["as_of_date"],
        "as_of_cutoff": packet["as_of_cutoff"],
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "candidate_pool": candidate_pool,
        "official_sources": sources,
        "rejected_source_count": len(packet.get("rejected_sources") or []),
    }
    max_veto_count = int(len(pool_symbols) * veto_max_ratio)
    return f"""
你正在执行 A 股短投历史隔离回放的 LLM 硬否决实验。你只能使用下面 sealed hard-veto packet 中的信息，不能联网，不能使用训练记忆补充事实，不能引用 packet 外来源。

任务日期：{run.run_date.isoformat()}
as_of_cutoff：{packet["as_of_cutoff"]}
输入池：扩大动量成交量候选池
池子数量：{len(pool_symbols)}
最多 hard veto 数量：{max_veto_count}

目标不是选股、不是排序、不是判断哪个催化更强。后续排序会由系统按原始动量成交量顺序机械完成。
你只负责识别“明显不该进入短投样本”的硬问题。宁可不否决，也不要因为故事弱、涨幅大、缺乏把握、看起来已经 price-in 而否决。

只允许以下 hard_veto reason_category：
- source_mismatch：候选上下文明示有 candidate-specific source，且该来源明确属于别的股票，或只证明行业/别的公司，不能支持该候选个股。
- future_source：来源时间或内容明显晚于 as_of_cutoff。
- source_not_in_packet：理由依赖 packet 外来源。
- untradeable：候选不可交易、停牌、ST、涨跌停导致 entry 不可执行，且 packet/候选上下文明确支持。
- liquidity_abnormal：流动性明显异常，不能形成可执行短投样本。
- negative_direct_conflict：封闭来源里存在直接、明确、个股级负面公告，且与短投催化冲突。

候选上下文里的 `source_support=no_symbol_specific_source` 表示系统没有给出该股票的候选专属来源；这不是 source_mismatch，也不能单独作为 hard veto 理由。
不要输出 keep/uncertain 的逐条长解释；`decisions` 主要输出需要 reject 的候选即可。未输出的候选会被系统视为保留。
`symbol` 必须来自 `candidate_pool`；`sources_used` 和 `evidence_mapping` 只能填写 packet 内的 `source_id`。

输出 JSON，不要加代码块：
{{
  "as_of_date": "{run.run_date.isoformat()}",
  "information_mode": "historical_replay",
  "rejection_mode": "hard_veto_only",
  "source_family": "momentum_volume_expanded_pool",
  "decisions": [
    {{
      "symbol": "000000.SZ",
      "decision": "reject",
      "reason_category": "source_mismatch|future_source|source_not_in_packet|untradeable|liquidity_abnormal|negative_direct_conflict",
      "reason": "...",
      "sources_used": ["src-001"],
      "evidence_mapping": {{"reason": ["src-001"]}},
      "limitations": ["..."]
    }}
  ],
  "limitations": []
}}

sealed hard-veto packet:
{json.dumps(sealed_packet, ensure_ascii=False, indent=2)}
""".strip()


def _distillation_candidate_contexts(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    packet: dict[str, Any],
    universe: dict[str, Any],
    symbols: list[str],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for symbol in symbols:
        member = universe["by_symbol"].get(symbol)
        if member is None:
            continue
        bars = _recent_daily_bars(session, symbol=symbol, as_of_date=run.run_date, limit=25)
        linked_sources = _linked_sources_for_symbol(packet, symbol)
        contexts.append(
            {
                "symbol": symbol,
                "name": member.name,
                "industry": member.industry,
                "market_cap_bucket": member.market_cap_bucket,
                "market_cap": member.market_cap,
                "day_return": round(_bar_return(member), 6),
                "return_3d": _bars_return(bars, 3),
                "return_5d": _bars_return(bars, 5),
                "return_10d": _bars_return(bars, 10),
                "amount": member.latest_bar.amount,
                "amount_ratio_5d": _amount_ratio(bars, 5),
                "turnover_rate": member.turnover_rate,
                "source_ids": [source["source_id"] for source in linked_sources[:3]],
                "source_titles": [source.get("title") for source in linked_sources[:3]],
                "source_support": "symbol_linked" if linked_sources else "no_symbol_specific_source",
            }
        )
    return contexts


def _recent_daily_bars(session: Session, *, symbol: str, as_of_date: date, limit: int) -> list[MarketBar]:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        return []
    rows = session.scalars(
        select(MarketBar)
        .where(
            MarketBar.stock_id == stock.id,
            MarketBar.timeframe == "1d",
            MarketBar.observed_at <= datetime.combine(as_of_date, time.max, tzinfo=UTC),
        )
        .order_by(MarketBar.observed_at.desc(), MarketBar.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def _bars_return(bars: list[MarketBar], days: int) -> float | None:
    if len(bars) <= days:
        return None
    start = bars[-(days + 1)]
    end = bars[-1]
    if not start.close_price:
        return None
    return round(float(end.close_price / start.close_price - 1), 6)


def _amount_ratio(bars: list[MarketBar], days: int) -> float | None:
    if len(bars) < days + 1:
        return None
    latest = float(bars[-1].amount or 0.0)
    previous = [float(bar.amount or 0.0) for bar in bars[-(days + 1):-1]]
    average = sum(previous) / len(previous) if previous else 0.0
    if average <= 0:
        return None
    return round(latest / average, 6)


def _normalize_replay_llm_payload(
    parsed: dict[str, Any],
    *,
    packet: dict[str, Any],
    universe: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    raw_candidates: list[Any] = []
    if isinstance(parsed.get("candidates"), list):
        raw_candidates.extend(parsed["candidates"])
    primary = parsed.get("primary_pick")
    if isinstance(primary, dict):
        raw_candidates.insert(0, primary)
    alternatives = parsed.get("alternative_picks")
    if isinstance(alternatives, list):
        raw_candidates.extend(alternatives)

    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        symbol = _resolve_replay_symbol(str(raw.get("symbol") or ""), universe)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        member = universe["by_symbol"][symbol]
        support_sources = _source_refs_for_llm_pick(packet=packet, pick=raw, symbol=symbol)
        evidence_mapping = _normalize_evidence_mapping(
            raw.get("evidence_mapping"),
            support_sources,
            allow_fallback=not _source_ids_declared_by_pick(raw),
        )
        candidates.append(
            {
                "symbol": symbol,
                "name": str(raw.get("name") or member.name),
                "theme": str(raw.get("theme") or member.industry or "historical_replay"),
                "thesis": str(raw.get("thesis") or _candidate_thesis(member, "llm")),
                "catalysts": _string_list(raw.get("catalysts")),
                "risks": _string_list(raw.get("risks")),
                "invalidation": _string_list(raw.get("invalidation")),
                "sources_used": [source["source_id"] for source in support_sources],
                "evidence_mapping": evidence_mapping,
                "limitations": _string_list(raw.get("limitations")),
            }
        )
        if len(candidates) >= limit:
            break
    if not candidates:
        raise ValueError("sealed-packet LLM response did not contain any valid universe candidates")
    return {
        "as_of_date": str(parsed.get("as_of_date") or packet["as_of_date"]),
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "primary_pick": candidates[0],
        "candidates": candidates,
        "limitations": _string_list(parsed.get("limitations")),
        "llm_executor": "sealed_packet_only",
    }


def _normalize_replay_distillation_payload(
    parsed: dict[str, Any],
    *,
    packet: dict[str, Any],
    universe: dict[str, Any],
    allowed_symbols: set[str],
    limit: int,
    source_family: str,
    output_family: str,
) -> dict[str, Any]:
    payload = _normalize_replay_llm_payload(parsed, packet=packet, universe=universe, limit=max(limit, 1))
    filtered = [candidate for candidate in payload["candidates"] if candidate["symbol"] in allowed_symbols][:limit]
    if not filtered:
        raise ValueError("distillation response did not contain any valid candidate_pool symbols")
    return {
        **payload,
        "distillation_mode": str(parsed.get("distillation_mode") or "llm_filtering"),
        "source_family": source_family,
        "output_family": output_family,
        "primary_pick": filtered[0],
        "candidates": filtered,
        "llm_executor": "sealed_packet_distillation",
    }


def _normalize_replay_rejection_payload(
    parsed: dict[str, Any],
    *,
    packet: dict[str, Any],
    universe: dict[str, Any],
    pool_symbols: list[str],
    reject_max_ratio: float,
) -> dict[str, Any]:
    allowed_symbols = set(pool_symbols)
    raw_decisions = parsed.get("decisions")
    if not isinstance(raw_decisions, list):
        raw_decisions = parsed.get("candidates") if isinstance(parsed.get("candidates"), list) else []
    max_reject_count = int(len(pool_symbols) * reject_max_ratio)
    reject_count = 0
    by_symbol: dict[str, dict[str, Any]] = {}
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            continue
        symbol = _resolve_replay_symbol(str(raw.get("symbol") or ""), universe)
        if not symbol or symbol not in allowed_symbols or symbol in by_symbol:
            continue
        decision = _normalize_rejection_decision(raw.get("decision"))
        limitations = _string_list(raw.get("limitations"))
        if decision == "reject":
            if reject_count >= max_reject_count:
                decision = "uncertain"
                limitations.append("reject cap applied by parser")
            else:
                reject_count += 1
        member = universe["by_symbol"][symbol]
        support_sources = _source_refs_for_llm_pick(packet=packet, pick=raw, symbol=symbol)
        evidence_mapping = _normalize_evidence_mapping(
            raw.get("evidence_mapping"),
            support_sources,
            allow_fallback=not _source_ids_declared_by_pick(raw),
        )
        by_symbol[symbol] = {
            "symbol": symbol,
            "name": str(raw.get("name") or member.name),
            "decision": decision,
            "reason_category": str(raw.get("reason_category") or "other"),
            "reason": str(raw.get("reason") or raw.get("thesis") or ""),
            "sources_used": [source["source_id"] for source in support_sources],
            "evidence_mapping": evidence_mapping,
            "limitations": limitations,
        }
    decisions: list[dict[str, Any]] = []
    for symbol in pool_symbols:
        if symbol in by_symbol:
            decisions.append(by_symbol[symbol])
            continue
        member = universe["by_symbol"].get(symbol)
        if member is None:
            continue
        decisions.append(
            {
                "symbol": symbol,
                "name": member.name,
                "decision": "uncertain",
                "reason_category": "not_returned_by_model",
                "reason": "model omitted this candidate; parser kept it as uncertain instead of rejection",
                "sources_used": [source["source_id"] for source in _sources_for_symbol(packet, symbol)[:2]],
                "evidence_mapping": {},
                "limitations": ["model did not return a decision for this candidate"],
            }
        )
    return {
        "as_of_date": str(parsed.get("as_of_date") or packet["as_of_date"]),
        "information_mode": SHORTPICK_HISTORICAL_REPLAY_MODE,
        "source_packet_id": packet["source_packet_id"],
        "source_packet_hash": packet["source_packet_hash"],
        "rejection_mode": "momentum_pool_reject_only",
        "source_family": "momentum_volume_expanded_pool",
        "decisions": decisions,
        "rejected_count": len([item for item in decisions if item["decision"] == "reject"]),
        "limitations": _string_list(parsed.get("limitations")),
        "llm_executor": "sealed_packet_rejection",
    }


def _normalize_rejection_decision(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"reject", "rejected", "drop", "exclude", "剔除", "删除", "排除"}:
        return "reject"
    if normalized in {"keep", "kept", "pass", "retain", "保留", "通过"}:
        return "keep"
    return "uncertain"


def _extract_replay_rejection_json_with_partial_repair(
    *,
    transport: Any,
    base_url: str,
    api_key: str,
    model_name: str,
    raw_answer: str,
) -> tuple[dict[str, Any], str, bool]:
    try:
        return extract_shortpick_json(raw_answer), raw_answer, False
    except ValueError as parse_exc:
        try:
            repaired = transport.complete(
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                prompt=_build_replay_json_repair_prompt(raw_answer),
                system="只修复 JSON 格式，不要新增事实、股票、来源或解释。只输出 JSON。",
                enable_search=False,
            )
            return extract_shortpick_json(repaired), repaired, True
        except Exception:
            partial = _extract_partial_rejection_decisions(raw_answer)
            if partial:
                return {"decisions": partial, "limitations": ["partial rejection JSON recovered from raw answer"]}, raw_answer, True
            raise parse_exc


def _extract_partial_rejection_decisions(raw_answer: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    decisions: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for match in re.finditer(r"\{", raw_answer):
        try:
            value, _ = decoder.raw_decode(raw_answer[match.start():])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        if not value.get("symbol") or not value.get("decision"):
            continue
        symbol = str(value.get("symbol"))
        if symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        decisions.append(value)
    return decisions


def _extract_replay_llm_json_with_repair(
    *,
    transport: Any,
    base_url: str,
    api_key: str,
    model_name: str,
    raw_answer: str,
) -> tuple[dict[str, Any], str, bool]:
    try:
        return extract_shortpick_json(raw_answer), raw_answer, False
    except ValueError:
        repaired = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=_build_replay_json_repair_prompt(raw_answer),
            system="只修复 JSON 格式，不要新增事实、股票、来源或解释。只输出 JSON。",
            enable_search=False,
        )
        return extract_shortpick_json(repaired), repaired, True


def _build_replay_json_repair_prompt(raw_answer: str) -> str:
    return f"""
下面是 sealed-packet historical replay LLM executor 的原始回答。它没有被系统解析为 JSON。

请只做格式修复：输出一个 JSON object，不要新增任何事实、股票、来源、URL 或解释。保留原始回答中的候选、source id、thesis、catalysts、risks、limitations。不要使用 markdown 代码块。

原始回答：
{raw_answer[:12000]}
""".strip()


def _resolve_replay_symbol(value: str, universe: dict[str, Any]) -> str | None:
    normalized = value.strip().upper()
    if normalized in universe["by_symbol"]:
        return normalized
    ticker = normalized.split(".")[0]
    matches = [symbol for symbol in universe["by_symbol"] if symbol.split(".")[0] == ticker]
    return matches[0] if len(matches) == 1 else None


def _source_ids_from_value(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    output: list[str] = []
    for item in values:
        if isinstance(item, dict):
            source_id = item.get("source_id") or item.get("id")
        else:
            source_id = item
        if source_id:
            output.append(str(source_id))
    return output


def _sources_by_ids(packet: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(source_ids)
    return [source for source in packet["official_sources"] if source["source_id"] in wanted]


def _normalize_evidence_mapping(
    value: Any,
    support_sources: list[dict[str, Any]],
    *,
    allow_fallback: bool = True,
) -> dict[str, list[str]]:
    fallback_ids = [source["source_id"] for source in support_sources[:2]]
    if not isinstance(value, dict):
        return {"thesis": fallback_ids} if allow_fallback and fallback_ids else {}
    allowed = {source["source_id"] for source in support_sources}
    output: dict[str, list[str]] = {}
    for key, raw_ids in value.items():
        ids = [source_id for source_id in _source_ids_from_value(raw_ids) if source_id in allowed]
        if ids:
            output[str(key)] = ids
    return output or ({"thesis": fallback_ids} if allow_fallback and fallback_ids else {})


def _sources_for_pick(packet: dict[str, Any], pick: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not pick:
        return []
    return _source_refs_for_llm_pick(packet=packet, pick=pick, symbol=str(pick.get("symbol") or ""))


def _evidence_mapping_for_pick(pick: dict[str, Any] | None, support_sources: list[dict[str, Any]]) -> dict[str, list[str]]:
    return _normalize_evidence_mapping(
        (pick or {}).get("evidence_mapping"),
        support_sources,
        allow_fallback=not _source_ids_declared_by_pick(pick),
    )


def _source_refs_for_llm_pick(*, packet: dict[str, Any], pick: dict[str, Any] | None, symbol: str) -> list[dict[str, Any]]:
    source_ids = _source_ids_declared_by_pick(pick)
    if source_ids:
        return _sources_or_rejections_by_ids(packet, source_ids)
    return _sources_for_symbol(packet, symbol) if symbol else []


def _source_ids_declared_by_pick(pick: dict[str, Any] | None) -> list[str]:
    if not pick:
        return []
    source_ids = _source_ids_from_value(pick.get("sources_used"))
    mapping = pick.get("evidence_mapping")
    if isinstance(mapping, dict):
        for raw_ids in mapping.values():
            source_ids.extend(_source_ids_from_value(raw_ids))
    return list(dict.fromkeys(source_ids))


def _sources_or_rejections_by_ids(packet: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    official = {source["source_id"]: source for source in packet["official_sources"]}
    rejected = {source["source_id"]: source for source in packet.get("rejected_sources") or []}
    output: list[dict[str, Any]] = []
    for source_id in dict.fromkeys(source_ids):
        if source_id in official:
            output.append(official[source_id])
        elif source_id in rejected:
            output.append(rejected[source_id])
        else:
            output.append(
                {
                    "source_id": source_id,
                    "status": "invalid",
                    "reject_reason": "source_not_in_packet",
                    "title": "packet 外来源引用",
                    "url": None,
                    "published_at": None,
                    "fetched_at": None,
                    "body_excerpt": "",
                    "source_type": "invalid",
                    "linked_symbols": [],
                }
            )
    return output


def _candidate_source_payload(source: dict[str, Any]) -> dict[str, Any]:
    status = str(source.get("status") or "official")
    if status == "official":
        return {
            **source,
            "credibility_status": "verified",
            "credibility_reason": "source timestamp is inside sealed replay packet",
            "support_status": "supported_by_source_text",
        }
    return {
        **source,
        "credibility_status": "rejected",
        "credibility_reason": str(source.get("reject_reason") or status),
        "support_status": "not_eligible_for_official_replay",
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _round_sources_from_payload(packet: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    source_ids: list[str] = []
    source_ids.extend(_source_ids_from_value(payload.get("sources_used")))
    for candidate in payload.get("candidates") or []:
        if isinstance(candidate, dict):
            source_ids.extend(_source_ids_from_value(candidate.get("sources_used")))
    for decision in payload.get("decisions") or []:
        if isinstance(decision, dict):
            source_ids.extend(_source_ids_from_value(decision.get("sources_used")))
    sources = _sources_by_ids(packet, source_ids)
    return sources[:10] if sources else packet["official_sources"][:5]


def _provider_name_from_base_url(base_url: str) -> str:
    lowered = base_url.lower()
    if "deepseek" in lowered:
        return "deepseek"
    if "openai" in lowered:
        return "openai_compatible"
    return "llm"


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


def _factor_ranked_symbols(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    universe: dict[str, Any],
    pool_symbols: list[str],
) -> dict[str, list[str]]:
    contexts = [
        _factor_rank_context(session, run=run, universe=universe, symbol=symbol)
        for symbol in pool_symbols
        if symbol in universe["by_symbol"]
    ]
    contexts = [context for context in contexts if context is not None]
    percentiles = {
        "return_1d": _factor_percentiles(contexts, "return_1d"),
        "return_5d": _factor_percentiles(contexts, "return_5d"),
        "return_10d": _factor_percentiles(contexts, "return_10d"),
        "turnover_rate": _factor_percentiles(contexts, "turnover_rate"),
    }
    by_symbol = {context["symbol"]: context for context in contexts}

    def score(symbol: str, family: str) -> tuple[float, float, float, float]:
        context = by_symbol[symbol]
        if family == "momentum_turnover_rank":
            primary = percentiles["turnover_rate"].get(symbol, 0.0)
        elif family == "momentum_10d_rank":
            primary = percentiles["return_10d"].get(symbol, 0.0)
        elif family == "momentum_10d_turnover_rank":
            primary = percentiles["return_10d"].get(symbol, 0.0) + percentiles["turnover_rate"].get(symbol, 0.0)
        elif family == "momentum_10d_turnover_cooldown_rank":
            primary = (
                percentiles["return_10d"].get(symbol, 0.0)
                + percentiles["turnover_rate"].get(symbol, 0.0)
                - 0.5 * percentiles["return_1d"].get(symbol, 0.0)
            )
        else:
            primary = (
                percentiles["return_1d"].get(symbol, 0.0)
                + 0.5 * percentiles["return_5d"].get(symbol, 0.0)
                + 0.5 * percentiles["turnover_rate"].get(symbol, 0.0)
            )
        return (
            primary,
            float(context.get("return_1d") or 0.0),
            float(context.get("amount") or 0.0),
            float(context.get("turnover_rate") or 0.0),
        )

    symbols = [context["symbol"] for context in contexts]
    return {
        family: sorted(symbols, key=lambda symbol, family=family: score(symbol, family), reverse=True)
        for family in SHORTPICK_REPLAY_FACTOR_RANK_FAMILIES
    }


def _factor_rank_context(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    universe: dict[str, Any],
    symbol: str,
) -> dict[str, Any] | None:
    member = universe["by_symbol"].get(symbol)
    if member is None:
        return None
    bars = _recent_daily_bars(session, symbol=symbol, as_of_date=run.run_date, limit=25)
    return {
        "symbol": symbol,
        "return_1d": _bar_return(member),
        "return_5d": _bars_return(bars, 5),
        "return_10d": _bars_return(bars, 10),
        "turnover_rate": member.turnover_rate,
        "amount": member.latest_bar.amount,
        "amount_ratio_5d": _amount_ratio(bars, 5),
    }


def _factor_percentiles(contexts: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [
        (str(context["symbol"]), float(context[key]))
        for context in contexts
        if context.get(key) is not None
    ]
    values.sort(key=lambda item: item[1], reverse=True)
    if not values:
        return {}
    if len(values) == 1:
        return {values[0][0]: 1.0}
    return {symbol: 1.0 - (rank / (len(values) - 1)) for rank, (symbol, _value) in enumerate(values)}


def _factor_rank_pick_payload(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    universe: dict[str, Any],
    symbol: str,
    family: str,
    original_rank: int,
    derived_rank: int,
) -> dict[str, Any]:
    member = universe["by_symbol"][symbol]
    context = _factor_rank_context(session, run=run, universe=universe, symbol=symbol) or {}
    label = _baseline_label(family)
    return {
        "symbol": symbol,
        "name": member.name,
        "thesis": f"{member.name} 由 {label} 在扩大动量池内再排序入选；只使用 {run.run_date.isoformat()} 收盘前行情特征。",
        "catalysts": [
            label,
            f"原动量池排名 {original_rank}，再排序排名 {derived_rank}",
        ],
        "risks": ["该组为行情特征实验，不读取 packet 外信息，也不进入主推荐或模拟盘。"],
        "invalidation": ["若后续样本显示该特征只在单一月份有效，则降级为诊断基线。"],
        "sources_used": [],
        "evidence_mapping": {},
        "candidate_payload": {
            "factor_rank_experiment": {
                "family": family,
                "source_pool": "momentum_volume_expanded_pool",
                "original_momentum_rank": original_rank,
                "derived_rank": derived_rank,
                "features": context,
                "score_formula": _factor_rank_formula(family),
            }
        },
    }


def _factor_rank_formula(family: str) -> str:
    if family == "momentum_turnover_rank":
        return "rank_percentile(turnover_rate) within top40 momentum-volume pool"
    if family == "momentum_10d_rank":
        return "rank_percentile(return_10d) within top40 momentum-volume pool"
    if family == "momentum_10d_turnover_rank":
        return "rank_percentile(return_10d) + rank_percentile(turnover_rate) within top40 momentum-volume pool"
    if family == "momentum_10d_turnover_cooldown_rank":
        return "rank_percentile(return_10d) + rank_percentile(turnover_rate) - 0.5*rank_percentile(return_1d) within top40 momentum-volume pool"
    return "rank_percentile(return_1d) + 0.5*rank_percentile(return_5d) + 0.5*rank_percentile(turnover_rate)"


def _deterministic_random_rejections(
    *,
    run: ShortpickExperimentRun,
    symbols: list[str],
    reject_count: int,
    salt: str = "random_reject_then_momentum_rank",
) -> list[str]:
    if reject_count <= 0 or not symbols:
        return []
    count = min(reject_count, len(symbols))
    seed_text = f"{run.id}:{run.run_date.isoformat()}:{salt}:{','.join(symbols)}"
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    return rng.sample(list(symbols), count)


def _strict_veto_retained_decision(decision: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(decision, dict):
        return decision
    if decision.get("decision") != "reject":
        return decision
    category = str(decision.get("reason_category") or "")
    if category in SHORTPICK_REPLAY_STRICT_VETO_CATEGORIES:
        return decision
    return {
        **decision,
        "decision": "keep",
        "reason": f"model hard-veto category `{category}` is not in the strict bad-event veto set; retained for strict-veto experiment",
        "limitations": [*_string_list(decision.get("limitations")), "retained by strict-veto subset"],
    }


def _rejection_pick_payload(
    *,
    universe: dict[str, Any],
    symbol: str,
    family: str,
    decision: dict[str, Any] | None,
    original_rank: int,
    derived_rank: int,
) -> dict[str, Any]:
    member = universe["by_symbol"][symbol]
    decision_payload = dict(decision or {})
    decision_label = str(decision_payload.get("decision") or "uncertain")
    reason = str(decision_payload.get("reason") or "LLM 未识别出必须剔除的封闭信息问题。")
    family_label = _baseline_label(family)
    return {
        "symbol": symbol,
        "name": member.name,
        "theme": member.industry or family,
        "thesis": f"{member.name} 经 LLM 只剔除流程保留，原动量排序第 {original_rank}，{family_label} 排序第 {derived_rank}；判断为 {decision_label}：{reason}",
        "catalysts": ["扩大动量池候选通过 LLM 伪催化/弱来源剔除检查"],
        "risks": ["LLM 只负责剔除，不负责收益排序；剩余排序由原动量成交量规则机械决定。"],
        "invalidation": ["若剔除理由被证明与封闭来源不一致，该候选应从 LLM 剔除样本中排除。"],
        "sources_used": [],
        "evidence_mapping": {},
        "limitations": _string_list(decision_payload.get("limitations")),
        "candidate_payload": {
            "rejector_decision": decision_label,
            "rejector_reason_category": str(decision_payload.get("reason_category") or "other"),
            "rejector_reason": reason,
            "rejector_sources_used": _string_list(decision_payload.get("sources_used")),
            "rejector_evidence_mapping": dict(decision_payload.get("evidence_mapping") or {}),
            "original_momentum_rank": original_rank,
            "derived_rank_after_rejection": derived_rank,
            "rejection_design": "llm_reject_only_then_mechanical_momentum_rank",
        },
    }


def _random_rejection_pick_payload(
    *,
    universe: dict[str, Any],
    symbol: str,
    original_rank: int,
    derived_rank: int,
    random_rejected_symbols: list[str],
) -> dict[str, Any]:
    member = universe["by_symbol"][symbol]
    return {
        "symbol": symbol,
        "name": member.name,
        "theme": member.industry or "random_reject_control",
        "thesis": f"{member.name} 在随机剔除同等数量候选后，按原动量排序进入第 {derived_rank} 名；原动量排序第 {original_rank}。",
        "catalysts": ["随机剔除对照组，用于隔离 LLM 剔除是否超过随机删样本。"],
        "risks": ["该组不使用 LLM 判断，只作为统计对照。"],
        "invalidation": ["历史隔离回放只验证信号，不进入主推荐或模拟盘。"],
        "sources_used": [],
        "evidence_mapping": {},
        "limitations": ["random rejection control"],
        "candidate_payload": {
            "random_rejected_symbols": random_rejected_symbols,
            "original_momentum_rank": original_rank,
            "derived_rank_after_rejection": derived_rank,
            "rejection_design": "random_reject_then_mechanical_momentum_rank",
        },
    }


def refresh_shortpick_replay_feedback_cache(
    session: Session,
    *,
    output_path: str | Path,
    validate_missing: bool = True,
) -> dict[str, Any]:
    """Materialize replay feedback so the live UI never recomputes it on page load."""
    runs = session.scalars(
        select(ShortpickExperimentRun)
        .where(ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE)
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
    ).all()
    run_feedback: dict[str, dict[str, Any]] = {}
    validated_run_count = 0
    updated_summary_count = 0
    skipped_run_count = 0
    for run in runs:
        if _is_diagnostic_replay_run(run):
            skipped_run_count += 1
            continue
        parsed_candidate_count = session.scalar(
            select(func.count())
            .select_from(ShortpickCandidate)
            .where(
                ShortpickCandidate.run_id == run.id,
                ShortpickCandidate.parse_status == "parsed",
                ShortpickCandidate.symbol != "PARSE_FAILED",
            )
        )
        if int(parsed_candidate_count or 0) == 0:
            skipped_run_count += 1
            continue
        validation_count = session.scalar(
            select(func.count())
            .select_from(ShortpickValidationSnapshot)
            .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
            .where(ShortpickCandidate.run_id == run.id)
        )
        if validate_missing and int(validation_count or 0) == 0:
            validate_historical_replay_run(session, int(run.id), horizons=SHORTPICK_DEFAULT_HORIZONS)
            validated_run_count += 1
        summary = dict(run.summary_payload or {})
        feedback = summary.get("replay_feedback")
        if not isinstance(feedback, dict):
            feedback = build_shortpick_replay_feedback(session, run_id=int(run.id))
            summary["replay_feedback"] = _json_safe(feedback)
            run.summary_payload = summary
            updated_summary_count += 1
        run_feedback[str(run.id)] = _json_safe(feedback)
    aggregate_feedback = _json_safe(build_shortpick_replay_feedback(session, run_id=None))
    payload = {
        "schema_version": SHORTPICK_REPLAY_FEEDBACK_CACHE_VERSION,
        "generated_at": utcnow().isoformat(),
        "aggregate": aggregate_feedback,
        "runs": run_feedback,
        "metadata": {
            "run_count": len(run_feedback),
            "validated_missing_run_count": validated_run_count,
            "updated_summary_count": updated_summary_count,
            "skipped_run_count": skipped_run_count,
            "aggregate_validation_count": aggregate_feedback.get("overall", {}).get("validation_count"),
        },
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return payload


def _replay_validation_rows(session: Session, *, run_id: int | None) -> list[dict[str, Any]]:
    default_run_ids = _latest_default_replay_run_ids(session) if run_id is None else None
    query = (
        select(
            ShortpickValidationSnapshot.candidate_id,
            ShortpickValidationSnapshot.horizon_days,
            ShortpickValidationSnapshot.status,
            ShortpickValidationSnapshot.excess_return,
            ShortpickValidationSnapshot.stock_return,
            ShortpickCandidate.symbol,
            ShortpickCandidate.run_id,
            ShortpickCandidate.candidate_payload.label("candidate_payload"),
            func.coalesce(func.json_extract(ShortpickCandidate.candidate_payload, "$.baseline_family"), "unknown").label("baseline_family"),
            func.coalesce(func.json_extract(ShortpickCandidate.candidate_payload, "$.official_sample_eligible"), 0).label("official_sample_eligible"),
            ShortpickExperimentRun.run_date,
            func.json_extract(ShortpickExperimentRun.summary_payload, "$.llm_executor_kind").label("llm_executor_kind"),
            func.json_extract(ShortpickExperimentRun.summary_payload, "$.model_family").label("model_family"),
            func.json_extract(ShortpickExperimentRun.summary_payload, "$.account_profile").label("account_profile"),
        )
        .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
        .join(ShortpickExperimentRun, ShortpickCandidate.run_id == ShortpickExperimentRun.id)
        .where(ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE)
    )
    if run_id is not None:
        query = query.where(ShortpickCandidate.run_id == run_id)
    rows = []
    for row in session.execute(query).mappings().all():
        if default_run_ids is not None and int(row["run_id"]) not in default_run_ids:
            continue
        llm_executor_kind = str(row.get("llm_executor_kind") or "")
        model_family = str(row.get("model_family") or "")
        account_profile = str(row.get("account_profile") or "")
        if run_id is None and account_profile and account_profile != ACCOUNT_PROFILE_NEW_RETAIL_CASH:
            continue
        if run_id is None and not account_profile:
            continue
        if run_id is None and (
            llm_executor_kind == "historical_replay_diagnostic_proxy"
            or model_family == "diagnostic-sealed-packet-proxy"
            or model_family.startswith("diagnostic-sealed-packet-proxy")
        ):
            continue
        family = str(row.get("baseline_family") or "unknown")
        if family == "llm" and llm_executor_kind == "historical_replay_diagnostic_proxy":
            family = "diagnostic_proxy_llm"
        candidate_payload = row.get("candidate_payload") if isinstance(row.get("candidate_payload"), dict) else {}
        rows.append(
            {
                "candidate_id": int(row["candidate_id"]),
                "symbol": str(row["symbol"]),
                "horizon_days": int(row["horizon_days"]),
                "status": str(row["status"]),
                "excess_return": row["excess_return"],
                "stock_return": row["stock_return"],
                "baseline_family": family,
                "official_sample_eligible": bool(row["official_sample_eligible"]),
                "tradable_sample_eligible": _replay_tradable_sample_eligible(candidate_payload),
                "run_id": int(row["run_id"]),
                "run_date": row["run_date"],
                "account_profile": account_profile,
            }
        )
    return rows


def _latest_default_replay_run_ids(session: Session) -> set[int]:
    runs = (
        session.scalars(
            select(ShortpickExperimentRun)
            .where(
                ShortpickExperimentRun.information_mode == SHORTPICK_HISTORICAL_REPLAY_MODE,
                ShortpickExperimentRun.status == "completed",
            )
            .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickExperimentRun.id.asc())
        )
        .all()
    )
    latest_by_date: dict[date, int] = {}
    for run in runs:
        summary = dict(run.summary_payload or {})
        account_profile = str(summary.get("account_profile") or "")
        if account_profile != ACCOUNT_PROFILE_NEW_RETAIL_CASH:
            continue
        if _is_diagnostic_replay_run(run):
            continue
        if not _replay_run_has_completed_llm_sample(session, int(run.id)):
            continue
        latest_by_date[run.run_date] = int(run.id)
    return set(latest_by_date.values())


def _replay_run_has_completed_llm_sample(session: Session, run_id: int) -> bool:
    failed_llm_rounds = session.scalar(
        select(func.count())
        .select_from(ShortpickModelRound)
        .where(
            ShortpickModelRound.run_id == run_id,
            ShortpickModelRound.executor_kind == "historical_replay_sealed_packet_llm",
            ShortpickModelRound.status == "failed",
        )
    )
    if int(failed_llm_rounds or 0) > 0:
        return False
    llm_candidates = session.scalar(
        select(func.count())
        .select_from(ShortpickCandidate)
        .where(
            ShortpickCandidate.run_id == run_id,
            func.json_extract(ShortpickCandidate.candidate_payload, "$.baseline_family") == "llm",
        )
    )
    return int(llm_candidates or 0) > 0


def _replay_tradable_sample_eligible(candidate_payload: dict[str, Any]) -> bool:
    if not isinstance(candidate_payload, dict):
        return False
    tradeability = dict(candidate_payload.get("tradeability") or candidate_payload.get("universe_membership") or {})
    if tradeability and not bool(tradeability.get("is_tradeable", True)):
        return False
    reasons = {str(reason) for reason in candidate_payload.get("leakage_audit_reasons") or []}
    return not bool(reasons & SHORTPICK_REPLAY_HARD_LEAKAGE_REASONS)


def _replay_feedback_scope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    run_ids = sorted({int(row["run_id"]) for row in rows if row.get("run_id") is not None})
    dates = sorted({row["run_date"] for row in rows if row.get("run_date") is not None})
    return {
        "run_count": len(run_ids),
        "unique_replay_date_count": len(dates),
        "date_from": dates[0].isoformat() if dates else None,
        "date_to": dates[-1].isoformat() if dates else None,
    }


def _replay_statistical_gate(rows: list[dict[str, Any]], horizon_groups: list[dict[str, Any]]) -> dict[str, Any]:
    completed_official = [
        row
        for row in rows
        if row["official_sample_eligible"] and row["status"] == "completed"
    ]
    completed_tradable = [
        row
        for row in rows
        if row["tradable_sample_eligible"] and row["status"] == "completed"
    ]
    completed_dates = {row["run_date"] for row in completed_official if row.get("run_date") is not None}
    completed_tradable_dates = {row["run_date"] for row in completed_tradable if row.get("run_date") is not None}
    completed_symbols = {row["symbol"] for row in completed_official}
    completed_tradable_symbols = {row["symbol"] for row in completed_tradable}
    min_completed_samples = 30
    min_completed_dates = 5
    horizon_readiness = []
    for group in horizon_groups:
        completed_count = int(group.get("completed_official_sample_count") or 0)
        horizon_readiness.append(
            {
                "horizon": int(group["group_key"]),
                "completed_official_sample_count": completed_count,
                "completed_tradable_sample_count": int(group.get("completed_tradable_sample_count") or 0),
                "ready": completed_count >= min_completed_samples,
            }
        )
    ready_horizons = [item["horizon"] for item in horizon_readiness if item["ready"]]
    status = "ready" if len(completed_official) >= min_completed_samples and len(completed_dates) >= min_completed_dates else "exploratory"
    return {
        "status": status,
        "min_completed_samples": min_completed_samples,
        "min_completed_dates": min_completed_dates,
        "completed_official_sample_count": len(completed_official),
        "completed_tradable_sample_count": len(completed_tradable),
        "completed_date_count": len(completed_dates),
        "completed_tradable_date_count": len(completed_tradable_dates),
        "completed_symbol_count": len(completed_symbols),
        "completed_tradable_symbol_count": len(completed_tradable_symbols),
        "ready_horizons": ready_horizons,
        "horizon_readiness": horizon_readiness,
        "reason": (
            "Replay sample is broad enough for aggregate readout."
            if status == "ready"
            else "Replay sample is still exploratory; add more historical dates before treating family-level differences as statistically meaningful."
        ),
    }


def _replay_feedback_groups(rows: list[dict[str, Any]], *, group_key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row["horizon_days"] if group_key == "horizon" else row["baseline_family"])
        grouped.setdefault(key, []).append(row)
    output = []
    for key, values in sorted(grouped.items(), key=lambda item: _replay_group_sort_key(item[0], group_key=group_key)):
        completed = [
            row for row in values
            if row["official_sample_eligible"] and row["status"] == "completed"
        ]
        tradable_completed = [
            row for row in values
            if row["tradable_sample_eligible"] and row["status"] == "completed"
        ]
        excess = [float(row["excess_return"]) for row in completed if row["excess_return"] is not None]
        tradable_excess = [float(row["excess_return"]) for row in tradable_completed if row["excess_return"] is not None]
        stock_returns = [float(row["stock_return"]) for row in completed if row["stock_return"] is not None]
        tradable_stock_returns = [float(row["stock_return"]) for row in tradable_completed if row["stock_return"] is not None]
        output.append(
            {
                "group_key": key,
                "label": f"{key}日" if group_key == "horizon" else _baseline_label(key),
                "sample_count": len(values),
                "official_sample_count": len([row for row in values if row["official_sample_eligible"]]),
                "tradable_sample_count": len([row for row in values if row["tradable_sample_eligible"]]),
                "completed_official_sample_count": len(completed),
                "completed_tradable_sample_count": len(tradable_completed),
                "completed_validation_count": len([row for row in values if row["status"] == "completed"]),
                "mean_stock_return": _mean_or_none(stock_returns),
                "mean_excess_return": _mean_or_none(excess),
                "trimmed_mean_excess_return": _trimmed_mean_or_none(excess),
                "positive_excess_rate": _positive_rate(excess),
                "tradable_mean_stock_return": _mean_or_none(tradable_stock_returns),
                "tradable_mean_excess_return": _mean_or_none(tradable_excess),
                "tradable_trimmed_mean_excess_return": _trimmed_mean_or_none(tradable_excess),
                "tradable_positive_excess_rate": _positive_rate(tradable_excess),
                "benchmark_metrics": {},
                "status_counts": _count_by([row["status"] for row in values]),
            }
        )
    return output


def _replay_group_sort_key(key: str, *, group_key: str) -> tuple[int, int, str]:
    if group_key == "horizon":
        try:
            horizon = int(key)
        except ValueError:
            return (1, len(SHORTPICK_REPLAY_HORIZON_ORDER), key)
        if horizon in SHORTPICK_REPLAY_HORIZON_ORDER:
            return (0, SHORTPICK_REPLAY_HORIZON_ORDER.index(horizon), key)
        return (0, len(SHORTPICK_REPLAY_HORIZON_ORDER) + horizon, key)
    if group_key == "family" and key in SHORTPICK_REPLAY_BASELINE_FAMILIES:
        return (0, SHORTPICK_REPLAY_BASELINE_FAMILIES.index(key), key)
    return (1, 0, key)


def _robustness_metrics(rows: list[dict[str, Any]], *, eligibility_key: str = "official_sample_eligible") -> dict[str, Any]:
    completed = [
        row for row in rows
        if row.get(eligibility_key) and row["status"] == "completed" and row["excess_return"] is not None
    ]
    values = [float(row["excess_return"]) for row in completed]
    by_symbol: dict[str, list[float]] = {}
    by_date: dict[str, list[float]] = {}
    for row in completed:
        value = float(row["excess_return"])
        by_symbol.setdefault(row["symbol"], []).append(value)
        run = row["run_id"]
        date_key = str(run)
        by_date.setdefault(date_key, []).append(value)
    best_symbol = max(by_symbol, key=lambda key: _mean_or_none(by_symbol[key]) or -999.0) if by_symbol else None
    best_date = max(by_date, key=lambda key: _mean_or_none(by_date[key]) or -999.0) if by_date else None
    return {
        "raw_mean_excess_return": _mean_or_none(values),
        "trimmed_mean_excess_return": _trimmed_mean_or_none(values),
        "positive_excess_rate": _positive_rate(values),
        "drop_best_symbol_mean_excess_return": _mean_or_none([
            float(row["excess_return"])
            for row in completed
            if best_symbol is None or row["symbol"] != best_symbol
        ]),
        "drop_best_date_mean_excess_return": _mean_or_none([
            float(row["excess_return"])
            for row in completed
            if best_date is None or str(row["run_id"]) != best_date
        ]),
        "best_symbol": best_symbol,
        "sample_count": len(values),
    }


def _replay_confidence_intervals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    focus_rows = []
    for family in ("llm", "momentum_10d_turnover_cooldown_rank", "overall"):
        scoped_rows = rows if family == "overall" else [row for row in rows if row["baseline_family"] == family]
        for eligibility_key, label_suffix in (
            ("official_sample_eligible", "严格来源"),
            ("tradable_sample_eligible", "可交易"),
        ):
            row = _clustered_bootstrap_interval(
                scoped_rows,
                family=family,
                label_suffix=label_suffix,
                eligibility_key=eligibility_key,
                horizon_days=5,
            )
            if row:
                focus_rows.append(row)
    return {
        "status": "ready" if focus_rows else "missing_artifact",
        "method": "trading_day_clustered_bootstrap",
        "basis": "precomputed_replay_validation_rows",
        "note": "按 replay signal date 聚类抽样；策略晋级只参考置信区间下沿是否为正，不参考单一均值。",
        "rows": focus_rows,
    }


def _clustered_bootstrap_interval(
    rows: list[dict[str, Any]],
    *,
    family: str,
    label_suffix: str,
    eligibility_key: str,
    horizon_days: int,
) -> dict[str, Any] | None:
    completed = [
        row
        for row in rows
        if row.get(eligibility_key)
        and row["status"] == "completed"
        and int(row["horizon_days"]) == horizon_days
        and row["excess_return"] is not None
        and row.get("run_date") is not None
    ]
    by_date: dict[date, list[float]] = {}
    symbols: set[str] = set()
    for row in completed:
        by_date.setdefault(row["run_date"], []).append(float(row["excess_return"]))
        symbols.add(str(row["symbol"]))
    date_means = [_mean(values) for _, values in sorted(by_date.items()) if values]
    if len(date_means) < 2:
        return None
    rng = random.Random(f"shortpick-replay-ci:{family}:{eligibility_key}:{horizon_days}")
    bootstrap_means = []
    for _ in range(1000):
        sample = [date_means[rng.randrange(len(date_means))] for _ in date_means]
        bootstrap_means.append(_mean(sample))
    lower = _percentile(bootstrap_means, 0.025)
    upper = _percentile(bootstrap_means, 0.975)
    mean_value = _mean([float(row["excess_return"]) for row in completed])
    lower_positive = lower is not None and lower > 0
    family_label = "整体" if family == "overall" else _baseline_label(family)
    return {
        "id": f"{family}_{horizon_days}d_{eligibility_key.replace('_sample_eligible', '')}",
        "family": family,
        "label": f"{family_label} {horizon_days}日{label_suffix}",
        "horizon_days": horizon_days,
        "eligibility": eligibility_key.replace("_sample_eligible", ""),
        "mean_excess_return": None if mean_value is None else round(mean_value, 6),
        "lower_excess_return": None if lower is None else round(lower, 6),
        "upper_excess_return": None if upper is None else round(upper, 6),
        "lower_bound_positive": lower_positive,
        "promotion_decision": "eligible_by_ci_lower_bound" if lower_positive else "blocked_by_ci_lower_bound",
        "sample_date_count": len(date_means),
        "sample_stock_count": len(symbols),
        "sample_count": len(completed),
    }


def _replay_regime_stability_projection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    focus_families = ("llm", "momentum_10d_turnover_cooldown_rank")
    month_rows = _time_slice_rows(rows, period="month", focus_families=focus_families)
    quarter_rows = _time_slice_rows(rows, period="quarter", focus_families=focus_families)
    return {
        "status": "ready" if month_rows or quarter_rows else "missing_artifact",
        "basis": "precomputed_replay_validation_rows",
        "time_slices": {
            "month": month_rows,
            "quarter": quarter_rows,
        },
        "market_regime": {
            "status": "missing_artifact",
            "reason": "历史 replay cache 当前没有逐日市场状态标签；后续需要离线补齐 regime artifact。",
        },
        "industry_theme": {
            "status": "missing_artifact",
            "reason": "历史 replay cache 当前没有行业/题材归因字段；后续需要离线补齐行业映射 artifact。",
        },
    }


def _time_slice_rows(
    rows: list[dict[str, Any]],
    *,
    period: str,
    focus_families: tuple[str, ...],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row["baseline_family"] not in focus_families:
            continue
        if int(row["horizon_days"]) != 5:
            continue
        if not row["tradable_sample_eligible"] or row["status"] != "completed" or row["excess_return"] is None:
            continue
        run_date = row.get("run_date")
        if not isinstance(run_date, date):
            continue
        if period == "quarter":
            period_key = f"{run_date.year}-Q{((run_date.month - 1) // 3) + 1}"
        else:
            period_key = f"{run_date.year}-{run_date.month:02d}"
        grouped.setdefault((str(row["baseline_family"]), period_key), []).append(row)
    output = []
    for (family, period_key), values in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        excess = [float(row["excess_return"]) for row in values]
        dates = {row["run_date"] for row in values}
        output.append(
            {
                "family": family,
                "label": _baseline_label(family),
                "period": period_key,
                "horizon_days": 5,
                "mean_excess_return": _round_or_none(_mean(excess)),
                "positive_excess_rate": _positive_rate(excess),
                "sample_count": len(excess),
                "sample_date_count": len(dates),
            }
        )
    return output


def _replay_return_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    focus = [
        ("overall", rows),
        ("llm", [row for row in rows if row["baseline_family"] == "llm"]),
        (
            "momentum_10d_turnover_cooldown_rank",
            [row for row in rows if row["baseline_family"] == "momentum_10d_turnover_cooldown_rank"],
        ),
    ]
    return {
        "status": "ready" if rows else "missing_artifact",
        "basis": "precomputed_replay_validation_rows",
        "horizon_days": 5,
        "rows": [
            row
            for family, family_rows in focus
            if (row := _return_attribution_row(family, family_rows)) is not None
        ],
        "industry_theme": {
            "status": "missing_artifact",
            "reason": "行业/题材级最佳最差贡献需要行业映射 artifact，当前不在页面请求时临时补齐。",
        },
    }


def _return_attribution_row(family: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed = [
        row
        for row in rows
        if row["tradable_sample_eligible"]
        and row["status"] == "completed"
        and int(row["horizon_days"]) == 5
        and row["excess_return"] is not None
    ]
    if not completed:
        return None
    values = [float(row["excess_return"]) for row in completed]
    by_symbol = _group_excess(completed, "symbol")
    by_date = _group_excess(completed, "run_date")
    by_month: dict[str, list[float]] = {}
    for row in completed:
        run_date = row.get("run_date")
        if isinstance(run_date, date):
            by_month.setdefault(f"{run_date.year}-{run_date.month:02d}", []).append(float(row["excess_return"]))
    best_symbol, best_symbol_mean = _best_group(by_symbol)
    worst_symbol, worst_symbol_mean = _worst_group(by_symbol)
    best_date, best_date_mean = _best_group(by_date)
    worst_date, worst_date_mean = _worst_group(by_date)
    best_month, best_month_mean = _best_group(by_month)
    worst_month, worst_month_mean = _worst_group(by_month)
    return {
        "family": family,
        "label": "整体" if family == "overall" else _baseline_label(family),
        "mean_excess_return": _round_or_none(_mean(values)),
        "sample_count": len(values),
        "best_symbol": best_symbol,
        "best_symbol_mean_excess_return": _round_or_none(best_symbol_mean),
        "worst_symbol": worst_symbol,
        "worst_symbol_mean_excess_return": _round_or_none(worst_symbol_mean),
        "best_date": None if best_date is None else str(best_date),
        "best_date_mean_excess_return": _round_or_none(best_date_mean),
        "worst_date": None if worst_date is None else str(worst_date),
        "worst_date_mean_excess_return": _round_or_none(worst_date_mean),
        "best_month": best_month,
        "best_month_mean_excess_return": _round_or_none(best_month_mean),
        "worst_month": worst_month,
        "worst_month_mean_excess_return": _round_or_none(worst_month_mean),
        "drop_best_symbol_mean_excess_return": _round_or_none(_mean([
            float(row["excess_return"])
            for row in completed
            if best_symbol is None or row["symbol"] != best_symbol
        ])),
        "drop_best_date_mean_excess_return": _round_or_none(_mean([
            float(row["excess_return"])
            for row in completed
            if best_date is None or row["run_date"] != best_date
        ])),
        "drop_best_month_mean_excess_return": _round_or_none(_mean([
            float(row["excess_return"])
            for row in completed
            if best_month is None
            or not isinstance(row.get("run_date"), date)
            or f"{row['run_date'].year}-{row['run_date'].month:02d}" != best_month
        ])),
    }


def _group_excess(rows: list[dict[str, Any]], key: str) -> dict[Any, list[float]]:
    grouped: dict[Any, list[float]] = {}
    for row in rows:
        group_key = row.get(key)
        if group_key is None:
            continue
        grouped.setdefault(group_key, []).append(float(row["excess_return"]))
    return grouped


def _best_group(grouped: dict[Any, list[float]]) -> tuple[Any | None, float | None]:
    if not grouped:
        return None, None
    key = max(grouped, key=lambda item: _mean(grouped[item]) or -999.0)
    return key, _mean(grouped[key])


def _worst_group(grouped: dict[Any, list[float]]) -> tuple[Any | None, float | None]:
    if not grouped:
        return None, None
    key = min(grouped, key=lambda item: _mean(grouped[item]) or 999.0)
    return key, _mean(grouped[key])


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


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
    if any(source_id not in allowed_source_ids for source_id in used_source_ids):
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


def _linked_sources_for_symbol(packet: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    return [source for source in packet["official_sources"] if symbol in (source.get("linked_symbols") or [])][:3]


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


def _write_replay_round_artifact(
    session: Session,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound,
    *,
    prompt: str | None,
) -> None:
    write_shortpick_lab_artifact(
        artifact_id=str(round_record.artifact_id),
        root=_artifact_root(session),
        payload={
            "artifact_id": round_record.artifact_id,
            "artifact_type": "shortpick_historical_replay_round",
            "run_key": run.run_key,
            "round_key": round_record.round_key,
            "prompt_version": run.prompt_version,
            "information_mode": run.information_mode,
            "provider_name": round_record.provider_name,
            "model_name": round_record.model_name,
            "executor_kind": round_record.executor_kind,
            "status": round_record.status,
            "source_packet_id": (run.summary_payload or {}).get("source_packet_id"),
            "source_packet_hash": (run.summary_payload or {}).get("source_packet_hash"),
            "prompt": prompt,
            "raw_answer": round_record.raw_answer,
            "parsed_payload": round_record.parsed_payload,
            "sources": round_record.sources_payload,
            "error_message": round_record.error_message,
            "generated_at": utcnow().isoformat(),
            "boundary": "historical_replay_no_main_pool_write",
        },
    )


def _candidate_thesis(member: _UniverseMember, baseline_family: str) -> str:
    ret = _bar_return(member)
    if baseline_family == "llm":
        return f"{member.name} 在 sealed packet 的可得来源/题材中被选中，回放仅使用当日之前信息；最新日收益 {ret:.2%}。"
    if baseline_family == "llm_self_distilled":
        return f"{member.name} 由 LLM 在自身原选池中二次蒸馏保留，回放仅使用当日之前信息；最新日收益 {ret:.2%}。"
    if baseline_family == "llm_momentum_distilled":
        return f"{member.name} 由 LLM 在扩大动量池中蒸馏保留，回放仅使用当日之前信息；最新日收益 {ret:.2%}。"
    if baseline_family == "momentum_volume_baseline":
        return f"{member.name} 由动量成交量基准选中：截至当日日收益 {ret:.2%}，成交额 {member.latest_bar.amount:.0f}。"
    if baseline_family == "momentum_volume_expanded_pool":
        return f"{member.name} 进入扩大动量成交量候选池：截至当日日收益 {ret:.2%}，成交额 {member.latest_bar.amount:.0f}。"
    if baseline_family == "llm_reject_only":
        return f"{member.name} 在扩大动量池中未被 LLM 剔除；截至当日日收益 {ret:.2%}，成交额 {member.latest_bar.amount:.0f}。"
    if baseline_family == "llm_reject_then_momentum_rank":
        return f"{member.name} 先通过 LLM 只剔除检查，再按原动量成交量排序入选；截至当日日收益 {ret:.2%}。"
    if baseline_family == "random_reject_then_momentum_rank":
        return f"{member.name} 由随机剔除同等数量候选后按原动量排序入选；截至当日日收益 {ret:.2%}。"
    if baseline_family == "momentum_turnover_rank":
        return f"{member.name} 在扩大动量池中按换手率再排序入选；截至当日日收益 {ret:.2%}，换手率 {member.turnover_rate or 0:.2%}。"
    if baseline_family == "momentum_10d_rank":
        return f"{member.name} 在扩大动量池中按 10 日持续动量再排序入选；截至当日日收益 {ret:.2%}。"
    if baseline_family == "momentum_10d_turnover_rank":
        return f"{member.name} 在扩大动量池中按 10 日持续动量与换手率复合排序入选；截至当日日收益 {ret:.2%}。"
    if baseline_family == "momentum_10d_turnover_cooldown_rank":
        return f"{member.name} 在扩大动量池中按 10 日持续动量、换手率与单日追高惩罚复合排序入选；截至当日日收益 {ret:.2%}。"
    if baseline_family == "momentum_continuity_turnover_rank":
        return f"{member.name} 在扩大动量池中按短动量、5日持续性与换手率复合排序入选；截至当日日收益 {ret:.2%}。"
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
                market_cap_source=member.market_cap_source,
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


def _market_cap_for_universe_member(stock: Stock, latest: MarketBar) -> tuple[float | None, str]:
    candidates = [
        (latest.total_mv, "market_bar.total_mv"),
        (latest.circ_mv, "market_bar.circ_mv"),
        (_nested_float(latest.raw_payload, ("total_mv",)), "market_bar.raw_payload.total_mv"),
        (_nested_float(latest.raw_payload, ("circ_mv",)), "market_bar.raw_payload.circ_mv"),
        (_nested_float(latest.raw_payload, ("market_cap",)), "market_bar.raw_payload.market_cap"),
    ]
    profile = stock.profile_payload if isinstance(stock.profile_payload, dict) else {}
    candidates.extend(
        [
            (_nested_float(profile, ("total_mv",)), "stock.profile_payload.total_mv"),
            (_nested_float(profile, ("circ_mv",)), "stock.profile_payload.circ_mv"),
            (_nested_float(profile, ("market_cap",)), "stock.profile_payload.market_cap"),
            (_nested_float(profile, ("total_market_cap",)), "stock.profile_payload.total_market_cap"),
            (_nested_float(profile, ("analysis_pipeline", "market_cap", "total_mv")), "stock.profile_payload.analysis_pipeline.market_cap.total_mv"),
            (_nested_float(profile, ("analysis_pipeline", "market_cap", "circ_mv")), "stock.profile_payload.analysis_pipeline.market_cap.circ_mv"),
        ]
    )
    for value, source in candidates:
        if value is not None and value > 0:
            return float(value), source
    try:
        from ashare_evidence.signal_engine_parts.market_cap_seed import SEED_MARKET_CAP
    except Exception:
        seed_market_cap = {}
    else:
        seed_market_cap = SEED_MARKET_CAP
    seed_value = seed_market_cap.get(stock.symbol)
    if seed_value is not None and seed_value > 0:
        return float(seed_value), "market_cap_seed"
    return None, "missing"


def _nested_float(payload: Any, path: tuple[str, ...]) -> float | None:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    try:
        if current is None or current == "":
            return None
        return float(current)
    except (TypeError, ValueError):
        return None


def _source_excerpt(value: str | None, *, limit: int = 600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _candidate_payload(candidate: ShortpickCandidate) -> dict[str, Any]:
    return candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}


def _ensure_replay_candidate_contract(candidate: ShortpickCandidate) -> dict[str, Any]:
    payload = dict(_candidate_payload(candidate))
    membership = dict(payload.get("universe_membership") or {})
    tradeability = dict(payload.get("tradeability") or {})
    if not tradeability:
        tradeability = {
            "in_universe": bool(membership.get("in_universe", True)),
            "is_tradeable": bool(membership.get("is_tradeable", True)),
            "excluded_reason": payload.get("exclusion_reason"),
            "market_cap_bucket": membership.get("market_cap_bucket") or payload.get("market_cap_bucket") or "unknown",
            "industry": membership.get("industry") or payload.get("industry") or candidate.normalized_theme or "unknown",
            "turnover_rate": membership.get("turnover_rate"),
        }
    payload["tradeability"] = tradeability
    payload["market_cap_bucket"] = payload.get("market_cap_bucket") or tradeability.get("market_cap_bucket") or "unknown"
    payload["industry"] = payload.get("industry") or tradeability.get("industry") or candidate.normalized_theme or "unknown"
    payload["limitations"] = list(payload.get("limitations") or candidate.limitations or [])
    candidate.candidate_payload = payload
    return payload


def _candidate_baseline_family(candidate: ShortpickCandidate) -> str:
    return str(_candidate_payload(candidate).get("baseline_family") or "unknown")


def _is_llm_replay_family(value: str) -> bool:
    return value in {"llm", "llm_self_distilled", "llm_momentum_distilled"}


def _baseline_label(value: str) -> str:
    labels = {
        "llm": "LLM",
        "llm_self_distilled": "LLM自选蒸馏",
        "llm_momentum_distilled": "LLM动量池蒸馏",
        "random_same_tradeable_universe": "随机",
        "random_same_market_cap_bucket": "同市值随机",
        "momentum_volume_baseline": "动量成交量",
        "momentum_volume_expanded_pool": "扩大动量池",
        "llm_reject_only": "LLM只剔除保留池",
        "llm_reject_then_momentum_rank": "LLM剔除后动量排序",
        "random_reject_then_momentum_rank": "随机剔除后动量排序",
        "llm_hard_veto_then_momentum_rank": "LLM硬否决后动量排序",
        "random_hard_veto_then_momentum_rank": "随机硬否决后动量排序",
        "llm_strict_veto_then_momentum_rank": "LLM严格否决后动量排序",
        "random_strict_veto_then_momentum_rank": "随机严格否决后动量排序",
        "momentum_turnover_rank": "换手优先动量排序",
        "momentum_10d_rank": "10日持续动量排序",
        "momentum_10d_turnover_rank": "10日动量换手复合排序",
        "momentum_10d_turnover_cooldown_rank": "10日动量换手降追高排序",
        "momentum_continuity_turnover_rank": "持续动量换手复合排序",
    }
    return labels.get(value, value)


def _pending_replay_benchmark_dimensions(*, reason: str) -> dict[str, dict[str, Any]]:
    return {
        "hs300": {
            "dimension_key": "hs300",
            "benchmark_id": "CSI300",
            "label": "沪深300",
            "benchmark_label": "沪深300",
            "symbol": "000300.SH",
            "symbol_or_scope": "000300.SH",
            "benchmark_return": None,
            "excess_return": None,
            "status": "pending_forward_window",
            "reason": reason,
        },
        "csi1000": {
            "dimension_key": "csi1000",
            "benchmark_id": "CSI1000",
            "label": "中证1000",
            "benchmark_label": "中证1000",
            "symbol": "000852.SH",
            "symbol_or_scope": "000852.SH",
            "benchmark_return": None,
            "excess_return": None,
            "status": "pending_forward_window",
            "reason": reason,
        },
        "sector_equal_weight": {
            "dimension_key": "sector_equal_weight",
            "benchmark_id": "sector_equal_weight",
            "label": "同板块",
            "benchmark_label": "同板块",
            "symbol": None,
            "symbol_or_scope": None,
            "benchmark_return": None,
            "excess_return": None,
            "status": "historical_replay_existing_only",
            "reason": "Historical replay does not fetch or expand sector peer universe.",
            "peer_symbol_count": 0,
            "contributing_peer_symbol_count": 0,
        },
    }


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
