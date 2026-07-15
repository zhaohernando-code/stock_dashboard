from __future__ import annotations

import gzip
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def build_rolling_account_execution_snapshot(
    *,
    candidate_run: dict[str, Any],
    trial_id: str,
    candidate_inventory_rows: list[dict[str, Any]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    baseline_config: dict[str, Any],
    account_profile: dict[str, Any],
    baseline_result: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    trial = next(row for row in candidate_run["trial_diagnostics"] if row.get("trial_id") == trial_id)
    minimal_candidate_run = {
        "artifact_id": candidate_run.get("artifact_id"),
        "trial_diagnostics": [deepcopy(trial)],
    }
    normalized_bars = {
        symbol: [
            {
                "day": row["day"].isoformat() if hasattr(row.get("day"), "isoformat") else str(row["day"]),
                "close": float(row["close"]),
            }
            for row in rows
        ]
        for symbol, rows in sorted(market_bars_by_symbol.items())
    }
    inputs = {
        "candidate_run": minimal_candidate_run,
        "candidate_inventory_rows": deepcopy(candidate_inventory_rows),
        "market_bars_by_symbol": normalized_bars,
        "baseline_config": deepcopy(baseline_config),
        "account_profile": deepcopy(account_profile),
    }
    output = {
        "config_id": baseline_result["config_id"],
        "summary": deepcopy(baseline_result["summary"]),
        "reason_counts": deepcopy(baseline_result["reason_counts"]),
        "monthly_returns": deepcopy(baseline_result["monthly_returns"]),
        "order_ledger": deepcopy(baseline_result["order_ledger"]),
        "nav_rows": deepcopy(baseline_result["nav_rows"]),
    }
    input_digest = stable_digest(inputs)
    output_digest = stable_digest(output)
    artifact_material = {
        "trial_id": trial_id,
        "input_content_digest": input_digest,
        "output_content_digest": output_digest,
    }
    artifact_digest = stable_digest(artifact_material)
    return {
        "artifact_type": "shortpick_v3_rolling_account_execution_snapshot",
        "schema_version": "shortpick_v3_rolling_account_execution_snapshot.v1",
        "artifact_id": f"shortpick-v3-execution-snapshot-{artifact_digest[:16]}",
        "status": "ready",
        "claim_ceiling": "deterministic_historical_account_replay_input",
        "trial_id": trial_id,
        "source_lineage": deepcopy(source_lineage),
        "input_content_digest": input_digest,
        "output_content_digest": output_digest,
        "input_counts": {
            "selected_pick_count": len(trial.get("selected_top_k_picks_by_date") or []),
            "candidate_inventory_row_count": len(candidate_inventory_rows),
            "market_bar_symbol_count": len(normalized_bars),
            "market_bar_row_count": sum(len(rows) for rows in normalized_bars.values()),
        },
        "output_counts": {
            "order_ledger_row_count": len(output["order_ledger"]),
            "nav_row_count": len(output["nav_rows"]),
        },
        "inputs": inputs,
        "baseline_output": output,
    }


def write_rolling_account_execution_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with path.open("wb") as raw_handle:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
                with io.TextIOWrapper(gzip_handle, encoding="utf-8") as text_handle:
                    json.dump(payload, text_handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def load_rolling_account_execution_snapshot(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, mode="rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "shortpick_v3_rolling_account_execution_snapshot.v1":
        raise ValueError("unsupported rolling account execution snapshot schema")
    if stable_digest(payload["inputs"]) != payload.get("input_content_digest"):
        raise ValueError("rolling account execution snapshot input digest mismatch")
    if stable_digest(payload["baseline_output"]) != payload.get("output_content_digest"):
        raise ValueError("rolling account execution snapshot output digest mismatch")
    return payload


def stable_digest(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()
