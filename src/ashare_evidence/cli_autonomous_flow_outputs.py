from __future__ import annotations

from argparse import Namespace

from ashare_evidence.cli_autonomous_flow_output_context import (
    Phase5LocalCycleStepHandlers,
    print_json,
    run_tick_from_args,
)
from ashare_evidence.cli_autonomous_flow_output_dispatch import handle_secondary_phase5_local_cycle_step_output


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

    return handle_secondary_phase5_local_cycle_step_output(args, handlers=handlers, print_json=print_json)
