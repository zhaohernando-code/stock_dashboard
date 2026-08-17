#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.all_universe_opportunity_data import (
    build_all_universe_opportunity_dataset,
    write_gzip_dataset,
)
from ashare_evidence.all_universe_opportunity_head import run_all_universe_opportunity_head, write_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and evaluate the frozen full-universe opportunity head.")
    parser.add_argument("--historical-database", type=Path, required=True)
    parser.add_argument("--hot-database", type=Path, required=True)
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--recent-snapshot", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--data-source-amendment", type=Path, required=True)
    parser.add_argument("--dataset-output", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    args = parser.parse_args()
    design = json.loads(args.design.read_text(encoding="utf-8"))
    data_source_amendment = json.loads(args.data_source_amendment.read_text(encoding="utf-8"))
    dataset = build_all_universe_opportunity_dataset(
        historical_database=args.historical_database,
        hot_database=args.hot_database,
        execution_snapshot_path=args.execution_snapshot,
        recent_snapshot_path=args.recent_snapshot,
        design=design,
        data_source_amendment=data_source_amendment,
    )
    write_gzip_dataset(args.dataset_output, dataset)
    result = run_all_universe_opportunity_head(dataset_path=args.dataset_output, design_path=args.design)
    write_result(args.result_output, result)
    print(
        json.dumps(
            {
                "dataset_id": dataset["artifact_id"],
                "candidate_rows": dataset["candidate_row_count"],
                "result_id": result["artifact_id"],
                "status": result["status"],
                "named_case_passed": result["named_case_admission"]["passed"],
                "performance_gate_passed": result["performance_gate_passed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
