#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.external_inventory_rerank import (
    run_external_inventory_rerank_ablation,
    write_external_inventory_rerank_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered full V3 inventory external rerank.")
    for name in (
        "execution-snapshot",
        "global-market-snapshot",
        "sector-market-snapshot",
        "macro-market-snapshot",
        "sector-flow-snapshot",
        "design",
        "output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 6, 26))
    args = parser.parse_args()
    payload = run_external_inventory_rerank_ablation(
        execution_snapshot_path=args.execution_snapshot,
        global_market_snapshot_path=args.global_market_snapshot,
        sector_market_snapshot_path=args.sector_market_snapshot,
        macro_market_snapshot_path=args.macro_market_snapshot,
        sector_flow_snapshot_path=args.sector_flow_snapshot,
        design_path=args.design,
        signal_end=args.signal_end,
    )
    write_external_inventory_rerank_result(args.output, payload)
    print(
        json.dumps(
            {
                "artifact_id": payload["artifact_id"],
                "status": payload["status"],
                "selection": payload["selection_before_extended_readout"],
                "extended_readout": payload["extended_readout"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
