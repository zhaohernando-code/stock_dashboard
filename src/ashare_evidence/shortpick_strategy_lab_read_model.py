from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

STRATEGY_LAB_SCHEMA_VERSION = "shortpick_strategy_lab.v1"
PAPER_STATE_SCHEMA_VERSION = "shortpick_strategy_lab_paper_state.v1"
CLAIM_CEILING = "paper_observation_only"
EVIDENCE_BASIS_PAPER = "true_forward_tracking"
EVIDENCE_BASIS_HISTORY = "static_full_history_account_replay"
TRACKING_START_DATE = "2026-07-08"
INITIAL_CASH_CNY = 200_000
BOARD_LOT_SIZE = 100
MAIN_CONFIG_ID = "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1"
CONTROL_CONFIG_ID = "daily_15_tranche_rank_weighted_compound_min1000_v1"
CONDITIONAL_AGGRESSIVE_CONTROL_ID = (
    "daily_14_tranche_conditional_aggressive_ret20_98_benchmark_nonweak_industry35_dist8_scale14_11_v1"
)
THREE_PART_STABILITY_CONTROL_ID = "daily_14_tranche_three_part_stability_control_min1000_weak085_strong160_cap28_v1"
META_SIGNAL_QUALITY_CONTROL_ID = (
    "daily_14_tranche_meta_signal_quality_industry_leadership_min1000_"
    "weak092_strong165_lead135_low090_cap28_v1"
)
UPSTREAM_META_STABILITY_CONTROL_ID = (
    "daily_14_tranche_upstream_meta_signal_quality_min2250_"
    "weak100_strong165_lead135_low090_v1"
)
NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID = "negative_month_rank_weight_adjusted_capacity_cluster_v3_top3_20d_v1"
NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID = (
    "daily_15_tranche_rank_weighted_compound_min1000_layered_rank1_quickfail_rank3_pullback_exit_v1"
)
QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID = (
    "daily_15_tranche_rank_adjusted_r5_093_strong154_replacement_"
    "top5_gap010_fill075_market_cap25_v1"
)
PAPER_STATE_ENV = "ASHARE_SHORTPICK_STRATEGY_LAB_PAPER_STATE"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAPER_STATE_CANDIDATES = (
    Path("output/shortpick-strategy-lab-paper-state.json"),
    Path("data/shortpick-strategy-lab-paper-state.json"),
)


def build_shortpick_strategy_lab_historical_replay_read_model() -> dict[str, Any]:
    """Return static v3 model replay metrics without scanning market data."""

    return {
        "generated_at": _now_iso(),
        "schema_version": STRATEGY_LAB_SCHEMA_VERSION,
        "status": "ready",
        "claim_ceiling": CLAIM_CEILING,
        "evidence_basis": EVIDENCE_BASIS_HISTORY,
        "ui_language": "历史回放只展示已经落库的全量验证统计值；接口请求不会触发全量重算。",
        "data_disclaimer": "历史回放用于策略研究与前向观察基线，不构成投资建议或自动交易能力声明。",
        "source_artifacts": {
            "full_history_account_replay": {
                "status": "persisted_static_metrics",
                "path": "/tmp/stock_dashboard_v3_rolling_account_replay_20w_extended_to_20260626_layered_exit_rank3_gate_20260708.json",
                "artifact_type": "shortpick_v3_rolling_tranche_account_replay",
            },
            "recent_20260508_account_replay": {
                "status": "persisted_static_metrics",
                "path": "/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260508_layered_exit_rank3_gate_20260708.json",
                "artifact_type": "shortpick_v3_rolling_tranche_account_replay",
            },
            "conditional_aggressive_control_replay": {
                "status": "persisted_static_metrics",
                "path": "/tmp/stock_dashboard_v3_conditional_aggressive_control_formal_replay_20260709.json",
                "artifact_type": "shortpick_v3_rolling_tranche_account_replay",
            },
            "three_part_stability_control_replay": {
                "status": "persisted_static_metrics",
                "path": "/tmp/stock_dashboard_v3_goal10_three_part_stability_control_formal_replay_20260709.json",
                "artifact_type": "shortpick_v3_goal10_three_part_stability_control_formal_replay",
            },
            "meta_signal_quality_control_replay": {
                "status": "persisted_static_metrics",
                "path": "/tmp/stock_dashboard_v3_goal10_meta_signal_quality_formal_replay_20260709.json",
                "artifact_type": "shortpick_v3_goal10_meta_signal_quality_formal_replay",
            },
            "upstream_meta_stability_control_replay": {
                "status": "persisted_static_metrics",
                "path": "/tmp/stock_dashboard_v3_upstream_meta_w100_s165_l090_v1_formal_replay_20260709.json",
                "artifact_type": "shortpick_v3_upstream_meta_w100_s165_l090_v1_formal_replay",
            },
            "negative_month_rank_adjusted_control_replay": {
                "status": "persisted_static_metrics",
                "artifact_id": "self_driven_upstream_negative_month_adjusted_formal_account_scan_20260709",
                "artifact_type": "shortpick_v3_full_history_order_level_account_scan",
            },
            "quality_replacement_rebalance_control_replay": {
                "status": "persisted_static_metrics",
                "path": "docs/contracts/SHORTPICK_V3_R14_QUALITY_REPLACEMENT_REBALANCE_2026-07-10.json",
                "artifact_type": "shortpick_v3_full_history_order_level_account_replay",
            },
        },
        "data_scope": {
            "signal_date_from": "2023-09-07",
            "signal_date_to": "2026-06-26",
            "signal_day_count": 509,
            "selected_pick_count": 1527,
            "market_symbol_count": 593,
            "history_scope_label": "完整历史验证区间",
            "static_read_model": True,
        },
        "selection_policy": {
            "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
            "source_model_family": "regime_adaptive_breakout_defensive_ranker",
            "entry_policy": "每日滚动，按模型 Rank 权重分配 tranche 预算，100 股整手向下取整。",
            "exit_policy": "20 日机械退出叠加 Rank1 快速冲高失败与 Rank3 入场回撤后期亏损保护。",
            "capital_pool_cny": INITIAL_CASH_CNY,
            "forbidden_mode": "月度满仓轮动已明确禁止。",
        },
        "summary": {
            "selected_config_count": 1,
            "baseline_config_count": 7,
            "signal_day_count": 509,
            "coverage_status": "static_full_history_ready",
            "initial_cash_cny": INITIAL_CASH_CNY,
            "main_total_return": 3.119168564999999,
            "main_annualized_return": 0.6577172359709627,
            "main_max_drawdown": -0.07759130606066467,
            "main_negative_month_count": 4,
            "main_skipped_order_rate": 0.352260778128286,
            "main_skipped_signal_rate": 0.2455795677799607,
            "main_final_nav_cny": 823833.7129999999,
        },
        "selected_configs": [_main_config_readout()],
        "baseline_configs": [
            _quality_replacement_rebalance_control_readout(),
            _upstream_meta_stability_control_readout(),
            _negative_month_rank_adjusted_control_readout(),
            _meta_signal_quality_control_readout(),
            _three_part_stability_control_readout(),
            _conditional_aggressive_control_readout(),
            _control_config_readout(),
        ],
        "holdout_configs": [],
        "rejected_configs": [],
        "metric_groups": _historical_metric_groups(),
        "leakage_audit": {
            "status": "passed",
            "read_model_policy": "static_metrics_only_no_market_scan_no_dynamic_replay",
        },
        "research_labeling": _research_labeling(EVIDENCE_BASIS_HISTORY),
        "event_refs": ["shortpick_strategy_lab.static_historical_replay.v1"],
    }


def build_shortpick_strategy_lab_paper_tracking_read_model(
    *,
    include_records: bool = True,
    paper_state_path: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Return the forward paper tracking read model.

    The read model is intentionally lightweight: paper rows and planned orders come from a persisted state artifact
    written by the daily refresh path. Missing state is rendered as an empty forward ledger rather than a replay.
    """

    today = today or date.today()
    state_path = _resolve_paper_state_path(paper_state_path)
    state = _read_paper_state(state_path)
    records = _records_from_state(state) if include_records else []
    planned_orders = _planned_orders_from_state(state)
    account_states = (state or {}).get("account_states") if isinstance((state or {}).get("account_states"), dict) else {}
    source_coverage = (state or {}).get("source_coverage") if isinstance((state or {}).get("source_coverage"), dict) else {}
    plan_generation_status = (state or {}).get("plan_generation_status") if isinstance((state or {}), dict) else None
    if not isinstance(plan_generation_status, dict):
        plan_generation_status = {
            "status": "unknown",
            "message": "尚未写入 v3 计划源状态。",
        }
    tracking_start = str((state or {}).get("tracking_start_date") or TRACKING_START_DATE)
    latest_plan_signal_date = _latest_value(planned_orders, "signal_date") or plan_generation_status.get("signal_date")
    plan_status_code = str(plan_generation_status.get("status") or "unknown")
    plan_ready = plan_status_code.startswith("ready")
    no_order_ready = plan_status_code == "ready_no_executable_orders"
    summary = {
        "record_count": len(records),
        "buy_count": sum(1 for row in records if str(row.get("action") or "") == "buy"),
        "sell_count": sum(1 for row in records if str(row.get("action") or "") == "sell"),
        "planned_order_count": len(planned_orders),
        "tracking_start_date": tracking_start,
        "latest_plan_signal_date": latest_plan_signal_date,
        "initial_cash_cny": INITIAL_CASH_CNY,
        "plan_generation_status": plan_status_code,
    }
    return {
        "generated_at": _now_iso(),
        "schema_version": STRATEGY_LAB_SCHEMA_VERSION,
        "status": "active" if plan_ready else "blocked",
        "current_status": (
            "active"
            if records
            else "awaiting_first_forward_fill"
            if planned_orders
            else "blocked_missing_v3_plan_source"
            if not plan_ready
            else "model_cash_or_no_executable_order"
            if no_order_ready
            else "awaiting_v3_plan"
        ),
        "current_message": (
            "纸面账户已有成交，并已生成下一交易日计划单。"
            if records and planned_orders
            else "已生成明日计划单，等待纸面成交记录。"
            if planned_orders
            else str(plan_generation_status.get("message") or "v3 计划源未就绪。")
            if not plan_ready or no_order_ready
            else "纸面追踪已从今日起启用，等待下一次日刷写入明日计划单。"
        ),
        "claim_ceiling": CLAIM_CEILING,
        "evidence_basis": EVIDENCE_BASIS_PAPER,
        "ui_language": "所有 v3 策略统一从 2026-07-08 起算；历史回放收益不会写入纸面账户。",
        "data_disclaimer": "纸面追踪是研究观察，不构成投资建议或生产交易自动化。",
        "source_contract_ref": "docs/contracts/SHORTPICK_V3_PAPER_LEDGER_CONTRACT_2026-07-13.md",
        "source_artifacts": {
            "paper_state": {
                "path": str(state_path),
                "status": "ready" if state is not None else "missing",
                "schema_version": (state or {}).get("schema_version"),
            }
        },
        "tracking_window": {
            "start_date": tracking_start,
            "start_policy": "common_window_2026_07_08_with_labeled_synchronized_backfill",
            "today": today.isoformat(),
        },
        "account_contract": _account_contract(),
        "row_contract": {
            "records_source": "persisted_paper_state_artifact_only",
            "historical_replay_rows_allowed": False,
            "initial_record_count": 0,
        },
        "selected_configs": [
            _paper_config_with_account_state(_paper_main_config_readout(), account_states, records, planned_orders)
        ],
        "baseline_configs": [
            _paper_config_with_account_state(readout, account_states, records, planned_orders)
            for readout in (
                _paper_quality_replacement_rebalance_control_readout(),
                _paper_upstream_meta_stability_control_readout(),
                _paper_negative_month_rank_adjusted_control_readout(),
                _paper_meta_signal_quality_control_readout(),
                _paper_three_part_stability_control_readout(),
                _paper_conditional_aggressive_control_readout(),
                _paper_control_config_readout(),
            )
        ],
        "paper_governance": {
            "status": "active_forward_observation",
            "primary_config_id": MAIN_CONFIG_ID,
            "control_config_ids": [
                QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
                UPSTREAM_META_STABILITY_CONTROL_ID,
                NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID,
                META_SIGNAL_QUALITY_CONTROL_ID,
                THREE_PART_STABILITY_CONTROL_ID,
                CONDITIONAL_AGGRESSIVE_CONTROL_ID,
                CONTROL_CONFIG_ID,
            ],
            "daily_sync_policy": "same_scheduled_refresh_window_as_shortpick_v1",
        },
        "paper_display": _paper_display(
            summary=summary,
            records=records,
            planned_orders=planned_orders,
            tracking_start=tracking_start,
            plan_generation_status=plan_generation_status,
            account_states=account_states,
            source_coverage=source_coverage,
        ),
        "records": records,
        "summary": summary,
        "leakage_audit": {
            "status": "passed",
            "read_model_policy": "forward_paper_state_only_no_v2_replay_cache_no_dynamic_backtest",
        },
        "research_labeling": _research_labeling(EVIDENCE_BASIS_PAPER),
        "event_refs": ["shortpick_strategy_lab.forward_paper_tracking.v1"],
    }


def _main_config_readout() -> dict[str, Any]:
    return {
        "config_id": MAIN_CONFIG_ID,
        "label": "主策略：14 tranche 复投 + 分层退出",
        "role": "primary_forward_observation",
        "selection_rank": 1,
        "gate_status": "active",
        "reason": "完整历史收益最高，回撤和负月份未劣化；覆盖 Rank1 快速冲高失败与 Rank3 回撤后期亏损保护。",
        "summary": {
            "total_return": 3.119168564999999,
            "annualized_return": 0.6577172359709627,
            "max_drawdown": -0.07759130606066467,
            "negative_month_count": 4,
            "worst_monthly_return": -0.017802132479532773,
            "skipped_order_rate": 0.352260778128286,
            "skipped_signal_rate": 0.2455795677799607,
            "buy_order_count": 616,
            "sell_order_count": 598,
            "final_nav_cny": 823833.7129999999,
            "mean_invested_ratio": 0.6575855950174195,
            "p95_invested_ratio": 0.9738938996466462,
            "max_single_symbol_exposure_pct": 0.2676257460816531,
            "max_position_count": 37,
            "turnover": 86.75235328499998,
        },
        "selection_summary": {
            "tranche_count": 14,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2250,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
        },
        "reason_counts": {
            "below_min_order_notional": 264,
            "insufficient_cash": 15,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 30,
            "single_symbol_concentration_cap": 5,
        },
        "decision_samples": [],
    }


def _control_config_readout() -> dict[str, Any]:
    return {
        "config_id": CONTROL_CONFIG_ID,
        "label": "对照组：15 tranche 低集中度复投",
        "role": "lower_concentration_control",
        "selection_rank": 2,
        "gate_status": "active_control",
        "reason": "收益低于主策略，但买入更分散、跳过率更低，用于观察资金分散方向是否更适合前向环境。",
        "summary": {
            "total_return": 2.9338336924999995,
            "annualized_return": 0.6306921731524535,
            "max_drawdown": -0.07924388161723195,
            "negative_month_count": 5,
            "worst_monthly_return": -0.01726134810266111,
            "skipped_order_rate": 0.21766561514195584,
            "skipped_signal_rate": 0.21611001964636542,
            "buy_order_count": 744,
            "sell_order_count": 724,
            "final_nav_cny": 786766.7384999999,
            "mean_invested_ratio": 0.6411819683965754,
            "p95_invested_ratio": 0.9599565232500028,
            "max_single_symbol_exposure_pct": 0.2531534807918632,
            "max_position_count": 41,
            "turnover": 81.7173503325,
        },
        "selection_summary": {
            "tranche_count": 15,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1000,
            "exit_policy": "mechanical_horizon",
        },
        "reason_counts": {
            "below_min_order_notional": 82,
            "insufficient_cash": 11,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 90,
            "single_symbol_concentration_cap": 3,
        },
        "decision_samples": [],
    }


def _conditional_aggressive_control_readout() -> dict[str, Any]:
    return {
        "config_id": CONDITIONAL_AGGRESSIVE_CONTROL_ID,
        "label": "候选对照：条件化攻击模式",
        "role": "conditional_aggressive_control_candidate",
        "selection_rank": 2,
        "gate_status": "candidate_control",
        "reason": (
            "在 Rank1 动量极强、基准不弱、行业不过热且未明显跌离 20 日高点的 26 个信号日，"
            "把当日 Rank 权重放大到 14/11；收益和年化优于主策略，回撤略优，跳过率仅小幅上升。"
        ),
        "summary": {
            "total_return": 3.1897186824999997,
            "annualized_return": 0.6677990260254718,
            "max_drawdown": -0.0773095502778558,
            "negative_month_count": 4,
            "worst_monthly_return": -0.017802132479532773,
            "skipped_order_rate": 0.35541535226077814,
            "skipped_signal_rate": 0.24950884086444008,
            "buy_order_count": 613,
            "sell_order_count": 595,
            "final_nav_cny": 837943.7365,
            "mean_invested_ratio": 0.6642791352600816,
            "p95_invested_ratio": 0.9779863369527485,
            "max_single_symbol_exposure_pct": 0.2676534208214223,
            "max_position_count": 36,
            "turnover": 88.65149354249999,
        },
        "selection_summary": {
            "tranche_count": 14,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2250,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "conditional_aggressive_overlay": {
                "scale": 14 / 11,
                "aggressive_signal_day_count": 26,
                "rule": (
                    "Rank1 benchmark_return_20d >= 0, return_20d_percentile >= 0.98, "
                    "industry_return_20d_excess <= 0.35, distance_from_20d_high >= -0.08"
                ),
            },
        },
        "reason_counts": {
            "below_min_order_notional": 263,
            "insufficient_cash": 18,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 31,
            "single_symbol_concentration_cap": 5,
        },
        "decision_samples": [],
    }


def _three_part_stability_control_readout() -> dict[str, Any]:
    return {
        "config_id": THREE_PART_STABILITY_CONTROL_ID,
        "label": "候选对照：三段稳定性控制",
        "role": "execution_stability_control_candidate",
        "selection_rank": 2,
        "gate_status": "candidate_control",
        "reason": (
            "在 1000 元最小下单额基础上，弱基准日降权、强 Rank1 信号日加权，并把单票成本上限收紧到 28%；"
            "在不劣化收益、回撤、负月份、跳过率和集中度的前提下，订单跳过率改善超过 10%。"
        ),
        "summary": {
            "total_return": 3.1867116250000036,
            "annualized_return": 0.6673715464095795,
            "max_drawdown": -0.07563891723725635,
            "negative_month_count": 4,
            "worst_monthly_return": -0.01772263876613067,
            "skipped_order_rate": 0.231335436382755,
            "skipped_signal_rate": 0.2220039292730845,
            "buy_order_count": 731,
            "sell_order_count": 711,
            "final_nav_cny": 837342.3250000007,
            "mean_invested_ratio": 0.6546080867280545,
            "p95_invested_ratio": 0.965997547364644,
            "max_single_symbol_exposure_pct": 0.2610126540697801,
            "max_position_count": 35,
            "turnover": 87.70856572500001,
        },
        "selection_summary": {
            "tranche_count": 14,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1000,
            "max_single_symbol_cost_basis_pct": 0.28,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "three_part_stability_overlay": {
                "weak_scale": 0.85,
                "weak_rule": "Rank1 benchmark_return_20d < -0.02",
                "strong_scale": 1.60,
                "strong_rule": (
                    "Rank1 benchmark_return_20d >= 0, return_20d_percentile >= 0.98, "
                    "industry_return_20d_excess <= 0.50, distance_from_20d_high >= -0.08"
                ),
                "weak_signal_day_count": 137,
                "strong_signal_day_count": 41,
            },
        },
        "goal10_improvements": {
            "total_return_rel": 0.021654187195235597,
            "annualized_return_rel": 0.014678512148711631,
            "drawdown_reduction_rel": 0.02516246887095624,
            "skip_order_reduction_rel": 0.3432835820895522,
            "skip_signal_reduction_rel": 0.09599999999999996,
            "exposure_reduction_rel": 0.024710223544245173,
        },
        "reason_counts": {
            "below_min_order_notional": 71,
            "insufficient_cash": 20,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 93,
            "single_symbol_concentration_cap": 15,
        },
        "decision_samples": [],
    }


def _meta_signal_quality_control_readout() -> dict[str, Any]:
    return {
        "config_id": META_SIGNAL_QUALITY_CONTROL_ID,
        "label": "候选对照：元信号质量分层",
        "role": "meta_signal_quality_control_candidate",
        "selection_rank": 2,
        "gate_status": "candidate_control",
        "reason": (
            "在三段稳定性控制基础上，引入入场前元信号质量分层：强行业领导力且基准强时加权，"
            "行业领导力弱且基准不强时轻降权；在不劣化收益、回撤、最差月、跳过率和集中度的前提下，"
            "负月份从 4 个降至 3 个。"
        ),
        "summary": {
            "total_return": 3.2283272599999995,
            "annualized_return": 0.6732701332016364,
            "max_drawdown": -0.07279871301766871,
            "negative_month_count": 3,
            "worst_monthly_return": -0.015466628621165768,
            "skipped_order_rate": 0.2302839116719243,
            "skipped_signal_rate": 0.21611001964636542,
            "buy_order_count": 732,
            "sell_order_count": 712,
            "final_nav_cny": 845665.4519999998,
            "mean_invested_ratio": 0.6415002584714182,
            "p95_invested_ratio": 0.9529346262868691,
            "max_single_symbol_exposure_pct": 0.2521478386902156,
            "max_position_count": 36,
            "turnover": 87.19843104,
        },
        "selection_summary": {
            "tranche_count": 14,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1000,
            "max_single_symbol_cost_basis_pct": 0.28,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "three_part_stability_overlay": {
                "weak_scale": 0.92,
                "weak_rule": "Rank1 benchmark_return_20d < -0.02",
                "strong_scale": 1.65,
                "strong_rule": (
                    "Rank1 benchmark_return_20d >= 0, return_20d_percentile >= 0.98, "
                    "industry_return_20d_excess <= 0.50, distance_from_20d_high >= -0.08"
                ),
                "weak_signal_day_count": 137,
                "strong_signal_day_count": 41,
            },
            "meta_signal_quality_overlay": {
                "industry_leadership_scale": 1.35,
                "industry_leadership_rule": (
                    "Rank1 industry_return_20d_excess >= 0.35 and benchmark_return_20d >= 0.05"
                ),
                "low_quality_scale": 0.90,
                "low_quality_rule": "Rank1 industry_return_20d_excess <= 0.20 and benchmark_return_20d <= 0.08",
                "industry_leadership_signal_day_count": 14,
                "low_quality_signal_day_count": 339,
            },
        },
        "goal10_improvements": {
            "total_return_rel": 0.013059115444748137,
            "annualized_return_rel": 0.00883853503163401,
            "drawdown_reduction_rel": 0.03754950921202083,
            "negative_month_delta": 1,
            "worst_monthly_return_delta": 0.002256010144964904,
            "skip_order_reduction_rel": 0.0045454545454545175,
            "skip_signal_reduction_rel": 0.02654867256637173,
            "exposure_reduction_rel": 0.03396316324646279,
        },
        "reason_counts": {
            "below_min_order_notional": 72,
            "insufficient_cash": 17,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 94,
            "single_symbol_concentration_cap": 15,
        },
        "decision_samples": [],
    }


def _quality_replacement_rebalance_control_readout() -> dict[str, Any]:
    return {
        "config_id": QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
        "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
        "label": "候选对照：高质量可买替补 + 25% 暴露再平衡",
        "role": "quality_replacement_rebalance_candidate",
        "selection_rank": 1,
        "gate_status": "candidate_control",
        "reason": (
            "完整历史逐订单回放严格超过前端全部策略逐指标最优值；负收益月份从最优 3 个降至 2 个，"
            "订单跳过率和信号跳过率分别相对改善 20.21% 与 31.63%。"
        ),
        "summary": {
            "total_return": 3.4176736350000008,
            "annualized_return": 0.6996469611916643,
            "max_drawdown": -0.06796905647829043,
            "negative_month_count": 2,
            "worst_monthly_return": -0.014130266706049999,
            "skipped_order_rate": 0.15560165975103735,
            "skipped_signal_rate": 0.13111545988258316,
            "buy_order_count": 814,
            "sell_order_count": 790,
            "final_nav_cny": 883534.7270000002,
            "mean_invested_ratio": 0.6909971507926389,
            "p95_invested_ratio": 0.9872182920144233,
            "max_single_symbol_exposure_pct": 0.24953416606359471,
            "max_position_count": 37,
            "turnover": 99.425354415,
        },
        "selection_summary": {
            "signal_date_from": "2023-09-07",
            "signal_date_to": "2026-06-26",
            "signal_day_count": 511,
            "selected_pick_count": 1533,
            "tranche_count": 15,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 250,
            "max_single_symbol_cost_basis_pct": 0.35,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "rank1_quality_overlay": {
                "return_20d_percentile_min": 0.95,
                "return_5d_percentile_min": 0.93,
                "benchmark_return_20d_min": 0.0,
                "industry_return_20d_excess_max": 0.50,
                "distance_from_20d_high_min": -0.08,
                "strong_scale": 1.54,
            },
            "affordable_replacement": {
                "source": "same_day_pit_top20_inventory",
                "inventory_rank_range": [4, 5],
                "max_score_gap": 0.10,
                "min_fill_ratio": 0.75,
                "accepted_replacement_count": 53,
            },
            "market_value_rebalance": {
                "threshold": 0.25,
                "timing": "scheduled_exits_then_entries_then_close_mark_then_trim",
                "rebalance_sell_order_count": 2,
                "post_executable_order_breach_day_count": 0,
            },
        },
        "goal10_improvements": {
            "total_return_rel": 0.016198551986917133,
            "annualized_return_rel": 0.010855455255086665,
            "drawdown_reduction_rel": 0.017794513220975926,
            "negative_month_delta": 1,
            "worst_monthly_return_rel": 0.0035352726121860136,
            "skip_order_reduction_rel": 0.20212765957446807,
            "skip_signal_reduction_rel": 0.3163265306122449,
            "exposure_reduction_rel": 0.009245479498723404,
            "final_nav_rel": 0.01248600810220579,
        },
        "reason_counts": {
            "below_min_order_notional": 13,
            "insufficient_cash": 39,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 59,
            "single_symbol_concentration_cap": 18,
        },
        "decision_samples": [],
    }


def _upstream_meta_stability_control_readout() -> dict[str, Any]:
    return {
        "config_id": UPSTREAM_META_STABILITY_CONTROL_ID,
        "label": "候选对照：上游元信号稳健缩放",
        "role": "upstream_meta_signal_candidate",
        "selection_rank": 2,
        "gate_status": "candidate_control",
        "reason": (
            "保持 20 万资金池、14 tranche、2250 元最小下单额和分层退出不变，只在上游信号日根据 Rank1 "
            "元信号质量缩放 selected_top_k 权重；完整历史回放里收益不劣化，最大回撤相对改善超过 10%，"
            "负收益月份从 4 个降至 3 个。"
        ),
        "summary": {
            "total_return": 3.363194749999999,
            "annualized_return": 0.6921335365550461,
            "max_drawdown": -0.06920044470651798,
            "negative_month_count": 3,
            "worst_monthly_return": -0.014710185838297973,
            "skipped_order_rate": 0.3470031545741325,
            "skipped_signal_rate": 0.2455795677799607,
            "buy_order_count": 621,
            "sell_order_count": 602,
            "final_nav_cny": 872638.9499999998,
            "mean_invested_ratio": 0.6529829795470149,
            "p95_invested_ratio": 0.9672444902038784,
            "max_single_symbol_exposure_pct": 0.2518627580294479,
            "max_position_count": 36,
            "turnover": 90.51497414999999,
        },
        "selection_summary": {
            "tranche_count": 14,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 2250,
            "max_single_symbol_cost_basis_pct": 0.35,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "upstream_weight_scaling": {
                "family": "rank1_signal_day_portfolio_weight_scaling",
                "mutated_signal_day_count": 389,
                "mutated_pick_count": 1167,
                "weak_scale": 1.00,
                "weak_rule": "Rank1 benchmark_return_20d < -0.02",
                "strong_scale": 1.65,
                "strong_rule": (
                    "Rank1 benchmark_return_20d >= 0, return_20d_percentile >= 0.98, "
                    "industry_return_20d_excess <= 0.50, distance_from_20d_high >= -0.08"
                ),
                "industry_leadership_scale": 1.35,
                "industry_leadership_rule": (
                    "Rank1 industry_return_20d_excess >= 0.35 and benchmark_return_20d >= 0.05"
                ),
                "low_quality_scale": 0.90,
                "low_quality_rule": "Rank1 industry_return_20d_excess <= 0.20 and benchmark_return_20d <= 0.08",
                "weak_signal_day_count": 137,
                "strong_signal_day_count": 41,
                "industry_leadership_signal_day_count": 14,
                "low_quality_signal_day_count": 339,
            },
        },
        "goal10_improvements": {
            "total_return_rel": 0.07823436916433535,
            "annualized_return_rel": 0.05232689475329918,
            "drawdown_reduction_rel": 0.10814177232158328,
            "negative_month_delta": 1,
            "worst_monthly_return_delta": 0.0030919466412347996,
            "skip_order_reduction_rel": 0.014925373134328266,
            "skip_signal_reduction_rel": 0.0,
            "exposure_reduction_rel": 0.058899370792957643,
        },
        "reason_counts": {
            "below_min_order_notional": 248,
            "insufficient_cash": 21,
            "missing_entry_bar": 3,
            "missing_entry_bar_near_signal": 18,
            "price_too_high_for_slot": 33,
            "single_symbol_concentration_cap": 7,
        },
        "decision_samples": [],
    }


def _negative_month_rank_adjusted_control_readout() -> dict[str, Any]:
    return {
        "config_id": NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID,
        "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
        "label": "候选对照：递归上游 Rank 权重调整",
        "role": "recursive_upstream_rank_weight_candidate",
        "selection_rank": 2,
        "gate_status": "candidate_control",
        "reason": (
            "递归式上游探索候选：保留 capacity-cluster 入选结构，但在模型输出层对 Rank1/Rank2 做可解释的"
            "动态组合权重调整；完整历史逐订单回放中收益、回撤、跳过率和单票暴露均不劣化，负收益月份从 4 个降至 3 个。"
        ),
        "summary": {
            "total_return": 3.1410609749999994,
            "annualized_return": 0.6608575171773754,
            "max_drawdown": -0.07012803058821693,
            "negative_month_count": 3,
            "worst_monthly_return": -0.014180398279718176,
            "skipped_order_rate": 0.1950207468879668,
            "skipped_signal_rate": 0.1917808219178082,
            "buy_order_count": 776,
            "sell_order_count": None,
            "final_nav_cny": 828212.195,
            "mean_invested_ratio": None,
            "p95_invested_ratio": None,
            "max_single_symbol_exposure_pct": 0.25278436325160336,
            "max_position_count": None,
            "turnover": None,
        },
        "selection_summary": {
            "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
            "tranche_count": 15,
            "budget_mode": "current_nav_fraction",
            "min_order_notional_cny": 1000,
            "exit_policy": "rank3_pullback_rank1_quick_fail_guard",
            "rank_portfolio_adjustment": {
                "industry_leader_rank12_boost": 1.30,
                "rank1_strong_tail_low_industry_scale": 0.88,
                "rank1_stale_high20_fading_scale": 0.75,
                "rank1_strong_pullback_trim": 0.90,
            },
        },
        "goal10_improvements": {
            "total_return_rel": 0.029382916707000818,
            "annualized_return_rel": 0.019954982682119354,
            "drawdown_reduction_rel": 0.017716621018800005,
            "negative_month_delta": 1,
            "worst_monthly_return_delta": 0.003080949822942935,
            "worst_monthly_return_rel": 0.1784883662978767,
            "skip_order_reduction_rel": 0.015706806282722457,
            "skip_signal_reduction_rel": 0.010101010101010102,
            "exposure_reduction_rel": 0.0014580780762137376,
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_main_config_readout() -> dict[str, Any]:
    readout = _main_config_readout()
    return {
        **readout,
        "reason": "前向纸面追踪从 20 万本金重新开始；历史回放收益只作为历史页静态指标，不计入这里。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_quality_replacement_rebalance_control_readout() -> dict[str, Any]:
    readout = _quality_replacement_rebalance_control_readout()
    return {
        **readout,
        "reason": "高质量可买替补与 25% 暴露再平衡按历史回放同一规则从 20 万本金开始前向观察。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_control_config_readout() -> dict[str, Any]:
    readout = _control_config_readout()
    return {
        **readout,
        "reason": "低集中度对照组同样只做从今日开始的真实前向观察，不继承历史回放收益。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_conditional_aggressive_control_readout() -> dict[str, Any]:
    readout = _conditional_aggressive_control_readout()
    return {
        **readout,
        "reason": "条件化攻击对照组同样只做从今日开始的真实前向观察；历史回放收益只在历史页展示。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_three_part_stability_control_readout() -> dict[str, Any]:
    readout = _three_part_stability_control_readout()
    return {
        **readout,
        "reason": "三段稳定性控制同样只做从今日开始的真实前向观察；历史回放收益只在历史页展示。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_meta_signal_quality_control_readout() -> dict[str, Any]:
    readout = _meta_signal_quality_control_readout()
    return {
        **readout,
        "reason": "元信号质量分层候选同样只做从今日开始的真实前向观察；历史回放收益只在历史页展示。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_upstream_meta_stability_control_readout() -> dict[str, Any]:
    readout = _upstream_meta_stability_control_readout()
    return {
        **readout,
        "reason": "上游元信号稳健缩放候选同样只做从今日开始的真实前向观察；历史回放收益只在历史页展示。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_negative_month_rank_adjusted_control_readout() -> dict[str, Any]:
    readout = _negative_month_rank_adjusted_control_readout()
    return {
        **readout,
        "reason": "递归上游 Rank 权重调整候选同样只做从今日开始的真实前向观察；历史回放收益只在历史页展示。",
        "summary": {
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": INITIAL_CASH_CNY,
            "paper_total_return": None,
            "max_drawdown": None,
            "record_count": 0,
            "planned_order_count": None,
            "forward_status": "awaiting_first_forward_fill",
        },
        "reason_counts": {},
        "decision_samples": [],
    }


def _paper_config_with_account_state(
    readout: dict[str, Any],
    account_states: dict[str, Any],
    records: list[dict[str, Any]],
    planned_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    config_id = str(readout.get("config_id") or "")
    state = account_states.get(config_id) if isinstance(account_states.get(config_id), dict) else {}
    nav_rows = [row for row in state.get("nav_points") or [] if isinstance(row, dict)]
    peak_nav = float(INITIAL_CASH_CNY)
    max_drawdown = 0.0
    for row in nav_rows:
        nav = float(row.get("nav_cny") or INITIAL_CASH_CNY)
        peak_nav = max(peak_nav, nav)
        max_drawdown = min(max_drawdown, nav / peak_nav - 1.0 if peak_nav else 0.0)
    latest_nav = float(state.get("latest_nav_cny") or INITIAL_CASH_CNY)
    record_count = sum(1 for row in records if row.get("strategy_id") == config_id)
    planned_order_count = sum(1 for row in planned_orders if row.get("strategy_id") == config_id)
    return {
        **readout,
        "summary": {
            **(readout.get("summary") or {}),
            "initial_cash_cny": INITIAL_CASH_CNY,
            "current_nav_cny": latest_nav,
            "paper_total_return": latest_nav / INITIAL_CASH_CNY - 1.0 if record_count else None,
            "max_drawdown": max_drawdown if record_count else None,
            "record_count": record_count,
            "planned_order_count": planned_order_count,
            "forward_status": "tracking_active" if record_count else "awaiting_first_forward_fill",
        },
    }


def _historical_metric_groups() -> list[dict[str, Any]]:
    return [
        {
            "title": "收益与资金曲线",
            "items": [
                {"label": "初始资金", "value": INITIAL_CASH_CNY, "format": "currency"},
                {"label": "最终净值", "value": 823833.7129999999, "format": "currency"},
                {"label": "总收益", "value": 3.119168564999999, "format": "percent"},
                {"label": "年化收益", "value": 0.6577172359709627, "format": "percent"},
            ],
        },
        {
            "title": "稳定性与回撤",
            "items": [
                {"label": "最大回撤", "value": -0.07759130606066467, "format": "percent"},
                {"label": "负收益月份", "value": 4, "format": "number"},
                {"label": "最差月收益", "value": -0.017802132479532773, "format": "percent"},
                {"label": "平均投入比例", "value": 0.6575855950174195, "format": "percent"},
            ],
        },
        {
            "title": "执行约束",
            "items": [
                {"label": "买入订单", "value": 616, "format": "number"},
                {"label": "订单跳过率", "value": 0.352260778128286, "format": "percent"},
                {"label": "信号跳过率", "value": 0.2455795677799607, "format": "percent"},
                {"label": "最大单票暴露", "value": 0.2676257460816531, "format": "percent"},
            ],
        },
    ]


def _paper_display(
    *,
    summary: dict[str, Any],
    records: list[dict[str, Any]],
    planned_orders: list[dict[str, Any]],
    tracking_start: str,
    plan_generation_status: dict[str, Any],
    account_states: dict[str, Any],
    source_coverage: dict[str, Any],
) -> dict[str, Any]:
    latest_order = planned_orders[0] if planned_orders else None
    plan_status_code = str(plan_generation_status.get("status") or "unknown")
    plan_ready = plan_status_code.startswith("ready")
    account_curves = _paper_account_curves(account_states, records)
    main_account = account_states.get(MAIN_CONFIG_ID) if isinstance(account_states.get(MAIN_CONFIG_ID), dict) else {}
    main_nav = float(main_account.get("latest_nav_cny") or INITIAL_CASH_CNY)
    main_record_count = sum(1 for row in records if row.get("strategy_id") == MAIN_CONFIG_ID)
    latest_record_date = max((str(row.get("trade_date") or "") for row in records), default="")
    return {
        "title": "v3 模型纸面追踪",
        "status_label": (
            "纸面追踪运行中"
            if records
            else "纸面追踪"
            if plan_ready
            else "v3 计划源未就绪"
        ),
        "subtitle": (
            ""
            if plan_ready
            else str(plan_generation_status.get("message") or "缺少 v3 selected_top_k 计划源。")
        ),
        "latest_trade": _latest_trade_display(latest_order, planned_orders, plan_generation_status),
        "strategy_explanation": {
            "title": "策略说明",
            "items": [
                {"label": "主策略", "value": "14 tranche 复投，按模型 Rank 权重下单，叠加分层退出。"},
                {"label": "卖出规则", "value": "基础为 20 日退出；Rank1 快速冲高失败和 Rank3 入场回撤后期亏损会提前退出。"},
                {
                    "label": "对照组",
                    "value": (
                        "包含高质量可买替补与 25% 暴露再平衡、递归上游 Rank 调整、"
                        "元信号缩放及低集中度复投等方向性对照。"
                    ),
                },
            ],
        },
        "charts": [],
        "table": {
            "title": "交易明细",
            "columns": [
                {"key": "signal_date_text", "label": "信号日"},
                {"key": "strategy_text", "label": "策略"},
                {"key": "action_text", "label": "动作"},
                {"key": "stock_text", "label": "标的"},
                {"key": "quantity_text", "label": "数量"},
                {"key": "cash_after_text", "label": "剩余现金"},
                {"key": "exit_state_text", "label": "退出状态"},
                {"key": "return_text", "label": "收益"},
                {"key": "note", "label": "说明"},
            ],
            "rows": [_paper_record_display_row(record) for record in records],
            "empty_text": "统一纸面追踪窗口尚无成交记录。",
        },
        "account_curves": account_curves,
        "planned_orders": planned_orders,
        "plan_generation_status": plan_generation_status,
        "coverage": {
            "coverage_start": tracking_start,
            "coverage_end": latest_record_date or str(source_coverage.get("end_date") or tracking_start),
            "latest_source_signal_date": summary.get("latest_plan_signal_date"),
            "paper_record_count": summary.get("record_count"),
            "true_forward_record_count": sum(
                1 for row in records if row.get("evidence_basis") == "daily_forward_capture"
            ),
            "synchronized_backfill_record_count": sum(
                1 for row in records if row.get("evidence_basis") == "synchronized_start_backfill"
            ),
            "planned_order_count": summary.get("planned_order_count"),
            "historical_replay_row_count": 0,
            "strategy_count": len(account_states),
            "common_start_enforced": bool(source_coverage.get("common_start_enforced")),
            "source_gap_count": 0,
        },
        "summary_cards": [
            {"label": "初始本金", "value": f"{INITIAL_CASH_CNY}"},
            {"label": "主策略当前净值", "value": f"{main_nav:.2f}"},
            {
                "label": "主策略纸面收益",
                "value": f"{main_nav / INITIAL_CASH_CNY - 1.0:+.2%}" if main_record_count else "等待首笔成交",
            },
            {"label": "纸面成交记录", "value": str(summary.get("record_count") or 0)},
            {"label": "明日计划单", "value": str(summary.get("planned_order_count") or 0)},
            {"label": "计划源状态", "value": "v3 ready" if plan_ready else "阻塞"},
            {"label": "追踪起点", "value": tracking_start},
            {"label": "最新信号日", "value": str(summary.get("latest_plan_signal_date") or "等待日刷")},
        ],
    }


def _paper_account_curves(account_states: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sell_counts: dict[str, int] = {}
    for record in records:
        if record.get("action") == "sell":
            strategy_id = str(record.get("strategy_id") or "")
            sell_counts[strategy_id] = sell_counts.get(strategy_id, 0) + 1
    curves: list[dict[str, Any]] = []
    for strategy_id, state in account_states.items():
        if not isinstance(state, dict):
            continue
        points: list[dict[str, Any]] = []
        peak_nav = float(INITIAL_CASH_CNY)
        max_drawdown = 0.0
        for row in state.get("nav_points") or []:
            if not isinstance(row, dict):
                continue
            nav = float(row.get("nav_cny") or INITIAL_CASH_CNY)
            peak_nav = max(peak_nav, nav)
            drawdown = nav / peak_nav - 1.0 if peak_nav else 0.0
            max_drawdown = min(max_drawdown, drawdown)
            points.append(
                {
                    "date": row.get("date"),
                    "nav_cny": nav,
                    "account_return": nav / INITIAL_CASH_CNY - 1.0,
                    "drawdown": drawdown,
                }
            )
        latest_nav = float(state.get("latest_nav_cny") or INITIAL_CASH_CNY)
        curves.append(
            {
                "strategy": str(state.get("strategy_label") or strategy_id),
                "strategy_id": strategy_id,
                "initial_cash": INITIAL_CASH_CNY,
                "latest_nav": latest_nav,
                "latest_return": latest_nav / INITIAL_CASH_CNY - 1.0,
                "max_drawdown": max_drawdown,
                "point_count": len(points),
                "completed_trade_count": sell_counts.get(strategy_id, 0),
                "points": points,
            }
        )
    return curves


def _latest_trade_display(
    latest_order: dict[str, Any] | None,
    planned_orders: list[dict[str, Any]],
    plan_generation_status: dict[str, Any],
) -> dict[str, Any]:
    if latest_order is None:
        plan_status = str(plan_generation_status.get("status") or "")
        no_order_ready = plan_status == "ready_no_executable_orders"
        return {
            "title": "下一交易日计划",
            "tag": "模型现金" if no_order_ready else "计划源阻塞" if not plan_status.startswith("ready") else "等待日刷",
            "summary": str(
                plan_generation_status.get("message")
                or "还没有持久化的 v3 计划单；下一次日刷会和试验田 v1 同步写入。"
            ),
            "items": [],
            "note": "",
        }
    stock_text = f"{latest_order.get('name') or ''} · {latest_order.get('symbol') or ''}".strip(" ·")
    shares = int(float(latest_order.get("shares") or 0))
    entry_timing = str(latest_order.get("entry_timing") or "次日收盘")
    action = "卖" if latest_order.get("action") == "sell" else "买"
    summary = f"{stock_text}，{action} {shares} 股，{entry_timing}。"
    if len(planned_orders) > 1:
        summary = f"{summary} 另有 {len(planned_orders) - 1} 条对照组计划单。"
    return {
        "title": "下一交易日计划",
        "tag": "待执行",
        "summary": summary,
        "items": [
            {"label": "信号日", "value": latest_order.get("signal_date")},
            {"label": "预计买入日", "value": latest_order.get("planned_entry_date")},
            {"label": "策略", "value": latest_order.get("strategy_label")},
            {"label": "股票", "value": stock_text},
            {"label": "买入方式", "value": f"{entry_timing}，买 {shares} 股"},
            {"label": "预计金额", "value": latest_order.get("estimated_notional_cny")},
        ],
        "note": str(latest_order.get("note") or "按 20 万资金池和 100 股整手约束生成。"),
    }


def _paper_record_display_row(record: dict[str, Any]) -> dict[str, Any]:
    stock_text = f"{record.get('name') or ''} · {record.get('symbol') or ''}".strip(" ·")
    return {
        "row_key": str(record.get("row_key") or record.get("id") or ""),
        "signal_date_text": record.get("signal_date"),
        "strategy_text": record.get("strategy_label"),
        "action_text": record.get("action_label") or record.get("action"),
        "stock_text": stock_text,
        "quantity_text": record.get("quantity_text") or (
            f"{int(float(record.get('shares') or 0))} 股" if record.get("shares") is not None else ""
        ),
        "cash_after_text": record.get("cash_after_text"),
        "exit_state_text": record.get("exit_state_text") or "持仓中",
        "return_text": record.get("return_text") or "未退出",
        "note": record.get("note") or "",
    }


def _account_contract() -> dict[str, Any]:
    return {
        "initial_cash_cny": INITIAL_CASH_CNY,
        "capital_pool_scope": "<=200000_cny_practical_pool",
        "board_lot_size": BOARD_LOT_SIZE,
        "cash_account_only": True,
        "margin_allowed": False,
        "short_selling_allowed": False,
        "budget_mode": "current_nav_fraction",
        "max_single_signal_deployment_pct": 0.25,
    }


def _resolve_paper_state_path(explicit_path: str | Path | None = None) -> Path:
    if explicit_path is not None:
        return Path(explicit_path)
    configured = os.getenv(PAPER_STATE_ENV)
    if configured:
        return Path(configured)
    for candidate in DEFAULT_PAPER_STATE_CANDIDATES:
        path = PROJECT_ROOT / candidate
        if path.exists():
            return path
    return PROJECT_ROOT / DEFAULT_PAPER_STATE_CANDIDATES[0]


def _read_paper_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != PAPER_STATE_SCHEMA_VERSION:
        return None
    return payload


def _planned_orders_from_state(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (state or {}).get("planned_orders") or []
    if not isinstance(rows, list):
        return []
    normalized = [row for row in rows if isinstance(row, dict)]
    strategy_order = {
        MAIN_CONFIG_ID: 0,
        QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID: 1,
        UPSTREAM_META_STABILITY_CONTROL_ID: 2,
        NEGATIVE_MONTH_RANK_ADJUSTED_CONTROL_ID: 3,
        META_SIGNAL_QUALITY_CONTROL_ID: 4,
        THREE_PART_STABILITY_CONTROL_ID: 5,
        CONDITIONAL_AGGRESSIVE_CONTROL_ID: 6,
        CONTROL_CONFIG_ID: 7,
    }
    return sorted(
        normalized,
        key=lambda row: (
            strategy_order.get(str(row.get("strategy_id") or ""), 99),
            str(row.get("planned_entry_date") or ""),
            str(row.get("strategy_label") or ""),
        ),
    )


def _records_from_state(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (state or {}).get("records") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _latest_value(rows: list[dict[str, Any]], key: str) -> str | None:
    values = sorted(str(row.get(key) or "") for row in rows if row.get(key))
    return values[-1] if values else None


def _research_labeling(evidence_basis: str) -> dict[str, Any]:
    return {
        "claim_ceiling": CLAIM_CEILING,
        "evidence_basis": evidence_basis,
        "production_trading_allowed": False,
        "research_observation": True,
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def next_calendar_day(value: date) -> str:
    return (value + timedelta(days=1)).isoformat()
