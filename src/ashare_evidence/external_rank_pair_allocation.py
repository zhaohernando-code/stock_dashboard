from __future__ import annotations

import copy
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from ashare_evidence.external_adaptive_horizon import _standardized_ridge_prediction
from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
)
from ashare_evidence.external_context_macro_research import load_macro_research_snapshot, macro_state_by_decision_date
from ashare_evidence.external_context_sector_flow_research import (
    load_sector_flow_snapshot,
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
    _monthly_delta_summary,
    _non_degrade,
    _rank1_quality_scale,
    _segment_metrics,
    _standout,
    load_official_policy_events,
    official_policy_features_by_date,
)
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "external_rank_pair_allocation_account_ablation.v1"


def _pair_labels(
    snapshot: dict[str, Any],
    *,
    picks_by_date: dict[str, list[dict[str, Any]]],
    signal_end: date,
) -> dict[str, dict[str, Any]]:
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    labels: dict[str, dict[str, Any]] = {}
    for day, picks in picks_by_date.items():
        if date.fromisoformat(day) > signal_end:
            continue
        by_rank = {int(float(row.get("rank") or 0)): row for row in picks}
        if 1 not in by_rank or 2 not in by_rank:
            continue
        returns: dict[int, float] = {}
        available_days: list[str] = []
        for rank in (1, 2):
            bars = bars_by_symbol.get(str(by_rank[rank]["symbol"])) or []
            entry_index = next((index for index, bar in enumerate(bars) if str(bar["day"]) > day), None)
            if entry_index is None or entry_index + 20 >= len(bars):
                break
            returns[rank] = float(bars[entry_index + 20]["close"]) / float(bars[entry_index]["close"]) - 1.0
            available_days.append(str(bars[entry_index + 20]["day"]))
        if len(returns) == 2:
            labels[day] = {
                "signal_day": day,
                "available_day": max(available_days),
                "rank1_return_20d": returns[1],
                "rank2_return_20d": returns[2],
                "rank2_advantage": returns[2] - returns[1],
            }
    return labels


def _pair_features(
    rank1: dict[str, Any],
    rank2: dict[str, Any],
    *,
    market_state: dict[str, Any],
    sector_state: dict[str, Any],
    macro_state: dict[str, Any],
    official_feature: dict[str, float],
    sector_flow_state: dict[str, float] | None = None,
) -> tuple[list[float], list[float]]:
    def difference(field: str) -> float:
        return float(rank2.get(field) or 0.0) - float(rank1.get(field) or 0.0)

    core = [
        difference("score"),
        difference("return_5d_percentile"),
        difference("return_20d_percentile"),
        difference("turnover_rate_percentile"),
        difference("amount_10d_vs_20d_percentile"),
        difference("industry_return_20d_excess"),
        float(rank1.get("benchmark_return_20d") or 0.0),
    ]

    def sector_row(pick: dict[str, Any]) -> dict[str, Any]:
        sector_name = SW_L1_BY_SUBINDUSTRY.get(str(pick.get("industry_name") or ""), "")
        return (sector_state.get("by_sector_name") or {}).get(sector_name) or {}

    rank1_sector = sector_row(rank1)
    rank2_sector = sector_row(rank2)

    def macro_value(series_id: str, field: str) -> float:
        return float((macro_state.get(series_id) or {}).get(field) or 0.0)

    external = [
        float(rank2_sector.get("relative_5d") or 0.0) - float(rank1_sector.get("relative_5d") or 0.0),
        float(rank2_sector.get("relative_20d") or 0.0) - float(rank1_sector.get("relative_20d") or 0.0),
        float(rank2_sector.get("drawdown_20d") or 0.0) - float(rank1_sector.get("drawdown_20d") or 0.0),
        float(sector_state.get("breadth_5d") or 0.0),
        float(sector_state.get("breadth_20d") or 0.0),
        float(market_state.get("global_breadth_5d") or 0.0),
        float(market_state.get("global_breadth_20d") or 0.0),
        float(market_state.get("tech_relative_5d") or 0.0),
        float(market_state.get("tech_relative_20d") or 0.0),
        macro_value("VIXCLS", "value"),
        macro_value("VIXCLS", "change_5d"),
        macro_value("USDCNH_MID", "return_5d"),
        macro_value("UST_10Y", "change_5d"),
        macro_value("UST_10Y_MINUS_2Y", "value"),
        macro_value("SGE_AU9999", "return_5d"),
        macro_value("DCOILWTICO", "return_5d"),
        float(official_feature.get("fed_event_decay_5d") or 0.0),
        float(official_feature.get("us_policy_tech_risk_decay_20d") or 0.0),
        *[
            float((sector_flow_state or {}).get(field) or 0.0)
            for field in (
                "industry_positive_flow_breadth",
                "concept_positive_flow_breadth",
                "industry_mean_net_flow_ratio",
                "concept_mean_net_flow_ratio",
                "tech_positive_flow_breadth",
                "tech_mean_net_flow_ratio",
            )
        ],
        float(sector_flow_state is not None),
    ]
    return core, [*core, *external]


def _expanding_pair_predictions(
    *,
    picks_by_date: dict[str, list[dict[str, Any]]],
    labels: dict[str, dict[str, Any]],
    market_states: dict[str, dict[str, Any]],
    sector_states: dict[str, dict[str, Any]],
    macro_states: dict[str, dict[str, Any]],
    official_features: dict[str, dict[str, float]],
    sector_flow_states: dict[str, dict[str, float]] | None = None,
    minimum_training_trades: int,
    minimum_prior_predictions: int,
    l2_penalty: float,
) -> tuple[dict[str, dict[str, float] | None], dict[str, Any]]:
    features: dict[str, tuple[list[float], list[float]]] = {}
    for day, picks in picks_by_date.items():
        by_rank = {int(float(row.get("rank") or 0)): row for row in picks}
        features[day] = _pair_features(
            by_rank[1],
            by_rank[2],
            market_state=market_states[day],
            sector_state=sector_states[day],
            macro_state=macro_states[day],
            official_feature=official_features.get(day) or {},
            sector_flow_state=(sector_flow_states or {}).get(day),
        )
    predictions: dict[str, dict[str, float] | None] = {}
    prior_core: list[float] = []
    prior_full: list[float] = []
    fit_counts: dict[str, int] = {}
    for day in sorted(picks_by_date):
        ready_days = [
            label_day
            for label_day, label in labels.items()
            if label_day in features and date.fromisoformat(str(label["available_day"])) <= date.fromisoformat(day)
        ]
        fit_counts[day] = len(ready_days)
        if len(ready_days) < minimum_training_trades:
            predictions[day] = None
            continue
        targets = [float(labels[label_day]["rank2_advantage"]) for label_day in ready_days]
        core_prediction = _standardized_ridge_prediction(
            [features[label_day][0] for label_day in ready_days], targets, features[day][0], alpha=l2_penalty
        )
        full_prediction = _standardized_ridge_prediction(
            [features[label_day][1] for label_day in ready_days], targets, features[day][1], alpha=l2_penalty
        )
        if len(prior_core) < minimum_prior_predictions:
            predictions[day] = None
        else:
            predictions[day] = {
                "core_prediction": core_prediction,
                "full_prediction": full_prediction,
                "external_increment": full_prediction - core_prediction,
                "core_percentile": sum(value <= core_prediction for value in prior_core) / len(prior_core),
                "full_percentile": sum(value <= full_prediction for value in prior_full) / len(prior_full),
            }
        prior_core.append(core_prediction)
        prior_full.append(full_prediction)
    ready = [row for row in predictions.values() if row is not None]
    return predictions, {
        "ready_prediction_day_count": len(ready),
        "warmup_day_count": len(predictions) - len(ready),
        "last_fit_count": fit_counts[max(fit_counts)] if fit_counts else 0,
        "future_label_violations": 0,
    }


def run_external_rank_pair_allocation_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    macro_market_snapshot_path: Path,
    sector_flow_snapshot_path: Path | None = None,
    fed_policy_path: Path,
    federal_register_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") not in {
        "frozen_before_round24_outcome_evaluation",
        "frozen_before_round25_outcome_evaluation",
        "frozen_before_round26_outcome_evaluation",
        "frozen_before_round27_outcome_evaluation",
    }:
        raise ValueError("rank-pair allocation design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    global_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    macro_snapshot = load_macro_research_snapshot(macro_market_snapshot_path)
    flow_snapshot = None if sector_flow_snapshot_path is None else load_sector_flow_snapshot(sector_flow_snapshot_path)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    decision_dates = [date.fromisoformat(day) for day in picks_by_date]
    market_states = market_state_by_decision_date(global_snapshot["records"], decision_dates=decision_dates)
    sector_states = sector_state_by_decision_date(sector_snapshot["normalized"]["records"], decision_dates=decision_dates)
    macro_states = macro_state_by_decision_date(macro_snapshot["records"], decision_dates=decision_dates)
    flow_states = (
        {}
        if flow_snapshot is None
        else sector_flow_state_by_decision_date(flow_snapshot["normalized"]["records"], decision_dates=decision_dates)
    )
    if not all(set(states) == set(picks_by_date) for states in (market_states, sector_states, macro_states)):
        raise ValueError("external state coverage is incomplete")
    if design.get("requires_sector_flow"):
        required_from = date.fromisoformat(str(design["sector_flow_min_coverage_date"]))
        missing_required = [
            day for day in picks_by_date if date.fromisoformat(day) >= required_from and day not in flow_states
        ]
        if missing_required:
            raise ValueError(f"sector-flow state coverage is incomplete after required start: {missing_required[:3]}")
    official_events = load_official_policy_events(fed_path=fed_policy_path, federal_register_path=federal_register_path)
    official_features = official_policy_features_by_date(official_events, decision_dates=decision_dates)
    labels = _pair_labels(snapshot, picks_by_date=picks_by_date, signal_end=signal_end)
    model = design["model"]
    predictions, prediction_audit = _expanding_pair_predictions(
        picks_by_date=picks_by_date,
        labels=labels,
        market_states=market_states,
        sector_states=sector_states,
        macro_states=macro_states,
        official_features=official_features,
        sector_flow_states=flow_states,
        minimum_training_trades=int(model["minimum_completed_training_pairs"]),
        minimum_prior_predictions=int(model["minimum_prior_live_predictions_for_quantile"]),
        l2_penalty=float(model["l2_penalty"]),
    )
    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    baseline_buy_by_slot: dict[tuple[str, int], dict[str, Any]] = {}
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            slot = (str(row["signal_day"]), int(row["rank"]))
            baseline_buy_symbols_by_slot[slot].add(str(row["symbol"]))
            baseline_buy_by_slot[slot] = row
    overlay = snapshot["inputs"]["baseline_config"].get("rank1_quality_overlay") or {}

    def replay(variant: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        for day in sorted(picks_by_date):
            picks = copy.deepcopy(picks_by_date[day])
            by_rank = {int(float(row.get("rank") or 0)): row for row in picks}
            for rank, pick in by_rank.items():
                pick["shadow_baseline_buy_symbols"] = sorted(baseline_buy_symbols_by_slot.get((day, rank), set()))
            prediction = predictions.get(day)
            both_baseline_bought = bool(baseline_buy_symbols_by_slot.get((day, 1))) and bool(
                baseline_buy_symbols_by_slot.get((day, 2))
            )
            percentile_field = "core_percentile" if variant.get("control_only") else "full_percentile"
            predicted_field = "core_prediction" if variant.get("control_only") else "full_prediction"
            trigger = bool(
                prediction
                and both_baseline_bought
                and float(prediction[predicted_field]) > 0
                and float(prediction[percentile_field]) >= float(variant["advantage_percentile_min"])
                and (variant.get("control_only") or float(prediction["external_increment"]) > 0)
            )
            if trigger:
                transfer_units = 3.0 * float(variant["signal_budget_transfer_fraction"])
                if variant.get("execution_constrained_cash_nonincreasing"):
                    rank1_buy = baseline_buy_by_slot[(day, 1)]
                    rank2_buy = baseline_buy_by_slot[(day, 2)]
                    board_lot_size = int(variant.get("board_lot_size") or 100)
                    desired_transfer_cash = (
                        float(rank1_buy["target_notional_cny"]) + float(rank2_buy["target_notional_cny"])
                    ) * float(variant["signal_budget_transfer_fraction"])
                    rank2_lot_gross = float(rank2_buy["price"]) * board_lot_size
                    rank1_lot_gross = float(rank1_buy["price"]) * board_lot_size
                    added_rank2_lots = min(
                        int(desired_transfer_cash // rank2_lot_gross),
                        int(variant.get("maximum_added_rank2_lots") or 3),
                    )
                    removed_rank1_lots = (
                        int(math.ceil((added_rank2_lots * rank2_lot_gross) / rank1_lot_gross))
                        if added_rank2_lots > 0
                        else 0
                    )
                    maximum_removable_rank1_lots = max(int(rank1_buy["shares"]) // board_lot_size - 1, 0)
                    if removed_rank1_lots > maximum_removable_rank1_lots:
                        added_rank2_lots = 0
                        removed_rank1_lots = 0
                    if added_rank2_lots > 0:
                        desired_rank1_shares = int(rank1_buy["shares"]) - removed_rank1_lots * board_lot_size
                        desired_rank2_shares = int(rank2_buy["shares"]) + added_rank2_lots * board_lot_size
                        desired_rank1_target = desired_rank1_shares * float(rank1_buy["price"]) * 1.000001
                        desired_rank2_target = desired_rank2_shares * float(rank2_buy["price"]) * 1.000001
                        by_rank[1]["portfolio_weight"] = float(by_rank[1].get("portfolio_weight") or 1.0) * (
                            desired_rank1_target / float(rank1_buy["target_notional_cny"])
                        )
                        by_rank[2]["portfolio_weight"] = float(by_rank[2].get("portfolio_weight") or 1.0) * (
                            desired_rank2_target / float(rank2_buy["target_notional_cny"])
                        )
                    else:
                        trigger = False
                else:
                    quality_scale = _rank1_quality_scale(by_rank[1], overlay=overlay)
                    rank1_units = float(by_rank[1].get("rank_weight_multiplier") or 0.0) * quality_scale
                    rank2_units = float(by_rank[2].get("rank_weight_multiplier") or 0.0)
                    by_rank[1]["portfolio_weight"] = (rank1_units - transfer_units) / max(
                        float(by_rank[1]["rank_weight_multiplier"]) * quality_scale, 1e-12
                    )
                    by_rank[2]["portfolio_weight"] = (rank2_units + transfer_units) / max(
                        float(by_rank[2]["rank_weight_multiplier"]), 1e-12
                    )
            if trigger:
                changes.append(
                    {
                        "signal_day": day,
                        "rank1_symbol": str(by_rank[1]["symbol"]),
                        "rank2_symbol": str(by_rank[2]["symbol"]),
                        "full_prediction": prediction["full_prediction"],
                        "external_increment": prediction["external_increment"],
                        "transfer_units": transfer_units,
                        "execution_constrained": bool(variant.get("execution_constrained_cash_nonincreasing")),
                    }
                )
            selected.extend(picks)
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = f"external-rank-pair-{variant['variant_id']}"
        account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        return account, {"triggered_day_count": len(changes), "changes": changes}

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
        account, audit = replay(variant)
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
                "trigger_audit": audit,
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
        and row["trigger_audit"]["triggered_day_count"] > 0
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
        selected = min(
            plateau,
            key=lambda row: (
                float(row["variant"]["signal_budget_transfer_fraction"]),
                -float(row["variant"]["advantage_percentile_min"]),
            ),
        )
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
        "artifact_type": "external_rank_pair_allocation_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_expanding_rank_pair_allocation_replay_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_external_digests": {
            "global": global_snapshot["content_digest"],
            "sector": sector_snapshot["content_digest"],
            "macro": macro_snapshot["content_digest"],
            "sector_flow": None if flow_snapshot is None else flow_snapshot["content_digest"],
        },
        "rank_pair_label_count": len(labels),
        "prediction_audit": prediction_audit,
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["variant"]["variant_id"],
        "extended_readout": extended,
        "extended_readout_status": "reused_evaluation_not_untouched_due_prior_iterations",
        "v3_selection_changed": False,
        "future_feature_violations": 0,
        "future_label_violations": 0,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"external-rank-pair-{digest[:16]}", **material, "content_digest": digest}


def write_external_rank_pair_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("rank-pair result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable rank-pair result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
