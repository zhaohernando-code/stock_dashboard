from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.shortpick_portfolio_backtest import (
    build_shortpick_portfolio_backtest,
    write_shortpick_portfolio_backtest,
)


def run_shortpick_historical_backtest_request(
    session: Session,
    request: dict[str, Any],
    *,
    evidence_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute one governance historical-backtest request into a gated evidence artifact.

    The runner deliberately requires an explicit executable portfolio strategy mapping.
    A control rule without that mapping is persisted as blocked evidence instead of being
    treated as a successful historical control backtest.
    """

    normalized = _normalize_request(request)
    requested_output_path = evidence_output_path or normalized.get("output_path")
    if not requested_output_path:
        raise ValueError("evidence_output_path or request.output_path is required")

    block_reason = _request_block_reason(normalized)
    if block_reason:
        evidence = _blocked_evidence(normalized, block_reason=block_reason)
        evidence_path = write_shortpick_historical_backtest_evidence(evidence, output_path=requested_output_path)
        return {**evidence, "artifact": {"path": str(evidence_path)}}

    strategies = tuple(str(item) for item in normalized["portfolio_strategies"])
    portfolio_artifact_path = _portfolio_artifact_path(requested_output_path)
    payload = build_shortpick_portfolio_backtest(
        session,
        start_date=date.fromisoformat(str(normalized["start_date"])),
        end_date=date.fromisoformat(str(normalized["end_date"])),
        pool_limit=int(normalized["pool_limit"]),
        rank_limit=int(normalized["rank_limit"]),
        horizon_days=int(normalized["horizon_days"]),
        cost_bps=float(normalized["cost_bps"]),
        benchmark_mode=str(normalized["benchmark_mode"]),
        entry_price_source=str(normalized["entry_price_source"]),
        min_signal_symbol_count=int(normalized["min_signal_symbol_count"]),
        account_profile=str(normalized["account_profile"]),
        strategies=strategies,
    )
    write_shortpick_portfolio_backtest(payload, output_path=portfolio_artifact_path)

    leakage_audit = _leakage_audit(payload, request=normalized)
    gate = _historical_backtest_gate(payload, strategies=strategies, leakage_audit=leakage_audit)
    evidence = {
        "artifact_id": _evidence_artifact_id(normalized, gate),
        "artifact_type": "shortpick_historical_backtest_evidence",
        "version": "shortpick-historical-backtest-evidence-v1",
        "status": "ready" if gate["gate_status"] == "passed" else "blocked",
        "evidence_basis": "historical_backtest",
        "gate_status": gate["gate_status"],
        "gate_reasons": gate["gate_reasons"],
        "leakage_audit_status": leakage_audit["status"],
        "leakage_audit_reasons": leakage_audit["reasons"],
        "leakage_audit": leakage_audit,
        "request_id": normalized.get("request_id"),
        "control_group_id": normalized.get("control_group_id"),
        "rule_signature": normalized.get("rule_signature"),
        "rule": normalized.get("rule"),
        "request": normalized,
        "portfolio_strategies": list(strategies),
        "portfolio_backtest_artifact_path": str(portfolio_artifact_path),
        "metrics_by_mode_strategy": _metrics_by_mode_strategy(payload, strategies=strategies),
        "data_scope": payload.get("data_scope") or {},
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
        "retrospective": False,
        "runner_policy": "execute_only_explicit_portfolio_strategy_mapping_no_paper_tracking_write",
    }
    evidence_path = write_shortpick_historical_backtest_evidence(evidence, output_path=requested_output_path)
    return {**evidence, "artifact": {"path": str(evidence_path)}}


def run_shortpick_historical_backtest_requests(
    session: Session,
    requests: list[dict[str, Any]],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    evidence_items: list[dict[str, Any]] = []
    for request in requests:
        output_path = _request_output_path(request, output_dir=output_dir)
        evidence_items.append(
            run_shortpick_historical_backtest_request(
                session,
                request,
                evidence_output_path=output_path,
            )
        )
    return {
        "status": "ready" if evidence_items else "blocked",
        "evidence_basis": "historical_backtest",
        "request_count": len(requests),
        "evidence_count": len(evidence_items),
        "passed_count": sum(1 for item in evidence_items if item.get("gate_status") == "passed"),
        "blocked_count": sum(1 for item in evidence_items if item.get("gate_status") != "passed"),
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
        "evidence": evidence_items,
    }


def write_shortpick_historical_backtest_evidence(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _normalize_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(request),
        "start_date": str(request.get("start_date") or ""),
        "end_date": str(request.get("end_date") or ""),
        "entry_price_source": str(request.get("entry_price_source") or "next_close"),
        "benchmark_mode": str(request.get("benchmark_mode") or "universe_equal_weight"),
        "account_profile": str(request.get("account_profile") or "new_retail_cash_account"),
        "pool_limit": int(request.get("pool_limit") or 40),
        "rank_limit": int(request.get("rank_limit") or 6),
        "horizon_days": int(request.get("horizon_days") or 5),
        "cost_bps": float(request.get("cost_bps") if request.get("cost_bps") is not None else 20.0),
        "min_signal_symbol_count": int(request.get("min_signal_symbol_count") or 45),
        "portfolio_strategies": list(request.get("portfolio_strategies") or []),
    }


def _request_block_reason(request: dict[str, Any]) -> str | None:
    if request.get("evidence_basis") != "historical_backtest":
        return "unsupported_evidence_basis"
    if not request.get("control_group_id") or not request.get("rule_signature"):
        return "missing_control_group_id_or_rule_signature"
    if not request.get("start_date") or not request.get("end_date"):
        return "missing_backtest_date_window"
    if not request.get("portfolio_strategies"):
        return "no_executable_control_backtest_mapping"
    if str(request.get("start_date")) > str(request.get("end_date")):
        return "invalid_backtest_date_window"
    return None


def _blocked_evidence(request: dict[str, Any], *, block_reason: str) -> dict[str, Any]:
    return {
        "artifact_id": _evidence_artifact_id(request, {"gate_status": "blocked", "gate_reasons": [block_reason]}),
        "artifact_type": "shortpick_historical_backtest_evidence",
        "version": "shortpick-historical-backtest-evidence-v1",
        "status": "blocked",
        "evidence_basis": "historical_backtest",
        "gate_status": "blocked",
        "gate_reasons": [block_reason],
        "leakage_audit_status": "blocked",
        "leakage_audit_reasons": [block_reason],
        "request_id": request.get("request_id"),
        "control_group_id": request.get("control_group_id"),
        "rule_signature": request.get("rule_signature"),
        "rule": request.get("rule"),
        "request": request,
        "portfolio_strategies": list(request.get("portfolio_strategies") or []),
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
        "retrospective": False,
        "runner_policy": "blocked_until_explicit_portfolio_strategy_mapping_exists",
    }


def _historical_backtest_gate(
    payload: dict[str, Any],
    *,
    strategies: tuple[str, ...],
    leakage_audit: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    if int((payload.get("data_scope") or {}).get("signal_day_count") or 0) <= 0:
        reasons.append("no_historical_signal_days")
    metrics = _metrics_by_mode_strategy(payload, strategies=strategies)
    if not any(int(row.get("trade_count") or 0) > 0 for row in metrics):
        reasons.append("no_completed_historical_trades")
    if leakage_audit.get("status") != "passed":
        reasons.append("leakage_audit_failed")
    return {
        "gate_status": "passed" if not reasons else "blocked",
        "gate_reasons": reasons,
    }


def _leakage_audit(payload: dict[str, Any], *, request: dict[str, Any]) -> dict[str, Any]:
    data_scope = payload.get("data_scope") or {}
    requested_start = str(request.get("start_date") or "")
    requested_end = str(request.get("end_date") or "")
    signal_from = str(data_scope.get("signal_date_from") or "")
    signal_to = str(data_scope.get("signal_date_to") or "")
    reasons: list[str] = []
    if signal_from and requested_start and signal_from < requested_start:
        reasons.append("signal_date_from_before_requested_start")
    if signal_to and requested_end and signal_to > requested_end:
        reasons.append("signal_date_to_after_requested_end")
    return {
        "status": "failed" if reasons else "passed",
        "reasons": reasons or ["verified_signal_date_window_inside_request_date_window"],
        "requested_start_date": requested_start,
        "requested_end_date": requested_end,
        "observed_signal_date_from": signal_from or None,
        "observed_signal_date_to": signal_to or None,
    }


def _metrics_by_mode_strategy(payload: dict[str, Any], *, strategies: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode, by_strategy in (payload.get("results") or {}).items():
        if not isinstance(by_strategy, dict):
            continue
        for strategy in strategies:
            summary = ((by_strategy.get(strategy) or {}).get("summary") or {})
            rows.append(
                {
                    "mode": mode,
                    "strategy": strategy,
                    "trade_count": summary.get("trade_count"),
                    "total_return": summary.get("total_return"),
                    "excess_total_return": summary.get("excess_total_return"),
                    "max_drawdown": summary.get("max_drawdown"),
                    "evidence_grade": summary.get("evidence_grade"),
                }
            )
    return rows


def _portfolio_artifact_path(evidence_output_path: str | Path) -> Path:
    path = Path(evidence_output_path)
    return path.with_name(f"{path.stem}.portfolio-backtest{path.suffix or '.json'}")


def _request_output_path(request: dict[str, Any], *, output_dir: str | Path | None) -> str | Path:
    if output_dir:
        source = Path(str(request.get("output_path") or f"{request.get('request_id') or 'request'}.json"))
        return Path(output_dir) / source.name
    output_path = request.get("output_path")
    if not output_path:
        raise ValueError("request.output_path is required when output_dir is not provided")
    return str(output_path)


def _evidence_artifact_id(request: dict[str, Any], gate: dict[str, Any]) -> str:
    encoded = json.dumps(
        {
            "request_id": request.get("request_id"),
            "control_group_id": request.get("control_group_id"),
            "rule_signature": request.get("rule_signature"),
            "portfolio_strategies": request.get("portfolio_strategies") or [],
            "gate_status": gate.get("gate_status"),
            "gate_reasons": gate.get("gate_reasons") or [],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "shortpick-historical-backtest-evidence:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
