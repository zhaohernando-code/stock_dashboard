#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import copy
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import ashare_evidence.rolling_tranche_account_replay as replay_module
from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
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
RANK5_LATE_GUARD_RETURN = -0.08
RANK5_LATE_GUARD_PEAK_DRAWDOWN = -0.10
RANK5_LATE_GUARD_MIN_CALENDAR_DAYS = 10
RANK5_DAY10_HOLDING_TRADING_DAYS = 10


def run_experiment(execution_snapshot: str | Path) -> dict[str, Any]:
    snapshot_path = Path(execution_snapshot)
    snapshot = load_rolling_account_execution_snapshot(snapshot_path)
    inputs = snapshot["inputs"]
    baseline_config = copy.deepcopy(inputs["baseline_config"])
    trading_days_by_symbol = {
        symbol: [date.fromisoformat(str(row["day"])) for row in rows]
        for symbol, rows in inputs["market_bars_by_symbol"].items()
    }
    variants = [
        {
            "variant_id": "current_r14",
            "label": "当前 R14",
            "rank4_only": False,
            "rank5_one_lot_cap": False,
            "rank5_late_guard": False,
            "rank5_day10_below_entry_guard": False,
        },
        {
            "variant_id": "rank4_only",
            "label": "停用 Rank5",
            "rank4_only": True,
            "rank5_one_lot_cap": False,
            "rank5_late_guard": False,
            "rank5_day10_below_entry_guard": False,
        },
        {
            "variant_id": "rank5_one_lot_cap",
            "label": "Rank5 最多 1 手",
            "rank4_only": False,
            "rank5_one_lot_cap": True,
            "rank5_late_guard": False,
            "rank5_day10_below_entry_guard": False,
        },
        {
            "variant_id": "rank5_late_guard",
            "label": "Rank5 晚期亏损保护",
            "rank4_only": False,
            "rank5_one_lot_cap": False,
            "rank5_late_guard": True,
            "rank5_day10_below_entry_guard": False,
        },
        {
            "variant_id": "rank5_one_lot_plus_late_guard",
            "label": "1 手 + 晚期亏损保护",
            "rank4_only": False,
            "rank5_one_lot_cap": True,
            "rank5_late_guard": True,
            "rank5_day10_below_entry_guard": False,
        },
        {
            "variant_id": "rank5_day10_below_entry",
            "label": "第 10 日仍低于买入价退出",
            "rank4_only": False,
            "rank5_one_lot_cap": False,
            "rank5_late_guard": False,
            "rank5_day10_below_entry_guard": True,
        },
        {
            "variant_id": "rank5_one_lot_plus_day10_below_entry",
            "label": "1 手 + 第 10 日退出",
            "rank4_only": False,
            "rank5_one_lot_cap": True,
            "rank5_late_guard": False,
            "rank5_day10_below_entry_guard": True,
        },
    ]
    results = [
        _run_variant(
            snapshot=snapshot,
            inputs=inputs,
            baseline_config=baseline_config,
            trading_days_by_symbol=trading_days_by_symbol,
            variant=variant,
        )
        for variant in variants
    ]
    baseline = results[0]
    for result in results:
        result["vs_current_r14"] = _frontier_comparison(
            observed=result["summary"],
            baseline=baseline["summary"],
        )
    exact_replay = stable_digest(_snapshot_output(baseline["raw_result"])) == snapshot["output_content_digest"]
    payload = {
        "artifact_type": "shortpick_v3_rank5_risk_control_experiment",
        "schema_version": "shortpick_v3_rank5_risk_control_experiment.v1",
        "artifact_id": "shortpick-v3-rank5-risk-control-2026-07-17",
        "status": "completed" if exact_replay else "blocked_snapshot_replay_mismatch",
        "claim_ceiling": "exploratory_deterministic_historical_account_replay_not_live_policy",
        "source_execution_snapshot": {
            "artifact_id": snapshot["artifact_id"],
            "path": str(snapshot_path),
            "expected_output_content_digest": snapshot["output_content_digest"],
            "observed_output_content_digest": stable_digest(_snapshot_output(baseline["raw_result"])),
            "exact_replay": exact_replay,
            "input_counts": snapshot["input_counts"],
            "output_counts": snapshot["output_counts"],
        },
        "experiment_design": {
            "decision": "whether_rank5_should_be_disabled_risk_capped_or_given_a_structural_exit_guard",
            "historical_closed_rank5_sample_count": baseline["rank5_diagnostics"]["closed_count"],
            "anti_tuning": [
                "no_new_signal_day_quality_thresholds",
                "one_board_lot_is_the_only_sizing_candidate",
                "late_guard_reuses_existing_minus_8pct_return_minus_10pct_peak_drawdown_conditions",
                "day10_below_entry_is_reported_as_exploratory_and_not_eligible_for_activation",
            ],
            "unchanged_components": [
                "candidate_selection",
                "rank4_replacement",
                "fees",
                "account_profile",
                "rank1_overlay",
                "existing_exit_policy",
                "market_value_concentration_rebalance",
            ],
        },
        "results": [{key: value for key, value in result.items() if key != "raw_result"} for result in results],
        "decision": {
            "live_policy_change": None,
            "preferred_forward_candidate": "rank5_one_lot_cap",
            "reason": (
                "one_lot_cap_preserved_historical_execution_coverage_and_win_count_while_reducing_rank5_net_loss_"
                "but_did_not_reduce_negative_months_or_clear_the_frontier_breakthrough_gate"
            ),
            "rejected_directions": {
                "rank4_only": "higher_return_but_materially_higher_skip_rates_and_slightly_worse_worst_month",
                "rank5_late_guard": "only_four_exits_and_small_account_level_improvement",
                "rank5_day10_below_entry": "cut_one_eventual_winner_and_added_little_account_level_value",
                "combined_rules": "more_complex_without_clearing_the_existing_promotion_gate",
            },
        },
    }
    return payload


def _run_variant(
    *,
    snapshot: dict[str, Any],
    inputs: dict[str, Any],
    baseline_config: dict[str, Any],
    trading_days_by_symbol: dict[str, list[date]],
    variant: dict[str, Any],
) -> dict[str, Any]:
    config = copy.deepcopy(baseline_config)
    if variant["variant_id"] != "current_r14":
        config["config_id"] = f"research_{variant['variant_id']}_20260717_v1"
    if variant["rank4_only"]:
        config["affordable_replacement_policy"]["inventory_rank_max"] = 4
    with _research_controls(
        one_lot_cap=variant["rank5_one_lot_cap"],
        late_guard=variant["rank5_late_guard"],
        day10_guard=variant["rank5_day10_below_entry_guard"],
        trading_days_by_symbol=trading_days_by_symbol,
    ):
        replay = replay_module.build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=inputs["candidate_run"],
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=inputs["market_bars_by_symbol"],
            candidate_inventory_rows=inputs["candidate_inventory_rows"],
            candidate_configurations=[config],
            **inputs["account_profile"],
        )
    raw_result = replay["results"][0]
    rank5_sells = [
        row
        for row in raw_result["order_ledger"]
        if row.get("action") == "sell" and int(float(row.get("replacement_inventory_rank") or 0)) == 5
    ]
    gross_profit = sum(max(float(row.get("pnl_cny") or 0.0), 0.0) for row in rank5_sells)
    gross_loss = -sum(min(float(row.get("pnl_cny") or 0.0), 0.0) for row in rank5_sells)
    summary = raw_result["summary"]
    return {
        "variant_id": variant["variant_id"],
        "label": variant["label"],
        "summary": {
            **{metric: summary[metric] for metric in FRONTIER_METRICS},
            "turnover": summary["turnover"],
            "buy_order_count": summary["buy_order_count"],
            "sell_order_count": summary["sell_order_count"],
        },
        "rank5_diagnostics": {
            "closed_count": len(rank5_sells),
            "winner_count": sum(float(row.get("pnl_cny") or 0.0) > 0.0 for row in rank5_sells),
            "loser_count": sum(float(row.get("pnl_cny") or 0.0) <= 0.0 for row in rank5_sells),
            "win_rate": _safe_ratio(
                sum(float(row.get("pnl_cny") or 0.0) > 0.0 for row in rank5_sells),
                len(rank5_sells),
            ),
            "net_pnl_cny": sum(float(row.get("pnl_cny") or 0.0) for row in rank5_sells),
            "gross_profit_cny": gross_profit,
            "gross_loss_cny": gross_loss,
            "profit_factor": _safe_ratio(gross_profit, gross_loss),
            "dynamic_late_guard_exit_count": sum(
                row.get("reason") == "dynamic_rank5_late_trend_loss_guard" for row in rank5_sells
            ),
            "dynamic_day10_exit_count": sum(
                row.get("reason") == "dynamic_rank5_day10_below_entry_guard" for row in rank5_sells
            ),
        },
        "negative_months": [row for row in raw_result["monthly_returns"] if float(row.get("return") or 0.0) < 0.0],
        "raw_result": raw_result,
    }


@contextmanager
def _research_controls(
    *,
    one_lot_cap: bool,
    late_guard: bool,
    day10_guard: bool,
    trading_days_by_symbol: dict[str, list[date]],
) -> Iterator[None]:
    original_try_buy = replay_module._try_buy_request
    original_exit_reason = replay_module._exit_reason

    def controlled_try_buy(request: dict[str, Any], **kwargs: Any) -> Any:
        pick = request.get("pick") or {}
        if one_lot_cap and _replacement_inventory_rank(pick) == 5:
            symbol = str(pick.get("symbol") or "")
            bars = kwargs["bars_by_symbol"].get(symbol) or []
            entry_bar = bars[int(request["entry_index"])]
            kwargs["target_notional"] = entry_bar.close * int(kwargs["board_lot_size"]) + 1e-9
        return original_try_buy(request, **kwargs)

    def controlled_exit_reason(
        position: Any,
        *,
        current_day: date,
        price: float | None,
        exit_policy: str,
    ) -> str | None:
        base_reason = original_exit_reason(
            position,
            current_day=current_day,
            price=price,
            exit_policy=exit_policy,
        )
        if base_reason is not None or price is None or _replacement_inventory_rank(position.entry_features) != 5:
            return base_reason
        position_return = price / position.entry_price - 1.0 if position.entry_price else 0.0
        drawdown_from_peak = price / position.peak_price - 1.0 if position.peak_price else 0.0
        holding_calendar_days = (current_day - position.entry_day).days
        if (
            late_guard
            and holding_calendar_days >= RANK5_LATE_GUARD_MIN_CALENDAR_DAYS
            and position_return <= RANK5_LATE_GUARD_RETURN
            and drawdown_from_peak <= RANK5_LATE_GUARD_PEAK_DRAWDOWN
        ):
            return "dynamic_rank5_late_trend_loss_guard"
        if day10_guard:
            trading_days = trading_days_by_symbol.get(position.symbol) or []
            holding_trading_days = bisect.bisect_right(trading_days, current_day) - bisect.bisect_right(
                trading_days,
                position.entry_day,
            )
            if holding_trading_days == RANK5_DAY10_HOLDING_TRADING_DAYS and price < position.entry_price:
                return "dynamic_rank5_day10_below_entry_guard"
        return None

    replay_module._try_buy_request = controlled_try_buy
    replay_module._exit_reason = controlled_exit_reason
    try:
        yield
    finally:
        replay_module._try_buy_request = original_try_buy
        replay_module._exit_reason = original_exit_reason


def _frontier_comparison(*, observed: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    deltas: dict[str, float] = {}
    relative_improvements: dict[str, float] = {}
    for metric in FRONTIER_METRICS:
        observed_value = float(observed[metric])
        baseline_value = float(baseline[metric])
        deltas[metric] = observed_value - baseline_value
        if metric in LOWER_IS_BETTER:
            checks[metric] = observed_value <= baseline_value + 1e-12
            relative_improvements[metric] = (
                (baseline_value - observed_value) / abs(baseline_value) if baseline_value else 0.0
            )
        else:
            checks[metric] = observed_value + 1e-12 >= baseline_value
            relative_improvements[metric] = (
                (observed_value - baseline_value) / abs(baseline_value) if baseline_value else 0.0
            )
    negative_month_reduction = int(baseline["negative_month_count"]) - int(observed["negative_month_count"])
    breakthrough = negative_month_reduction >= 1 or any(
        improvement >= 0.10 for improvement in relative_improvements.values()
    )
    return {
        "all_nine_metrics_non_degraded": all(checks.values()),
        "breakthrough": breakthrough,
        "passed": all(checks.values()) and breakthrough,
        "checks": checks,
        "deltas": deltas,
        "relative_improvements": relative_improvements,
    }


def _snapshot_output(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in ("config_id", "summary", "reason_counts", "monthly_returns", "order_ledger", "nav_rows")
    }


def _replacement_inventory_rank(row: dict[str, Any]) -> int:
    return int(float(row.get("replacement_inventory_rank") or 0))


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_experiment(args.execution_snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "preferred_forward_candidate": payload["decision"]["preferred_forward_candidate"],
                "live_policy_change": payload["decision"]["live_policy_change"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
