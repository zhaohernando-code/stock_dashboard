from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH
from ashare_evidence.shortpick_market_factor_study import ENTRY_PRICE_SOURCE_NEXT_CLOSE, ENTRY_PRICE_SOURCES
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)
from ashare_evidence.shortpick_v2_strategy_search import (
    STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION,
    build_shortpick_v2_strategy_search_artifact,
)

SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_ARTIFACT_FAMILY = (
    "shortpick_v2_h10_parameter_significance_artifact"
)
SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_SCHEMA_VERSION = "v1"
SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_SOURCE_PLAN_REF = (
    "plans/active/plan-20260615-h10-parameter-significance.md"
)
H10_QUIET_PRIMARY_SOURCE_ID = "quiet_breakout_rank2_poolhot10_mtw"
H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID = (
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1"
)
RESEARCH_OBSERVATION_CLAIM_CEILING = "research_observation"
REQUIRED_PARAMETER_FAMILIES = (
    "weekday_gate",
    "rank_choice",
    "pool_hot_threshold",
    "fixed_notional",
    "fallback_skip",
    "concentration_stability",
)
VALID_SUPPORT_LABELS = {"supported", "inconclusive", "rejected"}
VALID_EVIDENCE_BASIS = {"statistical", "logical", "mixed", "diagnostic"}


def build_shortpick_v2_h10_parameter_significance_artifact(
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
        raise ValueError("h10 parameter significance requires horizon_days=10")
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
    return build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact(
        replay_artifact,
        generated_at=generated_at,
    )


def build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact(
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
    rule_by_config = _rule_by_config(replay_artifact)
    benchmark_summary = _summary_for_config(results_by_config, H10_QUIET_CHAMPION_CONFIG_ID)
    benchmark_trade_count = int(benchmark_summary.get("trade_count") or 0)

    rows = [
        _delta_parameter_row(
            parameter_family="weekday_gate",
            parameter_id="weekday_gate_mtw_vs_mt_tw",
            label="MTW weekday gate versus MT/TW controls",
            baseline_config_id=H10_QUIET_CHAMPION_CONFIG_ID,
            comparator_config_ids=[
                _fixed85_config_id("quiet_breakout_rank2_poolhot10_mt"),
                _fixed85_config_id("quiet_breakout_rank2_poolhot10_tw"),
            ],
            results_by_config=results_by_config,
            period_block_count=period_block_count,
            evidence_basis="statistical",
            notes=[
                "This is a same-window historical ablation over existing MT/TW controls.",
                "It is not causal proof that Monday through Wednesday is inherently superior.",
            ],
        ),
        _rank_choice_row(
            benchmark_summary=benchmark_summary,
            period_block_count=period_block_count,
        ),
        _delta_parameter_row(
            parameter_family="pool_hot_threshold",
            parameter_id="pool_hot_threshold_10_vs_09_11_12",
            label="pool_ret1_mean >= 0.10 versus nearby 0.09/0.11/0.12 thresholds",
            baseline_config_id=H10_QUIET_CHAMPION_CONFIG_ID,
            comparator_config_ids=[
                _fixed85_config_id("quiet_breakout_rank2_poolhot09_mtw"),
                _fixed85_config_id("quiet_breakout_rank2_poolhot11_mtw"),
                _fixed85_config_id("quiet_breakout_rank2_poolhot12_mtw"),
            ],
            results_by_config=results_by_config,
            period_block_count=period_block_count,
            evidence_basis="statistical",
            notes=[
                "Threshold support requires baseline outperformance against nearby local thresholds.",
                "A better neighbor should trigger a follow-up plan rather than silent promotion.",
            ],
        ),
        _delta_parameter_row(
            parameter_family="fixed_notional",
            parameter_id="fixed_notional_85k_vs_80k",
            label="85k primary fixed notional versus 80k capital-shadow baseline",
            baseline_config_id=H10_QUIET_CHAMPION_CONFIG_ID,
            comparator_config_ids=[H10_QUIET_CAPITAL_SHADOW_CONFIG_ID],
            results_by_config=results_by_config,
            period_block_count=period_block_count,
            evidence_basis="mixed",
            notes=[
                "85k is tested as the current benchmark notional, while 80k remains the capital-shadow baseline.",
                "The row does not authorize raising the notional boundary.",
            ],
        ),
        _diagnostic_90k_row(
            results_by_config=results_by_config,
            period_block_count=period_block_count,
        ),
        _fallback_skip_row(
            benchmark_summary=benchmark_summary,
            rule_by_config=rule_by_config,
            period_block_count=period_block_count,
        ),
        _concentration_stability_row(
            benchmark_summary=benchmark_summary,
            period_block_count=period_block_count,
        ),
    ]
    families = [
        {
            "family_id": family,
            "row_count": sum(1 for row in rows if row.get("parameter_family") == family),
        }
        for family in REQUIRED_PARAMETER_FAMILIES
    ]
    failed_validation = validate_shortpick_v2_h10_parameter_significance_payload({"parameter_rows": rows})[
        "failed_check_count"
    ]
    status = "ready" if rows and failed_validation == 0 else "blocked"
    return {
        "artifact_family": SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, data_scope),
        "generated_at": generated_at.isoformat(),
        "status": status,
        "claim_ceiling": RESEARCH_OBSERVATION_CLAIM_CEILING,
        "evidence_basis": "historical_parameter_ablation_and_governance_validation",
        "source_plan_ref": SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_SOURCE_PLAN_REF,
        "source_replay_artifact": _source_replay_ref(replay_artifact),
        "analysis_scope": {
            "candidate_batch": STRATEGY_SEARCH_BATCH_H10_QUIET_CHAMPION,
            "baseline_source_id": H10_QUIET_PRIMARY_SOURCE_ID,
            "benchmark_config_ids": [
                H10_QUIET_CHAMPION_CONFIG_ID,
                H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
            ],
            "diagnostic_config_ids": [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID],
            "signal_date_from": data_scope.get("signal_date_from"),
            "signal_date_to": data_scope.get("signal_date_to"),
            "signal_day_count": data_scope.get("signal_day_count"),
            "horizon_days": horizon_days,
            "initial_cash": _account_initial_cash(replay_artifact),
            "period_block_count": period_block_count,
            "benchmark_trade_count": benchmark_trade_count,
            "parameter_family_count": len(families),
        },
        "analysis_policy": {
            "horizon_policy": "H10 is fixed by prior v1 evidence and is not retested here.",
            "support_label_policy": (
                "Rows with period_block_count < 3 are automatically inconclusive. Supported/rejected rows must "
                "carry non-empty machine-readable evidence, not only narrative notes."
            ),
            "promotion_policy": (
                "This artifact is a research/governance artifact only. It cannot start paper tracking, promote 90k, "
                "or replace the current benchmark without a follow-up governed plan."
            ),
        },
        "parameter_families": families,
        "parameter_rows": rows,
        "recommendation": {
            "status": "research_only_no_paper_tracking_promotion",
            "notes": [
                "Treat supported labels as historical evidence, not causal proof.",
                "Treat inconclusive labels as follow-up validation targets, not hidden approvals.",
                "90k remains diagnostic-only even when its headline return is higher.",
            ],
        },
        "leakage_audit": {
            "status": "passed",
            "used_only_replay_artifact_and_signal_day_candidate_sources": True,
            "no_delayed_buy_action": True,
            "no_database_write_or_refresh": True,
            "notes": [
                "The builder consumes a strategy-search replay artifact or read-only database bars.",
                "Parameter labels summarize existing same-window replay evidence; no future paper-tracking data is used.",
            ],
        },
        "event_refs": [
            "shortpick_v2.h10_parameter_significance.generated",
            f"shortpick_v2.parameter_significance.source_replay.{replay_artifact.get('artifact_id')}",
        ],
    }


def write_shortpick_v2_h10_parameter_significance_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def validate_shortpick_v2_h10_parameter_significance_artifact(
    *,
    artifact_path: str | Path,
) -> dict[str, Any]:
    path = Path(artifact_path)
    checks: list[dict[str, Any]] = []
    payload = _load_json(path, checks)
    if payload is not None:
        checks.extend(validate_shortpick_v2_h10_parameter_significance_payload(payload)["checks"])
    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "artifact_path": str(path),
        "artifact_summary": _artifact_summary(payload),
        "checks": checks,
    }


def validate_shortpick_v2_h10_parameter_significance_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    rows = payload.get("parameter_rows") if isinstance(payload.get("parameter_rows"), list) else []
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    row_families = {str(row.get("parameter_family")) for row in rows if isinstance(row, dict)}

    if "artifact_family" in payload:
        _add_check(
            checks,
            "parameter_significance_family_ready",
            payload.get("artifact_family") == SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_ARTIFACT_FAMILY
            and payload.get("status") == "ready",
            "Artifact family/status must be ready h10 parameter significance",
            {"artifact_family": payload.get("artifact_family"), "status": payload.get("status")},
        )
        _add_check(
            checks,
            "parameter_significance_claim_ceiling_research_only",
            payload.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING,
            "Artifact claim ceiling must remain research_observation",
            {"claim_ceiling": payload.get("claim_ceiling")},
        )
        _add_check(
            checks,
            "parameter_significance_horizon_fixed_h10",
            scope.get("horizon_days") == 10,
            "Artifact analysis scope must keep horizon_days fixed at 10",
            {"horizon_days": scope.get("horizon_days")},
        )
        _add_check(
            checks,
            "parameter_significance_no_paper_tracking_promotion",
            str((payload.get("recommendation") or {}).get("status") or "").startswith("research_only"),
            "Artifact recommendation must not promote paper tracking",
            {"recommendation_status": (payload.get("recommendation") or {}).get("status")},
        )
        benchmark_ids = set(scope.get("benchmark_config_ids") or [])
        _add_check(
            checks,
            "parameter_significance_benchmark_context_present",
            {H10_QUIET_CHAMPION_CONFIG_ID, H10_QUIET_CAPITAL_SHADOW_CONFIG_ID} <= benchmark_ids,
            "Artifact must retain fixed85/fixed80 benchmark context",
            {"benchmark_config_ids": sorted(benchmark_ids)},
        )

    _add_check(
        checks,
        "parameter_significance_required_families",
        set(REQUIRED_PARAMETER_FAMILIES) <= row_families,
        "Artifact must cover required parameter families",
        {"required": list(REQUIRED_PARAMETER_FAMILIES), "actual": sorted(row_families)},
    )
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _add_check(checks, f"parameter_row_{index}_object", False, "Parameter row must be an object")
            continue
        _validate_parameter_row(row, checks, index)

    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "checks": checks,
    }


def _validate_parameter_row(row: dict[str, Any], checks: list[dict[str, Any]], index: int) -> None:
    row_id = str(row.get("parameter_id") or f"row_{index}")
    required_fields = {
        "parameter_family",
        "parameter_id",
        "support_label",
        "sample_count",
        "period_block_count",
        "evidence_basis",
        "comparison_evidence",
    }
    missing_fields = sorted(field for field in required_fields if field not in row)
    support_label = str(row.get("support_label") or "")
    evidence_basis = str(row.get("evidence_basis") or "")
    sample_count = _optional_int(row.get("sample_count"))
    period_block_count = _optional_int(row.get("period_block_count"))
    comparison_evidence = row.get("comparison_evidence")
    comparison_non_empty = isinstance(comparison_evidence, dict) and bool(comparison_evidence)

    _add_check(
        checks,
        f"parameter_row_{index}_required_fields",
        not missing_fields,
        "Parameter row must include required support fields",
        {"parameter_id": row_id, "missing_fields": missing_fields},
    )
    _add_check(
        checks,
        f"parameter_row_{index}_support_label_valid",
        support_label in VALID_SUPPORT_LABELS,
        "Parameter row support_label must be supported, inconclusive, or rejected",
        {"parameter_id": row_id, "support_label": support_label},
    )
    _add_check(
        checks,
        f"parameter_row_{index}_evidence_basis_valid",
        evidence_basis in VALID_EVIDENCE_BASIS,
        "Parameter row evidence_basis must be statistical, logical, mixed, or diagnostic",
        {"parameter_id": row_id, "evidence_basis": evidence_basis},
    )
    _add_check(
        checks,
        f"parameter_row_{index}_sample_count_present",
        sample_count is not None and sample_count >= 0,
        "Parameter row sample_count must be a non-negative integer",
        {"parameter_id": row_id, "sample_count": row.get("sample_count")},
    )
    _add_check(
        checks,
        f"parameter_row_{index}_period_block_count_present",
        period_block_count is not None and period_block_count >= 0,
        "Parameter row period_block_count must be a non-negative integer",
        {"parameter_id": row_id, "period_block_count": row.get("period_block_count")},
    )
    sparse = period_block_count is not None and period_block_count < 3
    _add_check(
        checks,
        f"parameter_row_{index}_sparse_blocks_inconclusive",
        not sparse or support_label == "inconclusive",
        "Rows with period_block_count < 3 must be inconclusive",
        {"parameter_id": row_id, "period_block_count": period_block_count, "support_label": support_label},
    )
    directional_claim = support_label in {"supported", "rejected"}
    _add_check(
        checks,
        f"parameter_row_{index}_directional_claim_has_evidence",
        not directional_claim or (comparison_non_empty and sample_count is not None and sample_count > 0),
        "Supported/rejected rows must have non-empty comparison evidence and sample count",
        {"parameter_id": row_id, "support_label": support_label, "sample_count": sample_count},
    )
    diagnostic_only = bool(row.get("diagnostic_only"))
    _add_check(
        checks,
        f"parameter_row_{index}_diagnostic_not_promoted",
        not diagnostic_only
        or (support_label == "inconclusive" and row.get("promotion_status") == "not_eligible"),
        "Diagnostic rows must remain inconclusive and not eligible for promotion",
        {"parameter_id": row_id, "support_label": support_label, "promotion_status": row.get("promotion_status")},
    )


def _validate_replay_artifact(replay_artifact: dict[str, Any]) -> None:
    if replay_artifact.get("artifact_family") != SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY:
        raise ValueError("parameter significance requires a shortpick_v2_replay_artifact source")
    if replay_artifact.get("status") != "ready":
        raise ValueError("source replay artifact status must be ready")
    if replay_artifact.get("claim_ceiling") != RESEARCH_OBSERVATION_CLAIM_CEILING:
        raise ValueError("source replay artifact must remain research_observation")
    if _replay_horizon_days(replay_artifact) != 10:
        raise ValueError("parameter significance source replay must use horizon_days=10")


def _delta_parameter_row(
    *,
    parameter_family: str,
    parameter_id: str,
    label: str,
    baseline_config_id: str,
    comparator_config_ids: list[str],
    results_by_config: dict[str, dict[str, Any]],
    period_block_count: int,
    evidence_basis: str,
    notes: list[str],
) -> dict[str, Any]:
    baseline_summary = _summary_for_config(results_by_config, baseline_config_id)
    comparator_rows = [
        {
            "config_id": config_id,
            "summary": _summary_projection(_summary_for_config(results_by_config, config_id)),
            "total_return_delta_vs_baseline": _delta(
                baseline_summary,
                _summary_for_config(results_by_config, config_id),
                "total_return",
            ),
            "max_drawdown_delta_vs_baseline": _delta(
                baseline_summary,
                _summary_for_config(results_by_config, config_id),
                "max_drawdown",
            ),
        }
        for config_id in comparator_config_ids
    ]
    sample_count = int(baseline_summary.get("trade_count") or 0)
    support_label = _support_from_total_return_delta(
        baseline_summary,
        [row["summary"] for row in comparator_rows],
        sample_count=sample_count,
        period_block_count=period_block_count,
    )
    return {
        "parameter_family": parameter_family,
        "parameter_id": parameter_id,
        "label": label,
        "support_label": support_label,
        "sample_count": sample_count,
        "period_block_count": period_block_count,
        "evidence_basis": evidence_basis,
        "comparison_evidence": {
            "baseline_config_id": baseline_config_id,
            "baseline_summary": _summary_projection(baseline_summary),
            "comparators": comparator_rows,
        },
        "notes": notes,
    }


def _rank_choice_row(
    *,
    benchmark_summary: dict[str, Any],
    period_block_count: int,
) -> dict[str, Any]:
    return {
        "parameter_family": "rank_choice",
        "parameter_id": "rank_choice_rank2_direct_ablation_missing",
        "label": "rank2 selection against direct rank1/rank3 ablations",
        "support_label": "inconclusive",
        "sample_count": int(benchmark_summary.get("trade_count") or 0),
        "period_block_count": period_block_count,
        "evidence_basis": "logical",
        "comparison_evidence": {
            "baseline_selection_rank": 2,
            "available_direct_rank_ablation_config_ids": [],
            "missing_direct_rank_ablation_config_ids": ["rank1_same_gate", "rank3_same_gate"],
        },
        "notes": [
            "Current source names and implementation select the second quiet-breakout rank.",
            "Direct rank1/rank3 same-gate ablations are not present in the existing replay batch, so no support claim is made.",
        ],
    }


def _diagnostic_90k_row(
    *,
    results_by_config: dict[str, dict[str, Any]],
    period_block_count: int,
) -> dict[str, Any]:
    summary = _summary_for_config(results_by_config, H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID)
    return {
        "parameter_family": "fixed_notional",
        "parameter_id": "fixed_notional_90k_diagnostic_boundary",
        "label": "90k fixed-notional execution pressure boundary",
        "support_label": "inconclusive",
        "sample_count": int(summary.get("trade_count") or 0),
        "period_block_count": period_block_count,
        "evidence_basis": "diagnostic",
        "diagnostic_only": True,
        "promotion_status": "not_eligible",
        "comparison_evidence": {
            "diagnostic_config_id": H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
            "diagnostic_summary": _summary_projection(summary),
            "boundary_reason": "90k previously exceeded the turnover governance boundary and is diagnostic only.",
        },
        "notes": [
            "90k can appear in sensitivity readouts but cannot become a promoted parameter in this plan.",
        ],
    }


def _fallback_skip_row(
    *,
    benchmark_summary: dict[str, Any],
    rule_by_config: dict[str, dict[str, Any]],
    period_block_count: int,
) -> dict[str, Any]:
    rule = rule_by_config.get(H10_QUIET_CHAMPION_CONFIG_ID) or {}
    allowed_actions = [str(item) for item in rule.get("allowed_actions") or []]
    fallback_policy = rule.get("fallback_policy") if isinstance(rule.get("fallback_policy"), dict) else {}
    signal_count = int(benchmark_summary.get("signal_count") or 0)
    has_delayed_action = any("delay" in action for action in allowed_actions)
    support_label = (
        "supported"
        if period_block_count >= 3
        and signal_count > 0
        and bool(fallback_policy.get("enabled"))
        and "buy_fallback" in allowed_actions
        and "skip" in allowed_actions
        and not has_delayed_action
        else "inconclusive"
    )
    return {
        "parameter_family": "fallback_skip",
        "parameter_id": "action_choice_fallback_or_skip_no_delay",
        "label": "fallback-or-skip action model with no delayed buy",
        "support_label": support_label,
        "sample_count": signal_count,
        "period_block_count": period_block_count,
        "evidence_basis": "logical",
        "comparison_evidence": {
            "allowed_actions": allowed_actions,
            "fallback_enabled": bool(fallback_policy.get("enabled")),
            "fallback_max_rank": fallback_policy.get("max_rank"),
            "trade_count": benchmark_summary.get("trade_count"),
            "fallback_trade_count": benchmark_summary.get("fallback_trade_count"),
            "skip_count": benchmark_summary.get("skip_count"),
            "skipped_ratio": benchmark_summary.get("skipped_ratio"),
        },
        "notes": [
            "The action set remains explainable: buy the current candidate, use a predeclared fallback, or skip.",
            "Delayed buy is intentionally absent because it has no stable interpretation in this strategy context.",
        ],
    }


def _concentration_stability_row(
    *,
    benchmark_summary: dict[str, Any],
    period_block_count: int,
) -> dict[str, Any]:
    return {
        "parameter_family": "concentration_stability",
        "parameter_id": "winner_concentration_and_period_stability_detail_missing",
        "label": "winner concentration and weak-period stability evidence",
        "support_label": "inconclusive",
        "sample_count": int(benchmark_summary.get("trade_count") or 0),
        "period_block_count": period_block_count,
        "evidence_basis": "mixed",
        "comparison_evidence": {
            "baseline_summary": _summary_projection(benchmark_summary),
            "missing_detail_refs": ["trade_contribution_table", "period_reset_replay"],
        },
        "notes": [
            "Replay summaries expose drawdown and turnover, but not enough trade-contribution detail for support.",
            "Robustness/decomposition artifacts should remain the source for winner-concentration judgement.",
        ],
    }


def _support_from_total_return_delta(
    baseline_summary: dict[str, Any],
    comparator_summaries: list[dict[str, Any]],
    *,
    sample_count: int,
    period_block_count: int,
) -> str:
    if period_block_count < 3 or sample_count <= 0:
        return "inconclusive"
    baseline_return = _optional_float(baseline_summary.get("total_return"))
    valid_comparator_returns = [
        value
        for summary in comparator_summaries
        for value in [_optional_float(summary.get("total_return"))]
        if value is not None
    ]
    if baseline_return is None or not valid_comparator_returns:
        return "inconclusive"
    deltas = [baseline_return - value for value in valid_comparator_returns]
    if min(deltas) >= 0.03:
        return "supported"
    if max(deltas) <= -0.03:
        return "rejected"
    return "inconclusive"


def _support_from_total_return_delta_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return validate_shortpick_v2_h10_parameter_significance_payload(payload)


def _results_by_config(replay_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("config_id")): row
        for row in replay_artifact.get("results") or []
        if isinstance(row, dict) and row.get("config_id")
    }


def _rule_by_config(replay_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("config_id")): row
        for row in replay_artifact.get("rule_matrix") or []
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
        "market_excess_total_return",
        "max_drawdown",
        "turnover",
        "skipped_ratio",
    )
    return {key: summary.get(key) for key in keys if key in summary}


def _delta(left_summary: dict[str, Any], right_summary: dict[str, Any], key: str) -> float | None:
    left_value = _optional_float(left_summary.get(key))
    right_value = _optional_float(right_summary.get(key))
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 9)


def _fixed85_config_id(source_id: str) -> str:
    return f"{source_id}__fixed_notional_85k_top5_h10_v1"


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
    return f"shortpick_v2_h10_parameter_significance:{start}:{end}:{generated_day}"


def _load_json(path: Path, checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _add_check(checks, "parameter_significance_json_readable", False, f"{path} is not readable JSON", {"error": str(exc)})
        return None
    if not isinstance(payload, dict):
        _add_check(
            checks,
            "parameter_significance_json_object",
            False,
            f"{path} must contain a JSON object",
            {"type": type(payload).__name__},
        )
        return None
    _add_check(checks, "parameter_significance_json_readable", True, f"{path} is readable JSON")
    return payload


def _artifact_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    return {
        "artifact_family": payload.get("artifact_family"),
        "artifact_id": payload.get("artifact_id"),
        "status": payload.get("status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "horizon_days": (payload.get("analysis_scope") or {}).get("horizon_days")
        if isinstance(payload.get("analysis_scope"), dict)
        else None,
        "parameter_row_count": len(payload.get("parameter_rows") or []),
    }


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "passed": bool(passed),
            "message": message,
            "details": details or {},
        }
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
