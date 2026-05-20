from __future__ import annotations

import json
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Phase5LocalCycleStepHandlers:
    run_tick: Callable[..., Any]
    plan_followup: Callable[..., Any]
    dry_run_scheduler_plan: Callable[..., Any]
    record_scheduler_plan_diagnostic: Callable[..., Any]
    record_scheduler_plan_execution: Callable[..., Any]
    run_service: Callable[..., Any]


def handle_phase5_local_cycle_step_output(
    args: Namespace,
    *,
    handlers: Phase5LocalCycleStepHandlers,
) -> int:
    if args.output == "status":
        tick_result = _run_tick_from_args(args, handlers)
        _print_json(tick_result.model_dump(mode="json"))
        return tick_result.exit_code

    if args.output == "plan":
        tick_result = _run_tick_from_args(args, handlers)
        plan = handlers.plan_followup(tick_result)
        _print_json(plan.model_dump(mode="json"))
        return 0

    if args.output == "dry-run":
        tick_result = _run_tick_from_args(args, handlers)
        plan = handlers.plan_followup(tick_result)
        dry_run_result = handlers.dry_run_scheduler_plan(plan)
        _print_json(dry_run_result.model_dump(mode="json"))
        return 0

    if args.output == "diagnostic":
        return _handle_diagnostic_output(args, handlers)

    if args.output == "execution":
        return _handle_execution_output(args, handlers)

    return _handle_full_output(args, handlers)


def _handle_diagnostic_output(args: Namespace, handlers: Phase5LocalCycleStepHandlers) -> int:
    missing_arguments = _missing_arguments(
        (
            ("--diagnostic-id", args.diagnostic_id),
            ("--observed-at", args.observed_at),
        )
    )
    if missing_arguments:
        _print_json(
            {
                "status": "error",
                "command": "phase5-local-cycle-step",
                "error_type": "MissingRequiredDiagnosticArgument",
                "message": "--diagnostic-id and --observed-at are required for diagnostic output.",
                "missing_arguments": missing_arguments,
            }
        )
        return 2

    tick_result = _run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    diagnostic_result = handlers.record_scheduler_plan_diagnostic(
        plan,
        diagnostic_id=args.diagnostic_id,
        observed_at=args.observed_at,
        root=args.artifact_root,
    )
    _print_json(diagnostic_result.model_dump(mode="json"))
    return 0


def _handle_execution_output(args: Namespace, handlers: Phase5LocalCycleStepHandlers) -> int:
    missing_arguments = _missing_arguments(
        (
            ("--execution-id", args.execution_id),
            ("--idempotency-key", args.idempotency_key),
            ("--created-at", args.created_at),
        )
    )
    if missing_arguments:
        _print_json(
            {
                "status": "error",
                "command": "phase5-local-cycle-step",
                "error_type": "MissingRequiredExecutionArgument",
                "message": "--execution-id, --idempotency-key and --created-at are required for execution output.",
                "missing_arguments": missing_arguments,
            }
        )
        return 2

    tick_result = _run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    execution_result = handlers.record_scheduler_plan_execution(
        plan,
        execution_id=args.execution_id,
        idempotency_key=args.idempotency_key,
        created_at=args.created_at,
        diagnostic_refs=[args.diagnostic_id] if args.diagnostic_id else [],
        root=args.artifact_root,
    )
    _print_json(execution_result.model_dump(mode="json"))
    return 0


def _handle_full_output(args: Namespace, handlers: Phase5LocalCycleStepHandlers) -> int:
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
        _print_json(
            {
                "status": "error",
                "command": "phase5-local-cycle-step",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 1

    _print_json(_jsonable_result(result))
    return 0


def _run_tick_from_args(args: Namespace, handlers: Phase5LocalCycleStepHandlers) -> Any:
    return handlers.run_tick(
        cycle_id=args.cycle_id,
        gate_id=args.gate_id,
        recovery_ticket_id=args.recovery_ticket_id,
        projection_id=args.projection_id,
        finished_at=args.finished_at,
        apply_closeout=args.apply_closeout,
        require_publish_verification=args.require_publish_verification,
        root=args.artifact_root,
    )


def _missing_arguments(arguments: tuple[tuple[str, Any], ...]) -> list[str]:
    return [argument for argument, value in arguments if not value]


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _jsonable_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result
