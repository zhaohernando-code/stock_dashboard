#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.external_context_sector_market_research import (
    load_sector_research_snapshot,
    merge_sector_research_snapshots,
    write_sector_research_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge immutable SW2021 L1 sector snapshots without refetching history.")
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = merge_sector_research_snapshots([load_sector_research_snapshot(path) for path in args.input])
    write_sector_research_snapshot(args.output, payload)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output),
                "content_digest": payload["content_digest"],
                "quality": payload["quality"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
