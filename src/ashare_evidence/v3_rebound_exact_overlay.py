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

SCHEMA_VERSION = "v3_rebound_exact_increment_overlay.v1"


def build_exact_v3_overlay_pick(pick: dict[str, Any]) -> dict[str, Any]:
    """Remove outcome fields without changing the original V3 execution recipe."""

    return {key: copy.deepcopy(value) for key, value in pick.items() if key not in FORBIDDEN_RESULT_FIELDS}


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("V3 rebound exact overlay design must be frozen before outcome evaluation")
    observed = {
        "weights": [float(value) for value in design["portfolio_carrier"]["weights"]],
        "minimum_validation_trigger_days": int(design["trigger"]["minimum_validation_trigger_days"]),
        "preserve_execution_recipe": bool(
            design["overlay"]["preserve_stock_symbol_rank_allocation_horizon_and_execution_config"]
        ),
        "separate_cash_ledger": bool(design["overlay"]["separate_cash_ledger"]),
    }
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "minimum_validation_trigger_days": DEFAULT_MINIMUM_VALIDATION_TRIGGER_DAYS,
        "preserve_execution_recipe": True,
        "separate_cash_ledger": True,
    }
    if observed != expected:
        raise ValueError(f"V3 rebound exact overlay implementation differs from frozen design: {observed}")


def _pick_execution_recipe(pick: dict[str, Any]) -> dict[str, Any]:
    ignored = set(FORBIDDEN_RESULT_FIELDS)
    return {key: value for key, value in pick.items() if key not in ignored}


def run_v3_rebound_exact_overlay(
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
            overlay_picks.extend(build_exact_v3_overlay_pick(row) for row in original_by_date[day])

    overlay_trial = copy.deepcopy(trial)
    overlay_trial["selected_top_k_picks_by_date"] = overlay_picks
    overlay_trial["model_spec_id"] = "v3_exact_top3_rebound_date_subset_v1"
    overlay_run = {
        "artifact_id": f"v3-rebound-exact-overlay-{stable_digest(overlay_picks)[:16]}",
        "trial_diagnostics": [overlay_trial],
    }
    overlay_config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
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
    validation_start = DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END)
    segment_ranges = {
        "tuning": (None, DEFAULT_TUNING_END),
        "validation": (validation_start, DEFAULT_VALIDATION_END),
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
    trigger_dates = {str(row["as_of_date"]) for row in overlay_picks}
    trigger_counts = {
        "tuning": sum(date.fromisoformat(day) <= DEFAULT_TUNING_END for day in trigger_dates),
        "validation": sum(
            DEFAULT_TUNING_END < date.fromisoformat(day) <= DEFAULT_VALIDATION_END for day in trigger_dates
        ),
        "extended": sum(date.fromisoformat(day) >= DEFAULT_FINAL_START for day in trigger_dates),
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
            start=validation_start,
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

    original_by_key = {
        (str(row["as_of_date"]), int(float(row["rank"]))): row
        for rows_for_day in original_by_date.values()
        for row in rows_for_day
    }
    exact_recipe_match_count = sum(
        _pick_execution_recipe(row)
        == _pick_execution_recipe(original_by_key[(str(row["as_of_date"]), int(float(row["rank"])))])
        for row in overlay_picks
    )
    baseline_config_match = stable_digest(overlay_config) == stable_digest(snapshot["inputs"]["baseline_config"])
    lambda_zero_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    selected_survived_extended = bool(extended_readout and extended_readout["gate"]["passed"])
    material = {
        "artifact_type": "v3_rebound_exact_increment_overlay",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_preselection_and_reused_extended"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "preregistered_exact_trigger_subset_attribution_not_v3_change_not_production_ready",
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
            "signal_date_count": len(trigger_dates),
            "selection_count": len(overlay_picks),
            "exact_original_recipe_match_count": exact_recipe_match_count,
            "baseline_execution_config_match": baseline_config_match,
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
    return {"artifact_id": f"v3-rebound-exact-overlay-{digest[:16]}", **material, "content_digest": digest}


def write_v3_rebound_exact_overlay_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("V3 rebound exact overlay result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable V3 rebound exact overlay result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
