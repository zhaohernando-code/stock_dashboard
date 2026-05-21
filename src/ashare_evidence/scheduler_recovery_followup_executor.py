from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow import start_phase5_cycle
from ashare_evidence.autonomous_flow_artifacts import Phase5CycleLedgerArtifact
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact_if_exists
from ashare_evidence.scheduler_recovery_followup_intent import Phase5SchedulerRecoveryFollowupIntent

RecoveryFollowupApplyStatus = Literal["started", "already_started", "blocked", "skipped"]


class Phase5SchedulerRecoveryFollowupApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    apply_status: RecoveryFollowupApplyStatus
    followup_cycle_id: str | None = None
    source_cycle_id: str | None = None
    source_ticket_id: str | None = None
    followup_cycle: Phase5CycleLedgerArtifact | None = None
    source_intent_status: str
    blocking_reasons: list[str] = Field(default_factory=list)
    notes: str


def apply_phase5_scheduler_recovery_followup_intent(
    intent: Phase5SchedulerRecoveryFollowupIntent,
    *,
    created_at: str | None,
    root: Path | None = None,
) -> Phase5SchedulerRecoveryFollowupApplyResult:
    if intent.intent_status == "skipped":
        return _result(intent, apply_status="skipped", notes="recovery follow-up intent skipped")
    if intent.intent_status == "blocked":
        return _result(
            intent,
            apply_status="blocked",
            blocking_reasons=intent.blocking_reasons or ["recovery follow-up intent is blocked"],
            notes="recovery follow-up intent blocked apply",
        )

    missing = _missing_ready_fields(intent, created_at)
    if missing:
        return _result(
            intent,
            apply_status="blocked",
            blocking_reasons=[f"missing required follow-up cycle field: {field}" for field in missing],
            notes="ready recovery follow-up intent is incomplete",
        )

    existing = read_phase5_cycle_ledger_artifact_if_exists(intent.followup_cycle_id, root=root)
    expected_scope = _followup_scope(intent)
    if existing is not None and _scope_matches(existing, expected_scope):
        return _result(
            intent,
            apply_status="already_started",
            followup_cycle=existing,
            notes="recovery follow-up cycle already started",
        )
    if existing is not None:
        return _result(
            intent,
            apply_status="blocked",
            followup_cycle=existing,
            blocking_reasons=[f"existing follow-up cycle conflicts with intent: {intent.followup_cycle_id}"],
            notes="recovery follow-up apply blocked by cycle id conflict",
        )

    cycle = start_phase5_cycle(
        cycle_id=intent.followup_cycle_id or "",
        trigger="recovery_followup",
        started_at=created_at or "",
        scope=expected_scope,
        root=root,
    )
    return _result(
        intent,
        apply_status="started",
        followup_cycle=cycle,
        notes="recovery follow-up cycle started from intent",
    )


def _result(
    intent: Phase5SchedulerRecoveryFollowupIntent,
    *,
    apply_status: RecoveryFollowupApplyStatus,
    notes: str,
    followup_cycle: Phase5CycleLedgerArtifact | None = None,
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerRecoveryFollowupApplyResult:
    return Phase5SchedulerRecoveryFollowupApplyResult(
        apply_status=apply_status,
        followup_cycle_id=intent.followup_cycle_id,
        source_cycle_id=intent.cycle_id,
        source_ticket_id=intent.ticket_id,
        followup_cycle=followup_cycle,
        source_intent_status=intent.intent_status,
        blocking_reasons=blocking_reasons or [],
        notes=notes,
    )


def _missing_ready_fields(intent: Phase5SchedulerRecoveryFollowupIntent, created_at: str | None) -> list[str]:
    fields = {
        "followup_cycle_id": intent.followup_cycle_id,
        "cycle_id": intent.cycle_id,
        "ticket_id": intent.ticket_id,
        "created_at": created_at,
    }
    return [field for field, value in fields.items() if not value]


def _followup_scope(intent: Phase5SchedulerRecoveryFollowupIntent) -> dict[str, object]:
    return {
        "source_cycle_id": intent.cycle_id,
        "source_ticket_id": intent.ticket_id,
        "source_ticket_ref": intent.source_ticket_ref,
        "source_evidence_refs": intent.evidence_refs,
    }


def _scope_matches(cycle: Phase5CycleLedgerArtifact, expected_scope: dict[str, object]) -> bool:
    return cycle.trigger == "recovery_followup" and cycle.scope == expected_scope
