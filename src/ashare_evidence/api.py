from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ashare_evidence.account_space import visible_account_spaces
from ashare_evidence.api_event import register_event_routes
from ashare_evidence.dashboard import (
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.db import get_database_url, get_session_factory, init_database, utcnow
from ashare_evidence.improvement_suggestions import (
    accept_suggestion_for_plan,
    run_improvement_suggestion_review,
    suggestion_details,
    suggestion_summary,
    update_suggestion_status,
)
from ashare_evidence.llm_service import run_follow_up_analysis
from ashare_evidence.manual_research_workflow import (
    complete_manual_research_request,
    create_manual_research_request,
    execute_manual_research_request,
    fail_manual_research_request,
    get_manual_research_request,
    list_manual_research_requests,
    retry_manual_research_request,
)
from ashare_evidence.models import ShortpickCandidate, ShortpickExperimentRun
from ashare_evidence.operations import build_operations_dashboard, build_operations_detail, build_operations_summary
from ashare_evidence.policy_audit import build_policy_audit_report
from ashare_evidence.policy_config_loader import build_policy_governance_summary, list_policy_config_versions
from ashare_evidence.runtime_config import (
    create_model_api_key,
    delete_model_api_key,
    ensure_runtime_defaults,
    get_runtime_overview,
    get_runtime_settings,
    set_default_model_api_key,
    update_model_api_key,
    upsert_provider_credential,
)
from ashare_evidence.runtime_ops import run_operations_tick
from ashare_evidence.scheduled_refresh_status import get_scheduled_refresh_status
from ashare_evidence.schemas import (
    AuthContextResponse,
    CandidateListResponse,
    FollowUpAnalysisRequest,
    FollowUpAnalysisResponse,
    LatestRecommendationResponse,
    ManualResearchRequestCompleteRequest,
    ManualResearchRequestCreateRequest,
    ManualResearchRequestExecuteRequest,
    ManualResearchRequestFailRequest,
    ManualResearchRequestListResponse,
    ManualResearchRequestRetryRequest,
    ManualResearchRequestView,
    ManualSimulationOrderRequest,
    ModelApiKeyCreateRequest,
    ModelApiKeyDeleteResponse,
    ModelApiKeyUpdateRequest,
    OperationsDashboardResponse,
    ProviderCredentialUpsertRequest,
    RecommendationTraceResponse,
    RuntimeOverviewResponse,
    RuntimeSettingsResponse,
    ScheduledRefreshStatusView,
    ShortpickCandidateListResponse,
    ShortpickCandidateView,
    ShortpickModelFeedbackResponse,
    ShortpickRetryFailedRoundsRequest,
    ShortpickRunCreateRequest,
    ShortpickRunListResponse,
    ShortpickRunValidateRequest,
    ShortpickRunView,
    ShortpickValidationQueueResponse,
    SimulationConfigRequest,
    SimulationControlActionResponse,
    SimulationEndRequest,
    SimulationWorkspaceResponse,
    StockDashboardResponse,
    WatchlistCreateRequest,
    WatchlistDeleteResponse,
    WatchlistMutationResponse,
    WatchlistResponse,
)
from ashare_evidence.services import get_latest_recommendation_summary, get_recommendation_trace
from ashare_evidence.shortpick_lab import (
    SHORTPICK_INFORMATION_MODE,
    SHORTPICK_LLM_PAPER_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES,
    SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
    build_shortpick_model_feedback,
    get_shortpick_candidate,
    get_shortpick_run,
    list_shortpick_candidates,
    list_shortpick_runs,
    list_shortpick_validation_queue,
    retry_failed_shortpick_rounds,
    run_shortpick_experiment,
    shortpick_frozen_paper_strategy_contract,
    shortpick_llm_paper_control_contract,
    shortpick_market_factor_paper_control_contracts,
    validate_shortpick_run,
)
from ashare_evidence.shortpick_replay import (
    get_shortpick_replay_run,
    get_shortpick_replay_sources,
    list_shortpick_replay_candidates,
    list_shortpick_replay_runs,
)
from ashare_evidence.simulation import (
    end_simulation_session,
    get_simulation_workspace,
    pause_simulation_session,
    place_manual_order,
    restart_simulation_session,
    resume_simulation_session,
    start_simulation_session,
    step_simulation_session,
    update_simulation_config,
)
from ashare_evidence.stock_auth import StockAccessContext, require_stock_access, require_stock_root
from ashare_evidence.watchlist import (
    add_watchlist_symbol,
    list_watchlist_entries,
    refresh_watchlist_symbol,
    remove_watchlist_symbol,
)

LOGGER = logging.getLogger(__name__)
SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT = Path("output/shortpick-portfolio-backtest-new-retail-mainboard-current.json")
LEGACY_SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT = Path("output/shortpick-portfolio-backtest-new-retail-mainboard-current-20260510.json")
STAGED_SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT = Path("output/shortpick-staged-backtests/20260512T221426/full_window-next_close.json")
SHORTPICK_MARKET_FACTOR_STUDY_ARTIFACT = Path("output/shortpick-market-factor-study-current.json")
SHORTPICK_REPLAY_FEEDBACK_CACHE_ARTIFACT = Path("output/shortpick-replay-feedback-cache.json")


def _existing_project_artifact_path(relative_path: Path, *, env_var: str | None = None) -> Path:
    candidates: list[Path] = []
    if env_var:
        configured = os.getenv(env_var)
        if configured:
            candidates.append(Path(configured).expanduser())
    candidates.extend([
        relative_path,
        Path(__file__).resolve().parents[2] / relative_path,
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def _shortpick_portfolio_artifact_path() -> Path:
    configured = os.getenv("ASHARE_SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT")
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.exists():
            return configured_path
        return configured_path
    for relative_path in (
        SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT,
        STAGED_SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT,
        LEGACY_SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT,
    ):
        candidate = _existing_project_artifact_path(relative_path)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2] / SHORTPICK_PORTFOLIO_BACKTEST_ARTIFACT


def _shortpick_market_factor_study_artifact_path() -> Path:
    return _existing_project_artifact_path(SHORTPICK_MARKET_FACTOR_STUDY_ARTIFACT, env_var="ASHARE_SHORTPICK_MARKET_FACTOR_STUDY_ARTIFACT")


def _shortpick_replay_feedback_cache_artifact_path() -> Path:
    return _existing_project_artifact_path(SHORTPICK_REPLAY_FEEDBACK_CACHE_ARTIFACT, env_var="ASHARE_SHORTPICK_REPLAY_FEEDBACK_CACHE_ARTIFACT")


def _read_json_artifact(path: Path, *, label: str) -> dict[str, object]:
    if not path.exists():
        raise LookupError(f"{label} artifact is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact root must be a JSON object: {path}")
    return payload


def _load_shortpick_market_factor_study_artifact(benchmark_mode: str) -> dict[str, object]:
    artifact_path = _shortpick_market_factor_study_artifact_path()
    payload = (
        _read_json_artifact(artifact_path, label="shortpick market-factor study")
        if artifact_path.exists()
        else _derive_market_factor_study_from_portfolio_artifact()
    )
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    artifact_benchmark_mode = str(config.get("benchmark_mode") or "universe_equal_weight")
    if artifact_benchmark_mode != benchmark_mode:
        raise LookupError(
            "shortpick market-factor study artifact benchmark mismatch: "
            f"requested={benchmark_mode}, artifact={artifact_benchmark_mode}"
        )
    enriched = _attach_shortpick_frozen_strategy_evidence(dict(payload))
    enriched.setdefault("artifact_path", str(artifact_path))
    return enriched


def _derive_market_factor_study_from_portfolio_artifact() -> dict[str, object]:
    artifact_path = _shortpick_portfolio_artifact_path()
    artifact = _read_json_artifact(artifact_path, label="shortpick portfolio backtest")
    daily_results = ((artifact.get("results") or {}).get("daily_rolling_5x10k") or {})
    if not isinstance(daily_results, dict) or not daily_results:
        raise LookupError(f"shortpick portfolio artifact has no daily_rolling_5x10k stats: {artifact_path}")
    data_scope = artifact.get("data_scope") if isinstance(artifact.get("data_scope"), dict) else {}
    config = artifact.get("config") if isinstance(artifact.get("config"), dict) else {}
    strategies = set(daily_results)
    alias_sources = {
        "ret10_turnover_cooldown_regime_gate": "ret10_turnover_cooldown_market_positive_cooldown",
        "ret10_amount_turnover_cooldown": "ret10_amount_turnover_strong_breadth_rank2_stop12",
    }
    strategies.update(alias_sources)

    def summary_for(strategy: str) -> dict[str, object]:
        source_strategy = alias_sources.get(strategy, strategy)
        source = daily_results.get(source_strategy) if isinstance(daily_results.get(source_strategy), dict) else {}
        summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
        trade_count = int(summary.get("trade_count") or 0)
        excess = summary.get("excess_total_return")
        total = summary.get("total_return")
        max_drawdown = summary.get("max_drawdown")
        block = {
            "completed_count": trade_count,
            "portfolio_count": trade_count,
            "completed_member_count": trade_count,
            "mean_net_excess_return": excess,
            "trimmed_mean_net_excess_return": excess,
            "positive_net_excess_rate": summary.get("positive_trade_rate"),
            "mean_stock_return": total,
            "max_additive_drawdown": max_drawdown,
        }
        return {
            "selected_symbol_day_count": trade_count,
            "completed_count": trade_count,
            "mean_net_excess_return": excess,
            "trimmed_mean_net_excess_return": excess,
            "positive_net_excess_rate": summary.get("positive_trade_rate"),
            "by_horizon": {"5": block},
            "source": "portfolio_backtest_artifact",
            "source_strategy": source_strategy,
        }

    def portfolio_for(strategy: str) -> dict[str, object]:
        source_strategy = alias_sources.get(strategy, strategy)
        source = daily_results.get(source_strategy) if isinstance(daily_results.get(source_strategy), dict) else {}
        summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
        trade_count = int(summary.get("trade_count") or 0)
        excess = summary.get("excess_total_return")
        total = summary.get("total_return")
        max_drawdown = summary.get("max_drawdown")
        block = {
            "portfolio_count": trade_count,
            "completed_member_count": trade_count,
            "mean_net_excess_return": excess,
            "trimmed_mean_net_excess_return": excess,
            "positive_net_excess_rate": summary.get("positive_trade_rate"),
        }
        return {
            "portfolio_count": trade_count,
            "signal_day_count": data_scope.get("signal_day_count"),
            "completed_member_count": trade_count,
            "average_member_count": 1,
            "mean_net_excess_return": excess,
            "trimmed_mean_net_excess_return": excess,
            "positive_net_excess_rate": summary.get("positive_trade_rate"),
            "volatility": summary.get("volatility"),
            "worst_portfolio_return": summary.get("worst_trade_return"),
            "best_portfolio_return": summary.get("best_trade_return"),
            "max_additive_drawdown": max_drawdown,
            "by_horizon": {"5": block},
            "source": "portfolio_backtest_artifact",
            "source_strategy": source_strategy,
            "total_return": total,
            "excess_total_return": excess,
            "max_drawdown": max_drawdown,
            "trade_count": trade_count,
        }

    period_summary = {
        period: {strategy: summary_for(strategy) for strategy in sorted(strategies)}
        for period in ("train", "holdout", "replay_window", "all")
    }
    portfolio_summary = {
        period: {strategy: portfolio_for(strategy) for strategy in sorted(strategies)}
        for period in ("train", "holdout", "replay_window", "all")
    }
    return {
        "experiment": "shortpick_market_factor_study_precomputed",
        "validation_mode": "portfolio_artifact_precomputed",
        "config": {
            **config,
            "benchmark_mode": str(config.get("benchmark_mode") or "universe_equal_weight"),
            "source_artifact_path": str(artifact_path),
        },
        "data_scope": data_scope,
        "period_summary": period_summary,
        "paired_vs_base": {period: {} for period in ("train", "holdout", "replay_window", "all")},
        "walk_forward_selection": {},
        "regime_gate": {"allowed_signal_day_count": 0, "source": "portfolio_backtest_artifact"},
        "monthly_summary": {},
        "portfolio_summary": portfolio_summary,
        "regime_summary": {},
    }


def _load_shortpick_replay_feedback_from_cache(run_id: int | None) -> dict[str, object]:
    artifact_path = _shortpick_replay_feedback_cache_artifact_path()
    payload = _read_json_artifact(artifact_path, label="shortpick replay feedback cache")
    if run_id is None:
        feedback = payload.get("aggregate")
    else:
        runs = payload.get("runs") if isinstance(payload.get("runs"), dict) else {}
        feedback = runs.get(str(run_id))
    if not isinstance(feedback, dict):
        raise LookupError(
            "shortpick replay feedback cache is missing "
            f"{'aggregate feedback' if run_id is None else f'run {run_id} feedback'}: {artifact_path}"
        )
    return feedback


def _attach_shortpick_frozen_strategy_evidence(payload: dict[str, object]) -> dict[str, object]:
    frozen = shortpick_frozen_paper_strategy_contract()
    artifact_payload: dict[str, object] = {}
    artifact_path = _shortpick_portfolio_artifact_path()
    if artifact_path.exists():
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            leading_mode = str(frozen.get("mode_key") or "daily_rolling_5x10k")
            leading_strategy = "low_turnover_20d_uptrend_liquid_top120"
            leading = (((artifact.get("results") or {}).get(leading_mode) or {}).get(leading_strategy) or {})
            daily_results = (artifact.get("results") or {}).get(leading_mode) or {}
            comparison_strategies = (
                leading_strategy,
                "ret10_turnover_second_market_positive_cooldown",
                "ret10_turnover_second_market_positive_cooldown_stop8",
                "ret10_amount_turnover_strong_breadth_rank2_stop12",
                "low_turnover_20d_uptrend_liquid_top120",
                "ret10_turnover_top3_market_positive_cooldown_equal_weight",
                "momentum_volume_golden_cross_10_200",
                "ret10_turnover",
                "ret10_turnover_cooldown",
            )
            paper_control_summaries = {
                strategy: {
                    "label": (daily_results.get(strategy) or {}).get("label") or strategy,
                    "summary": (daily_results.get(strategy) or {}).get("summary") or {},
                    "yearly": (daily_results.get(strategy) or {}).get("yearly") or [],
                }
                for strategy in comparison_strategies
                if strategy in daily_results
            }
            production_evidence = artifact.get("production_evidence") or {}
            artifact_payload = {
                "artifact_path": str(artifact_path),
                "summary": (leading.get("summary") or {}),
                "paper_control_summaries": paper_control_summaries,
                "production_evidence": production_evidence,
                "data_scope": artifact.get("data_scope") or {},
                "config": artifact.get("config") or {},
                "benchmark_references": artifact.get("benchmark_references") or {},
                "comparison": artifact.get("comparison") or {},
            }
        except Exception as exc:  # pragma: no cover - defensive runtime projection
            artifact_payload = {"artifact_path": str(artifact_path), "artifact_error": str(exc)}
    else:
        artifact_payload = {"artifact_path": str(artifact_path), "artifact_error": "artifact_not_found"}
    return {
        **payload,
        "frozen_paper_strategy": {
            **frozen,
            "evidence": artifact_payload,
        },
    }


def _iso_or_none(value: object) -> str | None:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return, attr-defined]
    return None


def _shortpick_market_control_contract_by_role(contract: dict[str, object], role: str) -> dict[str, object]:
    controls = contract.get("controls")
    if not isinstance(controls, list):
        return {}
    for control in controls:
        if isinstance(control, dict) and control.get("role") == role:
            return dict(control)
    return {}


def _shortpick_tracking_group_for_role(role: str, *, is_frozen_item: bool, is_llm_control_item: bool) -> str:
    if is_frozen_item:
        return "frozen_strategy"
    if is_llm_control_item:
        return "llm_paper_control"
    if role == SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE:
        return "market_random_control"
    if role in SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES:
        return "market_factor_control"
    return "paper_tracking"


def _build_shortpick_paper_tracking_ledger(session: Session) -> dict[str, object]:
    contract = shortpick_frozen_paper_strategy_contract()
    llm_contract = shortpick_llm_paper_control_contract()
    market_control_contract = shortpick_market_factor_paper_control_contracts()
    family = str(contract.get("family") or "")
    monitoring_tracks = contract.get("monitoring_tracks") if isinstance(contract.get("monitoring_tracks"), list) else []
    max_holding_days = max(
        [int(item.get("holding_days") or item.get("max_holding_days") or 0) for item in monitoring_tracks if isinstance(item, dict)]
        or [10]
    )
    frozen_at = date.fromisoformat(str(contract.get("frozen_at") or "2026-05-09"))
    latest_run = session.scalar(
        select(ShortpickExperimentRun)
        .where(ShortpickExperimentRun.information_mode == SHORTPICK_INFORMATION_MODE)
        .order_by(ShortpickExperimentRun.run_date.desc(), ShortpickExperimentRun.id.desc())
        .limit(1)
    )
    tracking_role_expr = func.coalesce(func.json_extract(ShortpickCandidate.candidate_payload, "$.tracking_role"), "")
    raw_rows = session.execute(
        select(ShortpickExperimentRun, ShortpickCandidate)
        .join(ShortpickCandidate, ShortpickCandidate.run_id == ShortpickExperimentRun.id)
        .where(
            ShortpickExperimentRun.information_mode == SHORTPICK_INFORMATION_MODE,
            or_(
                ShortpickExperimentRun.run_date >= frozen_at,
                ShortpickCandidate.research_priority == "market_factor_frozen_paper",
                tracking_role_expr.in_(
                    [
                        "frozen_paper_primary",
                        SHORTPICK_LLM_PAPER_CONTROL_ROLE,
                        *sorted(SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES),
                    ]
                ),
            ),
            ShortpickCandidate.parse_status == "parsed",
        )
        .order_by(ShortpickExperimentRun.run_date.desc(), ShortpickCandidate.id.desc())
        .limit(1000)
    ).all()

    items: list[dict[str, object]] = []
    for run, candidate in raw_rows:
        candidate_payload = dict(candidate.candidate_payload or {})
        tracking_role = str(candidate_payload.get("tracking_role") or "")
        is_frozen_item = candidate.research_priority == "market_factor_frozen_paper"
        is_llm_control_item = tracking_role == SHORTPICK_LLM_PAPER_CONTROL_ROLE
        is_market_control_item = tracking_role in SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES
        if not is_frozen_item and not is_llm_control_item and not is_market_control_item:
            continue
        overlay = dict(candidate_payload.get("market_factor_overlay") or {})
        llm_control = dict(candidate_payload.get("llm_paper_control") or {})
        entry_price_source = str(candidate_payload.get("paper_tracking_entry_price_source") or overlay.get("entry_price_source") or "next_close")
        summary_overlay = dict((run.summary_payload or {}).get("market_factor_overlay") or {})
        frozen = dict(summary_overlay.get("frozen_paper_strategy") or {})
        regime = dict(summary_overlay.get("regime") or overlay.get("regime") or {})
        signal_date = str(candidate_payload.get("paper_tracking_signal_date") or run.run_date.isoformat())
        entry_date = str(candidate_payload.get("paper_tracking_entry_date") or "")
        market_control = _shortpick_market_control_contract_by_role(market_control_contract, tracking_role)
        if is_frozen_item:
            item_contract = contract
        elif is_llm_control_item:
            item_contract = llm_contract
        else:
            item_contract = {**market_control_contract, **market_control}
        tracking_group = _shortpick_tracking_group_for_role(
            tracking_role,
            is_frozen_item=is_frozen_item,
            is_llm_control_item=is_llm_control_item,
        )
        items.append(
            {
                "run_id": run.id,
                "candidate_id": candidate.id,
                "run_date": run.run_date.isoformat(),
                "signal_date": signal_date,
                "entry_date": entry_date,
                "symbol": candidate.symbol,
                "name": candidate.name,
                "status": "tracking_signal",
                "tracking_group": tracking_group,
                "tracking_role": tracking_role or ("frozen_paper_primary" if is_frozen_item else ""),
                "selection_label": str(item_contract.get("label") or "纸面对照"),
                "source_rank": int(overlay.get("source_rank") or llm_control.get("selection_rank") or 2),
                "entry_rule": (
                    "次一交易日开盘买入；开盘直接接近涨停时标记为不可假设成交"
                    if entry_price_source == "next_open"
                    else "信号日盘中当前价买入；当前价接近涨停时跳过候选，不假设可以买入"
                    if entry_price_source == "same_day_intraday_current"
                    else "次一交易日收盘买入"
                ),
                "exit_rule": str(
                    item_contract.get("risk_rule")
                    or item_contract.get("monitoring_rule")
                    or item_contract.get("selection_rule")
                    or "四轨退出监测"
                ),
                "monitoring_tracks": item_contract.get("monitoring_tracks") if isinstance(item_contract.get("monitoring_tracks"), list) else monitoring_tracks,
                "holding_days": max_holding_days,
                "stop_loss_pct": 0.08,
                "thesis": candidate.thesis,
                "gate": {
                    "passed": bool(frozen.get("gate_pass", True)) if is_frozen_item else True,
                    "inserted": bool(frozen.get("inserted", True)) if is_frozen_item else bool(llm_control.get("selected", True)),
                },
                "regime": {
                    "universe_ret10_mean": regime.get("universe_ret10_mean"),
                    "pool_ret1_mean": regime.get("pool_ret1_mean"),
                    "breadth10": regime.get("breadth10"),
                    "pool_ret10_mean": regime.get("pool_ret10_mean"),
                },
                "selection_score_components": llm_control.get("selection_score_components") if is_llm_control_item else overlay,
                "created_at": _iso_or_none(candidate.created_at),
                "updated_at": _iso_or_none(candidate.updated_at),
            }
        )
        if len(items) >= 160:
            break

    latest_summary = dict(latest_run.summary_payload or {}) if latest_run else {}
    latest_overlay = dict(latest_summary.get("market_factor_overlay") or {})
    latest_frozen = dict(latest_overlay.get("frozen_paper_strategy") or {})
    latest_has_frozen_overlay = bool(latest_frozen)
    latest_run_date = latest_run.run_date if latest_run else None

    frozen_items = [item for item in items if item.get("tracking_group") == "frozen_strategy"]
    llm_control_items = [item for item in items if item.get("tracking_group") == "llm_paper_control"]
    market_control_items = [
        item
        for item in items
        if item.get("tracking_group") in {"market_factor_control", "market_random_control"}
    ]

    if frozen_items:
        current_status = "tracking_active"
        current_label = "已有冻结策略纸面跟踪标的"
        current_message = "冻结策略已经写入正式纸面跟踪标的；后续只做前向观察，不根据跟踪期表现改参数。"
    elif latest_run_date and (latest_run_date < frozen_at or not latest_has_frozen_overlay):
        current_status = "waiting_first_frozen_run"
        current_label = "等待首个冻结后正式批次"
        current_message = "当前最新短投批次生成于规则冻结前，或尚未写入冻结策略覆盖层；下一次盘后批次会开始记录正式纸面跟踪。"
    elif latest_has_frozen_overlay and not bool(latest_frozen.get("inserted")):
        current_status = "no_signal"
        current_label = "本批次未触发冻结策略"
        current_message = "冻结策略已启用，但当前市场状态或候选池热度未满足条件；这也是纸面跟踪的一部分。"
    else:
        current_status = "waiting_signal"
        current_label = "等待正式纸面信号"
        current_message = "冻结策略合同已存在，等待下一次符合条件的批次。"

    return {
        "generated_at": utcnow().isoformat(),
        "current_status": current_status,
        "current_label": current_label,
        "current_message": current_message,
        "contract": contract,
        "llm_control_contract": llm_contract,
        "market_control_contract": market_control_contract,
        "latest_run": (
            {
                "id": latest_run.id,
                "run_date": latest_run.run_date.isoformat(),
                "status": latest_run.status,
                "trigger_source": latest_run.trigger_source,
                "completed_at": _iso_or_none(latest_run.completed_at),
                "has_frozen_overlay": latest_has_frozen_overlay,
            }
            if latest_run
            else None
        ),
        "summary": {
            "tracked_signal_count": len(frozen_items),
            "llm_paper_control_signal_count": len(llm_control_items),
            "market_control_signal_count": len(market_control_items),
            "comparison_signal_count": len(items),
            "required_forward_trading_days": int(contract.get("required_forward_trading_days") or 40),
            "frozen_at": frozen_at.isoformat(),
            "family": family,
            "scope_note": str(contract.get("scope_note") or ""),
            "llm_control_scope_note": str(llm_contract.get("scope_note") or ""),
            "market_control_scope_note": str(market_control_contract.get("scope_note") or ""),
        },
        "items": items,
    }


def create_app(
    database_url: str | None = None,
    *,
    enable_background_ops_tick: bool | None = None,
) -> FastAPI:
    resolved_database_url = get_database_url(database_url)
    init_database(resolved_database_url)
    session_factory = get_session_factory(resolved_database_url)
    market_factor_study_cache: dict[str, tuple[float, dict[str, object]]] = {}
    market_factor_study_lock = threading.Lock()
    market_factor_study_ttl_seconds = 3600.0
    with session_factory() as session:
        ensure_runtime_defaults(session)
        session.commit()

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    tick_interval_seconds = max(int(os.getenv("ASHARE_BACKGROUND_OPS_TICK_SECONDS", "60")), 15)
    background_ops_enabled = (
        enable_background_ops_tick
        if enable_background_ops_tick is not None
        else os.getenv("ASHARE_DISABLE_BACKGROUND_OPS_TICK", "").strip().lower() not in {"1", "true", "yes", "on"}
    )

    async def background_operations_loop(stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                with session_factory() as session:
                    run_operations_tick(session)
            except Exception:
                LOGGER.exception("background operations tick failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=tick_interval_seconds)
            except TimeoutError:
                continue

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not background_ops_enabled:
            yield
            return
        stop_event = asyncio.Event()
        task = asyncio.create_task(background_operations_loop(stop_event))
        app.state.background_ops_stop_event = stop_event
        app.state.background_ops_task = task
        try:
            yield
        finally:
            stop_event.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="A-share Evidence Foundation",
        version="0.1.0",
        summary="Evidence-first market/news/model/recommendation data layer.",
        lifespan=lifespan,
    )
    cors_origins = [
        origin.strip()
        for origin in os.getenv("ASHARE_CORS_ALLOW_ORIGINS", "*").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_event_routes(app, get_session, require_stock_access, StockAccessContext)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database_url": resolved_database_url}

    @app.get("/auth/context", response_model=AuthContextResponse)
    def auth_context(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = {
            "actor_login": access.actor_login,
            "actor_role": access.actor_role,
            "target_login": access.target_login,
            "can_act_as": access.can_act_as,
            "auth_mode": access.auth_mode,
            "visible_account_spaces": visible_account_spaces(
                session,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            ),
        }
        session.commit()
        return payload

    @app.get("/runtime/overview", response_model=RuntimeOverviewResponse)
    def runtime_overview(
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return get_runtime_overview(session)

    @app.get("/settings/runtime", response_model=RuntimeSettingsResponse)
    def runtime_settings(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return get_runtime_settings(session)

    @app.get("/policy-governance/active")
    def policy_governance_active(
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return build_policy_governance_summary(session)

    @app.get("/policy-governance/history")
    def policy_governance_history(
        scope: str | None = Query(default=None),
        config_key: str | None = Query(default=None),
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return {
            "items": list_policy_config_versions(session, scope=scope, config_key=config_key),
        }

    @app.get("/policy-governance/audit")
    def policy_governance_audit(
        _access: StockAccessContext = Depends(require_stock_access),
    ) -> dict[str, object]:
        return build_policy_audit_report()

    @app.put("/settings/provider-credentials/{provider_name}")
    def provider_credential_upsert(
        provider_name: str,
        payload: ProviderCredentialUpsertRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            record = upsert_provider_credential(
                session,
                provider_name,
                access_token=payload.access_token,
                base_url=payload.base_url,
                enabled=payload.enabled,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return record

    @app.post("/settings/model-api-keys")
    def model_api_key_create(
        payload: ModelApiKeyCreateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            record = create_model_api_key(
                session,
                name=payload.name,
                provider_name=payload.provider_name,
                model_name=payload.model_name,
                base_url=payload.base_url,
                api_key=payload.api_key,
                enabled=payload.enabled,
                priority=payload.priority,
                make_default=payload.make_default,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return record

    @app.patch("/settings/model-api-keys/{key_id}")
    def model_api_key_update(
        key_id: int,
        payload: ModelApiKeyUpdateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            record = update_model_api_key(
                session,
                key_id,
                name=payload.name,
                provider_name=payload.provider_name,
                model_name=payload.model_name,
                base_url=payload.base_url,
                api_key=payload.api_key,
                enabled=payload.enabled,
                priority=payload.priority,
                make_default=payload.make_default,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return record

    @app.post("/settings/model-api-keys/{key_id}/default")
    def model_api_key_set_default(
        key_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            record = set_default_model_api_key(session, key_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return record

    @app.delete("/settings/model-api-keys/{key_id}", response_model=ModelApiKeyDeleteResponse)
    def model_api_key_remove(
        key_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            payload = delete_model_api_key(session, key_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return payload

    @app.post("/analysis/follow-up", response_model=FollowUpAnalysisResponse)
    def follow_up_analysis(
        payload: FollowUpAnalysisRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            return run_follow_up_analysis(
                session,
                symbol=payload.symbol,
                question=payload.question,
                model_api_key_id=payload.model_api_key_id,
                failover_enabled=payload.failover_enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/manual-research/requests", response_model=ManualResearchRequestView)
    def manual_research_request_create(
        payload: ManualResearchRequestCreateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = create_manual_research_request(
                session,
                symbol=payload.symbol,
                question=payload.question,
                trigger_source=payload.trigger_source,
                requested_by=access.actor_login,
                executor_kind=payload.executor_kind,
                model_api_key_id=payload.model_api_key_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.get("/manual-research/requests", response_model=ManualResearchRequestListResponse)
    def manual_research_request_list(
        symbol: str | None = Query(default=None),
        status: str | None = Query(default=None),
        executor_kind: str | None = Query(default=None),
        include_superseded: bool = Query(default=False),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return list_manual_research_requests(
            session,
            symbol=symbol,
            status=status,
            executor_kind=executor_kind,
            include_superseded=include_superseded,
        )

    @app.get("/manual-research/requests/{request_id}", response_model=ManualResearchRequestView)
    def manual_research_request_detail(
        request_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            return get_manual_research_request(session, request_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/manual-research/requests/{request_id}/execute", response_model=ManualResearchRequestView)
    def manual_research_request_execute(
        request_id: int,
        payload: ManualResearchRequestExecuteRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = execute_manual_research_request(
                session,
                request_id=request_id,
                failover_enabled=payload.failover_enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/manual-research/requests/{request_id}/complete", response_model=ManualResearchRequestView)
    def manual_research_request_complete(
        request_id: int,
        payload: ManualResearchRequestCompleteRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = complete_manual_research_request(
                session,
                request_id=request_id,
                summary=payload.summary,
                review_verdict=payload.review_verdict,
                risks=payload.risks,
                disagreements=payload.disagreements,
                decision_note=payload.decision_note,
                citations=payload.citations,
                answer=payload.answer,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/manual-research/requests/{request_id}/fail", response_model=ManualResearchRequestView)
    def manual_research_request_fail(
        request_id: int,
        payload: ManualResearchRequestFailRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = fail_manual_research_request(
                session,
                request_id=request_id,
                failure_reason=payload.failure_reason,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/manual-research/requests/{request_id}/retry", response_model=ManualResearchRequestView)
    def manual_research_request_retry(
        request_id: int,
        payload: ManualResearchRequestRetryRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = retry_manual_research_request(
                session,
                request_id=request_id,
                requested_by=payload.requested_by or access.actor_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.get("/shortpick-lab/runs", response_model=ShortpickRunListResponse)
    def shortpick_run_list(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: str | None = Query(default=None),
        date_from: date | None = Query(default=None),
        date_to: date | None = Query(default=None),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_shortpick_runs(
            session,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
            information_mode=SHORTPICK_INFORMATION_MODE,
            include_raw=False,
            include_candidates=False,
            compact_summary=True,
        )

    @app.get("/shortpick-lab/runs/{run_id}", response_model=ShortpickRunView)
    def shortpick_run_detail(
        run_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_shortpick_run(session, run_id, include_raw=access.actor_role == "root")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/shortpick-lab/candidates", response_model=ShortpickCandidateListResponse)
    def shortpick_candidate_list(
        run_id: int | None = Query(default=None),
        model: str | None = Query(default=None),
        priority: str | None = Query(default=None),
        validation_status: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_shortpick_candidates(
            session,
            run_id=run_id,
            model=model,
            priority=priority,
            validation_status=validation_status,
            limit=limit,
            include_raw=access.actor_role == "root",
        )

    @app.get("/shortpick-lab/candidates/{candidate_id}", response_model=ShortpickCandidateView)
    def shortpick_candidate_detail(
        candidate_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_shortpick_candidate(session, candidate_id, include_raw=access.actor_role == "root")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/shortpick-lab/validation-queue", response_model=ShortpickValidationQueueResponse)
    def shortpick_validation_queue(
        run_id: int | None = Query(default=None),
        status: str | None = Query(default=None),
        horizon: int | None = Query(default=None, ge=1, le=60),
        model: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        date_from: date | None = Query(default=None),
        date_to: date | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_shortpick_validation_queue(
            session,
            run_id=run_id,
            status=status,
            horizon=horizon,
            model=model,
            symbol=symbol,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    @app.get("/shortpick-lab/model-feedback", response_model=ShortpickModelFeedbackResponse)
    def shortpick_model_feedback(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return build_shortpick_model_feedback(session)

    @app.get("/shortpick-lab/market-factor-study")
    def shortpick_market_factor_study(
        benchmark_mode: str = Query(default="universe_equal_weight"),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        now = time.monotonic()
        cached = market_factor_study_cache.get(benchmark_mode)
        if cached and now - cached[0] < market_factor_study_ttl_seconds:
            return cached[1]
        try:
            with market_factor_study_lock:
                now = time.monotonic()
                cached = market_factor_study_cache.get(benchmark_mode)
                if cached and now - cached[0] < market_factor_study_ttl_seconds:
                    return cached[1]
                enriched = _load_shortpick_market_factor_study_artifact(benchmark_mode)
                market_factor_study_cache[benchmark_mode] = (time.monotonic(), enriched)
                return enriched
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/shortpick-lab/paper-tracking")
    def shortpick_paper_tracking(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return _build_shortpick_paper_tracking_ledger(session)

    @app.get("/shortpick-lab/replay-runs", response_model=ShortpickRunListResponse)
    def shortpick_replay_run_list(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: str | None = Query(default=None),
        date_from: date | None = Query(default=None),
        date_to: date | None = Query(default=None),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_shortpick_replay_runs(
            session,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
            include_raw=False,
        )

    @app.get("/shortpick-lab/replay-runs/{run_id}", response_model=ShortpickRunView)
    def shortpick_replay_run_detail(
        run_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_shortpick_replay_run(session, run_id, include_raw=access.actor_role == "root")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/shortpick-lab/replay-runs/{run_id}/candidates", response_model=ShortpickCandidateListResponse)
    def shortpick_replay_candidate_list(
        run_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return list_shortpick_replay_candidates(session, run_id=run_id, include_raw=access.actor_role == "root")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/shortpick-lab/replay-runs/{run_id}/sources")
    def shortpick_replay_sources(
        run_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_shortpick_replay_sources(session, run_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/shortpick-lab/replay-runs/{run_id}/feedback")
    def shortpick_replay_feedback(
        run_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            get_shortpick_replay_run(session, run_id, include_raw=False)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            return _load_shortpick_replay_feedback_from_cache(run_id)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/shortpick-lab/replay-feedback")
    def shortpick_replay_aggregate_feedback(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return _load_shortpick_replay_feedback_from_cache(run_id=None)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/shortpick-lab/runs", response_model=ShortpickRunView)
    def shortpick_run_create(
        payload: ShortpickRunCreateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = run_shortpick_experiment(
                session,
                run_date=payload.run_date,
                rounds_per_model=payload.rounds_per_model,
                triggered_by=access.actor_login,
                trigger_source="manual_api",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/shortpick-lab/runs/{run_id}/validate")
    def shortpick_run_validate(
        run_id: int,
        payload: ShortpickRunValidateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = validate_shortpick_run(session, run_id, horizons=payload.horizons)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/shortpick-lab/runs/{run_id}/retry-failed-rounds")
    def shortpick_run_retry_failed_rounds(
        run_id: int,
        payload: ShortpickRetryFailedRoundsRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = retry_failed_shortpick_rounds(session, run_id, max_rounds=payload.max_rounds)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.get("/watchlist", response_model=WatchlistResponse)
    def watchlist(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = list_watchlist_entries(
            session,
            target_login=access.target_login,
            actor_login=access.actor_login,
            actor_role=access.actor_role,
        )
        session.commit()
        return payload

    @app.post("/watchlist", response_model=WatchlistMutationResponse)
    def watchlist_add(
        payload: WatchlistCreateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            item = add_watchlist_symbol(
                session,
                payload.symbol,
                stock_name=payload.name,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        message = (
            f"已将 {item['name']}（{item['symbol']}）加入自选池并完成真实数据分析。"
            if item["analysis_status"] == "ready" and not item.get("last_error")
            else f"已将 {item['name']}（{item['symbol']}）加入自选池，但当前未能完成最新真实分析。"
        )
        return {
            "item": item,
            "message": message,
        }

    @app.post("/watchlist/{symbol}/refresh", response_model=WatchlistMutationResponse)
    def watchlist_refresh(
        symbol: str,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            item = refresh_watchlist_symbol(
                session,
                symbol,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        message = (
            f"已用最新真实数据刷新 {item['name']}（{item['symbol']}）。"
            if item["analysis_status"] == "ready" and not item.get("last_error")
            else f"已尝试刷新 {item['name']}（{item['symbol']}），当前继续保留已有真实结果或等待数据补齐。"
        )
        return {
            "item": item,
            "message": message,
        }

    @app.delete("/watchlist/{symbol}", response_model=WatchlistDeleteResponse)
    def watchlist_remove(
        symbol: str,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return remove_watchlist_symbol(
                session,
                symbol,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/stocks/{symbol}/recommendations/latest", response_model=LatestRecommendationResponse)
    def latest_recommendation(
        symbol: str,
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = get_latest_recommendation_summary(session, symbol)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"No recommendation found for {symbol}.")
        return payload

    @app.get("/stocks/{symbol}/dashboard", response_model=StockDashboardResponse)
    def stock_dashboard(
        symbol: str,
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_stock_dashboard(session, symbol)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/dashboard/candidates", response_model=CandidateListResponse)
    def dashboard_candidates(
        limit: int = Query(default=8, ge=1, le=20),
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_candidate_recommendations(session, limit=limit)

    @app.get("/dashboard/glossary")
    def dashboard_glossary(_access: StockAccessContext = Depends(require_stock_access)) -> list[dict[str, str]]:
        return get_glossary_entries()

    @app.get("/dashboard/scheduled-refresh-status", response_model=ScheduledRefreshStatusView)
    def dashboard_scheduled_refresh_status(
        _access: StockAccessContext = Depends(require_stock_access),
    ) -> dict[str, object]:
        return get_scheduled_refresh_status()

    @app.get("/dashboard/operations", response_model=OperationsDashboardResponse)
    def dashboard_operations(
        access: StockAccessContext = Depends(require_stock_access),
        sample_symbol: str = Query(default="600519.SH"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        run_operations_tick(session)
        return build_operations_dashboard(
            session,
            sample_symbol,
            include_simulation_workspace=True,
            target_login=access.target_login,
        )

    @app.get("/dashboard/operations/summary", response_model=OperationsDashboardResponse)
    def dashboard_operations_summary(
        access: StockAccessContext = Depends(require_stock_access),
        sample_symbol: str = Query(default="600519.SH"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        run_operations_tick(session)
        return build_operations_summary(
            session,
            sample_symbol,
            target_login=access.target_login,
        )

    @app.get("/dashboard/operations/details")
    def dashboard_operations_details(
        access: StockAccessContext = Depends(require_stock_access),
        section: str = Query(default="portfolios"),
        sample_symbol: str = Query(default="600519.SH"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            return build_operations_detail(
                session,
                section=section,
                sample_symbol=sample_symbol,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/dashboard/improvement-suggestions/summary")
    def dashboard_improvement_suggestions_summary(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return suggestion_summary(session)

    @app.get("/dashboard/improvement-suggestions/details")
    def dashboard_improvement_suggestions_details(
        access: StockAccessContext = Depends(require_stock_access),
        status: str | None = Query(default=None),
        category: str | None = Query(default=None),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return suggestion_details(session, status=status, category=category)

    @app.post("/dashboard/improvement-suggestions/run")
    def dashboard_improvement_suggestions_run(
        access: StockAccessContext = Depends(require_stock_access),
        window_days: int = Query(default=7, ge=1, le=60),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return run_improvement_suggestion_review(session, window_days=window_days)

    @app.post("/dashboard/improvement-suggestions/{suggestion_id}/status")
    def dashboard_improvement_suggestion_status(
        suggestion_id: str,
        payload: dict[str, str] = Body(default_factory=dict),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            return update_suggestion_status(
                session,
                suggestion_id=suggestion_id,
                status=str(payload.get("status") or ""),
                reason=str(payload.get("reason") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/dashboard/improvement-suggestions/{suggestion_id}/accept-plan")
    def dashboard_improvement_suggestion_accept_plan(
        suggestion_id: str,
        payload: dict[str, str] = Body(default_factory=dict),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            return accept_suggestion_for_plan(
                session,
                suggestion_id=suggestion_id,
                model=str(payload.get("model") or ""),
                reason=str(payload.get("reason") or "进入计划池"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/simulation/workspace", response_model=SimulationWorkspaceResponse)
    def simulation_workspace(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = get_simulation_workspace(
            session,
            owner_login=access.target_login,
            actor_login=access.actor_login,
            actor_role=access.actor_role,
        )
        session.commit()
        return payload

    @app.put("/simulation/config", response_model=SimulationControlActionResponse)
    def simulation_config(
        payload: SimulationConfigRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = update_simulation_config(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                initial_cash=payload.initial_cash,
                watch_symbols=payload.watch_symbols,
                focus_symbol=payload.focus_symbol,
                step_interval_seconds=payload.step_interval_seconds,
                auto_execute_model=payload.auto_execute_model,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "模拟参数已更新。"}

    @app.post("/simulation/start", response_model=SimulationControlActionResponse)
    def simulation_start(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = start_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已启动。"}

    @app.post("/simulation/pause", response_model=SimulationControlActionResponse)
    def simulation_pause(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = pause_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已暂停。"}

    @app.post("/simulation/resume", response_model=SimulationControlActionResponse)
    def simulation_resume(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = resume_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已恢复。"}

    @app.post("/simulation/step", response_model=SimulationControlActionResponse)
    def simulation_step(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = step_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "已推进一个刷新步。"}

    @app.post("/simulation/restart", response_model=SimulationControlActionResponse)
    def simulation_restart(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        workspace = restart_simulation_session(
            session,
            owner_login=access.target_login,
            actor_login=access.actor_login,
            actor_role=access.actor_role,
        )
        session.commit()
        return {"workspace": workspace, "message": "已重启为新的双轨模拟进程。"}

    @app.post("/simulation/end", response_model=SimulationControlActionResponse)
    def simulation_end(
        payload: SimulationEndRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = end_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                confirm=payload.confirm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已结束。"}

    @app.post("/simulation/manual-order", response_model=SimulationControlActionResponse)
    def simulation_manual_order(
        payload: ManualSimulationOrderRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = place_manual_order(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                symbol=payload.symbol,
                side=payload.side,
                quantity=payload.quantity,
                reason=payload.reason,
                limit_price=payload.limit_price,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "用户轨道模拟单已成交。"}

    @app.get("/recommendations/{recommendation_id}/trace", response_model=RecommendationTraceResponse)
    def recommendation_trace(
        recommendation_id: int,
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_recommendation_trace(session, recommendation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app

app = create_app()
