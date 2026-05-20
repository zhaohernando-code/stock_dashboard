from __future__ import annotations

from copy import deepcopy

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    PublishVerificationRef,
)
from ashare_evidence.autonomous_flow_planner import plan_phase5_next_step


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


def _ticket(**overrides: object) -> Phase5RecoveryTicketArtifact:
    values = {
        "ticket_id": "ticket-20260520-001",
        "cycle_id": "cycle-20260520-001",
        "failed_step": "projection_refresh",
        "failure_class": "stale_projection",
        "failure_observed_at": "2026-05-20T09:08:00Z",
        "evidence_refs": ["projection-log:20260520"],
        "recovery_action": "rebuild_projection",
        "retry_count": 1,
        "final_status": "resolved",
        "claim_ceiling_effect": "unchanged",
        "notes": "",
    }
    values.update(overrides)
    return Phase5RecoveryTicketArtifact(**values)


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


def test_cycle_already_blocked_short_circuits_to_blocked() -> None:
    decision = plan_phase5_next_step(
        cycle=_cycle(status="blocked", publish_verification_ref=None),
        gate_readout=_gate(gate_status="passed", claim_ceiling="validated_readout"),
        recovery_ticket=None,
        projection_manifest=_projection(),
    )

    assert decision.closeout_status == "blocked"
    assert decision.next_action == "blocked"
    assert decision.claim_ceiling == "blocked"
    assert decision.source_refs == ["cycle-20260520-001", "gate-20260520-001", "projection-20260520-001"]


def test_recovery_blocked_takes_priority_over_passed_gate() -> None:
    decision = plan_phase5_next_step(
        cycle=_cycle(),
        gate_readout=_gate(gate_status="passed", claim_ceiling="validated_readout"),
        recovery_ticket=_ticket(final_status="blocked"),
        projection_manifest=_projection(),
    )

    assert decision.closeout_status == "blocked"
    assert decision.next_action == "blocked"
    assert decision.claim_ceiling == "blocked"
    assert "ticket-20260520-001" in decision.source_refs


def test_gate_blocked_takes_priority_over_fresh_projection() -> None:
    decision = plan_phase5_next_step(
        cycle=_cycle(),
        gate_readout=_gate(
            gate_status="blocked",
            claim_ceiling="blocked",
            blocking_reasons=["contract registry check failed"],
            next_action="blocked",
        ),
        recovery_ticket=None,
        projection_manifest=_projection(),
    )

    assert decision.closeout_status == "blocked"
    assert decision.next_action == "blocked"
    assert decision.claim_ceiling == "blocked"
    assert decision.blocking_reasons == ["contract registry check failed"]


def test_missing_gate_degrades_to_retry_and_research_observation() -> None:
    decision = plan_phase5_next_step(
        cycle=_cycle(gate_readout_refs=[]),
        gate_readout=None,
        recovery_ticket=None,
        projection_manifest=_projection(),
    )

    assert decision.closeout_status == "degraded"
    assert decision.next_action == "retry_failed_step"
    assert decision.claim_ceiling == "research_observation"
    assert decision.source_refs == ["cycle-20260520-001", "projection-20260520-001"]


def test_missing_projection_degrades_to_rebuild_projection() -> None:
    decision = plan_phase5_next_step(
        cycle=_cycle(artifact_refs=[]),
        gate_readout=_gate(claim_ceiling="validated_readout"),
        recovery_ticket=None,
        projection_manifest=None,
    )

    assert decision.closeout_status == "degraded"
    assert decision.next_action == "rebuild_projection"
    assert decision.claim_ceiling == "validated_readout"
    assert decision.source_refs == ["cycle-20260520-001", "gate-20260520-001"]


def test_stale_or_degraded_projection_degrades_to_rebuild_projection() -> None:
    for staleness_status in ("stale", "degraded"):
        decision = plan_phase5_next_step(
            cycle=_cycle(),
            gate_readout=_gate(claim_ceiling="paper_tracking_candidate"),
            recovery_ticket=None,
            projection_manifest=_projection(staleness_status=staleness_status),
        )

        assert decision.closeout_status == "degraded"
        assert decision.next_action == "rebuild_projection"
        assert decision.claim_ceiling == "paper_tracking_candidate"
        assert decision.source_refs == ["cycle-20260520-001", "gate-20260520-001", "projection-20260520-001"]


def test_required_publish_verification_without_ref_degrades_to_retry() -> None:
    decision = plan_phase5_next_step(
        cycle=_cycle(publish_verification_ref=None),
        gate_readout=_gate(claim_ceiling="paper_tracking_candidate"),
        recovery_ticket=None,
        projection_manifest=_projection(),
        require_publish_verification=True,
    )

    assert decision.closeout_status == "degraded"
    assert decision.next_action == "retry_failed_step"
    assert decision.claim_ceiling == "paper_tracking_candidate"


def test_gate_requested_next_actions_are_preserved() -> None:
    expected_status = {
        "redesign": "degraded",
        "retry_failed_step": "degraded",
        "rebuild_projection": "degraded",
        "continue_tracking": "completed",
    }
    for next_action, closeout_status in expected_status.items():
        decision = plan_phase5_next_step(
            cycle=_cycle(),
            gate_readout=_gate(next_action=next_action),
            recovery_ticket=None,
            projection_manifest=_projection(),
        )

        assert decision.closeout_status == closeout_status
        assert decision.next_action == next_action


def test_source_refs_are_traceable_to_input_artifact_ids() -> None:
    cycle = _cycle()
    gate = _gate()
    ticket = _ticket()
    projection = _projection()

    decision = plan_phase5_next_step(
        cycle=cycle,
        gate_readout=gate,
        recovery_ticket=ticket,
        projection_manifest=projection,
    )

    assert set(decision.source_refs) <= {cycle.cycle_id, gate.gate_id, ticket.ticket_id, projection.projection_id}


def test_planner_does_not_mutate_input_objects() -> None:
    cycle = _cycle()
    gate = _gate()
    ticket = _ticket()
    projection = _projection()
    before = deepcopy((cycle, gate, ticket, projection))

    plan_phase5_next_step(
        cycle=cycle,
        gate_readout=gate,
        recovery_ticket=ticket,
        projection_manifest=projection,
        require_publish_verification=True,
    )

    assert (cycle, gate, ticket, projection) == before
