#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_evidence.db import session_scope
from ashare_evidence.shortpick_strategy_slices import build_shortpick_strategy_slice_evidence_from_staged_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build offline Short Pick Lab long-window strategy slice evidence.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--staged-artifact-dir", default="output/shortpick-staged-backtests/20260512T221426")
    parser.add_argument("--output-path", default="output/shortpick-strategy-slice-evidence.json")
    parser.add_argument("--entry-price-source", action="append", choices=["next_close", "next_open", "same_close_proxy"], default=None)
    parser.add_argument("--min-regime-period-count", type=int, default=2)
    args = parser.parse_args()

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(args.staged_artifact_dir)
    entry_sources = tuple(args.entry_price_source or ("next_close", "next_open", "same_close_proxy"))
    entry_paths = {
        entry: artifact_dir / f"full_window-{entry}.json"
        for entry in entry_sources
    }
    with session_scope(args.database_url) as session:
        payload = build_shortpick_strategy_slice_evidence_from_staged_artifacts(
            session,
            entry_artifact_paths=entry_paths,
            min_regime_period_count=args.min_regime_period_count,
        )
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload.get("status"),
                "output_path": str(output_path),
                "data_scope": payload.get("data_scope"),
                "sample_adequacy": payload.get("sample_adequacy"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
