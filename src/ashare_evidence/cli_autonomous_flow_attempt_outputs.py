from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from typing import Any

from ashare_evidence.autonomous_flow_scheduler_attempt import build_phase5_scheduler_attempt_context
from ashare_evidence.scheduler_attempt_run_recorder import record_phase5_scheduler_attempt_run_artifact

_ACTION_BLOCKED_EXIT_CODE = 4


def handle_attempt_context_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    result = build_phase5_scheduler_attempt_context(
        cycle_id=args.cycle_id,
        issued_at=args.issued_at,
        runner_id=args.runner_id,
    )
    print_json(result.model_dump(mode="json"))
    if result.status == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0


def handle_attempt_route_auto_apply_output(
    args: Namespace,
    handlers: Any,
    *,
    run_tick_from_args: Callable[[Namespace, Any], Any],
    print_json: Callable[[Any], None],
) -> int:
    tick_result = run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    action_result = handlers.execute_scheduler_noop_action(plan)
    route_result = handlers.route_scheduler_action_result(action_result)
    apply_result = handlers.build_attempt_context_and_apply_scheduler_action_route(
        plan,
        route_result,
        issued_at=args.issued_at,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    if not getattr(args, "record_attempt_run", False):
        print_json(apply_result.model_dump(mode="json"))
        return _attempt_route_apply_exit_code(apply_result)

    print_json(_attempt_run_record_envelope(apply_result, args))
    return _attempt_route_apply_exit_code(apply_result)


def _attempt_route_apply_exit_code(result: Any) -> int:
    if getattr(result, "execution_status", None) == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    if isinstance(getattr(result, "payload", None), dict) and result.payload.get("execution_status") == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0


def _attempt_run_record_envelope(apply_result: Any, args: Namespace) -> dict[str, Any]:
    apply_payload = apply_result.model_dump(mode="json")
    missing = _missing_attempt_run_record_context(args)
    if missing:
        return {
            "apply_result": apply_payload,
            "attempt_run_artifact": None,
            "attempt_run_artifact_path": None,
            "attempt_run_record_status": "blocked",
            "attempt_run_record_missing_arguments": missing,
            "attempt_run_record_blocking_reasons": [
                "missing required recorder context: " + ", ".join(missing)
            ],
        }

    recorded = record_phase5_scheduler_attempt_run_artifact(
        apply_result,
        runner_id=args.runner_id,
        issued_at=args.issued_at,
        run_id=args.attempt_run_id,
        root=args.artifact_root,
    )
    return {
        "apply_result": apply_payload,
        "attempt_run_artifact": recorded.artifact.model_dump(mode="json"),
        "attempt_run_artifact_path": str(recorded.path),
        "attempt_run_record_status": "recorded",
    }


def _missing_attempt_run_record_context(args: Namespace) -> list[str]:
    missing: list[str] = []
    if not args.issued_at:
        missing.append("issued_at")
    if not args.runner_id:
        missing.append("runner_id")
    return missing
