from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.capacity_opportunity_feature_gap import _candidate_archetypes
from ashare_evidence.capacity_opportunity_set_discovery import (
    DEFAULT_BENCHMARK_SYMBOL,
    DEFAULT_BENCHMARK_SYMBOLS,
    _attach_percentiles,
    _market_histories_for_window,
    _metrics_by_symbol,
)


CAPACITY_OPPORTUNITY_ARCHETYPE_SAMPLE_VERSION = "capacity_opportunity_archetype_sample.v1"


def build_capacity_opportunity_archetype_sample_preflight(
    session: Session,
    *,
    candidate_run: dict[str, Any],
    trial_id: str,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    sample_date_count: int = 12,
    top_k: int = 3,
    portfolio_notional_cny: float = 1_000_000.0,
    slot_capital_weight: float = 0.91,
    max_adv_participation_rate: float = 0.05,
) -> dict[str, Any]:
    """Run a small full-market sampled archetype preflight against the current frontier dates."""

    trial = _trial_by_id(candidate_run, trial_id)
    baseline_returns = list(trial.get("selected_top_k_returns_by_date") or [])
    sampled_dates = _sample_dates([str(row.get("as_of_date")) for row in baseline_returns], sample_date_count)
    baseline_by_date = {str(row.get("as_of_date")): _safe_float(row.get("mean_net_excess_return"), 0.0) for row in baseline_returns}
    full_fill_avg_amount_20d = (
        portfolio_notional_cny * slot_capital_weight / max(max_adv_participation_rate, 0.000001)
    )

    date_results: list[dict[str, Any]] = []
    blocking_gate_ids: list[str] = []
    for as_of_date_text in sampled_dates:
        as_of_date = date.fromisoformat(as_of_date_text)
        histories = _market_histories_for_window(session, as_of_date)
        metrics = _metrics_by_symbol(histories, as_of_date=as_of_date, benchmark_symbol=benchmark_symbol)
        benchmark = metrics.get(benchmark_symbol)
        if not benchmark or benchmark.get("future_return_20d") is None:
            blocking_gate_ids.append(f"capacity_opportunity_archetype_sample:{as_of_date_text}:missing_benchmark")
            continue
        benchmark_future = _safe_float(benchmark.get("future_return_20d"), 0.0)
        candidates = [
            row
            for symbol, row in metrics.items()
            if symbol not in DEFAULT_BENCHMARK_SYMBOLS
            and _is_executable_main_board_stock(symbol, row.get("name"))
            and _safe_float(row.get("avg_amount_20d"), 0.0) >= full_fill_avg_amount_20d
            and row.get("future_return_20d") is not None
        ]
        _attach_percentiles(
            candidates,
            fields=[
                "avg_amount_20d",
                "return_5d",
                "return_20d",
                "amount_10d_vs_20d",
                "volatility_20d",
                "turnover_rate",
                "total_mv",
            ],
        )
        scored = []
        for row in candidates:
            archetypes = _candidate_archetypes(row, full_fill_avg_amount_20d=full_fill_avg_amount_20d)
            if not archetypes:
                continue
            future_excess = _safe_float(row.get("future_return_20d"), 0.0) - benchmark_future
            scored.append(
                {
                    "symbol": row.get("symbol"),
                    "name": row.get("name"),
                    "archetypes": archetypes,
                    "archetype_score": _archetype_score(row, archetypes),
                    "future_excess_return_20d": future_excess,
                    "avg_amount_20d": _safe_float(row.get("avg_amount_20d")),
                    "amount_10d_vs_20d_percentile": _safe_float(row.get("amount_10d_vs_20d_percentile")),
                    "return_5d_percentile": _safe_float(row.get("return_5d_percentile")),
                    "return_20d_percentile": _safe_float(row.get("return_20d_percentile")),
                    "turnover_rate_percentile": _safe_float(row.get("turnover_rate_percentile")),
                    "volatility_20d_percentile": _safe_float(row.get("volatility_20d_percentile")),
                    "total_mv_percentile": _safe_float(row.get("total_mv_percentile")),
                }
            )
        scored.sort(key=lambda row: (_safe_float(row.get("archetype_score"), -999.0), _safe_float(row.get("avg_amount_20d"), 0.0)), reverse=True)
        selected = scored[: max(top_k, 1)]
        archetype_return = mean(_safe_float(row.get("future_excess_return_20d"), 0.0) for row in selected) if selected else 0.0
        baseline_return = baseline_by_date.get(as_of_date_text, 0.0)
        date_results.append(
            {
                "as_of_date": as_of_date_text,
                "baseline_frontier_mean_net_excess_return": baseline_return,
                "archetype_top_k_mean_future_excess_return": archetype_return,
                "return_gap_vs_baseline": archetype_return - baseline_return,
                "liquid_candidate_count": len(candidates),
                "archetype_candidate_count": len(scored),
                "selected_top_k": selected,
            }
        )

    if not sampled_dates:
        blocking_gate_ids.append("capacity_opportunity_archetype_sample:no_sample_dates")
    if len(date_results) < max(1, int(len(sampled_dates) * 0.8)):
        blocking_gate_ids.append("capacity_opportunity_archetype_sample:insufficient_completed_sample_dates")

    baseline_stats = _curve_stats(
        [(row["as_of_date"], _safe_float(row.get("baseline_frontier_mean_net_excess_return"), 0.0)) for row in date_results]
    )
    archetype_stats = _curve_stats(
        [(row["as_of_date"], _safe_float(row.get("archetype_top_k_mean_future_excess_return"), 0.0)) for row in date_results]
    )
    gap_stats = _curve_stats([(row["as_of_date"], _safe_float(row.get("return_gap_vs_baseline"), 0.0)) for row in date_results])

    if archetype_stats["mean"] < baseline_stats["mean"]:
        blocking_gate_ids.append("capacity_opportunity_archetype_sample:sample_mean_below_frontier")
    if archetype_stats["negative_month_count"] > baseline_stats["negative_month_count"]:
        blocking_gate_ids.append("capacity_opportunity_archetype_sample:sample_negative_months_above_frontier")
    if archetype_stats["path_drawdown_sum"] < baseline_stats["path_drawdown_sum"]:
        blocking_gate_ids.append("capacity_opportunity_archetype_sample:sample_path_drawdown_worse_than_frontier")

    return {
        "artifact_type": "capacity_opportunity_archetype_sample",
        "schema_version": CAPACITY_OPPORTUNITY_ARCHETYPE_SAMPLE_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": sorted(set(blocking_gate_ids)),
        "claim_ceiling": "sampled_full_market_preflight_only_no_model_replay_no_promotion",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "trial_id": trial_id,
        "benchmark_symbol": benchmark_symbol,
        "account_filter": "main_board_prefix_000_001_002_003_600_601_603_605_excluding_st_and_delisting_names",
        "sample_date_count_requested": sample_date_count,
        "sample_date_count_completed": len(date_results),
        "top_k": top_k,
        "full_fill_avg_amount_20d_required": full_fill_avg_amount_20d,
        "baseline_frontier_sample_stats": baseline_stats,
        "archetype_sample_stats": archetype_stats,
        "gap_vs_baseline_sample_stats": gap_stats,
        "interpretation": _interpretation(baseline_stats, archetype_stats),
        "dates": date_results,
    }


def write_capacity_opportunity_archetype_sample_preflight(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _trial_by_id(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    for trial in candidate_run.get("trial_diagnostics") or []:
        if trial.get("trial_id") == trial_id:
            return trial
    raise ValueError(f"trial_id not found in candidate run: {trial_id}")


def _sample_dates(date_values: list[str], sample_date_count: int) -> list[str]:
    dates = sorted({value for value in date_values if value})
    if len(dates) <= max(sample_date_count, 0):
        return dates
    if sample_date_count <= 1:
        return [dates[len(dates) // 2]]
    indices = [round(index * (len(dates) - 1) / (sample_date_count - 1)) for index in range(sample_date_count)]
    return [dates[index] for index in sorted(set(indices))]


def _is_main_board_stock_symbol(symbol: str) -> bool:
    ticker = symbol.split(".", 1)[0]
    return ticker.startswith(("000", "001", "002", "003", "600", "601", "603", "605"))


def _is_executable_main_board_stock(symbol: str, name: Any = None) -> bool:
    if not _is_main_board_stock_symbol(symbol):
        return False
    text = str(name or "").upper().replace(" ", "")
    return not (text.startswith("ST") or text.startswith("*ST") or "退" in text)


def _archetype_score(row: dict[str, Any], archetypes: list[str]) -> float:
    amount_expansion = _safe_float(row.get("amount_10d_vs_20d_percentile"), 0.0)
    return_5d = _safe_float(row.get("return_5d_percentile"), 0.0)
    return_20d = _safe_float(row.get("return_20d_percentile"), 0.0)
    turnover = _safe_float(row.get("turnover_rate_percentile"), 0.0)
    volatility = _safe_float(row.get("volatility_20d_percentile"), 1.0)
    total_mv = _safe_float(row.get("total_mv_percentile"), 0.0)
    avg_amount = _safe_float(row.get("avg_amount_20d_percentile"), 0.0)
    scores = []
    if "turnover_amount_rebound" in archetypes:
        scores.append(amount_expansion + return_5d + turnover - 0.2 * volatility)
    if "large_liquid_pullback" in archetypes:
        scores.append(avg_amount + total_mv + 0.3 * (1.0 - return_20d) + 0.3 * (1.0 - volatility))
    if "low_volatility_pullback_turn" in archetypes:
        scores.append(amount_expansion + (1.0 - volatility) + (1.0 - return_20d))
    if "small_mid_turnover_reversal" in archetypes:
        scores.append(amount_expansion + turnover + (1.0 - total_mv))
    return max(scores) if scores else -999.0


def _curve_stats(returns_by_date: list[tuple[str, float]]) -> dict[str, Any]:
    values = [value for _, value in returns_by_date]
    by_month: dict[str, list[float]] = defaultdict(list)
    for as_of_date, value in returns_by_date:
        by_month[str(as_of_date)[:7]].append(value)
    monthly = {month: sum(month_values) / len(month_values) for month, month_values in by_month.items()}
    negative_months = [month for month, value in sorted(monthly.items()) if value <= 0]
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
    return {
        "period_count": len(values),
        "mean": sum(values) / len(values) if values else 0.0,
        "positive_date_rate": sum(1 for value in values if value > 0) / len(values) if values else 0.0,
        "negative_month_count": len(negative_months),
        "negative_months": negative_months,
        "worst_monthly_mean": min(monthly.values()) if monthly else None,
        "path_drawdown_sum": max_drawdown,
        "sum_return_proxy": sum(values),
    }


def _interpretation(baseline_stats: dict[str, Any], archetype_stats: dict[str, Any]) -> str:
    if archetype_stats["mean"] >= baseline_stats["mean"] and archetype_stats["negative_month_count"] <= baseline_stats["negative_month_count"]:
        return "Sampled archetype opportunity generation is competitive enough to justify a larger preflight, not promotion."
    return "Sampled archetype opportunity generation does not beat the current frontier sample; do not run full713 from this archetype-only model."


def _safe_float(value: Any, default: float | None = None) -> float:
    try:
        if value is None:
            return 0.0 if default is None else default
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0 if default is None else default
    if math.isnan(parsed) or math.isinf(parsed):
        return 0.0 if default is None else default
    return parsed
