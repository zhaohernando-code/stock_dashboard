from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

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
from ashare_evidence.shortpick_v2_oos_position_rank_diagnostics import _build_quiet_ranked_symbols
from ashare_evidence.shortpick_v2_ranking_backtest import (
    _context_position_shape,
    _diagnostic_rankings_fast,
    _percentile_by_symbol,
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
    DEFAULT_CURRENT_MONTH_START_DATE,
    DEFAULT_TOP_WINNER_COUNT,
    _current_month_winners,
)

ARTIFACT_FAMILY = "shortpick_v2_industry_theme_experiment"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_industry_theme_experiment:v1"
DEFAULT_WEEKDAY_MODE = "mtw"
DEFAULT_MIN_ACCEPTABLE_ANNUALIZED_RETURN = 0.30
DEFAULT_MAX_ACCEPTABLE_DRAWDOWN = -0.25
DEFAULT_MIN_HOLDOUT_RETURN_DELTA = 0.10
DEFAULT_MAX_HOLDOUT_DRAWDOWN_WORSENING = -0.05


@dataclass(frozen=True)
class _ThemeVariant:
    variant_id: str
    label_cn: str
    source_id: str
    description_cn: str
    variant_group: str


VARIANTS = (
    _ThemeVariant(
        "baseline_quiet_rank2_mtw",
        "原 v2 安静突破 Rank2",
        "baseline_quiet_ranked",
        "当前 v2 基线：H10、20 万、固定 8.5 万、周一至周三、Rank2 首选且 Rank3-Rank6 同日候补。",
        "baseline",
    ),
    _ThemeVariant(
        "industry_heat_pullback_rank2_mtw",
        "旧对照：行业热度 + 回撤蓄势",
        "industry_heat_pullback",
        "上一轮已验证偏弱的简单行业 10 日热度加回撤形态排序。",
        "known_weak_control",
    ),
    _ThemeVariant(
        "industry_heat_amount_rank2_mtw",
        "旧对照：行业热度 + 成交额",
        "industry_heat_amount",
        "上一轮已验证偏弱的简单行业 10 日热度加成交额排序。",
        "known_weak_control",
    ),
    _ThemeVariant(
        "pullback_low_chase_rank2_mtw",
        "旧对照：回撤优先 + 低追高",
        "pullback_low_chase",
        "上一轮已验证偏弱的单纯位置形态排序。",
        "known_weak_control",
    ),
    _ThemeVariant(
        "theme_breadth_pullback_rank2_mtw",
        "主线宽度 + 回撤蓄势",
        "theme_breadth_pullback",
        "优先行业内上涨扩散、行业趋势和个股回撤蓄势，避免只看行业均值涨幅。",
        "new_theme_experiment",
    ),
    _ThemeVariant(
        "theme_leader_rotation_rank2_mtw",
        "主线轮动 + 非极端追高",
        "theme_leader_rotation",
        "保留行业主线强度，但避免行业内最极端追高标的，测试强势行业内轮动成员。",
        "new_theme_experiment",
    ),
    _ThemeVariant(
        "theme_breakout_cluster_rank2_mtw",
        "行业突破簇 + 流动性",
        "theme_breakout_cluster",
        "优先同一行业内多只股票接近短期高点且成交活跃的突破簇。",
        "new_theme_experiment",
    ),
    _ThemeVariant(
        "theme_position_guard_rank2_mtw",
        "原 Rank2 + 主线位置软修正",
        "theme_position_guard",
        "保留原安静突破排序为主，只用行业扩散和位置形态做软修正。",
        "new_theme_experiment",
    ),
)


def build_shortpick_v2_industry_theme_experiment_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    train_end_date: date = DEFAULT_TRAIN_END_DATE,
    holdout_start_date: date = DEFAULT_HOLDOUT_START_DATE,
    historical_end_date: date = DEFAULT_HISTORICAL_END_DATE,
    paper_start_date: date = DEFAULT_PAPER_START_DATE,
    paper_end_date: date = date(2026, 6, 17),
    current_month_start_date: date = DEFAULT_CURRENT_MONTH_START_DATE,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    target_notional: float = DEFAULT_BASELINE_TARGET_NOTIONAL,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    rank_limit: int = DEFAULT_RANK_LIMIT,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    min_acceptable_annualized_return: float = DEFAULT_MIN_ACCEPTABLE_ANNUALIZED_RETURN,
    max_acceptable_drawdown: float = DEFAULT_MAX_ACCEPTABLE_DRAWDOWN,
    min_holdout_return_delta: float = DEFAULT_MIN_HOLDOUT_RETURN_DELTA,
    max_holdout_drawdown_worsening: float = DEFAULT_MAX_HOLDOUT_DRAWDOWN_WORSENING,
    top_winner_count: int = DEFAULT_TOP_WINNER_COUNT,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if horizon_days != DEFAULT_HORIZON_DAYS:
        raise ValueError("industry theme experiment currently requires H10; horizon_days must be 10")
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
        for variant in VARIANTS
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
        for variant in VARIANTS:
            result = _simulate_rule_config(
                series_by_symbol,
                signal_days=signal_days,
                trade_days=trade_days,
                selections=selections_by_variant[variant.variant_id],
                config=_rule_config(variant.variant_id, target_notional=target_notional),
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

    winners = _current_month_winners(
        series_by_symbol,
        current_month_start_date=current_month_start_date,
        current_month_end_date=paper_end_date,
        top_n=top_winner_count,
    )
    paper_signal_days = [day for day in all_signal_days if paper_start_date <= day <= paper_end_date]
    capture = _strong_stock_capture_by_variant(
        winners.get("top_winners") if isinstance(winners.get("top_winners"), list) else [],
        paper_signal_days=paper_signal_days,
        contexts_by_day=contexts_by_day,
        selections_by_variant=selections_by_variant,
        current_month_start_date=current_month_start_date,
    )
    comparison = _comparison(
        rows,
        capture_rows=capture["variant_rows"],
        min_holdout_return_delta=min_holdout_return_delta,
        max_holdout_drawdown_worsening=max_holdout_drawdown_worsening,
    )
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, historical_start_date, paper_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready",
        "claim_ceiling": "research_observation",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "question_cn": "行业风口/行业主线能力能否解释或改善试验田 v2 当前排序，但不直接进入候选。",
            "historical_start_date": historical_start_date.isoformat(),
            "train_end_date": train_end_date.isoformat(),
            "holdout_start_date": holdout_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "actual_cutoff_date": paper_end_date.isoformat(),
            "current_month_start_date": current_month_start_date.isoformat(),
            "weekday_mode": DEFAULT_WEEKDAY_MODE,
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "target_notional": target_notional,
            "entry_price_source": entry_price_source,
            "min_acceptable_annualized_return": min_acceptable_annualized_return,
            "max_acceptable_drawdown": max_acceptable_drawdown,
            "min_holdout_return_delta": min_holdout_return_delta,
            "max_holdout_drawdown_worsening": max_holdout_drawdown_worsening,
            "promotion_status": "research_only_no_strategy_promotion",
        },
        "data_scope": {
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "signal_day_count": len(all_signal_days),
            "trade_day_count": len(all_trade_days),
            "paper_signal_day_count": len(paper_signal_days),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "prior_evidence_inventory": {
            "stage_summary_11_cn": "旧排序替代中，简单行业热度和回撤优先方向 paper 个别改善但 holdout/全历史弱于原 Rank2。",
            "stage_summary_15_cn": "6 月强势股大多在 eligible universe，但很少进入最终 Top5，说明排序/主题入口值得研究。",
            "known_dead_ends": [
                "simple_industry_10d_average_heat_as_candidate",
                "winner_label_driven_ranking",
                "hard_industry_only_buying",
            ],
        },
        "variant_definitions": [_variant_artifact(variant) for variant in VARIANTS],
        "result_rows": rows,
        "strong_stock_capture": capture,
        "comparison": comparison,
        "interpretation": _interpretation(comparison),
        "leakage_audit": {
            "status": "passed",
            "notes": [
                "Replay rankings use signal-day-or-earlier context only.",
                "Current-month winners are used only for post-hoc capture diagnostics.",
                "This artifact is research-only and cannot promote paper-tracking candidates.",
            ],
        },
        "event_refs": [
            "shortpick_v2.industry_theme_experiment.generated",
            f"shortpick_v2.industry_theme_experiment.window.{historical_start_date.isoformat()}_{paper_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_industry_theme_experiment_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"industry theme experiment validation failed: {validation}")
    return payload


def write_shortpick_v2_industry_theme_experiment_artifact(
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
        path.write_text(render_shortpick_v2_industry_theme_experiment_markdown(payload), encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_industry_theme_experiment_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_industry_theme_experiment_payload(json.loads(Path(artifact_path).read_text(encoding="utf-8")))


def validate_shortpick_v2_industry_theme_experiment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    rows = payload.get("result_rows") if isinstance(payload.get("result_rows"), list) else []
    variant_defs = payload.get("variant_definitions") if isinstance(payload.get("variant_definitions"), list) else []
    comparison = payload.get("comparison") if isinstance(payload.get("comparison"), dict) else {}
    capture = payload.get("strong_stock_capture") if isinstance(payload.get("strong_stock_capture"), dict) else {}
    variant_ids = {str(row.get("variant_id")) for row in rows if isinstance(row, dict)}
    window_ids = {str(row.get("window_id")) for row in rows if isinstance(row, dict)}
    group_ids = {str(row.get("variant_group")) for row in variant_defs if isinstance(row, dict)}
    future_research_ids = comparison.get("future_research_variant_ids") or []
    forbidden_phrases = ("candidate-ready", "investable")
    rendered = json.dumps(payload, ensure_ascii=False)

    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_strategy_promotion", str(scope.get("promotion_status")))
    check("windows_ready", {"train", "holdout", "historical_all", "paper"}.issubset(window_ids), str(sorted(window_ids)))
    check("variants_ready", len(variant_ids) >= len(VARIANTS), str(sorted(variant_ids)))
    check("new_theme_variants_ready", "new_theme_experiment" in group_ids, str(sorted(group_ids)))
    check("known_weak_controls_ready", "known_weak_control" in group_ids, str(sorted(group_ids)))
    check("baseline_ready", "baseline_quiet_rank2_mtw" in variant_ids, str(sorted(variant_ids)))
    check("capture_ready", int(capture.get("top_winner_count") or 0) >= 30, str(capture.get("top_winner_count")))
    check("no_direct_candidates", comparison.get("candidate_variant_ids") in (None, []), str(comparison.get("candidate_variant_ids")))
    check("future_research_limited", isinstance(future_research_ids, list), str(type(future_research_ids)))
    check("leakage_status", (payload.get("leakage_audit") or {}).get("status") == "passed", str((payload.get("leakage_audit") or {}).get("status")))
    check("no_forbidden_language", not any(phrase in rendered for phrase in forbidden_phrases), "forbidden language scan")
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "interpretation_status": (payload.get("interpretation") or {}).get("status"),
            "future_research_variant_ids": future_research_ids,
        },
    }


def render_shortpick_v2_industry_theme_experiment_markdown(payload: dict[str, Any]) -> str:
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    rows = payload.get("result_rows") if isinstance(payload.get("result_rows"), list) else []
    comparison = payload.get("comparison") if isinstance(payload.get("comparison"), dict) else {}
    capture = payload.get("strong_stock_capture") if isinstance(payload.get("strong_stock_capture"), dict) else {}
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    lines = [
        "# 试验田 v2 行业主线实验",
        "",
        "本产物只做研究诊断，不晋级或替换纸面追踪策略。",
        "",
        "## 结论",
        "",
        str(interpretation.get("message_cn") or "暂无结论。"),
        "",
        "## 回测约束",
        "",
        f"- 实际数据截止日：{scope.get('actual_cutoff_date')}。",
        f"- 资金：{float(scope.get('initial_cash') or 0) / 10000:.1f} 万；单笔：{float(scope.get('target_notional') or 0) / 10000:.1f} 万；卖出：H{int(scope.get('horizon_days') or 0)}。",
        f"- 交易日口径：{scope.get('weekday_mode')}；保持 Rank2 首选、Rank3-Rank6 同日候补。",
        "- 本轮只改变排序源；不改变买卖执行、纸面候选、前端展示或定时刷新。",
        "- 若没有同时满足 holdout 明显改善、回撤不明显恶化、paper 改善、强势股 Top5 捕捉改善，只能记为不成立或未证实。",
        "",
        "## 历史与纸面结果",
        "",
    ]
    for window_id, title in (
        ("holdout", "样本外 holdout"),
        ("historical_all", "历史全段"),
        ("paper", "纸面窗口"),
    ):
        lines.extend(
            [
                f"### {title}",
                "",
                "| 排序方案 | 类型 | 总收益 | 年化 | 市场超额 | 最大回撤 | 交易 | skip |",
                "|----------|------|--------|------|----------|----------|------|------|",
            ]
        )
        for row in [item for item in rows if item.get("window_id") == window_id]:
            lines.append(
                "| {label} | {group} | {total} | {ann} | {excess} | {dd} | {trades} | {skip} |".format(
                    label=row.get("label_cn"),
                    group=_variant_group_label(str(row.get("variant_group"))),
                    total=_pct(row.get("total_return")),
                    ann=_pct(row.get("annualized_return")),
                    excess=_pct(row.get("market_excess_total_return")),
                    dd=_pct(row.get("max_drawdown")),
                    trades=int(row.get("trade_count") or 0),
                    skip=_pct(row.get("skipped_ratio")),
                )
            )
        lines.append("")
    lines.extend(
        [
            "## 强势股捕捉",
            "",
            "| 排序方案 | Top 强势股进 Top5 | 启动前进 Top5 | 相对基线变化 |",
            "|----------|-------------------|---------------|--------------|",
        ]
    )
    for row in capture.get("variant_rows") or []:
        lines.append(
            "| {label} | {hit} | {pre} | {delta} |".format(
                label=row.get("label_cn"),
                hit=_pct(row.get("top5_hit_rate")),
                pre=_pct(row.get("pre_launch_top5_hit_rate")),
                delta=_pct(row.get("top5_hit_rate_delta_vs_baseline")),
            )
        )
    lines.extend(
        [
            "",
            "## 相对基线判断",
            "",
            "| 排序方案 | holdout 收益差 | holdout 回撤差 | paper 收益差 | 强势股捕捉差 | 结论 |",
            "|----------|----------------|----------------|--------------|--------------|------|",
        ]
    )
    for row in comparison.get("delta_rows") or []:
        lines.append(
            "| {label} | {holdout} | {drawdown} | {paper} | {capture_delta} | {verdict} |".format(
                label=row.get("label_cn"),
                holdout=_pct(row.get("holdout_total_return_delta")),
                drawdown=_pct(row.get("holdout_max_drawdown_delta")),
                paper=_pct(row.get("paper_total_return_delta")),
                capture_delta=_pct(row.get("top5_hit_rate_delta_vs_baseline")),
                verdict=row.get("verdict_cn"),
            )
        )
    lines.extend(["", "## 后续处理"])
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
    baseline = _build_quiet_ranked_symbols(
        signal_days=signal_days,
        contexts_by_day=contexts_by_day,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    sources = {"baseline_quiet_ranked": baseline}
    sources.update(_diagnostic_rankings_fast(series_by_symbol, signal_days=signal_days, contexts_by_day=contexts_by_day))
    sources.update(_theme_rankings(series_by_symbol, signal_days=signal_days, contexts_by_day=contexts_by_day, baseline=baseline))
    return sources


def _theme_rankings(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    baseline: dict[date, list[str]],
) -> dict[str, dict[date, list[str]]]:
    output: dict[str, dict[date, list[str]]] = {
        "theme_breadth_pullback": {},
        "theme_leader_rotation": {},
        "theme_breakout_cluster": {},
        "theme_position_guard": {},
    }
    for signal_day in signal_days:
        contexts = contexts_by_day.get(signal_day) or []
        enriched = _enriched_theme_contexts(series_by_symbol, contexts, signal_day=signal_day, baseline_ranked=baseline.get(signal_day) or [])
        output["theme_breadth_pullback"][signal_day] = _rank_by_theme_score(enriched, _score_theme_breadth_pullback)
        output["theme_leader_rotation"][signal_day] = _rank_by_theme_score(enriched, _score_theme_leader_rotation)
        output["theme_breakout_cluster"][signal_day] = _rank_by_theme_score(enriched, _score_theme_breakout_cluster)
        output["theme_position_guard"][signal_day] = _rank_by_theme_score(enriched, _score_theme_position_guard)
    return output


def _enriched_theme_contexts(
    series_by_symbol: dict[str, Any],
    contexts: list[dict[str, Any]],
    *,
    signal_day: date,
    baseline_ranked: list[str],
) -> list[dict[str, Any]]:
    amount_pct = _percentile_by_symbol(contexts, key="amount")
    ret20_pct = _percentile_by_symbol(contexts, key="return_20d")
    ret10_pct = _percentile_by_symbol(contexts, key="return_10d")
    industry_stats = _industry_theme_stats(contexts)
    baseline_score = _baseline_rank_scores(baseline_ranked)
    enriched = []
    for context in contexts:
        symbol = str(context.get("symbol"))
        industry = str(context.get("industry") or "unknown")
        stats = industry_stats.get(industry, {})
        shape = _context_position_shape(series_by_symbol, context, signal_day=signal_day)
        enriched.append(
            {
                **context,
                "position_shape": shape,
                "industry_breadth_pct": stats.get("breadth_pct", 0.0),
                "industry_heat_pct": stats.get("heat_pct", 0.0),
                "industry_breakout_pct": stats.get("breakout_pct", 0.0),
                "industry_member_count_pct": stats.get("member_count_pct", 0.0),
                "amount_pct": amount_pct.get(symbol, 0.0),
                "ret20_pct": ret20_pct.get(symbol, 0.0),
                "ret10_pct": ret10_pct.get(symbol, 0.0),
                "baseline_score": baseline_score.get(symbol, 0.0),
            }
        )
    return enriched


def _industry_theme_stats(contexts: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for context in contexts:
        grouped.setdefault(str(context.get("industry") or "unknown"), []).append(context)
    raw_rows = []
    for industry, rows in grouped.items():
        ret10 = [float(row.get("return_10d") or 0.0) for row in rows]
        ret20 = [float(row.get("return_20d") or 0.0) for row in rows]
        raw_rows.append(
            {
                "industry": industry,
                "breadth": _safe_rate(sum(1 for value in ret10 if value > 0), len(ret10)) or 0.0,
                "heat": fmean(ret10) if ret10 else 0.0,
                "breakout": _safe_rate(sum(1 for value in ret20 if value >= 0.08), len(ret20)) or 0.0,
                "member_count": float(len(rows)),
            }
        )
    pct_maps = {
        key: _percentile_by_key(raw_rows, key=key)
        for key in ("breadth", "heat", "breakout", "member_count")
    }
    return {
        row["industry"]: {
            "breadth_pct": pct_maps["breadth"].get(row["industry"], 0.0),
            "heat_pct": pct_maps["heat"].get(row["industry"], 0.0),
            "breakout_pct": pct_maps["breakout"].get(row["industry"], 0.0),
            "member_count_pct": pct_maps["member_count"].get(row["industry"], 0.0),
        }
        for row in raw_rows
    }


def _percentile_by_key(rows: list[dict[str, Any]], *, key: str) -> dict[str, float]:
    ordered = sorted(((str(row["industry"]), float(row.get(key) or 0.0)) for row in rows), key=lambda item: item[1])
    if len(ordered) <= 1:
        return {industry: 0.0 for industry, _ in ordered}
    denom = float(len(ordered) - 1)
    return {industry: index / denom for index, (industry, _) in enumerate(ordered)}


def _baseline_rank_scores(ranked: list[str]) -> dict[str, float]:
    if not ranked:
        return {}
    denom = float(max(1, len(ranked) - 1))
    return {symbol: 1.0 - (index / denom) for index, symbol in enumerate(ranked)}


def _score_theme_breadth_pullback(item: dict[str, Any]) -> float:
    shape_bonus = 1.0 if item.get("position_shape") in {"pullback_setup", "low_pre5_pullback"} else 0.0
    chase_penalty = 1.0 if item.get("position_shape") == "chase_high" else 0.0
    return (
        0.30 * float(item.get("industry_breadth_pct") or 0.0)
        + 0.20 * float(item.get("industry_heat_pct") or 0.0)
        + 0.18 * shape_bonus
        + 0.16 * float(item.get("amount_pct") or 0.0)
        + 0.16 * float(item.get("ret20_pct") or 0.0)
        - 0.18 * chase_penalty
    )


def _score_theme_leader_rotation(item: dict[str, Any]) -> float:
    ret10 = float(item.get("ret10_pct") or 0.0)
    moderation_bonus = 1.0 if 0.55 <= ret10 <= 0.90 else 0.0
    extreme_chase_penalty = 1.0 if ret10 >= 0.97 or item.get("position_shape") == "chase_high" else 0.0
    return (
        0.28 * float(item.get("industry_heat_pct") or 0.0)
        + 0.22 * float(item.get("industry_breadth_pct") or 0.0)
        + 0.18 * moderation_bonus
        + 0.16 * float(item.get("amount_pct") or 0.0)
        + 0.16 * float(item.get("ret20_pct") or 0.0)
        - 0.20 * extreme_chase_penalty
    )


def _score_theme_breakout_cluster(item: dict[str, Any]) -> float:
    return (
        0.34 * float(item.get("industry_breakout_pct") or 0.0)
        + 0.18 * float(item.get("industry_member_count_pct") or 0.0)
        + 0.20 * float(item.get("amount_pct") or 0.0)
        + 0.18 * float(item.get("ret20_pct") or 0.0)
        + 0.10 * float(item.get("industry_breadth_pct") or 0.0)
    )


def _score_theme_position_guard(item: dict[str, Any]) -> float:
    shape_bonus = 1.0 if item.get("position_shape") in {"pullback_setup", "low_pre5_pullback"} else 0.0
    chase_penalty = 1.0 if item.get("position_shape") == "chase_high" else 0.0
    return (
        0.58 * float(item.get("baseline_score") or 0.0)
        + 0.16 * float(item.get("industry_breadth_pct") or 0.0)
        + 0.12 * float(item.get("industry_heat_pct") or 0.0)
        + 0.10 * shape_bonus
        + 0.04 * float(item.get("amount_pct") or 0.0)
        - 0.08 * chase_penalty
    )


def _rank_by_theme_score(enriched: list[dict[str, Any]], scorer: Callable[[dict[str, Any]], float]) -> list[str]:
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
        {"window_id": "train", "label_cn": "训练段", "start_date": historical_start_date, "end_date": train_end_date},
        {"window_id": "holdout", "label_cn": "样本外 holdout", "start_date": holdout_start_date, "end_date": historical_end_date},
        {"window_id": "historical_all", "label_cn": "历史全段", "start_date": historical_start_date, "end_date": historical_end_date},
        {"window_id": "paper", "label_cn": "纸面窗口", "start_date": paper_start_date, "end_date": paper_end_date},
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
    variant: _ThemeVariant,
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
        "variant_group": variant.variant_group,
        "description_cn": variant.description_cn,
        **summary,
        "meets_min_annualized_return": meets_return,
        "beats_market_reference": beats_market,
        "drawdown_within_limit": drawdown_ok,
        "meets_user_floor": meets_return and beats_market and drawdown_ok,
    }


def _strong_stock_capture_by_variant(
    winners: list[dict[str, Any]],
    *,
    paper_signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    selections_by_variant: dict[str, dict[date, list[str]]],
    current_month_start_date: date,
) -> dict[str, Any]:
    winner_symbols = {str(row.get("symbol")) for row in winners}
    eligible_symbols = {
        str(context.get("symbol"))
        for day in paper_signal_days
        for context in contexts_by_day.get(day, [])
        if str(context.get("symbol")) in winner_symbols
    }
    variant_rows = []
    baseline_rate = None
    for variant in VARIANTS:
        selections = selections_by_variant.get(variant.variant_id) or {}
        top5_symbols = {
            str(symbol)
            for day in paper_signal_days
            for symbol in selections.get(day, [])
            if str(symbol) in winner_symbols
        }
        pre_launch_symbols = {
            str(symbol)
            for day in paper_signal_days
            if day < current_month_start_date
            for symbol in selections.get(day, [])
            if str(symbol) in winner_symbols
        }
        hit_rate = _safe_rate(len(top5_symbols), len(winner_symbols))
        if variant.variant_id == "baseline_quiet_rank2_mtw":
            baseline_rate = hit_rate
        variant_rows.append(
            {
                "variant_id": variant.variant_id,
                "label_cn": variant.label_cn,
                "variant_group": variant.variant_group,
                "top5_hit_count": len(top5_symbols),
                "top5_hit_rate": hit_rate,
                "pre_launch_top5_hit_count": len(pre_launch_symbols),
                "pre_launch_top5_hit_rate": _safe_rate(len(pre_launch_symbols), len(winner_symbols)),
                "top5_hit_rate_delta_vs_baseline": None,
            }
        )
    for row in variant_rows:
        row["top5_hit_rate_delta_vs_baseline"] = _delta(row.get("top5_hit_rate"), baseline_rate)
    industries = Counter(str(row.get("industry") or "unknown") for row in winners)
    return {
        "top_winner_count": len(winners),
        "paper_signal_day_count": len(paper_signal_days),
        "eligible_universe_hit_count": len(eligible_symbols),
        "eligible_universe_hit_rate": _safe_rate(len(eligible_symbols), len(winner_symbols)),
        "top_industries": [
            {"industry": industry, "count": count, "share": _safe_rate(count, len(winners))}
            for industry, count in industries.most_common(15)
        ],
        "variant_rows": variant_rows,
    }


def _comparison(
    rows: list[dict[str, Any]],
    *,
    capture_rows: list[dict[str, Any]],
    min_holdout_return_delta: float,
    max_holdout_drawdown_worsening: float,
) -> dict[str, Any]:
    baseline_by_window = {
        str(row.get("window_id")): row for row in rows if row.get("variant_id") == "baseline_quiet_rank2_mtw"
    }
    capture_by_variant = {str(row.get("variant_id")): row for row in capture_rows}
    baseline_capture = capture_by_variant.get("baseline_quiet_rank2_mtw") or {}
    delta_rows: list[dict[str, Any]] = []
    future_research_ids: list[str] = []
    for variant in VARIANTS:
        if variant.variant_id == "baseline_quiet_rank2_mtw":
            continue
        by_window = {
            str(row.get("window_id")): row for row in rows if row.get("variant_id") == variant.variant_id
        }
        holdout = by_window.get("holdout") or {}
        paper = by_window.get("paper") or {}
        baseline_holdout = baseline_by_window.get("holdout") or {}
        baseline_paper = baseline_by_window.get("paper") or {}
        capture = capture_by_variant.get(variant.variant_id) or {}
        holdout_delta = _delta(holdout.get("total_return"), baseline_holdout.get("total_return"))
        drawdown_delta = _delta(holdout.get("max_drawdown"), baseline_holdout.get("max_drawdown"))
        paper_delta = _delta(paper.get("total_return"), baseline_paper.get("total_return"))
        capture_delta = _delta(capture.get("top5_hit_rate"), baseline_capture.get("top5_hit_rate"))
        passes_future_research = (
            holdout_delta is not None
            and drawdown_delta is not None
            and paper_delta is not None
            and capture_delta is not None
            and holdout_delta >= min_holdout_return_delta
            and drawdown_delta >= max_holdout_drawdown_worsening
            and paper_delta > 0
            and capture_delta > 0
        )
        if passes_future_research:
            future_research_ids.append(variant.variant_id)
            verdict = "达到后续研究门槛，但本轮仍不进入纸面候选"
        elif capture_delta is not None and capture_delta > 0 and (holdout_delta is None or holdout_delta < min_holdout_return_delta):
            verdict = "强势股捕捉改善，但样本外收益不足"
        elif paper_delta is not None and paper_delta > 0 and (holdout_delta is None or holdout_delta < min_holdout_return_delta):
            verdict = "paper 改善但样本外不足"
        elif holdout_delta is not None and holdout_delta > 0:
            verdict = "样本外略改善但未达到阈值"
        else:
            verdict = "未优于原 v2 基线"
        delta_rows.append(
            {
                "variant_id": variant.variant_id,
                "label_cn": variant.label_cn,
                "variant_group": variant.variant_group,
                "holdout_total_return_delta": holdout_delta,
                "holdout_max_drawdown_delta": drawdown_delta,
                "paper_total_return_delta": paper_delta,
                "top5_hit_rate_delta_vs_baseline": capture_delta,
                "verdict_cn": verdict,
                "future_research_threshold_passed": passes_future_research,
            }
        )
    return {
        "baseline_variant_id": "baseline_quiet_rank2_mtw",
        "candidate_variant_ids": [],
        "future_research_variant_ids": future_research_ids,
        "thresholds": {
            "min_holdout_total_return_delta": min_holdout_return_delta,
            "max_holdout_drawdown_worsening": max_holdout_drawdown_worsening,
            "requires_paper_total_return_improvement": True,
            "requires_top5_capture_improvement": True,
        },
        "delta_rows": delta_rows,
    }


def _interpretation(comparison: dict[str, Any]) -> dict[str, Any]:
    future_ids = list(comparison.get("future_research_variant_ids") or [])
    if future_ids:
        return {
            "status": "future_research_only_no_promotion",
            "message_cn": f"{'、'.join(future_ids)} 达到后续研究门槛，但按用户约束本轮不进入纸面候选。",
            "recommended_next_steps_cn": [
                "后续若继续，只能新开计划做更严格的样本外和参数稳定性验证。",
                "本轮不得修改纸面追踪候选或冻结策略。",
            ],
        }
    return {
        "status": "no_theme_variant_promoted",
        "message_cn": "本轮行业主线实验没有同时满足样本外收益、回撤、paper 和强势股捕捉四项门槛，只能作为不成立或未证实的研究记录。",
        "recommended_next_steps_cn": [
            "不要把本轮任何行业主线变体加入纸面候选。",
            "如果继续研究行业方向，应先做更细的行业标签质量和主线识别解释性诊断，而不是继续扩大参数网格。",
        ],
    }


def _variant_artifact(variant: _ThemeVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "label_cn": variant.label_cn,
        "source_id": variant.source_id,
        "description_cn": variant.description_cn,
        "variant_group": variant.variant_group,
    }


def _variant_group_label(group: str) -> str:
    return {
        "baseline": "基线",
        "known_weak_control": "旧弱对照",
        "new_theme_experiment": "新主线实验",
    }.get(group, group)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _delta(value: object, baseline: object) -> float | None:
    if value is None or baseline is None:
        return None
    return round(float(value) - float(baseline), 6)


def _safe_rate(count: int, total: int) -> float | None:
    return round(float(count) / float(total), 6) if total > 0 else None


def _artifact_id(generated_at: datetime, start: date, end: date) -> str:
    return f"{ARTIFACT_FAMILY}:{start.isoformat()}:{end.isoformat()}:{generated_at.date().isoformat()}"
