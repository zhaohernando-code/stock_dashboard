from __future__ import annotations

import json
from copy import deepcopy

import pytest

from ashare_evidence.autonomous_flow import (
    PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT,
    start_phase5_cycle,
)
from ashare_evidence.autonomous_flow_artifact_store import (
    read_phase5_cycle_ledger_artifact,
    read_phase5_scheduler_diagnostic_artifact,
)
from ashare_evidence.autonomous_flow_scheduler_executor import record_phase5_scheduler_plan_diagnostic
from tests.helpers_autonomous_flow_scheduler import _plan


def test_scheduler_plan_diagnostic_records_artifact_and_only_appends_cycle_event(tmp_path) -> None:
    before = start_phase5_cycle(
        cycle_id="cycle-20260520-001",
        trigger="scheduled",
        started_at="2026-05-20T09:00:00Z",
        status="running",
        next_action="continue_tracking",
        root=tmp_path,
    )
    plan = _plan(
        action="open_recovery_ticket",
        reason="cycle precondition failed",
        blocking_reasons=["cycle ledger cannot confirm closeout"],
    )

    result = record_phase5_scheduler_plan_diagnostic(
        plan,
        diagnostic_id="diagnostic-20260520-001",
        observed_at="2026-05-20T09:06:00Z",
        root=tmp_path,
    )
    stored_cycle = read_phase5_cycle_ledger_artifact(plan.cycle_id, root=tmp_path)
    stored_diagnostic = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id, root=tmp_path)

    assert result.execution_mode == "diagnostic_record"
    assert result.execution_status == "recorded"
    assert result.diagnostic_recorded is True
    assert result.cycle_event_recorded is True
    assert result.action == "open_recovery_ticket"
    assert result.severity == "error"
    assert stored_diagnostic.scheduler_action == "open_recovery_ticket"
    assert stored_diagnostic.failure_class == "execution-precondition-failed"
    assert stored_diagnostic.recommended_recovery_action == "open_recovery_ticket"
    assert stored_diagnostic.blocking_reasons == ["cycle ledger cannot confirm closeout"]
    assert stored_diagnostic.notes == "cycle precondition failed"
    assert PHASE5_SCHEDULER_DIAGNOSTIC_RECORDED_EVENT in stored_cycle.event_refs
    assert stored_cycle.status == before.status
    assert stored_cycle.next_action == before.next_action
    assert stored_cycle.finished_at == before.finished_at
    assert stored_cycle.recovery_ticket_refs == []


def test_scheduler_plan_diagnostic_records_when_cycle_is_missing(tmp_path) -> None:
    plan = _plan(
        cycle_id="missing-cycle",
        action="open_recovery_ticket",
        reason="cycle ledger artifact is missing",
        blocking_reasons=["cycle ledger missing"],
    )

    result = record_phase5_scheduler_plan_diagnostic(
        plan,
        diagnostic_id="diagnostic-missing-cycle",
        observed_at="2026-05-20T09:06:00Z",
        root=tmp_path,
    )
    stored = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id, root=tmp_path)

    assert result.diagnostic_recorded is True
    assert result.cycle_event_recorded is False
    assert stored.cycle_id == "missing-cycle"
    assert stored.scheduler_action == "open_recovery_ticket"
    assert stored.failure_class == "execution-precondition-failed"


@pytest.mark.parametrize(
    ("plan_status", "action", "expected_severity", "expected_recovery_action", "expected_failure_class"),
    [
        ("blocked", "continue_tracking", "blocked", "none", "blocked-plan"),
        ("ready", "block_cycle", "blocked", "block_cycle", "blocked-plan"),
        ("ready", "open_recovery_ticket", "error", "open_recovery_ticket", "execution-precondition-failed"),
        ("ready", "retry_failed_step", "error", "retry_with_backoff", "execution-precondition-failed"),
        ("ready", "rebuild_projection", "warning", "none", "execution-precondition-failed"),
        ("ready", "redesign", "warning", "none", "execution-precondition-failed"),
        ("ready", "continue_tracking", "info", "none", "none"),
        ("ready", "none", "info", "none", "none"),
    ],
)
def test_scheduler_plan_diagnostic_maps_action_contract(
    tmp_path,
    plan_status: str,
    action: str,
    expected_severity: str,
    expected_recovery_action: str,
    expected_failure_class: str,
) -> None:
    plan = _plan(plan_status=plan_status, action=action, reason=f"{action} diagnostic reason")

    result = record_phase5_scheduler_plan_diagnostic(
        plan,
        diagnostic_id=f"diagnostic-{plan_status}-{action}",
        observed_at="2026-05-20T09:06:00Z",
        root=tmp_path,
    )
    stored = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id, root=tmp_path)

    assert result.severity == expected_severity
    assert stored.severity == expected_severity
    assert stored.recommended_recovery_action == expected_recovery_action
    assert stored.failure_class == expected_failure_class


def test_scheduler_plan_diagnostic_payload_does_not_leak_nested_or_sensitive_details(tmp_path) -> None:
    plan = _plan(
        action="retry_failed_step",
        reason="Traceback from input_bundle release-manifest:phase5:20260520 sha256:abc123",
        blocking_reasons=[
            "runner_result included raw exception",
            "safe scheduler summary",
            "release-manifest:phase5:20260520",
            "sha256:abc123",
        ],
    )

    result = record_phase5_scheduler_plan_diagnostic(
        plan,
        diagnostic_id="diagnostic-redacted",
        observed_at="2026-05-20T09:06:00Z",
        root=tmp_path,
    )
    stored = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id, root=tmp_path)
    rendered = json.dumps(
        {
            "result": result.model_dump(mode="json"),
            "diagnostic": stored.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    assert result.reason == "[redacted sensitive diagnostic detail]"
    assert result.blocking_reasons == [
        "[redacted sensitive diagnostic detail]",
        "safe scheduler summary",
        "[redacted-release-manifest-ref]",
        "[redacted-digest]",
    ]
    assert stored.blocking_reasons == [
        "[redacted sensitive diagnostic detail]",
        "safe scheduler summary",
        "[redacted-release-manifest-ref]",
        "[redacted-digest]",
    ]
    assert stored.notes == "[redacted sensitive diagnostic detail]"
    for forbidden in (
        '"plan_status":',
        '"source_tick_status":',
        '"summary_status":',
        '"claim_ceiling":',
        "input_bundle",
        "runner_result",
        "release-manifest:",
        "sha256:",
        "Traceback",
    ):
        assert forbidden not in rendered


def test_scheduler_plan_diagnostic_does_not_modify_input_object(tmp_path) -> None:
    plan = _plan(
        action="retry_failed_step",
        reason="failed for release-manifest:phase5:20260520 sha256:abc123",
        blocking_reasons=["release-manifest:phase5:20260520 failed"],
    )
    before = deepcopy(plan.model_dump(mode="json"))

    record_phase5_scheduler_plan_diagnostic(
        plan,
        diagnostic_id="diagnostic-no-mutation",
        observed_at="2026-05-20T09:06:00Z",
        root=tmp_path,
    )

    assert plan.model_dump(mode="json") == before
