from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.benchmark import benchmark_close_maps
from ashare_evidence.shortpick_replay_feedback_stats import (
    _baseline_label,
    _best_group,
    _group_excess,
    _mean,
    _positive_rate,
    _round_or_none,
    _worst_group,
)


def _replay_regime_stability_projection(rows: list[dict[str, Any]], *, session: Session | None = None) -> dict[str, Any]:
    focus_families = ("llm", "momentum_10d_turnover_cooldown_rank")
    month_rows = _time_slice_rows(rows, period="month", focus_families=focus_families)
    quarter_rows = _time_slice_rows(rows, period="quarter", focus_families=focus_families)
    market_regime = _market_regime_stability_rows(rows, session=session, focus_families=focus_families)
    industry_theme = _industry_theme_stability_rows(rows, focus_families=focus_families)
    return {
        "status": "ready" if month_rows or quarter_rows or market_regime.get("status") == "ready" or industry_theme.get("status") == "ready" else "missing_artifact",
        "basis": "precomputed_replay_validation_rows",
        "time_slices": {
            "month": month_rows,
            "quarter": quarter_rows,
        },
        "market_regime": market_regime,
        "industry_theme": industry_theme,
    }


def _market_regime_stability_rows(
    rows: list[dict[str, Any]],
    *,
    session: Session | None,
    focus_families: tuple[str, ...],
) -> dict[str, Any]:
    dates = sorted({row["run_date"] for row in rows if isinstance(row.get("run_date"), date)})
    if not dates:
        return {
            "status": "missing_artifact",
            "reason": "历史 replay validation rows 缺少 signal date，无法离线标注市场阶段。",
        }
    if session is None:
        return {
            "status": "missing_artifact",
            "reason": "缺少数据库 session，无法读取本地指数日线生成市场阶段 artifact。",
        }
    daily_tags = _market_regime_tags_by_date(dates, benchmark_close_maps(session))
    if not daily_tags:
        return {
            "status": "missing_artifact",
            "reason": "本地指数日线不足，无法覆盖 replay signal date 的市场阶段标注。",
        }
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row["baseline_family"] not in focus_families:
            continue
        if int(row["horizon_days"]) != 5:
            continue
        if not row["tradable_sample_eligible"] or row["status"] != "completed" or row["excess_return"] is None:
            continue
        run_date = row.get("run_date")
        if not isinstance(run_date, date) or run_date not in daily_tags:
            continue
        tag = str(daily_tags[run_date]["market_regime_tag"])
        grouped.setdefault((str(row["baseline_family"]), tag), []).append(row)
    output = []
    for (family, tag), values in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        excess = [float(row["excess_return"]) for row in values]
        dates_in_group = {row["run_date"] for row in values}
        sample_tag = daily_tags[next(iter(dates_in_group))]
        output.append(
            {
                "family": family,
                "label": _baseline_label(family),
                "market_regime_tag": tag,
                "trend_regime": sample_tag["trend_regime"],
                "volatility_regime": sample_tag["volatility_regime"],
                "size_style_regime": sample_tag["size_style_regime"],
                "horizon_days": 5,
                "mean_excess_return": _round_or_none(_mean(excess)),
                "positive_excess_rate": _positive_rate(excess),
                "sample_count": len(excess),
                "sample_date_count": len(dates_in_group),
            }
        )
    return {
        "status": "ready" if output else "missing_artifact",
        "method": "offline_benchmark_index_regime_labels",
        "basis": "CSI300/CSI1000 local daily bars available before cache materialization",
        "coverage": {
            "requested_date_count": len(dates),
            "tagged_date_count": len(daily_tags),
        },
        "rows": output,
        "daily_tags": [{**tag, "date": day.isoformat()} for day, tag in sorted(daily_tags.items())],
        **({} if output else {"reason": "市场阶段标签已生成，但 replay 完成样本不足以形成分组统计。"}),
    }


def _market_regime_tags_by_date(
    dates: list[date],
    close_maps: dict[str, dict[Any, float]],
) -> dict[date, dict[str, Any]]:
    csi300 = {day: float(close) for day, close in close_maps.get("000300.SH", {}).items()}
    csi1000 = {day: float(close) for day, close in close_maps.get("000852.SH", {}).items()}
    if not csi300:
        return {}
    ordered_days = sorted(csi300)
    index_by_day = {day: index for index, day in enumerate(ordered_days)}
    output: dict[date, dict[str, Any]] = {}
    for original_day in dates:
        target_day = original_day
        index = index_by_day.get(target_day)
        if index is None:
            prior_days = [day for day in ordered_days if day <= target_day]
            if not prior_days:
                continue
            target_day = prior_days[-1]
            index = index_by_day[target_day]
        lookback = min(20, index)
        if lookback < 5:
            continue
        start_day = ordered_days[index - lookback]
        start_close = csi300.get(start_day)
        end_close = csi300.get(target_day)
        if not start_close or not end_close:
            continue
        return_20d = end_close / start_close - 1.0
        return_5d = None
        if index >= 5:
            five_day = ordered_days[index - 5]
            five_close = csi300.get(five_day)
            if five_close:
                return_5d = end_close / five_close - 1.0
        window_days = ordered_days[max(0, index - lookback):index + 1]
        daily_returns = []
        for prev_day, day in zip(window_days, window_days[1:]):
            prev_close = csi300.get(prev_day)
            close = csi300.get(day)
            if prev_close and close:
                daily_returns.append(close / prev_close - 1.0)
        volatility = _sample_std(daily_returns)
        csi1000_return_20d = None
        if target_day in csi1000 and start_day in csi1000 and csi1000[start_day]:
            csi1000_return_20d = csi1000[target_day] / csi1000[start_day] - 1.0
        size_spread = None if csi1000_return_20d is None else csi1000_return_20d - return_20d
        trend_regime = (
            "uptrend"
            if return_20d >= 0.05
            else "downtrend"
            if return_20d <= -0.05
            else "range_bound"
        )
        volatility_regime = (
            "high_volatility"
            if volatility is not None and volatility >= 0.018
            else "low_volatility"
            if volatility is not None and volatility <= 0.01
            else "normal_volatility"
        )
        size_style_regime = (
            "small_cap_lead"
            if size_spread is not None and size_spread >= 0.03
            else "large_cap_lead"
            if size_spread is not None and size_spread <= -0.03
            else "balanced_size"
        )
        output[original_day] = {
            "market_regime_tag": f"{trend_regime}:{volatility_regime}:{size_style_regime}",
            "trend_regime": trend_regime,
            "volatility_regime": volatility_regime,
            "size_style_regime": size_style_regime,
            "csi300_return_20d": _round_or_none(return_20d),
            "csi300_return_5d": _round_or_none(return_5d),
            "csi300_volatility_20d": _round_or_none(volatility),
            "csi1000_return_20d": _round_or_none(csi1000_return_20d),
            "size_spread_20d": _round_or_none(size_spread),
        }
    return output


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_value = _mean(values)
    if mean_value is None:
        return None
    return (sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)) ** 0.5


def _industry_theme_stability_rows(
    rows: list[dict[str, Any]],
    *,
    focus_families: tuple[str, ...],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row["baseline_family"] not in focus_families:
            continue
        if int(row["horizon_days"]) != 5:
            continue
        if not row["tradable_sample_eligible"] or row["status"] != "completed" or row["excess_return"] is None:
            continue
        industry = str(row.get("industry") or "").strip()
        if not industry:
            continue
        grouped.setdefault((str(row["baseline_family"]), industry), []).append(row)
    output = []
    for (family, industry), values in sorted(grouped.items(), key=lambda item: (item[0][0], -len(item[1]), item[0][1])):
        excess = [float(row["excess_return"]) for row in values]
        dates = {row["run_date"] for row in values if row.get("run_date") is not None}
        output.append(
            {
                "family": family,
                "label": _baseline_label(family),
                "industry": industry,
                "horizon_days": 5,
                "mean_excess_return": _round_or_none(_mean(excess)),
                "positive_excess_rate": _positive_rate(excess),
                "sample_count": len(excess),
                "sample_date_count": len(dates),
            }
        )
    return {
        "status": "ready" if output else "missing_artifact",
        "method": "candidate_payload_industry_grouping",
        "basis": "precomputed_replay_validation_rows",
        "rows": output[:20],
        **({} if output else {"reason": "历史 replay validation rows 当前缺少可用行业/题材字段。"}),
    }


def _time_slice_rows(
    rows: list[dict[str, Any]],
    *,
    period: str,
    focus_families: tuple[str, ...],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row["baseline_family"] not in focus_families:
            continue
        if int(row["horizon_days"]) != 5:
            continue
        if not row["tradable_sample_eligible"] or row["status"] != "completed" or row["excess_return"] is None:
            continue
        run_date = row.get("run_date")
        if not isinstance(run_date, date):
            continue
        if period == "quarter":
            period_key = f"{run_date.year}-Q{((run_date.month - 1) // 3) + 1}"
        else:
            period_key = f"{run_date.year}-{run_date.month:02d}"
        grouped.setdefault((str(row["baseline_family"]), period_key), []).append(row)
    output = []
    for (family, period_key), values in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        excess = [float(row["excess_return"]) for row in values]
        dates = {row["run_date"] for row in values}
        output.append(
            {
                "family": family,
                "label": _baseline_label(family),
                "period": period_key,
                "horizon_days": 5,
                "mean_excess_return": _round_or_none(_mean(excess)),
                "positive_excess_rate": _positive_rate(excess),
                "sample_count": len(excess),
                "sample_date_count": len(dates),
            }
        )
    return output


def _replay_return_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    focus = [
        ("overall", rows),
        ("llm", [row for row in rows if row["baseline_family"] == "llm"]),
        (
            "momentum_10d_turnover_cooldown_rank",
            [row for row in rows if row["baseline_family"] == "momentum_10d_turnover_cooldown_rank"],
        ),
    ]
    return {
        "status": "ready" if rows else "missing_artifact",
        "basis": "precomputed_replay_validation_rows",
        "horizon_days": 5,
        "rows": [
            row
            for family, family_rows in focus
            if (row := _return_attribution_row(family, family_rows)) is not None
        ],
        "industry_theme": _industry_theme_return_attribution(rows),
    }


def _industry_theme_return_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        row
        for row in rows
        if row["tradable_sample_eligible"]
        and row["status"] == "completed"
        and int(row["horizon_days"]) == 5
        and row["excess_return"] is not None
        and str(row.get("industry") or "").strip()
    ]
    if not completed:
        return {
            "status": "missing_artifact",
            "reason": "行业/题材级最佳最差贡献需要候选行业字段，当前不在页面请求时临时补齐。",
        }
    by_industry = _group_excess(completed, "industry")
    best_industry, best_industry_mean = _best_group(by_industry)
    worst_industry, worst_industry_mean = _worst_group(by_industry)
    rows_by_family = []
    for family in ("overall", "llm", "momentum_10d_turnover_cooldown_rank"):
        family_rows = completed if family == "overall" else [row for row in completed if row["baseline_family"] == family]
        if not family_rows:
            continue
        family_group = _group_excess(family_rows, "industry")
        family_best, family_best_mean = _best_group(family_group)
        family_worst, family_worst_mean = _worst_group(family_group)
        family_values = [float(row["excess_return"]) for row in family_rows]
        rows_by_family.append(
            {
                "family": family,
                "label": "整体" if family == "overall" else _baseline_label(family),
                "best_industry": family_best,
                "best_industry_mean_excess_return": _round_or_none(family_best_mean),
                "worst_industry": family_worst,
                "worst_industry_mean_excess_return": _round_or_none(family_worst_mean),
                "drop_best_industry_mean_excess_return": _round_or_none(_mean([
                    float(row["excess_return"])
                    for row in family_rows
                    if family_best is None or row.get("industry") != family_best
                ])),
                "mean_excess_return": _round_or_none(_mean(family_values)),
                "sample_count": len(family_values),
            }
        )
    return {
        "status": "ready",
        "method": "candidate_payload_industry_grouping",
        "basis": "precomputed_replay_validation_rows",
        "best_industry": best_industry,
        "best_industry_mean_excess_return": _round_or_none(best_industry_mean),
        "worst_industry": worst_industry,
        "worst_industry_mean_excess_return": _round_or_none(worst_industry_mean),
        "rows": rows_by_family,
    }


def _return_attribution_row(family: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed = [
        row
        for row in rows
        if row["tradable_sample_eligible"]
        and row["status"] == "completed"
        and int(row["horizon_days"]) == 5
        and row["excess_return"] is not None
    ]
    if not completed:
        return None
    values = [float(row["excess_return"]) for row in completed]
    by_symbol = _group_excess(completed, "symbol")
    by_date = _group_excess(completed, "run_date")
    by_month: dict[str, list[float]] = {}
    for row in completed:
        run_date = row.get("run_date")
        if isinstance(run_date, date):
            by_month.setdefault(f"{run_date.year}-{run_date.month:02d}", []).append(float(row["excess_return"]))
    best_symbol, best_symbol_mean = _best_group(by_symbol)
    worst_symbol, worst_symbol_mean = _worst_group(by_symbol)
    best_date, best_date_mean = _best_group(by_date)
    worst_date, worst_date_mean = _worst_group(by_date)
    best_month, best_month_mean = _best_group(by_month)
    worst_month, worst_month_mean = _worst_group(by_month)
    return {
        "family": family,
        "label": "整体" if family == "overall" else _baseline_label(family),
        "mean_excess_return": _round_or_none(_mean(values)),
        "sample_count": len(values),
        "best_symbol": best_symbol,
        "best_symbol_mean_excess_return": _round_or_none(best_symbol_mean),
        "worst_symbol": worst_symbol,
        "worst_symbol_mean_excess_return": _round_or_none(worst_symbol_mean),
        "best_date": None if best_date is None else str(best_date),
        "best_date_mean_excess_return": _round_or_none(best_date_mean),
        "worst_date": None if worst_date is None else str(worst_date),
        "worst_date_mean_excess_return": _round_or_none(worst_date_mean),
        "best_month": best_month,
        "best_month_mean_excess_return": _round_or_none(best_month_mean),
        "worst_month": worst_month,
        "worst_month_mean_excess_return": _round_or_none(worst_month_mean),
        "drop_best_symbol_mean_excess_return": _round_or_none(_mean([
            float(row["excess_return"])
            for row in completed
            if best_symbol is None or row["symbol"] != best_symbol
        ])),
        "drop_best_date_mean_excess_return": _round_or_none(_mean([
            float(row["excess_return"])
            for row in completed
            if best_date is None or row["run_date"] != best_date
        ])),
        "drop_best_month_mean_excess_return": _round_or_none(_mean([
            float(row["excess_return"])
            for row in completed
            if best_month is None
            or not isinstance(row.get("run_date"), date)
            or f"{row['run_date'].year}-{row['run_date'].month:02d}" != best_month
        ])),
    }

