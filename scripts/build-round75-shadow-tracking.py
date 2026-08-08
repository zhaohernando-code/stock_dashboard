#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ashare_evidence.round75_shadow_tracking import (
    ROUND75_ACTIVATION_DATE,
    advance_round75_signal_registry,
    build_round75_shadow_tracking_artifact,
    build_round75_signal_registry,
    validate_round75_signal_registry,
    write_round75_shadow_tracking,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the frozen Round 75 historical backfill and signal registry.")
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--round75-result", type=Path, required=True)
    parser.add_argument("--activation-date", type=date.fromisoformat, default=date.fromisoformat(ROUND75_ACTIVATION_DATE))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-output", type=Path, required=True)
    parser.add_argument("--existing-signal-registry", type=Path, default=None)
    args = parser.parse_args()
    payload = build_round75_shadow_tracking_artifact(
        execution_snapshot_path=args.execution_snapshot,
        result_path=args.round75_result,
        activation_date=args.activation_date,
    )
    registry = build_round75_signal_registry(payload, activation_date=args.activation_date)
    if args.existing_signal_registry is not None and args.existing_signal_registry.exists():
        existing = json.loads(args.existing_signal_registry.read_text(encoding="utf-8"))
        registry = advance_round75_signal_registry(existing, registry)
    validation = validate_round75_signal_registry(registry)
    write_round75_shadow_tracking(args.output, payload)
    write_round75_shadow_tracking(args.signal_output, registry)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "signal_output": str(args.signal_output),
                "content_digest": payload["content_digest"],
                "backfill_from": payload["historical_backfill"]["from"],
                "backfill_to": payload["historical_backfill"]["to"],
                "signal_count": validation["signal_count"],
                "true_forward_signal_count": validation["true_forward_signal_count"],
                "evaluated_through": validation["evaluated_through"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
