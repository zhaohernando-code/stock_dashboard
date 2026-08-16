from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from ashare_evidence.external_context_sector_market_research import (
    SHANGHAI,
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
    _segment_metrics,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.stock_transition_sleeve import _monthly_delta_summary
from ashare_evidence.v3_position_lifecycle import (
    _buy_key_audit,
    _lifecycle_risk_gate,
    _lifecycle_sell_count,
    _sanitize_rows,
    lifecycle_position_features,
    lifecycle_variant_triggered,
)

SCHEMA_VERSION = "v3_market_confirmed_lifecycle_challenger.v1"
MINIMUM_VALIDATION_ACTION_COUNT = 8


def negative_context_confirmed(
    *,
    sector_state: dict[str, Any],
    industry_name: str,
    require_sector_weakness: bool,
) -> tuple[bool, dict[str, Any]]:
    global_weakness = bool(
        float(sector_state["breadth_5d"]) < float(sector_state["breadth_20d"])
        and float(sector_state["mean_return_5d"]) / 5.0
        < float(sector_state["mean_return_20d"]) / 20.0
    )
    sector_name = SW_L1_BY_SUBINDUSTRY.get(industry_name)
    sector_row = (sector_state.get("by_sector_name") or {}).get(sector_name) if sector_name else None
    sector_weakness = bool(
        sector_row
        and float(sector_row["return_5d"]) < 0.0
        and float(sector_row["relative_5d"]) < 0.0
    )
    confirmed = global_weakness and (sector_weakness if require_sector_weakness else True)
    return confirmed, {
        "global_weakness": global_weakness,
        "sector_name": sector_name,
        "sector_mapping_available": sector_name is not None,
        "sector_weakness": sector_weakness,
    }


def build_market_confirmed_lifecycle_actions(
    *,
    selected_picks_by_date: dict[str, list[dict[str, Any]]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    sector_states: dict[str, dict[str, Any]],
    common_deterioration: dict[str, Any],
    variant: dict[str, Any],
    signal_end: date,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    exit_signals: dict[str, dict[str, str]] = defaultdict(dict)
    trim_signals: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    audit_rows: list[dict[str, Any]] = []
    missing_context_count = 0
    pit_violation_count = 0
    for signal_day, picks in sorted(selected_picks_by_date.items()):
        signal_date = date.fromisoformat(signal_day)
        for pick in picks:
            symbol = str(pick["symbol"])
            rank = int(float(pick["rank"]))
            industry_name = str(pick.get("industry_name") or "")
            bars = [
                (date.fromisoformat(str(row["day"])), float(row["close"]))
                for row in market_bars_by_symbol.get(symbol, [])
                if date.fromisoformat(str(row["day"])) <= signal_end
            ]
            entry_index = next((index for index, (day, _close) in enumerate(bars) if day > signal_date), None)
            if entry_index is None:
                continue
            horizon = int(float(pick.get("target_horizon_days") or 20))
            planned_exit_index = min(entry_index + horizon, len(bars) - 1)
            if planned_exit_index <= entry_index + 1:
                continue
            entry_day = bars[entry_index][0]
            closes = [close for _day, close in bars]
            for decision_index in range(entry_index, planned_exit_index):
                decision_day = bars[decision_index][0]
                state = sector_states.get(decision_day.isoformat())
                if state is None:
                    missing_context_count += 1
                    continue
                features = lifecycle_position_features(
                    closes=closes,
                    entry_index=entry_index,
                    decision_index=decision_index,
                    top3_absence_streak=0,
                )
                if not lifecycle_variant_triggered(features, common_deterioration):
                    continue
                confirmed, context_audit = negative_context_confirmed(
                    sector_state=state,
                    industry_name=industry_name,
                    require_sector_weakness=bool(variant["require_sector_weakness"]),
                )
                if not confirmed:
                    continue
                execution_index = decision_index + 1
                if execution_index >= planned_exit_index:
                    break
                execution_day = bars[execution_index][0]
                position_key = "|".join((signal_day, entry_day.isoformat(), symbol, str(rank)))
                reason = f"pit_lifecycle_{variant['id']}"
                if variant["action"] == "full_exit":
                    exit_signals[execution_day.isoformat()][position_key] = reason
                else:
                    trim_signals[execution_day.isoformat()][position_key] = {
                        "reason": reason,
                        "retained_share_scale": float(variant["retained_share_scale"]),
                    }
                available_rows = list((state.get("by_sector_name") or {}).values())
                cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
                if any(datetime.fromisoformat(str(row["available_at"])) > cutoff for row in available_rows):
                    pit_violation_count += 1
                audit_rows.append(
                    {
                        "signal_day": signal_day,
                        "entry_day": entry_day.isoformat(),
                        "decision_day": decision_day.isoformat(),
                        "execution_day": execution_day.isoformat(),
                        "symbol": symbol,
                        "rank": rank,
                        "features": features,
                        "context": context_audit,
                    }
                )
                break
    return dict(exit_signals), dict(trim_signals), {
        "potential_action_count": len(audit_rows),
        "missing_context_count": missing_context_count,
        "minimum_execution_lag_trading_days": 1,
        "same_close_decision_execution_count": 0,
        "future_feature_violation_count": pit_violation_count,
        "audit_digest": stable_digest(audit_rows),
        "audit_sample": audit_rows[:5],
    }


def _validate_design(design: dict[str, Any]) -> list[dict[str, Any]]:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("market-confirmed lifecycle design must be frozen before outcome evaluation")
    variants = list(design["variants"])
    if [int(row["complexity_order"]) for row in variants] != [1, 2, 3, 4]:
        raise ValueError("market-confirmed lifecycle complexity order differs from frozen design")
    if int(design["selection"]["minimum_validation_action_count"]) != MINIMUM_VALIDATION_ACTION_COUNT:
        raise ValueError("minimum validation action count differs from frozen design")
    return variants


def run_v3_market_confirmed_lifecycle_challenger(
    *,
    execution_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    variants = _validate_design(design)
    source_snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    if source_snapshot["artifact_id"] != design["data_contract"]["execution_snapshot_id"]:
        raise ValueError("execution snapshot does not match frozen market-confirmed lifecycle design")
    snapshot, eligibility_audit = build_personal_eligible_execution_snapshot(source_snapshot)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    if sector_snapshot["content_digest"] != design["data_contract"]["sector_market_digest"]:
        raise ValueError("sector snapshot does not match frozen market-confirmed lifecycle design")

    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    selected_by_day = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_day = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    all_decision_dates = sorted(
        {
            date.fromisoformat(str(row["day"]))
            for symbol in {str(row["symbol"]) for rows in selected_by_day.values() for row in rows}
            for row in snapshot["inputs"]["market_bars_by_symbol"].get(symbol, [])
            if date.fromisoformat(str(row["day"])) <= signal_end
        }
    )
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"],
        decision_dates=all_decision_dates,
    )
    baseline = snapshot["baseline_output"]
    baseline_buys_by_slot: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    for row in baseline["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buys_by_slot[(str(row["signal_day"]), int(row["rank"]))][str(row["symbol"])] = int(
                row["shares"]
            )
    selected_rows = _sanitize_rows([row for day in sorted(selected_by_day) for row in selected_by_day[day]])
    frozen_selected_rows = copy.deepcopy(selected_rows)
    for row in frozen_selected_rows:
        slot = (str(row["as_of_date"]), int(float(row["rank"])))
        shares = baseline_buys_by_slot.get(slot, {})
        row["shadow_baseline_buy_symbols"] = sorted(shares)
        row["shadow_baseline_buy_shares_by_symbol"] = shares
    inventory_rows = _sanitize_rows([row for day in sorted(inventory_by_day) for row in inventory_by_day[day]])

    def replay(
        *,
        selected: list[dict[str, Any]],
        exit_signals: dict[str, dict[str, str]],
        trim_signals: dict[str, dict[str, dict[str, Any]]],
        artifact_suffix: str,
    ) -> dict[str, Any]:
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = f"v3-market-confirmed-lifecycle-{artifact_suffix}"
        config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        config["pit_position_lifecycle_exit_signals"] = exit_signals
        config["pit_position_lifecycle_trim_signals"] = trim_signals
        return build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=inventory_rows,
            candidate_configurations=[config],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]

    unrestricted_control = replay(
        selected=selected_rows, exit_signals={}, trim_signals={}, artifact_suffix="control"
    )
    frozen_control = replay(
        selected=frozen_selected_rows, exit_signals={}, trim_signals={}, artifact_suffix="frozen-control"
    )
    baseline_nav_digest = stable_digest(baseline["nav_rows"])
    baseline_trade_digest = stable_digest(
        [row for row in baseline["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    control_reproduction = {
        "unrestricted_nav_match": stable_digest(unrestricted_control["nav_rows"]) == baseline_nav_digest,
        "unrestricted_trade_match": stable_digest(
            [row for row in unrestricted_control["order_ledger"] if row.get("action") in {"buy", "sell"}]
        )
        == baseline_trade_digest,
        "frozen_nav_match": stable_digest(frozen_control["nav_rows"]) == baseline_nav_digest,
        "frozen_trade_match": stable_digest(
            [row for row in frozen_control["order_ledger"] if row.get("action") in {"buy", "sell"}]
        )
        == baseline_trade_digest,
    }
    if not all(control_reproduction.values()):
        raise ValueError(f"market-confirmed controls failed to reproduce V3: {control_reproduction}")

    validation_start = DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END)
    segment_ranges = {
        "tuning": (None, DEFAULT_TUNING_END),
        "validation": (validation_start, DEFAULT_VALIDATION_END),
        "full_pre_extended": (None, DEFAULT_VALIDATION_END),
    }
    baseline_segments = {
        key: _segment_metrics(baseline, start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    variant_accounts: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    for variant in variants:
        exit_signals, trim_signals, signal_audit = build_market_confirmed_lifecycle_actions(
            selected_picks_by_date=selected_by_day,
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            sector_states=sector_states,
            common_deterioration=design["common_position_deterioration"],
            variant=variant,
            signal_end=signal_end,
        )
        if signal_audit["future_feature_violation_count"]:
            raise ValueError("market-confirmed lifecycle generated a PIT violation")
        variant_id = str(variant["id"])
        unrestricted = replay(
            selected=selected_rows,
            exit_signals=exit_signals,
            trim_signals=trim_signals,
            artifact_suffix=f"{variant_id}-shared",
        )
        frozen = replay(
            selected=frozen_selected_rows,
            exit_signals=exit_signals,
            trim_signals=trim_signals,
            artifact_suffix=f"{variant_id}-frozen",
        )
        variant_accounts[variant_id] = (unrestricted, frozen)
        ledger_results: dict[str, Any] = {}
        for ledger_name, account in (("shared_cash", unrestricted), ("frozen_entry", frozen)):
            segments = {
                key: _segment_metrics(account, start=start, end=end)
                for key, (start, end) in segment_ranges.items()
            }
            ledger_results[ledger_name] = {
                "segments": segments,
                "gates": {
                    key: _lifecycle_risk_gate(segments[key], baseline_segments[key])
                    for key in segment_ranges
                },
                "action_counts": {
                    key: _lifecycle_sell_count(account, start=start, end=end)
                    for key, (start, end) in segment_ranges.items()
                },
                "validation_monthly_delta": _monthly_delta_summary(
                    account, baseline, start=validation_start, end=DEFAULT_VALIDATION_END
                ),
                "buy_key_audit": _buy_key_audit(account, baseline),
            }
        row = {
            "variant_id": variant_id,
            "complexity_order": int(variant["complexity_order"]),
            "action": variant["action"],
            "signal_audit": signal_audit,
            "ledgers": ledger_results,
        }
        rows.append(row)
        shared = ledger_results["shared_cash"]
        frozen = ledger_results["frozen_entry"]
        if (
            shared["action_counts"]["validation"] >= MINIMUM_VALIDATION_ACTION_COUNT
            and frozen["action_counts"]["validation"] >= MINIMUM_VALIDATION_ACTION_COUNT
            and shared["gates"]["tuning"]["passed"]
            and shared["gates"]["validation"]["passed"]
            and frozen["gates"]["tuning"]["passed"]
            and frozen["gates"]["validation"]["passed"]
            and float(shared["validation_monthly_delta"]["mean_monthly_return_delta"]) > 0.0
            and float(frozen["validation_monthly_delta"]["mean_monthly_return_delta"]) > 0.0
            and frozen["buy_key_audit"]["candidate_only_buy_key_count"] == 0
            and frozen["buy_key_audit"]["missing_baseline_buy_key_count"] == 0
        ):
            eligible_rows.append(row)

    selected: dict[str, Any] | None = None
    if eligible_rows:
        best = max(
            eligible_rows,
            key=lambda row: float(
                row["ledgers"]["shared_cash"]["validation_monthly_delta"]["mean_monthly_return_delta"]
            ),
        )
        best_delta = best["ledgers"]["shared_cash"]["validation_monthly_delta"]
        floor = float(best_delta["mean_monthly_return_delta"]) - float(
            best_delta["monthly_delta_standard_error"]
        )
        selected = min(
            [
                row
                for row in eligible_rows
                if float(
                    row["ledgers"]["shared_cash"]["validation_monthly_delta"]["mean_monthly_return_delta"]
                )
                >= floor
            ],
            key=lambda row: int(row["complexity_order"]),
        )

    extended_readout: dict[str, Any] | None = None
    if selected is not None:
        variant_id = str(selected["variant_id"])
        unrestricted, frozen = variant_accounts[variant_id]
        baseline_extended = _segment_metrics(baseline, start=DEFAULT_FINAL_START, end=signal_end)
        extended_readout = {"variant_id": variant_id, "baseline": baseline_extended, "ledgers": {}}
        for ledger_name, account in (("shared_cash", unrestricted), ("frozen_entry", frozen)):
            metrics = _segment_metrics(account, start=DEFAULT_FINAL_START, end=signal_end)
            extended_readout["ledgers"][ledger_name] = {
                "metrics": metrics,
                "gate": _lifecycle_risk_gate(metrics, baseline_extended),
                "action_count": _lifecycle_sell_count(account, start=DEFAULT_FINAL_START, end=signal_end),
                "monthly_delta": _monthly_delta_summary(
                    account, baseline, start=DEFAULT_FINAL_START, end=signal_end
                ),
                "buy_order_delta": _buy_order_delta(
                    account, baseline, start=DEFAULT_FINAL_START, end=signal_end
                ),
            }

    selected_survived_extended = bool(
        extended_readout
        and all(row["gate"]["passed"] for row in extended_readout["ledgers"].values())
    )
    material = {
        "artifact_type": "v3_market_confirmed_lifecycle_challenger",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_preselection_and_reused_extended"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "preregistered_pit_negative_context_partial_lifecycle_attribution_not_v3_change_not_production_ready",
        "source_execution_snapshot_id": source_snapshot["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "personal_eligibility_audit": eligibility_audit,
        "control_reproduction": control_reproduction,
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["variant_id"],
        "extended_readout": extended_readout,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "provider_revision_lineage_missing": True,
        "promotion_blockers": [
            "sector_provider_revision_lineage_missing",
            "new_independent_time_holdout_missing",
            "true_forward_shadow_missing",
        ],
        "v3_entry_selection_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"v3-market-confirmed-lifecycle-{digest[:16]}", **material, "content_digest": digest}


def write_v3_market_confirmed_lifecycle_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("V3 market-confirmed lifecycle result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable V3 market-confirmed lifecycle result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
