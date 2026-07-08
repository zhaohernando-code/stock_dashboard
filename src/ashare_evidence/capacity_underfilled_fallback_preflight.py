from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.capacity_opportunity_learned_sample import (
    _candidate_rows_for_date,
    _compact_candidate,
    _fit_model_profile,
    _sample_dates,
    _score_row,
    _safe_float,
)
from ashare_evidence.capacity_opportunity_set_discovery import DEFAULT_BENCHMARK_SYMBOL


CAPACITY_UNDERFILLED_FALLBACK_PREFLIGHT_VERSION = "capacity_underfilled_fallback_preflight.v1"

FALLBACK_VARIANT_OBJECTIVES = {
    "fallback_learned_frontier_excess": "frontier_excess",
    "fallback_prototype_frontier_excess": "prototype_frontier_excess",
    "fallback_prototype_frontier_floor_stability": "prototype_frontier_floor_stability",
}


def build_capacity_underfilled_fallback_preflight(
    session: Session,
    *,
    candidate_run: dict[str, Any],
    trial_id: str,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    train_date_count: int = 24,
    portfolio_notional_cny: float = 1_000_000.0,
    max_adv_participation_rate: float = 0.05,
) -> dict[str, Any]:
    """Test full-market learned fallback only on selected underfilled slots.

    This preflight preserves the current frontier on all non-underfilled dates. It only asks whether a
    prior-date-trained full-market model can fill residual capital for the three remaining capacity blocker slots.
    """

    trial = _trial_by_id(candidate_run, trial_id)
    selected_top_k = int(_safe_float(trial.get("selected_top_k"), 1.0) or 1)
    selected_picks = list(trial.get("selected_top_k_picks_by_date") or [])
    selected_returns = list(trial.get("selected_top_k_returns_by_date") or [])
    baseline_by_date = {
        str(row.get("as_of_date")): _safe_float(row.get("mean_net_excess_return"))
        for row in selected_returns
        if row.get("as_of_date")
    }
    selected_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected_picks:
        as_of_date_text = str(row.get("as_of_date") or "")
        if as_of_date_text:
            selected_by_date[as_of_date_text].append(row)

    underfilled_dates = [
        as_of_date_text
        for as_of_date_text in sorted(selected_by_date)
        if _underfilled_rows(
            selected_by_date[as_of_date_text],
            selected_top_k=selected_top_k,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
        )
    ]
    all_baseline_returns = [(str(row.get("as_of_date")), _safe_float(row.get("mean_net_excess_return"))) for row in selected_returns]
    baseline_stats = _curve_stats(all_baseline_returns)
    variant_returns = {variant_name: dict(all_baseline_returns) for variant_name in FALLBACK_VARIANT_OBJECTIVES}
    variant_details: dict[str, list[dict[str, Any]]] = {variant_name: [] for variant_name in FALLBACK_VARIANT_OBJECTIVES}
    skipped_dates: list[dict[str, str]] = []

    for as_of_date_text in underfilled_dates:
        prior_dates = [date_text for date_text in sorted(baseline_by_date) if date_text < as_of_date_text]
        train_dates = _sample_dates(prior_dates, train_date_count)
        if len(train_dates) < max(1, min(train_date_count, len(prior_dates))):
            skipped_dates.append({"as_of_date": as_of_date_text, "reason": "insufficient_train_dates"})
            continue
        rows_by_train_date: dict[str, list[dict[str, Any]]] = {}
        for train_date in train_dates:
            train_rows = _candidate_rows_for_date(
                session,
                as_of_date=date.fromisoformat(train_date),
                benchmark_symbol=benchmark_symbol,
                full_fill_avg_amount_20d=0.0,
            )
            for row in train_rows:
                row["frontier_baseline_return"] = baseline_by_date.get(train_date, 0.0)
            rows_by_train_date[train_date] = train_rows
        train_rows = [row for rows in rows_by_train_date.values() for row in rows]
        if not train_rows:
            skipped_dates.append({"as_of_date": as_of_date_text, "reason": "empty_train_rows"})
            continue
        eval_candidates = _candidate_rows_for_date(
            session,
            as_of_date=date.fromisoformat(as_of_date_text),
            benchmark_symbol=benchmark_symbol,
            full_fill_avg_amount_20d=0.0,
        )
        if not eval_candidates:
            skipped_dates.append({"as_of_date": as_of_date_text, "reason": "empty_eval_candidates"})
            continue
        for row in eval_candidates:
            row["frontier_baseline_return"] = baseline_by_date.get(as_of_date_text, 0.0)

        for variant_name, objective in FALLBACK_VARIANT_OBJECTIVES.items():
            model_profile = _fit_model_profile(train_rows, objective=objective)
            scored_candidates = [
                {
                    **_compact_candidate(row),
                    "max_fill_weight": _max_fill_weight(
                        row,
                        portfolio_notional_cny=portfolio_notional_cny,
                        max_adv_participation_rate=max_adv_participation_rate,
                    ),
                    "model_score": _score_row(row, model_profile=model_profile),
                }
                for row in eval_candidates
            ]
            scored_candidates.sort(
                key=lambda row: (_safe_float(row.get("model_score")), _safe_float(row.get("avg_amount_20d"))),
                reverse=True,
            )
            adjusted = _adjust_underfilled_date_return(
                selected_by_date[as_of_date_text],
                fallback_candidates=scored_candidates,
                selected_top_k=selected_top_k,
                portfolio_notional_cny=portfolio_notional_cny,
                max_adv_participation_rate=max_adv_participation_rate,
            )
            variant_returns[variant_name][as_of_date_text] = adjusted["adjusted_net_excess_return"]
            variant_details[variant_name].append(
                {
                    "as_of_date": as_of_date_text,
                    "baseline_frontier_return": baseline_by_date.get(as_of_date_text),
                    "adjusted_net_excess_return": adjusted["adjusted_net_excess_return"],
                    "return_gap_vs_baseline": adjusted["adjusted_net_excess_return"]
                    - baseline_by_date.get(as_of_date_text, 0.0),
                    "train_date_count": len(train_dates),
                    "train_row_count": len(train_rows),
                    "underfilled_rows": adjusted["underfilled_rows"],
                    "fallback_rows": adjusted["fallback_rows"],
                }
            )

    variant_stats = {
        variant_name: _curve_stats(sorted(returns_by_date.items()))
        for variant_name, returns_by_date in variant_returns.items()
    }
    promising_variants = [
        variant_name
        for variant_name, stats in variant_stats.items()
        if stats["mean"] >= baseline_stats["mean"]
        and stats["negative_month_count"] <= baseline_stats["negative_month_count"]
        and stats["path_drawdown_sum"] >= baseline_stats["path_drawdown_sum"]
    ]
    blocking_gate_ids = []
    if skipped_dates:
        blocking_gate_ids.append("capacity_underfilled_fallback:skipped_underfilled_dates")
    if not underfilled_dates:
        blocking_gate_ids.append("capacity_underfilled_fallback:no_underfilled_dates")
    if not promising_variants:
        blocking_gate_ids.append("capacity_underfilled_fallback:no_variant_preserves_frontier")

    return {
        "artifact_type": "capacity_underfilled_fallback_preflight",
        "schema_version": CAPACITY_UNDERFILLED_FALLBACK_PREFLIGHT_VERSION,
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": sorted(set(blocking_gate_ids)),
        "claim_ceiling": "targeted_underfilled_slot_fallback_preflight_only_no_model_replay_no_promotion",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "trial_id": trial_id,
        "benchmark_symbol": benchmark_symbol,
        "portfolio_notional_cny": portfolio_notional_cny,
        "max_adv_participation_rate": max_adv_participation_rate,
        "selected_top_k": selected_top_k,
        "underfilled_dates": underfilled_dates,
        "train_date_count_requested": train_date_count,
        "baseline_frontier_stats": baseline_stats,
        "variant_objectives": FALLBACK_VARIANT_OBJECTIVES,
        "variant_stats": variant_stats,
        "promising_variants": promising_variants,
        "skipped_dates": skipped_dates,
        "variant_details": variant_details,
        "interpretation": _interpretation(promising_variants, baseline_stats, variant_stats),
    }


def write_capacity_underfilled_fallback_preflight(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _adjust_underfilled_date_return(
    selected_rows: list[dict[str, Any]],
    *,
    fallback_candidates: list[dict[str, Any]],
    selected_top_k: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
) -> dict[str, Any]:
    used_symbols = {str(row.get("symbol") or "") for row in selected_rows}
    adjusted_return = 0.0
    underfilled_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    candidate_index = 0
    for row in sorted(selected_rows, key=lambda item: _safe_float(item.get("rank"), 999999.0)):
        target_weight = _target_capital_weight(row, selected_top_k=selected_top_k)
        if target_weight <= 0:
            continue
        max_fill_weight = _max_fill_weight(
            row,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
        )
        filled_weight = min(target_weight, max_fill_weight)
        adjusted_return += filled_weight * _safe_float(row.get("net_excess_return"))
        residual_weight = max(target_weight - filled_weight, 0.0)
        if residual_weight <= 0:
            continue
        underfilled_rows.append(
            {
                "symbol": row.get("symbol"),
                "rank": row.get("rank"),
                "target_weight": target_weight,
                "filled_weight": filled_weight,
                "residual_weight": residual_weight,
                "net_excess_return": _safe_float(row.get("net_excess_return")),
                "avg_amount_20d": _safe_float(row.get("avg_amount_20d")),
            }
        )
        while residual_weight > 0 and candidate_index < len(fallback_candidates):
            candidate = fallback_candidates[candidate_index]
            candidate_index += 1
            symbol = str(candidate.get("symbol") or "")
            if not symbol or symbol in used_symbols:
                continue
            fill_weight = min(residual_weight, _safe_float(candidate.get("max_fill_weight")))
            if fill_weight <= 0:
                continue
            used_symbols.add(symbol)
            residual_weight -= fill_weight
            candidate_return = _safe_float(candidate.get("future_excess_return_20d"))
            adjusted_return += fill_weight * candidate_return
            fallback_rows.append(
                {
                    "symbol": candidate.get("symbol"),
                    "name": candidate.get("name"),
                    "filled_weight": fill_weight,
                    "future_excess_return_20d": candidate_return,
                    "avg_amount_20d": _safe_float(candidate.get("avg_amount_20d")),
                    "model_score": _safe_float(candidate.get("model_score")),
                }
            )
    return {
        "adjusted_net_excess_return": adjusted_return,
        "underfilled_rows": underfilled_rows,
        "fallback_rows": fallback_rows,
    }


def _trial_by_id(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    for trial in candidate_run.get("trial_diagnostics") or []:
        if trial.get("trial_id") == trial_id:
            return trial
    raise ValueError(f"trial_id not found in candidate run: {trial_id}")


def _underfilled_rows(
    rows: list[dict[str, Any]],
    *,
    selected_top_k: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        target_weight = _target_capital_weight(row, selected_top_k=selected_top_k)
        if target_weight <= 0:
            continue
        if _max_fill_weight(
            row,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
        ) < target_weight:
            result.append(row)
    return result


def _target_capital_weight(row: dict[str, Any], *, selected_top_k: int) -> float:
    return (
        _safe_float(row.get("portfolio_weight"), 1.0)
        * _safe_float(row.get("rank_weight_multiplier"), 1.0)
        / max(float(selected_top_k), 1.0)
    )


def _max_fill_weight(row: dict[str, Any], *, portfolio_notional_cny: float, max_adv_participation_rate: float) -> float:
    avg_amount_20d = _safe_float(row.get("avg_amount_20d"))
    return (
        avg_amount_20d * max_adv_participation_rate / portfolio_notional_cny
        if portfolio_notional_cny > 0 and avg_amount_20d > 0
        else 0.0
    )


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


def _interpretation(
    promising_variants: list[str],
    baseline_stats: dict[str, Any],
    variant_stats: dict[str, dict[str, Any]],
) -> str:
    if promising_variants:
        return (
            "At least one targeted underfilled-slot fallback preserves frontier mean, negative-month count, and path "
            "in this preflight. This justifies a formal candidate design review, not promotion."
        )
    best_name = max(variant_stats, key=lambda name: _safe_float(variant_stats[name].get("mean"))) if variant_stats else ""
    best_mean = variant_stats.get(best_name, {}).get("mean")
    return (
        f"No targeted underfilled-slot fallback preserves the current frontier. Best mean variant `{best_name}` "
        f"has mean `{best_mean}` versus frontier `{baseline_stats.get('mean')}`."
    )
