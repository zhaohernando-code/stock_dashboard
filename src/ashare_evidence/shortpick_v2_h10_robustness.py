from __future__ import annotations

import json
from collections import Counter, defaultdict
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
    _load_daily_series,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    _eligible_signal_days,
    _exit_is_unfillable_limit_down,
    _max_drawdown,
    _trade_days,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
    ShortpickV2RuleConfig,
    _evaluate_signal_entry,
    _market_reference_summary,
    _nav_and_market_value,
    _prepare_signal_entries,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_BENCHMARK_CONFIG_IDS,
    SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_strategy_search import (
    CONTROL_CANDIDATE_SOURCE_ID,
    H10_QUIET_CANDIDATE_SOURCE_IDS,
    H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS,
    STRATEGY_SEARCH_BATCH_H10_QUIET,
    StrategySearchCandidateSource,
    build_h10_quiet_strategy_search_candidate_sources,
)

SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY = "shortpick_v2_h10_robustness_artifact"
SHORTPICK_V2_H10_ROBUSTNESS_SCHEMA_VERSION = "v1"
SHORTPICK_V2_H10_ROBUSTNESS_SOURCE_PLAN_REF = (
    "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-4-candidate-rule-selection"
)
SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY = "shortpick_v2_replay_artifact"
DEFAULT_MAX_HOLDOUT_CONFIGS = 10
DEFAULT_TOP_TRADE_LIMIT = 8
H10_QUIET_ROBUSTNESS_SOURCE_IDS = (
    *H10_QUIET_CANDIDATE_SOURCE_IDS,
    *H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS,
)
H10_QUIET_DIAGNOSTIC_CONFIG_IDS = (
    "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1",
)
BENCHMARK_ANALYSIS_ROLES = {"benchmark_control"}
DIAGNOSTIC_ANALYSIS_ROLE = "diagnostic_boundary"


@dataclass(frozen=True)
class _AnalysisConfig:
    config_id: str
    source_id: str
    role: str
    selection_rank: int | None
    rule_config: ShortpickV2RuleConfig
    source_replay_summary: dict[str, Any]


def build_shortpick_v2_h10_robustness_artifact(
    session: Session,
    *,
    replay_artifact_path: str | Path,
    selection_artifact_path: str | Path,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 10,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = 45,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    max_holdout_configs: int = DEFAULT_MAX_HOLDOUT_CONFIGS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
    if horizon_days != 10:
        raise ValueError("h10 robustness requires horizon_days=10")
    replay_path = Path(replay_artifact_path)
    selection_path = Path(selection_artifact_path)
    replay_artifact = json.loads(replay_path.read_text(encoding="utf-8"))
    selection_artifact = json.loads(selection_path.read_text(encoding="utf-8"))

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
    candidate_sources = build_h10_quiet_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    artifact = build_shortpick_v2_h10_robustness_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=candidate_sources,
        replay_artifact=replay_artifact,
        selection_artifact=selection_artifact,
        replay_artifact_path=replay_path,
        selection_artifact_path=selection_path,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        stock_like_series_count=len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        account_profile=str(account_eligibility["account_profile"]),
        coverage_notes=[
            "Read-only daily bars from the existing SQLite database; no refresh or model call performed.",
            (
                "Account eligibility filtered stock-like series from "
                f"{len([symbol for symbol in raw_series_by_symbol if symbol not in INDEX_SYMBOLS])} "
                f"to {len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])}."
            ),
        ],
        max_holdout_configs=max_holdout_configs,
        generated_at=generated_at,
    )
    return artifact


def build_shortpick_v2_h10_robustness_artifact_from_series(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    candidate_sources: tuple[StrategySearchCandidateSource, ...],
    replay_artifact: dict[str, Any],
    selection_artifact: dict[str, Any],
    replay_artifact_path: str | Path | None = None,
    selection_artifact_path: str | Path | None = None,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 10,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    stock_like_series_count: int | None = None,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    coverage_notes: list[str] | None = None,
    max_holdout_configs: int = DEFAULT_MAX_HOLDOUT_CONFIGS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    _validate_source_artifacts(replay_artifact, selection_artifact)
    generated_at = generated_at or datetime.now(UTC)
    signal_days = sorted(signal_days)
    trade_days = sorted(trade_days)
    source_by_id = {source.source_id: source for source in candidate_sources}
    configs = _analysis_configs(
        replay_artifact,
        selection_artifact,
        max_holdout_configs=max_holdout_configs,
    )
    full_results = [
        _build_config_robustness(
            series_by_symbol,
            signal_days=signal_days,
            trade_days=trade_days,
            source_by_id=source_by_id,
            analysis_config=config,
            initial_cash=initial_cash,
            entry_price_source=entry_price_source,
            horizon_days=horizon_days,
            cost_bps=cost_bps,
            stamp_tax_bps=stamp_tax_bps,
        )
        for config in configs
    ]
    market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
    period_reset_results = _period_reset_results(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        source_by_id=source_by_id,
        configs=configs,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    risk_flags = _risk_flags(
        full_results,
        period_reset_results=period_reset_results,
        market_reference_total_return=market_reference["total_return"],
    )
    consistency_status = (
        "passed"
        if all(result["source_replay_consistency"]["status"] == "passed" for result in full_results)
        else "failed"
    )
    stock_like_series_count = (
        stock_like_series_count
        if stock_like_series_count is not None
        else len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    )
    status = "ready" if configs and full_results else "blocked"
    if any(flag["severity"] == "high" for flag in risk_flags):
        recommendation_status = "not_ready_for_paper_tracking"
    elif status == "ready":
        recommendation_status = "candidate_requires_forward_tracking"
    else:
        recommendation_status = "blocked"
    return {
        "artifact_family": SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_H10_ROBUSTNESS_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, start_date, end_date, initial_cash),
        "generated_at": generated_at.isoformat(),
        "status": status,
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_robustness",
        "source_plan_ref": SHORTPICK_V2_H10_ROBUSTNESS_SOURCE_PLAN_REF,
        "source_replay_artifact": _source_artifact_ref(replay_artifact, replay_artifact_path),
        "source_selection_artifact": _source_artifact_ref(selection_artifact, selection_artifact_path),
        "analysis_scope": {
            "candidate_batch": STRATEGY_SEARCH_BATCH_H10_QUIET,
            "signal_date_from": signal_days[0].isoformat() if signal_days else None,
            "signal_date_to": signal_days[-1].isoformat() if signal_days else None,
            "signal_day_count": len(signal_days),
            "trade_day_count": len(trade_days),
            "stock_like_series_count": stock_like_series_count,
            "account_profile": account_profile,
            "initial_cash": initial_cash,
            "entry_price_source": entry_price_source,
            "horizon_days": horizon_days,
            "analyzed_config_count": len(configs),
            "market_reference": market_reference,
            "coverage_notes": coverage_notes
            or ["Synthetic or caller-supplied fixed daily bars; no refresh performed."],
        },
        "analysis_policy": {
            "period_reset_policy": (
                "Each period replays only signals from that period with account cash reset to the same initial cash; "
                "declared horizon exits may occur after the period end."
            ),
            "trade_contribution_policy": (
                "Trade contribution uses reconstructed account replay records. Winner-removal stress is a "
                "post-hoc PnL contribution proxy, not a resimulated account path."
            ),
            "promotion_policy": (
                "This artifact cannot promote paper tracking by itself; weak-period and concentration flags must be "
                "resolved or explicitly accepted by a later governed plan."
            ),
        },
        "analyzed_configs": full_results,
        "period_reset_results": period_reset_results,
        "parameter_stability": _parameter_stability(replay_artifact, selection_artifact),
        "risk_flags": risk_flags,
        "recommendation": {
            "status": recommendation_status,
            "notes": _recommendation_notes(recommendation_status, risk_flags),
        },
        "leakage_audit": {
            "status": consistency_status,
            "source_replay_consistency_status": consistency_status,
            "used_only_signal_day_or_earlier_selection_features": True,
            "execution_replay_uses_declared_entry_and_exit_bars_only": True,
            "notes": [
                "Candidate pools are reconstructed through the h10 quiet source builder.",
                "Buy, fallback, and skip decisions reuse the existing shortpick v2 replay evaluators.",
                "No delayed-entry action, discretionary reselection, database write, refresh, or model call is used.",
            ],
        },
        "event_refs": [
            "shortpick_v2.h10_quiet.robustness.generated",
            f"shortpick_v2.robustness.source_replay.{replay_artifact.get('artifact_id')}",
            f"shortpick_v2.robustness.source_selection.{selection_artifact.get('artifact_id')}",
        ],
    }


def write_shortpick_v2_h10_robustness_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _build_config_robustness(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    source_by_id: dict[str, StrategySearchCandidateSource],
    analysis_config: _AnalysisConfig,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    cost_bps: float,
    stamp_tax_bps: float,
) -> dict[str, Any]:
    source = source_by_id.get(analysis_config.source_id)
    if source is None:
        raise ValueError(f"candidate source missing for {analysis_config.source_id}")
    simulation = _simulate_config_with_records(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=source.selections,
        config=analysis_config.rule_config,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
    )
    consistency = _consistency_check(
        simulation["summary"],
        analysis_config.source_replay_summary,
    )
    return {
        "config_id": analysis_config.config_id,
        "role": analysis_config.role,
        "selection_rank": analysis_config.selection_rank,
        "source_id": analysis_config.source_id,
        "summary": simulation["summary"],
        "source_replay_consistency": consistency,
        "execution_mix": simulation["execution_mix"],
        "monthly_nav_returns": simulation["monthly_nav_returns"],
        "monthly_trade_contribution": simulation["monthly_trade_contribution"],
        "trade_contribution_stress": simulation["trade_contribution_stress"],
        "symbol_concentration": simulation["symbol_concentration"],
        "industry_concentration": simulation["industry_concentration"],
        "top_winning_trades": simulation["top_winning_trades"],
        "top_losing_trades": simulation["top_losing_trades"],
    }


def _simulate_config_with_records(
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
    active_days = sorted(set(trade_days) | set(entries_by_day))
    cash = float(initial_cash)
    buy_cost_rate = float(cost_bps) / 10000.0
    sell_cost_rate = float(cost_bps + stamp_tax_bps) / 10000.0
    open_positions: list[Any] = []
    position_trade_ids: dict[int, str] = {}
    trade_records: list[dict[str, Any]] = []
    decisions = list(pre_entry_decisions)
    reason_counts = Counter(pre_entry_counts)
    timeline: list[dict[str, Any]] = []
    total_buy_value = 0.0
    total_sell_value = 0.0
    blocked_exit_count = 0

    for current_day in active_days:
        still_open: list[Any] = []
        for position in open_positions:
            if current_day < position.planned_exit_day:
                still_open.append(position)
                continue
            series = series_by_symbol.get(position.symbol)
            current_index = series.by_day.get(current_day) if series is not None else None
            if series is None or current_index is None:
                still_open.append(position)
                continue
            if _exit_is_unfillable_limit_down(series, current_index):
                blocked_exit_count += 1
                reason_counts["blocked_exit:limit_down"] += 1
                still_open.append(position)
                continue
            close = float(series.bars[current_index].close)
            proceeds = position.shares * close * (1.0 - sell_cost_rate)
            cash += proceeds
            total_sell_value += proceeds
            reason_counts["exit:mechanical_horizon"] += 1
            trade_id = position_trade_ids.get(id(position))
            if trade_id is not None:
                _close_trade_record(
                    trade_records,
                    trade_id,
                    current_day=current_day,
                    exit_price=close,
                    proceeds=proceeds,
                )
        open_positions = still_open

        for signal_entry in sorted(entries_by_day.get(current_day, []), key=lambda item: item.signal_day):
            cash_before = cash
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
            reason_counts[f"action:{evaluation.action}"] += 1
            reason_counts[f"reason:{evaluation.reason}"] += 1
            for rejected_reason in evaluation.rejected_reasons:
                reason_counts[f"candidate_reject:{rejected_reason}"] += 1
            if evaluation.position is not None:
                cash -= evaluation.cash_spent
                total_buy_value += evaluation.cash_spent
                open_positions.append(evaluation.position)
                trade_id = f"{config.config_id}:{len(trade_records) + 1}"
                position_trade_ids[id(evaluation.position)] = trade_id
                trade_records.append(
                    _open_trade_record(
                        trade_id=trade_id,
                        signal_day=signal_entry.signal_day,
                        action=evaluation.action,
                        position=evaluation.position,
                        cash_spent=evaluation.cash_spent,
                        series_by_symbol=series_by_symbol,
                    )
                )
            decisions.append(
                {
                    "signal_date": signal_entry.signal_day.isoformat(),
                    "entry_date": current_day.isoformat(),
                    "action": evaluation.action,
                    "reason": evaluation.reason,
                    "selected_rank": evaluation.selected_rank,
                    "symbol": evaluation.symbol,
                    "cash_before": round(cash_before, 6),
                    "cash_after": round(cash, 6),
                    "quantity": evaluation.shares,
                }
            )

        nav, market_value = _nav_and_market_value(series_by_symbol, open_positions, current_day, cash)
        timeline.append(
            {
                "date": current_day.isoformat(),
                "nav": round(nav, 6),
                "cash": round(cash, 6),
                "market_value": round(market_value, 6),
                "open_position_count": len(open_positions),
            }
        )

    final_day = active_days[-1] if active_days else None
    if final_day is None:
        final_nav = float(initial_cash)
        final_market_value = 0.0
    else:
        final_nav, final_market_value = _nav_and_market_value(series_by_symbol, open_positions, final_day, cash)
        for position in open_positions:
            trade_id = position_trade_ids.get(id(position))
            if trade_id is None:
                continue
            mark_value = _position_mark_value(series_by_symbol, position, final_day)
            _mark_open_trade_record(
                trade_records,
                trade_id,
                mark_day=final_day,
                mark_value=mark_value,
            )
    market_reference = _market_reference_summary(series_by_symbol, signal_days=signal_days)
    market_reference_total_return = market_reference["total_return"]
    summary = _simulation_summary(
        signal_days=signal_days,
        trade_days=trade_days,
        decisions=decisions,
        timeline=timeline,
        open_positions=open_positions,
        initial_cash=initial_cash,
        cash=cash,
        final_nav=final_nav,
        final_market_value=final_market_value,
        blocked_exit_count=blocked_exit_count,
        total_buy_value=total_buy_value,
        total_sell_value=total_sell_value,
        market_reference_total_return=market_reference_total_return,
    )
    return {
        "summary": summary,
        "execution_mix": _execution_mix(decisions),
        "monthly_nav_returns": _nav_period_returns(timeline, "month"),
        "monthly_trade_contribution": _trade_period_contribution(trade_records, initial_cash, "month"),
        "trade_contribution_stress": _trade_contribution_stress(
            trade_records,
            initial_cash=initial_cash,
            final_nav=float(final_nav),
            trade_day_count=len(trade_days),
            market_reference_total_return=market_reference_total_return,
        ),
        "symbol_concentration": _concentration(trade_records, key="symbol", limit=10),
        "industry_concentration": _concentration(trade_records, key="industry", limit=10),
        "top_winning_trades": _top_trades(trade_records, reverse=True),
        "top_losing_trades": _top_trades(trade_records, reverse=False),
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def _simulation_summary(
    *,
    signal_days: list[date],
    trade_days: list[date],
    decisions: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    open_positions: list[Any],
    initial_cash: float,
    cash: float,
    final_nav: float,
    final_market_value: float,
    blocked_exit_count: int,
    total_buy_value: float,
    total_sell_value: float,
    market_reference_total_return: float | None,
) -> dict[str, Any]:
    buy_decisions = [decision for decision in decisions if decision["action"] in {"buy_primary", "buy_fallback"}]
    skip_count = sum(1 for decision in decisions if decision["action"] == "skip")
    fallback_trade_count = sum(1 for decision in decisions if decision["action"] == "buy_fallback")
    invested_ratios = [
        float(point["market_value"]) / float(point["nav"])
        for point in timeline
        if float(point["nav"]) > 0
    ]
    total_return = round(float(final_nav) / float(initial_cash) - 1.0, 6) if initial_cash else 0.0
    market_excess_total_return = (
        None if market_reference_total_return is None else round(total_return - market_reference_total_return, 6)
    )
    return {
        "signal_count": len(signal_days),
        "trade_count": len(buy_decisions),
        "skip_count": skip_count,
        "fallback_trade_count": fallback_trade_count,
        "final_nav": round(final_nav, 6),
        "total_return": total_return,
        "annualized_return": _annualized_return(total_return=total_return, trade_day_count=len(trade_days)),
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
        "total_buy_value": round(total_buy_value, 6),
        "total_sell_value": round(total_sell_value, 6),
        "skipped_ratio": round(skip_count / len(signal_days), 6) if signal_days else 0.0,
    }


def _open_trade_record(
    *,
    trade_id: str,
    signal_day: date,
    action: str,
    position: Any,
    cash_spent: float,
    series_by_symbol: dict[str, Any],
) -> dict[str, Any]:
    series = series_by_symbol.get(position.symbol)
    return {
        "trade_id": trade_id,
        "signal_date": signal_day.isoformat(),
        "entry_date": position.entry_day.isoformat(),
        "planned_exit_date": position.planned_exit_day.isoformat(),
        "action": action,
        "symbol": position.symbol,
        "industry": getattr(series, "industry", "unknown") if series is not None else "unknown",
        "rank": position.rank,
        "shares": position.shares,
        "entry_price": round(position.entry_price, 6),
        "cost_basis": round(cash_spent, 6),
        "status": "open",
        "exit_date": None,
        "exit_price": None,
        "proceeds": None,
        "net_pnl": None,
        "net_return": None,
        "contribution_day": None,
    }


def _close_trade_record(
    trade_records: list[dict[str, Any]],
    trade_id: str,
    *,
    current_day: date,
    exit_price: float,
    proceeds: float,
) -> None:
    for record in trade_records:
        if record["trade_id"] != trade_id:
            continue
        pnl = float(proceeds) - float(record["cost_basis"])
        record.update(
            {
                "status": "closed",
                "exit_date": current_day.isoformat(),
                "exit_price": round(exit_price, 6),
                "proceeds": round(proceeds, 6),
                "net_pnl": round(pnl, 6),
                "net_return": round(pnl / float(record["cost_basis"]), 6) if record["cost_basis"] else 0.0,
                "contribution_day": current_day.isoformat(),
            }
        )
        return


def _mark_open_trade_record(
    trade_records: list[dict[str, Any]],
    trade_id: str,
    *,
    mark_day: date,
    mark_value: float,
) -> None:
    for record in trade_records:
        if record["trade_id"] != trade_id:
            continue
        pnl = float(mark_value) - float(record["cost_basis"])
        record.update(
            {
                "status": "open_marked",
                "proceeds": round(mark_value, 6),
                "net_pnl": round(pnl, 6),
                "net_return": round(pnl / float(record["cost_basis"]), 6) if record["cost_basis"] else 0.0,
                "contribution_day": mark_day.isoformat(),
            }
        )
        return


def _position_mark_value(series_by_symbol: dict[str, Any], position: Any, mark_day: date) -> float:
    series = series_by_symbol.get(position.symbol)
    index = series.by_day.get(mark_day) if series is not None else None
    if series is None or index is None:
        return float(position.shares) * float(position.entry_price)
    return float(position.shares) * float(series.bars[index].close)


def _period_reset_results(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    source_by_id: dict[str, StrategySearchCandidateSource],
    configs: list[_AnalysisConfig],
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    cost_bps: float,
    stamp_tax_bps: float,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {"yearly": [], "quarterly": []}
    for period_type, ranges in (("yearly", _year_periods(signal_days)), ("quarterly", _quarter_periods(signal_days))):
        for period_id, period_start, period_end in ranges:
            period_signal_days = [day for day in signal_days if period_start <= day <= period_end]
            if not period_signal_days:
                continue
            period_trade_days = [
                day
                for day in trade_days
                if period_start <= day <= period_end + timedelta(days=max(30, horizon_days * 4))
            ]
            for config in configs:
                source = source_by_id.get(config.source_id)
                if source is None:
                    continue
                simulation = _simulate_config_with_records(
                    series_by_symbol,
                    signal_days=period_signal_days,
                    trade_days=period_trade_days,
                    selections=source.selections,
                    config=config.rule_config,
                    initial_cash=initial_cash,
                    entry_price_source=entry_price_source,
                    horizon_days=horizon_days,
                    cost_bps=cost_bps,
                    stamp_tax_bps=stamp_tax_bps,
                )
                summary = simulation["summary"]
                output[period_type].append(
                    {
                        "period_id": period_id,
                        "period_signal_date_from": period_signal_days[0].isoformat(),
                        "period_signal_date_to": period_signal_days[-1].isoformat(),
                        "config_id": config.config_id,
                        "role": config.role,
                        "summary": {
                            key: summary[key]
                            for key in (
                                "signal_count",
                                "trade_count",
                                "skip_count",
                                "fallback_trade_count",
                                "total_return",
                                "annualized_return",
                                "market_reference_total_return",
                                "market_excess_total_return",
                                "max_drawdown",
                                "turnover",
                                "skipped_ratio",
                            )
                        },
                    }
                )
    return output


def _analysis_configs(
    replay_artifact: dict[str, Any],
    selection_artifact: dict[str, Any],
    *,
    max_holdout_configs: int,
) -> list[_AnalysisConfig]:
    results_by_config = {
        str(result["config_id"]): result
        for result in replay_artifact.get("results") or []
        if isinstance(result, dict) and result.get("config_id")
    }
    rule_matrix = {
        str(row["config_id"]): row
        for row in replay_artifact.get("rule_matrix") or []
        if isinstance(row, dict) and row.get("config_id")
    }
    rows = []
    benchmark_rows = selection_artifact.get("benchmark_configs") or []
    rows.extend(benchmark_rows)
    if benchmark_rows:
        rows.extend(_diagnostic_config_rows(results_by_config))
    rows.extend(selection_artifact.get("selected_configs") or [])
    rows.extend((selection_artifact.get("holdout_configs") or [])[:max_holdout_configs])
    rows.extend(selection_artifact.get("baseline_configs") or [])
    configs: list[_AnalysisConfig] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        config_id = str(row.get("config_id") or "")
        if not config_id or config_id in seen:
            continue
        if config_id not in results_by_config or config_id not in rule_matrix:
            continue
        source_id = _source_id_for_config(config_id)
        configs.append(
            _AnalysisConfig(
                config_id=config_id,
                source_id=source_id,
                role=str(row.get("role") or "unknown"),
                selection_rank=_optional_int(row.get("selection_rank")),
                rule_config=_rule_config_from_artifact(rule_matrix[config_id]),
                source_replay_summary=dict((results_by_config[config_id].get("summary") or {})),
            )
        )
        seen.add(config_id)
    if not configs:
        raise ValueError("selection artifact does not provide analyzable benchmark, selected, holdout, or baseline configs")
    return configs


def _diagnostic_config_rows(results_by_config: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "config_id": config_id,
            "role": DIAGNOSTIC_ANALYSIS_ROLE,
            "selection_rank": None,
            "reason": "Diagnostic boundary row only; not eligible for paper-tracking promotion in h10 robustness.",
        }
        for config_id in H10_QUIET_DIAGNOSTIC_CONFIG_IDS
        if config_id in results_by_config
    ]


def _rule_config_from_artifact(row: dict[str, Any]) -> ShortpickV2RuleConfig:
    cash_policy = row.get("cash_policy") if isinstance(row.get("cash_policy"), dict) else {}
    fallback_policy = row.get("fallback_policy") if isinstance(row.get("fallback_policy"), dict) else {}
    position_policy = row.get("position_policy") if isinstance(row.get("position_policy"), dict) else {}
    lot_policy = row.get("lot_policy") if isinstance(row.get("lot_policy"), dict) else {}
    return ShortpickV2RuleConfig(
        config_id=str(row["config_id"]),
        family=str(row["family"]),
        candidate_rank_limit=int(row["candidate_rank_limit"]),
        fallback_enabled=bool(fallback_policy.get("enabled")),
        target_mode=str(cash_policy.get("target_mode") or "position_cap"),
        allowed_actions=tuple(str(item) for item in row.get("allowed_actions") or []),
        target_notional=_optional_float(cash_policy.get("target_notional")),
        cash_reserve=float(cash_policy.get("cash_reserve") or 0.0),
        max_position_count=int(position_policy.get("max_position_count") or 5),
        max_position_pct=float(position_policy.get("max_position_pct") or 0.35),
        board_lot_size=int(lot_policy.get("board_lot_size") or 100),
    )


def _source_id_for_config(config_id: str) -> str:
    if "__" not in config_id:
        return CONTROL_CANDIDATE_SOURCE_ID
    source_id, _ = config_id.split("__", 1)
    if source_id not in H10_QUIET_ROBUSTNESS_SOURCE_IDS:
        raise ValueError(f"config_id {config_id} is not an h10 quiet source config")
    return source_id


def _validate_source_artifacts(replay_artifact: dict[str, Any], selection_artifact: dict[str, Any]) -> None:
    if replay_artifact.get("artifact_family") != SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY:
        raise ValueError("replay_artifact must be shortpick_v2_replay_artifact")
    if replay_artifact.get("schema_version") != "v1":
        raise ValueError("replay_artifact schema_version must be v1")
    if replay_artifact.get("status") != "ready":
        raise ValueError("replay_artifact status must be ready")
    candidate_source = ((replay_artifact.get("input_contracts") or {}).get("candidate_source") or {})
    source_ref = str(candidate_source.get("source_ref") or "")
    if STRATEGY_SEARCH_BATCH_H10_QUIET not in source_ref and "h10_quiet" not in str(replay_artifact.get("artifact_id")):
        raise ValueError("replay_artifact must come from the h10_quiet strategy-search batch")
    if selection_artifact.get("artifact_family") != SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY:
        raise ValueError("selection_artifact must be shortpick_v2_rule_selection_artifact")
    if selection_artifact.get("schema_version") != "v1":
        raise ValueError("selection_artifact schema_version must be v1")
    if selection_artifact.get("status") != "ready":
        raise ValueError("selection_artifact status must be ready")


def _source_artifact_ref(artifact: dict[str, Any], path: str | Path | None) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.get("artifact_id") or ""),
        "artifact_family": str(artifact.get("artifact_family") or ""),
        "schema_version": str(artifact.get("schema_version") or ""),
        "status": str(artifact.get("status") or ""),
        "claim_ceiling": str(artifact.get("claim_ceiling") or ""),
        "evidence_basis": str(artifact.get("evidence_basis") or ""),
        "path": None if path is None else str(path),
    }


def _consistency_check(summary: dict[str, Any], source_summary: dict[str, Any]) -> dict[str, Any]:
    checks = [
        _metric_check("trade_count", summary, source_summary, tolerance=0.0),
        _metric_check("skip_count", summary, source_summary, tolerance=0.0),
        _metric_check("fallback_trade_count", summary, source_summary, tolerance=0.0),
        _metric_check("total_return", summary, source_summary, tolerance=0.000001),
        _metric_check("max_drawdown", summary, source_summary, tolerance=0.000001),
        _metric_check("turnover", summary, source_summary, tolerance=0.000001),
        _metric_check("skipped_ratio", summary, source_summary, tolerance=0.000001),
    ]
    return {
        "status": "passed" if all(check["passed"] for check in checks) else "failed",
        "checks": checks,
    }


def _metric_check(
    metric_id: str,
    actual_source: dict[str, Any],
    expected_source: dict[str, Any],
    *,
    tolerance: float,
) -> dict[str, Any]:
    actual = _optional_float(actual_source.get(metric_id))
    expected = _optional_float(expected_source.get(metric_id))
    if actual is None or expected is None:
        passed = actual == expected
        diff = None
    else:
        diff = round(actual - expected, 9)
        passed = abs(diff) <= tolerance
    return {
        "metric_id": metric_id,
        "passed": passed,
        "actual": actual,
        "expected": expected,
        "diff": diff,
        "tolerance": tolerance,
    }


def _execution_mix(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts = Counter(str(decision.get("action")) for decision in decisions)
    weekday_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for decision in decisions:
        signal_date = date.fromisoformat(str(decision["signal_date"]))
        weekday_counts[str(signal_date.isoweekday())][str(decision.get("action"))] += 1
    return {
        "action_counts": dict(sorted(action_counts.items())),
        "weekday_action_counts": {
            weekday: dict(sorted(counter.items())) for weekday, counter in weekday_counts.items()
        },
    }


def _nav_period_returns(timeline: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in timeline:
        grouped[_period_id(date.fromisoformat(str(point["date"])), period)].append(point)
    output = []
    for period_id, points in sorted(grouped.items()):
        start_nav = float(points[0]["nav"])
        end_nav = float(points[-1]["nav"])
        output.append(
            {
                "period_id": period_id,
                "date_from": points[0]["date"],
                "date_to": points[-1]["date"],
                "start_nav": round(start_nav, 6),
                "end_nav": round(end_nav, 6),
                "period_return": round(end_nav / start_nav - 1.0, 6) if start_nav > 0 else None,
            }
        )
    return output


def _trade_period_contribution(
    trade_records: list[dict[str, Any]],
    initial_cash: float,
    period: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trade_records:
        contribution_day = trade.get("contribution_day")
        if contribution_day:
            grouped[_period_id(date.fromisoformat(str(contribution_day)), period)].append(trade)
    output = []
    for period_id, trades in sorted(grouped.items()):
        net_pnl = sum(float(trade.get("net_pnl") or 0.0) for trade in trades)
        output.append(
            {
                "period_id": period_id,
                "trade_count": len(trades),
                "net_pnl": round(net_pnl, 6),
                "return_contribution": round(net_pnl / float(initial_cash), 6) if initial_cash else 0.0,
                "win_rate": _win_rate(trades),
            }
        )
    return output


def _trade_contribution_stress(
    trade_records: list[dict[str, Any]],
    *,
    initial_cash: float,
    final_nav: float,
    trade_day_count: int,
    market_reference_total_return: float | None,
) -> list[dict[str, Any]]:
    winners = sorted(
        [float(trade.get("net_pnl") or 0.0) for trade in trade_records if float(trade.get("net_pnl") or 0.0) > 0],
        reverse=True,
    )
    output = []
    for remove_count in (1, 3, 5):
        removed_pnl = sum(winners[:remove_count])
        stressed_nav = final_nav - removed_pnl
        total_return = round(stressed_nav / float(initial_cash) - 1.0, 6) if initial_cash else 0.0
        market_excess = (
            None if market_reference_total_return is None else round(total_return - market_reference_total_return, 6)
        )
        output.append(
            {
                "remove_top_winner_count": remove_count,
                "removed_pnl": round(removed_pnl, 6),
                "total_return_proxy": total_return,
                "annualized_return_proxy": _annualized_return(
                    total_return=total_return,
                    trade_day_count=trade_day_count,
                ),
                "market_excess_total_return_proxy": market_excess,
                "method": "post_hoc_trade_pnl_subtraction_not_resimulated",
            }
        )
    return output


def _concentration(trade_records: list[dict[str, Any]], *, key: str, limit: int) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trade_records:
        grouped[str(trade.get(key) or "unknown")].append(trade)
    rows = []
    total_abs_pnl = sum(abs(float(trade.get("net_pnl") or 0.0)) for trade in trade_records)
    for value, trades in grouped.items():
        net_pnl = sum(float(trade.get("net_pnl") or 0.0) for trade in trades)
        rows.append(
            {
                key: value,
                "trade_count": len(trades),
                "net_pnl": round(net_pnl, 6),
                "abs_pnl_share": round(abs(net_pnl) / total_abs_pnl, 6) if total_abs_pnl else 0.0,
                "win_rate": _win_rate(trades),
            }
        )
    rows = sorted(rows, key=lambda item: (float(item["abs_pnl_share"]), abs(float(item["net_pnl"]))), reverse=True)
    return {
        "top": rows[:limit],
        "distinct_count": len(rows),
        "largest_abs_pnl_share": rows[0]["abs_pnl_share"] if rows else 0.0,
    }


def _top_trades(trade_records: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    ranked = sorted(trade_records, key=lambda trade: float(trade.get("net_pnl") or 0.0), reverse=reverse)
    return [
        {
            "signal_date": trade["signal_date"],
            "entry_date": trade["entry_date"],
            "exit_date": trade["exit_date"],
            "symbol": trade["symbol"],
            "industry": trade["industry"],
            "rank": trade["rank"],
            "net_pnl": trade["net_pnl"],
            "net_return": trade["net_return"],
        }
        for trade in ranked[:DEFAULT_TOP_TRADE_LIMIT]
    ]


def _risk_flags(
    full_results: list[dict[str, Any]],
    *,
    period_reset_results: dict[str, list[dict[str, Any]]],
    market_reference_total_return: float | None,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    risk_target_ids = _risk_target_config_ids(full_results)
    for result in full_results:
        if result["source_replay_consistency"]["status"] != "passed":
            flags.append(
                {
                    "flag_id": "source_replay_consistency_failed",
                    "severity": "high",
                    "config_id": result["config_id"],
                    "message": "Reconstructed robustness replay does not match the source replay artifact summary.",
                }
            )
        largest_symbol_share = float(result["symbol_concentration"]["largest_abs_pnl_share"])
        if result["config_id"] in risk_target_ids and largest_symbol_share >= 0.35:
            flags.append(
                {
                    "flag_id": "symbol_concentration_high",
                    "severity": "medium",
                    "config_id": result["config_id"],
                    "actual": largest_symbol_share,
                    "threshold": 0.35,
                    "message": "A single symbol explains too much absolute trade PnL.",
                }
            )
        for stress in result["trade_contribution_stress"]:
            annualized = _optional_float(stress.get("annualized_return_proxy"))
            market_excess = _optional_float(stress.get("market_excess_total_return_proxy"))
            annualized_failed = annualized is not None and annualized < 0.30
            market_excess_failed = (
                market_reference_total_return is not None and market_excess is not None and market_excess <= 0
            )
            if result["config_id"] in risk_target_ids and (
                annualized_failed
                or market_excess_failed
            ):
                flags.append(
                    {
                        "flag_id": "winner_removal_stress_fails_gate",
                        "severity": "medium",
                        "config_id": result["config_id"],
                        "remove_top_winner_count": stress["remove_top_winner_count"],
                        "annualized_return_proxy": annualized,
                        "market_excess_total_return_proxy": market_excess,
                        "message": "Post-hoc removal of top winners breaks the return gate.",
                    }
                )
                break
    for row in period_reset_results.get("yearly") or []:
        if row["config_id"] not in risk_target_ids:
            continue
        summary = row["summary"]
        annualized = _optional_float(summary.get("annualized_return"))
        market_excess = _optional_float(summary.get("market_excess_total_return"))
        if annualized is not None and annualized < 0.30:
            flags.append(
                {
                    "flag_id": "yearly_period_below_annualized_floor",
                    "severity": "high",
                    "config_id": row["config_id"],
                    "period_id": row["period_id"],
                    "actual": annualized,
                    "threshold": 0.30,
                    "message": "A yearly reset period fails the 30% annualized floor.",
                }
            )
        if market_excess is not None and market_excess <= 0:
            flags.append(
                {
                    "flag_id": "yearly_period_underperforms_market",
                    "severity": "high",
                    "config_id": row["config_id"],
                    "period_id": row["period_id"],
                    "actual": market_excess,
                    "threshold": 0.0,
                    "message": "A yearly reset period does not beat the equal-weight market reference.",
                }
            )
    return flags


def _risk_target_config_ids(full_results: list[dict[str, Any]]) -> set[str]:
    benchmark_ids = {
        str(result["config_id"])
        for result in full_results
        if str(result.get("role") or "") in BENCHMARK_ANALYSIS_ROLES
        and str(result.get("config_id") or "") in H10_QUIET_BENCHMARK_CONFIG_IDS
    }
    if benchmark_ids:
        return benchmark_ids
    return {
        str(result["config_id"])
        for result in full_results
        if str(result.get("role") or "") == "phase5_contract_candidate"
    }


def _parameter_stability(replay_artifact: dict[str, Any], selection_artifact: dict[str, Any]) -> dict[str, Any]:
    role_by_config = {
        str(row.get("config_id")): str(row.get("role"))
        for key in ("benchmark_configs", "selected_configs", "holdout_configs", "baseline_configs", "rejected_configs")
        for row in selection_artifact.get(key) or []
        if isinstance(row, dict)
    }
    for config_id in H10_QUIET_DIAGNOSTIC_CONFIG_IDS:
        role_by_config.setdefault(config_id, DIAGNOSTIC_ANALYSIS_ROLE)
    rule_by_config = {
        str(row.get("config_id")): row
        for row in replay_artifact.get("rule_matrix") or []
        if isinstance(row, dict) and row.get("config_id")
    }
    rows = []
    for result in replay_artifact.get("results") or []:
        if not isinstance(result, dict):
            continue
        config_id = str(result.get("config_id") or "")
        if "__fixed_notional_" not in config_id or "h10" not in config_id:
            continue
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        rule = rule_by_config.get(config_id) or {}
        cash_policy = rule.get("cash_policy") if isinstance(rule.get("cash_policy"), dict) else {}
        rows.append(
            {
                "config_id": config_id,
                "role": role_by_config.get(config_id, "unselected"),
                "source_id": _source_id_for_config(config_id),
                "target_notional": _optional_float(cash_policy.get("target_notional")),
                "total_return": _optional_float(summary.get("total_return")),
                "annualized_return": _annualized_return(
                    total_return=float(summary.get("total_return") or 0.0),
                    trade_day_count=int(summary.get("annualization_trade_day_count") or 0),
                ),
                "max_drawdown": _optional_float(summary.get("max_drawdown")),
                "trade_count": _optional_int(summary.get("trade_count")),
                "fallback_trade_count": _optional_int(summary.get("fallback_trade_count")),
                "turnover": _optional_float(summary.get("turnover")),
                "skipped_ratio": _optional_float(summary.get("skipped_ratio")),
            }
        )
    rows.sort(key=lambda item: (str(item["source_id"]), float(item["target_notional"] or 0.0)))
    return {
        "rows": rows,
        "notes": [
            "Rows are read from the source replay artifact, not re-ranked here.",
            "The 90k variants can show higher return but may fail turnover governance in rule selection.",
        ],
    }


def _recommendation_notes(status: str, risk_flags: list[dict[str, Any]]) -> list[str]:
    if status == "not_ready_for_paper_tracking":
        high_count = sum(1 for flag in risk_flags if flag["severity"] == "high")
        return [
            f"{high_count} high-severity robustness flags remain open.",
            "Treat h10 quiet as a research lead; do not start v2 paper tracking from this artifact alone.",
        ]
    if status == "candidate_requires_forward_tracking":
        return [
            "Historical robustness checks did not create high-severity blockers.",
            "A later governed plan must still freeze a config and start forward paper tracking.",
        ]
    return ["No analyzable h10 quiet selected or holdout configs were available."]


def _year_periods(signal_days: list[date]) -> list[tuple[str, date, date]]:
    years = sorted({day.year for day in signal_days})
    return [(str(year), date(year, 1, 1), date(year, 12, 31)) for year in years]


def _quarter_periods(signal_days: list[date]) -> list[tuple[str, date, date]]:
    quarters = sorted({(day.year, (day.month - 1) // 3 + 1) for day in signal_days})
    output = []
    for year, quarter in quarters:
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        period_start = date(year, start_month, 1)
        period_end = date(year, end_month, _month_end_day(year, end_month))
        output.append((f"{year}Q{quarter}", period_start, period_end))
    return output


def _month_end_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _period_id(day: date, period: str) -> str:
    if period == "month":
        return day.strftime("%Y-%m")
    if period == "quarter":
        return f"{day.year}Q{((day.month - 1) // 3) + 1}"
    if period == "year":
        return str(day.year)
    raise ValueError(f"unsupported period: {period}")


def _win_rate(trades: list[dict[str, Any]]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for trade in trades if float(trade.get("net_pnl") or 0.0) > 0)
    return round(wins / len(trades), 6)


def _annualized_return(*, total_return: float, trade_day_count: int) -> float | None:
    if trade_day_count <= 0 or total_return <= -1.0:
        return None
    return round(((1.0 + total_return) ** (252.0 / trade_day_count)) - 1.0, 6)


def _artifact_id(generated_at: datetime, start_date: date, end_date: date, initial_cash: float) -> str:
    generated_day = generated_at.date().isoformat()
    cash_text = str(int(initial_cash)) if float(initial_cash).is_integer() else str(initial_cash)
    return f"shortpick_v2_h10_robustness:{start_date.isoformat()}:{end_date.isoformat()}:{cash_text}:{generated_day}"


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
