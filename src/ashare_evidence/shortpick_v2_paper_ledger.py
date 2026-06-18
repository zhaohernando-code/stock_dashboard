from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ashare_evidence.shortpick_v2_h10_paper_governance import H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS
from ashare_evidence.shortpick_v2_read_model import (
    SHORTPICK_V2_CLAIM_CEILING,
    SHORTPICK_V2_DEFAULT_BOARD_LOT_SIZE,
    SHORTPICK_V2_DEFAULT_INITIAL_CASH,
    SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_CANDIDATES,
    SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
    SHORTPICK_V2_PAPER_CONTRACT_REF,
    SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS,
    SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT,
    SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID,
    SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
    SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_CANDIDATES,
    SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV,
    SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY,
    SHORTPICK_V2_RULE_SELECTION_ARTIFACT_CANDIDATES,
    SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV,
    SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY,
    SHORTPICK_V2_SCHEMA_VERSION,
    SHORTPICK_V2_TRACKING_START_DATE,
    _account_contract,
    _build_paper_display_replay_rows_from_session,
    _latest_daily_market_bar_day,
    _paper_display_rule_configs,
    _paper_governance_selected_config_ids,
    _read_json_artifact,
    _read_optional_paper_governance_artifact,
    _resolve_artifact_path,
    _row_contract,
    _tracking_window_contract,
    _validate_paper_tracking_ledger_artifact,
    _validate_paper_tracking_selection_alignment,
    _validate_rule_selection_artifact,
)


def build_shortpick_v2_paper_ledger_artifact(
    session: Any,
    *,
    rule_selection_artifact_path: str | Path | None = None,
    paper_governance_artifact_path: str | Path | None = None,
    generated_at: datetime | None = None,
    target_date: date | None = None,
) -> dict[str, Any]:
    """Build the governed v2 true-forward paper ledger from local market data."""
    generated_at = generated_at or datetime.now(UTC)
    selection_path = _resolve_artifact_path(
        explicit_path=rule_selection_artifact_path,
        env_var=SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_RULE_SELECTION_ARTIFACT_CANDIDATES,
    )
    governance_path = _resolve_artifact_path(
        explicit_path=paper_governance_artifact_path,
        env_var=SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_CANDIDATES,
    )
    selection_artifact = _read_json_artifact(selection_path, label="shortpick v2 rule selection")
    _validate_rule_selection_artifact(selection_artifact)
    paper_governance_artifact = _read_optional_paper_governance_artifact(governance_path)
    if paper_governance_artifact is None:
        raise ValueError(f"shortpick v2 paper ledger refresh requires H10 paper governance artifact: {governance_path}")

    active_config_ids = _paper_governance_selected_config_ids(paper_governance_artifact)
    active_config_ids = tuple(config_id for config_id in active_config_ids if config_id in H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    boundary_date = _true_forward_boundary_date(paper_governance_artifact)
    latest_market_day = _latest_daily_market_bar_day(session)
    effective_target_date = _effective_target_date(
        latest_market_day=latest_market_day,
        target_date=target_date,
    )
    rows, source_coverage = _build_true_forward_display_rows(
        session=session,
        active_config_ids=active_config_ids,
        boundary_date=boundary_date,
        target_date=effective_target_date,
    )
    records = [
        _ledger_record_from_display_row(
            row,
            config_role=_config_role(str(row.get("config_id") or ""), paper_governance_artifact=paper_governance_artifact),
        )
        for row in rows
    ]
    summary = _ledger_summary(records)
    status = "active" if records else "contract_ready"
    artifact = {
        "artifact_family": SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY,
        "schema_version": SHORTPICK_V2_SCHEMA_VERSION,
        "ledger_id": f"{SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY}:{generated_at.date().isoformat()}",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
        "source_contract_ref": SHORTPICK_V2_PAPER_CONTRACT_REF,
        "source_selection_artifact": _source_selection_artifact_ref(
            selection_artifact,
            selection_path=selection_path,
            paper_governance_artifact=paper_governance_artifact,
        ),
        "tracking_window": _tracking_window_contract(),
        "account_contract": _account_contract(selection_artifact, paper_governance_artifact=paper_governance_artifact),
        "row_contract": _row_contract(paper_governance_artifact=paper_governance_artifact),
        "records": records,
        "summary": summary,
        "leakage_audit": {
            "status": "passed",
            "source_selection_artifact_required": True,
            "used_only_signal_day_or_earlier_data": True,
            "notes": [
                "Ledger rows are generated only for governance-approved H10 candidate configs.",
                f"True-forward row boundary is strictly after {boundary_date.isoformat()}.",
                "Rows before the boundary remain display replay rows and are not backfilled into this ledger.",
                str(source_coverage.get("source_status_label") or ""),
            ],
        },
        "research_labeling": {
            "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
            "evidence_basis": SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
            "prohibited_claims": ["production_ready", "investment_advice", "automated_trading"],
            "notes": ["试验田v2纸面追踪仅用于研究观察，不构成投资建议或自动交易承诺。"],
        },
        "event_refs": [
            "shortpick_v2.phase6.paper_ledger.refresh",
            str(selection_artifact.get("artifact_id") or ""),
            str((paper_governance_artifact or {}).get("artifact_id") or ""),
        ],
    }
    _validate_paper_tracking_ledger_artifact(artifact)
    _validate_paper_tracking_selection_alignment(
        artifact,
        selection_artifact,
        paper_governance_artifact=paper_governance_artifact,
    )
    return artifact


def write_shortpick_v2_paper_ledger_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output.with_name(f".{output.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(output)
    return output


def refresh_shortpick_v2_paper_ledger_artifact(
    session: Any,
    *,
    output_path: str | Path | None = None,
    rule_selection_artifact_path: str | Path | None = None,
    paper_governance_artifact_path: str | Path | None = None,
    generated_at: datetime | None = None,
    target_date: date | None = None,
) -> tuple[dict[str, Any], Path]:
    output = Path(output_path) if output_path is not None else _default_ledger_output_path()
    payload = build_shortpick_v2_paper_ledger_artifact(
        session,
        rule_selection_artifact_path=rule_selection_artifact_path,
        paper_governance_artifact_path=paper_governance_artifact_path,
        generated_at=generated_at,
        target_date=target_date,
    )
    path = write_shortpick_v2_paper_ledger_artifact(payload, output_path=output)
    return payload, path


def _build_true_forward_display_rows(
    *,
    session: Any,
    active_config_ids: tuple[str, ...],
    boundary_date: date,
    target_date: date | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not active_config_ids:
        return [], {"source_status": "no_active_h10_config", "source_status_label": "没有可写入 v2 ledger 的治理候选。"}
    if target_date is None or target_date <= boundary_date:
        return [], {
            "source_status": "no_post_governance_signal_date",
            "source_status_label": "本地行情尚未覆盖治理日之后的新信号日。",
        }
    rows, coverage, _account_curves = _build_paper_display_replay_rows_for_window(
        session=session,
        active_config_ids=active_config_ids,
        start_date=boundary_date + timedelta(days=1),
        end_date=target_date,
    )
    return rows, coverage


def _build_paper_display_replay_rows_for_window(
    *,
    session: Any,
    active_config_ids: tuple[str, ...],
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    # Reuse the existing display replay implementation when the requested window
    # starts at the public tracking start. For the ledger writer we need the same
    # H10 rule mechanics, but a stricter post-governance signal-day window.
    if start_date == date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE):
        return _build_paper_display_replay_rows_from_session(session=session, active_config_ids=active_config_ids)

    from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
    from ashare_evidence.shortpick_market_factor_study import ENTRY_PRICE_SOURCE_NEXT_CLOSE, INDEX_SYMBOLS
    from ashare_evidence.shortpick_portfolio_backtest import _trade_days
    from ashare_evidence.shortpick_ranked_pool_replay_input import _load_daily_series_for_replay_window
    from ashare_evidence.shortpick_v2_read_model import (
        _empty_paper_display_coverage,
        _finalize_paper_display_coverage,
        _latest_series_day,
        _paper_display_account_curves_from_rows,
        _paper_display_gap_row,
        _paper_display_rows_from_replay_artifact,
    )
    from ashare_evidence.shortpick_v2_replay import (
        DEFAULT_COST_BPS,
        DEFAULT_STAMP_TAX_BPS,
        build_shortpick_v2_replay_artifact_from_series,
    )
    from ashare_evidence.shortpick_v2_strategy_search import build_h10_quiet_champion_strategy_search_candidate_sources

    coverage = _empty_paper_display_coverage()
    coverage["coverage_start"] = start_date.isoformat()
    coverage["true_forward_record_count"] = 0
    rule_configs = _paper_display_rule_configs(active_config_ids)
    if not rule_configs:
        coverage["source_status"] = "no_active_h10_config"
        coverage["source_status_label"] = "当前没有可进入纸面观察的 H10 候选策略"
        return [], coverage, []

    raw_series_by_symbol = _load_daily_series_for_replay_window(
        session,
        start_date=date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE)
        - timedelta(days=SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS),
        end_date=end_date,
    )
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        include_index_symbols=INDEX_SYMBOLS,
    )
    latest_bar_day = _latest_series_day(series_by_symbol)
    if latest_bar_day is None or latest_bar_day < start_date:
        coverage["coverage_end"] = latest_bar_day.isoformat() if latest_bar_day is not None else None
        coverage["latest_source_signal_date"] = coverage["coverage_end"]
        coverage["source_status"] = "no_market_data_after_governance"
        coverage["source_status_label"] = "本地行情库没有覆盖治理日之后的数据"
        return [], coverage, []
    latest_bar_day = min(latest_bar_day, end_date)
    available_signal_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=latest_bar_day,
        min_symbol_count=SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT,
    )
    coverage["coverage_end"] = (
        available_signal_days[-1].isoformat() if available_signal_days else latest_bar_day.isoformat()
    )
    coverage["latest_source_signal_date"] = coverage["coverage_end"]
    coverage["available_source_signal_dates"] = [day.isoformat() for day in available_signal_days]
    coverage["available_source_signal_day_count"] = len(available_signal_days)
    coverage["source_status"] = "ready" if available_signal_days else "no_eligible_signal_days"
    coverage["source_status_label"] = (
        "已读取本地行情库生成治理后真实前向覆盖"
        if available_signal_days
        else "本地行情库存在治理后数据，但没有达到策略可用的信号日"
    )
    coverage["account_profile_label"] = str(account_eligibility.get("account_profile_label") or "新开户普通现金账户")
    if not available_signal_days:
        return [], coverage, []

    candidate_sources = build_h10_quiet_champion_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=available_signal_days,
        pool_limit=40,
        rank_limit=6,
        source_ids=(SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID,),
    )
    display_source = next(
        (source for source in candidate_sources if source.source_id == SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID),
        None,
    )
    if display_source is None:
        coverage["source_status"] = "missing_h10_replay_source"
        coverage["source_status_label"] = "缺少 H10 安静突破回放源，已按数据缺口保留信号日"
        rows = [
            _paper_display_gap_row(
                signal_date,
                config.config_id,
                reason_text="缺少 H10 安静突破回放源，无法生成当天动作判断。",
                note="该信号日保留为真实前向覆盖缺口，避免把源缺失误读成策略结果。",
            )
            for signal_date in coverage["available_source_signal_dates"]
            for config in rule_configs
        ]
        _finalize_paper_display_coverage(coverage, rows, active_config_ids=tuple(config.config_id for config in rule_configs))
        return rows, coverage, []

    display_trade_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=latest_bar_day + timedelta(days=80),
        min_symbol_count=SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT,
    )
    replay_artifact = build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=available_signal_days,
        trade_days=display_trade_days,
        selections=display_source.selections,
        start_date=start_date,
        end_date=latest_bar_day,
        initial_cash=SHORTPICK_V2_DEFAULT_INITIAL_CASH,
        entry_price_source=ENTRY_PRICE_SOURCE_NEXT_CLOSE,
        horizon_days=10,
        pool_limit=40,
        rank_limit=6,
        cost_bps=DEFAULT_COST_BPS,
        stamp_tax_bps=DEFAULT_STAMP_TAX_BPS,
        account_profile=str(account_eligibility.get("account_profile") or ACCOUNT_PROFILE_NEW_RETAIL_CASH),
        stock_like_series_count=len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        coverage_notes=["纸面 ledger 写入只覆盖治理后真实前向窗口。"],
        rule_configs=rule_configs,
        decision_sample_limit=len(available_signal_days),
    )
    rows = _paper_display_rows_from_replay_artifact(
        replay_artifact,
        active_config_ids=tuple(config.config_id for config in rule_configs),
        available_signal_dates=coverage["available_source_signal_dates"],
        symbol_names={symbol: str(getattr(series, "name", "") or symbol) for symbol, series in series_by_symbol.items()},
        series_by_symbol=series_by_symbol,
        trade_days=display_trade_days,
    )
    for row in rows:
        row["tracking_tag"] = "真实前向"
        row["tracking_tag_tone"] = "success"
        row["note"] = "真实前向：来自治理后 v2 ledger 写入。"
    _finalize_paper_display_coverage(coverage, rows, active_config_ids=tuple(config.config_id for config in rule_configs))
    account_curves = _paper_display_account_curves_from_rows(
        rows,
        series_by_symbol=series_by_symbol,
        trade_days=display_trade_days,
        initial_cash=SHORTPICK_V2_DEFAULT_INITIAL_CASH,
    )
    coverage["account_curve_count"] = len(account_curves)
    return rows, coverage, account_curves


def _ledger_record_from_display_row(row: dict[str, Any], *, config_role: str) -> dict[str, Any]:
    action = str(row.get("action") or "skip")
    source_state = str(row.get("source_state") or "observed")
    if action == "source_gap":
        decision_action = "skip"
        source_state = "source_gap"
        validation_status = "source_gap"
        position_state = "source_gap"
    else:
        decision_action = action if action in {"buy_primary", "buy_fallback", "skip"} else "skip"
        validation_status = _validation_status_for_row(row, decision_action=decision_action)
        position_state = _position_state_for_row(row, decision_action=decision_action)
    signal_date = str(row.get("signal_date") or "")
    entry_date = row.get("entry_date")
    exit_date = row.get("exit_date")
    return {
        "record_id": f"shortpick_v2:{signal_date}:{row.get('config_id')}",
        "config_id": str(row.get("config_id") or ""),
        "config_role": config_role,
        "signal_date": signal_date,
        "decision_date": signal_date,
        "decision_action": decision_action,
        "reason": str(row.get("reason_text") or "按既定规则完成判断。"),
        "selected_rank": _rank_value(row.get("selected_rank_text")),
        "symbol": str(row.get("symbol") or "") or None,
        "entry_trade_date": str(entry_date) if entry_date else None,
        "entry_price_source": "next_close" if decision_action in {"buy_primary", "buy_fallback"} else None,
        "quantity": int(row.get("quantity") or 0),
        "board_lot_size": SHORTPICK_V2_DEFAULT_BOARD_LOT_SIZE,
        "cash_before": _cash_value(row.get("cash_before")),
        "cash_after": _cash_value(row.get("cash_after")),
        "position_state": position_state,
        "evidence_basis": SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
        "source_state": source_state,
        "validation_status": validation_status,
        "exit_trade_date": str(exit_date) if exit_date else None,
        "exit_reason": "mechanical_10d" if exit_date else None,
        "notes": [str(row.get("note") or "真实前向：来自治理后 v2 ledger 写入。")],
    }


def _source_selection_artifact_ref(
    selection_artifact: dict[str, Any],
    *,
    selection_path: Path,
    paper_governance_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    selected_config_ids = (
        list(_paper_governance_selected_config_ids(paper_governance_artifact))
        if paper_governance_artifact is not None
        else [str(row.get("config_id") or "") for row in selection_artifact.get("selected_configs") or [] if isinstance(row, dict)]
    )
    return {
        "artifact_id": str(selection_artifact.get("artifact_id") or "shortpick_v2_rule_selection_artifact:missing_id"),
        "artifact_family": SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_SCHEMA_VERSION,
        "path": str(selection_path),
        "selected_config_ids": selected_config_ids,
        "baseline_config_ids": [
            str(row.get("config_id") or "") for row in selection_artifact.get("baseline_configs") or [] if isinstance(row, dict)
        ],
        "holdout_config_ids": [
            str(row.get("config_id") or "") for row in selection_artifact.get("holdout_configs") or [] if isinstance(row, dict)
        ],
        "rejected_config_ids": [
            str(row.get("config_id") or "") for row in selection_artifact.get("rejected_configs") or [] if isinstance(row, dict)
        ],
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
    }


def _true_forward_boundary_date(paper_governance_artifact: dict[str, Any] | None) -> date:
    if paper_governance_artifact is None:
        return date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE) - timedelta(days=1)
    generated_at = str(paper_governance_artifact.get("generated_at") or "")
    try:
        return datetime.fromisoformat(generated_at).date()
    except ValueError:
        return date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE) - timedelta(days=1)


def _effective_target_date(*, latest_market_day: date | None, target_date: date | None) -> date | None:
    if latest_market_day is None:
        return None
    if target_date is None:
        return latest_market_day
    return min(target_date, latest_market_day)


def _config_role(config_id: str, *, paper_governance_artifact: dict[str, Any] | None) -> str:
    if paper_governance_artifact is not None and config_id in _paper_governance_selected_config_ids(paper_governance_artifact):
        return "phase6_forward_observation_candidate"
    if config_id == "top1_or_skip_v1":
        return "baseline_control"
    return "phase5_contract_candidate"


def _validation_status_for_row(row: dict[str, Any], *, decision_action: str) -> str:
    if decision_action == "skip":
        return "skipped"
    exit_state = str(row.get("exit_state") or "")
    if exit_state == "completed":
        return "closed"
    if exit_state == "source_gap":
        return "source_gap"
    if row.get("entry_date"):
        return "open"
    return "pending_entry"


def _position_state_for_row(row: dict[str, Any], *, decision_action: str) -> str:
    if decision_action == "skip":
        return "not_opened"
    exit_state = str(row.get("exit_state") or "")
    if exit_state == "completed":
        return "closed"
    if exit_state == "source_gap":
        return "source_gap"
    return "open"


def _rank_value(rank_text: object) -> int | None:
    if not isinstance(rank_text, str):
        return None
    digits = "".join(ch for ch in rank_text if ch.isdigit())
    return int(digits) if digits else None


def _cash_value(value: object) -> float:
    try:
        if value is None:
            return SHORTPICK_V2_DEFAULT_INITIAL_CASH
        return float(value)
    except (TypeError, ValueError):
        return SHORTPICK_V2_DEFAULT_INITIAL_CASH


def _ledger_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    buy_count = sum(1 for record in records if str(record.get("decision_action") or "").startswith("buy_"))
    skip_count = sum(1 for record in records if record.get("decision_action") == "skip")
    source_gap_count = sum(1 for record in records if record.get("source_state") in {"source_gap", "not_observed"})
    open_position_count = sum(1 for record in records if record.get("position_state") == "open")
    closed_position_count = sum(1 for record in records if record.get("position_state") == "closed")
    return {
        "record_count": len(records),
        "buy_count": buy_count,
        "skip_count": skip_count,
        "source_gap_count": source_gap_count,
        "open_position_count": open_position_count,
        "closed_position_count": closed_position_count,
    }


def _default_ledger_output_path() -> Path:
    return _resolve_artifact_path(
        explicit_path=None,
        env_var=SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_CANDIDATES,
    )
