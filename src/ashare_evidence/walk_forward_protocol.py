from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ashare_evidence.research_artifact_store import write_research_validation_artifact

WALK_FORWARD_PROTOCOL_SCHEMA_VERSION = "walk_forward_purge_embargo.v1"
WALK_FORWARD_PROTOCOL_VERSION = "anchored_walk_forward_purge_embargo:v1"
MIN_WALK_FORWARD_SPLITS = 3
MIN_TRAIN_PERIODS = 6
MIN_TEST_PERIODS = 2


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _parse_day(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _date_range(days: list[date]) -> dict[str, str | None]:
    ordered = sorted(days)
    return {
        "start": ordered[0].isoformat() if ordered else None,
        "end": ordered[-1].isoformat() if ordered else None,
    }


def _build_splits(days: list[date], *, max_horizon_days: int) -> list[dict[str, Any]]:
    ordered = sorted(set(days))
    splits: list[dict[str, Any]] = []
    split_index = 1
    cursor = MIN_TRAIN_PERIODS
    while cursor + MIN_TEST_PERIODS <= len(ordered):
        train_days = ordered[:cursor]
        test_days = ordered[cursor : cursor + MIN_TEST_PERIODS]
        test_start = test_days[0]
        purge_start = test_start - timedelta(days=max_horizon_days)
        purged_train_days = [day for day in train_days if day < purge_start]
        embargo_end = test_days[-1] + timedelta(days=max_horizon_days)
        split_ready = len(purged_train_days) >= MIN_TRAIN_PERIODS and len(test_days) >= MIN_TEST_PERIODS
        splits.append(
            {
                "split_id": f"wf-{split_index:03d}",
                "train_range": _date_range(train_days),
                "purged_train_range": _date_range(purged_train_days),
                "test_range": _date_range(test_days),
                "train_period_count": len(train_days),
                "purged_train_period_count": len(purged_train_days),
                "test_period_count": len(test_days),
                "purge_days": max_horizon_days,
                "embargo_days": max_horizon_days,
                "embargo_until": embargo_end.isoformat(),
                "status": "ready" if split_ready else "blocked",
            }
        )
        split_index += 1
        cursor += MIN_TEST_PERIODS
    return splits


def build_walk_forward_protocol_artifact(
    *,
    validation_run_id: str,
    source_db_snapshot_id: str,
    source_data_time_range: dict[str, Any],
    objective_universe: dict[str, Any],
    input_snapshot: dict[str, Any],
    pit_feature_store: dict[str, Any],
    observation_rows: list[dict[str, Any]],
    horizons: list[int],
) -> dict[str, Any]:
    max_horizon_days = max([int(horizon) for horizon in horizons] or [0])
    as_of_days = [
        day
        for row in observation_rows
        if (day := _parse_day(row.get("as_of_date") or row.get("as_of"))) is not None
    ]
    splits = _build_splits(as_of_days, max_horizon_days=max_horizon_days)
    ready_splits = [split for split in splits if split.get("status") == "ready"]
    protocol_digest = _stable_digest(
        {
            "protocol_version": WALK_FORWARD_PROTOCOL_VERSION,
            "source_db_snapshot_id": source_db_snapshot_id,
            "objective_universe_id": objective_universe.get("artifact_id"),
            "input_snapshot_id": input_snapshot.get("artifact_id"),
            "pit_feature_store_id": pit_feature_store.get("artifact_id"),
            "observation_as_of_days": sorted(day.isoformat() for day in set(as_of_days)),
            "horizons": horizons,
            "splits": splits,
        }
    )
    artifact_id = f"walk-forward-protocol-{protocol_digest[:16]}"
    blocked = len(ready_splits) < MIN_WALK_FORWARD_SPLITS
    return {
        "artifact_type": "walk_forward_purge_embargo",
        "schema_version": WALK_FORWARD_PROTOCOL_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_db_snapshot_id,
        "source_data_time_range": source_data_time_range,
        "feature_version": pit_feature_store.get("feature_version"),
        "label_version": "daily_close_forward_excess_return:v1",
        "code_version": "unresolved_local_checkout",
        "config_version": WALK_FORWARD_PROTOCOL_VERSION,
        "validation_protocol": {
            "artifact_role": "walk_forward_purge_embargo",
            "protocol_version": WALK_FORWARD_PROTOCOL_VERSION,
            "split_policy": "anchored_walk_forward",
            "purge_days": max_horizon_days,
            "embargo_days": max_horizon_days,
            "min_train_periods": MIN_TRAIN_PERIODS,
            "min_test_periods": MIN_TEST_PERIODS,
            "min_ready_splits": MIN_WALK_FORWARD_SPLITS,
        },
        "gate_readout": {
            "gate_status": "blocked" if blocked else "walk_forward_ready",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "walk_forward_protocol_only",
            "blocking_gate_ids": ["walk_forward_min_splits"] if blocked else [],
            "ready_split_count": len(ready_splits),
            "required_ready_split_count": MIN_WALK_FORWARD_SPLITS,
        },
        "claim_ceiling": "walk_forward_protocol_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_artifacts": {
            "objective_universe_id": objective_universe.get("artifact_id"),
            "research_input_snapshot_id": input_snapshot.get("artifact_id"),
            "pit_feature_store_id": pit_feature_store.get("artifact_id"),
        },
        "observation_period_count": len(set(as_of_days)),
        "split_count": len(splits),
        "ready_split_count": len(ready_splits),
        "protocol_content_digest": protocol_digest,
        "splits": splits,
    }


def walk_forward_protocol_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "schema_version": payload.get("schema_version"),
        "artifact_id": payload.get("artifact_id"),
        "protocol_version": (payload.get("validation_protocol") or {}).get("protocol_version"),
        "split_count": payload.get("split_count"),
        "ready_split_count": payload.get("ready_split_count"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "gate_readout": payload.get("gate_readout"),
        "storage_boundary": payload.get("storage_boundary"),
    }


def write_walk_forward_protocol_artifact(payload: dict[str, Any], *, artifact_root: str) -> Path:
    return write_research_validation_artifact(
        "walk_forward_purge_embargo",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
