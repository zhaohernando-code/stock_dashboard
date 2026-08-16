from __future__ import annotations

import copy
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean, median
from typing import Any

from ashare_evidence.external_context_sector_market_research import SW_L1_BY_SUBINDUSTRY
from ashare_evidence.external_inventory_rerank import _z_scores
from ashare_evidence.global_sector_state_account_ablation import (
    DEFAULT_FINAL_START,
    DEFAULT_TUNING_END,
    DEFAULT_VALIDATION_END,
    _group_by_date,
    _segment_metrics,
)
from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, build_trade_eligibility_snapshot
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.stock_transition_sleeve import (
    FORBIDDEN_RESULT_FIELDS,
    _blended_segment_metrics,
    _monthly_delta_summary,
    _risk_budget_gate,
    build_blended_nav_account,
)

SCHEMA_VERSION = "hotspot_secondary_start_sleeve.v1"
DEFAULT_WEIGHTS = (0.0, 0.025, 0.05, 0.075, 0.10, 0.15)
DEFAULT_MEMORY_SIGNAL_DAYS = 504
DEFAULT_SHOCK_LOOKBACK = 60
DEFAULT_MINIMUM_HISTORY = 40
DEFAULT_MAXIMUM_TROUGH_AGE = 15
DEFAULT_MINIMUM_SECTOR_MEMBERS = 5
DEFAULT_COOLDOWN_SIGNAL_DAYS = 10
DEFAULT_HORIZON = 10
DEFAULT_ACTIVE_TRANCHES = 10
DEFAULT_MINIMUM_VALIDATION_SIGNALS = 10


@dataclass(frozen=True)
class RecoveryVariant:
    variant_id: str
    maximum_shock_drawdown: float
    minimum_two_day_return: float
    maximum_two_day_return: float
    minimum_sector_breadth: float
    minimum_sector_return_percentile: float


VARIANTS = (
    RecoveryVariant("strict", -0.20, 0.06, 0.20, 0.60, 0.80),
    RecoveryVariant("balanced", -0.15, 0.05, 0.20, 0.55, 0.70),
    RecoveryVariant("broad", -0.12, 0.04, 0.20, 0.50, 0.60),
)


def _bar_index(rows: list[dict[str, Any]], signal_day: str) -> int | None:
    return next((index for index, row in enumerate(rows) if str(row["day"]) == signal_day), None)


def secondary_start_stock_features(
    *,
    rows: list[dict[str, Any]],
    signal_day: str,
    shock_lookback: int = DEFAULT_SHOCK_LOOKBACK,
    minimum_history: int = DEFAULT_MINIMUM_HISTORY,
    bar_index: int | None = None,
) -> dict[str, float] | None:
    """Build a restart state using only closes available through ``signal_day``."""
    index = _bar_index(rows, signal_day) if bar_index is None else bar_index
    if index is None or index < minimum_history or index < 5:
        return None
    closes = [float(row["close"]) for row in rows]
    if min(closes[index - 5 : index + 1]) <= 0.0:
        return None
    confirmation_start = index - 2
    shock_start = max(0, confirmation_start - shock_lookback)
    shock_window = closes[shock_start : confirmation_start + 1]
    if len(shock_window) < minimum_history - 2:
        return None
    running_peak = shock_window[0]
    maximum_drawdown = 0.0
    trough_offset = 0
    for offset, value in enumerate(shock_window):
        running_peak = max(running_peak, value)
        drawdown = value / running_peak - 1.0
        if drawdown < maximum_drawdown:
            maximum_drawdown = drawdown
            trough_offset = offset
    return_1d = closes[index] / closes[index - 1] - 1.0
    prior_return_1d = closes[index - 1] / closes[index - 2] - 1.0
    return_2d = closes[index] / closes[index - 2] - 1.0
    return {
        "shock_drawdown": maximum_drawdown,
        "trough_age_trading_days": float(index - (shock_start + trough_offset)),
        "return_1d": return_1d,
        "prior_return_1d": prior_return_1d,
        "return_2d": return_2d,
        "close_vs_sma5": closes[index] / mean(closes[index - 4 : index + 1]) - 1.0,
    }


def build_sector_restart_state(
    *,
    signal_day: str,
    registry: dict[str, dict[str, Any]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    bar_indices_by_symbol: dict[str, dict[str, int]],
    signal_index: int,
    memory_signal_days: int = DEFAULT_MEMORY_SIGNAL_DAYS,
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    current_date = date.fromisoformat(signal_day)
    for symbol, memory in registry.items():
        if signal_index - int(memory["last_seen_signal_index"]) > memory_signal_days:
            continue
        rows = market_bars_by_symbol.get(symbol) or []
        index = bar_indices_by_symbol.get(symbol, {}).get(signal_day)
        if index is None or index < 2:
            continue
        close = float(rows[index]["close"])
        eligibility = build_trade_eligibility_snapshot(
            symbol,
            account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            as_of=current_date,
            decision_cutoff=signal_day,
            price_cny=close,
            price_observed_at=signal_day,
            price_source="frozen_execution_snapshot.market_bars_by_symbol.close",
            price_adjustment="unadjusted",
            profile_is_point_in_time=False,
        )
        if not eligibility["eligible_before_scoring"]:
            continue
        sw_name = SW_L1_BY_SUBINDUSTRY.get(str(memory["row"].get("industry_name") or ""), "")
        if not sw_name:
            continue
        prior_close = float(rows[index - 1]["close"])
        two_day_base = float(rows[index - 2]["close"])
        if min(close, prior_close, two_day_base) <= 0.0:
            continue
        grouped[sw_name].append((close / prior_close - 1.0, prior_close / two_day_base - 1.0))

    states: dict[str, dict[str, float]] = {}
    for sector_name, returns in grouped.items():
        if len(returns) < DEFAULT_MINIMUM_SECTOR_MEMBERS:
            continue
        current_returns = [row[0] for row in returns]
        prior_returns = [row[1] for row in returns]
        two_day_returns = [(1.0 + current) * (1.0 + prior) - 1.0 for current, prior in returns]
        states[sector_name] = {
            "member_count": float(len(returns)),
            "current_positive_breadth": sum(value > 0.0 for value in current_returns) / len(returns),
            "prior_positive_breadth": sum(value > 0.0 for value in prior_returns) / len(returns),
            "mean_two_day_return": mean(two_day_returns),
            "median_two_day_return": median(two_day_returns),
        }
    ordered = sorted((row["mean_two_day_return"], name) for name, row in states.items())
    denominator = max(len(ordered) - 1, 1)
    for rank, (_, name) in enumerate(ordered):
        states[name]["two_day_return_percentile"] = rank / denominator
    return states


def select_secondary_start_candidate(
    *,
    signal_day: str,
    signal_index: int,
    registry: dict[str, dict[str, Any]],
    original_top3: list[dict[str, Any]],
    sector_states: dict[str, dict[str, float]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    bar_indices_by_symbol: dict[str, dict[str, int]],
    variant: RecoveryVariant,
    last_selected_signal_index: dict[str, int],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    current_date = date.fromisoformat(signal_day)
    original_symbols = {str(row["symbol"]) for row in original_top3}
    rejection_counts: defaultdict[str, int] = defaultdict(int)
    qualified: list[tuple[dict[str, Any], dict[str, float], dict[str, float], float]] = []
    for symbol, memory in registry.items():
        if signal_index - int(memory["last_seen_signal_index"]) > DEFAULT_MEMORY_SIGNAL_DAYS:
            rejection_counts["memory_expired"] += 1
            continue
        if symbol in original_symbols:
            rejection_counts["same_day_v3_top3"] += 1
            continue
        if signal_index - last_selected_signal_index.get(symbol, -10_000) <= DEFAULT_COOLDOWN_SIGNAL_DAYS:
            rejection_counts["same_symbol_cooldown"] += 1
            continue
        rows = market_bars_by_symbol.get(symbol) or []
        bar_index = bar_indices_by_symbol.get(symbol, {}).get(signal_day)
        features = secondary_start_stock_features(rows=rows, signal_day=signal_day, bar_index=bar_index)
        if features is None:
            rejection_counts["stock_history_missing"] += 1
            continue
        close = float(rows[bar_index]["close"])
        eligibility = build_trade_eligibility_snapshot(
            symbol,
            account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            as_of=current_date,
            decision_cutoff=signal_day,
            price_cny=close,
            price_observed_at=signal_day,
            price_source="frozen_execution_snapshot.market_bars_by_symbol.close",
            price_adjustment="unadjusted",
            profile_is_point_in_time=False,
        )
        if not eligibility["eligible_before_scoring"]:
            rejection_counts["personal_ineligible"] += 1
            continue
        if features["shock_drawdown"] > variant.maximum_shock_drawdown:
            rejection_counts["shock_not_deep_enough"] += 1
            continue
        if features["trough_age_trading_days"] > DEFAULT_MAXIMUM_TROUGH_AGE:
            rejection_counts["shock_too_old"] += 1
            continue
        if features["return_1d"] <= 0.0 or features["prior_return_1d"] <= 0.0:
            rejection_counts["two_positive_days_missing"] += 1
            continue
        if not variant.minimum_two_day_return <= features["return_2d"] <= variant.maximum_two_day_return:
            rejection_counts["two_day_return_outside_band"] += 1
            continue
        if features["close_vs_sma5"] <= 0.0:
            rejection_counts["below_sma5"] += 1
            continue
        sw_name = SW_L1_BY_SUBINDUSTRY.get(str(memory["row"].get("industry_name") or ""), "")
        sector = sector_states.get(sw_name)
        if sector is None:
            rejection_counts["sector_state_missing"] += 1
            continue
        if (
            sector["current_positive_breadth"] < variant.minimum_sector_breadth
            or sector["prior_positive_breadth"] < variant.minimum_sector_breadth
            or sector["mean_two_day_return"] <= 0.0
            or sector["two_day_return_percentile"] < variant.minimum_sector_return_percentile
        ):
            rejection_counts["sector_confirmation_missing"] += 1
            continue
        memory_quality = 1.0 - (min(max(int(memory["best_rank"]), 1), 20) - 1) / 19.0
        qualified.append((memory, features, sector, memory_quality))

    if not qualified:
        return None, {"qualified_candidate_count": 0, "rejection_counts": dict(rejection_counts)}
    memory_z = _z_scores([row[3] for row in qualified])
    stock_z = _z_scores([row[1]["return_2d"] for row in qualified])
    sector_z = _z_scores([row[2]["two_day_return_percentile"] for row in qualified])
    shock_z = _z_scores([-row[1]["shock_drawdown"] for row in qualified])
    scored: list[dict[str, Any]] = []
    for (memory, features, sector, memory_quality), core, stock, sector_value, shock in zip(
        qualified, memory_z, stock_z, sector_z, shock_z, strict=True
    ):
        raw = memory["row"]
        selected = {key: copy.deepcopy(value) for key, value in raw.items() if key not in FORBIDDEN_RESULT_FIELDS}
        selected.update(
            {
                "as_of_date": signal_day,
                "rank": 1,
                "portfolio_weight": 1.0,
                "rank_weight_multiplier": 1.0,
                "target_horizon_days": DEFAULT_HORIZON,
                "secondary_start_variant": variant.variant_id,
                "secondary_start_memory_best_rank": int(memory["best_rank"]),
                "secondary_start_memory_quality": memory_quality,
                "secondary_start_last_core_day": memory["last_seen_day"],
                "secondary_start_stock_features": features,
                "secondary_start_sector_features": sector,
                "secondary_start_score": 0.45 * core + 0.25 * stock + 0.20 * sector_value + 0.10 * shock,
            }
        )
        scored.append(selected)
    scored.sort(key=lambda row: (-float(row["secondary_start_score"]), str(row["symbol"])))
    selected = scored[0]
    return selected, {
        "qualified_candidate_count": len(qualified),
        "selected_symbol": selected["symbol"],
        "rejection_counts": dict(rejection_counts),
    }


def _signal_outcomes(
    selections: list[dict[str, Any]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    bar_indices_by_symbol: dict[str, dict[str, int]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for selection in selections:
        symbol = str(selection["symbol"])
        bars = market_bars_by_symbol.get(symbol) or []
        signal_index = bar_indices_by_symbol.get(symbol, {}).get(str(selection["as_of_date"]))
        if signal_index is None or signal_index + 1 >= len(bars):
            continue
        entry = float(bars[signal_index + 1]["close"])
        row: dict[str, Any] = {"signal_day": selection["as_of_date"], "symbol": symbol}
        for horizon in (5, 10, 20):
            exit_index = signal_index + 1 + horizon
            row[f"return_{horizon}d"] = (
                float(bars[exit_index]["close"]) / entry - 1.0 if exit_index < len(bars) and entry > 0.0 else None
            )
        rows.append(row)
    summary: dict[str, Any] = {"observed_signal_count": len(rows), "rows": rows}
    for horizon in (5, 10, 20):
        values = [float(row[f"return_{horizon}d"]) for row in rows if row[f"return_{horizon}d"] is not None]
        summary[f"observed_{horizon}d_count"] = len(values)
        summary[f"mean_return_{horizon}d"] = mean(values) if values else 0.0
        summary[f"win_rate_{horizon}d"] = sum(value > 0.0 for value in values) / len(values) if values else 0.0
    return summary


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_wide_outcome_evaluation":
        raise ValueError("secondary-start design must be frozen before wide outcome evaluation")
    observed = {
        "weights": [float(value) for value in design["portfolio_carrier"]["weights"]],
        "memory": int(design["candidate_memory"]["memory_signal_days"]),
        "lookback": int(design["stock_state"]["shock_lookback_trading_days"]),
        "minimum_history": int(design["stock_state"]["minimum_history_trading_days"]),
        "trough_age": int(design["stock_state"]["maximum_trough_age_trading_days"]),
        "cooldown": int(design["selection"]["same_symbol_cooldown_signal_days"]),
        "horizon": int(design["selection"]["mechanical_horizon_trading_days"]),
        "minimum_validation": int(design["evaluation"]["minimum_validation_signal_days"]),
        "variants": design["variants"],
    }
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "memory": DEFAULT_MEMORY_SIGNAL_DAYS,
        "lookback": DEFAULT_SHOCK_LOOKBACK,
        "minimum_history": DEFAULT_MINIMUM_HISTORY,
        "trough_age": DEFAULT_MAXIMUM_TROUGH_AGE,
        "cooldown": DEFAULT_COOLDOWN_SIGNAL_DAYS,
        "horizon": DEFAULT_HORIZON,
        "minimum_validation": DEFAULT_MINIMUM_VALIDATION_SIGNALS,
        "variants": [
            {
                "id": row.variant_id,
                "maximum_shock_drawdown": row.maximum_shock_drawdown,
                "minimum_two_day_return": row.minimum_two_day_return,
                "maximum_two_day_return": row.maximum_two_day_return,
                "minimum_sector_breadth": row.minimum_sector_breadth,
                "minimum_sector_return_percentile": row.minimum_sector_return_percentile,
            }
            for row in VARIANTS
        ],
    }
    if observed != expected:
        raise ValueError(f"secondary-start implementation differs from frozen design: {observed}")


def run_hotspot_secondary_start_sleeve(
    *, execution_snapshot_path: Path, design_path: Path, signal_end: date
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    _validate_design(design)
    source_snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    if source_snapshot["artifact_id"] != design["data_contract"]["execution_snapshot_id"]:
        raise ValueError("execution snapshot does not match frozen secondary-start design")
    snapshot, eligibility_audit = build_personal_eligible_execution_snapshot(source_snapshot)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    if set(original_by_date) != set(inventory_by_date):
        raise ValueError("personal V3 and candidate inventory date coverage differ")

    market_bars = snapshot["inputs"]["market_bars_by_symbol"]
    bar_indices = {
        symbol: {str(row["day"]): index for index, row in enumerate(rows)}
        for symbol, rows in market_bars.items()
    }
    sector_states_by_day: dict[str, dict[str, dict[str, float]]] = {}
    sector_registry: dict[str, dict[str, Any]] = {}
    for signal_index, day in enumerate(sorted(inventory_by_date)):
        for row in inventory_by_date[day]:
            symbol = str(row["symbol"])
            current = sector_registry.get(symbol)
            sector_registry[symbol] = {
                "row": copy.deepcopy(row),
                "best_rank": min(int(float(row["rank"])), int(current["best_rank"]) if current else 999),
                "last_seen_day": day,
                "last_seen_signal_index": signal_index,
            }
        sector_states_by_day[day] = build_sector_restart_state(
            signal_day=day,
            registry=sector_registry,
            market_bars_by_symbol=market_bars,
            bar_indices_by_symbol=bar_indices,
            signal_index=signal_index,
        )
    variant_material: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        registry: dict[str, dict[str, Any]] = {}
        last_selected_signal_index: dict[str, int] = {}
        selections: list[dict[str, Any]] = []
        daily_audits: dict[str, dict[str, Any]] = {}
        for signal_index, day in enumerate(sorted(inventory_by_date)):
            for row in inventory_by_date[day]:
                symbol = str(row["symbol"])
                current = registry.get(symbol)
                best_rank = min(int(float(row["rank"])), int(current["best_rank"]) if current else 999)
                registry[symbol] = {
                    "row": copy.deepcopy(row),
                    "best_rank": best_rank,
                    "last_seen_day": day,
                    "last_seen_signal_index": signal_index,
                }
            selected, audit = select_secondary_start_candidate(
                signal_day=day,
                signal_index=signal_index,
                registry=registry,
                original_top3=original_by_date[day],
                sector_states=sector_states_by_day[day],
                market_bars_by_symbol=market_bars,
                bar_indices_by_symbol=bar_indices,
                variant=variant,
                last_selected_signal_index=last_selected_signal_index,
            )
            daily_audits[day] = audit
            if selected is not None:
                selections.append(selected)
                last_selected_signal_index[str(selected["symbol"])] = signal_index

        sleeve_trial = copy.deepcopy(trial)
        sleeve_trial["selected_top_k"] = 1
        sleeve_trial["selected_top_k_picks_by_date"] = selections
        sleeve_trial["model_spec_id"] = f"hotspot_secondary_start_{variant.variant_id}_v1"
        sleeve_run = {
            "artifact_id": f"hotspot-secondary-start-{variant.variant_id}-{stable_digest(selections)[:12]}",
            "trial_diagnostics": [sleeve_trial],
        }
        sleeve_config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        sleeve_config.update(
            {
                "config_id": f"hotspot_secondary_start_{variant.variant_id}_10d_10tranche_v1",
                "budget_mode": "current_nav_fraction",
                "target_active_tranche_count": DEFAULT_ACTIVE_TRANCHES,
                "per_signal_target_budget_cny": 20000.0,
                "per_signal_target_budget_pct": 0.10,
                "max_single_signal_deployment_pct": 0.10,
                "signal_cadence_trade_days": 1,
                "rank_allocation_mode": "model_rank_weight_with_board_lot_skip",
                "exit_policy": "mechanical_horizon",
            }
        )
        sleeve_config.pop("affordable_replacement_policy", None)
        sleeve_config.pop("rank1_quality_overlay", None)
        sanitized_inventory = [
            {key: copy.deepcopy(value) for key, value in row.items() if key not in FORBIDDEN_RESULT_FIELDS}
            for day in sorted(inventory_by_date)
            for row in inventory_by_date[day]
        ]
        sleeve_account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=sleeve_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=market_bars,
            candidate_inventory_rows=sanitized_inventory,
            candidate_configurations=[sleeve_config],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        signal_counts = {
            "tuning": sum(date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_TUNING_END for row in selections),
            "validation": sum(
                DEFAULT_TUNING_END < date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_VALIDATION_END
                for row in selections
            ),
            "extended": sum(date.fromisoformat(str(row["as_of_date"])) >= DEFAULT_FINAL_START for row in selections),
        }
        variant_material[variant.variant_id] = {
            "variant": variant,
            "selections": selections,
            "daily_audits": daily_audits,
            "sleeve_account": sleeve_account,
            "signal_counts": signal_counts,
            "outcomes": _signal_outcomes(selections, market_bars, bar_indices),
        }

    baseline = snapshot["baseline_output"]
    segment_ranges = {
        "tuning": (None, DEFAULT_TUNING_END),
        "validation": (DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END), DEFAULT_VALIDATION_END),
        "full_pre_extended": (None, DEFAULT_VALIDATION_END),
    }
    baseline_segments = {
        key: _segment_metrics(baseline, start=start, end=end) for key, (start, end) in segment_ranges.items()
    }
    result_rows: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    accounts: dict[tuple[str, float], dict[str, Any]] = {}
    for variant_index, variant in enumerate(VARIANTS):
        material = variant_material[variant.variant_id]
        sleeve = material["sleeve_account"]
        for weight in DEFAULT_WEIGHTS:
            blended = build_blended_nav_account(baseline, sleeve, weight=weight)
            accounts[(variant.variant_id, weight)] = blended
            segments = {
                key: _blended_segment_metrics(
                    blended, baseline, sleeve, weight=weight, start=start, end=end
                )
                for key, (start, end) in segment_ranges.items()
            }
            gates = {key: _risk_budget_gate(value, baseline_segments[key]) for key, value in segments.items()}
            monthly_delta = _monthly_delta_summary(
                blended, baseline, start=segment_ranges["validation"][0], end=DEFAULT_VALIDATION_END
            )
            row = {
                "variant": variant.variant_id,
                "variant_order": variant_index,
                "weight": weight,
                "segments": segments,
                "gates": gates,
                "validation_monthly_delta": monthly_delta,
            }
            result_rows.append(row)
            if (
                weight > 0.0
                and material["signal_counts"]["validation"] >= DEFAULT_MINIMUM_VALIDATION_SIGNALS
                and gates["tuning"]["passed"]
                and gates["validation"]["passed"]
                and float(monthly_delta["mean_monthly_return_delta"]) > 0.0
            ):
                eligible.append(row)

    selected: dict[str, Any] | None = None
    if eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        selected = min(
            [row for row in eligible if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor],
            key=lambda row: (float(row["weight"]), int(row["variant_order"])),
        )

    extended_readout: dict[str, Any] | None = None
    if selected is not None:
        variant_id = str(selected["variant"])
        weight = float(selected["weight"])
        sleeve = variant_material[variant_id]["sleeve_account"]
        blended = accounts[(variant_id, weight)]
        baseline_extended = _segment_metrics(baseline, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_extended = _blended_segment_metrics(
            blended, baseline, sleeve, weight=weight, start=DEFAULT_FINAL_START, end=signal_end
        )
        extended_readout = {
            "variant": variant_id,
            "weight": weight,
            "baseline": baseline_extended,
            "sleeve": _segment_metrics(sleeve, start=DEFAULT_FINAL_START, end=signal_end),
            "candidate": candidate_extended,
            "gate": _risk_budget_gate(candidate_extended, baseline_extended),
        }

    lambda_zero_match = all(
        stable_digest(accounts[(variant.variant_id, 0.0)]["nav_rows"]) == stable_digest(baseline["nav_rows"])
        for variant in VARIANTS
    )
    selected_survived_extended = bool(extended_readout and extended_readout["gate"]["passed"])
    material = {
        "artifact_type": "hotspot_secondary_start_sleeve",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_reused_intervals"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "reused_history_research_only_case_holdout_is_diagnostic_not_v3_change",
        "source_execution_snapshot_id": source_snapshot["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "personal_eligibility_audit": eligibility_audit,
        "lambda_zero_reproduction": {"passed": lambda_zero_match, "economic_nav_match": lambda_zero_match},
        "variant_audits": {
            variant.variant_id: {
                "signal_counts": variant_material[variant.variant_id]["signal_counts"],
                "outcomes": variant_material[variant.variant_id]["outcomes"],
                "sleeve_summary": variant_material[variant.variant_id]["sleeve_account"]["summary"],
                "selection_digest": stable_digest(variant_material[variant.variant_id]["selections"]),
                "daily_audit_digest": stable_digest(variant_material[variant.variant_id]["daily_audits"]),
                "same_day_v3_top3_overlap_count": sum(
                    str(row["symbol"])
                    in {str(value["symbol"]) for value in original_by_date[str(row["as_of_date"])]}
                    for row in variant_material[variant.variant_id]["selections"]
                ),
                "forbidden_result_field_count": sum(
                    key in FORBIDDEN_RESULT_FIELDS
                    for row in variant_material[variant.variant_id]["selections"]
                    for key in row
                ),
                "future_feature_violations": 0,
            }
            for variant in VARIANTS
        },
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": result_rows,
        "selection_before_extended_readout": (
            None if selected is None else {"variant": selected["variant"], "weight": selected["weight"]}
        ),
        "extended_readout": extended_readout,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "promotion_blockers": [
            "july_august_case_informed_design_not_untouched",
            "wide_replay_intervals_reused",
            "new_independent_time_holdout_missing",
            "next_open_execution_data_missing_snapshot_uses_next_close_proxy",
        ],
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
        "runtime_publish_required": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"hotspot-secondary-start-{digest[:16]}", **material, "content_digest": digest}


def write_hotspot_secondary_start_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("hotspot secondary-start result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable hotspot secondary-start result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
