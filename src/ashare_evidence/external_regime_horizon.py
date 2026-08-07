from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
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
    _segment_metrics,
    _standout,
)
from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
)
from ashare_evidence.rolling_tranche_account_replay import (
    build_shortpick_v3_rolling_account_replay_artifact,
)

SCHEMA_VERSION = "external_regime_horizon.v1"


def past_only_regime_percentiles(
    *,
    picks_by_date: dict[str, list[dict[str, Any]]],
    global_states: dict[str, dict[str, Any]],
    sector_states: dict[str, dict[str, Any]],
    minimum_prior_days: int = 60,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    prior: list[float] = []
    percentiles: dict[str, float | None] = {}
    raw_scores: dict[str, float] = {}
    for day in sorted(picks_by_date):
        rank1 = next(row for row in picks_by_date[day] if int(float(row.get("rank") or 0)) == 1)
        sector_name = SW_L1_BY_SUBINDUSTRY[str(rank1.get("industry_name") or "")]
        state = sector_states[day]
        sector_rows = list((state["by_sector_name"] or {}).values())
        relative_values = [float(row["relative_5d"]) for row in sector_rows]
        sector_scale = pstdev(relative_values) if len(relative_values) > 1 else 0.0
        rank1_sector_relative_z = (
            float(state["by_sector_name"][sector_name]["relative_5d"]) / sector_scale
            if sector_scale > 1e-12
            else 0.0
        )
        global_state = global_states[day]
        score = (
            0.30 * (float(state["breadth_5d"]) - 0.5) * 2.0
            + 0.20 * (float(state["breadth_20d"]) - 0.5) * 2.0
            + 0.25 * (float(global_state["global_breadth_5d"]) - 0.5) * 2.0
            + 0.10 * (float(global_state["global_breadth_20d"]) - 0.5) * 2.0
            + 0.15 * max(-2.0, min(2.0, rank1_sector_relative_z)) / 2.0
        )
        raw_scores[day] = score
        if len(prior) < minimum_prior_days:
            percentiles[day] = None
        else:
            percentiles[day] = sum(value <= score for value in prior) / len(prior)
        prior.append(score)
    return percentiles, {
        "past_only": True,
        "minimum_prior_days": minimum_prior_days,
        "ready_day_count": sum(value is not None for value in percentiles.values()),
        "warmup_day_count": sum(value is None for value in percentiles.values()),
        "raw_score_min": min(raw_scores.values()),
        "raw_score_max": max(raw_scores.values()),
        "raw_score_mean": mean(raw_scores.values()),
        "future_observation_violations": 0,
    }


def run_external_regime_horizon_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date = date(2026, 6, 26),
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round19_outcome_evaluation":
        raise ValueError("round19 design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    global_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    global_states = market_state_by_decision_date(global_snapshot["records"], decision_dates=decision_dates)
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"], decision_dates=decision_dates
    )
    if set(global_states) != set(inventory_by_date) or set(sector_states) != set(inventory_by_date):
        raise ValueError("external regime state is incomplete")
    percentiles, state_audit = past_only_regime_percentiles(
        picks_by_date=picks_by_date,
        global_states=global_states,
        sector_states=sector_states,
        minimum_prior_days=int(design["state"]["minimum_prior_days"]),
    )

    def replay(selected: list[dict[str, Any]], artifact_id: str) -> dict[str, Any]:
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = artifact_id
        artifact = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )
        return artifact["results"][0]

    baseline_selected = [copy.deepcopy(row) for day in sorted(picks_by_date) for row in picks_by_date[day]]
    baseline_account = replay(baseline_selected, "round19-lambda-zero-v3")
    baseline_buy_keys = {
        (str(row["signal_day"]), str(row["symbol"]), int(row["rank"]))
        for row in baseline_account["order_ledger"]
        if row.get("action") == "buy"
    }
    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_final": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    results: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, Any]] = {}
    for variant in design["variants"]:
        selected: list[dict[str, Any]] = []
        risk_dates: list[str] = []
        rebound_dates: list[str] = []
        for day in sorted(picks_by_date):
            picks = copy.deepcopy(picks_by_date[day])
            for pick in picks:
                pick["shadow_baseline_buy_eligible"] = (
                    day,
                    str(pick.get("symbol") or ""),
                    int(float(pick.get("rank") or 0)),
                ) in baseline_buy_keys
            rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
            percentile = percentiles[day]
            if (day, str(rank1.get("symbol") or ""), 1) in baseline_buy_keys and percentile is not None:
                if percentile <= float(variant["risk_percentile_max"]):
                    rank1["target_horizon_days"] = int(variant["risk_horizon_days"])
                    risk_dates.append(day)
                elif percentile >= float(variant["rebound_percentile_min"]):
                    rank1["target_horizon_days"] = int(variant["rebound_horizon_days"])
                    rebound_dates.append(day)
                rank1["external_regime_past_only_percentile"] = percentile
            selected.extend(picks)
        variant_id = str(variant["variant_id"])
        account = replay(selected, f"round19-{variant_id}")
        accounts[variant_id] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_final": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        results.append(
            {
                "variant": variant,
                "trigger_audit": {
                    "risk_day_count": len(risk_dates),
                    "rebound_day_count": len(rebound_dates),
                    "risk_dates": risk_dates,
                    "rebound_dates": rebound_dates,
                    "shadow_fill_constraint": True,
                },
                "segments": segments,
                "gates": {
                    segment: _non_degrade(segments[segment], baseline_segments[segment]) for segment in segments
                },
                "standout": {
                    segment: _standout(segments[segment], baseline_segments[segment]) for segment in segments
                },
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
        for row in results
        if row["trigger_audit"]["risk_day_count"] + row["trigger_audit"]["rebound_day_count"] > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
    ]
    selected_row: dict[str, Any] | None = None
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
                abs(int(row["variant"]["risk_horizon_days"]) - 20)
                + abs(int(row["variant"]["rebound_horizon_days"]) - 20),
                float(row["variant"]["rebound_percentile_min"])
                - float(row["variant"]["risk_percentile_max"]),
            ),
        )
    final: dict[str, Any] | None = None
    if selected_row is not None:
        selected_id = str(selected_row["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[selected_id], start=DEFAULT_FINAL_START, end=signal_end)
        final = {
            "variant_id": selected_id,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(
                accounts[selected_id], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }
    passed = bool(selected_row is not None and final and final["gate"]["passed"] and final["standout"]["passed"])
    material = {
        "artifact_type": "external_regime_horizon_ablation",
        "schema_version": SCHEMA_VERSION,
        "round": 19,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_global_and_sw_sector_regime_horizon_account_replay",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_global_market_digest": global_snapshot["content_digest"],
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "state_audit": state_audit,
        "baseline_segments_pre_final": baseline_segments,
        "results_pre_final": results,
        "selection_before_final": None if selected_row is None else selected_row["variant"]["variant_id"],
        "final_untouched_readout": final,
        "new_fill_allowed": False,
        "v3_symbol_selection_changed": False,
        "promotion_blocker": "provisional_market_sources_require_qualified_vendor_revision_reproduction",
    }
    digest = stable_digest(material)
    return {
        "artifact_id": f"external-regime-horizon-{digest[:16]}",
        **material,
        "content_digest": digest,
    }
