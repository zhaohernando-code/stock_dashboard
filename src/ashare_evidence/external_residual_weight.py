from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.external_adaptive_horizon import _standardized_ridge_prediction
from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
)
from ashare_evidence.external_context_macro_research import load_macro_research_snapshot, macro_state_by_decision_date
from ashare_evidence.external_context_sector_market_research import (
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
    _monthly_delta_summary,
    _non_degrade,
    _segment_metrics,
    _standout,
    build_past_only_global_risk_residuals,
    build_past_only_sector_residuals,
    load_official_policy_events,
    official_policy_features_by_date,
    rank1_feature_vector,
)
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "external_residual_weight_account_ablation.v1"


def _rank1_return_labels(snapshot: dict[str, Any], *, signal_end: date) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for row in snapshot["baseline_output"]["order_ledger"]:
        if row.get("action") != "sell" or int(row.get("rank") or 0) != 1:
            continue
        signal_day = date.fromisoformat(str(row["signal_day"]))
        if signal_day > signal_end:
            continue
        labels[signal_day.isoformat()] = {
            "signal_day": signal_day.isoformat(),
            "actual_symbol": str(row["symbol"]),
            "available_day": str(row["trade_day"]),
            "realized_return": float(row["return"]),
        }
    return labels


def _expanding_external_residuals(
    *,
    original_picks_by_date: dict[str, list[dict[str, Any]]],
    labels: dict[str, dict[str, Any]],
    market_states: dict[str, dict[str, Any]],
    global_risk_residuals: dict[str, float],
    global_tech_residuals: dict[str, float],
    official_features: dict[str, dict[str, float]],
    sector_states: dict[str, dict[str, Any]],
    macro_states: dict[str, dict[str, Any]],
    minimum_training_trades: int,
    minimum_prior_predictions: int,
    l2_penalty: float,
    residual_z_cap: float,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    core_by_day: dict[str, list[float]] = {}
    full_by_day: dict[str, list[float]] = {}
    for day, picks in original_picks_by_date.items():
        rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
        common = {
            "market_state": market_states[day],
            "global_risk_z": global_risk_residuals.get(day, 0.0),
            "global_tech_z": global_tech_residuals.get(day, 0.0),
            "official_policy": official_features.get(day) or {},
            "sector_state": sector_states.get(day) or {},
            "macro_state": macro_states.get(day) or {},
        }
        core_by_day[day] = rank1_feature_vector(rank1, feature_set="compressed_core_only", **common)
        full_by_day[day] = rank1_feature_vector(
            rank1, feature_set="compressed_core_plus_global_sector_macro", **common
        )
    raw_residuals: dict[str, float | None] = {}
    standardized: dict[str, float | None] = {}
    prior_predictions: list[float] = []
    fit_counts: dict[str, int] = {}
    for day in sorted(original_picks_by_date):
        ready_days = [
            label_day
            for label_day, label in labels.items()
            if label_day in core_by_day and date.fromisoformat(str(label["available_day"])) <= date.fromisoformat(day)
        ]
        fit_counts[day] = len(ready_days)
        if len(ready_days) < minimum_training_trades:
            raw_residuals[day] = None
            standardized[day] = None
            continue
        targets = [float(labels[label_day]["realized_return"]) for label_day in ready_days]
        core_prediction = _standardized_ridge_prediction(
            [core_by_day[label_day] for label_day in ready_days],
            targets,
            core_by_day[day],
            alpha=l2_penalty,
        )
        full_prediction = _standardized_ridge_prediction(
            [full_by_day[label_day] for label_day in ready_days],
            targets,
            full_by_day[day],
            alpha=l2_penalty,
        )
        residual = full_prediction - core_prediction
        raw_residuals[day] = residual
        if len(prior_predictions) < minimum_prior_predictions or pstdev(prior_predictions) <= 1e-12:
            standardized[day] = None
        else:
            z_score = (residual - mean(prior_predictions)) / pstdev(prior_predictions)
            standardized[day] = max(-residual_z_cap, min(residual_z_cap, z_score))
        prior_predictions.append(residual)
    ready = [value for value in standardized.values() if value is not None]
    return standardized, {
        "minimum_training_trades": minimum_training_trades,
        "minimum_prior_predictions": minimum_prior_predictions,
        "l2_penalty": l2_penalty,
        "residual_z_cap": residual_z_cap,
        "ready_residual_day_count": len(ready),
        "warmup_day_count": len(standardized) - len(ready),
        "last_fit_count": fit_counts[max(fit_counts)] if fit_counts else 0,
        "minimum_residual_z": min(ready, default=None),
        "maximum_residual_z": max(ready, default=None),
        "future_label_violations": 0,
    }


def run_external_residual_weight_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    macro_market_snapshot_path: Path,
    fed_policy_path: Path,
    federal_register_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round23_outcome_evaluation":
        raise ValueError("external residual weight design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    global_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    macro_snapshot = load_macro_research_snapshot(macro_market_snapshot_path)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    decision_dates = [date.fromisoformat(day) for day in original_picks_by_date]
    market_states = market_state_by_decision_date(global_snapshot["records"], decision_dates=decision_dates)
    sector_states = sector_state_by_decision_date(sector_snapshot["normalized"]["records"], decision_dates=decision_dates)
    macro_states = macro_state_by_decision_date(macro_snapshot["records"], decision_dates=decision_dates)
    if not all(set(states) == set(original_picks_by_date) for states in (market_states, sector_states, macro_states)):
        raise ValueError("external state coverage is incomplete")
    tech_residuals, tech_audit = build_past_only_sector_residuals(
        inventory_by_date=inventory_by_date, market_states=market_states
    )
    global_residuals, global_audit = build_past_only_global_risk_residuals(
        inventory_by_date=inventory_by_date, market_states=market_states
    )
    official_events = load_official_policy_events(fed_path=fed_policy_path, federal_register_path=federal_register_path)
    official_features = official_policy_features_by_date(official_events, decision_dates=decision_dates)
    labels = _rank1_return_labels(snapshot, signal_end=signal_end)
    model = design["model"]
    residuals, residual_audit = _expanding_external_residuals(
        original_picks_by_date=original_picks_by_date,
        labels=labels,
        market_states=market_states,
        global_risk_residuals=global_residuals,
        global_tech_residuals=tech_residuals,
        official_features=official_features,
        sector_states=sector_states,
        macro_states=macro_states,
        minimum_training_trades=int(model["minimum_completed_training_trades"]),
        minimum_prior_predictions=int(model["minimum_prior_live_predictions_for_standardization"]),
        l2_penalty=float(model["l2_penalty"]),
        residual_z_cap=float(model["residual_z_cap"]),
    )
    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))

    def replay(weight: float) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        cap = float(design["carrier"]["maximum_absolute_weight_adjustment"])
        for day in sorted(original_picks_by_date):
            picks = copy.deepcopy(original_picks_by_date[day])
            for pick in picks:
                slot = (day, int(float(pick.get("rank") or 0)))
                pick["shadow_baseline_buy_symbols"] = sorted(baseline_buy_symbols_by_slot.get(slot, set()))
            residual_z = residuals.get(day)
            if weight > 0 and residual_z is not None:
                contribution = max(-cap, min(cap, weight * float(residual_z)))
                rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
                rank1["portfolio_weight"] = float(rank1.get("portfolio_weight") or 1.0) * (1.0 + contribution)
                rank1["external_residual_z"] = residual_z
                rank1["external_residual_weight"] = weight
                rank1["external_residual_contribution"] = contribution
                if abs(contribution) > 1e-12:
                    changes.append(
                        {
                            "signal_day": day,
                            "symbol": str(rank1.get("symbol") or ""),
                            "residual_z": residual_z,
                            "contribution": contribution,
                        }
                    )
            selected.extend(picks)
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=weight)
        candidate_run["artifact_id"] = f"external-residual-weight-{weight:.3f}"
        account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        return account, {
            "changed_weight_day_count": len(changes),
            "positive_adjustment_day_count": sum(row["contribution"] > 0 for row in changes),
            "negative_adjustment_day_count": sum(row["contribution"] < 0 for row in changes),
            "cap_hit_day_count": sum(abs(row["contribution"]) >= cap - 1e-12 for row in changes),
            "mean_absolute_contribution": mean(abs(row["contribution"]) for row in changes) if changes else 0.0,
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
        account, change_audit = replay(weight)
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
                "change_audit": change_audit,
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
    eligible = [
        row
        for row in rows
        if row["weight"] > 0 and row["gates"]["tuning"]["passed"] and row["gates"]["validation"]["passed"]
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
        "artifact_type": "external_residual_weight_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_expanding_core_plus_external_residual_weight_replay_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_external_digests": {
            "global": global_snapshot["content_digest"],
            "sector": sector_snapshot["content_digest"],
            "macro": macro_snapshot["content_digest"],
        },
        "rank1_return_label_count": len(labels),
        "residual_audit": residual_audit,
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["weight"],
        "extended_readout": extended,
        "extended_readout_status": "reused_evaluation_not_untouched_due_prior_iterations",
        "external_data_audit": {
            "global_risk_residual_digest": stable_digest(global_audit),
            "global_tech_residual_digest": stable_digest(tech_audit),
            "future_feature_violations": 0,
            "future_label_violations": 0,
        },
        "v3_selection_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"external-residual-weight-{digest[:16]}", **material, "content_digest": digest}


def write_external_residual_weight_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("external residual result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable external residual result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
