from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PHASE5_SCHEDULER_AUTO_PROGRESS_RUN_RECORDED_EVENT_ID = "phase5.scheduler.auto_progress_run.recorded.v1"


class Phase5SchedulerAutoProgressRunArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["phase5_scheduler_auto_progress_run"] = "phase5_scheduler_auto_progress_run"
    schema_version: Literal["v1"] = "v1"
    auto_progress_run_id: str = Field(min_length=1)
    cycle_id: str | None = None
    runner_id: str = Field(min_length=1)
    issued_at: str = Field(min_length=1)
    plan_status: str
    phase: str
    apply_status: str
    applied_output: str
    recommended_output: str | None = None
    recommended_flags: list[str] = Field(default_factory=list)
    required_arguments: list[str] = Field(default_factory=list)
    missing_arguments: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    result_refs: list[str] = Field(default_factory=list)
    notes: str
    event_refs: list[str] = Field(
        default_factory=lambda: [PHASE5_SCHEDULER_AUTO_PROGRESS_RUN_RECORDED_EVENT_ID]
    )
