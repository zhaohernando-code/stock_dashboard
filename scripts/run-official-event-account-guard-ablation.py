#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.global_sector_state_account_ablation import write_ablation_result
from ashare_evidence.official_event_account_guard import run_official_event_account_guard_ablation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run round15 CNINFO official negative-event account guard.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--curation", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 6, 26))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run_official_event_account_guard_ablation(
        execution_snapshot_path=args.execution_snapshot,
        external_root=args.external_root,
        curation_path=args.curation,
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
