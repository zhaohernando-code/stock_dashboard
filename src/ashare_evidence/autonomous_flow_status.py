from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_artifacts import Phase5CycleLedgerArtifact
from ashare_evidence.autonomous_flow_service import Phase5LocalCycleServiceResult

Phase5CycleStatus = Literal["planned", "running", "degraded", "blocked", "completed"]
Phase5DecisionStatus = Literal["completed", "degraded", "blocked"]
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
Phase5PublishVerificationStatus = Literal["present", "missing", "not_required"]
Phase5ProjectionStalenessStatus = Literal["fresh", "stale", "degraded", "missing"]
Phase5SummaryStatus = Literal["completed", "degraded", "blocked"]


class Phase5LocalCycleStatusProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    cycle_status: Phase5CycleStatus
    decision_status: Phase5DecisionStatus
    next_action: Phase5NextAction
    claim_ceiling: Phase5ClaimCeiling
    decision_reason: str
    missing_refs: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    closeout_applied: bool
    finished_at: str | None = None
    publish_verification_status: Phase5PublishVerificationStatus
    staleness_status: Phase5ProjectionStalenessStatus
    summary_status: Phase5SummaryStatus


def project_phase5_local_cycle_status(
    result: Phase5LocalCycleServiceResult,
) -> Phase5LocalCycleStatusProjection:
    cycle = _effective_cycle(result)
    decision = result.runner_result.decision
    missing_refs = _dedupe(result.missing_refs)
    blocking_reasons = _dedupe(decision.blocking_reasons)
    publish_verification_status = _publish_verification_status(
        cycle=cycle,
        blocking_reasons=blocking_reasons,
    )
    staleness_status = _staleness_status(result)

    return Phase5LocalCycleStatusProjection(
        cycle_id=result.cycle_id,
        cycle_status=cycle.status,
        decision_status=decision.closeout_status,
        next_action=decision.next_action,
        claim_ceiling=decision.claim_ceiling,
        decision_reason=decision.decision_reason,
        missing_refs=missing_refs,
        blocking_reasons=blocking_reasons,
        source_refs=_dedupe(decision.source_refs),
        closeout_applied=result.runner_result.closeout_applied,
        finished_at=cycle.finished_at,
        publish_verification_status=publish_verification_status,
        staleness_status=staleness_status,
        summary_status=_summary_status(
            cycle_status=cycle.status,
            decision_status=decision.closeout_status,
            missing_refs=missing_refs,
            publish_verification_status=publish_verification_status,
            staleness_status=staleness_status,
        ),
    )


def _effective_cycle(result: Phase5LocalCycleServiceResult) -> Phase5CycleLedgerArtifact:
    if result.runner_result.closeout_cycle is not None:
        return result.runner_result.closeout_cycle
    return result.input_bundle.cycle


def _publish_verification_status(
    *,
    cycle: Phase5CycleLedgerArtifact,
    blocking_reasons: list[str],
) -> Phase5PublishVerificationStatus:
    if cycle.publish_verification_ref is not None:
        return "present"
    if any(_is_publish_verification_missing_reason(reason) for reason in blocking_reasons):
        return "missing"
    return "not_required"


def _is_publish_verification_missing_reason(reason: str) -> bool:
    normalized = reason.casefold()
    return "publish verification" in normalized and "missing" in normalized


def _staleness_status(result: Phase5LocalCycleServiceResult) -> Phase5ProjectionStalenessStatus:
    projection_manifest = result.input_bundle.projection_manifest
    if projection_manifest is None:
        return "missing"
    return projection_manifest.staleness_status


def _summary_status(
    *,
    cycle_status: Phase5CycleStatus,
    decision_status: Phase5DecisionStatus,
    missing_refs: list[str],
    publish_verification_status: Phase5PublishVerificationStatus,
    staleness_status: Phase5ProjectionStalenessStatus,
) -> Phase5SummaryStatus:
    if cycle_status == "blocked" or decision_status == "blocked":
        return "blocked"
    if (
        cycle_status == "degraded"
        or decision_status == "degraded"
        or missing_refs
        or publish_verification_status == "missing"
        or staleness_status in {"stale", "degraded", "missing"}
    ):
        return "degraded"
    return "completed"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
