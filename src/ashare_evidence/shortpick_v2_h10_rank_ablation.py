from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH
from ashare_evidence.shortpick_market_factor_study import ENTRY_PRICE_SOURCE_NEXT_CLOSE, ENTRY_PRICE_SOURCES
from ashare_evidence.shortpick_v2_replay import DEFAULT_COST_BPS, DEFAULT_INITIAL_CASH, DEFAULT_STAMP_TAX_BPS
from ashare_evidence.shortpick_v2_strategy_search import (
    STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION,
    build_shortpick_v2_strategy_search_artifact,
)

SHORTPICK_V2_H10_RANK_ABLATION_ARTIFACT_FAMILY = "shortpick_v2_h10_rank_ablation_artifact"
SHORTPICK_V2_H10_RANK_ABLATION_SCHEMA_VERSION = "v1"
SHORTPICK_V2_H10_RANK_ABLATION_SOURCE_PLAN_REF = "plans/active/plan-20260615-h10-rank-ablation.md"
RESEARCH_OBSERVATION_CLAIM_CEILING = "research_observation"
H10_QUIET_RANK_SOURCE_PREFIX = "quiet_breakout_rank"
H10_QUIET_RANK_SOURCE_SUFFIX = "_poolhot10_mtw"
MANDATORY_RANKS = (1, 2, 3)
DIAGNOSTIC_RANKS = (4, 5)
PRIMARY_NOTIONAL = 85_000
INFORMATIONAL_NOTIONALS = (80_000, 90_000)
MIN_SAMPLE_COUNT = 50
MIN_PERIOD_BLOCK_COUNT = 3
TOTAL_RETURN_DELTA_THRESHOLD = 0.03
MAX_DRAWDOWN_DETERIORATION = 0.03
VALID_SUPPORT_LABELS = {"supported", "inconclusive", "challenged"}


def build_shortpick_v2_h10_rank_ablation_artifact(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 10,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = 45,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if horizon_days != 10:
        raise ValueError("h10 rank ablation requires horizon_days=10")
    replay_artifact = build_shortpick_v2_strategy_search_artifact(
        session,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        min_signal_symbol_count=min_signal_symbol_count,
        account_profile=account_profile,
        candidate_batch=STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION,
        generated_at=generated_at,
    )
    return build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
        replay_artifact,
        generated_at=generated_at,
    )


def build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
    replay_artifact: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    _validate_replay_artifact(replay_artifact)
    generated_at = generated_at or datetime.now(UTC)
    data_scope = dict(replay_artifact.get("data_scope") or {})
    horizon_days = _replay_horizon_days(replay_artifact)
    period_block_count = _year_block_count(data_scope)
    results_by_config = _results_by_config(replay_artifact)

    primary_rows = [
        _rank_row(rank, notional=PRIMARY_NOTIONAL, results_by_config=results_by_config, period_block_count=period_block_count)
        for rank in (*MANDATORY_RANKS, *DIAGNOSTIC_RANKS)
    ]
    decision = _rank2_decision([row for row in primary_rows if int(row["rank"]) in MANDATORY_RANKS])
    challenger_ranks = set(decision.get("challenger_ranks") or [])
    for row in primary_rows:
        rank = int(row["rank"])
        # Non-baseline labels are relative to rank2 governance; diagnostic ranks never promote themselves here.
        if _row_has_weak_coverage(row):
            row["support_label"] = "inconclusive"
        elif rank == 2:
            row["support_label"] = decision["support_label"]
        elif rank in challenger_ranks:
            row["support_label"] = "challenged"
        else:
            row["support_label"] = "inconclusive"

    execution_context_rows = [
        _rank_row(rank, notional=notional, results_by_config=results_by_config, period_block_count=period_block_count)
        | {"support_label": "inconclusive", "informational_only": True}
        for notional in INFORMATIONAL_NOTIONALS
        for rank in MANDATORY_RANKS
    ]
    payload = {
        "artifact_family": SHORTPICK_V2_H10_RANK_ABLATION_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_H10_RANK_ABLATION_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, data_scope),
        "generated_at": generated_at.isoformat(),
        "status": "ready",
        "claim_ceiling": RESEARCH_OBSERVATION_CLAIM_CEILING,
        "evidence_basis": "historical_same_gate_rank_ablation",
        "source_plan_ref": SHORTPICK_V2_H10_RANK_ABLATION_SOURCE_PLAN_REF,
        "source_replay_artifact": _source_replay_ref(replay_artifact),
        "analysis_scope": {
            "candidate_batch": STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION,
            "baseline_source_id": _rank_source_id(2),
            "mandatory_ranks": list(MANDATORY_RANKS),
            "diagnostic_ranks": list(DIAGNOSTIC_RANKS),
            "primary_notional": PRIMARY_NOTIONAL,
            "informational_notionals": list(INFORMATIONAL_NOTIONALS),
            "signal_date_from": data_scope.get("signal_date_from"),
            "signal_date_to": data_scope.get("signal_date_to"),
            "signal_day_count": data_scope.get("signal_day_count"),
            "horizon_days": horizon_days,
            "initial_cash": _account_initial_cash(replay_artifact),
            "period_block_count": period_block_count,
            "period_block_definition": "calendar years covered by the replay signal_date_from/signal_date_to range",
        },
        "analysis_policy": {
            "horizon_policy": "H10 is fixed by prior evidence and is not retested here.",
            "rank_decision_thresholds": _decision_thresholds(),
            "support_label_policy": (
                "Primary fixed85 rank rows with sample_count < 50 or period_block_count < 3 are inconclusive. "
                "Rank2 support requires at least a 0.03 total-return edge versus rank1/rank3 and no material "
                "drawdown deterioration. A comparator challenges rank2 when it has at least a 0.03 total-return "
                "edge and no material drawdown deterioration."
            ),
            "execution_context_policy": (
                "Fixed80 and fixed90 rows are informational execution-pressure context only; they cannot override "
                "the primary fixed85 rank2 support decision."
            ),
            "promotion_policy": "This artifact cannot start paper tracking or replace the benchmark.",
        },
        "rank2_decision": decision,
        "rank_rows": primary_rows,
        "execution_context_rows": execution_context_rows,
        "recommendation": {
            "status": "research_only_no_paper_tracking_promotion",
            "rank2_status": decision["support_label"],
            "notes": [
                "Treat the rank result as same-window historical evidence, not causal proof.",
                "A challenged outcome requires a separate benchmark-governance plan before any replacement.",
            ],
        },
        "leakage_audit": {
            "status": "passed",
            "used_only_replay_artifact_and_signal_day_candidate_sources": True,
            "no_delayed_buy_action": True,
            "no_database_write_or_refresh": True,
        },
        "event_refs": [
            "shortpick_v2.h10_rank_ablation.generated",
            f"shortpick_v2.h10_rank_ablation.source_replay.{replay_artifact.get('artifact_id')}",
        ],
    }
    validation = validate_shortpick_v2_h10_rank_ablation_payload(payload)
    if validation["failed_check_count"]:
        payload["status"] = "blocked"
    return payload


def write_shortpick_v2_h10_rank_ablation_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def validate_shortpick_v2_h10_rank_ablation_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("rank ablation artifact must contain a JSON object")
    return validate_shortpick_v2_h10_rank_ablation_payload(payload)


def validate_shortpick_v2_h10_rank_ablation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    policy = payload.get("analysis_policy") if isinstance(payload.get("analysis_policy"), dict) else {}
    decision = payload.get("rank2_decision") if isinstance(payload.get("rank2_decision"), dict) else {}
    rank_rows = [row for row in payload.get("rank_rows") or [] if isinstance(row, dict)]
    rows_by_rank = {int(row["rank"]): row for row in rank_rows if _optional_int(row.get("rank")) is not None}
    thresholds = policy.get("rank_decision_thresholds") if isinstance(policy.get("rank_decision_thresholds"), dict) else {}

    _add_check(checks, "artifact_family", payload.get("artifact_family") == SHORTPICK_V2_H10_RANK_ABLATION_ARTIFACT_FAMILY)
    _add_check(checks, "schema_version", payload.get("schema_version") == SHORTPICK_V2_H10_RANK_ABLATION_SCHEMA_VERSION)
    _add_check(checks, "status_ready", payload.get("status") == "ready")
    _add_check(checks, "claim_ceiling", payload.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING)
    _add_check(checks, "horizon_days_fixed_h10", scope.get("horizon_days") == 10)
    _add_check(checks, "baseline_source_rank2", scope.get("baseline_source_id") == _rank_source_id(2))
    _add_check(checks, "mandatory_ranks", tuple(scope.get("mandatory_ranks") or []) == MANDATORY_RANKS)
    _add_check(checks, "period_block_definition", bool(scope.get("period_block_definition")))
    _add_check(checks, "recommendation_research_only", (payload.get("recommendation") or {}).get("status") == "research_only_no_paper_tracking_promotion")
    _add_check(checks, "no_delayed_buy", (payload.get("leakage_audit") or {}).get("no_delayed_buy_action") is True)
    _add_check(checks, "threshold_min_sample", thresholds.get("min_sample_count") == MIN_SAMPLE_COUNT)
    _add_check(checks, "threshold_min_period_blocks", thresholds.get("min_period_block_count") == MIN_PERIOD_BLOCK_COUNT)
    _add_check(checks, "threshold_total_return_delta", thresholds.get("total_return_delta_threshold") == TOTAL_RETURN_DELTA_THRESHOLD)
    _add_check(checks, "threshold_drawdown", thresholds.get("max_drawdown_deterioration") == MAX_DRAWDOWN_DETERIORATION)

    for rank in MANDATORY_RANKS:
        row = rows_by_rank.get(rank)
        _add_check(checks, f"rank_{rank}_row_present", row is not None)
        if row is None:
            continue
        _validate_rank_row(checks, row, rank=rank, mandatory=True)
    for row in rank_rows:
        rank = int(row["rank"])
        if rank not in MANDATORY_RANKS:
            _validate_rank_row(checks, row, rank=rank, mandatory=False)

    decision_label = decision.get("support_label")
    _add_check(checks, "rank2_decision_label_valid", decision_label in VALID_SUPPORT_LABELS)
    recomputed = _rank2_decision([rows_by_rank[rank] for rank in MANDATORY_RANKS if rank in rows_by_rank])
    _add_check(
        checks,
        "rank2_decision_matches_rows",
        decision_label == recomputed.get("support_label"),
        {"expected": recomputed.get("support_label"), "actual": decision_label},
    )
    rank2_row = rows_by_rank.get(2)
    _add_check(
        checks,
        "rank2_row_matches_decision",
        rank2_row is not None and rank2_row.get("support_label") == decision_label,
        {"rank2_row_label": rank2_row.get("support_label") if rank2_row else None, "decision_label": decision_label},
    )

    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "artifact_id": payload.get("artifact_id"),
            "horizon_days": scope.get("horizon_days"),
            "rank2_status": decision_label,
            "rank_row_count": len(rank_rows),
        },
    }


def _validate_rank_row(checks: list[dict[str, Any]], row: dict[str, Any], *, rank: int, mandatory: bool) -> None:
    support_label = str(row.get("support_label") or "")
    sample_count = _optional_int(row.get("sample_count"))
    period_block_count = _optional_int(row.get("period_block_count"))
    result_status = str(row.get("result_status") or "")
    _add_check(checks, f"rank_{rank}_support_label_valid", support_label in VALID_SUPPORT_LABELS)
    _add_check(checks, f"rank_{rank}_sample_count_present", sample_count is not None and sample_count >= 0)
    _add_check(checks, f"rank_{rank}_period_block_count_present", period_block_count is not None and period_block_count >= 0)
    if mandatory:
        _add_check(checks, f"rank_{rank}_result_present", result_status == "present")
    if sample_count is not None and period_block_count is not None:
        sparse = sample_count < MIN_SAMPLE_COUNT or period_block_count < MIN_PERIOD_BLOCK_COUNT
        _add_check(
            checks,
            f"rank_{rank}_sparse_rows_inconclusive",
            not sparse or support_label == "inconclusive",
            {"support_label": support_label, "sample_count": sample_count, "period_block_count": period_block_count},
        )
    _add_check(checks, f"rank_{rank}_promotion_blocked", row.get("promotion_status") == "not_eligible")
    _add_check(checks, f"rank_{rank}_comparison_present", isinstance(row.get("comparison_to_rank2"), dict))


def _rank_row(
    rank: int,
    *,
    notional: int,
    results_by_config: dict[str, dict[str, Any]],
    period_block_count: int,
) -> dict[str, Any]:
    config_id = _fixed_notional_config_id(_rank_source_id(rank), notional)
    summary = _summary_for_config(results_by_config, config_id)
    rank2_summary = _summary_for_config(results_by_config, _fixed_notional_config_id(_rank_source_id(2), notional))
    return {
        "rank": rank,
        "source_id": _rank_source_id(rank),
        "config_id": config_id,
        "notional": notional,
        "comparison_role": "baseline_rank2" if rank == 2 else ("mandatory_comparator" if rank in MANDATORY_RANKS else "diagnostic_comparator"),
        "result_status": "present" if summary else "missing",
        "support_label": "inconclusive",
        "sample_count": int(summary.get("trade_count") or 0),
        "period_block_count": period_block_count,
        "evidence_basis": "statistical",
        "summary": _summary_projection(summary),
        "comparison_to_rank2": _comparison_to_rank2(summary, rank2_summary),
        "promotion_status": "not_eligible",
    }


def _rank2_decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows_by_rank = {int(row["rank"]): row for row in rows if _optional_int(row.get("rank")) is not None}
    missing = [rank for rank in MANDATORY_RANKS if rank not in rows_by_rank or rows_by_rank[rank].get("result_status") != "present"]
    if missing:
        return _decision("inconclusive", reason_codes=["missing_mandatory_rank_rows"], challenger_ranks=[], missing_ranks=missing)
    weak = [rank for rank in MANDATORY_RANKS if _row_has_weak_coverage(rows_by_rank[rank])]
    if weak:
        return _decision("inconclusive", reason_codes=["weak_mandatory_rank_coverage"], challenger_ranks=[], weak_ranks=weak)
    rank2 = rows_by_rank[2]
    rank2_return = _optional_float((rank2.get("summary") or {}).get("total_return"))
    rank2_drawdown = _optional_float((rank2.get("summary") or {}).get("max_drawdown"))
    comparator_rows = [rows_by_rank[1], rows_by_rank[3]]
    comparator_returns = [_optional_float((row.get("summary") or {}).get("total_return")) for row in comparator_rows]
    comparator_drawdowns = [_optional_float((row.get("summary") or {}).get("max_drawdown")) for row in comparator_rows]
    if rank2_return is None or rank2_drawdown is None or any(value is None for value in comparator_returns + comparator_drawdowns):
        return _decision("inconclusive", reason_codes=["missing_return_or_drawdown"], challenger_ranks=[])
    challenger_ranks = [
        int(row["rank"])
        for row, comparator_return, comparator_drawdown in zip(comparator_rows, comparator_returns, comparator_drawdowns, strict=True)
        if comparator_return is not None
        and comparator_drawdown is not None
        and _return_edge(comparator_return, rank2_return) >= TOTAL_RETURN_DELTA_THRESHOLD
        and _drawdown_deterioration(comparator_drawdown, rank2_drawdown) <= MAX_DRAWDOWN_DETERIORATION
    ]
    if challenger_ranks:
        return _decision("challenged", reason_codes=["mandatory_comparator_outperformed_rank2"], challenger_ranks=challenger_ranks)
    best_comparator_return = max(value for value in comparator_returns if value is not None)
    max_rank2_drawdown_deterioration = max(
        _drawdown_deterioration(rank2_drawdown, value) for value in comparator_drawdowns if value is not None
    )
    if (
        _return_edge(rank2_return, best_comparator_return) >= TOTAL_RETURN_DELTA_THRESHOLD
        and max_rank2_drawdown_deterioration <= MAX_DRAWDOWN_DETERIORATION
    ):
        return _decision(
            "supported",
            reason_codes=["rank2_return_edge_without_material_drawdown_deterioration"],
            challenger_ranks=[],
        )
    return _decision("inconclusive", reason_codes=["rank2_edge_below_threshold"], challenger_ranks=[])


def _decision(support_label: str, *, reason_codes: list[str], challenger_ranks: list[int], **extra: Any) -> dict[str, Any]:
    return {
        "support_label": support_label,
        "reason_codes": reason_codes,
        "challenger_ranks": challenger_ranks,
        "thresholds": _decision_thresholds(),
        "promotion_status": "not_eligible",
        **extra,
    }


def _decision_thresholds() -> dict[str, Any]:
    return {
        "min_sample_count": MIN_SAMPLE_COUNT,
        "min_period_block_count": MIN_PERIOD_BLOCK_COUNT,
        "total_return_delta_threshold": TOTAL_RETURN_DELTA_THRESHOLD,
        "max_drawdown_deterioration": MAX_DRAWDOWN_DETERIORATION,
    }


def _row_has_weak_coverage(row: dict[str, Any]) -> bool:
    sample_count = _optional_int(row.get("sample_count")) or 0
    period_block_count = _optional_int(row.get("period_block_count")) or 0
    return sample_count < MIN_SAMPLE_COUNT or period_block_count < MIN_PERIOD_BLOCK_COUNT


def _return_edge(left_return: float, right_return: float) -> float:
    return round(left_return - right_return, 9)


def _drawdown_deterioration(left_drawdown: float, right_drawdown: float) -> float:
    return max(0.0, round(right_drawdown - left_drawdown, 9))


def _comparison_to_rank2(summary: dict[str, Any], rank2_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_return_delta": _delta(summary, rank2_summary, "total_return"),
        "annualized_return_delta": _delta(summary, rank2_summary, "annualized_return"),
        "max_drawdown_delta": _delta(summary, rank2_summary, "max_drawdown"),
        "trade_count_delta": _delta(summary, rank2_summary, "trade_count"),
    }


def _fixed_notional_config_id(source_id: str, notional: int) -> str:
    return f"{source_id}__fixed_notional_{int(notional / 1000)}k_top5_h10_v1"


def _rank_source_id(rank: int) -> str:
    return f"{H10_QUIET_RANK_SOURCE_PREFIX}{rank}{H10_QUIET_RANK_SOURCE_SUFFIX}"


def _validate_replay_artifact(replay_artifact: dict[str, Any]) -> None:
    if replay_artifact.get("artifact_family") != "shortpick_v2_replay_artifact":
        raise ValueError("rank ablation requires a shortpick_v2_replay_artifact input")
    if _replay_horizon_days(replay_artifact) != 10:
        raise ValueError("h10 rank ablation requires horizon_days=10")


def _results_by_config(replay_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("config_id")): row
        for row in replay_artifact.get("results") or []
        if isinstance(row, dict) and row.get("config_id")
    }


def _summary_for_config(results_by_config: dict[str, dict[str, Any]], config_id: str) -> dict[str, Any]:
    row = results_by_config.get(config_id) or {}
    summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    return dict(summary)


def _summary_projection(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "signal_count",
        "trade_count",
        "skip_count",
        "fallback_trade_count",
        "total_return",
        "annualized_return",
        "market_excess_total_return",
        "max_drawdown",
        "turnover",
        "skipped_ratio",
    )
    return {key: summary.get(key) for key in keys if key in summary}


def _delta(left_summary: dict[str, Any], right_summary: dict[str, Any], key: str) -> float | int | None:
    left_value = _optional_float(left_summary.get(key))
    right_value = _optional_float(right_summary.get(key))
    if left_value is None or right_value is None:
        return None
    value = round(left_value - right_value, 9)
    return int(value) if key.endswith("count") else value


def _replay_horizon_days(replay_artifact: dict[str, Any]) -> int | None:
    input_contracts = replay_artifact.get("input_contracts") if isinstance(replay_artifact.get("input_contracts"), dict) else {}
    exit_model = input_contracts.get("exit_model") if isinstance(input_contracts.get("exit_model"), dict) else {}
    return _optional_int(exit_model.get("holding_days"))


def _account_initial_cash(replay_artifact: dict[str, Any]) -> float | None:
    input_contracts = replay_artifact.get("input_contracts") if isinstance(replay_artifact.get("input_contracts"), dict) else {}
    account = input_contracts.get("account") if isinstance(input_contracts.get("account"), dict) else {}
    return _optional_float(account.get("initial_cash"))


def _year_block_count(data_scope: dict[str, Any]) -> int:
    start = _optional_date(data_scope.get("signal_date_from"))
    end = _optional_date(data_scope.get("signal_date_to"))
    if start is None or end is None or end < start:
        return 0
    return end.year - start.year + 1


def _source_replay_ref(replay_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": str(replay_artifact.get("artifact_id") or ""),
        "artifact_family": str(replay_artifact.get("artifact_family") or ""),
        "schema_version": str(replay_artifact.get("schema_version") or ""),
        "status": str(replay_artifact.get("status") or ""),
        "claim_ceiling": str(replay_artifact.get("claim_ceiling") or ""),
    }


def _artifact_id(generated_at: datetime, data_scope: dict[str, Any]) -> str:
    start = str(data_scope.get("signal_date_from") or "unknown")
    end = str(data_scope.get("signal_date_to") or "unknown")
    generated_day = generated_at.astimezone(UTC).strftime("%Y%m%d")
    return f"shortpick_v2_h10_rank_ablation:{start}:{end}:{generated_day}"


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    detail: dict[str, Any] | None = None,
) -> None:
    checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail or {}})
