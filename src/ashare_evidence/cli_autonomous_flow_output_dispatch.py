from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.cli_autonomous_flow_action_outputs import (
    handle_action_output,
    handle_action_route_apply_output,
    handle_action_route_auto_apply_output,
    handle_action_route_output,
    handle_action_route_preflight_output,
)
from ashare_evidence.cli_autonomous_flow_attempt_intervention_outputs import (
    handle_attempt_intervention_followup_decision_output,
    handle_attempt_intervention_run_readout_output,
    handle_attempt_recovery_ticket_apply_output,
    handle_attempt_recovery_ticket_intent_output,
    handle_attempt_run_intervention_apply_output,
    handle_attempt_run_intervention_plan_output,
)
from ashare_evidence.cli_autonomous_flow_attempt_outputs import (
    handle_attempt_context_output,
    handle_attempt_route_auto_apply_output,
)
from ashare_evidence.cli_autonomous_flow_attempt_readout_outputs import (
    handle_attempt_run_followup_decision_output,
    handle_attempt_run_readout_output,
)
from ashare_evidence.cli_autonomous_flow_auto_progress_outputs import (
    handle_attempt_run_auto_progress_apply_output,
    handle_attempt_run_auto_progress_plan_output,
    handle_attempt_run_auto_progress_readout_output,
)
from ashare_evidence.cli_autonomous_flow_diagnostic_outputs import handle_diagnostic_output
from ashare_evidence.cli_autonomous_flow_execution_outputs import (
    handle_execution_output,
    handle_full_output,
)
from ashare_evidence.cli_autonomous_flow_output_context import Phase5LocalCycleStepHandlers, run_tick_from_args
from ashare_evidence.cli_autonomous_flow_recovery_outputs import (
    handle_attempt_recovery_followup_apply_output,
    handle_attempt_recovery_followup_intent_output,
)


def handle_secondary_phase5_local_cycle_step_output(
    args: Namespace,
    *,
    handlers: Phase5LocalCycleStepHandlers,
    print_json: Any,
) -> int:
    if args.output in _ACTION_OUTPUTS:
        return _handle_action_family_output(args, handlers, print_json=print_json)
    if args.output in _ATTEMPT_OUTPUTS:
        return _handle_attempt_family_output(args, handlers, print_json=print_json)
    if args.output == "diagnostic":
        return handle_diagnostic_output(args, handlers, run_tick_from_args=run_tick_from_args, print_json=print_json)
    if args.output == "execution":
        return handle_execution_output(args, handlers, run_tick_from_args=run_tick_from_args, print_json=print_json)
    return handle_full_output(args, handlers, print_json=print_json)


_ACTION_OUTPUTS = {
    "action",
    "action-route",
    "action-route-apply",
    "action-route-auto-apply",
    "action-route-preflight",
}
_ATTEMPT_OUTPUTS = {
    "attempt-context",
    "attempt-route-auto-apply",
    "attempt-run-auto-progress-apply",
    "attempt-run-auto-progress-plan",
    "attempt-run-auto-progress-readout",
    "attempt-run-intervention-followup-decision",
    "attempt-run-intervention-readout",
    "attempt-run-intervention-apply",
    "attempt-run-intervention-plan",
    "attempt-run-recovery-followup-apply",
    "attempt-run-recovery-followup-intent",
    "attempt-run-recovery-ticket-apply",
    "attempt-run-recovery-ticket-intent",
    "attempt-run-followup-decision",
    "attempt-run-readout",
}


def _handle_action_family_output(
    args: Namespace,
    handlers: Phase5LocalCycleStepHandlers,
    *,
    print_json: Any,
) -> int:
    common = {"run_tick_from_args": run_tick_from_args, "print_json": print_json}
    if args.output == "action":
        return handle_action_output(args, handlers, **common)
    if args.output == "action-route":
        return handle_action_route_output(args, handlers, **common)
    if args.output == "action-route-apply":
        return handle_action_route_apply_output(args, handlers, **common)
    if args.output == "action-route-auto-apply":
        return handle_action_route_auto_apply_output(args, handlers, **common)
    return handle_action_route_preflight_output(args, handlers, **common)


def _handle_attempt_family_output(
    args: Namespace,
    handlers: Phase5LocalCycleStepHandlers,
    *,
    print_json: Any,
) -> int:
    if args.output == "attempt-context":
        return handle_attempt_context_output(args, print_json=print_json)
    if args.output == "attempt-run-auto-progress-apply":
        return handle_attempt_run_auto_progress_apply_output(args, print_json=print_json)
    if args.output == "attempt-run-auto-progress-plan":
        return handle_attempt_run_auto_progress_plan_output(args, print_json=print_json)
    if args.output == "attempt-run-auto-progress-readout":
        return handle_attempt_run_auto_progress_readout_output(args, print_json=print_json)
    if args.output == "attempt-run-intervention-followup-decision":
        return handle_attempt_intervention_followup_decision_output(args, print_json=print_json)
    if args.output == "attempt-run-intervention-readout":
        return handle_attempt_intervention_run_readout_output(args, print_json=print_json)
    if args.output == "attempt-run-recovery-followup-apply":
        return handle_attempt_recovery_followup_apply_output(args, print_json=print_json)
    if args.output == "attempt-run-recovery-followup-intent":
        return handle_attempt_recovery_followup_intent_output(args, print_json=print_json)
    if args.output == "attempt-run-recovery-ticket-apply":
        return handle_attempt_recovery_ticket_apply_output(args, print_json=print_json)
    if args.output == "attempt-run-recovery-ticket-intent":
        return handle_attempt_recovery_ticket_intent_output(args, print_json=print_json)
    if args.output == "attempt-route-auto-apply":
        return handle_attempt_route_auto_apply_output(
            args,
            handlers,
            run_tick_from_args=run_tick_from_args,
            print_json=print_json,
        )
    if args.output == "attempt-run-readout":
        return handle_attempt_run_readout_output(args, print_json=print_json)
    if args.output == "attempt-run-intervention-apply":
        return handle_attempt_run_intervention_apply_output(args, print_json=print_json)
    if args.output == "attempt-run-intervention-plan":
        return handle_attempt_run_intervention_plan_output(args, print_json=print_json)
    return handle_attempt_run_followup_decision_output(args, print_json=print_json)
