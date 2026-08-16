#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.external_reversal_rotation import (
    run_external_reversal_rotation_challenger,
    write_external_reversal_rotation_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered PIT-only reversal rotation challenger.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--sector-market-snapshot", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 6, 26))
    args = parser.parse_args()
    payload = run_external_reversal_rotation_challenger(
        execution_snapshot_path=args.execution_snapshot,
        sector_market_snapshot_path=args.sector_market_snapshot,
        design_path=args.design,
        signal_end=args.signal_end,
    )
    write_external_reversal_rotation_result(args.output, payload)
    print(
        json.dumps(
            {
                "artifact_id": payload["artifact_id"],
                "status": payload["status"],
                "event_detection": payload["event_detection"],
                "selection": payload["selection_before_extended_readout"],
                "extended_readout": payload["extended_readout"],
                "leave_one_event_out": payload["leave_one_event_out"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
