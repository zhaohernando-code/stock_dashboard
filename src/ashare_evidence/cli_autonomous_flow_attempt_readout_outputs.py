from __future__ import annotations

from argparse import Namespace
from typing import Any

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
