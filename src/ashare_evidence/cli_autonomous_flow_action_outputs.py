from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any

_ACTION_BLOCKED_EXIT_CODE = 4


def handle_action_output(
    args: Namespace,
    handlers: Any,
    *,
    run_tick_from_args: Callable[[Namespace, Any], Any],
    print_json: Callable[[Any], None],
) -> int:
    tick_result = run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    action_result = handlers.execute_scheduler_noop_action(plan)
    print_json(action_result.model_dump(mode="json"))
    return _action_exit_code(action_result)


def handle_action_route_output(
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
    print_json(route_result.model_dump(mode="json"))
    return 0


def _action_exit_code(action_result: Any) -> int:
    execution_status = getattr(action_result, "execution_status", None)
    if execution_status is None and isinstance(getattr(action_result, "payload", None), dict):
        execution_status = action_result.payload.get("execution_status")
    if execution_status == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0
