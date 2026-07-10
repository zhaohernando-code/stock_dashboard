#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ashare_evidence.db import session_scope
from ashare_evidence.shortpick_strategy_lab_v3_projection import (
    build_latest_v3_candidate_run_source,
    default_v3_candidate_run_source_path,
    write_latest_v3_candidate_run_source,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_database_url() -> str | None:
    configured = os.getenv("ASHARE_SHORTPICK_STRATEGY_LAB_V3_SOURCE_DATABASE_URL")
    if configured:
        return configured
    hot_db = _repo_root() / "data" / "ashare_hot.db"
    if hot_db.exists() and hot_db.stat().st_size > 0:
        return f"sqlite:///{hot_db}"
    return os.getenv("ASHARE_DATABASE_URL")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the v3 selected_top_k candidate-run source for paper tracking.")
    parser.add_argument("--output", default=None)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else default_v3_candidate_run_source_path(_repo_root())
    with session_scope(args.database_url or _default_database_url()) as session:
        payload = build_latest_v3_candidate_run_source(session)
    write_latest_v3_candidate_run_source(payload, output_path)
    print(
        json.dumps(
            {
                "status": "ok",
                "path": str(output_path),
                "artifact_id": payload.get("artifact_id"),
                "signal_date": payload.get("signal_date"),
                "selected_pick_count": payload.get("selected_pick_count"),
                "model_spec_ids": payload.get("model_spec_ids"),
                "selected_pick_count_by_model_spec": payload.get("selected_pick_count_by_model_spec"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
