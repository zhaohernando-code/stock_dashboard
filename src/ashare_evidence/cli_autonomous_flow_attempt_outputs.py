from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any

from ashare_evidence.autonomous_flow_scheduler_attempt import build_phase5_scheduler_attempt_context

_ACTION_BLOCKED_EXIT_CODE = 4


def handle_attempt_context_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    result = build_phase5_scheduler_attempt_context(
        cycle_id=args.cycle_id,
        issued_at=args.issued_at,
        runner_id=args.runner_id,
    )
    print_json(result.model_dump(mode="json"))
    if result.status == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0


def handle_attempt_route_auto_apply_output(
    args: Namespace,
    handlers: Any,
    *,
    run_tick_from_args: Callable[[Namespace, Any], Any],
    print_json: Callable[[Any], None],
) -> int:
    tick_result = run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    action_result = handlers.execute_scheduler_noop_action(plan)
    route_result = handlers.route_scheduler_action_result(action_result)
    apply_result = handlers.build_attempt_context_and_apply_scheduler_action_route(
        plan,
        route_result,
        issued_at=args.issued_at,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    print_json(apply_result.model_dump(mode="json"))
    return _attempt_route_apply_exit_code(apply_result)


def _attempt_route_apply_exit_code(result: Any) -> int:
    if getattr(result, "execution_status", None) == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    if isinstance(getattr(result, "payload", None), dict) and result.payload.get("execution_status") == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0
