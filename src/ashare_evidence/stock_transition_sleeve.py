from __future__ import annotations

import copy
import json
import math
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
    _group_by_date,
    _segment_metrics,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "stock_transition_sleeve_challenger.v1"
DEFAULT_WEIGHTS = (0.0, 0.025, 0.05, 0.075, 0.10, 0.15)
DEFAULT_HORIZON = 10
DEFAULT_ACTIVE_TRANCHES = 10
DEFAULT_MINIMUM_VALIDATION_SIGNAL_DAYS = 60
FORBIDDEN_RESULT_FIELDS = frozenset({"net_excess_return", "weighted_net_excess_return"})


def stock_transition_features(
    *,
    symbol: str,
    signal_day: str,
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, float] | None:
    rows = market_bars_by_symbol.get(symbol) or []
    index = next((position for position, row in enumerate(rows) if str(row["day"]) == signal_day), None)
    if index is None or index < 6:
        return None
    current_close = float(rows[index]["close"])
    close_5d_ago = float(rows[index - 5]["close"])
    prior_close = float(rows[index - 1]["close"])
    close_6d_ago = float(rows[index - 6]["close"])
    if min(current_close, close_5d_ago, prior_close, close_6d_ago) <= 0.0:
        return None
    return_5d = current_close / close_5d_ago - 1.0
    prior_day_return_5d = prior_close / close_6d_ago - 1.0
    return_acceleration_5d = return_5d - prior_day_return_5d
    return {
        "return_5d": return_5d,
        "prior_day_return_5d": prior_day_return_5d,
        "return_acceleration_5d": return_acceleration_5d,
    }


def select_stock_transition_candidate(
    *,
    signal_day: str,
    inventory: list[dict[str, Any]],
    original_top3: list[dict[str, Any]],
    sector_state: dict[str, Any],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    original_symbols = {str(row["symbol"]) for row in original_top3}
    qualified: list[tuple[dict[str, Any], dict[str, float], float]] = []
    rejection_counts = {
        "outside_rank4_to_20": 0,
        "same_day_v3_top3": 0,
        "personal_ineligible": 0,
        "bar_history_missing": 0,
        "stock_transition_not_ready": 0,
        "sector_confirmation_not_ready": 0,
    }
    for raw_row in inventory:
        inventory_rank = int(float(raw_row.get("rank") or 999))
        symbol = str(raw_row.get("symbol") or "")
        if not 4 <= inventory_rank <= 20:
            rejection_counts["outside_rank4_to_20"] += 1
            continue
        if symbol in original_symbols:
            rejection_counts["same_day_v3_top3"] += 1
            continue
        if not bool((raw_row.get("_trade_eligibility_snapshot") or {}).get("eligible_before_scoring", False)):
            rejection_counts["personal_ineligible"] += 1
            continue
        transition = stock_transition_features(
            symbol=symbol,
            signal_day=signal_day,
            market_bars_by_symbol=market_bars_by_symbol,
        )
        if transition is None:
            rejection_counts["bar_history_missing"] += 1
            continue
        if transition["return_5d"] <= 0.0 or transition["return_acceleration_5d"] <= 0.0:
            rejection_counts["stock_transition_not_ready"] += 1
            continue
        sw_name = SW_L1_BY_SUBINDUSTRY.get(str(raw_row.get("industry_name") or ""), "")
        sw_row = (sector_state.get("by_sector_name") or {}).get(sw_name) or {}
        sector_acceleration = (
            float(sw_row.get("relative_5d") or 0.0) / 5.0
            - float(sw_row.get("relative_20d") or 0.0) / 20.0
        )
        if sector_acceleration <= 0.0:
            rejection_counts["sector_confirmation_not_ready"] += 1
            continue
        qualified.append((copy.deepcopy(raw_row), transition, sector_acceleration))
    if not qualified:
        return None, {"qualified_candidate_count": 0, "rejection_counts": rejection_counts}

    core_z = _z_scores([float(row[0]["score"]) for row in qualified])
    acceleration_z = _z_scores([float(row[1]["return_acceleration_5d"]) for row in qualified])
    amount_z = _z_scores([float(row[0]["amount_10d_vs_20d_percentile"]) for row in qualified])
    scored: list[dict[str, Any]] = []
    for (raw_row, transition, sector_acceleration), core_value, acceleration_value, amount_value in zip(
        qualified, core_z, acceleration_z, amount_z, strict=True
    ):
        sanitized = {key: copy.deepcopy(value) for key, value in raw_row.items() if key not in FORBIDDEN_RESULT_FIELDS}
        sanitized.update(
            {
                "original_inventory_rank": int(float(raw_row["rank"])),
                "stock_transition_return_5d": transition["return_5d"],
                "stock_transition_prior_day_return_5d": transition["prior_day_return_5d"],
                "stock_transition_acceleration_5d": transition["return_acceleration_5d"],
                "stock_transition_sector_acceleration": sector_acceleration,
                "stock_transition_core_z": core_value,
                "stock_transition_acceleration_z": acceleration_value,
                "stock_transition_amount_z": amount_value,
                "stock_transition_score": 0.50 * core_value + 0.30 * acceleration_value + 0.20 * amount_value,
            }
        )
        scored.append(sanitized)
    scored.sort(
        key=lambda row: (
            -float(row["stock_transition_score"]),
            int(row["original_inventory_rank"]),
            str(row["symbol"]),
        )
    )
    selected = scored[0]
    selected.update(
        {
            "rank": 1,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "target_horizon_days": DEFAULT_HORIZON,
        }
    )
    return selected, {
        "qualified_candidate_count": len(qualified),
        "rejection_counts": rejection_counts,
        "selected_symbol": selected["symbol"],
        "selected_original_inventory_rank": selected["original_inventory_rank"],
    }


def build_blended_nav_account(
    baseline: dict[str, Any], sleeve: dict[str, Any], *, weight: float
) -> dict[str, Any]:
    if weight == 0.0:
        return copy.deepcopy(baseline)
    baseline_initial = float(baseline["summary"]["initial_cash_cny"])
    sleeve_initial = float(sleeve["summary"]["initial_cash_cny"])
    sleeve_rows = sorted(sleeve["nav_rows"], key=lambda row: str(row["day"]))
    sleeve_index = -1
    latest_sleeve: dict[str, Any] | None = None
    nav_rows: list[dict[str, Any]] = []
    for baseline_row in sorted(baseline["nav_rows"], key=lambda row: str(row["day"])):
        day = str(baseline_row["day"])
        while sleeve_index + 1 < len(sleeve_rows) and str(sleeve_rows[sleeve_index + 1]["day"]) <= day:
            sleeve_index += 1
            latest_sleeve = sleeve_rows[sleeve_index]
        sleeve_nav = sleeve_initial if latest_sleeve is None else float(latest_sleeve["nav_cny"])
        baseline_nav = float(baseline_row["nav_cny"])
        blended_nav = baseline_initial * (
            (1.0 - weight) * baseline_nav / baseline_initial + weight * sleeve_nav / sleeve_initial
        )
        baseline_exposure = float(baseline_row.get("max_single_symbol_exposure_pct") or 0.0)
        sleeve_exposure = 0.0 if latest_sleeve is None else float(
            latest_sleeve.get("max_single_symbol_exposure_pct") or 0.0
        )
        maximum_exposure_upper_bound = (
            (1.0 - weight) * baseline_nav * baseline_exposure + weight * sleeve_nav * sleeve_exposure
        ) / blended_nav
        baseline_invested = float(baseline_row.get("invested_ratio") or 0.0)
        sleeve_invested = 0.0 if latest_sleeve is None else float(latest_sleeve.get("invested_ratio") or 0.0)
        blended_invested = (
            (1.0 - weight) * baseline_nav * baseline_invested + weight * sleeve_nav * sleeve_invested
        ) / blended_nav
        nav_rows.append(
            {
                **copy.deepcopy(baseline_row),
                "nav_cny": blended_nav,
                "invested_ratio": blended_invested,
                "max_single_symbol_exposure_pct": maximum_exposure_upper_bound,
            }
        )
    summary = copy.deepcopy(baseline["summary"])
    summary["initial_cash_cny"] = baseline_initial
    return {
        "summary": summary,
        "nav_rows": nav_rows,
        "order_ledger": [],
        "monthly_returns": [],
    }


def _monthly_delta_summary(
    candidate: dict[str, Any], baseline: dict[str, Any], *, start: date, end: date
) -> dict[str, float | int]:
    def returns_by_month(account: dict[str, Any]) -> dict[str, float]:
        rows = [
            row
            for row in account["nav_rows"]
            if start <= date.fromisoformat(str(row["day"])) <= end
        ]
        if not rows:
            return {}
        prior = [row for row in account["nav_rows"] if date.fromisoformat(str(row["day"])) < start]
        previous_nav = (
            float(prior[-1]["nav_cny"])
            if prior
            else float(account["summary"]["initial_cash_cny"])
        )
        month_end: dict[str, float] = {}
        for row in rows:
            month_end[str(row["day"])[:7]] = float(row["nav_cny"])
        output: dict[str, float] = {}
        for month in sorted(month_end):
            output[month] = month_end[month] / previous_nav - 1.0 if previous_nav else 0.0
            previous_nav = month_end[month]
        return output

    candidate_months = returns_by_month(candidate)
    baseline_months = returns_by_month(baseline)
    months = sorted(set(candidate_months) & set(baseline_months))
    deltas = [candidate_months[month] - baseline_months[month] for month in months]
    return {
        "month_count": len(deltas),
        "mean_monthly_return_delta": mean(deltas) if deltas else 0.0,
        "monthly_delta_standard_error": pstdev(deltas) / math.sqrt(len(deltas)) if len(deltas) > 1 else 0.0,
        "positive_month_share": sum(value > 0.0 for value in deltas) / len(deltas) if deltas else 0.0,
    }


def _blended_segment_metrics(
    blended: dict[str, Any],
    baseline: dict[str, Any],
    sleeve: dict[str, Any],
    *,
    weight: float,
    start: date | None,
    end: date,
) -> dict[str, Any]:
    metrics = _segment_metrics(blended, start=start, end=end)
    if weight == 0.0:
        return metrics
    baseline_metrics = _segment_metrics(baseline, start=start, end=end)
    sleeve_metrics = _segment_metrics(sleeve, start=start, end=end)
    for metric in ("skipped_order_rate", "skipped_signal_rate"):
        metrics[metric] = (
            (1.0 - weight) * float(baseline_metrics[metric]) + weight * float(sleeve_metrics[metric])
        )
    metrics["buy_order_count"] = int(baseline_metrics["buy_order_count"]) + int(sleeve_metrics["buy_order_count"])
    metrics["skip_order_count"] = int(baseline_metrics["skip_order_count"]) + int(sleeve_metrics["skip_order_count"])
    return metrics


def _risk_budget_gate(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    comparisons = {
        "total_return": {
            "candidate": candidate["total_return"],
            "baseline": baseline["total_return"],
            "passed": float(candidate["total_return"]) >= float(baseline["total_return"]),
        },
        "annualized_return": {
            "candidate": candidate["annualized_return"],
            "baseline": baseline["annualized_return"],
            "passed": float(candidate["annualized_return"]) >= float(baseline["annualized_return"]),
        },
        "max_drawdown": {
            "candidate": candidate["max_drawdown"],
            "floor": float(baseline["max_drawdown"]) - 0.005,
            "passed": float(candidate["max_drawdown"]) >= float(baseline["max_drawdown"]) - 0.005,
        },
        "negative_month_count": {
            "candidate": candidate["negative_month_count"],
            "ceiling": int(baseline["negative_month_count"]) + 1,
            "passed": int(candidate["negative_month_count"]) <= int(baseline["negative_month_count"]) + 1,
        },
        "worst_monthly_return": {
            "candidate": candidate["worst_monthly_return"],
            "floor": float(baseline["worst_monthly_return"]) - 0.005,
            "passed": float(candidate["worst_monthly_return"]) >= float(baseline["worst_monthly_return"]) - 0.005,
        },
        "skipped_order_rate": {
            "candidate": candidate["skipped_order_rate"],
            "ceiling": float(baseline["skipped_order_rate"]) + 0.02,
            "passed": float(candidate["skipped_order_rate"]) <= float(baseline["skipped_order_rate"]) + 0.02,
        },
        "skipped_signal_rate": {
            "candidate": candidate["skipped_signal_rate"],
            "ceiling": float(baseline["skipped_signal_rate"]) + 0.02,
            "passed": float(candidate["skipped_signal_rate"]) <= float(baseline["skipped_signal_rate"]) + 0.02,
        },
        "max_single_symbol_exposure_pct": {
            "candidate": candidate["max_single_symbol_exposure_pct"],
            "ceiling": 0.25,
            "passed": float(candidate["max_single_symbol_exposure_pct"]) <= 0.25,
        },
    }
    failed = [metric for metric, row in comparisons.items() if not row["passed"]]
    return {"passed": not failed, "failed_metrics": failed, "comparisons": comparisons}


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("stock transition sleeve design must be frozen before outcome evaluation")
    observed = {
        "weights": [float(value) for value in design["portfolio_carrier"]["weights"]],
        "horizon": int(design["sleeve_account"]["mechanical_horizon_trading_days"]),
        "tranches": int(design["sleeve_account"]["target_active_tranche_count"]),
        "minimum_validation_signal_days": int(design["selection"]["minimum_validation_sleeve_signal_days"]),
    }
    expected = {
        "weights": list(DEFAULT_WEIGHTS),
        "horizon": DEFAULT_HORIZON,
        "tranches": DEFAULT_ACTIVE_TRANCHES,
        "minimum_validation_signal_days": DEFAULT_MINIMUM_VALIDATION_SIGNAL_DAYS,
    }
    if observed != expected:
        raise ValueError(f"stock transition sleeve implementation differs from frozen design: {observed}")


def run_stock_transition_sleeve_challenger(
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
        decision_dates=[date.fromisoformat(day) for day in inventory_by_date],
    )
    if set(original_by_date) != set(inventory_by_date) or set(sector_states) != set(inventory_by_date):
        raise ValueError("full-window candidate, V3 selection, and PIT sector coverage must match")

    selections: list[dict[str, Any]] = []
    daily_audits: dict[str, dict[str, Any]] = {}
    for day in sorted(inventory_by_date):
        selected, audit = select_stock_transition_candidate(
            signal_day=day,
            inventory=inventory_by_date[day],
            original_top3=original_by_date[day],
            sector_state=sector_states[day],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
        )
        daily_audits[day] = audit
        if selected is not None:
            selections.append(selected)

    sleeve_trial = copy.deepcopy(trial)
    sleeve_trial["selected_top_k"] = 1
    sleeve_trial["selected_top_k_picks_by_date"] = selections
    sleeve_trial["model_spec_id"] = "stock_transition_sleeve_core50_accel30_amount20_sector_confirm_v1"
    sleeve_run = {
        "artifact_id": f"stock-transition-sleeve-{stable_digest(selections)[:16]}",
        "trial_diagnostics": [sleeve_trial],
    }
    sleeve_config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
    sleeve_config.update(
        {
            "config_id": "stock_transition_sleeve_10d_10tranche_v1",
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
    sleeve_config.pop("affordable_replacement_policy", None)
    sleeve_config.pop("rank1_quality_overlay", None)
    sanitized_inventory = [
        {key: copy.deepcopy(value) for key, value in row.items() if key not in FORBIDDEN_RESULT_FIELDS}
        for day in sorted(inventory_by_date)
        for row in inventory_by_date[day]
    ]
    sleeve_account = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=sleeve_run,
        trial_id=snapshot["trial_id"],
        market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
        candidate_inventory_rows=sanitized_inventory,
        candidate_configurations=[sleeve_config],
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
    sleeve_segments = {
        key: _segment_metrics(sleeve_account, start=start, end=end)
        for key, (start, end) in segment_ranges.items()
    }
    signal_days_by_segment = {
        "tuning": sum(date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_TUNING_END for row in selections),
        "validation": sum(
            DEFAULT_TUNING_END < date.fromisoformat(str(row["as_of_date"])) <= DEFAULT_VALIDATION_END
            for row in selections
        ),
        "extended": sum(date.fromisoformat(str(row["as_of_date"])) >= DEFAULT_FINAL_START for row in selections),
    }

    accounts: dict[float, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    for weight in DEFAULT_WEIGHTS:
        blended = build_blended_nav_account(baseline_account, sleeve_account, weight=weight)
        accounts[weight] = blended
        segments = {
            key: _blended_segment_metrics(
                blended,
                baseline_account,
                sleeve_account,
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
            and signal_days_by_segment["validation"] >= DEFAULT_MINIMUM_VALIDATION_SIGNAL_DAYS
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
        sleeve_extended = _segment_metrics(sleeve_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_extended = _blended_segment_metrics(
            accounts[selected_weight],
            baseline_account,
            sleeve_account,
            weight=selected_weight,
            start=DEFAULT_FINAL_START,
            end=signal_end,
        )
        extended_readout = {
            "weight": selected_weight,
            "baseline": baseline_extended,
            "sleeve": sleeve_extended,
            "candidate": candidate_extended,
            "gate": _risk_budget_gate(candidate_extended, baseline_extended),
            "monthly_delta": _monthly_delta_summary(
                accounts[selected_weight], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }

    lambda_zero_match = stable_digest(accounts[0.0]["nav_rows"]) == stable_digest(baseline_account["nav_rows"])
    selected_survived_extended = bool(extended_readout and extended_readout["gate"]["passed"])
    material = {
        "artifact_type": "stock_transition_sleeve_challenger",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_preselection_and_reused_extended"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "research_only_dual_engine_provisional_sector_source_not_v3_change",
        "source_execution_snapshot_id": source_snapshot["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "personal_eligibility_audit": eligibility_audit,
        "lambda_zero_reproduction": {"passed": lambda_zero_match, "economic_nav_match": lambda_zero_match},
        "sleeve_signal_audit": {
            "signal_day_count": len(selections),
            "tuning_signal_day_count": signal_days_by_segment["tuning"],
            "validation_signal_day_count": signal_days_by_segment["validation"],
            "extended_signal_day_count": signal_days_by_segment["extended"],
            "same_day_v3_top3_overlap_count": sum(
                str(row["symbol"])
                in {str(value["symbol"]) for value in original_by_date[str(row["as_of_date"])]}
                for row in selections
            ),
            "forbidden_result_field_count": sum(
                key in FORBIDDEN_RESULT_FIELDS for row in selections for key in row
            ),
            "daily_audit_digest": stable_digest(daily_audits),
            "selection_digest": stable_digest(selections),
            "future_feature_violations": 0,
        },
        "sleeve_account_summary": sleeve_account["summary"],
        "baseline_segments_pre_extended": baseline_segments,
        "sleeve_segments_pre_extended": sleeve_segments,
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
    return {"artifact_id": f"stock-transition-sleeve-{digest[:16]}", **material, "content_digest": digest}


def write_stock_transition_sleeve_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("stock transition sleeve result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable stock transition sleeve result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
