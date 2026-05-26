from __future__ import annotations

import random
from datetime import date
from typing import Any

SHORTPICK_REPLAY_BASELINE_FAMILIES = (
    "llm",
    "llm_self_distilled",
    "llm_momentum_distilled",
    "random_same_tradeable_universe",
    "random_same_market_cap_bucket",
    "momentum_volume_baseline",
    "momentum_volume_expanded_pool",
    "llm_reject_only",
    "llm_reject_then_momentum_rank",
    "random_reject_then_momentum_rank",
    "llm_hard_veto_then_momentum_rank",
    "random_hard_veto_then_momentum_rank",
    "llm_strict_veto_then_momentum_rank",
    "random_strict_veto_then_momentum_rank",
    "momentum_turnover_rank",
    "momentum_10d_rank",
    "momentum_10d_turnover_rank",
    "momentum_10d_turnover_cooldown_rank",
    "momentum_continuity_turnover_rank",
)
SHORTPICK_REPLAY_HORIZON_ORDER = (1, 3, 5, 10, 20)

def _baseline_label(value: str) -> str:
    labels = {
        "llm": "LLM",
        "llm_self_distilled": "LLM自选蒸馏",
        "llm_momentum_distilled": "LLM动量池蒸馏",
        "random_same_tradeable_universe": "随机",
        "random_same_market_cap_bucket": "同市值随机",
        "momentum_volume_baseline": "动量成交量",
        "momentum_volume_expanded_pool": "扩大动量池",
        "llm_reject_only": "LLM只剔除保留池",
        "llm_reject_then_momentum_rank": "LLM剔除后动量排序",
        "random_reject_then_momentum_rank": "随机剔除后动量排序",
        "llm_hard_veto_then_momentum_rank": "LLM硬否决后动量排序",
        "random_hard_veto_then_momentum_rank": "随机硬否决后动量排序",
        "llm_strict_veto_then_momentum_rank": "LLM严格否决后动量排序",
        "random_strict_veto_then_momentum_rank": "随机严格否决后动量排序",
        "momentum_turnover_rank": "换手优先动量排序",
        "momentum_10d_rank": "10日持续动量排序",
        "momentum_10d_turnover_rank": "10日动量换手复合排序",
        "momentum_10d_turnover_cooldown_rank": "10日动量换手降追高排序",
        "momentum_continuity_turnover_rank": "持续动量换手复合排序",
    }
    return labels.get(value, value)


def _group_excess(rows: list[dict[str, Any]], key: str) -> dict[Any, list[float]]:
    grouped: dict[Any, list[float]] = {}
    for row in rows:
        group_key = row.get(key)
        if group_key is None:
            continue
        grouped.setdefault(group_key, []).append(float(row["excess_return"]))
    return grouped


def _best_group(grouped: dict[Any, list[float]]) -> tuple[Any | None, float | None]:
    if not grouped:
        return None, None
    key = max(grouped, key=lambda item: _mean(grouped[item]) or -999.0)
    return key, _mean(grouped[key])


def _worst_group(grouped: dict[Any, list[float]]) -> tuple[Any | None, float | None]:
    if not grouped:
        return None, None
    key = min(grouped, key=lambda item: _mean(grouped[item]) or 999.0)
    return key, _mean(grouped[key])


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _mean_or_none(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _trimmed_mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) < 5:
        return _mean_or_none(values)
    ordered = sorted(values)
    return _mean_or_none(ordered[1:-1])


def _positive_rate(values: list[float]) -> float | None:
    return round(sum(1 for value in values if value > 0) / len(values), 6) if values else None

def _replay_feedback_scope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    run_ids = sorted({int(row["run_id"]) for row in rows if row.get("run_id") is not None})
    dates = sorted({row["run_date"] for row in rows if row.get("run_date") is not None})
    return {
        "run_count": len(run_ids),
        "unique_replay_date_count": len(dates),
        "date_from": dates[0].isoformat() if dates else None,
        "date_to": dates[-1].isoformat() if dates else None,
    }


def _replay_statistical_gate(rows: list[dict[str, Any]], horizon_groups: list[dict[str, Any]]) -> dict[str, Any]:
    completed_official = [
        row
        for row in rows
        if row["official_sample_eligible"] and row["status"] == "completed"
    ]
    completed_tradable = [
        row
        for row in rows
        if row["tradable_sample_eligible"] and row["status"] == "completed"
    ]
    completed_dates = {row["run_date"] for row in completed_official if row.get("run_date") is not None}
    completed_tradable_dates = {row["run_date"] for row in completed_tradable if row.get("run_date") is not None}
    completed_symbols = {row["symbol"] for row in completed_official}
    completed_tradable_symbols = {row["symbol"] for row in completed_tradable}
    min_completed_samples = 30
    min_completed_dates = 5
    horizon_readiness = []
    for group in horizon_groups:
        completed_count = int(group.get("completed_official_sample_count") or 0)
        horizon_readiness.append(
            {
                "horizon": int(group["group_key"]),
                "completed_official_sample_count": completed_count,
                "completed_tradable_sample_count": int(group.get("completed_tradable_sample_count") or 0),
                "ready": completed_count >= min_completed_samples,
            }
        )
    ready_horizons = [item["horizon"] for item in horizon_readiness if item["ready"]]
    status = "ready" if len(completed_official) >= min_completed_samples and len(completed_dates) >= min_completed_dates else "exploratory"
    return {
        "status": status,
        "min_completed_samples": min_completed_samples,
        "min_completed_dates": min_completed_dates,
        "completed_official_sample_count": len(completed_official),
        "completed_tradable_sample_count": len(completed_tradable),
        "completed_date_count": len(completed_dates),
        "completed_tradable_date_count": len(completed_tradable_dates),
        "completed_symbol_count": len(completed_symbols),
        "completed_tradable_symbol_count": len(completed_tradable_symbols),
        "ready_horizons": ready_horizons,
        "horizon_readiness": horizon_readiness,
        "reason": (
            "Replay sample is broad enough for aggregate readout."
            if status == "ready"
            else "Replay sample is still exploratory; add more historical dates before treating family-level differences as statistically meaningful."
        ),
    }


def _replay_feedback_groups(rows: list[dict[str, Any]], *, group_key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row["horizon_days"] if group_key == "horizon" else row["baseline_family"])
        grouped.setdefault(key, []).append(row)
    output = []
    for key, values in sorted(grouped.items(), key=lambda item: _replay_group_sort_key(item[0], group_key=group_key)):
        completed = [
            row for row in values
            if row["official_sample_eligible"] and row["status"] == "completed"
        ]
        tradable_completed = [
            row for row in values
            if row["tradable_sample_eligible"] and row["status"] == "completed"
        ]
        excess = [float(row["excess_return"]) for row in completed if row["excess_return"] is not None]
        tradable_excess = [float(row["excess_return"]) for row in tradable_completed if row["excess_return"] is not None]
        stock_returns = [float(row["stock_return"]) for row in completed if row["stock_return"] is not None]
        tradable_stock_returns = [float(row["stock_return"]) for row in tradable_completed if row["stock_return"] is not None]
        output.append(
            {
                "group_key": key,
                "label": f"{key}日" if group_key == "horizon" else _baseline_label(key),
                "sample_count": len(values),
                "official_sample_count": len([row for row in values if row["official_sample_eligible"]]),
                "tradable_sample_count": len([row for row in values if row["tradable_sample_eligible"]]),
                "completed_official_sample_count": len(completed),
                "completed_tradable_sample_count": len(tradable_completed),
                "completed_validation_count": len([row for row in values if row["status"] == "completed"]),
                "mean_stock_return": _mean_or_none(stock_returns),
                "mean_excess_return": _mean_or_none(excess),
                "trimmed_mean_excess_return": _trimmed_mean_or_none(excess),
                "positive_excess_rate": _positive_rate(excess),
                "tradable_mean_stock_return": _mean_or_none(tradable_stock_returns),
                "tradable_mean_excess_return": _mean_or_none(tradable_excess),
                "tradable_trimmed_mean_excess_return": _trimmed_mean_or_none(tradable_excess),
                "tradable_positive_excess_rate": _positive_rate(tradable_excess),
                "benchmark_metrics": {},
                "status_counts": _count_by([row["status"] for row in values]),
            }
        )
    return output


def _replay_group_sort_key(key: str, *, group_key: str) -> tuple[int, int, str]:
    if group_key == "horizon":
        try:
            horizon = int(key)
        except ValueError:
            return (1, len(SHORTPICK_REPLAY_HORIZON_ORDER), key)
        if horizon in SHORTPICK_REPLAY_HORIZON_ORDER:
            return (0, SHORTPICK_REPLAY_HORIZON_ORDER.index(horizon), key)
        return (0, len(SHORTPICK_REPLAY_HORIZON_ORDER) + horizon, key)
    if group_key == "family" and key in SHORTPICK_REPLAY_BASELINE_FAMILIES:
        return (0, SHORTPICK_REPLAY_BASELINE_FAMILIES.index(key), key)
    return (1, 0, key)


def _robustness_metrics(rows: list[dict[str, Any]], *, eligibility_key: str = "official_sample_eligible") -> dict[str, Any]:
    completed = [
        row for row in rows
        if row.get(eligibility_key) and row["status"] == "completed" and row["excess_return"] is not None
    ]
    values = [float(row["excess_return"]) for row in completed]
    by_symbol: dict[str, list[float]] = {}
    by_date: dict[str, list[float]] = {}
    for row in completed:
        value = float(row["excess_return"])
        by_symbol.setdefault(row["symbol"], []).append(value)
        run = row["run_id"]
        date_key = str(run)
        by_date.setdefault(date_key, []).append(value)
    best_symbol = max(by_symbol, key=lambda key: _mean_or_none(by_symbol[key]) or -999.0) if by_symbol else None
    best_date = max(by_date, key=lambda key: _mean_or_none(by_date[key]) or -999.0) if by_date else None
    return {
        "raw_mean_excess_return": _mean_or_none(values),
        "trimmed_mean_excess_return": _trimmed_mean_or_none(values),
        "positive_excess_rate": _positive_rate(values),
        "drop_best_symbol_mean_excess_return": _mean_or_none([
            float(row["excess_return"])
            for row in completed
            if best_symbol is None or row["symbol"] != best_symbol
        ]),
        "drop_best_date_mean_excess_return": _mean_or_none([
            float(row["excess_return"])
            for row in completed
            if best_date is None or str(row["run_id"]) != best_date
        ]),
        "best_symbol": best_symbol,
        "sample_count": len(values),
    }


def _replay_confidence_intervals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    focus_rows = []
    for family in ("llm", "momentum_10d_turnover_cooldown_rank", "overall"):
        scoped_rows = rows if family == "overall" else [row for row in rows if row["baseline_family"] == family]
        for eligibility_key, label_suffix in (
            ("official_sample_eligible", "严格来源"),
            ("tradable_sample_eligible", "可交易"),
        ):
            row = _clustered_bootstrap_interval(
                scoped_rows,
                family=family,
                label_suffix=label_suffix,
                eligibility_key=eligibility_key,
                horizon_days=5,
            )
            if row:
                focus_rows.append(row)
    return {
        "status": "ready" if focus_rows else "missing_artifact",
        "method": "trading_day_clustered_bootstrap",
        "basis": "precomputed_replay_validation_rows",
        "note": "按 replay signal date 聚类抽样；策略晋级只参考置信区间下沿是否为正，不参考单一均值。",
        "rows": focus_rows,
    }


def _clustered_bootstrap_interval(
    rows: list[dict[str, Any]],
    *,
    family: str,
    label_suffix: str,
    eligibility_key: str,
    horizon_days: int,
) -> dict[str, Any] | None:
    completed = [
        row
        for row in rows
        if row.get(eligibility_key)
        and row["status"] == "completed"
        and int(row["horizon_days"]) == horizon_days
        and row["excess_return"] is not None
        and row.get("run_date") is not None
    ]
    by_date: dict[date, list[float]] = {}
    symbols: set[str] = set()
    for row in completed:
        by_date.setdefault(row["run_date"], []).append(float(row["excess_return"]))
        symbols.add(str(row["symbol"]))
    date_means = [_mean(values) for _, values in sorted(by_date.items()) if values]
    if len(date_means) < 2:
        return None
    rng = random.Random(f"shortpick-replay-ci:{family}:{eligibility_key}:{horizon_days}")
    bootstrap_means = []
    for _ in range(1000):
        sample = [date_means[rng.randrange(len(date_means))] for _ in date_means]
        bootstrap_means.append(_mean(sample))
    lower = _percentile(bootstrap_means, 0.025)
    upper = _percentile(bootstrap_means, 0.975)
    mean_value = _mean([float(row["excess_return"]) for row in completed])
    lower_positive = lower is not None and lower > 0
    family_label = "整体" if family == "overall" else _baseline_label(family)
    return {
        "id": f"{family}_{horizon_days}d_{eligibility_key.replace('_sample_eligible', '')}",
        "family": family,
        "label": f"{family_label} {horizon_days}日{label_suffix}",
        "horizon_days": horizon_days,
        "eligibility": eligibility_key.replace("_sample_eligible", ""),
        "mean_excess_return": None if mean_value is None else round(mean_value, 6),
        "lower_excess_return": None if lower is None else round(lower, 6),
        "upper_excess_return": None if upper is None else round(upper, 6),
        "lower_bound_positive": lower_positive,
        "promotion_decision": "eligible_by_ci_lower_bound" if lower_positive else "blocked_by_ci_lower_bound",
        "sample_date_count": len(date_means),
        "sample_stock_count": len(symbols),
        "sample_count": len(completed),
    }


def _candidate_industry(candidate_payload: dict[str, Any]) -> str | None:
    for key in ("industry", "sector", "theme", "normalized_theme"):
        value = candidate_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None

