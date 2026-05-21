from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.scheduler_workbench_projection import read_phase5_workbench_projection_manifest


def handle_attempt_run_workbench_projection_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    projection = read_phase5_workbench_projection_manifest(
        cycle_id=args.cycle_id,
        runner_id=args.runner_id,
        root=args.artifact_root,
    )
    print_json(projection.model_dump(mode="json"))
    return 4 if projection.projection_status == "blocked" else 0
