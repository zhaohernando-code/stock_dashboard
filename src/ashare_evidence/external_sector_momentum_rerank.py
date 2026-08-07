from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
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
    _monthly_delta_summary,
    _non_degrade,
    _segment_metrics,
    _standout,
)
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "external_sector_momentum_rerank_account_ablation.v1"


def _hybrid_gate(
    candidate: dict[str, Any],
    *,
    frozen_v3: dict[str, Any],
    instrumented_lambda_zero: dict[str, Any],
) -> dict[str, Any]:
    comparator = copy.deepcopy(frozen_v3)
    for metric in ("skipped_order_rate", "skipped_signal_rate"):
        comparator[metric] = instrumented_lambda_zero[metric]
    return _non_degrade(candidate, comparator)


def run_external_sector_momentum_rerank_ablation(
    *,
    execution_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round29_outcome_evaluation":
        raise ValueError("sector momentum rerank design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    expected_digest = design["data_contract"]["sector_market_digest"]
    if sector_snapshot["content_digest"] != expected_digest:
        raise ValueError("sector snapshot digest does not match the frozen design")
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    pool_depth = int(design["candidate_boundary"]["maximum_original_rank"])
    inventory_by_date = {
        day: sorted(
            [row for row in rows if int(float(row["rank"])) <= pool_depth],
            key=lambda row: int(float(row["rank"])),
        )
        for day, rows in inventory_by_date.items()
    }
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"], decision_dates=decision_dates
    )
    if set(sector_states) != set(inventory_by_date):
        raise ValueError("full-window sector state coverage is incomplete")
    baseline_account = snapshot["baseline_output"]
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))

    def replay(weight: float) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        changed_dates = 0
        changed_slots = 0
        promoted_from_rank4_or_5 = 0
        eligible_candidate_counts: list[int] = []
        cap = float(design["carrier"]["maximum_absolute_external_contribution"])
        max_score_gap = float(design["candidate_boundary"]["maximum_raw_score_gap_from_original_rank3"])
        for day in sorted(inventory_by_date):
            inventory = copy.deepcopy(inventory_by_date[day])
            original = sorted(copy.deepcopy(original_by_date[day]), key=lambda row: int(float(row["rank"])))
            rank3_score = float(original[-1]["score"])
            eligible = [row for row in inventory if float(row["score"]) >= rank3_score - max_score_gap]
            original_symbols = {str(row["symbol"]) for row in original}
            for row in original:
                if str(row["symbol"]) not in {str(value["symbol"]) for value in eligible}:
                    eligible.append(copy.deepcopy(row))
            eligible_candidate_counts.append(len(eligible))
            if weight == 0:
                chosen = original
            else:
                core_z = _z_scores([float(row["score"]) for row in eligible])
                sector_values: list[float] = []
                for row in eligible:
                    sw_name = SW_L1_BY_SUBINDUSTRY.get(str(row.get("industry_name") or ""), "")
                    sw_row = (sector_states[day].get("by_sector_name") or {}).get(sw_name) or {}
                    sector_values.append(float(sw_row.get("relative_20d") or 0.0))
                sector_z = _z_scores(sector_values)
                for row, core_value, raw_sector_value, sector_value in zip(
                    eligible, core_z, sector_values, sector_z, strict=True
                ):
                    contribution = max(-cap, min(cap, weight * sector_value))
                    row["sector_relative_20d"] = raw_sector_value
                    row["external_sector_momentum_z"] = sector_value
                    row["external_sector_contribution"] = contribution
                    row["external_adjusted_score"] = core_value + contribution
                eligible.sort(key=lambda row: (-float(row["external_adjusted_score"]), -float(row["score"])))
                chosen = eligible[: len(original)]
            rebuilt: list[dict[str, Any]] = []
            for index, candidate in enumerate(chosen):
                template = original[index]
                unchanged_slot = str(candidate["symbol"]) == str(template["symbol"])
                shadow_buy_symbols = (
                    sorted(baseline_buy_symbols_by_slot.get((day, index + 1), set()))
                    if unchanged_slot
                    else [str(candidate["symbol"])]
                )
                rebuilt.append(
                    {
                        **candidate,
                        "rank": index + 1,
                        "portfolio_weight": float(template.get("portfolio_weight") or 1.0),
                        "rank_weight_multiplier": float(template.get("rank_weight_multiplier") or 0.0),
                        "target_horizon_days": int(float(template.get("target_horizon_days") or 20)),
                        "shadow_baseline_buy_symbols": shadow_buy_symbols,
                    }
                )
                if not unchanged_slot:
                    changed_slots += 1
                    promoted_from_rank4_or_5 += int(str(candidate["symbol"]) not in original_symbols)
            changed_dates += int(
                any(str(candidate["symbol"]) != str(template["symbol"]) for candidate, template in zip(rebuilt, original, strict=True))
            )
            selected.extend(rebuilt)
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=weight)
        candidate_run["artifact_id"] = f"external-sector-momentum-rerank-{weight:.3f}"
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
            "promoted_from_original_rank4_or_5_count": promoted_from_rank4_or_5,
            "mean_near_tie_candidate_count": sum(eligible_candidate_counts) / len(eligible_candidate_counts),
        }

    weights = [float(value) for value in design["weights"]]
    accounts: dict[float, dict[str, Any]] = {}
    audits: dict[float, dict[str, Any]] = {}
    for weight in weights:
        accounts[weight], audits[weight] = replay(weight)
    nav_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    trade_match = stable_digest(
        [row for row in accounts[0.0]["order_ledger"] if row.get("action") in {"buy", "sell"}]
    ) == stable_digest(
        [row for row in baseline_account["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    if not (nav_match and trade_match):
        raise ValueError("lambda zero failed to reproduce frozen V3 economics")
    segment_ranges = {
        "tuning": (None, DEFAULT_TUNING_END),
        "validation": (DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END), DEFAULT_VALIDATION_END),
        "full_pre_extended": (None, DEFAULT_VALIDATION_END),
    }
    frozen_segments = {
        key: _segment_metrics(baseline_account, start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    instrumented_segments = {
        key: _segment_metrics(accounts[0.0], start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    rows: list[dict[str, Any]] = []
    for weight in weights:
        segments = {
            key: _segment_metrics(accounts[weight], start=start, end=end)
            for key, (start, end) in segment_ranges.items()
        }
        rows.append(
            {
                "weight": weight,
                "change_audit": audits[weight],
                "segments": segments,
                "gates": {
                    key: _hybrid_gate(
                        value,
                        frozen_v3=frozen_segments[key],
                        instrumented_lambda_zero=instrumented_segments[key],
                    )
                    for key, value in segments.items()
                },
                "validation_monthly_delta": _monthly_delta_summary(
                    accounts[weight],
                    baseline_account,
                    start=segment_ranges["validation"][0],
                    end=DEFAULT_VALIDATION_END,
                ),
            }
        )
    eligible_rows = [
        row
        for row in rows
        if row["weight"] > 0
        and row["change_audit"]["changed_date_count"] > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
    ]
    selected = None
    if eligible_rows:
        best = max(eligible_rows, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        selected = min(
            [row for row in eligible_rows if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor],
            key=lambda row: float(row["weight"]),
        )
    extended = None
    if selected is not None:
        weight = float(selected["weight"])
        frozen_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        instrumented_final = _segment_metrics(accounts[0.0], start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[weight], start=DEFAULT_FINAL_START, end=signal_end)
        extended = {
            "weight": weight,
            "baseline": frozen_final,
            "candidate": candidate_final,
            "gate": _hybrid_gate(
                candidate_final,
                frozen_v3=frozen_final,
                instrumented_lambda_zero=instrumented_final,
            ),
            "standout": _standout(candidate_final, frozen_final),
            "buy_order_delta": _buy_order_delta(accounts[weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end),
        }
    passed = bool(extended and extended["gate"]["passed"] and extended["standout"]["passed"])
    material = {
        "artifact_type": "external_sector_momentum_rerank_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_near_tie_sector_momentum_rerank_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "lambda_zero_reproduction": {
            "passed": nav_match and trade_match,
            "economic_nav_match": nav_match,
            "executed_buy_sell_ledger_match": trade_match,
        },
        "gate_comparator_contract": {
            "economic_and_risk_metrics": "frozen V3 snapshot",
            "skip_rate_metrics": "lambda-zero replay with identical shadow-guard instrumentation",
        },
        "baseline_segments_pre_extended": frozen_segments,
        "instrumented_lambda_zero_segments_pre_extended": instrumented_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["weight"],
        "extended_readout": extended,
        "extended_readout_status": "reused_evaluation_not_untouched_due_prior_iterations",
        "future_feature_violations": 0,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"external-sector-momentum-rerank-{digest[:16]}", **material, "content_digest": digest}


def write_external_sector_momentum_rerank_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("sector momentum rerank result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable sector momentum rerank result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
