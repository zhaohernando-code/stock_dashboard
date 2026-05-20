from __future__ import annotations

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerFollowupPlan


def _plan(
    *,
    cycle_id: str = "cycle-20260520-001",
    plan_status: str = "ready",
    action: str = "continue_tracking",
    reason: str = "scheduler can continue with the next tick",
    blocking_reasons: list[str] | None = None,
) -> Phase5SchedulerFollowupPlan:
    return Phase5SchedulerFollowupPlan(
        cycle_id=cycle_id,
        plan_status=plan_status,
        action=action,
        reason=reason,
        source_tick_status="ok",
        summary_status="completed" if plan_status == "ready" else "blocked",
        claim_ceiling="paper_tracking_candidate",
        blocking_reasons=blocking_reasons or [],
    )
