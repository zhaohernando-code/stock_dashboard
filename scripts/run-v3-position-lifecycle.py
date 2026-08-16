#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.v3_position_lifecycle import (
    run_v3_position_lifecycle_challenger,
    write_v3_position_lifecycle_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered V3 position-lifecycle challenger.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 6, 26))
    args = parser.parse_args()
    payload = run_v3_position_lifecycle_challenger(
        execution_snapshot_path=args.execution_snapshot,
        design_path=args.design,
        signal_end=args.signal_end,
    )
    write_v3_position_lifecycle_result(args.output, payload)
    print(
        json.dumps(
            {
                "artifact_id": payload["artifact_id"],
                "status": payload["status"],
                "control_reproduction": payload["control_reproduction"],
                "selection": payload["selection_before_extended_readout"],
                "extended_readout": payload["extended_readout"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
