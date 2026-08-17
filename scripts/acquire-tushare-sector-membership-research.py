#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.db import session_scope
from ashare_evidence.external_context_sector_membership import (
    acquire_tushare_sector_membership_snapshot,
    write_sector_membership_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire effective-dated SW2021 sector memberships.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def progress(payload):  # type: ignore[no-untyped-def]
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    with session_scope(args.database_url) as session:
        payload = acquire_tushare_sector_membership_snapshot(session, progress_fn=progress)
    write_sector_membership_snapshot(args.output, payload)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output),
                "content_digest": payload["content_digest"],
                "quality": payload["quality"],
                "readiness": payload["readiness"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
