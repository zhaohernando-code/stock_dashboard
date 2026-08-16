#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.stock_transition_sleeve import (
    run_stock_transition_sleeve_challenger,
    write_stock_transition_sleeve_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered stock-transition sleeve challenger.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--sector-market-snapshot", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 6, 26))
    args = parser.parse_args()
    payload = run_stock_transition_sleeve_challenger(
        execution_snapshot_path=args.execution_snapshot,
        sector_market_snapshot_path=args.sector_market_snapshot,
        design_path=args.design,
        signal_end=args.signal_end,
    )
    write_stock_transition_sleeve_result(args.output, payload)
    print(
        json.dumps(
            {
                "artifact_id": payload["artifact_id"],
                "status": payload["status"],
                "sleeve_signal_audit": payload["sleeve_signal_audit"],
                "selection": payload["selection_before_extended_readout"],
                "extended_readout": payload["extended_readout"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
