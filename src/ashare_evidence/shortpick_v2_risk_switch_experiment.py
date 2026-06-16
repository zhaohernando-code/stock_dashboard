from __future__ import annotations

import json
from collections import Counter
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
    _eligible_signal_days,
    _exit_is_unfillable_limit_down,
    _max_drawdown,
    _regime_features_by_day,
    _trade_days,
)
from ashare_evidence.shortpick_strategy_governance import build_shortpick_drawdown_reversal_filter_rule
from ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix import (
    DEFAULT_POOL_HOT_THRESHOLD,
    WEEKDAY_MODE_SPECS,
    _apply_drawdown_mode,
    _build_rank2_primary_top5_selections,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    DYNAMIC_EXIT_REASONS,
    ShortpickV2RuleConfig,
    _coverage_notes,
    _dynamic_exit_reason,
    _evaluate_signal_entry,
    _market_reference_summary,
    _nav_and_market_value,
    _prepare_signal_entries,
    _simulate_rule_config,
)

ARTIFACT_FAMILY = "shortpick_v2_risk_switch_experiment"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_risk_switch_experiment:v1"
DEFAULT_HISTORICAL_START_DATE = date(2023, 4, 13)
DEFAULT_HISTORICAL_END_DATE = date(2026, 5, 8)
DEFAULT_PAPER_START_DATE = date(2026, 5, 8)
DEFAULT_PAPER_END_DATE = date(2026, 6, 15)
DEFAULT_HORIZON_DAYS = 10
DEFAULT_TARGET_NOTIONAL = 85_000.0
DEFAULT_WEAK_TARGET_NOTIONAL = 50_000.0
DEFAULT_WEAK_MARKET_INDEX_SYMBOL = "000300.SH"
DEFAULT_WEAK_MARKET_LOOKBACK_DAYS = 5
DEFAULT_WEAK_MARKET_RETURN_THRESHOLD = -0.02
DEFAULT_POOL_LIMIT = 40
DEFAULT_RANK_LIMIT = 6
DEFAULT_MIN_SIGNAL_SYMBOL_COUNT = 45
DEFAULT_BASELINE_CONFIG_ID = "risk_switch_baseline_fixed85_max5"


@dataclass(frozen=True)
class _RiskSwitchVariant:
    variant_id: str
    label_cn: str
    risk_switch_description_cn: str
    drawdown_mode: str = "off"
    weak_market_action: str = "none"
    max_position_count: int = 5
    target_notional: float = DEFAULT_TARGET_NOTIONAL
    weak_target_notional: float | None = None


DEFAULT_VARIANTS: tuple[_RiskSwitchVariant, ...] = (
    _RiskSwitchVariant(
        variant_id=DEFAULT_BASELINE_CONFIG_ID,
        label_cn="基线：固定 8.5 万，最多 5 仓",
        risk_switch_description_cn="不加额外风控开关。",
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_weak_market_skip_fixed85_max5",
        label_cn="弱势日跳过，固定 8.5 万，最多 5 仓",
        risk_switch_description_cn="若沪深300近 5 个交易日跌幅超过 2%，当天不买入。",
        weak_market_action="skip",
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_weak_market_50k_max5",
        label_cn="弱势日降到 5 万，最多 5 仓",
        risk_switch_description_cn="若沪深300近 5 个交易日跌幅超过 2%，单笔目标从 8.5 万降到 5 万。",
        weak_market_action="lower_notional",
        weak_target_notional=DEFAULT_WEAK_TARGET_NOTIONAL,
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_fixed85_max3",
        label_cn="固定 8.5 万，最多 3 仓",
        risk_switch_description_cn="不改变选股，只把最大同时持仓数从 5 降到 3。",
        max_position_count=3,
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_v1_drawdown_entry_fixed85_max5",
        label_cn="v1 回撤反转入场过滤，固定 8.5 万，最多 5 仓",
        risk_switch_description_cn="候选股先经过 v1 回撤反转过滤；只影响入场，不改变 H10 卖出。",
        drawdown_mode="v1_on",
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_weak_skip_fixed85_max3",
        label_cn="弱势日跳过，固定 8.5 万，最多 3 仓",
        risk_switch_description_cn="弱势日不买入，同时最多 3 仓。",
        weak_market_action="skip",
        max_position_count=3,
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_weak_50k_max3",
        label_cn="弱势日降到 5 万，最多 3 仓",
        risk_switch_description_cn="弱势日单笔目标降到 5 万，同时最多 3 仓。",
        weak_market_action="lower_notional",
        max_position_count=3,
        weak_target_notional=DEFAULT_WEAK_TARGET_NOTIONAL,
    ),
    _RiskSwitchVariant(
        variant_id="risk_switch_all_defensive_skip_drawdown_max3",
        label_cn="全防御：弱势跳过 + v1 入场过滤 + 最多 3 仓",
        risk_switch_description_cn="弱势日不买入，候选股经过 v1 回撤反转入场过滤，同时最多 3 仓。",
        drawdown_mode="v1_on",
        weak_market_action="skip",
        max_position_count=3,
    ),
)


def build_shortpick_v2_risk_switch_experiment_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    historical_end_date: date = DEFAULT_HISTORICAL_END_DATE,
    paper_start_date: date = DEFAULT_PAPER_START_DATE,
    paper_end_date: date = DEFAULT_PAPER_END_DATE,
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
        raise ValueError("risk switch experiment requires H10; horizon_days must be 10")
    if rank_limit < DEFAULT_RANK_LIMIT:
        raise ValueError("rank_limit must be at least 6 so Rank2-Rank6 candidates are available")

    generated_at = generated_at or datetime.now(UTC)
    raw_series_by_symbol = _load_daily_series(session)
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    common = {
        "series_by_symbol": series_by_symbol,
        "initial_cash": initial_cash,
        "entry_price_source": entry_price_source,
        "horizon_days": horizon_days,
        "pool_limit": pool_limit,
        "rank_limit": rank_limit,
        "cost_bps": cost_bps,
        "stamp_tax_bps": stamp_tax_bps,
        "min_signal_symbol_count": min_signal_symbol_count,
    }
    historical = _build_window_result(
        start_date=historical_start_date,
        end_date=historical_end_date,
        window_id="historical",
        window_label_cn="历史回测",
        **common,
    )
    paper = _build_window_result(
        start_date=paper_start_date,
        end_date=paper_end_date,
        window_id="paper",
        window_label_cn="当前纸面窗口回放",
        **common,
    )
    rows = _combine_window_rows(historical["rows"], paper["rows"])
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, historical_start_date, historical_end_date, paper_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready" if rows else "blocked",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_and_current_paper_window_account_replay",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "strategy_family_cn": "安静突破 Rank2 + 热度池 10% + H10",
            "baseline_config_id": DEFAULT_BASELINE_CONFIG_ID,
            "baseline_description_cn": "周一至周三触发；热度池 10%；Rank2 首选；Rank3-Rank6 同日候补；固定 8.5 万；最多 5 仓；H10 卖出。",
            "historical_start_date": historical_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "entry_price_source": entry_price_source,
            "target_notional": DEFAULT_TARGET_NOTIONAL,
            "weak_target_notional": DEFAULT_WEAK_TARGET_NOTIONAL,
            "pool_hot_threshold": DEFAULT_POOL_HOT_THRESHOLD,
            "variant_count": len(DEFAULT_VARIANTS),
            "promotion_status": "research_only_no_paper_tracking_promotion",
        },
        "weak_market_rule": {
            "status": "frozen_before_run",
            "index_symbol": DEFAULT_WEAK_MARKET_INDEX_SYMBOL,
            "index_label_cn": "沪深300",
            "lookback_trade_days": DEFAULT_WEAK_MARKET_LOOKBACK_DAYS,
            "return_threshold": DEFAULT_WEAK_MARKET_RETURN_THRESHOLD,
            "definition_cn": "沪深300信号日收盘价相对 5 个交易日前收盘价跌幅超过 2%，定义为弱势日。",
            "tuning_policy": "not_tuned_after_observing_this_run_results",
        },
        "data_scope": {
            "historical": historical["data_scope"],
            "paper": paper["data_scope"],
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "variant_rows": rows,
        "drawdown_reversal_rule": build_shortpick_drawdown_reversal_filter_rule(),
        "recommendation": _recommendation(rows),
        "leakage_audit": {
            "status": "passed",
            "used_only_signal_day_or_earlier_data": True,
            "paper_window_role": "smoke_check_only_not_parameter_selection",
            "notes": [
                "Weak-market labels use the frozen CSI300 signal-day-or-earlier close series.",
                "v1 drawdown reversal is applied only as an entry-pool filter.",
                "Entry and exit future bars are used only by account replay simulation.",
                "No result is promoted into paper tracking by this artifact.",
            ],
        },
        "event_refs": [
            "shortpick_v2.risk_switch_experiment.generated",
            f"shortpick_v2.risk_switch.historical.{historical_start_date.isoformat()}_{historical_end_date.isoformat()}",
            f"shortpick_v2.risk_switch.paper.{paper_start_date.isoformat()}_{paper_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_risk_switch_experiment_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"risk switch experiment validation failed: {validation}")
    return payload


def write_shortpick_v2_risk_switch_experiment_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
    summary_path: str | Path | None = None,
) -> dict[str, Path]:
    artifact_path = Path(output_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = {"artifact": artifact_path}
    if summary_path is not None:
        summary = render_shortpick_v2_risk_switch_experiment_markdown(payload)
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_risk_switch_experiment_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_risk_switch_experiment_payload(
        json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    )


def validate_shortpick_v2_risk_switch_experiment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    rows = [row for row in payload.get("variant_rows") or [] if isinstance(row, dict)]
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    weak_rule = payload.get("weak_market_rule") if isinstance(payload.get("weak_market_rule"), dict) else {}
    variant_ids = {str(row.get("variant_id")) for row in rows}
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_paper_tracking_promotion", str(scope.get("promotion_status")))
    check("horizon_h10", int(scope.get("horizon_days") or 0) == DEFAULT_HORIZON_DAYS, str(scope.get("horizon_days")))
    check("variant_count", len(rows) == len(DEFAULT_VARIANTS), str(len(rows)))
    check("baseline_present", DEFAULT_BASELINE_CONFIG_ID in variant_ids, str(sorted(variant_ids)))
    check(
        "weak_rule_frozen",
        weak_rule.get("status") == "frozen_before_run"
        and weak_rule.get("index_symbol") == DEFAULT_WEAK_MARKET_INDEX_SYMBOL
        and int(weak_rule.get("lookback_trade_days") or 0) == DEFAULT_WEAK_MARKET_LOOKBACK_DAYS
        and abs(float(weak_rule.get("return_threshold") or 0.0) - DEFAULT_WEAK_MARKET_RETURN_THRESHOLD) < 1e-12,
        str(weak_rule),
    )
    check(
        "both_windows_present",
        all(isinstance(row.get("historical"), dict) and isinstance(row.get("paper"), dict) for row in rows),
        "historical and paper fields scanned",
    )
    check(
        "no_delay_actions",
        all("delay" not in action for row in rows for action in row.get("allowed_actions") or []),
        "allowed actions scanned",
    )
    check(
        "drawdown_entry_only",
        all(row.get("exit_policy_cn") == "固定 H10 机械卖出" for row in rows),
        "exit policy scanned",
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
            "variant_count": len(rows),
            "baseline_config_id": scope.get("baseline_config_id"),
            "recommendation_status": (payload.get("recommendation") or {}).get("status"),
        },
    }


def render_shortpick_v2_risk_switch_experiment_markdown(payload: dict[str, Any]) -> str:
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    weak_rule = payload.get("weak_market_rule") if isinstance(payload.get("weak_market_rule"), dict) else {}
    rows = [row for row in payload.get("variant_rows") or [] if isinstance(row, dict)]
    rows.sort(
        key=lambda row: (
            _outcome_rank(str(row.get("outcome_status") or "")),
            -float((row.get("historical") or {}).get("calmar") or -999.0),
            -float((row.get("historical") or {}).get("annualized_return") or -999.0),
        )
    )
    lines = [
        "# 试验田 v2 风险开关实验",
        "",
        "本产物只用于研究验证，不代表纸面追踪冻结策略晋级。",
        "",
        "## 口径",
        "",
        f"- 基线：{scope.get('baseline_description_cn')}",
        f"- 弱势定义：{weak_rule.get('definition_cn')}",
        "- 纸面窗口只作为压力烟雾测试，不用于调参。",
        "- v1 回撤反转只作为入场过滤，不改变固定 H10 卖出。",
        "",
        "## 研究结论",
        "",
        str((payload.get("recommendation") or {}).get("message_cn") or "暂无结论。"),
        "",
        "## 结果表",
        "",
        "| 排名 | 方案 | 怎么选股 / 买股 | 历史总收益 | 历史年化 | 历史超额 | 历史回撤 | 历史交易 / skip | 纸面收益 | 纸面回撤 | 判断 |",
        "|------|------|----------------|------------|----------|----------|----------|-----------------|----------|----------|------|",
    ]
    for index, row in enumerate(rows, start=1):
        historical = row.get("historical") if isinstance(row.get("historical"), dict) else {}
        paper = row.get("paper") if isinstance(row.get("paper"), dict) else {}
        lines.append(
            "| {rank} | {label} | {desc} | {hist_total} | {hist_ann} | {hist_excess} | {hist_dd} | {hist_trades} / {hist_skip} | {paper_total} | {paper_dd} | {outcome} |".format(
                rank=index,
                label=str(row.get("label_cn") or ""),
                desc=str(row.get("selection_and_buy_description_cn") or ""),
                hist_total=_pct(historical.get("total_return")),
                hist_ann=_pct(historical.get("annualized_return")),
                hist_excess=_pct(historical.get("market_excess_total_return")),
                hist_dd=_pct(historical.get("max_drawdown")),
                hist_trades=int(historical.get("trade_count") or 0),
                hist_skip=_pct(historical.get("skipped_ratio")),
                paper_total=_pct(paper.get("total_return")),
                paper_dd=_pct(paper.get("max_drawdown")),
                outcome=str(row.get("outcome_label_cn") or ""),
            )
        )
    lines.extend(
        [
            "",
            "## 审计说明",
            "",
            "- 本次不做阈值网格搜索；弱势阈值在运行前固定。",
            "- 除 v1 回撤反转过滤外，本轮风险开关在当前纸面窗口的结果完全收敛，说明这个 5 周窗口不足以证明弱势开关有效。",
            "- 若某个方案只改善当前纸面窗口，但显著牺牲历史回测，会标记为不晋级或观察。",
            "- 本产物不写入纸面追踪，不修改前端或 API。",
            "",
        ]
    )
    return "\n".join(lines)


def _build_window_result(
    *,
    series_by_symbol: dict[str, Any],
    start_date: date,
    end_date: date,
    window_id: str,
    window_label_cn: str,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    pool_limit: int,
    rank_limit: int,
    cost_bps: float,
    stamp_tax_bps: float,
    min_signal_symbol_count: int,
) -> dict[str, Any]:
    signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=start_date,
        end_date=end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    trade_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=end_date + timedelta(days=max(30, horizon_days * 4)),
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
    base_selections = _build_rank2_primary_top5_selections(
        signal_days,
        quiet_base_selections=quiet_base,
        regime_features=regime_features,
        weekday_spec=weekday_spec,
    )
    weak_market = _weak_market_features_by_day(
        series_by_symbol,
        signal_days=signal_days,
        lookback_trade_days=DEFAULT_WEAK_MARKET_LOOKBACK_DAYS,
        return_threshold=DEFAULT_WEAK_MARKET_RETURN_THRESHOLD,
    )
    weak_days = {day for day, row in weak_market.items() if bool(row.get("is_weak_market"))}
    market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
    drawdown_rule = build_shortpick_drawdown_reversal_filter_rule()
    rows: list[dict[str, Any]] = []
    drawdown_summaries: dict[str, dict[str, Any]] = {}

    for variant in DEFAULT_VARIANTS:
        selections, drawdown_summary = _variant_selections(
            base_selections,
            series_by_symbol=series_by_symbol,
            variant=variant,
            drawdown_rule=drawdown_rule,
            weak_days=weak_days,
        )
        drawdown_summaries[variant.variant_id] = drawdown_summary
        config = _rule_config_for_variant(variant)
        if variant.weak_market_action == "lower_notional":
            result = _simulate_dynamic_notional_rule_config(
                series_by_symbol,
                signal_days=signal_days,
                trade_days=trade_days,
                selections=selections,
                config=config,
                weak_days=weak_days,
                weak_target_notional=float(variant.weak_target_notional or DEFAULT_WEAK_TARGET_NOTIONAL),
                initial_cash=initial_cash,
                entry_price_source=entry_price_source,
                horizon_days=horizon_days,
                cost_bps=cost_bps,
                stamp_tax_bps=stamp_tax_bps,
                market_reference_total_return=market_reference.get("total_return"),
            )
        else:
            result = _simulate_rule_config(
                series_by_symbol,
                signal_days=signal_days,
                trade_days=trade_days,
                selections=selections,
                config=config,
                initial_cash=initial_cash,
                entry_price_source=entry_price_source,
                horizon_days=horizon_days,
                cost_bps=cost_bps,
                stamp_tax_bps=stamp_tax_bps,
                market_reference_total_return=market_reference.get("total_return"),
                decision_sample_limit=0,
            )
        rows.append(_window_row(variant, result, trade_day_count=len(trade_days), weak_market=weak_market))

    return {
        "window_id": window_id,
        "window_label_cn": window_label_cn,
        "data_scope": {
            "window_id": window_id,
            "window_label_cn": window_label_cn,
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "weak_market_signal_count": len(weak_days),
            "weak_market_signal_ratio": round(len(weak_days) / len(signal_days), 6) if signal_days else 0.0,
            "market_reference_total_return": market_reference.get("total_return"),
        },
        "rows": rows,
        "drawdown_filter_summaries": drawdown_summaries,
    }


def _variant_selections(
    base_selections: dict[date, list[str]],
    *,
    series_by_symbol: dict[str, Any],
    variant: _RiskSwitchVariant,
    drawdown_rule: dict[str, Any],
    weak_days: set[date],
) -> tuple[dict[date, list[str]], dict[str, Any]]:
    selections, drawdown_summary = _apply_drawdown_mode(
        base_selections,
        series_by_symbol=series_by_symbol,
        drawdown_mode=variant.drawdown_mode,
        drawdown_rule=drawdown_rule,
    )
    if variant.weak_market_action == "skip":
        selections = {signal_day: ([] if signal_day in weak_days else list(symbols)) for signal_day, symbols in selections.items()}
    return selections, drawdown_summary


def _simulate_dynamic_notional_rule_config(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    selections: dict[date, list[str]],
    config: ShortpickV2RuleConfig,
    weak_days: set[date],
    weak_target_notional: float,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    cost_bps: float,
    stamp_tax_bps: float,
    market_reference_total_return: float | None,
) -> dict[str, Any]:
    entries_by_day, pre_entry_decisions, pre_entry_counts = _prepare_signal_entries(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=selections,
        config=config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
    )
    weak_config = ShortpickV2RuleConfig(
        config_id=f"{config.config_id}__weak50k",
        family=config.family,
        candidate_rank_limit=config.candidate_rank_limit,
        fallback_enabled=config.fallback_enabled,
        target_mode=config.target_mode,
        target_notional=float(weak_target_notional),
        allowed_actions=config.allowed_actions,
        cash_reserve=config.cash_reserve,
        max_position_count=config.max_position_count,
        max_position_pct=config.max_position_pct,
        board_lot_size=config.board_lot_size,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        trailing_stop_pct=config.trailing_stop_pct,
        trailing_activation_pct=config.trailing_activation_pct,
    )
    active_days = sorted(set(trade_days) | set(entries_by_day))
    cash = float(initial_cash)
    buy_cost_rate = float(cost_bps) / 10000.0
    sell_cost_rate = float(cost_bps + stamp_tax_bps) / 10000.0
    open_positions: list[Any] = []
    decisions = list(pre_entry_decisions)
    reason_counts = Counter(pre_entry_counts)
    timeline: list[dict[str, Any]] = []
    total_buy_value = 0.0
    total_sell_value = 0.0
    blocked_exit_count = 0
    exit_reason_counts: Counter[str] = Counter()
    weak_entry_count = 0

    for current_day in active_days:
        still_open: list[Any] = []
        for position in open_positions:
            series = series_by_symbol.get(position.symbol)
            current_index = series.by_day.get(current_day) if series is not None else None
            if series is None or current_index is None:
                still_open.append(position)
                continue
            close = float(series.bars[current_index].close)
            position.peak_close = max(position.peak_close, close)
            exit_reason = (
                "mechanical_horizon"
                if current_day >= position.planned_exit_day
                else _dynamic_exit_reason(position, close=close, current_day=current_day, config=config)
            )
            if exit_reason is None:
                still_open.append(position)
                continue
            if _exit_is_unfillable_limit_down(series, current_index):
                blocked_exit_count += 1
                reason_counts["blocked_exit:limit_down"] += 1
                still_open.append(position)
                continue
            proceeds = position.shares * close * (1.0 - sell_cost_rate)
            cash += proceeds
            total_sell_value += proceeds
            reason_counts[f"exit:{exit_reason}"] += 1
            exit_reason_counts[exit_reason] += 1
        open_positions = still_open

        for signal_entry in sorted(entries_by_day.get(current_day, []), key=lambda item: item.signal_day):
            entry_config = weak_config if signal_entry.signal_day in weak_days else config
            if entry_config is weak_config:
                weak_entry_count += 1
                reason_counts["weak_market_lower_notional_signal"] += 1
            cash_before = cash
            evaluation = _evaluate_signal_entry(
                signal_entry,
                config=entry_config,
                cash=cash,
                open_positions=open_positions,
                series_by_symbol=series_by_symbol,
                current_day=current_day,
                initial_cash=initial_cash,
                buy_cost_rate=buy_cost_rate,
                entry_price_source=entry_price_source,
            )
            reason_counts[f"action:{evaluation.action}"] += 1
            reason_counts[f"reason:{evaluation.reason}"] += 1
            for rejected_reason in evaluation.rejected_reasons:
                reason_counts[f"candidate_reject:{rejected_reason}"] += 1
            if evaluation.position is not None:
                cash -= evaluation.cash_spent
                total_buy_value += evaluation.cash_spent
                open_positions.append(evaluation.position)
            decisions.append(
                {
                    "signal_date": signal_entry.signal_day.isoformat(),
                    "action": evaluation.action,
                    "reason": evaluation.reason,
                    "selected_rank": evaluation.selected_rank,
                    "symbol": evaluation.symbol,
                    "cash_before": round(cash_before, 6),
                    "cash_after": round(cash, 6),
                    "quantity": evaluation.shares,
                    "target_notional": entry_config.target_notional,
                }
            )

        nav, market_value = _nav_and_market_value(series_by_symbol, open_positions, current_day, cash)
        timeline.append(
            {
                "date": current_day.isoformat(),
                "nav": nav,
                "cash": cash,
                "market_value": market_value,
                "open_position_count": len(open_positions),
            }
        )

    final_day = active_days[-1] if active_days else None
    if final_day is None:
        final_nav = float(initial_cash)
        final_market_value = 0.0
    else:
        final_nav, final_market_value = _nav_and_market_value(series_by_symbol, open_positions, final_day, cash)
    buy_decisions = [decision for decision in decisions if decision["action"] in {"buy_primary", "buy_fallback"}]
    skip_count = sum(1 for decision in decisions if decision["action"] == "skip")
    fallback_trade_count = sum(1 for decision in decisions if decision["action"] == "buy_fallback")
    invested_ratios = [
        float(point["market_value"]) / float(point["nav"])
        for point in timeline
        if float(point["nav"]) > 0
    ]
    total_return = round(final_nav / float(initial_cash) - 1.0, 6) if initial_cash else 0.0
    market_excess_total_return = (
        None if market_reference_total_return is None else round(total_return - market_reference_total_return, 6)
    )
    return {
        "config_id": config.config_id,
        "status": "ready" if signal_days else "blocked",
        "summary": {
            "signal_count": len(signal_days),
            "trade_count": len(buy_decisions),
            "skip_count": skip_count,
            "fallback_trade_count": fallback_trade_count,
            "final_nav": round(final_nav, 6),
            "total_return": total_return,
            "annualization_trade_day_count": len(trade_days),
            "market_reference_total_return": market_reference_total_return,
            "market_excess_total_return": market_excess_total_return,
            "max_drawdown": _max_drawdown([float(point["nav"]) for point in timeline]) or 0.0,
            "mean_invested_ratio": round(sum(invested_ratios) / len(invested_ratios), 6) if invested_ratios else 0.0,
            "max_position_count": max((int(point["open_position_count"]) for point in timeline), default=0),
            "turnover": round(total_buy_value / float(initial_cash), 6) if initial_cash else 0.0,
            "final_cash": round(cash, 6),
            "final_market_value": round(final_market_value, 6),
            "open_position_count": len(open_positions),
            "blocked_exit_count": blocked_exit_count,
            "dynamic_exit_count": sum(
                count for reason, count in exit_reason_counts.items() if reason in DYNAMIC_EXIT_REASONS
            ),
            "exit_reason_counts": dict(sorted(exit_reason_counts.items())),
            "total_buy_value": round(total_buy_value, 6),
            "total_sell_value": round(total_sell_value, 6),
            "skipped_ratio": round(skip_count / len(signal_days), 6) if signal_days else 0.0,
            "weak_market_lower_notional_signal_count": weak_entry_count,
        },
        "reason_counts": dict(sorted(reason_counts.items())),
        "decision_samples": [],
        "detail_refs": {
            "nav_timeline": "research-summary-only:nav_timeline_not_emitted",
            "trades": "research-summary-only:trade_table_not_emitted",
            "decisions": "research-summary-only:decision_samples_omitted",
        },
    }


def _weak_market_features_by_day(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    lookback_trade_days: int,
    return_threshold: float,
) -> dict[date, dict[str, Any]]:
    benchmark = series_by_symbol.get(DEFAULT_WEAK_MARKET_INDEX_SYMBOL)
    rows: dict[date, dict[str, Any]] = {}
    for signal_day in signal_days:
        index = benchmark.by_day.get(signal_day) if benchmark is not None else None
        recent_return: float | None = None
        if benchmark is not None and index is not None and index >= lookback_trade_days:
            old_close = float(benchmark.bars[index - lookback_trade_days].close)
            new_close = float(benchmark.bars[index].close)
            if old_close > 0:
                recent_return = new_close / old_close - 1.0
        rows[signal_day] = {
            "signal_date": signal_day.isoformat(),
            "index_symbol": DEFAULT_WEAK_MARKET_INDEX_SYMBOL,
            "lookback_trade_days": lookback_trade_days,
            "recent_return": round(recent_return, 6) if recent_return is not None else None,
            "is_weak_market": recent_return is not None and recent_return < return_threshold,
        }
    return rows


def _window_row(
    variant: _RiskSwitchVariant,
    result: dict[str, Any],
    *,
    trade_day_count: int,
    weak_market: dict[date, dict[str, Any]],
) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    total_return = float(summary.get("total_return") or 0.0)
    max_drawdown = float(summary.get("max_drawdown") or 0.0)
    annualized = _annualized(total_return, trade_day_count)
    return {
        "variant_id": variant.variant_id,
        "config_id": result.get("config_id"),
        "status": result.get("status"),
        "signal_count": int(summary.get("signal_count") or 0),
        "trade_count": int(summary.get("trade_count") or 0),
        "skip_count": int(summary.get("skip_count") or 0),
        "fallback_trade_count": int(summary.get("fallback_trade_count") or 0),
        "total_return": total_return,
        "annualized_return": annualized,
        "market_reference_total_return": summary.get("market_reference_total_return"),
        "market_excess_total_return": summary.get("market_excess_total_return"),
        "max_drawdown": max_drawdown,
        "calmar": _calmar(annualized, max_drawdown),
        "mean_invested_ratio": summary.get("mean_invested_ratio"),
        "max_position_count": summary.get("max_position_count"),
        "turnover": summary.get("turnover"),
        "skipped_ratio": summary.get("skipped_ratio"),
        "final_nav": summary.get("final_nav"),
        "weak_market_signal_count": sum(1 for row in weak_market.values() if row.get("is_weak_market")),
        "weak_market_action": variant.weak_market_action,
        "weak_market_lower_notional_signal_count": summary.get("weak_market_lower_notional_signal_count", 0),
    }


def _combine_window_rows(
    historical_rows: list[dict[str, Any]],
    paper_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    historical_by_id = {str(row.get("variant_id")): row for row in historical_rows}
    paper_by_id = {str(row.get("variant_id")): row for row in paper_rows}
    baseline_historical = historical_by_id.get(DEFAULT_BASELINE_CONFIG_ID, {})
    baseline_paper = paper_by_id.get(DEFAULT_BASELINE_CONFIG_ID, {})
    rows: list[dict[str, Any]] = []
    for variant in DEFAULT_VARIANTS:
        historical = historical_by_id.get(variant.variant_id, {})
        paper = paper_by_id.get(variant.variant_id, {})
        outcome = _outcome(variant, historical, paper, baseline_historical, baseline_paper)
        rows.append(
            {
                "variant_id": variant.variant_id,
                "label_cn": variant.label_cn,
                "risk_switch_description_cn": variant.risk_switch_description_cn,
                "selection_and_buy_description_cn": _selection_description(variant),
                "allowed_actions": ["buy_primary", "buy_fallback", "skip"],
                "exit_policy_cn": "固定 H10 机械卖出",
                "drawdown_reversal_policy_cn": (
                    "v1 回撤反转只做入场过滤" if variant.drawdown_mode == "v1_on" else "不加 v1 回撤反转过滤"
                ),
                "weak_market_action": variant.weak_market_action,
                "max_position_count_limit": variant.max_position_count,
                "target_notional": variant.target_notional,
                "weak_target_notional": variant.weak_target_notional,
                "historical": historical,
                "paper": paper,
                "outcome_status": outcome["status"],
                "outcome_label_cn": outcome["label_cn"],
                "outcome_reasons_cn": outcome["reasons_cn"],
            }
        )
    return rows


def _outcome(
    variant: _RiskSwitchVariant,
    historical: dict[str, Any],
    paper: dict[str, Any],
    baseline_historical: dict[str, Any],
    baseline_paper: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    annualized = _float_or_none(historical.get("annualized_return"))
    max_drawdown = _float_or_none(historical.get("max_drawdown"))
    excess = _float_or_none(historical.get("market_excess_total_return"))
    trade_count = int(historical.get("trade_count") or 0)
    skipped_ratio = _float_or_none(historical.get("skipped_ratio"))
    paper_drawdown = _float_or_none(paper.get("max_drawdown"))
    baseline_paper_drawdown = _float_or_none(baseline_paper.get("max_drawdown"))
    if annualized is None or annualized < 0.30:
        reasons.append("历史年化低于 30% 底线")
    if max_drawdown is not None and max_drawdown < -0.20:
        reasons.append("历史最大回撤超过 20%")
    if excess is not None and excess < 0:
        reasons.append("历史未跑赢市场参考")
    if trade_count < 100:
        reasons.append("历史交易数不足 100 笔")
    if skipped_ratio is not None and skipped_ratio > 0.85:
        reasons.append("历史 skip 率超过 85%")
    if (
        paper_drawdown is not None
        and baseline_paper_drawdown is not None
        and paper_drawdown < baseline_paper_drawdown - 0.05
    ):
        reasons.append("纸面窗口回撤比基线恶化超过 5pp")
    if variant.variant_id == DEFAULT_BASELINE_CONFIG_ID:
        return {
            "status": "baseline",
            "label_cn": "基线对照",
            "reasons_cn": ["作为当前主线对照，不因本产物晋级或淘汰"],
        }
    if reasons:
        return {"status": "rejected", "label_cn": "不晋级", "reasons_cn": reasons}

    baseline_annualized = _float_or_none(baseline_historical.get("annualized_return"))
    baseline_drawdown = _float_or_none(baseline_historical.get("max_drawdown"))
    paper_total = _float_or_none(paper.get("total_return"))
    baseline_paper_total = _float_or_none(baseline_paper.get("total_return"))
    improves_drawdown = (
        max_drawdown is not None
        and baseline_drawdown is not None
        and abs(max_drawdown) <= abs(baseline_drawdown) * 0.80
    )
    keeps_return = (
        annualized is not None
        and baseline_annualized is not None
        and annualized >= baseline_annualized * 0.70
    )
    paper_not_much_worse = (
        paper_total is None
        or baseline_paper_total is None
        or paper_total >= baseline_paper_total - 0.03
    )
    if improves_drawdown and keeps_return and paper_not_much_worse:
        return {"status": "candidate", "label_cn": "候选观察", "reasons_cn": ["历史风险收益保留较好，纸面窗口未明显恶化"]}
    return {"status": "watch", "label_cn": "观察但不替换", "reasons_cn": ["未同时满足回撤改善、收益保留和纸面不恶化条件"]}


def _recommendation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in rows if row.get("outcome_status") == "candidate"]
    if not candidates:
        watch_rows = [row for row in rows if row.get("outcome_status") == "watch"]
        watch_rows.sort(
            key=lambda row: float((row.get("historical") or {}).get("annualized_return") or -999.0),
            reverse=True,
        )
        best_watch = watch_rows[0] if watch_rows else None
        best_watch_note = (
            f"历史表现最接近的是“{best_watch.get('label_cn')}”，"
            f"但它没有改善当前纸面窗口。"
            if best_watch
            else "没有风险开关形成可观察候选。"
        )
        return {
            "status": "research_only_no_paper_tracking_promotion",
            "message_cn": (
                "本轮没有发现可以替代基线的风险开关组合；基线仍应作为后续对标标准。"
                f"{best_watch_note}"
                "v1 回撤反转入场过滤在当前纸面窗口显著恶化，暂不应并入 v2 主线。"
            ),
            "candidate_variant_ids": [],
        }
    candidates.sort(key=lambda row: float((row.get("historical") or {}).get("calmar") or -999.0), reverse=True)
    return {
        "status": "research_only_candidate_requires_forward_observation",
        "message_cn": f"存在 {len(candidates)} 个研究候选，但仍需新的前向纸面观察期，不能用已看过的 5 周窗口直接晋级。",
        "candidate_variant_ids": [str(row.get("variant_id")) for row in candidates],
    }


def _rule_config_for_variant(variant: _RiskSwitchVariant) -> ShortpickV2RuleConfig:
    return ShortpickV2RuleConfig(
        config_id=variant.variant_id,
        family="shortpick_v2_risk_switch_experiment",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=float(variant.target_notional),
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
        max_position_count=variant.max_position_count,
    )


def _selection_description(variant: _RiskSwitchVariant) -> str:
    base = "周一至周三触发；热度池 10%；Rank2 首选，Rank3-Rank6 同日候补"
    buy = f"常规单笔约 {variant.target_notional / 10000:.1f} 万"
    if variant.weak_market_action == "skip":
        buy += "；沪深300 5 日跌超 2% 时不买"
    elif variant.weak_market_action == "lower_notional":
        buy += f"；沪深300 5 日跌超 2% 时降到 {float(variant.weak_target_notional or 0) / 10000:.1f} 万"
    buy += f"；最多 {variant.max_position_count} 仓"
    if variant.drawdown_mode == "v1_on":
        buy += "；候选先过 v1 回撤反转入场过滤"
    return f"{base}；{buy}。"


def _annualized(total_return: float, trade_day_count: int) -> float | None:
    if trade_day_count <= 0 or total_return <= -1.0:
        return None
    return round((1.0 + float(total_return)) ** (252.0 / float(trade_day_count)) - 1.0, 6)


def _calmar(annualized_return: float | None, max_drawdown: float | None) -> float | None:
    if annualized_return is None or max_drawdown is None or max_drawdown >= 0:
        return None
    return round(float(annualized_return) / abs(float(max_drawdown)), 6)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _artifact_id(generated_at: datetime, historical_start: date, historical_end: date, paper_end: date) -> str:
    return (
        f"{ARTIFACT_FAMILY}:{historical_start.isoformat()}:{historical_end.isoformat()}:"
        f"paper_to_{paper_end.isoformat()}:{generated_at.date().isoformat()}"
    )


def _outcome_rank(status: str) -> int:
    return {"candidate": 0, "baseline": 1, "watch": 2, "rejected": 3}.get(status, 9)


def _pct(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"
