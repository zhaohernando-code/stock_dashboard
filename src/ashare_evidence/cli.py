from __future__ import annotations

import argparse
import json
import os
import socket
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ashare_evidence.benchmark import sync_benchmark_index_bars
from ashare_evidence.cli_autonomous_flow import (
    add_autonomous_flow_parsers,
    handle_phase5_local_cycle_step_command,
)
from ashare_evidence.cli_event import add_event_check_parser, handle_event_check, run_refresh_event_checks
from ashare_evidence.cli_governance import add_governance_parsers, handle_governance_command
from ashare_evidence.cli_research import add_research_parsers, handle_factor_observation, handle_weight_sweep
from ashare_evidence.dashboard import get_glossary_entries, get_stock_dashboard, list_candidate_recommendations
from ashare_evidence.db import init_database, preflight_database_writable, session_scope
from ashare_evidence.frontend_projections import refresh_frontend_projections
from ashare_evidence.improvement_suggestions import run_improvement_suggestion_review
from ashare_evidence.intraday_market import sync_intraday_market
from ashare_evidence.model_exploration_workflow import run_shortpick_model_exploration_workbench
from ashare_evidence.model_feature_diagnostics import run_model_feature_diagnostics
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.phase2 import rebuild_phase2_research_state
from ashare_evidence.phase2.holding_policy_experiments import (
    build_phase5_holding_policy_experiment,
    build_phase5_holding_policy_experiment_artifact,
)
from ashare_evidence.phase2.holding_policy_study import (
    build_phase5_holding_policy_study,
    build_phase5_holding_policy_study_artifact,
)
from ashare_evidence.phase2.horizon_study import build_phase5_horizon_study, build_phase5_horizon_study_artifact
from ashare_evidence.phase2.producer_contract_study import (
    build_phase5_producer_contract_study,
    build_phase5_producer_contract_study_artifact,
)
from ashare_evidence.policy_config_loader import (
    activate_policy_config_version,
    build_policy_governance_summary,
    create_policy_config_version,
    list_policy_config_versions,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_holding_policy_experiment_artifact_if_exists,
    read_phase5_holding_policy_study_artifact_if_exists,
    read_phase5_horizon_study_artifact_if_exists,
    read_phase5_producer_contract_study_artifact_if_exists,
    write_phase5_holding_policy_experiment_artifact,
    write_phase5_holding_policy_study_artifact,
    write_phase5_horizon_study_artifact,
    write_phase5_producer_contract_study_artifact,
)
from ashare_evidence.services import get_latest_recommendation_summary, get_recommendation_trace
from ashare_evidence.shortpick_combined_ledger_writer import (
    load_shortpick_combined_ledger_inputs,
    materialize_shortpick_combined_ledger_from_artifact_root,
    run_shortpick_combined_ledger_backfill_artifact,
)
from ashare_evidence.shortpick_lab import (
    retry_failed_shortpick_rounds,
    run_shortpick_experiment,
    run_shortpick_intraday_same_day_control,
    validate_recent_shortpick_runs,
    validate_shortpick_run,
)
from ashare_evidence.shortpick_market_factor_study import build_shortpick_market_factor_study
from ashare_evidence.shortpick_paper_divergence_attribution import (
    build_shortpick_paper_divergence_attribution_artifact,
    validate_shortpick_paper_divergence_attribution_artifact,
    write_shortpick_paper_divergence_attribution_artifact,
)
from ashare_evidence.shortpick_portfolio_backtest import (
    build_shortpick_portfolio_backtest,
    write_shortpick_portfolio_backtest,
)
from ashare_evidence.shortpick_ranked_pool_replay_input import (
    enrich_shortpick_replay_paper_tracking_with_reconstructed_ranked_pools,
)
from ashare_evidence.shortpick_replay import (
    refresh_shortpick_replay_feedback_cache,
    run_shortpick_historical_replay,
    run_shortpick_historical_replay_concurrent,
    run_shortpick_historical_replay_dates,
    run_shortpick_replay_distillation,
    run_shortpick_replay_distillation_concurrent,
    run_shortpick_replay_factor_rank_experiment,
    run_shortpick_replay_hard_veto_experiment,
    run_shortpick_replay_rejection,
)
from ashare_evidence.shortpick_strategy_backtest_runner import run_shortpick_historical_backtest_requests
from ashare_evidence.shortpick_strategy_governance import build_shortpick_credible_control_comparison_line_plan
from ashare_evidence.shortpick_strategy_replay_runner import run_shortpick_retrospective_forward_replay_requests
from ashare_evidence.shortpick_strategy_retirement_writer import (
    load_shortpick_strategy_retirement_inputs,
    run_shortpick_strategy_retirement_artifact,
)
from ashare_evidence.shortpick_strategy_slices import build_shortpick_strategy_slice_evidence
from ashare_evidence.shortpick_v2_h10_artifact_validation import validate_shortpick_v2_h10_artifacts
from ashare_evidence.shortpick_v2_h10_execution_decomposition import (
    build_shortpick_v2_h10_execution_decomposition_artifact,
    write_shortpick_v2_h10_execution_decomposition_artifact,
)
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    build_shortpick_v2_h10_paper_governance_artifact_from_paths,
    validate_shortpick_v2_h10_paper_governance_artifact,
    write_shortpick_v2_h10_paper_governance_artifact,
)
from ashare_evidence.shortpick_v2_h10_parameter_significance import (
    build_shortpick_v2_h10_parameter_significance_artifact,
    validate_shortpick_v2_h10_parameter_significance_artifact,
    write_shortpick_v2_h10_parameter_significance_artifact,
)
from ashare_evidence.shortpick_v2_h10_rank_ablation import (
    build_shortpick_v2_h10_rank_ablation_artifact,
    validate_shortpick_v2_h10_rank_ablation_artifact,
    write_shortpick_v2_h10_rank_ablation_artifact,
)
from ashare_evidence.shortpick_v2_h10_robustness import (
    build_shortpick_v2_h10_robustness_artifact,
    write_shortpick_v2_h10_robustness_artifact,
)
from ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix import (
    build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact,
    validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact,
    write_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact,
)
from ashare_evidence.shortpick_v2_next_diagnostics import (
    build_shortpick_v2_next_diagnostics_artifact,
    validate_shortpick_v2_next_diagnostics_artifact,
    write_shortpick_v2_next_diagnostics_artifact,
)
from ashare_evidence.shortpick_v2_oos_loss_filter import (
    build_shortpick_v2_oos_loss_filter_artifact,
    validate_shortpick_v2_oos_loss_filter_artifact,
    write_shortpick_v2_oos_loss_filter_artifact,
)
from ashare_evidence.shortpick_v2_oos_position_rank_diagnostics import (
    build_shortpick_v2_oos_position_rank_diagnostics_artifact,
    validate_shortpick_v2_oos_position_rank_diagnostics_artifact,
    write_shortpick_v2_oos_position_rank_diagnostics_artifact,
)
from ashare_evidence.shortpick_v2_out_of_sample_risk import (
    build_shortpick_v2_out_of_sample_risk_artifact,
    validate_shortpick_v2_out_of_sample_risk_artifact,
    write_shortpick_v2_out_of_sample_risk_artifact,
)
from ashare_evidence.shortpick_v2_ranking_backtest import (
    build_shortpick_v2_ranking_backtest_artifact,
    validate_shortpick_v2_ranking_backtest_artifact,
    write_shortpick_v2_ranking_backtest_artifact,
)
from ashare_evidence.shortpick_v2_replay import (
    build_shortpick_v2_replay_artifact,
    write_shortpick_v2_replay_artifact,
)
from ashare_evidence.shortpick_v2_risk_switch_experiment import (
    build_shortpick_v2_risk_switch_experiment_artifact,
    validate_shortpick_v2_risk_switch_experiment_artifact,
    write_shortpick_v2_risk_switch_experiment_artifact,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    SELECTION_THRESHOLD_PROFILE_STANDARD,
    SELECTION_THRESHOLD_PROFILES,
    build_shortpick_v2_rule_selection_artifact_from_path,
    write_shortpick_v2_rule_selection_artifact,
)
from ashare_evidence.shortpick_v2_strategy_search import (
    STRATEGY_SEARCH_BATCH_INITIAL,
    STRATEGY_SEARCH_BATCHES,
    build_shortpick_v2_strategy_search_artifact,
    write_shortpick_v2_strategy_search_artifact,
)
from ashare_evidence.shortpick_v2_theme_position_diagnostics import (
    build_shortpick_v2_theme_position_diagnostics_artifact,
    validate_shortpick_v2_theme_position_diagnostics_artifact,
    write_shortpick_v2_theme_position_diagnostics_artifact,
)
from ashare_evidence.simulation import restart_simulation_session, step_simulation_session
from ashare_evidence.stock_master import DEFAULT_AKSHARE_TIMEOUT_SECONDS
from ashare_evidence.watchlist import active_watchlist_symbols, refresh_watchlist_symbol


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _scheduled_refresh_now() -> datetime:
    return datetime.now(ZoneInfo(os.environ.get("ASHARE_REFRESH_TIMEZONE", "Asia/Shanghai")))


def _scheduled_time_value(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _assert_postmarket_daily_slot_allowed(target_date: date | None = None) -> None:
    if os.environ.get("ASHARE_ALLOW_EARLY_DAILY_REFRESH") == "1":
        return
    now = _scheduled_refresh_now()
    effective_date = target_date or now.date()
    if effective_date > now.date():
        raise RuntimeError(
            f"scheduled daily analysis for future date {effective_date.isoformat()} is blocked; "
            "set ASHARE_ALLOW_EARLY_DAILY_REFRESH=1 only for an explicit manual override."
        )
    if effective_date != now.date() or now.isoweekday() > 5:
        return
    postmarket_at = _scheduled_time_value("ASHARE_POSTMARKET_DAILY_REFRESH_AT", "16:20")
    if now.strftime("%H:%M") < postmarket_at:
        raise RuntimeError(
            f"scheduled daily analysis for {effective_date.isoformat()} is blocked before {postmarket_at}; "
            "set ASHARE_ALLOW_EARLY_DAILY_REFRESH=1 only for an explicit manual override."
        )


def _assert_intraday_same_day_slot_allowed(target_date: date | None = None) -> None:
    if os.environ.get("ASHARE_ALLOW_EARLY_DAILY_REFRESH") == "1":
        return
    now = _scheduled_refresh_now()
    effective_date = target_date or now.date()
    if effective_date > now.date():
        raise RuntimeError(
            f"scheduled intraday same-day shortpick for future date {effective_date.isoformat()} is blocked; "
            "set ASHARE_ALLOW_EARLY_DAILY_REFRESH=1 only for an explicit manual override."
        )
    if effective_date != now.date() or now.isoweekday() > 5:
        return
    now_hhmm = now.strftime("%H:%M")
    intraday_at = _scheduled_time_value("ASHARE_INTRADAY_SAME_DAY_REFRESH_AT", "13:55")
    postmarket_at = _scheduled_time_value("ASHARE_POSTMARKET_DAILY_REFRESH_AT", "16:20")
    if now_hhmm < intraday_at or now_hhmm >= postmarket_at:
        raise RuntimeError(
            f"scheduled intraday same-day shortpick for {effective_date.isoformat()} is blocked outside "
            f"{intraday_at}-{postmarket_at}."
        )


def _parse_shortpick_replay_dates(date_values: list[str], dates_file: str | None) -> list[date]:
    raw_values = list(date_values or [])
    if dates_file:
        file_payload = Path(dates_file).read_text(encoding="utf-8").strip()
        if file_payload:
            if file_payload.startswith("["):
                parsed = json.loads(file_payload)
                raw_values.extend(str(item) for item in parsed)
            elif file_payload.startswith("{"):
                parsed = json.loads(file_payload)
                raw_values.extend(str(item) for item in parsed.get("dates") or [])
            else:
                raw_values.extend(line.strip() for line in file_payload.splitlines() if line.strip())
    return sorted({date.fromisoformat(item) for item in raw_values})


@contextmanager
def _refresh_socket_timeout(timeout_seconds: int = DEFAULT_AKSHARE_TIMEOUT_SECONDS):
    previous_timeout = socket.getdefaulttimeout()
    original_urlopen = urllib.request.urlopen
    try:
        import requests
    except Exception:
        requests = None
        original_request = None
    else:
        original_request = requests.sessions.Session.request

    def _urlopen_with_timeout(*args, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = timeout_seconds
        return original_urlopen(*args, **kwargs)

    def _request_with_timeout(self, method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = timeout_seconds
        return original_request(self, method, url, **kwargs)

    socket.setdefaulttimeout(timeout_seconds)
    urllib.request.urlopen = _urlopen_with_timeout
    if requests is not None and original_request is not None:
        requests.sessions.Session.request = _request_with_timeout
    try:
        yield
    finally:
        if requests is not None and original_request is not None:
            requests.sessions.Session.request = original_request
        urllib.request.urlopen = original_urlopen
        socket.setdefaulttimeout(previous_timeout)


def _should_initialize_database(database_url: str | None) -> bool:
    if not database_url:
        return True
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return True
    return not Path(database_url.removeprefix("sqlite:///")).exists()


# Commands in this set are pure file/plan commands and may omit --database-url.
NO_DB_COMMANDS = {
    "shortpick-model-feature-diagnostics-run",
    "shortpick-governance-credible-control-plan",
    "shortpick-v2-h10-artifact-validate",
    "shortpick-v2-h10-paper-governance",
    "shortpick-v2-h10-paper-governance-validate",
    "shortpick-v2-h10-parameter-significance-validate",
    "shortpick-v2-h10-rank-ablation-validate",
    "shortpick-v2-h10-weekday-drawdown-notional-matrix-validate",
    "shortpick-v2-next-diagnostics-validate",
    "shortpick-v2-oos-loss-filter-validate",
    "shortpick-v2-oos-position-rank-diagnostics-validate",
    "shortpick-v2-theme-position-diagnostics-validate",
    "shortpick-v2-out-of-sample-risk-validate",
    "shortpick-v2-ranking-backtest-validate",
    "shortpick-v2-risk-switch-experiment-validate",
    "shortpick-paper-divergence-attribution-validate",
}


def _governance_requests_from_payload(
    payload: object,
    *,
    nested_plan_key: str,
    path_label: str = "request-path",
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError(f"{path_label} must contain a request object or an object with a requests list")
    requests = payload.get("requests")
    nested_plan = payload.get(nested_plan_key)
    if requests is None and isinstance(nested_plan, dict):
        requests = nested_plan.get("requests")
    if requests is None:
        requests = [payload]
    if not isinstance(requests, list):
        raise ValueError(f"{path_label} must contain a request object or an object with a requests list")
    return [dict(item) for item in requests if isinstance(item, dict)]


def _filter_governance_requests(
    requests: list[dict[str, Any]],
    *,
    request_ids: list[str] | None,
    control_group_ids: list[str] | None,
) -> list[dict[str, Any]]:
    selected_request_ids = {str(value) for value in request_ids or [] if str(value)}
    selected_control_group_ids = {str(value) for value in control_group_ids or [] if str(value)}
    if not selected_request_ids and not selected_control_group_ids:
        return requests
    filtered = [
        request
        for request in requests
        if (
            (selected_request_ids and str(request.get("request_id") or "") in selected_request_ids)
            or (
                selected_control_group_ids
                and str(request.get("control_group_id") or "") in selected_control_group_ids
            )
        )
    ]
    if not filtered:
        raise ValueError("No governance requests matched --request-id or --control-group-id")
    return filtered


def _phase5_horizon_study_output(
    session,
    *,
    database_url: str | None,
    symbols: list[str] | None = None,
    include_history: bool,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_horizon_study(
        session,
        symbols=symbols,
        include_history=include_history,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_horizon_study_artifact(payload)
    prior_artifact = read_phase5_horizon_study_artifact_if_exists(artifact.artifact_id, root=artifact_root)
    artifact_path = write_phase5_horizon_study_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }

def _phase5_holding_policy_study_output(
    session,
    *,
    database_url: str | None,
    portfolio_keys: list[str] | None = None,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_holding_policy_study(
        session,
        portfolio_keys=portfolio_keys,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_holding_policy_study_artifact(payload)
    prior_artifact = read_phase5_holding_policy_study_artifact_if_exists(artifact.artifact_id, root=artifact_root)
    artifact_path = write_phase5_holding_policy_study_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }
def _phase5_holding_policy_experiment_output(
    session,
    *,
    database_url: str | None,
    experiment_id: str,
    symbols: list[str] | None = None,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_holding_policy_experiment(
        session,
        experiment_id=experiment_id,
        symbols=symbols,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_holding_policy_experiment_artifact(payload)
    prior_artifact = read_phase5_holding_policy_experiment_artifact_if_exists(
        artifact.artifact_id,
        root=artifact_root,
    )
    artifact_path = write_phase5_holding_policy_experiment_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }

def _phase5_producer_contract_study_output(
    session,
    *,
    database_url: str | None,
    symbols: list[str] | None,
    include_history: bool,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_producer_contract_study(
        session,
        symbols=symbols,
        include_history=include_history,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_producer_contract_study_artifact(payload)
    prior_artifact = read_phase5_producer_contract_study_artifact_if_exists(artifact.artifact_id, root=artifact_root)
    artifact_path = write_phase5_producer_contract_study_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }

def _refresh_runtime_data_output(
    session,
    *,
    analysis_only: bool,
    ops_only: bool,
    skip_simulation: bool,
) -> dict[str, Any]:
    symbols = active_watchlist_symbols(session)
    run_analysis_refresh = not ops_only
    run_ops_refresh = not analysis_only
    refreshed = [refresh_watchlist_symbol(session, symbol) for symbol in symbols] if run_analysis_refresh else []
    event_results = run_refresh_event_checks(session, [item["symbol"] for item in refreshed]) if run_analysis_refresh and refreshed else []
    intraday = sync_intraday_market(session, symbols) if run_ops_refresh else None
    # Benchmark index bars feed shortpick validation excess-return. The daily
    # refresh runs --analysis-only (run_ops_refresh=False); gating benchmarks on
    # ops-only left individual stocks advancing to the latest trading day while
    # benchmarks lagged a day, stranding 5d/10d exits at pending_benchmark_data.
    # Sync benchmarks whenever any refresh runs so they stay on the same day.
    benchmark_bars = sync_benchmark_index_bars(session) if (run_ops_refresh or run_analysis_refresh) else None
    simulation = None
    if not skip_simulation and run_analysis_refresh:
        restart_simulation_session(session)
        simulation = step_simulation_session(session)
        if symbols:
            rebuild_phase2_research_state(
                session,
                symbols=set(symbols),
                active_symbols=set(symbols),
            )
    return {
        "analysis_refreshed": run_analysis_refresh,
        "ops_refreshed": run_ops_refresh,
        "refreshed_symbols": [item["symbol"] for item in refreshed],
        "latest_generated_at": {
            item["symbol"]: item.get("latest_generated_at")
            for item in refreshed
        },
        "intraday_market": intraday,
        "benchmark_index_bars": benchmark_bars,
        "simulation_last_data_time": None if simulation is None else simulation["session"]["last_data_time"],
        "simulation_current_step": None if simulation is None else simulation["session"]["current_step"], "event_analyses_triggered": len(event_results), "event_analyses": event_results[:3] if event_results else [],
    }

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-first data foundation CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create database tables.")
    init_db.add_argument("--database-url", default=None)
    latest = subparsers.add_parser("latest", help="Show the latest recommendation for a stock.")
    latest.add_argument("--database-url", default=None)
    latest.add_argument("--symbol", default="600519.SH")
    candidates = subparsers.add_parser("candidates", help="Show ranked dashboard candidates.")
    candidates.add_argument("--database-url", default=None)
    candidates.add_argument("--limit", type=int, default=8)

    stock_dashboard = subparsers.add_parser("stock-dashboard", help="Show the user-facing dashboard payload for a stock.")
    stock_dashboard.add_argument("--database-url", default=None)
    stock_dashboard.add_argument("--symbol", default="600519.SH")

    operations = subparsers.add_parser("operations", help="Show paper trading, replay, and beta-readiness payload.")
    operations.add_argument("--database-url", default=None)
    operations.add_argument("--sample-symbol", default="600519.SH")

    horizon_study = subparsers.add_parser(
        "phase5-horizon-study",
        help="Aggregate Phase 5 candidate-horizon comparison across the active watchlist or a custom symbol scope.",
    )
    horizon_study.add_argument("--database-url", default=None)
    horizon_study.add_argument("--symbol", action="append", default=None)
    horizon_study.add_argument(
        "--include-history",
        action="store_true",
        help="Use the latest recommendation for each symbol + as-of day instead of only the current latest recommendation.",
    )
    horizon_study.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 horizon-study snapshot under the database-linked artifacts root.",
    )

    holding_policy_study = subparsers.add_parser(
        "phase5-holding-policy-study",
        help="Aggregate Phase 5 simulation holding-policy turnover, cost, and stability evidence across auto-model portfolios.",
    )
    holding_policy_study.add_argument("--database-url", default=None)
    holding_policy_study.add_argument("--portfolio-key", action="append", default=None)
    holding_policy_study.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 holding-policy study snapshot under the database-linked artifacts root.",
    )

    holding_policy_experiment = subparsers.add_parser(
        "phase5-holding-policy-experiment",
        help="Replay a Phase 5 holding-policy redesign experiment across recommendation history and daily closes.",
    )
    holding_policy_experiment.add_argument("--database-url", default=None)
    holding_policy_experiment.add_argument("--experiment-id", required=True)
    holding_policy_experiment.add_argument("--symbol", action="append", default=None)
    holding_policy_experiment.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 holding-policy experiment snapshot under the database-linked artifacts root.",
    )

    producer_contract_study = subparsers.add_parser(
        "phase5-producer-contract-study",
        help="Compare narrow Phase 5 producer-contract alternatives for zero-news-evidence recommendations.",
    )
    producer_contract_study.add_argument("--database-url", default=None)
    producer_contract_study.add_argument("--symbol", action="append", default=None)
    producer_contract_study.add_argument(
        "--latest-only",
        action="store_true",
        help="Use only the latest preferred recommendation per symbol instead of the full preferred history.",
    )
    producer_contract_study.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 producer-contract study snapshot under the database-linked artifacts root.",
    )

    trace = subparsers.add_parser("trace", help="Show a full evidence trace for a recommendation ID.")
    trace.add_argument("--database-url", default=None)
    trace.add_argument("--recommendation-id", type=int, required=True)

    glossary = subparsers.add_parser("glossary", help="Show the dashboard glossary entries.")
    glossary.add_argument("--database-url", default=None)

    add_autonomous_flow_parsers(subparsers)
    add_governance_parsers(subparsers)

    policy_config = subparsers.add_parser("policy-configs", help="List active and historical governed policy configs.")
    policy_config.add_argument("--database-url", default=None)
    policy_config.add_argument("--scope", default=None)
    policy_config.add_argument("--config-key", default=None)

    policy_config_create = subparsers.add_parser("policy-config-create", help="Create a draft governed policy config version.")
    policy_config_create.add_argument("--database-url", default=None)
    policy_config_create.add_argument("--scope", required=True)
    policy_config_create.add_argument("--config-key", required=True)
    policy_config_create.add_argument("--version", required=True)
    policy_config_create.add_argument("--payload-json", required=True)
    policy_config_create.add_argument("--reason", required=True)
    policy_config_create.add_argument("--evidence-ref", action="append", default=None)
    policy_config_create.add_argument("--created-by", default="root")

    policy_config_activate = subparsers.add_parser("policy-config-activate", help="Activate an existing draft policy config version.")
    policy_config_activate.add_argument("--database-url", default=None)
    policy_config_activate.add_argument("--scope", required=True)
    policy_config_activate.add_argument("--config-key", required=True)
    policy_config_activate.add_argument("--version", required=True)
    policy_config_activate.add_argument("--approved-by", required=True)
    add_event_check_parser(subparsers)
    add_research_parsers(subparsers)

    model_exploration = subparsers.add_parser(
        "shortpick-model-exploration-run",
        help="Run the offline Short Pick model exploration workbench and write research-validation artifacts only.",
    )
    model_exploration.add_argument("--database-url", default=None)
    model_exploration.add_argument("--validation-run-id", required=True)
    model_exploration.add_argument(
        "--as-of-date",
        action="append",
        default=None,
        help="Restrict the universe-date matrix to one YYYY-MM-DD as-of date; may be repeated.",
    )
    model_exploration.add_argument("--max-as-of-dates", type=int, default=None)
    model_exploration.add_argument("--benchmark-symbol", default="000300.SH")
    model_exploration.add_argument(
        "--model-spec-id",
        action="append",
        default=None,
        help="Run only this registered model spec id; may be repeated.",
    )
    model_exploration.add_argument("--min-train-dates", type=int, default=60)
    model_exploration.add_argument("--test-window-dates", type=int, default=20)
    model_exploration.add_argument("--input-snapshot-artifact", default=None)
    model_exploration.add_argument("--feature-matrix-artifact", default=None)
    model_exploration.add_argument("--label-matrix-artifact", default=None)
    model_exploration.add_argument("--artifact-root", default=None)
    model_exploration.add_argument("--no-write-artifacts", action="store_true")

    model_feature_diagnostics = subparsers.add_parser(
        "shortpick-model-feature-diagnostics-run",
        help="Diagnose feature, direction and horizon signal from existing Short Pick model exploration matrices.",
    )
    model_feature_diagnostics.add_argument("--validation-run-id", required=True)
    model_feature_diagnostics.add_argument("--feature-matrix-artifact", required=True)
    model_feature_diagnostics.add_argument("--label-matrix-artifact", required=True)
    model_feature_diagnostics.add_argument("--artifact-root", default=None)
    model_feature_diagnostics.add_argument("--no-write-artifacts", action="store_true")

    refresh_runtime = subparsers.add_parser(
        "refresh-runtime-data",
        help="Refresh analysis and/or ops intraday market data for the current watchlist.",
    )
    refresh_runtime.add_argument("--database-url", default=None)
    refresh_runtime.add_argument("--analysis-only", action="store_true")
    refresh_runtime.add_argument("--ops-only", action="store_true")
    refresh_runtime.add_argument("--skip-simulation", action="store_true")

    sync_benchmarks = subparsers.add_parser(
        "sync-benchmark-index-bars",
        help="Sync CSI benchmark index daily bars for validation and replay studies.",
    )
    sync_benchmarks.add_argument("--database-url", default=None)
    sync_benchmarks.add_argument("--lookback-days", type=int, default=400)

    suggestion_review = subparsers.add_parser(
        "review-improvement-suggestions",
        help="Collect improvement suggestions and run the multi-model audit.",
    )
    suggestion_review.add_argument("--database-url", default=None)
    suggestion_review.add_argument("--window-days", type=int, default=7)

    shortpick_run = subparsers.add_parser(
        "shortpick-lab-run",
        help="Run the isolated native-web short-pick research lab experiment.",
    )
    shortpick_run.add_argument("--database-url", default=None)
    shortpick_run.add_argument("--run-date", default=None)
    shortpick_run.add_argument("--rounds-per-model", type=int, default=5)

    shortpick_intraday = subparsers.add_parser(
        "shortpick-lab-intraday-same-day",
        help="Run the time-boxed intraday same-day entry control using frozen short-pick rules.",
    )
    shortpick_intraday.add_argument("--database-url", default=None)
    shortpick_intraday.add_argument("--run-date", default=None)

    shortpick_validate = subparsers.add_parser(
        "shortpick-lab-validate",
        help="Refresh post-pick validation snapshots for one short-pick lab run.",
    )
    shortpick_validate.add_argument("--database-url", default=None)
    shortpick_validate.add_argument("--run-id", type=int, required=True)
    shortpick_validate.add_argument("--horizon", type=int, action="append", default=None)
    shortpick_validate.add_argument("--existing-market-data-only", action="store_true")

    shortpick_validate_recent = subparsers.add_parser(
        "shortpick-lab-validate-recent",
        help="Refresh post-pick validation snapshots for recent completed short-pick lab runs.",
    )
    shortpick_validate_recent.add_argument("--database-url", default=None)
    shortpick_validate_recent.add_argument("--days", type=int, default=30)
    shortpick_validate_recent.add_argument("--limit", type=int, default=20)
    shortpick_validate_recent.add_argument("--horizon", type=int, action="append", default=None)
    shortpick_validate_recent.add_argument("--existing-market-data-only", action="store_true")

    shortpick_retry_failed = subparsers.add_parser(
        "shortpick-lab-retry-failed",
        help="Retry retryable failed rounds for one short-pick lab run.",
    )
    shortpick_retry_failed.add_argument("--database-url", default=None)
    shortpick_retry_failed.add_argument("--run-id", type=int, required=True)
    shortpick_retry_failed.add_argument("--max-rounds", type=int, default=None)

    shortpick_replay = subparsers.add_parser(
        "shortpick-replay",
        help="Build historical sealed-packet replay runs with sealed-packet LLM and baseline controls.",
    )
    shortpick_replay.add_argument("--database-url", default=None)
    shortpick_replay.add_argument("--start-date", required=True)
    shortpick_replay.add_argument("--end-date", required=True)
    shortpick_replay.add_argument("--rounds", type=int, default=5)
    shortpick_replay.add_argument("--candidate-limit", type=int, default=3)
    shortpick_replay.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_replay.add_argument(
        "--llm-max-workers",
        type=int,
        default=1,
        help="Run sealed-packet LLM requests concurrently while keeping SQLite writes serial.",
    )

    shortpick_replay_dates = subparsers.add_parser(
        "shortpick-replay-dates",
        help="Build historical sealed-packet replay runs for explicit stratified replay dates.",
    )
    shortpick_replay_dates.add_argument("--database-url", default=None)
    shortpick_replay_dates.add_argument(
        "--date",
        dest="dates",
        action="append",
        default=[],
        help="Replay date in YYYY-MM-DD format. Can be provided multiple times.",
    )
    shortpick_replay_dates.add_argument(
        "--dates-file",
        default=None,
        help="JSON array or newline-delimited file of YYYY-MM-DD replay dates.",
    )
    shortpick_replay_dates.add_argument("--rounds", type=int, default=5)
    shortpick_replay_dates.add_argument("--candidate-limit", type=int, default=3)
    shortpick_replay_dates.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )

    shortpick_replay_distill = subparsers.add_parser(
        "shortpick-replay-distill",
        help="Expand historical replay with momentum pools and sealed-packet LLM distillation tracks.",
    )
    shortpick_replay_distill.add_argument("--database-url", default=None)
    shortpick_replay_distill.add_argument("--run-id", type=int, default=None)
    shortpick_replay_distill.add_argument("--start-date", default=None)
    shortpick_replay_distill.add_argument("--end-date", default=None)
    shortpick_replay_distill.add_argument("--momentum-pool-limit", type=int, default=20)
    shortpick_replay_distill.add_argument("--self-distill-limit", type=int, default=3)
    shortpick_replay_distill.add_argument("--momentum-distill-limit", type=int, default=5)
    shortpick_replay_distill.add_argument(
        "--llm-max-workers",
        type=int,
        default=1,
        help="Run distillation LLM requests concurrently while keeping SQLite writes serial.",
    )

    shortpick_replay_reject = subparsers.add_parser(
        "shortpick-replay-reject",
        help="Expand historical replay with LLM reject-only filtering and random reject controls.",
    )
    shortpick_replay_reject.add_argument("--database-url", default=None)
    shortpick_replay_reject.add_argument("--run-id", type=int, default=None)
    shortpick_replay_reject.add_argument("--start-date", default=None)
    shortpick_replay_reject.add_argument("--end-date", default=None)
    shortpick_replay_reject.add_argument("--momentum-pool-limit", type=int, default=40)
    shortpick_replay_reject.add_argument("--rank-limit", type=int, default=5)
    shortpick_replay_reject.add_argument("--reject-max-ratio", type=float, default=0.4)

    shortpick_replay_hard_veto = subparsers.add_parser(
        "shortpick-replay-hard-veto",
        help="Run sealed-packet hard-veto-only replay experiments on expanded momentum pools.",
    )
    shortpick_replay_hard_veto.add_argument("--database-url", default=None)
    shortpick_replay_hard_veto.add_argument("--run-id", type=int, default=None)
    shortpick_replay_hard_veto.add_argument("--start-date", default=None)
    shortpick_replay_hard_veto.add_argument("--end-date", default=None)
    shortpick_replay_hard_veto.add_argument("--momentum-pool-limit", type=int, default=40)
    shortpick_replay_hard_veto.add_argument("--rank-limit", type=int, default=6)
    shortpick_replay_hard_veto.add_argument("--veto-max-ratio", type=float, default=0.15)

    shortpick_replay_factor_rank = subparsers.add_parser(
        "shortpick-replay-factor-rank",
        help="Run deterministic sealed-market feature ranking experiments on expanded momentum pools.",
    )
    shortpick_replay_factor_rank.add_argument("--database-url", default=None)
    shortpick_replay_factor_rank.add_argument("--run-id", type=int, default=None)
    shortpick_replay_factor_rank.add_argument("--start-date", default=None)
    shortpick_replay_factor_rank.add_argument("--end-date", default=None)
    shortpick_replay_factor_rank.add_argument("--momentum-pool-limit", type=int, default=40)
    shortpick_replay_factor_rank.add_argument("--rank-limit", type=int, default=6)

    shortpick_replay_feedback_cache = subparsers.add_parser(
        "shortpick-replay-feedback-cache",
        help="Materialize historical replay feedback cache for the served Short Pick Lab page.",
    )
    shortpick_replay_feedback_cache.add_argument("--database-url", default=None)
    shortpick_replay_feedback_cache.add_argument("--output-path", default="output/shortpick-replay-feedback-cache.json")
    shortpick_replay_feedback_cache.add_argument("--skip-validate-missing", action="store_true")

    frontend_projections_refresh = subparsers.add_parser(
        "frontend-projections-refresh",
        help="Materialize small frontend-facing projection rows from existing artifacts and read-only ledgers.",
    )
    frontend_projections_refresh.add_argument("--database-url", default=None)
    frontend_projections_refresh.add_argument(
        "--projection",
        choices=[
            "all",
            "home_shell",
            "shortpick_model_feedback",
            "shortpick_replay_feedback",
            "operations_summary",
            "simulation_workspace_summary",
        ],
        default="all",
    )
    frontend_projections_refresh.add_argument("--target-login", default="root")
    frontend_projections_refresh.add_argument(
        "--sample-symbol",
        action="append",
        default=None,
        help="Sample symbol to precompute for operations_summary. May be provided multiple times.",
    )

    shortpick_market_factor_study = subparsers.add_parser(
        "shortpick-market-factor-study",
        help="Run a market-only shortpick factor ranking study across a broader daily-bar history.",
    )
    shortpick_market_factor_study.add_argument("--database-url", default=None)
    shortpick_market_factor_study.add_argument("--start-date", default="2024-01-01")
    shortpick_market_factor_study.add_argument("--end-date", default="2026-04-30")
    shortpick_market_factor_study.add_argument("--train-end", default="2026-02-27")
    shortpick_market_factor_study.add_argument("--holdout-start", default="2026-03-01")
    shortpick_market_factor_study.add_argument("--pool-limit", type=int, default=40)
    shortpick_market_factor_study.add_argument("--rank-limit", type=int, default=6)
    shortpick_market_factor_study.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_market_factor_study.add_argument("--apply-limit-up-filter", action="store_true")
    shortpick_market_factor_study.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_market_factor_study.add_argument(
        "--benchmark-mode",
        choices=["csi300", "universe_equal_weight"],
        default="universe_equal_weight",
    )
    shortpick_market_factor_study.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_market_factor_study.add_argument("--walk-forward-lookback-days", type=int, default=120)
    shortpick_market_factor_study.add_argument("--output-path", default=None)

    shortpick_portfolio_backtest = subparsers.add_parser(
        "shortpick-portfolio-backtest",
        help="Backtest daily rolling and weekly concentrated shortpick capital deployment modes on a long market-only sample.",
    )
    shortpick_portfolio_backtest.add_argument("--database-url", default=None)
    shortpick_portfolio_backtest.add_argument("--start-date", default="2023-04-13")
    shortpick_portfolio_backtest.add_argument("--end-date", default="2026-05-08")
    shortpick_portfolio_backtest.add_argument("--pool-limit", type=int, default=40)
    shortpick_portfolio_backtest.add_argument("--rank-limit", type=int, default=6)
    shortpick_portfolio_backtest.add_argument("--horizon-days", type=int, default=5)
    shortpick_portfolio_backtest.add_argument("--initial-cash", type=float, default=50_000.0)
    shortpick_portfolio_backtest.add_argument("--daily-sleeve-cash", type=float, default=10_000.0)
    shortpick_portfolio_backtest.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_portfolio_backtest.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_portfolio_backtest.add_argument("--no-limit-up-filter", action="store_true")
    shortpick_portfolio_backtest.add_argument("--no-limit-down-exit-filter", action="store_true")
    shortpick_portfolio_backtest.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_portfolio_backtest.add_argument(
        "--benchmark-mode",
        choices=["csi300", "universe_equal_weight"],
        default="universe_equal_weight",
    )
    shortpick_portfolio_backtest.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_portfolio_backtest.add_argument("--output", default=None)

    shortpick_v2_replay = subparsers.add_parser(
        "shortpick-v2-replay",
        help="Generate the offline Short Pick Lab v2 account-constrained historical replay artifact.",
    )
    shortpick_v2_replay.add_argument("--database-url", default=None)
    shortpick_v2_replay.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_replay.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_replay.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_replay.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_replay.add_argument("--horizon-days", type=int, default=5)
    shortpick_v2_replay.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_replay.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_replay.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_replay.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_replay.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_replay.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_replay.add_argument("--output", default="output/shortpick-v2-replay-artifact.json")

    shortpick_v2_strategy_search = subparsers.add_parser(
        "shortpick-v2-strategy-search",
        help="Generate a batched Short Pick Lab v2 strategy-search replay artifact.",
    )
    shortpick_v2_strategy_search.add_argument("--database-url", default=None)
    shortpick_v2_strategy_search.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_strategy_search.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_strategy_search.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_strategy_search.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_strategy_search.add_argument("--horizon-days", type=int, default=5)
    shortpick_v2_strategy_search.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_strategy_search.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_strategy_search.add_argument(
        "--candidate-batch",
        choices=STRATEGY_SEARCH_BATCHES,
        default=STRATEGY_SEARCH_BATCH_INITIAL,
    )
    shortpick_v2_strategy_search.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_strategy_search.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_strategy_search.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_strategy_search.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_strategy_search.add_argument(
        "--output",
        default="output/shortpick-v2-strategy-search-replay-artifact.json",
    )

    shortpick_v2_rule_selection = subparsers.add_parser(
        "shortpick-v2-rule-selection",
        help="Select bounded Short Pick Lab v2 rule candidates from a replay artifact.",
    )
    shortpick_v2_rule_selection.add_argument("--database-url", default=None, help=argparse.SUPPRESS)
    shortpick_v2_rule_selection.add_argument("--replay-artifact", required=True)
    shortpick_v2_rule_selection.add_argument("--output", default="output/shortpick-v2-rule-selection-artifact.json")
    shortpick_v2_rule_selection.add_argument("--max-selected", type=int, default=2)
    shortpick_v2_rule_selection.add_argument(
        "--threshold-profile",
        choices=SELECTION_THRESHOLD_PROFILES,
        default=SELECTION_THRESHOLD_PROFILE_STANDARD,
    )
    shortpick_v2_rule_selection.add_argument("--generated-at", default=None)

    shortpick_v2_h10_robustness = subparsers.add_parser(
        "shortpick-v2-h10-robustness",
        help="Generate robustness diagnostics for h10 quiet Short Pick Lab v2 candidates.",
    )
    shortpick_v2_h10_robustness.add_argument("--database-url", default=None)
    shortpick_v2_h10_robustness.add_argument(
        "--replay-artifact",
        default="output/shortpick-v2-h10-quiet-strategy-search-replay-artifact.json",
    )
    shortpick_v2_h10_robustness.add_argument(
        "--selection-artifact",
        default="output/shortpick-v2-h10-quiet-sparse-selection-artifact.json",
    )
    shortpick_v2_h10_robustness.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_h10_robustness.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_h10_robustness.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_h10_robustness.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_h10_robustness.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_h10_robustness.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_h10_robustness.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_h10_robustness.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_h10_robustness.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_h10_robustness.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_h10_robustness.add_argument("--max-holdout-configs", type=int, default=10)
    shortpick_v2_h10_robustness.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_h10_robustness.add_argument(
        "--output",
        default="output/shortpick-v2-h10-quiet-robustness-artifact.json",
    )

    shortpick_v2_h10_execution_decomposition = subparsers.add_parser(
        "shortpick-v2-h10-execution-decomposition",
        help="Generate execution decomposition diagnostics for h10 quiet fixed80/fixed85/90k configs.",
    )
    shortpick_v2_h10_execution_decomposition.add_argument("--database-url", default=None)
    shortpick_v2_h10_execution_decomposition.add_argument(
        "--replay-artifact",
        default="output/shortpick-v2-h10-quiet-strategy-search-replay-artifact.json",
    )
    shortpick_v2_h10_execution_decomposition.add_argument(
        "--selection-artifact",
        default="output/shortpick-v2-h10-quiet-sparse-selection-artifact.json",
    )
    shortpick_v2_h10_execution_decomposition.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_h10_execution_decomposition.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_h10_execution_decomposition.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_h10_execution_decomposition.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_h10_execution_decomposition.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_h10_execution_decomposition.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_h10_execution_decomposition.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_h10_execution_decomposition.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_h10_execution_decomposition.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_h10_execution_decomposition.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_h10_execution_decomposition.add_argument("--max-holdout-configs", type=int, default=10)
    shortpick_v2_h10_execution_decomposition.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_h10_execution_decomposition.add_argument(
        "--output",
        default="output/shortpick-v2-h10-quiet-execution-decomposition-artifact.json",
    )

    shortpick_v2_h10_parameter_significance = subparsers.add_parser(
        "shortpick-v2-h10-parameter-significance",
        help="Generate parameter significance diagnostics for the h10 quiet champion line.",
    )
    shortpick_v2_h10_parameter_significance.add_argument("--database-url", default=None)
    shortpick_v2_h10_parameter_significance.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_h10_parameter_significance.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_h10_parameter_significance.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_h10_parameter_significance.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_h10_parameter_significance.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_h10_parameter_significance.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_h10_parameter_significance.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_h10_parameter_significance.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_h10_parameter_significance.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_h10_parameter_significance.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_h10_parameter_significance.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_h10_parameter_significance.add_argument(
        "--output",
        default="output/shortpick-v2-h10-parameter-significance-artifact.json",
    )

    shortpick_v2_h10_parameter_significance_validate = subparsers.add_parser(
        "shortpick-v2-h10-parameter-significance-validate",
        help="Validate h10 quiet parameter significance artifact structure and governance labels.",
    )
    shortpick_v2_h10_parameter_significance_validate.add_argument("--artifact", required=True)

    shortpick_v2_h10_weekday_drawdown_notional_matrix = subparsers.add_parser(
        "shortpick-v2-h10-weekday-drawdown-notional-matrix",
        help="Generate the H10 quiet weekday, drawdown-filter, and fixed-notional validation matrix.",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--database-url", default=None)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument(
        "--weekday-mode",
        action="append",
        choices=[
            "mtw",
            "tue_wed_thu",
            "mon_wed_fri",
            "wed_thu_fri",
            "mon_to_thu",
            "all_weekdays",
        ],
        dest="weekday_modes",
        help="Weekday mode to include; repeat for multiple modes. Defaults to the historical MTW/all-weekdays matrix.",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument(
        "--target-notional",
        action="append",
        type=float,
        dest="target_notionals",
        help="Fixed buy notional to include; repeat for multiple sizes. Defaults to the historical 10k-85k matrix.",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument(
        "--output",
        default="output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_NOTIONAL_MATRIX.md",
    )

    shortpick_v2_h10_weekday_drawdown_notional_matrix_validate = subparsers.add_parser(
        "shortpick-v2-h10-weekday-drawdown-notional-matrix-validate",
        help="Validate the H10 quiet weekday, drawdown-filter, and notional matrix artifact.",
    )
    shortpick_v2_h10_weekday_drawdown_notional_matrix_validate.add_argument("--artifact", required=True)

    shortpick_v2_out_of_sample_risk = subparsers.add_parser(
        "shortpick-v2-out-of-sample-risk",
        help="Generate rolling-window diagnostics for current v2 paper drawdown pressure.",
    )
    shortpick_v2_out_of_sample_risk.add_argument("--database-url", default=None)
    shortpick_v2_out_of_sample_risk.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_out_of_sample_risk.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_out_of_sample_risk.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_out_of_sample_risk.add_argument("--paper-end-date", default="2026-06-15")
    shortpick_v2_out_of_sample_risk.add_argument("--observed-paper-max-drawdown", type=float, default=-0.175)
    shortpick_v2_out_of_sample_risk.add_argument(
        "--window-size",
        action="append",
        type=int,
        dest="window_sizes",
        help="Rolling trade-day window size; repeat for multiple windows. Defaults to 25 and 50.",
    )
    shortpick_v2_out_of_sample_risk.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_out_of_sample_risk.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_out_of_sample_risk.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_out_of_sample_risk.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_out_of_sample_risk.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_out_of_sample_risk.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_out_of_sample_risk.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_out_of_sample_risk.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_out_of_sample_risk.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_out_of_sample_risk.add_argument(
        "--output",
        default="output/shortpick-v2-out-of-sample-risk-diagnostic-20260616.json",
    )
    shortpick_v2_out_of_sample_risk.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_OUT_OF_SAMPLE_RISK_DIAGNOSTIC_2026-06-16.md",
    )

    shortpick_v2_out_of_sample_risk_validate = subparsers.add_parser(
        "shortpick-v2-out-of-sample-risk-validate",
        help="Validate the v2 out-of-sample risk diagnostic artifact.",
    )
    shortpick_v2_out_of_sample_risk_validate.add_argument("--artifact", required=True)

    shortpick_v2_risk_switch_experiment = subparsers.add_parser(
        "shortpick-v2-risk-switch-experiment",
        help="Generate the research-only v2 H10 risk-switch experiment artifact.",
    )
    shortpick_v2_risk_switch_experiment.add_argument("--database-url", default=None)
    shortpick_v2_risk_switch_experiment.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_risk_switch_experiment.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_risk_switch_experiment.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_risk_switch_experiment.add_argument("--paper-end-date", default="2026-06-15")
    shortpick_v2_risk_switch_experiment.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_risk_switch_experiment.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_risk_switch_experiment.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_risk_switch_experiment.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_risk_switch_experiment.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_risk_switch_experiment.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_risk_switch_experiment.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_risk_switch_experiment.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_risk_switch_experiment.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_risk_switch_experiment.add_argument(
        "--output",
        default="output/shortpick-v2-risk-switch-experiment-20260616.json",
    )
    shortpick_v2_risk_switch_experiment.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md",
    )

    shortpick_v2_risk_switch_experiment_validate = subparsers.add_parser(
        "shortpick-v2-risk-switch-experiment-validate",
        help="Validate the research-only v2 H10 risk-switch experiment artifact.",
    )
    shortpick_v2_risk_switch_experiment_validate.add_argument("--artifact", required=True)

    shortpick_v2_next_diagnostics = subparsers.add_parser(
        "shortpick-v2-next-diagnostics",
        help="Generate the next diagnostics artifact for v2 paper-window divergence.",
    )
    shortpick_v2_next_diagnostics.add_argument("--database-url", default=None)
    shortpick_v2_next_diagnostics.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_next_diagnostics.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_next_diagnostics.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_next_diagnostics.add_argument("--paper-end-date", default="2026-06-15")
    shortpick_v2_next_diagnostics.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_next_diagnostics.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_next_diagnostics.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_next_diagnostics.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_next_diagnostics.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_next_diagnostics.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_next_diagnostics.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_next_diagnostics.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_next_diagnostics.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_next_diagnostics.add_argument(
        "--output",
        default="output/shortpick-v2-next-diagnostics-20260616.json",
    )
    shortpick_v2_next_diagnostics.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_NEXT_DIAGNOSTICS_2026-06-16.md",
    )

    shortpick_v2_next_diagnostics_validate = subparsers.add_parser(
        "shortpick-v2-next-diagnostics-validate",
        help="Validate the next diagnostics artifact.",
    )
    shortpick_v2_next_diagnostics_validate.add_argument("--artifact", required=True)

    shortpick_v2_oos_loss_filter = subparsers.add_parser(
        "shortpick-v2-oos-loss-filter",
        help="Generate the train/holdout OOS loss-precursor filter artifact for v2 H10 baseline.",
    )
    shortpick_v2_oos_loss_filter.add_argument("--database-url", default=None)
    shortpick_v2_oos_loss_filter.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_oos_loss_filter.add_argument("--train-end-date", default="2025-04-30")
    shortpick_v2_oos_loss_filter.add_argument("--holdout-start-date", default="2025-05-01")
    shortpick_v2_oos_loss_filter.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_oos_loss_filter.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_oos_loss_filter.add_argument("--paper-end-date", default="2026-06-15")
    shortpick_v2_oos_loss_filter.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_oos_loss_filter.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_oos_loss_filter.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_oos_loss_filter.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_oos_loss_filter.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_oos_loss_filter.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_oos_loss_filter.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_oos_loss_filter.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_oos_loss_filter.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_oos_loss_filter.add_argument(
        "--output",
        default="output/shortpick-v2-oos-loss-filter-20260616.json",
    )
    shortpick_v2_oos_loss_filter.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_OOS_LOSS_FILTER_2026-06-16.md",
    )

    shortpick_v2_oos_loss_filter_validate = subparsers.add_parser(
        "shortpick-v2-oos-loss-filter-validate",
        help="Validate the OOS loss-filter artifact.",
    )
    shortpick_v2_oos_loss_filter_validate.add_argument("--artifact", required=True)

    shortpick_v2_theme_position_diagnostics = subparsers.add_parser(
        "shortpick-v2-theme-position-diagnostics",
        help="Generate the v2 current-month theme and position-shape diagnostics artifact.",
    )
    shortpick_v2_theme_position_diagnostics.add_argument("--database-url", default=None)
    shortpick_v2_theme_position_diagnostics.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_theme_position_diagnostics.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_theme_position_diagnostics.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_theme_position_diagnostics.add_argument("--paper-end-date", default="2026-06-16")
    shortpick_v2_theme_position_diagnostics.add_argument("--current-month-start-date", default="2026-06-01")
    shortpick_v2_theme_position_diagnostics.add_argument("--current-month-end-date", default="2026-06-16")
    shortpick_v2_theme_position_diagnostics.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_theme_position_diagnostics.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_theme_position_diagnostics.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_theme_position_diagnostics.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_theme_position_diagnostics.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_theme_position_diagnostics.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_theme_position_diagnostics.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_theme_position_diagnostics.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_theme_position_diagnostics.add_argument("--top-winner-count", type=int, default=50)
    shortpick_v2_theme_position_diagnostics.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_theme_position_diagnostics.add_argument(
        "--output",
        default="output/shortpick-v2-theme-position-diagnostics-20260616.json",
    )
    shortpick_v2_theme_position_diagnostics.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_THEME_POSITION_DIAGNOSTICS_2026-06-16.md",
    )

    shortpick_v2_theme_position_diagnostics_validate = subparsers.add_parser(
        "shortpick-v2-theme-position-diagnostics-validate",
        help="Validate the v2 theme and position-shape diagnostics artifact.",
    )
    shortpick_v2_theme_position_diagnostics_validate.add_argument("--artifact", required=True)

    shortpick_v2_oos_position_rank_diagnostics = subparsers.add_parser(
        "shortpick-v2-oos-position-rank-diagnostics",
        help="Generate OOS position-bucket and Rank2/Top5 entry diagnostics for v2 H10.",
    )
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--database-url", default=None)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--train-end-date", default="2025-04-30")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--holdout-start-date", default="2025-05-01")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--paper-end-date", default="2026-06-16")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--current-month-start-date", default="2026-06-01")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--current-month-end-date", default="2026-06-16")
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_oos_position_rank_diagnostics.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--broad-rank-limit", type=int, default=80)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_oos_position_rank_diagnostics.add_argument("--top-winner-count", type=int, default=50)
    shortpick_v2_oos_position_rank_diagnostics.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_oos_position_rank_diagnostics.add_argument(
        "--output",
        default="output/shortpick-v2-oos-position-rank-diagnostics-20260616.json",
    )
    shortpick_v2_oos_position_rank_diagnostics.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_OOS_POSITION_RANK_DIAGNOSTICS_2026-06-16.md",
    )

    shortpick_v2_oos_position_rank_diagnostics_validate = subparsers.add_parser(
        "shortpick-v2-oos-position-rank-diagnostics-validate",
        help="Validate the v2 OOS position and Rank2/Top5 diagnostics artifact.",
    )
    shortpick_v2_oos_position_rank_diagnostics_validate.add_argument("--artifact", required=True)

    shortpick_v2_ranking_backtest = subparsers.add_parser(
        "shortpick-v2-ranking-backtest",
        help="Generate formal v2 ranking replacement backtests under the fixed H10/MTW execution frame.",
    )
    shortpick_v2_ranking_backtest.add_argument("--database-url", default=None)
    shortpick_v2_ranking_backtest.add_argument("--historical-start-date", default="2023-04-13")
    shortpick_v2_ranking_backtest.add_argument("--train-end-date", default="2025-04-30")
    shortpick_v2_ranking_backtest.add_argument("--holdout-start-date", default="2025-05-01")
    shortpick_v2_ranking_backtest.add_argument("--historical-end-date", default="2026-05-08")
    shortpick_v2_ranking_backtest.add_argument("--paper-start-date", default="2026-05-08")
    shortpick_v2_ranking_backtest.add_argument("--paper-end-date", default="2026-06-16")
    shortpick_v2_ranking_backtest.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_ranking_backtest.add_argument("--target-notional", type=float, default=85_000.0)
    shortpick_v2_ranking_backtest.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_ranking_backtest.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_ranking_backtest.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_ranking_backtest.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_ranking_backtest.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_ranking_backtest.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_ranking_backtest.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_ranking_backtest.add_argument("--min-acceptable-annualized-return", type=float, default=0.30)
    shortpick_v2_ranking_backtest.add_argument("--max-acceptable-drawdown", type=float, default=-0.25)
    shortpick_v2_ranking_backtest.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_ranking_backtest.add_argument(
        "--output",
        default="output/shortpick-v2-ranking-backtest-20260616.json",
    )
    shortpick_v2_ranking_backtest.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_V2_RANKING_BACKTEST_2026-06-16.md",
    )

    shortpick_v2_ranking_backtest_validate = subparsers.add_parser(
        "shortpick-v2-ranking-backtest-validate",
        help="Validate the v2 ranking replacement backtest artifact.",
    )
    shortpick_v2_ranking_backtest_validate.add_argument("--artifact", required=True)

    shortpick_paper_divergence_attribution = subparsers.add_parser(
        "shortpick-paper-divergence-attribution",
        help="Generate research-only attribution for v1/v2 paper-window divergence.",
    )
    shortpick_paper_divergence_attribution.add_argument("--database-url", default=None)
    shortpick_paper_divergence_attribution.add_argument("--start-date", default="2026-05-08")
    shortpick_paper_divergence_attribution.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_paper_divergence_attribution.add_argument(
        "--output",
        default="output/shortpick-paper-divergence-attribution-20260616.json",
    )
    shortpick_paper_divergence_attribution.add_argument(
        "--summary-output",
        default="docs/archive/SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_2026-06-16.md",
    )
    shortpick_paper_divergence_attribution.add_argument("--rule-selection-artifact", default=None)
    shortpick_paper_divergence_attribution.add_argument("--ledger-artifact", default=None)
    shortpick_paper_divergence_attribution.add_argument("--paper-governance-artifact", default=None)

    shortpick_paper_divergence_attribution_validate = subparsers.add_parser(
        "shortpick-paper-divergence-attribution-validate",
        help="Validate the v1/v2 paper-window divergence attribution artifact.",
    )
    shortpick_paper_divergence_attribution_validate.add_argument("--artifact", required=True)

    shortpick_v2_h10_rank_ablation = subparsers.add_parser(
        "shortpick-v2-h10-rank-ablation",
        help="Generate same-gate rank ablation diagnostics for the h10 quiet champion line.",
    )
    shortpick_v2_h10_rank_ablation.add_argument("--database-url", default=None)
    shortpick_v2_h10_rank_ablation.add_argument("--start-date", default="2023-04-13")
    shortpick_v2_h10_rank_ablation.add_argument("--end-date", default="2026-05-08")
    shortpick_v2_h10_rank_ablation.add_argument("--initial-cash", type=float, default=200_000.0)
    shortpick_v2_h10_rank_ablation.add_argument(
        "--entry-price-source",
        choices=["next_close", "next_open", "same_close_proxy"],
        default="next_close",
    )
    shortpick_v2_h10_rank_ablation.add_argument("--horizon-days", type=int, default=10)
    shortpick_v2_h10_rank_ablation.add_argument("--pool-limit", type=int, default=40)
    shortpick_v2_h10_rank_ablation.add_argument("--rank-limit", type=int, default=6)
    shortpick_v2_h10_rank_ablation.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_v2_h10_rank_ablation.add_argument("--stamp-tax-bps", type=float, default=5.0)
    shortpick_v2_h10_rank_ablation.add_argument("--min-signal-symbol-count", type=int, default=45)
    shortpick_v2_h10_rank_ablation.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_v2_h10_rank_ablation.add_argument(
        "--output",
        default="output/shortpick-v2-h10-rank-ablation-artifact.json",
    )

    shortpick_v2_h10_rank_ablation_validate = subparsers.add_parser(
        "shortpick-v2-h10-rank-ablation-validate",
        help="Validate h10 quiet rank ablation artifact structure and governance labels.",
    )
    shortpick_v2_h10_rank_ablation_validate.add_argument("--artifact", required=True)

    shortpick_v2_h10_artifact_validate = subparsers.add_parser(
        "shortpick-v2-h10-artifact-validate",
        help="Validate h10 quiet robustness and execution decomposition artifacts.",
    )
    shortpick_v2_h10_artifact_validate.add_argument("--robustness-artifact", required=True)
    shortpick_v2_h10_artifact_validate.add_argument("--execution-artifact", required=True)
    shortpick_v2_h10_artifact_validate.add_argument(
        "--schema-root",
        default="docs/contracts/registry/schemas",
    )

    shortpick_v2_h10_paper_governance = subparsers.add_parser(
        "shortpick-v2-h10-paper-governance",
        help="Build the h10 quiet paper-governance artifact from validated source artifacts.",
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--rank-ablation-artifact",
        required=True,
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--parameter-significance-artifact",
        required=True,
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--robustness-artifact",
        required=True,
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--execution-artifact",
        required=True,
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--output",
        default="output/shortpick-v2-h10-paper-governance-artifact.json",
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--published-artifact",
        default=None,
        help="Optional committed docs/archive copy used by runtime publish.",
    )
    shortpick_v2_h10_paper_governance.add_argument(
        "--schema-root",
        default="docs/contracts/registry/schemas",
    )

    shortpick_v2_h10_paper_governance_validate = subparsers.add_parser(
        "shortpick-v2-h10-paper-governance-validate",
        help="Validate h10 quiet paper-governance artifact structure and governance semantics.",
    )
    shortpick_v2_h10_paper_governance_validate.add_argument("--artifact", required=True)
    shortpick_v2_h10_paper_governance_validate.add_argument(
        "--schema-root",
        default="docs/contracts/registry/schemas",
    )

    shortpick_governance_historical_backtest = subparsers.add_parser(
        "shortpick-governance-historical-backtest",
        help="Run Short Pick governance historical-backtest request plans into gated evidence artifacts.",
    )
    shortpick_governance_historical_backtest.add_argument("--database-url", default=None)
    shortpick_governance_historical_backtest.add_argument("--request-path", required=True)
    shortpick_governance_historical_backtest.add_argument("--output-dir", default=None)
    shortpick_governance_historical_backtest.add_argument("--request-id", action="append", default=None)
    shortpick_governance_historical_backtest.add_argument("--control-group-id", action="append", default=None)

    shortpick_governance_retrospective_replay = subparsers.add_parser(
        "shortpick-governance-retrospective-replay",
        help="Run Short Pick governance retrospective replay requests into labeled evidence artifacts.",
    )
    shortpick_governance_retrospective_replay.add_argument("--database-url", default=None)
    shortpick_governance_retrospective_replay.add_argument("--request-path", required=True)
    shortpick_governance_retrospective_replay.add_argument("--paper-tracking-path", required=True)
    shortpick_governance_retrospective_replay.add_argument("--output-dir", default=None)
    shortpick_governance_retrospective_replay.add_argument("--request-id", action="append", default=None)
    shortpick_governance_retrospective_replay.add_argument("--control-group-id", action="append", default=None)
    shortpick_governance_retrospective_replay.add_argument("--skip-ranked-pool-reconstruction", action="store_true")

    shortpick_governance_credible_control_plan = subparsers.add_parser(
        "shortpick-governance-credible-control-plan",
        help="Build the Short Pick credible-control comparison-line request plan without executing jobs.",
    )
    shortpick_governance_credible_control_plan.add_argument("--database-url", default=None)
    shortpick_governance_credible_control_plan.add_argument("--paper-tracking-path", required=True)
    shortpick_governance_credible_control_plan.add_argument("--rule-defined-at", required=True)
    shortpick_governance_credible_control_plan.add_argument("--historical-evidence-path", default=None)
    shortpick_governance_credible_control_plan.add_argument("--generated-at", default=None)
    shortpick_governance_credible_control_plan.add_argument("--historical-backtest-start-date", default="2023-04-13")
    shortpick_governance_credible_control_plan.add_argument("--historical-backtest-end-date", default=None)
    shortpick_governance_credible_control_plan.add_argument("--tracking-started-at", default=None)
    shortpick_governance_credible_control_plan.add_argument("--entry-price-source", action="append", default=None)
    shortpick_governance_credible_control_plan.add_argument("--baseline-id", action="append", default=None)
    shortpick_governance_credible_control_plan.add_argument("--output-path", default=None)

    shortpick_governance_combined_ledger_backfill = subparsers.add_parser(
        "shortpick-governance-combined-ledger-backfill",
        help="Materialize Short Pick retrospective replay artifacts into a labeled combined-ledger artifact.",
    )
    shortpick_governance_combined_ledger_backfill.add_argument("--database-url", default=None)
    shortpick_governance_combined_ledger_backfill.add_argument(
        "--replay-artifact-path",
        action="append",
        required=True,
        help="Path to a shortpick_retrospective_forward_replay artifact. Repeat for multiple artifacts.",
    )
    shortpick_governance_combined_ledger_backfill.add_argument("--true-forward-path", default=None)
    shortpick_governance_combined_ledger_backfill.add_argument("--generated-at", default=None)
    shortpick_governance_combined_ledger_backfill.add_argument("--output-path", required=True)

    shortpick_governance_combined_ledger_materialize = subparsers.add_parser(
        "shortpick-governance-combined-ledger-materialize",
        help="Discover ready retrospective replay artifacts and materialize a combined-ledger artifact.",
    )
    shortpick_governance_combined_ledger_materialize.add_argument("--database-url", default=None)
    shortpick_governance_combined_ledger_materialize.add_argument("--artifact-root", default=None)
    shortpick_governance_combined_ledger_materialize.add_argument("--true-forward-path", default=None)
    shortpick_governance_combined_ledger_materialize.add_argument("--generated-at", default=None)
    shortpick_governance_combined_ledger_materialize.add_argument("--output-path", default=None)
    shortpick_governance_combined_ledger_materialize.add_argument("--write-blocked", action="store_true")

    shortpick_governance_retirement_artifact = subparsers.add_parser(
        "shortpick-governance-retirement-artifact",
        help="Write a governed Short Pick strategy-retirement artifact for an approved retire_candidate strategy.",
    )
    shortpick_governance_retirement_artifact.add_argument("--database-url", default=None)
    shortpick_governance_retirement_artifact.add_argument("--evidence-pack-path", required=True)
    shortpick_governance_retirement_artifact.add_argument("--status-recommendation-path", required=True)
    shortpick_governance_retirement_artifact.add_argument("--strategy-id", required=True)
    shortpick_governance_retirement_artifact.add_argument("--decision-log-ref", required=True)
    shortpick_governance_retirement_artifact.add_argument("--evidence-snapshot-ref", action="append", required=True)
    shortpick_governance_retirement_artifact.add_argument("--retired-at", required=True)
    shortpick_governance_retirement_artifact.add_argument("--archived-at", default=None)
    shortpick_governance_retirement_artifact.add_argument("--strategy-version", default="shortpick-governance-v1")
    shortpick_governance_retirement_artifact.add_argument("--retirement-reason-code", default=None)
    shortpick_governance_retirement_artifact.add_argument("--replacement-guidance", default="")
    shortpick_governance_retirement_artifact.add_argument("--event-ref", action="append", default=None)
    shortpick_governance_retirement_artifact.add_argument("--output-path", required=True)

    shortpick_strategy_slice_evidence = subparsers.add_parser(
        "shortpick-strategy-slice-evidence",
        help="Build offline trade-level strategy slice evidence for Short Pick Lab history analysis.",
    )
    shortpick_strategy_slice_evidence.add_argument("--database-url", default=None)
    shortpick_strategy_slice_evidence.add_argument("--start-date", default="2023-05-16")
    shortpick_strategy_slice_evidence.add_argument("--end-date", default="2026-04-29")
    shortpick_strategy_slice_evidence.add_argument(
        "--entry-price-source",
        action="append",
        choices=["next_close", "next_open", "same_close_proxy"],
        default=None,
        help="Entry price source to include. May be provided multiple times. Defaults to all staged entry sources.",
    )
    shortpick_strategy_slice_evidence.add_argument("--pool-limit", type=int, default=40)
    shortpick_strategy_slice_evidence.add_argument("--rank-limit", type=int, default=6)
    shortpick_strategy_slice_evidence.add_argument("--horizon-days", type=int, default=5)
    shortpick_strategy_slice_evidence.add_argument("--cost-bps", type=float, default=20.0)
    shortpick_strategy_slice_evidence.add_argument("--min-signal-symbol-count", type=int, default=1000)
    shortpick_strategy_slice_evidence.add_argument("--min-regime-trade-count", type=int, default=30)
    shortpick_strategy_slice_evidence.add_argument(
        "--benchmark-mode",
        choices=["csi300", "universe_equal_weight"],
        default="universe_equal_weight",
    )
    shortpick_strategy_slice_evidence.add_argument(
        "--account-profile",
        choices=["new_retail_cash_account", "unrestricted"],
        default="new_retail_cash_account",
    )
    shortpick_strategy_slice_evidence.add_argument("--output", default="output/shortpick-strategy-trade-regime-evidence.json")

    phase5_daily = subparsers.add_parser(
        "phase5-daily-refresh",
        help="Run the daily Phase 5 refresh workflow: refresh runtime data, then write latest/history horizon-study snapshots.",
    )
    phase5_daily.add_argument("--database-url", default=None)
    phase5_daily.add_argument("--analysis-only", action="store_true")
    phase5_daily.add_argument("--ops-only", action="store_true")
    phase5_daily.add_argument("--skip-simulation", action="store_true")

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init-db":
        init_database(args.database_url)
        print("database initialized")
        return 0
    governance_exit_code = handle_governance_command(args)
    if governance_exit_code is not None:
        return governance_exit_code
    if args.command == "phase5-local-cycle-step":
        return handle_phase5_local_cycle_step_command(args)
    if args.command not in NO_DB_COMMANDS and _should_initialize_database(args.database_url):
        init_database(args.database_url)
    if args.command == "latest":
        with session_scope(args.database_url) as session:
            payload = get_latest_recommendation_summary(session, args.symbol)
        if payload is None:
            print(f"no recommendation found for {args.symbol}")
            return 1
        _print_json(payload)
        return 0
    if args.command == "candidates":
        with session_scope(args.database_url) as session:
            payload = list_candidate_recommendations(session, limit=args.limit)
        _print_json(payload)
        return 0
    if args.command == "stock-dashboard":
        with session_scope(args.database_url) as session:
            payload = get_stock_dashboard(session, args.symbol)
        _print_json(payload)
        return 0
    if args.command == "operations":
        with session_scope(args.database_url) as session:
            payload = build_operations_dashboard(session, sample_symbol=args.sample_symbol)
        _print_json(payload)
        return 0
    if args.command == "phase5-horizon-study":
        with session_scope(args.database_url) as session:
            payload = _phase5_horizon_study_output(
                session,
                database_url=args.database_url,
                symbols=args.symbol,
                include_history=args.include_history,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "phase5-holding-policy-study":
        with session_scope(args.database_url) as session:
            payload = _phase5_holding_policy_study_output(
                session,
                database_url=args.database_url,
                portfolio_keys=args.portfolio_key,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "phase5-holding-policy-experiment":
        with session_scope(args.database_url) as session:
            payload = _phase5_holding_policy_experiment_output(
                session,
                database_url=args.database_url,
                experiment_id=args.experiment_id,
                symbols=args.symbol,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "phase5-producer-contract-study":
        with session_scope(args.database_url) as session:
            payload = _phase5_producer_contract_study_output(
                session,
                database_url=args.database_url,
                symbols=args.symbol,
                include_history=not args.latest_only,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "trace":
        with session_scope(args.database_url) as session:
            payload = get_recommendation_trace(session, args.recommendation_id)
        _print_json(payload)
        return 0
    if args.command == "glossary":
        _print_json(get_glossary_entries())
        return 0

    if args.command == "policy-configs":
        with session_scope(args.database_url) as session:
            payload = {
                "active": build_policy_governance_summary(session),
                "history": list_policy_config_versions(session, scope=args.scope, config_key=args.config_key),
            }
        _print_json(payload)
        return 0

    if args.command == "policy-config-create":
        with session_scope(args.database_url) as session:
            record = create_policy_config_version(
                session,
                scope=args.scope,
                config_key=args.config_key,
                version=args.version,
                payload=json.loads(args.payload_json),
                reason=args.reason,
                evidence_refs=args.evidence_ref,
                created_by=args.created_by,
            )
            session.flush()
            payload = {"id": record.id, "scope": record.scope, "config_key": record.config_key, "version": record.version}
        _print_json(payload)
        return 0

    if args.command == "policy-config-activate":
        with session_scope(args.database_url) as session:
            record = activate_policy_config_version(
                session,
                scope=args.scope,
                config_key=args.config_key,
                version=args.version,
                approved_by=args.approved_by,
            )
            session.flush()
            payload = {"id": record.id, "scope": record.scope, "config_key": record.config_key, "version": record.version, "status": record.status}
        _print_json(payload)
        return 0

    if args.command == "event-check":
        with session_scope(args.database_url) as session:
            collected = handle_event_check(session, symbol=args.symbol, run=args.run, database_url=args.database_url)
        _print_json(collected)
        return 0

    if args.command == "factor-observation":
        with session_scope(args.database_url) as session:
            _print_json(handle_factor_observation(session, database_url=args.database_url))
        return 0

    if args.command == "weight-sweep":
        with session_scope(args.database_url) as session:
            _print_json(handle_weight_sweep(session, database_url=args.database_url))
        return 0

    if args.command == "shortpick-model-exploration-run":
        as_of_dates = [date.fromisoformat(value) for value in args.as_of_date or []] or None
        with session_scope(args.database_url) as session:
            payload = run_shortpick_model_exploration_workbench(
                session,
                database_url=args.database_url,
                validation_run_id=args.validation_run_id,
                as_of_dates=as_of_dates,
                max_as_of_dates=args.max_as_of_dates,
                benchmark_symbol=args.benchmark_symbol,
                selected_model_spec_ids=args.model_spec_id,
                min_train_dates=args.min_train_dates,
                test_window_dates=args.test_window_dates,
                write_artifacts=not args.no_write_artifacts,
                artifact_root=args.artifact_root,
                input_snapshot_artifact=args.input_snapshot_artifact,
                feature_matrix_artifact=args.feature_matrix_artifact,
                label_matrix_artifact=args.label_matrix_artifact,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-model-feature-diagnostics-run":
        payload = run_model_feature_diagnostics(
            validation_run_id=args.validation_run_id,
            feature_matrix_artifact=args.feature_matrix_artifact,
            label_matrix_artifact=args.label_matrix_artifact,
            artifact_root=args.artifact_root,
            write_artifacts=not args.no_write_artifacts,
        )
        _print_json(payload)
        return 0

    if args.command in ("refresh-runtime-data", "phase5-daily-refresh"):
        if args.analysis_only and args.ops_only:
            parser.error("--analysis-only 和 --ops-only 不能同时传入")
        preflight_database_writable(args.database_url)
    if args.command == "refresh-runtime-data":
        with _refresh_socket_timeout():
            with session_scope(args.database_url) as session:
                payload = _refresh_runtime_data_output(
                    session,
                    analysis_only=args.analysis_only,
                    ops_only=args.ops_only,
                    skip_simulation=args.skip_simulation,
                )
        _print_json(payload)
        return 0

    if args.command == "sync-benchmark-index-bars":
        with session_scope(args.database_url) as session:
            payload = sync_benchmark_index_bars(session, lookback_days=args.lookback_days)
        _print_json(payload)
        return 0

    if args.command == "review-improvement-suggestions":
        with session_scope(args.database_url) as session:
            payload = run_improvement_suggestion_review(session, window_days=args.window_days)
        _print_json(payload)
        return 0

    if args.command == "shortpick-lab-run":
        target_date = None if args.run_date is None else date.fromisoformat(args.run_date)
        _assert_postmarket_daily_slot_allowed(target_date)
        with session_scope(args.database_url) as session:
            payload = run_shortpick_experiment(
                session,
                run_date=target_date,
                rounds_per_model=args.rounds_per_model,
                triggered_by="scheduled_cli",
                trigger_source="scheduled_cli",
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-lab-intraday-same-day":
        target_date = None if args.run_date is None else date.fromisoformat(args.run_date)
        _assert_intraday_same_day_slot_allowed(target_date)
        with session_scope(args.database_url) as session:
            payload = run_shortpick_intraday_same_day_control(
                session,
                run_date=target_date,
                triggered_by="scheduled_cli",
                trigger_source="scheduled_intraday_cli",
            )
        _print_json(payload)
        return 0 if payload.get("status") != "failed" else 1

    if args.command == "shortpick-lab-validate":
        with session_scope(args.database_url) as session:
            payload = validate_shortpick_run(
                session,
                args.run_id,
                horizons=args.horizon,
                sync_market_data=not args.existing_market_data_only,
                sync_benchmarks=not args.existing_market_data_only,
                include_sector_benchmark=not args.existing_market_data_only,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-lab-validate-recent":
        with session_scope(args.database_url) as session:
            payload = validate_recent_shortpick_runs(
                session,
                days=args.days,
                limit=args.limit,
                horizons=args.horizon,
                sync_market_data=not args.existing_market_data_only,
                sync_benchmarks=not args.existing_market_data_only,
                include_sector_benchmark=not args.existing_market_data_only,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-lab-retry-failed":
        with session_scope(args.database_url) as session:
            payload = retry_failed_shortpick_rounds(session, args.run_id, max_rounds=args.max_rounds)
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay":
        with session_scope(args.database_url) as session:
            replay_kwargs = {
                "start_date": date.fromisoformat(args.start_date),
                "end_date": date.fromisoformat(args.end_date),
                "rounds": args.rounds,
                "candidate_limit": args.candidate_limit,
                "account_profile": args.account_profile,
                "triggered_by": "scheduled_cli",
            }
            if args.llm_max_workers and args.llm_max_workers > 1:
                payload = run_shortpick_historical_replay_concurrent(
                    session,
                    max_workers=args.llm_max_workers,
                    **replay_kwargs,
                )
            else:
                payload = run_shortpick_historical_replay(session, **replay_kwargs)
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay-dates":
        replay_dates = _parse_shortpick_replay_dates(args.dates, args.dates_file)
        if not replay_dates:
            raise SystemExit("shortpick-replay-dates requires at least one --date or --dates-file entry")
        with session_scope(args.database_url) as session:
            payload = run_shortpick_historical_replay_dates(
                session,
                replay_dates=replay_dates,
                rounds=args.rounds,
                candidate_limit=args.candidate_limit,
                account_profile=args.account_profile,
                triggered_by="stratified_replay_cli",
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay-distill":
        with session_scope(args.database_url) as session:
            distill_kwargs = {
                "run_id": args.run_id,
                "start_date": None if args.start_date is None else date.fromisoformat(args.start_date),
                "end_date": None if args.end_date is None else date.fromisoformat(args.end_date),
                "momentum_pool_limit": args.momentum_pool_limit,
                "self_distill_limit": args.self_distill_limit,
                "momentum_distill_limit": args.momentum_distill_limit,
            }
            if args.llm_max_workers and args.llm_max_workers > 1:
                payload = run_shortpick_replay_distillation_concurrent(
                    session,
                    max_workers=args.llm_max_workers,
                    **distill_kwargs,
                )
            else:
                payload = run_shortpick_replay_distillation(session, **distill_kwargs)
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay-reject":
        with session_scope(args.database_url) as session:
            payload = run_shortpick_replay_rejection(
                session,
                run_id=args.run_id,
                start_date=None if args.start_date is None else date.fromisoformat(args.start_date),
                end_date=None if args.end_date is None else date.fromisoformat(args.end_date),
                momentum_pool_limit=args.momentum_pool_limit,
                rank_limit=args.rank_limit,
                reject_max_ratio=args.reject_max_ratio,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay-hard-veto":
        with session_scope(args.database_url) as session:
            payload = run_shortpick_replay_hard_veto_experiment(
                session,
                run_id=args.run_id,
                start_date=None if args.start_date is None else date.fromisoformat(args.start_date),
                end_date=None if args.end_date is None else date.fromisoformat(args.end_date),
                momentum_pool_limit=args.momentum_pool_limit,
                rank_limit=args.rank_limit,
                veto_max_ratio=args.veto_max_ratio,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay-factor-rank":
        with session_scope(args.database_url) as session:
            payload = run_shortpick_replay_factor_rank_experiment(
                session,
                run_id=args.run_id,
                start_date=None if args.start_date is None else date.fromisoformat(args.start_date),
                end_date=None if args.end_date is None else date.fromisoformat(args.end_date),
                momentum_pool_limit=args.momentum_pool_limit,
                rank_limit=args.rank_limit,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-replay-feedback-cache":
        with session_scope(args.database_url) as session:
            payload = refresh_shortpick_replay_feedback_cache(
                session,
                output_path=args.output_path,
                validate_missing=not args.skip_validate_missing,
            )
        _print_json({
            "status": "ok",
            "output_path": args.output_path,
            "metadata": payload.get("metadata", {}),
        })
        return 0

    if args.command == "frontend-projections-refresh":
        init_database(args.database_url)
        with session_scope(args.database_url) as session:
            payload = refresh_frontend_projections(
                session,
                projection=args.projection,
                target_login=args.target_login,
                sample_symbols=args.sample_symbol,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-market-factor-study":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_market_factor_study(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                train_end=date.fromisoformat(args.train_end),
                holdout_start=date.fromisoformat(args.holdout_start),
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                apply_limit_up_filter=args.apply_limit_up_filter,
                benchmark_mode=args.benchmark_mode,
                entry_price_source=args.entry_price_source,
                walk_forward_lookback_days=args.walk_forward_lookback_days,
                account_profile=args.account_profile,
            )
        if args.output_path:
            output_path = Path(args.output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            _print_json({"status": "ok", "output_path": str(output_path)})
            return 0
        _print_json(payload)
        return 0

    if args.command == "shortpick-portfolio-backtest":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_portfolio_backtest(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                horizon_days=args.horizon_days,
                initial_cash=args.initial_cash,
                daily_sleeve_cash=args.daily_sleeve_cash,
                cost_bps=args.cost_bps,
                benchmark_mode=args.benchmark_mode,
                entry_price_source=args.entry_price_source,
                apply_limit_up_filter=not args.no_limit_up_filter,
                apply_limit_down_exit_filter=not args.no_limit_down_exit_filter,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        if args.output:
            path = write_shortpick_portfolio_backtest(payload, output_path=args.output)
            payload = {**payload, "artifact": {"path": str(path)}}
        _print_json(payload)
        return 0

    if args.command == "shortpick-v2-replay":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_replay_artifact(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        path = write_shortpick_v2_replay_artifact(payload, output_path=args.output)
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "signal_day_count": (payload.get("data_scope") or {}).get("signal_day_count"),
                "result_count": len(payload.get("results") or []),
            }
        )
        return 0

    if args.command == "shortpick-v2-strategy-search":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_strategy_search_artifact(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                candidate_batch=args.candidate_batch,
            )
        path = write_shortpick_v2_strategy_search_artifact(payload, output_path=args.output)
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "candidate_batch": args.candidate_batch,
                "signal_day_count": (payload.get("data_scope") or {}).get("signal_day_count"),
                "result_count": len(payload.get("results") or []),
            }
        )
        return 0

    if args.command == "shortpick-v2-rule-selection":
        generated_at = datetime.fromisoformat(args.generated_at) if args.generated_at else None
        payload = build_shortpick_v2_rule_selection_artifact_from_path(
            args.replay_artifact,
            max_selected=args.max_selected,
            threshold_profile=args.threshold_profile,
            generated_at=generated_at,
        )
        path = write_shortpick_v2_rule_selection_artifact(payload, output_path=args.output)
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "threshold_profile": args.threshold_profile,
                "selected_config_ids": [item["config_id"] for item in payload.get("selected_configs") or []],
                "baseline_config_ids": [item["config_id"] for item in payload.get("baseline_configs") or []],
                "holdout_count": len(payload.get("holdout_configs") or []),
                "rejected_count": len(payload.get("rejected_configs") or []),
            }
        )
        return 0

    if args.command == "shortpick-v2-h10-robustness":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_h10_robustness_artifact(
                session,
                replay_artifact_path=args.replay_artifact,
                selection_artifact_path=args.selection_artifact,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                max_holdout_configs=args.max_holdout_configs,
            )
        path = write_shortpick_v2_h10_robustness_artifact(payload, output_path=args.output)
        risk_flags = payload.get("risk_flags") or []
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
                "analyzed_config_count": (payload.get("analysis_scope") or {}).get("analyzed_config_count"),
                "high_risk_flag_count": sum(1 for flag in risk_flags if flag.get("severity") == "high"),
                "risk_flag_count": len(risk_flags),
            }
        )
        return 0

    if args.command == "shortpick-v2-h10-execution-decomposition":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_h10_execution_decomposition_artifact(
                session,
                replay_artifact_path=args.replay_artifact,
                selection_artifact_path=args.selection_artifact,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                max_holdout_configs=args.max_holdout_configs,
            )
        path = write_shortpick_v2_h10_execution_decomposition_artifact(payload, output_path=args.output)
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "decomposed_config_count": (payload.get("analysis_scope") or {}).get("decomposed_config_count"),
                "missing_config_ids": (payload.get("analysis_scope") or {}).get("missing_config_ids"),
            }
        )
        return 0

    if args.command == "shortpick-v2-h10-parameter-significance":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_h10_parameter_significance_artifact(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        path = write_shortpick_v2_h10_parameter_significance_artifact(payload, output_path=args.output)
        support_counts: dict[str, int] = {}
        for row in payload.get("parameter_rows") or []:
            label = str(row.get("support_label") or "unknown")
            support_counts[label] = support_counts.get(label, 0) + 1
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "horizon_days": (payload.get("analysis_scope") or {}).get("horizon_days"),
                "parameter_row_count": len(payload.get("parameter_rows") or []),
                "support_counts": support_counts,
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-h10-parameter-significance-validate":
        payload = validate_shortpick_v2_h10_parameter_significance_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-h10-weekday-drawdown-notional-matrix":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                weekday_modes=tuple(args.weekday_modes) if args.weekday_modes else None,
                notional_values=tuple(args.target_notionals) if args.target_notionals else None,
            )
        paths = write_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "row_count": len(payload.get("matrix_rows") or []),
                "horizon_days": (payload.get("analysis_scope") or {}).get("horizon_days"),
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-h10-weekday-drawdown-notional-matrix-validate":
        payload = validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-out-of-sample-risk":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_out_of_sample_risk_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                observed_paper_max_drawdown=args.observed_paper_max_drawdown,
                window_sizes=tuple(args.window_sizes) if args.window_sizes else (25, 50),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        paths = write_shortpick_v2_out_of_sample_risk_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "interpretation_status": (payload.get("interpretation") or {}).get("status"),
                "rolling_window_count": len(payload.get("rolling_window_diagnostics") or []),
            }
        )
        return 0

    if args.command == "shortpick-v2-out-of-sample-risk-validate":
        payload = validate_shortpick_v2_out_of_sample_risk_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-risk-switch-experiment":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_risk_switch_experiment_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        paths = write_shortpick_v2_risk_switch_experiment_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "variant_count": len(payload.get("variant_rows") or []),
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-risk-switch-experiment-validate":
        payload = validate_shortpick_v2_risk_switch_experiment_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-next-diagnostics":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_next_diagnostics_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        paths = write_shortpick_v2_next_diagnostics_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "historical_trade_count": (diagnostics.get("trade_profile") or {}).get("historical_trade_count"),
                "matched_window_count": (diagnostics.get("similar_market_windows") or {}).get("matched_window_count"),
                "interpretation_status": (payload.get("interpretation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-next-diagnostics-validate":
        payload = validate_shortpick_v2_next_diagnostics_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-oos-loss-filter":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_oos_loss_filter_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                train_end_date=date.fromisoformat(args.train_end_date),
                holdout_start_date=date.fromisoformat(args.holdout_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        paths = write_shortpick_v2_oos_loss_filter_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "variant_count": len(payload.get("variant_rows") or []),
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
                "candidate_variant_ids": (payload.get("recommendation") or {}).get("candidate_variant_ids"),
            }
        )
        return 0

    if args.command == "shortpick-v2-oos-loss-filter-validate":
        payload = validate_shortpick_v2_oos_loss_filter_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-theme-position-diagnostics":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_theme_position_diagnostics_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                current_month_start_date=date.fromisoformat(args.current_month_start_date),
                current_month_end_date=date.fromisoformat(args.current_month_end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                top_winner_count=args.top_winner_count,
            )
        paths = write_shortpick_v2_theme_position_diagnostics_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        coverage = payload.get("candidate_pool_coverage") if isinstance(payload.get("candidate_pool_coverage"), dict) else {}
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "top_winner_count": coverage.get("top_winner_count"),
                "v2_candidate_hit_rate": coverage.get("v2_candidate_hit_rate"),
                "pre_launch_v2_candidate_hit_rate": coverage.get("pre_launch_v2_candidate_hit_rate"),
                "bought_top_winner_rate": coverage.get("bought_top_winner_rate"),
                "interpretation_status": (payload.get("interpretation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-theme-position-diagnostics-validate":
        payload = validate_shortpick_v2_theme_position_diagnostics_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-oos-position-rank-diagnostics":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_oos_position_rank_diagnostics_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                train_end_date=date.fromisoformat(args.train_end_date),
                holdout_start_date=date.fromisoformat(args.holdout_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                current_month_start_date=date.fromisoformat(args.current_month_start_date),
                current_month_end_date=date.fromisoformat(args.current_month_end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                broad_rank_limit=args.broad_rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                top_winner_count=args.top_winner_count,
            )
        paths = write_shortpick_v2_oos_position_rank_diagnostics_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        rank = payload.get("rank_entry_diagnostics") if isinstance(payload.get("rank_entry_diagnostics"), dict) else {}
        position = payload.get("position_oos_diagnostics") if isinstance(payload.get("position_oos_diagnostics"), dict) else {}
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "holdout_trade_count": position.get("holdout_trade_count"),
                "quiet_broad_hit_rate": rank.get("quiet_broad_hit_rate"),
                "final_top5_hit_rate": rank.get("final_top5_hit_rate"),
                "interpretation_status": (payload.get("interpretation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-oos-position-rank-diagnostics-validate":
        payload = validate_shortpick_v2_oos_position_rank_diagnostics_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-ranking-backtest":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_ranking_backtest_artifact(
                session,
                historical_start_date=date.fromisoformat(args.historical_start_date),
                train_end_date=date.fromisoformat(args.train_end_date),
                holdout_start_date=date.fromisoformat(args.holdout_start_date),
                historical_end_date=date.fromisoformat(args.historical_end_date),
                paper_start_date=date.fromisoformat(args.paper_start_date),
                paper_end_date=date.fromisoformat(args.paper_end_date),
                initial_cash=args.initial_cash,
                target_notional=args.target_notional,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
                min_acceptable_annualized_return=args.min_acceptable_annualized_return,
                max_acceptable_drawdown=args.max_acceptable_drawdown,
            )
        paths = write_shortpick_v2_ranking_backtest_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        comparison = payload.get("comparison") if isinstance(payload.get("comparison"), dict) else {}
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "candidate_variant_ids": comparison.get("candidate_variant_ids"),
                "interpretation_status": (payload.get("interpretation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-ranking-backtest-validate":
        payload = validate_shortpick_v2_ranking_backtest_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-paper-divergence-attribution":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_paper_divergence_attribution_artifact(
                session,
                start_date=date.fromisoformat(args.start_date),
                initial_cash=args.initial_cash,
                rule_selection_artifact_path=args.rule_selection_artifact,
                ledger_artifact_path=args.ledger_artifact,
                paper_governance_artifact_path=args.paper_governance_artifact,
            )
        paths = write_shortpick_paper_divergence_attribution_artifact(
            payload,
            output_path=args.output,
            summary_path=args.summary_output,
        )
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "validation_status": payload.get("validation_status"),
                "output_path": str(paths["artifact"]),
                "summary_output_path": str(paths.get("summary")) if paths.get("summary") else None,
                "strategy_count": len(payload.get("strategies") or []),
                "latest_available_date": (payload.get("tracking_window") or {}).get("latest_available_date"),
            }
        )
        return 0

    if args.command == "shortpick-paper-divergence-attribution-validate":
        payload = validate_shortpick_paper_divergence_attribution_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-h10-rank-ablation":
        with session_scope(args.database_url) as session:
            payload = build_shortpick_v2_h10_rank_ablation_artifact(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                initial_cash=args.initial_cash,
                entry_price_source=args.entry_price_source,
                horizon_days=args.horizon_days,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                cost_bps=args.cost_bps,
                stamp_tax_bps=args.stamp_tax_bps,
                min_signal_symbol_count=args.min_signal_symbol_count,
                account_profile=args.account_profile,
            )
        path = write_shortpick_v2_h10_rank_ablation_artifact(payload, output_path=args.output)
        _print_json(
            {
                "status": "ok",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "horizon_days": (payload.get("analysis_scope") or {}).get("horizon_days"),
                "rank2_status": (payload.get("rank2_decision") or {}).get("support_label"),
                "rank_row_count": len(payload.get("rank_rows") or []),
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
            }
        )
        return 0

    if args.command == "shortpick-v2-h10-rank-ablation-validate":
        payload = validate_shortpick_v2_h10_rank_ablation_artifact(artifact_path=args.artifact)
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-h10-artifact-validate":
        payload = validate_shortpick_v2_h10_artifacts(
            robustness_artifact_path=args.robustness_artifact,
            execution_artifact_path=args.execution_artifact,
            schema_root=args.schema_root,
        )
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-v2-h10-paper-governance":
        payload = build_shortpick_v2_h10_paper_governance_artifact_from_paths(
            rank_ablation_artifact_path=args.rank_ablation_artifact,
            parameter_significance_artifact_path=args.parameter_significance_artifact,
            robustness_artifact_path=args.robustness_artifact,
            execution_artifact_path=args.execution_artifact,
        )
        path = write_shortpick_v2_h10_paper_governance_artifact(payload, output_path=args.output)
        published_path = None
        if args.published_artifact:
            published_path = write_shortpick_v2_h10_paper_governance_artifact(
                payload,
                output_path=args.published_artifact,
            )
        validation = validate_shortpick_v2_h10_paper_governance_artifact(
            artifact_path=path,
            schema_root=args.schema_root,
        )
        _print_json(
            {
                "status": "ok" if validation.get("status") == "passed" else "failed",
                "artifact_family": payload.get("artifact_family"),
                "artifact_id": payload.get("artifact_id"),
                "output_path": str(path),
                "published_artifact_path": str(published_path) if published_path else None,
                "recommendation_status": (payload.get("recommendation") or {}).get("status"),
                "paper_tracking_status": (payload.get("recommendation") or {}).get("paper_tracking_status"),
                "validation_status": validation.get("status"),
                "failed_check_count": validation.get("failed_check_count"),
            }
        )
        return 0 if validation.get("status") == "passed" else 1

    if args.command == "shortpick-v2-h10-paper-governance-validate":
        payload = validate_shortpick_v2_h10_paper_governance_artifact(
            artifact_path=args.artifact,
            schema_root=args.schema_root,
        )
        _print_json(payload)
        return 0 if payload.get("status") == "passed" else 1

    if args.command == "shortpick-governance-historical-backtest":
        request_payload = json.loads(Path(args.request_path).read_text(encoding="utf-8"))
        requests = _governance_requests_from_payload(
            request_payload,
            nested_plan_key="historical_backtest_plan",
        )
        requests = _filter_governance_requests(
            requests,
            request_ids=args.request_id,
            control_group_ids=args.control_group_id,
        )
        with session_scope(args.database_url) as session:
            payload = run_shortpick_historical_backtest_requests(
                session,
                requests,
                output_dir=args.output_dir,
            )
        _print_json(payload)
        return 0

    if args.command == "shortpick-governance-retrospective-replay":
        request_payload = json.loads(Path(args.request_path).read_text(encoding="utf-8"))
        paper_tracking = json.loads(Path(args.paper_tracking_path).read_text(encoding="utf-8"))
        requests = _governance_requests_from_payload(
            request_payload,
            nested_plan_key="retrospective_replay_plan",
        )
        requests = _filter_governance_requests(
            requests,
            request_ids=args.request_id,
            control_group_ids=args.control_group_id,
        )
        if args.database_url and not args.skip_ranked_pool_reconstruction:
            with session_scope(args.database_url) as session:
                paper_tracking = enrich_shortpick_replay_paper_tracking_with_reconstructed_ranked_pools(
                    session,
                    dict(paper_tracking) if isinstance(paper_tracking, dict) else {},
                    requests=requests,
                )
        payload = run_shortpick_retrospective_forward_replay_requests(
            requests,
            dict(paper_tracking) if isinstance(paper_tracking, dict) else {},
            output_dir=args.output_dir,
        )
        _print_json(payload)
        return 0

    if args.command == "shortpick-governance-credible-control-plan":
        paper_tracking = json.loads(Path(args.paper_tracking_path).read_text(encoding="utf-8"))
        historical_evidence = None
        if args.historical_evidence_path:
            historical_evidence_payload = json.loads(Path(args.historical_evidence_path).read_text(encoding="utf-8"))
            if not isinstance(historical_evidence_payload, dict):
                raise ValueError("historical-evidence-path must contain a JSON object")
            historical_evidence = historical_evidence_payload
        if not isinstance(paper_tracking, dict):
            raise ValueError("paper-tracking-path must contain a JSON object")
        payload = build_shortpick_credible_control_comparison_line_plan(
            paper_tracking,
            rule_defined_at=args.rule_defined_at,
            historical_backtest_evidence=historical_evidence,
            generated_at=args.generated_at,
            historical_backtest_start_date=args.historical_backtest_start_date,
            historical_backtest_end_date=args.historical_backtest_end_date,
            tracking_started_at=args.tracking_started_at,
            entry_price_sources=args.entry_price_source,
            baseline_ids=args.baseline_id,
        )
        if args.output_path:
            output_path = Path(args.output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            payload = {**payload, "artifact": {"path": str(output_path)}}
        _print_json(payload)
        return 0

    if args.command == "shortpick-governance-combined-ledger-backfill":
        replay_artifacts, true_forward_rows = load_shortpick_combined_ledger_inputs(
            args.replay_artifact_path,
            true_forward_path=args.true_forward_path,
        )
        payload = run_shortpick_combined_ledger_backfill_artifact(
            replay_artifacts,
            true_forward_rows=true_forward_rows,
            generated_at=args.generated_at,
            output_path=args.output_path,
        )
        _print_json(payload)
        return 0

    if args.command == "shortpick-governance-combined-ledger-materialize":
        root = Path(args.artifact_root) if args.artifact_root else artifact_root_from_database_url(args.database_url)
        _, true_forward_rows = load_shortpick_combined_ledger_inputs([], true_forward_path=args.true_forward_path)
        payload = materialize_shortpick_combined_ledger_from_artifact_root(
            root=root,
            true_forward_rows=true_forward_rows,
            generated_at=args.generated_at,
            output_path=args.output_path,
            write_blocked=args.write_blocked,
        )
        _print_json(payload)
        return 0

    if args.command == "shortpick-governance-retirement-artifact":
        evidence_pack_result, status_recommendation_result = load_shortpick_strategy_retirement_inputs(
            evidence_pack_path=args.evidence_pack_path,
            status_recommendation_path=args.status_recommendation_path,
        )
        payload = run_shortpick_strategy_retirement_artifact(
            evidence_pack_result,
            status_recommendation_result,
            strategy_id=args.strategy_id,
            decision_log_ref=args.decision_log_ref,
            evidence_snapshot_refs=args.evidence_snapshot_ref,
            retired_at=args.retired_at,
            archived_at=args.archived_at,
            strategy_version=args.strategy_version,
            retirement_reason_code=args.retirement_reason_code,
            replacement_guidance=args.replacement_guidance,
            event_refs=args.event_ref,
            output_path=args.output_path,
        )
        _print_json(payload)
        return 0

    if args.command == "shortpick-strategy-slice-evidence":
        entry_price_sources = tuple(args.entry_price_source or ["next_close", "next_open", "same_close_proxy"])
        with session_scope(args.database_url) as session:
            payload = build_shortpick_strategy_slice_evidence(
                session,
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
                entry_price_sources=entry_price_sources,
                pool_limit=args.pool_limit,
                rank_limit=args.rank_limit,
                horizon_days=args.horizon_days,
                cost_bps=args.cost_bps,
                benchmark_mode=args.benchmark_mode,
                min_signal_symbol_count=args.min_signal_symbol_count,
                min_regime_trade_count=args.min_regime_trade_count,
                account_profile=args.account_profile,
            )
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            _print_json({
                "status": "ok",
                "output_path": str(output_path),
                "regime_winner_count": len(payload.get("regime_winner_rows") or []),
                "signal_day_count": (payload.get("data_scope") or {}).get("signal_day_count") if isinstance(payload.get("data_scope"), dict) else None,
            })
            return 0
        _print_json(payload)
        return 0

    if args.command == "phase5-daily-refresh":
        _assert_postmarket_daily_slot_allowed()
        # Each step gets its own session_scope so the DB connection (and any
        # write lock) is released between steps instead of being held across
        # the whole ~50min pipeline. The steps are independent: each reads what
        # it needs and returns a plain dict, with no cross-step session object
        # or uncommitted-write dependency.
        with _refresh_socket_timeout():
            with session_scope(args.database_url) as session:
                refresh_payload = _refresh_runtime_data_output(
                    session,
                    analysis_only=args.analysis_only,
                    ops_only=args.ops_only,
                    skip_simulation=args.skip_simulation,
                )
            with session_scope(args.database_url) as session:
                latest_study = _phase5_horizon_study_output(
                    session,
                    database_url=args.database_url,
                    include_history=False,
                    write_artifact=True,
                )
            with session_scope(args.database_url) as session:
                history_study = _phase5_horizon_study_output(
                    session,
                    database_url=args.database_url,
                    include_history=True,
                    write_artifact=True,
                )
            with session_scope(args.database_url) as session:
                holding_policy_study = _phase5_holding_policy_study_output(
                    session,
                    database_url=args.database_url,
                    write_artifact=True,
                )
        _print_json({
            "refresh": refresh_payload,
            "phase5_horizon_studies": {
                "latest": {
                    "approval_state": latest_study["decision"]["approval_state"],
                    "candidate_frontier": latest_study["decision"]["candidate_frontier"],
                    "lagging_horizons": latest_study["decision"]["lagging_horizons"],
                    "included_record_count": latest_study["summary"]["included_record_count"],
                    "included_as_of_date_count": latest_study["summary"]["included_as_of_date_count"],
                    "artifact": latest_study.get("artifact"),
                },
                "history": {
                    "approval_state": history_study["decision"]["approval_state"],
                    "candidate_frontier": history_study["decision"]["candidate_frontier"],
                    "lagging_horizons": history_study["decision"]["lagging_horizons"],
                    "included_record_count": history_study["summary"]["included_record_count"],
                    "included_as_of_date_count": history_study["summary"]["included_as_of_date_count"],
                    "artifact": history_study.get("artifact"),
                },
            },
            "phase5_holding_policy_study": {
                "approval_state": holding_policy_study["decision"]["approval_state"],
                "included_portfolio_count": holding_policy_study["summary"]["included_portfolio_count"],
                "mean_turnover": holding_policy_study["summary"].get("mean_turnover"),
                "mean_annualized_excess_return_after_baseline_cost": holding_policy_study["cost_sensitivity"].get(
                    "mean_annualized_excess_return_after_baseline_cost"
                ),
                "gate_status": holding_policy_study["decision"].get("gate_status"),
                "governance_status": holding_policy_study["decision"].get("governance_status"),
                "governance_action": holding_policy_study["decision"].get("governance_action"),
                "redesign_status": holding_policy_study["decision"].get("redesign_status"),
                "redesign_focus_areas": list(holding_policy_study["decision"].get("redesign_focus_areas") or []),
                "redesign_triggered_signal_ids": list(
                    holding_policy_study["decision"].get("redesign_triggered_signal_ids") or []
                ),
                "redesign_primary_experiment_ids": list(
                    holding_policy_study["decision"].get("redesign_primary_experiment_ids") or []
                ),
                "failing_gate_ids": list(holding_policy_study["decision"].get("failing_gate_ids") or []),
                "artifact": holding_policy_study.get("artifact"),
            },
        })
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
