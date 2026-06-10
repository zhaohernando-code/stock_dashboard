"""Short-pick strategy governance evidence builders.

The functions in this module are intentionally read-only. They aggregate
already materialized paper-tracking rows into evidence packs for later human
or policy-governed retirement decisions, but they do not decide retirement.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any

SAME_SYMBOL_COOLDOWN_CONTROL_ID = "control_same_symbol_cooldown:v1"
DRAWDOWN_REVERSAL_FILTER_CONTROL_ID = "control_drawdown_reversal_filter:v1"


def build_shortpick_strategy_retirement_evidence_packs(
    paper_tracking: dict[str, Any],
    *,
    evidence_basis: str = "true_forward_tracking",
    historical_evidence: dict[str, Any] | None = None,
    baseline_evidence: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build strategy-level evidence packs from the paper-tracking ledger.

    ``paper_tracking`` is expected to match the JSON returned by
    ``_build_shortpick_paper_tracking_ledger``. ``evidence_basis`` defaults to
    true forward tracking because that is the source ledger, but callers must
    override it for retrospective or historical inputs. Optional historical and
    baseline inputs are copied by strategy key/family when available; missing
    optional evidence is represented explicitly instead of inferred.
    """

    if evidence_basis not in {"true_forward_tracking", "retrospective_forward_replay", "historical_backtest"}:
        raise ValueError(f"unsupported shortpick evidence_basis: {evidence_basis}")

    items = [_dict(item) for item in paper_tracking.get("items") or [] if isinstance(item, dict)]
    grouped: dict[str, dict[str, Any]] = {}
    observations_by_strategy_horizon: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for item in items:
        metadata = _strategy_metadata(item)
        strategy_id = str(metadata["strategy_id"])
        existing = grouped.get(strategy_id)
        if existing is None:
            grouped[strategy_id] = {
                **metadata,
                "signal_count": 0,
                "symbols": set(),
                "names": set(),
                "first_signal_date": None,
                "latest_signal_date": None,
            }
            existing = grouped[strategy_id]

        existing["signal_count"] = int(existing.get("signal_count") or 0) + 1
        symbol = str(item.get("symbol") or "")
        name = str(item.get("name") or "")
        if symbol:
            existing["symbols"].add(symbol)
        if name:
            existing["names"].add(name)
        _extend_date_bounds(existing, str(item.get("signal_date") or item.get("run_date") or ""))

        for horizon in item.get("validation_by_horizon") or []:
            if not isinstance(horizon, dict) or horizon.get("status") != "completed":
                continue
            stock_return = _float(horizon.get("stock_return"))
            if stock_return is None:
                continue
            horizon_days = _horizon_key(horizon.get("horizon_days"))
            observations_by_strategy_horizon[strategy_id][horizon_days].append(
                {
                    "candidate_id": item.get("candidate_id"),
                    "run_id": item.get("run_id"),
                    "signal_date": item.get("signal_date") or item.get("run_date"),
                    "entry_date": item.get("entry_date") or _date_part(horizon.get("entry_at") or item.get("entry_at")),
                    "exit_date": _date_part(horizon.get("exit_at") or item.get("exit_at")),
                    "symbol": symbol,
                    "name": name,
                    "stock_return": stock_return,
                    "excess_return": _float(horizon.get("excess_return")),
                }
            )

    packs: list[dict[str, Any]] = []
    for strategy_id in sorted(grouped):
        metadata = grouped[strategy_id]
        horizon_summaries = [
            _horizon_summary(horizon_days, observations)
            for horizon_days, observations in sorted(
                observations_by_strategy_horizon.get(strategy_id, {}).items(),
                key=lambda item: int(item[0]) if item[0].isdigit() else 9999,
            )
        ]
        completed_count = sum(int(summary["completed_sample_count"]) for summary in horizon_summaries)
        packs.append(
            {
                "strategy_id": strategy_id,
                "evidence_basis": evidence_basis,
                "decision_status": "not_evaluated",
                "tracking_group": metadata["tracking_group"],
                "tracking_role": metadata["tracking_role"],
                "strategy_family": metadata["strategy_family"],
                "entry_price_source": metadata["entry_price_source"],
                "source_rank": metadata["source_rank"],
                "selection_label": metadata["selection_label"],
                "entry_rule": metadata["entry_rule"],
                "signal_count": metadata["signal_count"],
                "completed_observation_count": completed_count,
                "distinct_symbol_count": len(metadata["symbols"]),
                "symbols": sorted(metadata["symbols"]),
                "names": sorted(metadata["names"]),
                "first_signal_date": metadata["first_signal_date"],
                "latest_signal_date": metadata["latest_signal_date"],
                "horizon_summaries": horizon_summaries,
                "historical_evidence": _evidence_lookup(historical_evidence, metadata),
                "baseline_comparison": _evidence_lookup(baseline_evidence, metadata),
            }
        )

    return {
        "status": "ready",
        "generated_at": generated_at,
        "evidence_basis": evidence_basis,
        "source": "shortpick_paper_tracking_ledger",
        "decision_policy": "evidence_only_no_retirement_decision",
        "strategy_count": len(packs),
        "packs": packs,
    }


def build_shortpick_strategy_status_recommendations(
    evidence_pack_result: dict[str, Any],
    *,
    retirement_artifacts: dict[str, Any] | None = None,
    primary_horizon_days: int = 10,
) -> dict[str, Any]:
    """Recommend governance status from evidence packs without writing state."""

    packs = [_dict(item) for item in evidence_pack_result.get("packs") or [] if isinstance(item, dict)]
    recommendations = [
        _status_recommendation(
            pack,
            retirement_artifact=_retirement_artifact_lookup(retirement_artifacts, str(pack.get("strategy_id") or "")),
            primary_horizon_days=primary_horizon_days,
        )
        for pack in packs
    ]
    return {
        "status": "ready",
        "source": "shortpick_strategy_retirement_evidence_packs",
        "decision_policy": "retired_requires_strategy_retirement_artifact_and_decision_log_ref",
        "primary_horizon_days": primary_horizon_days,
        "strategy_count": len(recommendations),
        "recommendations": recommendations,
    }


def filter_shortpick_generation_eligible_items(
    items: list[dict[str, Any]],
    status_recommendation_result: dict[str, Any],
    *,
    include_retired: bool = False,
) -> dict[str, Any]:
    """Filter generation candidates using already computed governance status."""

    status_by_strategy_id = {
        str(item.get("strategy_id") or ""): str(item.get("recommended_status") or "")
        for item in status_recommendation_result.get("recommendations") or []
        if isinstance(item, dict) and item.get("strategy_id")
    }
    eligible_items: list[dict[str, Any]] = []
    excluded_items: list[dict[str, Any]] = []
    for item in [_dict(value) for value in items if isinstance(value, dict)]:
        strategy_id = _strategy_id_from_generation_item(item)
        governance_status = status_by_strategy_id.get(strategy_id, "untracked")
        projected = {
            **item,
            "strategy_id": strategy_id,
            "governance_status": governance_status,
        }
        if governance_status == "retired" and not include_retired:
            excluded_items.append(
                {
                    "strategy_id": strategy_id,
                    "governance_status": governance_status,
                    "reason": "retired_strategy_excluded_from_active_generation",
                    "item": projected,
                }
            )
        else:
            eligible_items.append(projected)

    return {
        "status": "ready",
        "decision_policy": "exclude_only_retired_status_from_active_generation",
        "include_retired": include_retired,
        "input_count": len(items),
        "eligible_count": len(eligible_items),
        "excluded_count": len(excluded_items),
        "eligible_items": eligible_items,
        "excluded_items": excluded_items,
    }


def project_shortpick_strategy_view_sections(
    status_recommendation_result: dict[str, Any],
) -> dict[str, Any]:
    """Split strategy status rows into primary and archive display sections."""

    primary_items: list[dict[str, Any]] = []
    archive_items: list[dict[str, Any]] = []
    for item in status_recommendation_result.get("recommendations") or []:
        if not isinstance(item, dict):
            continue
        projected = {
            "strategy_id": item.get("strategy_id"),
            "recommended_status": item.get("recommended_status"),
            "evidence_basis": item.get("evidence_basis"),
            "tracking_group": item.get("tracking_group"),
            "tracking_role": item.get("tracking_role"),
            "strategy_family": item.get("strategy_family"),
            "entry_price_source": item.get("entry_price_source"),
            "primary_horizon_days": item.get("primary_horizon_days"),
            "reasons": item.get("reasons") if isinstance(item.get("reasons"), list) else [],
            "blockers": item.get("blockers") if isinstance(item.get("blockers"), list) else [],
        }
        if projected["recommended_status"] == "retired":
            archive_items.append({**projected, "view_section": "archive"})
        else:
            primary_items.append({**projected, "view_section": "primary"})

    return {
        "status": "ready",
        "decision_policy": "retired_status_hidden_from_primary_view_and_kept_in_archive",
        "primary_count": len(primary_items),
        "archive_count": len(archive_items),
        "primary_items": primary_items,
        "archive_items": archive_items,
    }


def build_shortpick_strategy_archive_records(
    view_projection_result: dict[str, Any],
    evidence_pack_result: dict[str, Any],
    *,
    retirement_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build auditable archive records for strategies removed from primary view."""

    packs_by_strategy_id = {
        str(item.get("strategy_id") or ""): _dict(item)
        for item in evidence_pack_result.get("packs") or []
        if isinstance(item, dict) and item.get("strategy_id")
    }
    records: list[dict[str, Any]] = []
    for item in view_projection_result.get("archive_items") or []:
        if not isinstance(item, dict):
            continue
        strategy_id = str(item.get("strategy_id") or "")
        pack = packs_by_strategy_id.get(strategy_id, {})
        records.append(
            {
                "strategy_id": strategy_id,
                "recommended_status": item.get("recommended_status"),
                "evidence_basis": item.get("evidence_basis") or pack.get("evidence_basis"),
                "tracking_group": item.get("tracking_group") or pack.get("tracking_group"),
                "tracking_role": item.get("tracking_role") or pack.get("tracking_role"),
                "strategy_family": item.get("strategy_family") or pack.get("strategy_family"),
                "entry_price_source": item.get("entry_price_source") or pack.get("entry_price_source"),
                "first_signal_date": pack.get("first_signal_date"),
                "latest_signal_date": pack.get("latest_signal_date"),
                "signal_count": pack.get("signal_count"),
                "completed_observation_count": pack.get("completed_observation_count"),
                "horizon_summaries": pack.get("horizon_summaries") if isinstance(pack.get("horizon_summaries"), list) else [],
                "historical_evidence": _dict(pack.get("historical_evidence")),
                "baseline_comparison": _dict(pack.get("baseline_comparison")),
                "retirement_artifact_ref": _retirement_artifact_lookup(retirement_artifacts, strategy_id),
                "archive_reason": "retired_strategy_removed_from_primary_view",
            }
        )

    return {
        "status": "ready",
        "decision_policy": "preserve_retired_strategy_statistics_and_evidence_refs",
        "archive_count": len(records),
        "records": records,
    }


def build_shortpick_same_symbol_cooldown_rule(
    *,
    control_group_id: str = SAME_SYMBOL_COOLDOWN_CONTROL_ID,
    cooldown_signal_days: int = 5,
    severe_loss_threshold: float = -0.08,
    severe_cooldown_signal_days: int = 10,
    loss_return_threshold: float = 0.0,
    negative_horizon_days: int = 10,
    rule_defined_at: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic same-symbol cooldown control rule."""

    if cooldown_signal_days <= 0:
        raise ValueError("cooldown_signal_days must be positive")
    if severe_cooldown_signal_days < cooldown_signal_days:
        raise ValueError("severe_cooldown_signal_days must be greater than or equal to cooldown_signal_days")
    if negative_horizon_days <= 0:
        raise ValueError("negative_horizon_days must be positive")

    payload = {
        "control_group_id": control_group_id,
        "rule_version": "same-symbol-cooldown-v1",
        "cooldown_basis": "prior_completed_negative_same_symbol_signal_days",
        "cooldown_signal_days": int(cooldown_signal_days),
        "severe_loss_threshold": round(float(severe_loss_threshold), 6),
        "severe_cooldown_signal_days": int(severe_cooldown_signal_days),
        "loss_return_threshold": round(float(loss_return_threshold), 6),
        "negative_horizon_days": int(negative_horizon_days),
        "rule_defined_at": rule_defined_at,
        "leakage_policy": "ignore_outcomes_with_exit_date_on_or_after_signal_date",
    }
    return {
        **payload,
        "rule_signature": _rule_signature(payload),
    }


def apply_shortpick_same_symbol_cooldown_control(
    candidate_rows: list[dict[str, Any]],
    completed_outcome_rows: list[dict[str, Any]],
    *,
    rule: dict[str, Any] | None = None,
    evidence_basis: str = "retrospective_forward_replay",
) -> dict[str, Any]:
    """Apply same-symbol cooldown using only prior completed outcomes."""

    rule = dict(rule or build_shortpick_same_symbol_cooldown_rule())
    signal_dates = sorted(
        {
            _date_part(item.get("signal_date"))
            for item in candidate_rows
            if isinstance(item, dict) and _date_part(item.get("signal_date"))
        }
    )
    negative_events_by_symbol = _same_symbol_negative_events_by_symbol(completed_outcome_rows, rule)
    rows: list[dict[str, Any]] = []
    ignored_future_or_same_day_count = 0

    for item in [_dict(value) for value in candidate_rows if isinstance(value, dict)]:
        symbol = str(item.get("symbol") or "")
        signal_date = _date_part(item.get("signal_date"))
        blocker_events: list[dict[str, Any]] = []
        for event in negative_events_by_symbol.get(symbol, []):
            exit_date = str(event.get("exit_date") or "")
            if not signal_date or not exit_date or exit_date >= signal_date:
                ignored_future_or_same_day_count += 1
                continue
            elapsed_signal_days = _elapsed_signal_days(signal_dates, exit_date=exit_date, signal_date=signal_date)
            cooldown_days = (
                int(rule["severe_cooldown_signal_days"])
                if float(event["stock_return"]) <= float(rule["severe_loss_threshold"])
                else int(rule["cooldown_signal_days"])
            )
            if 0 < elapsed_signal_days <= cooldown_days:
                blocker_events.append(
                    {
                        **event,
                        "elapsed_signal_days": elapsed_signal_days,
                        "cooldown_signal_days": cooldown_days,
                    }
                )

        rows.append(
            {
                **item,
                "control_group_id": rule.get("control_group_id"),
                "rule_signature": rule.get("rule_signature"),
                "evidence_basis": evidence_basis,
                "cooldown_action": "blocked" if blocker_events else "allowed",
                "cooldown_blocked": bool(blocker_events),
                "cooldown_blocker_events": blocker_events,
                "leakage_audit_status": "passed",
                "leakage_audit_reasons": ["used_only_completed_same_symbol_outcomes_before_signal_date"],
            }
        )

    return {
        "status": "ready",
        "control_group_id": rule.get("control_group_id"),
        "rule_signature": rule.get("rule_signature"),
        "evidence_basis": evidence_basis,
        "rule": rule,
        "leakage_audit_status": "passed",
        "leakage_audit_reasons": [
            "used_only_completed_same_symbol_outcomes_before_signal_date",
            "ignored_same_day_or_future_outcomes",
        ],
        "input_candidate_count": len(candidate_rows),
        "blocked_count": sum(1 for row in rows if row["cooldown_blocked"]),
        "allowed_count": sum(1 for row in rows if not row["cooldown_blocked"]),
        "ignored_future_or_same_day_outcome_count": ignored_future_or_same_day_count,
        "rows": rows,
    }


def build_shortpick_drawdown_reversal_filter_rule(
    *,
    control_group_id: str = DRAWDOWN_REVERSAL_FILTER_CONTROL_ID,
    drawdown_lookback_days: int = 10,
    max_recent_drawdown_return: float = -0.08,
    short_window_return_threshold: float = -0.03,
    price_vs_ma20_threshold: float = 0.0,
    high_level_reversal_return_threshold: float = -0.05,
    rule_defined_at: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic drawdown/reversal filter control rule."""

    if drawdown_lookback_days <= 0:
        raise ValueError("drawdown_lookback_days must be positive")

    payload = {
        "control_group_id": control_group_id,
        "rule_version": "drawdown-reversal-filter-v1",
        "filter_basis": "signal_date_or_prior_technical_features",
        "drawdown_lookback_days": int(drawdown_lookback_days),
        "max_recent_drawdown_return": round(float(max_recent_drawdown_return), 6),
        "short_window_return_threshold": round(float(short_window_return_threshold), 6),
        "price_vs_ma20_threshold": round(float(price_vs_ma20_threshold), 6),
        "high_level_reversal_return_threshold": round(float(high_level_reversal_return_threshold), 6),
        "trigger_policy": "block_if_any_threshold_triggered",
        "rule_defined_at": rule_defined_at,
        "leakage_policy": "ignore_features_after_signal_date",
    }
    return {
        **payload,
        "rule_signature": _rule_signature(payload),
    }


def apply_shortpick_drawdown_reversal_filter_control(
    candidate_rows: list[dict[str, Any]],
    signal_feature_rows: list[dict[str, Any]],
    *,
    rule: dict[str, Any] | None = None,
    evidence_basis: str = "retrospective_forward_replay",
) -> dict[str, Any]:
    """Apply drawdown/reversal filtering using signal-date-or-prior features."""

    rule = dict(rule or build_shortpick_drawdown_reversal_filter_rule())
    features_by_symbol = _drawdown_reversal_features_by_symbol(signal_feature_rows)
    rows: list[dict[str, Any]] = []
    ignored_future_feature_count = 0

    for item in [_dict(value) for value in candidate_rows if isinstance(value, dict)]:
        symbol = str(item.get("symbol") or "")
        signal_date = _date_part(item.get("signal_date"))
        feature, ignored_count = _latest_drawdown_reversal_feature(
            features_by_symbol.get(symbol, []),
            signal_date=signal_date,
        )
        ignored_future_feature_count += ignored_count
        triggers = _drawdown_reversal_triggers(feature, rule) if feature else []

        rows.append(
            {
                **item,
                "control_group_id": rule.get("control_group_id"),
                "rule_signature": rule.get("rule_signature"),
                "evidence_basis": evidence_basis,
                "filter_action": "blocked" if triggers else "allowed",
                "filter_blocked": bool(triggers),
                "filter_triggers": triggers,
                "feature_cutoff_date": feature.get("feature_date") if feature else None,
                "feature_coverage_status": "ready" if feature else "missing",
                "leakage_audit_status": "passed",
                "leakage_audit_reasons": ["used_only_signal_date_or_prior_features"],
            }
        )

    return {
        "status": "ready",
        "control_group_id": rule.get("control_group_id"),
        "rule_signature": rule.get("rule_signature"),
        "evidence_basis": evidence_basis,
        "rule": rule,
        "leakage_audit_status": "passed",
        "leakage_audit_reasons": [
            "used_only_signal_date_or_prior_features",
            "ignored_features_after_signal_date",
        ],
        "input_candidate_count": len(candidate_rows),
        "blocked_count": sum(1 for row in rows if row["filter_blocked"]),
        "allowed_count": sum(1 for row in rows if not row["filter_blocked"]),
        "missing_feature_count": sum(1 for row in rows if row["feature_coverage_status"] == "missing"),
        "ignored_future_feature_count": ignored_future_feature_count,
        "rows": rows,
    }


def _rule_signature(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _same_symbol_negative_events_by_symbol(
    rows: list[dict[str, Any]],
    rule: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    loss_threshold = float(rule.get("loss_return_threshold", 0.0))
    horizon_days = int(rule.get("negative_horizon_days", 10))

    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "completed") != "completed":
            continue
        if _horizon_key(row.get("horizon_days")) != str(horizon_days):
            continue

        symbol = str(row.get("symbol") or "")
        exit_date = _date_part(row.get("exit_date") or row.get("exit_at"))
        stock_return = _float(row.get("stock_return"))
        if not symbol or not exit_date or stock_return is None or stock_return >= loss_threshold:
            continue

        grouped[symbol].append(
            {
                "symbol": symbol,
                "signal_date": _date_part(row.get("signal_date") or row.get("run_date")),
                "exit_date": exit_date,
                "horizon_days": horizon_days,
                "stock_return": _round(stock_return),
                "source_candidate_id": row.get("candidate_id"),
                "source_run_id": row.get("run_id"),
            }
        )

    for values in grouped.values():
        values.sort(key=lambda item: (str(item.get("exit_date") or ""), str(item.get("signal_date") or "")))
    return grouped


def _elapsed_signal_days(signal_dates: list[str], *, exit_date: str, signal_date: str) -> int:
    return sum(1 for value in signal_dates if exit_date < value <= signal_date)


def _drawdown_reversal_features_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "")
        feature_date = _date_part(row.get("feature_date") or row.get("as_of_date") or row.get("signal_date"))
        if not symbol or not feature_date:
            continue
        grouped[symbol].append(
            {
                **dict(row),
                "symbol": symbol,
                "feature_date": feature_date,
            }
        )

    for values in grouped.values():
        values.sort(key=lambda item: str(item.get("feature_date") or ""))
    return grouped


def _latest_drawdown_reversal_feature(
    rows: list[dict[str, Any]],
    *,
    signal_date: str,
) -> tuple[dict[str, Any], int]:
    latest: dict[str, Any] = {}
    ignored_future_count = 0
    for row in rows:
        feature_date = str(row.get("feature_date") or "")
        if not signal_date or not feature_date or feature_date > signal_date:
            ignored_future_count += 1
            continue
        latest = row
    return latest, ignored_future_count


def _drawdown_reversal_triggers(feature: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    recent_drawdown = _float(feature.get("recent_drawdown_return"))
    short_window_return = _float(feature.get("short_window_return"))
    price_vs_ma20 = _float(feature.get("price_vs_ma20"))
    high_level_reversal = _float(feature.get("high_level_reversal_return"))

    if recent_drawdown is not None and recent_drawdown <= float(rule["max_recent_drawdown_return"]):
        triggers.append(
            {
                "reason": "recent_drawdown_threshold_triggered",
                "field": "recent_drawdown_return",
                "value": _round(recent_drawdown),
                "threshold": rule["max_recent_drawdown_return"],
            }
        )
    if (
        short_window_return is not None
        and price_vs_ma20 is not None
        and short_window_return <= float(rule["short_window_return_threshold"])
        and price_vs_ma20 <= float(rule["price_vs_ma20_threshold"])
    ):
        triggers.append(
            {
                "reason": "short_window_breakdown_triggered",
                "field": "short_window_return_and_price_vs_ma20",
                "value": {
                    "short_window_return": _round(short_window_return),
                    "price_vs_ma20": _round(price_vs_ma20),
                },
                "threshold": {
                    "short_window_return": rule["short_window_return_threshold"],
                    "price_vs_ma20": rule["price_vs_ma20_threshold"],
                },
            }
        )
    if high_level_reversal is not None and high_level_reversal <= float(rule["high_level_reversal_return_threshold"]):
        triggers.append(
            {
                "reason": "high_level_reversal_threshold_triggered",
                "field": "high_level_reversal_return",
                "value": _round(high_level_reversal),
                "threshold": rule["high_level_reversal_return_threshold"],
            }
        )
    return triggers


def _strategy_metadata(item: dict[str, Any]) -> dict[str, Any]:
    components = _dict(item.get("selection_score_components"))
    tracking_group = str(item.get("tracking_group") or "unknown")
    tracking_role = str(item.get("tracking_role") or "")
    family = str(
        components.get("family")
        or item.get("baseline_family")
        or item.get("strategy_family")
        or ("llm" if tracking_group == "llm_paper_control" else "unknown")
    )
    source_rank = item.get("source_rank")
    entry_rule = str(item.get("entry_rule") or "")
    entry_price_source = str(
        components.get("entry_price_source")
        or item.get("entry_price_source")
        or _infer_entry_price_source(tracking_group=tracking_group, entry_rule=entry_rule)
    )
    strategy_id = _strategy_id(
        [
            tracking_group,
            tracking_role or "primary",
            family,
            entry_price_source,
            "" if source_rank is None else str(source_rank),
        ]
    )
    return {
        "strategy_id": strategy_id,
        "tracking_group": tracking_group,
        "tracking_role": tracking_role,
        "strategy_family": family,
        "entry_price_source": entry_price_source,
        "source_rank": source_rank,
        "selection_label": str(item.get("selection_label") or ""),
        "entry_rule": entry_rule,
        "signal_count": 0,
    }


def _status_recommendation(
    pack: dict[str, Any],
    *,
    retirement_artifact: dict[str, Any],
    primary_horizon_days: int,
) -> dict[str, Any]:
    strategy_id = str(pack.get("strategy_id") or "")
    horizon = _primary_horizon_summary(pack, primary_horizon_days)
    historical = _dict(pack.get("historical_evidence"))
    baseline = _dict(pack.get("baseline_comparison"))
    reasons: list[str] = []
    blockers: list[str] = []

    if _has_retirement_authority(retirement_artifact):
        status = "retired"
        reasons.append("strategy_retirement_artifact_and_decision_log_ref_present")
    elif not horizon:
        status = "observe"
        blockers.append("primary_horizon_missing")
    elif _has_negative_forward_signal(horizon):
        if _retire_candidate_gates_pass(horizon, historical, baseline, reasons, blockers):
            status = "retire_candidate"
        else:
            status = "observe"
    else:
        status = "active"
        reasons.append("no_retirement_evidence_trigger")

    return {
        "strategy_id": strategy_id,
        "recommended_status": status,
        "evidence_basis": pack.get("evidence_basis"),
        "tracking_group": pack.get("tracking_group"),
        "tracking_role": pack.get("tracking_role"),
        "strategy_family": pack.get("strategy_family"),
        "entry_price_source": pack.get("entry_price_source"),
        "primary_horizon_days": primary_horizon_days,
        "primary_horizon_summary": horizon,
        "reasons": reasons,
        "blockers": blockers,
        "retirement_artifact_ref": retirement_artifact if status == "retired" else None,
    }


def _retire_candidate_gates_pass(
    horizon: dict[str, Any],
    historical: dict[str, Any],
    baseline: dict[str, Any],
    reasons: list[str],
    blockers: list[str],
) -> bool:
    if not horizon:
        blockers.append("primary_horizon_missing")
        return False

    if horizon.get("maturity_status") not in {"mature_one_stock_review_sample", "mature_multi_row_review_sample"}:
        blockers.append("forward_sample_not_mature")
    else:
        reasons.append("forward_sample_mature")

    historical_value = _float(historical.get("after_cost_excess_return"))
    if historical.get("status") != "ready" or historical_value is None:
        blockers.append("historical_after_cost_evidence_missing")
    elif historical_value < 0:
        reasons.append("historical_after_cost_excess_negative")
    else:
        blockers.append("historical_after_cost_excess_not_negative")

    median_return = _float(horizon.get("median_stock_return"))
    mean_return = _float(horizon.get("mean_stock_return"))
    win_rate = _float(horizon.get("win_rate"))
    worst_return = _float(horizon.get("worst_stock_return"))
    max_drawdown = _float(horizon.get("max_additive_drawdown"))
    tail_dependency = _dict(horizon.get("tail_dependency"))
    tail_dependent = bool(tail_dependency.get("tail_dependent"))

    if median_return is not None and median_return < 0:
        reasons.append("forward_median_stock_return_negative")
    else:
        blockers.append("forward_median_stock_return_not_negative")
    if mean_return is not None and (mean_return < 0 or tail_dependent):
        reasons.append("forward_mean_negative_or_tail_dependent")
    else:
        blockers.append("forward_mean_not_negative_and_not_tail_dependent")
    if win_rate is not None and win_rate < 0.45:
        reasons.append("forward_win_rate_below_45pct")
    else:
        blockers.append("forward_win_rate_not_below_threshold")
    if (worst_return is not None and worst_return < -0.08) or (max_drawdown is not None and max_drawdown < -0.08):
        reasons.append("tail_risk_gate_failed")
    else:
        blockers.append("tail_risk_gate_not_failed")

    baseline_gap = _float(baseline.get("mean_excess_return_gap"))
    if baseline.get("status") == "ready" and baseline_gap is not None:
        if baseline_gap < 0:
            reasons.append("registered_baseline_gap_negative")
        else:
            blockers.append("registered_baseline_gap_not_negative")

    return not blockers


def _has_negative_forward_signal(horizon: dict[str, Any]) -> bool:
    median_return = _float(horizon.get("median_stock_return"))
    mean_return = _float(horizon.get("mean_stock_return"))
    win_rate = _float(horizon.get("win_rate"))
    return any(
        [
            median_return is not None and median_return < 0,
            mean_return is not None and mean_return < 0,
            win_rate is not None and win_rate < 0.45,
        ]
    )


def _primary_horizon_summary(pack: dict[str, Any], primary_horizon_days: int) -> dict[str, Any]:
    summaries = [_dict(item) for item in pack.get("horizon_summaries") or [] if isinstance(item, dict)]
    for summary in summaries:
        if _horizon_key(summary.get("horizon_days")) == str(primary_horizon_days):
            return summary
    return summaries[0] if summaries else {}


def _strategy_id_from_generation_item(item: dict[str, Any]) -> str:
    explicit = str(item.get("strategy_id") or "")
    if explicit:
        return explicit
    components = _dict(item.get("selection_score_components"))
    tracking_group = str(item.get("tracking_group") or item.get("group") or "unknown")
    tracking_role = str(item.get("tracking_role") or item.get("role") or "primary")
    family = str(
        components.get("family")
        or item.get("strategy_family")
        or item.get("family")
        or item.get("baseline_family")
        or "unknown"
    )
    entry_price_source = str(
        components.get("entry_price_source")
        or item.get("entry_price_source")
        or _infer_entry_price_source(tracking_group=tracking_group, entry_rule=str(item.get("entry_rule") or ""))
    )
    source_rank = item.get("source_rank")
    return _strategy_id(
        [
            tracking_group,
            tracking_role,
            family,
            entry_price_source,
            "" if source_rank is None else str(source_rank),
        ]
    )


def _retirement_artifact_lookup(source: dict[str, Any] | None, strategy_id: str) -> dict[str, Any]:
    if not isinstance(source, dict) or not source:
        return {}
    value = source.get(strategy_id)
    if isinstance(value, dict):
        return dict(value)
    artifacts = source.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("strategy_id") == strategy_id:
                return dict(artifact)
    return {}


def _has_retirement_authority(artifact: dict[str, Any]) -> bool:
    return bool(
        artifact
        and artifact.get("status") in {"ready", "recorded"}
        and artifact.get("artifact_family") in {"strategy_retirement:v1", "shortpick_strategy_retirement"}
        and artifact.get("artifact_id")
        and artifact.get("decision_log_ref")
    )


def _horizon_summary(horizon_days: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    stock_returns = [float(item["stock_return"]) for item in observations]
    excess_returns = [float(item["excess_return"]) for item in observations if item.get("excess_return") is not None]
    signal_dates = sorted({str(item.get("signal_date") or "") for item in observations if item.get("signal_date")})
    symbol_negative_counts = Counter(
        str(item.get("symbol") or "")
        for item in observations
        if item.get("symbol") and float(item["stock_return"]) < 0
    )
    repeated_losses = [
        {"symbol": symbol, "negative_completed_count": count}
        for symbol, count in sorted(symbol_negative_counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ]
    positive_returns = [value for value in stock_returns if value > 0]
    positive_sum = sum(positive_returns)
    best_positive_share = max(positive_returns) / positive_sum if positive_sum > 0 else None
    return {
        "horizon_days": int(horizon_days) if horizon_days.isdigit() else horizon_days,
        "completed_sample_count": len(observations),
        "distinct_signal_date_count": len(signal_dates),
        "maturity_status": _maturity_status(len(observations), len(signal_dates)),
        "mean_stock_return": _round(mean(stock_returns)),
        "median_stock_return": _round(median(stock_returns)),
        "win_rate": _round(sum(1 for value in stock_returns if value > 0) / len(stock_returns)),
        "mean_excess_return": _round(mean(excess_returns)) if excess_returns else None,
        "median_excess_return": _round(median(excess_returns)) if excess_returns else None,
        "worst_stock_return": _round(min(stock_returns)),
        "best_stock_return": _round(max(stock_returns)),
        "negative_completed_count": sum(1 for value in stock_returns if value < 0),
        "max_additive_drawdown": _round(_max_additive_drawdown(observations)),
        "tail_dependency": {
            "best_positive_share": _round(best_positive_share),
            "tail_dependent": bool(best_positive_share is not None and best_positive_share > 0.5),
            "basis": "best_positive_stock_return_share_of_positive_stock_return_sum",
        },
        "same_symbol_loss_repeats": repeated_losses,
        "first_signal_date": signal_dates[0] if signal_dates else None,
        "latest_signal_date": signal_dates[-1] if signal_dates else None,
    }


def _maturity_status(completed_count: int, distinct_signal_date_count: int) -> str:
    if completed_count >= 30 and distinct_signal_date_count >= 10:
        return "mature_multi_row_review_sample"
    if completed_count >= 10:
        return "mature_one_stock_review_sample"
    return "insufficient_completed_sample"


def _max_additive_drawdown(observations: list[dict[str, Any]]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for item in sorted(observations, key=lambda row: str(row.get("signal_date") or "")):
        cumulative += float(item["stock_return"])
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
    return drawdown


def _evidence_lookup(source: dict[str, Any] | None, metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict) or not source:
        return {"status": "missing_artifact"}
    for key in (
        str(metadata.get("strategy_id") or ""),
        str(metadata.get("strategy_family") or ""),
        str(metadata.get("tracking_role") or ""),
        str(metadata.get("tracking_group") or ""),
    ):
        value = source.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {"status": "missing_artifact"}


def _extend_date_bounds(metadata: dict[str, Any], value: str) -> None:
    if not value:
        return
    first = metadata.get("first_signal_date")
    latest = metadata.get("latest_signal_date")
    if not first or value < first:
        metadata["first_signal_date"] = value
    if not latest or value > latest:
        metadata["latest_signal_date"] = value


def _infer_entry_price_source(*, tracking_group: str, entry_rule: str) -> str:
    if tracking_group == "frozen_strategy_v2":
        return "next_open"
    return "unknown"


def _strategy_id(parts: list[str]) -> str:
    return "__".join(_slug(part) for part in parts if part)


def _slug(value: str) -> str:
    safe = []
    for char in value.lower():
        if char.isalnum():
            safe.append(char)
        else:
            safe.append("_")
    return "_".join("".join(safe).strip("_").split("_")) or "unknown"


def _horizon_key(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value or "")
    return text if text else "unknown"


def _date_part(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return value.split("T", 1)[0].split(" ", 1)[0]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)
