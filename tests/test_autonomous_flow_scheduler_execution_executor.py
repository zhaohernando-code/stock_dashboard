from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashare_evidence.autonomous_flow import (
    PHASE5_CYCLE_STARTED_EVENT,
    PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT,
    Phase5SchedulerExecutionIdempotencyConflictError,
)
from ashare_evidence.autonomous_flow_scheduler_executor import record_phase5_scheduler_plan_execution
from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact
from ashare_evidence.scheduler_execution_artifact_store import (
    create_phase5_scheduler_execution_reservation_artifact,
    read_phase5_scheduler_execution_ledger_artifact,
    read_phase5_scheduler_execution_ledger_artifact_if_exists,
)
from tests.helpers_autonomous_flow_scheduler import _plan
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle


def test_execution_executor_records_ledger_and_cycle_event(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-execution")

    result = record_phase5_scheduler_plan_execution(
        _plan(cycle_id="cycle-execution", action="retry_failed_step", reason="retryable failure"),
        execution_id="execution-record",
        idempotency_key="idempotency:execution-record",
        created_at="2026-05-21T10:00:00Z",
        diagnostic_refs=["diagnostic-1", "diagnostic-1"],
        root=root,
    )
    ledger = read_phase5_scheduler_execution_ledger_artifact("execution-record", root=root)
    cycle = read_phase5_cycle_ledger_artifact("cycle-execution", root=root)

    assert result.execution_mode == "ledger_record"
    assert result.execution_status == "planned"
    assert result.action == "retry_failed_step"
    assert result.would_execute is False
    assert result.ledger_recorded is True
    assert result.cycle_event_recorded is True
    assert result.diagnostic_refs == ["diagnostic-1"]
    assert ledger.plan_action == "retry_failed_step"
    assert ledger.would_execute is False
    assert cycle.event_refs == [PHASE5_CYCLE_STARTED_EVENT, PHASE5_SCHEDULER_EXECUTION_RECORDED_EVENT]


@pytest.mark.parametrize(
    ("plan_status", "action", "expected_status"),
    [
        ("blocked", "continue_tracking", "blocked"),
        ("ready", "block_cycle", "blocked"),
        ("ready", "none", "skipped"),
        ("ready", "continue_tracking", "planned"),
    ],
)
def test_execution_executor_maps_statuses(
    tmp_path: Path,
    plan_status: str,
    action: str,
    expected_status: str,
) -> None:
    result = record_phase5_scheduler_plan_execution(
        _plan(cycle_id="cycle-missing", plan_status=plan_status, action=action),
        execution_id=f"execution-{expected_status}-{action}",
        idempotency_key=f"idempotency:{expected_status}:{action}",
        created_at="2026-05-21T10:00:00Z",
        root=tmp_path / "artifacts",
    )

    assert result.execution_status == expected_status
    assert result.action == action
    assert result.would_execute is False
    assert result.cycle_event_recorded is False


def test_execution_executor_propagates_idempotency_conflict_without_requested_ledger(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    create_phase5_scheduler_execution_reservation_artifact(
        idempotency_key="idempotency:conflict",
        execution_id="execution-existing",
        cycle_id="cycle-conflict",
        created_at="2026-05-21T09:00:00Z",
        root=root,
    )

    with pytest.raises(Phase5SchedulerExecutionIdempotencyConflictError) as raised:
        record_phase5_scheduler_plan_execution(
            _plan(cycle_id="cycle-conflict", action="retry_failed_step"),
            execution_id="execution-requested",
            idempotency_key="idempotency:conflict",
            created_at="2026-05-21T10:00:00Z",
            root=root,
        )

    assert raised.value.existing_execution_id == "execution-existing"
    assert raised.value.requested_execution_id == "execution-requested"
    assert read_phase5_scheduler_execution_ledger_artifact_if_exists("execution-requested", root=root) is None


def test_execution_executor_payload_does_not_leak_nested_or_sensitive_refs(tmp_path: Path) -> None:
    result = record_phase5_scheduler_plan_execution(
        _plan(
            cycle_id="cycle-sensitive",
            action="open_recovery_ticket",
            reason="input_bundle failed for release-manifest:phase5:20260521 sha256:abc123",
            blocking_reasons=[
                "runner_result failed",
                "release-manifest:phase5:20260521 failed",
                "digest sha256:abc123 failed",
            ],
        ),
        execution_id="execution-sensitive",
        idempotency_key="idempotency:execution-sensitive",
        created_at="2026-05-21T10:00:00Z",
        diagnostic_refs=["diagnostic-safe", "release-manifest:phase5:20260521"],
        root=tmp_path / "artifacts",
    )
    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

    assert '"plan_status":' not in rendered
    assert '"source_tick_status":' not in rendered
    assert '"status":' not in rendered
    assert '"error":' not in rendered
    assert "input_bundle" not in rendered
    assert "runner_result" not in rendered
    assert "release-manifest:" not in rendered
    assert "sha256:" not in rendered
    assert result.diagnostic_refs == ["diagnostic-safe"]
