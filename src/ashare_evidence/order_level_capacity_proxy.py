from __future__ import annotations

from collections import defaultdict
from math import prod
from statistics import mean
from typing import Any

DEFAULT_PORTFOLIO_NOTIONAL_CNY = 1_000_000.0
DEFAULT_MAX_ADV_PARTICIPATION_RATE = 0.05
DEFAULT_MODES = (
    "adv_cap_cash",
    "adv_cap_rank_redistribute",
    "adv_cap_score_redistribute",
    "adv_cap_residual_top5_fill",
    "adv_cap_top5_substitute",
    "adv_cap_topn_capacity_aware_selection",
)
DEFAULT_SOFT_RERANK_LIQUIDITY_WEIGHTS = (0.02, 0.05, 0.1, 0.2, 0.4)
DEFAULT_EXPOSURE_FLOOR_QUANTILES = (0.02, 0.05, 0.1, 0.15, 0.2, 0.25)
DEFAULT_EXPOSURE_STABILITY_OVERLAY_MODES = ("cash_floor", "linear_scale", "sqrt_scale", "half_cash_scale")
DEFAULT_CAPACITY_CONTRACT_NOTIONAL_TIERS = (
    100_000.0,
    120_000.0,
    150_000.0,
    200_000.0,
    300_000.0,
    500_000.0,
    1_000_000.0,
)


def build_capacity_contract_tier_scan(
    selected_picks: list[dict[str, Any]],
    *,
    selected_top_k: int,
    notional_tiers_cny: tuple[float, ...] = DEFAULT_CAPACITY_CONTRACT_NOTIONAL_TIERS,
    max_adv_participation_rate: float = DEFAULT_MAX_ADV_PARTICIPATION_RATE,
) -> dict[str, Any]:
    """Scan capital tiers for the same selected strategy without changing picks or returns."""

    active_pick_count = sum(1 for row in selected_picks if _target_capital_weight(row, selected_top_k=selected_top_k) > 0)
    pick_limits = [
        _pick_full_fill_notional_limit(row, selected_top_k=selected_top_k, max_adv_participation_rate=max_adv_participation_rate)
        for row in selected_picks
        if _target_capital_weight(row, selected_top_k=selected_top_k) > 0
    ]
    valid_limits = [row for row in pick_limits if row["full_fill_notional_limit_cny"] is not None]
    full_fill_notional_limit = min(
        (row["full_fill_notional_limit_cny"] for row in valid_limits if row["full_fill_notional_limit_cny"] is not None),
        default=None,
    )
    sorted_tiers = tuple(sorted({float(value) for value in notional_tiers_cny if float(value) > 0}))
    tier_summaries = [
        _capacity_contract_tier_summary(
            selected_picks,
            selected_top_k=selected_top_k,
            portfolio_notional_cny=tier,
            max_adv_participation_rate=max_adv_participation_rate,
        )
        for tier in sorted_tiers
    ]
    first_full_fill_tier = next(
        (row["portfolio_notional_cny"] for row in tier_summaries if row["underfilled_pick_count"] == 0),
        None,
    )
    binding_picks_at_largest_tier: list[dict[str, Any]] = []
    if tier_summaries:
        largest_tier = max(sorted_tiers)
        binding_picks_at_largest_tier = _binding_picks(
            selected_picks,
            selected_top_k=selected_top_k,
            portfolio_notional_cny=largest_tier,
            max_adv_participation_rate=max_adv_participation_rate,
            limit=10,
        )
    return {
        "artifact_type": "capacity_contract_tier_scan",
        "diagnostic_scope": "selected_strategy_capital_contract_adv_fill_tiers",
        "claim_ceiling": "capacity_contract_diagnostic_only_no_model_replay_no_return_acceptance",
        "selected_pick_count": len(selected_picks),
        "active_pick_count": active_pick_count,
        "selected_top_k": selected_top_k,
        "max_adv_participation_rate": max_adv_participation_rate,
        "notional_tiers_cny": list(sorted_tiers),
        "full_fill_notional_limit_cny": full_fill_notional_limit,
        "first_scanned_full_fill_tier_cny": first_full_fill_tier,
        "tier_summaries": tier_summaries,
        "binding_picks_at_largest_tier": binding_picks_at_largest_tier,
        "interpretation": (
            "This scan estimates the product-capital contract supported by the already-selected strategy under "
            "a fixed ADV participation cap. It does not change model picks, substitute symbols, or prove a new "
            "return frontier."
        ),
    }


def build_order_level_capacity_proxy(
    selected_picks: list[dict[str, Any]],
    *,
    selected_top_k: int,
    selected_returns_by_date: list[dict[str, Any]] | None = None,
    top_candidate_picks: list[dict[str, Any]] | None = None,
    target_horizon_days: int = 20,
    portfolio_notional_cny: float = DEFAULT_PORTFOLIO_NOTIONAL_CNY,
    max_adv_participation_rate: float = DEFAULT_MAX_ADV_PARTICIPATION_RATE,
    modes: tuple[str, ...] = DEFAULT_MODES,
) -> dict[str, Any]:
    _validate_modes(modes)
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected_picks:
        as_of_date = str(row.get("as_of_date") or "")
        if as_of_date:
            by_date[as_of_date].append(row)
    top_candidates_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in top_candidate_picks or []:
        as_of_date = str(row.get("as_of_date") or "")
        if as_of_date:
            top_candidates_by_date[as_of_date].append(row)
    reference_returns_by_date = {
        str(row.get("as_of_date") or ""): row
        for row in selected_returns_by_date or []
        if isinstance(row, dict) and row.get("as_of_date")
    }
    mode_summaries = [
        _evaluate_mode(
            by_date,
            reference_returns_by_date=reference_returns_by_date,
            top_candidates_by_date=top_candidates_by_date,
            selected_top_k=selected_top_k,
            target_horizon_days=target_horizon_days,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
            mode=mode,
        )
        for mode in modes
    ]
    baseline = _evaluate_mode(
        by_date,
        reference_returns_by_date=reference_returns_by_date,
        top_candidates_by_date=top_candidates_by_date,
        selected_top_k=selected_top_k,
        target_horizon_days=target_horizon_days,
        portfolio_notional_cny=portfolio_notional_cny,
        max_adv_participation_rate=max_adv_participation_rate,
        mode="full_fill_reference",
    )
    return {
        "artifact_type": "order_level_capacity_proxy",
        "diagnostic_scope": "selected_pick_order_level_adv_fill_proxy",
        "selected_pick_count": len(selected_picks),
        "top_candidate_pick_count": len(top_candidate_picks or []),
        "candidate_inventory_scope": (
            "trial_diagnostic_top_candidate_picks" if top_candidate_picks else "selected_picks_only"
        ),
        "selected_top_k": selected_top_k,
        "date_count": len(set(by_date) | set(reference_returns_by_date)),
        "target_horizon_days": target_horizon_days,
        "portfolio_notional_cny": portfolio_notional_cny,
        "max_adv_participation_rate": max_adv_participation_rate,
        "baseline_full_fill_reference": baseline,
        "mode_summaries": mode_summaries,
        "non_degrading_modes": _non_degrading_modes(baseline, mode_summaries),
        "interpretation": (
            "This proxy applies pick-level 5pct ADV fill caps to already-selected picks. Unfilled capital is either "
            "left as cash or redistributed only within the same selected-date basket. It is a bounded execution "
            "diagnostic, not a new model promotion or production capacity clearance."
        ),
    }


def _capacity_contract_tier_summary(
    selected_picks: list[dict[str, Any]],
    *,
    selected_top_k: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
) -> dict[str, Any]:
    order_rows = [
        _order_row(
            row,
            selected_top_k=selected_top_k,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
        )
        for row in selected_picks
    ]
    active_rows = [row for row in order_rows if row["target_capital_weight"] > 0]
    fill_rates = [min(row["base_fill_rate"], 1.0) for row in active_rows]
    underfilled_rows = [row for row in active_rows if row["base_fill_rate"] < 1.0]
    return {
        "portfolio_notional_cny": portfolio_notional_cny,
        "active_pick_count": len(active_rows),
        "underfilled_pick_count": len(underfilled_rows),
        "full_fill_pick_rate": (len(active_rows) - len(underfilled_rows)) / len(active_rows) if active_rows else None,
        "min_fill_rate": min(fill_rates, default=None),
        "mean_fill_rate": mean(fill_rates) if fill_rates else None,
        "underfilled_dates": sorted({str(row.get("as_of_date") or "") for row in underfilled_rows if row.get("as_of_date")}),
        "underfilled_symbols": sorted({str(row.get("symbol") or "") for row in underfilled_rows if row.get("symbol")}),
    }


def _pick_full_fill_notional_limit(
    row: dict[str, Any],
    *,
    selected_top_k: int,
    max_adv_participation_rate: float,
) -> dict[str, Any]:
    target_weight = _target_capital_weight(row, selected_top_k=selected_top_k)
    avg_amount_20d = _safe_float(row.get("avg_amount_20d"))
    full_fill_notional_limit = (
        avg_amount_20d * max_adv_participation_rate / target_weight
        if target_weight > 0 and avg_amount_20d > 0
        else None
    )
    return {
        "as_of_date": row.get("as_of_date"),
        "symbol": row.get("symbol"),
        "rank": row.get("rank"),
        "avg_amount_20d": avg_amount_20d,
        "target_capital_weight": target_weight,
        "full_fill_notional_limit_cny": full_fill_notional_limit,
    }


def _binding_picks(
    selected_picks: list[dict[str, Any]],
    *,
    selected_top_k: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
    limit: int,
) -> list[dict[str, Any]]:
    rows = [
        _order_row(
            row,
            selected_top_k=selected_top_k,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
        )
        for row in selected_picks
    ]
    underfilled = [row for row in rows if row["target_capital_weight"] > 0 and row["base_fill_rate"] < 1.0]
    return [
        {
            "as_of_date": row.get("as_of_date"),
            "symbol": row.get("symbol"),
            "rank": row.get("rank"),
            "avg_amount_20d": row.get("avg_amount_20d"),
            "target_capital_weight": row.get("target_capital_weight"),
            "base_fill_rate": row.get("base_fill_rate"),
            "portfolio_notional_cny": portfolio_notional_cny,
            "net_excess_return": row.get("net_excess_return"),
            "score": row.get("score"),
        }
        for row in sorted(underfilled, key=lambda item: item["base_fill_rate"])[:limit]
    ]


def _target_capital_weight(row: dict[str, Any], *, selected_top_k: int) -> float:
    return (
        _safe_float(row.get("portfolio_weight"), 1.0)
        * _safe_float(row.get("rank_weight_multiplier"), 1.0)
        / max(float(selected_top_k), 1.0)
    )


def build_capacity_soft_rerank_proxy(
    selected_picks: list[dict[str, Any]],
    *,
    selected_top_k: int,
    top_candidate_picks: list[dict[str, Any]],
    selected_returns_by_date: list[dict[str, Any]] | None = None,
    target_horizon_days: int = 20,
    portfolio_notional_cny: float = DEFAULT_PORTFOLIO_NOTIONAL_CNY,
    max_adv_participation_rate: float = DEFAULT_MAX_ADV_PARTICIPATION_RATE,
    liquidity_weights: tuple[float, ...] = DEFAULT_SOFT_RERANK_LIQUIDITY_WEIGHTS,
) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected_picks:
        as_of_date = str(row.get("as_of_date") or "")
        if as_of_date:
            by_date[as_of_date].append(row)
    candidates_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in top_candidate_picks:
        as_of_date = str(row.get("as_of_date") or "")
        if as_of_date:
            candidates_by_date[as_of_date].append(row)
    reference_returns_by_date = {
        str(row.get("as_of_date") or ""): row
        for row in selected_returns_by_date or []
        if isinstance(row, dict) and row.get("as_of_date")
    }
    baseline = _evaluate_mode(
        by_date,
        reference_returns_by_date=reference_returns_by_date,
        top_candidates_by_date=candidates_by_date,
        selected_top_k=selected_top_k,
        target_horizon_days=target_horizon_days,
        portfolio_notional_cny=portfolio_notional_cny,
        max_adv_participation_rate=max_adv_participation_rate,
        mode="full_fill_reference",
    )
    scans = [
        _evaluate_soft_rerank(
            by_date=by_date,
            candidates_by_date=candidates_by_date,
            evaluation_dates=sorted(set(by_date) | set(reference_returns_by_date)),
            selected_top_k=selected_top_k,
            target_horizon_days=target_horizon_days,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
            liquidity_weight=liquidity_weight,
        )
        for liquidity_weight in liquidity_weights
    ]
    return {
        "artifact_type": "capacity_soft_rerank_proxy",
        "diagnostic_scope": "top_candidate_inventory_liquidity_capacity_soft_rerank",
        "selected_pick_count": len(selected_picks),
        "top_candidate_pick_count": len(top_candidate_picks),
        "selected_top_k": selected_top_k,
        "date_count": len(set(by_date) | set(reference_returns_by_date)),
        "target_horizon_days": target_horizon_days,
        "portfolio_notional_cny": portfolio_notional_cny,
        "max_adv_participation_rate": max_adv_participation_rate,
        "baseline_full_fill_reference": baseline,
        "scan_summaries": scans,
        "non_degrading_scans": _non_degrading_modes(baseline, scans),
        "interpretation": (
            "This proxy softly adds capacity to scoring over a bounded TopN candidate inventory. It is a "
            "pre-formal replay diagnostic and must not be treated as a promoted model or production capacity gate."
        ),
    }


def build_exposure_floor_stability_proxy(
    selected_returns_by_date: list[dict[str, Any]],
    *,
    target_horizon_days: int = 20,
    floor_quantiles: tuple[float, ...] = DEFAULT_EXPOSURE_FLOOR_QUANTILES,
    overlay_modes: tuple[str, ...] = DEFAULT_EXPOSURE_STABILITY_OVERLAY_MODES,
) -> dict[str, Any]:
    daily_rows = [
        {
            "as_of_date": str(row.get("as_of_date") or ""),
            "month": str(row.get("month") or str(row.get("as_of_date") or "")[:7]),
            "mean_net_excess_return": _safe_float(row.get("mean_net_excess_return")),
            "gross_exposure": _safe_float(row.get("gross_exposure")),
            "pick_count": int(_safe_float(row.get("pick_count"))),
        }
        for row in selected_returns_by_date
        if isinstance(row, dict) and row.get("as_of_date")
    ]
    active_gross_exposures = sorted(
        row["gross_exposure"] for row in daily_rows if row["pick_count"] > 0 and row["gross_exposure"] > 0
    )
    gross_exposure_floors = _quantile_candidates(active_gross_exposures, floor_quantiles)
    baseline = _evaluate_exposure_floor_overlay(
        daily_rows,
        gross_exposure_floor=0.0,
        target_horizon_days=target_horizon_days,
    )
    scans = [
        _evaluate_exposure_floor_overlay(
            daily_rows,
            gross_exposure_floor=floor,
            overlay_mode=overlay_mode,
            target_horizon_days=target_horizon_days,
        )
        for floor in gross_exposure_floors
        if floor > 0
        for overlay_mode in overlay_modes
    ]
    return {
        "artifact_type": "exposure_floor_stability_proxy",
        "diagnostic_scope": "selected_return_gross_exposure_floor_overlay",
        "date_count": len(daily_rows),
        "active_date_count": sum(1 for row in daily_rows if row["pick_count"] > 0),
        "target_horizon_days": target_horizon_days,
        "floor_quantiles": list(floor_quantiles),
        "gross_exposure_floors": gross_exposure_floors,
        "overlay_modes": list(overlay_modes),
        "baseline_full_exposure_reference": baseline,
        "scan_summaries": scans,
        "non_degrading_scans": _non_degrading_modes(baseline, scans),
        "interpretation": (
            "This proxy scans a date-level gross-exposure floor that leaves low-participation selected dates in cash. "
            "It is a stability diagnostic over an existing candidate, not a promoted model or final execution rule."
        ),
    }


def _evaluate_exposure_floor_overlay(
    daily_rows: list[dict[str, Any]],
    *,
    gross_exposure_floor: float,
    overlay_mode: str = "cash_floor",
    target_horizon_days: int,
) -> dict[str, Any]:
    overlay_rows: list[dict[str, Any]] = []
    gated_active_date_count = 0
    for row in daily_rows:
        is_low_exposure = row["pick_count"] > 0 and row["gross_exposure"] < gross_exposure_floor
        if is_low_exposure:
            gated_active_date_count += 1
        scale = _exposure_overlay_scale(
            gross_exposure=row["gross_exposure"],
            gross_exposure_floor=gross_exposure_floor,
            overlay_mode=overlay_mode,
        ) if is_low_exposure else 1.0
        overlay_rows.append(
            {
                "as_of_date": row["as_of_date"],
                "month": row["month"],
                "mean_net_excess_return": row["mean_net_excess_return"] * scale,
            }
        )
    returns = [row["mean_net_excess_return"] for row in overlay_rows]
    monthly = _monthly_summary(overlay_rows)
    curve = _rolling_sleeve_curve(returns, horizon_days=target_horizon_days)
    path_drawdown = _series_drawdown(returns)
    return {
        "mode": f"gross_exposure_{overlay_mode}_overlay",
        "gross_exposure_floor": gross_exposure_floor,
        "date_count": len(overlay_rows),
        "active_date_count": sum(1 for row in daily_rows if row["pick_count"] > 0),
        "low_exposure_active_date_count": gated_active_date_count,
        "gated_active_date_count": gated_active_date_count if overlay_mode == "cash_floor" else 0,
        "mean_daily_net_excess_return": mean(returns) if returns else None,
        "positive_date_rate": sum(1 for value in returns if value > 0) / len(returns) if returns else None,
        "horizon_normalized_total_return_proxy": curve["total_return"],
        "horizon_normalized_annualized_return_proxy": curve["annualized_return"],
        "horizon_normalized_max_drawdown_proxy": curve["max_drawdown"],
        "path_drawdown_sum": path_drawdown["max_drawdown_sum"],
        "negative_months": [row["month"] for row in monthly if row["mean_net_excess_return"] < 0],
        "negative_month_count": sum(1 for row in monthly if row["mean_net_excess_return"] < 0),
        "worst_monthly_mean": min((row["mean_net_excess_return"] for row in monthly), default=None),
    }


def _exposure_overlay_scale(
    *, gross_exposure: float, gross_exposure_floor: float, overlay_mode: str
) -> float:
    if overlay_mode == "cash_floor":
        return 0.0
    exposure_ratio = max(gross_exposure, 0.0) / max(gross_exposure_floor, 0.000001)
    if overlay_mode == "linear_scale":
        return exposure_ratio
    if overlay_mode == "sqrt_scale":
        return exposure_ratio**0.5
    if overlay_mode == "half_cash_scale":
        return 0.5 + 0.5 * exposure_ratio
    raise ValueError(f"unsupported exposure stability overlay mode: {overlay_mode}")


def _evaluate_soft_rerank(
    *,
    by_date: dict[str, list[dict[str, Any]]],
    candidates_by_date: dict[str, list[dict[str, Any]]],
    evaluation_dates: list[str],
    selected_top_k: int,
    target_horizon_days: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
    liquidity_weight: float,
) -> dict[str, Any]:
    daily_rows: list[dict[str, Any]] = []
    active_pick_count = 0
    underfilled_pick_count = 0
    changed_pick_count = 0
    for as_of_date in evaluation_dates:
        slot_rows = [
            _order_row(
                row,
                selected_top_k=selected_top_k,
                portfolio_notional_cny=portfolio_notional_cny,
                max_adv_participation_rate=max_adv_participation_rate,
            )
            for row in sorted(by_date[as_of_date], key=lambda item: _safe_float(item.get("rank")))
        ]
        active_slots = [row for row in slot_rows if row["target_capital_weight"] > 0]
        candidates = [
            _order_row(
                row,
                selected_top_k=selected_top_k,
                portfolio_notional_cny=portfolio_notional_cny,
                max_adv_participation_rate=max_adv_participation_rate,
            )
            for row in candidates_by_date.get(as_of_date, [])
        ]
        max_slot_weight = max((row["target_capital_weight"] for row in active_slots), default=0.0)
        ranked_candidates = sorted(
            candidates,
            key=lambda row: _soft_rerank_score(row, liquidity_weight=liquidity_weight, max_slot_weight=max_slot_weight),
            reverse=True,
        )
        used_symbols: set[str] = set()
        final_rows: list[dict[str, Any]] = []
        for slot in active_slots:
            chosen = None
            for candidate in ranked_candidates:
                symbol = str(candidate.get("symbol") or "")
                if symbol and symbol not in used_symbols:
                    chosen = dict(candidate)
                    break
            if chosen is None:
                chosen = dict(slot)
            used_symbols.add(str(chosen.get("symbol") or ""))
            chosen["target_capital_weight"] = slot["target_capital_weight"]
            chosen["final_capital_weight"] = min(slot["target_capital_weight"], chosen["max_fill_weight"])
            final_rows.append(chosen)
            if str(chosen.get("symbol") or "") != str(slot.get("symbol") or ""):
                changed_pick_count += 1
        active_pick_count += len(active_slots)
        underfilled_pick_count += sum(1 for row in final_rows if row["final_capital_weight"] < row["target_capital_weight"])
        daily_return = sum(row["net_excess_return"] * row["final_capital_weight"] for row in final_rows)
        daily_rows.append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "mean_net_excess_return": daily_return,
                "cash_weight": max(
                    sum(row["target_capital_weight"] for row in active_slots)
                    - sum(row["final_capital_weight"] for row in final_rows),
                    0.0,
                ),
                "final_capital_weight_sum": sum(row["final_capital_weight"] for row in final_rows),
            }
        )
    returns = [row["mean_net_excess_return"] for row in daily_rows]
    monthly = _monthly_summary(daily_rows)
    curve = _rolling_sleeve_curve(returns, horizon_days=target_horizon_days)
    path_drawdown = _series_drawdown(returns)
    return {
        "mode": "capacity_soft_rerank",
        "liquidity_weight": liquidity_weight,
        "date_count": len(daily_rows),
        "active_pick_count": active_pick_count,
        "base_underfilled_pick_count": underfilled_pick_count,
        "changed_pick_count": changed_pick_count,
        "mean_daily_net_excess_return": mean(returns) if returns else None,
        "positive_date_rate": sum(1 for value in returns if value > 0) / len(returns) if returns else None,
        "horizon_normalized_total_return_proxy": curve["total_return"],
        "horizon_normalized_annualized_return_proxy": curve["annualized_return"],
        "horizon_normalized_max_drawdown_proxy": curve["max_drawdown"],
        "path_drawdown_sum": path_drawdown["max_drawdown_sum"],
        "negative_months": [row["month"] for row in monthly if row["mean_net_excess_return"] < 0],
        "negative_month_count": sum(1 for row in monthly if row["mean_net_excess_return"] < 0),
        "worst_monthly_mean": min((row["mean_net_excess_return"] for row in monthly), default=None),
        "mean_cash_weight": mean([row["cash_weight"] for row in daily_rows]) if daily_rows else None,
        "mean_final_capital_weight": mean([row["final_capital_weight_sum"] for row in daily_rows])
        if daily_rows
        else None,
    }


def _soft_rerank_score(row: dict[str, Any], *, liquidity_weight: float, max_slot_weight: float) -> float:
    fill_capacity_score = min(row["max_fill_weight"] / max(max_slot_weight, 0.000001), 2.0)
    return row["score"] + liquidity_weight * fill_capacity_score


def _evaluate_mode(
    by_date: dict[str, list[dict[str, Any]]],
    *,
    reference_returns_by_date: dict[str, dict[str, Any]],
    top_candidates_by_date: dict[str, list[dict[str, Any]]],
    selected_top_k: int,
    target_horizon_days: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
    mode: str,
) -> dict[str, Any]:
    daily_rows: list[dict[str, Any]] = []
    underfilled_pick_count = 0
    total_active_pick_count = 0
    missing_avg_amount_count = 0
    substituted_pick_count = 0
    for as_of_date in sorted(set(by_date) | set(reference_returns_by_date)):
        rows = by_date.get(as_of_date, [])
        reference_row = reference_returns_by_date.get(as_of_date) or {}
        order_rows = [
            _order_row(
                row,
                selected_top_k=selected_top_k,
                portfolio_notional_cny=portfolio_notional_cny,
                max_adv_participation_rate=max_adv_participation_rate,
            )
            for row in rows
        ]
        active_rows = [row for row in order_rows if row["target_capital_weight"] > 0]
        candidate_rows = [
            _order_row(
                row,
                selected_top_k=selected_top_k,
                portfolio_notional_cny=portfolio_notional_cny,
                max_adv_participation_rate=max_adv_participation_rate,
            )
            for row in top_candidates_by_date.get(as_of_date, [])
        ]
        total_active_pick_count += len(active_rows)
        missing_avg_amount_count += sum(1 for row in active_rows if row["avg_amount_20d"] <= 0)
        underfilled_pick_count += sum(1 for row in active_rows if row["base_fill_rate"] < 1.0)
        final_rows, daily_substitutions = _allocate_mode(active_rows, mode=mode, candidate_rows=candidate_rows)
        substituted_pick_count += daily_substitutions
        daily_return = (
            _safe_float(reference_row.get("mean_net_excess_return"))
            if mode == "full_fill_reference" and reference_row
            else sum(row["net_excess_return"] * row["final_capital_weight"] for row in final_rows)
        )
        daily_rows.append(
            {
                "as_of_date": as_of_date,
                "month": as_of_date[:7],
                "mean_net_excess_return": daily_return,
                "target_capital_weight_sum": sum(row["target_capital_weight"] for row in active_rows),
                "final_capital_weight_sum": sum(row["final_capital_weight"] for row in final_rows),
                "cash_weight": max(
                    sum(row["target_capital_weight"] for row in active_rows)
                    - sum(row["final_capital_weight"] for row in final_rows),
                    0.0,
                ),
                "underfilled_pick_count": sum(1 for row in active_rows if row["base_fill_rate"] < 1.0),
            }
        )
    returns = [row["mean_net_excess_return"] for row in daily_rows]
    monthly = _monthly_summary(daily_rows)
    curve = _rolling_sleeve_curve(returns, horizon_days=target_horizon_days)
    path_drawdown = _series_drawdown(returns)
    return {
        "mode": mode,
        "date_count": len(daily_rows),
        "active_pick_count": total_active_pick_count,
        "missing_avg_amount_20d_count": missing_avg_amount_count,
        "base_underfilled_pick_count": underfilled_pick_count,
        "substituted_pick_count": substituted_pick_count,
        "mean_daily_net_excess_return": mean(returns) if returns else None,
        "positive_date_rate": sum(1 for value in returns if value > 0) / len(returns) if returns else None,
        "horizon_normalized_total_return_proxy": curve["total_return"],
        "horizon_normalized_annualized_return_proxy": curve["annualized_return"],
        "horizon_normalized_max_drawdown_proxy": curve["max_drawdown"],
        "path_drawdown_sum": path_drawdown["max_drawdown_sum"],
        "negative_months": [row["month"] for row in monthly if row["mean_net_excess_return"] < 0],
        "negative_month_count": sum(1 for row in monthly if row["mean_net_excess_return"] < 0),
        "worst_monthly_mean": min((row["mean_net_excess_return"] for row in monthly), default=None),
        "mean_cash_weight": mean([row["cash_weight"] for row in daily_rows]) if daily_rows else None,
        "mean_final_capital_weight": mean([row["final_capital_weight_sum"] for row in daily_rows])
        if daily_rows
        else None,
    }


def _order_row(
    row: dict[str, Any],
    *,
    selected_top_k: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
) -> dict[str, Any]:
    target_capital_weight = (
        _safe_float(row.get("portfolio_weight"), 1.0)
        * _safe_float(row.get("rank_weight_multiplier"), 1.0)
        / max(float(selected_top_k), 1.0)
    )
    avg_amount_20d = _safe_float(row.get("avg_amount_20d"))
    max_fill_weight = (
        avg_amount_20d * max_adv_participation_rate / portfolio_notional_cny
        if portfolio_notional_cny > 0 and avg_amount_20d > 0
        else 0.0
    )
    base_filled_weight = min(target_capital_weight, max_fill_weight)
    return {
        "as_of_date": row.get("as_of_date"),
        "symbol": row.get("symbol"),
        "rank": int(_safe_float(row.get("rank"), 999999.0)),
        "score": _safe_float(row.get("score")),
        "net_excess_return": _safe_float(row.get("net_excess_return")),
        "avg_amount_20d": avg_amount_20d,
        "target_capital_weight": target_capital_weight,
        "max_fill_weight": max_fill_weight,
        "base_filled_weight": base_filled_weight,
        "base_fill_rate": base_filled_weight / target_capital_weight if target_capital_weight > 0 else 1.0,
        "final_capital_weight": target_capital_weight,
    }


def _allocate_mode(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    allocated = [dict(row) for row in rows]
    if mode == "full_fill_reference":
        for row in allocated:
            row["final_capital_weight"] = row["target_capital_weight"]
        return allocated, 0
    if mode == "adv_cap_residual_top5_fill":
        return _allocate_residual_top5_fill(allocated, candidate_rows)
    if mode == "adv_cap_top5_substitute":
        return _allocate_top5_substitutes(allocated, candidate_rows)
    if mode == "adv_cap_topn_capacity_aware_selection":
        return _allocate_capacity_aware_selection(allocated, candidate_rows)
    for row in allocated:
        row["final_capital_weight"] = row["base_filled_weight"]
    if mode == "adv_cap_cash":
        return allocated, 0

    leftover = sum(row["target_capital_weight"] for row in allocated) - sum(
        row["final_capital_weight"] for row in allocated
    )
    if leftover <= 0:
        return allocated, 0
    if mode == "adv_cap_rank_redistribute":
        candidates = sorted(allocated, key=lambda row: row["rank"])
    elif mode == "adv_cap_score_redistribute":
        candidates = sorted(allocated, key=lambda row: row["score"], reverse=True)
    else:
        raise ValueError(f"unsupported order-level capacity proxy mode: {mode}")
    for row in candidates:
        spare = max(row["max_fill_weight"] - row["final_capital_weight"], 0.0)
        if spare <= 0:
            continue
        add_weight = min(spare, leftover)
        row["final_capital_weight"] += add_weight
        leftover -= add_weight
        if leftover <= 0:
            break
    return allocated, 0


def _allocate_top5_substitutes(
    selected_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    used_symbols = {str(row.get("symbol") or "") for row in selected_rows}
    substitutes = sorted(
        [dict(row) for row in candidate_rows if str(row.get("symbol") or "") not in used_symbols],
        key=lambda row: row["rank"],
    )
    final_rows: list[dict[str, Any]] = []
    substituted_count = 0
    substitute_index = 0
    for row in selected_rows:
        if row["base_fill_rate"] >= 1.0:
            row["final_capital_weight"] = row["target_capital_weight"]
            final_rows.append(row)
            continue
        while (
            substitute_index < len(substitutes)
            and (
                str(substitutes[substitute_index].get("symbol") or "") in used_symbols
                or substitutes[substitute_index]["max_fill_weight"] < row["target_capital_weight"]
            )
        ):
            substitute_index += 1
        if substitute_index < len(substitutes):
            substitute = substitutes[substitute_index]
            substitute_index += 1
            used_symbols.add(str(substitute.get("symbol") or ""))
            substitute["target_capital_weight"] = row["target_capital_weight"]
            substitute["final_capital_weight"] = row["target_capital_weight"]
            final_rows.append(substitute)
            substituted_count += 1
        else:
            row["final_capital_weight"] = row["base_filled_weight"]
            final_rows.append(row)
    return final_rows, substituted_count


def _allocate_residual_top5_fill(
    selected_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    used_symbols = {str(row.get("symbol") or "") for row in selected_rows}
    residual_candidates = sorted(
        [dict(row) for row in candidate_rows if str(row.get("symbol") or "") not in used_symbols],
        key=lambda row: row["rank"],
    )
    final_rows = [dict(row) for row in selected_rows]
    for row in final_rows:
        row["final_capital_weight"] = row["base_filled_weight"]

    candidate_index = 0
    added_count = 0
    for row in sorted(final_rows, key=lambda item: item["rank"]):
        residual_weight = max(row["target_capital_weight"] - row["final_capital_weight"], 0.0)
        while residual_weight > 0 and candidate_index < len(residual_candidates):
            candidate = residual_candidates[candidate_index]
            candidate_index += 1
            symbol = str(candidate.get("symbol") or "")
            if not symbol or symbol in used_symbols:
                continue
            fill_weight = min(residual_weight, candidate["max_fill_weight"])
            if fill_weight <= 0:
                continue
            used_symbols.add(symbol)
            candidate["target_capital_weight"] = fill_weight
            candidate["final_capital_weight"] = fill_weight
            final_rows.append(candidate)
            residual_weight -= fill_weight
            added_count += 1
    return final_rows, added_count


def _allocate_capacity_aware_selection(
    selected_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    slots = sorted(selected_rows, key=lambda row: row["rank"])
    candidates = sorted([dict(row) for row in candidate_rows], key=lambda row: row["rank"])
    used_symbols: set[str] = set()
    final_rows: list[dict[str, Any]] = []
    changed_count = 0
    for slot in slots:
        chosen: dict[str, Any] | None = None
        for candidate in candidates:
            symbol = str(candidate.get("symbol") or "")
            if not symbol or symbol in used_symbols:
                continue
            if candidate["max_fill_weight"] < slot["target_capital_weight"]:
                continue
            chosen = dict(candidate)
            break
        if chosen is None:
            slot["final_capital_weight"] = slot["base_filled_weight"]
            final_rows.append(slot)
            continue
        used_symbols.add(str(chosen.get("symbol") or ""))
        chosen["target_capital_weight"] = slot["target_capital_weight"]
        chosen["final_capital_weight"] = slot["target_capital_weight"]
        final_rows.append(chosen)
        if str(chosen.get("symbol") or "") != str(slot.get("symbol") or ""):
            changed_count += 1
    return final_rows, changed_count


def _validate_modes(modes: tuple[str, ...]) -> None:
    supported = {
        "adv_cap_cash",
        "adv_cap_rank_redistribute",
        "adv_cap_score_redistribute",
        "adv_cap_residual_top5_fill",
        "adv_cap_top5_substitute",
        "adv_cap_topn_capacity_aware_selection",
    }
    unsupported = sorted(set(modes) - supported)
    if unsupported:
        raise ValueError(f"unsupported order-level capacity proxy mode: {unsupported[0]}")


def _non_degrading_modes(baseline: dict[str, Any], modes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_total = _safe_float(baseline.get("horizon_normalized_total_return_proxy"))
    baseline_max_drawdown = _safe_float(baseline.get("horizon_normalized_max_drawdown_proxy"))
    baseline_negative_months = int(_safe_float(baseline.get("negative_month_count")))
    baseline_worst_month = _safe_float(baseline.get("worst_monthly_mean"))
    baseline_positive_date_rate = _safe_float(baseline.get("positive_date_rate"))
    baseline_path_drawdown = _safe_float(baseline.get("path_drawdown_sum"))
    accepted = []
    for mode in modes:
        if (
            _safe_float(mode.get("horizon_normalized_total_return_proxy")) >= baseline_total
            and _safe_float(mode.get("horizon_normalized_max_drawdown_proxy")) >= baseline_max_drawdown
            and _safe_float(mode.get("path_drawdown_sum")) >= baseline_path_drawdown
            and _safe_float(mode.get("positive_date_rate")) >= baseline_positive_date_rate
            and int(_safe_float(mode.get("negative_month_count"))) <= baseline_negative_months
            and _safe_float(mode.get("worst_monthly_mean")) >= baseline_worst_month
        ):
            summary = {
                "mode": mode.get("mode"),
                "mean_daily_net_excess_return": mode.get("mean_daily_net_excess_return"),
                "horizon_normalized_total_return_proxy": mode.get("horizon_normalized_total_return_proxy"),
                "horizon_normalized_annualized_return_proxy": mode.get("horizon_normalized_annualized_return_proxy"),
                "horizon_normalized_max_drawdown_proxy": mode.get("horizon_normalized_max_drawdown_proxy"),
                "path_drawdown_sum": mode.get("path_drawdown_sum"),
                "positive_date_rate": mode.get("positive_date_rate"),
                "negative_month_count": mode.get("negative_month_count"),
                "worst_monthly_mean": mode.get("worst_monthly_mean"),
            }
            if "liquidity_weight" in mode:
                summary["liquidity_weight"] = mode.get("liquidity_weight")
            if "gross_exposure_floor" in mode:
                summary["gross_exposure_floor"] = mode.get("gross_exposure_floor")
                summary["gated_active_date_count"] = mode.get("gated_active_date_count")
                summary["low_exposure_active_date_count"] = mode.get("low_exposure_active_date_count")
            for optional_field in (
                "entry_days",
                "exit_policy",
                "exposure_overlay_mode",
                "full_fill_repaired_pick_count",
                "min_staggered_fill_rate",
                "mean_staggered_fill_rate",
            ):
                if optional_field in mode:
                    summary[optional_field] = mode.get(optional_field)
            accepted.append(summary)
    return accepted


def _monthly_summary(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month: dict[str, list[float]] = defaultdict(list)
    for row in daily_rows:
        by_month[str(row["month"])].append(_safe_float(row.get("mean_net_excess_return")))
    return [
        {
            "month": month,
            "date_count": len(values),
            "mean_net_excess_return": mean(values),
        }
        for month, values in sorted(by_month.items())
        if values
    ]


def _compound_return(returns: list[float]) -> float | None:
    if not returns:
        return None
    return prod(1.0 + value for value in returns) - 1.0


def _rolling_sleeve_curve(returns: list[float], *, horizon_days: int) -> dict[str, float | None]:
    normalized = [value / max(float(horizon_days), 1.0) for value in returns]
    total_return = _compound_return(normalized)
    max_drawdown = _max_drawdown(normalized)
    annualized = None
    if total_return is not None and returns and total_return > -1.0:
        annualized = (1.0 + total_return) ** (252.0 / len(returns)) - 1.0
    return {
        "total_return": total_return,
        "annualized_return": annualized,
        "max_drawdown": max_drawdown,
    }


def _max_drawdown(returns: list[float]) -> float | None:
    if not returns:
        return None
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1.0)
    return max_drawdown


def _series_drawdown(values: list[float]) -> dict[str, float]:
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


def _quantile_candidates(values: list[float], quantiles: tuple[float, ...]) -> list[float]:
    if not values:
        return []
    candidates = []
    for quantile in quantiles:
        clamped = min(max(float(quantile), 0.0), 1.0)
        index = int(clamped * (len(values) - 1))
        candidates.append(values[index])
    return sorted(set(candidates))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
