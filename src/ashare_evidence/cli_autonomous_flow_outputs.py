from __future__ import annotations

import json
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ashare_evidence.cli_autonomous_flow_action_outputs import (
    handle_action_output,
    handle_action_route_apply_output,
    handle_action_route_auto_apply_output,
    handle_action_route_output,
    handle_action_route_preflight_output,
)
from ashare_evidence.cli_autonomous_flow_diagnostic_outputs import handle_diagnostic_output
from ashare_evidence.cli_autonomous_flow_execution_outputs import (
    handle_execution_output,
    handle_full_output,
)


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

    if args.output == "action":
        return handle_action_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    if args.output == "action-route":
        return handle_action_route_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    if args.output == "action-route-apply":
        return handle_action_route_apply_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    if args.output == "action-route-auto-apply":
        return handle_action_route_auto_apply_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    if args.output == "action-route-preflight":
        return handle_action_route_preflight_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    if args.output == "diagnostic":
        return handle_diagnostic_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    if args.output == "execution":
        return handle_execution_output(
            args,
            handlers,
            run_tick_from_args=_run_tick_from_args,
            print_json=_print_json,
        )

    return handle_full_output(args, handlers, print_json=_print_json)


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


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
