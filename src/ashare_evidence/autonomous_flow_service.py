from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_resolver import (
    Phase5RunnerInputBundle,
    resolve_phase5_runner_inputs,
)
from ashare_evidence.autonomous_flow_runner import (
    Phase5RunnerResult,
    run_phase5_local_cycle_step,
)


class Phase5LocalCycleServiceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    input_bundle: Phase5RunnerInputBundle
    runner_result: Phase5RunnerResult
    missing_refs: list[str] = Field(default_factory=list)


def run_phase5_local_cycle_service(
    *,
    cycle_id: str,
    gate_id: str | None = None,
    recovery_ticket_id: str | None = None,
    projection_id: str | None = None,
    finished_at: str | None = None,
    apply_closeout: bool = False,
    require_publish_verification: bool = False,
    root: Path | None = None,
) -> Phase5LocalCycleServiceResult:
    if apply_closeout and not finished_at:
        raise ValueError("phase5 local cycle service apply_closeout requires finished_at")

    input_bundle = resolve_phase5_runner_inputs(
        cycle_id=cycle_id,
        gate_id=gate_id,
        recovery_ticket_id=recovery_ticket_id,
        projection_id=projection_id,
        root=root,
    )
    runner_result = run_phase5_local_cycle_step(
        cycle=input_bundle.cycle,
        gate_readout=input_bundle.gate_readout,
        recovery_ticket=input_bundle.recovery_ticket,
        projection_manifest=input_bundle.projection_manifest,
        finished_at=finished_at,
        apply_closeout=apply_closeout,
        require_publish_verification=require_publish_verification,
        root=root,
    )
    return Phase5LocalCycleServiceResult(
        cycle_id=input_bundle.cycle.cycle_id,
        input_bundle=input_bundle,
        runner_result=runner_result,
        missing_refs=list(input_bundle.missing_refs),
    )
