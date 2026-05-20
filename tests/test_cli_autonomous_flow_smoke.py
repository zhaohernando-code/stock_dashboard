from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.autonomous_flow_artifacts import (
    FrontendProjectionManifestArtifact,
    Phase5CycleLedgerArtifact,
    Phase5GateReadoutArtifact,
    PublishVerificationRef,
)
from ashare_evidence.research_artifact_store import (
    write_frontend_projection_manifest_artifact,
    write_phase5_cycle_ledger_artifact,
    write_phase5_gate_readout_artifact,
)


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


def _assert_no_sensitive_service_payload(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert "input_bundle" not in serialized
    assert "runner_result" not in serialized
    assert "release-manifest:" not in serialized
    assert "sha256:" not in serialized


def test_phase5_local_cycle_step_default_smoke_reads_real_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    init_database_calls: list[object] = []

    def fail_init_database(database_url: str | None = None) -> None:
        init_database_calls.append(database_url)
        raise AssertionError("phase5-local-cycle-step must not initialize the database")

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)

    exit_code = _run_cli_tick(artifact_root=artifact_root)

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-20260520-smoke"
    assert payload["tick_status"] == "ok"
    assert payload["exit_code"] == 0
    assert payload["error"] is None
    assert payload["recommended_next_action"] == "continue_tracking"
    assert payload["summary_status"] == "completed"
    assert payload["status"]["cycle_id"] == "cycle-20260520-smoke"
    assert payload["status"]["decision_status"] == "completed"
    assert payload["status"]["summary_status"] == "completed"
    assert payload["status"]["publish_verification_status"] == "present"
    assert payload["status"]["staleness_status"] == "fresh"
    _assert_no_sensitive_service_payload(payload)


def test_phase5_local_cycle_step_default_smoke_missing_cycle_returns_tick_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls: list[object] = []

    def fail_init_database(database_url: str | None = None) -> None:
        init_database_calls.append(database_url)
        raise AssertionError("phase5-local-cycle-step must not initialize the database")

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)

    exit_code = _run_cli_tick(artifact_root=artifact_root, cycle_id="cycle-missing-smoke")

    assert exit_code == 1
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-missing-smoke"
    assert payload["tick_status"] == "error"
    assert payload["exit_code"] == 1
    assert payload["status"] is None
    assert payload["recommended_next_action"] == "retry_failed_step"
    assert payload["summary_status"] == "degraded"
    assert payload["error"]["error_type"] == "Phase5RunnerInputResolutionError"
    assert payload["error"]["failure_class"] == "artifact-missing"
    assert payload["error"]["recommended_recovery_action"] == "open_recovery_ticket"
    _assert_no_sensitive_service_payload(payload)


def test_phase5_local_cycle_step_plan_smoke_reads_real_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _write_happy_path_artifacts(artifact_root)
    init_database_calls: list[object] = []

    def fail_init_database(database_url: str | None = None) -> None:
        init_database_calls.append(database_url)
        raise AssertionError("phase5-local-cycle-step must not initialize the database")

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)

    exit_code = _run_cli_tick(artifact_root=artifact_root, output="plan")

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-20260520-smoke"
    assert payload["plan_status"] == "ready"
    assert payload["action"] == "continue_tracking"
    assert payload["source_tick_status"] == "ok"
    assert payload["summary_status"] == "completed"
    assert payload["claim_ceiling"] == "paper_tracking_candidate"
    assert payload["blocking_reasons"] == []
    assert "status" not in payload
    assert "error" not in payload
    _assert_no_sensitive_service_payload(payload)


def test_phase5_local_cycle_step_plan_smoke_missing_cycle_returns_recovery_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls: list[object] = []

    def fail_init_database(database_url: str | None = None) -> None:
        init_database_calls.append(database_url)
        raise AssertionError("phase5-local-cycle-step must not initialize the database")

    monkeypatch.setattr(cli_module, "init_database", fail_init_database)

    exit_code = _run_cli_tick(
        artifact_root=artifact_root,
        cycle_id="cycle-missing-smoke",
        output="plan",
    )

    assert exit_code == 0
    assert init_database_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle_id"] == "cycle-missing-smoke"
    assert payload["plan_status"] == "ready"
    assert payload["action"] == "open_recovery_ticket"
    assert payload["source_tick_status"] == "error"
    assert payload["summary_status"] == "degraded"
    assert payload["claim_ceiling"] is None
    assert payload["blocking_reasons"] == ["tick failure_class is artifact-missing"]
    assert "status" not in payload
    assert "error" not in payload
    _assert_no_sensitive_service_payload(payload)
