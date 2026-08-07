from __future__ import annotations

import copy
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import numpy as np

from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
)
from ashare_evidence.external_context_macro_research import load_macro_research_snapshot, macro_state_by_decision_date
from ashare_evidence.external_context_sector_flow_research import (
    load_sector_flow_snapshot,
    sector_flow_by_name_by_decision_date,
    sector_flow_state_by_decision_date,
)
from ashare_evidence.external_context_sector_market_research import (
    SW_L1_BY_SUBINDUSTRY,
    load_sector_research_snapshot,
    sector_state_by_decision_date,
)
from ashare_evidence.global_sector_state_account_ablation import (
    DEFAULT_FINAL_START,
    DEFAULT_TUNING_END,
    DEFAULT_VALIDATION_END,
    _buy_order_delta,
    _candidate_run,
    _group_by_date,
    _industry_loading,
    _monthly_delta_summary,
    _non_degrade,
    _segment_metrics,
    _standout,
)
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "external_inventory_rerank_account_ablation.v1"


def _z_scores(values: list[float]) -> list[float]:
    deviation = pstdev(values)
    if deviation <= 1e-12:
        return [0.0] * len(values)
    center = mean(values)
    return [(value - center) / deviation for value in values]


def _candidate_return_labels(
    snapshot: dict[str, Any], *, inventory_by_date: dict[str, list[dict[str, Any]]], signal_end: date
) -> dict[tuple[str, str], dict[str, Any]]:
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    labels: dict[tuple[str, str], dict[str, Any]] = {}
    for day, rows in inventory_by_date.items():
        if date.fromisoformat(day) > signal_end:
            continue
        for row in rows:
            symbol = str(row["symbol"])
            bars = bars_by_symbol.get(symbol) or []
            entry_index = next((index for index, bar in enumerate(bars) if str(bar["day"]) > day), None)
            if entry_index is None or entry_index + 20 >= len(bars):
                continue
            labels[(day, symbol)] = {
                "signal_day": day,
                "symbol": symbol,
                "available_day": str(bars[entry_index + 20]["day"]),
                "return_20d": float(bars[entry_index + 20]["close"]) / float(bars[entry_index]["close"]) - 1.0,
            }
    return labels


def _candidate_features(
    row: dict[str, Any],
    *,
    global_state: dict[str, Any],
    sector_state: dict[str, Any],
    macro_state: dict[str, Any],
    flow_state: dict[str, float] | None,
    flow_by_name: dict[str, dict[str, Any]] | None,
) -> tuple[list[float], list[float], bool]:
    core = [
        float(row.get("score") or 0.0),
        float(row.get("return_5d_percentile") or 0.0),
        float(row.get("return_20d_percentile") or 0.0),
        float(row.get("turnover_rate_percentile") or 0.0),
        float(row.get("amount_10d_vs_20d_percentile") or 0.0),
        float(row.get("distance_from_20d_high") or 0.0),
        math.log1p(max(float(row.get("avg_amount_20d") or 0.0), 0.0)),
        float(row.get("benchmark_return_20d") or 0.0),
        float(row.get("industry_return_20d_excess") or 0.0),
    ]
    industry = str(row.get("industry_name") or "")
    sw_name = SW_L1_BY_SUBINDUSTRY.get(industry, "")
    sw_row = (sector_state.get("by_sector_name") or {}).get(sw_name) or {}
    ths_row = (flow_by_name or {}).get(industry) or {}
    ths_mapped = bool(ths_row)
    loading = _industry_loading(industry)

    def macro_value(series_id: str, field: str) -> float:
        return float((macro_state.get(series_id) or {}).get(field) or 0.0)

    external = [
        float(sw_row.get("relative_5d") or 0.0),
        float(sw_row.get("relative_20d") or 0.0),
        float(sw_row.get("drawdown_20d") or 0.0),
        float(ths_row.get("net_flow_ratio") or 0.0),
        float(ths_row.get("pct_change") or 0.0),
        float(ths_mapped),
        loading * float(global_state.get("tech_relative_5d") or 0.0),
        loading * float(global_state.get("tech_relative_20d") or 0.0),
        loading * macro_value("VIXCLS", "change_5d"),
        loading * macro_value("USDCNH_MID", "return_5d"),
        loading * float((flow_state or {}).get("tech_positive_flow_breadth") or 0.0),
        loading * float((flow_state or {}).get("tech_mean_net_flow_ratio") or 0.0),
        float(flow_state is not None),
    ]
    return core, [*core, *external], ths_mapped


def _ridge_predictions(
    training: list[list[float]], targets: list[float], current: list[list[float]], *, alpha: float
) -> list[float]:
    matrix = np.asarray(training, dtype=float)
    target = np.asarray(targets, dtype=float)
    current_matrix = np.asarray(current, dtype=float)
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales <= 1e-12] = 1.0
    standardized = (matrix - centers) / scales
    standardized_current = (current_matrix - centers) / scales
    design = np.column_stack([np.ones(len(matrix)), standardized])
    current_design = np.column_stack([np.ones(len(current_matrix)), standardized_current])
    penalty = np.eye(design.shape[1], dtype=float) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(design.T @ design + penalty) @ design.T @ target
    return [float(value) for value in current_design @ beta]


def _expanding_inventory_residuals(
    *,
    inventory_by_date: dict[str, list[dict[str, Any]]],
    labels: dict[tuple[str, str], dict[str, Any]],
    market_states: dict[str, dict[str, Any]],
    sector_states: dict[str, dict[str, Any]],
    macro_states: dict[str, dict[str, Any]],
    flow_states: dict[str, dict[str, float]],
    flow_by_name_states: dict[str, dict[str, dict[str, Any]]],
    minimum_training_candidates: int,
    l2_penalty: float,
) -> tuple[dict[str, dict[str, float] | None], dict[str, Any]]:
    features: dict[tuple[str, str], tuple[list[float], list[float]]] = {}
    mapped_count = 0
    total_count = 0
    for day, rows in inventory_by_date.items():
        for row in rows:
            core, full, mapped = _candidate_features(
                row,
                global_state=market_states[day],
                sector_state=sector_states[day],
                macro_state=macro_states[day],
                flow_state=flow_states.get(day),
                flow_by_name=flow_by_name_states.get(day),
            )
            features[(day, str(row["symbol"]))] = (core, full)
            mapped_count += int(mapped)
            total_count += 1
    residuals: dict[str, dict[str, float] | None] = {}
    fit_counts: dict[str, int] = {}
    for day in sorted(inventory_by_date):
        ready_keys = [
            key
            for key, label in labels.items()
            if key in features and date.fromisoformat(str(label["available_day"])) <= date.fromisoformat(day)
        ]
        fit_counts[day] = len(ready_keys)
        if len(ready_keys) < minimum_training_candidates:
            residuals[day] = None
            continue
        targets = [float(labels[key]["return_20d"]) for key in ready_keys]
        current_keys = [(day, str(row["symbol"])) for row in inventory_by_date[day]]
        core_predictions = _ridge_predictions(
            [features[key][0] for key in ready_keys],
            targets,
            [features[key][0] for key in current_keys],
            alpha=l2_penalty,
        )
        full_predictions = _ridge_predictions(
            [features[key][1] for key in ready_keys],
            targets,
            [features[key][1] for key in current_keys],
            alpha=l2_penalty,
        )
        residuals[day] = {
            key[1]: full - core
            for key, core, full in zip(current_keys, core_predictions, full_predictions, strict=True)
        }
    return residuals, {
        "minimum_training_candidates": minimum_training_candidates,
        "l2_penalty": l2_penalty,
        "ready_prediction_day_count": sum(row is not None for row in residuals.values()),
        "warmup_day_count": sum(row is None for row in residuals.values()),
        "last_fit_count": fit_counts[max(fit_counts)] if fit_counts else 0,
        "ths_exact_industry_mapping_rate": mapped_count / max(total_count, 1),
        "future_label_violations": 0,
    }


def run_external_inventory_rerank_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    macro_market_snapshot_path: Path,
    sector_flow_snapshot_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round28_outcome_evaluation":
        raise ValueError("full inventory rerank design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    global_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    macro_snapshot = load_macro_research_snapshot(macro_market_snapshot_path)
    flow_snapshot = load_sector_flow_snapshot(sector_flow_snapshot_path)
    expected_digests = design["data_contract"]
    actual_digests = {
        "global_market_digest": global_snapshot["content_digest"],
        "sector_market_digest": sector_snapshot["content_digest"],
        "macro_market_digest": macro_snapshot["content_digest"],
        "sector_flow_digest": flow_snapshot["content_digest"],
    }
    mismatches = {
        key: {"expected": expected_digests.get(key), "actual": value}
        for key, value in actual_digests.items()
        if expected_digests.get(key) != value
    }
    if mismatches:
        raise ValueError(f"external snapshot digest mismatch: {mismatches}")
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    maximum_rank = int(design["candidate_boundary"]["maximum_original_rank"])
    inventory_by_date = {
        day: [row for row in rows if int(float(row["rank"])) <= maximum_rank]
        for day, rows in inventory_by_date.items()
    }
    if any(len(rows) < len(original_picks_by_date[day]) for day, rows in inventory_by_date.items()):
        raise ValueError("frozen V3 inventory is too shallow for the selected top-k")
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    market_states = market_state_by_decision_date(global_snapshot["records"], decision_dates=decision_dates)
    sector_states = sector_state_by_decision_date(sector_snapshot["normalized"]["records"], decision_dates=decision_dates)
    macro_states = macro_state_by_decision_date(macro_snapshot["records"], decision_dates=decision_dates)
    flow_states = sector_flow_state_by_decision_date(
        flow_snapshot["normalized"]["records"], decision_dates=decision_dates
    )
    flow_by_name_states = sector_flow_by_name_by_decision_date(
        flow_snapshot["normalized"]["records"], decision_dates=decision_dates
    )
    if not all(set(states) == set(inventory_by_date) for states in (market_states, sector_states, macro_states)):
        raise ValueError("full-window market state coverage is incomplete")
    labels = _candidate_return_labels(snapshot, inventory_by_date=inventory_by_date, signal_end=signal_end)
    model = design["model"]
    residuals, prediction_audit = _expanding_inventory_residuals(
        inventory_by_date=inventory_by_date,
        labels=labels,
        market_states=market_states,
        sector_states=sector_states,
        macro_states=macro_states,
        flow_states=flow_states,
        flow_by_name_states=flow_by_name_states,
        minimum_training_candidates=int(model["minimum_completed_candidate_labels"]),
        l2_penalty=float(model["l2_penalty"]),
    )
    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))

    def replay(weight: float) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        changed_dates = 0
        changed_slots = 0
        promoted_from_outside_top3 = 0
        cap = float(design["carrier"]["maximum_absolute_external_contribution"])
        for day in sorted(inventory_by_date):
            inventory = sorted(copy.deepcopy(inventory_by_date[day]), key=lambda row: int(float(row["rank"])))
            original = sorted(copy.deepcopy(original_picks_by_date[day]), key=lambda row: int(float(row["rank"])))
            residual_by_symbol = residuals.get(day)
            if weight == 0 or residual_by_symbol is None:
                chosen = original
            else:
                core_z = _z_scores([float(row["score"]) for row in inventory])
                external_z = _z_scores([float(residual_by_symbol[str(row["symbol"])]) for row in inventory])
                for row, core_value, external_value in zip(inventory, core_z, external_z, strict=True):
                    contribution = max(-cap, min(cap, weight * external_value))
                    row["external_inventory_residual_z"] = external_value
                    row["external_inventory_contribution"] = contribution
                    row["external_adjusted_score"] = core_value + contribution
                inventory.sort(key=lambda row: (-float(row["external_adjusted_score"]), -float(row["score"])))
                chosen = inventory[: len(original)]
            rebuilt: list[dict[str, Any]] = []
            for index, candidate in enumerate(chosen):
                template = original[index]
                unchanged_slot = str(candidate["symbol"]) == str(template["symbol"])
                shadow_buy_symbols = (
                    sorted(baseline_buy_symbols_by_slot.get((day, index + 1), set()))
                    if unchanged_slot
                    else [str(candidate["symbol"])]
                )
                rebuilt.append(
                    {
                        **candidate,
                        "rank": index + 1,
                        "portfolio_weight": float(template.get("portfolio_weight") or 1.0),
                        "rank_weight_multiplier": float(template.get("rank_weight_multiplier") or 0.0),
                        "target_horizon_days": int(float(template.get("target_horizon_days") or 20)),
                        "shadow_baseline_buy_symbols": shadow_buy_symbols,
                    }
                )
                if str(candidate["symbol"]) != str(template["symbol"]):
                    changed_slots += 1
                    promoted_from_outside_top3 += int(int(float(candidate.get("rank") or 0)) > 3)
            if any(str(a["symbol"]) != str(b["symbol"]) for a, b in zip(rebuilt, original, strict=True)):
                changed_dates += 1
            selected.extend(rebuilt)
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=weight)
        candidate_run["artifact_id"] = f"external-full-inventory-rerank-{weight:.3f}"
        account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        return account, {
            "changed_date_count": changed_dates,
            "changed_rank_slot_count": changed_slots,
            "promoted_from_outside_original_top3_count": promoted_from_outside_top3,
        }

    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_extended": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    rows: list[dict[str, Any]] = []
    accounts: dict[float, dict[str, Any]] = {}
    for weight in [float(value) for value in design["weights"]]:
        account, audit = replay(weight)
        accounts[weight] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_extended": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        rows.append(
            {
                "weight": weight,
                "change_audit": audit,
                "segments": segments,
                "gates": {key: _non_degrade(value, baseline_segments[key]) for key, value in segments.items()},
                "validation_monthly_delta": _monthly_delta_summary(
                    account,
                    baseline_account,
                    start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                    end=DEFAULT_VALIDATION_END,
                ),
            }
        )
    lambda_zero_full_digest_match = stable_digest(accounts[0.0]) == stable_digest(baseline_account)
    lambda_zero_nav_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    lambda_zero_trade_match = stable_digest(
        [row for row in accounts[0.0]["order_ledger"] if row.get("action") in {"buy", "sell"}]
    ) == stable_digest(
        [row for row in baseline_account["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    lambda_zero_economic_match = lambda_zero_nav_match and lambda_zero_trade_match
    if not lambda_zero_economic_match:
        raise ValueError("lambda zero failed to reproduce the frozen V3 account economics")
    eligible = [
        row
        for row in rows
        if row["weight"] > 0
        and row["change_audit"]["changed_date_count"] > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
    ]
    selected = None
    if eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        plateau = [
            row for row in eligible if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor
        ]
        selected = min(plateau, key=lambda row: float(row["weight"]))
    extended = None
    if selected is not None:
        weight = float(selected["weight"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[weight], start=DEFAULT_FINAL_START, end=signal_end)
        extended = {
            "weight": weight,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(accounts[weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end),
        }
    passed = bool(extended and extended["gate"]["passed"] and extended["standout"]["passed"])
    material = {
        "artifact_type": "external_inventory_rerank_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_full_v3_inventory_external_residual_rerank_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_external_digests": {
            "global": global_snapshot["content_digest"],
            "sector": sector_snapshot["content_digest"],
            "macro": macro_snapshot["content_digest"],
            "sector_flow": flow_snapshot["content_digest"],
        },
        "candidate_return_label_count": len(labels),
        "prediction_audit": prediction_audit,
        "lambda_zero_reproduction": {
            "passed": lambda_zero_economic_match and rows[0]["change_audit"]["changed_date_count"] == 0,
            "changed_date_count": rows[0]["change_audit"]["changed_date_count"],
            "economic_nav_match": lambda_zero_nav_match,
            "executed_buy_sell_ledger_match": lambda_zero_trade_match,
            "full_account_output_digest_match": lambda_zero_full_digest_match,
            "full_digest_difference_expected_reason": (
                None
                if lambda_zero_full_digest_match
                else "shadow guard emits explicit skip-reason rows while preserving NAV and executed trades"
            ),
        },
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["weight"],
        "extended_readout": extended,
        "extended_readout_status": "reused_evaluation_not_untouched_due_prior_iterations",
        "candidate_pool_boundary": "frozen_v3_top20_inventory_only_no_pool_external_symbol",
        "future_feature_violations": 0,
        "future_label_violations": 0,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"external-inventory-rerank-{digest[:16]}", **material, "content_digest": digest}


def write_external_inventory_rerank_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("inventory rerank result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable inventory rerank result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
