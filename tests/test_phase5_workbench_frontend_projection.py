from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ashare_evidence.api import create_app
from ashare_evidence.autonomous_flow import record_phase5_recovery_ticket, start_phase5_cycle
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.frontend_projections import (
    build_phase5_workbench_projection_payload,
    get_ready_frontend_projection_payload,
    phase5_workbench_projection_key,
    refresh_frontend_projections,
    refresh_phase5_workbench_frontend_projection,
)
from ashare_evidence.scheduler_auto_progress_artifact_store import (
    write_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact


def test_phase5_workbench_projection_materializes_ready_frontend_payload(tmp_path: Path) -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)
    _seed_workbench_inputs(tmp_path)

    with session_scope(database_url) as session:
        result = refresh_phase5_workbench_frontend_projection(
            session,
            cycle_id="cycle-cp1",
            runner_id="runner-cp1",
            artifact_root=tmp_path,
        )
        session.flush()
        payload = get_ready_frontend_projection_payload(
            session,
            phase5_workbench_projection_key(cycle_id="cycle-cp1"),
        )

    assert result["projection_group"] == "phase5_workbench"
    assert payload is not None
    assert payload["projection_name"] == "phase5_operations_workbench"
    assert payload["cycle"]["cycle_id"] == "cycle-cp1"
    assert payload["auto_progress"]["latest_run_id"] == "auto-progress-run-cp1"
    assert payload["recommended_next_action"] == "continue_tracking"


def test_phase5_workbench_projection_refresh_requires_cycle_id() -> None:
    database_url = "sqlite:///:memory:"
    init_database(database_url)

    with session_scope(database_url) as session:
        try:
            refresh_frontend_projections(session, projection="phase5_workbench")
        except ValueError as exc:
            assert "cycle_id is required" in str(exc)
        else:
            raise AssertionError("phase5_workbench projection should require a cycle_id")


def test_phase5_workbench_projection_api_returns_fallback_and_refresh_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    _seed_workbench_inputs(tmp_path)
    monkeypatch.setenv("ASHARE_ARTIFACT_ROOT", str(tmp_path))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    fallback = client.get(
        "/dashboard/operations/workbench-projection",
        params={"cycle_id": "cycle-cp1", "runner_id": "runner-cp1"},
    )
    assert fallback.status_code == 200
    assert fallback.json()["projection_status"] == "degraded"

    refreshed = client.get(
        "/dashboard/operations/workbench-projection",
        params={"cycle_id": "cycle-cp1", "runner_id": "runner-cp1", "refresh": True},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["auto_progress"]["total_runs"] == 1

    with session_scope(database_url) as session:
        cached = get_ready_frontend_projection_payload(
            session,
            phase5_workbench_projection_key(cycle_id="cycle-cp1"),
        )

    assert cached is not None
    assert cached["source_refs"] == [
        "phase5_cycle_ledger:cycle-cp1",
        "auto-progress-run-cp1",
        "phase5_recovery_ticket:ticket-cp1",
    ]


def test_phase5_workbench_projection_api_blocks_missing_cycle(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-missing.db'}"
    monkeypatch.setenv("ASHARE_ARTIFACT_ROOT", str(tmp_path))

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    response = client.get("/dashboard/operations/workbench-projection", params={"cycle_id": "missing-cycle"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_status"] == "blocked"
    assert payload["missing_refs"] == ["phase5_cycle_ledger:missing-cycle"]


def test_phase5_workbench_projection_payload_builder_is_json_ready(tmp_path: Path) -> None:
    _seed_workbench_inputs(tmp_path)

    payload = build_phase5_workbench_projection_payload(
        cycle_id="cycle-cp1",
        runner_id="runner-cp1",
        artifact_root=tmp_path,
    )

    assert payload["projection_version"] == "workbench-projection-v1"
    assert payload["recovery"]["latest_ticket_id"] == "ticket-cp1"


def _seed_workbench_inputs(root: Path) -> None:
    start_phase5_cycle(
        cycle_id="cycle-cp1",
        trigger="recovery_followup",
        started_at="2026-05-21T10:00:00Z",
        root=root,
    )
    record_phase5_recovery_ticket(
        cycle_id="cycle-cp1",
        ticket_id="ticket-cp1",
        failed_step="replay_schedule",
        failure_class="contract_violation",
        failure_observed_at="2026-05-21T10:00:00Z",
        evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cp1"],
        recovery_action="open_followup_cycle",
        final_status="degraded",
        claim_ceiling_effect="unchanged",
        notes="scheduler recovery ticket intent built from intervention diagnostic",
        root=root,
    )
    write_phase5_scheduler_auto_progress_run_artifact(
        Phase5SchedulerAutoProgressRunArtifact(
            auto_progress_run_id="auto-progress-run-cp1",
            cycle_id="cycle-cp1",
            runner_id="runner-cp1",
            issued_at="2026-05-21T10:10:00Z",
            plan_status="ready",
            phase="recovery_followup_apply",
            apply_status="applied",
            applied_output="followup_cycle",
            recommended_output="attempt-run-recovery-followup-apply",
            recommended_flags=[],
            required_arguments=["created_at"],
            missing_arguments=[],
            blocking_reasons=[],
            evidence_refs=["phase5_scheduler_diagnostic:diagnostic-cp1"],
            result_refs=["phase5_cycle_ledger:followup-cycle-cp1"],
            notes="recovery follow-up cycle started from intent",
            event_refs=[],
        ),
        root=root,
    )
