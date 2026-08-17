from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

EXTERNAL_SHADOW_STRATEGY_ID = "round75_exact_share_core_veto_exit_extension_shadow_v1"
EXTERNAL_SHADOW_LABEL = "对照组：Round 75 外部信息持仓延期"
EXTERNAL_SHADOW_SIGNAL_SCHEMA_VERSION = "shortpick_round75_shadow_signals.v1"
EXTERNAL_SHADOW_ACTIVATION_DATE = "2026-08-08"
EXTERNAL_SHADOW_BACKFILL_START_DATE = "2025-11-27"
SHANGHAI = ZoneInfo("Asia/Shanghai")

# Compatibility aliases keep the persisted paper-account contract stable while
# removing the rejected research engine that originally produced it.
ROUND75_SHADOW_STRATEGY_ID = EXTERNAL_SHADOW_STRATEGY_ID
ROUND75_SHADOW_LABEL = EXTERNAL_SHADOW_LABEL
ROUND75_SIGNAL_SCHEMA_VERSION = EXTERNAL_SHADOW_SIGNAL_SCHEMA_VERSION
ROUND75_ACTIVATION_DATE = EXTERNAL_SHADOW_ACTIVATION_DATE
ROUND75_BACKFILL_START_DATE = EXTERNAL_SHADOW_BACKFILL_START_DATE


def build_external_shadow_signal_registry(
    tracking_artifact: dict[str, Any],
    *,
    activation_date: date = date.fromisoformat(EXTERNAL_SHADOW_ACTIVATION_DATE),
) -> dict[str, Any]:
    """Freeze approved triggers into the append-only PIT paper-control registry."""
    signals: list[dict[str, Any]] = []
    variant = tracking_artifact.get("frozen_variant") or {}
    for trigger in (tracking_artifact.get("historical_backfill") or {}).get("triggers") or []:
        position_return = float(trigger.get("position_return") or 0.0)
        wide = position_return >= float(variant.get("wide_protection_min_position_return") or 1.0)
        prefix = "wide_" if wide else ""
        decision_day = date.fromisoformat(str(trigger["decision_day"]))
        decision_cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
        signals.append(
            {
                **trigger,
                "available_at": decision_cutoff.isoformat(),
                "decision_cutoff": decision_cutoff.isoformat(),
                "evidence_basis": (
                    "true_forward_shadow" if decision_day >= activation_date else "retrospective_pit_backfill"
                ),
                "source_artifact_id": (tracking_artifact.get("source_lineage") or {}).get(
                    "round75_result_artifact_id"
                ),
                "execution": {
                    "deferred_exit_day": str(trigger["deferred_exit_day"]),
                    "retained_share_scale": float(trigger.get("retained_share_scale") or 1.0),
                    "deferral_stop_loss_pct": float(variant.get(f"{prefix}deferral_stop_loss_pct") or 0.0),
                    "deferral_trailing_activation_pct": float(
                        variant.get(f"{prefix}deferral_trailing_activation_pct") or 0.0
                    ),
                    "deferral_trailing_drawdown_pct": float(
                        variant.get(f"{prefix}deferral_trailing_drawdown_pct") or 0.0
                    ),
                },
            }
        )
    return {
        "schema_version": EXTERNAL_SHADOW_SIGNAL_SCHEMA_VERSION,
        "strategy_id": EXTERNAL_SHADOW_STRATEGY_ID,
        "activation_date": activation_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluated_through": str((tracking_artifact.get("historical_backfill") or {}).get("to") or ""),
        "signals": signals,
        "future_information_violation_count": 0,
        "append_policy": "immutable_decision_rows_only_never_rewrite_prior_signal",
    }


def validate_external_shadow_signal_registry(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != EXTERNAL_SHADOW_SIGNAL_SCHEMA_VERSION:
        raise ValueError("unsupported external shadow signal registry schema")
    seen: set[tuple[str, str]] = set()
    accepted: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    activation = date.fromisoformat(str(payload["activation_date"]))
    evaluated_through = date.fromisoformat(str(payload["evaluated_through"]))
    if evaluated_through < activation and (activation - evaluated_through).days > 3:
        raise ValueError("external shadow signal registry is stale before activation")
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
        deferred_day = date.fromisoformat(
            str((row.get("execution") or {}).get("deferred_exit_day") or row["deferred_exit_day"])
        )
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
        raise ValueError(f"external shadow signal registry failed PIT validation: {violations[:3]}")
    return {
        "signals": accepted,
        "signal_count": len(accepted),
        "true_forward_signal_count": sum(
            row.get("evidence_basis") == "true_forward_shadow" for row in accepted
        ),
        "evaluated_through": evaluated_through.isoformat(),
        "future_information_violation_count": 0,
    }


def advance_external_shadow_signal_registry(
    existing: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    existing_validation = validate_external_shadow_signal_registry(existing)
    candidate_validation = validate_external_shadow_signal_registry(candidate)
    if existing.get("strategy_id") != candidate.get("strategy_id"):
        raise ValueError("external shadow strategy id cannot change during forward tracking")
    if existing.get("activation_date") != candidate.get("activation_date"):
        raise ValueError("external shadow activation date cannot change during forward tracking")
    old_through = date.fromisoformat(existing_validation["evaluated_through"])
    new_through = date.fromisoformat(candidate_validation["evaluated_through"])
    if new_through < old_through:
        raise ValueError("external shadow evaluated-through date cannot move backwards")
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
            raise ValueError(f"external shadow immutable signal changed or disappeared: {key}")
    for key, row in candidate_by_key.items():
        if key in old_by_key:
            continue
        if date.fromisoformat(str(row["decision_day"])) <= old_through:
            raise ValueError(f"external shadow late signal attempted to rewrite an evaluated day: {key}")
        if row.get("evidence_basis") != "true_forward_shadow":
            raise ValueError(f"external shadow new post-activation signal is not true-forward labeled: {key}")
    return candidate


def write_external_shadow_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


# Transitional function aliases for call sites that persist the historical schema.
build_round75_signal_registry = build_external_shadow_signal_registry
validate_round75_signal_registry = validate_external_shadow_signal_registry
advance_round75_signal_registry = advance_external_shadow_signal_registry
write_round75_shadow_tracking = write_external_shadow_artifact
