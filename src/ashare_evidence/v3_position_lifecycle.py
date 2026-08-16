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
    _segment_metrics,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.stock_transition_sleeve import FORBIDDEN_RESULT_FIELDS, _monthly_delta_summary

SCHEMA_VERSION = "v3_position_lifecycle_challenger.v1"
MINIMUM_VALIDATION_EXIT_COUNT = 12


def lifecycle_position_features(
    *,
    closes: list[float],
    entry_index: int,
    decision_index: int,
    top3_absence_streak: int,
) -> dict[str, float | int | bool]:
    if not 0 <= entry_index <= decision_index < len(closes):
        raise ValueError("invalid lifecycle feature indices")
    entry_price = float(closes[entry_index])
    decision_price = float(closes[decision_index])
    trailing_index = max(entry_index, decision_index - 3)
    trailing_price = float(closes[trailing_index])
    peak_price = max(float(value) for value in closes[entry_index : decision_index + 1])
    sma5_values = closes[max(entry_index, decision_index - 4) : decision_index + 1]
    sma5 = sum(float(value) for value in sma5_values) / len(sma5_values)
    return {
        "holding_sessions": decision_index - entry_index,
        "position_return": decision_price / entry_price - 1.0 if entry_price else 0.0,
        "trailing_3_session_return": decision_price / trailing_price - 1.0 if trailing_price else 0.0,
        "drawdown_from_peak": decision_price / peak_price - 1.0 if peak_price else 0.0,
        "close_below_sma5": decision_price < sma5,
        "top3_absence_streak": top3_absence_streak,
    }


def lifecycle_variant_triggered(features: dict[str, Any], variant: dict[str, Any]) -> bool:
    if int(features["holding_sessions"]) < int(variant["minimum_holding_sessions"]):
        return False
    comparisons = (
        ("maximum_position_return", "position_return"),
        ("maximum_trailing_3_session_return", "trailing_3_session_return"),
        ("maximum_drawdown_from_peak", "drawdown_from_peak"),
    )
    for policy_key, feature_key in comparisons:
        if policy_key in variant and float(features[feature_key]) > float(variant[policy_key]):
            return False
    if bool(variant.get("require_close_below_sma5")) and not bool(features["close_below_sma5"]):
        return False
    required_absence = variant.get("minimum_consecutive_top3_absence_signal_days")
    if required_absence is not None and int(features["top3_absence_streak"]) < int(required_absence):
        return False
    return True


def build_position_lifecycle_exit_signals(
    *,
    selected_picks_by_date: dict[str, list[dict[str, Any]]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    variant: dict[str, Any],
    signal_end: date,
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    selected_symbols_by_day = {
        day: {str(row["symbol"]) for row in rows}
        for day, rows in selected_picks_by_date.items()
    }
    signals: dict[str, dict[str, str]] = defaultdict(dict)
    audit_rows: list[dict[str, Any]] = []
    missing_history_count = 0
    for signal_day, picks in sorted(selected_picks_by_date.items()):
        signal_date = date.fromisoformat(signal_day)
        for pick in picks:
            symbol = str(pick["symbol"])
            rank = int(float(pick["rank"]))
            bars = [
                (date.fromisoformat(str(row["day"])), float(row["close"]))
                for row in market_bars_by_symbol.get(symbol, [])
                if date.fromisoformat(str(row["day"])) <= signal_end
            ]
            entry_index = next((index for index, (day, _close) in enumerate(bars) if day > signal_date), None)
            if entry_index is None:
                missing_history_count += 1
                continue
            horizon = int(float(pick.get("target_horizon_days") or 20))
            planned_exit_index = min(entry_index + horizon, len(bars) - 1)
            if planned_exit_index <= entry_index + 1:
                missing_history_count += 1
                continue
            entry_day = bars[entry_index][0]
            closes = [close for _day, close in bars]
            absence_streak = 0
            for decision_index in range(entry_index, planned_exit_index):
                decision_day = bars[decision_index][0]
                decision_key = decision_day.isoformat()
                if decision_key in selected_symbols_by_day:
                    if symbol in selected_symbols_by_day[decision_key]:
                        absence_streak = 0
                    else:
                        absence_streak += 1
                features = lifecycle_position_features(
                    closes=closes,
                    entry_index=entry_index,
                    decision_index=decision_index,
                    top3_absence_streak=absence_streak,
                )
                if not lifecycle_variant_triggered(features, variant):
                    continue
                execution_index = decision_index + 1
                if execution_index >= planned_exit_index:
                    break
                execution_day = bars[execution_index][0]
                position_key = "|".join((signal_day, entry_day.isoformat(), symbol, str(rank)))
                reason = f"pit_lifecycle_{variant['id']}"
                signals[execution_day.isoformat()][position_key] = reason
                audit_rows.append(
                    {
                        "signal_day": signal_day,
                        "entry_day": entry_day.isoformat(),
                        "decision_day": decision_day.isoformat(),
                        "execution_day": execution_day.isoformat(),
                        "symbol": symbol,
                        "rank": rank,
                        "features": features,
                    }
                )
                break
    return dict(signals), {
        "potential_exit_count": len(audit_rows),
        "missing_history_count": missing_history_count,
        "minimum_execution_lag_trading_days": 1,
        "same_close_decision_execution_count": 0,
        "future_feature_violation_count": 0,
        "audit_digest": stable_digest(audit_rows),
        "audit_sample": audit_rows[:5],
    }


def _validate_design(design: dict[str, Any]) -> list[dict[str, Any]]:
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("V3 position lifecycle design must be frozen before outcome evaluation")
    variants = list(design["variants"])
    if [int(row["complexity_order"]) for row in variants] != [1, 2, 3, 4]:
        raise ValueError("lifecycle variant complexity order differs from frozen design")
    if int(design["selection"]["minimum_validation_exit_count"]) != MINIMUM_VALIDATION_EXIT_COUNT:
        raise ValueError("lifecycle minimum validation exit count differs from frozen design")
    return variants


def _lifecycle_risk_gate(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
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
            "ceiling": int(baseline["negative_month_count"]),
            "passed": int(candidate["negative_month_count"]) <= int(baseline["negative_month_count"]),
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
    failed = [name for name, row in comparisons.items() if not row["passed"]]
    return {"passed": not failed, "failed_metrics": failed, "comparisons": comparisons}


def _lifecycle_sell_count(account: dict[str, Any], *, start: date | None, end: date) -> int:
    return sum(
        row.get("action") == "sell"
        and str(row.get("reason") or "").startswith("pit_lifecycle_")
        and (start is None or date.fromisoformat(str(row["trade_day"])) >= start)
        and date.fromisoformat(str(row["trade_day"])) <= end
        for row in account["order_ledger"]
    )


def _buy_key_audit(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, int]:
    def keys(account: dict[str, Any]) -> set[tuple[str, int, str]]:
        return {
            (str(row["signal_day"]), int(row["rank"]), str(row["symbol"]))
            for row in account["order_ledger"]
            if row.get("action") == "buy"
        }

    candidate_keys = keys(candidate)
    baseline_keys = keys(baseline)
    return {
        "candidate_only_buy_key_count": len(candidate_keys - baseline_keys),
        "missing_baseline_buy_key_count": len(baseline_keys - candidate_keys),
    }


def _sanitize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: copy.deepcopy(value) for key, value in row.items() if key not in FORBIDDEN_RESULT_FIELDS}
        for row in rows
    ]


def run_v3_position_lifecycle_challenger(
    *,
    execution_snapshot_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    variants = _validate_design(design)
    source_snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    if source_snapshot["artifact_id"] != design["data_contract"]["execution_snapshot_id"]:
        raise ValueError("execution snapshot does not match frozen lifecycle design")
    snapshot, eligibility_audit = build_personal_eligible_execution_snapshot(source_snapshot)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    selected_by_day = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_day = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    if set(selected_by_day) != set(inventory_by_day):
        raise ValueError("personal V3 and inventory coverage must match")

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
        artifact_suffix: str,
    ) -> dict[str, Any]:
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = f"v3-position-lifecycle-{artifact_suffix}"
        config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        config["pit_position_lifecycle_exit_signals"] = exit_signals
        return build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=inventory_rows,
            candidate_configurations=[config],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]

    unrestricted_control = replay(selected=selected_rows, exit_signals={}, artifact_suffix="control")
    frozen_control = replay(selected=frozen_selected_rows, exit_signals={}, artifact_suffix="frozen-control")
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
        raise ValueError(f"lifecycle controls failed to reproduce personal V3: {control_reproduction}")

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
        exit_signals, signal_audit = build_position_lifecycle_exit_signals(
            selected_picks_by_date=selected_by_day,
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            variant=variant,
            signal_end=signal_end,
        )
        variant_id = str(variant["id"])
        unrestricted = replay(
            selected=selected_rows,
            exit_signals=exit_signals,
            artifact_suffix=f"{variant_id}-shared",
        )
        frozen = replay(
            selected=frozen_selected_rows,
            exit_signals=exit_signals,
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
                "exit_counts": {
                    key: _lifecycle_sell_count(account, start=start, end=end)
                    for key, (start, end) in segment_ranges.items()
                },
                "validation_monthly_delta": _monthly_delta_summary(
                    account,
                    baseline,
                    start=validation_start,
                    end=DEFAULT_VALIDATION_END,
                ),
                "buy_key_audit": _buy_key_audit(account, baseline),
            }
        row = {
            "variant_id": variant_id,
            "complexity_order": int(variant["complexity_order"]),
            "signal_audit": signal_audit,
            "ledgers": ledger_results,
        }
        rows.append(row)
        shared = ledger_results["shared_cash"]
        frozen = ledger_results["frozen_entry"]
        if (
            shared["exit_counts"]["validation"] >= MINIMUM_VALIDATION_EXIT_COUNT
            and frozen["exit_counts"]["validation"] >= MINIMUM_VALIDATION_EXIT_COUNT
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
                "exit_count": _lifecycle_sell_count(account, start=DEFAULT_FINAL_START, end=signal_end),
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
        "artifact_type": "v3_position_lifecycle_challenger",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "research_candidate_survived_preselection_and_reused_extended"
            if selected is not None and selected_survived_extended
            else "preselected_candidate_failed_reused_extended"
            if selected is not None
            else "no_candidate_cleared_preselection"
        ),
        "claim_ceiling": "preregistered_pit_same_symbol_lifecycle_attribution_not_v3_change_not_production_ready",
        "source_execution_snapshot_id": source_snapshot["artifact_id"],
        "personal_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "personal_eligibility_audit": eligibility_audit,
        "control_reproduction": control_reproduction,
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None if selected is None else selected["variant_id"],
        "extended_readout": extended_readout,
        "extended_readout_status": "reused_diagnostic_not_untouched",
        "promotion_blockers": [
            "new_independent_time_holdout_missing",
            "true_forward_shadow_missing",
        ],
        "external_information_used": False,
        "v3_entry_selection_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"v3-position-lifecycle-{digest[:16]}", **material, "content_digest": digest}


def write_v3_position_lifecycle_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("V3 position lifecycle result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable V3 position lifecycle result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
