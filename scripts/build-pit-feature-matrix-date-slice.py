#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.db import session_scope
from ashare_evidence.model_exploration_snapshot import build_model_exploration_p1_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded PIT feature-matrix date slice.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--as-of-date", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    as_of_dates = sorted({date.fromisoformat(value) for value in args.as_of_date})
    with session_scope(args.database_url) as session:
        artifacts = build_model_exploration_p1_artifacts(
            session,
            validation_run_id=f"pit-feature-date-slice-{as_of_dates[0]}-{as_of_dates[-1]}",
            as_of_dates=as_of_dates,
            entry_price_source="next_close",
        )
    payload = artifacts["pit_feature_matrix"]
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable PIT feature-matrix slice collision: {args.output}")
    if not args.output.exists():
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output),
                "artifact_id": payload["artifact_id"],
                "row_count": payload["row_count"],
                "source_data_time_range": payload["source_data_time_range"],
                "gate_readout": payload["gate_readout"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
