from __future__ import annotations

from ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply import (
    Phase5SchedulerAttemptRouteApplyResult,
)
from ashare_evidence.scheduler_attempt_run_artifact_store import (
    read_phase5_scheduler_attempt_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_recorder import (
    build_phase5_scheduler_attempt_run_artifact,
    build_phase5_scheduler_attempt_run_id,
    record_phase5_scheduler_attempt_run_artifact,
)


def test_build_attempt_run_artifact_from_applied_result() -> None:
    result = _route_apply_result()

    artifact = build_phase5_scheduler_attempt_run_artifact(
        result,
        runner_id="runner-br1",
        issued_at="2026-05-21T10:00:00Z",
        run_id="run-explicit",
    )

    assert artifact.run_id == "run-explicit"
    assert artifact.attempt_id == "attempt-br1"
    assert artifact.cycle_id == "cycle-br1"
    assert artifact.runner_id == "runner-br1"
    assert artifact.issued_at == "2026-05-21T10:00:00Z"
    assert artifact.attempt_status == "ready"
    assert artifact.route_type == "execution_output"
    assert artifact.preflight_status == "ready"
    assert artifact.apply_status == "applied"
    assert artifact.applied_output == "execution"
    assert artifact.required_arguments == ["execution_id", "idempotency_key", "created_at"]
    assert artifact.missing_arguments == []
    assert artifact.execution_id == "execution-br1"
    assert artifact.idempotency_key == "cycle:cycle-br1:record_execution"
    assert artifact.cycle_event_recorded is True
    assert artifact.reason == "execution ledger recorded"
    assert artifact.error_type is None
    assert artifact.blocking_reasons == []


def test_build_attempt_run_artifact_from_blocked_missing_context_result() -> None:
    result = _route_apply_result(
        attempt_id=None,
        attempt_context_status="blocked",
        execution_status="blocked",
        preflight_status="blocked",
        applied_output="none",
        required_arguments=("cycle_id", "issued_at", "runner_id"),
        missing_arguments=("issued_at", "runner_id"),
        execution_id=None,
        idempotency_key=None,
        cycle_event_recorded=False,
        reason="plain reason should be copied but not parsed",
    )

    artifact = build_phase5_scheduler_attempt_run_artifact(
        result,
        runner_id="runner-br1",
        issued_at="2026-05-21T10:00:00Z",
    )

    assert artifact.attempt_status == "blocked"
    assert artifact.apply_status == "blocked"
    assert artifact.applied_output == "none"
    assert artifact.missing_arguments == ["issued_at", "runner_id"]
    assert artifact.blocking_reasons == ["missing required arguments: issued_at, runner_id"]
    assert artifact.reason == "plain reason should be copied but not parsed"


def test_attempt_run_id_is_deterministic_from_structured_inputs() -> None:
    result = _route_apply_result()

    first = build_phase5_scheduler_attempt_run_id(
        result,
        runner_id="runner-br1",
        issued_at="2026-05-21T10:00:00Z",
    )
    second = build_phase5_scheduler_attempt_run_id(
        result,
        runner_id="runner-br1",
        issued_at="2026-05-21T10:00:00Z",
    )
    changed = build_phase5_scheduler_attempt_run_id(
        result,
        runner_id="runner-br2",
        issued_at="2026-05-21T10:00:00Z",
    )

    assert first == second
    assert first != changed
    assert first.startswith("attempt-run-cycle-br1-runner-br1-")


def test_record_attempt_run_artifact_writes_store(tmp_path) -> None:
    result = _route_apply_result()

    recorded = record_phase5_scheduler_attempt_run_artifact(
        result,
        runner_id="runner-br1",
        issued_at="2026-05-21T10:00:00Z",
        run_id="run-store-br1",
        root=tmp_path,
    )

    stored = read_phase5_scheduler_attempt_run_artifact("run-store-br1", root=tmp_path)

    assert recorded.path == tmp_path / "autonomous_flow" / "phase5_scheduler_attempt_run" / "run-store-br1.json"
    assert recorded.artifact == stored
    assert stored.apply_status == "applied"
    assert stored.applied_output == "execution"


def _route_apply_result(**overrides) -> Phase5SchedulerAttemptRouteApplyResult:
    payload = {
        "cycle_id": "cycle-br1",
        "route_type": "execution_output",
        "attempt_id": "attempt-br1",
        "attempt_context_status": "ready",
        "execution_status": "applied",
        "preflight_status": "ready",
        "applied_output": "execution",
        "required_arguments": ("execution_id", "idempotency_key", "created_at"),
        "missing_arguments": (),
        "diagnostic_id": None,
        "execution_id": "execution-br1",
        "idempotency_key": "cycle:cycle-br1:record_execution",
        "cycle_event_recorded": True,
        "reason": "execution ledger recorded",
        "error_type": None,
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRouteApplyResult(**payload)
