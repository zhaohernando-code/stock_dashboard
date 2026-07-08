#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.shortpick_strategy_lab_read_model import (
    PAPER_STATE_ENV,
    PAPER_STATE_SCHEMA_VERSION,
    TRACKING_START_DATE,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_path() -> Path:
    configured = os.getenv(PAPER_STATE_ENV)
    if configured:
        return Path(configured)
    return _repo_root() / "data" / "shortpick-strategy-lab-paper-state.json"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _plan_source_orders() -> list[dict[str, Any]]:
    source = os.getenv("ASHARE_SHORTPICK_STRATEGY_LAB_PLAN_SOURCE")
    if not source:
        return []
    payload = _load_json(Path(source))
    rows = (payload or {}).get("planned_orders") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def main() -> int:
    path = _state_path()
    existing = _load_json(path) or {}
    records = existing.get("records") if isinstance(existing.get("records"), list) else []
    existing_orders = existing.get("planned_orders") if isinstance(existing.get("planned_orders"), list) else []
    planned_orders = _plan_source_orders() or [row for row in existing_orders if isinstance(row, dict)]
    payload = {
        "schema_version": PAPER_STATE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tracking_start_date": str(existing.get("tracking_start_date") or TRACKING_START_DATE),
        "records": [row for row in records if isinstance(row, dict)],
        "planned_orders": planned_orders,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    print(json.dumps({"status": "ok", "path": str(path), "planned_order_count": len(planned_orders)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
