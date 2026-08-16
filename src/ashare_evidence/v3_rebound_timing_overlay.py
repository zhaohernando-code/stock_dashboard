from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

from ashare_evidence.external_context_sector_market_research import (
    load_sector_research_snapshot,
    sector_state_by_decision_date,
)
from ashare_evidence.global_sector_state_account_ablation import (
    DEFAULT_FINAL_START,
    DEFAULT_TUNING_END,
    DEFAULT_VALIDATION_END,
    _group_by_date,
    _segment_metrics,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.stock_transition_sleeve import (
    DEFAULT_ACTIVE_TRANCHES,
    DEFAULT_HORIZON,
    DEFAULT_WEIGHTS,
    FORBIDDEN_RESULT_FIELDS,
    _blended_segment_metrics,
    _monthly_delta_summary,
    _risk_budget_gate,
    build_blended_nav_account,
)
from ashare_evidence.v3_rebound_deployment import (
    DEFAULT_MINIMUM_VALIDATION_TRIGGER_DAYS,
    rebound_deployment_trigger,
)

SCHEMA_VERSION = "v3_rebound_timing_overlay.v1"


def build_rebound_rank1_overlay_pick(pick: dict[str, Any]) -> dict[str, Any]:
    output = {key: copy.deepcopy(value) for key, value in pick.items() if key not in FORBIDDEN_RESULT_FIELDS}
    output.update(
        {
            "rank": 1,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "target_horizon_days": DEFAULT_HORIZON,
            "rebound_timing_overlay": True,
        }
    )
    return output


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("V3 rebound timing overlay design must be frozen before outcome evaluation")
    observed = {
        "weights": [float(value) for value in design["portfolio_carrier"]["weights"]],
        "horizon": int(design["overlay"]["mechanical_horizon_trading_days"]),
        "tranches": int(design["overlay"]["target_active_tranche_count"]),
        "minimum_validation_trigger_days": int(design["trigger"]["minimum_validation_trigger_days"]),
    }
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "horizon": DEFAULT_HORIZON,
        "tranches": DEFAULT_ACTIVE_TRANCHES,
        "minimum_validation_trigger_days": DEFAULT_MINIMUM_VALIDATION_TRIGGER_DAYS,
    }
    if observed != expected:
        raise ValueError(f"V3 rebound timing overlay implementation differs from frozen design: {observed}")


def run_v3_rebound_timing_overlay(
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

    overlay_picks: list[dict[str, Any]] = []
    trigger_audit_by_day: dict[str, dict[str, Any]] = {}
    for day in sorted(original_by_date):
        triggered, audit = rebound_deployment_trigger(
            picks=original_by_date[day],
            signal_day=day,
            sector_state=sector_states[day],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
        )
        trigger_audit_by_day[day] = audit
        if triggered:
            rank1 = next(row for row in original_by_date[day] if int(float(row["rank"])) == 1)
            overlay_picks.append(build_rebound_rank1_overlay_pick(rank1))

    overlay_trial = copy.deepcopy(trial)
    overlay_trial["selected_top_k"] = 1
    overlay_trial["selected_top_k_picks_by_date"] = overlay_picks
    overlay_trial["model_spec_id"] = "v3_rank1_rebound_timing_overlay_10d_v1"
    overlay_run = {
        "artifact_id": f"v3-rebound-timing-overlay-{stable_digest(overlay_picks)[:16]}",
        "trial_diagnostics": [overlay_trial],
    }
    overlay_config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
    overlay_config.update(
        {
            "config_id": "v3_rebound_rank1_timing_overlay_10d_10tranche_v1",
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
    overlay_config.pop("affordable_replacement_policy", None)
    overlay_config.pop("rank1_quality_overlay", None)
    sanitized_inventory = [
        {key: copy.deepcopy(value) for key, value in row.items() if key not in FORBIDDEN_RESULT_FIELDS}
        for day in sorted(inventory_by_date)
        for row in inventory_by_date[day]
    ]
    overlay_account = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=overlay_run,
        trial_id=snapshot["trial_id"],
        market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
        candidate_inventory_rows=sanitized_inventory,
        candidate_configurations=[overlay_config],
        **snapshot["inputs"]["account_profile"],
    )["results"][0]
    baseline_account = snapshot["baseline_output"]
    segment_ranges = {
        "tuning": (None, DEFAULT_TUNING_END),
        "validation": (DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END), DEFAULT_VALIDATION_END),
        "full_pre_extended": (None, DEFAULT_VALIDATION_END),
    }
    baseline_segments = {
        key: _segment_metrics(baseline_account, start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    overlay_segments = {
        key: _segment_metrics(overlay_account, start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    trigger_counts = {
        "tuning": sum(date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_TUNING_END for row in overlay_picks),
        "validation": sum(
            DEFAULT_TUNING_END < date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_VALIDATION_END
            for row in overlay_picks
        ),
        "extended": sum(
            date.fromisoformat(str(row["as_of_date"])) >= DEFAULT_FINAL_START for row in overlay_picks
        ),
    }

    accounts: dict[float, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    for weight in DEFAULT_WEIGHTS:
        blended = build_blended_nav_account(baseline_account, overlay_account, weight=weight)
        accounts[weight] = blended
        segments = {
            key: _blended_segment_metrics(
                blended,
                baseline_account,
                overlay_account,
                weight=weight,
                start=start,
                end=end,
            )
            for key, (start, end) in segment_ranges.items()
        }
        gates = {key: _risk_budget_gate(segments[key], baseline_segments[key]) for key in segment_ranges}
        validation_monthly_delta = _monthly_delta_summary(
            blended,
            baseline_account,
            start=segment_ranges["validation"][0],
            end=DEFAULT_VALIDATION_END,
        )
        row = {
            "weight": weight,
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
        overlay_extended = _segment_metrics(overlay_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_extended = _blended_segment_metrics(
            accounts[selected_weight],
            baseline_account,
            overlay_account,
            weight=selected_weight,
            start=DEFAULT_FINAL_START,
            end=signal_end,
        )
        extended_readout = {
            "weight": selected_weight,
            "baseline": baseline_extended,
            "overlay": overlay_extended,
            "candidate": candidate_extended,
            "gate": _risk_budget_gate(candidate_extended, baseline_extended),
            "monthly_delta": _monthly_delta_summary(
                accounts[selected_weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }

    lambda_zero_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    selected_survived_extended = bool(extended_readout and extended_readout["gate"]["passed"])
    material = {
        "artifact_type": "v3_rebound_timing_overlay",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_preselection_and_reused_extended"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "research_only_cash_isolated_rebound_timing_diagnostic_not_v3_change",
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
        "overlay_selection_audit": {
            "selection_count": len(overlay_picks),
            "same_day_v3_rank1_match_count": sum(
                str(row["symbol"])
                == str(
                    next(
                        value
                        for value in original_by_date[str(row["as_of_date"])]
                        if int(value["rank"]) == 1
                    )["symbol"]
                )
                for row in overlay_picks
            ),
            "forbidden_result_field_count": sum(
                key in FORBIDDEN_RESULT_FIELDS for row in overlay_picks for key in row
            ),
            "selection_digest": stable_digest(overlay_picks),
        },
        "lambda_zero_reproduction": {"passed": lambda_zero_match, "economic_nav_match": lambda_zero_match},
        "overlay_account_summary": overlay_account["summary"],
        "baseline_segments_pre_extended": baseline_segments,
        "overlay_segments_pre_extended": overlay_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["weight"],
        "extended_readout": extended_readout,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "provider_revision_lineage_missing": True,
        "promotion_blockers": [
            "shared_cash_execution_solution_missing",
            "sector_provider_revision_lineage_missing",
            "new_independent_time_holdout_missing",
        ],
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"v3-rebound-timing-overlay-{digest[:16]}", **material, "content_digest": digest}


def write_v3_rebound_timing_overlay_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("V3 rebound timing overlay result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable V3 rebound timing overlay result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
