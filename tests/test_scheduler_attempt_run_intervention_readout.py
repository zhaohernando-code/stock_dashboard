from __future__ import annotations

from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    write_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_artifacts import (
    Phase5SchedulerAttemptInterventionRunArtifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    build_phase5_scheduler_attempt_intervention_run_readout,
    read_phase5_scheduler_attempt_intervention_run_readout,
)


def test_build_intervention_run_readout_handles_empty_input() -> None:
    readout = build_phase5_scheduler_attempt_intervention_run_readout([])

    assert readout.cycle_id is None
    assert readout.runner_id is None
    assert readout.total_runs == 0
    assert readout.latest_intervention_run_id is None
    assert readout.latest_execution_status is None
    assert readout.readout_status == "degraded"
    assert readout.intervention_run_refs == []


def test_build_intervention_run_readout_summarizes_mixed_runs() -> None:
    readout = build_phase5_scheduler_attempt_intervention_run_readout(
        [
            _intervention_run(intervention_run_id="run-applied", issued_at="2026-05-21T08:00:00Z"),
            _intervention_run(
                intervention_run_id="run-skipped",
                issued_at="2026-05-21T09:00:00Z",
                execution_status="skipped",
                applied_output="none",
            ),
            _intervention_run(
                intervention_run_id="run-blocked",
                issued_at="2026-05-21T10:00:00Z",
                execution_status="blocked",
                applied_output="none",
            ),
        ]
    )

    assert readout.cycle_id == "cycle-20260521-am"
    assert readout.runner_id == "runner-ce1"
    assert readout.total_runs == 3
    assert readout.latest_intervention_run_id == "run-blocked"
    assert readout.latest_execution_status == "blocked"
    assert readout.latest_issued_at == "2026-05-21T10:00:00Z"
    assert readout.applied_count == 1
    assert readout.blocked_count == 1
    assert readout.skipped_count == 1
    assert readout.latest_blocked_run_id == "run-blocked"
    assert readout.latest_applied_run_id == "run-applied"
    assert readout.readout_status == "blocked"
    assert readout.intervention_run_refs == ["run-blocked", "run-skipped", "run-applied"]


def test_read_intervention_run_readout_uses_cycle_runner_query(tmp_path) -> None:
    for artifact in [
        _intervention_run(intervention_run_id="run-other-cycle", cycle_id="cycle-other", issued_at="2026-05-21T11:00:00Z"),
        _intervention_run(intervention_run_id="run-other-runner", runner_id="runner-other", issued_at="2026-05-21T10:30:00Z"),
        _intervention_run(intervention_run_id="run-target-old", issued_at="2026-05-21T09:00:00Z", execution_status="blocked", applied_output="none"),
        _intervention_run(intervention_run_id="run-target-new", issued_at="2026-05-21T10:00:00Z"),
    ]:
        write_phase5_scheduler_attempt_intervention_run_artifact(artifact, root=tmp_path)

    readout = read_phase5_scheduler_attempt_intervention_run_readout(
        cycle_id="cycle-20260521-am",
        runner_id="runner-ce1",
        root=tmp_path,
    )

    assert readout.total_runs == 2
    assert readout.latest_intervention_run_id == "run-target-new"
    assert readout.latest_blocked_run_id == "run-target-old"
    assert readout.latest_applied_run_id == "run-target-new"
    assert readout.readout_status == "current"
    assert readout.intervention_run_refs == ["run-target-new", "run-target-old"]


def _intervention_run(**overrides) -> Phase5SchedulerAttemptInterventionRunArtifact:
    payload = {
        "intervention_run_id": "intervention-run-20260521-am",
        "cycle_id": "cycle-20260521-am",
        "runner_id": "runner-ce1",
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
