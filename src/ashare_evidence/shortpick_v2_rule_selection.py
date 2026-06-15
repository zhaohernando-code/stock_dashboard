from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY = "shortpick_v2_rule_selection_artifact"
SHORTPICK_V2_RULE_SELECTION_SCHEMA_VERSION = "v1"
SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION = "shortpick_v2_rule_selection_v2"
SHORTPICK_V2_RULE_SELECTION_SOURCE_PLAN_REF = (
    "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-4-candidate-rule-selection"
)
REQUIRED_REPLAY_ARTIFACT_FAMILY = "shortpick_v2_replay_artifact"
REQUIRED_REPLAY_EVIDENCE_BASIS = "historical_account_replay"
REQUIRED_REPLAY_CLAIM_CEILING = "research_observation"
DEFAULT_MAX_SELECTED = 2
BASELINE_CONFIG_IDS = ("top1_or_skip_v1",)
H10_QUIET_CHAMPION_CONFIG_ID = "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1"
H10_QUIET_CAPITAL_SHADOW_CONFIG_ID = "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1"
H10_QUIET_BENCHMARK_CONFIG_IDS = (
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
)
REQUIRED_CONFIG_IDS = (
    "top1_or_skip_v1",
    "top3_fallback_v1",
    "fixed_notional_40k_top5_v1",
    "position_cap_utilization_top5_v1",
    "conservative_cash_reserve_60k_top5_v1",
)
RANKING_ORDER = (
    "max_drawdown_desc",
    "annualized_return_desc",
    "market_excess_total_return_desc",
    "total_return_desc",
    "skip_ratio_asc",
    "turnover_asc",
    "trade_count_desc",
)
SELECTION_THRESHOLD_PROFILE_STANDARD = "standard"
SELECTION_THRESHOLD_PROFILE_SPARSE_HIGH_CONFIDENCE = "sparse_high_confidence"
SELECTION_THRESHOLD_PROFILE_H10_QUIET_CHAMPION = "h10_quiet_champion"
SELECTION_THRESHOLD_PROFILES = (
    SELECTION_THRESHOLD_PROFILE_STANDARD,
    SELECTION_THRESHOLD_PROFILE_SPARSE_HIGH_CONFIDENCE,
    SELECTION_THRESHOLD_PROFILE_H10_QUIET_CHAMPION,
)


@dataclass(frozen=True)
class SelectionThresholds:
    threshold_profile: str = SELECTION_THRESHOLD_PROFILE_STANDARD
    required_config_ids: tuple[str, ...] = REQUIRED_CONFIG_IDS
    benchmark_config_ids: tuple[str, ...] = ()
    signal_count_min: int = 300
    trade_count_min: int = 180
    skip_ratio_max: float = 0.60
    total_return_min_exclusive: float = 0.0
    annualized_return_min: float = 0.30
    market_reference_required: bool = True
    market_excess_total_return_min_exclusive: float = 0.0
    max_drawdown_min: float = -0.35
    mean_invested_ratio_min: float = 0.25
    turnover_max: float = 80.0
    reason_counts_required: bool = True

    def to_artifact(self) -> dict[str, Any]:
        return {
            "threshold_profile": self.threshold_profile,
            "signal_count_min": self.signal_count_min,
            "trade_count_min": self.trade_count_min,
            "skip_ratio_max": self.skip_ratio_max,
            "total_return_min_exclusive": self.total_return_min_exclusive,
            "annualized_return_min": self.annualized_return_min,
            "market_reference_required": self.market_reference_required,
            "market_excess_total_return_min_exclusive": self.market_excess_total_return_min_exclusive,
            "max_drawdown_min": self.max_drawdown_min,
            "mean_invested_ratio_min": self.mean_invested_ratio_min,
            "turnover_max": self.turnover_max,
            "reason_counts_required": self.reason_counts_required,
            "source_replay_leakage_status_required": "passed",
        }


DEFAULT_SELECTION_THRESHOLDS = SelectionThresholds()
SPARSE_HIGH_CONFIDENCE_SELECTION_THRESHOLDS = SelectionThresholds(
    threshold_profile=SELECTION_THRESHOLD_PROFILE_SPARSE_HIGH_CONFIDENCE,
    skip_ratio_max=0.75,
)
H10_QUIET_CHAMPION_SELECTION_THRESHOLDS = SelectionThresholds(
    threshold_profile=SELECTION_THRESHOLD_PROFILE_H10_QUIET_CHAMPION,
    required_config_ids=(*REQUIRED_CONFIG_IDS, *H10_QUIET_BENCHMARK_CONFIG_IDS),
    benchmark_config_ids=H10_QUIET_BENCHMARK_CONFIG_IDS,
    skip_ratio_max=1.0,
    max_drawdown_min=-0.18,
    mean_invested_ratio_min=0.0,
)
SELECTION_THRESHOLDS_BY_PROFILE = {
    SELECTION_THRESHOLD_PROFILE_STANDARD: DEFAULT_SELECTION_THRESHOLDS,
    SELECTION_THRESHOLD_PROFILE_SPARSE_HIGH_CONFIDENCE: SPARSE_HIGH_CONFIDENCE_SELECTION_THRESHOLDS,
    SELECTION_THRESHOLD_PROFILE_H10_QUIET_CHAMPION: H10_QUIET_CHAMPION_SELECTION_THRESHOLDS,
}


def build_shortpick_v2_rule_selection_artifact(
    replay_artifact: dict[str, Any],
    *,
    replay_artifact_path: str | Path | None = None,
    max_selected: int = DEFAULT_MAX_SELECTED,
    thresholds: SelectionThresholds = DEFAULT_SELECTION_THRESHOLDS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Select a bounded set of v2 execution configs from a Phase 3 replay artifact."""
    if max_selected < 1:
        raise ValueError("max_selected must be at least 1")
    _validate_replay_artifact_for_selection(
        replay_artifact,
        required_config_ids=thresholds.required_config_ids,
    )

    generated_at = generated_at or datetime.now(UTC)
    results_by_config = _results_by_config(replay_artifact)
    selection_context = _selection_context(replay_artifact)
    gate_results = [
        _gate_result(
            config_id,
            results_by_config[config_id],
            thresholds=thresholds,
            selection_context=selection_context,
        )
        for config_id in sorted(results_by_config)
    ]
    gate_by_config = {item["config_id"]: item for item in gate_results}
    baseline_configs = [
        _selection_row(
            config_id=config_id,
            role="baseline_control",
            selection_rank=None,
            gate_result=gate_by_config[config_id],
            reason=(
                "Retained as the strict Top1-or-skip control; "
                "not promoted because Phase 4 keeps a bounded candidate set."
            ),
        )
        for config_id in BASELINE_CONFIG_IDS
        if config_id in gate_by_config
    ]
    benchmark_configs = [
        _selection_row(
            config_id=config_id,
            role="benchmark_control",
            selection_rank=None,
            gate_result=gate_by_config[config_id],
            reason=(
                "Retained as a mandatory h10 quiet benchmark; later candidates must be compared against this "
                "same-window replay row before any replacement decision."
            ),
        )
        for config_id in thresholds.benchmark_config_ids
        if config_id in gate_by_config
    ]
    eligible = [
        item
        for item in gate_results
        if item["gate_status"] == "passed" and item["config_id"] not in BASELINE_CONFIG_IDS
    ]
    ranked = sorted(eligible, key=_ranking_key)
    selected_gate_results = ranked[:max_selected]
    selected_config_ids = {item["config_id"] for item in selected_gate_results}
    selected_configs = [
        _selection_row(
            config_id=item["config_id"],
            role="phase5_contract_candidate",
            selection_rank=index,
            gate_result=item,
            reason=_selected_reason(index, item["config_id"]),
        )
        for index, item in enumerate(selected_gate_results, start=1)
    ]
    holdout_configs = [
        _selection_row(
            config_id=item["config_id"],
            role="holdout",
            selection_rank=None,
            gate_result=item,
            reason="Passed deterministic gates but held out because Phase 4 allows at most two candidates.",
        )
        for item in ranked
        if item["config_id"] not in selected_config_ids
    ]
    rejected_configs = [
        _selection_row(
            config_id=item["config_id"],
            role="rejected",
            selection_rank=None,
            gate_result=item,
            reason=item["reason"],
        )
        for item in gate_results
        if item["gate_status"] == "failed" and item["config_id"] not in BASELINE_CONFIG_IDS
    ]
    status = "ready" if selected_configs else "blocked"
    source = _source_replay_artifact(replay_artifact, replay_artifact_path)
    return {
        "artifact_family": SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_RULE_SELECTION_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, str(source["artifact_id"])),
        "generated_at": generated_at.isoformat(),
        "status": status,
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_selection",
        "source_plan_ref": SHORTPICK_V2_RULE_SELECTION_SOURCE_PLAN_REF,
        "source_replay_artifact": source,
        "selection_policy": {
            "policy_version": SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION,
            "max_selected": max_selected,
            "required_config_ids": list(thresholds.required_config_ids),
            "baseline_config_ids": list(BASELINE_CONFIG_IDS),
            "benchmark_config_ids": list(thresholds.benchmark_config_ids),
            "gate_thresholds": thresholds.to_artifact(),
            "ranking_order": list(RANKING_ORDER),
        },
        "gate_results": gate_results,
        "benchmark_configs": benchmark_configs,
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "holdout_configs": holdout_configs,
        "rejected_configs": rejected_configs,
        "leakage_audit": {
            "status": "passed",
            "source_replay_leakage_status": "passed",
            "used_only_replay_artifact": True,
            "notes": [
                "Selection reads only the Phase 3 replay artifact.",
                "Source replay leakage_audit.status is passed and required before any candidate can be selected.",
            ],
        },
        "research_labeling": {
            "claim_ceiling": "research_observation",
            "selected_role_label": "phase5_contract_candidate",
            "notes": [
                "Selected configurations are candidates for Phase 5 contract design only.",
                (
                    "When present, benchmark_config_ids are the mandatory comparison baseline for later "
                    "Short Pick Lab v2 strategy-search rounds; broad search results cannot replace them without "
                    "strict same-window replay evidence."
                ),
                (
                    "This artifact does not start paper tracking, create a ledger, expose an API, "
                    "or claim production readiness."
                ),
            ],
        },
        "event_refs": [
            "shortpick_v2.phase4.rule_selection.generated",
            f"shortpick_v2.rule_selection.source.{source['artifact_id']}",
        ],
    }


def build_shortpick_v2_rule_selection_artifact_from_path(
    replay_artifact_path: str | Path,
    *,
    max_selected: int = DEFAULT_MAX_SELECTED,
    threshold_profile: str = SELECTION_THRESHOLD_PROFILE_STANDARD,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    path = Path(replay_artifact_path)
    replay_artifact = json.loads(path.read_text(encoding="utf-8"))
    if threshold_profile not in SELECTION_THRESHOLD_PROFILES:
        raise ValueError(f"threshold_profile must be one of {sorted(SELECTION_THRESHOLD_PROFILES)}")
    return build_shortpick_v2_rule_selection_artifact(
        replay_artifact,
        replay_artifact_path=path,
        max_selected=max_selected,
        thresholds=SELECTION_THRESHOLDS_BY_PROFILE[threshold_profile],
        generated_at=generated_at,
    )


def write_shortpick_v2_rule_selection_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _validate_replay_artifact_for_selection(
    replay_artifact: dict[str, Any],
    *,
    required_config_ids: tuple[str, ...],
) -> None:
    if replay_artifact.get("artifact_family") != REQUIRED_REPLAY_ARTIFACT_FAMILY:
        raise ValueError("source replay artifact must be shortpick_v2_replay_artifact")
    if replay_artifact.get("schema_version") != "v1":
        raise ValueError("source replay artifact schema_version must be v1")
    if replay_artifact.get("status") != "ready":
        raise ValueError("source replay artifact status must be ready")
    if replay_artifact.get("evidence_basis") != REQUIRED_REPLAY_EVIDENCE_BASIS:
        raise ValueError("source replay artifact must use historical_account_replay evidence")
    if replay_artifact.get("claim_ceiling") != REQUIRED_REPLAY_CLAIM_CEILING:
        raise ValueError("source replay artifact must keep claim_ceiling=research_observation")
    if (replay_artifact.get("leakage_audit") or {}).get("status") != "passed":
        raise ValueError("source replay artifact leakage_audit.status must be passed")
    results_by_config = _results_by_config(replay_artifact)
    missing = sorted(set(required_config_ids) - set(results_by_config))
    if missing:
        raise ValueError(f"source replay artifact is missing required v2 configs: {missing}")


def _results_by_config(replay_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = replay_artifact.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("source replay artifact must contain replay results")
    output: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        config_id = result.get("config_id")
        if isinstance(config_id, str) and config_id:
            output[config_id] = result
    if not output:
        raise ValueError("source replay artifact results do not include config_id rows")
    return output


def _gate_result(
    config_id: str,
    replay_result: dict[str, Any],
    *,
    thresholds: SelectionThresholds,
    selection_context: dict[str, Any],
) -> dict[str, Any]:
    summary = _selection_summary(replay_result, selection_context=selection_context)
    reason_counts = replay_result.get("reason_counts") if isinstance(replay_result.get("reason_counts"), dict) else {}
    has_market_reference = summary["market_reference_total_return"] is not None
    market_reference_passed = has_market_reference or not thresholds.market_reference_required
    market_excess_passed = (
        summary["market_excess_total_return"] is not None
        and summary["market_excess_total_return"] > thresholds.market_excess_total_return_min_exclusive
    )
    if not thresholds.market_reference_required and not has_market_reference:
        market_excess_passed = True
    checks = [
        _check(
            "result_status_ready",
            replay_result.get("status"),
            "ready",
            replay_result.get("status") == "ready",
            "eq",
        ),
        _check(
            "signal_count",
            summary["signal_count"],
            thresholds.signal_count_min,
            summary["signal_count"] >= thresholds.signal_count_min,
            "gte",
        ),
        _check(
            "trade_count",
            summary["trade_count"],
            thresholds.trade_count_min,
            summary["trade_count"] >= thresholds.trade_count_min,
            "gte",
        ),
        _check(
            "skip_ratio",
            summary["skip_ratio"],
            thresholds.skip_ratio_max,
            summary["skip_ratio"] <= thresholds.skip_ratio_max,
            "lte",
        ),
        _check(
            "total_return",
            summary["total_return"],
            thresholds.total_return_min_exclusive,
            summary["total_return"] > thresholds.total_return_min_exclusive,
            "gt",
        ),
        _check(
            "annualized_return",
            summary["annualized_return"],
            thresholds.annualized_return_min,
            summary["annualized_return"] is not None
            and summary["annualized_return"] >= thresholds.annualized_return_min,
            "gte",
        ),
        _check(
            "market_reference_total_return",
            summary["market_reference_total_return"],
            thresholds.market_reference_required,
            market_reference_passed,
            "present",
        ),
        _check(
            "market_excess_total_return",
            summary["market_excess_total_return"],
            thresholds.market_excess_total_return_min_exclusive,
            market_excess_passed,
            "gt",
        ),
        _check(
            "max_drawdown",
            summary["max_drawdown"],
            thresholds.max_drawdown_min,
            summary["max_drawdown"] >= thresholds.max_drawdown_min,
            "gte",
        ),
        _check(
            "mean_invested_ratio",
            summary["mean_invested_ratio"],
            thresholds.mean_invested_ratio_min,
            summary["mean_invested_ratio"] >= thresholds.mean_invested_ratio_min,
            "gte",
        ),
        _check(
            "turnover",
            summary["turnover"],
            thresholds.turnover_max,
            summary["turnover"] <= thresholds.turnover_max,
            "lte",
        ),
        _check("reason_counts", bool(reason_counts), True, bool(reason_counts), "present"),
    ]
    failed = [check["check_id"] for check in checks if not check["passed"]]
    if config_id in BASELINE_CONFIG_IDS:
        gate_status = "baseline_control"
        reason = "Retained as baseline/control regardless of promotion gate outcome."
    elif failed:
        gate_status = "failed"
        reason = "Failed deterministic selection gates: " + ", ".join(failed)
    else:
        gate_status = "passed"
        reason = "Passed deterministic selection gates."
    return {
        "config_id": config_id,
        "gate_status": gate_status,
        "checks": checks,
        "summary": summary,
        "reason": reason,
    }


def _selection_context(replay_artifact: dict[str, Any]) -> dict[str, Any]:
    data_scope = replay_artifact.get("data_scope") if isinstance(replay_artifact.get("data_scope"), dict) else {}
    trade_day_count = _int(data_scope.get("trade_day_count")) or _int(data_scope.get("signal_day_count"))
    return {
        "annualization_trade_day_count": trade_day_count,
        "market_reference_total_return": _first_float(
            data_scope,
            (
                "market_reference_total_return",
                "benchmark_total_return",
                "eligible_universe_equal_weight_total_return",
                "universe_equal_weight_total_return",
            ),
        ),
    }


def _selection_summary(replay_result: dict[str, Any], *, selection_context: dict[str, Any]) -> dict[str, Any]:
    summary = replay_result.get("summary") if isinstance(replay_result.get("summary"), dict) else {}
    signal_count = _int(summary.get("signal_count"))
    skip_count = _int(summary.get("skip_count"))
    skip_ratio = _float(summary.get("skipped_ratio"))
    if skip_ratio is None:
        skip_ratio = skip_count / signal_count if signal_count > 0 else 1.0
    total_return = _float(summary.get("total_return")) or 0.0
    annualization_trade_day_count = _int(
        summary.get("annualization_trade_day_count")
        or selection_context.get("annualization_trade_day_count")
    )
    annualized_return = _annualized_return(
        total_return=total_return,
        trade_day_count=annualization_trade_day_count,
    )
    market_reference_total_return = _first_float(
        summary,
        (
            "market_reference_total_return",
            "benchmark_total_return",
            "eligible_universe_equal_weight_total_return",
            "universe_equal_weight_total_return",
        ),
    )
    if market_reference_total_return is None:
        market_reference_total_return = _float(selection_context.get("market_reference_total_return"))
    market_excess_total_return = (
        None
        if market_reference_total_return is None
        else round(total_return - market_reference_total_return, 6)
    )
    return {
        "signal_count": signal_count,
        "trade_count": _int(summary.get("trade_count")),
        "skip_count": skip_count,
        "skip_ratio": round(float(skip_ratio), 6),
        "fallback_trade_count": _int(summary.get("fallback_trade_count")),
        "total_return": total_return,
        "annualization_trade_day_count": annualization_trade_day_count,
        "annualized_return": annualized_return,
        "market_reference_total_return": market_reference_total_return,
        "market_excess_total_return": market_excess_total_return,
        "max_drawdown": _float(summary.get("max_drawdown")) or 0.0,
        "mean_invested_ratio": _float(summary.get("mean_invested_ratio")) or 0.0,
        "turnover": _float(summary.get("turnover")) or 0.0,
    }


def _selection_row(
    *,
    config_id: str,
    role: str,
    selection_rank: int | None,
    gate_result: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "config_id": config_id,
        "role": role,
        "selection_rank": selection_rank,
        "gate_status": gate_result["gate_status"],
        "reason": reason,
        "summary": gate_result["summary"],
    }


def _ranking_key(gate_result: dict[str, Any]) -> tuple[float, float, float, float, float, float, int, str]:
    summary = gate_result["summary"]
    return (
        -float(summary["max_drawdown"]),
        -float(summary["annualized_return"] or float("-inf")),
        -float(summary["market_excess_total_return"] or float("-inf")),
        -float(summary["total_return"]),
        float(summary["skip_ratio"]),
        float(summary["turnover"]),
        -int(summary["trade_count"]),
        str(gate_result["config_id"]),
    )


def _selected_reason(selection_rank: int, config_id: str) -> str:
    if selection_rank == 1:
        return "Selected by risk-first ranking among gate-passing configs; best drawdown profile in the bounded set."
    return (
        "Selected by risk-first ranking among gate-passing configs after higher-ranked candidates; "
        f"config_id={config_id}."
    )


def _source_replay_artifact(replay_artifact: dict[str, Any], replay_artifact_path: str | Path | None) -> dict[str, Any]:
    data_scope = replay_artifact.get("data_scope") if isinstance(replay_artifact.get("data_scope"), dict) else {}
    return {
        "artifact_id": str(replay_artifact["artifact_id"]),
        "artifact_family": str(replay_artifact["artifact_family"]),
        "schema_version": str(replay_artifact.get("schema_version") or ""),
        "path": None if replay_artifact_path is None else str(replay_artifact_path),
        "status": str(replay_artifact.get("status") or "blocked"),
        "claim_ceiling": str(replay_artifact["claim_ceiling"]),
        "evidence_basis": str(replay_artifact["evidence_basis"]),
        "signal_day_count": _int(data_scope.get("signal_day_count")),
        "trade_day_count": _int(data_scope.get("trade_day_count")),
    }


def _check(check_id: str, actual: Any, threshold: Any, passed: bool, direction: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "actual": actual,
        "threshold": threshold,
        "direction": direction,
    }


def _artifact_id(generated_at: datetime, source_artifact_id: str) -> str:
    source_key = source_artifact_id or "unknown_source"
    return f"shortpick_v2_rule_selection_artifact:{source_key}:{generated_at.date().isoformat()}"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(source: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _float(source.get(key))
        if value is not None:
            return value
    return None


def _annualized_return(*, total_return: float, trade_day_count: int) -> float | None:
    if trade_day_count <= 0 or total_return <= -1.0:
        return None
    return round(((1.0 + total_return) ** (252.0 / trade_day_count)) - 1.0, 6)
