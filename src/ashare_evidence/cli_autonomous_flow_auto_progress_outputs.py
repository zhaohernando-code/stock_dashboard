from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.scheduler_auto_progress_plan import read_phase5_scheduler_auto_progress_plan


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
