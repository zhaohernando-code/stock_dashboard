from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SchemaVersion = Literal["v1"]
PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT_ID = "phase5.scheduler.diagnostic.recorded.v1"
PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID = "phase5.scheduler.execution.recorded.v1"
SENSITIVE_DIAGNOSTIC_TOKENS = ("input_bundle", "runner_result", "release-manifest:", "sha256:", "Traceback")


class PublishVerificationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_manifest_ref: str
    digest: str
    event_ref: str | None = None


class FrontendProjectionManifestArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["frontend_projection_manifest"] = "frontend_projection_manifest"
    schema_version: SchemaVersion = "v1"
    projection_id: str
    cycle_id: str
    projection_name: str
    projection_family: str
    version: str
    generated_at: str
    freshness_at: str
    source_artifact_ids: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    staleness_status: Literal["fresh", "stale", "degraded"]
    fallback_reason: str | None = None
    event_refs: list[str] = Field(default_factory=list)

    @field_validator("source_artifact_ids", "event_refs")
    @classmethod
    def _dedupe_refs(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value not in result:
                result.append(value)
        return result


class Phase5CycleLedgerArtifact(BaseModel):
    artifact_family: Literal["phase5_cycle_ledger"] = "phase5_cycle_ledger"
    schema_version: SchemaVersion = "v1"
    cycle_id: str
    trigger: Literal["scheduled", "manual", "retry", "recovery_followup"]
    scope: dict[str, Any] = Field(default_factory=dict)
    status: Literal["planned", "running", "degraded", "blocked", "completed"]
    started_at: str
    finished_at: str | None = None
    input_contract_versions: dict[str, str] = Field(default_factory=dict)
    event_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    gate_readout_refs: list[str] = Field(default_factory=list)
    recovery_ticket_refs: list[str] = Field(default_factory=list)
    publish_verification_ref: PublishVerificationRef | None = None
    next_action: Literal["continue_tracking", "rebuild_projection", "retry_failed_step", "redesign", "blocked", "none"]


class Phase5RecoveryTicketArtifact(BaseModel):
    artifact_family: Literal["phase5_recovery_ticket"] = "phase5_recovery_ticket"
    schema_version: SchemaVersion = "v1"
    ticket_id: str
    cycle_id: str
    failed_step: Literal["artifact_build", "gate_eval", "projection_refresh", "publish_verify", "replay_schedule"]
    failure_class: Literal[
        "external_data_timeout",
        "sqlite_write_lock",
        "artifact_schema_unknown",
        "stale_projection",
        "publish_blocked",
        "test_failed",
        "contract_violation",
    ]
    failure_observed_at: str
    evidence_refs: list[str] = Field(default_factory=list)
    recovery_action: Literal[
        "reuse_last_valid_artifact",
        "retry_with_backoff",
        "rebuild_projection",
        "mark_degraded",
        "open_followup_cycle",
        "block_cycle",
    ]
    retry_count: int = 0
    final_status: Literal["resolved", "degraded", "blocked"]
    claim_ceiling_effect: Literal["unchanged", "lowered"]
    notes: str = ""


class Phase5SchedulerDiagnosticArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["phase5_scheduler_diagnostic"] = "phase5_scheduler_diagnostic"
    schema_version: SchemaVersion = "v1"
    diagnostic_id: str = Field(min_length=1)
    cycle_id: str | None = None
    source: Literal["phase5_scheduler"] = "phase5_scheduler"
    observed_at: str = Field(min_length=1)
    severity: Literal["info", "warning", "error", "blocked"]
    scheduler_action: Literal[
        "continue_tracking",
        "rebuild_projection",
        "retry_failed_step",
        "open_recovery_ticket",
        "block_cycle",
        "redesign",
        "none",
    ]
    failure_class: Literal[
        "artifact-missing",
        "contract-violation",
        "unexpected-error",
        "blocked-plan",
        "execution-precondition-failed",
        "none",
    ]
    recommended_recovery_action: Literal["open_recovery_ticket", "retry_with_backoff", "block_cycle", "none"]
    blocking_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    notes: str = ""
    event_refs: list[str] = Field(default_factory=lambda: [PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT_ID])

    @field_validator("blocking_reasons", "evidence_refs")
    @classmethod
    def _dedupe_sanitized_refs(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if not _contains_sensitive_diagnostic_token(value) and value not in result:
                result.append(value)
        return result

    @field_validator("event_refs")
    @classmethod
    def _dedupe_event_refs(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in [*values, PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT_ID]:
            if value not in result:
                result.append(value)
        return result

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, value: str) -> str:
        if _contains_sensitive_diagnostic_token(value):
            return "[redacted sensitive diagnostic detail]"
        return value


class Phase5SchedulerExecutionLedgerArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["phase5_scheduler_execution_ledger"] = "phase5_scheduler_execution_ledger"
    schema_version: SchemaVersion = "v1"
    execution_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    cycle_id: str | None = None
    source: Literal["phase5_scheduler"] = "phase5_scheduler"
    created_at: str = Field(min_length=1)
    plan_action: Literal[
        "continue_tracking",
        "rebuild_projection",
        "retry_failed_step",
        "open_recovery_ticket",
        "block_cycle",
        "redesign",
        "none",
    ]
    execution_status: Literal["planned", "skipped", "blocked"]
    would_execute: bool
    diagnostic_refs: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: str = ""
    event_refs: list[str] = Field(default_factory=lambda: [PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID])

    @field_validator("execution_id", "idempotency_key", "created_at", "cycle_id")
    @classmethod
    def _reject_sensitive_identity_fields(cls, value: str | None) -> str | None:
        if value is not None and _contains_sensitive_diagnostic_token(value):
            raise ValueError("scheduler execution identity fields must not contain sensitive diagnostic detail")
        return value

    @field_validator("diagnostic_refs", "blocking_reasons")
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
        for value in [*values, PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT_ID]:
            if value not in result:
                result.append(value)
        return result

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, value: str) -> str:
        if _contains_sensitive_diagnostic_token(value):
            return "[redacted sensitive scheduler execution detail]"
        return value


class Phase5SchedulerExecutionReservationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_family: Literal["phase5_scheduler_execution_reservation"] = "phase5_scheduler_execution_reservation"
    schema_version: SchemaVersion = "v1"
    reservation_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    cycle_id: str | None = None
    created_at: str = Field(min_length=1)
    source: Literal["phase5_scheduler"] = "phase5_scheduler"

    @field_validator("reservation_id", "idempotency_key", "execution_id", "cycle_id", "created_at")
    @classmethod
    def _reject_sensitive_identity_fields(cls, value: str | None) -> str | None:
        if value is not None and _contains_sensitive_diagnostic_token(value):
            raise ValueError("scheduler execution reservation identity fields must not contain sensitive diagnostic detail")
        return value


class Phase5GateReadoutArtifact(BaseModel):
    artifact_family: Literal["phase5_gate_readout"] = "phase5_gate_readout"
    schema_version: SchemaVersion = "v1"
    gate_id: str
    cycle_id: str
    gate_status: Literal["passed", "insufficient_evidence", "blocked", "degraded"]
    failing_gate_ids: list[str] = Field(default_factory=list)
    incomplete_gate_ids: list[str] = Field(default_factory=list)
    claim_ceiling: Literal["blocked", "research_observation", "paper_tracking_candidate", "validated_readout"]
    source_artifact_ids: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    next_action: Literal["continue_tracking", "rebuild_projection", "redesign", "retry_failed_step", "blocked"]
    evaluated_at: str


def _contains_sensitive_diagnostic_token(value: str) -> bool:
    return any(token in value for token in SENSITIVE_DIAGNOSTIC_TOKENS)
