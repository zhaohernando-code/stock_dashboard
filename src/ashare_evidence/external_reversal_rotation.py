from __future__ import annotations

import copy
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.external_context_sector_market_research import (
    SW_L1_BY_SUBINDUSTRY,
    load_sector_research_snapshot,
    sector_state_by_decision_date,
)
from ashare_evidence.external_inventory_rerank import _z_scores
from ashare_evidence.global_sector_state_account_ablation import (
    DEFAULT_FINAL_START,
    DEFAULT_TUNING_END,
    DEFAULT_VALIDATION_END,
    _buy_order_delta,
    _candidate_run,
    _group_by_date,
    _non_degrade,
    _segment_metrics,
    _standout,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "external_reversal_rotation_challenger.v1"
DEFAULT_WEIGHTS = (0.0, 0.025, 0.05, 0.075, 0.10, 0.15)
DEFAULT_MINIMUM_HISTORY = 60
DEFAULT_EVENT_THRESHOLD = 0.5
DEFAULT_EVENT_COOLDOWN = 10
DEFAULT_ACTIVE_WINDOW = 3
DEFAULT_POOL_DEPTH = 20
DEFAULT_SCORE_GAP = 0.10
DEFAULT_CONTRIBUTION_CAP = 0.15
DEFAULT_MINIMUM_VALIDATION_EVENTS = 3
DEFAULT_MINIMUM_POSITIVE_EVENT_SHARE = 0.5
EVENT_HORIZONS = (5, 10)

_ALLOCATION_FIELDS = (
    "base_gross_exposure",
    "date_exposure_floor",
    "date_exposure_scale",
    "date_exposure_scale_reasons",
    "date_position_scale",
    "date_position_scale_reasons",
    "portfolio_weight",
    "rank_portfolio_adjustment_multiplier",
    "rank_portfolio_adjustment_reasons",
    "rank_position_scale",
    "rank_position_scale_reasons",
    "rank_weight_multiplier",
    "signal_position_scale",
    "signal_position_scale_reasons",
    "target_horizon_days",
)


def _past_only_z(value: float, prior_values: list[float], *, minimum_history: int) -> tuple[float, bool]:
    if len(prior_values) < minimum_history or pstdev(prior_values) <= 1e-12:
        return 0.0, False
    return (value - mean(prior_values)) / pstdev(prior_values), True


def build_past_only_reversal_events(
    *,
    signal_days: list[str],
    sector_states: dict[str, dict[str, Any]],
    minimum_history: int = DEFAULT_MINIMUM_HISTORY,
    event_threshold: float = DEFAULT_EVENT_THRESHOLD,
    cooldown_signal_days: int = DEFAULT_EVENT_COOLDOWN,
    active_window_signal_days: int = DEFAULT_ACTIVE_WINDOW,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    """Detect broad acceleration events without fitting any statistic on the current or future day."""
    ordered_days = sorted(signal_days)
    prior_breadth_acceleration: list[float] = []
    prior_return_acceleration: list[float] = []
    trigger_indices: list[int] = []
    audit_by_day: dict[str, dict[str, Any]] = {}
    for index, day in enumerate(ordered_days):
        state = sector_states[day]
        breadth_acceleration = float(state["breadth_5d"]) - float(state["breadth_20d"])
        return_acceleration = float(state["mean_return_5d"]) / 5.0 - float(state["mean_return_20d"]) / 20.0
        breadth_z, breadth_ready = _past_only_z(
            breadth_acceleration, prior_breadth_acceleration, minimum_history=minimum_history
        )
        return_z, return_ready = _past_only_z(
            return_acceleration, prior_return_acceleration, minimum_history=minimum_history
        )
        ready = breadth_ready and return_ready
        combined_score = (breadth_z + return_z) / 2.0 if ready else 0.0
        triggered = bool(
            ready
            and breadth_acceleration > 0.0
            and return_acceleration > 0.0
            and combined_score >= event_threshold
        )
        if triggered:
            trigger_indices.append(index)
        audit_by_day[day] = {
            "status": "ready" if ready else "warmup",
            "prior_signal_day_count": len(prior_breadth_acceleration),
            "breadth_acceleration": breadth_acceleration,
            "return_acceleration": return_acceleration,
            "breadth_acceleration_z": breadth_z,
            "return_acceleration_z": return_z,
            "combined_score": combined_score,
            "triggered": triggered,
        }
        prior_breadth_acceleration.append(breadth_acceleration)
        prior_return_acceleration.append(return_acceleration)

    events: list[dict[str, Any]] = []
    last_trigger_index: int | None = None
    for trigger_index in trigger_indices:
        if last_trigger_index is None or trigger_index - last_trigger_index > cooldown_signal_days:
            event_id = f"reversal-event-{len(events) + 1:02d}"
            active_days = ordered_days[trigger_index : trigger_index + active_window_signal_days]
            events.append(
                {
                    "event_id": event_id,
                    "start_day": ordered_days[trigger_index],
                    "start_signal_index": trigger_index,
                    "trigger_days": [ordered_days[trigger_index]],
                    "active_days": active_days,
                }
            )
        else:
            events[-1]["trigger_days"].append(ordered_days[trigger_index])
        last_trigger_index = trigger_index

    active_event_by_day: dict[str, str] = {}
    for event in events:
        for day in event["active_days"]:
            active_event_by_day[day] = str(event["event_id"])
            audit_by_day[day]["active_event_id"] = str(event["event_id"])
    return events, active_event_by_day, audit_by_day


def select_reversal_rotation_day(
    *,
    original: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    sector_state: dict[str, Any],
    weight: float,
    active_event_id: str | None,
    pool_depth: int = DEFAULT_POOL_DEPTH,
    maximum_score_gap: float = DEFAULT_SCORE_GAP,
    contribution_cap: float = DEFAULT_CONTRIBUTION_CAP,
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered_original = sorted(copy.deepcopy(original), key=lambda row: int(float(row["rank"])))
    if len(ordered_original) != 3:
        raise ValueError("reversal rotation requires exactly three original V3 selections per signal day")
    day = str(ordered_original[0]["as_of_date"])
    if weight == 0.0 or active_event_id is None:
        if baseline_buy_symbols_by_slot is not None:
            for index, row in enumerate(ordered_original, start=1):
                row["shadow_baseline_buy_symbols"] = sorted(
                    baseline_buy_symbols_by_slot.get((day, index), set())
                )
        return ordered_original, {
            "changed": False,
            "changed_slot_count": 0,
            "new_symbol_count": 0,
            "active_event_id": active_event_id,
            "eligible_candidate_count": 0,
        }

    rank3_score = float(ordered_original[2]["score"])
    eligible = [
        copy.deepcopy(row)
        for row in inventory
        if int(float(row.get("rank") or 999)) <= pool_depth
        and float(row.get("score") or 0.0) >= rank3_score - maximum_score_gap
        and bool((row.get("_trade_eligibility_snapshot") or {}).get("eligible_before_scoring", True))
    ]
    eligible_by_symbol = {str(row["symbol"]): row for row in eligible}
    for row in ordered_original:
        eligible_by_symbol.setdefault(str(row["symbol"]), copy.deepcopy(row))
    eligible = list(eligible_by_symbol.values())
    core_z = _z_scores([float(row["score"]) for row in eligible])
    sector_accelerations: list[float] = []
    for row in eligible:
        sw_name = SW_L1_BY_SUBINDUSTRY.get(str(row.get("industry_name") or ""), "")
        sw_row = (sector_state.get("by_sector_name") or {}).get(sw_name) or {}
        sector_accelerations.append(
            float(sw_row.get("relative_5d") or 0.0) / 5.0
            - float(sw_row.get("relative_20d") or 0.0) / 20.0
        )
    sector_z = _z_scores(sector_accelerations)
    for row, core_value, raw_external, external_value in zip(
        eligible, core_z, sector_accelerations, sector_z, strict=True
    ):
        contribution = max(-contribution_cap, min(contribution_cap, weight * external_value))
        row["external_sector_acceleration"] = raw_external
        row["external_sector_acceleration_z"] = external_value
        row["external_reversal_contribution"] = contribution
        row["external_reversal_adjusted_score"] = core_value + contribution
        row["external_reversal_event_id"] = active_event_id
    eligible.sort(
        key=lambda row: (-float(row["external_reversal_adjusted_score"]), -float(row["score"]), str(row["symbol"]))
    )

    rank1_symbol = str(ordered_original[0]["symbol"])
    original_lower_symbols = {str(row["symbol"]) for row in ordered_original[1:]}
    chosen_lower: list[dict[str, Any]] = []
    new_symbol_count = 0
    for candidate in eligible:
        symbol = str(candidate["symbol"])
        if symbol == rank1_symbol or symbol in {str(row["symbol"]) for row in chosen_lower}:
            continue
        is_new = symbol not in original_lower_symbols
        if is_new and new_symbol_count >= 1:
            continue
        chosen_lower.append(candidate)
        new_symbol_count += int(is_new)
        if len(chosen_lower) == 2:
            break
    if len(chosen_lower) != 2:
        raise ValueError(f"insufficient core-qualified candidates on {day}")

    chosen = [copy.deepcopy(ordered_original[0]), *chosen_lower]
    rebuilt: list[dict[str, Any]] = []
    changed_slots = 0
    baseline_slots = baseline_buy_symbols_by_slot or {}
    for index, candidate in enumerate(chosen):
        template = ordered_original[index]
        row = copy.deepcopy(candidate)
        for field in _ALLOCATION_FIELDS:
            row[field] = copy.deepcopy(template.get(field))
        row["rank"] = index + 1
        unchanged_slot = str(row["symbol"]) == str(template["symbol"])
        row["shadow_baseline_buy_symbols"] = (
            sorted(baseline_slots.get((day, index + 1), set())) if unchanged_slot else [str(row["symbol"])]
        )
        rebuilt.append(row)
        changed_slots += int(not unchanged_slot)
    return rebuilt, {
        "changed": changed_slots > 0,
        "changed_slot_count": changed_slots,
        "new_symbol_count": new_symbol_count,
        "active_event_id": active_event_id,
        "eligible_candidate_count": len(eligible),
        "rank1_preserved": str(rebuilt[0]["symbol"]) == rank1_symbol,
    }


def _event_return(account: dict[str, Any], *, start_day: str, horizon: int) -> float | None:
    nav_rows = sorted(account["nav_rows"], key=lambda row: str(row["day"]))
    start_index = next((index for index, row in enumerate(nav_rows) if str(row["day"]) >= start_day), None)
    if start_index is None or start_index + horizon >= len(nav_rows):
        return None
    starting_nav = float(nav_rows[start_index]["nav_cny"])
    ending_nav = float(nav_rows[start_index + horizon]["nav_cny"])
    return ending_nav / starting_nav - 1.0 if starting_nav else None


def _event_metrics(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    changed_event_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        row: dict[str, Any] = {
            "event_id": event["event_id"],
            "start_day": event["start_day"],
            "trigger_day_count": len(event["trigger_days"]),
            "changed_by_candidate": str(event["event_id"]) in changed_event_ids,
        }
        for horizon in EVENT_HORIZONS:
            candidate_return = _event_return(candidate, start_day=str(event["start_day"]), horizon=horizon)
            baseline_return = _event_return(baseline, start_day=str(event["start_day"]), horizon=horizon)
            row[f"candidate_return_{horizon}d"] = candidate_return
            row[f"baseline_return_{horizon}d"] = baseline_return
            row[f"incremental_return_{horizon}d"] = (
                None if candidate_return is None or baseline_return is None else candidate_return - baseline_return
            )
        rows.append(row)

    segments = {
        "tuning": [row for row in rows if date.fromisoformat(str(row["start_day"])) <= DEFAULT_TUNING_END],
        "validation": [
            row
            for row in rows
            if DEFAULT_TUNING_END < date.fromisoformat(str(row["start_day"])) <= DEFAULT_VALIDATION_END
        ],
        "extended": [row for row in rows if date.fromisoformat(str(row["start_day"])) >= DEFAULT_FINAL_START],
    }
    summaries: dict[str, dict[str, Any]] = {}
    for segment, segment_rows in segments.items():
        summary: dict[str, Any] = {"event_count": len(segment_rows)}
        for horizon in EVENT_HORIZONS:
            values = [
                float(row[f"incremental_return_{horizon}d"])
                for row in segment_rows
                if row["changed_by_candidate"] and row[f"incremental_return_{horizon}d"] is not None
            ]
            summary[f"changed_event_count_{horizon}d"] = sum(
                bool(row["changed_by_candidate"]) for row in segment_rows
            )
            summary[f"observed_event_count_{horizon}d"] = len(values)
            summary[f"mean_incremental_return_{horizon}d"] = mean(values) if values else 0.0
            summary[f"positive_event_share_{horizon}d"] = (
                sum(value > 0.0 for value in values) / len(values) if values else 0.0
            )
            summary[f"standard_error_{horizon}d"] = (
                pstdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
            )
        summaries[segment] = summary
    return rows, summaries


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("reversal challenger design must be frozen before outcome evaluation")
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "minimum_prior_signal_days": DEFAULT_MINIMUM_HISTORY,
        "combined_threshold": DEFAULT_EVENT_THRESHOLD,
        "cooldown": DEFAULT_EVENT_COOLDOWN,
        "active_window": DEFAULT_ACTIVE_WINDOW,
        "pool_depth": DEFAULT_POOL_DEPTH,
        "score_gap": DEFAULT_SCORE_GAP,
        "cap": DEFAULT_CONTRIBUTION_CAP,
    }
    observed = {
        "weights": [float(value) for value in design["weights"]],
        "minimum_prior_signal_days": int(design["event_definition"]["minimum_prior_signal_days"]),
        "combined_threshold": float(str(design["event_definition"]["trigger"]).rsplit(">=", 1)[1]),
        "cooldown": int(design["event_definition"]["independent_event_cooldown_signal_days"]),
        "active_window": int(design["event_definition"]["active_window_signal_days"]),
        "pool_depth": int(design["candidate_boundary"]["maximum_original_rank"]),
        "score_gap": float(design["candidate_boundary"]["maximum_raw_score_gap_from_original_rank3"]),
        "cap": float(design["carrier"]["maximum_absolute_external_contribution"]),
    }
    if observed != expected:
        raise ValueError(f"reversal challenger implementation differs from frozen design: {observed}")


def run_external_reversal_rotation_challenger(
    *,
    execution_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    _validate_design(design)
    source_snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    if source_snapshot["artifact_id"] != design["data_contract"]["execution_snapshot_id"]:
        raise ValueError("execution snapshot does not match the frozen design")
    snapshot, personal_eligibility_audit = build_personal_eligible_execution_snapshot(source_snapshot)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    if sector_snapshot["content_digest"] != design["data_contract"]["sector_market_digest"]:
        raise ValueError("sector snapshot digest does not match the frozen design")

    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    if set(original_by_date) != set(inventory_by_date):
        raise ValueError("personal selected picks and inventory date coverage differ")
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"], decision_dates=decision_dates
    )
    if set(sector_states) != set(inventory_by_date):
        raise ValueError("full-window PIT sector state coverage is incomplete")
    events, active_event_by_day, event_signal_audit = build_past_only_reversal_events(
        signal_days=list(inventory_by_date), sector_states=sector_states
    )

    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))

    def replay(weight: float, *, disabled_event_ids: set[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        disabled = disabled_event_ids or set()
        selected: list[dict[str, Any]] = []
        changed_dates = 0
        changed_slots = 0
        new_symbols = 0
        changed_event_ids: set[str] = set()
        eligible_counts: list[int] = []
        for day in sorted(inventory_by_date):
            active_event_id = active_event_by_day.get(day)
            if active_event_id in disabled:
                active_event_id = None
            picks, audit = select_reversal_rotation_day(
                original=original_by_date[day],
                inventory=inventory_by_date[day],
                sector_state=sector_states[day],
                weight=weight,
                active_event_id=active_event_id,
                baseline_buy_symbols_by_slot=baseline_buy_symbols_by_slot,
            )
            selected.extend(picks)
            changed_dates += int(audit["changed"])
            changed_slots += int(audit["changed_slot_count"])
            new_symbols += int(audit["new_symbol_count"])
            if audit["changed"] and active_event_id:
                changed_event_ids.add(active_event_id)
            if audit["eligible_candidate_count"]:
                eligible_counts.append(int(audit["eligible_candidate_count"]))
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=weight)
        candidate_run["artifact_id"] = f"external-reversal-rotation-{weight:.3f}-{stable_digest(sorted(disabled))[:8]}"
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
            "new_symbol_selection_count": new_symbols,
            "changed_event_ids": sorted(changed_event_ids),
            "mean_core_qualified_candidate_count": mean(eligible_counts) if eligible_counts else 0.0,
        }

    accounts: dict[float, dict[str, Any]] = {}
    audits: dict[float, dict[str, Any]] = {}
    for weight in DEFAULT_WEIGHTS:
        accounts[weight], audits[weight] = replay(weight)
    nav_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    trade_match = stable_digest(
        [row for row in accounts[0.0]["order_ledger"] if row.get("action") in {"buy", "sell"}]
    ) == stable_digest(
        [row for row in baseline_account["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    if not nav_match or not trade_match:
        raise ValueError("lambda zero failed to reproduce personal-eligible V3 economics")

    segment_ranges = {
        "tuning": (None, DEFAULT_TUNING_END),
        "validation": (DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END), DEFAULT_VALIDATION_END),
        "full_pre_extended": (None, DEFAULT_VALIDATION_END),
    }
    baseline_segments = {
        key: _segment_metrics(baseline_account, start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    for weight in DEFAULT_WEIGHTS:
        segments = {
            key: _segment_metrics(accounts[weight], start=start, end=end)
            for key, (start, end) in segment_ranges.items()
        }
        event_rows, event_summaries = _event_metrics(
            accounts[weight],
            baseline_account,
            events,
            changed_event_ids=set(audits[weight]["changed_event_ids"]),
        )
        gates = {key: _non_degrade(value, baseline_segments[key]) for key, value in segments.items()}
        row = {
            "weight": weight,
            "change_audit": audits[weight],
            "segments": segments,
            "gates": gates,
            "event_summaries": event_summaries,
            "event_rows": event_rows,
        }
        rows.append(row)
        validation = event_summaries["validation"]
        if (
            weight > 0.0
            and audits[weight]["changed_date_count"] > 0
            and gates["tuning"]["passed"]
            and gates["validation"]["passed"]
            and int(validation["observed_event_count_10d"]) >= DEFAULT_MINIMUM_VALIDATION_EVENTS
            and float(validation["mean_incremental_return_10d"]) > 0.0
            and float(validation["positive_event_share_10d"]) >= DEFAULT_MINIMUM_POSITIVE_EVENT_SHARE
        ):
            eligible_rows.append(row)

    selected: dict[str, Any] | None = None
    if eligible_rows:
        best = max(
            eligible_rows,
            key=lambda row: float(row["event_summaries"]["validation"]["mean_incremental_return_10d"]),
        )
        best_validation = best["event_summaries"]["validation"]
        floor = float(best_validation["mean_incremental_return_10d"]) - float(
            best_validation["standard_error_10d"]
        )
        selected = min(
            [
                row
                for row in eligible_rows
                if float(row["event_summaries"]["validation"]["mean_incremental_return_10d"]) >= floor
            ],
            key=lambda row: float(row["weight"]),
        )

    extended_readout: dict[str, Any] | None = None
    leave_one_event_out: dict[str, Any] | None = None
    if selected is not None:
        selected_weight = float(selected["weight"])
        baseline_extended = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_extended = _segment_metrics(accounts[selected_weight], start=DEFAULT_FINAL_START, end=signal_end)
        extended_readout = {
            "weight": selected_weight,
            "baseline": baseline_extended,
            "candidate": candidate_extended,
            "gate": _non_degrade(candidate_extended, baseline_extended),
            "standout": _standout(candidate_extended, baseline_extended),
            "event_summary": selected["event_summaries"]["extended"],
            "buy_order_delta": _buy_order_delta(
                accounts[selected_weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }
        full_baseline = _segment_metrics(baseline_account, start=None, end=signal_end)
        full_candidate = _segment_metrics(accounts[selected_weight], start=None, end=signal_end)
        full_improvement = float(full_candidate["total_return"]) - float(full_baseline["total_return"])
        loo_rows: list[dict[str, Any]] = []
        for event_id in audits[selected_weight]["changed_event_ids"]:
            loo_account, loo_audit = replay(selected_weight, disabled_event_ids={event_id})
            loo_metrics = _segment_metrics(loo_account, start=None, end=signal_end)
            loo_improvement = float(loo_metrics["total_return"]) - float(full_baseline["total_return"])
            removed_fraction = (
                (full_improvement - loo_improvement) / full_improvement if full_improvement > 0.0 else None
            )
            loo_rows.append(
                {
                    "disabled_event_id": event_id,
                    "remaining_changed_event_ids": loo_audit["changed_event_ids"],
                    "full_period_return_improvement": loo_improvement,
                    "removed_fraction_of_positive_improvement": removed_fraction,
                    "flipped_positive_improvement": full_improvement > 0.0 and loo_improvement <= 0.0,
                }
            )
        concentrated = bool(
            full_improvement <= 0.0
            or any(
                row["flipped_positive_improvement"]
                or (
                    row["removed_fraction_of_positive_improvement"] is not None
                    and float(row["removed_fraction_of_positive_improvement"]) > 0.5
                )
                for row in loo_rows
            )
        )
        leave_one_event_out = {
            "full_period_return_improvement": full_improvement,
            "changed_event_count": len(loo_rows),
            "concentrated": concentrated,
            "rows": loo_rows,
        }

    numerical_pass = bool(
        selected is not None
        and extended_readout
        and extended_readout["gate"]["passed"]
        and extended_readout["standout"]["passed"]
        and leave_one_event_out
        and not leave_one_event_out["concentrated"]
    )
    material = {
        "artifact_type": "external_reversal_rotation_challenger",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_cleared_numerical_gates"
            if numerical_pass
            else "no_candidate_cleared_full_objective"
        ),
        "claim_ceiling": "research_only_provisional_sector_source_not_v3_change",
        "source_execution_snapshot_id": source_snapshot["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "personal_eligibility_audit": personal_eligibility_audit,
        "lambda_zero_reproduction": {
            "passed": nav_match and trade_match,
            "economic_nav_match": nav_match,
            "executed_buy_sell_ledger_match": trade_match,
        },
        "event_detection": {
            "event_count": len(events),
            "events": events,
            "tuning_event_count": sum(
                date.fromisoformat(str(row["start_day"])) <= DEFAULT_TUNING_END for row in events
            ),
            "validation_event_count": sum(
                DEFAULT_TUNING_END < date.fromisoformat(str(row["start_day"])) <= DEFAULT_VALIDATION_END
                for row in events
            ),
            "extended_event_count": sum(
                date.fromisoformat(str(row["start_day"])) >= DEFAULT_FINAL_START for row in events
            ),
            "signal_audit_digest": stable_digest(event_signal_audit),
            "future_feature_violations": 0,
        },
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["weight"],
        "extended_readout": extended_readout,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "leave_one_event_out": leave_one_event_out,
        "provider_revision_lineage_missing": True,
        "promotion_blockers": [
            "sector_provider_revision_lineage_missing",
            "independent_future_event_validation_missing",
        ],
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"external-reversal-rotation-{digest[:16]}", **material, "content_digest": digest}


def write_external_reversal_rotation_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("external reversal rotation result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable external reversal rotation result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
