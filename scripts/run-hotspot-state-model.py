#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.hotspot_state_model_replay import (
    run_hotspot_state_reestablishment_model,
    write_hotspot_state_model_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered expanding hotspot state model.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-end", type=date.fromisoformat, default=date(2026, 6, 26))
    args = parser.parse_args()
    payload = run_hotspot_state_reestablishment_model(
        execution_snapshot_path=args.execution_snapshot,
        design_path=args.design,
        signal_end=args.signal_end,
    )
    write_hotspot_state_model_result(args.output, payload)
    print(
        json.dumps(
            {
                "artifact_id": payload["artifact_id"],
                "status": payload["status"],
                "opportunity_row_count": payload["opportunity_row_count"],
                "selection": payload["selection_before_extended_readout"],
                "families": {
                    key: {
                        "signal_counts": value["signal_counts"],
                        "sleeve_summary": value["sleeve_summary"],
                        "model_audit": value["model_audit"],
                    }
                    for key, value in payload["family_audits"].items()
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
