from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

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

SCHEMA_VERSION = "external_adaptive_horizon_account_ablation.v1"


def _standardized_ridge_prediction(
    features: list[list[float]], targets: list[float], current: list[float], *, alpha: float
) -> float:
    if not features or len(features) != len(targets):
        raise ValueError("ridge training rows and targets must be non-empty and aligned")
    matrix = np.asarray(features, dtype=float)
    target = np.asarray(targets, dtype=float)
    current_row = np.asarray(current, dtype=float)
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales <= 1e-12] = 1.0
    standardized = (matrix - centers) / scales
    standardized_current = (current_row - centers) / scales
    design = np.column_stack([np.ones(len(matrix)), standardized])
    penalty = np.eye(design.shape[1], dtype=float) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(design.T @ design + penalty) @ design.T @ target
    return float(np.asarray([1.0, *standardized_current]) @ beta)


def _rank1_horizon_labels(snapshot: dict[str, Any], *, signal_end: date) -> dict[str, dict[str, Any]]:
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    labels: dict[str, dict[str, Any]] = {}
    for row in snapshot["baseline_output"]["order_ledger"]:
        if row.get("action") != "buy" or int(row.get("rank") or 0) != 1:
            continue
        signal_day = date.fromisoformat(str(row["signal_day"]))
        if signal_day > signal_end:
            continue
        symbol = str(row["symbol"])
        bars = bars_by_symbol.get(symbol) or []
        entry_index = next(
            (index for index, bar in enumerate(bars) if str(bar["day"]) == str(row["trade_day"])),
            None,
        )
        if entry_index is None or entry_index + 30 >= len(bars):
            continue
        entry = float(row["price"])
        returns = {
            horizon: float(bars[entry_index + horizon]["close"]) / entry - 1.0
            for horizon in (10, 20, 30)
        }
        labels[signal_day.isoformat()] = {
            "signal_day": signal_day.isoformat(),
            "actual_symbol": symbol,
            "available_day": str(bars[entry_index + 30]["day"]),
            "short_advantage": returns[10] - returns[20],
            "long_advantage": returns[30] - returns[20],
            "return_10d": returns[10],
            "return_20d": returns[20],
            "return_30d": returns[30],
        }
    return labels


def _expanding_horizon_predictions(
    *,
    original_picks_by_date: dict[str, list[dict[str, Any]]],
    labels: dict[str, dict[str, Any]],
    market_states: dict[str, dict[str, Any]],
    global_risk_residuals: dict[str, float],
    global_tech_residuals: dict[str, float],
    official_features: dict[str, dict[str, float]],
    sector_states: dict[str, dict[str, Any]],
    macro_states: dict[str, dict[str, Any]],
    feature_set: str,
    minimum_training_trades: int,
    l2_penalty: float,
) -> tuple[dict[str, dict[str, float] | None], dict[str, Any]]:
    features_by_day: dict[str, list[float]] = {}
    for day, picks in original_picks_by_date.items():
        rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
        features_by_day[day] = rank1_feature_vector(
            rank1,
            market_state=market_states[day],
            global_risk_z=global_risk_residuals.get(day, 0.0),
            global_tech_z=global_tech_residuals.get(day, 0.0),
            official_policy=official_features.get(day) or {},
            sector_state=sector_states.get(day) or {},
            macro_state=macro_states.get(day) or {},
            feature_set=feature_set,
        )
    predictions: dict[str, dict[str, float] | None] = {}
    fit_counts: dict[str, int] = {}
    for day in sorted(original_picks_by_date):
        ready = [
            (features_by_day[label_day], label)
            for label_day, label in labels.items()
            if label_day in features_by_day and date.fromisoformat(str(label["available_day"])) <= date.fromisoformat(day)
        ]
        fit_counts[day] = len(ready)
        if len(ready) < minimum_training_trades:
            predictions[day] = None
            continue
        training_features = [row[0] for row in ready]
        predictions[day] = {
            target: _standardized_ridge_prediction(
                training_features,
                [float(row[1][target]) for row in ready],
                features_by_day[day],
                alpha=l2_penalty,
            )
            for target in ("short_advantage", "long_advantage")
        }
    ready_rows = [row for row in predictions.values() if row is not None]
    return predictions, {
        "feature_set": feature_set,
        "minimum_training_trades": minimum_training_trades,
        "l2_penalty": l2_penalty,
        "ready_prediction_day_count": len(ready_rows),
        "warmup_prediction_day_count": len(predictions) - len(ready_rows),
        "last_fit_count": fit_counts[max(fit_counts)] if fit_counts else 0,
        "future_label_violations": 0,
    }


def _past_only_channel_percentiles(
    predictions: dict[str, dict[str, float] | None], *, minimum_prior_predictions: int
) -> dict[str, dict[str, float] | None]:
    prior: dict[str, list[float]] = defaultdict(list)
    result: dict[str, dict[str, float] | None] = {}
    for day in sorted(predictions):
        row = predictions[day]
        if row is None:
            result[day] = None
            continue
        if min((len(values) for values in prior.values()), default=0) < minimum_prior_predictions:
            result[day] = None
        else:
            result[day] = {
                channel: sum(value <= prediction for value in prior[channel]) / len(prior[channel])
                for channel, prediction in row.items()
            }
        for channel, prediction in row.items():
            prior[channel].append(float(prediction))
    return result


def run_external_adaptive_horizon_ablation(
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
    if design.get("status") not in {
        "frozen_before_round21_outcome_evaluation",
        "frozen_before_round22_outcome_evaluation",
    }:
        raise ValueError("adaptive horizon design must be frozen before outcome evaluation")
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
    labels = _rank1_horizon_labels(snapshot, signal_end=signal_end)
    model = design["model"]
    feature_sets = sorted({str(row["feature_set"]) for row in design["variants"]})
    predictions: dict[str, dict[str, dict[str, float] | None]] = {}
    percentiles: dict[str, dict[str, dict[str, float] | None]] = {}
    prediction_audit: dict[str, Any] = {}
    for feature_set in feature_sets:
        rows, audit = _expanding_horizon_predictions(
            original_picks_by_date=original_picks_by_date,
            labels=labels,
            market_states=market_states,
            global_risk_residuals=global_residuals,
            global_tech_residuals=tech_residuals,
            official_features=official_features,
            sector_states=sector_states,
            macro_states=macro_states,
            feature_set=feature_set,
            minimum_training_trades=int(model["minimum_completed_training_trades"]),
            l2_penalty=float(model["l2_penalty"]),
        )
        predictions[feature_set] = rows
        percentiles[feature_set] = _past_only_channel_percentiles(
            rows, minimum_prior_predictions=int(model["minimum_prior_live_predictions_for_quantile"])
        )
        prediction_audit[feature_set] = audit

    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))

    def replay(variant: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        feature_set = str(variant["feature_set"])
        for day in sorted(original_picks_by_date):
            picks = copy.deepcopy(original_picks_by_date[day])
            for pick in picks:
                slot = (day, int(float(pick.get("rank") or 0)))
                pick["shadow_baseline_buy_symbols"] = sorted(baseline_buy_symbols_by_slot.get(slot, set()))
            prediction = predictions[feature_set].get(day)
            percentile = percentiles[feature_set].get(day)
            if prediction is not None and percentile is not None:
                choices = [
                    ("short", 10, float(prediction["short_advantage"]), float(percentile["short_advantage"])),
                    ("long", 30, float(prediction["long_advantage"]), float(percentile["long_advantage"])),
                ]
                allowed_channels = {str(value) for value in variant.get("allowed_channels") or ("short", "long")}
                eligible = [
                    row
                    for row in choices
                    if row[0] in allowed_channels
                    if row[2] > float(variant.get("minimum_predicted_advantage") or 0.0)
                    and row[3] >= float(variant["advantage_percentile_min"])
                ]
                if eligible:
                    channel, horizon, predicted_advantage, selected_percentile = max(eligible, key=lambda row: row[2])
                    rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
                    rank1["target_horizon_days"] = horizon
                    rank1["external_horizon_channel"] = channel
                    rank1["external_horizon_predicted_advantage"] = predicted_advantage
                    rank1["external_horizon_past_only_percentile"] = selected_percentile
                    changes.append(
                        {
                            "signal_day": day,
                            "symbol": str(rank1.get("symbol") or ""),
                            "horizon": horizon,
                            "channel": channel,
                            "predicted_advantage": predicted_advantage,
                            "past_only_percentile": selected_percentile,
                        }
                    )
            selected.extend(picks)
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = f"external-adaptive-horizon-{variant['variant_id']}"
        replayed = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        return replayed, {
            "changed_horizon_day_count": len(changes),
            "short_horizon_day_count": sum(row["horizon"] == 10 for row in changes),
            "long_horizon_day_count": sum(row["horizon"] == 30 for row in changes),
            "changes": changes,
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
    accounts: dict[str, dict[str, Any]] = {}
    core_control_validation_return: float | None = None
    for variant in design["variants"]:
        account, trigger_audit = replay(variant)
        variant_id = str(variant["variant_id"])
        accounts[variant_id] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_extended": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        if variant.get("control_only"):
            core_control_validation_return = float(segments["validation"]["total_return"])
        rows.append(
            {
                "variant": variant,
                "trigger_audit": trigger_audit,
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
        if not row["variant"].get("control_only")
        and row["trigger_audit"]["changed_horizon_day_count"] > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
        and (
            core_control_validation_return is None
            or float(row["segments"]["validation"]["total_return"]) >= core_control_validation_return
        )
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
        selected = max(plateau, key=lambda row: float(row["variant"]["advantage_percentile_min"]))
    extended = None
    if selected is not None:
        variant_id = str(selected["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[variant_id], start=DEFAULT_FINAL_START, end=signal_end)
        extended = {
            "variant_id": variant_id,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(
                accounts[variant_id], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }
    passed = bool(extended and extended["gate"]["passed"] and extended["standout"]["passed"])
    material = {
        "artifact_type": "external_adaptive_horizon_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_expanding_ridge_horizon_replay_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_external_digests": {
            "global": global_snapshot["content_digest"],
            "sector": sector_snapshot["content_digest"],
            "macro": macro_snapshot["content_digest"],
        },
        "rank1_horizon_label_count": len(labels),
        "prediction_audit": prediction_audit,
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["variant"]["variant_id"],
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
    return {"artifact_id": f"external-adaptive-horizon-{digest[:16]}", **material, "content_digest": digest}


def write_external_adaptive_horizon_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("adaptive horizon result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable adaptive horizon result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
