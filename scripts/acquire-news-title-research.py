#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ashare_evidence.db import session_scope
from ashare_evidence.external_context_news_research import acquire_news_title_snapshot, write_news_title_snapshot

SHANGHAI = ZoneInfo("Asia/Shanghai")


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire compact relevant historical news-title research data.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--start", default="2023-05-01 00:00:00")
    parser.add_argument("--end", default="2026-06-26 23:59:59")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with gzip.open(args.execution_snapshot, "rt", encoding="utf-8") as handle:
        execution = json.load(handle)
    inventory = execution["inputs"]["candidate_inventory_rows"]
    company_names = sorted({str(row.get("stock_name") or "").strip() for row in inventory if row.get("stock_name")})
    industry_names = sorted({str(row.get("industry_name") or "").strip() for row in inventory if row.get("industry_name")})
    with session_scope(args.database_url) as session:
        payload = acquire_news_title_snapshot(
            session,
            start=datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI),
            end=datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI),
            company_names=company_names,
            industry_names=industry_names,
        )
    write_news_title_snapshot(args.output, payload)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output),
                "content_digest": payload["content_digest"],
                "quality": payload["quality"],
                "promotion_blocker": payload["promotion_blocker"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
