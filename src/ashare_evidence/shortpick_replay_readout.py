"""Read-only Short Pick Lab historical replay decision projections."""

from __future__ import annotations

from typing import Any


CURRENT_FROZEN_STRATEGY = "low_turnover_20d_uptrend_liquid_top120"
DEFAULT_CANDIDATE_FAMILY = "momentum_10d_turnover_cooldown_rank"
LLM_FAMILY = "llm"
CORE_HORIZON = "5"


def build_shortpick_replay_decision_projection(
    replay_feedback: dict[str, Any],
    *,
    market_study: dict[str, Any] | None = None,
    entry_artifacts: dict[str, dict[str, Any]] | None = None,
    paper_tracking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build UI-facing readouts from already materialized artifacts only."""

    market_study = market_study or {}
    entry_artifacts = entry_artifacts or {}
    paper_tracking = paper_tracking or {}
    overall = _dict(replay_feedback.get("overall"))
    families = [_dict(item) for item in replay_feedback.get("families") or [] if isinstance(item, dict)]
    default_family = _find_family(families, DEFAULT_CANDIDATE_FAMILY)
    llm_family = _find_family(families, LLM_FAMILY)
    frozen_evidence = _dict(_dict(market_study.get("frozen_paper_strategy")).get("evidence"))
    frozen_summary = _dict(frozen_evidence.get("summary"))
    production_evidence = _dict(frozen_evidence.get("production_evidence"))

    return {
        "decision_readout": _decision_readout(
            overall=overall,
            llm_family=llm_family,
            default_family=default_family,
            frozen_summary=frozen_summary,
            production_evidence=production_evidence,
            paper_tracking=paper_tracking,
        ),
        "execution_funnel": _execution_funnel(overall=overall, market_study=market_study),
        "entry_sensitivity_matrix": _entry_sensitivity_matrix(
            entry_artifacts=entry_artifacts,
            paper_tracking=paper_tracking,
        ),
        "regime_stability": _deferred_projection(
            "phase_2_backlog",
            "行情阶段、月份、行业稳定性将在下一阶段由预计算 artifact 提供；当前不在页面请求时临时聚合。",
        ),
        "confidence_intervals": _deferred_projection(
            "phase_2_backlog",
            "按交易日聚类的 bootstrap 置信区间待后续离线产物补齐；策略晋级不得只看当前均值。",
        ),
        "return_attribution": _deferred_projection(
            "phase_3_backlog",
            "最佳/最差股票、日期、行业和去贡献项后的收益归因待后续 artifact 补齐。",
        ),
        "forward_tracking_alignment": _deferred_projection(
            "phase_3_backlog",
            "历史预期 vs 纸面跟踪偏离读数待前向样本继续积累后补齐。",
        ),
    }


def _decision_readout(
    *,
    overall: dict[str, Any],
    llm_family: dict[str, Any],
    default_family: dict[str, Any],
    frozen_summary: dict[str, Any],
    production_evidence: dict[str, Any],
    paper_tracking: dict[str, Any],
) -> dict[str, Any]:
    llm_metric = _family_horizon_metric(llm_family, CORE_HORIZON)
    default_metric = _family_horizon_metric(default_family, CORE_HORIZON)
    failed_checks = [str(item) for item in production_evidence.get("failed_check_ids") or []]
    paper_summary = _dict(paper_tracking.get("summary"))
    current_status = str(paper_tracking.get("current_status") or "unknown")
    frozen_excess = _float(frozen_summary.get("excess_total_return"))
    frozen_drawdown = _float(frozen_summary.get("max_drawdown"))
    llm_value = _float(llm_metric.get("tradable_mean_excess_return") or llm_metric.get("mean_excess_return"))
    default_value = _float(default_metric.get("tradable_mean_excess_return") or default_metric.get("mean_excess_return"))
    portfolio_value = frozen_excess
    sample_count = _int(llm_metric.get("completed_tradable_sample_count") or llm_metric.get("completed_official_sample_count"))

    if sample_count <= 0:
        llm_status = "insufficient_sample"
        llm_headline = "LLM自由选股样本不足"
    elif llm_value is not None and llm_value > 0:
        llm_status = "observe_only"
        llm_headline = "LLM候选有正超额，但不是可执行晋级证据"
    else:
        llm_status = "no_verified_advantage"
        llm_headline = "LLM自由选股暂未显示稳定优势"

    if failed_checks:
        frozen_status = "paper_tracking_only"
        frozen_headline = "冻结策略只保留纸面跟踪"
    elif current_status == "tracking_active":
        frozen_status = "forward_observation"
        frozen_headline = "冻结策略进入前向观察"
    else:
        frozen_status = "waiting_forward_sample"
        frozen_headline = "冻结策略等待更多前向样本"

    if default_value is None or portfolio_value is None:
        consistency_status = "missing_artifact"
        consistency_headline = "候选与组合口径等待产物补齐"
    elif default_value > 0 and portfolio_value > 0:
        consistency_status = "directionally_aligned"
        consistency_headline = "候选平均和组合资金曲线方向一致"
    elif default_value > 0 and portfolio_value <= 0:
        consistency_status = "execution_gap"
        consistency_headline = "候选平均为正，但组合执行未兑现"
    else:
        consistency_status = "selection_gap"
        consistency_headline = "候选池平均质量仍需改善"

    blocker = _primary_blocker(
        failed_checks=failed_checks,
        frozen_drawdown=frozen_drawdown,
        paper_tracking=paper_tracking,
        overall=overall,
    )
    return {
        "status": "ready",
        "basis": "precomputed_replay_feedback_and_portfolio_artifacts",
        "questions": [
            {
                "id": "llm_free_pick",
                "label": "LLM自由选股",
                "status": llm_status,
                "headline": llm_headline,
                "metric_label": "5日可交易平均超额",
                "metric_value": llm_value,
                "sample_count": sample_count,
                "reason": "候选逐条验证只衡量模型原始选股池质量，不等同真实资金组合收益。",
            },
            {
                "id": "frozen_strategy",
                "label": "冻结纸面策略",
                "status": frozen_status,
                "headline": frozen_headline,
                "metric_label": "长样本组合超额",
                "metric_value": frozen_excess,
                "sample_count": _int(frozen_summary.get("trade_count")),
                "reason": f"当前纸面跟踪信号 {paper_summary.get('tracked_signal_count', 0)} 个；失败门槛 {len(failed_checks)} 项。",
            },
            {
                "id": "candidate_vs_portfolio",
                "label": "候选质量 vs 资金曲线",
                "status": consistency_status,
                "headline": consistency_headline,
                "candidate_metric_value": default_value,
                "portfolio_metric_value": portfolio_value,
                "reason": "候选逐条验证看平均alpha，组合资金曲线看每日滚动部署后的收益和回撤，两者必须分开读。",
            },
            {
                "id": "primary_blocker",
                "label": "当前最大约束",
                **blocker,
            },
        ],
    }


def _primary_blocker(
    *,
    failed_checks: list[str],
    frozen_drawdown: float | None,
    paper_tracking: dict[str, Any],
    overall: dict[str, Any],
) -> dict[str, Any]:
    statistical_gate = _dict(overall.get("statistical_gate"))
    if str(statistical_gate.get("status") or "") != "ready":
        return {
            "status": "sample_blocker",
            "headline": "历史样本仍不足",
            "reason": str(statistical_gate.get("reason") or "等待更多完成验证样本。"),
        }
    if failed_checks:
        return {
            "status": "production_gate_blocker",
            "headline": "生产门槛未通过",
            "reason": "、".join(failed_checks[:3]),
        }
    if frozen_drawdown is not None and frozen_drawdown < 0:
        return {
            "status": "drawdown_blocker",
            "headline": "回撤仍是主要约束",
            "metric_label": "长样本最大回撤",
            "metric_value": frozen_drawdown,
            "reason": "纸面策略需要前向样本证明回撤可控后才能讨论晋级。",
        }
    if str(paper_tracking.get("current_status") or "") != "tracking_active":
        return {
            "status": "forward_sample_blocker",
            "headline": "前向纸面样本不足",
            "reason": str(paper_tracking.get("current_message") or "等待冻结策略真实前向跟踪。"),
        }
    return {
        "status": "entry_assumption_blocker",
        "headline": "入场假设仍需并排观察",
        "reason": "次日收盘、次日开盘和14点代理口径的差异必须持续展示。",
    }


def _execution_funnel(*, overall: dict[str, Any], market_study: dict[str, Any]) -> dict[str, Any]:
    data_scope = _dict(market_study.get("data_scope"))
    account = _dict(data_scope.get("account_eligibility"))
    horizon_rows = [_dict(item) for item in overall.get("validation_by_horizon") or [] if isinstance(item, dict)]
    limit_blocked = sum(_int(_dict(row.get("status_counts")).get("entry_unfillable_limit_up")) for row in horizon_rows)
    reason = str(market_study.get("projection_reason") or "缺少 market-factor study 预计算产物；页面不得临时重算。")
    return {
        "status": "ready" if data_scope else "missing_artifact",
        "basis": "mixed_universe_and_candidate_horizon_counts",
        "reason": None if data_scope else reason,
        "note": "前两步是股票池口径，后续步骤是候选/验证行口径；页面必须按 basis 展示，不能解释成同一分母漏斗。",
        "steps": [
            _funnel_step("raw_universe", "全量股票", data_scope.get("raw_stock_like_series_count"), "stock_series"),
            _funnel_step("account_eligible", "新开户主板可交易池", account.get("included_series_count"), "stock_series"),
            _funnel_step("daily_tradeable", "当日可交易", data_scope.get("stock_like_series_count"), "stock_series"),
            _funnel_step("limit_up_fillable", "非涨停不可买", limit_blocked, "blocked_candidate_horizon_rows", invert=True),
            _funnel_step("complete_bars", "完整K线", overall.get("validation_count"), "candidate_horizon_rows"),
            _funnel_step("official_samples", "正式样本", overall.get("completed_official_sample_count"), "candidate_horizon_rows"),
            _funnel_step("completed_validation", "完成验证", overall.get("completed_tradable_sample_count"), "candidate_horizon_rows"),
        ],
    }


def _entry_sensitivity_matrix(
    *,
    entry_artifacts: dict[str, dict[str, Any]],
    paper_tracking: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        _entry_artifact_row("next_close", entry_artifacts.get("next_close")),
        _entry_artifact_row("next_open", entry_artifacts.get("next_open")),
        _entry_artifact_row("same_close_proxy", entry_artifacts.get("same_close_proxy")),
        _intraday_forward_row(paper_tracking),
    ]
    return {
        "status": "ready" if any(row.get("status") == "ready" for row in rows) else "missing_artifact",
        "strategy_key": CURRENT_FROZEN_STRATEGY,
        "strategy_label": "低换手上升趋势",
        "reason": None if any(row.get("status") == "ready" for row in rows) else "缺少预计算入场口径产物；页面不得临时回测。",
        "rows": rows,
    }


def _entry_artifact_row(entry_source: str, artifact: dict[str, Any] | None) -> dict[str, Any]:
    labels = {
        "next_close": "次日收盘",
        "next_open": "次日开盘",
        "same_close_proxy": "14点同日代理",
    }
    if not artifact:
        return {
            "entry_price_source": entry_source,
            "label": labels.get(entry_source, entry_source),
            "status": "missing_artifact",
            "reason": "缺少预计算入场口径产物；页面不得临时回测。",
        }
    payload = _dict(artifact.get("payload"))
    artifact_error = str(artifact.get("artifact_error") or "")
    config = _dict(payload.get("config"))
    result = _dict(_dict(_dict(payload.get("results")).get("daily_rolling_5x10k")).get(CURRENT_FROZEN_STRATEGY))
    summary = _dict(result.get("summary"))
    status = "ready" if summary else "missing_artifact"
    note = str(config.get("entry_price_source_note") or "")
    if entry_source == "same_close_proxy" and "代理" not in note and "proxy" not in note.lower():
        note = f"{note} 该口径是日线代理，不等同真实14:00全市场快照。".strip()
    return {
        "entry_price_source": entry_source,
        "label": labels.get(entry_source, entry_source),
        "status": status,
        "reason": artifact_error or (None if summary else "入场口径产物缺少策略 summary。"),
        "assumption_level": "diagnostic_proxy" if entry_source == "same_close_proxy" else "research_backtest",
        "entry_price_source_note": note,
        "artifact_path": artifact.get("artifact_path"),
        "trade_count": _int(summary.get("trade_count")),
        "skipped_count": _int(summary.get("skipped_count")),
        "blocked_exit_count": _int(summary.get("blocked_exit_count")),
        "total_return": _float(summary.get("total_return")),
        "excess_total_return": _float(summary.get("excess_total_return")),
        "max_drawdown": _float(summary.get("max_drawdown")),
    }


def _intraday_forward_row(paper_tracking: dict[str, Any]) -> dict[str, Any]:
    items = [_dict(item) for item in paper_tracking.get("items") or [] if isinstance(item, dict)]
    intraday_items = [
        item
        for item in items
        if str(_dict(item.get("selection_score_components")).get("entry_price_source") or "") == "same_day_intraday_current"
    ]
    return {
        "entry_price_source": "same_day_intraday_current",
        "label": "盘中当前价",
        "status": "forward_tracking_only",
        "assumption_level": "live_forward_paper",
        "entry_price_source_note": "真实纸面跟踪只来自盘中捕获价；当前没有完整历史回测矩阵，不能用日线代理替代。",
        "trade_count": len(intraday_items),
        "reason": str(paper_tracking.get("current_message") or "等待盘中前向样本继续积累。"),
    }


def _funnel_step(id_: str, label: str, count: Any, basis: str, *, invert: bool = False) -> dict[str, Any]:
    parsed_count = _int(count)
    return {
        "id": id_,
        "label": label,
        "status": "ready" if parsed_count > 0 or count == 0 else "missing_artifact",
        "count": parsed_count if count is not None else None,
        "basis": basis,
        "invert_meaning": invert,
    }


def _deferred_projection(status: str, reason: str) -> dict[str, str]:
    return {"status": status, "reason": reason}


def _find_family(families: list[dict[str, Any]], family_key: str) -> dict[str, Any]:
    for family in families:
        if family.get("baseline_family") == family_key:
            return family
    return {}


def _family_horizon_metric(family: dict[str, Any], horizon: str) -> dict[str, Any]:
    for row in family.get("validation_by_horizon") or []:
        if isinstance(row, dict) and str(row.get("group_key")) == horizon:
            return row
    return {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
