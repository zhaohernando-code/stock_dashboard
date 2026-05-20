from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.autonomous_flow_scheduler_attempt import build_phase5_scheduler_attempt_context

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
