#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from ashare_evidence.model_candidate_runner import (
    _fit_model,
    _iter_artifact_rows,
    _top_k_picks_by_date,
)
from ashare_evidence.model_spec_registry import default_model_specs
from ashare_evidence.rolling_account_execution_snapshot import (
    build_rolling_account_execution_snapshot,
    write_rolling_account_execution_snapshot,
)
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.rolling_tranche_execution_contract import build_shortpick_v3_rolling_tranche_execution_contract
from ashare_evidence.shortpick_strategy_lab_v3_projection import _projection_prediction

R14_CONFIG_ID = (
    "daily_15_tranche_rank_adjusted_r5_093_strong154_replacement_"
    "top5_gap010_fill075_market_cap25_v1"
)
R14_MODEL_SPEC_ID = "negative_month_rank_weight_adjusted_capacity_cluster_v3_top3_20d_v1"
R14_TRIAL_ID = f"{R14_MODEL_SPEC_ID}:trial-000"
FRONTIER_METRICS = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "negative_month_count",
    "worst_monthly_return",
    "skipped_order_rate",
    "skipped_signal_rate",
    "max_single_symbol_exposure_pct",
    "final_nav_cny",
)
LOWER_IS_BETTER = {
    "negative_month_count",
    "skipped_order_rate",
    "skipped_signal_rate",
    "max_single_symbol_exposure_pct",
}


def main() -> int:
    args = _parse_args()
    candidate_run = _load_json(args.candidate_run)
    expected_contract = _load_json(args.r14_contract)
    trial = _trial(candidate_run, args.trial_id)
    params = _trial_params(candidate_run, args.trial_id)
    spec = next(spec for spec in default_model_specs() if spec.get("model_spec_id") == R14_MODEL_SPEC_ID)
    signal_dates = {str(row["as_of_date"]) for row in trial["selected_top_k_picks_by_date"]}

    with tempfile.TemporaryDirectory(prefix="shortpick-r14-october-") as temp_dir:
        return_index = Path(temp_dir) / "feature_returns.sqlite"
        inventory_rows, regenerated_selected, feature_row_count = _build_inventory_and_return_index(
            feature_matrix=args.feature_matrix,
            return_index=return_index,
            signal_dates=signal_dates,
            spec=spec,
            params=params,
            trial_id=args.trial_id,
        )
        selection_validation = _validate_regenerated_selection(
            expected=trial["selected_top_k_picks_by_date"],
            observed=regenerated_selected,
        )
        enriched_run = _enrich_candidate_run(candidate_run, inventory_rows=inventory_rows, trial_id=args.trial_id)
        symbols = {str(row.get("symbol") or "") for row in inventory_rows if row.get("symbol")}
        bars_by_symbol, bar_validation = _reconstruct_bars(
            return_index=return_index,
            hot_database=args.hot_database,
            symbols=symbols,
            end_day=max(signal_dates),
        )

    configurations = _candidate_configurations()
    replay = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=enriched_run,
        trial_id=args.trial_id,
        market_bars_by_symbol=bars_by_symbol,
        initial_cash_cny=200_000.0,
        buy_cost_bps=20.0,
        sell_cost_bps=25.0,
        min_order_notional_cny=250.0,
        candidate_inventory_rows=inventory_rows,
        candidate_configurations=configurations,
    )
    expected_summary = expected_contract["summary"]
    baseline = next(result for result in replay["results"] if result["config_id"] == R14_CONFIG_ID)
    execution_snapshot = None
    if args.execution_snapshot_output is not None:
        baseline_config = next(config for config in configurations if config["config_id"] == R14_CONFIG_ID)
        execution_snapshot = build_rolling_account_execution_snapshot(
            candidate_run=enriched_run,
            trial_id=args.trial_id,
            candidate_inventory_rows=inventory_rows,
            market_bars_by_symbol=bars_by_symbol,
            baseline_config=baseline_config,
            account_profile={
                "initial_cash_cny": 200_000.0,
                "buy_cost_bps": 20.0,
                "sell_cost_bps": 25.0,
                "min_order_notional_cny": 250.0,
                "max_entry_lag_days": 7,
            },
            baseline_result=baseline,
            source_lineage={
                "feature_matrix": str(args.feature_matrix),
                "feature_matrix_artifact_id": _artifact_id(args.feature_matrix),
                "candidate_run": str(args.candidate_run),
                "candidate_run_artifact_id": candidate_run.get("artifact_id"),
                "r14_contract": _portable_source_path(args.r14_contract),
                "market_database": str(args.hot_database),
                "selection_validation": selection_validation,
                "bar_reconstruction_validation": bar_validation,
            },
        )
        write_rolling_account_execution_snapshot(args.execution_snapshot_output, execution_snapshot)
    reproduction = _reproduction_readout(expected=expected_summary, observed=baseline["summary"])
    variant_rows = [
        _variant_readout(result, frontier=expected_summary)
        for result in replay["results"]
    ]
    reconstructed_frontier = variant_rows[0]["summary"]
    for row in variant_rows:
        row["directional_vs_reconstructed_baseline"] = _frontier_gate(
            observed=row["summary"],
            frontier=reconstructed_frontier,
        )
    accepted = [row for row in variant_rows if row["frontier_acceptance"]["passed"] and row["config_id"] != R14_CONFIG_ID]
    status = "completed"
    blockers: list[str] = []
    promotion_blockers: list[str] = []
    if not selection_validation["passed"]:
        blockers.append("regenerated_top3_selection_mismatch")
    if not bar_validation["passed"]:
        blockers.append("feature_return_bar_reconstruction_failed")
    if not reproduction["passed"]:
        promotion_blockers.append("r14_contract_reproduction_mismatch")
    if blockers:
        status = "blocked_invalid_reproduction"
        accepted = []
    elif promotion_blockers:
        status = "completed_research_only_reproduction_gap"
        accepted = []
    payload = {
        "artifact_type": "shortpick_v3_r14_october_optimization_experiment",
        "schema_version": "shortpick_v3_r14_october_optimization_experiment.v1",
        "status": status,
        "claim_ceiling": "historical_account_replay_research_only",
        "source_artifacts": {
            "feature_matrix": str(args.feature_matrix),
            "feature_matrix_artifact_id": _artifact_id(args.feature_matrix),
            "candidate_run": str(args.candidate_run),
            "candidate_run_artifact_id": candidate_run.get("artifact_id"),
            "r14_contract": _portable_source_path(args.r14_contract),
            "hot_database": str(args.hot_database),
        },
        "trial_id": args.trial_id,
        "feature_row_count": feature_row_count,
        "signal_date_count": len(signal_dates),
        "inventory_row_count": len(inventory_rows),
        "inventory_symbol_count": len(symbols),
        "selection_validation": selection_validation,
        "bar_reconstruction_validation": bar_validation,
        "baseline_reproduction": reproduction,
        "variants": variant_rows,
        "accepted_candidate_ids": [row["config_id"] for row in accepted],
        "blocking_gate_ids": blockers,
        "promotion_blocking_gate_ids": promotion_blockers,
        "decision": (
            "replace_r14_with_single_accepted_candidate"
            if len(accepted) == 1
            else "retain_r14_no_candidate_cleared_replacement_gate"
        ),
        "multiple_testing_policy": {
            "families": [
                "short_market_momentum_confirmation",
                "weak_benchmark_defensive_scaling",
            ],
            "variant_count": len(configurations) - 1,
            "promotion_rule": "all_nine_metrics_non_degraded_and_one_10pct_breakthrough_or_one_fewer_negative_month",
            "date_or_symbol_hardcoding": False,
        },
        "execution_snapshot": (
            {
                "artifact_id": execution_snapshot["artifact_id"],
                "path": str(args.execution_snapshot_output),
                "input_content_digest": execution_snapshot["input_content_digest"],
                "output_content_digest": execution_snapshot["output_content_digest"],
                "input_counts": execution_snapshot["input_counts"],
                "output_counts": execution_snapshot["output_counts"],
            }
            if execution_snapshot is not None
            else None
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "output": str(args.output), "decision": payload["decision"]}, ensure_ascii=False))
    return 0 if status.startswith("completed") else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-matrix", type=Path, required=True)
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--hot-database", type=Path, required=True)
    parser.add_argument("--r14-contract", type=Path, required=True)
    parser.add_argument("--trial-id", default=R14_TRIAL_ID)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-snapshot-output", type=Path)
    return parser.parse_args()


def _portable_source_path(path: Path) -> str:
    resolved = path.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        return str(resolved.relative_to(repository_root))
    except ValueError:
        return str(path)


def _build_inventory_and_return_index(
    *,
    feature_matrix: Path,
    return_index: Path,
    signal_dates: set[str],
    spec: dict[str, Any],
    params: dict[str, Any],
    trial_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    selection_policy = spec.get("selection_policy") or {}
    horizon_days = int(spec.get("prediction_horizon_days") or 20)
    fitted_model = _fit_model([], model_spec=spec, params=params)
    inventory_rows: list[dict[str, Any]] = []
    regenerated_selected: list[dict[str, Any]] = []
    current_date: str | None = None
    predictions: list[dict[str, Any]] = []
    row_count = 0
    connection = sqlite3.connect(return_index)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("CREATE TABLE feature_returns(symbol TEXT, day TEXT, return_1d REAL, PRIMARY KEY(symbol, day))")
    return_batch: list[tuple[str, str, float]] = []

    def flush() -> None:
        if not predictions:
            return
        regenerated_selected.extend(
            _top_k_picks_by_date(
                predictions,
                top_k=3,
                selection_policy=selection_policy,
                params=params,
            )
        )
        inventory_rows.extend(
            _top_k_picks_by_date(
                predictions,
                top_k=20,
                selection_policy=selection_policy,
                params=params,
            )
        )
        predictions.clear()

    for feature_row in _iter_artifact_rows(feature_matrix):
        row_count += 1
        as_of_date = str(feature_row.get("as_of_date") or "")
        if current_date is None:
            current_date = as_of_date
        elif as_of_date != current_date:
            flush()
            current_date = as_of_date
        feature_values = feature_row.get("feature_values") or {}
        reversal = feature_values.get("reversal_overheat") or {}
        return_batch.append(
            (str(feature_row.get("symbol") or ""), as_of_date, float(reversal.get("return_1d") or 0.0))
        )
        if len(return_batch) >= 10_000:
            connection.executemany("INSERT OR REPLACE INTO feature_returns VALUES (?, ?, ?)", return_batch)
            return_batch.clear()
        if as_of_date not in signal_dates:
            continue
        predictions.append(
            _projection_prediction(
                feature_row=feature_row,
                spec=spec,
                params=params,
                selection_policy=selection_policy,
                trial_id=trial_id,
                fitted_model=fitted_model,
                fitted_model_digest="deterministic-score-only-no-fit",
                horizon_days=horizon_days,
            )
        )
    flush()
    if return_batch:
        connection.executemany("INSERT OR REPLACE INTO feature_returns VALUES (?, ?, ?)", return_batch)
    connection.commit()
    connection.close()
    return inventory_rows, regenerated_selected, row_count


def _reconstruct_bars(
    *,
    return_index: Path,
    hot_database: Path,
    symbols: set[str],
    end_day: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    return_connection = sqlite3.connect(return_index)
    hot_connection = sqlite3.connect(hot_database)
    feature_returns: dict[str, dict[str, float]] = defaultdict(dict)
    direct_closes: dict[str, dict[str, float]] = defaultdict(dict)
    for symbol_chunk in _chunks(sorted(symbols), 400):
        placeholders = ",".join("?" for _ in symbol_chunk)
        for symbol, day, return_1d in return_connection.execute(
            f"SELECT symbol, day, return_1d FROM feature_returns WHERE symbol IN ({placeholders}) ORDER BY symbol, day",
            symbol_chunk,
        ):
            feature_returns[str(symbol)][str(day)] = float(return_1d)
        for symbol, observed_at, close_price in hot_connection.execute(
            f"""
            SELECT s.symbol, m.observed_at, m.close_price
            FROM market_bars m JOIN stocks s ON s.id = m.stock_id
            WHERE m.timeframe = '1d' AND s.symbol IN ({placeholders})
            ORDER BY s.symbol, m.observed_at
            """,
            symbol_chunk,
        ):
            day = str(observed_at)[:10]
            if day <= end_day:
                direct_closes[str(symbol)][day] = float(close_price)
    return_connection.close()
    hot_connection.close()

    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    missing_anchor_symbols: list[str] = []
    overlap_return_errors: list[float] = []
    for symbol in sorted(symbols):
        returns = feature_returns.get(symbol) or {}
        direct = direct_closes.get(symbol) or {}
        overlap = sorted(set(returns) & set(direct))
        if not overlap:
            missing_anchor_symbols.append(symbol)
            continue
        anchor = overlap[0]
        reconstructed = dict(direct)
        feature_dates = sorted(returns)
        anchor_index = feature_dates.index(anchor)
        current_close = direct[anchor]
        for index in range(anchor_index, 0, -1):
            current_day = feature_dates[index]
            previous_day = feature_dates[index - 1]
            denominator = 1.0 + returns[current_day]
            if denominator <= 0:
                break
            current_close = current_close / denominator
            reconstructed[previous_day] = current_close
        # Only the initial overlap is used to prove the backward reconstruction anchor.
        # Later differences can be legitimate stale-feature rows; execution uses direct closes there.
        for index in range(1, min(len(overlap), 61)):
            previous_day, current_day = overlap[index - 1], overlap[index]
            observed_return = direct[current_day] / direct[previous_day] - 1.0
            overlap_return_errors.append(abs(observed_return - returns[current_day]))
        bars_by_symbol[symbol] = [
            {"day": day, "close": close}
            for day, close in sorted(reconstructed.items())
        ]
    validation = {
        "passed": not missing_anchor_symbols and max(overlap_return_errors, default=0.0) <= 1e-12,
        "requested_symbol_count": len(symbols),
        "reconstructed_symbol_count": len(bars_by_symbol),
        "missing_anchor_symbols": missing_anchor_symbols,
        "overlap_return_check_count": len(overlap_return_errors),
        "max_overlap_return_error": max(overlap_return_errors, default=0.0),
    }
    return bars_by_symbol, validation


def _candidate_configurations() -> list[dict[str, Any]]:
    contract = build_shortpick_v3_rolling_tranche_execution_contract(model_spec_id=R14_MODEL_SPEC_ID)
    baseline = next(config for config in contract["candidate_configurations"] if config["config_id"] == R14_CONFIG_ID)
    rows = [copy.deepcopy(baseline)]
    for threshold in (-0.01, 0.0, 0.01, 0.02):
        candidate = copy.deepcopy(baseline)
        suffix = str(threshold).replace("-", "m").replace(".", "p")
        candidate["config_id"] = f"r14_strong_benchmark10_ge_{suffix}_research_v1"
        candidate["rank1_quality_overlay"]["strong_benchmark_return_10d_min"] = threshold
        rows.append(candidate)
    for threshold, scale in ((-0.02, 0.9), (-0.02, 0.8), (0.0, 0.9)):
        candidate = copy.deepcopy(baseline)
        threshold_suffix = str(threshold).replace("-", "m").replace(".", "p")
        scale_suffix = str(scale).replace(".", "p")
        candidate["config_id"] = f"r14_weak_benchmark20_lt_{threshold_suffix}_scale_{scale_suffix}_research_v1"
        candidate["rank1_quality_overlay"]["weak_benchmark_return_20d_lt"] = threshold
        candidate["rank1_quality_overlay"]["weak_scale"] = scale
        rows.append(candidate)
    return rows


def _enrich_candidate_run(
    candidate_run: dict[str, Any],
    *,
    inventory_rows: list[dict[str, Any]],
    trial_id: str,
) -> dict[str, Any]:
    enriched = copy.deepcopy(candidate_run)
    trial = _trial(enriched, trial_id)
    by_key = {
        (str(row.get("as_of_date") or ""), str(row.get("symbol") or "")): row
        for row in inventory_rows
    }
    trial["selected_top_k_picks_by_date"] = [
        _merge_pick_features(row, by_key.get((str(row.get("as_of_date") or ""), str(row.get("symbol") or ""))))
        for row in trial["selected_top_k_picks_by_date"]
    ]
    return enriched


def _merge_pick_features(selected: dict[str, Any], inventory: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(inventory, dict):
        return dict(selected)
    features = inventory.get("rank_weight_feature_values")
    return {
        **selected,
        "rank_weight_feature_values": dict(features) if isinstance(features, dict) else {},
        "benchmark_return_10d": (features or {}).get("benchmark_return_10d") if isinstance(features, dict) else None,
    }


def _validate_regenerated_selection(
    *,
    expected: list[dict[str, Any]],
    observed: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_keys = [(row.get("as_of_date"), int(float(row.get("rank") or 0)), row.get("symbol")) for row in expected]
    observed_keys = [(row.get("as_of_date"), int(float(row.get("rank") or 0)), row.get("symbol")) for row in observed]
    mismatches = [
        {"expected": expected_row, "observed": observed_row}
        for expected_row, observed_row in zip(expected_keys, observed_keys, strict=False)
        if expected_row != observed_row
    ]
    return {
        "passed": len(expected_keys) == len(observed_keys) and not mismatches,
        "expected_count": len(expected_keys),
        "observed_count": len(observed_keys),
        "mismatch_count": len(mismatches) + abs(len(expected_keys) - len(observed_keys)),
        "mismatch_samples": mismatches[:10],
    }


def _reproduction_readout(*, expected: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    tolerances = {
        "negative_month_count": 0.0,
        "buy_order_count": 0.0,
        "sell_order_count": 0.0,
        "final_nav_cny": 0.02,
    }
    checks: dict[str, Any] = {}
    for metric in (*FRONTIER_METRICS, "buy_order_count", "sell_order_count"):
        expected_value = float(expected[metric])
        observed_value = float(observed[metric])
        tolerance = tolerances.get(metric, 1e-10)
        checks[metric] = {
            "expected": expected_value,
            "observed": observed_value,
            "absolute_delta": observed_value - expected_value,
            "passed": abs(observed_value - expected_value) <= tolerance,
        }
    return {"passed": all(row["passed"] for row in checks.values()), "checks": checks}


def _variant_readout(result: dict[str, Any], *, frontier: dict[str, Any]) -> dict[str, Any]:
    summary = result["summary"]
    monthly = result["monthly_returns"]
    gate_checks: dict[str, bool] = {}
    breakthroughs: dict[str, float] = {}
    for metric in FRONTIER_METRICS:
        observed = float(summary[metric])
        baseline = float(frontier[metric])
        if metric in LOWER_IS_BETTER:
            gate_checks[metric] = observed <= baseline + 1e-12
            if baseline > 0:
                breakthroughs[metric] = (baseline - observed) / baseline
        else:
            gate_checks[metric] = observed + 1e-12 >= baseline
            denominator = abs(baseline)
            if denominator > 0:
                breakthroughs[metric] = (observed - baseline) / denominator
    negative_month_reduction = int(frontier["negative_month_count"]) - int(summary["negative_month_count"])
    passed_breakthrough = negative_month_reduction >= 1 or any(value >= 0.10 for value in breakthroughs.values())
    return {
        "config_id": result["config_id"],
        "strong_benchmark_return_10d_min": (
            (result["config"].get("rank1_quality_overlay") or {}).get("strong_benchmark_return_10d_min")
        ),
        "summary": {metric: summary[metric] for metric in FRONTIER_METRICS},
        "october_2025_return": next(
            (row["return"] for row in monthly if row["month"] == "2025-10"),
            None,
        ),
        "negative_months": [row for row in monthly if row["return"] < 0],
        "replacement_buy_count": sum(
            1 for row in result["order_ledger"] if row.get("reason") == "bought_affordable_rank4_5_replacement"
        ),
        "rebalance_sell_count": sum(
            1 for row in result["order_ledger"] if row.get("reason") == "market_value_concentration_rebalance"
        ),
        "frontier_acceptance": {
            "passed": all(gate_checks.values()) and passed_breakthrough,
            "all_nine_metrics_non_degraded": all(gate_checks.values()),
            "breakthrough": passed_breakthrough,
            "negative_month_reduction": negative_month_reduction,
            "checks": gate_checks,
            "relative_improvements": breakthroughs,
        },
    }


def _frontier_gate(*, observed: dict[str, Any], frontier: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    improvements: dict[str, float] = {}
    for metric in FRONTIER_METRICS:
        observed_value = float(observed[metric])
        baseline_value = float(frontier[metric])
        if metric in LOWER_IS_BETTER:
            checks[metric] = observed_value <= baseline_value + 1e-12
            improvements[metric] = (
                (baseline_value - observed_value) / abs(baseline_value) if baseline_value else 0.0
            )
        else:
            checks[metric] = observed_value + 1e-12 >= baseline_value
            improvements[metric] = (
                (observed_value - baseline_value) / abs(baseline_value) if baseline_value else 0.0
            )
    negative_month_reduction = int(frontier["negative_month_count"]) - int(observed["negative_month_count"])
    breakthrough = negative_month_reduction >= 1 or any(value >= 0.10 for value in improvements.values())
    return {
        "all_nine_metrics_non_degraded": all(checks.values()),
        "breakthrough": breakthrough,
        "passed": all(checks.values()) and breakthrough,
        "negative_month_reduction": negative_month_reduction,
        "checks": checks,
        "relative_improvements": improvements,
    }


def _trial(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    return next(row for row in candidate_run["trial_diagnostics"] if row.get("trial_id") == trial_id)


def _trial_params(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    return dict(next(row for row in candidate_run["trial_summaries"] if row.get("trial_id") == trial_id)["params"])


def _artifact_id(path: Path) -> str | None:
    with path.open(encoding="utf-8") as handle:
        for _ in range(40):
            line = handle.readline()
            if '"artifact_id"' not in line:
                continue
            return str(json.loads("{" + line.strip().rstrip(",") + "}")["artifact_id"])
    return None


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
