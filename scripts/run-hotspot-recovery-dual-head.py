#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.hotspot_recovery_dual_head import run_hotspot_recovery_dual_head, write_dual_head_result
from ashare_evidence.recent_hotspot_pit import (
    analyze_recent_hotspot_misses,
    build_recent_hotspot_pit_snapshot,
    write_gzip_artifact,
    write_json_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the recent PIT hotspot audit and frozen dual-head shadow seed.")
    parser.add_argument("--hot-database", type=Path, required=True)
    parser.add_argument("--daily-source-directory", type=Path, required=True)
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--recent-snapshot-output", type=Path, required=True)
    parser.add_argument("--attribution-output", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    args = parser.parse_args()

    design = json.loads(args.design.read_text(encoding="utf-8"))
    recent = build_recent_hotspot_pit_snapshot(
        hot_database=args.hot_database,
        daily_source_directory=args.daily_source_directory,
        design_path=args.design,
    )
    write_gzip_artifact(args.recent_snapshot_output, recent)
    attribution = analyze_recent_hotspot_misses(recent, design=design)
    write_json_artifact(args.attribution_output, attribution)
    model = run_hotspot_recovery_dual_head(
        execution_snapshot_path=args.execution_snapshot,
        recent_snapshot_path=args.recent_snapshot_output,
        hot_database=args.hot_database,
        design_path=args.design,
    )
    write_dual_head_result(args.model_output, model)
    print(
        json.dumps(
            {
                "recent_snapshot_id": recent["artifact_id"],
                "recent_rows": recent["row_count"],
                "attribution_id": attribution["artifact_id"],
                "broad_winners": attribution["broad_winner_count"],
                "strong_hotspots": attribution["strong_hotspot_count"],
                "model_id": model["artifact_id"],
                "retrospective_signals": model["retrospective_selected_signal_count"],
                "forward_signals": model["forward_shadow"]["signal_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
