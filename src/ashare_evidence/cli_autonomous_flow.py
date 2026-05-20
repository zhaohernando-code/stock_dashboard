from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_evidence.autonomous_flow_service import run_phase5_local_cycle_service


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


def handle_phase5_local_cycle_step_command(args: argparse.Namespace) -> int:
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
