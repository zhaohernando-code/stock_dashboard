from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any


def handle_diagnostic_output(
    args: Namespace,
    handlers: Any,
    *,
    run_tick_from_args: Callable[[Namespace, Any], Any],
    print_json: Callable[[Any], None],
) -> int:
    missing_arguments = _missing_arguments(
        (
            ("--diagnostic-id", args.diagnostic_id),
            ("--observed-at", args.observed_at),
        )
    )
    if missing_arguments:
        print_json(
            {
                "status": "error",
                "command": "phase5-local-cycle-step",
                "error_type": "MissingRequiredDiagnosticArgument",
                "message": "--diagnostic-id and --observed-at are required for diagnostic output.",
                "missing_arguments": missing_arguments,
            }
        )
        return 2

    tick_result = run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    diagnostic_result = handlers.record_scheduler_plan_diagnostic(
        plan,
        diagnostic_id=args.diagnostic_id,
        observed_at=args.observed_at,
        root=args.artifact_root,
    )
    print_json(diagnostic_result.model_dump(mode="json"))
    return 0


def _missing_arguments(arguments: tuple[tuple[str, Any], ...]) -> list[str]:
    return [argument for argument, value in arguments if not value]
