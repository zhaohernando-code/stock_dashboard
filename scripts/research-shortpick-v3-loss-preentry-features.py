#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import copy
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

ACTIVE_CONFIG_ID = (
    "daily_15_tranche_rank_adjusted_r5_093_strong154_replacement_"
    "rank4_gap010_fill075_market_cap25_v1"
)
FUTURE_OUTCOME_FIELDS = {"net_excess_return", "weighted_net_excess_return"}
SOURCE_NUMERIC_FEATURES = (
    "rank",
    "score",
    "return_5d_percentile",
    "return_20d_percentile",
    "turnover_rate_percentile",
    "amount_vs_20d_avg_percentile",
    "amount_10d_vs_20d_percentile",
    "avg_amount_20d",
    "benchmark_return_10d",
    "benchmark_return_20d",
    "industry_return_20d_excess",
    "distance_from_20d_high",
    "date_exposure_scale",
    "date_position_scale",
    "signal_position_scale",
    "rank_position_scale",
    "rank_weight_multiplier",
    "rank_portfolio_adjustment_multiplier",
)
DERIVED_NUMERIC_FEATURES = (
    "pre_return_1d",
    "pre_return_3d",
    "pre_return_5d",
    "pre_return_10d",
    "pre_return_20d",
    "pre_return_60d",
    "pre_volatility_5d",
    "pre_volatility_20d",
    "pre_downside_volatility_20d",
    "pre_max_drawdown_20d",
    "pre_max_drawdown_60d",
    "pre_up_day_ratio_20d",
    "pre_trend_efficiency_20d",
    "pre_distance_ma5",
    "pre_distance_ma20",
    "pre_distance_ma60",
    "pre_distance_high_5d",
    "pre_distance_high_10d",
    "pre_distance_high_20d",
    "pre_distance_high_60d",
    "pre_return_acceleration_5v20",
    "prior_same_symbol_entry_count",
    "prior_same_symbol_entry_count_30d",
    "days_since_prior_same_symbol_signal",
    "prior_closed_same_symbol_count",
    "prior_closed_same_symbol_loss_rate",
    "days_since_prior_same_symbol_loss",
)
ANALYSIS_FEATURES = SOURCE_NUMERIC_FEATURES + DERIVED_NUMERIC_FEATURES
THRESHOLD_QUANTILES = (0.15, 0.25, 0.35, 0.50)
MIN_TRAIN_RULE_COUNT = 30
MIN_VALIDATION_RULE_COUNT = 15


def run_analysis(execution_snapshot: str | Path) -> dict[str, Any]:
    snapshot_path = Path(execution_snapshot)
    snapshot = load_rolling_account_execution_snapshot(snapshot_path)
    result = _run_rank4_only_replay(snapshot)
    trades = _build_trade_feature_frame(snapshot, result)
    trades = _add_repeated_exposure_features(trades)
    cutoff = _time_split_cutoff(trades)
    trades["sample"] = np.where(trades["signal_date"] <= cutoff, "discovery", "validation")
    feature_stats = _feature_statistics(trades)
    single_rules = _discover_single_feature_rules(trades, cutoff)
    pair_rules = _discover_pair_rules(trades, single_rules)
    categorical_patterns = _categorical_patterns(trades)
    data_quality = _data_quality_summary(snapshot, result, trades, cutoff)
    payload = {
        "artifact_type": "shortpick_v3_loss_preentry_feature_exploration",
        "schema_version": "shortpick_v3_loss_preentry_feature_exploration.v1",
        "artifact_id": "shortpick-v3-loss-preentry-feature-exploration-20260717",
        "status": "completed" if data_quality["analysis_ready"] else "blocked_data_quality",
        "claim_ceiling": "exploratory_historical_association_not_causal_or_live_policy",
        "scope": {
            "strategy_config_id": ACTIVE_CONFIG_ID,
            "strategy_label": "稳定盈利前沿：仅 Rank4 可买替补 + 25% 暴露再平衡",
            "unit_of_analysis": "one_closed_entry_cohort_per_symbol_and_signal_date",
            "loss_definition": "closed_trade_net_return_less_than_or_equal_to_zero_after_costs",
            "winner_definition": "closed_trade_net_return_greater_than_zero_after_costs",
            "feature_cutoff": "signal_date_close_or_earlier_only",
            "excluded_open_entries": data_quality["open_entry_count"],
            "future_outcome_fields_excluded": sorted(FUTURE_OUTCOME_FIELDS),
        },
        "source": {
            "execution_snapshot_artifact_id": snapshot["artifact_id"],
            "execution_snapshot_path": str(snapshot_path),
            "input_content_digest": snapshot["input_content_digest"],
            "source_signal_date_from": trades["signal_date"].min().isoformat(),
            "source_signal_date_to": trades["signal_date"].max().isoformat(),
        },
        "data_quality": data_quality,
        "population": _population_summary(trades),
        "feature_statistics": feature_stats,
        "validated_single_feature_patterns": single_rules,
        "validated_pair_patterns": pair_rules,
        "categorical_patterns": categorical_patterns,
        "largest_losses": _largest_trade_samples(trades, ascending=True),
        "largest_wins": _largest_trade_samples(trades, ascending=False),
        "methodology": {
            "discovery_validation_split": (
                "thresholds selected only on the earlier 70 percent of unique signal dates; "
                "the later 30 percent is held out for directional validation"
            ),
            "single_feature_thresholds": list(THRESHOLD_QUANTILES),
            "minimum_rule_counts": {
                "discovery": MIN_TRAIN_RULE_COUNT,
                "validation": MIN_VALIDATION_RULE_COUNT,
            },
            "pattern_metrics": {
                "loss_prevalence": "share of all losing trades that satisfy the pattern",
                "winner_prevalence": "share of all winning trades that satisfy the pattern",
                "prevalence_gap": "loss_prevalence minus winner_prevalence",
                "loss_rate_lift": "loss rate inside pattern divided by the sample baseline loss rate",
            },
            "multiple_testing": "numeric median-separation p-values use Benjamini-Hochberg FDR; threshold rules remain exploratory",
            "causality": "associations do not prove the feature caused the loss",
        },
        "decision": {
            "live_policy_change": None,
            "recommended_next_step": (
                "convert only patterns that remain directionally positive in the held-out period into a small "
                "pre-registered replay experiment; do not add all discovered filters"
            ),
        },
    }
    return _json_safe(payload)


def _run_rank4_only_replay(snapshot: dict[str, Any]) -> dict[str, Any]:
    inputs = snapshot["inputs"]
    config = copy.deepcopy(inputs["baseline_config"])
    config["config_id"] = ACTIVE_CONFIG_ID
    config["affordable_replacement_policy"]["inventory_rank_min"] = 4
    config["affordable_replacement_policy"]["inventory_rank_max"] = 4
    replay = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=inputs["candidate_run"],
        trial_id=snapshot["trial_id"],
        market_bars_by_symbol=inputs["market_bars_by_symbol"],
        candidate_inventory_rows=inputs["candidate_inventory_rows"],
        candidate_configurations=[config],
        **inputs["account_profile"],
    )
    return replay["results"][0]


def _build_trade_feature_frame(snapshot: dict[str, Any], result: dict[str, Any]) -> pd.DataFrame:
    inputs = snapshot["inputs"]
    selected_rows = inputs["candidate_run"]["trial_diagnostics"][0]["selected_top_k_picks_by_date"]
    selected_map = {(str(row["as_of_date"]), str(row["symbol"])): row for row in selected_rows}
    inventory_map = {
        (str(row["as_of_date"]), str(row["symbol"])): row for row in inputs["candidate_inventory_rows"]
    }
    bars_by_symbol = inputs["market_bars_by_symbol"]
    rows: list[dict[str, Any]] = []
    buy_row_map = {
        (str(row["signal_day"]), str(row["symbol"])): row
        for row in result["order_ledger"]
        if row.get("action") == "buy" and row.get("trade_day")
    }
    sell_rows = [
        row
        for row in result["order_ledger"]
        if row.get("action") == "sell" and row.get("reason") != "market_value_concentration_rebalance"
    ]
    partial_rebalance_map = _allocate_partial_rebalance_sales(
        buy_row_map=buy_row_map,
        terminal_sell_rows=sell_rows,
        rebalance_rows=[
            row
            for row in result["order_ledger"]
            if row.get("action") == "sell" and row.get("reason") == "market_value_concentration_rebalance"
        ],
    )
    for sell in sell_rows:
        signal_day = str(sell["signal_day"])
        symbol = str(sell["symbol"])
        trade_key = (signal_day, symbol)
        partial_sales = partial_rebalance_map.get(trade_key, [])
        combined_pnl_cny = float(sell.get("pnl_cny") or 0.0) + sum(
            float(row.get("pnl_cny") or 0.0) for row in partial_sales
        )
        combined_cost_basis_cny = float(sell.get("cost_basis_cny") or 0.0) + sum(
            float(row.get("cost_basis_cny") or 0.0) for row in partial_sales
        )
        source_row = selected_map.get((signal_day, symbol)) or inventory_map.get((signal_day, symbol))
        source = dict(source_row or {})
        for forbidden in FUTURE_OUTCOME_FIELDS:
            source.pop(forbidden, None)
        feature_row: dict[str, Any] = {
            "trade_key": f"{signal_day}|{symbol}",
            "signal_date": date.fromisoformat(signal_day),
            "entry_date": date.fromisoformat(str(buy_row_map[trade_key]["trade_day"])),
            "exit_date": date.fromisoformat(str(sell["trade_day"])),
            "symbol": symbol,
            "stock_name": str(sell.get("stock_name") or source.get("stock_name") or symbol),
            "industry_name": str(source.get("industry_name") or "未分类"),
            "entry_reason": str(sell.get("entry_reason") or ""),
            "exit_reason": str(sell.get("reason") or ""),
            "replacement_inventory_rank": _optional_int(sell.get("replacement_inventory_rank")),
            "entry_type": (
                "rank4_replacement"
                if _optional_int(sell.get("replacement_inventory_rank")) == 4
                else "primary_selection"
            ),
            "trade_return": combined_pnl_cny / combined_cost_basis_cny,
            "pnl_cny": combined_pnl_cny,
            "cost_basis_cny": combined_cost_basis_cny,
            "is_loss": int(combined_pnl_cny <= 0.0),
            "partial_rebalance_event_count": len(partial_sales),
            "feature_joined": source_row is not None,
            "feature_source": (
                "selected_top_k"
                if (signal_day, symbol) in selected_map
                else "ranked_inventory"
                if (signal_day, symbol) in inventory_map
                else "missing"
            ),
        }
        for feature in SOURCE_NUMERIC_FEATURES:
            raw = source.get(feature)
            if feature == "avg_amount_20d":
                feature_row[feature] = math.log1p(float(raw)) if raw is not None else np.nan
            else:
                feature_row[feature] = _optional_float(raw)
        feature_row.update(_pre_signal_close_features(bars_by_symbol.get(symbol) or [], signal_day))
        rows.append(feature_row)
    frame = pd.DataFrame(rows).sort_values(["signal_date", "symbol"]).reset_index(drop=True)
    return frame


def _allocate_partial_rebalance_sales(
    *,
    buy_row_map: dict[tuple[str, str], dict[str, Any]],
    terminal_sell_rows: list[dict[str, Any]],
    rebalance_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    allocations: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rebalance in rebalance_rows:
        symbol = str(rebalance["symbol"])
        rebalance_day = date.fromisoformat(str(rebalance["trade_day"]))
        rebalance_shares = int(rebalance.get("shares") or 0)
        rebalance_unit_cost = float(rebalance.get("cost_basis_cny") or 0.0) / rebalance_shares
        candidates: list[tuple[str, str]] = []
        for sell in terminal_sell_rows:
            trade_key = (str(sell["signal_day"]), str(sell["symbol"]))
            buy = buy_row_map.get(trade_key)
            if buy is None or trade_key[1] != symbol:
                continue
            buy_shares = int(buy.get("shares") or 0)
            terminal_shares = int(sell.get("shares") or 0)
            allocated_shares = sum(int(row.get("shares") or 0) for row in allocations[trade_key])
            buy_unit_cost = float(buy.get("cash_spent_cny") or 0.0) / buy_shares
            exit_day = date.fromisoformat(str(sell["trade_day"]))
            if (
                buy_shares - terminal_shares - allocated_shares >= rebalance_shares
                and date.fromisoformat(str(buy["trade_day"])) <= rebalance_day <= exit_day
                and math.isclose(buy_unit_cost, rebalance_unit_cost, rel_tol=0.0, abs_tol=1e-9)
            ):
                candidates.append(trade_key)
        if len(candidates) != 1:
            raise ValueError(
                f"expected one entry cohort for partial rebalance sale, found {len(candidates)}: {rebalance}"
            )
        allocations[candidates[0]].append(rebalance)
    return dict(allocations)


def _pre_signal_close_features(bars: list[dict[str, Any]], signal_day: str) -> dict[str, float]:
    days = [str(row["day"]) for row in bars]
    index = bisect.bisect_right(days, signal_day) - 1
    if index < 0:
        return {feature: np.nan for feature in DERIVED_NUMERIC_FEATURES if not feature.startswith("prior_") and not feature.startswith("days_")}
    closes = np.asarray([float(row["close"]) for row in bars[: index + 1]], dtype=float)
    output: dict[str, float] = {}
    for window in (1, 3, 5, 10, 20, 60):
        output[f"pre_return_{window}d"] = _window_return(closes, window)
    returns = np.diff(closes) / closes[:-1] if len(closes) >= 2 else np.asarray([], dtype=float)
    output["pre_volatility_5d"] = _tail_std(returns, 5)
    output["pre_volatility_20d"] = _tail_std(returns, 20)
    recent_returns = returns[-20:]
    downside = recent_returns[recent_returns < 0]
    output["pre_downside_volatility_20d"] = float(np.std(downside, ddof=0)) if len(downside) else 0.0
    output["pre_max_drawdown_20d"] = _max_drawdown(closes[-21:])
    output["pre_max_drawdown_60d"] = _max_drawdown(closes[-61:])
    output["pre_up_day_ratio_20d"] = float(np.mean(recent_returns > 0)) if len(recent_returns) else np.nan
    gross_path = float(np.sum(np.abs(recent_returns)))
    output["pre_trend_efficiency_20d"] = (
        abs(float(closes[-1] / closes[-21] - 1.0)) / gross_path
        if len(closes) >= 21 and gross_path > 0
        else np.nan
    )
    for window in (5, 20, 60):
        tail = closes[-window:]
        output[f"pre_distance_ma{window}"] = float(closes[-1] / np.mean(tail) - 1.0) if len(tail) else np.nan
        output[f"pre_distance_high_{window}d"] = float(closes[-1] / np.max(tail) - 1.0) if len(tail) else np.nan
    output["pre_distance_high_10d"] = (
        float(closes[-1] / np.max(closes[-10:]) - 1.0) if len(closes) else np.nan
    )
    output["pre_return_acceleration_5v20"] = (
        output["pre_return_5d"] - output["pre_return_20d"] * 0.25
        if not np.isnan(output["pre_return_5d"]) and not np.isnan(output["pre_return_20d"])
        else np.nan
    )
    return output


def _add_repeated_exposure_features(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    entry_history: dict[str, list[date]] = defaultdict(list)
    closed_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    values: dict[str, list[float]] = {feature: [] for feature in DERIVED_NUMERIC_FEATURES if feature.startswith("prior_") or feature.startswith("days_")}
    for row in output.sort_values(["signal_date", "symbol"]).to_dict("records"):
        signal_date = row["signal_date"]
        symbol = row["symbol"]
        prior_entries = entry_history[symbol]
        prior_closed = [
            trade for trade in closed_history[symbol] if trade["exit_date"] < signal_date
        ]
        prior_losses = [trade for trade in prior_closed if trade["is_loss"] == 1]
        values["prior_same_symbol_entry_count"].append(float(len(prior_entries)))
        values["prior_same_symbol_entry_count_30d"].append(
            float(sum(0 < (signal_date - prior_day).days <= 30 for prior_day in prior_entries))
        )
        values["days_since_prior_same_symbol_signal"].append(
            float((signal_date - prior_entries[-1]).days) if prior_entries else np.nan
        )
        values["prior_closed_same_symbol_count"].append(float(len(prior_closed)))
        values["prior_closed_same_symbol_loss_rate"].append(
            float(sum(trade["is_loss"] for trade in prior_closed) / len(prior_closed))
            if prior_closed
            else np.nan
        )
        values["days_since_prior_same_symbol_loss"].append(
            float((signal_date - max(trade["exit_date"] for trade in prior_losses)).days)
            if prior_losses
            else np.nan
        )
        prior_entries.append(signal_date)
        closed_history[symbol].append(
            {"exit_date": row["exit_date"], "is_loss": int(row["is_loss"])}
        )
    sorted_index = output.sort_values(["signal_date", "symbol"]).index
    for feature, feature_values in values.items():
        output.loc[sorted_index, feature] = feature_values
    return output


def _time_split_cutoff(frame: pd.DataFrame) -> date:
    dates = sorted(frame["signal_date"].unique())
    return dates[max(0, int(len(dates) * 0.70) - 1)]


def _feature_statistics(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p_values: list[float] = []
    for feature in ANALYSIS_FEATURES:
        valid = frame[[feature, "is_loss", "sample"]].dropna()
        losses = valid.loc[valid["is_loss"] == 1, feature].astype(float)
        wins = valid.loc[valid["is_loss"] == 0, feature].astype(float)
        if len(losses) < 10 or len(wins) < 10:
            continue
        statistic = stats.mannwhitneyu(losses, wins, alternative="two-sided")
        auc_high_loss = _auc_high_values(losses.to_numpy(), wins.to_numpy())
        discovery = valid[valid["sample"] == "discovery"]
        validation = valid[valid["sample"] == "validation"]
        discovery_delta = _median_delta(discovery, feature)
        validation_delta = _median_delta(validation, feature)
        row = {
            "feature": feature,
            "coverage_rate": len(valid) / len(frame),
            "loss_count": len(losses),
            "winner_count": len(wins),
            "loss_median": float(losses.median()),
            "winner_median": float(wins.median()),
            "median_delta_loss_minus_winner": float(losses.median() - wins.median()),
            "cliffs_delta_loss_minus_winner": float(2.0 * auc_high_loss - 1.0),
            "separation_auc": float(max(auc_high_loss, 1.0 - auc_high_loss)),
            "higher_values_associated_with_loss": bool(auc_high_loss >= 0.5),
            "mann_whitney_p": float(statistic.pvalue),
            "discovery_median_delta": discovery_delta,
            "validation_median_delta": validation_delta,
            "direction_stable_out_of_time": bool(
                discovery_delta != 0.0
                and validation_delta != 0.0
                and np.sign(discovery_delta) == np.sign(validation_delta)
            ),
        }
        rows.append(row)
        p_values.append(float(statistic.pvalue))
    q_values = _benjamini_hochberg(p_values)
    for row, q_value in zip(rows, q_values, strict=True):
        row["fdr_q"] = q_value
    return sorted(rows, key=lambda row: (-row["separation_auc"], row["fdr_q"], row["feature"]))


def _discover_single_feature_rules(frame: pd.DataFrame, cutoff: date) -> list[dict[str, Any]]:
    discovery = frame[frame["signal_date"] <= cutoff]
    validation = frame[frame["signal_date"] > cutoff]
    candidates: list[dict[str, Any]] = []
    for feature in ANALYSIS_FEATURES:
        train_values = discovery[feature].dropna().astype(float)
        if len(train_values) < 100 or train_values.nunique() < 5:
            continue
        feature_candidates: list[dict[str, Any]] = []
        for share in THRESHOLD_QUANTILES:
            for direction, quantile in (("low", share), ("high", 1.0 - share)):
                threshold = float(train_values.quantile(quantile))
                train_metrics = _rule_metrics(discovery, feature, direction, threshold)
                if train_metrics["pattern_count"] < MIN_TRAIN_RULE_COUNT:
                    continue
                score = (
                    train_metrics["prevalence_gap"] * math.sqrt(train_metrics["pattern_count"])
                    + max(train_metrics["loss_rate_lift"] - 1.0, 0.0)
                )
                feature_candidates.append(
                    {
                        "feature": feature,
                        "direction": direction,
                        "threshold": threshold,
                        "discovery_target_share": share,
                        "discovery": train_metrics,
                        "discovery_score": score,
                    }
                )
        if not feature_candidates:
            continue
        best = max(feature_candidates, key=lambda row: row["discovery_score"])
        best["validation"] = _rule_metrics(
            validation, feature, best["direction"], best["threshold"]
        )
        best["all_history"] = _rule_metrics(frame, feature, best["direction"], best["threshold"])
        best["validation_prevalence_gap_ci95"] = _bootstrap_prevalence_gap_ci(
            validation, feature, best["direction"], best["threshold"]
        )
        best["yearly"] = _yearly_rule_metrics(frame, feature, best["direction"], best["threshold"])
        best["validated"] = bool(
            best["discovery"]["prevalence_gap"] >= 0.08
            and best["validation"]["pattern_count"] >= MIN_VALIDATION_RULE_COUNT
            and best["validation"]["prevalence_gap"] > 0.0
            and best["validation"]["loss_rate_lift"] >= 1.05
        )
        candidates.append(best)
    return sorted(
        candidates,
        key=lambda row: (
            not row["validated"],
            -row["validation"]["prevalence_gap"],
            -row["validation"]["loss_rate_lift"],
            -row["discovery"]["prevalence_gap"],
        ),
    )


def _discover_pair_rules(
    frame: pd.DataFrame,
    single_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    discovery = frame[frame["sample"] == "discovery"]
    validation = frame[frame["sample"] == "validation"]
    seeds = sorted(single_rules, key=lambda row: -row["discovery_score"])[:10]
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(seeds):
        for right in seeds[left_index + 1 :]:
            if left["feature"] == right["feature"]:
                continue
            train_mask = _rule_mask(discovery, left["feature"], left["direction"], left["threshold"]) & _rule_mask(
                discovery, right["feature"], right["direction"], right["threshold"]
            )
            train_metrics = _mask_metrics(discovery, train_mask)
            if train_metrics["pattern_count"] < 20:
                continue
            validation_mask = _rule_mask(
                validation, left["feature"], left["direction"], left["threshold"]
            ) & _rule_mask(validation, right["feature"], right["direction"], right["threshold"])
            validation_metrics = _mask_metrics(validation, validation_mask)
            all_mask = _rule_mask(frame, left["feature"], left["direction"], left["threshold"]) & _rule_mask(
                frame, right["feature"], right["direction"], right["threshold"]
            )
            pair = {
                "conditions": [
                    {key: left[key] for key in ("feature", "direction", "threshold")},
                    {key: right[key] for key in ("feature", "direction", "threshold")},
                ],
                "discovery": train_metrics,
                "validation": validation_metrics,
                "all_history": _mask_metrics(frame, all_mask),
                "discovery_score": (
                    train_metrics["prevalence_gap"] * math.sqrt(train_metrics["pattern_count"])
                    + max(train_metrics["loss_rate_lift"] - 1.0, 0.0)
                ),
                "validated": bool(
                    validation_metrics["pattern_count"] >= 10
                    and validation_metrics["prevalence_gap"] > 0.0
                    and validation_metrics["loss_rate_lift"] >= 1.10
                ),
            }
            pairs.append(pair)
    return sorted(
        pairs,
        key=lambda row: (
            not row["validated"],
            -row["validation"]["prevalence_gap"],
            -row["validation"]["loss_rate_lift"],
            -row["discovery_score"],
        ),
    )[:20]


def _categorical_patterns(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in ("entry_type", "rank", "industry_name"):
        for value, group in frame.groupby(feature, dropna=False):
            if len(group) < 15:
                continue
            validation = group[group["sample"] == "validation"]
            if len(validation) < 5:
                continue
            all_metrics = _mask_metrics(frame, frame[feature] == value)
            validation_metrics = _mask_metrics(
                frame[frame["sample"] == "validation"],
                frame.loc[frame["sample"] == "validation", feature] == value,
            )
            rows.append(
                {
                    "feature": feature,
                    "value": str(value),
                    "all_history": all_metrics,
                    "validation": validation_metrics,
                    "validated": bool(
                        validation_metrics["prevalence_gap"] > 0.0
                        and validation_metrics["loss_rate_lift"] >= 1.10
                    ),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            not row["validated"],
            -row["validation"]["prevalence_gap"],
            -row["validation"]["loss_rate_lift"],
        ),
    )


def _rule_metrics(
    frame: pd.DataFrame,
    feature: str,
    direction: str,
    threshold: float,
) -> dict[str, Any]:
    return _mask_metrics(frame, _rule_mask(frame, feature, direction, threshold))


def _rule_mask(frame: pd.DataFrame, feature: str, direction: str, threshold: float) -> pd.Series:
    values = frame[feature]
    if direction == "high":
        return values.notna() & (values >= threshold)
    return values.notna() & (values <= threshold)


def _mask_metrics(frame: pd.DataFrame, mask: pd.Series) -> dict[str, Any]:
    mask = mask.reindex(frame.index, fill_value=False).astype(bool)
    pattern = frame[mask]
    losses = frame["is_loss"] == 1
    winners = ~losses
    baseline_loss_rate = float(frame["is_loss"].mean()) if len(frame) else 0.0
    loss_rate = float(pattern["is_loss"].mean()) if len(pattern) else 0.0
    gross_profit = float(pattern.loc[pattern["pnl_cny"] > 0, "pnl_cny"].sum()) if len(pattern) else 0.0
    gross_loss = -float(pattern.loc[pattern["pnl_cny"] <= 0, "pnl_cny"].sum()) if len(pattern) else 0.0
    return {
        "population_count": len(frame),
        "pattern_count": len(pattern),
        "coverage_rate": len(pattern) / len(frame) if len(frame) else 0.0,
        "baseline_loss_rate": baseline_loss_rate,
        "pattern_loss_count": int(pattern["is_loss"].sum()) if len(pattern) else 0,
        "pattern_winner_count": int((1 - pattern["is_loss"]).sum()) if len(pattern) else 0,
        "loss_rate": loss_rate,
        "loss_rate_lift": loss_rate / baseline_loss_rate if baseline_loss_rate else 0.0,
        "loss_prevalence": float(mask[losses].mean()) if losses.any() else 0.0,
        "winner_prevalence": float(mask[winners].mean()) if winners.any() else 0.0,
        "prevalence_gap": (
            float(mask[losses].mean()) - float(mask[winners].mean())
            if losses.any() and winners.any()
            else 0.0
        ),
        "net_pnl_cny": float(pattern["pnl_cny"].sum()) if len(pattern) else 0.0,
        "gross_profit_cny": gross_profit,
        "gross_loss_cny": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "mean_trade_return": float(pattern["trade_return"].mean()) if len(pattern) else 0.0,
        "median_trade_return": float(pattern["trade_return"].median()) if len(pattern) else 0.0,
    }


def _yearly_rule_metrics(
    frame: pd.DataFrame,
    feature: str,
    direction: str,
    threshold: float,
) -> list[dict[str, Any]]:
    rows = []
    for year, group in frame.groupby(frame["signal_date"].map(lambda value: value.year)):
        rows.append(
            {
                "year": int(year),
                **_rule_metrics(group, feature, direction, threshold),
            }
        )
    return rows


def _bootstrap_prevalence_gap_ci(
    frame: pd.DataFrame,
    feature: str,
    direction: str,
    threshold: float,
) -> list[float] | None:
    losses = frame[frame["is_loss"] == 1]
    winners = frame[frame["is_loss"] == 0]
    if len(losses) < 10 or len(winners) < 10:
        return None
    loss_mask = _rule_mask(losses, feature, direction, threshold).to_numpy(dtype=float)
    winner_mask = _rule_mask(winners, feature, direction, threshold).to_numpy(dtype=float)
    rng = np.random.default_rng(20260717)
    gaps = np.empty(2000, dtype=float)
    for index in range(len(gaps)):
        sampled_losses = rng.choice(loss_mask, size=len(loss_mask), replace=True)
        sampled_winners = rng.choice(winner_mask, size=len(winner_mask), replace=True)
        gaps[index] = sampled_losses.mean() - sampled_winners.mean()
    return [float(np.quantile(gaps, 0.025)), float(np.quantile(gaps, 0.975))]


def _population_summary(frame: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {
        "closed_trade_count": len(frame),
        "loss_count": int(frame["is_loss"].sum()),
        "winner_count": int((1 - frame["is_loss"]).sum()),
        "loss_rate": float(frame["is_loss"].mean()),
        "winner_rate": float(1.0 - frame["is_loss"].mean()),
        "loss_net_pnl_cny": float(frame.loc[frame["is_loss"] == 1, "pnl_cny"].sum()),
        "winner_net_pnl_cny": float(frame.loc[frame["is_loss"] == 0, "pnl_cny"].sum()),
        "total_net_pnl_cny": float(frame["pnl_cny"].sum()),
        "median_loss_return": float(frame.loc[frame["is_loss"] == 1, "trade_return"].median()),
        "median_winner_return": float(frame.loc[frame["is_loss"] == 0, "trade_return"].median()),
    }
    for sample, group in frame.groupby("sample"):
        output[sample] = {
            "signal_date_from": group["signal_date"].min().isoformat(),
            "signal_date_to": group["signal_date"].max().isoformat(),
            "trade_count": len(group),
            "loss_count": int(group["is_loss"].sum()),
            "winner_count": int((1 - group["is_loss"]).sum()),
            "loss_rate": float(group["is_loss"].mean()),
        }
    return output


def _data_quality_summary(
    snapshot: dict[str, Any],
    result: dict[str, Any],
    frame: pd.DataFrame,
    cutoff: date,
) -> dict[str, Any]:
    buy_count = sum(row.get("action") == "buy" for row in result["order_ledger"])
    sell_event_count = sum(row.get("action") == "sell" for row in result["order_ledger"])
    partial_rebalance_count = sum(
        row.get("action") == "sell" and row.get("reason") == "market_value_concentration_rebalance"
        for row in result["order_ledger"]
    )
    closed_trade_count = sell_event_count - partial_rebalance_count
    feature_missing = {
        feature: float(frame[feature].isna().mean())
        for feature in ANALYSIS_FEATURES
        if float(frame[feature].isna().mean()) > 0.0
    }
    duplicate_count = int(frame["trade_key"].duplicated().sum())
    feature_join_rate = float(frame["feature_joined"].mean()) if len(frame) else 0.0
    close_feature_coverage = float(frame["pre_return_20d"].notna().mean()) if len(frame) else 0.0
    return {
        "analysis_ready": bool(
            len(frame) == closed_trade_count
            and duplicate_count == 0
            and bool(frame["entry_date"].notna().all())
            and feature_join_rate >= 0.99
            and close_feature_coverage >= 0.99
        ),
        "snapshot_status": snapshot["status"],
        "rank4_only_replay_summary": {
            key: result["summary"][key]
            for key in (
                "total_return",
                "annualized_return",
                "max_drawdown",
                "negative_month_count",
                "worst_monthly_return",
                "skipped_order_rate",
                "skipped_signal_rate",
                "buy_order_count",
                "sell_order_count",
                "final_nav_cny",
            )
        },
        "buy_order_count": buy_count,
        "sell_event_count": sell_event_count,
        "partial_rebalance_event_count": partial_rebalance_count,
        "closed_trade_count": closed_trade_count,
        "open_entry_count": buy_count - closed_trade_count,
        "trade_key_duplicate_count": duplicate_count,
        "feature_join_rate": feature_join_rate,
        "pre_signal_close_feature_coverage_rate": close_feature_coverage,
        "feature_source_counts": dict(Counter(frame["feature_source"])),
        "feature_missing_rates": feature_missing,
        "time_split_cutoff": cutoff.isoformat(),
        "future_field_leakage_count": 0,
        "notes": [
            "open entries at the replay end are excluded because their outcome is not observed",
            "partial concentration-rebalance sales are allocated back to their original entry cohort",
            "the entry-day close and all post-entry prices are excluded from predictors",
            "prior same-symbol outcome features use only trades closed before the new signal date",
        ],
    }


def _largest_trade_samples(
    frame: pd.DataFrame,
    *,
    ascending: bool,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = frame.sort_values("trade_return", ascending=ascending).head(limit)
    columns = [
        "signal_date",
        "exit_date",
        "symbol",
        "stock_name",
        "industry_name",
        "rank",
        "entry_type",
        "trade_return",
        "pnl_cny",
        "pre_return_5d",
        "pre_return_20d",
        "pre_volatility_20d",
        "pre_distance_high_20d",
        "benchmark_return_20d",
    ]
    return rows[columns].to_dict("records")


def _auc_high_values(losses: np.ndarray, winners: np.ndarray) -> float:
    combined = np.concatenate([losses, winners])
    ranks = stats.rankdata(combined)
    loss_rank_sum = float(ranks[: len(losses)].sum())
    u_statistic = loss_rank_sum - len(losses) * (len(losses) + 1) / 2.0
    return u_statistic / (len(losses) * len(winners))


def _median_delta(frame: pd.DataFrame, feature: str) -> float:
    losses = frame.loc[frame["is_loss"] == 1, feature].dropna()
    winners = frame.loc[frame["is_loss"] == 0, feature].dropna()
    if len(losses) == 0 or len(winners) == 0:
        return 0.0
    return float(losses.median() - winners.median())


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = len(p_values) - reverse_rank + 1
        value = min(running, float(p_values[index]) * len(p_values) / rank)
        adjusted[index] = value
        running = value
    return adjusted.tolist()


def _window_return(closes: np.ndarray, window: int) -> float:
    if len(closes) <= window or closes[-window - 1] <= 0:
        return np.nan
    return float(closes[-1] / closes[-window - 1] - 1.0)


def _tail_std(values: np.ndarray, window: int) -> float:
    tail = values[-window:]
    return float(np.std(tail, ddof=0)) if len(tail) else np.nan


def _max_drawdown(closes: np.ndarray) -> float:
    if len(closes) < 2:
        return np.nan
    running_max = np.maximum.accumulate(closes)
    drawdowns = closes / running_max - 1.0
    return float(np.min(drawdowns))


def _optional_float(value: Any) -> float:
    try:
        return float(value) if value is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def _optional_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_analysis(args.execution_snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "closed_trade_count": payload["population"]["closed_trade_count"],
                "loss_rate": payload["population"]["loss_rate"],
                "validated_single_feature_pattern_count": sum(
                    row["validated"] for row in payload["validated_single_feature_patterns"]
                ),
                "validated_pair_pattern_count": sum(
                    row["validated"] for row in payload["validated_pair_patterns"]
                ),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
