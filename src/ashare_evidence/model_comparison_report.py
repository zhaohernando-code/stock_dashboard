from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from math import erf, log, sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.phase2.common import spearman_correlation
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_COMPARISON_REPORT_SCHEMA_VERSION = "model_comparison_report.v1"


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _leaderboard_row(trial: dict[str, Any]) -> dict[str, Any]:
    metrics = trial.get("metrics") or {}
    blockers = list(trial.get("blocking_gate_ids") or [])
    return {
        "trial_id": trial.get("trial_id"),
        "model_spec_id": trial.get("model_spec_id"),
        "rank_ic_mean": metrics.get("rank_ic_mean"),
        "positive_rank_ic_rate": metrics.get("positive_rank_ic_rate"),
        "top_quantile_net_excess_mean": metrics.get("top_quantile_net_excess_mean"),
        "top_bottom_spread_mean": metrics.get("top_bottom_spread_mean"),
        "labeled_prediction_count": metrics.get("labeled_prediction_count"),
        "decision": "kill" if blockers else "observe_blocked",
        "blocking_gate_ids": blockers,
    }


def _sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        _safe_float(row.get("rank_ic_mean"), -999.0),
        _safe_float(row.get("top_quantile_net_excess_mean"), -999.0),
        _safe_float(row.get("top_bottom_spread_mean"), -999.0),
    )


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _prediction_rows(candidate_run: dict[str, Any], trial_id: str) -> list[dict[str, Any]]:
    return [row for row in candidate_run.get("prediction_rows") or [] if str(row.get("trial_id")) == trial_id]


def _split_rank_ic(predictions: list[dict[str, Any]]) -> float | None:
    scored = [row for row in predictions if row.get("target_label") is not None]
    if len(scored) < 2:
        return None
    scores = [_safe_float(row.get("score")) for row in scored]
    labels = [_safe_float(row.get("target_label")) for row in scored]
    return spearman_correlation(scores, labels)


def _top_pick_returns(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    top_picks: list[dict[str, Any]] = []
    for as_of_date, rows in sorted(by_date.items()):
        if not rows:
            continue
        best = max(rows, key=lambda row: _safe_float(row.get("score")))
        top_picks.append(
            {
                "symbol": best.get("symbol"),
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "net_excess_return": _safe_float(best.get("target_label")),
                "score": _safe_float(best.get("score")),
            }
        )
    return top_picks


def _overfit_diagnostics(candidate_run: dict[str, Any], leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in leaderboard
        if row.get("rank_ic_mean") is not None and _safe_float(row.get("labeled_prediction_count")) > 0
    ]
    trial_count = len(leaderboard)
    eligible_trial_count = len(eligible)
    split_ids = sorted({str(row.get("split_id")) for row in candidate_run.get("prediction_rows") or [] if row.get("split_id")})
    split_rank_ics: list[float] = []
    overfit_like_count = 0
    for row in eligible:
        predictions = _prediction_rows(candidate_run, str(row.get("trial_id") or ""))
        by_split: dict[str, list[dict[str, Any]]] = {}
        for prediction in predictions:
            by_split.setdefault(str(prediction.get("split_id") or ""), []).append(prediction)
        trial_split_ics = [value for rows in by_split.values() if (value := _split_rank_ic(rows)) is not None]
        split_rank_ics.extend(trial_split_ics)
        if trial_split_ics and _safe_float(row.get("rank_ic_mean")) > 0 and mean(trial_split_ics) <= 0:
            overfit_like_count += 1
    pbo_proxy = overfit_like_count / eligible_trial_count if eligible_trial_count else None
    period_count = len(split_rank_ics)
    alpha_t_stat = None
    deflated_sharpe_confidence = None
    if period_count >= 2:
        avg = mean(split_rank_ics)
        std = pstdev(split_rank_ics)
        if std > 0:
            alpha_t_stat = avg / (std / sqrt(period_count))
            multiple_testing_penalty = sqrt(2 * log(max(eligible_trial_count, 2)))
            deflated_sharpe_confidence = _normal_cdf(alpha_t_stat - multiple_testing_penalty)
    blockers: list[str] = []
    if eligible_trial_count < 4:
        blockers.append("insufficient_eligible_trials_for_pbo")
    if period_count < 20:
        blockers.append("insufficient_periods_for_dsr")
    if pbo_proxy is None:
        blockers.append("missing_pbo_proxy")
    elif pbo_proxy > 0.10:
        blockers.append("pbo_proxy_above_10pct")
    if deflated_sharpe_confidence is None:
        blockers.append("missing_deflated_sharpe_confidence")
    elif deflated_sharpe_confidence < 0.95:
        blockers.append("deflated_sharpe_confidence_below_95pct")
    if alpha_t_stat is None:
        blockers.append("missing_alpha_t_stat")
    elif alpha_t_stat < 3.0:
        blockers.append("alpha_t_stat_below_multiple_testing_threshold")
    return {
        "status": "blocked" if blockers else "ready",
        "diagnostic_scope": "candidate_run_trial_split_proxy",
        "trial_count": trial_count,
        "eligible_trial_count": eligible_trial_count,
        "split_count": len(split_ids),
        "period_count": period_count,
        "pbo_proxy": pbo_proxy,
        "deflated_sharpe_confidence": deflated_sharpe_confidence,
        "alpha_t_stat": alpha_t_stat,
        "blocking_gate_ids": blockers,
        "thresholds": {
            "minimum_eligible_trials_for_pbo": 4,
            "minimum_periods_for_dsr": 20,
            "pbo_proxy_max": 0.10,
            "deflated_sharpe_confidence_min": 0.95,
            "alpha_t_stat_min": 3.0,
        },
    }


def _remove_and_recompute(top_picks: list[dict[str, Any]], *, field: str, value: str | None) -> dict[str, Any]:
    remaining = [row for row in top_picks if str(row.get(field) or "") != str(value or "")]
    returns = [_safe_float(row.get("net_excess_return")) for row in remaining]
    return {
        "removed_field": field,
        "removed_value": value,
        "remaining_count": len(remaining),
        "mean_net_excess_after_removal": mean(returns) if returns else None,
    }


def _winner_dependency(candidate_run: dict[str, Any], leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    best = leaderboard[0] if leaderboard else None
    if not best:
        return {
            "status": "blocked",
            "blocking_gate_ids": ["missing_best_trial"],
            "best_trial_id": None,
        }
    best_trial_id = str(best.get("trial_id") or "")
    top_picks = _top_pick_returns(_prediction_rows(candidate_run, best_trial_id))
    returns = [_safe_float(row.get("net_excess_return")) for row in top_picks]
    baseline_mean = mean(returns) if returns else None
    blockers: list[str] = []
    if len(top_picks) < 20:
        blockers.append("insufficient_top_pick_observations_for_winner_dependency")
    if baseline_mean is None:
        blockers.append("missing_top_pick_returns")
    by_symbol: dict[str, float] = {}
    by_date: dict[str, float] = {}
    by_month: dict[str, float] = {}
    for row in top_picks:
        contribution = _safe_float(row.get("net_excess_return"))
        symbol = str(row.get("symbol") or "")
        as_of_date = str(row.get("as_of_date") or "")
        month = str(row.get("month") or "")
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + contribution
        by_date[as_of_date] = by_date.get(as_of_date, 0.0) + contribution
        by_month[month] = by_month.get(month, 0.0) + contribution
    top_symbol = max(by_symbol, key=by_symbol.get) if by_symbol else None
    top_date = max(by_date, key=by_date.get) if by_date else None
    top_month = max(by_month, key=by_month.get) if by_month else None
    removal_checks = [
        _remove_and_recompute(top_picks, field="symbol", value=top_symbol),
        _remove_and_recompute(top_picks, field="as_of_date", value=top_date),
        _remove_and_recompute(top_picks, field="month", value=top_month),
    ]
    for check in removal_checks:
        recomputed = check.get("mean_net_excess_after_removal")
        if recomputed is None:
            blockers.append(f"missing_recomputed_return_after_removing_{check['removed_field']}")
        elif baseline_mean is not None and baseline_mean > 0 and recomputed <= 0:
            blockers.append(f"winner_dependency_collapses_after_removing_{check['removed_field']}")
    return {
        "status": "blocked" if blockers else "ready",
        "best_trial_id": best_trial_id,
        "top_pick_count": len(top_picks),
        "baseline_mean_net_excess": baseline_mean,
        "top_contributors": {
            "symbol": top_symbol,
            "as_of_date": top_date,
            "month": top_month,
        },
        "removal_checks": removal_checks,
        "blocking_gate_ids": blockers,
    }


def build_model_comparison_report_artifact(
    *,
    validation_run_id: str,
    candidate_run: dict[str, Any],
    model_spec_registry: dict[str, Any],
) -> dict[str, Any]:
    leaderboard = [_leaderboard_row(trial) for trial in candidate_run.get("trial_summaries") or []]
    leaderboard.sort(key=_sort_key, reverse=True)
    spec_ids = [str(spec.get("model_spec_id")) for spec in model_spec_registry.get("model_specs") or []]
    baseline_rows = [
        row for row in leaderboard if row.get("model_spec_id") == "baseline_momentum_10d_turnover_cooldown_v1"
    ]
    best_baseline = baseline_rows[0] if baseline_rows else None
    kill_list = [
        {
            "trial_id": row.get("trial_id"),
            "model_spec_id": row.get("model_spec_id"),
            "reasons": row.get("blocking_gate_ids") or ["blocked_until_governance_review"],
        }
        for row in leaderboard
        if row.get("blocking_gate_ids")
    ]
    overfit_diagnostics = _overfit_diagnostics(candidate_run, leaderboard)
    winner_dependency = _winner_dependency(candidate_run, leaderboard)
    gate_blockers = [
        *[f"overfit:{blocker}" for blocker in overfit_diagnostics.get("blocking_gate_ids") or []],
        *[f"winner_dependency:{blocker}" for blocker in winner_dependency.get("blocking_gate_ids") or []],
        "governance_promotion_pending",
    ]
    report_body = {
        "summary": {
            "candidate_run_id": candidate_run.get("artifact_id"),
            "model_spec_registry_id": model_spec_registry.get("artifact_id"),
            "registered_model_spec_ids": spec_ids,
            "trial_count": candidate_run.get("trial_count"),
            "prediction_row_count": candidate_run.get("prediction_row_count"),
            "claim_ceiling": "comparison_report_only",
            "promotion_status": "blocked_from_production",
        },
        "candidate_leaderboard": leaderboard,
        "baseline_comparison": {
            "baseline_model_spec_id": "baseline_momentum_10d_turnover_cooldown_v1",
            "best_baseline": best_baseline,
            "best_overall": leaderboard[0] if leaderboard else None,
            "same_window_policy": "all rows come from the same candidate_run splits",
        },
        "overfit_diagnostics": overfit_diagnostics,
        "winner_dependency": winner_dependency,
        "execution_diagnostics": {
            "status": "partial",
            "source": "executable_label_matrix label block reasons are included through candidate run labels",
        },
        "kill_list": kill_list,
        "next_research_questions": [
            "Replace proxy PBO/DSR with full combinatorially symmetric cross-validation diagnostics when sample width is sufficient.",
            "Broaden winner-dependency checks to top 3 symbols, top 3 dates and industry concentration.",
            "Harden candidate runner training logic beyond deterministic foundation scoring.",
        ],
    }
    content_digest = _stable_digest(report_body)
    artifact_id = f"model-comparison-report-{content_digest[:16]}"
    return {
        "artifact_type": "model_comparison_report",
        "schema_version": MODEL_COMPARISON_REPORT_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": candidate_run.get("source_db_snapshot_id"),
        "source_data_time_range": candidate_run.get("source_data_time_range"),
        "feature_version": candidate_run.get("feature_version"),
        "label_version": candidate_run.get("label_version"),
        "code_version": "unresolved_local_checkout",
        "config_version": "shortpick_model_comparison_report:v1",
        "validation_protocol": {
            "comparison_policy": "registered_candidate_run_trials_only",
            "raw_prediction_policy": "summarize_and_gate_do_not_promote",
            "production_effect": "forbidden",
        },
        "gate_readout": {
            "gate_status": "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "comparison_report_only",
            "blocking_gate_ids": gate_blockers,
        },
        "claim_ceiling": "comparison_report_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "report_content_digest": content_digest,
        **report_body,
    }


def write_model_comparison_report_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> Path:
    return write_research_validation_artifact(
        "model_comparison_report",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
