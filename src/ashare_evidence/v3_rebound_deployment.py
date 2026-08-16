from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

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
    _segment_metrics,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.stock_transition_sleeve import (
    DEFAULT_WEIGHTS,
    _monthly_delta_summary,
    _risk_budget_gate,
    stock_transition_features,
)

SCHEMA_VERSION = "v3_rebound_deployment_accelerator.v1"
DEFAULT_MINIMUM_VALIDATION_TRIGGER_DAYS = 12


def rebound_deployment_trigger(
    *,
    picks: list[dict[str, Any]],
    signal_day: str,
    sector_state: dict[str, Any],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> tuple[bool, dict[str, Any]]:
    transition_rows = [
        stock_transition_features(
            symbol=str(pick["symbol"]),
            signal_day=signal_day,
            market_bars_by_symbol=market_bars_by_symbol,
        )
        for pick in picks
    ]
    if not transition_rows or any(row is None for row in transition_rows):
        return False, {"status": "missing_stock_transition_history", "triggered": False}
    ready_rows = [row for row in transition_rows if row is not None]
    breadth_acceleration = float(sector_state["breadth_5d"]) - float(sector_state["breadth_20d"])
    sector_return_acceleration = (
        float(sector_state["mean_return_5d"]) / 5.0
        - float(sector_state["mean_return_20d"]) / 20.0
    )
    median_return_5d = median(float(row["return_5d"]) for row in ready_rows)
    median_stock_acceleration = median(float(row["return_acceleration_5d"]) for row in ready_rows)
    triggered = bool(
        breadth_acceleration > 0.0
        and sector_return_acceleration > 0.0
        and median_return_5d > 0.0
        and median_stock_acceleration > 0.0
    )
    return triggered, {
        "status": "ready",
        "triggered": triggered,
        "breadth_acceleration": breadth_acceleration,
        "sector_return_acceleration": sector_return_acceleration,
        "median_v3_top3_return_5d": median_return_5d,
        "median_v3_top3_return_acceleration_5d": median_stock_acceleration,
    }


def apply_rebound_deployment_boost(
    picks: list[dict[str, Any]], *, weight: float, triggered: bool
) -> list[dict[str, Any]]:
    output = copy.deepcopy(picks)
    if not triggered or weight == 0.0:
        return output
    for row in output:
        row["portfolio_weight"] = float(row.get("portfolio_weight") or 1.0) * (1.0 + weight)
        row["rebound_deployment_weight"] = weight
    return output


def _hybrid_risk_budget_gate(
    candidate: dict[str, Any], *, frozen_baseline: dict[str, Any], instrumented_lambda_zero: dict[str, Any]
) -> dict[str, Any]:
    comparator = copy.deepcopy(frozen_baseline)
    comparator["skipped_order_rate"] = instrumented_lambda_zero["skipped_order_rate"]
    comparator["skipped_signal_rate"] = instrumented_lambda_zero["skipped_signal_rate"]
    return _risk_budget_gate(candidate, comparator)


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("rebound deployment design must be frozen before outcome evaluation")
    observed = {
        "weights": [float(value) for value in design["carrier"]["weights"]],
        "minimum_validation_trigger_days": int(design["trigger"]["minimum_validation_trigger_days"]),
    }
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "minimum_validation_trigger_days": DEFAULT_MINIMUM_VALIDATION_TRIGGER_DAYS,
    }
    if observed != expected:
        raise ValueError(f"rebound deployment implementation differs from frozen design: {observed}")


def run_v3_rebound_deployment_accelerator(
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
    snapshot, eligibility_audit = build_personal_eligible_execution_snapshot(source_snapshot)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    if sector_snapshot["content_digest"] != design["data_contract"]["sector_market_digest"]:
        raise ValueError("sector snapshot digest does not match the frozen design")

    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"],
        decision_dates=[date.fromisoformat(day) for day in original_by_date],
    )
    if set(original_by_date) != set(inventory_by_date) or set(sector_states) != set(original_by_date):
        raise ValueError("full-window personal V3, inventory, and PIT sector coverage must match")

    trigger_by_day: dict[str, bool] = {}
    trigger_audit_by_day: dict[str, dict[str, Any]] = {}
    for day in sorted(original_by_date):
        trigger_by_day[day], trigger_audit_by_day[day] = rebound_deployment_trigger(
            picks=original_by_date[day],
            signal_day=day,
            sector_state=sector_states[day],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
        )

    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))

    def replay(weight: float) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for day in sorted(original_by_date):
            picks = apply_rebound_deployment_boost(
                original_by_date[day], weight=weight, triggered=trigger_by_day[day]
            )
            for pick in picks:
                slot = (day, int(float(pick["rank"])))
                pick["shadow_baseline_buy_symbols"] = sorted(baseline_buy_symbols_by_slot.get(slot, set()))
                pick["rebound_deployment_triggered"] = trigger_by_day[day]
            selected.extend(picks)
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=weight)
        candidate_run["artifact_id"] = f"v3-rebound-deployment-{weight:.3f}"
        account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        baseline_buy_keys = {
            (str(row["signal_day"]), int(row["rank"]), str(row["symbol"]))
            for row in baseline_account["order_ledger"]
            if row.get("action") == "buy"
        }
        candidate_buy_keys = {
            (str(row["signal_day"]), int(row["rank"]), str(row["symbol"]))
            for row in account["order_ledger"]
            if row.get("action") == "buy"
        }
        return account, {
            "triggered_signal_day_count": sum(trigger_by_day.values()),
            "candidate_only_buy_key_count": len(candidate_buy_keys - baseline_buy_keys),
            "missing_baseline_buy_key_count": len(baseline_buy_keys - candidate_buy_keys),
        }

    accounts: dict[float, dict[str, Any]] = {}
    execution_audits: dict[float, dict[str, Any]] = {}
    for weight in DEFAULT_WEIGHTS:
        accounts[weight], execution_audits[weight] = replay(weight)
        if execution_audits[weight]["candidate_only_buy_key_count"]:
            raise ValueError("rebound deployment created a buy outside the frozen baseline buy scope")

    lambda_zero_nav_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    lambda_zero_trade_match = stable_digest(
        [row for row in accounts[0.0]["order_ledger"] if row.get("action") in {"buy", "sell"}]
    ) == stable_digest(
        [row for row in baseline_account["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    if not lambda_zero_nav_match or not lambda_zero_trade_match:
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
    instrumented_segments = {
        key: _segment_metrics(accounts[0.0], start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    trigger_counts = {
        "tuning": sum(
            triggered and date.fromisoformat(day) <= DEFAULT_TUNING_END
            for day, triggered in trigger_by_day.items()
        ),
        "validation": sum(
            triggered and DEFAULT_TUNING_END < date.fromisoformat(day) <= DEFAULT_VALIDATION_END
            for day, triggered in trigger_by_day.items()
        ),
        "extended": sum(
            triggered and date.fromisoformat(day) >= DEFAULT_FINAL_START
            for day, triggered in trigger_by_day.items()
        ),
    }

    rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    for weight in DEFAULT_WEIGHTS:
        segments = {
            key: _segment_metrics(accounts[weight], start=start, end=end)
            for key, (start, end) in segment_ranges.items()
        }
        gates = {
            key: _hybrid_risk_budget_gate(
                value,
                frozen_baseline=baseline_segments[key],
                instrumented_lambda_zero=instrumented_segments[key],
            )
            for key, value in segments.items()
        }
        validation_monthly_delta = _monthly_delta_summary(
            accounts[weight],
            baseline_account,
            start=segment_ranges["validation"][0],
            end=DEFAULT_VALIDATION_END,
        )
        row = {
            "weight": weight,
            "execution_audit": execution_audits[weight],
            "segments": segments,
            "gates": gates,
            "validation_monthly_delta": validation_monthly_delta,
        }
        rows.append(row)
        if (
            weight > 0.0
            and trigger_counts["validation"] >= DEFAULT_MINIMUM_VALIDATION_TRIGGER_DAYS
            and gates["tuning"]["passed"]
            and gates["validation"]["passed"]
            and float(validation_monthly_delta["mean_monthly_return_delta"]) > 0.0
        ):
            eligible_rows.append(row)

    selected: dict[str, Any] | None = None
    if eligible_rows:
        best = max(
            eligible_rows,
            key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]),
        )
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        selected = min(
            [
                row
                for row in eligible_rows
                if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor
            ],
            key=lambda row: float(row["weight"]),
        )

    extended_readout: dict[str, Any] | None = None
    if selected is not None:
        selected_weight = float(selected["weight"])
        baseline_extended = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        instrumented_extended = _segment_metrics(accounts[0.0], start=DEFAULT_FINAL_START, end=signal_end)
        candidate_extended = _segment_metrics(accounts[selected_weight], start=DEFAULT_FINAL_START, end=signal_end)
        extended_readout = {
            "weight": selected_weight,
            "baseline": baseline_extended,
            "candidate": candidate_extended,
            "gate": _hybrid_risk_budget_gate(
                candidate_extended,
                frozen_baseline=baseline_extended,
                instrumented_lambda_zero=instrumented_extended,
            ),
            "monthly_delta": _monthly_delta_summary(
                accounts[selected_weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
            "buy_order_delta": _buy_order_delta(
                accounts[selected_weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }

    selected_survived_extended = bool(extended_readout and extended_readout["gate"]["passed"])
    material = {
        "artifact_type": "v3_rebound_deployment_accelerator",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_preselection_and_reused_extended"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "research_only_same_stock_deployment_accelerator_not_v3_change",
        "source_execution_snapshot_id": source_snapshot["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "personal_eligibility_audit": eligibility_audit,
        "trigger_audit": {
            "counts": trigger_counts,
            "daily_audit_digest": stable_digest(trigger_audit_by_day),
            "future_feature_violations": 0,
        },
        "lambda_zero_reproduction": {
            "passed": lambda_zero_nav_match and lambda_zero_trade_match,
            "economic_nav_match": lambda_zero_nav_match,
            "executed_buy_sell_ledger_match": lambda_zero_trade_match,
        },
        "baseline_segments_pre_extended": baseline_segments,
        "instrumented_lambda_zero_segments_pre_extended": instrumented_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["weight"],
        "extended_readout": extended_readout,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "provider_revision_lineage_missing": True,
        "promotion_blockers": [
            "sector_provider_revision_lineage_missing",
            "new_independent_time_holdout_missing",
        ],
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"v3-rebound-deployment-{digest[:16]}", **material, "content_digest": digest}


def write_v3_rebound_deployment_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("V3 rebound deployment result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable V3 rebound deployment result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
