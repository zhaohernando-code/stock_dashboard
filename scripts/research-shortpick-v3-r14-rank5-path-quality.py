#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

from ashare_evidence.rank5_path_quality import (
    PATH_QUALITY_FEATURE_KEYS,
    enrich_inventory_with_path_quality_features,
)
from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
)
from ashare_evidence.rolling_tranche_account_replay import (
    build_shortpick_v3_rolling_account_replay_artifact,
    rank5_replacement_quality_rejection_reason,
)

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
FORBIDDEN_OUTCOME_FIELDS = {
    "net_excess_return",
    "weighted_net_excess_return",
    "future_price",
    "future_return",
    "close_after_signal_day",
}


def main() -> int:
    args = _parse_args()
    snapshot = load_rolling_account_execution_snapshot(args.execution_snapshot)
    frozen_contract = json.loads(args.r14_contract.read_text(encoding="utf-8"))
    design = json.loads(args.design.read_text(encoding="utf-8"))
    _validate_design(design, snapshot=snapshot)
    inputs = snapshot["inputs"]

    exact_baseline_replay = _replay(
        inputs,
        trial_id=snapshot["trial_id"],
        inventory_rows=inputs["candidate_inventory_rows"],
        configurations=[copy.deepcopy(inputs["baseline_config"])],
    )
    baseline = exact_baseline_replay["results"][0]
    observed_output_digest = stable_digest(_snapshot_output(baseline))
    exact_replay = observed_output_digest == snapshot["output_content_digest"]

    enriched_inventory = enrich_inventory_with_path_quality_features(
        inputs["candidate_inventory_rows"],
        market_bars_by_symbol=inputs["market_bars_by_symbol"],
    )
    candidate_replay = _replay(
        inputs,
        trial_id=snapshot["trial_id"],
        inventory_rows=enriched_inventory,
        configurations=_candidate_configurations(inputs["baseline_config"], design=design),
    )
    baseline_summary = baseline["summary"]
    frozen_summary = frozen_contract["summary"]
    variants = [
        _variant_readout(baseline, baseline=baseline_summary, frozen_frontier=frozen_summary),
        *[
            _variant_readout(result, baseline=baseline_summary, frozen_frontier=frozen_summary)
            for result in candidate_replay["results"]
        ],
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
    if accepted:
        promotion_blockers.append("forward_path_feature_builder_parity_not_implemented")

    coverage = _feature_coverage(enriched_inventory)
    payload = {
        "artifact_type": "shortpick_v3_r14_rank5_path_quality_experiment",
        "schema_version": "shortpick_v3_r14_rank5_path_quality_experiment.v1",
        "status": "completed" if exact_replay else "blocked_invalid_execution_snapshot_replay",
        "claim_ceiling": "deterministic_historical_account_replay_research_only",
        "source_design": {
            "path": "docs/contracts/SHORTPICK_V3_R14_RANK5_PATH_QUALITY_DESIGN_2026-07-15.json",
            "content_digest": stable_digest(design),
            "status": design["status"],
            "variant_count": len(design["candidate_variants"]),
        },
        "source_execution_snapshot": {
            "artifact_id": snapshot["artifact_id"],
            "relative_runtime_path": (
                "research_validation/rolling_account_execution_snapshots/"
                f"{snapshot['artifact_id']}.json.gz"
            ),
            "expected_output_content_digest": snapshot["output_content_digest"],
            "observed_output_content_digest": observed_output_digest,
            "exact_replay": exact_replay,
            "input_counts": snapshot["input_counts"],
            "output_counts": snapshot["output_counts"],
        },
        "feature_contract_validation": {
            "feature_keys": list(PATH_QUALITY_FEATURE_KEYS),
            "forbidden_outcome_fields": sorted(FORBIDDEN_OUTCOME_FIELDS),
            "outcome_fields_used_for_candidate_selection": [],
            "date_or_symbol_hardcoding": False,
            "signal_day_or_earlier_only": True,
            "coverage": coverage,
            "passed": coverage["rank5_complete_feature_rate"] == 1.0,
        },
        "frozen_r14_contract": {
            "artifact_id": frozen_contract["artifact_id"],
            "path": "docs/contracts/SHORTPICK_V3_R14_QUALITY_REPLACEMENT_REBALANCE_2026-07-10.json",
            "baseline_reproduces_contract": _metric_equality(baseline_summary, frozen_summary),
        },
        "baseline_rank5_diagnostics": _rank5_diagnostics(
            baseline,
            inventory_rows=enriched_inventory,
            candidate_designs=design["candidate_variants"],
        ),
        "rank5_inventory_feature_distribution": _feature_distribution(enriched_inventory),
        "multiple_testing_policy": design["multiple_testing_policy"],
        "variants": variants,
        "accepted_research_candidate_ids": [row["config_id"] for row in accepted],
        "promotion_blocking_gate_ids": promotion_blockers,
        "decision": (
            "research_candidate_cleared_metrics_but_requires_forward_parity"
            if accepted
            else "retain_r14_no_rank5_path_quality_candidate_cleared_gate"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "decision": payload["decision"],
                "accepted_research_candidate_ids": payload["accepted_research_candidate_ids"],
                "promotion_blocking_gate_ids": promotion_blockers,
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if exact_replay and coverage["rank5_complete_feature_rate"] == 1.0 else 1


def _replay(
    inputs: dict[str, Any],
    *,
    trial_id: str,
    inventory_rows: list[dict[str, Any]],
    configurations: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=inputs["candidate_run"],
        trial_id=trial_id,
        market_bars_by_symbol=inputs["market_bars_by_symbol"],
        candidate_inventory_rows=inventory_rows,
        candidate_configurations=configurations,
        **inputs["account_profile"],
    )


def _validate_design(design: dict[str, Any], *, snapshot: dict[str, Any]) -> None:
    if design.get("status") != "frozen_before_candidate_outcome_evaluation":
        raise ValueError("Rank5 path-quality design must be frozen before candidate evaluation")
    source = design.get("source_execution_snapshot") or {}
    if source.get("artifact_id") != snapshot.get("artifact_id"):
        raise ValueError("Rank5 path-quality design snapshot does not match replay snapshot")
    variants = design.get("candidate_variants") or []
    if len(variants) != 6 or int(design["multiple_testing_policy"]["variant_count"]) != 6:
        raise ValueError("Rank5 path-quality design must contain exactly six preregistered variants")
    forbidden = set((design.get("feature_availability_contract") or {}).get("forbidden_fields") or [])
    if not FORBIDDEN_OUTCOME_FIELDS.issubset(forbidden):
        raise ValueError("Rank5 path-quality design must explicitly forbid outcome and future fields")


def _candidate_configurations(baseline: dict[str, Any], *, design: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for variant in design["candidate_variants"]:
        candidate = copy.deepcopy(baseline)
        candidate["config_id"] = variant["config_id"]
        candidate["affordable_replacement_policy"]["rank5_quality_policy"] = copy.deepcopy(
            variant["rank5_quality_policy"]
        )
        rows.append(candidate)
    return rows


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
    replacement_counts = Counter(
        int(row.get("replacement_inventory_rank") or 0)
        for row in result["order_ledger"]
        if row.get("reason") == "bought_affordable_rank4_5_replacement"
    )
    return {
        "config_id": result["config_id"],
        "rank5_quality_policy": (result["config"].get("affordable_replacement_policy") or {}).get(
            "rank5_quality_policy"
        ),
        "summary": {
            **{metric: summary[metric] for metric in FRONTIER_METRICS},
            "mean_invested_ratio": summary["mean_invested_ratio"],
            "p95_invested_ratio": summary["p95_invested_ratio"],
            "buy_order_count": summary["buy_order_count"],
            "sell_order_count": summary["sell_order_count"],
            "turnover": summary["turnover"],
        },
        "replacement_buy_count": sum(replacement_counts.values()),
        "replacement_buy_count_by_inventory_rank": {
            str(rank): count for rank, count in sorted(replacement_counts.items())
        },
        "vs_reproducible_baseline": _frontier_gate(observed=summary, frontier=baseline),
        "vs_frozen_r14_contract": _frontier_gate(observed=summary, frontier=frozen_frontier),
    }


def _feature_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rank5 = [row for row in rows if int(float(row.get("rank") or 0)) == 5]
    complete = [row for row in rank5 if all(row.get(key) is not None for key in PATH_QUALITY_FEATURE_KEYS)]
    return {
        "inventory_row_count": len(rows),
        "rank5_row_count": len(rank5),
        "rank5_complete_feature_count": len(complete),
        "rank5_complete_feature_rate": len(complete) / len(rank5) if rank5 else 0.0,
        "rank5_observation_count_min": min(
            (int(row.get("path_feature_observation_count") or 0) for row in rank5), default=0
        ),
        "rank5_observation_count_max": max(
            (int(row.get("path_feature_observation_count") or 0) for row in rank5), default=0
        ),
    }


def _rank5_diagnostics(
    baseline: dict[str, Any],
    *,
    inventory_rows: list[dict[str, Any]],
    candidate_designs: list[dict[str, Any]],
) -> dict[str, Any]:
    inventory_by_key = {
        (str(row.get("as_of_date") or ""), str(row.get("symbol") or "")): row
        for row in inventory_rows
    }
    closed = []
    for row in baseline["order_ledger"]:
        if row.get("action") != "sell" or int(row.get("replacement_inventory_rank") or 0) != 5:
            continue
        features = inventory_by_key.get((str(row.get("signal_day") or ""), str(row.get("symbol") or "")))
        if features is None:
            continue
        closed.append(
            {
                **{feature: features.get(feature) for feature in PATH_QUALITY_FEATURE_KEYS},
                "pnl_cny": float(row["pnl_cny"]),
                "return": float(row["return"]),
                "profitable": float(row["pnl_cny"]) > 0,
            }
        )
    feature_readout: dict[str, Any] = {}
    for feature in PATH_QUALITY_FEATURE_KEYS:
        values = [float(row[feature]) for row in closed if row.get(feature) is not None]
        winners = [float(row[feature]) for row in closed if row.get(feature) is not None and row["profitable"]]
        losers = [float(row[feature]) for row in closed if row.get(feature) is not None and not row["profitable"]]
        feature_readout[feature] = {
            "non_null_count": len(values),
            "overall_median": median(values) if values else None,
            "winner_median": median(winners) if winners else None,
            "loser_median": median(losers) if losers else None,
            "overall_mean": mean(values) if values else None,
        }
    policy_coverage = {}
    for design in candidate_designs:
        policy = design["rank5_quality_policy"]
        passed = sum(
            rank5_replacement_quality_rejection_reason(
                row,
                inventory_rank=5,
                original_score=0.0,
                policy=policy,
            )
            is None
            for row in closed
        )
        policy_coverage[design["config_id"]] = {
            "closed_rank5_row_count": len(closed),
            "feature_only_pass_count": passed,
            "feature_only_pass_rate": passed / len(closed) if closed else 0.0,
        }
    return {
        "closed_rank5_count": len(closed),
        "profitable_closed_count": sum(row["profitable"] for row in closed),
        "profitable_closed_rate": sum(row["profitable"] for row in closed) / len(closed) if closed else 0.0,
        "closed_total_pnl_cny": sum(row["pnl_cny"] for row in closed),
        "feature_outcome_diagnostic": feature_readout,
        "preregistered_policy_feature_only_coverage": policy_coverage,
        "interpretation_limit": (
            "Winner and loser medians are post-hoc diagnostics only; candidate decisions use full account replay."
        ),
    }


def _feature_distribution(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int | None]]:
    rank5 = [row for row in rows if int(float(row.get("rank") or 0)) == 5]
    output: dict[str, dict[str, float | int | None]] = {}
    for feature in PATH_QUALITY_FEATURE_KEYS:
        values = sorted(float(row[feature]) for row in rank5 if row.get(feature) is not None)
        output[feature] = {
            "count": len(values),
            "min": values[0] if values else None,
            "p10": _percentile(values, 0.10),
            "p25": _percentile(values, 0.25),
            "median": _percentile(values, 0.50),
            "p75": _percentile(values, 0.75),
            "p90": _percentile(values, 0.90),
            "max": values[-1] if values else None,
            "mean": mean(values) if values else None,
        }
    return output


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--r14-contract", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
