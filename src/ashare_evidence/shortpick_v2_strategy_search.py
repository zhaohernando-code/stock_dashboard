from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
from ashare_evidence.shortpick_market_factor_study import (
    ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    ENTRY_PRICE_SOURCES,
    GOLDEN_CROSS_STRATEGY,
    INDEX_SYMBOLS,
    LOW_TURNOVER_UPTREND_STRATEGY,
    QUIET_BREAKOUT_BASE_STRATEGY,
    _build_strategy_selections,
    _load_daily_series,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    QUIET_BREAKOUT_RANK2_STRATEGY,
    STRONG_BREADTH_RANK2_STRATEGY,
    _apply_strategy_regime_filter,
    _apply_strategy_selection_transform,
    _eligible_signal_days,
    _regime_features_by_day,
    _trade_days,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MAX_POSITION_COUNT,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_STAMP_TAX_BPS,
    DEFAULT_SHORTPICK_V2_RULE_CONFIGS,
    SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY,
    SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
    SHORTPICK_V2_REPLAY_SCHEMA_VERSION,
    SHORTPICK_V2_REPLAY_SOURCE_PLAN_REF,
    ShortpickV2RuleConfig,
    _build_low_turnover_uptrend_candidate_pool,
    _coverage_notes,
    build_shortpick_v2_replay_artifact_from_series,
    write_shortpick_v2_replay_artifact,
)

SHORTPICK_V2_STRATEGY_SEARCH_SOURCE_REF = "market_only_reconstruction:shortpick_v2_strategy_search_batch:v1"
SHORTPICK_V2_STRATEGY_SEARCH_EVENT_REF = "shortpick_v2.strategy_search.generated"
CONTROL_CANDIDATE_SOURCE_ID = LOW_TURNOVER_UPTREND_STRATEGY
DEFAULT_CANDIDATE_SOURCE_IDS = (
    CONTROL_CANDIDATE_SOURCE_ID,
    "quiet_breakout_rank2",
    "ret10_turnover_strong_breadth",
    "ret10_turnover_rank2_market_positive",
    "ret10_turnover_industry_diversified",
    "golden_cross_10_200",
)


@dataclass(frozen=True)
class StrategySearchCandidateSource:
    source_id: str
    source_ref: str
    selections: dict[date, list[str]]


def build_shortpick_v2_strategy_search_artifact(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 5,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = 45,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if entry_price_source not in ENTRY_PRICE_SOURCES:
        raise ValueError(f"entry_price_source must be one of {sorted(ENTRY_PRICE_SOURCES)}")
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
    candidate_sources = build_default_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=signal_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
    )
    return build_shortpick_v2_strategy_search_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=candidate_sources,
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
        generated_at=generated_at,
    )


def build_default_strategy_search_candidate_sources(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    pool_limit: int,
    rank_limit: int,
) -> tuple[StrategySearchCandidateSource, ...]:
    effective_rank_limit = max(rank_limit, max(config.candidate_rank_limit for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS))
    regime_features = _regime_features_by_day(series_by_symbol, signal_days=signal_days, pool_limit=pool_limit)
    ret10_turnover = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy="ret10_turnover",
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    quiet_breakout = _build_strategy_selections(
        series_by_symbol,
        signal_days=signal_days,
        strategy=QUIET_BREAKOUT_BASE_STRATEGY,
        pool_limit=pool_limit,
        rank_limit=effective_rank_limit,
    )
    return (
        StrategySearchCandidateSource(
            source_id=CONTROL_CANDIDATE_SOURCE_ID,
            source_ref=SHORTPICK_V2_REPLAY_CANDIDATE_SOURCE_REF,
            selections=_build_low_turnover_uptrend_candidate_pool(
                series_by_symbol,
                signal_days=signal_days,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="quiet_breakout_rank2",
            source_ref=f"market_only_reconstruction:{QUIET_BREAKOUT_RANK2_STRATEGY}:v1",
            selections=_apply_strategy_selection_transform(QUIET_BREAKOUT_RANK2_STRATEGY, quiet_breakout),
        ),
        StrategySearchCandidateSource(
            source_id="ret10_turnover_strong_breadth",
            source_ref="market_only_reconstruction:ret10_turnover_strong_breadth_pool:v1",
            selections=_apply_strategy_regime_filter("ret10_turnover_strong_breadth_pool", ret10_turnover, regime_features),
        ),
        StrategySearchCandidateSource(
            source_id="ret10_turnover_rank2_market_positive",
            source_ref=f"market_only_reconstruction:{STRONG_BREADTH_RANK2_STRATEGY}:v1",
            selections=_apply_strategy_regime_filter(
                STRONG_BREADTH_RANK2_STRATEGY,
                _apply_strategy_selection_transform(STRONG_BREADTH_RANK2_STRATEGY, ret10_turnover),
                regime_features,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="ret10_turnover_industry_diversified",
            source_ref="market_only_reconstruction:ret10_turnover_cooldown_diversified:v1",
            selections=_build_strategy_selections(
                series_by_symbol,
                signal_days=signal_days,
                strategy="ret10_turnover_cooldown_diversified",
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
        StrategySearchCandidateSource(
            source_id="golden_cross_10_200",
            source_ref=f"market_only_reconstruction:{GOLDEN_CROSS_STRATEGY}:v1",
            selections=_build_strategy_selections(
                series_by_symbol,
                signal_days=signal_days,
                strategy=GOLDEN_CROSS_STRATEGY,
                pool_limit=pool_limit,
                rank_limit=effective_rank_limit,
            ),
        ),
    )


def build_shortpick_v2_strategy_search_artifact_from_series(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    candidate_sources: tuple[StrategySearchCandidateSource, ...],
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 5,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    stock_like_series_count: int | None = None,
    coverage_notes: list[str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if not candidate_sources:
        raise ValueError("candidate_sources must not be empty")
    if CONTROL_CANDIDATE_SOURCE_ID not in {source.source_id for source in candidate_sources}:
        raise ValueError(f"candidate_sources must include {CONTROL_CANDIDATE_SOURCE_ID}")
    generated_at = generated_at or datetime.now(UTC)
    stock_like_series_count = (
        stock_like_series_count
        if stock_like_series_count is not None
        else len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS])
    )
    child_artifacts = [
        _build_child_artifact(
            series_by_symbol,
            signal_days=signal_days,
            trade_days=trade_days,
            candidate_source=source,
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
            generated_at=generated_at,
        )
        for source in candidate_sources
    ]
    return _merge_child_artifacts(
        child_artifacts,
        candidate_sources=candidate_sources,
        generated_at=generated_at,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
    )


def write_shortpick_v2_strategy_search_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    return write_shortpick_v2_replay_artifact(payload, output_path=output_path)


def _build_child_artifact(
    series_by_symbol: dict[str, Any],
    *,
    signal_days: list[date],
    trade_days: list[date],
    candidate_source: StrategySearchCandidateSource,
    start_date: date,
    end_date: date,
    initial_cash: float,
    entry_price_source: str,
    horizon_days: int,
    pool_limit: int,
    rank_limit: int,
    cost_bps: float,
    stamp_tax_bps: float,
    account_profile: str,
    stock_like_series_count: int,
    coverage_notes: list[str] | None,
    generated_at: datetime,
) -> dict[str, Any]:
    return build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        selections=candidate_source.selections,
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
        rule_configs=_rule_configs_for_source(candidate_source.source_id),
        generated_at=generated_at,
    )


def _rule_configs_for_source(source_id: str) -> tuple[ShortpickV2RuleConfig, ...]:
    if source_id == CONTROL_CANDIDATE_SOURCE_ID:
        return DEFAULT_SHORTPICK_V2_RULE_CONFIGS
    return tuple(_prefixed_rule_config(source_id, config) for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS)


def _prefixed_rule_config(source_id: str, config: ShortpickV2RuleConfig) -> ShortpickV2RuleConfig:
    return ShortpickV2RuleConfig(
        config_id=f"{source_id}__{config.config_id}",
        family=config.family,
        candidate_rank_limit=config.candidate_rank_limit,
        fallback_enabled=config.fallback_enabled,
        target_mode=config.target_mode,
        allowed_actions=config.allowed_actions,
        target_notional=config.target_notional,
        cash_reserve=config.cash_reserve,
        max_position_count=config.max_position_count,
        max_position_pct=config.max_position_pct,
        board_lot_size=config.board_lot_size,
    )


def _merge_child_artifacts(
    child_artifacts: list[dict[str, Any]],
    *,
    candidate_sources: tuple[StrategySearchCandidateSource, ...],
    generated_at: datetime,
    start_date: date,
    end_date: date,
    initial_cash: float,
) -> dict[str, Any]:
    template = dict(child_artifacts[0])
    template["artifact_id"] = _strategy_search_artifact_id(generated_at, start_date, end_date, initial_cash)
    template["source_plan_ref"] = SHORTPICK_V2_REPLAY_SOURCE_PLAN_REF
    template["rule_matrix"] = _unique_by_config_id(
        row for child in child_artifacts for row in child.get("rule_matrix") or []
    )
    template["results"] = _unique_by_config_id(
        row for child in child_artifacts for row in child.get("results") or []
    )
    input_contracts = dict(template.get("input_contracts") or {})
    input_contracts["candidate_source"] = {
        "source_family": "shortpick_v2_candidate_projection",
        "source_ref": SHORTPICK_V2_STRATEGY_SEARCH_SOURCE_REF,
        "ranked_pool_required": True,
        "source_feature_cutoff_policy": (
            "Strategy-search candidate pools are reconstructed from signal-day-or-earlier daily-bar features; "
            "entry and exit bars are used only by the execution replay."
        ),
        "allowed_evidence_basis": ["historical_backtest", "market_only_reconstruction"],
    }
    template["input_contracts"] = input_contracts
    data_scope = dict(template.get("data_scope") or {})
    coverage_notes = list(data_scope.get("coverage_notes") or [])
    coverage_notes.append(
        "Strategy-search batch evaluated candidate sources: "
        + ", ".join(source.source_ref for source in candidate_sources)
        + "."
    )
    data_scope["coverage_notes"] = coverage_notes
    template["data_scope"] = data_scope
    template["event_refs"] = sorted(
        {
            *(str(ref) for child in child_artifacts for ref in child.get("event_refs") or []),
            SHORTPICK_V2_STRATEGY_SEARCH_EVENT_REF,
        }
    )
    _validate_merged_artifact(template)
    return template


def _unique_by_config_id(rows: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        config_id = str(row.get("config_id") or "")
        if not config_id or config_id in seen:
            raise ValueError(f"duplicate or missing config_id in strategy search artifact: {config_id!r}")
        seen.add(config_id)
        output.append(row)
    return output


def _validate_merged_artifact(payload: dict[str, Any]) -> None:
    if payload.get("artifact_family") != SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY:
        raise ValueError("strategy search artifact must remain a shortpick_v2_replay_artifact")
    if payload.get("schema_version") != SHORTPICK_V2_REPLAY_SCHEMA_VERSION:
        raise ValueError("strategy search artifact must keep schema_version v1")
    result_ids = {str(row.get("config_id") or "") for row in payload.get("results") or []}
    missing_controls = [
        config.config_id for config in DEFAULT_SHORTPICK_V2_RULE_CONFIGS if config.config_id not in result_ids
    ]
    if missing_controls:
        raise ValueError(f"strategy search artifact is missing control configs: {missing_controls}")


def _strategy_search_artifact_id(generated_at: datetime, start_date: date, end_date: date, initial_cash: float) -> str:
    generated_day = generated_at.date().isoformat()
    cash_text = str(int(initial_cash)) if float(initial_cash).is_integer() else str(initial_cash)
    return f"shortpick_v2_replay_artifact:strategy_search:{start_date.isoformat()}:{end_date.isoformat()}:{cash_text}:{generated_day}"
