from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

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
from ashare_evidence.official_facts_static_ablation import (
    _decision_cutoff,
    load_official_risk_events,
    official_risk_signal,
)
from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
)
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "official_event_account_guard.v1"


def run_official_event_account_guard_ablation(
    *,
    execution_snapshot_path: Path,
    external_root: Path,
    curation_path: Path,
    design_path: Path,
    signal_end: date = date(2026, 6, 26),
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    supported_rounds = {
        "frozen_before_round15_outcome_evaluation": 15,
        "frozen_before_round16_outcome_evaluation": 16,
        "frozen_before_round17_outcome_evaluation": 17,
        "frozen_before_round18_outcome_evaluation": 18,
    }
    if design.get("status") not in supported_rounds:
        raise ValueError("official-event design must be frozen before outcome evaluation")
    round_number = supported_rounds[str(design["status"])]
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    events_by_symbol, event_audit = load_official_risk_events(
        external_root=external_root,
        curation_path=curation_path,
    )
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)

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
    baseline_account = replay(baseline_selected, "round15-lambda-zero-v3")
    baseline_buy_keys = {
        (str(row["signal_day"]), str(row["symbol"]), int(row["rank"]))
        for row in baseline_account["order_ledger"]
        if row.get("action") == "buy"
    }
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))
    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_final": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    result_rows: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, Any]] = {}
    for variant in design["variants"]:
        selected: list[dict[str, Any]] = []
        trigger_dates: list[dict[str, Any]] = []
        suppressed_dates: list[dict[str, Any]] = []
        for day in sorted(picks_by_date):
            picks = copy.deepcopy(picks_by_date[day])
            for pick in picks:
                slot = (day, int(float(pick.get("rank") or 0)))
                pick["shadow_baseline_buy_symbols"] = sorted(baseline_buy_symbols_by_slot.get(slot, set()))
            rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
            symbol = str(rank1.get("symbol") or "")
            score, events = official_risk_signal(
                events_by_symbol.get(symbol) or [],
                decision_cutoff=_decision_cutoff(day),
                lookback_days=int(variant["lookback_days"]),
                half_life_days=float(variant["half_life_days"]),
            )
            if score >= float(variant["risk_score_min"]):
                if (day, symbol, 1) not in baseline_buy_keys and not baseline_buy_symbols_by_slot.get((day, 1)):
                    suppressed_dates.append({"signal_date": day, "rank1_symbol": symbol, "risk_score": score})
                else:
                    rank1["portfolio_weight"] = float(rank1.get("portfolio_weight") or 1.0) * float(variant["scale"])
                    if variant.get("target_horizon_days") is not None:
                        rank1["target_horizon_days"] = int(variant["target_horizon_days"])
                    rank1["official_event_guard_score"] = score
                    rank1["official_event_guard_scale"] = float(variant["scale"])
                    trigger_dates.append(
                        {
                            "signal_date": day,
                            "rank1_symbol": symbol,
                            "risk_score": score,
                            "event_count": len(events),
                            "event_rules": sorted({event.rule for event in events}),
                            "latest_available_from": max(event.available_from.isoformat() for event in events),
                            "target_horizon_days": rank1.get("target_horizon_days"),
                        }
                    )
            selected.extend(picks)
        variant_id = str(variant["variant_id"])
        account = replay(selected, f"round15-{variant_id}")
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
        result_rows.append(
            {
                "variant": variant,
                "trigger_audit": {
                    "triggered_signal_day_count": len(trigger_dates),
                    "triggered_signal_dates": trigger_dates,
                    "suppressed_baseline_skip_day_count": len(suppressed_dates),
                    "suppressed_baseline_skip_dates": suppressed_dates,
                    "positive_event_buy_count": 0,
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
        for row in result_rows
        if int(row["trigger_audit"]["triggered_signal_day_count"]) > 0
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
        selected_row = max(
            plateau,
            key=lambda row: (
                float(row["variant"]["scale"]),
                float(row["variant"]["risk_score_min"]),
                -int(row["variant"]["lookback_days"]),
            ),
        )
    final_readout: dict[str, Any] | None = None
    if selected_row is not None:
        selected_id = str(selected_row["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[selected_id], start=DEFAULT_FINAL_START, end=signal_end)
        final_readout = {
            "variant_id": selected_id,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(
                accounts[selected_id], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }
    passed = bool(
        selected_row is not None
        and final_readout
        and final_readout["gate"]["passed"]
        and final_readout["standout"]["passed"]
    )
    material = {
        "artifact_type": "official_event_account_guard_ablation",
        "schema_version": SCHEMA_VERSION,
        "round": round_number,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_cninfo_official_negative_event_account_guard",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "official_event_audit": {**event_audit, "future_event_violations": 0},
        "baseline_segments_pre_final": baseline_segments,
        "results_pre_final": result_rows,
        "selection_before_final": None if selected_row is None else selected_row["variant"]["variant_id"],
        "final_untouched_readout": final_readout,
        "v3_symbol_selection_changed": False,
        "positive_event_buy_count": 0,
        "promotion_blocker": "title_only_event_taxonomy_requires_document_body_and_vendor_revision_reproduction",
    }
    digest = stable_digest(material)
    return {
        "artifact_id": f"official-event-account-guard-{digest[:16]}",
        **material,
        "content_digest": digest,
    }
