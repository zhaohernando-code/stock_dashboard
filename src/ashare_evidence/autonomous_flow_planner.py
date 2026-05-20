from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
)

Phase5CloseoutStatus = Literal["completed", "degraded", "blocked"]
Phase5NextAction = Literal[
    "continue_tracking",
    "rebuild_projection",
    "retry_failed_step",
    "redesign",
    "blocked",
    "none",
]
Phase5ClaimCeiling = Literal[
    "blocked",
    "research_observation",
    "paper_tracking_candidate",
    "validated_readout",
]


class Phase5PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    closeout_status: Phase5CloseoutStatus
    next_action: Phase5NextAction
    claim_ceiling: Phase5ClaimCeiling
    decision_reason: str
    blocking_reasons: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


def plan_phase5_next_step(
    *,
    cycle: Phase5CycleLedgerArtifact,
    gate_readout: Phase5GateReadoutArtifact | None,
    recovery_ticket: Phase5RecoveryTicketArtifact | None,
    projection_manifest: FrontendProjectionManifestArtifact | None,
    require_publish_verification: bool = False,
) -> Phase5PlannerDecision:
    source_refs = _source_refs(cycle, gate_readout, recovery_ticket, projection_manifest)

    if cycle.status == "blocked":
        return _decision(
            cycle=cycle,
            closeout_status="blocked",
            next_action="blocked",
            claim_ceiling="blocked",
            decision_reason="cycle ledger is already blocked",
            blocking_reasons=["cycle ledger status is blocked"],
            source_refs=source_refs,
        )

    if recovery_ticket is not None and recovery_ticket.final_status == "blocked":
        return _decision(
            cycle=cycle,
            closeout_status="blocked",
            next_action="blocked",
            claim_ceiling="blocked",
            decision_reason="recovery ticket blocked the cycle",
            blocking_reasons=[f"recovery ticket {recovery_ticket.ticket_id} final_status is blocked"],
            source_refs=source_refs,
        )

    if gate_readout is not None and gate_readout.gate_status == "blocked":
        return _decision(
            cycle=cycle,
            closeout_status="blocked",
            next_action="blocked",
            claim_ceiling="blocked",
            decision_reason="gate readout blocked the cycle",
            blocking_reasons=_non_empty_or_default(gate_readout.blocking_reasons, "gate readout status is blocked"),
            source_refs=source_refs,
        )

    if gate_readout is None:
        return _decision(
            cycle=cycle,
            closeout_status="degraded",
            next_action="retry_failed_step",
            claim_ceiling="research_observation",
            decision_reason="gate readout is missing",
            blocking_reasons=["phase5 gate readout is missing"],
            source_refs=source_refs,
        )

    if projection_manifest is None:
        return _decision(
            cycle=cycle,
            closeout_status="degraded",
            next_action="rebuild_projection",
            claim_ceiling=gate_readout.claim_ceiling,
            decision_reason="frontend projection manifest is missing",
            blocking_reasons=["frontend projection manifest is missing"],
            source_refs=source_refs,
        )

    if projection_manifest.staleness_status in {"stale", "degraded"}:
        return _decision(
            cycle=cycle,
            closeout_status="degraded",
            next_action="rebuild_projection",
            claim_ceiling=gate_readout.claim_ceiling,
            decision_reason=f"frontend projection manifest is {projection_manifest.staleness_status}",
            blocking_reasons=[f"projection staleness_status is {projection_manifest.staleness_status}"],
            source_refs=source_refs,
        )

    if require_publish_verification and cycle.publish_verification_ref is None:
        return _decision(
            cycle=cycle,
            closeout_status="degraded",
            next_action="retry_failed_step",
            claim_ceiling=gate_readout.claim_ceiling,
            decision_reason="publish verification is required but missing",
            blocking_reasons=["runtime publish verification ref is missing"],
            source_refs=source_refs,
        )

    if gate_readout.next_action in {"redesign", "retry_failed_step", "rebuild_projection", "continue_tracking"}:
        return _decision(
            cycle=cycle,
            closeout_status=_status_for_gate_action(gate_readout.next_action),
            next_action=gate_readout.next_action,
            claim_ceiling=gate_readout.claim_ceiling,
            decision_reason=f"preserving gate requested next_action={gate_readout.next_action}",
            blocking_reasons=list(gate_readout.blocking_reasons),
            source_refs=source_refs,
        )

    return _decision(
        cycle=cycle,
        closeout_status="completed",
        next_action="none",
        claim_ceiling=gate_readout.claim_ceiling,
        decision_reason="all planner inputs are fresh and unblocked",
        blocking_reasons=[],
        source_refs=source_refs,
    )


def _decision(
    *,
    cycle: Phase5CycleLedgerArtifact,
    closeout_status: Phase5CloseoutStatus,
    next_action: Phase5NextAction,
    claim_ceiling: Phase5ClaimCeiling,
    decision_reason: str,
    blocking_reasons: list[str],
    source_refs: list[str],
) -> Phase5PlannerDecision:
    return Phase5PlannerDecision(
        cycle_id=cycle.cycle_id,
        closeout_status=closeout_status,
        next_action=next_action,
        claim_ceiling=claim_ceiling,
        decision_reason=decision_reason,
        blocking_reasons=_dedupe(blocking_reasons),
        source_refs=_dedupe(source_refs),
    )


def _status_for_gate_action(next_action: str) -> Phase5CloseoutStatus:
    if next_action == "continue_tracking":
        return "completed"
    return "degraded"


def _source_refs(
    cycle: Phase5CycleLedgerArtifact,
    gate_readout: Phase5GateReadoutArtifact | None,
    recovery_ticket: Phase5RecoveryTicketArtifact | None,
    projection_manifest: FrontendProjectionManifestArtifact | None,
) -> list[str]:
    refs = [cycle.cycle_id]
    if gate_readout is not None:
        refs.append(gate_readout.gate_id)
    if recovery_ticket is not None:
        refs.append(recovery_ticket.ticket_id)
    if projection_manifest is not None:
        refs.append(projection_manifest.projection_id)
    return _dedupe(refs)


def _non_empty_or_default(values: list[str], default: str) -> list[str]:
    return values if values else [default]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
