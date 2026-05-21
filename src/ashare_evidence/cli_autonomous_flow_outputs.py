from __future__ import annotations

from argparse import Namespace

from ashare_evidence.cli_autonomous_flow_action_outputs import (
    handle_action_output,
    handle_action_route_apply_output,
    handle_action_route_auto_apply_output,
    handle_action_route_output,
    handle_action_route_preflight_output,
)
from ashare_evidence.cli_autonomous_flow_attempt_outputs import (
    handle_attempt_context_output,
    handle_attempt_route_auto_apply_output,
)
from ashare_evidence.cli_autonomous_flow_diagnostic_outputs import handle_diagnostic_output
from ashare_evidence.cli_autonomous_flow_execution_outputs import (
    handle_execution_output,
    handle_full_output,
)
from ashare_evidence.cli_autonomous_flow_output_context import (
    Phase5LocalCycleStepHandlers,
    print_json,
    run_tick_from_args,
)


def handle_phase5_local_cycle_step_output(
    args: Namespace,
    *,
    handlers: Phase5LocalCycleStepHandlers,
) -> int:
    if args.output == "status":
        tick_result = run_tick_from_args(args, handlers)
        print_json(tick_result.model_dump(mode="json"))
        return tick_result.exit_code

    if args.output == "plan":
        tick_result = run_tick_from_args(args, handlers)
        plan = handlers.plan_followup(tick_result)
        print_json(plan.model_dump(mode="json"))
        return 0

    if args.output == "dry-run":
        tick_result = run_tick_from_args(args, handlers)
        plan = handlers.plan_followup(tick_result)
        dry_run_result = handlers.dry_run_scheduler_plan(plan)
        print_json(dry_run_result.model_dump(mode="json"))
        return 0

    if args.output == "action":
        return handle_action_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "action-route":
        return handle_action_route_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "action-route-apply":
        return handle_action_route_apply_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "action-route-auto-apply":
        return handle_action_route_auto_apply_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "attempt-route-auto-apply":
        return handle_attempt_route_auto_apply_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "action-route-preflight":
        return handle_action_route_preflight_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "attempt-context":
        return handle_attempt_context_output(args, print_json=print_json)

    if args.output == "diagnostic":
        return handle_diagnostic_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    if args.output == "execution":
        return handle_execution_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )

    return handle_full_output(args, handlers, print_json=print_json)
