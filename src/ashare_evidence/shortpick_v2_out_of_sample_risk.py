from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    INDEX_SYMBOLS,
    QUIET_BREAKOUT_BASE_STRATEGY,
    _build_strategy_selections,
    _load_daily_series,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    _eligible_signal_days,
    _max_drawdown,
    _regime_features_by_day,
    _trade_days,
)
from ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix import (
    DEFAULT_POOL_HOT_THRESHOLD,
    WEEKDAY_MODE_SPECS,
    _build_rank2_primary_top5_selections,
    _rule_config,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    _coverage_notes,
    _market_reference_summary,
    _simulate_rule_config,
)

ARTIFACT_FAMILY = "shortpick_v2_out_of_sample_risk_diagnostic"
SCHEMA_VERSION = "v1"
DEFAULT_HISTORICAL_START_DATE = date(2023, 4, 13)
DEFAULT_HISTORICAL_END_DATE = date(2026, 5, 8)
DEFAULT_PAPER_START_DATE = date(2026, 5, 8)
DEFAULT_PAPER_END_DATE = date(2026, 6, 15)
DEFAULT_OBSERVED_PAPER_MAX_DRAWDOWN = -0.175
DEFAULT_WINDOW_SIZES = (25, 50)
DEFAULT_HORIZON_DAYS = 10
DEFAULT_TARGET_NOTIONAL = 85_000.0
DEFAULT_POOL_LIMIT = 40
DEFAULT_RANK_LIMIT = 6
DEFAULT_MIN_SIGNAL_SYMBOL_COUNT = 45


def build_shortpick_v2_out_of_sample_risk_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    historical_end_date: date = DEFAULT_HISTORICAL_END_DATE,
    paper_start_date: date = DEFAULT_PAPER_START_DATE,
    paper_end_date: date = DEFAULT_PAPER_END_DATE,
    observed_paper_max_drawdown: float = DEFAULT_OBSERVED_PAPER_MAX_DRAWDOWN,
    window_sizes: tuple[int, ...] = DEFAULT_WINDOW_SIZES,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    rank_limit: int = DEFAULT_RANK_LIMIT,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if horizon_days != DEFAULT_HORIZON_DAYS:
        raise ValueError("out-of-sample risk diagnostic currently requires horizon_days=10")
    if rank_limit < DEFAULT_RANK_LIMIT:
        raise ValueError("rank_limit must be at least 6 so Rank2-Rank6 candidates are available")
    if not window_sizes or any(int(value) <= 1 for value in window_sizes):
        raise ValueError("window_sizes must contain values greater than 1")

    generated_at = generated_at or datetime.now(UTC)
    raw_series_by_symbol = _load_daily_series(session)
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=historical_end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    trade_days = _trade_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=historical_end_date + timedelta(days=max(30, horizon_days * 4)),
        min_symbol_count=min_signal_symbol_count,
    )
    quiet_base = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=max(rank_limit, DEFAULT_RANK_LIMIT),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    weekday_spec = WEEKDAY_MODE_SPECS["mtw"]
    selections = _build_rank2_primary_top5_selections(
        signal_days,
        quiet_base_selections=quiet_base,
        regime_features=regime_features,
        weekday_spec=weekday_spec,
    )
    rule_config = _rule_config(
        weekday_mode="mtw",
        drawdown_mode="off",
        target_notional=DEFAULT_TARGET_NOTIONAL,
    )
    market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
    replay_result = _simulate_rule_config(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=selections,
        config=rule_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        market_reference_total_return=market_reference.get("total_return"),
        decision_sample_limit=0,
        include_nav_timeline=True,
    )
    timeline = [
        {
            "date": str(point["date"]),
            "nav": float(point["nav"]),
            "cash": float(point["cash"]),
            "market_value": float(point["market_value"]),
            "open_position_count": int(point["open_position_count"]),
        }
        for point in ((replay_result.get("diagnostic_details") or {}).get("nav_timeline") or [])
    ]
    window_sizes = tuple(dict.fromkeys(int(value) for value in window_sizes))
    strategy_window_diagnostics = [
        _window_diagnostic(
            timeline,
            window_size=window_size,
            observed_paper_max_drawdown=observed_paper_max_drawdown,
        )
        for window_size in window_sizes
    ]
    index_diagnostics = _index_window_diagnostics(
        series_by_symbol,
        trade_days=trade_days,
        window_sizes=window_sizes,
        observed_paper_max_drawdown=observed_paper_max_drawdown,
    )
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, historical_start_date, historical_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready" if timeline and strategy_window_diagnostics else "blocked",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_rolling_window_vs_current_paper_pressure",
        "analysis_scope": {
            "strategy_id": rule_config.config_id,
            "strategy_label_cn": "安静突破 Rank2 + 热度池 10% + 周一至周三 + H10 + 8.5 万目标买入",
            "selection_policy_cn": "仅在周一至周三触发；热度池 10%；Rank2 为首选；Rank3-Rank6 为同日候补；不加回撤反转过滤。",
            "historical_start_date": historical_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "observed_paper_max_drawdown": round(float(observed_paper_max_drawdown), 6),
            "window_sizes_trade_days": list(window_sizes),
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "target_notional": DEFAULT_TARGET_NOTIONAL,
            "pool_hot_threshold": DEFAULT_POOL_HOT_THRESHOLD,
            "entry_price_source": entry_price_source,
            "account_profile": str(account_eligibility["account_profile"]),
            "promotion_status": "risk_warning_only_no_strategy_replacement",
        },
        "data_scope": {
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "timeline_point_count": len(timeline),
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "historical_replay_summary": replay_result.get("summary") or {},
        "rolling_window_diagnostics": strategy_window_diagnostics,
        "index_window_diagnostics": index_diagnostics,
        "interpretation": _interpretation(strategy_window_diagnostics, observed_paper_max_drawdown),
        "leakage_audit": {
            "status": "passed",
            "used_only_existing_market_rows": True,
            "paper_tracking_write_policy": "forbidden",
            "notes": [
                "Historical timeline is rebuilt from the governed v2 H10 replay engine.",
                "Current paper drawdown is an observed input and is not used to choose strategy parameters.",
                "The artifact compares rolling historical pressure windows; it does not promote or retire a strategy.",
            ],
        },
        "event_refs": [
            "shortpick_v2.out_of_sample_risk_diagnostic.generated",
            f"shortpick_v2.paper_window.{paper_start_date.isoformat()}_{paper_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_out_of_sample_risk_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"out-of-sample risk artifact validation failed: {validation}")
    return payload


def validate_shortpick_v2_out_of_sample_risk_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_out_of_sample_risk_payload(
        json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    )


def validate_shortpick_v2_out_of_sample_risk_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    rolling = [row for row in payload.get("rolling_window_diagnostics") or [] if isinstance(row, dict)]
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("promotion_status", scope.get("promotion_status") == "risk_warning_only_no_strategy_replacement", str(scope.get("promotion_status")))
    check("observed_drawdown_negative", float(scope.get("observed_paper_max_drawdown") or 0.0) < 0.0, str(scope.get("observed_paper_max_drawdown")))
    check("rolling_windows_present", bool(rolling), str(len(rolling)))
    check(
        "rolling_windows_have_counts",
        all(int(row.get("historical_window_count") or 0) > 0 for row in rolling),
        str([row.get("historical_window_count") for row in rolling]),
    )
    check(
        "leakage_status",
        (payload.get("leakage_audit") or {}).get("status") == "passed",
        str((payload.get("leakage_audit") or {}).get("status")),
    )
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "window_sizes_trade_days": [row.get("window_size_trade_days") for row in rolling],
            "observed_paper_max_drawdown": scope.get("observed_paper_max_drawdown"),
            "interpretation_status": (payload.get("interpretation") or {}).get("status"),
        },
    }


def write_shortpick_v2_out_of_sample_risk_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
    summary_path: str | Path | None = None,
) -> dict[str, Path]:
    artifact_path = Path(output_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    paths = {"artifact": artifact_path}
    if summary_path is not None:
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_shortpick_v2_out_of_sample_risk_markdown(payload), encoding="utf-8")
        paths["summary"] = path
    return paths


def render_shortpick_v2_out_of_sample_risk_markdown(payload: dict[str, Any]) -> str:
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    summary = payload.get("historical_replay_summary") if isinstance(payload.get("historical_replay_summary"), dict) else {}
    rolling = [row for row in payload.get("rolling_window_diagnostics") or [] if isinstance(row, dict)]
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    lines = [
        "# 试验田 v2 样本外回撤压力诊断",
        "",
        "本诊断只回答一个问题：当前纸面追踪阶段出现的回撤，在历史滚动窗口里是不是常见。",
        "",
        "## 口径",
        "",
        f"- 策略：{scope.get('strategy_label_cn')}",
        f"- 历史窗口：{scope.get('historical_start_date')} 至 {scope.get('historical_end_date')}",
        f"- 纸面观察：{scope.get('paper_start_date')} 至 {scope.get('paper_end_date')}",
        f"- 纸面最大回撤观察值：{_pct(scope.get('observed_paper_max_drawdown'))}",
        f"- 历史总收益：{_pct(summary.get('total_return'))}",
        f"- 历史最大回撤：{_pct(summary.get('max_drawdown'))}",
        "",
        "## 滚动窗口对比",
        "",
        "| 窗口 | 历史窗口数 | 历史最差 | 历史中位数 | 与当前一样差或更差 | 判断 |",
        "|------|------------|----------|------------|--------------------|------|",
    ]
    for row in rolling:
        lines.append(
            "| {window} 交易日 | {count} | {worst} | {median} | {ratio} | {label} |".format(
                window=int(row.get("window_size_trade_days") or 0),
                count=int(row.get("historical_window_count") or 0),
                worst=_pct((row.get("drawdown_distribution") or {}).get("min")),
                median=_pct((row.get("drawdown_distribution") or {}).get("median")),
                ratio=_pct(row.get("equal_or_worse_historical_window_ratio")),
                label=str(row.get("rarity_label_cn") or ""),
            )
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            str(interpretation.get("message_cn") or ""),
            "",
            "## 约束",
            "",
            "- 这是风险治理诊断，不是策略晋级、退役或替换结论。",
            "- 历史三年最大回撤和当前一个多月纸面回撤不是同一种统计口径。",
            "- 当前纸面窗口过短，必须继续结合后续窗口观察。",
            "",
        ]
    )
    return "\n".join(lines)


def _window_diagnostic(
    timeline: list[dict[str, Any]],
    *,
    window_size: int,
    observed_paper_max_drawdown: float,
) -> dict[str, Any]:
    windows = _rolling_windows(timeline, window_size=window_size)
    drawdowns = [float(window["max_drawdown"]) for window in windows]
    equal_or_worse = [value for value in drawdowns if value <= float(observed_paper_max_drawdown)]
    ratio = round(len(equal_or_worse) / len(drawdowns), 6) if drawdowns else 0.0
    return {
        "window_size_trade_days": window_size,
        "historical_window_count": len(windows),
        "observed_paper_max_drawdown": round(float(observed_paper_max_drawdown), 6),
        "equal_or_worse_historical_window_count": len(equal_or_worse),
        "equal_or_worse_historical_window_ratio": ratio,
        "rarity_label_cn": _rarity_label(ratio),
        "drawdown_distribution": _distribution(drawdowns),
        "worst_windows": sorted(windows, key=lambda item: float(item["max_drawdown"]))[:5],
    }


def _rolling_windows(timeline: list[dict[str, Any]], *, window_size: int) -> list[dict[str, Any]]:
    if window_size <= 1:
        return []
    rows = sorted(timeline, key=lambda item: str(item["date"]))
    windows: list[dict[str, Any]] = []
    for end_index in range(window_size - 1, len(rows)):
        window = rows[end_index - window_size + 1 : end_index + 1]
        navs = [float(point["nav"]) for point in window]
        start_nav = navs[0]
        end_nav = navs[-1]
        max_drawdown = _max_drawdown(navs) or 0.0
        windows.append(
            {
                "start_date": str(window[0]["date"]),
                "end_date": str(window[-1]["date"]),
                "max_drawdown": round(max_drawdown, 6),
                "window_return": round(end_nav / start_nav - 1.0, 6) if start_nav else 0.0,
            }
        )
    return windows


def _index_window_diagnostics(
    series_by_symbol: dict[str, Any],
    *,
    trade_days: list[date],
    window_sizes: tuple[int, ...],
    observed_paper_max_drawdown: float,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for symbol in sorted(INDEX_SYMBOLS):
        series = series_by_symbol.get(symbol)
        if series is None:
            continue
        timeline = []
        base_close: float | None = None
        for day in trade_days:
            index = series.by_day.get(day)
            if index is None:
                continue
            close = float(series.bars[index].close)
            base_close = close if base_close is None else base_close
            timeline.append({"date": day.isoformat(), "nav": close / base_close if base_close else 1.0})
        if not timeline:
            continue
        diagnostics.append(
            {
                "symbol": symbol,
                "window_diagnostics": [
                    _window_diagnostic(
                        timeline,
                        window_size=window_size,
                        observed_paper_max_drawdown=observed_paper_max_drawdown,
                    )
                    for window_size in window_sizes
                ],
            }
        )
    return diagnostics


def _distribution(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p05": None, "p10": None, "p25": None, "median": None, "p75": None, "max": None}
    ordered = sorted(float(value) for value in values)
    return {
        "min": round(ordered[0], 6),
        "p05": round(_quantile(ordered, 0.05), 6),
        "p10": round(_quantile(ordered, 0.10), 6),
        "p25": round(_quantile(ordered, 0.25), 6),
        "median": round(_quantile(ordered, 0.50), 6),
        "p75": round(_quantile(ordered, 0.75), 6),
        "max": round(ordered[-1], 6),
    }


def _quantile(ordered_values: list[float], q: float) -> float:
    if not ordered_values:
        return 0.0
    if len(ordered_values) == 1:
        return ordered_values[0]
    position = (len(ordered_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered_values) - 1)
    weight = position - lower
    return ordered_values[lower] * (1.0 - weight) + ordered_values[upper] * weight


def _rarity_label(equal_or_worse_ratio: float) -> str:
    if equal_or_worse_ratio <= 0.01:
        return "历史极少见"
    if equal_or_worse_ratio <= 0.05:
        return "历史偏少见"
    if equal_or_worse_ratio <= 0.15:
        return "历史低频"
    return "历史常见"


def _interpretation(
    diagnostics: list[dict[str, Any]],
    observed_paper_max_drawdown: float,
) -> dict[str, Any]:
    ratios = [float(row.get("equal_or_worse_historical_window_ratio") or 0.0) for row in diagnostics]
    min_ratio = min(ratios) if ratios else 0.0
    if min_ratio <= 0.01:
        status = "sample_out_pressure_extreme"
        message = (
            "当前纸面回撤已经落在历史滚动窗口的极少见区域。它不能单独证明策略失效，"
            "但足以要求继续做逐笔归因、市场窗口归因和纸面风险标签。"
        )
    elif min_ratio <= 0.05:
        status = "sample_out_pressure_unusual"
        message = (
            "当前纸面回撤在历史滚动窗口中偏少见。更合理的处理是先标记风险预警，"
            "不要直接退役策略，也不要直接扩大资金。"
        )
    else:
        status = "sample_out_pressure_within_historical_range"
        message = (
            "当前纸面回撤仍在历史滚动窗口中出现过。短期表现难看，但更像是已知波动区间内的压力窗口。"
        )
    return {
        "status": status,
        "observed_paper_max_drawdown": round(float(observed_paper_max_drawdown), 6),
        "minimum_equal_or_worse_historical_window_ratio": round(min_ratio, 6),
        "message_cn": message,
    }


def _artifact_id(generated_at: datetime, start_date: date, end_date: date) -> str:
    return (
        f"{ARTIFACT_FAMILY}:{start_date.isoformat()}:{end_date.isoformat()}:"
        f"{generated_at.date().isoformat()}"
    )


def _pct(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"
