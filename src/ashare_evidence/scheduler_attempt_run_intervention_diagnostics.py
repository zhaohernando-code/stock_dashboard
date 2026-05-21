from __future__ import annotations

import hashlib
import re

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction
from ashare_evidence.scheduler_attempt_run_intervention_plan import Phase5SchedulerAttemptRunInterventionPlan


def stable_phase5_scheduler_attempt_run_intervention_diagnostic_id(
    plan: Phase5SchedulerAttemptRunInterventionPlan,
) -> str | None:
    if not plan.cycle_id or not plan.source_latest_run_id:
        return None
    raw = "|".join((plan.cycle_id, plan.action, plan.source_latest_run_id, plan.reason_code))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(("diagnostic", _slug(plan.cycle_id), _slug(plan.action), _slug(plan.source_latest_run_id), digest))


def phase5_scheduler_attempt_run_intervention_severity(action: Phase5SchedulerAction) -> str:
    if action == "block_cycle":
        return "blocked"
    if action in {"open_recovery_ticket", "retry_failed_step"}:
        return "error"
    return "warning"


def phase5_scheduler_attempt_run_intervention_failure_class(action: Phase5SchedulerAction) -> str:
    if action == "block_cycle":
        return "blocked-plan"
    return "execution-precondition-failed"


def phase5_scheduler_attempt_run_intervention_recovery_action(action: Phase5SchedulerAction) -> str:
    if action == "open_recovery_ticket":
        return "open_recovery_ticket"
    if action == "retry_failed_step":
        return "retry_with_backoff"
    if action == "block_cycle":
        return "block_cycle"
    return "none"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"
