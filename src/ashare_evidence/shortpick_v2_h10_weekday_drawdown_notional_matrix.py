from __future__ import annotations

import json
from dataclasses import dataclass
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
    _drawdown_reversal_feature_rows,
    _eligible_signal_days,
    _regime_features_by_day,
    _trade_days,
)
from ashare_evidence.shortpick_strategy_governance import (
    apply_shortpick_drawdown_reversal_filter_control,
    build_shortpick_drawdown_reversal_filter_rule,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    ShortpickV2RuleConfig,
    _coverage_notes,
    build_shortpick_v2_replay_artifact_from_series,
    write_shortpick_v2_replay_artifact,
)

ARTIFACT_FAMILY = "shortpick_v2_h10_weekday_drawdown_notional_matrix"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_h10_weekday_drawdown_notional_matrix:v1"
EVENT_REF = "shortpick_v2.h10_weekday_drawdown_notional_matrix.generated"
DEFAULT_HORIZON_DAYS = 10
DEFAULT_POOL_HOT_THRESHOLD = 0.10
DEFAULT_NOTIONAL_VALUES = (10_000.0, 20_000.0, 30_000.0, 40_000.0, 50_000.0, 60_000.0, 70_000.0, 80_000.0, 85_000.0)
WEEKDAY_MODES = ("mtw", "all_weekdays")
DRAWDOWN_MODES = ("off", "v1_on")


@dataclass(frozen=True)
class _WeekdayMode:
    mode_id: str
    label_cn: str
    allowed_weekdays: frozenset[int] | None


WEEKDAY_MODE_SPECS = {
    "mtw": _WeekdayMode("mtw", "周一至周三", frozenset({0, 1, 2})),
    "tue_wed_thu": _WeekdayMode("tue_wed_thu", "周二至周四", frozenset({1, 2, 3})),
    "mon_wed_fri": _WeekdayMode("mon_wed_fri", "周一、周三、周五", frozenset({0, 2, 4})),
    "wed_thu_fri": _WeekdayMode("wed_thu_fri", "周三至周五", frozenset({2, 3, 4})),
    "mon_to_thu": _WeekdayMode("mon_to_thu", "周一至周四", frozenset({0, 1, 2, 3})),
    "all_weekdays": _WeekdayMode("all_weekdays", "周一至周五", None),
}


def build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = 45,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    weekday_modes: tuple[str, ...] | None = None,
    notional_values: tuple[float, ...] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if horizon_days != DEFAULT_HORIZON_DAYS:
        raise ValueError("h10 weekday/drawdown/notional matrix requires horizon_days=10")
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")

    generated_at = generated_at or datetime.now(UTC)
    raw_series_by_symbol = _load_daily_series(session)
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=start_date,
        end_date=end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    trade_day_end = end_date + timedelta(days=max(30, horizon_days * 4))
    trade_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=trade_day_end,
        min_symbol_count=min_signal_symbol_count,
    )
    artifact = build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        account_profile=str(account_eligibility["account_profile"]),
        stock_like_series_count=len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        coverage_notes=_coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        weekday_modes=weekday_modes,
        notional_values=notional_values,
        generated_at=generated_at,
    )
    return artifact


def build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact_from_series(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    stock_like_series_count: int | None = None,
    coverage_notes: list[str] | None = None,
    weekday_modes: tuple[str, ...] | None = None,
    notional_values: tuple[float, ...] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if horizon_days != DEFAULT_HORIZON_DAYS:
        raise ValueError("h10 weekday/drawdown/notional matrix requires horizon_days=10")
    if rank_limit < 6:
        raise ValueError("rank_limit must be at least 6 so rank2 through rank6 fallback candidates are available")
    generated_at = generated_at or datetime.now(UTC)
    signal_days = sorted(signal_days)
    trade_days = sorted(trade_days)
    weekday_modes = _validated_weekday_modes(weekday_modes or WEEKDAY_MODES)
    notional_values = _validated_notional_values(notional_values or DEFAULT_NOTIONAL_VALUES)
    stock_like_series_count = (
        stock_like_series_count
        if stock_like_series_count is not None
        else len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    )

    quiet_base = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=max(rank_limit, 6),
    )
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    drawdown_rule = build_shortpick_drawdown_reversal_filter_rule()
    rows: list[dict[str, Any]] = []
    child_artifact_refs: list[dict[str, Any]] = []

    for weekday_mode in weekday_modes:
        weekday_spec = WEEKDAY_MODE_SPECS[weekday_mode]
        raw_selections = _build_rank2_primary_top5_selections(
            signal_days,
            quiet_base_selections=quiet_base,
            regime_features=regime_features,
            weekday_spec=weekday_spec,
        )
        for drawdown_mode in DRAWDOWN_MODES:
            selections, drawdown_summary = _apply_drawdown_mode(
                raw_selections,
                series_by_symbol=series_by_symbol,
                drawdown_mode=drawdown_mode,
                drawdown_rule=drawdown_rule,
            )
            rule_configs = tuple(
                _rule_config(
                    weekday_mode=weekday_mode,
                    drawdown_mode=drawdown_mode,
                    target_notional=target_notional,
                )
                for target_notional in notional_values
            )
            notional_by_config_id = {
                config.config_id: float(config.target_notional or 0.0)
                for config in rule_configs
            }
            child = build_shortpick_v2_replay_artifact_from_series(
                series_by_symbol,
                signal_days=signal_days,
                trade_days=trade_days,
                selections=selections,
                start_date=start_date,
                end_date=end_date,
                initial_cash=initial_cash,
                entry_price_source=entry_price_source,
                horizon_days=horizon_days,
                pool_limit=pool_limit,
                rank_limit=rank_limit,
                cost_bps=cost_bps,
                stamp_tax_bps=stamp_tax_bps,
                account_profile=account_profile,
                stock_like_series_count=stock_like_series_count,
                coverage_notes=coverage_notes,
                rule_configs=rule_configs,
                generated_at=generated_at,
            )
            child_artifact_refs.append(
                {
                    "weekday_mode": weekday_mode,
                    "drawdown_mode": drawdown_mode,
                    "artifact_id": child.get("artifact_id"),
                    "status": child.get("status"),
                }
            )
            for result in child.get("results") or []:
                config_id = str(result.get("config_id") or "")
                target_notional = notional_by_config_id.get(config_id, 0.0)
                rows.append(
                    _matrix_row(
                        result,
                        weekday_spec=weekday_spec,
                        drawdown_mode=drawdown_mode,
                        target_notional=target_notional,
                        drawdown_summary=drawdown_summary,
                        trade_day_count=len(trade_days),
                    )
                )

    rows.sort(
        key=lambda item: (
            item["weekday_mode"],
            item["drawdown_mode"],
            float(item["target_notional"]),
        )
    )
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, start_date, end_date, initial_cash),
        "generated_at": generated_at.isoformat(),
        "status": "ready" if signal_days and rows else "blocked",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "strategy_family": "安静突破 Rank2 首选 + 热度池 10% + H10",
            "selection_policy": (
                "Rank2 is the primary candidate; Rank3-Rank6 are same-day fallback candidates. "
                "Drawdown-on rows first apply the v1 drawdown reversal filter to that candidate pool."
            ),
            "horizon_days": horizon_days,
            "entry_price_source": entry_price_source,
            "initial_cash": initial_cash,
            "pool_hot_threshold": DEFAULT_POOL_HOT_THRESHOLD,
            "weekday_modes": list(weekday_modes),
            "weekday_mode_labels_cn": [WEEKDAY_MODE_SPECS[mode].label_cn for mode in weekday_modes],
            "drawdown_modes": list(DRAWDOWN_MODES),
            "notional_values": list(notional_values),
            "expected_row_count": len(weekday_modes) * len(DRAWDOWN_MODES) * len(notional_values),
            "actual_row_count": len(rows),
            "source_feature_cutoff_policy": "signal_day_or_prior_daily_bar_features_only",
            "promotion_status": "research_only_no_paper_tracking_promotion",
        },
        "data_scope": {
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "stock_like_series_count": stock_like_series_count,
            "account_profile": account_profile,
            "coverage_notes": coverage_notes
            or ["Synthetic or caller-supplied fixed daily bars; no refresh performed."],
        },
        "drawdown_reversal_rule": drawdown_rule,
        "matrix_rows": rows,
        "child_artifact_refs": child_artifact_refs,
        "leakage_audit": {
            "status": "passed",
            "used_only_signal_day_or_earlier_data": True,
            "notes": [
                "Quiet breakout candidate ranking uses signal-day-or-prior daily-bar features.",
                "Drawdown reversal filter uses the existing v1 signal-date-or-prior feature policy.",
                "Entry and exit future bars are used only by the account replay simulation.",
            ],
        },
        "recommendation": {
            "status": "research_only_no_paper_tracking_promotion",
            "message_cn": "本产物只用于参数验证，不把任何组合直接晋级为纸面追踪冻结策略。",
        },
        "event_refs": [EVENT_REF, f"shortpick_v2.h10_matrix_window.{start_date.isoformat()}_{end_date.isoformat()}"],
    }
    validation = validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"matrix artifact validation failed: {validation}")
    return payload


def write_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
    summary_path: str | Path | None = None,
) -> dict[str, Path]:
    artifact_path = write_shortpick_v2_replay_artifact(payload, output_path=output_path)
    paths = {"artifact": artifact_path}
    if summary_path is not None:
        summary = render_shortpick_v2_h10_weekday_drawdown_notional_matrix_markdown(payload)
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
    *,
    artifact_path: str | Path,
) -> dict[str, Any]:
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    return validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_payload(payload)


def validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    rows = [row for row in payload.get("matrix_rows") or [] if isinstance(row, dict)]
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    scope_weekday_modes = tuple(str(value) for value in scope.get("weekday_modes") or WEEKDAY_MODES)
    scope_notional_values = tuple(float(value) for value in scope.get("notional_values") or DEFAULT_NOTIONAL_VALUES)
    expected_row_count = int(scope.get("expected_row_count") or 0) or (
        len(scope_weekday_modes) * len(DRAWDOWN_MODES) * len(scope_notional_values)
    )
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("horizon_days", int(scope.get("horizon_days") or 0) == DEFAULT_HORIZON_DAYS, str(scope.get("horizon_days")))
    check("row_count", len(rows) == expected_row_count, f"{len(rows)} of {expected_row_count}")
    check(
        "weekday_modes",
        sorted({str(row.get("weekday_mode")) for row in rows}) == sorted(scope_weekday_modes),
        str(sorted({str(row.get("weekday_mode")) for row in rows})),
    )
    check(
        "drawdown_modes",
        sorted({str(row.get("drawdown_mode")) for row in rows}) == sorted(DRAWDOWN_MODES),
        str(sorted({str(row.get("drawdown_mode")) for row in rows})),
    )
    check(
        "notional_values",
        sorted({float(row.get("target_notional") or 0.0) for row in rows}) == sorted(scope_notional_values),
        str(sorted({float(row.get("target_notional") or 0.0) for row in rows})),
    )
    check(
        "no_delay_actions",
        all("delay" not in action for row in rows for action in row.get("allowed_actions") or []),
        "allowed actions scanned",
    )
    check(
        "degenerate_rows_labeled",
        all(not row.get("degenerate") or row.get("degenerate_label_cn") for row in rows),
        "degenerate labels scanned",
    )
    check(
        "drawdown_rule_v1",
        (payload.get("drawdown_reversal_rule") or {}).get("rule_version") == "drawdown-reversal-filter-v1",
        str((payload.get("drawdown_reversal_rule") or {}).get("rule_version")),
    )
    check(
        "research_only",
        (payload.get("recommendation") or {}).get("status") == "research_only_no_paper_tracking_promotion",
        str((payload.get("recommendation") or {}).get("status")),
    )
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "horizon_days": scope.get("horizon_days"),
            "row_count": len(rows),
            "weekday_modes": sorted({str(row.get("weekday_mode")) for row in rows}),
            "drawdown_modes": sorted({str(row.get("drawdown_mode")) for row in rows}),
            "notional_values": sorted({float(row.get("target_notional") or 0.0) for row in rows}),
        },
    }


def render_shortpick_v2_h10_weekday_drawdown_notional_matrix_markdown(payload: dict[str, Any]) -> str:
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    weekday_labels = [str(value) for value in scope.get("weekday_mode_labels_cn") or []]
    notional_values = [float(value) for value in scope.get("notional_values") or []]
    rows = sorted(
        [row for row in payload.get("matrix_rows") or [] if isinstance(row, dict)],
        key=lambda item: (
            -float(item.get("annualized_return") or -999.0),
            float(item.get("max_drawdown") or 0.0),
        ),
    )
    lines = [
        "# 试验田 v2 H10 参数验证矩阵",
        "",
        "本表只用于研究验证，不代表纸面追踪冻结策略晋级。",
        "",
        "## 口径",
        "",
        "- 选股：安静突破，热度池 10%，Rank2 为首选，Rank3-Rank6 为同日候补。",
        "- 持有：H10，使用既有 v2 回放引擎。",
        "- 交易日：对比 " + "、".join(weekday_labels) + "。",
        "- 回撤反转：对比关闭与 v1 过滤开启。",
        "- 单笔金额：" + "、".join(_notional_label(value) for value in notional_values) + "。",
        "",
        "## 结果排序",
        "",
        "| 排名 | 方案 | 总收益 | 年化 | 超额 | 最大回撤 | 交易 | skip | turnover | 平均仓位 | 标记 |",
        "|------|------|--------|------|------|----------|------|------|----------|----------|------|",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(
            "| {rank} | {desc} | {total} | {annual} | {excess} | {drawdown} | {trades} | {skip} | {turnover} | {invested} | {label} |".format(
                rank=index,
                desc=str(row.get("strategy_description_cn") or ""),
                total=_pct(row.get("total_return")),
                annual=_pct(row.get("annualized_return")),
                excess=_pct(row.get("market_excess_total_return")),
                drawdown=_pct(row.get("max_drawdown")),
                trades=int(row.get("trade_count") or 0),
                skip=_pct(row.get("skipped_ratio")),
                turnover=f"{float(row.get('turnover') or 0.0):.2f}",
                invested=_pct(row.get("mean_invested_ratio")),
                label=str(row.get("degenerate_label_cn") or ""),
            )
        )
    lines.extend(
        [
            "",
            "## 审计说明",
            "",
            "- 所有组合都保留在表内；如果完全无法成单，会标记为全跳过。",
            "- 回撤反转开启时使用既有 v1 规则签名，不使用信号日之后的数据。",
            "- 本产物不写入纸面追踪，不修改前端或 API。",
            "",
        ]
    )
    return "\n".join(lines)


def _build_rank2_primary_top5_selections(
    signal_days: list[date],
    *,
    quiet_base_selections: dict[date, list[str]],
    regime_features: dict[date, dict[str, float]],
    weekday_spec: _WeekdayMode,
) -> dict[date, list[str]]:
    selections: dict[date, list[str]] = {}
    for signal_day in signal_days:
        if weekday_spec.allowed_weekdays is not None and signal_day.weekday() not in weekday_spec.allowed_weekdays:
            selections[signal_day] = []
            continue
        if float((regime_features.get(signal_day) or {}).get("pool_ret1_mean", 0.0)) < DEFAULT_POOL_HOT_THRESHOLD:
            selections[signal_day] = []
            continue
        base_symbols = quiet_base_selections.get(signal_day) or []
        selections[signal_day] = base_symbols[1:6] if len(base_symbols) >= 2 else []
    return selections


def _apply_drawdown_mode(
    selections: dict[date, list[str]],
    *,
    series_by_symbol: dict[str, Any],
    drawdown_mode: str,
    drawdown_rule: dict[str, Any],
) -> tuple[dict[date, list[str]], dict[str, Any]]:
    if drawdown_mode == "off":
        return dict(selections), {
            "mode": "off",
            "input_candidate_count": sum(len(symbols) for symbols in selections.values()),
            "blocked_count": 0,
            "allowed_count": sum(len(symbols) for symbols in selections.values()),
            "missing_feature_count": 0,
        }
    candidate_rows = _selection_candidate_rows_with_original_rank(selections)
    result = apply_shortpick_drawdown_reversal_filter_control(
        candidate_rows,
        _drawdown_reversal_feature_rows(series_by_symbol, selections),
        rule=drawdown_rule,
        evidence_basis="historical_backtest",
    )
    allowed: dict[date, list[str]] = {}
    rows_by_day: dict[date, list[dict[str, Any]]] = {}
    for row in result.get("rows") or []:
        if not isinstance(row, dict) or row.get("filter_action") != "allowed":
            continue
        signal_day = date.fromisoformat(str(row["signal_date"]))
        rows_by_day.setdefault(signal_day, []).append(row)
    for signal_day, rows in rows_by_day.items():
        rows.sort(key=lambda item: int(item.get("candidate_rank") or 999999))
        allowed[signal_day] = [str(row["symbol"]) for row in rows]
    for signal_day in selections:
        allowed.setdefault(signal_day, [])
    return allowed, {
        "mode": "v1_on",
        "input_candidate_count": result.get("input_candidate_count"),
        "blocked_count": result.get("blocked_count"),
        "allowed_count": result.get("allowed_count"),
        "missing_feature_count": result.get("missing_feature_count"),
        "rule_signature": result.get("rule_signature"),
    }


def _selection_candidate_rows_with_original_rank(selections: dict[date, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal_day, symbols in sorted(selections.items()):
        # The candidate pool is base_symbols[1:6], so the first emitted row is original Rank2.
        for offset, symbol in enumerate(symbols, start=2):
            rows.append(
                {
                    "candidate_id": f"{signal_day.isoformat()}:{offset}:{symbol}",
                    "signal_date": signal_day.isoformat(),
                    "symbol": symbol,
                    "candidate_rank": offset,
                }
            )
    return rows


def _rule_config(*, weekday_mode: str, drawdown_mode: str, target_notional: float) -> ShortpickV2RuleConfig:
    notional_key = _notional_key(target_notional)
    return ShortpickV2RuleConfig(
        config_id=(
            f"h10_quiet_rank2_primary_poolhot10_{weekday_mode}_drawdown_{drawdown_mode}"
            f"__fixed_notional_{notional_key}_top5_h10_v1"
        ),
        family="h10_quiet_weekday_drawdown_notional_matrix",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=float(target_notional),
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    )


def _matrix_row(
    result: dict[str, Any],
    *,
    weekday_spec: _WeekdayMode,
    drawdown_mode: str,
    target_notional: float,
    drawdown_summary: dict[str, Any],
    trade_day_count: int,
) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    total_return = float(summary.get("total_return") or 0.0)
    skipped_ratio = float(summary.get("skipped_ratio") or 0.0)
    trade_count = int(summary.get("trade_count") or 0)
    annualized_return = _annualized(total_return, trade_day_count)
    degenerate_label = ""
    if trade_count == 0:
        degenerate_label = "全跳过"
    elif skipped_ratio >= 0.95:
        degenerate_label = "高跳过"
    drawdown_label = "开启 v1 回撤反转过滤" if drawdown_mode == "v1_on" else "不加回撤反转过滤"
    strategy_description = f"{weekday_spec.label_cn}，{drawdown_label}，单笔约 {target_notional / 10000:.1f} 万"
    return {
        "config_id": result.get("config_id"),
        "status": result.get("status"),
        "weekday_mode": weekday_spec.mode_id,
        "weekday_label_cn": weekday_spec.label_cn,
        "drawdown_mode": drawdown_mode,
        "drawdown_label_cn": drawdown_label,
        "target_notional": float(target_notional),
        "strategy_description_cn": strategy_description,
        "selection_description_cn": (
            "安静突破热度池 10%，Rank2 为首选，Rank3-Rank6 为同日候补；"
            + ("候选先通过 v1 回撤反转过滤。" if drawdown_mode == "v1_on" else "不做回撤反转过滤。")
        ),
        "allowed_actions": ["buy_primary", "buy_fallback", "skip"],
        "signal_count": int(summary.get("signal_count") or 0),
        "trade_count": trade_count,
        "skip_count": int(summary.get("skip_count") or 0),
        "fallback_trade_count": int(summary.get("fallback_trade_count") or 0),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "market_reference_total_return": summary.get("market_reference_total_return"),
        "market_excess_total_return": summary.get("market_excess_total_return"),
        "max_drawdown": summary.get("max_drawdown"),
        "mean_invested_ratio": summary.get("mean_invested_ratio"),
        "max_position_count": summary.get("max_position_count"),
        "turnover": summary.get("turnover"),
        "skipped_ratio": skipped_ratio,
        "degenerate": bool(degenerate_label),
        "degenerate_label_cn": degenerate_label,
        "drawdown_filter_summary": drawdown_summary,
    }

def _notional_key(target_notional: float) -> str:
    value = float(target_notional) / 1000.0
    return f"{value:g}k"


def _notional_label(target_notional: float) -> str:
    return f"{float(target_notional) / 10000.0:g}万"


def _validated_weekday_modes(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise ValueError("weekday_modes must not be empty")
    invalid = [value for value in values if value not in WEEKDAY_MODE_SPECS]
    if invalid:
        raise ValueError(f"unknown weekday_modes: {invalid}")
    return tuple(dict.fromkeys(values))


def _validated_notional_values(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values:
        raise ValueError("notional_values must not be empty")
    cleaned = tuple(float(value) for value in values)
    if any(value <= 0.0 for value in cleaned):
        raise ValueError("notional_values must be positive")
    return tuple(dict.fromkeys(cleaned))


def _annualized(total_return: float, trade_day_count: int) -> float | None:
    if trade_day_count <= 0 or total_return <= -1.0:
        return None
    return round((1.0 + float(total_return)) ** (252.0 / float(trade_day_count)) - 1.0, 6)


def _artifact_id(generated_at: datetime, start_date: date, end_date: date, initial_cash: float) -> str:
    return (
        f"{ARTIFACT_FAMILY}:{start_date.isoformat()}:{end_date.isoformat()}:"
        f"{int(initial_cash)}:{generated_at.date().isoformat()}"
    )


def _pct(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"
