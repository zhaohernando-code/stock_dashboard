from __future__ import annotations

from pathlib import Path

import pytest

from ashare_evidence import autonomous_flow_service as service_module
from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    PublishVerificationRef,
)
from ashare_evidence.autonomous_flow_planner import Phase5PlannerDecision
from ashare_evidence.autonomous_flow_resolver import (
    Phase5RunnerInputBundle,
    Phase5RunnerInputResolutionError,
)
from ashare_evidence.autonomous_flow_runner import Phase5RunnerResult
from ashare_evidence.autonomous_flow_service import run_phase5_local_cycle_service
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    write_frontend_projection_manifest_artifact,
    write_phase5_cycle_ledger_artifact,
    write_phase5_gate_readout_artifact,
    write_phase5_recovery_ticket_artifact,
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


def _write_complete_inputs(root: Path, cycle: Phase5CycleLedgerArtifact | None = None) -> Phase5CycleLedgerArtifact:
    resolved_cycle = cycle or _cycle()
    write_phase5_cycle_ledger_artifact(resolved_cycle, root=root)
    write_phase5_gate_readout_artifact(_gate(cycle_id=resolved_cycle.cycle_id), root=root)
    write_frontend_projection_manifest_artifact(_projection(cycle_id=resolved_cycle.cycle_id), root=root)
    return resolved_cycle


def _file_set(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def _decision(cycle_id: str) -> Phase5PlannerDecision:
    return Phase5PlannerDecision(
        cycle_id=cycle_id,
        closeout_status="completed",
        next_action="continue_tracking",
        claim_ceiling="paper_tracking_candidate",
        decision_reason="test decision",
        blocking_reasons=[],
        source_refs=[cycle_id],
    )


def test_dry_run_resolves_bundle_and_returns_runner_decision_without_writing_closeout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    _write_complete_inputs(root)
    before = _file_set(root)

    result = run_phase5_local_cycle_service(
        cycle_id="cycle-20260520-001",
        apply_closeout=False,
        root=root,
    )

    assert result.cycle_id == "cycle-20260520-001"
    assert result.input_bundle.cycle.cycle_id == "cycle-20260520-001"
    assert result.runner_result.decision.closeout_status == "completed"
    assert result.runner_result.decision.next_action == "continue_tracking"
    assert result.runner_result.closeout_applied is False
    assert result.runner_result.closeout_cycle is None
    assert result.missing_refs == []
    assert _file_set(root) == before


def test_apply_closeout_through_service_writes_cycle_closeout(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write_complete_inputs(root)

    result = run_phase5_local_cycle_service(
        cycle_id="cycle-20260520-001",
        finished_at="2026-05-20T09:20:00Z",
        apply_closeout=True,
        root=root,
    )

    assert result.runner_result.closeout_applied is True
    assert result.runner_result.closeout_cycle is not None
    assert result.runner_result.closeout_cycle.status == "degraded"
    assert result.runner_result.closeout_cycle.finished_at == "2026-05-20T09:20:00Z"

    stored = read_phase5_cycle_ledger_artifact("cycle-20260520-001", root=root)
    assert stored == result.runner_result.closeout_cycle


def test_missing_cycle_resolution_error_is_not_swallowed(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"

    with pytest.raises(Phase5RunnerInputResolutionError, match="cycle ledger artifact is missing"):
        run_phase5_local_cycle_service(cycle_id="missing-cycle", root=root)


def test_missing_gate_and_projection_are_reported_and_runner_degrades(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(
        artifact_refs=[],
        gate_readout_refs=[],
        recovery_ticket_refs=[],
    )
    write_phase5_cycle_ledger_artifact(cycle, root=root)

    result = run_phase5_local_cycle_service(cycle_id=cycle.cycle_id, root=root)

    assert result.missing_refs == [
        "phase5_gate_readout:<missing>",
        "frontend_projection_manifest:<missing>",
    ]
    assert result.input_bundle.gate_readout is None
    assert result.input_bundle.projection_manifest is None
    assert result.runner_result.decision.closeout_status == "degraded"
    assert result.runner_result.decision.next_action == "retry_failed_step"
    assert result.runner_result.decision.decision_reason == "gate readout is missing"


def test_explicit_ids_override_cycle_refs(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(
        recovery_ticket_refs=["ticket-20260520-001"],
    )
    _write_complete_inputs(root, cycle)
    write_phase5_gate_readout_artifact(_gate(gate_id="gate-explicit"), root=root)
    write_phase5_recovery_ticket_artifact(_ticket(ticket_id="ticket-explicit"), root=root)
    write_frontend_projection_manifest_artifact(_projection(projection_id="projection-explicit"), root=root)

    result = run_phase5_local_cycle_service(
        cycle_id=cycle.cycle_id,
        gate_id="phase5_gate_readout:gate-explicit",
        recovery_ticket_id="phase5_recovery_ticket:ticket-explicit",
        projection_id="frontend_projection_manifest:projection-explicit",
        root=root,
    )

    assert result.input_bundle.gate_readout is not None
    assert result.input_bundle.gate_readout.gate_id == "gate-explicit"
    assert result.input_bundle.recovery_ticket is not None
    assert result.input_bundle.recovery_ticket.ticket_id == "ticket-explicit"
    assert result.input_bundle.projection_manifest is not None
    assert result.input_bundle.projection_manifest.projection_id == "projection-explicit"
    assert result.missing_refs == []


def test_apply_closeout_requires_finished_at_before_resolving_or_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifacts"

    def fail_if_called(**_: object) -> Phase5RunnerInputBundle:
        raise AssertionError("resolver should not be called when closeout lacks finished_at")

    monkeypatch.setattr(service_module, "resolve_phase5_runner_inputs", fail_if_called)

    with pytest.raises(ValueError, match="requires finished_at"):
        run_phase5_local_cycle_service(
            cycle_id="cycle-20260520-001",
            apply_closeout=True,
            root=root,
        )

    assert not root.exists()


def test_service_calls_resolver_then_runner_facade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle()
    gate = _gate()
    ticket = _ticket()
    projection = _projection()
    calls: list[tuple[str, object]] = []

    def fake_resolver(**kwargs: object) -> Phase5RunnerInputBundle:
        calls.append(("resolver", kwargs))
        return Phase5RunnerInputBundle(
            cycle=cycle,
            gate_readout=gate,
            recovery_ticket=ticket,
            projection_manifest=projection,
            missing_refs=["phase5_gate_readout:shadow"],
        )

    def fake_runner(**kwargs: object) -> Phase5RunnerResult:
        calls.append(("runner", kwargs))
        return Phase5RunnerResult(
            cycle_id=cycle.cycle_id,
            decision=_decision(cycle.cycle_id),
            closeout_applied=False,
            closeout_cycle=None,
            skipped_reason="closeout_not_requested",
        )

    monkeypatch.setattr(service_module, "resolve_phase5_runner_inputs", fake_resolver)
    monkeypatch.setattr(service_module, "run_phase5_local_cycle_step", fake_runner)

    result = run_phase5_local_cycle_service(
        cycle_id=cycle.cycle_id,
        gate_id="gate-explicit",
        recovery_ticket_id="ticket-explicit",
        projection_id="projection-explicit",
        require_publish_verification=True,
        root=root,
    )

    assert [call[0] for call in calls] == ["resolver", "runner"]
    assert calls[0][1] == {
        "cycle_id": cycle.cycle_id,
        "gate_id": "gate-explicit",
        "recovery_ticket_id": "ticket-explicit",
        "projection_id": "projection-explicit",
        "root": root,
    }
    assert calls[1][1] == {
        "cycle": cycle,
        "gate_readout": gate,
        "recovery_ticket": ticket,
        "projection_manifest": projection,
        "finished_at": None,
        "apply_closeout": False,
        "require_publish_verification": True,
        "root": root,
    }
    assert result.input_bundle.cycle == cycle
    assert result.runner_result.cycle_id == cycle.cycle_id
    assert result.missing_refs == ["phase5_gate_readout:shadow"]
