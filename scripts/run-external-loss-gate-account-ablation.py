#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.global_sector_state_account_ablation import (
    run_external_loss_gate_account_ablation,
    write_ablation_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered round3 expanding external loss gate.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--global-market-snapshot", type=Path, required=True)
    parser.add_argument("--sector-market-snapshot", type=Path)
    parser.add_argument("--macro-market-snapshot", type=Path)
    parser.add_argument("--fed-policy", type=Path, required=True)
    parser.add_argument("--federal-register", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 5, 26))
    args = parser.parse_args()
    payload = run_external_loss_gate_account_ablation(
        execution_snapshot_path=args.execution_snapshot,
        global_market_snapshot_path=args.global_market_snapshot,
        sector_market_snapshot_path=args.sector_market_snapshot,
        macro_market_snapshot_path=args.macro_market_snapshot,
        fed_policy_path=args.fed_policy,
        federal_register_path=args.federal_register,
        design_path=args.design,
        signal_end=args.signal_end,
    )
    write_ablation_result(args.output, payload)
    print(
        json.dumps(
            {
                "artifact_id": payload["artifact_id"],
                "status": payload["status"],
                "selection_before_final": payload["selection_before_final"],
                "final_untouched_readout": payload["final_untouched_readout"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
