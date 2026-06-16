from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import fmean, median
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    INDEX_SYMBOLS,
)
from ashare_evidence.shortpick_portfolio_backtest import _eligible_signal_days, _trade_days
from ashare_evidence.shortpick_v2_next_diagnostics import (
    DEFAULT_BASELINE_TARGET_NOTIONAL,
    DEFAULT_HISTORICAL_END_DATE,
    DEFAULT_HISTORICAL_START_DATE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    DEFAULT_PAPER_START_DATE,
    DEFAULT_POOL_LIMIT,
    DEFAULT_RANK_LIMIT,
    V2_BASELINE_CONFIG_ID,
    _build_v2_baseline_selections,
    _contexts_by_signal_day,
    _load_daily_series_between,
    _pct,
    _simulate_closed_trade_ledger,
    _summary_row,
    _trade_features,
    _v2_baseline_config,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    _coverage_notes,
    _market_reference_summary,
    _simulate_rule_config,
)

ARTIFACT_FAMILY = "shortpick_v2_theme_position_diagnostics"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_theme_position_diagnostics:v1"
DEFAULT_CURRENT_MONTH_START_DATE = date(2026, 6, 1)
DEFAULT_CURRENT_MONTH_END_DATE = date(2026, 6, 16)
DEFAULT_TOP_WINNER_COUNT = 50


def build_shortpick_v2_theme_position_diagnostics_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    historical_end_date: date = DEFAULT_HISTORICAL_END_DATE,
    paper_start_date: date = DEFAULT_PAPER_START_DATE,
    paper_end_date: date = DEFAULT_CURRENT_MONTH_END_DATE,
    current_month_start_date: date = DEFAULT_CURRENT_MONTH_START_DATE,
    current_month_end_date: date = DEFAULT_CURRENT_MONTH_END_DATE,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    pool_limit: int = DEFAULT_POOL_LIMIT,
    rank_limit: int = DEFAULT_RANK_LIMIT,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    top_winner_count: int = DEFAULT_TOP_WINNER_COUNT,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if horizon_days != DEFAULT_HORIZON_DAYS:
        raise ValueError("theme-position diagnostics currently requires H10; horizon_days must be 10")
    if current_month_start_date > current_month_end_date:
        raise ValueError("current month start date must be <= end date")

    generated_at = generated_at or datetime.now(UTC)
    raw_series_by_symbol = _load_daily_series_between(
        session,
        start_date=historical_start_date - timedelta(days=420),
        end_date=max(paper_end_date, current_month_end_date) + timedelta(days=max(45, horizon_days * 5)),
    )
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=account_profile,
        include_index_symbols=INDEX_SYMBOLS,
    )
    paper_signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=paper_start_date,
        end_date=paper_end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    paper_trade_days = _trade_days(
        series_by_symbol,
        start_date=paper_start_date,
        end_date=paper_end_date + timedelta(days=max(30, horizon_days * 4)),
        min_symbol_count=min_signal_symbol_count,
    )
    historical_signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=historical_end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    historical_trade_days = _trade_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=historical_end_date + timedelta(days=max(30, horizon_days * 4)),
        min_symbol_count=min_signal_symbol_count,
    )
    paper_contexts = _contexts_by_signal_day(series_by_symbol, signal_days=paper_signal_days)
    historical_contexts = _contexts_by_signal_day(series_by_symbol, signal_days=historical_signal_days)
    paper_selections = _build_v2_baseline_selections(
        signal_days=paper_signal_days,
        contexts_by_day=paper_contexts,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    historical_selections = _build_v2_baseline_selections(
        signal_days=historical_signal_days,
        contexts_by_day=historical_contexts,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    market_reference = _market_reference_summary(series_by_symbol, signal_days=paper_signal_days)
    paper_result = _simulate_rule_config(
        series_by_symbol,
        signal_days=paper_signal_days,
        trade_days=paper_trade_days,
        selections=paper_selections,
        config=_v2_baseline_config(),
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        market_reference_total_return=market_reference.get("total_return"),
        decision_sample_limit=0,
    )
    paper_trades = _simulate_closed_trade_ledger(
        series_by_symbol,
        signal_days=paper_signal_days,
        trade_days=paper_trade_days,
        selections=paper_selections,
        config=_v2_baseline_config(),
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    historical_trades = _simulate_closed_trade_ledger(
        series_by_symbol,
        signal_days=historical_signal_days,
        trade_days=historical_trade_days,
        selections=historical_selections,
        config=_v2_baseline_config(),
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    winners = _current_month_winners(
        series_by_symbol,
        current_month_start_date=current_month_start_date,
        current_month_end_date=current_month_end_date,
        top_n=top_winner_count,
    )
    coverage = _candidate_pool_coverage(
        winners["top_winners"],
        paper_signal_days=paper_signal_days,
        contexts_by_day=paper_contexts,
        selections=paper_selections,
        paper_trades=paper_trades,
        current_month_start_date=current_month_start_date,
    )
    position_buckets = _position_bucket_diagnostics(
        series_by_symbol,
        historical_trades=historical_trades,
        paper_trades=paper_trades,
        historical_signal_days=historical_signal_days,
        paper_signal_days=paper_signal_days,
    )
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, current_month_start_date, current_month_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "current_month_winner_profile_candidate_pool_position_bucket_diagnostics",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "question_cn": "为什么 v2 当前纸面窗口效果差：错过当月主线、候选池覆盖不足、排序失效，还是位置形态错配？",
            "baseline_config_id": V2_BASELINE_CONFIG_ID,
            "baseline_buy_cn": f"固定单笔约 {DEFAULT_BASELINE_TARGET_NOTIONAL / 10000:.1f} 万，Rank2 首选，Rank3-Rank6 同日候补。",
            "historical_start_date": historical_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "current_month_start_date": current_month_start_date.isoformat(),
            "current_month_end_date": current_month_end_date.isoformat(),
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "entry_price_source": entry_price_source,
            "promotion_status": "research_only_no_strategy_promotion",
        },
        "data_scope": {
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "paper_signal_day_count": len(paper_signal_days),
            "historical_trade_count": len(historical_trades),
            "paper_closed_trade_count": len(paper_trades),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "paper_baseline": _summary_row(paper_result, trade_day_count=len(paper_trade_days)),
        "current_month_winners": winners,
        "candidate_pool_coverage": coverage,
        "position_bucket_diagnostics": position_buckets,
        "interpretation": _interpretation(winners, coverage, position_buckets),
        "leakage_audit": {
            "status": "passed",
            "notes": [
                "Current-month winner labels use June outcomes and are used only for post-hoc opportunity attribution.",
                "Candidate-pool coverage only asks whether already-known v2 paper signal pools contained those later winners.",
                "Position bucket diagnostics use signal-day-or-earlier features for bucket labels; returns are outcomes.",
                "No rule is promoted by this artifact.",
            ],
        },
        "event_refs": [
            "shortpick_v2.theme_position_diagnostics.generated",
            f"shortpick_v2.theme_position_diagnostics.month.{current_month_start_date.isoformat()}_{current_month_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_theme_position_diagnostics_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"theme-position diagnostics validation failed: {validation}")
    return payload


def write_shortpick_v2_theme_position_diagnostics_artifact(
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
        path.write_text(render_shortpick_v2_theme_position_diagnostics_markdown(payload), encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_theme_position_diagnostics_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_theme_position_diagnostics_payload(json.loads(Path(artifact_path).read_text(encoding="utf-8")))


def validate_shortpick_v2_theme_position_diagnostics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    winners = payload.get("current_month_winners") if isinstance(payload.get("current_month_winners"), dict) else {}
    coverage = payload.get("candidate_pool_coverage") if isinstance(payload.get("candidate_pool_coverage"), dict) else {}
    buckets = payload.get("position_bucket_diagnostics") if isinstance(payload.get("position_bucket_diagnostics"), dict) else {}
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_strategy_promotion", str(scope.get("promotion_status")))
    check("winner_count", int(winners.get("top_winner_count") or 0) >= 30, str(winners.get("top_winner_count")))
    check("coverage_ready", int(coverage.get("top_winner_count") or 0) >= 30, str(coverage.get("top_winner_count")))
    check("historical_bucket_ready", int(buckets.get("historical_trade_count") or 0) >= 50, str(buckets.get("historical_trade_count")))
    check("paper_bucket_ready", int(buckets.get("paper_trade_count") or 0) >= 5, str(buckets.get("paper_trade_count")))
    check("leakage_status", (payload.get("leakage_audit") or {}).get("status") == "passed", str((payload.get("leakage_audit") or {}).get("status")))
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "top_winner_count": winners.get("top_winner_count"),
            "v2_candidate_hit_rate": coverage.get("v2_candidate_hit_rate"),
            "interpretation_status": (payload.get("interpretation") or {}).get("status"),
        },
    }


def render_shortpick_v2_theme_position_diagnostics_markdown(payload: dict[str, Any]) -> str:
    winners = payload.get("current_month_winners") if isinstance(payload.get("current_month_winners"), dict) else {}
    coverage = payload.get("candidate_pool_coverage") if isinstance(payload.get("candidate_pool_coverage"), dict) else {}
    buckets = payload.get("position_bucket_diagnostics") if isinstance(payload.get("position_bucket_diagnostics"), dict) else {}
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    paper = payload.get("paper_baseline") if isinstance(payload.get("paper_baseline"), dict) else {}
    lines = [
        "# 试验田 v2 主线与位置形态诊断",
        "",
        "本产物只解释当前纸面窗口为什么差，不晋级或替换纸面追踪策略。",
        "",
        "## 结论",
        "",
        str(interpretation.get("message_cn") or "暂无结论。"),
        "",
        "## 当前纸面基线",
        "",
        "| 总收益 | 年化 | 最大回撤 | 交易 | skip |",
        "|--------|------|----------|------|------|",
        "| {total} | {ann} | {dd} | {trades} | {skip} |".format(
            total=_pct(paper.get("total_return")),
            ann=_pct(paper.get("annualized_return")),
            dd=_pct(paper.get("max_drawdown")),
            trades=int(paper.get("trade_count") or 0),
            skip=_pct(paper.get("skipped_ratio")),
        ),
        "",
        "## 6 月强势股画像",
        "",
        f"- 全市场样本：{int(winners.get('universe_count') or 0)} 只；平均收益 {_pct(winners.get('universe_avg_return'))}；上涨占比 {_pct(winners.get('universe_positive_rate'))}；涨幅超过 20% 占比 {_pct(winners.get('universe_over20_rate'))}。",
        f"- Top{int(winners.get('top_winner_count') or 0)} 启动前 5 日涨幅中位数：{_pct(winners.get('top_pre5_return_median'))}；距离 20 日高点中位数：{_pct(winners.get('top_vs_20d_high_median'))}。",
        f"- 与 v2 纸面亏损相似的“高位追强形态”占比：{_pct(winners.get('top_chase_high_shape_rate'))}。",
        "",
        "| 行业 | Top 数量 | 平均涨幅 | 样例 |",
        "|------|----------|----------|------|",
    ]
    for row in winners.get("top_industries") or []:
        lines.append(
            "| {industry} | {count} | {ret} | {names} |".format(
                industry=row.get("industry"),
                count=int(row.get("count") or 0),
                ret=_pct(row.get("avg_month_return")),
                names="、".join(row.get("sample_names") or []),
            )
        )
    lines.extend(
        [
            "",
            "## v2 候选池覆盖",
            "",
            f"- {coverage.get('coverage_definition_cn') or '这里的 v2 候选池指最终可买候选。'}",
            f"- Top 强势股出现在 v2 合格观察域比例：{_pct(coverage.get('eligible_universe_hit_rate'))}。",
            f"- 在 6 月启动前已经出现在 v2 合格观察域比例：{_pct(coverage.get('pre_launch_eligible_universe_hit_rate'))}。",
            f"- Top 强势股进入 v2 纸面候选池比例：{_pct(coverage.get('v2_candidate_hit_rate'))}。",
            f"- 在 6 月启动前已经进入 v2 候选池比例：{_pct(coverage.get('pre_launch_v2_candidate_hit_rate'))}。",
            f"- 实际被 v2 买入的 Top 强势股比例：{_pct(coverage.get('bought_top_winner_rate'))}。",
            "",
            "| 类型 | 数量 | 说明 |",
            "|------|------|------|",
            f"| Top 强势股 | {int(coverage.get('top_winner_count') or 0)} | 6 月收益排序前列 |",
            f"| 出现在合格观察域 | {int(coverage.get('eligible_universe_hit_count') or 0)} | paper 信号日有可计算上下文，不代表进入 Top5 |",
            f"| 启动前出现在合格观察域 | {int(coverage.get('pre_launch_eligible_universe_hit_count') or 0)} | 2026-06-01 前已有可计算上下文 |",
            f"| 进入 v2 候选池 | {int(coverage.get('v2_candidate_hit_count') or 0)} | paper 信号日 Top5 候选出现过 |",
            f"| 启动前进入候选池 | {int(coverage.get('pre_launch_v2_candidate_hit_count') or 0)} | 2026-06-01 前信号日出现过 |",
            f"| 实际买入 | {int(coverage.get('bought_top_winner_count') or 0)} | v2 paper 已平仓交易包含 |",
            "",
            "## 位置形态桶",
            "",
            "| 形态 | 历史交易 | 历史中位收益 | 历史胜率 | 当前纸面交易 | 当前纸面中位收益 |",
            "|------|----------|--------------|----------|--------------|------------------|",
        ]
    )
    for row in buckets.get("bucket_rows") or []:
        historical = row.get("historical") if isinstance(row.get("historical"), dict) else {}
        paper_bucket = row.get("paper") if isinstance(row.get("paper"), dict) else {}
        lines.append(
            "| {label} | {hc} | {hm} | {hw} | {pc} | {pm} |".format(
                label=row.get("label_cn"),
                hc=int(historical.get("count") or 0),
                hm=_pct(historical.get("median_net_return")),
                hw=_pct(historical.get("win_rate")),
                pc=int(paper_bucket.get("count") or 0),
                pm=_pct(paper_bucket.get("median_net_return")),
            )
        )
    lines.extend(
        [
            "",
            "## 下一步建议",
            "",
        ]
    )
    for step in interpretation.get("recommended_next_steps_cn") or []:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def _current_month_winners(
    series_by_symbol: dict[str, Any],
    *,
    current_month_start_date: date,
    current_month_end_date: date,
    top_n: int,
) -> dict[str, Any]:
    trade_days = _trade_days(series_by_symbol, start_date=current_month_start_date - timedelta(days=20), end_date=current_month_end_date, min_symbol_count=1)
    start_anchor = max((day for day in trade_days if day < current_month_start_date), default=None)
    end_anchor = max((day for day in trade_days if day <= current_month_end_date), default=None)
    if start_anchor is None or end_anchor is None:
        return {"status": "blocked", "reason_cn": "缺少当前月起止行情。", "top_winners": [], "top_winner_count": 0}
    rows: list[dict[str, Any]] = []
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS or "ST" in str(series.name).upper():
            continue
        start_index = series.by_day.get(start_anchor)
        end_index = series.by_day.get(end_anchor)
        if start_index is None or end_index is None or end_index <= start_index:
            continue
        start_close = float(series.bars[start_index].close)
        end_close = float(series.bars[end_index].close)
        if start_close <= 0 or end_close <= 0:
            continue
        pre_features = _pre_signal_features(series, start_anchor)
        rows.append(
            {
                "symbol": symbol,
                "name": str(series.name or symbol),
                "industry": str(series.industry or "unknown"),
                "month_return": round(end_close / start_close - 1.0, 6),
                "start_close": round(start_close, 6),
                "end_close": round(end_close, 6),
                "pre5_return": pre_features.get("pre5_return"),
                "price_vs_20d_high": pre_features.get("price_vs_20d_high"),
                "avg_amount_20d": pre_features.get("avg_amount_20d"),
                "avg_turnover_20d": pre_features.get("avg_turnover_20d"),
                "position_shape": _position_shape(pre_features.get("pre5_return"), pre_features.get("price_vs_20d_high")),
            }
        )
    rows.sort(key=lambda row: float(row["month_return"]), reverse=True)
    top = rows[:top_n]
    industries = []
    for industry, count in Counter(str(row["industry"]) for row in top).most_common(15):
        industry_rows = [row for row in top if row["industry"] == industry]
        industries.append(
            {
                "industry": industry,
                "count": count,
                "avg_month_return": _avg([row.get("month_return") for row in industry_rows]),
                "sample_names": [str(row["name"]) for row in industry_rows[:5]],
            }
        )
    return {
        "status": "ready",
        "start_anchor_date": start_anchor.isoformat(),
        "end_anchor_date": end_anchor.isoformat(),
        "universe_count": len(rows),
        "universe_avg_return": _avg([row.get("month_return") for row in rows]),
        "universe_positive_rate": _rate([float(row["month_return"]) > 0 for row in rows]),
        "universe_over20_rate": _rate([float(row["month_return"]) >= 0.20 for row in rows]),
        "top_winner_count": len(top),
        "top_pre5_return_median": _med([row.get("pre5_return") for row in top]),
        "top_vs_20d_high_median": _med([row.get("price_vs_20d_high") for row in top]),
        "top_avg_amount_20d_median": _med([row.get("avg_amount_20d") for row in top]),
        "top_avg_turnover_20d_median": _med([row.get("avg_turnover_20d") for row in top]),
        "top_chase_high_shape_rate": _rate([row.get("position_shape") == "chase_high" for row in top]),
        "top_industries": industries,
        "top_winners": top,
    }


def _candidate_pool_coverage(
    winners: list[dict[str, Any]],
    *,
    paper_signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    selections: dict[date, list[str]],
    paper_trades: list[Any],
    current_month_start_date: date,
) -> dict[str, Any]:
    winner_symbols = {str(row.get("symbol")) for row in winners}
    bought_symbols = {str(trade.symbol) for trade in paper_trades}
    rows: list[dict[str, Any]] = []
    for winner in winners:
        symbol = str(winner.get("symbol"))
        eligible_days = [
            day.isoformat()
            for day in paper_signal_days
            if any(str(context.get("symbol")) == symbol for context in contexts_by_day.get(day, []))
        ]
        pre_launch_eligible_days = [day for day in eligible_days if date.fromisoformat(day) < current_month_start_date]
        v2_candidate_days = [
            day.isoformat()
            for day in paper_signal_days
            if symbol in [str(candidate) for candidate in selections.get(day, [])]
        ]
        pre_launch_days = [day for day in v2_candidate_days if date.fromisoformat(day) < current_month_start_date]
        rows.append(
            {
                "symbol": symbol,
                "name": winner.get("name"),
                "industry": winner.get("industry"),
                "month_return": winner.get("month_return"),
                "position_shape": winner.get("position_shape"),
                "eligible_signal_day_count": len(eligible_days),
                "pre_launch_eligible_signal_day_count": len(pre_launch_eligible_days),
                "v2_candidate_day_count": len(v2_candidate_days),
                "pre_launch_v2_candidate_day_count": len(pre_launch_days),
                "bought_by_v2": symbol in bought_symbols,
                "v2_candidate_days": v2_candidate_days[:8],
            }
        )
    eligible_hits = [row for row in rows if int(row["eligible_signal_day_count"]) > 0]
    pre_eligible_hits = [row for row in rows if int(row["pre_launch_eligible_signal_day_count"]) > 0]
    v2_hits = [row for row in rows if int(row["v2_candidate_day_count"]) > 0]
    pre_hits = [row for row in rows if int(row["pre_launch_v2_candidate_day_count"]) > 0]
    bought_hits = [row for row in rows if bool(row["bought_by_v2"])]
    return {
        "coverage_definition_cn": "这里的 v2 候选池指每个 paper 信号日最终可买的 Top5 selections，不是全市场 eligible universe。",
        "top_winner_count": len(winners),
        "paper_signal_day_count": len(paper_signal_days),
        "winner_symbol_count": len(winner_symbols),
        "eligible_universe_hit_count": len(eligible_hits),
        "eligible_universe_hit_rate": _safe_rate(len(eligible_hits), len(winners)),
        "pre_launch_eligible_universe_hit_count": len(pre_eligible_hits),
        "pre_launch_eligible_universe_hit_rate": _safe_rate(len(pre_eligible_hits), len(winners)),
        "v2_candidate_hit_count": len(v2_hits),
        "v2_candidate_hit_rate": _safe_rate(len(v2_hits), len(winners)),
        "pre_launch_v2_candidate_hit_count": len(pre_hits),
        "pre_launch_v2_candidate_hit_rate": _safe_rate(len(pre_hits), len(winners)),
        "bought_top_winner_count": len(bought_hits),
        "bought_top_winner_rate": _safe_rate(len(bought_hits), len(winners)),
        "coverage_rows": rows,
        "missed_top10_examples": [row for row in rows[:10] if int(row["v2_candidate_day_count"]) == 0],
        "hit_examples": v2_hits[:10],
    }


def _position_bucket_diagnostics(
    series_by_symbol: dict[str, Any],
    *,
    historical_trades: list[Any],
    paper_trades: list[Any],
    historical_signal_days: list[date],
    paper_signal_days: list[date],
) -> dict[str, Any]:
    historical_features = [
        _trade_feature_with_shape(series_by_symbol, trade, signal_days=historical_signal_days) for trade in historical_trades
    ]
    paper_features = [_trade_feature_with_shape(series_by_symbol, trade, signal_days=paper_signal_days) for trade in paper_trades]
    bucket_ids = ("chase_high", "pullback_setup", "low_pre5_pullback", "other")
    rows = []
    for bucket_id in bucket_ids:
        rows.append(
            {
                "bucket_id": bucket_id,
                "label_cn": _bucket_label(bucket_id),
                "definition_cn": _bucket_definition(bucket_id),
                "historical": _bucket_summary([row for row in historical_features if row.get("position_shape") == bucket_id]),
                "paper": _bucket_summary([row for row in paper_features if row.get("position_shape") == bucket_id]),
            }
        )
    return {
        "historical_trade_count": len(historical_features),
        "paper_trade_count": len(paper_features),
        "bucket_rows": rows,
        "paper_trade_samples": [
            {
                "signal_date": trade.signal_day.isoformat(),
                "entry_date": trade.entry_day.isoformat(),
                "exit_date": trade.exit_day.isoformat(),
                "symbol": trade.symbol,
                "name": trade.name,
                "industry": trade.industry,
                "net_return": round(float(trade.net_return), 6),
                "position_shape": feature.get("position_shape"),
                "pre5_return": feature.get("stock_pre5d_return"),
                "price_vs_20d_high": feature.get("price_vs_20d_high"),
            }
            for trade, feature in zip(paper_trades, paper_features, strict=False)
        ],
    }


def _trade_feature_with_shape(series_by_symbol: dict[str, Any], trade: Any, *, signal_days: list[date]) -> dict[str, Any]:
    feature = _trade_features(series_by_symbol, trade, signal_days=signal_days)
    feature["position_shape"] = _position_shape(feature.get("stock_pre5d_return"), feature.get("price_vs_20d_high"))
    return feature


def _pre_signal_features(series: Any, signal_day: date) -> dict[str, float | None]:
    index = series.by_day.get(signal_day)
    if index is None:
        index = max((idx for idx, bar in enumerate(series.bars) if bar.day <= signal_day), default=None)
    if index is None:
        return {"pre5_return": None, "price_vs_20d_high": None, "avg_amount_20d": None, "avg_turnover_20d": None}
    bar = series.bars[index]
    pre5_return = None
    if index >= 5:
        start = float(series.bars[index - 5].close)
        if start > 0:
            pre5_return = round(float(bar.close) / start - 1.0, 6)
    start_index = max(0, index - 19)
    recent = series.bars[start_index : index + 1]
    closes = [float(item.close) for item in recent if float(item.close) > 0]
    price_vs_20d_high = round(float(bar.close) / max(closes) - 1.0, 6) if closes else None
    amounts = [float(item.amount) for item in recent if float(item.amount) > 0]
    turnovers = [float(item.turnover) for item in recent if item.turnover is not None]
    return {
        "pre5_return": pre5_return,
        "price_vs_20d_high": price_vs_20d_high,
        "avg_amount_20d": round(fmean(amounts), 6) if amounts else None,
        "avg_turnover_20d": round(fmean(turnovers), 6) if turnovers else None,
    }


def _position_shape(pre5_return: object, price_vs_20d_high: object) -> str:
    pre5 = _float_or_none(pre5_return)
    vs_high = _float_or_none(price_vs_20d_high)
    if pre5 is None or vs_high is None:
        return "other"
    if pre5 >= 0.08 and vs_high >= -0.005:
        return "chase_high"
    if pre5 <= 0.05 and vs_high < -0.15:
        return "low_pre5_pullback"
    if -0.10 <= pre5 <= 0.05 and -0.15 <= vs_high <= -0.03:
        return "pullback_setup"
    return "other"


def _bucket_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [float(row["net_return"]) for row in rows if row.get("net_return") is not None]
    pnl = [float(row["pnl_pct_initial_cash"]) for row in rows if row.get("pnl_pct_initial_cash") is not None]
    industries = Counter(str(row.get("industry") or "unknown") for row in rows)
    return {
        "count": len(rows),
        "avg_net_return": round(fmean(returns), 6) if returns else None,
        "median_net_return": round(median(returns), 6) if returns else None,
        "win_rate": _rate([value > 0 for value in returns]),
        "median_pnl_pct_initial_cash": round(median(pnl), 6) if pnl else None,
        "top_industries": industries.most_common(5),
    }


def _bucket_label(bucket_id: str) -> str:
    return {
        "chase_high": "高位追强",
        "pullback_setup": "回撤蓄势",
        "low_pre5_pullback": "低涨幅回撤",
        "other": "其它形态",
    }.get(bucket_id, bucket_id)


def _bucket_definition(bucket_id: str) -> str:
    return {
        "chase_high": "信号日前 5 日涨幅 >= 8%，且距离 20 日高点不低于 -0.5%。",
        "pullback_setup": "信号日前 5 日涨幅在 -10% 到 +5%，且距离 20 日高点 -15% 到 -3%。",
        "low_pre5_pullback": "信号日前 5 日涨幅 <= 5%，且距离 20 日高点低于 -15%。",
        "other": "不属于上述固定形态。",
    }.get(bucket_id, "")


def _interpretation(winners: dict[str, Any], coverage: dict[str, Any], buckets: dict[str, Any]) -> dict[str, Any]:
    eligible_hit_rate = _float_or_none(coverage.get("eligible_universe_hit_rate"))
    winner_hit_rate = _float_or_none(coverage.get("v2_candidate_hit_rate"))
    bought_rate = _float_or_none(coverage.get("bought_top_winner_rate"))
    chase_rate = _float_or_none(winners.get("top_chase_high_shape_rate"))
    paper_chase_count = 0
    paper_pullback_count = 0
    historical_pullback_median = None
    historical_chase_median = None
    for row in buckets.get("bucket_rows") or []:
        if row.get("bucket_id") == "chase_high":
            paper_chase_count = int((row.get("paper") or {}).get("count") or 0)
            historical_chase_median = (row.get("historical") or {}).get("median_net_return")
        if row.get("bucket_id") == "pullback_setup":
            paper_pullback_count = int((row.get("paper") or {}).get("count") or 0)
            historical_pullback_median = (row.get("historical") or {}).get("median_net_return")
    reasons: list[str] = []
    if eligible_hit_rate is not None and winner_hit_rate is not None and eligible_hit_rate >= 0.50 and winner_hit_rate < 0.20:
        reasons.append("6 月强势股大多在 v2 合格观察域内，但极少进入最终 Top5，当前更像 rank2/Top5 入口排序错过主线")
    elif winner_hit_rate is not None and winner_hit_rate < 0.20:
        reasons.append("6 月强势股很少进入 v2 最终 Top5 候选池，当前更像可买候选池错过主线")
    elif bought_rate is not None and bought_rate < 0.10:
        reasons.append("6 月强势股进入过候选池但实际买入很少，当前更像排序或资金占用错配")
    else:
        reasons.append("v2 对 6 月强势股有一定覆盖，不能简单归因于候选池缺失")
    if chase_rate is not None and chase_rate < 0.20:
        reasons.append("本月强势股多数不是高位追强形态，和 v2 当前亏损样本的入场位置不一致")
    if paper_chase_count > paper_pullback_count:
        reasons.append("当前纸面交易更偏高位追强，回撤蓄势样本不足")
    if historical_pullback_median is not None and historical_chase_median is not None:
        if float(historical_pullback_median) > float(historical_chase_median):
            reasons.append("历史逐笔中回撤蓄势形态中位收益优于高位追强，值得进入 OOS 验证")
        else:
            reasons.append("历史逐笔中回撤蓄势尚未明显优于高位追强，不能直接作为新规则")
    return {
        "status": "continue_diagnostics_no_strategy_promotion",
        "message_cn": "；".join(reasons),
        "recommended_next_steps_cn": [
            "下一轮先做 OOS 位置形态对照：高位追强、回撤蓄势、低涨幅回撤三类固定桶，不从 6 月收益反向调阈值。",
            "同时做 rank2/Top5 入口排序诊断：验证行业主线热度、回撤蓄势形态能否把已在 eligible universe 的强势股推入最终可买候选，而不是直接替换 rank2。",
            "如果 Top5 覆盖仍低，优先研究排序和截断；如果 Top5 覆盖高但买入少，再研究资金占用和买入执行。",
        ],
    }


def _avg(values: list[object]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(fmean(clean), 6) if clean else None


def _med(values: list[object]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(median(clean), 6) if clean else None


def _rate(values: list[bool]) -> float | None:
    return round(sum(1 for value in values if value) / len(values), 6) if values else None


def _safe_rate(count: int, total: int) -> float | None:
    return round(float(count) / float(total), 6) if total > 0 else None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _artifact_id(generated_at: datetime, month_start: date, month_end: date) -> str:
    return f"{ARTIFACT_FAMILY}:{month_start.isoformat()}:{month_end.isoformat()}:{generated_at.date().isoformat()}"
