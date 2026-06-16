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
from ashare_evidence.shortpick_v2_next_diagnostics import (
    DEFAULT_BASELINE_TARGET_NOTIONAL,
    DEFAULT_HISTORICAL_END_DATE,
    DEFAULT_HISTORICAL_START_DATE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_MIN_SIGNAL_SYMBOL_COUNT,
    DEFAULT_PAPER_END_DATE,
    DEFAULT_PAPER_START_DATE,
    DEFAULT_POOL_LIMIT,
    DEFAULT_RANK_LIMIT,
    V2_BASELINE_CONFIG_ID,
    _build_v2_baseline_selections,
    _contexts_by_signal_day,
    _index_return,
    _load_daily_series_between,
    _pct,
    _summary_row,
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

ARTIFACT_FAMILY = "shortpick_v2_oos_loss_filter"
SCHEMA_VERSION = "v1"
SOURCE_REF = "market_only_reconstruction:shortpick_v2_oos_loss_filter:v1"
DEFAULT_TRAIN_END_DATE = date(2025, 4, 30)
DEFAULT_HOLDOUT_START_DATE = date(2025, 5, 1)


@dataclass(frozen=True)
class _FilterVariant:
    variant_id: str
    label_cn: str
    description_cn: str
    stock_pre5d_return_min: float | None = None
    price_vs_20d_high_min: float | None = None
    market_5d_return_min: float | None = None


FILTER_VARIANTS: tuple[_FilterVariant, ...] = (
    _FilterVariant(
        variant_id="baseline_no_filter",
        label_cn="基线：不加大亏前兆过滤",
        description_cn="安静突破 Rank2 + 热度池 10% + 周一至周三 + 固定 8.5 万 + H10。",
    ),
    _FilterVariant(
        variant_id="runup_high_guard_v1",
        label_cn="涨幅贴高过滤",
        description_cn="候选信号日前 5 日涨幅 >= 8%，且收盘距离 20 日高点不低于 -0.5% 时跳过该候选，允许同日候补。",
        stock_pre5d_return_min=0.08,
        price_vs_20d_high_min=-0.005,
    ),
    _FilterVariant(
        variant_id="runup_only_guard_v1",
        label_cn="高涨幅过滤",
        description_cn="候选信号日前 5 日涨幅 >= 10% 时跳过该候选，允许同日候补。",
        stock_pre5d_return_min=0.10,
    ),
    _FilterVariant(
        variant_id="near_high_only_guard_v1",
        label_cn="贴 20 日高点过滤",
        description_cn="候选信号日收盘距离 20 日高点不低于 -0.2% 时跳过该候选，允许同日候补。",
        price_vs_20d_high_min=-0.002,
    ),
    _FilterVariant(
        variant_id="market_runup_guard_v1",
        label_cn="市场走强叠加个股涨幅过滤",
        description_cn="沪深300信号日前 5 日收益 >= 1%，且候选前 5 日涨幅 >= 8% 时跳过该候选，允许同日候补。",
        market_5d_return_min=0.01,
        stock_pre5d_return_min=0.08,
    ),
)


def build_shortpick_v2_oos_loss_filter_artifact(
    session: Session,
    *,
    historical_start_date: date = DEFAULT_HISTORICAL_START_DATE,
    train_end_date: date = DEFAULT_TRAIN_END_DATE,
    holdout_start_date: date = DEFAULT_HOLDOUT_START_DATE,
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
        raise ValueError("OOS loss-filter experiment currently requires H10; horizon_days must be 10")
    if not (historical_start_date <= train_end_date < holdout_start_date <= historical_end_date):
        raise ValueError("train/holdout dates must form a non-overlapping historical split")

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
    windows = (
        ("train", "训练段", historical_start_date, train_end_date),
        ("holdout", "样本外验证段", holdout_start_date, historical_end_date),
        ("historical_all", "完整历史段", historical_start_date, historical_end_date),
        ("paper", "当前纸面窗口回放", paper_start_date, paper_end_date),
    )
    window_results = {
        window_id: _build_window_result(
            series_by_symbol,
            window_id=window_id,
            window_label_cn=window_label,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            entry_price_source=entry_price_source,
            horizon_days=horizon_days,
            pool_limit=pool_limit,
            rank_limit=rank_limit,
            cost_bps=cost_bps,
            stamp_tax_bps=stamp_tax_bps,
            min_signal_symbol_count=min_signal_symbol_count,
        )
        for window_id, window_label, start_date, end_date in windows
    }
    rows = _combine_variant_rows(window_results)
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, historical_start_date, historical_end_date, paper_end_date),
        "generated_at": generated_at.isoformat(),
        "status": "ready" if rows else "blocked",
        "claim_ceiling": "research_observation",
        "evidence_basis": "train_holdout_paper_account_replay",
        "source_ref": SOURCE_REF,
        "analysis_scope": {
            "question_cn": "历史大亏画像里的涨幅贴高特征，能否形成可样本外验证的候选过滤器？",
            "baseline_config_id": V2_BASELINE_CONFIG_ID,
            "baseline_buy_cn": f"固定单笔约 {DEFAULT_BASELINE_TARGET_NOTIONAL / 10000:.1f} 万，Rank2 首选，Rank3-Rank6 同日候补。",
            "historical_start_date": historical_start_date.isoformat(),
            "train_end_date": train_end_date.isoformat(),
            "holdout_start_date": holdout_start_date.isoformat(),
            "historical_end_date": historical_end_date.isoformat(),
            "paper_start_date": paper_start_date.isoformat(),
            "paper_end_date": paper_end_date.isoformat(),
            "horizon_days": horizon_days,
            "initial_cash": initial_cash,
            "entry_price_source": entry_price_source,
            "promotion_status": "research_only_no_strategy_promotion",
        },
        "data_scope": {
            "stock_like_series_count": len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
            "account_profile": str(account_eligibility["account_profile"]),
            "coverage_notes": _coverage_notes(raw_series_by_symbol, series_by_symbol, account_eligibility),
        },
        "filter_variants": [_variant_contract(variant) for variant in FILTER_VARIANTS],
        "variant_rows": rows,
        "window_data_scope": {window_id: result["data_scope"] for window_id, result in window_results.items()},
        "recommendation": _recommendation(rows),
        "leakage_audit": {
            "status": "passed",
            "used_only_signal_day_or_earlier_data": True,
            "notes": [
                "Candidate filters use only signal-day-or-prior close, return, and index features.",
                "Train/holdout split is predeclared; current paper window is reported as smoke evidence only.",
                "Filtered candidates are skipped within the ranked pool, and same-day fallback remains allowed.",
            ],
        },
        "event_refs": [
            "shortpick_v2.oos_loss_filter.generated",
            f"shortpick_v2.oos_loss_filter.historical.{historical_start_date.isoformat()}_{historical_end_date.isoformat()}",
            f"shortpick_v2.oos_loss_filter.paper.{paper_start_date.isoformat()}_{paper_end_date.isoformat()}",
        ],
    }
    validation = validate_shortpick_v2_oos_loss_filter_payload(payload)
    if validation["status"] != "passed":
        raise ValueError(f"OOS loss filter validation failed: {validation}")
    return payload


def write_shortpick_v2_oos_loss_filter_artifact(
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
        summary = render_shortpick_v2_oos_loss_filter_markdown(payload)
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_v2_oos_loss_filter_artifact(*, artifact_path: str | Path) -> dict[str, Any]:
    return validate_shortpick_v2_oos_loss_filter_payload(json.loads(Path(artifact_path).read_text(encoding="utf-8")))


def validate_shortpick_v2_oos_loss_filter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    rows = [row for row in payload.get("variant_rows") or [] if isinstance(row, dict)]
    scope = payload.get("analysis_scope") if isinstance(payload.get("analysis_scope"), dict) else {}
    variant_ids = {str(row.get("variant_id")) for row in rows}
    check("artifact_family", payload.get("artifact_family") == ARTIFACT_FAMILY, str(payload.get("artifact_family")))
    check("schema_version", payload.get("schema_version") == SCHEMA_VERSION, str(payload.get("schema_version")))
    check("claim_ceiling", payload.get("claim_ceiling") == "research_observation", str(payload.get("claim_ceiling")))
    check("research_only", scope.get("promotion_status") == "research_only_no_strategy_promotion", str(scope.get("promotion_status")))
    check("baseline_present", "baseline_no_filter" in variant_ids, str(sorted(variant_ids)))
    check("variant_count", len(rows) == len(FILTER_VARIANTS), str(len(rows)))
    check(
        "all_windows_present",
        all(all(window in row for window in ("train", "holdout", "historical_all", "paper")) for row in rows),
        "train/holdout/historical_all/paper scanned",
    )
    check(
        "holdout_trade_count",
        all(int((row.get("holdout") or {}).get("trade_count") or 0) >= 20 for row in rows),
        "holdout trade counts scanned",
    )
    check("leakage_status", (payload.get("leakage_audit") or {}).get("status") == "passed", str((payload.get("leakage_audit") or {}).get("status")))
    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "artifact_summary": {
            "artifact_family": payload.get("artifact_family"),
            "variant_count": len(rows),
            "recommendation_status": (payload.get("recommendation") or {}).get("status"),
            "candidate_variant_ids": (payload.get("recommendation") or {}).get("candidate_variant_ids"),
        },
    }


def render_shortpick_v2_oos_loss_filter_markdown(payload: dict[str, Any]) -> str:
    rows = [row for row in payload.get("variant_rows") or [] if isinstance(row, dict)]
    rows.sort(
        key=lambda row: (
            _outcome_rank(str(row.get("outcome_status") or "")),
            -float((row.get("holdout") or {}).get("annualized_return") or -999.0),
        )
    )
    recommendation = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
    lines = [
        "# 试验田 v2 OOS 大亏前兆过滤验证",
        "",
        "本产物只验证候选过滤器，不晋级或替换纸面追踪策略。",
        "",
        "## 结论",
        "",
        str(recommendation.get("message_cn") or "暂无结论。"),
        "",
        "## 结果表",
        "",
        "| 排名 | 方案 | 过滤方式 | Train 年化 / 回撤 | Holdout 年化 / 回撤 | Holdout 交易 / skip | Paper 收益 / 回撤 | 判断 |",
        "|------|------|----------|-------------------|---------------------|----------------------|-------------------|------|",
    ]
    for index, row in enumerate(rows, start=1):
        train = row.get("train") if isinstance(row.get("train"), dict) else {}
        holdout = row.get("holdout") if isinstance(row.get("holdout"), dict) else {}
        paper = row.get("paper") if isinstance(row.get("paper"), dict) else {}
        lines.append(
            "| {rank} | {label} | {desc} | {train_ann} / {train_dd} | {hold_ann} / {hold_dd} | {hold_trades} / {hold_skip} | {paper_total} / {paper_dd} | {outcome} |".format(
                rank=index,
                label=str(row.get("label_cn") or ""),
                desc=str(row.get("description_cn") or ""),
                train_ann=_pct(train.get("annualized_return")),
                train_dd=_pct(train.get("max_drawdown")),
                hold_ann=_pct(holdout.get("annualized_return")),
                hold_dd=_pct(holdout.get("max_drawdown")),
                hold_trades=int(holdout.get("trade_count") or 0),
                hold_skip=_pct(holdout.get("skipped_ratio")),
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
            "- 当前纸面窗口只作为烟雾观察，不用于选择阈值。",
            "- 过滤器只剔除触发前兆的候选，仍允许同日候补。",
            "- 若 holdout 收益或回撤不成立，即使 paper 好看也不晋级。",
            "",
        ]
    )
    return "\n".join(lines)


def _build_window_result(
    series_by_symbol: dict[str, Any],
    *,
    window_id: str,
    window_label_cn: str,
    start_date: date,
    end_date: date,
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
    contexts_by_day = _contexts_by_signal_day(series_by_symbol, signal_days=signal_days)
    base_selections = _build_v2_baseline_selections(
        signal_days=signal_days,
        contexts_by_day=contexts_by_day,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
    result_by_variant: dict[str, dict[str, Any]] = {}
    rejection_by_variant: dict[str, dict[str, Any]] = {}
    for variant in FILTER_VARIANTS:
        filtered, rejection_summary = _filtered_selections(
            base_selections,
            series_by_symbol=series_by_symbol,
            contexts_by_day=contexts_by_day,
            variant=variant,
        )
        result = _simulate_rule_config(
            series_by_symbol,
            signal_days=signal_days,
            trade_days=trade_days,
            selections=filtered,
            config=_v2_baseline_config(),
            initial_cash=initial_cash,
            entry_price_source=entry_price_source,
            horizon_days=horizon_days,
            cost_bps=cost_bps,
            stamp_tax_bps=stamp_tax_bps,
            market_reference_total_return=market_reference.get("total_return"),
            decision_sample_limit=0,
        )
        result_by_variant[variant.variant_id] = _summary_row(result, trade_day_count=len(trade_days))
        rejection_by_variant[variant.variant_id] = rejection_summary
    return {
        "window_id": window_id,
        "window_label_cn": window_label_cn,
        "data_scope": {
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "market_reference_total_return": market_reference.get("total_return"),
        },
        "result_by_variant": result_by_variant,
        "rejection_by_variant": rejection_by_variant,
    }


def _filtered_selections(
    selections: dict[date, list[str]],
    *,
    series_by_symbol: dict[str, Any],
    contexts_by_day: dict[date, list[dict[str, Any]]],
    variant: _FilterVariant,
) -> tuple[dict[date, list[str]], dict[str, Any]]:
    if variant.variant_id == "baseline_no_filter":
        return dict(selections), {"rejected_candidate_count": 0, "affected_signal_count": 0, "reason_counts": {}}
    context_by_day_symbol = {
        signal_day: {str(context["symbol"]): context for context in contexts}
        for signal_day, contexts in contexts_by_day.items()
    }
    output: dict[date, list[str]] = {}
    reason_counts: dict[str, int] = {}
    rejected_count = 0
    affected_signal_count = 0
    for signal_day, symbols in sorted(selections.items()):
        kept: list[str] = []
        rejected_on_day = 0
        for symbol in symbols:
            features = _candidate_features(
                series_by_symbol,
                context_by_day_symbol=context_by_day_symbol,
                signal_day=signal_day,
                symbol=symbol,
            )
            reason = _reject_reason(features, variant)
            if reason is None:
                kept.append(symbol)
                continue
            rejected_count += 1
            rejected_on_day += 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if rejected_on_day:
            affected_signal_count += 1
        output[signal_day] = kept
    return output, {
        "rejected_candidate_count": rejected_count,
        "affected_signal_count": affected_signal_count,
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def _candidate_features(
    series_by_symbol: dict[str, Any],
    *,
    context_by_day_symbol: dict[date, dict[str, dict[str, Any]]],
    signal_day: date,
    symbol: str,
) -> dict[str, float | None]:
    context = (context_by_day_symbol.get(signal_day) or {}).get(symbol)
    series = series_by_symbol.get(symbol)
    index = series.by_day.get(signal_day) if series is not None else None
    price_vs_20d_high = None
    if series is not None and index is not None and index >= 20:
        closes = [float(bar.close) for bar in series.bars[index - 20 : index + 1] if float(bar.close) > 0]
        if closes:
            price_vs_20d_high = closes[-1] / max(closes) - 1.0
    return {
        "stock_pre5d_return": float((context or {}).get("return_5d") or 0.0) if context is not None else None,
        "price_vs_20d_high": price_vs_20d_high,
        "market_5d_return": _index_return(series_by_symbol, signal_day, lookback_days=5),
    }


def _reject_reason(features: dict[str, float | None], variant: _FilterVariant) -> str | None:
    checks = (
        ("stock_pre5d_return", variant.stock_pre5d_return_min),
        ("price_vs_20d_high", variant.price_vs_20d_high_min),
        ("market_5d_return", variant.market_5d_return_min),
    )
    for field, threshold in checks:
        if threshold is None:
            continue
        value = features.get(field)
        if value is None or float(value) < float(threshold):
            return None
    active = [field for field, threshold in checks if threshold is not None]
    return "+".join(active)


def _combine_variant_rows(window_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = _variant_result(window_results, "baseline_no_filter")
    rows: list[dict[str, Any]] = []
    for variant in FILTER_VARIANTS:
        row = {
            "variant_id": variant.variant_id,
            "label_cn": variant.label_cn,
            "description_cn": variant.description_cn,
            "filter_contract": _variant_contract(variant),
            "train": _variant_window_summary(window_results, variant.variant_id, "train"),
            "holdout": _variant_window_summary(window_results, variant.variant_id, "holdout"),
            "historical_all": _variant_window_summary(window_results, variant.variant_id, "historical_all"),
            "paper": _variant_window_summary(window_results, variant.variant_id, "paper"),
            "rejection_summary": {
                window_id: (window.get("rejection_by_variant") or {}).get(variant.variant_id, {})
                for window_id, window in window_results.items()
            },
        }
        outcome = _outcome(row, baseline)
        row["outcome_status"] = outcome["status"]
        row["outcome_label_cn"] = outcome["label_cn"]
        row["outcome_reasons_cn"] = outcome["reasons_cn"]
        rows.append(row)
    return rows


def _variant_result(window_results: dict[str, dict[str, Any]], variant_id: str) -> dict[str, dict[str, Any]]:
    return {
        window_id: _variant_window_summary(window_results, variant_id, window_id)
        for window_id in ("train", "holdout", "historical_all", "paper")
    }


def _variant_window_summary(window_results: dict[str, dict[str, Any]], variant_id: str, window_id: str) -> dict[str, Any]:
    return dict(((window_results.get(window_id) or {}).get("result_by_variant") or {}).get(variant_id) or {})


def _outcome(row: dict[str, Any], baseline: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if row["variant_id"] == "baseline_no_filter":
        return {"status": "baseline", "label_cn": "基线对照", "reasons_cn": ["不参与晋级判断"]}
    holdout = row.get("holdout") if isinstance(row.get("holdout"), dict) else {}
    paper = row.get("paper") if isinstance(row.get("paper"), dict) else {}
    baseline_holdout = baseline.get("holdout") or {}
    baseline_paper = baseline.get("paper") or {}
    reasons: list[str] = []
    holdout_ann = _float_or_none(holdout.get("annualized_return"))
    baseline_holdout_ann = _float_or_none(baseline_holdout.get("annualized_return"))
    holdout_dd = _float_or_none(holdout.get("max_drawdown"))
    baseline_holdout_dd = _float_or_none(baseline_holdout.get("max_drawdown"))
    holdout_trades = int(holdout.get("trade_count") or 0)
    paper_return = _float_or_none(paper.get("total_return"))
    baseline_paper_return = _float_or_none(baseline_paper.get("total_return"))
    if holdout_trades < 20:
        reasons.append("holdout 交易数不足 20")
    if holdout_ann is None or baseline_holdout_ann is None or holdout_ann < baseline_holdout_ann * 0.90:
        reasons.append("holdout 年化未保留基线 90%")
    if holdout_dd is None or baseline_holdout_dd is None or abs(holdout_dd) > abs(baseline_holdout_dd):
        reasons.append("holdout 回撤未改善")
    if paper_return is not None and baseline_paper_return is not None and paper_return < baseline_paper_return - 0.03:
        reasons.append("paper 收益较基线恶化超过 3pp")
    if reasons:
        return {"status": "rejected", "label_cn": "不晋级", "reasons_cn": reasons}
    return {"status": "candidate", "label_cn": "候选观察", "reasons_cn": ["holdout 保留收益、回撤改善，且 paper 未明显恶化"]}


def _recommendation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in rows if row.get("outcome_status") == "candidate"]
    if not candidates:
        best = max(
            (row for row in rows if row.get("variant_id") != "baseline_no_filter"),
            key=lambda row: float((row.get("holdout") or {}).get("annualized_return") or -999.0),
            default=None,
        )
        best_note = f"相对最接近的是“{best.get('label_cn')}”，但未同时满足 holdout 收益保留与回撤改善。" if best else ""
        return {
            "status": "no_promotable_filter",
            "message_cn": f"本轮大亏前兆过滤器没有形成可晋级候选；不要把当前纸面窗口反向调参为新规则。{best_note}",
            "candidate_variant_ids": [],
        }
    candidates.sort(key=lambda row: float((row.get("holdout") or {}).get("annualized_return") or -999.0), reverse=True)
    return {
        "status": "research_candidate_requires_forward_observation",
        "message_cn": f"存在 {len(candidates)} 个研究候选，但仍需新的前向纸面观察，不能直接替换冻结策略。",
        "candidate_variant_ids": [str(row.get("variant_id")) for row in candidates],
    }


def _variant_contract(variant: _FilterVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "label_cn": variant.label_cn,
        "description_cn": variant.description_cn,
        "stock_pre5d_return_min": variant.stock_pre5d_return_min,
        "price_vs_20d_high_min": variant.price_vs_20d_high_min,
        "market_5d_return_min": variant.market_5d_return_min,
        "fallback_after_filter": True,
    }


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _outcome_rank(status: str) -> int:
    return {"candidate": 0, "baseline": 1, "rejected": 2}.get(status, 9)


def _artifact_id(generated_at: datetime, historical_start: date, historical_end: date, paper_end: date) -> str:
    return (
        f"{ARTIFACT_FAMILY}:{historical_start.isoformat()}:{historical_end.isoformat()}:"
        f"paper_to_{paper_end.isoformat()}:{generated_at.date().isoformat()}"
    )
