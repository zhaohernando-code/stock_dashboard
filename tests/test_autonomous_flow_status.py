from __future__ import annotations

from copy import deepcopy
from typing import cast

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    PublishVerificationRef,
)
from ashare_evidence.autonomous_flow_planner import Phase5PlannerDecision
from ashare_evidence.autonomous_flow_resolver import Phase5RunnerInputBundle
from ashare_evidence.autonomous_flow_runner import Phase5RunnerResult
from ashare_evidence.autonomous_flow_service import Phase5LocalCycleServiceResult
from ashare_evidence.autonomous_flow_status import project_phase5_local_cycle_status

_DEFAULT = object()


def _cycle(**overrides: object) -> Phase5CycleLedgerArtifact:
    values = {
        "cycle_id": "cycle-20260520-001",
        "trigger": "manual",
        "scope": {"portfolio": "short_pick_lab"},
        "status": "running",
        "started_at": "2026-05-20T09:00:00Z",
        "finished_at": None,
        "input_contract_versions": {"registry": "autonomous_flow_registry.v1"},
        "event_refs": ["phase5.cycle.started.v1"],
        "artifact_refs": ["frontend_projection_manifest:projection-20260520-001"],
        "gate_readout_refs": ["gate-20260520-001"],
        "recovery_ticket_refs": [],
        "publish_verification_ref": PublishVerificationRef(
            release_manifest_ref="release-manifest:phase5:20260520",
            digest="sha256:abc123",
            event_ref="runtime.publish.verified.v1",
        ),
        "next_action": "continue_tracking",
    }
    values.update(overrides)
    return Phase5CycleLedgerArtifact(**values)


def _gate(**overrides: object) -> Phase5GateReadoutArtifact:
    values = {
        "gate_id": "gate-20260520-001",
        "cycle_id": "cycle-20260520-001",
        "gate_status": "passed",
        "failing_gate_ids": [],
        "incomplete_gate_ids": [],
        "claim_ceiling": "paper_tracking_candidate",
        "source_artifact_ids": ["phase5-horizon-study:latest"],
        "blocking_reasons": [],
        "next_action": "continue_tracking",
        "evaluated_at": "2026-05-20T09:10:00Z",
    }
    values.update(overrides)
    return Phase5GateReadoutArtifact(**values)


def _projection(**overrides: object) -> FrontendProjectionManifestArtifact:
    values = {
        "projection_id": "projection-20260520-001",
        "cycle_id": "cycle-20260520-001",
        "projection_name": "operations_summary",
        "projection_family": "operations",
        "version": "frontend-projection-v1",
        "generated_at": "2026-05-20T09:12:00Z",
        "freshness_at": "2026-05-20T09:10:00Z",
        "source_artifact_ids": ["phase5-horizon-study:latest"],
        "row_count": 3,
        "staleness_status": "fresh",
        "fallback_reason": None,
        "event_refs": ["phase5.projection.refreshed.v1"],
    }
    values.update(overrides)
    return FrontendProjectionManifestArtifact(**values)


def _decision(**overrides: object) -> Phase5PlannerDecision:
    values = {
        "cycle_id": "cycle-20260520-001",
        "closeout_status": "completed",
        "next_action": "continue_tracking",
        "claim_ceiling": "paper_tracking_candidate",
        "decision_reason": "all planner inputs are fresh and unblocked",
        "blocking_reasons": [],
        "source_refs": ["cycle-20260520-001", "gate-20260520-001", "projection-20260520-001"],
    }
    values.update(overrides)
    return Phase5PlannerDecision(**values)


def _service_result(
    *,
    cycle: Phase5CycleLedgerArtifact | None = None,
    gate: Phase5GateReadoutArtifact | None | object = _DEFAULT,
    projection: FrontendProjectionManifestArtifact | None | object = _DEFAULT,
    decision: Phase5PlannerDecision | None = None,
    closeout_applied: bool = False,
    closeout_cycle: Phase5CycleLedgerArtifact | None = None,
    missing_refs: list[str] | None = None,
) -> Phase5LocalCycleServiceResult:
    resolved_cycle = cycle or _cycle()
    resolved_gate = (
        _gate(cycle_id=resolved_cycle.cycle_id)
        if gate is _DEFAULT
        else cast(Phase5GateReadoutArtifact | None, gate)
    )
    resolved_projection = (
        _projection(cycle_id=resolved_cycle.cycle_id)
        if projection is _DEFAULT
        else cast(FrontendProjectionManifestArtifact | None, projection)
    )
    return Phase5LocalCycleServiceResult(
        cycle_id=resolved_cycle.cycle_id,
        input_bundle=Phase5RunnerInputBundle(
            cycle=resolved_cycle,
            gate_readout=resolved_gate,
            recovery_ticket=None,
            projection_manifest=resolved_projection,
            missing_refs=missing_refs or [],
        ),
        runner_result=Phase5RunnerResult(
            cycle_id=resolved_cycle.cycle_id,
            decision=decision or _decision(cycle_id=resolved_cycle.cycle_id),
            closeout_applied=closeout_applied,
            closeout_cycle=closeout_cycle,
            skipped_reason=None if closeout_applied else "closeout_not_requested",
        ),
        missing_refs=missing_refs or [],
    )


def test_completed_dry_run_projects_small_completed_summary() -> None:
    projection = project_phase5_local_cycle_status(_service_result())

    assert projection.cycle_id == "cycle-20260520-001"
    assert projection.cycle_status == "running"
    assert projection.decision_status == "completed"
    assert projection.next_action == "continue_tracking"
    assert projection.claim_ceiling == "paper_tracking_candidate"
    assert projection.missing_refs == []
    assert projection.blocking_reasons == []
    assert projection.closeout_applied is False
    assert projection.finished_at is None
    assert projection.publish_verification_status == "present"
    assert projection.staleness_status == "fresh"
    assert projection.summary_status == "completed"


def test_degraded_decision_projects_degraded_summary() -> None:
    projection = project_phase5_local_cycle_status(
        _service_result(
            decision=_decision(
                closeout_status="degraded",
                next_action="rebuild_projection",
                decision_reason="frontend projection manifest is stale",
                blocking_reasons=["projection staleness_status is stale"],
            ),
            projection=_projection(staleness_status="stale"),
        )
    )

    assert projection.decision_status == "degraded"
    assert projection.next_action == "rebuild_projection"
    assert projection.staleness_status == "stale"
    assert projection.summary_status == "degraded"


def test_blocked_decision_projects_blocked_summary() -> None:
    projection = project_phase5_local_cycle_status(
        _service_result(
            cycle=_cycle(publish_verification_ref=None),
            decision=_decision(
                closeout_status="blocked",
                next_action="blocked",
                claim_ceiling="blocked",
                decision_reason="gate readout blocked the cycle",
                blocking_reasons=["contract registry check failed"],
            ),
        )
    )

    assert projection.decision_status == "blocked"
    assert projection.next_action == "blocked"
    assert projection.claim_ceiling == "blocked"
    assert projection.blocking_reasons == ["contract registry check failed"]
    assert projection.summary_status == "blocked"


def test_missing_refs_degrade_summary_and_are_stably_deduped() -> None:
    projection = project_phase5_local_cycle_status(
        _service_result(
            projection=None,
            decision=_decision(
                source_refs=[
                    "cycle-20260520-001",
                    "gate-20260520-001",
                    "gate-20260520-001",
                ],
            ),
            missing_refs=[
                "frontend_projection_manifest:<missing>",
                "frontend_projection_manifest:<missing>",
                "phase5_gate_readout:<missing>",
            ],
        )
    )

    assert projection.missing_refs == [
        "frontend_projection_manifest:<missing>",
        "phase5_gate_readout:<missing>",
    ]
    assert projection.source_refs == ["cycle-20260520-001", "gate-20260520-001"]
    assert projection.staleness_status == "missing"
    assert projection.summary_status == "degraded"


def test_publish_verification_missing_reason_maps_to_missing() -> None:
    projection = project_phase5_local_cycle_status(
        _service_result(
            cycle=_cycle(publish_verification_ref=None),
            decision=_decision(
                closeout_status="degraded",
                next_action="retry_failed_step",
                decision_reason="publish verification is required but missing",
                blocking_reasons=[
                    "runtime publish verification ref is missing",
                    "runtime publish verification ref is missing",
                ],
            ),
        )
    )

    assert projection.publish_verification_status == "missing"
    assert projection.blocking_reasons == ["runtime publish verification ref is missing"]
    assert projection.summary_status == "degraded"


def test_publish_verification_without_required_blocker_maps_to_not_required() -> None:
    projection = project_phase5_local_cycle_status(
        _service_result(
            cycle=_cycle(publish_verification_ref=None),
        )
    )

    assert projection.publish_verification_status == "not_required"
    assert projection.summary_status == "completed"


def test_closeout_applied_uses_closeout_cycle_status_and_finished_at() -> None:
    closeout_cycle = _cycle(
        status="degraded",
        finished_at="2026-05-20T09:20:00Z",
        next_action="continue_tracking",
    )

    projection = project_phase5_local_cycle_status(
        _service_result(
            closeout_applied=True,
            closeout_cycle=closeout_cycle,
        )
    )

    assert projection.closeout_applied is True
    assert projection.cycle_status == "degraded"
    assert projection.finished_at == "2026-05-20T09:20:00Z"
    assert projection.summary_status == "degraded"


def test_projection_json_excludes_nested_bundle_and_release_manifest_details() -> None:
    json_payload = project_phase5_local_cycle_status(_service_result()).model_dump_json()

    assert "input_bundle" not in json_payload
    assert "runner_result" not in json_payload
    assert "projection_name" not in json_payload
    assert "row_count" not in json_payload
    assert "release_manifest_ref" not in json_payload
    assert "release-manifest:phase5:20260520" not in json_payload
    assert "sha256:abc123" not in json_payload


def test_projection_does_not_mutate_input_object() -> None:
    service_result = _service_result(
        decision=_decision(
            blocking_reasons=["runtime publish verification ref is missing"],
            source_refs=["cycle-20260520-001", "cycle-20260520-001"],
        ),
        missing_refs=["frontend_projection_manifest:<missing>", "frontend_projection_manifest:<missing>"],
    )
    before = deepcopy(service_result)

    project_phase5_local_cycle_status(service_result)

    assert service_result == before
