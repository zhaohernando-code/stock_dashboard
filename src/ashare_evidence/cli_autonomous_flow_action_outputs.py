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


def handle_action_route_preflight_output(
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
    preflight_result = handlers.preflight_scheduler_action_route(
        route_result,
        _provided_action_route_argument_names(args),
    )
    print_json(preflight_result.model_dump(mode="json"))
    return _action_exit_code(preflight_result)


def handle_action_route_apply_output(
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
    apply_result = handlers.apply_scheduler_action_route(
        plan,
        route_result,
        diagnostic_id=args.diagnostic_id,
        observed_at=args.observed_at,
        execution_id=args.execution_id,
        idempotency_key=args.idempotency_key,
        created_at=args.created_at,
        diagnostic_refs=[args.diagnostic_id] if args.diagnostic_id else [],
        root=args.artifact_root,
    )
    print_json(apply_result.model_dump(mode="json"))
    return _action_exit_code(apply_result)


def handle_action_route_auto_apply_output(
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
    apply_result = handlers.bind_and_apply_scheduler_action_route(
        plan,
        route_result,
        attempt_id=args.attempt_id,
        issued_at=args.issued_at,
        root=args.artifact_root,
    )
    print_json(apply_result.model_dump(mode="json"))
    return _action_exit_code(apply_result)


def _action_exit_code(action_result: Any) -> int:
    execution_status = getattr(action_result, "execution_status", None)
    if execution_status is None and isinstance(getattr(action_result, "payload", None), dict):
        execution_status = action_result.payload.get("execution_status")
    if execution_status is None:
        execution_status = getattr(action_result, "status", None)
    if execution_status is None and isinstance(getattr(action_result, "payload", None), dict):
        execution_status = action_result.payload.get("status")
    if execution_status == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0


def _provided_action_route_argument_names(args: Namespace) -> tuple[str, ...]:
    arguments = (
        ("diagnostic_id", args.diagnostic_id),
        ("observed_at", args.observed_at),
        ("execution_id", args.execution_id),
        ("idempotency_key", args.idempotency_key),
        ("created_at", args.created_at),
    )
    return tuple(name for name, value in arguments if value)
