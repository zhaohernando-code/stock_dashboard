#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.db import session_scope
from ashare_evidence.external_context_sector_flow_research import (
    acquire_sector_flow_snapshot,
    write_sector_flow_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire compact THS industry and concept flow research data.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--start", default="2023-05-01")
    parser.add_argument("--end", default="2026-06-26")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with session_scope(args.database_url) as session:
        payload = acquire_sector_flow_snapshot(
            session,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
        )
    write_sector_flow_snapshot(args.output, payload)
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
