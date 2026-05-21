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
    execute_scheduler_noop_action: Callable[..., Any]
    route_scheduler_action_result: Callable[..., Any]
    preflight_scheduler_action_route: Callable[..., Any]
    apply_scheduler_action_route: Callable[..., Any]
    bind_and_apply_scheduler_action_route: Callable[..., Any]
    build_attempt_context_and_apply_scheduler_action_route: Callable[..., Any]
    run_service: Callable[..., Any]


def run_tick_from_args(args: Namespace, handlers: Phase5LocalCycleStepHandlers) -> Any:
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


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
