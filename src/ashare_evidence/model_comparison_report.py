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
RESULT_ANCHOR_THRESHOLDS = {
    "strict_next_close_governance_leader": {
        "label": "低换手趋势加同标的冷却 next_close 治理口径",
        "total_return": 0.7587,
        "annualized_return": 0.211998,
        "max_drawdown": -0.440409,
    },
    "drawdown_reversal_next_close": {
        "label": "低换手趋势加回撤反转过滤 next_close 治理口径",
        "total_return": 0.595009,
        "annualized_return": 0.172328,
        "max_drawdown": -0.326671,
    },
    "legacy_long_sample_research_target": {
        "label": "老 long-sample T+1 收盘研究口径",
        "total_return": 1.7596,
        "annualized_return": 0.416942,
        "max_drawdown": -0.31704,
        "comparability": "research_target_not_same_artifact_contract",
    },
    "same_close_proxy_diagnostic_ceiling": {
        "label": "same_close_proxy 诊断口径账面最高",
        "total_return": 1.9460,
        "annualized_return": 0.442612,
        "max_drawdown": -0.711528,
        "comparability": "diagnostic_proxy_not_executable_proof",
    },
}
SIGNIFICANT_EDGE_OVER_NEXT_CLOSE_TOTAL_RETURN = 0.95
MIN_RESULT_ANCHOR_PERIOD_COUNT = 500


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


def _registry_selection_policies(model_spec_registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policies: dict[str, dict[str, Any]] = {}
    for spec in model_spec_registry.get("model_specs") or []:
        if not isinstance(spec, dict):
            continue
        model_spec_id = str(spec.get("model_spec_id") or "")
        selection_policy = spec.get("selection_policy")
        if model_spec_id and isinstance(selection_policy, dict):
            policies[model_spec_id] = selection_policy
    return policies


def _leaderboard_row(
    trial: dict[str, Any],
    *,
    registry_selection_policies: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metrics = trial.get("metrics") or {}
    blockers = list(trial.get("blocking_gate_ids") or [])
    model_spec_id = str(trial.get("model_spec_id") or "")
    candidate_run_selection_policy = trial.get("selection_policy") or {}
    comparison_selection_policy = (
        registry_selection_policies.get(model_spec_id, candidate_run_selection_policy)
        if registry_selection_policies
        else candidate_run_selection_policy
    )
    return {
        "trial_id": trial.get("trial_id"),
        "model_spec_id": trial.get("model_spec_id"),
        "selection_policy": comparison_selection_policy,
        "candidate_run_selection_policy": candidate_run_selection_policy,
        "rank_ic_mean": metrics.get("rank_ic_mean"),
        "positive_rank_ic_rate": metrics.get("positive_rank_ic_rate"),
        "top_5_net_excess_mean": metrics.get("top_5_net_excess_mean"),
        "positive_top_5_rate": metrics.get("positive_top_5_rate"),
        "top_10_net_excess_mean": metrics.get("top_10_net_excess_mean"),
        "selected_top_k": metrics.get("selected_top_k"),
        "selected_top_k_net_excess_mean": metrics.get("selected_top_k_net_excess_mean"),
        "positive_selected_top_k_rate": metrics.get("positive_selected_top_k_rate"),
        "top_quantile_net_excess_mean": metrics.get("top_quantile_net_excess_mean"),
        "top_bottom_spread_mean": metrics.get("top_bottom_spread_mean"),
        "labeled_prediction_count": metrics.get("labeled_prediction_count"),
        "decision": "kill" if blockers else "observe_blocked",
        "blocking_gate_ids": blockers,
    }


def _selection_return_metric(row: dict[str, Any]) -> str:
    selection_policy = row.get("selection_policy") or {}
    return str(selection_policy.get("evaluation_return_metric") or "top_quantile_net_excess_mean")


def _is_concentrated_top_k(row: dict[str, Any]) -> bool:
    selection_policy = row.get("selection_policy") or {}
    return selection_policy.get("mode") == "concentrated_top_k" and _selection_return_metric(row) in {
        "top_5_net_excess_mean",
        "selected_top_k_net_excess_mean",
    }


def _sort_key(row: dict[str, Any]) -> tuple[float, ...]:
    return_metric = _selection_return_metric(row)
    selection_policy = row.get("selection_policy") or {}
    trial_selection_policy = selection_policy.get("trial_selection_policy")
    if isinstance(trial_selection_policy, dict) and trial_selection_policy.get("mode") == "stability_adjusted":
        stability = row.get("trial_stability") if isinstance(row.get("trial_stability"), dict) else {}
        period_count = int(_safe_float(stability.get("period_count")))
        total_return_floor_periods = int(
            _safe_float(trial_selection_policy.get("minimum_period_count_for_total_return_floor"), 999999.0)
        )
        return_value = _safe_float(row.get(return_metric), -999.0)
        if period_count >= total_return_floor_periods:
            minimum_total_return = _safe_float(trial_selection_policy.get("minimum_portfolio_total_return"), 0.0)
            minimum_max_drawdown = _safe_float(trial_selection_policy.get("minimum_portfolio_max_drawdown"), -1.0)
            portfolio_total_return = _safe_float(stability.get("portfolio_total_return"), -999.0)
            portfolio_max_drawdown = _safe_float(stability.get("portfolio_max_drawdown"), -999.0)
            eligible = (
                portfolio_total_return >= minimum_total_return
                and portfolio_max_drawdown >= minimum_max_drawdown
            )
            if not eligible:
                return (
                    0.0,
                    portfolio_total_return,
                    portfolio_max_drawdown,
                    -_safe_float(stability.get("negative_month_count"), 999.0),
                    _safe_float(stability.get("min_monthly_mean_net_excess"), -999.0),
                )
        else:
            minimum_return = _safe_float(
                trial_selection_policy.get("minimum_selected_top_k_net_excess_mean"),
                _safe_float(trial_selection_policy.get("minimum_mean_net_excess"), 0.0),
            )
            eligible = return_value >= minimum_return
        tie_break_values = {
            "negative_month_count_asc": -_safe_float(stability.get("negative_month_count"), 999.0),
            "portfolio_max_drawdown_desc": _safe_float(stability.get("portfolio_max_drawdown"), -999.0),
            "portfolio_path_drawdown_sum_desc": _safe_float(stability.get("portfolio_path_drawdown_sum"), -999.0),
            "min_monthly_mean_net_excess_desc": _safe_float(
                stability.get("min_monthly_mean_net_excess"), -999.0
            ),
            "portfolio_total_return_desc": _safe_float(stability.get("portfolio_total_return"), return_value),
            "selected_top_k_net_excess_mean_desc": return_value,
            "top_5_net_excess_mean_desc": _safe_float(row.get("top_5_net_excess_mean"), -999.0),
            "positive_selected_top_k_rate_desc": _safe_float(row.get("positive_selected_top_k_rate"), -999.0),
        }
        default_tie_break_order = [
            "negative_month_count_asc",
            "portfolio_max_drawdown_desc",
            "min_monthly_mean_net_excess_desc",
            "portfolio_total_return_desc",
            "selected_top_k_net_excess_mean_desc",
        ]
        declared_order = trial_selection_policy.get("tie_break_order")
        tie_break_order = declared_order if isinstance(declared_order, list) else default_tie_break_order
        ordered_values = [
            tie_break_values[key]
            for key in tie_break_order
            if key != "portfolio_total_return_floor_first_after_500_periods" and key in tie_break_values
        ]
        if not ordered_values:
            ordered_values = [tie_break_values[key] for key in default_tie_break_order]
        return (1.0 if eligible else 0.0, *ordered_values)
    if _is_concentrated_top_k(row):
        return (
            _safe_float(row.get(return_metric), -999.0),
            _safe_float(row.get("positive_selected_top_k_rate"), _safe_float(row.get("positive_top_5_rate"), -999.0)),
            _safe_float(row.get("top_10_net_excess_mean"), -999.0),
            _safe_float(row.get("rank_ic_mean"), -999.0),
        )
    return (
        _safe_float(row.get("rank_ic_mean"), -999.0),
        _safe_float(row.get(return_metric), -999.0),
        _safe_float(row.get("top_bottom_spread_mean"), -999.0),
        _safe_float(row.get("top_5_net_excess_mean"), -999.0),
    )


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _prediction_rows(candidate_run: dict[str, Any], trial_id: str) -> list[dict[str, Any]]:
    return [row for row in candidate_run.get("prediction_rows") or [] if str(row.get("trial_id")) == trial_id]


def _trial_diagnostic(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any] | None:
    for row in candidate_run.get("trial_diagnostics") or []:
        if str(row.get("trial_id") or "") == trial_id:
            return row
    return None


def _trial_stability_summary(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    diagnostic = _trial_diagnostic(candidate_run, trial_id)
    if not diagnostic:
        return {}
    returns_by_date = diagnostic.get("selected_top_k_returns_by_date")
    if not isinstance(returns_by_date, list):
        return {}
    by_month: dict[str, list[float]] = {}
    values: list[float] = []
    for row in returns_by_date:
        if not isinstance(row, dict):
            continue
        value = _safe_float(row.get("mean_net_excess_return"))
        values.append(value)
        month = str(row.get("month") or str(row.get("as_of_date") or "")[:7])
        if month:
            by_month.setdefault(month, []).append(value)
    monthly_means = {month: mean(month_values) for month, month_values in by_month.items() if month_values}
    negative_months = [month for month, value in sorted(monthly_means.items()) if value < 0]
    horizon_days = int(_safe_float(diagnostic.get("target_horizon_days"), 20.0))
    portfolio_curve = _rolling_sleeve_curve(returns_by_date, horizon_days=horizon_days)
    path_drawdown = _series_drawdown(values)
    return {
        "period_count": len(values),
        "negative_month_count": len(negative_months),
        "negative_months": negative_months,
        "min_monthly_mean_net_excess": min(monthly_means.values()) if monthly_means else None,
        "positive_date_rate": sum(1 for value in values if value > 0) / len(values) if values else None,
        "portfolio_path_drawdown_sum": path_drawdown["max_drawdown_sum"],
        "portfolio_total_return": portfolio_curve["total_return"],
        "portfolio_annualized_return": portfolio_curve["annualized_return"],
        "portfolio_max_drawdown": portfolio_curve["max_drawdown"],
    }


def _attach_trial_stability(leaderboard: list[dict[str, Any]], candidate_run: dict[str, Any]) -> None:
    for row in leaderboard:
        trial_id = str(row.get("trial_id") or "")
        if trial_id:
            row["trial_stability"] = _trial_stability_summary(candidate_run, trial_id)


def _split_rank_ic(predictions: list[dict[str, Any]]) -> float | None:
    scored = [row for row in predictions if row.get("target_label") is not None]
    if len(scored) < 2:
        return None
    scores = [_safe_float(row.get("score")) for row in scored]
    labels = [_safe_float(row.get("target_label")) for row in scored]
    return spearman_correlation(scores, labels)


def _period_rank_ics(predictions: list[dict[str, Any]], *, period_field: str) -> list[float]:
    by_period: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        period = str(row.get(period_field) or "")
        if not period:
            continue
        by_period.setdefault(period, []).append(row)
    return [value for rows in by_period.values() if (value := _split_rank_ic(rows)) is not None]


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
                "weighted_net_excess_return": _safe_float(best.get("target_label"))
                * _safe_float(best.get("portfolio_weight"), 1.0),
                "portfolio_weight": _safe_float(best.get("portfolio_weight"), 1.0),
                "score": _safe_float(best.get("score")),
            }
        )
    return top_picks


def _weighted_return(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return mean(_safe_float(row.get("target_label")) * _safe_float(row.get("portfolio_weight"), 1.0) for row in rows)


def _top5_returns_from_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    returns: list[dict[str, Any]] = []
    for as_of_date, rows in sorted(by_date.items()):
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        if not active_rows:
            returns.append(
                {
                    "as_of_date": as_of_date,
                    "month": as_of_date[:7],
                    "pick_count": 0,
                    "mean_net_excess_return": 0.0,
                    "mean_total_return_after_cost": 0.0,
                    "selection_state": "cash",
                }
            )
            continue
        ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        top_rows = ordered[: min(5, len(ordered))]
        if not top_rows:
            continue
        returns.append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "pick_count": len(top_rows),
                "mean_net_excess_return": _weighted_return(top_rows),
                "mean_total_return_after_cost": mean(
                    _safe_float(row.get("target_total_return"), _safe_float(row.get("target_label")))
                    * _safe_float(row.get("portfolio_weight"), 1.0)
                    for row in top_rows
                ),
                "gross_exposure": mean(_safe_float(row.get("portfolio_weight"), 1.0) for row in top_rows),
                "selection_state": "invested",
            }
        )
    return returns


def _top5_picks_from_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        if row.get("target_label") is None:
            continue
        by_date.setdefault(str(row.get("as_of_date") or ""), []).append(row)
    picks: list[dict[str, Any]] = []
    for as_of_date, rows in sorted(by_date.items()):
        active_rows = [row for row in rows if row.get("selection_allowed", True)]
        if not active_rows:
            continue
        ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
        for rank, picked in enumerate(ordered[: min(5, len(ordered))], start=1):
            picks.append(
                {
                    "symbol": picked.get("symbol"),
                    "as_of_date": as_of_date,
                    "month": as_of_date[:7],
                    "rank": rank,
                    "net_excess_return": _safe_float(picked.get("target_label")),
                    "weighted_net_excess_return": _safe_float(picked.get("target_label"))
                    * _safe_float(picked.get("portfolio_weight"), 1.0),
                    "portfolio_weight": _safe_float(picked.get("portfolio_weight"), 1.0),
                    "score": _safe_float(picked.get("score")),
                }
            )
    return picks


def _overfit_diagnostics(candidate_run: dict[str, Any], leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in leaderboard
        if row.get("rank_ic_mean") is not None and _safe_float(row.get("labeled_prediction_count")) > 0
    ]
    trial_count = len(leaderboard)
    eligible_trial_count = len(eligible)
    split_ids = sorted(
        {
            str(split.get("split_id"))
            for split in candidate_run.get("splits") or []
            if split.get("status") == "ready" and split.get("split_id")
        }
    )
    overfit_like_count = 0
    for row in eligible:
        trial_id = str(row.get("trial_id") or "")
        diagnostic = _trial_diagnostic(candidate_run, trial_id)
        if diagnostic is not None:
            trial_split_ics = [
                _safe_float(item.get("rank_ic"))
                for item in diagnostic.get("split_rank_ics") or []
                if item.get("rank_ic") is not None
            ]
        else:
            predictions = _prediction_rows(candidate_run, trial_id)
            by_split: dict[str, list[dict[str, Any]]] = {}
            for prediction in predictions:
                by_split.setdefault(str(prediction.get("split_id") or ""), []).append(prediction)
            trial_split_ics = [value for rows in by_split.values() if (value := _split_rank_ic(rows)) is not None]
        if trial_split_ics and _safe_float(row.get("rank_ic_mean")) > 0 and mean(trial_split_ics) <= 0:
            overfit_like_count += 1
    pbo_proxy = overfit_like_count / eligible_trial_count if eligible_trial_count else None
    best_trial_id = str((leaderboard[0] if leaderboard else {}).get("trial_id") or "")
    best_row = leaderboard[0] if leaderboard else {}
    best_diagnostic = _trial_diagnostic(candidate_run, best_trial_id) if best_trial_id else None
    period_source = "best_trial_as_of_date_rank_ic"
    if _is_concentrated_top_k(best_row):
        if best_diagnostic is not None:
            period_values = [
                _safe_float(item.get("mean_net_excess_return"))
                for item in best_diagnostic.get("selected_top_k_returns_by_date")
                or best_diagnostic.get("top_5_returns_by_date")
                or []
                if item.get("mean_net_excess_return") is not None
            ]
        else:
            best_trial_predictions = _prediction_rows(candidate_run, best_trial_id) if best_trial_id else []
            period_values = [
                _safe_float(item.get("mean_net_excess_return"))
                for item in _top5_returns_from_predictions(best_trial_predictions)
                if item.get("mean_net_excess_return") is not None
            ]
        period_source = "best_trial_top_5_mean_net_excess_by_date"
    elif best_diagnostic is not None:
        period_values = [
            _safe_float(item.get("rank_ic"))
            for item in best_diagnostic.get("date_rank_ics") or []
            if item.get("rank_ic") is not None
        ]
    else:
        best_trial_predictions = _prediction_rows(candidate_run, best_trial_id) if best_trial_id else []
        period_values = _period_rank_ics(best_trial_predictions, period_field="as_of_date")
    period_count = len(period_values)
    alpha_t_stat = None
    deflated_sharpe_confidence = None
    if period_count >= 2:
        avg = mean(period_values)
        std = pstdev(period_values)
        if std > 0:
            alpha_t_stat = avg / (std / sqrt(period_count))
            multiple_testing_penalty = sqrt(2 * log(max(eligible_trial_count, 2)))
            deflated_sharpe_confidence = _normal_cdf(alpha_t_stat - multiple_testing_penalty)
    blockers: list[str] = []
    if eligible_trial_count < 4:
        blockers.append("insufficient_eligible_trials_for_pbo")
    if len(split_ids) < 4:
        blockers.append("insufficient_independent_walk_forward_splits_for_overfit")
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
        "period_source": period_source,
        "pbo_proxy": pbo_proxy,
        "deflated_sharpe_confidence": deflated_sharpe_confidence,
        "alpha_t_stat": alpha_t_stat,
        "blocking_gate_ids": blockers,
        "thresholds": {
            "minimum_eligible_trials_for_pbo": 4,
            "minimum_independent_walk_forward_splits_for_overfit": 4,
            "minimum_periods_for_dsr": 20,
            "pbo_proxy_max": 0.10,
            "deflated_sharpe_confidence_min": 0.95,
            "alpha_t_stat_min": 3.0,
        },
    }


def _remove_and_recompute(top_picks: list[dict[str, Any]], *, field: str, value: str | None) -> dict[str, Any]:
    remaining = [row for row in top_picks if str(row.get(field) or "") != str(value or "")]
    returns = [
        _safe_float(row.get("weighted_net_excess_return"), _safe_float(row.get("net_excess_return")))
        for row in remaining
    ]
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
    diagnostic = _trial_diagnostic(candidate_run, best_trial_id)
    if _is_concentrated_top_k(best):
        top_picks = (
            list((diagnostic.get("selected_top_k_picks_by_date") or diagnostic.get("top_5_picks_by_date") or []))
            if diagnostic is not None
            else _top5_picks_from_predictions(_prediction_rows(candidate_run, best_trial_id))
        )
        pick_scope = f"top_{int(_safe_float(best.get('selected_top_k'), 5.0))}_picks_by_date"
    else:
        top_picks = (
            list(diagnostic.get("top_picks_by_date") or [])
            if diagnostic is not None
            else _top_pick_returns(_prediction_rows(candidate_run, best_trial_id))
        )
        pick_scope = "top_1_pick_by_date"
    returns = [
        _safe_float(row.get("weighted_net_excess_return"), _safe_float(row.get("net_excess_return")))
        for row in top_picks
    ]
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
        contribution = _safe_float(
            row.get("weighted_net_excess_return"),
            _safe_float(row.get("net_excess_return")),
        )
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
        "pick_scope": pick_scope,
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


def _series_drawdown(values: list[float]) -> dict[str, Any]:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
    return {
        "cumulative_return_sum": cumulative,
        "max_drawdown_sum": max_drawdown,
    }


def _compounded_curve(values: list[float]) -> dict[str, Any]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0 if peak > 0 else 0.0
        max_drawdown = min(max_drawdown, drawdown)
    return {
        "total_return": equity - 1.0,
        "max_drawdown": max_drawdown,
    }


def _rolling_sleeve_curve(returns_by_date: list[dict[str, Any]], *, horizon_days: int) -> dict[str, Any]:
    values = [
        _safe_float(row.get("mean_total_return_after_cost"), _safe_float(row.get("mean_net_excess_return")))
        for row in returns_by_date
    ]
    row_horizons = [
        max(_safe_float(row.get("mean_target_horizon_days"), float(horizon_days)), 1.0)
        for row in returns_by_date
    ]
    normalized = [value / row_horizons[index] for index, value in enumerate(values)]
    curve = _compounded_curve(normalized)
    period_count = len(values)
    annualized = None
    if period_count > 0 and curve["total_return"] > -1:
        annualized = (1.0 + curve["total_return"]) ** (252.0 / period_count) - 1.0
    return {
        "method": "horizon_normalized_compounded_proxy",
        "period_count": period_count,
        "target_horizon_days": horizon_days,
        "mean_target_horizon_days": mean(row_horizons) if row_horizons else None,
        "total_return": curve["total_return"],
        "annualized_return": annualized,
        "max_drawdown": curve["max_drawdown"],
        "note": (
            "Proxy from model label returns, not a full order-level portfolio simulator. "
            "Use to gate research candidates before expensive same-contract portfolio replay."
        ),
    }


def _result_anchor_comparison(portfolio_curve: dict[str, Any]) -> dict[str, Any]:
    total_return = _safe_float(portfolio_curve.get("total_return"))
    max_drawdown = _safe_float(portfolio_curve.get("max_drawdown"))
    period_count = int(_safe_float(portfolio_curve.get("period_count")))
    blockers: list[str] = []
    if period_count < MIN_RESULT_ANCHOR_PERIOD_COUNT:
        blockers.append("insufficient_periods_for_three_year_result_anchor")
    else:
        if total_return < RESULT_ANCHOR_THRESHOLDS["strict_next_close_governance_leader"]["total_return"]:
            blockers.append("total_return_below_best_strict_next_close_governance_anchor")
        if total_return < SIGNIFICANT_EDGE_OVER_NEXT_CLOSE_TOTAL_RETURN:
            blockers.append("total_return_lacks_significant_edge_over_next_close_anchor")
        if max_drawdown < RESULT_ANCHOR_THRESHOLDS["drawdown_reversal_next_close"]["max_drawdown"]:
            blockers.append("max_drawdown_worse_than_drawdown_reversal_anchor")
    return {
        "status": "blocked" if blockers else "anchor_floor_passed",
        "period_count": period_count,
        "measured_total_return": total_return,
        "measured_max_drawdown": max_drawdown,
        "blocking_gate_ids": blockers,
        "thresholds": {
            "minimum_strict_next_close_total_return": RESULT_ANCHOR_THRESHOLDS[
                "strict_next_close_governance_leader"
            ]["total_return"],
            "significant_edge_total_return_min": SIGNIFICANT_EDGE_OVER_NEXT_CLOSE_TOTAL_RETURN,
            "max_drawdown_floor": RESULT_ANCHOR_THRESHOLDS["drawdown_reversal_next_close"]["max_drawdown"],
            "legacy_research_target_total_return": RESULT_ANCHOR_THRESHOLDS[
                "legacy_long_sample_research_target"
            ]["total_return"],
            "minimum_period_count_for_three_year_anchor": MIN_RESULT_ANCHOR_PERIOD_COUNT,
        },
        "anchors": RESULT_ANCHOR_THRESHOLDS,
    }


def _monthly_return_summary(returns_by_date: list[dict[str, Any]], *, extra_cost: float = 0.0) -> list[dict[str, Any]]:
    by_month: dict[str, list[float]] = {}
    for row in returns_by_date:
        month = str(row.get("month") or str(row.get("as_of_date") or "")[:7])
        if not month:
            continue
        by_month.setdefault(month, []).append(_safe_float(row.get("mean_net_excess_return")) - extra_cost)
    return [
        {
            "month": month,
            "date_count": len(values),
            "mean_net_excess_return": mean(values),
            "positive_date_rate": sum(1 for value in values if value > 0) / len(values),
            "min_date_return": min(values),
            "max_date_return": max(values),
        }
        for month, values in sorted(by_month.items())
        if values
    ]


def _capacity_fill_rate_diagnostics(
    selected_picks: list[dict[str, Any]],
    *,
    selected_top_k: int,
    selection_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    portfolio_notional_cny = 1_000_000.0
    max_adv_participation_rate = 0.05
    minimum_active_pick_count = 20
    capacity_tier_notionals = [50_000.0, 100_000.0, 120_000.0, 150_000.0, 250_000.0, 500_000.0, 1_000_000.0]
    active_rows: list[dict[str, Any]] = []
    missing_avg_amount_count = 0
    below_full_fill: list[dict[str, Any]] = []
    for row in selected_picks:
        if not isinstance(row, dict):
            continue
        capital_weight = (
            _safe_float(row.get("portfolio_weight"), 1.0)
            * _safe_float(row.get("rank_weight_multiplier"), 1.0)
            / max(float(selected_top_k), 1.0)
        )
        if capital_weight <= 0:
            continue
        avg_amount_20d = _safe_float(row.get("avg_amount_20d"))
        required_notional = portfolio_notional_cny * capital_weight
        fill_rate = (avg_amount_20d * max_adv_participation_rate / required_notional) if required_notional > 0 else 1.0
        diagnostic_row = {
            "symbol": row.get("symbol"),
            "as_of_date": row.get("as_of_date"),
            "rank": row.get("rank"),
            "avg_amount_20d": avg_amount_20d,
            "capital_weight": capital_weight,
            "required_notional_cny": required_notional,
            "max_notional_at_5pct_adv_cny": avg_amount_20d * max_adv_participation_rate,
            "max_full_fill_portfolio_notional_cny": (
                avg_amount_20d * max_adv_participation_rate / capital_weight if capital_weight > 0 else None
            ),
            "fill_rate": fill_rate,
        }
        active_rows.append(diagnostic_row)
        if avg_amount_20d <= 0:
            missing_avg_amount_count += 1
        elif fill_rate < 1.0:
            below_full_fill.append(diagnostic_row)

    blockers: list[str] = []
    if len(active_rows) < minimum_active_pick_count:
        blockers.append("insufficient_active_picks_for_capacity_stress")
    if missing_avg_amount_count:
        blockers.append("capacity_pick_avg_amount_20d_missing")
    if below_full_fill:
        blockers.append("adv_capacity_fill_rate_below_floor")
    worst_pick = min(active_rows, key=lambda row: _safe_float(row.get("fill_rate"), 1.0), default=None)
    fill_rates = [_safe_float(row.get("fill_rate"), 1.0) for row in active_rows if _safe_float(row.get("avg_amount_20d")) > 0]
    full_fill_notionals = sorted(
        _safe_float(row.get("max_full_fill_portfolio_notional_cny"))
        for row in active_rows
        if _safe_float(row.get("avg_amount_20d")) > 0
    )

    def _tier_fill_stats(notional: float) -> dict[str, Any]:
        tier_fill_rates: list[float] = []
        tier_below_full = 0
        for active_row in active_rows:
            avg_amount_20d = _safe_float(active_row.get("avg_amount_20d"))
            capital_weight = _safe_float(active_row.get("capital_weight"))
            if avg_amount_20d <= 0 or capital_weight <= 0:
                continue
            required_notional = notional * capital_weight
            fill_rate = (
                avg_amount_20d * max_adv_participation_rate / required_notional
                if required_notional > 0
                else 1.0
            )
            tier_fill_rates.append(fill_rate)
            if fill_rate < 1.0:
                tier_below_full += 1
        return {
            "portfolio_notional_cny": notional,
            "active_pick_count": len(tier_fill_rates),
            "active_pick_below_full_fill_count": tier_below_full,
            "active_pick_full_fill_rate": (len(tier_fill_rates) - tier_below_full) / len(tier_fill_rates)
            if tier_fill_rates
            else None,
            "min_fill_rate": min(tier_fill_rates) if tier_fill_rates else None,
            "p05_fill_rate": sorted(tier_fill_rates)[max(int(len(tier_fill_rates) * 0.05) - 1, 0)]
            if tier_fill_rates
            else None,
        }

    capacity_envelope = {
        "all_active_full_fill_portfolio_notional_cny": min(full_fill_notionals) if full_fill_notionals else None,
        "p05_full_fill_portfolio_notional_cny": full_fill_notionals[max(int(len(full_fill_notionals) * 0.05) - 1, 0)]
        if full_fill_notionals
        else None,
        "median_full_fill_portfolio_notional_cny": full_fill_notionals[len(full_fill_notionals) // 2]
        if full_fill_notionals
        else None,
        "capacity_tier_stats": [_tier_fill_stats(notional) for notional in capacity_tier_notionals],
        "interpretation": (
            "This envelope does not clear the configured 1,000,000 CNY governance stress by itself; it reports "
            "the capital scale at which the same percentage-return strategy can be fully filled under the ADV proxy."
        ),
    }
    tier_stats = capacity_envelope["capacity_tier_stats"]
    ready_tiers = [
        row
        for row in tier_stats
        if _safe_float(row.get("active_pick_count")) >= minimum_active_pick_count
        and int(_safe_float(row.get("active_pick_below_full_fill_count"), 999999.0)) == 0
    ]
    largest_ready_tier = max(
        ready_tiers,
        key=lambda row: _safe_float(row.get("portfolio_notional_cny")),
        default=None,
    )
    capacity_contract = {
        "status": (
            "configured_governance_capacity_ready"
            if not blockers
            else "lower_capital_research_contract_ready"
            if largest_ready_tier
            else "no_full_fill_research_contract_tier"
        ),
        "claim_ceiling": (
            "production_capacity_clearance"
            if not blockers
            else "research_only_lower_capital_capacity_diagnostic"
            if largest_ready_tier
            else "capacity_blocked_diagnostic"
        ),
        "configured_governance_portfolio_notional_cny": portfolio_notional_cny,
        "configured_governance_status": "ready" if not blockers else "blocked",
        "max_ready_research_portfolio_notional_cny": (
            largest_ready_tier.get("portfolio_notional_cny") if largest_ready_tier else None
        ),
        "max_ready_research_tier": largest_ready_tier,
        "blocking_gate_ids": (
            [] if not blockers else ["configured_governance_capacity_stress_not_cleared"]
        ),
        "interpretation": (
            "A lower-capital tier can be used as a research-only capacity contract, but it must not be used to "
            "clear the configured governance notional or dashboard/production claims."
            if blockers and largest_ready_tier
            else "The configured governance notional is fully fillable under the ADV proxy."
            if not blockers
            else "No configured tier clears the full-fill ADV proxy."
        ),
    }
    diagnostics = {
        "status": "blocked" if blockers else "ready",
        "diagnostic_scope": "selected_pick_adv_capacity_proxy",
        "blocking_gate_ids": blockers,
        "selected_pick_count": len(selected_picks),
        "active_pick_count": len(active_rows),
        "missing_avg_amount_20d_count": missing_avg_amount_count,
        "active_pick_below_full_fill_count": len(below_full_fill),
        "active_pick_full_fill_rate": (len(active_rows) - len(below_full_fill) - missing_avg_amount_count) / len(active_rows)
        if active_rows
        else None,
        "min_fill_rate": min(fill_rates) if fill_rates else None,
        "p05_fill_rate": sorted(fill_rates)[max(int(len(fill_rates) * 0.05) - 1, 0)] if fill_rates else None,
        "worst_pick": worst_pick,
        "capacity_envelope": capacity_envelope,
        "capacity_contract": capacity_contract,
        "thresholds": {
            "portfolio_notional_cny": portfolio_notional_cny,
            "max_adv_participation_rate": max_adv_participation_rate,
            "minimum_active_pick_count": minimum_active_pick_count,
            "required_min_fill_rate": 1.0,
            "capital_weight_formula": "portfolio_weight * rank_weight_multiplier / selected_top_k",
        },
    }
    return _apply_staggered_capacity_overlay(diagnostics, selection_policy=selection_policy)


def _apply_staggered_capacity_overlay(
    capacity_diagnostics: dict[str, Any],
    *,
    selection_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(selection_policy, dict):
        return capacity_diagnostics
    overlay = selection_policy.get("staggered_entry_execution_overlay")
    if not isinstance(overlay, dict) or not overlay.get("enabled"):
        return capacity_diagnostics
    repaired_count = int(_safe_float(overlay.get("full_fill_repaired_pick_count")))
    min_fill_rate = _safe_float(overlay.get("min_staggered_fill_rate"))
    underfilled_count = int(_safe_float(capacity_diagnostics.get("active_pick_below_full_fill_count")))
    missing_count = int(_safe_float(capacity_diagnostics.get("missing_avg_amount_20d_count")))
    active_count = int(_safe_float(capacity_diagnostics.get("active_pick_count")))
    minimum_active_count = int(
        _safe_float((capacity_diagnostics.get("thresholds") or {}).get("minimum_active_pick_count"), 20.0)
    )
    blockers = [str(item) for item in capacity_diagnostics.get("blocking_gate_ids") or []]
    repair_covers_capacity_gap = (
        underfilled_count > 0
        and repaired_count >= underfilled_count
        and min_fill_rate >= 1.0
        and missing_count == 0
        and active_count >= minimum_active_count
    )
    if not repair_covers_capacity_gap:
        adjusted = dict(capacity_diagnostics)
        adjusted["staggered_entry_execution_overlay"] = {
            "status": "not_capacity_clearing",
            "entry_days": overlay.get("entry_days"),
            "exit_policy": overlay.get("exit_policy"),
            "full_fill_repaired_pick_count": repaired_count,
            "min_staggered_fill_rate": min_fill_rate,
            "source_proxy_artifact": overlay.get("source_proxy_artifact"),
            "reason": (
                "staggered overlay is present but does not cover every below-full-fill active pick with "
                "min_staggered_fill_rate >= 1.0"
            ),
        }
        return adjusted

    adjusted = dict(capacity_diagnostics)
    original_contract = capacity_diagnostics.get("capacity_contract")
    adjusted["status"] = "ready"
    adjusted["diagnostic_scope"] = "selected_pick_adv_capacity_proxy_with_staggered_entry_overlay"
    adjusted["blocking_gate_ids"] = [
        blocker for blocker in blockers if blocker != "adv_capacity_fill_rate_below_floor"
    ]
    adjusted["staggered_entry_execution_overlay"] = {
        "status": "configured_notional_proxy_ready",
        "claim_ceiling": "research_only_staggered_execution_capacity_proxy",
        "entry_days": overlay.get("entry_days"),
        "exit_policy": overlay.get("exit_policy"),
        "full_fill_repaired_pick_count": repaired_count,
        "covered_underfilled_pick_count": underfilled_count,
        "min_staggered_fill_rate": min_fill_rate,
        "source_proxy_artifact": overlay.get("source_proxy_artifact"),
        "interpretation": (
            "The original same-day selected-pick ADV proxy is below full fill, but the declared staggered-entry "
            "execution overlay repairs every below-full-fill active pick in the retained proxy evidence."
        ),
    }
    adjusted["original_same_day_capacity_diagnostics"] = {
        "status": capacity_diagnostics.get("status"),
        "diagnostic_scope": capacity_diagnostics.get("diagnostic_scope"),
        "blocking_gate_ids": capacity_diagnostics.get("blocking_gate_ids") or [],
        "active_pick_count": capacity_diagnostics.get("active_pick_count"),
        "active_pick_below_full_fill_count": capacity_diagnostics.get("active_pick_below_full_fill_count"),
        "active_pick_full_fill_rate": capacity_diagnostics.get("active_pick_full_fill_rate"),
        "min_fill_rate": capacity_diagnostics.get("min_fill_rate"),
        "worst_pick": capacity_diagnostics.get("worst_pick"),
        "capacity_contract": original_contract,
    }
    adjusted["capacity_contract"] = {
        "status": "configured_staggered_execution_capacity_proxy_ready",
        "claim_ceiling": "research_only_staggered_execution_capacity_proxy",
        "configured_governance_portfolio_notional_cny": (original_contract or {}).get(
            "configured_governance_portfolio_notional_cny",
            (capacity_diagnostics.get("thresholds") or {}).get("portfolio_notional_cny"),
        ),
        "configured_governance_status": "ready",
        "max_ready_research_portfolio_notional_cny": (original_contract or {}).get(
            "configured_governance_portfolio_notional_cny",
            (capacity_diagnostics.get("thresholds") or {}).get("portfolio_notional_cny"),
        ),
        "blocking_gate_ids": [],
        "interpretation": (
            "Capacity is ready only under the declared staggered-entry execution proxy. This does not upgrade "
            "the claim ceiling to production clearance without a full order-level replay."
        ),
    }
    return adjusted


def _execution_stress_diagnostics(candidate_run: dict[str, Any], leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    best = leaderboard[0] if leaderboard else None
    if not best:
        return {
            "status": "blocked",
            "blocking_gate_ids": ["missing_best_trial"],
        }
    best_trial_id = str(best.get("trial_id") or "")
    diagnostic = _trial_diagnostic(candidate_run, best_trial_id)
    horizon_days = int(_safe_float((diagnostic or {}).get("target_horizon_days"), 10.0))
    selected_top_k = int(_safe_float(best.get("selected_top_k"), _safe_float((diagnostic or {}).get("selected_top_k"), 5.0)))
    if _is_concentrated_top_k(best):
        if diagnostic is not None:
            returns_by_date = list(
                diagnostic.get("selected_top_k_returns_by_date") or diagnostic.get("top_5_returns_by_date") or []
            )
            selected_picks = list(
                diagnostic.get("selected_top_k_picks_by_date") or diagnostic.get("top_5_picks_by_date") or []
            )
        else:
            returns_by_date = _top5_returns_from_predictions(_prediction_rows(candidate_run, best_trial_id))
            selected_picks = _top5_picks_from_predictions(_prediction_rows(candidate_run, best_trial_id))
        portfolio_scope = f"top_{int(_safe_float(best.get('selected_top_k'), 5.0))}_equal_weight_by_date"
    else:
        if diagnostic is not None:
            picks = list(diagnostic.get("top_picks_by_date") or [])
        else:
            picks = _top_pick_returns(_prediction_rows(candidate_run, best_trial_id))
        selected_picks = picks
        returns_by_date = [
            {
                "as_of_date": row.get("as_of_date"),
                "month": row.get("month"),
                "pick_count": 1,
                "mean_net_excess_return": row.get("net_excess_return"),
            }
            for row in picks
        ]
        portfolio_scope = "top_1_pick_by_date"
    values = [_safe_float(row.get("mean_net_excess_return")) for row in returns_by_date]
    blockers: list[str] = []
    if len(values) < 20:
        blockers.append("insufficient_periods_for_execution_stress")
    cost_stress = []
    base_round_trip_cost = 0.001
    for multiplier in (1.0, 2.0, 3.0):
        extra_cost = base_round_trip_cost * (multiplier - 1.0)
        stressed_values = [value - extra_cost for value in values]
        stress_mean = mean(stressed_values) if stressed_values else None
        cost_stress.append(
            {
                "cost_multiplier": multiplier,
                "extra_cost_subtracted": extra_cost,
                "mean_net_excess_after_cost_stress": stress_mean,
                "positive_date_rate_after_cost_stress": sum(1 for value in stressed_values if value > 0)
                / len(stressed_values)
                if stressed_values
                else None,
            }
        )
        if multiplier == 2.0 and (stress_mean is None or stress_mean <= 0):
            blockers.append("cost_stress_2x_not_positive")
        if multiplier == 3.0 and (stress_mean is None or stress_mean <= 0):
            blockers.append("cost_stress_3x_not_positive")
    monthly = _monthly_return_summary(returns_by_date)
    negative_months = [row["month"] for row in monthly if _safe_float(row.get("mean_net_excess_return")) <= 0]
    if negative_months:
        blockers.append("negative_monthly_mean_under_base_cost")
    drawdown = _series_drawdown(values)
    if _safe_float(drawdown.get("max_drawdown_sum")) <= -1.0:
        blockers.append("portfolio_path_drawdown_sum_below_minus_1")
    portfolio_curve = _rolling_sleeve_curve(returns_by_date, horizon_days=horizon_days)
    result_anchor_comparison = _result_anchor_comparison(portfolio_curve)
    blockers.extend(f"result_anchor:{blocker}" for blocker in result_anchor_comparison.get("blocking_gate_ids") or [])
    selection_policy = best.get("candidate_run_selection_policy") if isinstance(best, dict) else None
    capacity_diagnostics = _capacity_fill_rate_diagnostics(
        selected_picks,
        selected_top_k=selected_top_k,
        selection_policy=selection_policy if isinstance(selection_policy, dict) else best.get("selection_policy"),
    )
    blockers.extend(f"capacity:{blocker}" for blocker in capacity_diagnostics.get("blocking_gate_ids") or [])
    return {
        "status": "blocked" if blockers else "ready",
        "diagnostic_scope": "comparison_report_execution_stress_proxy",
        "best_trial_id": best_trial_id,
        "portfolio_scope": portfolio_scope,
        "period_count": len(values),
        "mean_net_excess_return": mean(values) if values else None,
        "positive_date_rate": sum(1 for value in values if value > 0) / len(values) if values else None,
        "cost_stress": cost_stress,
        "monthly_return_summary": monthly,
        "negative_months": negative_months,
        "path_drawdown": drawdown,
        "portfolio_curve": portfolio_curve,
        "capacity_diagnostics": capacity_diagnostics,
        "result_anchor_comparison": result_anchor_comparison,
        "blocking_gate_ids": blockers,
        "thresholds": {
            "minimum_periods": 20,
            "cost_stress_multipliers": [1.0, 2.0, 3.0],
            "monthly_mean_must_be_positive": True,
            "max_drawdown_sum_min": -1.0,
            "result_anchor_thresholds": result_anchor_comparison["thresholds"],
        },
    }


def _fees_slippage_stamp_tax_stress_ready(execution_diagnostics: dict[str, Any] | None) -> bool:
    if not isinstance(execution_diagnostics, dict):
        return False
    blockers = {str(item) for item in execution_diagnostics.get("blocking_gate_ids") or []}
    if (
        "insufficient_periods_for_execution_stress" in blockers
        or "cost_stress_2x_not_positive" in blockers
        or "cost_stress_3x_not_positive" in blockers
    ):
        return False
    thresholds = execution_diagnostics.get("thresholds")
    minimum_periods = 20
    if isinstance(thresholds, dict):
        try:
            minimum_periods = int(thresholds.get("minimum_periods", minimum_periods))
        except (TypeError, ValueError):
            minimum_periods = 20
    try:
        period_count = int(execution_diagnostics.get("period_count"))
    except (TypeError, ValueError):
        return False
    if period_count < minimum_periods:
        return False
    stress_by_multiplier: dict[float, dict[str, Any]] = {}
    for row in execution_diagnostics.get("cost_stress") or []:
        if not isinstance(row, dict):
            continue
        try:
            multiplier = float(row.get("cost_multiplier"))
        except (TypeError, ValueError):
            continue
        stress_by_multiplier[multiplier] = row
    for multiplier in (1.0, 2.0, 3.0):
        row = stress_by_multiplier.get(multiplier)
        if not row:
            return False
        try:
            stress_mean = float(row.get("mean_net_excess_after_cost_stress"))
        except (TypeError, ValueError):
            return False
        if stress_mean <= 0:
            return False
    return True


def _adv_capacity_fill_rate_ready(execution_diagnostics: dict[str, Any] | None) -> bool:
    if not isinstance(execution_diagnostics, dict):
        return False
    capacity = execution_diagnostics.get("capacity_diagnostics")
    if not isinstance(capacity, dict):
        return False
    if str(capacity.get("status") or "") != "ready":
        return False
    if capacity.get("blocking_gate_ids"):
        return False
    return True


def _execution_label_contract_diagnostics(
    candidate_run: dict[str, Any],
    *,
    execution_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    label_version = str(candidate_run.get("label_version") or "")
    validation_protocol = candidate_run.get("validation_protocol") if isinstance(candidate_run, dict) else {}
    evaluation_row_policy = (
        str(validation_protocol.get("evaluation_row_policy") or "")
        if isinstance(validation_protocol, dict)
        else ""
    )
    v3_ready = label_version == "shortpick_model_executable_label_matrix:v3"
    ready_only = evaluation_row_policy == "label_status_ready_and_target_label_present_only"
    fees_ready = _fees_slippage_stamp_tax_stress_ready(execution_diagnostics)
    capacity_ready = _adv_capacity_fill_rate_ready(execution_diagnostics)
    covered_gate_ids: list[str] = []
    checks = [
        {
            "gate_id": "t_plus_1_execution_model",
            "status": "ready" if v3_ready and ready_only else "blocked",
            "evidence": (
                "label-v3 rows persist entry_execution and runner evaluates ready labels only"
                if v3_ready and ready_only
                else "requires label-v3 entry_execution plus ready-label-only evaluation"
            ),
        },
        {
            "gate_id": "suspension_limit_buy_sellability",
            "status": "ready" if v3_ready and ready_only else "blocked",
            "evidence": (
                "label-v3 rows persist entry and per-horizon exit execution including limit/suspension blocks"
                if v3_ready and ready_only
                else "requires label-v3 entry/exit execution fields plus ready-label-only evaluation"
            ),
        },
        {
            "gate_id": "fees_slippage_stamp_tax",
            "status": "ready" if fees_ready else "blocked",
            "evidence": (
                "comparison report cost stress covers 1x/2x/3x fee, slippage and stamp-tax proxy with positive mean"
                if fees_ready
                else "requires positive 1x/2x/3x fee, slippage and stamp-tax stress evidence"
            ),
        },
        {
            "gate_id": "adv_capacity_fill_rate",
            "status": "ready" if capacity_ready else "blocked",
            "evidence": (
                "selected-pick ADV capacity proxy has sufficient pick-level liquidity and full fill at 5pct ADV"
                if capacity_ready
                else "requires selected-pick avg_amount_20d capacity stress with full fill at 5pct ADV"
            ),
        },
    ]
    for check in checks:
        if check["status"] == "ready":
            covered_gate_ids.append(str(check["gate_id"]))
    return {
        "status": "partial_ready" if covered_gate_ids else "blocked",
        "label_version": label_version,
        "evaluation_row_policy": evaluation_row_policy,
        "fees_slippage_stamp_tax_stress_ready": fees_ready,
        "adv_capacity_fill_rate_ready": capacity_ready,
        "covered_execution_gate_ids": covered_gate_ids,
        "blocking_gate_ids": [str(check["gate_id"]) for check in checks if check["status"] != "ready"],
        "checks": checks,
    }


def build_model_comparison_report_artifact(
    *,
    validation_run_id: str,
    candidate_run: dict[str, Any],
    model_spec_registry: dict[str, Any],
) -> dict[str, Any]:
    registry_selection_policies = _registry_selection_policies(model_spec_registry)
    leaderboard = [
        _leaderboard_row(trial, registry_selection_policies=registry_selection_policies)
        for trial in candidate_run.get("trial_summaries") or []
    ]
    _attach_trial_stability(leaderboard, candidate_run)
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
    execution_diagnostics = _execution_stress_diagnostics(candidate_run, leaderboard)
    execution_label_contract = _execution_label_contract_diagnostics(
        candidate_run,
        execution_diagnostics=execution_diagnostics,
    )
    gate_blockers = [
        *[f"overfit:{blocker}" for blocker in overfit_diagnostics.get("blocking_gate_ids") or []],
        *[f"winner_dependency:{blocker}" for blocker in winner_dependency.get("blocking_gate_ids") or []],
        *[f"execution_stress:{blocker}" for blocker in execution_diagnostics.get("blocking_gate_ids") or []],
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
        "execution_diagnostics": execution_diagnostics,
        "execution_label_contract": execution_label_contract,
        "kill_list": kill_list,
        "next_research_questions": [
            "Replace proxy PBO/DSR with full combinatorially symmetric cross-validation diagnostics when sample width is sufficient.",
            "Broaden winner-dependency checks to top 3 symbols, top 3 dates and industry concentration.",
            "Extend executable labels from T+1 and limit/suspension readiness into fee/slippage/stamp-tax and ADV capacity.",
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
