from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.order_level_capacity_proxy import (
    DEFAULT_MAX_ADV_PARTICIPATION_RATE,
    DEFAULT_PORTFOLIO_NOTIONAL_CNY,
    _exposure_overlay_scale,
    _monthly_summary,
    _non_degrading_modes,
    _rolling_sleeve_curve,
    _safe_float,
    _series_drawdown,
    _target_capital_weight,
)


CAPACITY_STAGGERED_ENTRY_PROXY_VERSION = "capacity_staggered_entry_proxy.v1"
DEFAULT_ENTRY_DAY_OPTIONS = (1, 3, 5, 10, 15, 20)
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"
SUPPORTED_EXIT_POLICIES = ("original_exit", "per_tranche_horizon")
DEFAULT_EXIT_POLICIES = ("original_exit",)
SUPPORTED_EXPOSURE_OVERLAY_MODES = ("none", "linear_scale", "sqrt_scale", "half_cash_scale")
DEFAULT_EXPOSURE_OVERLAY_MODES = ("none",)


def build_capacity_staggered_entry_proxy(
    session: Session,
    *,
    candidate_run: dict[str, Any],
    trial_id: str,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    entry_day_options: tuple[int, ...] = DEFAULT_ENTRY_DAY_OPTIONS,
    exit_policies: tuple[str, ...] = DEFAULT_EXIT_POLICIES,
    exposure_overlay_modes: tuple[str, ...] = DEFAULT_EXPOSURE_OVERLAY_MODES,
    gross_exposure_floors: tuple[float, ...] = (),
    portfolio_notional_cny: float = DEFAULT_PORTFOLIO_NOTIONAL_CNY,
    max_adv_participation_rate: float = DEFAULT_MAX_ADV_PARTICIPATION_RATE,
) -> dict[str, Any]:
    trial = _find_trial(candidate_run, trial_id)
    selected_top_k = int(trial.get("selected_top_k") or 1)
    target_horizon_days = int(trial.get("target_horizon_days") or 20)
    selected_picks = list(trial.get("selected_top_k_picks_by_date") or [])
    selected_returns_by_date = list(trial.get("selected_top_k_returns_by_date") or [])
    baseline = _evaluate_return_rows(selected_returns_by_date, target_horizon_days=target_horizon_days)
    underfilled = [
        row for row in selected_picks
        if _is_underfilled_pick(
            row,
            selected_top_k=selected_top_k,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
        )
    ]
    histories = _histories_for_underfilled(session, underfilled, benchmark_symbol=benchmark_symbol)
    scanned_exit_policies = _normalize_exit_policies(exit_policies)
    scanned_exposure_overlays = _normalize_exposure_overlay_scans(exposure_overlay_modes, gross_exposure_floors)
    scans = [
        _evaluate_staggered_entry_option(
            selected_returns_by_date,
            underfilled,
            histories=histories,
            selected_top_k=selected_top_k,
            target_horizon_days=target_horizon_days,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
            entry_days=entry_days,
            exit_policy=exit_policy,
            exposure_overlay_mode=exposure_overlay["mode"],
            gross_exposure_floor=exposure_overlay["gross_exposure_floor"],
            benchmark_symbol=benchmark_symbol,
        )
        for entry_days in sorted({int(value) for value in entry_day_options if int(value) > 0})
        for exit_policy in scanned_exit_policies
        for exposure_overlay in scanned_exposure_overlays
    ]
    return {
        "artifact_type": "capacity_staggered_entry_proxy",
        "schema_version": CAPACITY_STAGGERED_ENTRY_PROXY_VERSION,
        "diagnostic_scope": "underfilled_selected_pick_staggered_entry_execution_proxy",
        "claim_ceiling": "execution_proxy_only_no_model_replay_no_promotion",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "trial_id": trial_id,
        "selected_top_k": selected_top_k,
        "target_horizon_days": target_horizon_days,
        "portfolio_notional_cny": portfolio_notional_cny,
        "max_adv_participation_rate": max_adv_participation_rate,
        "exit_policies": scanned_exit_policies,
        "exposure_overlay_scans": scanned_exposure_overlays,
        "benchmark_symbol": benchmark_symbol,
        "underfilled_pick_count": len(underfilled),
        "underfilled_picks": [_compact_underfilled_pick(row, selected_top_k=selected_top_k) for row in underfilled],
        "baseline_full_fill_reference": baseline,
        "scan_summaries": scans,
        "non_degrading_scans": _non_degrading_modes(baseline, scans),
        "interpretation": (
            "This proxy tests whether underfilled selected picks can be accumulated over later trading days under "
            "a fixed ADV participation cap while preserving the original signal-date portfolio accounting. It is "
            "an execution diagnostic only; it does not change model selection or prove production capacity."
        ),
    }


def write_capacity_staggered_entry_proxy(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _normalize_exit_policies(exit_policies: tuple[str, ...]) -> tuple[str, ...]:
    policies = tuple(dict.fromkeys(str(value) for value in exit_policies if str(value)))
    unsupported = [value for value in policies if value not in SUPPORTED_EXIT_POLICIES]
    if unsupported:
        raise ValueError(f"unsupported exit_policy values: {unsupported}; supported={SUPPORTED_EXIT_POLICIES}")
    return policies or DEFAULT_EXIT_POLICIES


def _normalize_exposure_overlay_scans(
    exposure_overlay_modes: tuple[str, ...],
    gross_exposure_floors: tuple[float, ...],
) -> list[dict[str, Any]]:
    modes = tuple(dict.fromkeys(str(value) for value in exposure_overlay_modes if str(value)))
    unsupported = [value for value in modes if value not in SUPPORTED_EXPOSURE_OVERLAY_MODES]
    if unsupported:
        raise ValueError(
            f"unsupported exposure_overlay_mode values: {unsupported}; supported={SUPPORTED_EXPOSURE_OVERLAY_MODES}"
        )
    normalized_modes = modes or DEFAULT_EXPOSURE_OVERLAY_MODES
    floors = tuple(sorted({float(value) for value in gross_exposure_floors if float(value) > 0}))
    scans: list[dict[str, Any]] = []
    for mode in normalized_modes:
        if mode == "none":
            scans.append({"mode": "none", "gross_exposure_floor": None})
        else:
            if not floors:
                raise ValueError("gross_exposure_floors are required when exposure overlay mode is enabled")
            scans.extend({"mode": mode, "gross_exposure_floor": floor} for floor in floors)
    return scans


def _find_trial(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    trial = next((row for row in candidate_run.get("trial_diagnostics") or [] if row.get("trial_id") == trial_id), None)
    if not isinstance(trial, dict):
        raise ValueError(f"trial_id not found in candidate run: {trial_id}")
    return trial


def _is_underfilled_pick(
    row: dict[str, Any],
    *,
    selected_top_k: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
) -> bool:
    target_weight = _target_capital_weight(row, selected_top_k=selected_top_k)
    if target_weight <= 0:
        return False
    avg_amount_20d = _safe_float(row.get("avg_amount_20d"))
    target_notional = portfolio_notional_cny * target_weight
    return avg_amount_20d * max_adv_participation_rate < target_notional


def _histories_for_underfilled(
    session: Session,
    underfilled: list[dict[str, Any]],
    *,
    benchmark_symbol: str,
) -> dict[str, list[dict[str, Any]]]:
    symbols = {str(row.get("symbol") or "") for row in underfilled if row.get("symbol")}
    symbols.add(benchmark_symbol)
    as_of_dates = [date.fromisoformat(str(row["as_of_date"])) for row in underfilled if row.get("as_of_date")]
    if not symbols or not as_of_dates:
        return {}
    start = min(as_of_dates) - timedelta(days=5)
    end = max(as_of_dates) + timedelta(days=80)
    rows = session.execute(
        select(
            Stock.symbol,
            MarketBar.observed_at,
            MarketBar.close_price,
            MarketBar.amount,
        )
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(
            Stock.symbol.in_(symbols),
            MarketBar.timeframe == "1d",
            MarketBar.observed_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            MarketBar.observed_at <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
        )
        .order_by(Stock.symbol, MarketBar.observed_at)
    ).mappings()
    histories: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        histories.setdefault(str(row["symbol"]), []).append(dict(row))
    return histories


def _evaluate_staggered_entry_option(
    selected_returns_by_date: list[dict[str, Any]],
    underfilled: list[dict[str, Any]],
    *,
    histories: dict[str, list[dict[str, Any]]],
    selected_top_k: int,
    target_horizon_days: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
    entry_days: int,
    exit_policy: str,
    exposure_overlay_mode: str,
    gross_exposure_floor: float | None,
    benchmark_symbol: str,
) -> dict[str, Any]:
    replacements_by_date: dict[str, list[dict[str, Any]]] = {}
    fill_details = []
    for pick in underfilled:
        replacement = _staggered_pick_replacement(
            pick,
            histories=histories,
            selected_top_k=selected_top_k,
            target_horizon_days=target_horizon_days,
            portfolio_notional_cny=portfolio_notional_cny,
            max_adv_participation_rate=max_adv_participation_rate,
            entry_days=entry_days,
            exit_policy=exit_policy,
            benchmark_symbol=benchmark_symbol,
        )
        replacements_by_date.setdefault(str(pick.get("as_of_date")), []).append(replacement)
        fill_details.append(replacement)

    adjusted_rows = []
    for row in selected_returns_by_date:
        as_of_date = str(row.get("as_of_date") or "")
        base_return = _safe_float(row.get("mean_net_excess_return"))
        adjusted_return = base_return
        for replacement in replacements_by_date.get(as_of_date, []):
            adjusted_return = adjusted_return - replacement["baseline_contribution"] + replacement["staggered_contribution"]
        adjusted_rows.append(
            _apply_exposure_overlay(
                {**row, "mean_net_excess_return": adjusted_return},
                exposure_overlay_mode=exposure_overlay_mode,
                gross_exposure_floor=gross_exposure_floor,
            )
        )
    summary = _evaluate_return_rows(adjusted_rows, target_horizon_days=target_horizon_days)
    low_exposure_active_date_count = sum(1 for row in adjusted_rows if row.get("exposure_overlay_applied"))
    mode_suffix = (
        f":exposure_{exposure_overlay_mode}_{gross_exposure_floor:.6f}"
        if exposure_overlay_mode != "none" and gross_exposure_floor is not None
        else ""
    )
    summary.update(
        {
            "mode": f"staggered_entry_adv_cap:{exit_policy}{mode_suffix}",
            "entry_days": entry_days,
            "exit_policy": exit_policy,
            "exposure_overlay_mode": exposure_overlay_mode,
            "gross_exposure_floor": gross_exposure_floor,
            "low_exposure_active_date_count": low_exposure_active_date_count,
            "underfilled_pick_count": len(underfilled),
            "full_fill_repaired_pick_count": sum(1 for row in fill_details if row["staggered_fill_rate"] >= 0.999999),
            "mean_staggered_fill_rate": sum(row["staggered_fill_rate"] for row in fill_details) / len(fill_details)
            if fill_details
            else None,
            "min_staggered_fill_rate": min((row["staggered_fill_rate"] for row in fill_details), default=None),
            "fill_details": fill_details,
        }
    )
    return summary


def _apply_exposure_overlay(
    row: dict[str, Any],
    *,
    exposure_overlay_mode: str,
    gross_exposure_floor: float | None,
) -> dict[str, Any]:
    if exposure_overlay_mode == "none" or gross_exposure_floor is None:
        return row
    gross_exposure = _safe_float(row.get("gross_exposure"))
    pick_count = int(_safe_float(row.get("pick_count")))
    is_low_exposure = pick_count > 0 and gross_exposure < gross_exposure_floor
    if not is_low_exposure:
        return {
            **row,
            "exposure_overlay_mode": exposure_overlay_mode,
            "exposure_overlay_floor": gross_exposure_floor,
            "exposure_overlay_scale": 1.0,
            "exposure_overlay_applied": False,
        }
    scale = _exposure_overlay_scale(
        gross_exposure=gross_exposure,
        gross_exposure_floor=gross_exposure_floor,
        overlay_mode=exposure_overlay_mode,
    )
    return {
        **row,
        "pre_exposure_overlay_mean_net_excess_return": _safe_float(row.get("mean_net_excess_return")),
        "mean_net_excess_return": _safe_float(row.get("mean_net_excess_return")) * scale,
        "exposure_overlay_mode": exposure_overlay_mode,
        "exposure_overlay_floor": gross_exposure_floor,
        "exposure_overlay_scale": scale,
        "exposure_overlay_applied": True,
    }


def _staggered_pick_replacement(
    pick: dict[str, Any],
    *,
    histories: dict[str, list[dict[str, Any]]],
    selected_top_k: int,
    target_horizon_days: int,
    portfolio_notional_cny: float,
    max_adv_participation_rate: float,
    entry_days: int,
    exit_policy: str,
    benchmark_symbol: str,
) -> dict[str, Any]:
    if exit_policy not in SUPPORTED_EXIT_POLICIES:
        raise ValueError(f"unsupported exit_policy: {exit_policy}")
    symbol = str(pick.get("symbol") or "")
    as_of_date = date.fromisoformat(str(pick["as_of_date"]))
    symbol_rows = histories.get(symbol) or []
    benchmark_rows = histories.get(benchmark_symbol) or []
    symbol_idx = _row_index(symbol_rows, as_of_date)
    benchmark_idx = _row_index(benchmark_rows, as_of_date)
    target_weight = _target_capital_weight(pick, selected_top_k=selected_top_k)
    target_notional = portfolio_notional_cny * target_weight
    baseline_contribution = _safe_float(pick.get("net_excess_return")) * target_weight
    if symbol_idx is None or benchmark_idx is None:
        return _missing_replacement(pick, target_weight, baseline_contribution, "missing_entry_bar")
    original_exit_symbol_idx = symbol_idx + target_horizon_days
    original_exit_benchmark_idx = benchmark_idx + target_horizon_days
    if original_exit_symbol_idx >= len(symbol_rows) or original_exit_benchmark_idx >= len(benchmark_rows):
        return _missing_replacement(pick, target_weight, baseline_contribution, "missing_exit_bar")
    remaining_notional = target_notional
    staggered_contribution = 0.0
    entry_fills = []
    for offset in range(min(entry_days, target_horizon_days + 1)):
        current_symbol_idx = symbol_idx + offset
        current_benchmark_idx = benchmark_idx + offset
        if current_symbol_idx >= len(symbol_rows) or current_benchmark_idx >= len(benchmark_rows) or remaining_notional <= 0:
            break
        entry_symbol_close = _safe_float(symbol_rows[current_symbol_idx].get("close_price"))
        entry_benchmark_close = _safe_float(benchmark_rows[current_benchmark_idx].get("close_price"))
        exit_symbol_idx, exit_benchmark_idx = _exit_indices_for_fill(
            exit_policy=exit_policy,
            original_symbol_idx=symbol_idx,
            original_benchmark_idx=benchmark_idx,
            current_symbol_idx=current_symbol_idx,
            current_benchmark_idx=current_benchmark_idx,
            target_horizon_days=target_horizon_days,
        )
        if exit_symbol_idx >= len(symbol_rows) or exit_benchmark_idx >= len(benchmark_rows):
            break
        exit_symbol_close = _safe_float(symbol_rows[exit_symbol_idx].get("close_price"))
        exit_benchmark_close = _safe_float(benchmark_rows[exit_benchmark_idx].get("close_price"))
        day_amount = _safe_float(symbol_rows[current_symbol_idx].get("amount"))
        fill_notional = min(remaining_notional, day_amount * max_adv_participation_rate)
        if fill_notional <= 0 or entry_symbol_close <= 0 or entry_benchmark_close <= 0:
            continue
        fill_weight = fill_notional / portfolio_notional_cny
        stock_return = exit_symbol_close / entry_symbol_close - 1.0
        benchmark_return = exit_benchmark_close / entry_benchmark_close - 1.0
        net_excess = stock_return - benchmark_return
        staggered_contribution += fill_weight * net_excess
        remaining_notional -= fill_notional
        entry_fills.append(
            {
                "entry_date": _row_date(symbol_rows[current_symbol_idx]),
                "fill_notional_cny": fill_notional,
                "fill_weight": fill_weight,
                "entry_close": entry_symbol_close,
                "exit_date": _row_date(symbol_rows[exit_symbol_idx]),
                "exit_close": exit_symbol_close,
                "day_amount": day_amount,
                "net_excess": net_excess,
            }
        )
    filled_notional = target_notional - remaining_notional
    return {
        "as_of_date": pick.get("as_of_date"),
        "symbol": symbol,
        "rank": pick.get("rank"),
        "target_weight": target_weight,
        "target_notional_cny": target_notional,
        "baseline_net_excess_return": _safe_float(pick.get("net_excess_return")),
        "baseline_contribution": baseline_contribution,
        "staggered_contribution": staggered_contribution,
        "staggered_fill_rate": filled_notional / max(target_notional, 0.000001),
        "unfilled_notional_cny": remaining_notional,
        "exit_policy": exit_policy,
        "original_exit_date": _row_date(symbol_rows[original_exit_symbol_idx]),
        "last_exit_date": entry_fills[-1]["exit_date"] if entry_fills else None,
        "entry_fills": entry_fills,
    }


def _exit_indices_for_fill(
    *,
    exit_policy: str,
    original_symbol_idx: int,
    original_benchmark_idx: int,
    current_symbol_idx: int,
    current_benchmark_idx: int,
    target_horizon_days: int,
) -> tuple[int, int]:
    if exit_policy == "original_exit":
        return original_symbol_idx + target_horizon_days, original_benchmark_idx + target_horizon_days
    if exit_policy == "per_tranche_horizon":
        return current_symbol_idx + target_horizon_days, current_benchmark_idx + target_horizon_days
    raise ValueError(f"unsupported exit_policy: {exit_policy}")


def _evaluate_return_rows(
    rows: list[dict[str, Any]],
    *,
    target_horizon_days: int,
) -> dict[str, Any]:
    daily_rows = [
        {
            "as_of_date": str(row.get("as_of_date") or ""),
            "month": str(row.get("month") or str(row.get("as_of_date") or "")[:7]),
            "mean_net_excess_return": _safe_float(row.get("mean_net_excess_return")),
        }
        for row in rows
        if isinstance(row, dict) and row.get("as_of_date")
    ]
    returns = [row["mean_net_excess_return"] for row in daily_rows]
    monthly = _monthly_summary(daily_rows)
    curve = _rolling_sleeve_curve(returns, horizon_days=target_horizon_days)
    path_drawdown = _series_drawdown(returns)
    return {
        "mode": "full_fill_reference",
        "date_count": len(daily_rows),
        "mean_daily_net_excess_return": sum(returns) / len(returns) if returns else None,
        "positive_date_rate": sum(1 for value in returns if value > 0) / len(returns) if returns else None,
        "horizon_normalized_total_return_proxy": curve["total_return"],
        "horizon_normalized_annualized_return_proxy": curve["annualized_return"],
        "horizon_normalized_max_drawdown_proxy": curve["max_drawdown"],
        "path_drawdown_sum": path_drawdown["max_drawdown_sum"],
        "negative_months": [row["month"] for row in monthly if row["mean_net_excess_return"] < 0],
        "negative_month_count": sum(1 for row in monthly if row["mean_net_excess_return"] < 0),
        "worst_monthly_mean": min((row["mean_net_excess_return"] for row in monthly), default=None),
    }


def _compact_underfilled_pick(row: dict[str, Any], *, selected_top_k: int) -> dict[str, Any]:
    target_weight = _target_capital_weight(row, selected_top_k=selected_top_k)
    return {
        "as_of_date": row.get("as_of_date"),
        "symbol": row.get("symbol"),
        "rank": row.get("rank"),
        "avg_amount_20d": _safe_float(row.get("avg_amount_20d")),
        "target_weight": target_weight,
        "net_excess_return": _safe_float(row.get("net_excess_return")),
    }


def _missing_replacement(
    pick: dict[str, Any],
    target_weight: float,
    baseline_contribution: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "as_of_date": pick.get("as_of_date"),
        "symbol": pick.get("symbol"),
        "rank": pick.get("rank"),
        "target_weight": target_weight,
        "target_notional_cny": None,
        "baseline_net_excess_return": _safe_float(pick.get("net_excess_return")),
        "baseline_contribution": baseline_contribution,
        "staggered_contribution": 0.0,
        "staggered_fill_rate": 0.0,
        "unfilled_notional_cny": None,
        "blocked_reason": reason,
        "entry_fills": [],
    }


def _row_index(rows: list[dict[str, Any]], target_date: date) -> int | None:
    return next((index for index, row in enumerate(rows) if _row_date(row) == target_date.isoformat()), None)


def _row_date(row: dict[str, Any]) -> str | None:
    value = row.get("observed_at")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        return value[:10]
    return None
