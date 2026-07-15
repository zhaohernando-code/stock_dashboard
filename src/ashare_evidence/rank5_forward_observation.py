from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from ashare_evidence.rank5_path_quality import PATH_QUALITY_FEATURE_KEYS

RANK5_FORWARD_OBSERVATION_ARTIFACT_ID = "shortpick-v3-rank5-forward-observation-v1"
RANK5_FORWARD_OBSERVATION_SCHEMA_VERSION = "shortpick_v3_rank5_forward_observation.v1"
RANK5_FORWARD_OBSERVATION_START_DATE = date(2026, 7, 15)
RANK5_FORWARD_CAPTURE_MODE = "daily_forward_capture"
RANK5_FORWARD_BENCHMARK_SYMBOL = "000300.SH"
RANK5_FORWARD_RETURN_HORIZON = 20
RANK5_RESEARCH_REOPEN_MIN_MATURED = 80
RANK5_RESEARCH_REOPEN_MIN_MONTHS = 6
RANK5_RESEARCH_REOPEN_MIN_DAYS = 120
RANK5_PROMOTION_MIN_ACTUAL_CLOSED = 20
RANK5_PROMOTION_MIN_MONTHS = 12
RANK5_PROMOTION_MIN_DAYS = 365


def build_rank5_shadow_observation(
    *,
    strategy_id: str,
    signal_date: str,
    planned_trade_date: str,
    original_pick: dict[str, Any],
    candidate: dict[str, Any],
    inventory_sequence: int,
    shadow_base_eligible: bool,
    base_eligibility_reason: str | None,
) -> dict[str, Any]:
    """Freeze a signal-day Rank5 candidate row without any forward outcome fields."""

    key_payload = {
        "strategy_id": strategy_id,
        "signal_date": signal_date,
        "original_symbol": str(original_pick.get("symbol") or ""),
        "candidate_symbol": str(candidate.get("symbol") or ""),
        "inventory_sequence": inventory_sequence,
    }
    encoded = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    observation_key = "rank5-forward-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]
    path_features = {key: _safe_float(candidate.get(key)) for key in PATH_QUALITY_FEATURE_KEYS}
    observation_count = int(_safe_float(candidate.get("path_feature_observation_count")) or 0)
    feature_complete = observation_count == RANK5_FORWARD_RETURN_HORIZON and all(
        value is not None for value in path_features.values()
    )
    return {
        "observation_key": observation_key,
        "strategy_id": strategy_id,
        "signal_date": signal_date,
        "planned_trade_date": planned_trade_date,
        "original_symbol": str(original_pick.get("symbol") or ""),
        "original_rank": int(_safe_float(original_pick.get("rank")) or 0),
        "original_score": _safe_float(original_pick.get("score")),
        "candidate_symbol": str(candidate.get("symbol") or ""),
        "candidate_name": str(candidate.get("stock_name") or candidate.get("name") or ""),
        "candidate_inventory_rank": 5,
        "candidate_score": _safe_float(candidate.get("score")),
        "inventory_sequence": inventory_sequence,
        "shadow_base_eligible": shadow_base_eligible,
        "base_eligibility_reason": base_eligibility_reason,
        "path_feature_observation_count": observation_count,
        "path_feature_complete": feature_complete,
        **path_features,
        "selected_by_current_r14": False,
        "selection_decision": "shadow_base_eligible" if shadow_base_eligible else "shadow_base_rejected",
        "source_candidate_artifact_id": None,
        "paper_source_capture_mode": None,
        "evidence_eligible": False,
        "maturity_status": "pending_source_contract",
        "entry_trade_date": None,
        "entry_price_cny": None,
        "exit_trade_date": None,
        "exit_price_cny": None,
        "candidate_return_20d": None,
        "benchmark_return_20d": None,
        "candidate_excess_return_20d": None,
        "actual_executed": False,
        "actual_closed": False,
        "actual_return": None,
    }


def build_rank5_forward_observation_artifact(
    observations: list[dict[str, Any]],
    *,
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    paper_records: list[dict[str, Any]],
    as_of_day: date,
) -> dict[str, Any]:
    """Resolve deterministic shadow outcomes and compute frozen readiness gates."""

    observation_keys = [str(row.get("observation_key") or "") for row in observations]
    missing_key_count = sum(not key for key in observation_keys)
    populated_keys = [key for key in observation_keys if key]
    duplicate_count = len(populated_keys) - len(set(populated_keys))
    unique_by_key: dict[str, dict[str, Any]] = {}
    for source_row in observations:
        key = str(source_row.get("observation_key") or "")
        if key and key not in unique_by_key:
            unique_by_key[key] = dict(source_row)
    records_by_key: dict[str, list[dict[str, Any]]] = {}
    for record in paper_records:
        key = str(record.get("rank5_forward_observation_key") or "")
        if key:
            records_by_key.setdefault(key, []).append(record)
    normalized_bars = {
        symbol: _normalized_bars(rows)
        for symbol, rows in market_bars_by_symbol.items()
    }
    benchmark_by_day = dict(normalized_bars.get(RANK5_FORWARD_BENCHMARK_SYMBOL, []))
    resolved_rows: list[dict[str, Any]] = []
    for row in unique_by_key.values():
        signal_day = _iso_day(row.get("signal_date"))
        capture_mode = str(row.get("paper_source_capture_mode") or "")
        path_complete = row.get("path_feature_complete") is True
        shadow_base_eligible = row.get("shadow_base_eligible") is True
        evidence_eligible = bool(
            signal_day
            and signal_day >= RANK5_FORWARD_OBSERVATION_START_DATE
            and capture_mode == RANK5_FORWARD_CAPTURE_MODE
            and path_complete
            and shadow_base_eligible
        )
        row["evidence_eligible"] = evidence_eligible
        if not evidence_eligible:
            row["maturity_status"] = _exclusion_status(
                signal_day=signal_day,
                capture_mode=capture_mode,
                path_complete=path_complete,
                shadow_base_eligible=shadow_base_eligible,
            )
        else:
            _resolve_shadow_outcome(
                row,
                normalized_bars.get(str(row.get("candidate_symbol") or ""), []),
                benchmark_by_day=benchmark_by_day,
            )
        linked_records = records_by_key.get(str(row.get("observation_key") or ""), [])
        row["actual_executed"] = any(record.get("action") == "buy" for record in linked_records)
        closed = next(
            (
                record
                for record in reversed(linked_records)
                if record.get("action") == "sell" and _safe_float(record.get("return")) is not None
            ),
            None,
        )
        row["actual_closed"] = closed is not None
        row["actual_return"] = _safe_float((closed or {}).get("return"))
        resolved_rows.append(row)
    resolved_rows.sort(key=lambda row: (str(row.get("signal_date") or ""), str(row.get("observation_key") or "")))

    forward_source_rows = [
        row
        for row in resolved_rows
        if (_iso_day(row.get("signal_date")) or date.min) >= RANK5_FORWARD_OBSERVATION_START_DATE
        and row.get("paper_source_capture_mode") == RANK5_FORWARD_CAPTURE_MODE
        and row.get("shadow_base_eligible") is True
    ]
    matured = [row for row in forward_source_rows if row.get("maturity_status") == "matured_20d"]
    missing_path_count = sum(row.get("path_feature_complete") is not True for row in forward_source_rows)
    premature_outcome_count = sum(
        row.get("maturity_status") != "matured_20d"
        and any(row.get(key) is not None for key in _OUTCOME_KEYS)
        for row in resolved_rows
    )
    signal_months = sorted({str(row.get("signal_date") or "")[:7] for row in matured})
    first_eligible_day = min(
        (_iso_day(row.get("signal_date")) for row in forward_source_rows),
        default=None,
    )
    elapsed_days = max((as_of_day - first_eligible_day).days, 0) if first_eligible_day else 0
    actual_closed_count = sum(row.get("actual_closed") is True for row in forward_source_rows)
    data_quality_passed = (
        missing_key_count == 0
        and duplicate_count == 0
        and missing_path_count == 0
        and premature_outcome_count == 0
    )
    research_reopen_ready = bool(
        data_quality_passed
        and len(matured) >= RANK5_RESEARCH_REOPEN_MIN_MATURED
        and len(signal_months) >= RANK5_RESEARCH_REOPEN_MIN_MONTHS
        and elapsed_days >= RANK5_RESEARCH_REOPEN_MIN_DAYS
    )
    promotion_evidence_ready = bool(
        research_reopen_ready
        and actual_closed_count >= RANK5_PROMOTION_MIN_ACTUAL_CLOSED
        and len(signal_months) >= RANK5_PROMOTION_MIN_MONTHS
        and elapsed_days >= RANK5_PROMOTION_MIN_DAYS
    )
    progress = {
        "as_of_date": as_of_day.isoformat(),
        "captured_observation_count": len(resolved_rows),
        "forward_base_eligible_count": len(forward_source_rows),
        "matured_shadow_observation_count": len(matured),
        "pending_shadow_observation_count": sum(
            row.get("evidence_eligible") is True and row.get("maturity_status") != "matured_20d"
            for row in resolved_rows
        ),
        "distinct_matured_signal_month_count": len(signal_months),
        "matured_signal_months": signal_months,
        "elapsed_calendar_days": elapsed_days,
        "actual_executed_rank5_count": sum(row.get("actual_executed") is True for row in forward_source_rows),
        "actual_closed_rank5_count": actual_closed_count,
        "path_feature_complete_count": sum(row.get("path_feature_complete") is True for row in forward_source_rows),
        "path_feature_complete_rate": (
            sum(row.get("path_feature_complete") is True for row in forward_source_rows) / len(forward_source_rows)
            if forward_source_rows
            else 1.0
        ),
        "duplicate_observation_key_count": duplicate_count,
        "missing_observation_key_count": missing_key_count,
        "missing_path_feature_count": missing_path_count,
        "premature_future_outcome_count": premature_outcome_count,
        "return_horizon_trading_days": RANK5_FORWARD_RETURN_HORIZON,
        "research_reopen_min_matured": RANK5_RESEARCH_REOPEN_MIN_MATURED,
        "research_reopen_min_months": RANK5_RESEARCH_REOPEN_MIN_MONTHS,
        "research_reopen_min_days": RANK5_RESEARCH_REOPEN_MIN_DAYS,
        "promotion_min_actual_closed": RANK5_PROMOTION_MIN_ACTUAL_CLOSED,
        "promotion_min_months": RANK5_PROMOTION_MIN_MONTHS,
        "promotion_min_days": RANK5_PROMOTION_MIN_DAYS,
        "research_reopen_ready": research_reopen_ready,
        "promotion_evidence_ready": promotion_evidence_ready,
        "data_quality_passed": data_quality_passed,
    }
    return {
        "artifact_id": RANK5_FORWARD_OBSERVATION_ARTIFACT_ID,
        "schema_version": RANK5_FORWARD_OBSERVATION_SCHEMA_VERSION,
        "status": (
            "blocked_data_quality"
            if not data_quality_passed
            else "promotion_evidence_floor_reached"
            if promotion_evidence_ready
            else "research_reopen_gate_reached"
            if research_reopen_ready
            else "collecting_forward_observations"
        ),
        "claim_ceiling": "forward_paper_observation_readiness_only_not_investment_advice",
        "contract_ref": "docs/contracts/SHORTPICK_V3_RANK5_FORWARD_OBSERVATION_CONTRACT_2026-07-15.json",
        "observation_start_signal_date": RANK5_FORWARD_OBSERVATION_START_DATE.isoformat(),
        "active_rank5_quality_policy": None,
        "progress": progress,
        "rows": resolved_rows,
    }


_OUTCOME_KEYS = ("candidate_return_20d", "benchmark_return_20d", "candidate_excess_return_20d")


def _resolve_shadow_outcome(
    row: dict[str, Any],
    candidate_bars: list[tuple[date, float]],
    *,
    benchmark_by_day: dict[date, float],
) -> None:
    signal_day = _iso_day(row.get("signal_date"))
    entry_index = next(
        (index for index, (bar_day, _) in enumerate(candidate_bars) if signal_day and bar_day > signal_day),
        None,
    )
    if entry_index is None:
        row["maturity_status"] = "pending_entry_close"
        return
    exit_index = entry_index + RANK5_FORWARD_RETURN_HORIZON
    entry_day, entry_price = candidate_bars[entry_index]
    row["entry_trade_date"] = entry_day.isoformat()
    row["entry_price_cny"] = entry_price
    row["available_followup_trading_days"] = max(len(candidate_bars) - entry_index - 1, 0)
    if exit_index >= len(candidate_bars):
        row["maturity_status"] = "pending_20d_window"
        return
    exit_day, exit_price = candidate_bars[exit_index]
    benchmark_entry = benchmark_by_day.get(entry_day)
    benchmark_exit = benchmark_by_day.get(exit_day)
    if benchmark_entry is None or benchmark_exit is None:
        row["maturity_status"] = "pending_benchmark_alignment"
        return
    candidate_return = exit_price / entry_price - 1.0
    benchmark_return = benchmark_exit / benchmark_entry - 1.0
    row.update(
        {
            "maturity_status": "matured_20d",
            "exit_trade_date": exit_day.isoformat(),
            "exit_price_cny": exit_price,
            "candidate_return_20d": candidate_return,
            "benchmark_return_20d": benchmark_return,
            "candidate_excess_return_20d": candidate_return - benchmark_return,
        }
    )


def _exclusion_status(
    *,
    signal_day: date | None,
    capture_mode: str,
    path_complete: bool,
    shadow_base_eligible: bool,
) -> str:
    if signal_day is None:
        return "excluded_invalid_signal_date"
    if signal_day < RANK5_FORWARD_OBSERVATION_START_DATE:
        return "excluded_before_observation_window"
    if capture_mode != RANK5_FORWARD_CAPTURE_MODE:
        return "excluded_not_true_forward_capture"
    if not shadow_base_eligible:
        return "excluded_base_rejected"
    if not path_complete:
        return "excluded_incomplete_path_features"
    return "excluded_unknown_contract_failure"


def _normalized_bars(rows: list[dict[str, Any]]) -> list[tuple[date, float]]:
    by_day: dict[date, float] = {}
    for row in rows:
        day = _iso_day(row.get("day"))
        close = _safe_float(row.get("close"))
        if day is not None and close is not None and close > 0:
            by_day[day] = close
    return sorted(by_day.items())


def _iso_day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
