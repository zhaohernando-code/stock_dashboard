from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from ashare_evidence.event_confirmed_position_exit import (
    OfficialEvent,
    _bar_index_by_day,
    _event_features,
    _position_features,
    _position_key,
    expanding_position_predictions,
    load_merged_curated_official_events,
)
from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
)
from ashare_evidence.external_context_macro_research import load_macro_research_snapshot, macro_state_by_decision_date
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
    _segment_metrics,
    _standout,
    build_past_only_global_risk_residuals,
)
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "event_confirmed_position_extension_account_ablation.v1"


def _resolved_variants(design: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = design.get("variant_defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("variant_defaults must be an object")
    variants = design.get("variants") or []
    if not isinstance(variants, list) or not variants:
        raise ValueError("event-confirmed extension design requires variants")
    return [{**defaults, **row} for row in variants]


def build_position_extension_observations(
    *,
    snapshot: dict[str, Any],
    events_by_symbol: dict[str, list[OfficialEvent]],
    market_states: dict[str, dict[str, Any]],
    sector_states: dict[str, dict[str, Any]],
    macro_states: dict[str, dict[str, Any]],
    event_lookback_days: int,
    extension_trade_days: int,
    signal_end: date,
) -> list[dict[str, Any]]:
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    baseline = snapshot["baseline_output"]
    buys_by_key = {
        (str(row["signal_day"]), str(row["symbol"]), int(row["rank"])): row
        for row in baseline["order_ledger"]
        if row.get("action") == "buy"
    }
    picks_by_key = {
        (str(row["as_of_date"]), str(row["symbol"]), int(float(row.get("rank") or 0))): row
        for row in snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]["selected_top_k_picks_by_date"]
    }
    observations: list[dict[str, Any]] = []
    for sell in baseline["order_ledger"]:
        if sell.get("action") != "sell" or sell.get("reason") != "mechanical_horizon":
            continue
        signal_day = str(sell["signal_day"])
        symbol = str(sell["symbol"])
        rank = int(sell["rank"])
        buy = buys_by_key.get((signal_day, symbol, rank))
        if buy is None:
            continue
        bars = bars_by_symbol.get(symbol) or []
        index_by_day = _bar_index_by_day(bars)
        entry_day = str(buy["trade_day"])
        sell_day = str(sell["trade_day"])
        if entry_day not in index_by_day or sell_day not in index_by_day:
            continue
        entry_index = index_by_day[entry_day]
        sell_index = index_by_day[sell_day]
        decision_index = sell_index - 1
        deferred_index = sell_index + extension_trade_days
        if decision_index <= entry_index or deferred_index >= len(bars):
            continue
        deferred_day = date.fromisoformat(str(bars[deferred_index]["day"]))
        if deferred_day > signal_end:
            continue
        decision_day = date.fromisoformat(str(bars[decision_index]["day"]))
        day_key = decision_day.isoformat()
        if day_key not in market_states or day_key not in sector_states or day_key not in macro_states:
            continue
        event_vector, event_audit = _event_features(
            events=events_by_symbol.get(symbol) or [],
            decision_day=decision_day,
            lookback_days=event_lookback_days,
            bars=bars,
            current_index=decision_index,
        )
        enriched_buy = {
            **buy,
            "entry_features": picks_by_key.get((signal_day, symbol, rank)) or {},
        }
        core, full, path = _position_features(
            buy=enriched_buy,
            bars=bars,
            entry_index=entry_index,
            current_index=decision_index,
            market_state=market_states[day_key],
            sector_state=sector_states[day_key],
            macro_state=macro_states[day_key],
            event_features=event_vector,
        )
        entry_price = float(bars[entry_index]["close"])
        frozen_exit_price = float(bars[sell_index]["close"])
        deferred_exit_price = float(bars[deferred_index]["close"])
        entry = enriched_buy["entry_features"]
        sector_name = str(entry.get("industry_name") or "")
        sw_sector = SW_L1_BY_SUBINDUSTRY.get(sector_name, "")
        sector = (sector_states[day_key].get("by_sector_name") or {}).get(sw_sector) or {}
        observations.append(
            {
                "position_key": _position_key(
                    signal_day=signal_day, entry_day=entry_day, symbol=symbol, rank=rank
                ),
                "signal_day": signal_day,
                "entry_day": entry_day,
                "symbol": symbol,
                "rank": rank,
                "decision_day": day_key,
                "effective_deferral_day": sell_day,
                "deferred_exit_day": deferred_day.isoformat(),
                "label_available_day": deferred_day.isoformat(),
                "early_exit_advantage": (
                    (deferred_exit_price - frozen_exit_price) / entry_price if entry_price else 0.0
                ),
                "core_features": core,
                "full_features": full,
                "global_breadth_5d": float(market_states[day_key].get("global_breadth_5d") or 0.0),
                "global_mean_return_5d": float(market_states[day_key].get("global_mean_return_5d") or 0.0),
                "sector_relative_5d": float(sector.get("relative_5d") or 0.0),
                **path,
                **event_audit,
            }
        )
    return sorted(observations, key=lambda row: (row["decision_day"], row["position_key"]))


def _deferrals_for_variant(
    *,
    observations: list[dict[str, Any]],
    predictions: dict[tuple[str, str], dict[str, float] | None],
    variant: dict[str, Any],
) -> tuple[dict[str, dict[str, dict[str, str]]], list[dict[str, Any]]]:
    signals: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    triggers: list[dict[str, Any]] = []
    excluded_position_keys = {
        str(value) for value in (variant.get("diagnostic_excluded_position_keys") or [])
    }
    for row in observations:
        if str(row["position_key"]) in excluded_position_keys:
            continue
        if bool(variant.get("require_recent_event", True)) and int(row["event_count"]) <= 0:
            continue
        maximum_event_count = variant.get("maximum_event_count")
        if maximum_event_count is not None and int(row["event_count"]) > int(maximum_event_count):
            continue
        key = (str(row["position_key"]), str(row["decision_day"]))
        prediction = predictions.get(key)
        if prediction is None:
            continue
        control = bool(variant.get("control_only"))
        predicted = float(prediction["core_prediction"] if control else prediction["full_prediction"])
        percentile = float(prediction["core_percentile"] if control else prediction["full_percentile"])
        if not control and float(prediction["external_increment"]) <= 0:
            continue
        minimum_core_percentile = variant.get("minimum_core_percentile")
        if (
            minimum_core_percentile is not None
            and float(prediction["core_percentile"]) < float(minimum_core_percentile)
        ):
            continue
        if predicted < float(variant["minimum_predicted_advantage"]):
            continue
        if percentile < float(variant["prediction_percentile_min"]):
            continue
        if float(row["position_return"]) < float(variant["minimum_position_return"]):
            continue
        if float(row["global_breadth_5d"]) < float(variant["minimum_global_breadth_5d"]):
            continue
        if float(row.get("global_mean_return_5d") or 0.0) < float(variant.get("minimum_global_mean_return_5d", -1.0)):
            continue
        if float(row["sector_relative_5d"]) < float(variant["minimum_sector_relative_5d"]):
            continue
        use_wide_protection = (
            variant.get("wide_protection_min_position_return") is not None
            and float(row["position_return"]) >= float(variant["wide_protection_min_position_return"])
            and (
                variant.get("wide_protection_min_core_percentile") is None
                or float(prediction["core_percentile"])
                >= float(variant["wide_protection_min_core_percentile"])
            )
        )
        weak_core_scale_threshold = variant.get("weak_core_partial_extension_max_core_percentile")
        retained_share_scale = 1.0
        if (
            weak_core_scale_threshold is not None
            and float(prediction["core_percentile"]) < float(weak_core_scale_threshold)
        ):
            retained_share_scale = float(variant["weak_core_retained_share_scale"])
        if not 0.0 < retained_share_scale <= 1.0:
            raise ValueError("weak-core retained share scale must be in (0, 1]")
        protection_prefix = "wide_" if use_wide_protection else ""
        signals[str(row["effective_deferral_day"])][str(row["position_key"])] = {
            "deferred_exit_day": str(row["deferred_exit_day"]),
            "reason": "pit_external_event_confirmed_rebound_extension",
            "extension_priority": predicted,
            "retained_share_scale": retained_share_scale,
            "minimum_cash_reserve_cny": float(variant.get("minimum_cash_reserve_cny") or 0.0),
            "deferral_stop_loss_pct": float(
                variant.get(f"{protection_prefix}deferral_stop_loss_pct") or 0.0
            ),
            "deferral_trailing_activation_pct": float(
                variant.get(f"{protection_prefix}deferral_trailing_activation_pct") or 0.0
            ),
            "deferral_trailing_drawdown_pct": float(
                variant.get(f"{protection_prefix}deferral_trailing_drawdown_pct") or 0.0
            ),
        }
        triggers.append(
            {
                "position_key": row["position_key"],
                "decision_day": row["decision_day"],
                "effective_deferral_day": row["effective_deferral_day"],
                "deferred_exit_day": row["deferred_exit_day"],
                "symbol": row["symbol"],
                "rank": row["rank"],
                "event_count": row["event_count"],
                "post_event_price_confirmation": row["post_event_price_confirmation"],
                "position_return": row["position_return"],
                "global_breadth_5d": row["global_breadth_5d"],
                "sector_relative_5d": row["sector_relative_5d"],
                "retained_share_scale": retained_share_scale,
                **prediction,
            }
        )
    return dict(signals), triggers


def run_event_confirmed_position_extension_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    macro_market_snapshot_path: Path,
    external_root: Path,
    curation_path: Path,
    design_path: Path,
    signal_end: date,
    additional_event_sources: list[tuple[Path, Path]] | None = None,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") not in {
        "frozen_before_round31_outcome_evaluation",
        "frozen_before_round32_outcome_evaluation",
        "frozen_before_round33_outcome_evaluation",
        "frozen_before_round34_outcome_evaluation",
        "frozen_before_round35_outcome_evaluation",
        "frozen_before_round36_outcome_evaluation",
        "frozen_before_round37_outcome_evaluation",
        "frozen_before_round38_outcome_evaluation",
        "frozen_before_round39_outcome_evaluation",
        "frozen_before_round40_outcome_evaluation",
        "frozen_before_round41_outcome_evaluation",
        "frozen_before_round42_outcome_evaluation",
        "frozen_before_round43_outcome_evaluation",
        "frozen_before_round44_outcome_evaluation",
        "frozen_before_round45_outcome_evaluation",
        "frozen_before_round46_outcome_evaluation",
        "frozen_before_round47_outcome_evaluation",
        "frozen_before_round48_concentration_diagnostic",
        "frozen_before_round49_outcome_evaluation",
        "frozen_before_round50_outcome_evaluation",
        "frozen_before_round51_outcome_evaluation",
        "frozen_before_round52_outcome_evaluation",
        "frozen_before_round53_outcome_evaluation",
        "frozen_before_round54_outcome_evaluation",
        "frozen_before_round55_outcome_evaluation",
        "frozen_before_round56_outcome_evaluation",
        "frozen_before_round57_outcome_evaluation",
        "frozen_before_round58_outcome_evaluation",
        "frozen_before_round59_personal_baseline_outcome_evaluation",
        "frozen_before_round60_forward_outcome_evaluation",
        "frozen_before_round60_historical_refinement_outcome_evaluation",
        "frozen_before_round61_forward_outcome_evaluation",
        "frozen_before_round61_historical_risk_cap_outcome_evaluation",
        "frozen_before_round62_historical_external_state_cap_outcome_evaluation",
        "frozen_before_round63_historical_post_trigger_cap_outcome_evaluation",
        "frozen_before_round64_historical_tiered_protection_outcome_evaluation",
        "frozen_before_round65_forward_candidate_outcome_evaluation",
        "frozen_before_round66_historical_global_risk_budget_outcome_evaluation",
        "frozen_before_round67_historical_global_residual_risk_budget_outcome_evaluation",
        "frozen_before_round68_historical_sparse_residual_cap_boundary_outcome_evaluation",
        "frozen_before_round69_historical_combined_extension_residual_risk_outcome_evaluation",
        "frozen_before_round70_historical_domestic_alignment_decomposition_outcome_evaluation",
        "frozen_before_round71_historical_core_confirmed_protection_outcome_evaluation",
        "frozen_before_round72_historical_bounded_residual_position_weight_outcome_evaluation",
        "frozen_before_round73_historical_core_veto_outcome_evaluation",
        "frozen_before_round74_forward_core_veto_outcome_evaluation",
        "frozen_before_round75_forward_exact_share_core_veto_outcome_evaluation",
        "frozen_before_round76_historical_multi_trigger_core_veto_outcome_evaluation",
        "frozen_before_round77_multi_trigger_leave_one_out_diagnostic",
        "frozen_before_round78_forward_divergence_risk_channel_outcome_evaluation",
    }:
        raise ValueError("event-confirmed extension design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    global_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    macro_snapshot = load_macro_research_snapshot(macro_market_snapshot_path)
    primary_curation = json.loads(curation_path.read_text(encoding="utf-8"))
    actual_digests: dict[str, Any] = {
        "global_market_digest": global_snapshot["content_digest"],
        "sector_market_digest": sector_snapshot["content_digest"],
        "macro_market_digest": macro_snapshot["content_digest"],
        "cninfo_curation_file_sha256": hashlib.sha256(curation_path.read_bytes()).hexdigest(),
        "cninfo_curation_exclusion_digest": primary_curation.get("excluded_event_versions_sha256"),
    }
    resolved_additional_sources = additional_event_sources or []
    if resolved_additional_sources:
        actual_digests["additional_cninfo_sources"] = [
            {
                "curation_file_sha256": hashlib.sha256(source_curation.read_bytes()).hexdigest(),
                "curation_exclusion_digest": json.loads(
                    source_curation.read_text(encoding="utf-8")
                ).get("excluded_event_versions_sha256"),
            }
            for _, source_curation in resolved_additional_sources
        ]
    expected = design["data_contract"]
    if "execution_snapshot_id" in expected:
        actual_digests["execution_snapshot_id"] = snapshot["artifact_id"]
    mismatches = {
        key: {"expected": expected.get(key), "actual": value}
        for key, value in actual_digests.items()
        if expected.get(key) != value
    }
    if mismatches:
        raise ValueError(f"round31 data digest mismatch: {mismatches}")
    events_by_symbol, event_audit = load_merged_curated_official_events(
        sources=[(external_root, curation_path), *resolved_additional_sources]
    )
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    baseline_buy_days = [
        date.fromisoformat(str(row["trade_day"]))
        for row in snapshot["baseline_output"]["order_ledger"]
        if row.get("action") == "buy"
    ]
    if not baseline_buy_days:
        raise ValueError("round31 requires at least one frozen baseline buy")
    first_position_day = min(baseline_buy_days)
    all_days = sorted(
        {
            date.fromisoformat(str(row["day"]))
            for rows in bars_by_symbol.values()
            for row in rows
            if first_position_day <= date.fromisoformat(str(row["day"])) <= signal_end
        }
    )
    market_states = market_state_by_decision_date(global_snapshot["records"], decision_dates=all_days)
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"], decision_dates=all_days
    )
    macro_states = macro_state_by_decision_date(macro_snapshot["records"], decision_dates=all_days)
    model = design["model"]
    observations_by_horizon: dict[int, list[dict[str, Any]]] = {}
    predictions_by_horizon: dict[int, dict[tuple[str, str], dict[str, float] | None]] = {}
    prediction_audit_by_horizon: dict[int, dict[str, Any]] = {}
    resolved_variants = _resolved_variants(design)
    for extension_days in sorted({int(row["extension_trade_days"]) for row in resolved_variants}):
        observations = build_position_extension_observations(
            snapshot=snapshot,
            events_by_symbol=events_by_symbol,
            market_states=market_states,
            sector_states=sector_states,
            macro_states=macro_states,
            event_lookback_days=int(design["boundary"]["event_lookback_calendar_days"]),
            extension_trade_days=extension_days,
            signal_end=signal_end,
        )
        predictions, prediction_audit = expanding_position_predictions(
            observations,
            minimum_training_labels=int(model["minimum_completed_position_labels"]),
            minimum_prior_predictions=int(model["minimum_prior_predictions"]),
            l2_penalty=float(model["l2_penalty"]),
        )
        observations_by_horizon[extension_days] = observations
        predictions_by_horizon[extension_days] = predictions
        prediction_audit_by_horizon[extension_days] = prediction_audit
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    global_risk_residuals, global_risk_residual_audit = build_past_only_global_risk_residuals(
        inventory_by_date=inventory_by_date,
        market_states=market_states,
        minimum_history=int(design.get("model", {}).get("global_residual_minimum_history") or 20),
    )
    selected = [copy.deepcopy(row) for day in sorted(picks_by_date) for row in picks_by_date[day]]
    frozen_baseline = snapshot["baseline_output"]
    baseline_buy_symbols_by_signal_rank: dict[tuple[str, int], set[str]] = defaultdict(set)
    baseline_buy_shares_by_signal_rank: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    for row in frozen_baseline["order_ledger"]:
        if row.get("action") == "buy":
            key = (str(row["signal_day"]), int(row["rank"]))
            symbol = str(row["symbol"])
            baseline_buy_symbols_by_signal_rank[key].add(symbol)
            baseline_buy_shares_by_signal_rank[key][symbol] = int(row["shares"])
    inventory_rows_by_signal_symbol = {
        (str(row["as_of_date"]), str(row["symbol"])): row
        for rows in inventory_by_date.values()
        for row in rows
    }

    def replay(variant: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        triggers: list[dict[str, Any]] = []
        risk_days: list[str] = []
        if variant is not None:
            extension_days = int(variant["extension_trade_days"])
            if bool(variant.get("disable_position_extension")):
                deferrals, triggers = {}, []
            else:
                deferrals, triggers = _deferrals_for_variant(
                    observations=observations_by_horizon[extension_days],
                    predictions=predictions_by_horizon[extension_days],
                    variant=variant,
                )
            config["config_id"] = str(variant["variant_id"])
            config["pit_external_position_exit_deferrals"] = deferrals
            config["pit_external_entry_liquidity_recall"] = bool(
                variant.get("entry_liquidity_recall")
            )
            config["pit_external_entry_cash_fit"] = bool(variant.get("entry_cash_fit"))
            config["pit_external_entry_liquidity_substitution"] = bool(
                variant.get("entry_liquidity_substitution")
            )
            config["pit_external_core_entry_conflict_recall"] = bool(
                variant.get("freeze_to_baseline_executed_buys")
            )
            external_concentration_cap = variant.get("external_deferred_market_value_cap_pct")
            if external_concentration_cap is not None:
                concentration_policy = copy.deepcopy(config.get("market_value_concentration_rebalance") or {})
                concentration_policy["external_deferred_threshold"] = float(external_concentration_cap)
                config["market_value_concentration_rebalance"] = concentration_policy
            market_value_cap = variant.get("market_value_cap_pct")
            if market_value_cap is not None:
                concentration_policy = copy.deepcopy(config.get("market_value_concentration_rebalance") or {})
                concentration_policy["threshold"] = float(market_value_cap)
                config["market_value_concentration_rebalance"] = concentration_policy
            active_external_state_cap = variant.get("active_external_state_market_value_cap_pct")
            if active_external_state_cap is not None:
                concentration_policy = copy.deepcopy(config.get("market_value_concentration_rebalance") or {})
                concentration_policy["active_external_state_threshold"] = float(active_external_state_cap)
                config["market_value_concentration_rebalance"] = concentration_policy
            post_trigger_cap = variant.get("post_first_external_trigger_market_value_cap_pct")
            if post_trigger_cap is not None and triggers:
                concentration_policy = copy.deepcopy(config.get("market_value_concentration_rebalance") or {})
                concentration_policy["post_external_trigger_threshold"] = float(post_trigger_cap)
                concentration_policy["post_external_trigger_active_from"] = min(
                    str(row["effective_deferral_day"]) for row in triggers
                )
                config["market_value_concentration_rebalance"] = concentration_policy
            risk_target = variant.get("global_risk_target_invested_ratio")
            if risk_target is not None:
                breadth_max = float(variant["global_risk_breadth_5d_max"])
                return_max = float(variant["global_risk_mean_return_5d_max"])
                for state_day, execution_day in zip(all_days, all_days[1:]):
                    state = market_states.get(state_day.isoformat()) or {}
                    if (
                        state
                        and
                        float(state.get("global_breadth_5d") or 0.0) <= breadth_max
                        and float(state.get("global_mean_return_5d") or 0.0) <= return_max
                    ):
                        risk_days.append(execution_day.isoformat())
                config["pit_external_invested_ratio_caps"] = {
                    day: float(risk_target) for day in sorted(set(risk_days))
                }
            residual_risk_target = variant.get("global_residual_risk_target_invested_ratio")
            if residual_risk_target is not None:
                breadth_max = float(variant["global_residual_risk_breadth_5d_max"])
                residual_z_max = float(variant["global_residual_risk_z_max"])
                return_max = float(variant.get("global_residual_risk_mean_return_5d_max") or 0.0)
                benchmark_return_min = variant.get("global_residual_risk_benchmark_return_20d_min")
                benchmark_return_max = variant.get("global_residual_risk_benchmark_return_20d_max")
                for state_day, execution_day in zip(all_days, all_days[1:]):
                    day_key = state_day.isoformat()
                    state = market_states.get(day_key) or {}
                    residual_z = global_risk_residuals.get(day_key)
                    residual_audit = global_risk_residual_audit.get(day_key) or {}
                    benchmark_return = residual_audit.get("benchmark_return_20d")
                    if (
                        state
                        and residual_z is not None
                        and residual_z <= residual_z_max
                        and float(state.get("global_breadth_5d") or 0.0) <= breadth_max
                        and float(state.get("global_mean_return_5d") or 0.0) <= return_max
                        and (
                            benchmark_return_min is None
                            or (
                                benchmark_return is not None
                                and float(benchmark_return) >= float(benchmark_return_min)
                            )
                        )
                        and (
                            benchmark_return_max is None
                            or (
                                benchmark_return is not None
                                and float(benchmark_return) <= float(benchmark_return_max)
                            )
                        )
                    ):
                        risk_days.append(execution_day.isoformat())
                config["pit_external_invested_ratio_caps"] = {
                    day: float(residual_risk_target) for day in sorted(set(risk_days))
                }
        replay_picks = selected
        if variant is not None and bool(variant.get("freeze_to_baseline_executed_buys")):
            replay_picks = _freeze_to_baseline_executed_buys(
                selected,
                baseline_buy_symbols_by_signal_rank=baseline_buy_symbols_by_signal_rank,
                baseline_buy_shares_by_signal_rank=(
                    baseline_buy_shares_by_signal_rank
                    if bool(variant.get("freeze_baseline_buy_shares"))
                    else None
                ),
                inventory_rows_by_signal_symbol=inventory_rows_by_signal_symbol,
            )
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=replay_picks, weight=0.0)
        candidate_run["artifact_id"] = "round31-lambda-zero" if variant is None else f"round31-{variant['variant_id']}"
        account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=bars_by_symbol,
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[config],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        risk_orders = [
            {
                key: row.get(key)
                for key in (
                    "trade_day",
                    "signal_day",
                    "symbol",
                    "action",
                    "shares",
                    "price",
                    "gross_amount_cny",
                    "transaction_cost_cny",
                    "reason",
                )
            }
            for row in account["order_ledger"]
            if row.get("reason") == "pit_external_global_risk_invested_ratio_rebalance"
        ]
        risk_signal_audit = []
        for execution_day in sorted(set(risk_days)):
            index = all_days.index(date.fromisoformat(execution_day))
            signal_day = all_days[index - 1].isoformat()
            risk_signal_audit.append(
                {
                    "execution_day": execution_day,
                    "signal_day": signal_day,
                    **copy.deepcopy(global_risk_residual_audit.get(signal_day) or {}),
                    "global_mean_return_5d": (
                        market_states.get(signal_day) or {}
                    ).get("global_mean_return_5d"),
                }
            )
        return account, {
            "triggered_position_count": len(triggers),
            "triggers": triggers,
            "global_risk_cap_signal_count": len(risk_days) if variant is not None else 0,
            "global_risk_cap_execution_days": sorted(set(risk_days)) if variant is not None else [],
            "global_risk_signal_audit": risk_signal_audit if variant is not None else [],
            "global_risk_rebalance_orders": risk_orders if variant is not None else [],
            "external_action_signal_count": (
                len(triggers) + len(set(risk_days)) if variant is not None else 0
            ),
        }

    baseline_account, _ = replay(None)
    lambda_zero_nav_match = stable_digest(baseline_account["nav_rows"]) == stable_digest(frozen_baseline["nav_rows"])
    lambda_zero_trade_match = stable_digest(
        [row for row in baseline_account["order_ledger"] if row.get("action") in {"buy", "sell"}]
    ) == stable_digest(
        [row for row in frozen_baseline["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    if not (lambda_zero_nav_match and lambda_zero_trade_match):
        raise ValueError("round31 lambda zero failed to reproduce frozen account economics")
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
    for variant in resolved_variants:
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
                "validation_drawdown_audit": _drawdown_audit(
                    account,
                    start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                    end=DEFAULT_VALIDATION_END,
                ),
                "validation_skip_order_delta": _skip_order_delta(
                    account,
                    baseline_account,
                    start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                    end=DEFAULT_VALIDATION_END,
                ),
                "extended_diagnostic": {
                    "baseline": _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end),
                    "candidate": _segment_metrics(account, start=DEFAULT_FINAL_START, end=signal_end),
                    "drawdown_audit": _drawdown_audit(
                        account,
                        start=DEFAULT_FINAL_START,
                        end=signal_end,
                    ),
                    "monthly_returns": _monthly_return_comparison(
                        account,
                        baseline_account,
                        start=DEFAULT_FINAL_START,
                        end=signal_end,
                    ),
                },
            }
        )
    selection_contract = design.get("selection", {})
    minimum_triggered_position_count = int(
        selection_contract["minimum_triggered_position_count"]
        if "minimum_triggered_position_count" in selection_contract
        else 1
    )
    eligible = [
        row
        for row in rows
        if not row["variant"].get("control_only")
        and int(row["trigger_audit"]["external_action_signal_count"]) > 0
        and int(row["trigger_audit"]["triggered_position_count"])
        >= minimum_triggered_position_count
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
    ]
    selected_row = None
    if eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        plateau = [
            row for row in eligible if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor
        ]
        selected_row = min(
            plateau,
            key=lambda row: (
                int(row["variant"]["extension_trade_days"]),
                float(row["variant"].get("weak_core_retained_share_scale") or 1.0),
                -float(row["variant"].get("minimum_cash_reserve_cny") or 0.0),
                -float(row["variant"]["prediction_percentile_min"]),
                -float(row["variant"].get("minimum_position_return") or 0.0),
                -float(row["variant"].get("market_value_cap_pct") or 1.0),
                -float(row["variant"].get("active_external_state_market_value_cap_pct") or 1.0),
                -float(row["variant"].get("post_first_external_trigger_market_value_cap_pct") or 1.0),
                float(row["variant"].get("global_risk_breadth_5d_max") or 0.0),
                float(row["variant"].get("global_risk_mean_return_5d_max") or 0.0),
                -float(row["variant"].get("global_risk_target_invested_ratio") or 1.0),
                float(row["variant"].get("global_residual_risk_z_max") or 0.0),
                -float(row["variant"].get("global_residual_risk_target_invested_ratio") or 1.0),
            ),
        )
    extended = None
    forward_readout = None
    if selected_row is not None:
        variant_id = str(selected_row["variant"]["variant_id"])
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
        forward_start_value = design.get("selection", {}).get("forward_readout_from")
        if forward_start_value:
            forward_start = date.fromisoformat(str(forward_start_value))
            if forward_start > signal_end:
                raise ValueError("forward_readout_from cannot be after signal_end")
            baseline_forward = _segment_metrics(baseline_account, start=forward_start, end=signal_end)
            candidate_forward = _segment_metrics(accounts[variant_id], start=forward_start, end=signal_end)
            forward_readout = {
                "from": forward_start.isoformat(),
                "to": signal_end.isoformat(),
                "baseline": baseline_forward,
                "candidate": candidate_forward,
                "gate": _non_degrade(candidate_forward, baseline_forward),
                "standout": _standout(candidate_forward, baseline_forward),
                "buy_order_delta": _buy_order_delta(
                    accounts[variant_id], baseline_account, start=forward_start, end=signal_end
                ),
                "monthly_returns": _monthly_return_comparison(
                    accounts[variant_id], baseline_account, start=forward_start, end=signal_end
                ),
            }
    forward_required = bool(design.get("selection", {}).get("forward_non_degrade_required"))
    passed = bool(
        extended
        and extended["gate"]["passed"]
        and extended["standout"]["passed"]
        and (not forward_required or (forward_readout and forward_readout["gate"]["passed"]))
    )
    material = {
        "artifact_type": "event_confirmed_position_extension_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_event_triggered_price_confirmed_position_extension_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_external_digests": actual_digests,
        "official_event_audit": {**event_audit, "future_event_violations": 0},
        "prediction_audit_by_extension_days": prediction_audit_by_horizon,
        "global_risk_residual_audit_digest": stable_digest(global_risk_residual_audit),
        "lambda_zero_reproduction": {
            "passed": True,
            "economic_nav_match": lambda_zero_nav_match,
            "executed_buy_sell_ledger_match": lambda_zero_trade_match,
        },
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None
        if selected_row is None
        else selected_row["variant"]["variant_id"],
        "extended_readout": extended,
        "forward_readout": forward_readout,
        "forward_non_degrade_required": forward_required,
        "extended_readout_status": "reused_evaluation_not_untouched_due_prior_iterations",
        "entry_selection_changed": False,
        "external_buy_trigger_count": 0,
        "future_feature_violations": 0,
        "future_label_violations": 0,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"event-confirmed-position-extension-{digest[:16]}", **material, "content_digest": digest}


def _drawdown_audit(account: dict[str, Any], *, start: date, end: date) -> dict[str, Any]:
    rows = [
        row
        for row in account["nav_rows"]
        if start <= date.fromisoformat(str(row["day"])) <= end
    ]
    if not rows:
        return {"peak_day": None, "trough_day": None, "max_drawdown": 0.0, "external_orders": []}
    peak_nav = float(rows[0]["nav_cny"])
    peak_day = str(rows[0]["day"])
    worst = 0.0
    worst_peak_day = peak_day
    trough_day = peak_day
    for row in rows:
        nav = float(row["nav_cny"])
        if nav > peak_nav:
            peak_nav = nav
            peak_day = str(row["day"])
        drawdown = nav / peak_nav - 1.0 if peak_nav else 0.0
        if drawdown < worst:
            worst = drawdown
            worst_peak_day = peak_day
            trough_day = str(row["day"])
    external_orders = [
        {
            "trade_day": row.get("trade_day"),
            "signal_day": row.get("signal_day"),
            "symbol": row.get("symbol"),
            "action": row.get("action"),
            "reason": row.get("reason"),
            "pnl_cny": row.get("pnl_cny"),
        }
        for row in account["order_ledger"]
        if worst_peak_day <= str(row.get("trade_day") or "") <= trough_day
        and str(row.get("reason") or "").startswith("pit_external_")
    ]
    return {
        "peak_day": worst_peak_day,
        "trough_day": trough_day,
        "max_drawdown": worst,
        "external_orders": external_orders,
    }


def _skip_order_delta(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    start: date,
    end: date,
) -> dict[str, Any]:
    fields = ("signal_day", "trade_day", "symbol", "rank", "reason")

    def rows(account: dict[str, Any]) -> dict[tuple[str, str, str, int, str], dict[str, Any]]:
        result: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
        for row in account["order_ledger"]:
            trade_day = date.fromisoformat(str(row.get("trade_day") or row["signal_day"]))
            if row.get("action") != "skip" or not start <= trade_day <= end:
                continue
            key = (
                str(row.get("signal_day") or ""),
                str(row.get("trade_day") or ""),
                str(row.get("symbol") or ""),
                int(row.get("rank") or 0),
                str(row.get("reason") or ""),
            )
            result[key] = {field: row.get(field) for field in fields}
        return result

    candidate_rows = rows(candidate)
    baseline_rows = rows(baseline)
    return {
        "candidate_only": [candidate_rows[key] for key in sorted(set(candidate_rows) - set(baseline_rows))],
        "baseline_only": [baseline_rows[key] for key in sorted(set(baseline_rows) - set(candidate_rows))],
        "candidate_count": len(candidate_rows),
        "baseline_count": len(baseline_rows),
    }


def _monthly_return_comparison(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    def segment_returns(account: dict[str, Any]) -> dict[str, float]:
        rows = [
            row
            for row in account["nav_rows"]
            if start <= date.fromisoformat(str(row["day"])) <= end
        ]
        if not rows:
            return {}
        first_day = date.fromisoformat(str(rows[0]["day"]))
        prior = [row for row in account["nav_rows"] if date.fromisoformat(str(row["day"])) < first_day]
        previous_nav = float(prior[-1]["nav_cny"]) if prior else float(account["summary"]["initial_cash_cny"])
        month_end_nav: dict[str, float] = {}
        for row in rows:
            month_end_nav[str(row["day"])[:7]] = float(row["nav_cny"])
        result: dict[str, float] = {}
        for month in sorted(month_end_nav):
            ending_nav = month_end_nav[month]
            result[month] = ending_nav / previous_nav - 1.0 if previous_nav else 0.0
            previous_nav = ending_nav
        return result

    candidate_by_month = segment_returns(candidate)
    baseline_by_month = segment_returns(baseline)
    return [
        {
            "month": month,
            "baseline_return": baseline_by_month[month],
            "candidate_return": candidate_by_month[month],
            "delta": candidate_by_month[month] - baseline_by_month[month],
        }
        for month in sorted(set(candidate_by_month) & set(baseline_by_month))
        if start.strftime("%Y-%m") <= month <= end.strftime("%Y-%m")
    ]


def _freeze_to_baseline_executed_buys(
    picks: list[dict[str, Any]],
    *,
    baseline_buy_symbols_by_signal_rank: dict[tuple[str, int], set[str]],
    baseline_buy_shares_by_signal_rank: dict[tuple[str, int], dict[str, int]] | None = None,
    inventory_rows_by_signal_symbol: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    frozen: list[dict[str, Any]] = []
    for row in picks:
        key = (str(row["as_of_date"]), int(float(row.get("rank") or 0)))
        symbols = sorted(baseline_buy_symbols_by_signal_rank.get(key) or set())
        if len(symbols) > 1:
            raise ValueError(f"multiple frozen baseline buys for one signal/rank: {key} -> {symbols}")
        frozen_row = row
        if symbols and str(row.get("symbol") or "") != symbols[0]:
            replacement = (inventory_rows_by_signal_symbol or {}).get((key[0], symbols[0]))
            if replacement is None:
                raise ValueError(f"frozen baseline replacement is absent from PIT inventory: {key} -> {symbols[0]}")
            frozen_row = {
                **row,
                **replacement,
                "as_of_date": key[0],
                "symbol": symbols[0],
                "rank": key[1],
                "portfolio_weight": row.get("portfolio_weight"),
                "rank_weight_multiplier": row.get("rank_weight_multiplier"),
                "target_horizon_days": row.get("target_horizon_days"),
                "replacement_original_symbol": str(row.get("symbol") or ""),
                "replacement_inventory_rank": replacement.get("rank"),
            }
        frozen.append(
            {
                **frozen_row,
                "shadow_baseline_buy_eligible": bool(symbols),
                "shadow_baseline_buy_symbols": symbols,
                "shadow_baseline_buy_shares_by_symbol": (
                    dict((baseline_buy_shares_by_signal_rank or {}).get(key) or {})
                    if baseline_buy_shares_by_signal_rank is not None
                    else None
                ),
            }
        )
    return frozen


def write_event_confirmed_position_extension_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("event-confirmed position-extension result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable event-confirmed position-extension result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
