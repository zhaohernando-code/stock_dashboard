from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import floor
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ashare_evidence.models import ShortpickCandidate, ShortpickExperimentRun, ShortpickValidationSnapshot
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)
from ashare_evidence.shortpick_v2_read_model import build_shortpick_v2_paper_tracking_read_model

SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_FAMILY = "shortpick_paper_divergence_attribution"
SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_SCHEMA_VERSION = "v1"
SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_CLAIM_CEILING = "research_observation"
SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/contracts/registry/schemas/shortpick_paper_divergence_attribution.schema.json"
)
SHORTPICK_PAPER_DIVERGENCE_START_DATE = date(2026, 5, 8)
DEFAULT_INITIAL_CASH = 200_000.0
DEFAULT_BOARD_LOT_SIZE = 100
DEFAULT_HORIZON_DAYS = 10
SHORTPICK_INFORMATION_MODE = "native_web_open_discovery"
V1_DERIVED_CONTROL_ID = "v1_derived_200k_top1_or_skip_h10"
V1_RAW_OBSERVATION_ID = "v1_raw_candidate_forward_h10"


@dataclass(frozen=True)
class PaperCandidateObservation:
    signal_date: date
    symbol: str
    name: str
    source_rank: int
    entry_date: date | None
    exit_date: date | None
    entry_price: float | None
    exit_price: float | None
    stock_return: float | None
    tracking_group: str = "unknown"


@dataclass(frozen=True)
class AccountSimulationConfig:
    strategy_id: str
    label_cn: str
    initial_cash: float = DEFAULT_INITIAL_CASH
    board_lot_size: int = DEFAULT_BOARD_LOT_SIZE
    target_notional: float | None = None
    candidate_rank_limit: int = 1
    fallback_enabled: bool = False


def build_shortpick_paper_divergence_attribution_artifact(
    session: Session,
    *,
    start_date: date = SHORTPICK_PAPER_DIVERGENCE_START_DATE,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    generated_at: datetime | None = None,
    rule_selection_artifact_path: str | Path | None = None,
    ledger_artifact_path: str | Path | None = None,
    paper_governance_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a research-only attribution artifact without mutating paper ledgers."""

    v1_observations = load_v1_paper_candidate_observations(session, start_date=start_date)
    v2_read_model = build_shortpick_v2_paper_tracking_read_model(
        include_records=True,
        session=session,
        rule_selection_artifact_path=rule_selection_artifact_path,
        ledger_artifact_path=ledger_artifact_path,
        paper_governance_artifact_path=paper_governance_artifact_path,
    )
    return build_shortpick_paper_divergence_attribution_artifact_from_inputs(
        v1_observations=v1_observations,
        v2_read_model=v2_read_model,
        start_date=start_date,
        initial_cash=initial_cash,
        generated_at=generated_at,
    )


def build_shortpick_paper_divergence_attribution_artifact_from_inputs(
    *,
    v1_observations: list[PaperCandidateObservation],
    v2_read_model: dict[str, Any],
    start_date: date = SHORTPICK_PAPER_DIVERGENCE_START_DATE,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    v1_account = simulate_candidate_account(
        v1_observations,
        config=AccountSimulationConfig(
            strategy_id=V1_DERIVED_CONTROL_ID,
            label_cn="v1 派生对照：20万账户，只买首位候选，买不起就跳过",
            initial_cash=initial_cash,
            target_notional=initial_cash,
            candidate_rank_limit=1,
            fallback_enabled=False,
        ),
    )
    v1_raw_summary = summarize_raw_candidate_observations(v1_observations)
    v2_strategies = _v2_strategy_summaries(v2_read_model, initial_cash=initial_cash)
    strategies = [
        *v2_strategies,
        {
            "strategy_id": V1_RAW_OBSERVATION_ID,
            "label_cn": "v1 原始候选 forward 观察",
            "source_kind": "v1_candidate_forward_return_not_account_nav",
            "status": "ready" if v1_raw_summary["observation_count"] else "unavailable",
            "summary": v1_raw_summary,
            "reason_counts": {},
            "notes_cn": [
                "这是候选级 forward return 统计，不是账户 NAV。",
                "它只用于说明 v1 候选源在同窗期的 raw 表现。",
            ],
        },
        {
            "strategy_id": V1_DERIVED_CONTROL_ID,
            "label_cn": "v1 派生对照：20万账户，只买首位候选，买不起就跳过",
            "source_kind": "derived_v1_200k_account_control",
            "status": v1_account["status"],
            "summary": v1_account["summary"],
            "reason_counts": v1_account["reason_counts"],
            "notes_cn": [
                "该账户路径由 v1 候选记录派生，只用于研究对照。",
                "没有写入或替换现有 v1/v2 纸面追踪 ledger。",
            ],
        },
    ]
    latest_dates = [
        day
        for day in [
            _parse_date_or_none((v2_read_model.get("summary") or {}).get("latest_paper_display_signal_date")),
            _max_observation_date(v1_observations),
        ]
        if day is not None
    ]
    latest_date = max(latest_dates) if latest_dates else start_date
    attribution = classify_attribution(strategies, initial_cash=initial_cash)
    artifact = {
        "artifact_family": SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_FAMILY,
        "schema_version": SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_SCHEMA_VERSION,
        "claim_ceiling": SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_CLAIM_CEILING,
        "artifact_id": f"shortpick-paper-divergence-attribution-{generated_at.strftime('%Y%m%d%H%M%S')}",
        "generated_at": generated_at.isoformat(),
        "tracking_window": {
            "start_date": start_date.isoformat(),
            "latest_available_date": latest_date.isoformat(),
            "horizon_days": DEFAULT_HORIZON_DAYS,
        },
        "account_constraints": {
            "initial_cash": float(initial_cash),
            "board_lot_size": DEFAULT_BOARD_LOT_SIZE,
            "delayed_buy_allowed": False,
            "v1_control_rule": "top1_or_skip",
            "v2_control_rule": "fixed_notional_rank2_primary_top5_fallback_or_skip",
        },
        "source_notes": {
            "v1": "v1 paper records are candidate-level forward observations; the account control is derived in this artifact only.",
            "v2": "v2 account curves come from the existing v2 paper read model and are kept separate from v1 controls.",
            "sample_size": "The current paper window is short; attribution labels are research evidence, not strategy promotion decisions.",
        },
        "strategies": strategies,
        "attribution": attribution,
        "conclusions_cn": _conclusions_cn(attribution),
        "event_refs": [
            "shortpick.paper_divergence_attribution.generated",
            "shortpick.v2.paper_tracking_current_window",
            "shortpick.v1.derived_account_control_research_only",
        ],
    }
    validation = validate_shortpick_paper_divergence_attribution_payload(artifact)
    artifact["validation_status"] = validation["status"]
    return artifact


def load_v1_paper_candidate_observations(
    session: Session,
    *,
    start_date: date = SHORTPICK_PAPER_DIVERGENCE_START_DATE,
) -> list[PaperCandidateObservation]:
    tracking_role_expr = func.coalesce(func.json_extract(ShortpickCandidate.candidate_payload, "$.tracking_role"), "")
    rows = session.execute(
        select(ShortpickCandidate, ShortpickExperimentRun, ShortpickValidationSnapshot)
        .join(ShortpickExperimentRun, ShortpickCandidate.run_id == ShortpickExperimentRun.id)
        .outerjoin(
            ShortpickValidationSnapshot,
            (ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
            & (ShortpickValidationSnapshot.horizon_days == DEFAULT_HORIZON_DAYS),
        )
        .where(
            ShortpickExperimentRun.run_date >= start_date,
            ShortpickExperimentRun.information_mode == SHORTPICK_INFORMATION_MODE,
            ShortpickExperimentRun.status == "completed",
            ShortpickCandidate.parse_status == "parsed",
            ShortpickCandidate.symbol != "PARSE_FAILED",
            or_(
                ShortpickCandidate.research_priority == "market_factor_frozen_paper",
                tracking_role_expr == "frozen_paper_primary",
            ),
        )
        .order_by(ShortpickExperimentRun.run_date.asc(), ShortpickCandidate.id.asc())
    ).all()
    observations: list[PaperCandidateObservation] = []
    seen: set[tuple[str, str, int]] = set()
    for candidate, run, snapshot in rows:
        payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
        overlay = payload.get("market_factor_overlay") if isinstance(payload.get("market_factor_overlay"), dict) else {}
        signal_date = _parse_date_or_none(payload.get("paper_tracking_signal_date")) or run.run_date
        source_rank = _safe_int(overlay.get("source_rank"), default=1)
        semantic_key = (signal_date.isoformat(), str(candidate.symbol), source_rank)
        if semantic_key in seen:
            continue
        seen.add(semantic_key)
        observations.append(
            PaperCandidateObservation(
                signal_date=signal_date,
                symbol=str(candidate.symbol),
                name=str(candidate.name or candidate.symbol),
                source_rank=source_rank,
                entry_date=_date_from_datetime(getattr(snapshot, "entry_at", None)),
                exit_date=_date_from_datetime(getattr(snapshot, "exit_at", None)),
                entry_price=_safe_float(getattr(snapshot, "entry_close", None)),
                exit_price=_safe_float(getattr(snapshot, "exit_close", None)),
                stock_return=_safe_float(getattr(snapshot, "stock_return", None)),
                tracking_group=str(payload.get("tracking_role") or "frozen_paper_primary"),
            )
        )
    return observations


def simulate_candidate_account(
    observations: list[PaperCandidateObservation],
    *,
    config: AccountSimulationConfig,
) -> dict[str, Any]:
    signal_groups: dict[date, list[PaperCandidateObservation]] = {}
    for observation in observations:
        signal_groups.setdefault(observation.signal_date, []).append(observation)

    cash = float(config.initial_cash)
    peak_nav = float(config.initial_cash)
    nav_points: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    completed_pnls: list[float] = []
    total_buy_value = 0.0
    total_sell_value = 0.0

    def close_matured(up_to: date) -> None:
        nonlocal cash, peak_nav, total_sell_value
        still_open: list[dict[str, Any]] = []
        closed_days: list[date] = []
        for position in open_positions:
            exit_date = position["exit_date"]
            if exit_date is not None and exit_date <= up_to and position["stock_return"] is not None:
                proceeds = float(position["cost"]) * (1.0 + float(position["stock_return"]))
                cash += proceeds
                total_sell_value += proceeds
                pnl = proceeds - float(position["cost"])
                completed_pnls.append(pnl)
                reason_counts["exit:mechanical_h10"] += 1
                closed_days.append(exit_date)
            else:
                still_open.append(position)
        open_positions[:] = still_open
        if closed_days:
            nav = cash + sum(float(item["cost"]) for item in open_positions)
            peak_nav = max(peak_nav, nav)
            nav_points.append(
                {
                    "date": max(closed_days).isoformat(),
                    "nav": round(nav, 2),
                    "account_return": round(nav / float(config.initial_cash) - 1.0, 6),
                    "drawdown": round(nav / peak_nav - 1.0, 6) if peak_nav else 0.0,
                }
            )

    for signal_day in sorted(signal_groups):
        close_matured(signal_day)
        ranked = sorted(signal_groups[signal_day], key=lambda item: (item.source_rank, item.symbol))[
            : max(1, config.candidate_rank_limit)
        ]
        selected: PaperCandidateObservation | None = None
        rejected_reasons: list[str] = []
        for candidate in ranked:
            if candidate.entry_price is None or candidate.entry_price <= 0 or candidate.entry_date is None:
                rejected_reasons.append("missing_entry_price")
                if not config.fallback_enabled:
                    break
                continue
            notional = min(float(config.target_notional or config.initial_cash), cash)
            shares = floor(notional / float(candidate.entry_price) / float(config.board_lot_size)) * config.board_lot_size
            cost = shares * float(candidate.entry_price)
            if shares <= 0:
                rejected_reasons.append("board_lot_minimum")
                if not config.fallback_enabled:
                    break
                continue
            if cost > cash:
                rejected_reasons.append("insufficient_cash")
                if not config.fallback_enabled:
                    break
                continue
            selected = candidate
            break

        if selected is None:
            reason = rejected_reasons[0] if rejected_reasons else "no_ranked_candidates"
            reason_counts["action:skip"] += 1
            reason_counts[f"reason:{reason}"] += 1
            decisions.append(
                {
                    "signal_date": signal_day.isoformat(),
                    "action": "skip",
                    "reason": reason,
                    "symbol": None,
                    "quantity": 0,
                    "cash_before": round(cash, 2),
                    "cash_after": round(cash, 2),
                }
            )
            continue

        assert selected.entry_price is not None
        notional = min(float(config.target_notional or config.initial_cash), cash)
        shares = floor(notional / float(selected.entry_price) / float(config.board_lot_size)) * config.board_lot_size
        cost = shares * float(selected.entry_price)
        cash_before = cash
        cash -= cost
        total_buy_value += cost
        action = "buy_primary" if selected.source_rank == 1 else "buy_fallback"
        reason_counts[f"action:{action}"] += 1
        reason_counts["reason:selected"] += 1
        open_positions.append(
            {
                "symbol": selected.symbol,
                "name": selected.name,
                "signal_date": selected.signal_date,
                "entry_date": selected.entry_date,
                "exit_date": selected.exit_date,
                "shares": shares,
                "cost": cost,
                "stock_return": selected.stock_return,
            }
        )
        nav = cash + sum(float(item["cost"]) for item in open_positions)
        peak_nav = max(peak_nav, nav)
        nav_points.append(
            {
                "date": (selected.entry_date or signal_day).isoformat(),
                "nav": round(nav, 2),
                "account_return": round(nav / float(config.initial_cash) - 1.0, 6),
                "drawdown": round(nav / peak_nav - 1.0, 6) if peak_nav else 0.0,
            }
        )
        decisions.append(
            {
                "signal_date": signal_day.isoformat(),
                "action": action,
                "reason": "selected",
                "symbol": selected.symbol,
                "quantity": shares,
                "cash_before": round(cash_before, 2),
                "cash_after": round(cash, 2),
            }
        )
    closeout_days = [
        item.exit_date
        for item in observations
        if item.exit_date is not None and item.stock_return is not None
    ]
    if signal_groups or closeout_days:
        close_matured(max([*signal_groups.keys(), *closeout_days]))

    final_nav = cash + sum(float(position["cost"]) for position in open_positions)
    total_return = final_nav / float(config.initial_cash) - 1.0 if config.initial_cash else 0.0
    drawdowns = [float(point["drawdown"]) for point in nav_points]
    buy_decisions = [decision for decision in decisions if decision["action"] in {"buy_primary", "buy_fallback"}]
    skip_count = len([decision for decision in decisions if decision["action"] == "skip"])
    fallback_count = len([decision for decision in decisions if decision["action"] == "buy_fallback"])
    return {
        "status": "ready" if decisions else "unavailable",
        "summary": {
            "signal_count": len(signal_groups),
            "trade_count": len(buy_decisions),
            "completed_trade_count": len(completed_pnls),
            "skip_count": skip_count,
            "fallback_trade_count": fallback_count,
            "cash_or_lot_rejection_count": sum(
                count
                for reason, count in reason_counts.items()
                if reason in {"reason:board_lot_minimum", "reason:insufficient_cash"}
            ),
            "final_nav": round(final_nav, 2),
            "total_return": round(total_return, 6),
            "annualized_return": None,
            "max_drawdown": round(min(drawdowns), 6) if drawdowns else 0.0,
            "mean_invested_ratio": None,
            "turnover": round(total_buy_value / float(config.initial_cash), 6) if config.initial_cash else 0.0,
            "final_cash": round(cash, 2),
            "open_position_count": len(open_positions),
            "unresolved_position_count": len(
                [
                    position
                    for position in open_positions
                    if position.get("exit_date") is None or position.get("stock_return") is None
                ]
            ),
            "open_position_valuation_basis": "cost_until_exit_return_is_available",
            "total_buy_value": round(total_buy_value, 2),
            "total_sell_value": round(total_sell_value, 2),
            "tail_sensitivity": _tail_sensitivity(completed_pnls, initial_cash=config.initial_cash),
        },
        "reason_counts": dict(sorted(reason_counts.items())),
        "decision_samples": decisions[:50],
        "nav_points": nav_points[:120],
    }


def summarize_raw_candidate_observations(observations: list[PaperCandidateObservation]) -> dict[str, Any]:
    completed = [item for item in observations if item.stock_return is not None]
    returns = [float(item.stock_return) for item in completed if item.stock_return is not None]
    return {
        "observation_count": len(observations),
        "completed_observation_count": len(completed),
        "pending_observation_count": len(observations) - len(completed),
        "mean_stock_return": round(sum(returns) / len(returns), 6) if returns else None,
        "win_rate": round(len([value for value in returns if value > 0]) / len(returns), 6) if returns else None,
        "best_stock_return": round(max(returns), 6) if returns else None,
        "worst_stock_return": round(min(returns), 6) if returns else None,
    }


def classify_attribution(strategies: list[dict[str, Any]], *, initial_cash: float) -> list[dict[str, Any]]:
    by_id = {str(item.get("strategy_id")): item for item in strategies}
    v2 = by_id.get(H10_QUIET_CHAMPION_CONFIG_ID) or {}
    v1 = by_id.get(V1_DERIVED_CONTROL_ID) or {}
    v2_summary = v2.get("summary") if isinstance(v2.get("summary"), dict) else {}
    v1_summary = v1.get("summary") if isinstance(v1.get("summary"), dict) else {}
    v2_return = _safe_float(v2_summary.get("total_return"))
    v1_return = _safe_float(v1_summary.get("total_return"))
    v2_trade_count = _safe_int(v2_summary.get("trade_count"), default=0)
    v1_trade_count = _safe_int(v1_summary.get("trade_count"), default=0)
    fallback_count = _safe_int(v2_summary.get("fallback_trade_count"), default=0)
    tail = v1_summary.get("tail_sensitivity") if isinstance(v1_summary.get("tail_sensitivity"), dict) else {}
    worst_pnl = _safe_float(tail.get("worst_trade_pnl")) or 0.0
    rows = [
        {
            "dimension": "short_window_noise",
            "status": "uncertain" if max(v2_trade_count, v1_trade_count) < 10 else "does_not_support",
            "evidence_cn": "当前窗口成交笔数偏少，不能单独否定三年历史回测。"
            if max(v2_trade_count, v1_trade_count) < 10
            else "当前窗口成交笔数已经具备一定观察量，短期噪声解释需要降低权重。",
        },
        {
            "dimension": "v1_factor_current_window",
            "status": _compare_support(v1_return, v2_return, threshold=0.03),
            "evidence_cn": _return_compare_text("v1 派生 20 万账户", v1_return, "v2 fixed85", v2_return),
        },
        {
            "dimension": "execution_capital_constraint",
            "status": "supports" if fallback_count > 0 and (v2_return or 0.0) < 0 else "uncertain",
            "evidence_cn": f"v2 fixed85 当前窗口候补买入 {fallback_count} 次；若这些交易为负，需要继续拆分 fallback 贡献。",
        },
        {
            "dimension": "concentration_tail_risk",
            "status": "supports" if worst_pnl / float(initial_cash) <= -0.05 else "uncertain",
            "evidence_cn": f"v1 派生账户最差单笔 P/L 约 {worst_pnl:.2f} 元；短窗结果可能被少数交易主导。",
        },
        {
            "dimension": "regime_shift",
            "status": "uncertain",
            "evidence_cn": "本产物优先做同窗账户归因；市场 regime 需要结合指数与候选池覆盖率进一步确认。",
        },
    ]
    return rows


def render_shortpick_paper_divergence_attribution_markdown(payload: dict[str, Any]) -> str:
    strategies = payload.get("strategies") if isinstance(payload.get("strategies"), list) else []
    lines = [
        "# 试验田 v1/v2 纸面分歧归因",
        "",
        "本报告只用于研究归因，不代表策略晋级、淘汰或实盘建议。",
        "",
        "## 口径",
        "",
        f"- 观察起点：{(payload.get('tracking_window') or {}).get('start_date')}",
        f"- 最新可用日期：{(payload.get('tracking_window') or {}).get('latest_available_date')}",
        f"- 初始资金：{(payload.get('account_constraints') or {}).get('initial_cash')}",
        "- 买入限制：100 股整手；不允许延迟买入。",
        "- v1 原始纸面记录是候选 forward return；20 万账户路径是本产物派生的研究对照。",
        "",
        "## 策略对照",
        "",
        "| 策略 | 状态 | 总收益 | 最大回撤 | 交易 | 跳过 | 候补 | 说明 |",
        "|------|------|--------|----------|------|------|------|------|",
    ]
    for strategy in strategies:
        summary = strategy.get("summary") if isinstance(strategy.get("summary"), dict) else {}
        lines.append(
            "| {label} | {status} | {ret} | {dd} | {trades} | {skips} | {fallback} | {kind} |".format(
                label=strategy.get("label_cn") or strategy.get("strategy_id"),
                status=strategy.get("status") or "-",
                ret=_format_pct(summary.get("total_return")),
                dd=_format_pct(summary.get("max_drawdown")),
                trades=summary.get("trade_count", summary.get("completed_observation_count", "-")),
                skips=summary.get("skip_count", "-"),
                fallback=summary.get("fallback_trade_count", "-"),
                kind=strategy.get("source_kind") or "-",
            )
        )
    lines.extend(["", "## 归因判断", ""])
    for row in payload.get("attribution") or []:
        if not isinstance(row, dict):
            continue
        lines.append(f"- {row.get('dimension')}: {row.get('status')}。{row.get('evidence_cn')}")
    lines.extend(["", "## 当前结论", ""])
    for item in payload.get("conclusions_cn") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_shortpick_paper_divergence_attribution_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
    summary_path: str | Path | None = None,
) -> dict[str, Path]:
    artifact_path = Path(output_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    paths = {"artifact": artifact_path}
    if summary_path is not None:
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_shortpick_paper_divergence_attribution_markdown(payload), encoding="utf-8")
        paths["summary"] = path
    return paths


def validate_shortpick_paper_divergence_attribution_artifact(
    *,
    artifact_path: str | Path,
    schema_path: str | Path = SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_SCHEMA_PATH,
) -> dict[str, Any]:
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    return validate_shortpick_paper_divergence_attribution_payload(payload, schema_path=schema_path)


def validate_shortpick_paper_divergence_attribution_payload(
    payload: dict[str, Any],
    *,
    schema_path: str | Path = SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_SCHEMA_PATH,
) -> dict[str, Any]:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    checks = [
        {
            "check_id": "schema_valid",
            "passed": not errors,
            "details": "; ".join(error.message for error in errors[:5]) if errors else "",
        },
        {
            "check_id": "claim_ceiling_research_only",
            "passed": payload.get("claim_ceiling") == SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_CLAIM_CEILING,
            "details": str(payload.get("claim_ceiling")),
        },
        {
            "check_id": "no_delayed_buy",
            "passed": (payload.get("account_constraints") or {}).get("delayed_buy_allowed") is False,
            "details": str((payload.get("account_constraints") or {}).get("delayed_buy_allowed")),
        },
        {
            "check_id": "v1_derived_control_present",
            "passed": any(
                isinstance(row, dict) and row.get("strategy_id") == V1_DERIVED_CONTROL_ID
                for row in payload.get("strategies") or []
            ),
            "details": "",
        },
        {
            "check_id": "v2_fixed85_present",
            "passed": any(
                isinstance(row, dict) and row.get("strategy_id") == H10_QUIET_CHAMPION_CONFIG_ID
                for row in payload.get("strategies") or []
            ),
            "details": "",
        },
    ]
    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "failed_check_count": len(failed),
        "checks": checks,
    }


def _v2_strategy_summaries(v2_read_model: dict[str, Any], *, initial_cash: float) -> list[dict[str, Any]]:
    paper_display = v2_read_model.get("paper_display") if isinstance(v2_read_model.get("paper_display"), dict) else {}
    curves = paper_display.get("account_curves") if isinstance(paper_display.get("account_curves"), list) else []
    rows = ((paper_display.get("table") or {}).get("rows") if isinstance(paper_display.get("table"), dict) else []) or []
    action_counts_by_strategy: dict[str, Counter[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        strategy = str(row.get("strategy_text") or "")
        action = str(row.get("action_text") or "")
        action_counts_by_strategy.setdefault(strategy, Counter())[action] += 1

    configured = {
        H10_QUIET_CHAMPION_CONFIG_ID: "8.5 万目标买入方案",
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID: "8 万目标买入方案",
    }
    summaries: list[dict[str, Any]] = []
    for config_id, label in configured.items():
        curve = next((item for item in curves if isinstance(item, dict) and item.get("strategy") == label), None)
        counts = action_counts_by_strategy.get(label, Counter())
        if curve is None:
            summaries.append(
                {
                    "strategy_id": config_id,
                    "label_cn": label,
                    "source_kind": "v2_paper_account_curve",
                    "status": "unavailable",
                    "summary": {
                        "initial_cash": float(initial_cash),
                        "trade_count": 0,
                        "skip_count": 0,
                        "fallback_trade_count": 0,
                        "total_return": None,
                        "max_drawdown": None,
                    },
                    "reason_counts": {},
                    "notes_cn": ["当前 v2 读模型未暴露该策略账户曲线，标记为不可用。"],
                }
            )
            continue
        points = curve.get("points") if isinstance(curve.get("points"), list) else []
        latest_return = _safe_float(curve.get("latest_return"))
        curve_initial_cash = _safe_float(curve.get("initial_cash")) or float(initial_cash)
        summaries.append(
            {
                "strategy_id": config_id,
                "label_cn": label,
                "source_kind": "v2_paper_account_curve",
                "status": "ready",
                "summary": {
                    "initial_cash": curve_initial_cash,
                    "final_nav": curve.get("latest_nav"),
                    "total_return": latest_return,
                    "annualized_return": None,
                    "max_drawdown": _safe_float(curve.get("max_drawdown")),
                    "trade_count": _safe_int(curve.get("completed_trade_count"), default=0),
                    "completed_trade_count": _safe_int(curve.get("completed_trade_count"), default=0),
                    "skip_count": int(counts.get("不买入", 0)),
                    "fallback_trade_count": int(counts.get("买入候补", 0)),
                    "cash_or_lot_rejection_count": None,
                    "cash_or_lot_rejection_count_basis": "not_exposed_by_v2_paper_read_model",
                    "mean_invested_ratio": None,
                    "turnover": None,
                    "point_count": len(points),
                },
                "reason_counts": {
                    "action:buy_primary": int(counts.get("买入首选", 0)),
                    "action:buy_fallback": int(counts.get("买入候补", 0)),
                    "action:skip": int(counts.get("不买入", 0)),
                    "source_gap": int(counts.get("数据缺口", 0)),
                },
                "notes_cn": ["来自 v2 纸面追踪 read model 的账户曲线。"],
            }
        )
    return summaries


def _tail_sensitivity(pnls: list[float], *, initial_cash: float) -> dict[str, Any]:
    if not pnls:
        return {
            "trade_pnl_count": 0,
            "best_trade_pnl": None,
            "worst_trade_pnl": None,
            "drop_best_trade_total_return": None,
            "drop_worst_trade_total_return": None,
        }
    total = sum(pnls)
    best = max(pnls)
    worst = min(pnls)
    return {
        "trade_pnl_count": len(pnls),
        "best_trade_pnl": round(best, 2),
        "worst_trade_pnl": round(worst, 2),
        "drop_best_trade_total_return": round((total - best) / float(initial_cash), 6),
        "drop_worst_trade_total_return": round((total - worst) / float(initial_cash), 6),
    }


def _conclusions_cn(attribution: list[dict[str, Any]]) -> list[str]:
    support = [row for row in attribution if row.get("status") == "supports"]
    if not support:
        return ["当前证据不足以把 v2 近期弱势归因到单一原因；应继续做同窗前向观察。"]
    return [
        "当前更像是一个需要拆分的纸面窗口分歧，而不是可以直接推翻三年历史基准的证据。",
        "支持项应作为下一轮策略治理输入，但不能单独触发策略晋级或淘汰。",
    ]


def _compare_support(left: float | None, right: float | None, *, threshold: float) -> str:
    if left is None or right is None:
        return "uncertain"
    if left - right >= threshold:
        return "supports"
    if right - left >= threshold:
        return "does_not_support"
    return "uncertain"


def _return_compare_text(left_label: str, left: float | None, right_label: str, right: float | None) -> str:
    return f"{left_label} 当前收益 {_format_pct(left)}；{right_label} 当前收益 {_format_pct(right)}。"


def _format_pct(value: object) -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.1f}%"


def _date_from_datetime(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _parse_date_or_none(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value.split("T", 1)[0].split(" ", 1)[0])
    except ValueError:
        return None


def _max_observation_date(observations: list[PaperCandidateObservation]) -> date | None:
    dates = [item.signal_date for item in observations]
    return max(dates) if dates else None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
