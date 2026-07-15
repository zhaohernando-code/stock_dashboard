#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
)
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

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
    snapshot = load_rolling_account_execution_snapshot(args.execution_snapshot)
    frozen_contract = json.loads(args.r14_contract.read_text(encoding="utf-8"))
    inputs = snapshot["inputs"]
    configurations = _candidate_configurations(inputs["baseline_config"])
    replay = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=inputs["candidate_run"],
        trial_id=snapshot["trial_id"],
        market_bars_by_symbol=inputs["market_bars_by_symbol"],
        candidate_inventory_rows=inputs["candidate_inventory_rows"],
        candidate_configurations=configurations,
        **inputs["account_profile"],
    )
    baseline = replay["results"][0]
    baseline_output = _snapshot_output(baseline)
    observed_output_digest = stable_digest(baseline_output)
    exact_replay = observed_output_digest == snapshot["output_content_digest"]
    baseline_summary = baseline["summary"]
    frozen_summary = frozen_contract["summary"]
    variants = [
        _variant_readout(result, baseline=baseline_summary, frozen_frontier=frozen_summary)
        for result in replay["results"]
    ]
    accepted = [
        row
        for row in variants[1:]
        if row["vs_reproducible_baseline"]["passed"] and row["vs_frozen_r14_contract"]["passed"]
    ]
    promotion_blockers: list[str] = []
    if not exact_replay:
        promotion_blockers.append("execution_snapshot_output_digest_mismatch")
        accepted = []
    if len(accepted) > 1:
        promotion_blockers.append("multiple_candidates_clear_replacement_gate")
        accepted = []
    payload = {
        "artifact_type": "shortpick_v3_r14_execution_efficiency_experiment",
        "schema_version": "shortpick_v3_r14_execution_efficiency_experiment.v1",
        "status": "completed" if exact_replay else "blocked_invalid_execution_snapshot_replay",
        "claim_ceiling": "deterministic_historical_account_replay",
        "source_execution_snapshot": {
            "artifact_id": snapshot["artifact_id"],
            "relative_runtime_path": (
                "research_validation/rolling_account_execution_snapshots/"
                f"{snapshot['artifact_id']}.json.gz"
            ),
            "input_content_digest": snapshot["input_content_digest"],
            "expected_output_content_digest": snapshot["output_content_digest"],
            "observed_output_content_digest": observed_output_digest,
            "exact_replay": exact_replay,
            "input_counts": snapshot["input_counts"],
            "output_counts": snapshot["output_counts"],
        },
        "frozen_r14_contract": {
            "artifact_id": frozen_contract["artifact_id"],
            "path": "docs/contracts/SHORTPICK_V3_R14_QUALITY_REPLACEMENT_REBALANCE_2026-07-10.json",
            "baseline_reproduces_contract": _metric_equality(baseline_summary, frozen_summary),
        },
        "baseline_diagnostics": {
            "replacement_attribution": _replacement_attribution(baseline),
            "cash_deployment": _cash_deployment(baseline),
        },
        "multiple_testing_policy": {
            "families": ["replacement_quality_tightening", "cash_deployment_sizing"],
            "variant_count": len(configurations) - 1,
            "date_or_symbol_hardcoding": False,
            "promotion_rule": (
                "exact_snapshot_replay_and_all_nine_metrics_non_degraded_vs_both_reproducible_baseline_"
                "and_frozen_r14_contract_and_one_10pct_breakthrough_or_one_fewer_negative_month"
            ),
        },
        "variants": variants,
        "accepted_candidate_ids": [row["config_id"] for row in accepted],
        "promotion_blocking_gate_ids": promotion_blockers,
        "decision": (
            "replace_r14_with_single_execution_efficiency_candidate"
            if len(accepted) == 1
            else "retain_r14_no_execution_efficiency_candidate_cleared_gate"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "decision": payload["decision"],
                "accepted_candidate_ids": payload["accepted_candidate_ids"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if exact_replay else 1


def _candidate_configurations(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [copy.deepcopy(baseline)]

    no_replacement = copy.deepcopy(baseline)
    no_replacement["config_id"] = "r14_execution_no_affordable_replacement_research_v1"
    no_replacement.pop("affordable_replacement_policy", None)
    rows.append(no_replacement)

    rank4_only = copy.deepcopy(baseline)
    rank4_only["config_id"] = "r14_execution_replacement_rank4_only_research_v1"
    rank4_only["affordable_replacement_policy"]["inventory_rank_max"] = 4
    rows.append(rank4_only)

    score_gap_005 = copy.deepcopy(baseline)
    score_gap_005["config_id"] = "r14_execution_replacement_score_gap005_research_v1"
    score_gap_005["affordable_replacement_policy"]["max_score_gap"] = 0.05
    rows.append(score_gap_005)

    fill_090 = copy.deepcopy(baseline)
    fill_090["config_id"] = "r14_execution_replacement_fill090_research_v1"
    fill_090["affordable_replacement_policy"]["min_fill_ratio"] = 0.90
    rows.append(fill_090)

    rows.append(_deployment_candidate(baseline, target_tranches=14, deployment_cap=0.07))
    rows.append(_deployment_candidate(baseline, target_tranches=13, deployment_cap=0.075))
    rows.append(_deployment_candidate(baseline, target_tranches=12, deployment_cap=0.08))

    rank4_cap7 = _deployment_candidate(baseline, target_tranches=14, deployment_cap=0.07)
    rank4_cap7["config_id"] = "r14_execution_replacement_rank4_only_deployment070_research_v1"
    rank4_cap7["affordable_replacement_policy"]["inventory_rank_max"] = 4
    rows.append(rank4_cap7)
    return rows


def _deployment_candidate(
    baseline: dict[str, Any],
    *,
    target_tranches: int,
    deployment_cap: float,
) -> dict[str, Any]:
    candidate = copy.deepcopy(baseline)
    suffix = str(deployment_cap).replace(".", "p")
    candidate["config_id"] = f"r14_execution_deployment_cap_{suffix}_research_v1"
    candidate["target_active_tranche_count"] = target_tranches
    candidate["max_single_signal_deployment_pct"] = deployment_cap
    return candidate


def _snapshot_output(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in ("config_id", "summary", "reason_counts", "monthly_returns", "order_ledger", "nav_rows")
    }


def _variant_readout(
    result: dict[str, Any],
    *,
    baseline: dict[str, Any],
    frozen_frontier: dict[str, Any],
) -> dict[str, Any]:
    summary = result["summary"]
    return {
        "config_id": result["config_id"],
        "summary": {
            **{metric: summary[metric] for metric in FRONTIER_METRICS},
            "mean_invested_ratio": summary["mean_invested_ratio"],
            "p95_invested_ratio": summary["p95_invested_ratio"],
            "buy_order_count": summary["buy_order_count"],
            "sell_order_count": summary["sell_order_count"],
            "turnover": summary["turnover"],
        },
        "replacement_buy_count": sum(
            row.get("reason") == "bought_affordable_rank4_5_replacement" for row in result["order_ledger"]
        ),
        "vs_reproducible_baseline": _frontier_gate(observed=summary, frontier=baseline),
        "vs_frozen_r14_contract": _frontier_gate(observed=summary, frontier=frozen_frontier),
    }


def _replacement_attribution(result: dict[str, Any]) -> dict[str, Any]:
    ledger = result["order_ledger"]
    replacement_buys = [
        row for row in ledger if row.get("reason") == "bought_affordable_rank4_5_replacement"
    ]
    replacement_sells = [
        row
        for row in ledger
        if row.get("action") == "sell"
        and row.get("entry_reason") == "bought_affordable_rank4_5_replacement"
    ]
    by_rank: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in replacement_sells:
        by_rank[int(row.get("replacement_inventory_rank") or 0)].append(row)
    return {
        "buy_count": len(replacement_buys),
        "closed_sell_count": len(replacement_sells),
        "open_at_end_count": len(replacement_buys) - len(replacement_sells),
        "profitable_closed_count": sum(float(row["return"]) > 0 for row in replacement_sells),
        "profitable_closed_rate": _safe_ratio(
            sum(float(row["return"]) > 0 for row in replacement_sells), len(replacement_sells)
        ),
        "closed_total_pnl_cny": sum(float(row["pnl_cny"]) for row in replacement_sells),
        "closed_mean_return": mean(float(row["return"]) for row in replacement_sells),
        "closed_median_return": median(float(row["return"]) for row in replacement_sells),
        "by_inventory_rank": {
            str(rank): {
                "closed_count": len(rows),
                "profitable_rate": _safe_ratio(sum(float(row["return"]) > 0 for row in rows), len(rows)),
                "total_pnl_cny": sum(float(row["pnl_cny"]) for row in rows),
                "mean_return": mean(float(row["return"]) for row in rows),
                "median_return": median(float(row["return"]) for row in rows),
            }
            for rank, rows in sorted(by_rank.items())
        },
        "worst_closed_samples": [
            {
                key: row.get(key)
                for key in (
                    "signal_day",
                    "trade_day",
                    "symbol",
                    "stock_name",
                    "replacement_original_symbol",
                    "replacement_inventory_rank",
                    "return",
                    "pnl_cny",
                )
            }
            for row in sorted(replacement_sells, key=lambda item: float(item["return"]))[:10]
        ],
    }


def _cash_deployment(result: dict[str, Any]) -> dict[str, Any]:
    cash_ratios = [1.0 - float(row["invested_ratio"]) for row in result["nav_rows"]]
    return {
        "day_count": len(cash_ratios),
        "mean_cash_ratio": mean(cash_ratios),
        "median_cash_ratio": median(cash_ratios),
        "max_cash_ratio": max(cash_ratios, default=0.0),
        "cash_ratio_at_least_40pct_day_count": sum(value >= 0.40 for value in cash_ratios),
        "cash_ratio_at_least_40pct_day_rate": _safe_ratio(
            sum(value >= 0.40 for value in cash_ratios), len(cash_ratios)
        ),
        "cash_ratio_at_least_50pct_day_count": sum(value >= 0.50 for value in cash_ratios),
        "cash_ratio_at_least_50pct_day_rate": _safe_ratio(
            sum(value >= 0.50 for value in cash_ratios), len(cash_ratios)
        ),
    }


def _metric_equality(observed: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    checks = {
        metric: abs(float(observed[metric]) - float(expected[metric])) <= 1e-12
        for metric in FRONTIER_METRICS
    }
    return {"passed": all(checks.values()), "checks": checks}


def _frontier_gate(*, observed: dict[str, Any], frontier: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    improvements: dict[str, float] = {}
    for metric in FRONTIER_METRICS:
        observed_value = float(observed[metric])
        frontier_value = float(frontier[metric])
        if metric in LOWER_IS_BETTER:
            checks[metric] = observed_value <= frontier_value + 1e-12
            improvements[metric] = (
                (frontier_value - observed_value) / abs(frontier_value) if frontier_value else 0.0
            )
        else:
            checks[metric] = observed_value + 1e-12 >= frontier_value
            improvements[metric] = (
                (observed_value - frontier_value) / abs(frontier_value) if frontier_value else 0.0
            )
    negative_month_reduction = int(frontier["negative_month_count"]) - int(observed["negative_month_count"])
    breakthrough = negative_month_reduction >= 1 or any(value >= 0.10 for value in improvements.values())
    return {
        "passed": all(checks.values()) and breakthrough,
        "all_nine_metrics_non_degraded": all(checks.values()),
        "breakthrough": breakthrough,
        "negative_month_reduction": negative_month_reduction,
        "checks": checks,
        "relative_improvements": improvements,
    }


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--r14-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
