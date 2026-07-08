from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.research_artifact_store import write_research_validation_artifact

GOVERNANCE_PROMOTION_SCHEMA_VERSION = "governance_promotion_decision.v1"
GOVERNANCE_PROMOTION_PROTOCOL_VERSION = "shortpick_governance_promotion_state_machine:v1"
PROMOTION_STATES = (
    "diagnostic_only",
    "research_candidate",
    "oos_candidate",
    "paper_tracking_candidate",
    "production_eligible",
)
TERMINAL_DISPOSITIONS = ("none", "rejected", "retired")
STATE_TRANSITIONS = {
    "diagnostic_only": ["research_candidate"],
    "research_candidate": ["oos_candidate"],
    "oos_candidate": ["paper_tracking_candidate"],
    "paper_tracking_candidate": ["production_eligible"],
    "production_eligible": [],
}
REQUIRED_ARTIFACT_FIELDS = (
    "schema_version",
    "artifact_id",
    "validation_run_id",
    "generated_at",
    "source_db_snapshot_id",
    "source_data_time_range",
    "feature_version",
    "label_version",
    "code_version",
    "config_version",
    "validation_protocol",
    "gate_readout",
    "claim_ceiling",
    "promotion_status",
)


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _blocking_gate_ids(payload: dict[str, Any] | None) -> list[str]:
    gate_readout = (payload or {}).get("gate_readout") if isinstance(payload, dict) else {}
    if not isinstance(gate_readout, dict):
        return []
    return [str(item) for item in gate_readout.get("blocking_gate_ids") or []]


def _gate_status(payload: dict[str, Any] | None) -> str | None:
    gate_readout = (payload or {}).get("gate_readout") if isinstance(payload, dict) else {}
    return str(gate_readout.get("gate_status")) if isinstance(gate_readout, dict) and gate_readout.get("gate_status") else None


def _required_field_blockers(payload: dict[str, Any], *, source_name: str) -> list[str]:
    blockers: list[str] = []
    for field in REQUIRED_ARTIFACT_FIELDS:
        value = payload.get(field)
        if value is None or value == "":
            blockers.append(f"{source_name}_missing_required_field_{field}")
    return blockers


def _prefixed_blockers(prefix: str, payload: dict[str, Any] | None) -> list[str]:
    return [f"{prefix}:{gate_id}" for gate_id in _blocking_gate_ids(payload)]


def _fees_slippage_stamp_tax_stress_ready(candidate_artifact: dict[str, Any] | None) -> bool:
    diagnostics = (candidate_artifact or {}).get("execution_diagnostics") if isinstance(candidate_artifact, dict) else {}
    if not isinstance(diagnostics, dict):
        return False
    blockers = {str(item) for item in diagnostics.get("blocking_gate_ids") or []}
    if (
        "insufficient_periods_for_execution_stress" in blockers
        or "cost_stress_2x_not_positive" in blockers
        or "cost_stress_3x_not_positive" in blockers
    ):
        return False
    thresholds = diagnostics.get("thresholds")
    minimum_periods = 20
    if isinstance(thresholds, dict):
        try:
            minimum_periods = int(thresholds.get("minimum_periods", minimum_periods))
        except (TypeError, ValueError):
            minimum_periods = 20
    try:
        period_count = int(diagnostics.get("period_count"))
    except (TypeError, ValueError):
        return False
    if period_count < minimum_periods:
        return False
    stress_by_multiplier: dict[float, dict[str, Any]] = {}
    for row in diagnostics.get("cost_stress") or []:
        if not isinstance(row, dict):
            continue
        try:
            multiplier = float(row.get("cost_multiplier"))
        except (TypeError, ValueError):
            continue
        stress_by_multiplier[multiplier] = row
    for multiplier in (1.0, 2.0, 3.0):
        row = stress_by_multiplier.get(multiplier)
        if not row:
            return False
        try:
            stress_mean = float(row.get("mean_net_excess_after_cost_stress"))
        except (TypeError, ValueError):
            return False
        if stress_mean <= 0:
            return False
    return True


def _adv_capacity_fill_rate_ready(candidate_artifact: dict[str, Any] | None) -> bool:
    diagnostics = (candidate_artifact or {}).get("execution_diagnostics") if isinstance(candidate_artifact, dict) else {}
    if not isinstance(diagnostics, dict):
        return False
    capacity = diagnostics.get("capacity_diagnostics")
    if not isinstance(capacity, dict):
        return False
    if str(capacity.get("status") or "") != "ready":
        return False
    if capacity.get("blocking_gate_ids"):
        return False
    return True


def _capacity_contract_diagnostic(candidate_artifact: dict[str, Any] | None) -> dict[str, Any] | None:
    diagnostics = (candidate_artifact or {}).get("execution_diagnostics") if isinstance(candidate_artifact, dict) else {}
    if not isinstance(diagnostics, dict):
        return None
    capacity = diagnostics.get("capacity_diagnostics")
    if not isinstance(capacity, dict):
        return None
    contract = capacity.get("capacity_contract")
    if not isinstance(contract, dict):
        return None
    return {
        "status": contract.get("status"),
        "claim_ceiling": contract.get("claim_ceiling"),
        "configured_governance_status": contract.get("configured_governance_status"),
        "configured_governance_portfolio_notional_cny": contract.get("configured_governance_portfolio_notional_cny"),
        "max_ready_research_portfolio_notional_cny": contract.get("max_ready_research_portfolio_notional_cny"),
        "blocking_gate_ids": contract.get("blocking_gate_ids") or [],
        "interpretation": contract.get("interpretation"),
    }


def _execution_gate_readout(candidate_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = (candidate_artifact or {}).get("execution_label_contract") if isinstance(candidate_artifact, dict) else {}
    covered_gate_ids = set()
    if isinstance(contract, dict):
        covered_gate_ids = {str(item) for item in contract.get("covered_execution_gate_ids") or []}
    if _fees_slippage_stamp_tax_stress_ready(candidate_artifact):
        covered_gate_ids.add("fees_slippage_stamp_tax")
    if _adv_capacity_fill_rate_ready(candidate_artifact):
        covered_gate_ids.add("adv_capacity_fill_rate")
    capacity_contract = _capacity_contract_diagnostic(candidate_artifact)

    def _status(gate_id: str) -> str:
        return "ready" if gate_id in covered_gate_ids else "blocked"

    checks = [
        {
            "gate_id": "t_plus_1_execution_model",
            "status": _status("t_plus_1_execution_model"),
            "reason": (
                "covered by label-v3 entry_execution and ready-label-only candidate evaluation"
                if "t_plus_1_execution_model" in covered_gate_ids
                else "promotion requires T+1 execution labels and fill assumptions before approval"
            ),
        },
        {
            "gate_id": "suspension_limit_buy_sellability",
            "status": _status("suspension_limit_buy_sellability"),
            "reason": (
                "covered by label-v3 entry/exit execution fields and ready-label-only candidate evaluation"
                if "suspension_limit_buy_sellability" in covered_gate_ids
                else "promotion requires suspension, limit-up buyability and limit-down sellability constraints"
            ),
        },
        {
            "gate_id": "fees_slippage_stamp_tax",
            "status": _status("fees_slippage_stamp_tax"),
            "reason": (
                "covered by comparison report 1x/2x/3x fee, slippage and stamp-tax cost-stress evidence"
                if "fees_slippage_stamp_tax" in covered_gate_ids
                else "promotion requires positive fee, slippage and stamp-tax stress evidence before approval"
            ),
        },
        {
            "gate_id": "adv_capacity_fill_rate",
            "status": _status("adv_capacity_fill_rate"),
            "reason": (
                "covered by staged-entry capacity proxy; claim ceiling remains research-only until full order-level replay"
                if "adv_capacity_fill_rate" in covered_gate_ids
                and capacity_contract
                and capacity_contract.get("status") == "configured_staggered_execution_capacity_proxy_ready"
                else "covered by selected-pick ADV capacity proxy with full fill at 5pct ADV"
                if "adv_capacity_fill_rate" in covered_gate_ids
                else (
                    "configured governance notional remains blocked; lower-capital capacity contract is diagnostic only"
                    if capacity_contract
                    and capacity_contract.get("status") == "lower_capital_research_contract_ready"
                    else "promotion requires selected-pick ADV, capacity and fill-rate stress evidence before approval"
                )
            ),
            "capacity_contract": capacity_contract,
        },
    ]
    blockers = [str(check["gate_id"]) for check in checks if check["status"] != "ready"]
    return {
        "gate_status": "blocked" if blockers else "execution_ready",
        "blocking_gate_ids": blockers,
        "covered_gate_ids": sorted(covered_gate_ids),
        "checks": checks,
    }


def build_governance_promotion_decision_artifact(
    *,
    validation_run_id: str,
    source_db_snapshot_id: str | None,
    source_data_time_range: dict[str, Any],
    candidate_kind: str,
    candidate_artifact: dict[str, Any],
    objective_universe: dict[str, Any] | None,
    walk_forward_protocol: dict[str, Any] | None,
    oos_validation: dict[str, Any] | None,
    multiple_testing_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_protocol = candidate_artifact.get("validation_protocol") if isinstance(candidate_artifact, dict) else {}
    execution_gate = _execution_gate_readout(candidate_artifact)
    blockers: list[str] = []
    blockers.extend(_required_field_blockers(candidate_artifact, source_name=candidate_kind))
    blockers.extend(_prefixed_blockers(candidate_kind, candidate_artifact))
    blockers.extend(_prefixed_blockers("objective_universe", objective_universe))
    blockers.extend(_prefixed_blockers("walk_forward", walk_forward_protocol))
    blockers.extend(_prefixed_blockers("oos_validation", oos_validation))

    if isinstance(validation_protocol, dict) and validation_protocol.get("feature_source_status") == "legacy_diagnostic_only":
        blockers.append("legacy_recommendation_payload_diagnostic_only")
    if _gate_status(walk_forward_protocol) != "walk_forward_ready":
        blockers.append("walk_forward_not_ready")
    if _gate_status(oos_validation) != "oos_ready":
        blockers.append("oos_validation_not_ready")
    if multiple_testing_diagnostics is None:
        blockers.append("multiple_testing_diagnostics_missing")
    else:
        blockers.extend(_prefixed_blockers("multiple_testing", multiple_testing_diagnostics))
        if _gate_status(multiple_testing_diagnostics) != "multiple_testing_ready":
            blockers.append("multiple_testing_not_ready")
    blockers.extend(f"execution:{gate_id}" for gate_id in execution_gate["blocking_gate_ids"])

    unique_blockers = sorted(dict.fromkeys(blockers))
    current_state = "diagnostic_only" if unique_blockers else "research_candidate"
    allowed_next_states = STATE_TRANSITIONS[current_state]
    source_artifacts = {
        "candidate_kind": candidate_kind,
        "candidate_artifact_id": candidate_artifact.get("artifact_id"),
        "objective_universe_id": (objective_universe or {}).get("artifact_id"),
        "walk_forward_protocol_id": (walk_forward_protocol or {}).get("artifact_id"),
        "oos_validation_id": (oos_validation or {}).get("artifact_id"),
        "multiple_testing_diagnostics_id": (multiple_testing_diagnostics or {}).get("artifact_id")
        if isinstance(multiple_testing_diagnostics, dict)
        else None,
    }
    decision_digest = _stable_digest(
        {
            "protocol_version": GOVERNANCE_PROMOTION_PROTOCOL_VERSION,
            "source_artifacts": source_artifacts,
            "current_state": current_state,
            "blocking_gate_ids": unique_blockers,
        }
    )
    artifact_id = f"governance-promotion-decision-{decision_digest[:16]}"
    return {
        "artifact_type": "governance_promotion_decision",
        "schema_version": GOVERNANCE_PROMOTION_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_db_snapshot_id,
        "source_data_time_range": source_data_time_range,
        "feature_version": candidate_artifact.get("feature_version")
        or candidate_artifact.get("lineage", {}).get("independent_pit_feature_version")
        or candidate_artifact.get("lineage", {}).get("feature_version"),
        "label_version": candidate_artifact.get("label_version")
        or candidate_artifact.get("lineage", {}).get("label_version", "daily_close_forward_excess_return:v1"),
        "code_version": candidate_artifact.get("code_version")
        or candidate_artifact.get("lineage", {}).get("code_version", "unresolved_local_checkout"),
        "config_version": GOVERNANCE_PROMOTION_PROTOCOL_VERSION,
        "validation_protocol": {
            "artifact_role": "governance_promotion_decision",
            "protocol_version": GOVERNANCE_PROMOTION_PROTOCOL_VERSION,
            "state_machine_states": list(PROMOTION_STATES),
            "state_machine_transitions": STATE_TRANSITIONS,
            "terminal_dispositions": list(TERMINAL_DISPOSITIONS),
            "requires_approved_projection_before_dashboard_claim": True,
            "requires_human_approval_for_paper_or_live": True,
            "legacy_recommendation_payload_policy": "diagnostic_only_never_promote",
            "execution_gate_policy": "fail_closed_until_modeled",
        },
        "gate_readout": {
            "gate_status": "blocked" if unique_blockers else current_state,
            "promotion_status": "blocked_from_production" if unique_blockers else "research_candidate_only",
            "claim_ceiling": "diagnostic_research_only" if unique_blockers else "research_candidate",
            "blocking_gate_ids": unique_blockers,
            "execution_gate_readout": execution_gate,
        },
        "claim_ceiling": "diagnostic_research_only" if unique_blockers else "research_candidate",
        "promotion_status": "blocked_from_production" if unique_blockers else "research_candidate_only",
        "storage_boundary": "research_validation_artifact_store_only",
        "current_state": current_state,
        "terminal_disposition": "none",
        "allowed_next_states": allowed_next_states,
        "approved_for_dashboard_projection": False,
        "source_artifacts": source_artifacts,
        "decision_content_digest": decision_digest,
        "transition_log": [
            {
                "from_state": None,
                "to_state": current_state,
                "reason": "initial_governance_decision",
                "generated_at": datetime.now(UTC).isoformat(),
            }
        ],
    }


def governance_promotion_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "schema_version": payload.get("schema_version"),
        "artifact_id": payload.get("artifact_id"),
        "current_state": payload.get("current_state"),
        "allowed_next_states": payload.get("allowed_next_states"),
        "approved_for_dashboard_projection": payload.get("approved_for_dashboard_projection"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "gate_readout": payload.get("gate_readout"),
        "storage_boundary": payload.get("storage_boundary"),
    }


def write_governance_promotion_decision_artifact(payload: dict[str, Any], *, artifact_root: str) -> Path:
    return write_research_validation_artifact(
        "governance_promotion_decision",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
