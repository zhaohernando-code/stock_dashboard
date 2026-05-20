from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any

from ashare_evidence.autonomous_flow import Phase5SchedulerExecutionIdempotencyConflictError

_EXECUTION_CONFLICT_RECOMMENDED_NEXT_ACTION = (
    "reuse_existing_execution_id_or_retry_with_new_idempotency_key"
)


def handle_execution_output(
    args: Namespace,
    handlers: Any,
    *,
    run_tick_from_args: Callable[[Namespace, Any], Any],
    print_json: Callable[[Any], None],
) -> int:
    missing_arguments = _missing_arguments(
        (
            ("--execution-id", args.execution_id),
            ("--idempotency-key", args.idempotency_key),
            ("--created-at", args.created_at),
        )
    )
    if missing_arguments:
        print_json(
            {
                "status": "error",
                "command": "phase5-local-cycle-step",
                "error_type": "MissingRequiredExecutionArgument",
                "message": "--execution-id, --idempotency-key and --created-at are required for execution output.",
                "missing_arguments": missing_arguments,
            }
        )
        return 2

    tick_result = run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    try:
        execution_result = handlers.record_scheduler_plan_execution(
            plan,
            execution_id=args.execution_id,
            idempotency_key=args.idempotency_key,
            created_at=args.created_at,
            diagnostic_refs=[args.diagnostic_id] if args.diagnostic_id else [],
            root=args.artifact_root,
        )
    except Phase5SchedulerExecutionIdempotencyConflictError as exc:
        print_json(_execution_conflict_payload(exc))
        return 3
    print_json(execution_result.model_dump(mode="json"))
    return 0


def handle_full_output(
    args: Namespace,
    handlers: Any,
    *,
    print_json: Callable[[Any], None],
) -> int:
    try:
        result = handlers.run_service(
            cycle_id=args.cycle_id,
            gate_id=args.gate_id,
            recovery_ticket_id=args.recovery_ticket_id,
            projection_id=args.projection_id,
            finished_at=args.finished_at,
            apply_closeout=args.apply_closeout,
            require_publish_verification=args.require_publish_verification,
            root=args.artifact_root,
        )
    except Exception as exc:
        print_json(
            {
                "status": "error",
                "command": "phase5-local-cycle-step",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 1

    print_json(_jsonable_result(result))
    return 0


def _missing_arguments(arguments: tuple[tuple[str, Any], ...]) -> list[str]:
    return [argument for argument, value in arguments if not value]


def _execution_conflict_payload(exc: Phase5SchedulerExecutionIdempotencyConflictError) -> dict[str, str]:
    return {
        "status": "error",
        "command": "phase5-local-cycle-step",
        "error_type": type(exc).__name__,
        "message": str(exc),
        "idempotency_key": exc.idempotency_key,
        "existing_execution_id": exc.existing_execution_id,
        "requested_execution_id": exc.requested_execution_id,
        "recommended_next_action": _EXECUTION_CONFLICT_RECOMMENDED_NEXT_ACTION,
    }


def _jsonable_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result
