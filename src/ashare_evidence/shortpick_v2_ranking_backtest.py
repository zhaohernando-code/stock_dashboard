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
)
from ashare_evidence.shortpick_portfolio_backtest import _eligible_signal_days, _trade_days
from ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix import (
    WEEKDAY_MODE_SPECS,
    _build_rank2_primary_top5_selections,
)
from ashare_evidence.shortpick_v2_next_diagnostics import (
    DEFAULT_BASELINE_TARGET_NOTIONAL,
    DEFAULT_HISTORICAL_END_DATE,
    DEFAULT_HISTORICAL_START_DATE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    DEFAULT_PAPER_START_DATE,
    DEFAULT_POOL_LIMIT,
    DEFAULT_RANK_LIMIT,
    _cached_regime_features,
    _contexts_by_signal_day,
    _load_daily_series_between,
    _pct,
    _summary_row,
)
from ashare_evidence.shortpick_v2_oos_loss_filter import DEFAULT_HOLDOUT_START_DATE, DEFAULT_TRAIN_END_DATE
from ashare_evidence.shortpick_v2_oos_position_rank_diagnostics import (
    _build_quiet_ranked_symbols,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    ShortpickV2RuleConfig,
    _coverage_notes,
    _market_reference_summary,
    _simulate_rule_config,
)
from ashare_evidence.shortpick_v2_theme_position_diagnostics import (
    DEFAULT_CURRENT_MONTH_END_DATE,
    _position_shape,
    _pre_signal_features,
)

ARTIFACT_FAMILY = "shortpick_v2_ranking_backtest"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_ranking_backtest:v1"
DEFAULT_MIN_ACCEPTABLE_ANNUALIZED_RETURN = 0.30
DEFAULT_MAX_ACCEPTABLE_DRAWDOWN = -0.25
DEFAULT_WEEKDAY_MODE = "mtw"


@dataclass(frozen=True)
class _RankingVariant:
    variant_id: str
    label_cn: str
    source_id: str
    description_cn: str


RANKING_VARIANTS = (
    _RankingVariant(
        "baseline_quiet_rank2_mtw",
        "原 v2 安静突破 Rank2",
        "baseline_quiet_ranked",
        "沿用当前 v2：安静突破排序，周一至周三触发，Rank2 首选，Rank3-Rank6 同日候补。",
    ),
    _RankingVariant(
        "industry_heat_pullback_rank2_mtw",
        "行业热度 + 回撤蓄势",
        "industry_heat_pullback",
        "行业 10 日热度靠前、位置不过度追高、成交额和 20 日趋势较好的股票前置。",
    ),
    _RankingVariant(
        "industry_heat_amount_rank2_mtw",
        "行业热度 + 成交额",
        "industry_heat_amount",
        "行业 10 日热度靠前、成交额和 20 日趋势较好的股票前置。",
    ),
    _RankingVariant(
        "pullback_low_chase_rank2_mtw",
        "回撤优先 + 低追高",
        "pullback_low_chase",
        "优先回撤蓄势和低追高形态，降低高位追强的排序权重。",
    ),
)


def build_shortpick_v2_ranking_backtest_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    train_end_date: date = DEFAULT_TRAIN_END_DATE,
    holdout_start_date: date = DEFAULT_HOLDOUT_START_DATE,
    historical_end_date: date = DEFAULT_HISTORICAL_END_DATE,
    paper_start_date: date = DEFAULT_PAPER_START_DATE,
    paper_end_date: date = DEFAULT_CURRENT_MONTH_END_DATE,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    rank_limit: int = DEFAULT_RANK_LIMIT,
    target_notional: float = DEFAULT_BASELINE_TARGET_NOTIONAL,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    min_acceptable_annualized_return: float = DEFAULT_MIN_ACCEPTABLE_ANNUALIZED_RETURN,
    max_acceptable_drawdown: float = DEFAULT_MAX_ACCEPTABLE_DRAWDOWN,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if horizon_days != DEFAULT_HORIZON_DAYS:
        raise ValueError("ranking backtest currently requires H10; horizon_days must be 10")
    if rank_limit < DEFAULT_RANK_LIMIT:
        raise ValueError("rank_limit must be at least 6 so Rank2-Rank6 fallback candidates are available")
    if not (historical_start_date <= train_end_date < holdout_start_date <= historical_end_date < paper_end_date):
        raise ValueError("train/holdout/paper windows must be ordered")

    generated_at = generated_at or datetime.now(UTC)
    raw_series_by_symbol = _load_daily_series_between(
        session,
        start_date=historical_start_date - timedelta(days=420),
        end_date=paper_end_date + timedelta(days=max(45, horizon_days * 5)),
    )
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    all_signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=paper_end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    all_trade_days = _trade_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=paper_end_date + timedelta(days=max(30, horizon_days * 4)),
        min_symbol_count=min_signal_symbol_count,
    )
    contexts_by_day = _contexts_by_signal_day(series_by_symbol, signal_days=all_signal_days)
    ranked_sources = _ranking_sources(
        series_by_symbol,
        signal_days=all_signal_days,
        contexts_by_day=contexts_by_day,
        pool_limit=pool_limit,
        rank_limit=max(rank_limit, 80),
    )
    selections_by_variant = {
        variant.variant_id: _top5_from_ranked_source(
            signal_days=all_signal_days,
            contexts_by_day=contexts_by_day,
            ranked=ranked_sources[variant.source_id],
            pool_limit=pool_limit,
        )
        for variant in RANKING_VARIANTS
    }
    windows = _analysis_windows(
        historical_start_date=historical_start_date,
        train_end_date=train_end_date,
        holdout_start_date=holdout_start_date,
        historical_end_date=historical_end_date,
        paper_start_date=paper_start_date,
        paper_end_date=paper_end_date,
    )
    rows: list[dict[str, Any]] = []
    for window in windows:
        signal_days = [day for day in all_signal_days if window["start_date"] <= day <= window["end_date"]]
        trade_days = [
            day
            for day in all_trade_days
            if window["start_date"] <= day <= window["end_date"] + timedelta(days=max(30, horizon_days * 4))
        ]
        market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
        for variant in RANKING_VARIANTS:
            config = _rule_config(variant.variant_id, target_notional=target_notional)
            result = _simulate_rule_config(
                series_by_symbol,
                signal_days=signal_days,
                trade_days=trade_days,
                selections=selections_by_variant[variant.variant_id],
                config=config,
                initial_cash=initial_cash,
                entry_price_source=entry_price_source,
                horizon_days=horizon_days,
                cost_bps=cost_bps,
                stamp_tax_bps=stamp_tax_bps,
                market_reference_total_return=market_reference.get("total_return"),
                decision_sample_limit=0,
            )
            rows.append(
                _result_row(
                    result,
                    window=window,
                    variant=variant,
                    trade_day_count=len(trade_days),
                    min_acceptable_annualized_return=min_acceptable_annualized_return,
                    max_acceptable_drawdown=max_acceptable_drawdown,
                )
            )
    comparison = _comparison(rows)
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, historical_start_date, paper_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready" if rows else "blocked",
        "claim_ceiling": "research_observation",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "question_cn": "在相同 H10、20 万账户、固定 8.5 万、MTW Rank2→Top5 执行框架下，替代排序是否比当前 v2 排序更稳。",
            "historical_start_date": historical_start_date.isoformat(),
            "train_end_date": train_end_date.isoformat(),
            "holdout_start_date": holdout_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "weekday_mode": DEFAULT_WEEKDAY_MODE,
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "target_notional": target_notional,
            "entry_price_source": entry_price_source,
            "min_acceptable_annualized_return": min_acceptable_annualized_return,
            "max_acceptable_drawdown": max_acceptable_drawdown,
            "promotion_status": "research_only_no_strategy_promotion",
        },
        "data_scope": {
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "signal_day_count": len(all_signal_days),
            "trade_day_count": len(all_trade_days),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "variant_definitions": [_variant_artifact(variant) for variant in RANKING_VARIANTS],
        "result_rows": rows,
        "comparison": comparison,
        "interpretation": _interpretation(comparison),
        "leakage_audit": {
            "status": "passed",
            "notes": [
                "All ranking inputs are computed from signal-day-or-earlier daily context.",
                "This artifact evaluates realized replay returns; no current-month winner label is used by the simulated strategy.",
                "The strategy remains research-only; no paper-tracking rule is promoted by this artifact.",
            ],
        },
        "event_refs": [
            "shortpick_v2.ranking_backtest.generated",
            f"shortpick_v2.ranking_backtest.window.{historical_start_date.isoformat()}_{paper_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_ranking_backtest_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"ranking backtest validation failed: {validation}")
    return payload


def write_shortpick_v2_ranking_backtest_artifact(
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
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_shortpick_v2_ranking_backtest_markdown(payload), encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_ranking_backtest_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_ranking_backtest_payload(json.loads(Path(artifact_path).read_text(encoding="utf-8")))


def validate_shortpick_v2_ranking_backtest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    rows = payload.get("result_rows") if isinstance(payload.get("result_rows"), list) else []
    window_ids = {str(row.get("window_id")) for row in rows if isinstance(row, dict)}
    variant_ids = {str(row.get("variant_id")) for row in rows if isinstance(row, dict)}
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_strategy_promotion", str(scope.get("promotion_status")))
    check("windows_ready", {"train", "holdout", "historical_all", "paper"}.issubset(window_ids), str(sorted(window_ids)))
    check("variants_ready", len(variant_ids) >= 4, str(sorted(variant_ids)))
    check("baseline_ready", "baseline_quiet_rank2_mtw" in variant_ids, str(sorted(variant_ids)))
    check("comparison_ready", isinstance(payload.get("comparison"), dict), str(type(payload.get("comparison"))))
    check("leakage_status", (payload.get("leakage_audit") or {}).get("status") == "passed", str((payload.get("leakage_audit") or {}).get("status")))
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "recommendation_status": (payload.get("interpretation") or {}).get("status"),
            "candidate_variant_ids": (payload.get("comparison") or {}).get("candidate_variant_ids"),
        },
    }


def render_shortpick_v2_ranking_backtest_markdown(payload: dict[str, Any]) -> str:
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    rows = payload.get("result_rows") if isinstance(payload.get("result_rows"), list) else []
    comparison = payload.get("comparison") if isinstance(payload.get("comparison"), dict) else {}
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    lines = [
        "# 试验田 v2 排序替代正式回测",
        "",
        "本产物是研究型回测，不晋级或替换纸面追踪策略。",
        "",
        "## 结论",
        "",
        str(interpretation.get("message_cn") or "暂无结论。"),
        "",
        "## 回测约束",
        "",
        f"- 资金：{float(scope.get('initial_cash') or 0) / 10000:.1f} 万；单笔：{float(scope.get('target_notional') or 0) / 10000:.1f} 万；卖出：H{int(scope.get('horizon_days') or 0)}。",
        f"- 交易日口径：{scope.get('weekday_mode')}，保持当前 v2 的 Rank2 首选、Rank3-Rank6 同日候补框架。",
        f"- 合格标准：年化不低于 {_pct(scope.get('min_acceptable_annualized_return'))}，且必须跑赢市场参考。",
        "- paper 窗口只有约 5 周、单方案 7-9 笔交易，只用于压力观察，不能单独作为晋级依据。",
        "",
        "## 各窗口结果",
        "",
    ]
    for window_id, title in (
        ("train", "训练段"),
        ("holdout", "样本外 holdout"),
        ("historical_all", "历史全段"),
        ("paper", "纸面窗口"),
    ):
        lines.extend(
            [
                f"### {title}",
                "",
                "| 排序方案 | 总收益 | 年化 | 市场超额 | 最大回撤 | 交易 | skip | 是否达标 |",
                "|----------|--------|------|----------|----------|------|------|----------|",
            ]
        )
        for row in [item for item in rows if item.get("window_id") == window_id]:
            lines.append(
                "| {label} | {total} | {ann} | {excess} | {dd} | {trades} | {skip} | {qualified} |".format(
                    label=row.get("label_cn"),
                    total=_pct(row.get("total_return")),
                    ann=_pct(row.get("annualized_return")),
                    excess=_pct(row.get("market_excess_total_return")),
                    dd=_pct(row.get("max_drawdown")),
                    trades=int(row.get("trade_count") or 0),
                    skip=_pct(row.get("skipped_ratio")),
                    qualified="是" if row.get("meets_user_floor") else "否",
                )
            )
        lines.append("")
    lines.extend(
        [
            "## 相对原 v2 排序",
            "",
            "| 排序方案 | holdout 收益差 | paper 收益差 | holdout 回撤差 | 结论 |",
            "|----------|----------------|--------------|----------------|------|",
        ]
    )
    for row in comparison.get("delta_rows") or []:
        lines.append(
            "| {label} | {holdout} | {paper} | {drawdown} | {verdict} |".format(
                label=row.get("label_cn"),
                holdout=_pct(row.get("holdout_total_return_delta")),
                paper=_pct(row.get("paper_total_return_delta")),
                drawdown=_pct(row.get("holdout_max_drawdown_delta")),
                verdict=row.get("verdict_cn"),
            )
        )
    lines.extend(["", "## 下一步"])
    for step in interpretation.get("recommended_next_steps_cn") or []:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def _ranking_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    pool_limit: int,
    rank_limit: int,
) -> dict[str, dict[date, list[str]]]:
    sources = {
        "baseline_quiet_ranked": _build_quiet_ranked_symbols(
            signal_days=signal_days,
            contexts_by_day=contexts_by_day,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
        )
    }
    sources.update(_diagnostic_rankings_fast(series_by_symbol, signal_days=signal_days, contexts_by_day=contexts_by_day))
    return sources


def _diagnostic_rankings_fast(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
) -> dict[str, dict[date, list[str]]]:
    output: dict[str, dict[date, list[str]]] = {
        "industry_heat_pullback": {},
        "industry_heat_amount": {},
        "pullback_low_chase": {},
    }
    for signal_day in signal_days:
        contexts = contexts_by_day.get(signal_day) or []
        industry_heat = _industry_heat(contexts)
        amount_pct = _percentile_by_symbol(contexts, key="amount")
        ret20_pct = _percentile_by_symbol(contexts, key="return_20d")
        enriched = []
        for context in contexts:
            symbol = str(context.get("symbol"))
            shape = _context_position_shape(series_by_symbol, context, signal_day=signal_day)
            enriched.append(
                {
                    **context,
                    "position_shape": shape,
                    "industry_heat": industry_heat.get(str(context.get("industry") or "unknown"), 0.0),
                    "amount_pct": amount_pct.get(symbol, 0.0),
                    "ret20_pct": ret20_pct.get(symbol, 0.0),
                }
            )
        output["industry_heat_pullback"][signal_day] = _rank_by_score(enriched, _score_industry_heat_pullback)
        output["industry_heat_amount"][signal_day] = _rank_by_score(enriched, _score_industry_heat_amount)
        output["pullback_low_chase"][signal_day] = _rank_by_score(enriched, _score_pullback_low_chase)
    return output


def _industry_heat(contexts: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for context in contexts:
        industry = str(context.get("industry") or "unknown")
        grouped.setdefault(industry, []).append(float(context.get("return_10d") or 0.0))
    raw = {industry: sum(values) / len(values) if values else 0.0 for industry, values in grouped.items()}
    ordered = sorted(raw.items(), key=lambda item: item[1])
    denom = max(1, len(ordered) - 1)
    return {industry: index / denom for index, (industry, _) in enumerate(ordered)}


def _percentile_by_symbol(contexts: list[dict[str, Any]], *, key: str) -> dict[str, float]:
    ordered = sorted(
        ((str(context.get("symbol")), float(context.get(key) or 0.0)) for context in contexts),
        key=lambda item: item[1],
    )
    if len(ordered) <= 1:
        return {symbol: 0.0 for symbol, _ in ordered}
    denom = float(len(ordered) - 1)
    return {symbol: index / denom for index, (symbol, _) in enumerate(ordered)}


def _context_position_shape(series_by_symbol: dict[str, Any], context: dict[str, Any], *, signal_day: date) -> str:
    series = series_by_symbol.get(str(context.get("symbol")))
    if series is None:
        return "other"
    features = _pre_signal_features(series, signal_day)
    return _position_shape(features.get("pre5_return"), features.get("price_vs_20d_high"))


def _rank_by_score(enriched: list[dict[str, Any]], scorer: Any) -> list[str]:
    ranked = sorted(
        enriched,
        key=lambda item: (
            scorer(item),
            float(item.get("amount") or 0.0),
            float(item.get("return_20d") or 0.0),
        ),
        reverse=True,
    )
    return [str(item["symbol"]) for item in ranked]


def _score_industry_heat_pullback(item: dict[str, Any]) -> float:
    shape_bonus = 1.0 if item.get("position_shape") in {"pullback_setup", "low_pre5_pullback"} else 0.0
    chase_penalty = 1.0 if item.get("position_shape") == "chase_high" else 0.0
    return (
        0.42 * float(item.get("industry_heat") or 0.0)
        + 0.28 * shape_bonus
        + 0.20 * float(item.get("amount_pct") or 0.0)
        + 0.10 * float(item.get("ret20_pct") or 0.0)
        - 0.25 * chase_penalty
    )


def _score_industry_heat_amount(item: dict[str, Any]) -> float:
    return (
        0.45 * float(item.get("industry_heat") or 0.0)
        + 0.35 * float(item.get("amount_pct") or 0.0)
        + 0.20 * float(item.get("ret20_pct") or 0.0)
    )


def _score_pullback_low_chase(item: dict[str, Any]) -> float:
    shape_bonus = 1.0 if item.get("position_shape") in {"pullback_setup", "low_pre5_pullback"} else 0.0
    chase_penalty = 1.0 if item.get("position_shape") == "chase_high" else 0.0
    return (
        0.55 * shape_bonus
        + 0.25 * float(item.get("ret20_pct") or 0.0)
        + 0.20 * float(item.get("amount_pct") or 0.0)
        - 0.35 * chase_penalty
    )


def _top5_from_ranked_source(
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    ranked: dict[date, list[str]],
    pool_limit: int,
) -> dict[date, list[str]]:
    regime_features = _cached_regime_features(
        contexts_by_day=contexts_by_day,
        signal_days=signal_days,
        pool_limit=pool_limit,
    )
    return _build_rank2_primary_top5_selections(
        signal_days,
        quiet_base_selections=ranked,
        regime_features=regime_features,
        weekday_spec=WEEKDAY_MODE_SPECS[DEFAULT_WEEKDAY_MODE],
    )


def _analysis_windows(
    *,
    historical_start_date: date,
    train_end_date: date,
    holdout_start_date: date,
    historical_end_date: date,
    paper_start_date: date,
    paper_end_date: date,
) -> list[dict[str, Any]]:
    return [
        {
            "window_id": "train",
            "label_cn": "训练段",
            "start_date": historical_start_date,
            "end_date": train_end_date,
        },
        {
            "window_id": "holdout",
            "label_cn": "样本外 holdout",
            "start_date": holdout_start_date,
            "end_date": historical_end_date,
        },
        {
            "window_id": "historical_all",
            "label_cn": "历史全段",
            "start_date": historical_start_date,
            "end_date": historical_end_date,
        },
        {
            "window_id": "paper",
            "label_cn": "纸面窗口",
            "start_date": paper_start_date,
            "end_date": paper_end_date,
        },
    ]


def _rule_config(variant_id: str, *, target_notional: float) -> ShortpickV2RuleConfig:
    return ShortpickV2RuleConfig(
        config_id=variant_id,
        family=ARTIFACT_FAMILY,
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=target_notional,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
        max_position_count=5,
    )


def _result_row(
    result: dict[str, Any],
    *,
    window: dict[str, Any],
    variant: _RankingVariant,
    trade_day_count: int,
    min_acceptable_annualized_return: float,
    max_acceptable_drawdown: float,
) -> dict[str, Any]:
    summary = _summary_row(result, trade_day_count=trade_day_count)
    annualized = _float_or_none(summary.get("annualized_return"))
    excess = _float_or_none(summary.get("market_excess_total_return"))
    drawdown = _float_or_none(summary.get("max_drawdown"))
    meets_return = annualized is not None and annualized >= min_acceptable_annualized_return
    beats_market = excess is not None and excess > 0
    drawdown_ok = drawdown is not None and drawdown >= max_acceptable_drawdown
    return {
        "window_id": window["window_id"],
        "window_label_cn": window["label_cn"],
        "window_start_date": window["start_date"].isoformat(),
        "window_end_date": window["end_date"].isoformat(),
        "variant_id": variant.variant_id,
        "label_cn": variant.label_cn,
        "source_id": variant.source_id,
        "description_cn": variant.description_cn,
        **summary,
        "meets_min_annualized_return": meets_return,
        "beats_market_reference": beats_market,
        "drawdown_within_limit": drawdown_ok,
        "meets_user_floor": meets_return and beats_market and drawdown_ok,
    }


def _comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_by_window = {
        str(row.get("window_id")): row
        for row in rows
        if row.get("variant_id") == "baseline_quiet_rank2_mtw"
    }
    delta_rows: list[dict[str, Any]] = []
    candidate_ids: list[str] = []
    positive_holdout_non_candidate_ids: list[str] = []
    for variant in RANKING_VARIANTS:
        if variant.variant_id == "baseline_quiet_rank2_mtw":
            continue
        by_window = {
            str(row.get("window_id")): row
            for row in rows
            if row.get("variant_id") == variant.variant_id
        }
        holdout = by_window.get("holdout") or {}
        paper = by_window.get("paper") or {}
        baseline_holdout = baseline_by_window.get("holdout") or {}
        baseline_paper = baseline_by_window.get("paper") or {}
        holdout_delta = _delta(holdout.get("total_return"), baseline_holdout.get("total_return"))
        paper_delta = _delta(paper.get("total_return"), baseline_paper.get("total_return"))
        drawdown_delta = _delta(holdout.get("max_drawdown"), baseline_holdout.get("max_drawdown"))
        holdout_ok = bool(holdout.get("meets_user_floor")) and (holdout_delta is not None and holdout_delta > 0)
        paper_better = paper_delta is not None and paper_delta > 0
        drawdown_not_worse = drawdown_delta is not None and drawdown_delta >= -0.05
        if holdout_ok and paper_better and drawdown_not_worse:
            candidate_ids.append(variant.variant_id)
            verdict = "可进入下一轮参数验证"
        elif holdout_delta is not None and holdout_delta > 0 and not paper_better:
            verdict = "holdout 改善但 paper 未改善"
        elif paper_better and not holdout_ok:
            verdict = "paper 改善但历史样本外不达标"
        else:
            verdict = "未优于原 v2 排序"
        if not holdout_ok and _float_or_none(holdout.get("total_return")) is not None:
            if float(holdout.get("total_return") or 0.0) > 0:
                positive_holdout_non_candidate_ids.append(variant.variant_id)
        delta_rows.append(
            {
                "variant_id": variant.variant_id,
                "label_cn": variant.label_cn,
                "holdout_total_return_delta": holdout_delta,
                "paper_total_return_delta": paper_delta,
                "holdout_max_drawdown_delta": drawdown_delta,
                "holdout_meets_user_floor": bool(holdout.get("meets_user_floor")),
                "paper_meets_user_floor": bool(paper.get("meets_user_floor")),
                "verdict_cn": verdict,
            }
        )
    return {
        "baseline_variant_id": "baseline_quiet_rank2_mtw",
        "candidate_variant_ids": candidate_ids,
        "positive_holdout_non_candidate_ids": positive_holdout_non_candidate_ids,
        "delta_rows": delta_rows,
    }


def _interpretation(comparison: dict[str, Any]) -> dict[str, Any]:
    candidate_ids = list(comparison.get("candidate_variant_ids") or [])
    positive_holdout_ids = list(comparison.get("positive_holdout_non_candidate_ids") or [])
    if candidate_ids:
        return {
            "status": "candidate_for_parameter_validation",
            "message_cn": f"{'、'.join(candidate_ids)} 同时改善 holdout 与 paper，并满足基础收益/回撤门槛，可进入下一轮参数验证。",
            "recommended_next_steps_cn": [
                "对候选排序做小网格参数验证，保持窗口和资金约束不变。",
                "如果参数验证仍通过，再对候选加入纸面追踪对照组；不要直接替换冻结策略。",
            ],
        }
    steps = [
        "不要继续在这组三个排序方向上扩大参数网格，避免围绕弱方向过拟合。",
        "下一步回到 v1 冻结策略资金约束版，或专门验证交易日/行业主题池是否才是主要矛盾。",
    ]
    if positive_holdout_ids:
        steps.append(
            f"{'、'.join(positive_holdout_ids)} 在 holdout 为正但弱于原 v2，可作为后续 v1/主题池研究的辅助观察项，不单独晋级。"
        )
    return {
        "status": "no_ranking_variant_promoted",
        "message_cn": "本轮替代排序没有同时满足历史样本外、paper 改善和收益/回撤门槛，不能晋级。",
        "recommended_next_steps_cn": steps,
    }


def _variant_artifact(variant: _RankingVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "label_cn": variant.label_cn,
        "source_id": variant.source_id,
        "description_cn": variant.description_cn,
    }


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _delta(value: object, baseline: object) -> float | None:
    if value is None or baseline is None:
        return None
    return round(float(value) - float(baseline), 6)


def _artifact_id(generated_at: datetime, start: date, end: date) -> str:
    return f"{ARTIFACT_FAMILY}:{start.isoformat()}:{end.isoformat()}:{generated_at.date().isoformat()}"
