from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    AttemptRunInterventionAppliedOutput,
    AttemptRunInterventionApplyStatus,
)

PHASE5_SCHEDULER_ATTEMPT_INTERVENTION_RUN_RECORDED_EVENT_ID = (
    "phase5.scheduler.attempt_intervention_run.recorded.v1"
)


class Phase5SchedulerAttemptInterventionRunArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["phase5_scheduler_attempt_intervention_run"] = (
        "phase5_scheduler_attempt_intervention_run"
    )
    schema_version: Literal["v1"] = "v1"
    intervention_run_id: str = Field(min_length=1)
    cycle_id: str | None = None
    runner_id: str = Field(min_length=1)
    issued_at: str = Field(min_length=1)
    execution_status: AttemptRunInterventionApplyStatus
    applied_output: AttemptRunInterventionAppliedOutput
    action: Phase5SchedulerAction
    diagnostic_id: str | None = None
    observed_at: str | None = None
    required_arguments: list[str] = Field(default_factory=list)
    missing_arguments: list[str] = Field(default_factory=list)
    cycle_event_recorded: bool = False
    source_latest_run_id: str | None = None
    reason: str
    error_type: str | None = None
    event_refs: list[str] = Field(
        default_factory=lambda: [PHASE5_SCHEDULER_ATTEMPT_INTERVENTION_RUN_RECORDED_EVENT_ID]
    )
