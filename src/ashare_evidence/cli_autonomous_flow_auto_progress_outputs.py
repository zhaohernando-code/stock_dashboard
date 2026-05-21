from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.scheduler_auto_progress_executor import apply_phase5_scheduler_auto_progress_step
from ashare_evidence.scheduler_auto_progress_plan import read_phase5_scheduler_auto_progress_plan
from ashare_evidence.scheduler_auto_progress_readout import read_phase5_scheduler_auto_progress_run_readout
from ashare_evidence.scheduler_auto_progress_recorder import (
    record_phase5_scheduler_auto_progress_run_artifact,
)


def handle_attempt_run_auto_progress_plan_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    plan = read_phase5_scheduler_auto_progress_plan(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        created_at=args.created_at,
        issued_at=args.issued_at,
        root=args.artifact_root,
    )
    print_json(plan.model_dump(mode="json"))
    return 4 if plan.plan_status == "blocked" else 0


def handle_attempt_run_auto_progress_readout_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    readout = read_phase5_scheduler_auto_progress_run_readout(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    print_json(readout.model_dump(mode="json"))
    return 0


def handle_attempt_run_auto_progress_apply_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    result = apply_phase5_scheduler_auto_progress_step(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        created_at=args.created_at,
        issued_at=args.issued_at,
        intervention_run_id=args.intervention_run_id,
        root=args.artifact_root,
    )
    if getattr(args, "record_auto_progress_run", False):
        print_json(_auto_progress_run_record_envelope(result, args))
        return 4 if result.apply_status == "blocked" else 0

    print_json(result.model_dump(mode="json"))
    return 4 if result.apply_status == "blocked" else 0


def _auto_progress_run_record_envelope(result: Any, args: Namespace) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    missing = _missing_auto_progress_run_record_context(args)
    if missing:
        return {
            "auto_progress_apply_result": payload,
            "auto_progress_run_artifact": None,
            "auto_progress_run_artifact_path": None,
            "auto_progress_run_record_status": "blocked",
            "auto_progress_run_record_missing_arguments": missing,
            "auto_progress_run_record_blocking_reasons": [
                "missing required auto-progress recorder context: " + ", ".join(missing)
            ],
        }

    recorded = record_phase5_scheduler_auto_progress_run_artifact(
        result,
        runner_id=args.runner_id,
        issued_at=args.issued_at,
        auto_progress_run_id=args.auto_progress_run_id,
        root=args.artifact_root,
    )
    return {
        "auto_progress_apply_result": payload,
        "auto_progress_run_artifact": recorded.artifact.model_dump(mode="json"),
        "auto_progress_run_artifact_path": str(recorded.path),
        "auto_progress_run_record_status": "recorded",
    }


def _missing_auto_progress_run_record_context(args: Namespace) -> list[str]:
    missing: list[str] = []
    if not args.issued_at:
        missing.append("issued_at")
    if not args.runner_id:
        missing.append("runner_id")
    return missing
