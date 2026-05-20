from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

CLAIM_CEILING_BLOCKED = "blocked"
CLAIM_CEILING_RESEARCH_OBSERVATION = "research_observation"
CLAIM_CEILING_PAPER_TRACKING_CANDIDATE = "paper_tracking_candidate"
CLAIM_CEILING_VALIDATED_READOUT = "validated_readout"

CLAIM_CEILING_LEVELS = (
    CLAIM_CEILING_BLOCKED,
    CLAIM_CEILING_RESEARCH_OBSERVATION,
    CLAIM_CEILING_PAPER_TRACKING_CANDIDATE,
    CLAIM_CEILING_VALIDATED_READOUT,
)

GATE_STATUS_PASSED = "passed"
GATE_STATUS_DEGRADED = "degraded"
GATE_STATUS_BLOCKED = "blocked"
GATE_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"

_VALIDATION_PASSED = {
    "artifact_backed",
    "passed",
    "validated",
    "verified",
}
_VALIDATION_RESEARCH = {
    "draft",
    "insufficient_sample",
    "pending",
    "pending_rebuild",
    "research",
    "research_candidate",
    "simulation_only",
}
_VALIDATION_FAILED = {
    "blocked",
    "error",
    "failed",
    "rejected",
}
_MISSING_VALUES = {"", "missing", "none", "null", "unknown"}
_STALE_VALUES = {"expired", "stale"}
_FRESH_VALUES = {"current", "fresh", "verified"}
_PUBLISH_VERIFIED = {"passed", "verified"}
_PUBLISH_UNVERIFIED = {"failed", "missing", "not_verified", "pending", "unverified"}
_VALIDATED_BOUNDARIES = {
    "artifact_backed_validation",
    "production_readout",
    "validated_readout",
}
_SIMULATION_BOUNDARIES = {
    "paper_tracking",
    "research_only",
    "simulation_only",
}

_ALLOWED_CLAIMS: dict[str, tuple[str, ...]] = {
    CLAIM_CEILING_BLOCKED: (
        "show_missing_or_blocking_reasons",
    ),
    CLAIM_CEILING_RESEARCH_OBSERVATION: (
        "describe_research_observation",
        "describe_sample_or_artifact_gap",
        "request_more_validation",
    ),
    CLAIM_CEILING_PAPER_TRACKING_CANDIDATE: (
        "describe_paper_tracking_candidate",
        "describe_simulation_boundary",
        "request_continued_validation",
    ),
    CLAIM_CEILING_VALIDATED_READOUT: (
        "describe_artifact_backed_validation",
        "describe_limited_validated_readout",
        "show_evidence_scope",
    ),
}

_FORBIDDEN_CLAIMS: dict[str, tuple[str, ...]] = {
    CLAIM_CEILING_BLOCKED: (
        "strategy_is_effective",
        "validation_passed",
        "actionable_recommendation",
        "production_or_trading_claim",
    ),
    CLAIM_CEILING_RESEARCH_OBSERVATION: (
        "stable_strategy_claim",
        "production_proof",
        "automatic_promotion",
        "actionable_recommendation",
    ),
    CLAIM_CEILING_PAPER_TRACKING_CANDIDATE: (
        "live_trading_recommendation",
        "real_money_execution",
        "production_win_rate_commitment",
        "validated_generalization",
    ),
    CLAIM_CEILING_VALIDATED_READOUT: (
        "claims_outside_artifact_scope",
        "investment_commitment",
        "guaranteed_return",
        "automatic_live_trading",
    ),
}


@dataclass(frozen=True)
class ClaimCeilingInput:
    validation_status: str | None = None
    simulation_boundary: str | None = None
    staleness_status: str | None = None
    publish_verification_status: str | None = None
    manual_llm_disagreement: bool = False
    blocking_reasons: Sequence[str] = field(default_factory=tuple)
    gate_id: str = "claim_ceiling"
    cycle_id: str | None = None
    source_refs: Sequence[str] = field(default_factory=tuple)


def evaluate_claim_ceiling(
    input_payload: ClaimCeilingInput | Mapping[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Evaluate the maximum user-visible claim strength from explicit facts only."""

    payload = _coerce_input(input_payload, overrides)
    validation_status = _normalize(payload.validation_status)
    simulation_boundary = _normalize(payload.simulation_boundary)
    staleness_status = _normalize(payload.staleness_status)
    publish_status = _normalize(payload.publish_verification_status)
    blocking_reasons = tuple(str(reason).strip() for reason in payload.blocking_reasons if str(reason).strip())

    failing_gate_ids: list[str] = []
    incomplete_gate_ids: list[str] = []

    if blocking_reasons:
        failing_gate_ids.append("blocking_reasons")
        return _build_result(
            payload,
            gate_status=GATE_STATUS_BLOCKED,
            claim_ceiling=CLAIM_CEILING_BLOCKED,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="block",
            blocking_reasons=blocking_reasons,
        )

    if _is_missing(validation_status):
        incomplete_gate_ids.append("validation_status")
        return _build_result(
            payload,
            gate_status=GATE_STATUS_INSUFFICIENT_EVIDENCE,
            claim_ceiling=CLAIM_CEILING_BLOCKED,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="continue_tracking",
            blocking_reasons=("validation_status is missing",),
        )

    if validation_status in _VALIDATION_FAILED:
        failing_gate_ids.append("validation_status")
        return _build_result(
            payload,
            gate_status=GATE_STATUS_BLOCKED,
            claim_ceiling=CLAIM_CEILING_BLOCKED,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="redesign",
            blocking_reasons=(f"validation_status={validation_status}",),
        )

    if _is_missing(staleness_status):
        incomplete_gate_ids.append("staleness_status")
    elif staleness_status in _STALE_VALUES:
        failing_gate_ids.append("staleness_status")

    if _is_missing(simulation_boundary):
        incomplete_gate_ids.append("simulation_boundary")

    if _is_missing(publish_status):
        incomplete_gate_ids.append("publish_verification_status")
    elif publish_status in _PUBLISH_UNVERIFIED:
        incomplete_gate_ids.append("publish_verification_status")
    elif publish_status not in _PUBLISH_VERIFIED:
        incomplete_gate_ids.append("publish_verification_status")

    if payload.manual_llm_disagreement:
        failing_gate_ids.append("manual_llm_disagreement")

    if validation_status in _VALIDATION_RESEARCH:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_RESEARCH_OBSERVATION,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action=_next_action(failing_gate_ids, incomplete_gate_ids),
            blocking_reasons=blocking_reasons,
        )

    if validation_status not in _VALIDATION_PASSED:
        incomplete_gate_ids.append("validation_status")
        return _build_result(
            payload,
            gate_status=GATE_STATUS_INSUFFICIENT_EVIDENCE,
            claim_ceiling=CLAIM_CEILING_RESEARCH_OBSERVATION,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="continue_tracking",
            blocking_reasons=blocking_reasons,
        )

    if payload.manual_llm_disagreement:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_RESEARCH_OBSERVATION,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="continue_tracking",
            blocking_reasons=blocking_reasons,
        )

    if staleness_status in _STALE_VALUES:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_RESEARCH_OBSERVATION,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="retry",
            blocking_reasons=blocking_reasons,
        )

    if simulation_boundary in _SIMULATION_BOUNDARIES or simulation_boundary not in _VALIDATED_BOUNDARIES:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_PAPER_TRACKING_CANDIDATE,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action=_next_action(failing_gate_ids, incomplete_gate_ids),
            blocking_reasons=blocking_reasons,
        )

    if publish_status not in _PUBLISH_VERIFIED:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_PAPER_TRACKING_CANDIDATE,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="retry",
            blocking_reasons=blocking_reasons,
        )

    if incomplete_gate_ids:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_PAPER_TRACKING_CANDIDATE,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=incomplete_gate_ids,
            next_action="continue_tracking",
            blocking_reasons=blocking_reasons,
        )

    if staleness_status not in _FRESH_VALUES:
        return _build_result(
            payload,
            gate_status=GATE_STATUS_DEGRADED,
            claim_ceiling=CLAIM_CEILING_PAPER_TRACKING_CANDIDATE,
            failing_gate_ids=failing_gate_ids,
            incomplete_gate_ids=("staleness_status",),
            next_action="continue_tracking",
            blocking_reasons=blocking_reasons,
        )

    return _build_result(
        payload,
        gate_status=GATE_STATUS_PASSED,
        claim_ceiling=CLAIM_CEILING_VALIDATED_READOUT,
        failing_gate_ids=failing_gate_ids,
        incomplete_gate_ids=incomplete_gate_ids,
        next_action="none",
        blocking_reasons=blocking_reasons,
    )


def _coerce_input(input_payload: ClaimCeilingInput | Mapping[str, Any] | None, overrides: Mapping[str, Any]) -> ClaimCeilingInput:
    if input_payload is None:
        data: dict[str, Any] = {}
    elif isinstance(input_payload, ClaimCeilingInput):
        data = {
            "validation_status": input_payload.validation_status,
            "simulation_boundary": input_payload.simulation_boundary,
            "staleness_status": input_payload.staleness_status,
            "publish_verification_status": input_payload.publish_verification_status,
            "manual_llm_disagreement": input_payload.manual_llm_disagreement,
            "blocking_reasons": input_payload.blocking_reasons,
            "gate_id": input_payload.gate_id,
            "cycle_id": input_payload.cycle_id,
            "source_refs": input_payload.source_refs,
        }
    else:
        data = dict(input_payload)
    data.update(overrides)
    return ClaimCeilingInput(
        validation_status=data.get("validation_status"),
        simulation_boundary=data.get("simulation_boundary"),
        staleness_status=data.get("staleness_status"),
        publish_verification_status=data.get("publish_verification_status"),
        manual_llm_disagreement=bool(data.get("manual_llm_disagreement", False)),
        blocking_reasons=_coerce_sequence(data.get("blocking_reasons")),
        gate_id=str(data.get("gate_id") or "claim_ceiling"),
        cycle_id=str(data["cycle_id"]) if data.get("cycle_id") is not None else None,
        source_refs=_coerce_sequence(data.get("source_refs")),
    )


def _build_result(
    payload: ClaimCeilingInput,
    *,
    gate_status: str,
    claim_ceiling: str,
    failing_gate_ids: Sequence[str],
    incomplete_gate_ids: Sequence[str],
    next_action: str,
    blocking_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "gate_id": payload.gate_id,
        "cycle_id": payload.cycle_id,
        "gate_status": gate_status,
        "claim_ceiling": claim_ceiling,
        "allowed_claims": list(_ALLOWED_CLAIMS[claim_ceiling]),
        "forbidden_claims": list(_FORBIDDEN_CLAIMS[claim_ceiling]),
        "failing_gate_ids": list(dict.fromkeys(failing_gate_ids)),
        "incomplete_gate_ids": list(dict.fromkeys(incomplete_gate_ids)),
        "next_action": next_action,
        "blocking_reasons": list(blocking_reasons),
        "source_refs": list(payload.source_refs),
    }


def _next_action(failing_gate_ids: Sequence[str], incomplete_gate_ids: Sequence[str]) -> str:
    if "staleness_status" in failing_gate_ids:
        return "retry"
    if failing_gate_ids:
        return "continue_tracking"
    if incomplete_gate_ids:
        return "continue_tracking"
    return "continue_tracking"


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower().replace("-", "_")


def _is_missing(value: str | None) -> bool:
    return value is None or value in _MISSING_VALUES


def _coerce_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return (str(value),)
