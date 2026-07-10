from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.shortpick_strategy_lab_read_model import (
    INITIAL_CASH_CNY,
    build_shortpick_strategy_lab_historical_replay_read_model,
)

COMPARISON_CONTRACT_VERSION = "shortpick_strategy_lab_fair_comparison_contract.v1"
FRONTIER_ADVANTAGE_THRESHOLD = 0.10
REQUIRED_FULL_HISTORY_METRICS = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "negative_month_count",
    "worst_monthly_return",
    "skipped_order_rate",
    "skipped_signal_rate",
    "buy_order_count",
    "final_nav_cny",
    "mean_invested_ratio",
    "max_single_symbol_exposure_pct",
)
FRONTIER_METRIC_DIRECTIONS = {
    "total_return": "higher",
    "annualized_return": "higher",
    "max_drawdown": "higher",
    "negative_month_count": "lower",
    "worst_monthly_return": "higher",
    "skipped_order_rate": "lower",
    "skipped_signal_rate": "lower",
    "max_single_symbol_exposure_pct": "lower",
    "final_nav_cny": "higher",
}
STRICT_WINDOW_KEYS = ("signal_date_from", "signal_date_to")
DIAGNOSTIC_SCOPE_KEYS = ("signal_day_count", "selected_pick_count", "market_symbol_count")


def build_shortpick_strategy_lab_fair_comparison_readiness(
    *,
    candidate_replay_artifact: dict[str, Any] | None = None,
    baseline_read_model: dict[str, Any] | None = None,
    require_frontier_acceptance: bool = False,
) -> dict[str, Any]:
    """Build a deterministic audit that blocks cross-window promotion claims.

    This contract exists because the strategy-lab frontend uses static full-history
    account-replay summaries, while upstream exploration can produce shorter
    walk-forward candidate windows. Those two totals are not interchangeable.
    """

    baseline = baseline_read_model or build_shortpick_strategy_lab_historical_replay_read_model()
    baseline_scope = _normalize_scope(baseline.get("data_scope"))
    candidate_scope = _normalize_scope((candidate_replay_artifact or {}).get("data_scope"))
    baseline_configs = _baseline_config_summaries(baseline)
    window_checks = _window_checks(baseline_scope, candidate_scope)
    blocking_reasons = [row["reason"] for row in window_checks if row["status"] == "blocked"]
    candidate_artifact_id = _candidate_artifact_id(candidate_replay_artifact)
    candidate_summary = _candidate_summary(candidate_replay_artifact)
    frontier_acceptance = _frontier_acceptance(candidate_summary, baseline_configs)
    if require_frontier_acceptance:
        blocking_reasons.extend(frontier_acceptance["blocking_reasons"])
    status = (
        "passed_frontier_acceptance"
        if require_frontier_acceptance and not blocking_reasons
        else "passed_same_window_metrics_ready"
        if not blocking_reasons
        else "blocked"
    )
    claim_ceiling = (
        "same_window_research_comparison_allowed"
        if status.startswith("passed")
        else "directional_research_only_no_frontend_replacement_claim"
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "contract_version": COMPARISON_CONTRACT_VERSION,
        "artifact_type": "shortpick_strategy_lab_fair_comparison_readiness",
        "artifact_id": _artifact_id(
            {
                "baseline_scope": baseline_scope,
                "candidate_scope": candidate_scope,
                "candidate_artifact_id": candidate_artifact_id,
                "blocking_reasons": blocking_reasons,
                "require_frontier_acceptance": require_frontier_acceptance,
            }
        ),
        "status": status,
        "claim_ceiling": claim_ceiling,
        "baseline_reference": {
            "source": "shortpick_strategy_lab_historical_replay_static_read_model",
            "data_scope": baseline_scope,
            "config_count": len(baseline_configs),
            "best_metric_floor": _best_metric_floor(baseline_configs),
            "configs": baseline_configs,
        },
        "candidate_reference": {
            "artifact_id": candidate_artifact_id,
            "data_scope": candidate_scope,
            "summary": candidate_summary,
        },
        "frontier_acceptance": frontier_acceptance,
        "comparison_rules": {
            "total_return_cross_window_comparison_allowed": False,
            "annualized_return_cross_window_screening_allowed": True,
            "annualized_return_cross_window_promotion_allowed": False,
            "frontend_replacement_claim_allowed": status.startswith("passed"),
            "frontier_acceptance_required": require_frontier_acceptance,
            "frontier_control_admission_allowed": frontier_acceptance["status"] == "passed",
            "advantage_threshold": FRONTIER_ADVANTAGE_THRESHOLD,
            "negative_month_breakthrough_delta": 1,
            "same_window_required_keys": list(STRICT_WINDOW_KEYS),
            "diagnostic_scope_keys": list(DIAGNOSTIC_SCOPE_KEYS),
            "required_metrics": list(REQUIRED_FULL_HISTORY_METRICS),
        },
        "account_contract": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "capital_mode": "current_nav_fraction_compound",
            "board_lot_size": 100,
            "entry_execution": "next_trading_day_account_replay",
            "required_replay_granularity": "order_level_account_replay_with_nav_and_monthly_returns",
            "forbidden_comparison_mode": "short_window_total_return_vs_full_history_total_return",
        },
        "window_checks": window_checks,
        "blocking_reasons": blocking_reasons,
        "required_next_artifacts": _required_next_artifacts(blocking_reasons),
        "event_refs": ["shortpick_strategy_lab.fair_comparison_readiness.v1"],
    }
    return payload


def load_candidate_replay_artifact(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_shortpick_strategy_lab_fair_comparison_readiness(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _normalize_scope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "status": "missing",
            "signal_date_from": None,
            "signal_date_to": None,
            "signal_day_count": None,
            "selected_pick_count": None,
        }
    return {
        "status": "ready",
        "signal_date_from": value.get("signal_date_from"),
        "signal_date_to": value.get("signal_date_to"),
        "signal_day_count": value.get("signal_day_count"),
        "selected_pick_count": value.get("selected_pick_count"),
        "market_symbol_count": value.get("market_symbol_count"),
        "history_scope_label": value.get("history_scope_label"),
    }


def _baseline_config_summaries(read_model: dict[str, Any]) -> list[dict[str, Any]]:
    configs = []
    for row in list(read_model.get("selected_configs") or []) + list(read_model.get("baseline_configs") or []):
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        configs.append(
            {
                "config_id": row.get("config_id"),
                "label": row.get("label"),
                "role": row.get("role"),
                "summary": {key: summary.get(key) for key in REQUIRED_FULL_HISTORY_METRICS},
            }
        )
    return configs


def _window_checks(baseline_scope: dict[str, Any], candidate_scope: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if candidate_scope.get("status") != "ready":
        checks.append(
            {
                "check_id": "candidate_replay_scope_present",
                "status": "blocked",
                "reason": "candidate_replay_artifact_missing_data_scope",
            }
        )
        return checks
    for key in STRICT_WINDOW_KEYS:
        baseline_value = baseline_scope.get(key)
        candidate_value = candidate_scope.get(key)
        matched = baseline_value == candidate_value
        checks.append(
            {
                "check_id": f"same_{key}",
                "status": "passed" if matched else "blocked",
                "baseline_value": baseline_value,
                "candidate_value": candidate_value,
                "reason": None if matched else f"candidate_{key}_not_equal_frontend_full_history",
            }
        )
    return checks


def _best_metric_floor(configs: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [row.get("summary") or {} for row in configs]
    return {
        "best_total_return": _metric_best(summaries, "total_return", higher_is_better=True),
        "best_annualized_return": _metric_best(summaries, "annualized_return", higher_is_better=True),
        "best_max_drawdown": _metric_best(summaries, "max_drawdown", higher_is_better=True),
        "best_negative_month_count": _metric_best(summaries, "negative_month_count", higher_is_better=False),
        "best_worst_monthly_return": _metric_best(summaries, "worst_monthly_return", higher_is_better=True),
        "best_skipped_order_rate": _metric_best(summaries, "skipped_order_rate", higher_is_better=False),
        "best_skipped_signal_rate": _metric_best(summaries, "skipped_signal_rate", higher_is_better=False),
        "best_max_single_symbol_exposure_pct": _metric_best(
            summaries,
            "max_single_symbol_exposure_pct",
            higher_is_better=False,
        ),
        "best_final_nav_cny": _metric_best(summaries, "final_nav_cny", higher_is_better=True),
    }


def _frontier_acceptance(candidate_summary: dict[str, Any], configs: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [row.get("summary") or {} for row in configs]
    checks: list[dict[str, Any]] = []
    breakthroughs: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    for metric, direction in FRONTIER_METRIC_DIRECTIONS.items():
        best_value = _metric_best(summaries, metric, higher_is_better=direction == "higher")
        candidate_value = candidate_summary.get(metric)
        if not isinstance(candidate_value, int | float) or not isinstance(best_value, int | float):
            passed = False
            reason = f"candidate_missing_frontier_metric:{metric}"
        else:
            passed = candidate_value >= best_value if direction == "higher" else candidate_value <= best_value
            reason = None if passed else f"candidate_degrades_frontier_metric:{metric}"
        check = {
            "metric": metric,
            "direction": direction,
            "frontier_value": best_value,
            "candidate_value": candidate_value,
            "status": "passed" if passed else "blocked",
            "reason": reason,
        }
        checks.append(check)
        if reason:
            blocking_reasons.append(reason)
        if passed and isinstance(candidate_value, int | float) and isinstance(best_value, int | float):
            improvement = _relative_improvement(metric, float(candidate_value), float(best_value), direction=direction)
            if improvement >= FRONTIER_ADVANTAGE_THRESHOLD or (
                metric == "negative_month_count" and candidate_value <= best_value - 1
            ):
                breakthroughs.append(
                    {
                        "metric": metric,
                        "frontier_value": best_value,
                        "candidate_value": candidate_value,
                        "relative_improvement": improvement,
                        "negative_month_delta": best_value - candidate_value
                        if metric == "negative_month_count"
                        else None,
                    }
                )
    if not breakthroughs:
        blocking_reasons.append("candidate_has_no_10pct_or_negative_month_breakthrough")
    return {
        "status": "passed" if not blocking_reasons else "blocked",
        "frontier_config_count": len(configs),
        "all_frontier_metrics_non_degraded": all(row["status"] == "passed" for row in checks),
        "has_required_breakthrough": bool(breakthroughs),
        "checks": checks,
        "breakthroughs": breakthroughs,
        "blocking_reasons": blocking_reasons,
    }


def _relative_improvement(metric: str, candidate: float, frontier: float, *, direction: str) -> float:
    if metric == "negative_month_count":
        return (frontier - candidate) / frontier if frontier > 0 else 0.0
    if direction == "lower":
        return (frontier - candidate) / abs(frontier) if frontier else 0.0
    if metric in {"max_drawdown", "worst_monthly_return"} and frontier < 0:
        return (abs(frontier) - abs(candidate)) / abs(frontier)
    return (candidate - frontier) / abs(frontier) if frontier else 0.0


def _metric_best(summaries: list[dict[str, Any]], key: str, *, higher_is_better: bool) -> Any:
    values = [row.get(key) for row in summaries if isinstance(row.get(key), int | float)]
    if not values:
        return None
    return max(values) if higher_is_better else min(values)


def _candidate_artifact_id(candidate_replay_artifact: dict[str, Any] | None) -> str | None:
    if not isinstance(candidate_replay_artifact, dict):
        return None
    return (
        candidate_replay_artifact.get("artifact_id")
        or candidate_replay_artifact.get("replay_id")
        or candidate_replay_artifact.get("source_candidate_run_id")
        or candidate_replay_artifact.get("trial_id")
    )


def _candidate_summary(candidate_replay_artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate_replay_artifact, dict):
        return {}
    for key in ("summary", "baseline_summary"):
        value = candidate_replay_artifact.get(key)
        if isinstance(value, dict):
            return {metric: value.get(metric) for metric in REQUIRED_FULL_HISTORY_METRICS if metric in value}
    variants = candidate_replay_artifact.get("variants")
    if isinstance(variants, list) and variants:
        first = variants[0]
        if isinstance(first, dict) and isinstance(first.get("summary"), dict):
            summary = first["summary"]
            return {metric: summary.get(metric) for metric in REQUIRED_FULL_HISTORY_METRICS if metric in summary}
    leaderboard = candidate_replay_artifact.get("leaderboard")
    results = candidate_replay_artifact.get("results")
    if isinstance(leaderboard, list) and leaderboard and isinstance(results, list):
        top_config_id = leaderboard[0].get("config_id") if isinstance(leaderboard[0], dict) else None
        for result in results:
            if not isinstance(result, dict) or result.get("config_id") != top_config_id:
                continue
            summary = result.get("summary")
            if isinstance(summary, dict):
                return {metric: summary.get(metric) for metric in REQUIRED_FULL_HISTORY_METRICS if metric in summary}
    if isinstance(leaderboard, list) and leaderboard and isinstance(leaderboard[0], dict):
        return {metric: leaderboard[0].get(metric) for metric in REQUIRED_FULL_HISTORY_METRICS if metric in leaderboard[0]}
    return {}


def _required_next_artifacts(blocking_reasons: list[str]) -> list[dict[str, str]]:
    if not blocking_reasons:
        return []
    return [
        {
            "artifact": "candidate_full_history_order_level_account_replay",
            "purpose": "把新上游候选跑到前端完整历史窗口后，再与前端策略全集比较。",
        },
        {
            "artifact": "frontend_strategy_set_same_window_order_level_account_replays",
            "purpose": "如果候选只能产生较短信号期，则必须给前端策略全集补同窗口逐订单账本。",
        },
        {
            "artifact": "fair_comparison_readiness_passed_payload",
            "purpose": "任何上线或替换声明必须引用通过状态的可比性审计。",
        },
    ]


def _artifact_id(material: dict[str, Any]) -> str:
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
    return "shortpick-strategy-lab-fair-comparison-readiness-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[
        :16
    ]
