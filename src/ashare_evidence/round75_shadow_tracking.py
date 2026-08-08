from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ashare_evidence.event_confirmed_position_extension import _freeze_to_baseline_executed_buys
from ashare_evidence.global_sector_state_account_ablation import _candidate_run, _group_by_date
from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
)
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

ROUND75_SHADOW_STRATEGY_ID = "round75_exact_share_core_veto_exit_extension_shadow_v1"
ROUND75_SHADOW_LABEL = "对照组：Round 75 外部信息持仓延期"
ROUND75_SHADOW_SCHEMA_VERSION = "shortpick_round75_shadow_tracking.v1"
ROUND75_SIGNAL_SCHEMA_VERSION = "shortpick_round75_shadow_signals.v1"
ROUND75_ACTIVATION_DATE = "2026-08-08"
ROUND75_BACKFILL_START_DATE = "2025-11-27"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected_result_row(result: dict[str, Any]) -> dict[str, Any]:
    selected = str(result.get("selection_before_extended_readout") or "")
    for row in result.get("results_pre_extended") or []:
        if str((row.get("variant") or {}).get("variant_id") or "") == selected:
            return row
    raise ValueError(f"selected Round 75 result row is missing: {selected}")


def _deferrals_from_result(row: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    variant = row["variant"]
    deferrals: dict[str, dict[str, dict[str, Any]]] = {}
    for trigger in (row.get("trigger_audit") or {}).get("triggers") or []:
        use_wide = float(trigger.get("position_return") or 0.0) >= float(
            variant.get("wide_protection_min_position_return") or 1.0
        )
        prefix = "wide_" if use_wide else ""
        effective_day = str(trigger["effective_deferral_day"])
        deferrals.setdefault(effective_day, {})[str(trigger["position_key"])] = {
            "deferred_exit_day": str(trigger["deferred_exit_day"]),
            "reason": "pit_external_event_confirmed_rebound_extension",
            "extension_priority": float(trigger["full_prediction"]),
            "retained_share_scale": float(trigger.get("retained_share_scale") or 1.0),
            "minimum_cash_reserve_cny": float(variant.get("minimum_cash_reserve_cny") or 0.0),
            "deferral_stop_loss_pct": float(variant.get(f"{prefix}deferral_stop_loss_pct") or 0.0),
            "deferral_trailing_activation_pct": float(
                variant.get(f"{prefix}deferral_trailing_activation_pct") or 0.0
            ),
            "deferral_trailing_drawdown_pct": float(
                variant.get(f"{prefix}deferral_trailing_drawdown_pct") or 0.0
            ),
        }
    return deferrals


def _replay_candidate(snapshot: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    variant = row["variant"]
    baseline = snapshot["baseline_output"]
    baseline_symbols: dict[tuple[str, int], set[str]] = {}
    baseline_shares: dict[tuple[str, int], dict[str, int]] = {}
    for order in baseline["order_ledger"]:
        if order.get("action") != "buy":
            continue
        key = (str(order["signal_day"]), int(order["rank"]))
        symbol = str(order["symbol"])
        baseline_symbols.setdefault(key, set()).add(symbol)
        baseline_shares.setdefault(key, {})[symbol] = int(order["shares"])
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    selected = [copy.deepcopy(item) for item in trial["selected_top_k_picks_by_date"]]
    inventory = snapshot["inputs"]["candidate_inventory_rows"]
    inventory_by_date = _group_by_date(inventory, end=date.max)
    inventory_index = {
        (str(item["as_of_date"]), str(item["symbol"])): item
        for rows in inventory_by_date.values()
        for item in rows
    }
    frozen = _freeze_to_baseline_executed_buys(
        selected,
        baseline_buy_symbols_by_signal_rank=baseline_symbols,
        baseline_buy_shares_by_signal_rank=baseline_shares,
        inventory_rows_by_signal_symbol=inventory_index,
    )
    config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
    config["config_id"] = ROUND75_SHADOW_STRATEGY_ID
    config["pit_external_position_exit_deferrals"] = _deferrals_from_result(row)
    config["pit_external_entry_liquidity_substitution"] = bool(
        variant.get("entry_liquidity_substitution")
    )
    config["pit_external_core_entry_conflict_recall"] = True
    post_trigger_cap = variant.get("post_first_external_trigger_market_value_cap_pct")
    triggers = (row.get("trigger_audit") or {}).get("triggers") or []
    if post_trigger_cap is not None and triggers:
        concentration = copy.deepcopy(config.get("market_value_concentration_rebalance") or {})
        concentration["post_external_trigger_threshold"] = float(post_trigger_cap)
        concentration["post_external_trigger_active_from"] = min(
            str(trigger["effective_deferral_day"]) for trigger in triggers
        )
        config["market_value_concentration_rebalance"] = concentration
    candidate_run = _candidate_run(snapshot=snapshot, selected_picks=frozen, weight=0.0)
    candidate_run["artifact_id"] = "round75-shadow-backfill-candidate"
    return build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id=snapshot["trial_id"],
        market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
        candidate_inventory_rows=inventory,
        candidate_configurations=[config],
        **snapshot["inputs"]["account_profile"],
    )["results"][0]


def _normalized_curve(rows: list[dict[str, Any]], *, start: date, end: date) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if start <= date.fromisoformat(str(row["day"])) <= end
    ]
    if not selected:
        return []
    base = float(selected[0]["nav_cny"])
    return [
        {
            "date": str(row["day"]),
            "nav_cny": round(float(row["nav_cny"]), 2),
            "normalized_nav": float(row["nav_cny"]) / base if base else 1.0,
            "total_return": float(row["nav_cny"]) / base - 1.0 if base else 0.0,
            "evidence_basis": "retrospective_pit_backfill",
        }
        for row in selected
    ]


def build_round75_shadow_tracking_artifact(
    *,
    execution_snapshot_path: Path,
    result_path: Path,
    activation_date: date = date.fromisoformat(ROUND75_ACTIVATION_DATE),
) -> dict[str, Any]:
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "candidate_passed_all_gates":
        raise ValueError("Round 75 result has not passed all gates")
    if result.get("source_execution_snapshot_id") != snapshot.get("artifact_id"):
        raise ValueError("Round 75 result and execution snapshot do not share the same source id")
    row = _selected_result_row(result)
    candidate = _replay_candidate(snapshot, row)
    baseline = snapshot["baseline_output"]
    readout = result["extended_readout"]
    for label, account, expected in (
        ("baseline", baseline, readout["baseline"]),
        ("candidate", candidate, readout["candidate"]),
    ):
        ending = float(account["nav_rows"][-1]["nav_cny"])
        if abs(ending - float(expected["ending_nav_cny"])) > 0.01:
            raise ValueError(f"{label} replay ending NAV no longer matches frozen Round 75 result")
    start = date.fromisoformat(str(readout["baseline"]["from"]))
    end = date.fromisoformat(str(readout["baseline"]["to"]))
    baseline_curve = _normalized_curve(baseline["nav_rows"], start=start, end=end)
    candidate_curve = _normalized_curve(candidate["nav_rows"], start=start, end=end)
    trigger_rows = (row.get("trigger_audit") or {}).get("triggers") or []
    payload: dict[str, Any] = {
        "schema_version": ROUND75_SHADOW_SCHEMA_VERSION,
        "artifact_type": "shortpick_round75_shadow_tracking",
        "strategy_id": ROUND75_SHADOW_STRATEGY_ID,
        "strategy_label": ROUND75_SHADOW_LABEL,
        "status": "active_shadow_control",
        "generated_at": datetime.now(UTC).isoformat(),
        "activation_date": activation_date.isoformat(),
        "claim_ceiling": "historical_backfill_plus_true_forward_shadow_not_v3_change",
        "entry_policy": "copy_exact_round75_frozen_core_symbols_ranks_and_target_shares",
        "external_action_policy": "exit_horizon_only_no_external_buy",
        "frozen_variant": row["variant"],
        "historical_backfill": {
            "evidence_basis": "retrospective_pit_backfill",
            "from": start.isoformat(),
            "to": end.isoformat(),
            "baseline_summary": readout["baseline"],
            "candidate_summary": readout["candidate"],
            "gate": readout["gate"],
            "standout": readout["standout"],
            "baseline_curve": baseline_curve,
            "candidate_curve": candidate_curve,
            "trigger_count": len(trigger_rows),
            "triggers": trigger_rows,
        },
        "true_forward": {
            "evidence_basis": "true_forward_shadow",
            "from": activation_date.isoformat(),
            "status": "active_collecting",
            "initial_cash_cny": 200000.0,
            "historical_backfill_counts_toward_forward": False,
            "minimum_independent_extension_triggers": 3,
            "observed_extension_trigger_count": 0,
        },
        "pit_audit": {
            "available_at_rule": "available_at <= decision_cutoff",
            "future_event_violations": int((result.get("official_event_audit") or {}).get("future_event_violations") or 0),
            "future_feature_violations": int(result.get("future_feature_violations") or 0),
            "future_label_violations": int(result.get("future_label_violations") or 0),
            "lambda_zero_reproduction": result.get("lambda_zero_reproduction"),
        },
        "source_lineage": {
            "round75_result_artifact_id": result["artifact_id"],
            "round75_result_sha256": _sha256(result_path),
            "execution_snapshot_id": snapshot["artifact_id"],
            "execution_snapshot_sha256": _sha256(execution_snapshot_path),
            "source_design_digest": result.get("source_design_digest"),
            "source_external_digests": result.get("source_external_digests"),
        },
    }
    payload["content_digest"] = stable_digest(payload)
    return payload


def build_round75_signal_registry(
    tracking_artifact: dict[str, Any],
    *,
    activation_date: date = date.fromisoformat(ROUND75_ACTIVATION_DATE),
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    selected_row = (tracking_artifact.get("historical_backfill") or {}).get("triggers") or []
    variant = tracking_artifact.get("frozen_variant") or {}
    execution_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    # The frozen result already contains the protection regime used for every trigger.
    # It is copied into each decision row so future paper replays never depend on a
    # mutable global threshold file.
    for trigger in selected_row:
        position_return = float(trigger.get("position_return") or 0.0)
        wide = position_return >= float(variant.get("wide_protection_min_position_return") or 1.0)
        prefix = "wide_" if wide else ""
        execution_by_key[(str(trigger["position_key"]), str(trigger["decision_day"]))] = {
            "deferred_exit_day": str(trigger["deferred_exit_day"]),
            "retained_share_scale": float(trigger.get("retained_share_scale") or 1.0),
            "deferral_stop_loss_pct": float(variant.get(f"{prefix}deferral_stop_loss_pct") or 0.0),
            "deferral_trailing_activation_pct": float(
                variant.get(f"{prefix}deferral_trailing_activation_pct") or 0.0
            ),
            "deferral_trailing_drawdown_pct": float(
                variant.get(f"{prefix}deferral_trailing_drawdown_pct") or 0.0
            ),
        }
    for trigger in (tracking_artifact.get("historical_backfill") or {}).get("triggers") or []:
        decision_day = date.fromisoformat(str(trigger["decision_day"]))
        available_at = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
        signals.append(
            {
                **trigger,
                "available_at": available_at.isoformat(),
                "decision_cutoff": available_at.isoformat(),
                "evidence_basis": (
                    "true_forward_shadow" if decision_day >= activation_date else "retrospective_pit_backfill"
                ),
                "source_artifact_id": tracking_artifact.get("source_lineage", {}).get(
                    "round75_result_artifact_id"
                ),
                "execution": execution_by_key[(str(trigger["position_key"]), str(trigger["decision_day"]))],
            }
        )
    return {
        "schema_version": ROUND75_SIGNAL_SCHEMA_VERSION,
        "strategy_id": ROUND75_SHADOW_STRATEGY_ID,
        "activation_date": activation_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluated_through": str((tracking_artifact.get("historical_backfill") or {}).get("to") or ""),
        "signals": signals,
        "future_information_violation_count": 0,
        "append_policy": "immutable_decision_rows_only_never_rewrite_prior_signal",
    }


def validate_round75_signal_registry(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != ROUND75_SIGNAL_SCHEMA_VERSION:
        raise ValueError("unsupported Round 75 signal registry schema")
    seen: set[tuple[str, str]] = set()
    accepted: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    activation = date.fromisoformat(str(payload["activation_date"]))
    evaluated_through = date.fromisoformat(str(payload["evaluated_through"]))
    if evaluated_through < activation:
        # The activation can fall on a non-trading day. A registry evaluated
        # through the immediately preceding trading day is still a valid seed.
        gap = (activation - evaluated_through).days
        if gap > 3:
            raise ValueError("Round 75 signal registry is stale before activation")
    for row in payload.get("signals") or []:
        key = (str(row.get("position_key") or ""), str(row.get("decision_day") or ""))
        if not all(key) or key in seen:
            violations.append({"key": key, "reason": "missing_or_duplicate_signal_key"})
            continue
        seen.add(key)
        available_at = datetime.fromisoformat(str(row["available_at"]))
        decision_cutoff = datetime.fromisoformat(str(row["decision_cutoff"]))
        decision_day = date.fromisoformat(str(row["decision_day"]))
        effective_day = date.fromisoformat(str(row["effective_deferral_day"]))
        deferred_day = date.fromisoformat(str((row.get("execution") or {}).get("deferred_exit_day") or row["deferred_exit_day"]))
        if available_at.tzinfo is None or decision_cutoff.tzinfo is None:
            violations.append({"key": key, "reason": "timezone_required"})
        elif available_at > decision_cutoff:
            violations.append({"key": key, "reason": "available_after_decision_cutoff"})
        elif decision_cutoff.astimezone(SHANGHAI).date() != decision_day:
            violations.append({"key": key, "reason": "decision_cutoff_day_mismatch"})
        elif effective_day <= decision_day:
            violations.append({"key": key, "reason": "non_forward_effective_day"})
        elif deferred_day <= effective_day:
            violations.append({"key": key, "reason": "non_forward_deferred_exit_day"})
        elif decision_day >= activation and row.get("evidence_basis") != "true_forward_shadow":
            violations.append({"key": key, "reason": "post_activation_signal_mislabeled"})
        else:
            accepted.append(dict(row))
    if violations:
        raise ValueError(f"Round 75 signal registry failed PIT validation: {violations[:3]}")
    return {
        "signals": accepted,
        "signal_count": len(accepted),
        "true_forward_signal_count": sum(
            row.get("evidence_basis") == "true_forward_shadow" for row in accepted
        ),
        "evaluated_through": evaluated_through.isoformat(),
        "future_information_violation_count": 0,
    }


def advance_round75_signal_registry(
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    existing_validation = validate_round75_signal_registry(existing)
    candidate_validation = validate_round75_signal_registry(candidate)
    if existing.get("strategy_id") != candidate.get("strategy_id"):
        raise ValueError("Round 75 strategy id cannot change during forward tracking")
    if existing.get("activation_date") != candidate.get("activation_date"):
        raise ValueError("Round 75 activation date cannot change during forward tracking")
    old_through = date.fromisoformat(existing_validation["evaluated_through"])
    new_through = date.fromisoformat(candidate_validation["evaluated_through"])
    if new_through < old_through:
        raise ValueError("Round 75 evaluated-through date cannot move backwards")
    old_by_key = {
        (str(row["position_key"]), str(row["decision_day"])): row
        for row in existing_validation["signals"]
    }
    candidate_by_key = {
        (str(row["position_key"]), str(row["decision_day"])): row
        for row in candidate_validation["signals"]
    }
    for key, row in old_by_key.items():
        if candidate_by_key.get(key) != row:
            raise ValueError(f"Round 75 immutable signal changed or disappeared: {key}")
    for key, row in candidate_by_key.items():
        if key in old_by_key:
            continue
        if date.fromisoformat(str(row["decision_day"])) <= old_through:
            raise ValueError(f"Round 75 late signal attempted to rewrite an evaluated day: {key}")
        if row.get("evidence_basis") != "true_forward_shadow":
            raise ValueError(f"Round 75 new post-activation signal is not true-forward labeled: {key}")
    return candidate


def write_round75_shadow_tracking(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
