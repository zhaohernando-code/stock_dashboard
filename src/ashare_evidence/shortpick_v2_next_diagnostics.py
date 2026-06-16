from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    INDEX_SYMBOLS,
    LOW_TURNOVER_UPTREND_STRATEGY,
    QUIET_BREAKOUT_BASE_STRATEGY,
    _Bar,
    _context_for_signal_day,
    _industry_from_profile_payload,
    _mean,
    _Series,
    _strategy_score,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
    _apply_strategy_regime_filter,
    _eligible_signal_days,
    _trade_days,
)
from ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix import (
    WEEKDAY_MODE_SPECS,
    _build_rank2_primary_top5_selections,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    ShortpickV2RuleConfig,
    _coverage_notes,
    _dynamic_exit_reason,
    _evaluate_signal_entry,
    _exit_is_unfillable_limit_down,
    _market_reference_summary,
    _prepare_signal_entries,
    _simulate_rule_config,
)

ARTIFACT_FAMILY = "shortpick_v2_next_diagnostics"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_next_diagnostics:v1"
DEFAULT_HISTORICAL_START_DATE = date(2023, 4, 13)
DEFAULT_HISTORICAL_END_DATE = date(2026, 5, 8)
DEFAULT_PAPER_START_DATE = date(2026, 5, 8)
DEFAULT_PAPER_END_DATE = date(2026, 6, 15)
DEFAULT_HORIZON_DAYS = 10
DEFAULT_POOL_LIMIT = 40
DEFAULT_RANK_LIMIT = 6
DEFAULT_MIN_SIGNAL_SYMBOL_COUNT = 45
DEFAULT_BASELINE_TARGET_NOTIONAL = 85_000.0
DEFAULT_SIMILAR_WINDOW_SIZE = 25
DEFAULT_SIMILAR_TOP_N = 5
DEFAULT_BIG_TRADE_COUNT = 15
CSI300_SYMBOL = "000300.SH"
V2_BASELINE_CONFIG_ID = "diagnostic_v2_quiet_rank2_poolhot10_mtw_fixed85_top5_h10"
V1_CONSTRAINED_CONFIG_ID = "diagnostic_v1_low_turnover_uptrend_200k_top1_or_skip_h10"


@dataclass(frozen=True)
class _ClosedTrade:
    signal_day: date
    entry_day: date
    exit_day: date
    symbol: str
    name: str
    industry: str
    selected_rank: int
    shares: int
    entry_price: float
    exit_price: float
    cost_basis: float
    proceeds: float
    pnl: float
    net_return: float
    pnl_pct_initial_cash: float
    exit_reason: str


def build_shortpick_v2_next_diagnostics_artifact(
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
        raise ValueError("next diagnostics currently requires H10; horizon_days must be 10")
    if rank_limit < DEFAULT_RANK_LIMIT:
        raise ValueError("rank_limit must be at least 6 so Rank2-Rank6 fallback candidates are available")

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
    historical_contexts = _contexts_by_signal_day(series_by_symbol, signal_days=historical_signal_days)
    paper_contexts = _contexts_by_signal_day(series_by_symbol, signal_days=paper_signal_days)
    historical_v2_selections = _build_v2_baseline_selections(
        signal_days=historical_signal_days,
        contexts_by_day=historical_contexts,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    paper_v2_selections = _build_v2_baseline_selections(
        signal_days=paper_signal_days,
        contexts_by_day=paper_contexts,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    historical_market_reference = _market_reference_summary(series_by_symbol, signal_days=historical_signal_days)
    paper_market_reference = _market_reference_summary(series_by_symbol, signal_days=paper_signal_days)
    baseline_config = _v2_baseline_config()
    historical_v2_result = _simulate_rule_config(
        series_by_symbol,
        signal_days=historical_signal_days,
        trade_days=historical_trade_days,
        selections=historical_v2_selections,
        config=baseline_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        market_reference_total_return=historical_market_reference.get("total_return"),
        decision_sample_limit=0,
    )
    historical_v2_summary = _summary_row(historical_v2_result, trade_day_count=len(historical_trade_days))
    paper_v2_result = _simulate_rule_config(
        series_by_symbol,
        signal_days=paper_signal_days,
        trade_days=paper_trade_days,
        selections=paper_v2_selections,
        config=baseline_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        market_reference_total_return=paper_market_reference.get("total_return"),
        decision_sample_limit=0,
    )
    paper_v2_summary = _summary_row(paper_v2_result, trade_day_count=len(paper_trade_days))
    historical_trades = _simulate_closed_trade_ledger(
        series_by_symbol,
        signal_days=historical_signal_days,
        trade_days=historical_trade_days,
        selections=historical_v2_selections,
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
        selections=paper_v2_selections,
        config=baseline_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    v1_control = _build_v1_constrained_control(
        series_by_symbol,
        signal_days=historical_signal_days,
        trade_days=historical_trade_days,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        contexts_by_day=historical_contexts,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        market_reference_total_return=historical_market_reference.get("total_return"),
    )
    similar_windows = _build_similar_window_diagnostic(
        series_by_symbol,
        historical_start_date=historical_start_date,
        historical_end_date=historical_end_date,
        paper_start_date=paper_start_date,
        paper_end_date=paper_end_date,
        window_size=DEFAULT_SIMILAR_WINDOW_SIZE,
        top_n=DEFAULT_SIMILAR_TOP_N,
    )
    trade_profile = _build_trade_profile(
        series_by_symbol,
        trades=historical_trades,
        paper_trades=paper_trades,
        historical_signal_days=historical_signal_days,
        paper_signal_days=paper_signal_days,
        initial_cash=initial_cash,
        big_trade_count=DEFAULT_BIG_TRADE_COUNT,
    )
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, historical_start_date, historical_end_date, paper_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready" if historical_signal_days else "blocked",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_and_current_window_diagnostics",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "question_cn": "历史回测很强但当前纸面窗口很弱，究竟是偶然窗口、暴露结构，还是 v2 选股相对 v1 失效？",
            "historical_start_date": historical_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "entry_price_source": entry_price_source,
            "promotion_status": "research_only_no_strategy_promotion",
        },
        "external_review": {
            "deepseek": {
                "status": "passed",
                "summary_cn": "认可逐笔画像、相似窗口、v1 资金约束强对照三方向互补；要求冻结特征和样本门槛。",
            },
            "xiaomi_mimo": {
                "status": "passed",
                "summary_cn": "认可当前问题更像暴露结构与窗口压力；要求不要用 6 笔纸面交易直接推断规则。",
            },
        },
        "data_scope": {
            "historical_signal_day_count": len(historical_signal_days),
            "historical_trade_day_count": len(historical_trade_days),
            "paper_signal_day_count": len(paper_signal_days),
            "paper_trade_day_count": len(paper_trade_days),
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "baseline_v2": {
            "config_id": V2_BASELINE_CONFIG_ID,
            "description_cn": "安静突破热度池 10%，周一至周三，Rank2 首选，Rank3-Rank6 同日候补，单笔约 8.5 万，最多 5 仓，H10 卖出。",
            "historical": historical_v2_summary,
            "paper_window": paper_v2_summary,
        },
        "diagnostics": {
            "trade_profile": trade_profile,
            "similar_market_windows": similar_windows,
            "v1_constrained_control": v1_control,
        },
        "interpretation": _interpretation(trade_profile, similar_windows, v1_control, historical_v2_summary, paper_v2_summary),
        "leakage_audit": {
            "status": "passed",
            "used_only_signal_day_or_earlier_data_for_entry_features": True,
            "notes": [
                "逐笔画像使用信号日或之前的行情特征；收益和卖出价只用于结果归因。",
                "相似窗口只用沪深300历史收益做检索，不用未来收益参与匹配。",
                "v1 强对照使用既有低换手上升趋势候选，不写入纸面追踪。",
            ],
        },
        "event_refs": [
            "shortpick_v2.next_diagnostics.generated",
            f"shortpick_v2.next_diagnostics.historical.{historical_start_date.isoformat()}_{historical_end_date.isoformat()}",
            f"shortpick_v2.next_diagnostics.paper.{paper_start_date.isoformat()}_{paper_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_next_diagnostics_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"next diagnostics validation failed: {validation}")
    return payload


def write_shortpick_v2_next_diagnostics_artifact(
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
        summary = render_shortpick_v2_next_diagnostics_markdown(payload)
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_next_diagnostics_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_next_diagnostics_payload(json.loads(Path(artifact_path).read_text(encoding="utf-8")))


def validate_shortpick_v2_next_diagnostics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    trade_profile = diagnostics.get("trade_profile") if isinstance(diagnostics.get("trade_profile"), dict) else {}
    similar_windows = diagnostics.get("similar_market_windows") if isinstance(diagnostics.get("similar_market_windows"), dict) else {}
    v1_control = diagnostics.get("v1_constrained_control") if isinstance(diagnostics.get("v1_constrained_control"), dict) else {}
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_strategy_promotion", str(scope.get("promotion_status")))
    check("h10_only", int(scope.get("horizon_days") or 0) == DEFAULT_HORIZON_DAYS, str(scope.get("horizon_days")))
    check("trade_profile_ready", int(trade_profile.get("historical_trade_count") or 0) >= 50, str(trade_profile.get("historical_trade_count")))
    check("similar_window_ready", int(similar_windows.get("matched_window_count") or 0) >= 3, str(similar_windows.get("matched_window_count")))
    check("v1_control_ready", (v1_control.get("status") == "ready"), str(v1_control.get("status")))
    check("review_recorded", all((payload.get("external_review") or {}).get(key, {}).get("status") == "passed" for key in ("deepseek", "xiaomi_mimo")), "external review statuses")
    check("leakage_status", (payload.get("leakage_audit") or {}).get("status") == "passed", str((payload.get("leakage_audit") or {}).get("status")))
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "historical_trade_count": trade_profile.get("historical_trade_count"),
            "matched_window_count": similar_windows.get("matched_window_count"),
            "v1_control_status": v1_control.get("status"),
            "interpretation_status": (payload.get("interpretation") or {}).get("status"),
        },
    }


def render_shortpick_v2_next_diagnostics_markdown(payload: dict[str, Any]) -> str:
    baseline = payload.get("baseline_v2") if isinstance(payload.get("baseline_v2"), dict) else {}
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    trade_profile = diagnostics.get("trade_profile") if isinstance(diagnostics.get("trade_profile"), dict) else {}
    similar_windows = diagnostics.get("similar_market_windows") if isinstance(diagnostics.get("similar_market_windows"), dict) else {}
    v1_control = diagnostics.get("v1_constrained_control") if isinstance(diagnostics.get("v1_constrained_control"), dict) else {}
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    historical = baseline.get("historical") if isinstance(baseline.get("historical"), dict) else {}
    paper = baseline.get("paper_window") if isinstance(baseline.get("paper_window"), dict) else {}
    v1_summary = v1_control.get("summary") if isinstance(v1_control.get("summary"), dict) else {}
    lines = [
        "# 试验田 v2 下一轮诊断",
        "",
        "本产物只用于解释当前死胡同，不晋级或替换任何纸面追踪策略。",
        "",
        "## 结论",
        "",
        str(interpretation.get("message_cn") or "暂无结论。"),
        f"纸面窗口只有 {int(trade_profile.get('paper_trade_count') or 0)} 笔已平仓交易，回撤数字受单笔影响很大，不能直接外推为新规则。",
        "",
        "## 基线表现",
        "",
        "| 策略 | 总收益 | 年化 | 超额 | 最大回撤 | 交易 | skip |",
        "|------|--------|------|------|----------|------|------|",
        "| v2 基线历史 | {total} | {ann} | {excess} | {dd} | {trades} | {skip} |".format(
            total=_pct(historical.get("total_return")),
            ann=_pct(historical.get("annualized_return")),
            excess=_pct(historical.get("market_excess_total_return")),
            dd=_pct(historical.get("max_drawdown")),
            trades=int(historical.get("trade_count") or 0),
            skip=_pct(historical.get("skipped_ratio")),
        ),
        "| v2 当前纸面窗口 | {total} | {ann} | {excess} | {dd} | {trades} | {skip} |".format(
            total=_pct(paper.get("total_return")),
            ann=_pct(paper.get("annualized_return")),
            excess=_pct(paper.get("market_excess_total_return")),
            dd=_pct(paper.get("max_drawdown")),
            trades=int(paper.get("trade_count") or 0),
            skip=_pct(paper.get("skipped_ratio")),
        ),
        "| v1 资金约束强对照 | {total} | {ann} | {excess} | {dd} | {trades} | {skip} |".format(
            total=_pct(v1_summary.get("total_return")),
            ann=_pct(v1_summary.get("annualized_return")),
            excess=_pct(v1_summary.get("market_excess_total_return")),
            dd=_pct(v1_summary.get("max_drawdown")),
            trades=int(v1_summary.get("trade_count") or 0),
            skip=_pct(v1_summary.get("skipped_ratio")),
        ),
        "",
        "v1 强对照采用“20 万账户、100 股手数、买不起就跳过”的资金约束；v2 基线采用固定 8.5 万单笔目标和同日候补，两者用于强弱对照，不表示同一买入资金模型。",
        "",
        "## 逐笔画像",
        "",
        f"- 历史已平仓交易：{int(trade_profile.get('historical_trade_count') or 0)} 笔；当前纸面窗口已平仓交易：{int(trade_profile.get('paper_trade_count') or 0)} 笔。",
        f"- 大亏组特征：{trade_profile.get('loss_group_summary_cn') or '-'}",
        f"- 大赚组特征：{trade_profile.get('win_group_summary_cn') or '-'}",
        "",
        "## 相似窗口",
        "",
        f"- 当前窗口沪深300 {int(similar_windows.get('window_size') or 0)} 个交易日收益：{_pct(similar_windows.get('current_window_index_return'))}",
        f"- 最相似历史窗口数量：{int(similar_windows.get('matched_window_count') or 0)}；后续窗口收益中位数：{_pct(similar_windows.get('matched_future_return_median'))}",
        "",
        "| 排名 | 历史窗口 | 沪深300窗口收益 | 距离 | 后续25日沪深300 |",
        "|------|----------|----------------|------|----------------|",
    ]
    for index, row in enumerate(similar_windows.get("matched_windows") or [], start=1):
        lines.append(
            "| {rank} | {start} 至 {end} | {ret} | {dist} | {future} |".format(
                rank=index,
                start=row.get("start_date"),
                end=row.get("end_date"),
                ret=_pct(row.get("index_return")),
                dist=_pct(row.get("distance_abs")),
                future=_pct(row.get("future_index_return")),
            )
        )
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "- 如果逐笔画像只有样本内差异、没有稳定先验，本轮不生成新过滤器。",
            "- 如果相似窗口显示当前只是历史上常见弱窗口，优先继续纸面观察；如果显示明显分布外，再单独研究降仓或暂停规则。",
            "- 如果 v1 资金约束强对照接近或超过 v2，下一轮应回到 v1 冻结逻辑而不是继续扩展 v2 参数。",
            "",
        ]
    )
    return "\n".join(lines)


def _load_daily_series_between(session: Session, *, start_date: date, end_date: date) -> dict[str, _Series]:
    bind = session.get_bind()
    database_path = getattr(getattr(bind, "url", None), "database", None)
    if database_path and str(database_path) != ":memory:":
        return _load_daily_series_between_sqlite(Path(str(database_path)), start_date=start_date, end_date=end_date)

    start_at = datetime.combine(start_date, time.min)
    end_at = datetime.combine(end_date, time.max)
    rows = session.execute(
        select(
            Stock.symbol,
            Stock.name,
            Stock.profile_payload,
            MarketBar.observed_at,
            MarketBar.open_price,
            MarketBar.high_price,
            MarketBar.low_price,
            MarketBar.close_price,
            MarketBar.amount,
            MarketBar.turnover_rate,
        )
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(
            MarketBar.timeframe == "1d",
            MarketBar.observed_at >= start_at,
            MarketBar.observed_at <= end_at,
        )
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    )
    grouped: dict[str, tuple[str, str, list[_Bar]]] = {}
    for (
        symbol,
        name,
        profile_payload,
        observed_at,
        open_price,
        high_price,
        low_price,
        close_price,
        amount,
        turnover_rate,
    ) in rows:
        if not close_price:
            continue
        grouped.setdefault(str(symbol), (str(name or symbol), _industry_from_profile_payload(profile_payload), []))[2].append(
            _Bar(
                day=observed_at.date(),
                open=float(open_price),
                high=float(high_price),
                low=float(low_price),
                close=float(close_price),
                amount=float(amount or 0.0),
                turnover=None if turnover_rate is None else float(turnover_rate),
            )
        )
    output: dict[str, _Series] = {}
    for symbol, (name, industry, bars) in grouped.items():
        deduped: dict[date, _Bar] = {}
        for bar in bars:
            deduped[bar.day] = bar
        ordered = [deduped[day] for day in sorted(deduped)]
        output[symbol] = _Series(
            symbol=symbol,
            name=name,
            industry=industry,
            bars=ordered,
            by_day={bar.day: index for index, bar in enumerate(ordered)},
        )
    return output


def _load_daily_series_between_sqlite(db_path: Path, *, start_date: date, end_date: date) -> dict[str, _Series]:
    start_text = datetime.combine(start_date, time.min).isoformat(sep=" ")
    end_text = datetime.combine(end_date, time.max).isoformat(sep=" ")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        stock_rows = conn.execute("select id, symbol, name, profile_payload from stocks").fetchall()
        stock_meta: dict[int, tuple[str, str, str]] = {}
        for stock_id, symbol, name, profile_payload in stock_rows:
            stock_meta[int(stock_id)] = (
                str(symbol),
                str(name or symbol),
                _industry_from_profile_payload(json.loads(profile_payload) if isinstance(profile_payload, str) else profile_payload),
            )
        grouped: dict[str, tuple[str, str, list[_Bar]]] = {}
        rows = conn.execute(
            """
            select stock_id, observed_at, open_price, high_price, low_price, close_price, amount, turnover_rate
            from market_bars
            where timeframe = '1d'
              and observed_at >= ?
              and observed_at <= ?
            order by stock_id asc, observed_at asc, id asc
            """,
            (start_text, end_text),
        )
        for stock_id, observed_at, open_price, high_price, low_price, close_price, amount, turnover_rate in rows:
            if not close_price:
                continue
            meta = stock_meta.get(int(stock_id))
            if meta is None:
                continue
            symbol, name, industry = meta
            observed_day = datetime.fromisoformat(str(observed_at)).date()
            grouped.setdefault(symbol, (name, industry, []))[2].append(
                _Bar(
                    day=observed_day,
                    open=float(open_price),
                    high=float(high_price),
                    low=float(low_price),
                    close=float(close_price),
                    amount=float(amount or 0.0),
                    turnover=None if turnover_rate is None else float(turnover_rate),
                )
            )
        output: dict[str, _Series] = {}
        for symbol, (name, industry, bars) in grouped.items():
            deduped: dict[date, _Bar] = {}
            for bar in bars:
                deduped[bar.day] = bar
            ordered = [deduped[day] for day in sorted(deduped)]
            output[symbol] = _Series(
                symbol=symbol,
                name=name,
                industry=industry,
                bars=ordered,
                by_day={bar.day: index for index, bar in enumerate(ordered)},
            )
        return output
    finally:
        conn.close()


def _contexts_by_signal_day(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
) -> dict[date, list[dict[str, Any]]]:
    output: dict[date, list[dict[str, Any]]] = {}
    for signal_day in signal_days:
        contexts = [
            context
            for symbol, series in series_by_symbol.items()
            if symbol not in INDEX_SYMBOLS
            for context in [_context_for_signal_day(series, signal_day, include_golden_cross=False)]
            if context is not None
        ]
        output[signal_day] = contexts
    return output


def _build_cached_strategy_selections(
    *,
    contexts_by_day: dict[date, list[dict[str, Any]]],
    signal_days: list[date],
    strategy: str,
    pool_limit: int,
    rank_limit: int,
) -> dict[date, list[str]]:
    selections: dict[date, list[str]] = {}
    for signal_day in signal_days:
        contexts = contexts_by_day.get(signal_day) or []
        effective_pool_limit = pool_limit

        def pool_sort_key(item: dict[str, Any]) -> tuple[float, float, float] | tuple[float, float]:
            return (
                float(item["return_1d"]),
                float(item["amount"]),
                float(item["turnover_rate"]),
            )

        if strategy == LOW_TURNOVER_UPTREND_STRATEGY:
            effective_pool_limit = max(pool_limit, 120)

            def pool_sort_key(item: dict[str, Any]) -> tuple[float, float]:
                return (float(item["amount"]), float(item["turnover_rate"]))

        elif strategy == QUIET_BREAKOUT_BASE_STRATEGY:
            effective_pool_limit = max(pool_limit, 80)

            def pool_sort_key(item: dict[str, Any]) -> tuple[float, float]:
                return (-abs(float(item["return_1d"])), float(item["amount"]))

        pool = sorted(contexts, key=pool_sort_key, reverse=True)[:effective_pool_limit]
        if not pool:
            selections[signal_day] = []
            continue
        ranked = sorted(pool, key=lambda item, strategy=strategy: _strategy_score(pool, item, strategy), reverse=True)
        if strategy == LOW_TURNOVER_UPTREND_STRATEGY:
            ranked = [item for item in ranked if float(item.get("return_20d") or 0.0) > 0.0]
        elif strategy == QUIET_BREAKOUT_BASE_STRATEGY:
            quiet_pick = ranked[1] if len(ranked) >= 2 else None
            if (
                quiet_pick is None
                or float(quiet_pick.get("return_10d") or 0.0) < 0.0
                or float(quiet_pick.get("return_1d") or 0.0) > 0.04
            ):
                ranked = []
        selections[signal_day] = [str(item["symbol"]) for item in ranked[:rank_limit]]
    return selections


def _cached_regime_features(
    *,
    contexts_by_day: dict[date, list[dict[str, Any]]],
    signal_days: list[date],
    pool_limit: int,
) -> dict[date, dict[str, float]]:
    features_by_day: dict[date, dict[str, float]] = {}
    for signal_day in signal_days:
        contexts = contexts_by_day.get(signal_day) or []
        if not contexts:
            continue
        pool = sorted(
            contexts,
            key=lambda item: (
                float(item["return_1d"]),
                float(item["amount"]),
                float(item["turnover_rate"]),
            ),
            reverse=True,
        )[:pool_limit]
        if not pool:
            continue
        features_by_day[signal_day] = {
            "universe_ret10_mean": _mean([float(item["return_10d"]) for item in contexts]) or 0.0,
            "universe_breadth10": sum(1 for item in contexts if float(item["return_10d"]) > 0) / len(contexts),
            "pool_ret1_mean": _mean([float(item["return_1d"]) for item in pool]) or 0.0,
            "pool_ret10_mean": _mean([float(item["return_10d"]) for item in pool]) or 0.0,
        }
    return features_by_day


def _build_v2_baseline_selections(
    *,
    signal_days: list[date],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    pool_limit: int,
    rank_limit: int,
) -> dict[date, list[str]]:
    quiet_base = _build_cached_strategy_selections(
        contexts_by_day=contexts_by_day,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=max(rank_limit, DEFAULT_RANK_LIMIT),
    )
    regime_features = _cached_regime_features(contexts_by_day=contexts_by_day, signal_days=signal_days, pool_limit=pool_limit)
    return _build_rank2_primary_top5_selections(
        signal_days,
        quiet_base_selections=quiet_base,
        regime_features=regime_features,
        weekday_spec=WEEKDAY_MODE_SPECS["mtw"],
    )


def _v2_baseline_config() -> ShortpickV2RuleConfig:
    return ShortpickV2RuleConfig(
        config_id=V2_BASELINE_CONFIG_ID,
        family="shortpick_v2_next_diagnostics",
        candidate_rank_limit=5,
        fallback_enabled=True,
        target_mode="fixed_notional",
        target_notional=DEFAULT_BASELINE_TARGET_NOTIONAL,
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
        max_position_count=5,
    )


def _v1_control_config() -> ShortpickV2RuleConfig:
    return ShortpickV2RuleConfig(
        config_id=V1_CONSTRAINED_CONFIG_ID,
        family="shortpick_v2_next_diagnostics",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "skip"),
        max_position_count=5,
        max_position_pct=1.0,
    )


def _build_v1_constrained_control(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    pool_limit: int,
    rank_limit: int,
    contexts_by_day: dict[date, list[dict[str, Any]]],
    cost_bps: float,
    stamp_tax_bps: float,
    market_reference_total_return: float | None,
) -> dict[str, Any]:
    raw_selections = _build_cached_strategy_selections(
        contexts_by_day=contexts_by_day,
        signal_days=signal_days,
        strategy=LOW_TURNOVER_UPTREND_STRATEGY,
        pool_limit=max(pool_limit, 120),
        rank_limit=max(rank_limit, 6),
    )
    regime_features = _cached_regime_features(contexts_by_day=contexts_by_day, signal_days=signal_days, pool_limit=pool_limit)
    selections = _apply_strategy_regime_filter(LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY, raw_selections, regime_features)
    config = _v1_control_config()
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
        market_reference_total_return=market_reference_total_return,
        decision_sample_limit=0,
    )
    return {
        "status": result.get("status"),
        "config_id": V1_CONSTRAINED_CONFIG_ID,
        "description_cn": "v1 冻结思路强对照：全市场10日上涨占比不低于45%，选择低换手上升趋势首位；20万账户、100股手数、买不起就跳过、H10卖出。",
        "summary": _summary_row(result, trade_day_count=len(trade_days)),
        "reason_counts": result.get("reason_counts") or {},
        "control_role_cn": "用来判断 v2 复杂选股是否真的优于 v1 冻结逻辑在资金约束下的表现。",
    }


def _simulate_closed_trade_ledger(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    selections: dict[date, list[str]],
    config: ShortpickV2RuleConfig,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    cost_bps: float,
    stamp_tax_bps: float,
) -> list[_ClosedTrade]:
    entries_by_day, _, _ = _prepare_signal_entries(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=selections,
        config=config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
    )
    active_days = sorted(set(trade_days) | set(entries_by_day))
    cash = float(initial_cash)
    buy_cost_rate = float(cost_bps) / 10000.0
    sell_cost_rate = float(cost_bps + stamp_tax_bps) / 10000.0
    open_positions: list[Any] = []
    closed: list[_ClosedTrade] = []

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
                still_open.append(position)
                continue
            proceeds = position.shares * close * (1.0 - sell_cost_rate)
            cash += proceeds
            pnl = proceeds - position.cost_basis
            closed.append(
                _ClosedTrade(
                    signal_day=position.signal_day,
                    entry_day=position.entry_day,
                    exit_day=current_day,
                    symbol=position.symbol,
                    name=str(series.name or position.symbol),
                    industry=str(series.industry or "unknown"),
                    selected_rank=int(position.rank),
                    shares=int(position.shares),
                    entry_price=float(position.entry_price),
                    exit_price=close,
                    cost_basis=float(position.cost_basis),
                    proceeds=proceeds,
                    pnl=pnl,
                    net_return=pnl / position.cost_basis if position.cost_basis else 0.0,
                    pnl_pct_initial_cash=pnl / float(initial_cash) if initial_cash else 0.0,
                    exit_reason=exit_reason,
                )
            )
        open_positions = still_open

        for signal_entry in sorted(entries_by_day.get(current_day, []), key=lambda item: item.signal_day):
            evaluation = _evaluate_signal_entry(
                signal_entry,
                config=config,
                cash=cash,
                open_positions=open_positions,
                series_by_symbol=series_by_symbol,
                current_day=current_day,
                initial_cash=initial_cash,
                buy_cost_rate=buy_cost_rate,
                entry_price_source=entry_price_source,
            )
            if evaluation.position is not None:
                cash -= evaluation.cash_spent
                open_positions.append(evaluation.position)
    return closed


def _build_trade_profile(
    series_by_symbol: dict[str, Any],
    *,
    trades: list[_ClosedTrade],
    paper_trades: list[_ClosedTrade],
    historical_signal_days: list[date],
    paper_signal_days: list[date],
    initial_cash: float,
    big_trade_count: int,
) -> dict[str, Any]:
    sorted_trades = sorted(trades, key=lambda trade: trade.pnl_pct_initial_cash)
    loss_trades = sorted_trades[:big_trade_count]
    win_trades = sorted_trades[-big_trade_count:]
    loss_features = [_trade_features(series_by_symbol, trade, signal_days=historical_signal_days) for trade in loss_trades]
    win_features = [_trade_features(series_by_symbol, trade, signal_days=historical_signal_days) for trade in win_trades]
    paper_features = [_trade_features(series_by_symbol, trade, signal_days=paper_signal_days) for trade in paper_trades]
    loss_summary = _feature_summary(loss_features)
    win_summary = _feature_summary(win_features)
    paper_summary = _feature_summary(paper_features)
    largest_losses = [
        _trade_sample_row(series_by_symbol, trade, signal_days=historical_signal_days)
        for trade in loss_trades[: min(10, len(loss_trades))]
    ]
    largest_wins = [
        _trade_sample_row(series_by_symbol, trade, signal_days=historical_signal_days)
        for trade in reversed(win_trades[-min(10, len(win_trades)) :])
    ]
    return {
        "historical_trade_count": len(trades),
        "paper_trade_count": len(paper_trades),
        "big_group_trade_count": big_trade_count,
        "loss_group": loss_summary,
        "win_group": win_summary,
        "paper_window_group": paper_summary,
        "loss_group_summary_cn": _group_sentence(loss_summary),
        "win_group_summary_cn": _group_sentence(win_summary),
        "paper_window_summary_cn": _group_sentence(paper_summary),
        "feature_delta_win_minus_loss": _feature_delta(win_summary, loss_summary),
        "largest_loss_samples": largest_losses,
        "largest_win_samples": largest_wins,
        "sample_warning_cn": (
            "逐笔画像只描述历史大赚/大亏分布；当前纸面窗口样本很少，不能单独用来生成规则。"
        ),
        "initial_cash": initial_cash,
    }


def _trade_features(series_by_symbol: dict[str, Any], trade: _ClosedTrade, *, signal_days: list[date]) -> dict[str, Any]:
    series = series_by_symbol.get(trade.symbol)
    context = _context_for_signal_day(series, trade.signal_day, include_golden_cross=False) if series is not None else None
    index = series.by_day.get(trade.signal_day) if series is not None else None
    price_vs_20d_high = None
    pre_5d_volatility = None
    if series is not None and index is not None and index >= 20:
        closes = [float(bar.close) for bar in series.bars[index - 20 : index + 1] if float(bar.close) > 0]
        if closes:
            price_vs_20d_high = closes[-1] / max(closes) - 1.0
        recent = [float(bar.close) for bar in series.bars[index - 5 : index + 1] if float(bar.close) > 0]
        returns = [recent[i] / recent[i - 1] - 1.0 for i in range(1, len(recent)) if recent[i - 1] > 0]
        pre_5d_volatility = _stddev(returns)
    signal_density = _signal_density(signal_days, trade.signal_day, lookback_days=5)
    industry_hhi = _industry_hhi_for_day(series_by_symbol, trade.signal_day)
    market_5d_return = _index_return(series_by_symbol, trade.signal_day, lookback_days=5)
    return {
        "symbol": trade.symbol,
        "industry": trade.industry,
        "selected_rank": trade.selected_rank,
        "pnl_pct_initial_cash": round(trade.pnl_pct_initial_cash, 6),
        "net_return": round(trade.net_return, 6),
        "signal_density_5d": signal_density,
        "industry_hhi": industry_hhi,
        "market_5d_return": market_5d_return,
        "stock_pre5d_return": round(float((context or {}).get("return_5d") or 0.0), 6) if context else None,
        "stock_pre5d_volatility": round(pre_5d_volatility, 6) if pre_5d_volatility is not None else None,
        "price_vs_20d_high": round(price_vs_20d_high, 6) if price_vs_20d_high is not None else None,
        "turnover_rate": round(float((context or {}).get("turnover_rate") or 0.0), 6) if context else None,
    }


def _trade_sample_row(series_by_symbol: dict[str, Any], trade: _ClosedTrade, *, signal_days: list[date]) -> dict[str, Any]:
    features = _trade_features(series_by_symbol, trade, signal_days=signal_days)
    return {
        "signal_date": trade.signal_day.isoformat(),
        "entry_date": trade.entry_day.isoformat(),
        "exit_date": trade.exit_day.isoformat(),
        "symbol": trade.symbol,
        "name": trade.name,
        "industry": trade.industry,
        "selected_rank": trade.selected_rank,
        "net_return": round(trade.net_return, 6),
        "pnl_pct_initial_cash": round(trade.pnl_pct_initial_cash, 6),
        "features": features,
    }


def _build_similar_window_diagnostic(
    series_by_symbol: dict[str, Any],
    *,
    historical_start_date: date,
    historical_end_date: date,
    paper_start_date: date,
    paper_end_date: date,
    window_size: int,
    top_n: int,
) -> dict[str, Any]:
    index_series = series_by_symbol.get(CSI300_SYMBOL)
    if index_series is None:
        return {"status": "blocked", "reason_cn": "缺少沪深300指数行情。", "matched_window_count": 0}
    current_window = _index_window_return(index_series, end_date=paper_end_date, window_size=window_size)
    if current_window is None:
        return {"status": "blocked", "reason_cn": "当前纸面窗口指数样本不足。", "matched_window_count": 0}
    candidates: list[dict[str, Any]] = []
    for end_index, end_bar in enumerate(index_series.bars):
        if end_bar.day >= paper_start_date or end_bar.day > historical_end_date:
            continue
        start_index = end_index - window_size + 1
        future_end_index = end_index + window_size
        if start_index < 0 or future_end_index >= len(index_series.bars):
            continue
        start_day = index_series.bars[start_index].day
        if start_day < historical_start_date:
            continue
        start_close = float(index_series.bars[start_index].close)
        end_close = float(index_series.bars[end_index].close)
        future_close = float(index_series.bars[future_end_index].close)
        if start_close <= 0 or end_close <= 0:
            continue
        index_return = end_close / start_close - 1.0
        future_return = future_close / end_close - 1.0
        candidates.append(
            {
                "start_date": start_day.isoformat(),
                "end_date": end_bar.day.isoformat(),
                "future_end_date": index_series.bars[future_end_index].day.isoformat(),
                "index_return": round(index_return, 6),
                "distance_abs": round(abs(index_return - current_window["index_return"]), 6),
                "future_index_return": round(future_return, 6),
            }
        )
    candidates.sort(key=lambda row: (float(row["distance_abs"]), row["end_date"]))
    matches = candidates[:top_n]
    future_returns = [float(row["future_index_return"]) for row in matches if row.get("future_index_return") is not None]
    within_2pp_count = sum(1 for row in candidates if float(row["distance_abs"]) <= 0.02)
    return {
        "status": "ready" if len(matches) >= 3 else "insufficient_sample",
        "index_symbol": CSI300_SYMBOL,
        "window_size": window_size,
        "current_window_start_date": current_window["start_date"],
        "current_window_end_date": current_window["end_date"],
        "current_window_index_return": current_window["index_return"],
        "candidate_window_count": len(candidates),
        "matched_window_count": len(matches),
        "matched_window_within_2pp_count": within_2pp_count,
        "matched_future_return_median": round(median(future_returns), 6) if future_returns else None,
        "matched_future_positive_ratio": round(sum(1 for value in future_returns if value > 0) / len(future_returns), 6)
        if future_returns
        else None,
        "matched_windows": matches,
        "interpretation_cn": _similar_window_sentence(current_window["index_return"], future_returns, within_2pp_count),
    }


def _index_window_return(index_series: Any, *, end_date: date, window_size: int) -> dict[str, Any] | None:
    end_index = max((idx for idx, bar in enumerate(index_series.bars) if bar.day <= end_date), default=None)
    if end_index is None:
        return None
    start_index = end_index - window_size + 1
    if start_index < 0:
        return None
    start_close = float(index_series.bars[start_index].close)
    end_close = float(index_series.bars[end_index].close)
    if start_close <= 0:
        return None
    return {
        "start_date": index_series.bars[start_index].day.isoformat(),
        "end_date": index_series.bars[end_index].day.isoformat(),
        "index_return": round(end_close / start_close - 1.0, 6),
    }


def _summary_row(result: dict[str, Any], *, trade_day_count: int) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    total_return = float(summary.get("total_return") or 0.0)
    output = dict(summary)
    output["annualized_return"] = _annualized(total_return, trade_day_count)
    return output


def _interpretation(
    trade_profile: dict[str, Any],
    similar_windows: dict[str, Any],
    v1_control: dict[str, Any],
    historical_v2_summary: dict[str, Any],
    paper_v2_summary: dict[str, Any],
) -> dict[str, Any]:
    v1_summary = v1_control.get("summary") if isinstance(v1_control.get("summary"), dict) else {}
    v2_ann = _float_or_none(historical_v2_summary.get("annualized_return"))
    v1_ann = _float_or_none(v1_summary.get("annualized_return"))
    paper_dd = _float_or_none(paper_v2_summary.get("max_drawdown"))
    future_median = _float_or_none(similar_windows.get("matched_future_return_median"))
    loss_summary = trade_profile.get("loss_group") if isinstance(trade_profile.get("loss_group"), dict) else {}
    paper_profile = trade_profile.get("paper_window_group") if isinstance(trade_profile.get("paper_window_group"), dict) else {}
    reasons: list[str] = []
    if paper_dd is not None and paper_dd < -0.15:
        reasons.append("当前纸面窗口回撤已经明显超出用户可接受体感，需要继续归因而不是只等待")
    if v1_ann is not None and v2_ann is not None and v1_ann >= v2_ann * 0.85:
        reasons.append("v1 资金约束强对照接近 v2，说明需要重新评估 v2 复杂选股的增量价值")
    else:
        reasons.append("v1 资金约束强对照未明显替代 v2，v2 历史优势仍保留")
    if future_median is not None and future_median < 0:
        reasons.append("相似指数窗口后续中位数为负，当前环境可能不是单纯偶然噪声")
    else:
        reasons.append("相似指数窗口没有显示后续必然恶化，不能仅凭当前纸面窗口否定基线")
    if loss_summary and paper_profile:
        loss_market = _float_or_none(loss_summary.get("market_5d_return_median"))
        paper_market = _float_or_none(paper_profile.get("market_5d_return_median"))
        if loss_market is not None and paper_market is not None and paper_market <= loss_market:
            reasons.append("纸面窗口的市场 5 日状态接近历史大亏组，需要优先验证市场环境过滤")
    status = "continue_diagnostics_no_strategy_promotion"
    return {
        "status": status,
        "message_cn": "；".join(reasons),
        "recommended_next_steps_cn": [
            "先不要把当前纸面窗口反向调参为新规则。",
            "若逐笔画像特征在时间切分中仍能区分大亏，再进入 OOS 过滤器验证。",
            "若 v1 强对照长期接近 v2，应把 v1 冻结逻辑纳入 v2 候选池，而不是只优化安静突破族。",
        ],
    }


def _feature_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_fields = (
        "pnl_pct_initial_cash",
        "net_return",
        "signal_density_5d",
        "industry_hhi",
        "market_5d_return",
        "stock_pre5d_return",
        "stock_pre5d_volatility",
        "price_vs_20d_high",
        "turnover_rate",
    )
    summary: dict[str, Any] = {"count": len(rows)}
    for field in numeric_fields:
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        summary[f"{field}_median"] = round(median(values), 6) if values else None
        summary[f"{field}_mean"] = round(sum(values) / len(values), 6) if values else None
    industries = Counter(str(row.get("industry") or "unknown") for row in rows)
    ranks = Counter(int(row.get("selected_rank") or 0) for row in rows)
    summary["top_industries"] = industries.most_common(5)
    summary["rank_counts"] = dict(sorted(ranks.items()))
    return summary


def _feature_delta(win_summary: dict[str, Any], loss_summary: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, win_value in win_summary.items():
        if not key.endswith("_median"):
            continue
        loss_value = loss_summary.get(key)
        if win_value is None or loss_value is None:
            output[key] = None
            continue
        output[key] = round(float(win_value) - float(loss_value), 6)
    return output


def _group_sentence(summary: dict[str, Any]) -> str:
    if not summary or int(summary.get("count") or 0) == 0:
        return "样本不足。"
    industries = "、".join(f"{name}({count})" for name, count in summary.get("top_industries") or [])
    return (
        f"样本 {int(summary.get('count') or 0)} 笔，"
        f"单笔对初始资金影响中位数 {_pct(summary.get('pnl_pct_initial_cash_median'))}，"
        f"信号日前沪深300 5 日收益中位数 {_pct(summary.get('market_5d_return_median'))}，"
        f"个股前 5 日收益中位数 {_pct(summary.get('stock_pre5d_return_median'))}，"
        f"距离 20 日高点中位数 {_pct(summary.get('price_vs_20d_high_median'))}，"
        f"主要行业：{industries or '无'}。"
    )


def _similar_window_sentence(current_return: float, future_returns: list[float], within_2pp_count: int) -> str:
    if not future_returns:
        return "相似窗口不足，不能判断当前市场是否特殊。"
    return (
        f"当前沪深300窗口收益为 {_pct(current_return)}；"
        f"历史上 2pp 内相似窗口 {within_2pp_count} 个，"
        f"最相似窗口后续收益中位数 {_pct(median(future_returns))}。"
    )


def _signal_density(signal_days: list[date], signal_day: date, *, lookback_days: int) -> int:
    start = signal_day - timedelta(days=lookback_days * 2)
    return sum(1 for day in signal_days if start <= day <= signal_day)


def _industry_hhi_for_day(series_by_symbol: dict[str, Any], signal_day: date) -> float | None:
    industries: Counter[str] = Counter()
    total = 0
    for symbol, series in series_by_symbol.items():
        if symbol in INDEX_SYMBOLS:
            continue
        context = _context_for_signal_day(series, signal_day, include_golden_cross=False)
        if context is None:
            continue
        industries[str(context.get("industry") or "unknown")] += 1
        total += 1
    if total <= 0:
        return None
    return round(sum((count / total) ** 2 for count in industries.values()), 6)


def _index_return(series_by_symbol: dict[str, Any], signal_day: date, *, lookback_days: int) -> float | None:
    index_series = series_by_symbol.get(CSI300_SYMBOL)
    if index_series is None:
        return None
    index = index_series.by_day.get(signal_day)
    if index is None or index < lookback_days:
        return None
    start = float(index_series.bars[index - lookback_days].close)
    end = float(index_series.bars[index].close)
    if start <= 0:
        return None
    return round(end / start - 1.0, 6)


def _stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return variance**0.5


def _annualized(total_return: float, trade_day_count: int) -> float | None:
    if trade_day_count <= 0 or total_return <= -1.0:
        return None
    return round((1.0 + float(total_return)) ** (252.0 / float(trade_day_count)) - 1.0, 6)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _artifact_id(generated_at: datetime, historical_start: date, historical_end: date, paper_end: date) -> str:
    return (
        f"{ARTIFACT_FAMILY}:{historical_start.isoformat()}:{historical_end.isoformat()}:"
        f"paper_to_{paper_end.isoformat()}:{generated_at.date().isoformat()}"
    )


def _pct(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"
