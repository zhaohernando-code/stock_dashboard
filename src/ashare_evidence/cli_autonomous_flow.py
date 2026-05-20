from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_evidence.autonomous_flow_scheduler_plan import plan_phase5_scheduler_followup
from ashare_evidence.autonomous_flow_service import run_phase5_local_cycle_service
from ashare_evidence.autonomous_flow_tick import run_phase5_local_cycle_tick


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _jsonable_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result


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
    phase5_local_cycle_step.add_argument("--apply-closeout", action="store_true")
    phase5_local_cycle_step.add_argument("--require-publish-verification", action="store_true")
    phase5_local_cycle_step.add_argument(
        "--output",
        choices=("status", "plan", "full"),
        default="status",
        help=(
            "Choose the JSON shape: status emits the default tick envelope, "
            "plan emits a scheduler follow-up plan, full emits the service result for debugging."
        ),
    )


def handle_phase5_local_cycle_step_command(args: argparse.Namespace) -> int:
    if args.output == "status":
        tick_result = run_phase5_local_cycle_tick(
            cycle_id=args.cycle_id,
            gate_id=args.gate_id,
            recovery_ticket_id=args.recovery_ticket_id,
            projection_id=args.projection_id,
            finished_at=args.finished_at,
            apply_closeout=args.apply_closeout,
            require_publish_verification=args.require_publish_verification,
            root=args.artifact_root,
        )
        _print_json(tick_result.model_dump(mode="json"))
        return tick_result.exit_code

    if args.output == "plan":
        tick_result = run_phase5_local_cycle_tick(
            cycle_id=args.cycle_id,
            gate_id=args.gate_id,
            recovery_ticket_id=args.recovery_ticket_id,
            projection_id=args.projection_id,
            finished_at=args.finished_at,
            apply_closeout=args.apply_closeout,
            require_publish_verification=args.require_publish_verification,
            root=args.artifact_root,
        )
        plan = plan_phase5_scheduler_followup(tick_result)
        _print_json(plan.model_dump(mode="json"))
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
