from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.artifact_store_core import DEFAULT_ARTIFACT_ROOT, artifact_path
from ashare_evidence.autonomous_flow_artifacts import Phase5CycleLedgerArtifact
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact_if_exists,
    read_phase5_recovery_ticket_artifact_if_exists,
)
from ashare_evidence.scheduler_auto_progress_readout import (
    Phase5SchedulerAutoProgressRunReadout,
    read_phase5_scheduler_auto_progress_run_readout,
)

WorkbenchProjectionStatus = Literal["current", "degraded", "blocked"]


class Phase5WorkbenchCycleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str | None = None
    cycle_status: str | None = None
    trigger: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    next_action: str | None = None


class Phase5WorkbenchRecoverySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    latest_ticket_id: str | None = None
    final_status: str | None = None
    recovery_action: str | None = None
    failure_class: str | None = None
    failure_observed_at: str | None = None
    claim_ceiling_effect: str | None = None


class Phase5WorkbenchAutoProgressSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_runs: int = Field(ge=0)
    readout_status: str
    latest_run_id: str | None = None
    latest_phase: str | None = None
    latest_apply_status: str | None = None
    latest_applied_output: str | None = None
    latest_issued_at: str | None = None
    latest_recommended_output: str | None = None
    applied_count: int = 0
    blocked_count: int = 0
    idle_count: int = 0
    result_refs: list[str] = Field(default_factory=list)


class Phase5WorkbenchProjectionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    projection_name: Literal["phase5_operations_workbench"] = "phase5_operations_workbench"
    projection_version: Literal["workbench-projection-v1"] = "workbench-projection-v1"
    projection_status: WorkbenchProjectionStatus
    cycle: Phase5WorkbenchCycleSummary
    recovery: Phase5WorkbenchRecoverySummary
    auto_progress: Phase5WorkbenchAutoProgressSummary
    source_refs: list[str] = Field(default_factory=list)
    missing_refs: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    recommended_next_action: str


def read_phase5_workbench_projection_manifest(
    *,
    cycle_id: str | None = None,
    runner_id: str | None = None,
    root: Path | None = None,
) -> Phase5WorkbenchProjectionManifest:
    cycle_id = cycle_id or resolve_latest_phase5_workbench_cycle_id(root=root)
    if cycle_id is None:
        auto_progress = read_phase5_scheduler_auto_progress_run_readout(
            runner_id=runner_id,
            root=root,
        )
        return _manifest(
            projection_status="blocked",
            cycle=Phase5WorkbenchCycleSummary(),
            recovery=Phase5WorkbenchRecoverySummary(),
            auto_progress=_auto_progress_summary(auto_progress),
            missing_refs=["phase5_cycle_ledger:<latest>"],
            blocking_reasons=["cycle ledger not found: latest"],
            recommended_next_action="blocked",
        )

    cycle = read_phase5_cycle_ledger_artifact_if_exists(cycle_id, root=root)
    auto_progress = read_phase5_scheduler_auto_progress_run_readout(
        cycle_id=cycle_id,
        runner_id=runner_id,
        root=root,
    )
    if cycle is None:
        return _manifest(
            projection_status="blocked",
            cycle=Phase5WorkbenchCycleSummary(cycle_id=cycle_id),
            recovery=Phase5WorkbenchRecoverySummary(),
            auto_progress=_auto_progress_summary(auto_progress),
            missing_refs=[f"phase5_cycle_ledger:{cycle_id}"],
            blocking_reasons=[f"cycle ledger not found: {cycle_id}"],
            recommended_next_action="blocked",
        )

    ticket_id = cycle.recovery_ticket_refs[-1] if cycle.recovery_ticket_refs else None
    recovery_ticket = read_phase5_recovery_ticket_artifact_if_exists(ticket_id, root=root)
    missing_refs = []
    if ticket_id and recovery_ticket is None:
        missing_refs.append(f"phase5_recovery_ticket:{ticket_id}")

    blocking_reasons = _blocking_reasons(cycle.status, auto_progress, missing_refs)
    projection_status = _projection_status(cycle.status, auto_progress.readout_status, blocking_reasons)
    return _manifest(
        projection_status=projection_status,
        cycle=Phase5WorkbenchCycleSummary(
            cycle_id=cycle.cycle_id,
            cycle_status=cycle.status,
            trigger=cycle.trigger,
            started_at=cycle.started_at,
            finished_at=cycle.finished_at,
            next_action=cycle.next_action,
        ),
        recovery=Phase5WorkbenchRecoverySummary(
            latest_ticket_id=recovery_ticket.ticket_id if recovery_ticket else ticket_id,
            final_status=recovery_ticket.final_status if recovery_ticket else None,
            recovery_action=recovery_ticket.recovery_action if recovery_ticket else None,
            failure_class=recovery_ticket.failure_class if recovery_ticket else None,
            failure_observed_at=recovery_ticket.failure_observed_at if recovery_ticket else None,
            claim_ceiling_effect=recovery_ticket.claim_ceiling_effect if recovery_ticket else None,
        ),
        auto_progress=_auto_progress_summary(auto_progress),
        source_refs=_source_refs(cycle.cycle_id, ticket_id, auto_progress),
        missing_refs=missing_refs,
        blocking_reasons=blocking_reasons,
        recommended_next_action=_recommended_next_action(cycle.next_action, projection_status, auto_progress),
    )


def resolve_latest_phase5_workbench_cycle_id(*, root: Path | None = None) -> str | None:
    latest = find_latest_phase5_cycle_ledger_artifact(root=root)
    return latest.cycle_id if latest else None


def find_latest_phase5_cycle_ledger_artifact(
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> Phase5CycleLedgerArtifact | None:
    artifacts = list_phase5_cycle_ledger_artifacts(root=root, _default_artifact_root=_default_artifact_root)
    return artifacts[0] if artifacts else None


def list_phase5_cycle_ledger_artifacts(
    *,
    root: Path | None = None,
    _default_artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> list[Phase5CycleLedgerArtifact]:
    directory = artifact_path(
        "phase5_cycle_ledger",
        "_",
        root=root,
        default_artifact_root=_default_artifact_root,
    ).parent
    if not directory.exists():
        return []
    artifacts: list[Phase5CycleLedgerArtifact] = []
    for path in directory.glob("*.json"):
        if path.is_file():
            artifacts.append(Phase5CycleLedgerArtifact.model_validate(json.loads(path.read_text(encoding="utf-8"))))
    return sorted(artifacts, key=lambda artifact: (artifact.started_at, artifact.cycle_id), reverse=True)


def _manifest(
    *,
    projection_status: WorkbenchProjectionStatus,
    cycle: Phase5WorkbenchCycleSummary,
    recovery: Phase5WorkbenchRecoverySummary,
    auto_progress: Phase5WorkbenchAutoProgressSummary,
    recommended_next_action: str,
    source_refs: list[str] | None = None,
    missing_refs: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
) -> Phase5WorkbenchProjectionManifest:
    return Phase5WorkbenchProjectionManifest(
        projection_status=projection_status,
        cycle=cycle,
        recovery=recovery,
        auto_progress=auto_progress,
        source_refs=_dedupe(source_refs or []),
        missing_refs=_dedupe(missing_refs or []),
        blocking_reasons=_dedupe(blocking_reasons or []),
        recommended_next_action=recommended_next_action,
    )


def _auto_progress_summary(
    readout: Phase5SchedulerAutoProgressRunReadout,
) -> Phase5WorkbenchAutoProgressSummary:
    return Phase5WorkbenchAutoProgressSummary(
        total_runs=readout.total_runs,
        readout_status=readout.readout_status,
        latest_run_id=readout.latest_auto_progress_run_id,
        latest_phase=readout.latest_phase,
        latest_apply_status=readout.latest_apply_status,
        latest_applied_output=readout.latest_applied_output,
        latest_issued_at=readout.latest_issued_at,
        latest_recommended_output=readout.latest_recommended_output,
        applied_count=readout.applied_count,
        blocked_count=readout.blocked_count,
        idle_count=readout.idle_count,
        result_refs=readout.result_refs,
    )


def _projection_status(
    cycle_status: str,
    auto_progress_status: str,
    blocking_reasons: list[str],
) -> WorkbenchProjectionStatus:
    if blocking_reasons or cycle_status == "blocked" or auto_progress_status == "blocked":
        return "blocked"
    if cycle_status == "degraded" or auto_progress_status == "degraded":
        return "degraded"
    return "current"


def _blocking_reasons(
    cycle_status: str,
    auto_progress: Phase5SchedulerAutoProgressRunReadout,
    missing_refs: list[str],
) -> list[str]:
    reasons = [f"missing source ref: {ref}" for ref in missing_refs]
    if cycle_status == "blocked":
        reasons.append("cycle is blocked")
    if auto_progress.readout_status == "blocked":
        reasons.append("latest auto-progress run is blocked")
    return reasons


def _recommended_next_action(
    cycle_next_action: str,
    projection_status: WorkbenchProjectionStatus,
    auto_progress: Phase5SchedulerAutoProgressRunReadout,
) -> str:
    if projection_status == "blocked":
        return "inspect_blocking_reasons"
    if auto_progress.readout_status == "degraded":
        return "run_auto_progress_plan"
    return cycle_next_action


def _source_refs(
    cycle_id: str,
    ticket_id: str | None,
    auto_progress: Phase5SchedulerAutoProgressRunReadout,
) -> list[str]:
    refs = [f"phase5_cycle_ledger:{cycle_id}", *auto_progress.auto_progress_run_refs]
    if ticket_id:
        refs.append(f"phase5_recovery_ticket:{ticket_id}")
    return _dedupe(refs)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
