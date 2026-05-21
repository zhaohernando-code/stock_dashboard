from __future__ import annotations

import argparse
from pathlib import Path

from ashare_evidence.autonomous_flow_scheduler_action_executor import execute_phase5_scheduler_noop_action
from ashare_evidence.autonomous_flow_scheduler_action_route_attempt_auto_apply import (
    build_attempt_context_and_apply_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_action_route_auto_apply import (
    bind_and_apply_phase5_scheduler_action_route,
)
from ashare_evidence.autonomous_flow_scheduler_action_route_executor import apply_phase5_scheduler_action_route
from ashare_evidence.autonomous_flow_scheduler_action_router import (
    preflight_phase5_scheduler_action_route,
    route_phase5_scheduler_action_result,
)
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
    phase5_local_cycle_step.add_argument("--attempt-id", default=None)
    phase5_local_cycle_step.add_argument("--issued-at", default=None)
    phase5_local_cycle_step.add_argument("--runner-id", default=None)
    phase5_local_cycle_step.add_argument("--record-attempt-run", action="store_true")
    phase5_local_cycle_step.add_argument("--attempt-run-id", default=None)
    phase5_local_cycle_step.add_argument("--record-intervention-run", action="store_true")
    phase5_local_cycle_step.add_argument("--intervention-run-id", default=None)
    phase5_local_cycle_step.add_argument("--record-auto-progress-run", action="store_true")
    phase5_local_cycle_step.add_argument("--auto-progress-run-id", default=None)
    phase5_local_cycle_step.add_argument("--apply-closeout", action="store_true")
    phase5_local_cycle_step.add_argument("--require-publish-verification", action="store_true")
    phase5_local_cycle_step.add_argument(
        "--output",
        choices=(
            "status",
            "plan",
            "dry-run",
            "diagnostic",
            "execution",
            "action",
            "action-route",
            "action-route-apply",
            "action-route-auto-apply",
            "attempt-route-auto-apply",
            "attempt-run-auto-progress-apply",
            "attempt-run-auto-progress-plan",
            "attempt-run-auto-progress-readout",
            "attempt-run-followup-decision",
            "attempt-run-intervention-apply",
            "attempt-run-intervention-followup-decision",
            "attempt-run-intervention-plan",
            "attempt-run-intervention-readout",
            "attempt-run-recovery-followup-apply",
            "attempt-run-recovery-followup-intent",
            "attempt-run-recovery-ticket-apply",
            "attempt-run-recovery-ticket-intent",
            "attempt-run-readout",
            "action-route-preflight",
            "attempt-context",
            "full",
        ),
        default="status",
        help=(
            "Choose the JSON shape: status emits the default tick envelope, "
            "plan emits a scheduler follow-up plan, dry-run emits a no-side-effect scheduler "
            "execution intent, diagnostic records scheduler diagnostics, execution records a safe "
            "scheduler execution ledger, action executes an observe-only contract action, "
            "action-route routes that observe-only action result, action-route-apply applies the "
            "ready route through the core apply layer, action-route-auto-apply binds scheduler "
            "attempt arguments then applies the route, attempt-run-intervention-readout reads intervention runs, "
            "attempt-route-auto-apply builds an explicit "
            "attempt context then applies the route, attempt-run-auto-progress-apply executes one recommended "
            "auto-progress step, attempt-run-auto-progress-plan reads durable state and "
            "recommends the next CLI, attempt-run-auto-progress-readout reads auto-progress run history, "
            "attempt-run-followup-decision reads attempt runs and "
            "emits a policy decision, attempt-run-intervention-apply applies a safe intervention plan, "
            "attempt-run-intervention-followup-decision emits the next intervention decision, "
            "attempt-run-recovery-followup-apply starts a ready recovery follow-up cycle, "
            "attempt-run-recovery-followup-intent emits the next recovery follow-up intent, "
            "attempt-run-recovery-ticket-apply writes a ready recovery ticket intent, "
            "attempt-run-recovery-ticket-intent emits a no-side-effect recovery ticket intent, "
            "attempt-run-intervention-plan emits a no-side-effect intervention plan, "
            "attempt-run-readout reads recorded attempt runs, action-route-preflight "
            "checks route arguments, attempt-context builds an explicit scheduler attempt context, full emits "
            "the service result for debugging."
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
            preflight_scheduler_action_route=preflight_phase5_scheduler_action_route,
            apply_scheduler_action_route=apply_phase5_scheduler_action_route,
            bind_and_apply_scheduler_action_route=bind_and_apply_phase5_scheduler_action_route,
            build_attempt_context_and_apply_scheduler_action_route=(
                build_attempt_context_and_apply_phase5_scheduler_action_route
            ),
            run_service=run_phase5_local_cycle_service,
        ),
    )
