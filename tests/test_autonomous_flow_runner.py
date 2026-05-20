from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ashare_evidence import autonomous_flow_runner as runner_module
from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    PublishVerificationRef,
)
from ashare_evidence.autonomous_flow_runner import run_phase5_local_cycle_step
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    write_phase5_cycle_ledger_artifact,
)


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


def _write_cycle(root: Path, cycle: Phase5CycleLedgerArtifact) -> None:
    write_phase5_cycle_ledger_artifact(cycle, root=root)


def test_dry_run_returns_decision_without_calling_closeout_or_writing_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifacts"

    def fail_if_called(**_: object) -> Phase5CycleLedgerArtifact:
        raise AssertionError("finish_phase5_cycle should not be called during dry run")

    monkeypatch.setattr(runner_module, "finish_phase5_cycle", fail_if_called)

    result = run_phase5_local_cycle_step(
        cycle=_cycle(),
        gate_readout=_gate(),
        recovery_ticket=None,
        projection_manifest=_projection(),
        finished_at=None,
        apply_closeout=False,
        root=root,
    )

    assert result.cycle_id == "cycle-20260520-001"
    assert result.decision.closeout_status == "completed"
    assert result.decision.next_action == "continue_tracking"
    assert result.closeout_applied is False
    assert result.closeout_cycle is None
    assert result.skipped_reason == "closeout_not_requested"
    assert not root.exists()


def test_apply_closeout_writes_cycle_and_preserves_planner_decision(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle()
    _write_cycle(root, cycle)

    result = run_phase5_local_cycle_step(
        cycle=cycle,
        gate_readout=_gate(),
        recovery_ticket=None,
        projection_manifest=_projection(),
        finished_at="2026-05-20T09:20:00Z",
        apply_closeout=True,
        root=root,
    )

    assert result.closeout_applied is True
    assert result.decision.closeout_status == "completed"
    assert result.decision.next_action == "continue_tracking"
    assert result.closeout_cycle is not None
    assert result.closeout_cycle.status == "degraded"
    assert result.closeout_cycle.next_action == "continue_tracking"
    assert result.closeout_cycle.finished_at == "2026-05-20T09:20:00Z"

    stored = read_phase5_cycle_ledger_artifact("cycle-20260520-001", root=root)
    assert stored == result.closeout_cycle


def test_apply_closeout_requires_finished_at_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"

    with pytest.raises(ValueError, match="requires finished_at"):
        run_phase5_local_cycle_step(
            cycle=_cycle(),
            gate_readout=_gate(),
            recovery_ticket=None,
            projection_manifest=_projection(),
            finished_at=None,
            apply_closeout=True,
            root=root,
        )

    assert not root.exists()


def test_blocker_decision_closes_out_as_blocked(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(publish_verification_ref=None)
    _write_cycle(root, cycle)

    result = run_phase5_local_cycle_step(
        cycle=cycle,
        gate_readout=_gate(
            gate_status="blocked",
            claim_ceiling="blocked",
            blocking_reasons=["contract registry check failed"],
            next_action="blocked",
        ),
        recovery_ticket=None,
        projection_manifest=_projection(),
        finished_at="2026-05-20T09:20:00Z",
        apply_closeout=True,
        root=root,
    )

    assert result.decision.closeout_status == "blocked"
    assert result.decision.next_action == "blocked"
    assert result.closeout_cycle is not None
    assert result.closeout_cycle.status == "blocked"
    assert result.closeout_cycle.next_action == "blocked"


def test_stale_projection_closes_out_degraded_with_rebuild_projection(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle()
    _write_cycle(root, cycle)

    result = run_phase5_local_cycle_step(
        cycle=cycle,
        gate_readout=_gate(claim_ceiling="paper_tracking_candidate"),
        recovery_ticket=None,
        projection_manifest=_projection(staleness_status="stale"),
        finished_at="2026-05-20T09:20:00Z",
        apply_closeout=True,
        root=root,
    )

    assert result.decision.closeout_status == "degraded"
    assert result.decision.next_action == "rebuild_projection"
    assert result.closeout_cycle is not None
    assert result.closeout_cycle.status == "degraded"
    assert result.closeout_cycle.next_action == "rebuild_projection"


def test_runner_does_not_mutate_input_objects(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle()
    gate = _gate()
    ticket = _ticket()
    projection = _projection(staleness_status="degraded")
    before = deepcopy((cycle, gate, ticket, projection))
    _write_cycle(root, cycle)

    run_phase5_local_cycle_step(
        cycle=cycle,
        gate_readout=gate,
        recovery_ticket=ticket,
        projection_manifest=projection,
        finished_at="2026-05-20T09:20:00Z",
        apply_closeout=True,
        root=root,
    )

    assert (cycle, gate, ticket, projection) == before
