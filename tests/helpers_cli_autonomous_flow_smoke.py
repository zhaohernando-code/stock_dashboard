from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.autonomous_flow import (
    PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT,
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT,
)
from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    PublishVerificationRef,
)
from ashare_evidence.research_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    read_phase5_scheduler_diagnostic_artifact,
    write_frontend_projection_manifest_artifact,
    write_phase5_cycle_ledger_artifact,
    write_phase5_gate_readout_artifact,
)
from ashare_evidence.scheduler_execution_artifact_store import read_phase5_scheduler_execution_ledger_artifact


def _cycle(**overrides: object) -> Phase5CycleLedgerArtifact:
    values: dict[str, object] = {
        "cycle_id": "cycle-20260520-smoke",
        "trigger": "manual",
        "scope": {"portfolio": "short_pick_lab"},
        "status": "running",
        "started_at": "2026-05-20T09:00:00Z",
        "finished_at": None,
        "input_contract_versions": {"registry": "autonomous_flow_registry.v1"},
        "event_refs": ["phase5.cycle.started.v1"],
        "artifact_refs": ["frontend_projection_manifest:projection-20260520-smoke"],
        "gate_readout_refs": ["gate-20260520-smoke"],
        "recovery_ticket_refs": [],
        "publish_verification_ref": PublishVerificationRef(
            release_manifest_ref="release-manifest:phase5:20260520-smoke",
            digest="sha256:smokedigest123",
            event_ref="runtime.publish.verified.v1",
        ),
        "next_action": "continue_tracking",
    }
    values.update(overrides)
    return Phase5CycleLedgerArtifact(**values)


def _gate(**overrides: object) -> Phase5GateReadoutArtifact:
    values: dict[str, object] = {
        "gate_id": "gate-20260520-smoke",
        "cycle_id": "cycle-20260520-smoke",
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
    values: dict[str, object] = {
        "projection_id": "projection-20260520-smoke",
        "cycle_id": "cycle-20260520-smoke",
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


def _write_happy_path_artifacts(root: Path) -> None:
    write_phase5_cycle_ledger_artifact(_cycle(), root=root)
    write_phase5_gate_readout_artifact(_gate(), root=root)
    write_frontend_projection_manifest_artifact(_projection(), root=root)


def _run_cli_tick(
    *,
    artifact_root: Path,
    cycle_id: str = "cycle-20260520-smoke",
    output: str | None = None,
) -> int:
    argv = [
        "phase5-local-cycle-step",
        "--cycle-id",
        cycle_id,
        "--artifact-root",
        str(artifact_root),
    ]
    if output is not None:
        argv.extend(["--output", output])
    return cli_module.main(argv)


def _run_cli_diagnostic(
    *,
    artifact_root: Path,
    cycle_id: str,
    diagnostic_id: str,
    observed_at: str = "2026-05-20T10:01:00Z",
) -> int:
    argv = ["phase5-local-cycle-step", "--cycle-id", cycle_id, "--artifact-root", str(artifact_root)]
    argv.extend(["--output", "diagnostic", "--diagnostic-id", diagnostic_id, "--observed-at", observed_at])
    return cli_module.main(argv)


def _run_cli_execution(
    *,
    artifact_root: Path,
    cycle_id: str,
    execution_id: str = "execution-20260520-smoke",
    idempotency_key: str = "idempotency:execution-smoke",
    created_at: str = "2026-05-20T10:02:00Z",
    diagnostic_id: str | None = None,
) -> int:
    argv = ["phase5-local-cycle-step", "--cycle-id", cycle_id, "--artifact-root", str(artifact_root)]
    argv.extend(
        [
            "--output",
            "execution",
            "--execution-id",
            execution_id,
            "--idempotency-key",
            idempotency_key,
            "--created-at",
            created_at,
        ]
    )
    if diagnostic_id is not None:
        argv.extend(["--diagnostic-id", diagnostic_id])
    return cli_module.main(argv)


def _assert_diagnostic_smoke_recorded(
    *,
    payload: dict[str, Any],
    artifact_root: Path,
    cycle_id: str,
    expected_action: str,
    expected_severity: str,
    expected_cycle_event_recorded: bool,
) -> None:
    stored = read_phase5_scheduler_diagnostic_artifact(payload["diagnostic_id"], root=artifact_root)
    assert payload["execution_mode"] == "diagnostic_record"
    assert payload["action"] == expected_action
    assert payload["severity"] == expected_severity
    assert payload["cycle_event_recorded"] is expected_cycle_event_recorded
    assert stored.cycle_id == cycle_id
    assert stored.observed_at == "2026-05-20T10:01:00Z"
    assert stored.scheduler_action == expected_action
    if expected_cycle_event_recorded:
        stored_cycle = read_phase5_cycle_ledger_artifact(payload["cycle_id"], root=artifact_root)
        assert PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT in stored_cycle.event_refs


def _assert_execution_smoke_recorded(
    *,
    payload: dict[str, Any],
    artifact_root: Path,
    cycle_id: str,
    expected_action: str,
    expected_status: str,
    expected_cycle_event_recorded: bool,
) -> None:
    stored = read_phase5_scheduler_execution_ledger_artifact(payload["execution_id"], root=artifact_root)
    assert payload["execution_mode"] == "ledger_record"
    assert payload["action"] == expected_action
    assert payload["execution_status"] == expected_status
    assert payload["would_execute"] is False
    assert payload["ledger_recorded"] is True
    assert payload["cycle_event_recorded"] is expected_cycle_event_recorded
    assert stored.cycle_id == cycle_id
    assert stored.created_at == "2026-05-20T10:02:00Z"
    assert stored.plan_action == expected_action
    assert stored.execution_status == expected_status
    if expected_cycle_event_recorded:
        stored_cycle = read_phase5_cycle_ledger_artifact(payload["cycle_id"], root=artifact_root)
        assert PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT in stored_cycle.event_refs


def _assert_no_sensitive_service_payload(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert "input_bundle" not in serialized
    assert "runner_result" not in serialized
    assert "release-manifest:" not in serialized
    assert "sha256:" not in serialized


def _assert_no_nested_scheduler_payload(payload: dict[str, Any]) -> None:
    assert "plan_status" not in payload
    assert "source_tick_status" not in payload
    assert "status" not in payload
    assert "error" not in payload
    _assert_no_sensitive_service_payload(payload)


def _guard_init_database(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    init_database_calls: list[object] = []

    def fail_init_database(database_url: str | None = None) -> None:
        init_database_calls.append(database_url)
        raise AssertionError("phase5-local-cycle-step must not initialize the database")

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)
    return init_database_calls
