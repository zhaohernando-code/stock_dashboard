from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ashare_evidence.autonomous_flow import finish_phase5_cycle
from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
)
from ashare_evidence.autonomous_flow_planner import (
    Phase5CloseoutStatus,
    Phase5NextAction,
    Phase5PlannerDecision,
    plan_phase5_next_step,
)


class Phase5RunnerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    decision: Phase5PlannerDecision
    closeout_applied: bool
    closeout_cycle: Phase5CycleLedgerArtifact | None = None
    skipped_reason: str | None = None


def run_phase5_local_cycle_step(
    *,
    cycle: Phase5CycleLedgerArtifact,
    gate_readout: Phase5GateReadoutArtifact | None,
    recovery_ticket: Phase5RecoveryTicketArtifact | None,
    projection_manifest: FrontendProjectionManifestArtifact | None,
    finished_at: str | None,
    apply_closeout: bool = False,
    require_publish_verification: bool = False,
    root: Path | None = None,
) -> Phase5RunnerResult:
    decision = plan_phase5_next_step(
        cycle=cycle,
        gate_readout=gate_readout,
        recovery_ticket=recovery_ticket,
        projection_manifest=projection_manifest,
        require_publish_verification=require_publish_verification,
    )

    if not apply_closeout:
        return Phase5RunnerResult(
            cycle_id=cycle.cycle_id,
            decision=decision,
            closeout_applied=False,
            closeout_cycle=None,
            skipped_reason="closeout_not_requested",
        )

    if not finished_at:
        raise ValueError("phase5 runner apply_closeout requires finished_at")

    closeout_status, next_action = _closeout_args_for_decision(decision)
    closeout_cycle = finish_phase5_cycle(
        cycle_id=decision.cycle_id,
        status=closeout_status,
        finished_at=finished_at,
        next_action=next_action,
        root=root,
    )
    return Phase5RunnerResult(
        cycle_id=cycle.cycle_id,
        decision=decision,
        closeout_applied=True,
        closeout_cycle=closeout_cycle,
        skipped_reason=None,
    )


def _closeout_args_for_decision(decision: Phase5PlannerDecision) -> tuple[Phase5CloseoutStatus, Phase5NextAction]:
    if decision.closeout_status == "completed" and decision.next_action == "continue_tracking":
        return "degraded", decision.next_action
    return decision.closeout_status, decision.next_action
