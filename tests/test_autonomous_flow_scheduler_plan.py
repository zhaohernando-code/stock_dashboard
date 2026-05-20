from __future__ import annotations

import json
from copy import deepcopy

from ashare_evidence.autonomous_flow_scheduler_plan import plan_phase5_scheduler_followup
from ashare_evidence.autonomous_flow_status import Phase5LocalCycleStatusProjection
from ashare_evidence.autonomous_flow_tick import (
    Phase5LocalCycleTickError,
    Phase5LocalCycleTickResult,
)


def _status_projection(
    *,
    cycle_id: str = "cycle-20260520-001",
    next_action: str = "continue_tracking",
    summary_status: str = "completed",
    claim_ceiling: str = "paper_tracking_candidate",
    decision_reason: str = "all planner inputs are fresh and unblocked",
    missing_refs: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
) -> Phase5LocalCycleStatusProjection:
    return Phase5LocalCycleStatusProjection(
        cycle_id=cycle_id,
        cycle_status="running",
        decision_status="completed" if summary_status == "completed" else summary_status,
        next_action=next_action,
        claim_ceiling=claim_ceiling,
        decision_reason=decision_reason,
        missing_refs=missing_refs or [],
        blocking_reasons=blocking_reasons or [],
        source_refs=[cycle_id],
        closeout_applied=False,
        finished_at=None,
        publish_verification_status="not_required",
        staleness_status="fresh",
        summary_status=summary_status,
    )


def _ok_tick(
    *,
    cycle_id: str = "cycle-20260520-001",
    next_action: str = "continue_tracking",
    summary_status: str = "completed",
    claim_ceiling: str = "paper_tracking_candidate",
    decision_reason: str = "all planner inputs are fresh and unblocked",
    missing_refs: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
) -> Phase5LocalCycleTickResult:
    status = _status_projection(
        cycle_id=cycle_id,
        next_action=next_action,
        summary_status=summary_status,
        claim_ceiling=claim_ceiling,
        decision_reason=decision_reason,
        missing_refs=missing_refs,
        blocking_reasons=blocking_reasons,
    )
    return Phase5LocalCycleTickResult(
        cycle_id=cycle_id,
        tick_status="ok",
        exit_code=0,
        status=status,
        error=None,
        recommended_next_action=status.next_action,
        summary_status=status.summary_status,
    )


def _error_tick(
    *,
    cycle_id: str = "cycle-20260520-001",
    failure_class: str,
    recovery_action: str,
    summary_status: str,
    recommended_next_action: str,
    message: str = "raw error release-manifest:phase5:20260520 sha256:abc123",
) -> Phase5LocalCycleTickResult:
    return Phase5LocalCycleTickResult(
        cycle_id=cycle_id,
        tick_status="error",
        exit_code=1,
        status=None,
        error=Phase5LocalCycleTickError(
            error_type="RuntimeError",
            message=message,
            failure_class=failure_class,
            recommended_recovery_action=recovery_action,
        ),
        recommended_next_action=recommended_next_action,
        summary_status=summary_status,
    )


def test_completed_continue_tracking_tick_maps_to_ready_continue_tracking() -> None:
    plan = plan_phase5_scheduler_followup(_ok_tick())

    assert plan.cycle_id == "cycle-20260520-001"
    assert plan.plan_status == "ready"
    assert plan.action == "continue_tracking"
    assert plan.source_tick_status == "ok"
    assert plan.summary_status == "completed"
    assert plan.claim_ceiling == "paper_tracking_candidate"
    assert plan.blocking_reasons == []


def test_degraded_rebuild_projection_tick_maps_to_ready_rebuild_projection() -> None:
    plan = plan_phase5_scheduler_followup(
        _ok_tick(
            next_action="rebuild_projection",
            summary_status="degraded",
            decision_reason="frontend projection manifest is stale",
            blocking_reasons=["projection staleness_status is stale"],
        )
    )

    assert plan.plan_status == "ready"
    assert plan.action == "rebuild_projection"
    assert plan.summary_status == "degraded"
    assert plan.blocking_reasons == ["projection staleness_status is stale"]


def test_degraded_retry_failed_step_tick_maps_to_ready_retry_failed_step() -> None:
    plan = plan_phase5_scheduler_followup(
        _ok_tick(
            next_action="retry_failed_step",
            summary_status="degraded",
            decision_reason="publish verification is required but missing",
            blocking_reasons=["runtime publish verification ref is missing"],
        )
    )

    assert plan.plan_status == "ready"
    assert plan.action == "retry_failed_step"
    assert plan.reason == "publish verification is required but missing"


def test_degraded_redesign_tick_maps_to_ready_redesign() -> None:
    plan = plan_phase5_scheduler_followup(
        _ok_tick(
            next_action="redesign",
            summary_status="degraded",
            claim_ceiling="research_observation",
            decision_reason="gate requested redesign",
        )
    )

    assert plan.plan_status == "ready"
    assert plan.action == "redesign"
    assert plan.claim_ceiling == "research_observation"


def test_blocked_ok_tick_maps_to_block_cycle() -> None:
    plan = plan_phase5_scheduler_followup(
        _ok_tick(
            next_action="blocked",
            summary_status="blocked",
            claim_ceiling="blocked",
            decision_reason="gate readout blocked the cycle",
            blocking_reasons=["contract registry check failed"],
        )
    )

    assert plan.plan_status == "blocked"
    assert plan.action == "block_cycle"
    assert plan.claim_ceiling == "blocked"
    assert plan.blocking_reasons == ["contract registry check failed"]


def test_missing_cycle_error_maps_to_open_recovery_ticket() -> None:
    plan = plan_phase5_scheduler_followup(
        _error_tick(
            failure_class="artifact-missing",
            recovery_action="open_recovery_ticket",
            summary_status="degraded",
            recommended_next_action="retry_failed_step",
        )
    )

    assert plan.plan_status == "ready"
    assert plan.action == "open_recovery_ticket"
    assert plan.source_tick_status == "error"
    assert plan.summary_status == "degraded"
    assert plan.claim_ceiling is None
    assert plan.blocking_reasons == ["tick failure_class is artifact-missing"]


def test_unexpected_error_retry_with_backoff_maps_to_retry_failed_step() -> None:
    plan = plan_phase5_scheduler_followup(
        _error_tick(
            failure_class="unexpected-error",
            recovery_action="retry_with_backoff",
            summary_status="degraded",
            recommended_next_action="retry_failed_step",
        )
    )

    assert plan.plan_status == "ready"
    assert plan.action == "retry_failed_step"
    assert plan.reason == (
        "tick failed with failure_class=unexpected-error; "
        "recommended_recovery_action=retry_with_backoff"
    )


def test_contract_violation_block_cycle_maps_to_blocked() -> None:
    plan = plan_phase5_scheduler_followup(
        _error_tick(
            failure_class="contract-violation",
            recovery_action="block_cycle",
            summary_status="blocked",
            recommended_next_action="blocked",
        )
    )

    assert plan.plan_status == "blocked"
    assert plan.action == "block_cycle"
    assert plan.blocking_reasons == ["tick failure_class is contract-violation"]


def test_payload_does_not_leak_nested_status_error_or_sensitive_refs() -> None:
    plan = plan_phase5_scheduler_followup(
        _error_tick(
            failure_class="unexpected-error",
            recovery_action="retry_with_backoff",
            summary_status="degraded",
            recommended_next_action="retry_failed_step",
        )
    )

    payload = plan.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False)

    assert '"status":' not in rendered
    assert '"error":' not in rendered
    assert "release-manifest:" not in rendered
    assert "sha256:" not in rendered
    assert "digest" not in rendered
    assert "Traceback" not in rendered


def test_ok_payload_sanitizes_sensitive_refs_from_reason_and_blockers() -> None:
    plan = plan_phase5_scheduler_followup(
        _ok_tick(
            next_action="retry_failed_step",
            summary_status="degraded",
            decision_reason="publish failed for release-manifest:phase5:20260520 sha256:abc123",
            blocking_reasons=[
                "release-manifest:phase5:20260520 failed",
                "digest sha256:abc123 failed",
            ],
        )
    )
    rendered = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)

    assert "release-manifest:" not in rendered
    assert "sha256:" not in rendered
    assert "[redacted-release-manifest-ref]" in rendered
    assert "[redacted-digest]" in rendered


def test_blocking_reasons_are_stably_deduped_and_missing_refs_are_generic() -> None:
    plan = plan_phase5_scheduler_followup(
        _ok_tick(
            next_action="rebuild_projection",
            summary_status="degraded",
            missing_refs=[
                "frontend_projection_manifest:<missing>",
                "frontend_projection_manifest:<missing>",
            ],
            blocking_reasons=[
                "projection staleness_status is stale",
                "projection staleness_status is stale",
            ],
        )
    )

    assert plan.blocking_reasons == [
        "projection staleness_status is stale",
        "required input artifact reference is missing",
    ]


def test_planner_does_not_modify_input_object() -> None:
    tick = _ok_tick(
        next_action="rebuild_projection",
        summary_status="degraded",
        missing_refs=["frontend_projection_manifest:<missing>"],
        blocking_reasons=["projection staleness_status is stale"],
    )
    before = deepcopy(tick.model_dump(mode="json"))

    plan_phase5_scheduler_followup(tick)

    assert tick.model_dump(mode="json") == before
