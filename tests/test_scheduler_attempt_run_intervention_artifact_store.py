from __future__ import annotations

from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    find_latest_phase5_scheduler_attempt_intervention_run_artifact,
    list_phase5_scheduler_attempt_intervention_run_artifacts,
    read_phase5_scheduler_attempt_intervention_run_artifact,
    write_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)


def test_list_intervention_run_artifacts_filters_and_sorts(tmp_path) -> None:
    for artifact in [
        _intervention_run(intervention_run_id="run-1", issued_at="2026-05-21T08:00:00Z"),
        _intervention_run(intervention_run_id="run-3", issued_at="2026-05-21T10:00:00Z", execution_status="blocked"),
        _intervention_run(intervention_run_id="run-2", issued_at="2026-05-21T10:00:00Z", runner_id="runner-b"),
        _intervention_run(intervention_run_id="run-4", cycle_id="cycle-other", issued_at="2026-05-21T11:00:00Z"),
    ]:
        write_phase5_scheduler_attempt_intervention_run_artifact(artifact, root=tmp_path)

    assert [
        artifact.intervention_run_id
        for artifact in list_phase5_scheduler_attempt_intervention_run_artifacts(
            cycle_id="cycle-20260521-am",
            root=tmp_path,
        )
    ] == ["run-3", "run-2", "run-1"]
    assert [
        artifact.intervention_run_id
        for artifact in list_phase5_scheduler_attempt_intervention_run_artifacts(
            runner_id="runner-b",
            execution_status="applied",
            root=tmp_path,
        )
    ] == ["run-2"]


def test_find_latest_intervention_run_artifact_returns_latest_filtered_run(tmp_path) -> None:
    write_phase5_scheduler_attempt_intervention_run_artifact(
        _intervention_run(intervention_run_id="older-blocked", issued_at="2026-05-21T08:00:00Z", execution_status="blocked"),
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_intervention_run_artifact(
        _intervention_run(intervention_run_id="latest-applied", issued_at="2026-05-21T10:00:00Z"),
        root=tmp_path,
    )

    latest_blocked = find_latest_phase5_scheduler_attempt_intervention_run_artifact(
        execution_status="blocked",
        root=tmp_path,
    )
    latest_any = find_latest_phase5_scheduler_attempt_intervention_run_artifact(root=tmp_path)

    assert latest_blocked is not None
    assert latest_blocked.intervention_run_id == "older-blocked"
    assert latest_any is not None
    assert latest_any.intervention_run_id == "latest-applied"


def test_read_intervention_run_artifact_round_trips(tmp_path) -> None:
    artifact = _intervention_run(intervention_run_id="run-store")

    path = write_phase5_scheduler_attempt_intervention_run_artifact(artifact, root=tmp_path)
    stored = read_phase5_scheduler_attempt_intervention_run_artifact("run-store", root=tmp_path)

    assert path == tmp_path / "autonomous_flow" / "phase5_scheduler_attempt_intervention_run" / "run-store.json"
    assert stored == artifact


def _intervention_run(**overrides) -> Phase5SchedulerAttemptInterventionRunArtifact:
    payload = {
        "intervention_run_id": "intervention-run-20260521-am",
        "cycle_id": "cycle-20260521-am",
        "runner_id": "runner-a",
        "issued_at": "2026-05-21T09:00:00Z",
        "execution_status": "applied",
        "applied_output": "diagnostic",
        "action": "open_recovery_ticket",
        "diagnostic_id": "diagnostic-20260521-am",
        "observed_at": "2026-05-21T09:00:00Z",
        "required_arguments": ["cycle_id", "diagnostic_id", "observed_at"],
        "missing_arguments": [],
        "cycle_event_recorded": True,
        "source_latest_run_id": "attempt-run-blocked",
        "reason": "attempt-run intervention diagnostic recorded",
        "error_type": None,
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptInterventionRunArtifact(**payload)
