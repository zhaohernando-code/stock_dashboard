from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.scheduler_attempt_run_followup_policy import decide_phase5_scheduler_attempt_run_followup
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    apply_phase5_scheduler_attempt_run_intervention,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import plan_phase5_scheduler_attempt_run_intervention
from ashare_evidence.scheduler_attempt_run_readout import read_phase5_scheduler_attempt_run_readout


def handle_attempt_run_readout_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    readout = read_phase5_scheduler_attempt_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    print_json(readout.model_dump(mode="json"))
    return 0


def handle_attempt_run_followup_decision_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    readout = read_phase5_scheduler_attempt_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    decision = decide_phase5_scheduler_attempt_run_followup(readout)
    print_json(decision.model_dump(mode="json"))
    return 0


def handle_attempt_run_intervention_plan_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    plan = _build_attempt_run_intervention_plan(args)
    print_json(plan.model_dump(mode="json"))
    return 0


def handle_attempt_run_intervention_apply_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    plan = _build_attempt_run_intervention_plan(args)
    result = apply_phase5_scheduler_attempt_run_intervention(
        plan,
        diagnostic_id=args.diagnostic_id,
        observed_at=args.observed_at,
        root=args.artifact_root,
    )
    print_json(result.model_dump(mode="json"))
    return 4 if result.execution_status == "blocked" else 0


def _build_attempt_run_intervention_plan(args: Namespace):
    readout = read_phase5_scheduler_attempt_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    decision = decide_phase5_scheduler_attempt_run_followup(readout)
    return plan_phase5_scheduler_attempt_run_intervention(readout, decision)
