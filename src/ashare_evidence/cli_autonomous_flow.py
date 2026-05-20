from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_evidence.autonomous_flow_scheduler_executor import (
    dry_run_phase5_scheduler_plan,
    record_phase5_scheduler_plan_diagnostic,
)
from ashare_evidence.autonomous_flow_scheduler_plan import plan_phase5_scheduler_followup
from ashare_evidence.autonomous_flow_service import run_phase5_local_cycle_service
from ashare_evidence.autonomous_flow_tick import run_phase5_local_cycle_tick


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _jsonable_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result


def _run_tick_from_args(args: argparse.Namespace) -> Any:
    return run_phase5_local_cycle_tick(
        cycle_id=args.cycle_id,
        gate_id=args.gate_id,
        recovery_ticket_id=args.recovery_ticket_id,
        projection_id=args.projection_id,
        finished_at=args.finished_at,
        apply_closeout=args.apply_closeout,
        require_publish_verification=args.require_publish_verification,
        root=args.artifact_root,
    )


def add_autonomous_flow_parsers(subparsers: argparse._SubParsersAction) -> None:
    phase5_local_cycle_step = subparsers.add_parser(
        "phase5-local-cycle-step",
        help="Run one local Phase 5 autonomous-flow cycle service step without scheduler side effects.",
    )
    phase5_local_cycle_step.add_argument("--cycle-id", required=True)
    phase5_local_cycle_step.add_argument("--artifact-root", type=Path, default=None)
    phase5_local_cycle_step.add_argument("--gate-id", default=None)
    phase5_local_cycle_step.add_argument("--recovery-ticket-id", default=None)
    phase5_local_cycle_step.add_argument("--projection-id", default=None)
    phase5_local_cycle_step.add_argument("--finished-at", default=None)
    phase5_local_cycle_step.add_argument("--diagnostic-id", default=None)
    phase5_local_cycle_step.add_argument("--observed-at", default=None)
    phase5_local_cycle_step.add_argument("--apply-closeout", action="store_true")
    phase5_local_cycle_step.add_argument("--require-publish-verification", action="store_true")
    phase5_local_cycle_step.add_argument(
        "--output",
        choices=("status", "plan", "dry-run", "diagnostic", "full"),
        default="status",
        help=(
            "Choose the JSON shape: status emits the default tick envelope, "
            "plan emits a scheduler follow-up plan, dry-run emits a no-side-effect scheduler "
            "execution intent, diagnostic records scheduler diagnostics, full emits the service "
            "result for debugging."
        ),
    )


def handle_phase5_local_cycle_step_command(args: argparse.Namespace) -> int:
    if args.output == "status":
        tick_result = _run_tick_from_args(args)
        _print_json(tick_result.model_dump(mode="json"))
        return tick_result.exit_code

    if args.output == "plan":
        tick_result = _run_tick_from_args(args)
        plan = plan_phase5_scheduler_followup(tick_result)
        _print_json(plan.model_dump(mode="json"))
        return 0

    if args.output == "dry-run":
        tick_result = _run_tick_from_args(args)
        plan = plan_phase5_scheduler_followup(tick_result)
        dry_run_result = dry_run_phase5_scheduler_plan(plan)
        _print_json(dry_run_result.model_dump(mode="json"))
        return 0

    if args.output == "diagnostic":
        missing_arguments = [
            argument
            for argument, value in (
                ("--diagnostic-id", args.diagnostic_id),
                ("--observed-at", args.observed_at),
            )
            if not value
        ]
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

        tick_result = _run_tick_from_args(args)
        plan = plan_phase5_scheduler_followup(tick_result)
        diagnostic_result = record_phase5_scheduler_plan_diagnostic(
            plan,
            diagnostic_id=args.diagnostic_id,
            observed_at=args.observed_at,
            root=args.artifact_root,
        )
        _print_json(diagnostic_result.model_dump(mode="json"))
        return 0

    try:
        result = run_phase5_local_cycle_service(
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
