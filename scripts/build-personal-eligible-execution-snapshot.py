#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.personal_execution_snapshot import build_and_write_personal_eligible_execution_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a pre-ranking personal-eligibility V3 account snapshot.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot, audit = build_and_write_personal_eligible_execution_snapshot(
        source_path=args.source, output_path=args.output
    )
    print(json.dumps({"artifact_id": snapshot["artifact_id"], "audit": audit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
