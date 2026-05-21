from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.scheduler_attempt_run_followup_policy import decide_phase5_scheduler_attempt_run_followup
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    apply_phase5_scheduler_attempt_run_intervention,
)
from ashare_evidence.scheduler_attempt_run_intervention_followup_policy import (
    decide_phase5_scheduler_attempt_intervention_followup,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import plan_phase5_scheduler_attempt_run_intervention
from ashare_evidence.scheduler_attempt_run_intervention_readout import (
    read_phase5_scheduler_attempt_intervention_run_readout,
)
from ashare_evidence.scheduler_attempt_run_intervention_recorder import (
    record_phase5_scheduler_attempt_intervention_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_readout import read_phase5_scheduler_attempt_run_readout
from ashare_evidence.scheduler_attempt_run_recovery_ticket_executor import (
    apply_phase5_scheduler_recovery_ticket_intent,
)
from ashare_evidence.scheduler_attempt_run_recovery_ticket_intent import (
    build_phase5_scheduler_recovery_ticket_intent,
)


def handle_attempt_intervention_run_readout_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    readout = read_phase5_scheduler_attempt_intervention_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    print_json(readout.model_dump(mode="json"))
    return 0


def handle_attempt_intervention_followup_decision_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    readout = read_phase5_scheduler_attempt_intervention_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)
    print_json(decision.model_dump(mode="json"))
    return 0


def handle_attempt_recovery_ticket_intent_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    intent = _build_attempt_recovery_ticket_intent(args)
    print_json(intent.model_dump(mode="json"))
    return 4 if intent.intent_status == "blocked" else 0


def handle_attempt_recovery_ticket_apply_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    intent = _build_attempt_recovery_ticket_intent(args)
    result = apply_phase5_scheduler_recovery_ticket_intent(intent, root=args.artifact_root)
    print_json(result.model_dump(mode="json"))
    return 4 if result.apply_status == "blocked" else 0


def _build_attempt_recovery_ticket_intent(args: Namespace):
    readout = read_phase5_scheduler_attempt_intervention_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    decision = decide_phase5_scheduler_attempt_intervention_followup(readout)
    return build_phase5_scheduler_recovery_ticket_intent(readout, decision)


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
    if getattr(args, "record_intervention_run", False):
        print_json(_intervention_run_record_envelope(result, args))
        return 4 if result.execution_status == "blocked" else 0

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


def _intervention_run_record_envelope(result: Any, args: Namespace) -> dict[str, Any]:
    apply_payload = result.model_dump(mode="json")
    missing = _missing_intervention_run_record_context(args)
    if missing:
        return {
            "apply_result": apply_payload,
            "intervention_run_artifact": None,
            "intervention_run_artifact_path": None,
            "intervention_run_record_status": "blocked",
            "intervention_run_record_missing_arguments": missing,
            "intervention_run_record_blocking_reasons": [
                "missing required recorder context: " + ", ".join(missing)
            ],
        }

    recorded = record_phase5_scheduler_attempt_intervention_run_artifact(
        result,
        runner_id=args.runner_id,
        issued_at=args.issued_at,
        intervention_run_id=args.intervention_run_id,
        root=args.artifact_root,
    )
    return {
        "apply_result": apply_payload,
        "intervention_run_artifact": recorded.artifact.model_dump(mode="json"),
        "intervention_run_artifact_path": str(recorded.path),
        "intervention_run_record_status": "recorded",
    }


def _missing_intervention_run_record_context(args: Namespace) -> list[str]:
    missing: list[str] = []
    if not args.issued_at:
        missing.append("issued_at")
    if not args.runner_id:
        missing.append("runner_id")
    return missing
