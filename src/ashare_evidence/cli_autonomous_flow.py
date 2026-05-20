from __future__ import annotations

import argparse
from pathlib import Path

from ashare_evidence.autonomous_flow_scheduler_action_executor import execute_phase5_scheduler_noop_action
from ashare_evidence.autonomous_flow_scheduler_action_router import route_phase5_scheduler_action_result
from ashare_evidence.autonomous_flow_scheduler_executor import (
    dry_run_phase5_scheduler_plan,
    record_phase5_scheduler_plan_diagnostic,
    record_phase5_scheduler_plan_execution,
)
from ashare_evidence.autonomous_flow_scheduler_plan import plan_phase5_scheduler_followup
from ashare_evidence.autonomous_flow_service import run_phase5_local_cycle_service
from ashare_evidence.autonomous_flow_tick import run_phase5_local_cycle_tick
from ashare_evidence.cli_autonomous_flow_outputs import (
    Phase5LocalCycleStepHandlers,
    handle_phase5_local_cycle_step_output,
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
    phase5_local_cycle_step.add_argument("--execution-id", default=None)
    phase5_local_cycle_step.add_argument("--idempotency-key", default=None)
    phase5_local_cycle_step.add_argument("--created-at", default=None)
    phase5_local_cycle_step.add_argument("--apply-closeout", action="store_true")
    phase5_local_cycle_step.add_argument("--require-publish-verification", action="store_true")
    phase5_local_cycle_step.add_argument(
        "--output",
        choices=("status", "plan", "dry-run", "diagnostic", "execution", "action", "action-route", "full"),
        default="status",
        help=(
            "Choose the JSON shape: status emits the default tick envelope, "
            "plan emits a scheduler follow-up plan, dry-run emits a no-side-effect scheduler "
            "execution intent, diagnostic records scheduler diagnostics, execution records a safe "
            "scheduler execution ledger, action executes an observe-only contract action, "
            "action-route routes that observe-only action result, full emits the service result for debugging."
        ),
    )


def handle_phase5_local_cycle_step_command(args: argparse.Namespace) -> int:
    return handle_phase5_local_cycle_step_output(
        args,
        handlers=Phase5LocalCycleStepHandlers(
            run_tick=run_phase5_local_cycle_tick,
            plan_followup=plan_phase5_scheduler_followup,
            dry_run_scheduler_plan=dry_run_phase5_scheduler_plan,
            record_scheduler_plan_diagnostic=record_phase5_scheduler_plan_diagnostic,
            record_scheduler_plan_execution=record_phase5_scheduler_plan_execution,
            execute_scheduler_noop_action=execute_phase5_scheduler_noop_action,
            route_scheduler_action_result=route_phase5_scheduler_action_result,
            run_service=run_phase5_local_cycle_service,
        ),
    )
