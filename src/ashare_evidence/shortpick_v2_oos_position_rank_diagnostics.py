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
    QUIET_BREAKOUT_BASE_STRATEGY,
    _strategy_score,
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
    V2_BASELINE_CONFIG_ID,
    _cached_regime_features,
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
from ashare_evidence.shortpick_v2_theme_position_diagnostics import (
    DEFAULT_CURRENT_MONTH_END_DATE,
    DEFAULT_CURRENT_MONTH_START_DATE,
    DEFAULT_TOP_WINNER_COUNT,
    _current_month_winners,
    _float_or_none,
    _position_shape,
    _pre_signal_features,
    _safe_rate,
)

ARTIFACT_FAMILY = "shortpick_v2_oos_position_rank_diagnostics"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_oos_position_rank_diagnostics:v1"
DEFAULT_TRAIN_END_DATE = date(2025, 4, 30)
DEFAULT_HOLDOUT_START_DATE = date(2025, 5, 1)
DEFAULT_BROAD_RANK_LIMIT = 80


def build_shortpick_v2_oos_position_rank_diagnostics_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    train_end_date: date = DEFAULT_TRAIN_END_DATE,
    holdout_start_date: date = DEFAULT_HOLDOUT_START_DATE,
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
    broad_rank_limit: int = DEFAULT_BROAD_RANK_LIMIT,
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
        raise ValueError("OOS position/rank diagnostics currently requires H10; horizon_days must be 10")
    if broad_rank_limit < rank_limit:
        raise ValueError("broad_rank_limit must be >= rank_limit")
    if not (historical_start_date <= train_end_date < holdout_start_date <= historical_end_date):
        raise ValueError("train/holdout windows must be ordered and inside historical window")

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
    historical_signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=historical_end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    paper_signal_days = _eligible_signal_days(
        series_by_symbol,
        start_date=paper_start_date,
        end_date=paper_end_date,
        min_signal_symbol_count=min_signal_symbol_count,
    )
    historical_trade_days = _trade_days(
        series_by_symbol,
        start_date=historical_start_date,
        end_date=historical_end_date + timedelta(days=max(30, horizon_days * 4)),
        min_symbol_count=min_signal_symbol_count,
    )
    paper_trade_days = _trade_days(
        series_by_symbol,
        start_date=paper_start_date,
        end_date=paper_end_date + timedelta(days=max(30, horizon_days * 4)),
        min_symbol_count=min_signal_symbol_count,
    )
    historical_contexts = _contexts_by_signal_day(series_by_symbol, signal_days=historical_signal_days)
    paper_contexts = _contexts_by_signal_day(series_by_symbol, signal_days=paper_signal_days)
    historical_quiet_ranked = _build_quiet_ranked_symbols(
        signal_days=historical_signal_days,
        contexts_by_day=historical_contexts,
        pool_limit=pool_limit,
        rank_limit=max(broad_rank_limit, rank_limit),
    )
    paper_quiet_ranked = _build_quiet_ranked_symbols(
        signal_days=paper_signal_days,
        contexts_by_day=paper_contexts,
        pool_limit=pool_limit,
        rank_limit=max(broad_rank_limit, rank_limit),
    )
    historical_selections = _top5_from_quiet_ranked(
        signal_days=historical_signal_days,
        contexts_by_day=historical_contexts,
        quiet_ranked=historical_quiet_ranked,
        pool_limit=pool_limit,
    )
    paper_selections = _top5_from_quiet_ranked(
        signal_days=paper_signal_days,
        contexts_by_day=paper_contexts,
        quiet_ranked=paper_quiet_ranked,
        pool_limit=pool_limit,
    )
    baseline_config = _v2_baseline_config()
    historical_trades = _simulate_closed_trade_ledger(
        series_by_symbol,
        signal_days=historical_signal_days,
        trade_days=historical_trade_days,
        selections=historical_selections,
        config=baseline_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    paper_trades = _simulate_closed_trade_ledger(
        series_by_symbol,
        signal_days=paper_signal_days,
        trade_days=paper_trade_days,
        selections=paper_selections,
        config=baseline_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    paper_market_reference = _market_reference_summary(series_by_symbol, signal_days=paper_signal_days)
    paper_result = _simulate_rule_config(
        series_by_symbol,
        signal_days=paper_signal_days,
        trade_days=paper_trade_days,
        selections=paper_selections,
        config=baseline_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        market_reference_total_return=paper_market_reference.get("total_return"),
        decision_sample_limit=0,
    )
    winners = _current_month_winners(
        series_by_symbol,
        current_month_start_date=current_month_start_date,
        current_month_end_date=current_month_end_date,
        top_n=top_winner_count,
    )
    position_oos = _position_oos_diagnostics(
        series_by_symbol,
        historical_trades=historical_trades,
        paper_trades=paper_trades,
        historical_signal_days=historical_signal_days,
        paper_signal_days=paper_signal_days,
        train_end_date=train_end_date,
        holdout_start_date=holdout_start_date,
        historical_end_date=historical_end_date,
    )
    rank_diagnostics = _rank_entry_diagnostics(
        winners.get("top_winners") or [],
        series_by_symbol=series_by_symbol,
        paper_signal_days=paper_signal_days,
        contexts_by_day=paper_contexts,
        quiet_ranked=paper_quiet_ranked,
        top5_selections=paper_selections,
        paper_trades=paper_trades,
        current_month_start_date=current_month_start_date,
        broad_rank_limit=broad_rank_limit,
    )
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, current_month_start_date, current_month_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready",
        "claim_ceiling": "research_observation",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "question_cn": "上一跳显示 6 月强势股大多在可观察域内但进不了 v2 Top5；本跳验证位置形态是否样本外稳定，并定位 Rank2/Top5 排序链路卡点。",
            "baseline_config_id": V2_BASELINE_CONFIG_ID,
            "baseline_buy_cn": f"固定单笔约 {DEFAULT_BASELINE_TARGET_NOTIONAL / 10000:.1f} 万，Rank2 首选，Rank3-Rank6 同日候补。",
            "historical_start_date": historical_start_date.isoformat(),
            "train_end_date": train_end_date.isoformat(),
            "holdout_start_date": holdout_start_date.isoformat(),
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
            "historical_signal_day_count": len(historical_signal_days),
            "paper_signal_day_count": len(paper_signal_days),
            "historical_trade_count": len(historical_trades),
            "paper_closed_trade_count": len(paper_trades),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "paper_baseline": _summary_row(paper_result, trade_day_count=len(paper_trade_days)),
        "current_month_winners": {
            key: value for key, value in winners.items() if key != "top_winners"
        },
        "position_oos_diagnostics": position_oos,
        "rank_entry_diagnostics": rank_diagnostics,
        "interpretation": _interpretation(position_oos, rank_diagnostics),
        "leakage_audit": {
            "status": "passed",
            "notes": [
                "Position bucket labels use only signal-day-or-earlier features; trade returns are outcomes.",
                "Current-month winner labels are post-hoc opportunity labels and are not used to promote a rule.",
                "Diagnostic scoring uses only signal-day context, but it is reported as coverage diagnostics, not a backtest.",
                "No rule is promoted by this artifact.",
            ],
        },
        "event_refs": [
            "shortpick_v2.oos_position_rank_diagnostics.generated",
            f"shortpick_v2.oos_position_rank_diagnostics.month.{current_month_start_date.isoformat()}_{current_month_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_oos_position_rank_diagnostics_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"OOS position/rank diagnostics validation failed: {validation}")
    return payload


def write_shortpick_v2_oos_position_rank_diagnostics_artifact(
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
        path.write_text(render_shortpick_v2_oos_position_rank_diagnostics_markdown(payload), encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_oos_position_rank_diagnostics_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_oos_position_rank_diagnostics_payload(
        json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    )


def validate_shortpick_v2_oos_position_rank_diagnostics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    position = payload.get("position_oos_diagnostics") if isinstance(payload.get("position_oos_diagnostics"), dict) else {}
    rank = payload.get("rank_entry_diagnostics") if isinstance(payload.get("rank_entry_diagnostics"), dict) else {}
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_strategy_promotion", str(scope.get("promotion_status")))
    check("position_ready", int(position.get("historical_trade_count") or 0) >= 50, str(position.get("historical_trade_count")))
    check("holdout_ready", int(position.get("holdout_trade_count") or 0) >= 10, str(position.get("holdout_trade_count")))
    check("rank_ready", int(rank.get("top_winner_count") or 0) >= 30, str(rank.get("top_winner_count")))
    check("diagnostic_score_ready", len(rank.get("diagnostic_score_rows") or []) >= 2, str(len(rank.get("diagnostic_score_rows") or [])))
    check("leakage_status", (payload.get("leakage_audit") or {}).get("status") == "passed", str((payload.get("leakage_audit") or {}).get("status")))
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "position_recommendation_status": (position.get("recommendation") or {}).get("status"),
            "rank_recommendation_status": (rank.get("recommendation") or {}).get("status"),
        },
    }


def render_shortpick_v2_oos_position_rank_diagnostics_markdown(payload: dict[str, Any]) -> str:
    paper = payload.get("paper_baseline") if isinstance(payload.get("paper_baseline"), dict) else {}
    position = payload.get("position_oos_diagnostics") if isinstance(payload.get("position_oos_diagnostics"), dict) else {}
    rank = payload.get("rank_entry_diagnostics") if isinstance(payload.get("rank_entry_diagnostics"), dict) else {}
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    lines = [
        "# 试验田 v2 样本外位置形态与 Rank 入口诊断",
        "",
        "本产物是研究型下一跳：只解释方向，不晋级策略，不替换纸面追踪。",
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
        "## 位置形态样本外对照",
        "",
        "| 形态 | train 交易 | train 中位收益 | holdout 交易 | holdout 中位收益 | paper 交易 | paper 中位收益 | 判断 |",
        "|------|------------|----------------|---------------|------------------|------------|----------------|------|",
    ]
    for row in position.get("bucket_rows") or []:
        train = row.get("train") if isinstance(row.get("train"), dict) else {}
        holdout = row.get("holdout") if isinstance(row.get("holdout"), dict) else {}
        paper_bucket = row.get("paper") if isinstance(row.get("paper"), dict) else {}
        lines.append(
            "| {label} | {tc} | {tm} | {hc} | {hm} | {pc} | {pm} | {verdict} |".format(
                label=row.get("label_cn"),
                tc=int(train.get("count") or 0),
                tm=_pct(train.get("median_net_return")),
                hc=int(holdout.get("count") or 0),
                hm=_pct(holdout.get("median_net_return")),
                pc=int(paper_bucket.get("count") or 0),
                pm=_pct(paper_bucket.get("median_net_return")),
                verdict=row.get("verdict_cn"),
            )
        )
    lines.extend(
        [
            "",
            f"- 位置形态建议：{(position.get('recommendation') or {}).get('message_cn')}",
            "",
            "## Rank2/Top5 入口卡点",
            "",
            f"- Top 强势股进入合格观察域：{_pct(rank.get('eligible_universe_hit_rate'))}。",
            f"- Top 强势股进入 quiet broad rank 前 {int(rank.get('broad_rank_limit') or 0)}：{_pct(rank.get('quiet_broad_hit_rate'))}。",
            f"- Top 强势股进入最终 Top5：{_pct(rank.get('final_top5_hit_rate'))}。",
            f"- 实际买入 Top 强势股：{_pct(rank.get('bought_top_winner_rate'))}。",
            f"- 这里的“启动前”指 {rank.get('current_month_start_date') or 'current_month_start_date'} 之前；以上覆盖率是事后诊断，不构成可交易排序回测。",
            "",
            "| 诊断排序 | 含义 | Top5 覆盖 | 启动前 Top5 覆盖 | Top10 覆盖 |",
            "|----------|------|-----------|------------------|------------|",
        ]
    )
    for row in rank.get("diagnostic_score_rows") or []:
        lines.append(
            "| {label} | {meaning} | {top5} | {pre_top5} | {top10} |".format(
                label=row.get("label_cn"),
                meaning=row.get("meaning_cn"),
                top5=_pct(row.get("top5_hit_rate")),
                pre_top5=_pct(row.get("pre_launch_top5_hit_rate")),
                top10=_pct(row.get("top10_hit_rate")),
            )
        )
    lines.extend(["", f"- Rank 入口建议：{(rank.get('recommendation') or {}).get('message_cn')}", "", "## 下一步"])
    for step in interpretation.get("recommended_next_steps_cn") or []:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def _build_quiet_ranked_symbols(
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    pool_limit: int,
    rank_limit: int,
) -> dict[date, list[str]]:
    selections: dict[date, list[str]] = {}
    for signal_day in signal_days:
        contexts = contexts_by_day.get(signal_day) or []
        pool = sorted(
            contexts,
            key=lambda item: (-abs(float(item["return_1d"])), float(item["amount"])),
            reverse=True,
        )[: max(pool_limit, 80)]
        ranked = sorted(pool, key=lambda item: _strategy_score(pool, item, QUIET_BREAKOUT_BASE_STRATEGY), reverse=True)
        quiet_pick = ranked[1] if len(ranked) >= 2 else None
        if (
            quiet_pick is None
            or float(quiet_pick.get("return_10d") or 0.0) < 0.0
            or float(quiet_pick.get("return_1d") or 0.0) > 0.04
        ):
            ranked = []
        selections[signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections


def _top5_from_quiet_ranked(
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    quiet_ranked: dict[date, list[str]],
    pool_limit: int,
) -> dict[date, list[str]]:
    regime_features = _cached_regime_features(
        contexts_by_day=contexts_by_day,
        signal_days=signal_days,
        pool_limit=pool_limit,
    )
    return _build_rank2_primary_top5_selections(
        signal_days,
        quiet_base_selections=quiet_ranked,
        regime_features=regime_features,
        weekday_spec=WEEKDAY_MODE_SPECS["mtw"],
    )


def _position_oos_diagnostics(
    series_by_symbol: dict[str, Any],
    *,
    historical_trades: list[Any],
    paper_trades: list[Any],
    historical_signal_days: list[date],
    paper_signal_days: list[date],
    train_end_date: date,
    holdout_start_date: date,
    historical_end_date: date,
) -> dict[str, Any]:
    historical_features = [
        _trade_feature_with_shape(series_by_symbol, trade, signal_days=historical_signal_days)
        for trade in historical_trades
    ]
    paper_features = [
        _trade_feature_with_shape(series_by_symbol, trade, signal_days=paper_signal_days)
        for trade in paper_trades
    ]
    windows = {
        "train": [row for row in historical_features if date.fromisoformat(row["signal_day"]) <= train_end_date],
        "holdout": [
            row
            for row in historical_features
            if holdout_start_date <= date.fromisoformat(row["signal_day"]) <= historical_end_date
        ],
        "historical_all": historical_features,
        "paper": paper_features,
    }
    bucket_ids = ("chase_high", "pullback_setup", "low_pre5_pullback", "other")
    bucket_rows = []
    for bucket_id in bucket_ids:
        row = {
            "bucket_id": bucket_id,
            "label_cn": _bucket_label(bucket_id),
            "definition_cn": _bucket_definition(bucket_id),
        }
        for window_id, rows in windows.items():
            row[window_id] = _bucket_summary([item for item in rows if item.get("position_shape") == bucket_id])
        row["verdict_cn"] = _bucket_verdict(row)
        bucket_rows.append(row)
    return {
        "train_trade_count": len(windows["train"]),
        "holdout_trade_count": len(windows["holdout"]),
        "historical_trade_count": len(historical_features),
        "paper_trade_count": len(paper_features),
        "bucket_rows": bucket_rows,
        "recommendation": _position_recommendation(bucket_rows),
        "paper_trade_samples": _paper_trade_samples(paper_trades, paper_features),
    }


def _rank_entry_diagnostics(
    winners: list[dict[str, Any]],
    *,
    series_by_symbol: dict[str, Any],
    paper_signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    quiet_ranked: dict[date, list[str]],
    top5_selections: dict[date, list[str]],
    paper_trades: list[Any],
    current_month_start_date: date,
    broad_rank_limit: int,
) -> dict[str, Any]:
    winner_symbols = {str(row.get("symbol")) for row in winners}
    bought_symbols = {str(trade.symbol) for trade in paper_trades}
    context_by_day_symbol = {
        day: {str(context.get("symbol")): context for context in contexts_by_day.get(day, [])}
        for day in paper_signal_days
    }
    diagnostic_rankings = _diagnostic_rankings(
        series_by_symbol=series_by_symbol,
        paper_signal_days=paper_signal_days,
        contexts_by_day=contexts_by_day,
    )
    rows: list[dict[str, Any]] = []
    for winner in winners:
        symbol = str(winner.get("symbol"))
        eligible_days = [
            day for day in paper_signal_days if symbol in context_by_day_symbol.get(day, {})
        ]
        quiet_days = [day for day in paper_signal_days if symbol in set(quiet_ranked.get(day, [])[:broad_rank_limit])]
        top5_days = [day for day in paper_signal_days if symbol in set(top5_selections.get(day, []))]
        quiet_positions = [
            quiet_ranked[day].index(symbol) + 1
            for day in quiet_days
            if symbol in quiet_ranked.get(day, [])
        ]
        rows.append(
            {
                "symbol": symbol,
                "name": winner.get("name"),
                "industry": winner.get("industry"),
                "month_return": winner.get("month_return"),
                "position_shape": winner.get("position_shape"),
                "eligible_signal_day_count": len(eligible_days),
                "quiet_broad_day_count": len(quiet_days),
                "quiet_best_rank": min(quiet_positions) if quiet_positions else None,
                "quiet_median_rank": round(median(quiet_positions), 2) if quiet_positions else None,
                "final_top5_day_count": len(top5_days),
                "pre_launch_final_top5_day_count": len([day for day in top5_days if day < current_month_start_date]),
                "bought_by_v2": symbol in bought_symbols,
            }
        )
    score_rows = [
        _score_coverage_row(
            score_id,
            rankings,
            winners=winners,
            current_month_start_date=current_month_start_date,
        )
        for score_id, rankings in diagnostic_rankings.items()
    ]
    eligible_hits = [row for row in rows if int(row["eligible_signal_day_count"]) > 0]
    quiet_hits = [row for row in rows if int(row["quiet_broad_day_count"]) > 0]
    top5_hits = [row for row in rows if int(row["final_top5_day_count"]) > 0]
    bought_hits = [row for row in rows if bool(row["bought_by_v2"])]
    return {
        "top_winner_count": len(winners),
        "winner_symbol_count": len(winner_symbols),
        "paper_signal_day_count": len(paper_signal_days),
        "broad_rank_limit": broad_rank_limit,
        "current_month_start_date": current_month_start_date.isoformat(),
        "eligible_universe_hit_count": len(eligible_hits),
        "eligible_universe_hit_rate": _safe_rate(len(eligible_hits), len(winners)),
        "quiet_broad_hit_count": len(quiet_hits),
        "quiet_broad_hit_rate": _safe_rate(len(quiet_hits), len(winners)),
        "final_top5_hit_count": len(top5_hits),
        "final_top5_hit_rate": _safe_rate(len(top5_hits), len(winners)),
        "bought_top_winner_count": len(bought_hits),
        "bought_top_winner_rate": _safe_rate(len(bought_hits), len(winners)),
        "winner_rows": rows,
        "missed_top10_examples": [row for row in rows[:10] if int(row["final_top5_day_count"]) == 0],
        "diagnostic_score_rows": score_rows,
        "recommendation": _rank_recommendation(rows, score_rows),
    }


def _diagnostic_rankings(
    *,
    series_by_symbol: dict[str, Any],
    paper_signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
) -> dict[str, dict[date, list[str]]]:
    output: dict[str, dict[date, list[str]]] = {
        "industry_heat_pullback": {},
        "industry_heat_amount": {},
        "pullback_low_chase": {},
    }
    for signal_day in paper_signal_days:
        contexts = contexts_by_day.get(signal_day) or []
        industry_heat = _industry_heat(contexts)
        by_symbol = {str(context.get("symbol")): context for context in contexts}
        enriched = []
        for context in contexts:
            symbol = str(context.get("symbol"))
            shape = _context_position_shape(series_by_symbol, context, signal_day=signal_day)
            enriched.append(
                {
                    **context,
                    "position_shape": shape,
                    "industry_heat": industry_heat.get(str(context.get("industry") or "unknown"), 0.0),
                    "amount_pct": _percent_rank(by_symbol.values(), symbol=symbol, key="amount"),
                    "ret20_pct": _percent_rank(by_symbol.values(), symbol=symbol, key="return_20d"),
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
    raw = {industry: fmean(values) if values else 0.0 for industry, values in grouped.items()}
    if not raw:
        return {}
    ordered = sorted(raw.items(), key=lambda item: item[1])
    denom = max(1, len(ordered) - 1)
    return {industry: index / denom for index, (industry, _) in enumerate(ordered)}


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
    return 0.55 * shape_bonus + 0.25 * float(item.get("ret20_pct") or 0.0) + 0.20 * float(item.get("amount_pct") or 0.0) - 0.35 * chase_penalty


def _score_coverage_row(
    score_id: str,
    rankings: dict[date, list[str]],
    *,
    winners: list[dict[str, Any]],
    current_month_start_date: date,
) -> dict[str, Any]:
    winner_symbols = {str(row.get("symbol")) for row in winners}
    top5_hits: set[str] = set()
    top10_hits: set[str] = set()
    pre_top5_hits: set[str] = set()
    for signal_day, ranked in rankings.items():
        top5 = set(ranked[:5])
        top10 = set(ranked[:10])
        top5_hits.update(winner_symbols & top5)
        top10_hits.update(winner_symbols & top10)
        if signal_day < current_month_start_date:
            pre_top5_hits.update(winner_symbols & top5)
    return {
        "score_id": score_id,
        "label_cn": _score_label(score_id),
        "meaning_cn": _score_meaning(score_id),
        "top5_hit_count": len(top5_hits),
        "top5_hit_rate": _safe_rate(len(top5_hits), len(winners)),
        "pre_launch_top5_hit_count": len(pre_top5_hits),
        "pre_launch_top5_hit_rate": _safe_rate(len(pre_top5_hits), len(winners)),
        "top10_hit_count": len(top10_hits),
        "top10_hit_rate": _safe_rate(len(top10_hits), len(winners)),
    }


def _trade_feature_with_shape(series_by_symbol: dict[str, Any], trade: Any, *, signal_days: list[date]) -> dict[str, Any]:
    feature = _trade_features(series_by_symbol, trade, signal_days=signal_days)
    feature["signal_day"] = trade.signal_day.isoformat()
    feature["position_shape"] = _position_shape(feature.get("stock_pre5d_return"), feature.get("price_vs_20d_high"))
    return feature


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


def _bucket_verdict(row: dict[str, Any]) -> str:
    train = row.get("train") if isinstance(row.get("train"), dict) else {}
    holdout = row.get("holdout") if isinstance(row.get("holdout"), dict) else {}
    paper = row.get("paper") if isinstance(row.get("paper"), dict) else {}
    holdout_count = int(holdout.get("count") or 0)
    train_median = _float_or_none(train.get("median_net_return"))
    holdout_median = _float_or_none(holdout.get("median_net_return"))
    paper_median = _float_or_none(paper.get("median_net_return"))
    if holdout_count < 10:
        return "holdout 样本不足"
    if train_median is not None and holdout_median is not None and train_median > 0 and holdout_median > 0:
        if paper_median is not None and paper_median < 0:
            return "历史样本外为正，但 paper 已转弱"
        return "历史样本外为正"
    if holdout_median is not None and holdout_median < 0:
        return "holdout 为负"
    return "暂不明确"


def _position_recommendation(bucket_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    for row in bucket_rows:
        if row.get("bucket_id") == "other":
            continue
        holdout = row.get("holdout") if isinstance(row.get("holdout"), dict) else {}
        holdout_median = _float_or_none(holdout.get("median_net_return"))
        if int(holdout.get("count") or 0) >= 10 and holdout_median is not None and holdout_median > 0:
            candidates.append(row)
    if not candidates:
        pullback = next((row for row in bucket_rows if row.get("bucket_id") == "pullback_setup"), {})
        holdout = pullback.get("holdout") if isinstance(pullback.get("holdout"), dict) else {}
        pullback_count = int(holdout.get("count") or 0)
        pullback_median = _float_or_none(holdout.get("median_net_return"))
        detail = ""
        if pullback_count and pullback_median is not None:
            detail = f"回撤蓄势 holdout 中位收益为 {_pct(pullback_median)}，但只有 {pullback_count} 笔。"
        return {
            "status": "no_promotable_hard_bucket",
            "message_cn": f"没有非兜底形态同时满足 holdout 样本量和正收益要求；{detail}位置形态只能作为软排序特征继续验证。",
        }
    candidates.sort(
        key=lambda row: float((row.get("holdout") or {}).get("median_net_return") or -9.0),
        reverse=True,
    )
    best = candidates[0]
    return {
        "status": "candidate_dimension_only",
        "best_bucket_id": best.get("bucket_id"),
        "message_cn": f"{best.get('label_cn')}在 holdout 中位收益最高，但本产物只支持把它纳入下一轮正式回测，不支持直接晋级。",
    }


def _rank_recommendation(rows: list[dict[str, Any]], score_rows: list[dict[str, Any]]) -> dict[str, Any]:
    score_rows = sorted(score_rows, key=lambda row: float(row.get("top5_hit_rate") or -1.0), reverse=True)
    final_hits = [row for row in rows if int(row.get("final_top5_day_count") or 0) > 0]
    broad_hits = [row for row in rows if int(row.get("quiet_broad_day_count") or 0) > 0]
    truncation_ratio_threshold = 0.5
    if broad_hits and len(final_hits) < len(broad_hits) * truncation_ratio_threshold:
        return {
            "status": "rank_truncation_suspect",
            "best_diagnostic_score_id": score_rows[0].get("score_id") if score_rows else None,
            "truncation_ratio_threshold": truncation_ratio_threshold,
            "message_cn": "强势股能进入更宽的 quiet 排名但很少进入最终 Top5，下一轮应优先验证排序/截断，而不是先改资金执行。",
        }
    return {
        "status": "rank_pool_gap_not_isolated",
        "best_diagnostic_score_id": score_rows[0].get("score_id") if score_rows else None,
        "truncation_ratio_threshold": truncation_ratio_threshold,
        "message_cn": "当前证据还不能把问题单独归因于 Top5 截断，需要和候选池条件一起验证。",
    }


def _interpretation(position: dict[str, Any], rank: dict[str, Any]) -> dict[str, Any]:
    position_status = (position.get("recommendation") or {}).get("status")
    rank_status = (rank.get("recommendation") or {}).get("status")
    messages = []
    if position_status == "no_promotable_hard_bucket":
        messages.append(str((position.get("recommendation") or {}).get("message_cn") or "位置形态没有可晋级硬过滤"))
    else:
        messages.append(str((position.get("recommendation") or {}).get("message_cn") or "位置形态只能作为候选维度"))
    if rank_status == "rank_truncation_suspect":
        messages.append("Rank 入口更像主要矛盾：强势股能进入宽排名，但最终 Top5 覆盖不足")
    else:
        messages.append(str((rank.get("recommendation") or {}).get("message_cn") or "Rank 入口尚未完全定位"))
    return {
        "status": "continue_research_no_strategy_promotion",
        "message_cn": "；".join(messages),
        "recommended_next_steps_cn": [
            "下一轮做正式历史回测：保持 H10 和 20 万资金约束，比较原 Top5、行业热度+回撤蓄势排序、行业热度+成交额排序、低追高排序。",
            "位置形态只作为候选排序特征参与，不先做硬过滤，避免因为小样本误杀可盈利交易。",
            "如果排序版在历史、holdout、paper 都改善，再进入参数网格；否则回到 v1 冻结策略资金约束版做更强对照。",
        ],
    }


def _paper_trade_samples(paper_trades: list[Any], paper_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples = []
    for trade, feature in zip(paper_trades, paper_features, strict=True):
        samples.append(
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
        )
    return samples


def _percent_rank(values: Any, *, symbol: str, key: str) -> float:
    rows = list(values)
    ordered = sorted(
        ((str(row.get("symbol")), float(row.get(key) or 0.0)) for row in rows),
        key=lambda item: item[1],
    )
    if len(ordered) <= 1:
        return 0.0
    for index, (row_symbol, _) in enumerate(ordered):
        if row_symbol == symbol:
            return index / float(len(ordered) - 1)
    return 0.0


def _score_label(score_id: str) -> str:
    return {
        "industry_heat_pullback": "行业热度 + 回撤蓄势",
        "industry_heat_amount": "行业热度 + 成交额",
        "pullback_low_chase": "回撤优先 + 低追高",
    }.get(score_id, score_id)


def _score_meaning(score_id: str) -> str:
    return {
        "industry_heat_pullback": "主题行业强、位置不过度追高的股票前置。",
        "industry_heat_amount": "主题行业强且流动性高的股票前置。",
        "pullback_low_chase": "先排除高位追强，优先回撤蓄势。",
    }.get(score_id, "")


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


def _rate(values: list[bool]) -> float | None:
    return round(sum(1 for value in values if value) / len(values), 6) if values else None


def _artifact_id(generated_at: datetime, month_start: date, month_end: date) -> str:
    return f"{ARTIFACT_FAMILY}:{month_start.isoformat()}:{month_end.isoformat()}:{generated_at.date().isoformat()}"
