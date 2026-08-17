#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.all_universe_hotspot_classifier import run_hotspot_classifier, write_classifier_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the frozen all-universe hotspot-event classifier.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--regression-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_hotspot_classifier(
        dataset_path=args.dataset,
        design_path=args.design,
        regression_result_path=args.regression_result,
    )
    write_classifier_result(args.output, result)
    print(
        json.dumps(
            {
                "artifact_id": result["artifact_id"],
                "status": result["status"],
                "performance_gate_passed": result["performance_gate_passed"],
                "named_case_rank_gate_passed": result["named_case_rank_gate"]["passed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
