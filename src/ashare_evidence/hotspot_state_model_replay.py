from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

from ashare_evidence.global_sector_state_account_ablation import (
    DEFAULT_FINAL_START,
    DEFAULT_TUNING_END,
    DEFAULT_VALIDATION_END,
    _group_by_date,
    _segment_metrics,
)
from ashare_evidence.hotspot_secondary_start import (
    DEFAULT_ACTIVE_TRANCHES,
    DEFAULT_HORIZON,
    DEFAULT_WEIGHTS,
    _signal_outcomes,
    build_sector_restart_state,
)
from ashare_evidence.hotspot_state_model import (
    COOLDOWN_SIGNAL_DAYS,
    L2_PENALTY,
    MAXIMUM_TRAINING_ROWS,
    MINIMUM_CONFIDENCE_PERCENTILE,
    MINIMUM_PRIOR_PREDICTION_DAYS,
    MINIMUM_PROBABILITY,
    MINIMUM_TRAINING_ROWS,
    PREFILTER_TOP_K,
    REFIT_SIGNAL_DAYS,
    SECTOR_FEATURE_NAMES,
    STOCK_FEATURE_NAMES,
    attach_forward_label,
    build_prefilter_rows,
    feature_vector,
    fit_standardized_model,
    past_only_percentile,
)
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

SCHEMA_VERSION = "hotspot_state_reestablishment_model.v1"
FEATURE_SETS = ("stock_only", "stock_plus_sector")
MINIMUM_VALIDATION_SIGNALS = 10


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_model_outcome_evaluation":
        raise ValueError("hotspot state model must be frozen before outcome evaluation")
    observed = {
        "weights": [float(value) for value in design["portfolio_carrier"]["weights"]],
        "prefilter_top_k": int(design["opportunity_set"]["stock_only_prefilter_top_k"]),
        "feature_sets": [str(row["id"]) for row in design["model_families"]],
        "l2": float(design["training"]["l2_penalty"]),
        "minimum_training": int(design["training"]["minimum_training_rows"]),
        "maximum_training": int(design["training"]["maximum_training_rows"]),
        "refit": int(design["training"]["refit_every_signal_days"]),
        "probability": float(design["selection"]["minimum_positive_probability"]),
        "percentile": float(design["selection"]["minimum_past_only_confidence_percentile"]),
        "prior_days": int(design["selection"]["minimum_prior_prediction_days_for_confidence"]),
        "cooldown": int(design["selection"]["same_symbol_cooldown_signal_days"]),
        "minimum_validation": int(design["evaluation"]["minimum_validation_signal_days"]),
    }
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "prefilter_top_k": PREFILTER_TOP_K,
        "feature_sets": list(FEATURE_SETS),
        "l2": L2_PENALTY,
        "minimum_training": MINIMUM_TRAINING_ROWS,
        "maximum_training": MAXIMUM_TRAINING_ROWS,
        "refit": REFIT_SIGNAL_DAYS,
        "probability": MINIMUM_PROBABILITY,
        "percentile": MINIMUM_CONFIDENCE_PERCENTILE,
        "prior_days": MINIMUM_PRIOR_PREDICTION_DAYS,
        "cooldown": COOLDOWN_SIGNAL_DAYS,
        "minimum_validation": MINIMUM_VALIDATION_SIGNALS,
    }
    if observed != expected:
        raise ValueError(f"hotspot state model implementation differs from frozen design: {observed}")


def expanding_model_selections(
    rows_by_day: dict[str, list[dict[str, Any]]],
    *,
    feature_set: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_rows = [row for day in sorted(rows_by_day) for row in rows_by_day[day]]
    model = None
    last_fit_signal_index: int | None = None
    last_selected_signal_index: dict[str, int] = {}
    prior_max_probabilities: list[float] = []
    selections: list[dict[str, Any]] = []
    fit_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for signal_index, day in enumerate(sorted(rows_by_day)):
        should_refit = model is None or (
            last_fit_signal_index is not None and signal_index - last_fit_signal_index >= REFIT_SIGNAL_DAYS
        )
        if should_refit:
            try:
                model = fit_standardized_model(all_rows, feature_set=feature_set, fit_day=day)
            except ValueError:
                model = None
            if model is not None:
                last_fit_signal_index = signal_index
                fit_rows.append(
                    {
                        "fit_day": day,
                        "training_row_count": model.training_row_count,
                        "maximum_label_available_day": model.maximum_label_available_day,
                    }
                )
        current_rows = rows_by_day[day]
        if model is None or not current_rows:
            prediction_rows.append({"signal_day": day, "status": "warmup"})
            continue
        scored = [(model.predict(feature_vector(row, feature_set=feature_set)), row) for row in current_rows]
        scored.sort(key=lambda value: (-value[0], str(value[1]["symbol"])))
        probability, candidate = scored[0]
        confidence_percentile = past_only_percentile(probability, prior_max_probabilities)
        selected = bool(
            probability >= MINIMUM_PROBABILITY
            and confidence_percentile is not None
            and confidence_percentile >= MINIMUM_CONFIDENCE_PERCENTILE
            and signal_index - last_selected_signal_index.get(str(candidate["symbol"]), -10_000)
            > COOLDOWN_SIGNAL_DAYS
        )
        prediction_rows.append(
            {
                "signal_day": day,
                "symbol": candidate["symbol"],
                "probability": probability,
                "past_only_confidence_percentile": confidence_percentile,
                "selected": selected,
                "fit_maximum_label_available_day": model.maximum_label_available_day,
            }
        )
        if selected:
            memory = candidate["memory_row"]
            pick = {key: copy.deepcopy(value) for key, value in memory.items() if key not in FORBIDDEN_RESULT_FIELDS}
            pick.update(
                {
                    "as_of_date": day,
                    "rank": 1,
                    "portfolio_weight": 1.0,
                    "rank_weight_multiplier": 1.0,
                    "target_horizon_days": DEFAULT_HORIZON,
                    "hotspot_state_model": feature_set,
                    "hotspot_state_probability": probability,
                    "hotspot_state_confidence_percentile": confidence_percentile,
                    "hotspot_state_features": {
                        name: candidate[name]
                        for name in (*STOCK_FEATURE_NAMES, *SECTOR_FEATURE_NAMES)
                    },
                }
            )
            selections.append(pick)
            last_selected_signal_index[str(candidate["symbol"])] = signal_index
        prior_max_probabilities.append(probability)
    return selections, {
        "feature_set": feature_set,
        "fit_count": len(fit_rows),
        "fit_rows": fit_rows,
        "prediction_rows": prediction_rows,
        "ready_prediction_day_count": sum(row.get("status") != "warmup" for row in prediction_rows),
        "selected_signal_day_count": len(selections),
        "future_label_violation_count": sum(
            str(row["maximum_label_available_day"]) > str(row["fit_day"]) for row in fit_rows
        ),
    }


def run_hotspot_state_reestablishment_model(
    *, execution_snapshot_path: Path, design_path: Path, signal_end: date
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    _validate_design(design)
    source = load_rolling_account_execution_snapshot(execution_snapshot_path)
    if source["artifact_id"] != design["data_contract"]["execution_snapshot_id"]:
        raise ValueError("execution snapshot does not match frozen hotspot state model design")
    snapshot, eligibility_audit = build_personal_eligible_execution_snapshot(source)
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
    registry: dict[str, dict[str, Any]] = {}
    rows_by_day: dict[str, list[dict[str, Any]]] = {}
    for signal_index, day in enumerate(sorted(inventory_by_date)):
        for row in inventory_by_date[day]:
            symbol = str(row["symbol"])
            current = registry.get(symbol)
            registry[symbol] = {
                "row": copy.deepcopy(row),
                "best_rank": min(int(float(row["rank"])), int(current["best_rank"]) if current else 999),
                "last_seen_day": day,
                "last_seen_signal_index": signal_index,
            }
        sector_states = build_sector_restart_state(
            signal_day=day,
            registry=registry,
            market_bars_by_symbol=market_bars,
            bar_indices_by_symbol=bar_indices,
            signal_index=signal_index,
        )
        causal_rows = build_prefilter_rows(
            signal_day=day,
            signal_index=signal_index,
            registry=registry,
            current_inventory=inventory_by_date[day],
            original_top3=original_by_date[day],
            sector_states=sector_states,
            market_bars_by_symbol=market_bars,
            bar_indices_by_symbol=bar_indices,
        )
        rows_by_day[day] = [
            attach_forward_label(row, market_bars_by_symbol=market_bars, bar_indices_by_symbol=bar_indices)
            for row in causal_rows
        ]

    sanitized_inventory = [
        {key: copy.deepcopy(value) for key, value in row.items() if key not in FORBIDDEN_RESULT_FIELDS}
        for day in sorted(inventory_by_date)
        for row in inventory_by_date[day]
    ]
    family_material: dict[str, dict[str, Any]] = {}
    for feature_set in FEATURE_SETS:
        selections, model_audit = expanding_model_selections(rows_by_day, feature_set=feature_set)
        sleeve_trial = copy.deepcopy(trial)
        sleeve_trial["selected_top_k"] = 1
        sleeve_trial["selected_top_k_picks_by_date"] = selections
        sleeve_trial["model_spec_id"] = f"hotspot_state_reestablishment_{feature_set}_v1"
        sleeve_run = {
            "artifact_id": f"hotspot-state-{feature_set}-{stable_digest(selections)[:12]}",
            "trial_diagnostics": [sleeve_trial],
        }
        sleeve_config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        sleeve_config.update(
            {
                "config_id": f"hotspot_state_{feature_set}_10d_10tranche_v1",
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
        sleeve_account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=sleeve_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=market_bars,
            candidate_inventory_rows=sanitized_inventory,
            candidate_configurations=[sleeve_config],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        family_material[feature_set] = {
            "selections": selections,
            "model_audit": model_audit,
            "sleeve_account": sleeve_account,
            "outcomes": _signal_outcomes(selections, market_bars, bar_indices),
            "signal_counts": {
                "tuning": sum(date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_TUNING_END for row in selections),
                "validation": sum(
                    DEFAULT_TUNING_END < date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_VALIDATION_END
                    for row in selections
                ),
                "extended": sum(date.fromisoformat(str(row["as_of_date"])) >= DEFAULT_FINAL_START for row in selections),
            },
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
    sleeve_validation_returns = {
        feature_set: _segment_metrics(
            family_material[feature_set]["sleeve_account"],
            start=segment_ranges["validation"][0],
            end=DEFAULT_VALIDATION_END,
        )["total_return"]
        for feature_set in FEATURE_SETS
    }
    accounts: dict[tuple[str, float], dict[str, Any]] = {}
    result_rows: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for family_order, feature_set in enumerate(FEATURE_SETS):
        sleeve = family_material[feature_set]["sleeve_account"]
        for weight in DEFAULT_WEIGHTS:
            blended = build_blended_nav_account(baseline, sleeve, weight=weight)
            accounts[(feature_set, weight)] = blended
            segments = {
                key: _blended_segment_metrics(blended, baseline, sleeve, weight=weight, start=start, end=end)
                for key, (start, end) in segment_ranges.items()
            }
            gates = {key: _risk_budget_gate(value, baseline_segments[key]) for key, value in segments.items()}
            monthly_delta = _monthly_delta_summary(
                blended, baseline, start=segment_ranges["validation"][0], end=DEFAULT_VALIDATION_END
            )
            sector_increment_passed = bool(
                feature_set == "stock_only"
                or float(sleeve_validation_returns[feature_set]) > float(sleeve_validation_returns["stock_only"])
            )
            row = {
                "feature_set": feature_set,
                "family_order": family_order,
                "weight": weight,
                "segments": segments,
                "gates": gates,
                "validation_monthly_delta": monthly_delta,
                "sector_increment_passed": sector_increment_passed,
            }
            result_rows.append(row)
            if (
                weight > 0.0
                and family_material[feature_set]["signal_counts"]["validation"] >= MINIMUM_VALIDATION_SIGNALS
                and gates["tuning"]["passed"]
                and gates["validation"]["passed"]
                and sector_increment_passed
                and float(monthly_delta["mean_monthly_return_delta"]) > 0.0
            ):
                eligible.append(row)

    selected = None
    if eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        selected = min(
            [row for row in eligible if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor],
            key=lambda row: (float(row["weight"]), int(row["family_order"])),
        )

    extended = None
    if selected is not None:
        feature_set = str(selected["feature_set"])
        weight = float(selected["weight"])
        sleeve = family_material[feature_set]["sleeve_account"]
        baseline_extended = _segment_metrics(baseline, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_extended = _blended_segment_metrics(
            accounts[(feature_set, weight)], baseline, sleeve, weight=weight, start=DEFAULT_FINAL_START, end=signal_end
        )
        extended = {
            "feature_set": feature_set,
            "weight": weight,
            "baseline": baseline_extended,
            "candidate": candidate_extended,
            "gate": _risk_budget_gate(candidate_extended, baseline_extended),
        }
    lambda_zero_match = all(
        stable_digest(accounts[(feature_set, 0.0)]["nav_rows"]) == stable_digest(baseline["nav_rows"])
        for feature_set in FEATURE_SETS
    )
    material = {
        "artifact_type": "hotspot_state_reestablishment_model",
        "schema_version": SCHEMA_VERSION,
        "status": "diagnostic_candidate_found_requires_new_holdout" if selected else "no_candidate_cleared_preselection",
        "claim_ceiling": "constrained_expanding_model_on_reused_history_not_v3_change",
        "source_execution_snapshot_id": source["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "personal_eligibility_audit": eligibility_audit,
        "opportunity_row_count": sum(len(rows) for rows in rows_by_day.values()),
        "lambda_zero_reproduction": {"passed": lambda_zero_match, "economic_nav_match": lambda_zero_match},
        "family_audits": {
            feature_set: {
                "feature_names": (
                    list(STOCK_FEATURE_NAMES)
                    if feature_set == "stock_only"
                    else [*STOCK_FEATURE_NAMES, *SECTOR_FEATURE_NAMES]
                ),
                "model_audit": family_material[feature_set]["model_audit"],
                "signal_counts": family_material[feature_set]["signal_counts"],
                "outcomes": family_material[feature_set]["outcomes"],
                "sleeve_summary": family_material[feature_set]["sleeve_account"]["summary"],
                "validation_sleeve_total_return": sleeve_validation_returns[feature_set],
                "selection_digest": stable_digest(family_material[feature_set]["selections"]),
                "forbidden_result_field_count": sum(
                    key in FORBIDDEN_RESULT_FIELDS
                    for row in family_material[feature_set]["selections"]
                    for key in row
                ),
                "same_day_v3_top3_overlap_count": sum(
                    str(row["symbol"])
                    in {str(value["symbol"]) for value in original_by_date[str(row["as_of_date"])]}
                    for row in family_material[feature_set]["selections"]
                ),
            }
            for feature_set in FEATURE_SETS
        },
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": result_rows,
        "selection_before_extended_readout": (
            None if selected is None else {"feature_set": selected["feature_set"], "weight": selected["weight"]}
        ),
        "extended_readout": extended,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "independent_holdout_status": "missing",
        "promotion_allowed": False,
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
        "runtime_publish_required": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"hotspot-state-model-{digest[:16]}", **material, "content_digest": digest}


def write_hotspot_state_model_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("hotspot state model result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable hotspot state model result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
