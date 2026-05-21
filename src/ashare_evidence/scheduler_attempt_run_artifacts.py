from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ashare_evidence.autonomous_flow_scheduler_action_route_executor import AppliedOutput, ApplyStatus
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRoutePreflightStatus,
    Phase5SchedulerActionRouteType,
)
from ashare_evidence.autonomous_flow_scheduler_attempt import Phase5SchedulerAttemptContextStatus

PHASE5_SCHEDULER_ATTEMPT_RUN_RECORDED_EVENT_ID = "phase5.scheduler.attempt_run.recorded.v1"
SENSITIVE_DIAGNOSTIC_TOKENS = ("input_bundle", "runner_result", "release-manifest:", "sha256:", "Traceback")


class Phase5SchedulerAttemptRunArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["phase5_scheduler_attempt_run"] = "phase5_scheduler_attempt_run"
    schema_version: Literal["v1"] = "v1"
    run_id: str = Field(min_length=1)
    attempt_id: str | None = None
    cycle_id: str = Field(min_length=1)
    runner_id: str = Field(min_length=1)
    issued_at: str = Field(min_length=1)
    attempt_status: Phase5SchedulerAttemptContextStatus
    route_type: Phase5SchedulerActionRouteType
    preflight_status: Phase5SchedulerActionRoutePreflightStatus
    apply_status: ApplyStatus
    applied_output: AppliedOutput
    required_arguments: list[str] = Field(default_factory=list)
    missing_arguments: list[str] = Field(default_factory=list)
    diagnostic_id: str | None = None
    execution_id: str | None = None
    idempotency_key: str | None = None
    cycle_event_recorded: bool = False
    reason: str
    error_type: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=lambda: [PHASE5_SCHEDULER_ATTEMPT_RUN_RECORDED_EVENT_ID])

    @field_validator(
        "run_id",
        "attempt_id",
        "cycle_id",
        "runner_id",
        "issued_at",
        "diagnostic_id",
        "execution_id",
        "idempotency_key",
        "error_type",
    )
    @classmethod
    def _reject_sensitive_identity_fields(cls, value: str | None) -> str | None:
        if value is not None and _contains_sensitive_diagnostic_token(value):
            raise ValueError("scheduler attempt run identity fields must not contain sensitive diagnostic detail")
        return value

    @field_validator("required_arguments", "missing_arguments", "blocking_reasons")
    @classmethod
    def _dedupe_safe_refs(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if not _contains_sensitive_diagnostic_token(value) and value not in result:
                result.append(value)
        return result

    @field_validator("event_refs")
    @classmethod
    def _dedupe_event_refs(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in [*values, PHASE5_SCHEDULER_ATTEMPT_RUN_RECORDED_EVENT_ID]:
            if not _contains_sensitive_diagnostic_token(value) and value not in result:
                result.append(value)
        return result

    @field_validator("reason")
    @classmethod
    def _sanitize_reason(cls, value: str) -> str:
        if _contains_sensitive_diagnostic_token(value):
            return "[redacted sensitive scheduler attempt run detail]"
        return value


def _contains_sensitive_diagnostic_token(value: str) -> bool:
    return any(token in value for token in SENSITIVE_DIAGNOSTIC_TOKENS)
