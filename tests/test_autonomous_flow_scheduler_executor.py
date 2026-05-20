from __future__ import annotations

import json
from copy import deepcopy

import ashare_evidence.autonomous_flow_scheduler_executor as scheduler_executor
from ashare_evidence.autonomous_flow_scheduler_action_contract import get_phase5_scheduler_action_contract
from ashare_evidence.autonomous_flow_scheduler_executor import dry_run_phase5_scheduler_plan
from tests.helpers_autonomous_flow_scheduler import _plan


def test_ready_continue_tracking_plan_dry_run() -> None:
    result = dry_run_phase5_scheduler_plan(_plan())

    assert result.cycle_id == "cycle-20260520-001"
    assert result.execution_mode == "dry_run"
    assert result.execution_status == "planned"
    assert result.planned_action == "continue_tracking"
    assert result.would_execute is False
    assert result.planned_effects == ["keep_cycle_open_for_next_tick"]
    assert result.reason == "scheduler can continue with the next tick"
    assert result.blocking_reasons == []


def test_ready_rebuild_projection_plan_dry_run() -> None:
    result = dry_run_phase5_scheduler_plan(
        _plan(
            action="rebuild_projection",
            reason="projection manifest is stale",
            blocking_reasons=["projection staleness_status is stale"],
        )
    )

    assert result.execution_status == "planned"
    assert result.planned_action == "rebuild_projection"
    assert result.planned_effects == ["schedule_projection_rebuild"]
    assert result.blocking_reasons == ["projection staleness_status is stale"]


def test_ready_retry_failed_step_plan_dry_run() -> None:
    result = dry_run_phase5_scheduler_plan(
        _plan(action="retry_failed_step", reason="previous tick failed with a retryable error")
    )

    assert result.execution_status == "planned"
    assert result.planned_action == "retry_failed_step"
    assert result.planned_effects == ["schedule_retry"]


def test_ready_open_recovery_ticket_plan_dry_run() -> None:
    result = dry_run_phase5_scheduler_plan(
        _plan(action="open_recovery_ticket", reason="cycle ledger artifact is missing")
    )

    assert result.execution_status == "planned"
    assert result.planned_action == "open_recovery_ticket"
    assert result.planned_effects == ["prepare_recovery_ticket"]


def test_blocked_block_cycle_plan_dry_run() -> None:
    result = dry_run_phase5_scheduler_plan(
        _plan(
            plan_status="blocked",
            action="block_cycle",
            reason="contract violation blocks scheduler execution",
            blocking_reasons=["artifact cycle id mismatch"],
        )
    )

    assert result.execution_status == "blocked"
    assert result.planned_action == "block_cycle"
    assert result.planned_effects == ["mark_cycle_blocked"]
    assert result.blocking_reasons == ["artifact cycle id mismatch"]


def test_ready_redesign_plan_dry_run() -> None:
    result = dry_run_phase5_scheduler_plan(_plan(action="redesign", reason="design gate requested review"))

    assert result.execution_status == "planned"
    assert result.planned_action == "redesign"
    assert result.planned_effects == ["schedule_redesign_review"]


def test_none_plan_dry_run_is_no_op() -> None:
    result = dry_run_phase5_scheduler_plan(_plan(action="none", reason="no follow-up action required"))

    assert result.execution_status == "planned"
    assert result.planned_action == "none"
    assert result.planned_effects == ["no_op"]
    assert result.would_execute is False


def test_planned_effects_and_blocking_reasons_are_stably_deduped() -> None:
    result = dry_run_phase5_scheduler_plan(
        _plan(
            action="block_cycle",
            plan_status="blocked",
            blocking_reasons=[
                "artifact cycle id mismatch",
                "artifact cycle id mismatch",
                "contract registry failed",
            ],
        )
    )

    assert result.planned_effects == ["mark_cycle_blocked"]
    assert result.blocking_reasons == [
        "artifact cycle id mismatch",
        "contract registry failed",
    ]


def test_dry_run_planned_effects_come_from_action_contract() -> None:
    result = dry_run_phase5_scheduler_plan(_plan(action="redesign", reason="design gate requested review"))
    contract = get_phase5_scheduler_action_contract("redesign")

    assert result.planned_effects == list(contract.planned_effects)


def test_dry_run_uses_contract_lookup_for_planned_effects(monkeypatch) -> None:
    class StubContract:
        planned_effects = ("contract_effect", "contract_effect")

    monkeypatch.setattr(
        scheduler_executor,
        "get_phase5_scheduler_action_contract",
        lambda action: StubContract(),
    )

    result = dry_run_phase5_scheduler_plan(_plan(action="retry_failed_step"))

    assert result.planned_effects == ["contract_effect"]


def test_payload_does_not_leak_nested_plan_tick_payload_or_sensitive_refs() -> None:
    result = dry_run_phase5_scheduler_plan(
        _plan(
            action="retry_failed_step",
            reason="failed for release-manifest:phase5:20260520 sha256:abc123",
            blocking_reasons=[
                "release-manifest:phase5:20260520 failed",
                "digest sha256:abc123 failed",
            ],
        )
    )

    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False)

    assert '"plan_status":' not in rendered
    assert '"source_tick_status":' not in rendered
    assert '"summary_status":' not in rendered
    assert '"claim_ceiling":' not in rendered
    assert '"status":' not in rendered
    assert '"error":' not in rendered
    assert "release-manifest:" not in rendered
    assert "sha256:" not in rendered
    assert "Traceback" not in rendered
    assert "[redacted-release-manifest-ref]" in rendered
    assert "[redacted-digest]" in rendered


def test_dry_run_does_not_modify_input_object() -> None:
    plan = _plan(
        action="retry_failed_step",
        reason="failed for release-manifest:phase5:20260520 sha256:abc123",
        blocking_reasons=[
            "release-manifest:phase5:20260520 failed",
            "digest sha256:abc123 failed",
        ],
    )
    before = deepcopy(plan.model_dump(mode="json"))

    dry_run_phase5_scheduler_plan(plan)

    assert plan.model_dump(mode="json") == before
