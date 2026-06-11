from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ashare_evidence.shortpick_strategy_governance import (
    DRAWDOWN_REVERSAL_FILTER_CONTROL_ID,
    REPEATED_EXPOSURE_LIMIT_CONTROL_ID,
    SAME_SYMBOL_COOLDOWN_CONTROL_ID,
    apply_shortpick_drawdown_reversal_filter_control,
    apply_shortpick_repeated_exposure_limit_control,
    apply_shortpick_same_symbol_cooldown_control,
)

FILTER_RESELECT_SELECTION_POLICY = "filter_ranked_pool_select_first_allowed"


def run_shortpick_retrospective_forward_replay_request(
    request: dict[str, Any],
    paper_tracking: dict[str, Any],
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    normalized = _normalize_request(request)
    block_reason = _request_block_reason(normalized)
    if block_reason:
        payload = _blocked_replay(normalized, block_reason=block_reason)
        return _with_optional_artifact(payload, output_path)

    candidates, blocked_rows = _ranked_candidate_rows(paper_tracking, request=normalized)
    if not candidates:
        payload = _blocked_replay(
            normalized,
            block_reason="no_ranked_replay_candidates_inside_window_before_rule_defined_at",
            blocked_rows=blocked_rows,
        )
        return _with_optional_artifact(payload, output_path)

    result = _apply_control(normalized, candidates, paper_tracking)
    rows = [_replay_row(row, request=normalized) for row in result.get("rows") or [] if isinstance(row, dict)]
    payload = {
        "artifact_id": _replay_artifact_id(normalized, rows),
        "artifact_type": "shortpick_retrospective_forward_replay",
        "version": "shortpick-retrospective-forward-replay-v1",
        "status": "ready" if rows else "blocked",
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "request_id": normalized.get("request_id"),
        "control_group_id": normalized.get("control_group_id"),
        "rule_signature": normalized.get("rule_signature"),
        "rule_defined_at": normalized.get("rule_defined_at"),
        "request": normalized,
        "input_candidate_count": len(candidates),
        "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
        "replay_row_count": len(rows),
        "no_trade_signal_count": len(result.get("no_trade_rows") or []),
        "blocked_row_count": len(blocked_rows),
        "control_result": _control_summary(result),
        "rows": rows,
        "no_trade_rows": result.get("no_trade_rows") or [],
        "blocked_rows": blocked_rows,
        "leakage_audit_status": result.get("leakage_audit_status") or "passed",
        "leakage_audit_reasons": result.get("leakage_audit_reasons") or [
            "used_only_ranked_replay_pool_rows_before_rule_defined_at"
        ],
        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
        "runner_policy": "artifact_only_no_database_or_paper_tracking_write",
    }
    return _with_optional_artifact(payload, output_path)


def run_shortpick_retrospective_forward_replay_requests(
    requests: list[dict[str, Any]],
    paper_tracking: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    artifacts = []
    for request in requests:
        artifacts.append(
            run_shortpick_retrospective_forward_replay_request(
                request,
                paper_tracking,
                output_path=_request_output_path(request, output_dir=output_dir),
            )
        )
    return {
        "status": "ready" if artifacts else "blocked",
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "request_count": len(requests),
        "artifact_count": len(artifacts),
        "ready_count": sum(1 for item in artifacts if item.get("status") == "ready"),
        "blocked_count": sum(1 for item in artifacts if item.get("status") != "ready"),
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
        "artifacts": artifacts,
    }


def write_shortpick_retrospective_forward_replay(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _normalize_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(request),
        "control_group_id": str(request.get("control_group_id") or ""),
        "rule_signature": str(request.get("rule_signature") or ""),
        "rule_defined_at": _date_part(request.get("rule_defined_at")),
        "replay_start_date": _date_part(request.get("replay_start_date")),
        "replay_end_date": _date_part(request.get("replay_end_date")),
        "evidence_basis": str(request.get("evidence_basis") or ""),
        "retrospective": bool(request.get("retrospective")),
        "rule": dict(request.get("rule") or {}),
    }


def _request_block_reason(request: dict[str, Any]) -> str | None:
    if request.get("evidence_basis") != "retrospective_forward_replay":
        return "unsupported_evidence_basis"
    if not request.get("retrospective"):
        return "request_not_marked_retrospective"
    if not request.get("control_group_id") or not request.get("rule_signature"):
        return "missing_control_group_id_or_rule_signature"
    if not request.get("rule_defined_at"):
        return "missing_rule_defined_at"
    if not request.get("replay_start_date") or not request.get("replay_end_date"):
        return "missing_replay_window"
    if str(request["replay_start_date"]) > str(request["replay_end_date"]):
        return "invalid_replay_window"
    if request["replay_end_date"] >= request["rule_defined_at"]:
        return "replay_window_must_end_before_rule_defined_at"
    if bool(request.get("true_forward_tracking_eligible")):
        return "request_must_not_be_true_forward_eligible"
    if bool(request.get("headline_metric_eligible")):
        return "request_must_not_be_headline_metric_eligible"
    if request["control_group_id"] not in {
        SAME_SYMBOL_COOLDOWN_CONTROL_ID,
        DRAWDOWN_REVERSAL_FILTER_CONTROL_ID,
        REPEATED_EXPOSURE_LIMIT_CONTROL_ID,
    }:
        return "unsupported_control_group_id"
    return None


def _ranked_candidate_rows(
    paper_tracking: dict[str, Any],
    *,
    request: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    source_rows = _ranked_candidate_source_rows(paper_tracking)
    if not source_rows:
        return [], [{"blocker": "missing_ranked_candidate_pool", "paper_tracking_item_count": len(paper_tracking.get("items") or [])}]

    for index, item in enumerate(source_rows):
        if not isinstance(item, dict):
            blocked.append({"row_index": index, "blocker": "row_not_object"})
            continue
        signal_date = _date_part(item.get("signal_date") or item.get("run_date"))
        symbol = str(item.get("symbol") or "")
        if not signal_date or not symbol:
            blocked.append({"row_index": index, "blocker": "missing_signal_date_or_symbol"})
            continue
        if signal_date < request["replay_start_date"] or signal_date > request["replay_end_date"]:
            continue
        if signal_date >= request["rule_defined_at"]:
            blocked.append({"row_index": index, "signal_date": signal_date, "blocker": "signal_date_not_before_rule_defined_at"})
            continue
        candidates.append(
            {
                **item,
                "candidate_id": item.get("candidate_id") or f"{signal_date}:{symbol}:{index}",
                "signal_date": signal_date,
                "symbol": symbol,
                "candidate_rank": _rank_value(item, fallback=index + 1),
            }
        )
    return candidates, blocked


def _ranked_candidate_source_rows(paper_tracking: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(paper_tracking.get("ranked_candidates"), list):
        return [dict(item) for item in paper_tracking["ranked_candidates"] if isinstance(item, dict)]

    rows: list[dict[str, Any]] = []
    for pool_index, pool in enumerate(paper_tracking.get("ranked_candidate_pools") or []):
        if not isinstance(pool, dict):
            continue
        signal_date = _date_part(pool.get("signal_date") or pool.get("run_date"))
        run_id = pool.get("run_id")
        for rank_index, item in enumerate(pool.get("candidates") or [], start=1):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    **item,
                    "signal_date": _date_part(item.get("signal_date") or item.get("run_date")) or signal_date,
                    "run_id": item.get("run_id") or run_id,
                    "candidate_rank": _rank_value(item, fallback=rank_index),
                    "ranked_pool_index": pool_index,
                }
            )
    return rows


def _apply_control(request: dict[str, Any], candidates: list[dict[str, Any]], paper_tracking: dict[str, Any]) -> dict[str, Any]:
    rule = dict(request.get("rule") or {})
    if request["control_group_id"] == SAME_SYMBOL_COOLDOWN_CONTROL_ID:
        return _apply_stateful_filter_reselect(
            request,
            candidates,
            rule=rule,
            action_field="cooldown_action",
            control_fn=apply_shortpick_same_symbol_cooldown_control,
            evidence_builder=_selected_completed_outcome_rows,
        )
    if request["control_group_id"] == REPEATED_EXPOSURE_LIMIT_CONTROL_ID:
        return _apply_stateful_filter_reselect(
            request,
            candidates,
            rule=rule,
            action_field="exposure_action",
            control_fn=apply_shortpick_repeated_exposure_limit_control,
            evidence_builder=lambda selected_rows: selected_rows,
        )
    if request["control_group_id"] == DRAWDOWN_REVERSAL_FILTER_CONTROL_ID:
        result = apply_shortpick_drawdown_reversal_filter_control(
            candidates,
            _feature_rows(paper_tracking, request=request),
            rule=rule,
            evidence_basis="retrospective_forward_replay",
        )
        return _filter_reselect_result(result, action_field="filter_action")
    return _blocked_control_result(
        request,
        candidates,
        block_reason="unsupported_control_group_id",
    )


def _apply_stateful_filter_reselect(
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    rule: dict[str, Any],
    action_field: str,
    control_fn: Any,
    evidence_builder: Any,
) -> dict[str, Any]:
    selected_rows: list[dict[str, Any]] = []
    no_trade_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for signal_date in sorted({_date_part(row.get("signal_date")) for row in candidates if _date_part(row.get("signal_date"))}):
        day_candidates = sorted(
            [row for row in candidates if _date_part(row.get("signal_date")) == signal_date],
            key=lambda row: _rank_value(row, fallback=999999),
        )
        result = control_fn(
            day_candidates,
            evidence_builder(selected_rows),
            rule=rule,
            evidence_basis="retrospective_forward_replay",
        )
        diagnostic_rows.extend(result.get("rows") or [])
        selected = _first_allowed_row(result.get("rows") or [], action_field=action_field)
        if selected is None:
            no_trade_rows.append(
                {
                    "signal_date": signal_date,
                    "control_group_id": request["control_group_id"],
                    "rule_signature": request["rule_signature"],
                    "blocked_higher_ranked_candidates": result.get("rows") or [],
                    "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
                    "no_trade_reason": "all_ranked_candidates_blocked_by_control",
                }
            )
            continue
        selected_rows.append(
            {
                **selected,
                "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
                "selected_after_control": True,
                "selected_rank_after_filter": 1,
                "blocked_higher_ranked_candidates": [
                    row
                    for row in result.get("rows") or []
                    if _rank_value(row, fallback=999999) < _rank_value(selected, fallback=999999)
                    and row.get(action_field) != "allowed"
                ],
            }
        )
    return {
        "status": "ready",
        "control_group_id": request["control_group_id"],
        "rule_signature": request["rule_signature"],
        "evidence_basis": "retrospective_forward_replay",
        "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
        "leakage_audit_status": "passed",
        "leakage_audit_reasons": ["selected_first_allowed_candidate_from_ranked_pool_by_signal_date"],
        "input_candidate_count": len(candidates),
        "diagnostic_row_count": len(diagnostic_rows),
        "blocked_count": len(diagnostic_rows) - len([row for row in diagnostic_rows if row.get(action_field) == "allowed"]),
        "allowed_count": len([row for row in diagnostic_rows if row.get(action_field) == "allowed"]),
        "selected_count": len(selected_rows),
        "no_trade_count": len(no_trade_rows),
        "rows": selected_rows,
        "diagnostic_rows": diagnostic_rows,
        "no_trade_rows": no_trade_rows,
    }


def _filter_reselect_result(result: dict[str, Any], *, action_field: str) -> dict[str, Any]:
    selected_rows: list[dict[str, Any]] = []
    no_trade_rows: list[dict[str, Any]] = []
    rows = [dict(row) for row in result.get("rows") or [] if isinstance(row, dict)]
    for signal_date in sorted({_date_part(row.get("signal_date")) for row in rows if _date_part(row.get("signal_date"))}):
        day_rows = sorted(
            [row for row in rows if _date_part(row.get("signal_date")) == signal_date],
            key=lambda row: _rank_value(row, fallback=999999),
        )
        selected = _first_allowed_row(day_rows, action_field=action_field)
        if selected is None:
            no_trade_rows.append(
                {
                    "signal_date": signal_date,
                    "control_group_id": result.get("control_group_id"),
                    "rule_signature": result.get("rule_signature"),
                    "blocked_higher_ranked_candidates": day_rows,
                    "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
                    "no_trade_reason": "all_ranked_candidates_blocked_by_control",
                }
            )
            continue
        selected_rows.append(
            {
                **selected,
                "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
                "selected_after_control": True,
                "selected_rank_after_filter": 1,
                "blocked_higher_ranked_candidates": [
                    row
                    for row in day_rows
                    if _rank_value(row, fallback=999999) < _rank_value(selected, fallback=999999)
                    and row.get(action_field) != "allowed"
                ],
            }
        )
    return {
        **result,
        "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
        "diagnostic_row_count": len(rows),
        "selected_count": len(selected_rows),
        "no_trade_count": len(no_trade_rows),
        "rows": selected_rows,
        "diagnostic_rows": rows,
        "no_trade_rows": no_trade_rows,
    }


def _first_allowed_row(rows: list[dict[str, Any]], *, action_field: str) -> dict[str, Any] | None:
    for row in sorted(rows, key=lambda item: _rank_value(item, fallback=999999)):
        if row.get(action_field) == "allowed":
            return dict(row)
    return None


def _blocked_control_result(request: dict[str, Any], candidates: list[dict[str, Any]], *, block_reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "control_group_id": request.get("control_group_id"),
        "rule_signature": request.get("rule_signature"),
        "evidence_basis": "retrospective_forward_replay",
        "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
        "leakage_audit_status": "blocked",
        "leakage_audit_reasons": [block_reason],
        "input_candidate_count": len(candidates),
        "rows": [],
        "no_trade_rows": [],
        "blocker": block_reason,
    }


def _selected_completed_outcome_rows(selected_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in selected_rows:
        signal_date = _date_part(item.get("signal_date") or item.get("run_date"))
        symbol = str(item.get("symbol") or "")
        for horizon in item.get("validation_by_horizon") or []:
            if not isinstance(horizon, dict) or str(horizon.get("status") or "") != "completed":
                continue
            stock_return = _float(horizon.get("stock_return"))
            exit_date = _date_part(horizon.get("exit_date") or horizon.get("exit_at") or item.get("exit_date") or item.get("exit_at"))
            if signal_date and symbol and exit_date and stock_return is not None:
                rows.append(
                    {
                        "candidate_id": item.get("candidate_id"),
                        "signal_date": signal_date,
                        "symbol": symbol,
                        "exit_date": exit_date,
                        "horizon_days": horizon.get("horizon_days"),
                        "status": "completed",
                        "stock_return": stock_return,
                    }
                )
    return rows


def _completed_outcome_rows(paper_tracking: dict[str, Any], *, request: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in paper_tracking.get("items") or []:
        if not isinstance(item, dict):
            continue
        signal_date = _date_part(item.get("signal_date") or item.get("run_date"))
        symbol = str(item.get("symbol") or "")
        if not _paper_item_in_replay_scope(signal_date, request):
            continue
        for horizon in item.get("validation_by_horizon") or []:
            if not isinstance(horizon, dict) or str(horizon.get("status") or "") != "completed":
                continue
            stock_return = _float(horizon.get("stock_return"))
            exit_date = _date_part(horizon.get("exit_date") or horizon.get("exit_at") or item.get("exit_date") or item.get("exit_at"))
            if signal_date and symbol and exit_date and stock_return is not None:
                rows.append(
                    {
                        "candidate_id": item.get("candidate_id"),
                        "signal_date": signal_date,
                        "symbol": symbol,
                        "exit_date": exit_date,
                        "horizon_days": horizon.get("horizon_days"),
                        "status": "completed",
                        "stock_return": stock_return,
                    }
                )
    return rows


def _feature_rows(paper_tracking: dict[str, Any], *, request: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_items = [
        *[item for item in paper_tracking.get("items") or [] if isinstance(item, dict)],
        *_ranked_candidate_source_rows(paper_tracking),
    ]
    seen: set[tuple[str, str, str]] = set()
    for item in source_items:
        if not isinstance(item, dict):
            continue
        signal_date = _date_part(item.get("signal_date") or item.get("run_date"))
        symbol = str(item.get("symbol") or "")
        if not _paper_item_in_replay_scope(signal_date, request):
            continue
        features = dict(item.get("drawdown_reversal_features") or item.get("signal_features") or {})
        row = {
            "symbol": symbol,
            "feature_date": _date_part(features.get("feature_date") or item.get("feature_date") or signal_date),
            "recent_drawdown_return": features.get("recent_drawdown_return", item.get("recent_drawdown_return")),
            "short_window_return": features.get("short_window_return", item.get("short_window_return")),
            "price_vs_ma20": features.get("price_vs_ma20", item.get("price_vs_ma20")),
            "high_level_reversal_return": features.get("high_level_reversal_return", item.get("high_level_reversal_return")),
        }
        has_feature_value = any(
            row.get(field) is not None
            for field in (
                "recent_drawdown_return",
                "short_window_return",
                "price_vs_ma20",
                "high_level_reversal_return",
            )
        )
        key = (str(row["symbol"]), str(row["feature_date"]), signal_date)
        if row["symbol"] and row["feature_date"] and has_feature_value and key not in seen:
            seen.add(key)
            rows.append(row)
    return rows


def _paper_item_in_replay_scope(signal_date: str, request: dict[str, Any]) -> bool:
    return bool(
        signal_date
        and request["replay_start_date"] <= signal_date <= request["replay_end_date"]
        and signal_date < request["rule_defined_at"]
    )


def _replay_row(row: dict[str, Any], *, request: dict[str, Any]) -> dict[str, Any]:
    signal_date = _date_part(row.get("signal_date") or row.get("run_date"))
    symbol = str(row.get("symbol") or "")
    return {
        **row,
        "signal_date": signal_date,
        "symbol": symbol,
        "control_group_id": request["control_group_id"],
        "rule_signature": request["rule_signature"],
        "rule_defined_at": request["rule_defined_at"],
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "true_forward_tracking_eligible": False,
        "headline_metric_eligible": False,
        "paper_tracking_write_policy": "forbidden",
        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
        "pairing_key": f"{request['control_group_id']}|{request['rule_signature']}|{symbol}|{signal_date}",
    }


def _rank_value(row: dict[str, Any], *, fallback: int) -> int:
    for field in ("candidate_rank", "source_rank", "rank"):
        try:
            value = int(row.get(field))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return fallback


def _control_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status"),
        "control_group_id": result.get("control_group_id"),
        "rule_signature": result.get("rule_signature"),
        "blocked_count": result.get("blocked_count"),
        "allowed_count": result.get("allowed_count"),
        "leakage_audit_status": result.get("leakage_audit_status"),
        "leakage_audit_reasons": result.get("leakage_audit_reasons"),
    }


def _blocked_replay(
    request: dict[str, Any],
    *,
    block_reason: str,
    blocked_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": _replay_artifact_id(request, []),
        "artifact_type": "shortpick_retrospective_forward_replay",
        "version": "shortpick-retrospective-forward-replay-v1",
        "status": "blocked",
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "request_id": request.get("request_id"),
        "control_group_id": request.get("control_group_id"),
        "rule_signature": request.get("rule_signature"),
        "rule_defined_at": request.get("rule_defined_at"),
        "request": request,
        "blocker": block_reason,
        "rows": [],
        "blocked_rows": blocked_rows or [],
        "leakage_audit_status": "blocked",
        "leakage_audit_reasons": [block_reason],
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
        "runner_policy": "artifact_only_no_database_or_paper_tracking_write",
    }


def _with_optional_artifact(payload: dict[str, Any], output_path: str | Path | None) -> dict[str, Any]:
    if output_path is None:
        return payload
    path = write_shortpick_retrospective_forward_replay(payload, output_path=output_path)
    return {**payload, "artifact": {"path": str(path)}}


def _request_output_path(request: dict[str, Any], *, output_dir: str | Path | None) -> str | Path | None:
    if output_dir is None:
        return request.get("output_path")
    source = Path(str(request.get("output_path") or f"{request.get('request_id') or 'request'}.json"))
    return Path(output_dir) / source.name


def _replay_artifact_id(request: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        {
            "request_id": request.get("request_id"),
            "control_group_id": request.get("control_group_id"),
            "rule_signature": request.get("rule_signature"),
            "row_count": len(rows),
            "row_keys": [row.get("pairing_key") for row in rows],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "shortpick-retrospective-forward-replay:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _date_part(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return value.split("T", 1)[0].split(" ", 1)[0]


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
