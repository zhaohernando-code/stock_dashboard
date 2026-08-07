#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import runpy
import sqlite3
import tempfile
from pathlib import Path

from ashare_evidence.model_spec_registry import default_model_specs
from ashare_evidence.rolling_account_execution_snapshot import (
    build_rolling_account_execution_snapshot,
    load_rolling_account_execution_snapshot,
    stable_digest,
    write_rolling_account_execution_snapshot,
)
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a PIT model window to a frozen V3 execution snapshot.")
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--incremental-feature-matrix", type=Path, required=True)
    parser.add_argument("--incremental-candidate-run", type=Path, required=True)
    parser.add_argument("--hot-database", type=Path, required=True)
    parser.add_argument("--end-day", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load_rolling_account_execution_snapshot(args.source_snapshot)
    incremental_run = json.loads(args.incremental_candidate_run.read_text(encoding="utf-8"))
    trial_id = str(source["trial_id"])
    incremental_trial = next(row for row in incremental_run["trial_diagnostics"] if row["trial_id"] == trial_id)
    old_trial = source["inputs"]["candidate_run"]["trial_diagnostics"][0]
    old_end = max(str(row["as_of_date"]) for row in old_trial["selected_top_k_picks_by_date"])
    incremental_expected = [
        row for row in incremental_trial["selected_top_k_picks_by_date"] if str(row["as_of_date"]) > old_end
    ]
    signal_dates = {str(row["as_of_date"]) for row in incremental_expected}
    if not signal_dates:
        raise ValueError("incremental candidate run has no signal dates after the source snapshot")

    helper_path = Path(__file__).with_name("research-shortpick-v3-r14-october-optimization.py")
    helpers = runpy.run_path(str(helper_path))
    params = dict(
        next(row for row in incremental_run["trial_summaries"] if row.get("trial_id") == trial_id)["params"]
    )
    model_spec_id = str(incremental_trial["model_spec_id"])
    spec = next(row for row in default_model_specs() if row.get("model_spec_id") == model_spec_id)
    with tempfile.TemporaryDirectory(prefix="extend-v3-execution-") as temp_dir:
        return_index = Path(temp_dir) / "feature_returns.sqlite"
        inventory, regenerated, feature_row_count = helpers["_build_inventory_and_return_index"](
            feature_matrix=args.incremental_feature_matrix,
            return_index=return_index,
            signal_dates=signal_dates,
            spec=spec,
            params=params,
            trial_id=trial_id,
        )
    validation = helpers["_validate_regenerated_selection"](
        expected=incremental_expected,
        observed=regenerated,
    )
    if not validation["passed"]:
        raise ValueError(f"incremental selection mismatch: {validation}")
    enriched_incremental = helpers["_enrich_candidate_run"](
        incremental_run,
        inventory_rows=inventory,
        trial_id=trial_id,
    )
    enriched_trial = next(row for row in enriched_incremental["trial_diagnostics"] if row["trial_id"] == trial_id)
    incremental_selected = [
        row for row in enriched_trial["selected_top_k_picks_by_date"] if str(row["as_of_date"]) > old_end
    ]

    merged_candidate_run = copy.deepcopy(source["inputs"]["candidate_run"])
    merged_trial = merged_candidate_run["trial_diagnostics"][0]
    merged_trial["selected_top_k_picks_by_date"] = sorted(
        [*merged_trial["selected_top_k_picks_by_date"], *incremental_selected],
        key=lambda row: (str(row["as_of_date"]), int(float(row["rank"]))),
    )
    merged_candidate_run["artifact_id"] = f"extended-{stable_digest(merged_trial['selected_top_k_picks_by_date'])[:16]}"
    merged_inventory = sorted(
        [*source["inputs"]["candidate_inventory_rows"], *inventory],
        key=lambda row: (str(row["as_of_date"]), int(float(row["rank"])), str(row["symbol"])),
    )
    merged_bars = copy.deepcopy(source["inputs"]["market_bars_by_symbol"])
    symbols = {str(row["symbol"]) for row in merged_inventory}
    connection = sqlite3.connect(f"file:{args.hot_database}?immutable=1", uri=True)
    appended_bar_count = 0
    for chunk_start in range(0, len(symbols), 400):
        chunk = sorted(symbols)[chunk_start : chunk_start + 400]
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"""
            SELECT s.symbol, substr(m.observed_at, 1, 10), m.close_price
            FROM market_bars m JOIN stocks s ON s.id = m.stock_id
            WHERE m.timeframe = '1d' AND s.symbol IN ({placeholders})
              AND substr(m.observed_at, 1, 10) > ? AND substr(m.observed_at, 1, 10) <= ?
            ORDER BY s.symbol, m.observed_at
            """,
            [*chunk, old_end, args.end_day],
        )
        for symbol, day, close in rows:
            target = merged_bars.setdefault(str(symbol), [])
            if not any(str(row["day"]) == str(day) for row in target):
                target.append({"day": str(day), "close": float(close)})
                appended_bar_count += 1
    connection.close()
    for rows in merged_bars.values():
        rows.sort(key=lambda row: str(row["day"]))

    baseline = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=merged_candidate_run,
        trial_id=trial_id,
        market_bars_by_symbol=merged_bars,
        candidate_inventory_rows=merged_inventory,
        candidate_configurations=[copy.deepcopy(source["inputs"]["baseline_config"])],
        **source["inputs"]["account_profile"],
    )["results"][0]
    source_prefix_orders = [
        row
        for row in source["baseline_output"]["order_ledger"]
        if str(row.get("trade_day") or "") <= old_end and row.get("action") in {"buy", "sell"}
    ]
    observed_prefix_orders = [
        row
        for row in baseline["order_ledger"]
        if str(row.get("trade_day") or "") <= old_end and row.get("action") in {"buy", "sell"}
    ]
    source_prefix_nav = [row for row in source["baseline_output"]["nav_rows"] if str(row["day"]) <= old_end]
    observed_prefix_nav = [row for row in baseline["nav_rows"] if str(row["day"]) <= old_end]
    prefix_validation = {
        "order_ledger_match": stable_digest(source_prefix_orders) == stable_digest(observed_prefix_orders),
        "nav_match": stable_digest(source_prefix_nav) == stable_digest(observed_prefix_nav),
        "source_order_count": len(source_prefix_orders),
        "observed_order_count": len(observed_prefix_orders),
        "resolved_source_terminal_missing_entry_bar_count": sum(
            row.get("reason") == "missing_entry_bar" and str(row.get("signal_day") or "") == old_end
            for row in source["baseline_output"]["order_ledger"]
        ),
    }
    prefix_validation["passed"] = bool(
        prefix_validation["order_ledger_match"] and prefix_validation["nav_match"]
    )
    if not prefix_validation["passed"]:
        mismatch_index = next(
            (
                index
                for index, (left, right) in enumerate(
                    zip(source_prefix_orders, observed_prefix_orders, strict=False)
                )
                if left != right
            ),
            None,
        )
        prefix_validation["first_order_mismatch"] = (
            None
            if mismatch_index is None
            else {
                "index": mismatch_index,
                "source": source_prefix_orders[mismatch_index],
                "observed": observed_prefix_orders[mismatch_index],
            }
        )
        raise ValueError(f"source account prefix changed: {prefix_validation}")
    snapshot = build_rolling_account_execution_snapshot(
        candidate_run=merged_candidate_run,
        trial_id=trial_id,
        candidate_inventory_rows=merged_inventory,
        market_bars_by_symbol=merged_bars,
        baseline_config=source["inputs"]["baseline_config"],
        account_profile=source["inputs"]["account_profile"],
        baseline_result=baseline,
        source_lineage={
            **source["source_lineage"],
            "parent_execution_snapshot_id": source["artifact_id"],
            "incremental_feature_matrix": str(args.incremental_feature_matrix),
            "incremental_candidate_run": str(args.incremental_candidate_run),
            "incremental_selection_validation": validation,
            "prefix_validation": prefix_validation,
            "feature_row_count": feature_row_count,
            "appended_bar_count": appended_bar_count,
        },
    )
    write_rolling_account_execution_snapshot(args.output, snapshot)
    print(
        json.dumps(
            {
                "artifact_id": snapshot["artifact_id"],
                "old_end": old_end,
                "new_end": args.end_day,
                "incremental_signal_date_count": len(signal_dates),
                "incremental_selected_pick_count": len(incremental_selected),
                "incremental_inventory_row_count": len(inventory),
                "appended_bar_count": appended_bar_count,
                "prefix_validation": prefix_validation,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
