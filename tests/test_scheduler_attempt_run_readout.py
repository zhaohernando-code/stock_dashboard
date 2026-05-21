from __future__ import annotations

from ashare_evidence.scheduler_attempt_run_artifact_store import write_phase5_scheduler_attempt_run_artifact
from ashare_evidence.scheduler_attempt_run_artifacts import Phase5SchedulerAttemptRunArtifact
from ashare_evidence.scheduler_attempt_run_readout import (
    build_phase5_scheduler_attempt_run_readout,
    read_phase5_scheduler_attempt_run_readout,
)


def test_build_attempt_run_readout_handles_empty_input() -> None:
    readout = build_phase5_scheduler_attempt_run_readout([])

    assert readout.cycle_id is None
    assert readout.runner_id is None
    assert readout.total_runs == 0
    assert readout.latest_run_id is None
    assert readout.latest_apply_status is None
    assert readout.latest_attempt_status is None
    assert readout.latest_issued_at is None
    assert readout.applied_count == 0
    assert readout.blocked_count == 0
    assert readout.skipped_count == 0
    assert readout.latest_blocked_run_id is None
    assert readout.latest_applied_run_id is None
    assert readout.staleness_status == "degraded"
    assert readout.run_refs == []


def test_build_attempt_run_readout_summarizes_mixed_runs() -> None:
    readout = build_phase5_scheduler_attempt_run_readout(
        [
            _attempt_run(run_id="run-applied", issued_at="2026-05-21T08:00:00Z"),
            _attempt_run(run_id="run-skipped", issued_at="2026-05-21T09:00:00Z", apply_status="skipped"),
            _attempt_run(
                run_id="run-blocked",
                issued_at="2026-05-21T10:00:00Z",
                attempt_status="blocked",
                apply_status="blocked",
            ),
        ]
    )

    assert readout.cycle_id == "cycle-20260521-am"
    assert readout.runner_id == "runner-bv1"
    assert readout.total_runs == 3
    assert readout.latest_run_id == "run-blocked"
    assert readout.latest_apply_status == "blocked"
    assert readout.latest_attempt_status == "blocked"
    assert readout.latest_issued_at == "2026-05-21T10:00:00Z"
    assert readout.applied_count == 1
    assert readout.blocked_count == 1
    assert readout.skipped_count == 1
    assert readout.latest_blocked_run_id == "run-blocked"
    assert readout.latest_applied_run_id == "run-applied"
    assert readout.staleness_status == "blocked"
    assert readout.run_refs == ["run-blocked", "run-skipped", "run-applied"]


def test_read_attempt_run_readout_uses_cycle_runner_query(tmp_path) -> None:
    for artifact in [
        _attempt_run(run_id="run-other-cycle", cycle_id="cycle-other", issued_at="2026-05-21T11:00:00Z"),
        _attempt_run(run_id="run-other-runner", runner_id="runner-other", issued_at="2026-05-21T10:30:00Z"),
        _attempt_run(run_id="run-target-old", issued_at="2026-05-21T09:00:00Z", apply_status="blocked"),
        _attempt_run(run_id="run-target-new", issued_at="2026-05-21T10:00:00Z"),
    ]:
        write_phase5_scheduler_attempt_run_artifact(artifact, root=tmp_path)

    readout = read_phase5_scheduler_attempt_run_readout(
        cycle_id="cycle-20260521-am",
        runner_id="runner-bv1",
        root=tmp_path,
    )

    assert readout.cycle_id == "cycle-20260521-am"
    assert readout.runner_id == "runner-bv1"
    assert readout.total_runs == 2
    assert readout.latest_run_id == "run-target-new"
    assert readout.latest_blocked_run_id == "run-target-old"
    assert readout.latest_applied_run_id == "run-target-new"
    assert readout.staleness_status == "current"
    assert readout.run_refs == ["run-target-new", "run-target-old"]


def _attempt_run(**overrides) -> Phase5SchedulerAttemptRunArtifact:
    payload = {
        "run_id": "run-20260521-am",
        "attempt_id": "attempt-20260521-am",
        "cycle_id": "cycle-20260521-am",
        "runner_id": "runner-bv1",
        "issued_at": "2026-05-21T09:00:00Z",
        "attempt_status": "ready",
        "route_type": "execution_output",
        "preflight_status": "ready",
        "apply_status": "applied",
        "applied_output": "execution",
        "required_arguments": ["execution_id", "idempotency_key", "created_at"],
        "missing_arguments": [],
        "diagnostic_id": None,
        "execution_id": "execution-20260521-am",
        "idempotency_key": "cycle:cycle-20260521-am:retry_failed_step",
        "cycle_event_recorded": True,
        "reason": "captured scheduler attempt route apply result",
        "error_type": None,
        "blocking_reasons": [],
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunArtifact(**payload)
