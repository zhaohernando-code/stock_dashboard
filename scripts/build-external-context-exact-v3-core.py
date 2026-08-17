#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.external_context_exact_core import build_exact_v3_core_snapshot, write_exact_v3_core_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize exact active V3 trial-000 core scores for candidates.")
    parser.add_argument("--candidate-dataset", type=Path, required=True)
    parser.add_argument("--feature-matrix", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_exact_v3_core_snapshot(
        candidate_dataset_path=args.candidate_dataset,
        feature_matrix_paths=args.feature_matrix,
    )
    write_exact_v3_core_snapshot(args.output, payload)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output),
                "content_digest": payload["content_digest"],
                "candidate_row_count": payload["candidate_row_count"],
                "resolved_core_score_count": payload["resolved_core_score_count"],
                "missing_core_score_count": payload["missing_core_score_count"],
                "core_score_coverage_ratio": payload["core_score_coverage_ratio"],
                "covered_date_range": payload["covered_date_range"],
                "quality": payload["quality"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
