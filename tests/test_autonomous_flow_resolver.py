from __future__ import annotations

from pathlib import Path

import pytest

from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    Phase5RecoveryTicketArtifact,
    PublishVerificationRef,
)
from ashare_evidence.autonomous_flow_resolver import (
    Phase5RunnerInputResolutionError,
    resolve_phase5_runner_inputs,
)
from ashare_evidence.research_artifact_store import (
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
        "recovery_ticket_refs": ["ticket-20260520-001"],
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
    write_phase5_recovery_ticket_artifact(_ticket(cycle_id=resolved_cycle.cycle_id), root=root)
    write_frontend_projection_manifest_artifact(_projection(cycle_id=resolved_cycle.cycle_id), root=root)
    return resolved_cycle


def _file_set(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def test_resolves_cycle_gate_recovery_and_projection(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write_complete_inputs(root)

    bundle = resolve_phase5_runner_inputs(cycle_id="cycle-20260520-001", root=root)

    assert bundle.cycle.cycle_id == "cycle-20260520-001"
    assert bundle.gate_readout is not None
    assert bundle.gate_readout.gate_id == "gate-20260520-001"
    assert bundle.recovery_ticket is not None
    assert bundle.recovery_ticket.ticket_id == "ticket-20260520-001"
    assert bundle.projection_manifest is not None
    assert bundle.projection_manifest.projection_id == "projection-20260520-001"
    assert bundle.missing_refs == []


def test_no_recovery_ref_returns_none_without_missing_ref(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(recovery_ticket_refs=[])
    write_phase5_cycle_ledger_artifact(cycle, root=root)
    write_phase5_gate_readout_artifact(_gate(), root=root)
    write_frontend_projection_manifest_artifact(_projection(), root=root)

    bundle = resolve_phase5_runner_inputs(cycle_id=cycle.cycle_id, root=root)

    assert bundle.recovery_ticket is None
    assert bundle.missing_refs == []


def test_missing_gate_ref_is_recorded(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(gate_readout_refs=[], recovery_ticket_refs=[])
    write_phase5_cycle_ledger_artifact(cycle, root=root)
    write_frontend_projection_manifest_artifact(_projection(), root=root)

    bundle = resolve_phase5_runner_inputs(cycle_id=cycle.cycle_id, root=root)

    assert bundle.gate_readout is None
    assert bundle.missing_refs == ["phase5_gate_readout:<missing>"]


def test_default_projection_uses_latest_ref_from_artifact_refs(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(
        artifact_refs=[
            "frontend_projection_manifest:projection-20260520-older",
            "phase5-horizon-study:latest",
            "frontend_projection_manifest:projection-20260520-latest",
        ],
        recovery_ticket_refs=[],
    )
    write_phase5_cycle_ledger_artifact(cycle, root=root)
    write_phase5_gate_readout_artifact(_gate(), root=root)
    write_frontend_projection_manifest_artifact(
        _projection(projection_id="projection-20260520-older"),
        root=root,
    )
    write_frontend_projection_manifest_artifact(
        _projection(projection_id="projection-20260520-latest"),
        root=root,
    )

    bundle = resolve_phase5_runner_inputs(cycle_id=cycle.cycle_id, root=root)

    assert bundle.projection_manifest is not None
    assert bundle.projection_manifest.projection_id == "projection-20260520-latest"
    assert bundle.missing_refs == []


def test_explicit_ids_override_cycle_refs(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle()
    _write_complete_inputs(root, cycle)
    write_phase5_gate_readout_artifact(_gate(gate_id="gate-explicit"), root=root)
    write_phase5_recovery_ticket_artifact(_ticket(ticket_id="ticket-explicit"), root=root)
    write_frontend_projection_manifest_artifact(_projection(projection_id="projection-explicit"), root=root)

    bundle = resolve_phase5_runner_inputs(
        cycle_id=cycle.cycle_id,
        gate_id="gate-explicit",
        recovery_ticket_id="ticket-explicit",
        projection_id="projection-explicit",
        root=root,
    )

    assert bundle.gate_readout is not None
    assert bundle.gate_readout.gate_id == "gate-explicit"
    assert bundle.recovery_ticket is not None
    assert bundle.recovery_ticket.ticket_id == "ticket-explicit"
    assert bundle.projection_manifest is not None
    assert bundle.projection_manifest.projection_id == "projection-explicit"
    assert bundle.missing_refs == []


def test_refs_pointing_to_missing_artifacts_are_recorded_once(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle(
        artifact_refs=[
            "frontend_projection_manifest:projection-missing",
            "frontend_projection_manifest:projection-missing",
        ],
        gate_readout_refs=["gate-missing"],
        recovery_ticket_refs=["ticket-missing"],
    )
    write_phase5_cycle_ledger_artifact(cycle, root=root)

    bundle = resolve_phase5_runner_inputs(cycle_id=cycle.cycle_id, root=root)

    assert bundle.gate_readout is None
    assert bundle.recovery_ticket is None
    assert bundle.projection_manifest is None
    assert bundle.missing_refs == [
        "phase5_gate_readout:gate-missing",
        "phase5_recovery_ticket:ticket-missing",
        "frontend_projection_manifest:projection-missing",
    ]


def test_missing_cycle_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"

    with pytest.raises(Phase5RunnerInputResolutionError, match="cycle ledger artifact is missing") as exc_info:
        resolve_phase5_runner_inputs(cycle_id="missing-cycle", root=root)

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.failure_class == "artifact-missing"
    assert exc_info.value.recommended_recovery_action == "open_recovery_ticket"
    assert exc_info.value.summary_status == "degraded"
    assert exc_info.value.recommended_next_action == "retry_failed_step"


def test_mismatched_artifact_cycle_id_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    cycle = _cycle()
    write_phase5_cycle_ledger_artifact(cycle, root=root)
    write_phase5_gate_readout_artifact(_gate(cycle_id="other-cycle"), root=root)
    write_frontend_projection_manifest_artifact(_projection(), root=root)

    with pytest.raises(
        Phase5RunnerInputResolutionError,
        match="phase5_gate_readout artifact cycle mismatch",
    ) as exc_info:
        resolve_phase5_runner_inputs(cycle_id=cycle.cycle_id, root=root)

    assert exc_info.value.failure_class == "contract-violation"
    assert exc_info.value.recommended_recovery_action == "block_cycle"
    assert exc_info.value.summary_status == "blocked"
    assert exc_info.value.recommended_next_action == "blocked"


def test_resolver_does_not_write_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _write_complete_inputs(root)
    before = _file_set(root)

    resolve_phase5_runner_inputs(cycle_id="cycle-20260520-001", root=root)

    assert _file_set(root) == before
