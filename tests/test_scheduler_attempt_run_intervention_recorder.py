from __future__ import annotations

from pathlib import Path

from ashare_evidence.scheduler_attempt_run_intervention_artifact_store import (
    read_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    Phase5SchedulerAttemptRunInterventionApplyResult,
)
from ashare_evidence.scheduler_attempt_run_intervention_recorder import (
    build_phase5_scheduler_attempt_intervention_run_id,
    record_phase5_scheduler_attempt_intervention_run_artifact,
)


def test_record_intervention_run_artifact_writes_apply_result(tmp_path: Path) -> None:
    result = _apply_result()

    recorded = record_phase5_scheduler_attempt_intervention_run_artifact(
        result,
        runner_id="runner-cd1",
        issued_at="2026-05-21T12:01:00Z",
        intervention_run_id="intervention-run-explicit",
        root=tmp_path,
    )
    stored = read_phase5_scheduler_attempt_intervention_run_artifact("intervention-run-explicit", root=tmp_path)

    assert recorded.path == (
        tmp_path
        / "autonomous_flow"
        / "phase5_scheduler_attempt_intervention_run"
        / "intervention-run-explicit.json"
    )
    assert stored.execution_status == "applied"
    assert stored.applied_output == "diagnostic"
    assert stored.diagnostic_id == "diagnostic-cd1"
    assert stored.source_latest_run_id == "run-blocked"
    assert stored.runner_id == "runner-cd1"


def test_intervention_run_id_is_stable_and_changes_on_status() -> None:
    first = build_phase5_scheduler_attempt_intervention_run_id(
        _apply_result(),
        runner_id="runner-cd1",
        issued_at="2026-05-21T12:01:00Z",
    )
    second = build_phase5_scheduler_attempt_intervention_run_id(
        _apply_result(),
        runner_id="runner-cd1",
        issued_at="2026-05-21T12:01:00Z",
    )
    changed = build_phase5_scheduler_attempt_intervention_run_id(
        _apply_result(execution_status="blocked", applied_output="none"),
        runner_id="runner-cd1",
        issued_at="2026-05-21T12:01:00Z",
    )

    assert first == second
    assert first != changed


def _apply_result(**overrides) -> Phase5SchedulerAttemptRunInterventionApplyResult:
    payload = {
        "cycle_id": "cycle-cd1",
        "execution_status": "applied",
        "applied_output": "diagnostic",
        "action": "open_recovery_ticket",
        "diagnostic_id": "diagnostic-cd1",
        "observed_at": "2026-05-21T12:00:00Z",
        "required_arguments": ("cycle_id", "diagnostic_id", "observed_at"),
        "missing_arguments": (),
        "cycle_event_recorded": True,
        "source_latest_run_id": "run-blocked",
        "reason": "attempt-run intervention diagnostic recorded",
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunInterventionApplyResult(**payload)
