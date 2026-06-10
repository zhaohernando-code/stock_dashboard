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
REPEATED_EXPOSURE_LIMIT_CONTROL_ID = "control_repeated_exposure_limit:v1"
SHORTPICK_HISTORICAL_BACKTEST_ENTRY_PRICE_SOURCES = {"next_close", "next_open", "same_close_proxy"}
REGISTERED_SHORTPICK_CONTROL_GROUP_IDS = frozenset(
    {
        SAME_SYMBOL_COOLDOWN_CONTROL_ID,
        DRAWDOWN_REVERSAL_FILTER_CONTROL_ID,
        REPEATED_EXPOSURE_LIMIT_CONTROL_ID,
    }
)
SHORTPICK_STRATEGY_STATUS_DISPLAY = {
    "active": {"label": "Active", "tone": "green", "primary_section": "primary"},
    "observe": {"label": "Observe", "tone": "gold", "primary_section": "primary"},
    "retire_candidate": {"label": "Retire candidate", "tone": "orange", "primary_section": "primary"},
    "retired": {"label": "Retired", "tone": "default", "primary_section": "archive"},
    "historical_only": {"label": "Historical only", "tone": "blue", "primary_section": "research"},
    "retrospective_only": {"label": "Retrospective only", "tone": "purple", "primary_section": "research"},
    "true_forward": {"label": "True forward", "tone": "green", "primary_section": "primary"},
}
SHORTPICK_EVIDENCE_BASIS_DISPLAY = {
    "historical_backtest": {"label": "Historical backtest", "tone": "blue"},
    "retrospective_forward_replay": {"label": "Retrospective replay", "tone": "purple"},
    "true_forward_tracking": {"label": "True forward tracking", "tone": "green"},
}
SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER = [
    "true_forward_tracking",
    "retrospective_forward_replay",
    "historical_backtest",
    "unknown",
]


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
            "status_display": _strategy_status_display(item.get("recommended_status")),
            "evidence_basis": item.get("evidence_basis"),
            "evidence_basis_display": _evidence_basis_display(item.get("evidence_basis")),
            "tracking_group": item.get("tracking_group"),
            "tracking_role": item.get("tracking_role"),
            "strategy_family": item.get("strategy_family"),
            "entry_price_source": item.get("entry_price_source"),
            "primary_horizon_days": item.get("primary_horizon_days"),
            "reasons": item.get("reasons") if isinstance(item.get("reasons"), list) else [],
            "blockers": item.get("blockers") if isinstance(item.get("blockers"), list) else [],
            "leakage_coverage_note": _leakage_coverage_note(item),
        }
        if projected["recommended_status"] == "retired":
            archive_items.append({**projected, "view_section": "archive"})
        else:
            primary_items.append({**projected, "view_section": "primary"})

    all_items = [*primary_items, *archive_items]

    return {
        "status": "ready",
        "decision_policy": "retired_status_hidden_from_primary_view_and_kept_in_archive",
        "primary_count": len(primary_items),
        "archive_count": len(archive_items),
        "primary_items": primary_items,
        "archive_items": archive_items,
        "evidence_basis_section_policy": "separate_historical_retrospective_and_true_forward_sections",
        "evidence_basis_sections": _evidence_basis_sections(all_items),
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
                "leakage_coverage_note": _dict(item.get("leakage_coverage_note")) or _leakage_coverage_note(pack),
                "retirement_artifact_ref": _retirement_artifact_lookup(retirement_artifacts, strategy_id),
                "archive_reason": "retired_strategy_removed_from_primary_view",
            }
        )

    return {
        "status": "ready",
        "decision_policy": "preserve_retired_strategy_statistics_and_evidence_refs",
        "archive_count": len(records),
        "records": records,
        "archive_summary_policy": "group_retired_strategies_by_evidence_basis_family_and_entry_source",
        "summary_rows": _archive_summary_rows(records),
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


def build_shortpick_repeated_exposure_limit_rule(
    *,
    control_group_id: str = REPEATED_EXPOSURE_LIMIT_CONTROL_ID,
    exposure_window_signal_days: int = 10,
    max_prior_signals_per_group: int = 1,
    group_fields: list[str] | None = None,
    rule_defined_at: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic repeated-exposure limit control rule."""

    if exposure_window_signal_days <= 0:
        raise ValueError("exposure_window_signal_days must be positive")
    if max_prior_signals_per_group < 0:
        raise ValueError("max_prior_signals_per_group must be non-negative")

    payload = {
        "control_group_id": control_group_id,
        "rule_version": "repeated-exposure-limit-v1",
        "exposure_basis": "prior_signal_rows_within_signal_day_window",
        "exposure_window_signal_days": int(exposure_window_signal_days),
        "max_prior_signals_per_group": int(max_prior_signals_per_group),
        "group_fields": list(group_fields or ["symbol"]),
        "rule_defined_at": rule_defined_at,
        "leakage_policy": "ignore_signal_rows_on_or_after_candidate_signal_date",
    }
    return {
        **payload,
        "rule_signature": _rule_signature(payload),
    }


def apply_shortpick_repeated_exposure_limit_control(
    candidate_rows: list[dict[str, Any]],
    exposure_signal_rows: list[dict[str, Any]],
    *,
    rule: dict[str, Any] | None = None,
    evidence_basis: str = "retrospective_forward_replay",
) -> dict[str, Any]:
    """Apply repeated-exposure limits using only prior signal rows."""

    rule = dict(rule or build_shortpick_repeated_exposure_limit_rule())
    group_fields = [str(value) for value in rule.get("group_fields") or ["symbol"]]
    exposure_rows = [_dict(value) for value in exposure_signal_rows if isinstance(value, dict)]
    signal_dates = sorted(
        {
            _date_part(item.get("signal_date") or item.get("run_date"))
            for item in [*candidate_rows, *exposure_rows]
            if isinstance(item, dict) and _date_part(item.get("signal_date") or item.get("run_date"))
        }
    )
    rows: list[dict[str, Any]] = []
    ignored_same_day_or_future_count = 0

    for item in [_dict(value) for value in candidate_rows if isinstance(value, dict)]:
        signal_date = _date_part(item.get("signal_date") or item.get("run_date"))
        group_key = _exposure_group_key(item, group_fields)
        blocker_rows: list[dict[str, Any]] = []

        for exposure in exposure_rows:
            if _exposure_group_key(exposure, group_fields) != group_key or not group_key:
                continue
            exposure_date = _date_part(exposure.get("signal_date") or exposure.get("run_date"))
            if not signal_date or not exposure_date or exposure_date >= signal_date:
                ignored_same_day_or_future_count += 1
                continue
            elapsed_signal_days = _elapsed_signal_days(signal_dates, exit_date=exposure_date, signal_date=signal_date)
            if 0 < elapsed_signal_days <= int(rule["exposure_window_signal_days"]):
                blocker_rows.append(
                    {
                        "candidate_id": exposure.get("candidate_id"),
                        "run_id": exposure.get("run_id"),
                        "signal_date": exposure_date,
                        "group_key": _exposure_group_key_label(group_key),
                        "elapsed_signal_days": elapsed_signal_days,
                    }
                )

        blocked = len(blocker_rows) > int(rule["max_prior_signals_per_group"])
        rows.append(
            {
                **item,
                "control_group_id": rule.get("control_group_id"),
                "rule_signature": rule.get("rule_signature"),
                "evidence_basis": evidence_basis,
                "exposure_action": "blocked" if blocked else "allowed",
                "exposure_blocked": blocked,
                "exposure_group_key": _exposure_group_key_label(group_key),
                "exposure_prior_signal_count": len(blocker_rows),
                "exposure_blocker_rows": blocker_rows if blocked else [],
                "leakage_audit_status": "passed",
                "leakage_audit_reasons": ["used_only_prior_signal_rows"],
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
            "used_only_prior_signal_rows",
            "ignored_same_day_or_future_signal_rows",
        ],
        "input_candidate_count": len(candidate_rows),
        "blocked_count": sum(1 for row in rows if row["exposure_blocked"]),
        "allowed_count": sum(1 for row in rows if not row["exposure_blocked"]),
        "ignored_same_day_or_future_signal_count": ignored_same_day_or_future_count,
        "rows": rows,
    }


def build_shortpick_historical_backtest_generation_requests(
    control_rules: list[dict[str, Any]],
    *,
    start_date: str,
    end_date: str,
    entry_price_sources: list[str] | None = None,
    horizon_days: int = 10,
    cost_bps: float = 20.0,
    benchmark_mode: str = "universe_equal_weight",
    account_profile: str = "new_retail_cash_account",
    pool_limit: int = 40,
    rank_limit: int = 6,
    min_signal_symbol_count: int = 45,
    output_dir: str = "output/shortpick-governance-backtests",
) -> dict[str, Any]:
    """Build deterministic historical-backtest generation requests without executing them."""

    start = _date_part(start_date)
    end = _date_part(end_date)
    if not start or not end or start > end:
        raise ValueError("start_date must be <= end_date")
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    if cost_bps < 0:
        raise ValueError("cost_bps must be non-negative")
    if min_signal_symbol_count <= 0:
        raise ValueError("min_signal_symbol_count must be positive")

    entry_sources = list(entry_price_sources or ["next_close"])
    unsupported = sorted(set(entry_sources) - SHORTPICK_HISTORICAL_BACKTEST_ENTRY_PRICE_SOURCES)
    if unsupported:
        raise ValueError(f"unsupported entry_price_sources: {unsupported}")

    requests: list[dict[str, Any]] = []
    for rule in [_dict(value) for value in control_rules if isinstance(value, dict)]:
        control_group_id = str(rule.get("control_group_id") or "")
        rule_signature = str(rule.get("rule_signature") or "")
        if not control_group_id or not rule_signature:
            continue
        for entry_source in entry_sources:
            request_payload = {
                "control_group_id": control_group_id,
                "rule_signature": rule_signature,
                "entry_price_source": entry_source,
                "start_date": start,
                "end_date": end,
                "horizon_days": int(horizon_days),
                "cost_bps": round(float(cost_bps), 6),
                "benchmark_mode": benchmark_mode,
                "account_profile": account_profile,
                "pool_limit": int(pool_limit),
                "rank_limit": int(rank_limit),
                "min_signal_symbol_count": int(min_signal_symbol_count),
            }
            request_id = _historical_backtest_request_id(request_payload)
            output_path = (
                f"{output_dir}/"
                f"{_slug(control_group_id)}__{rule_signature.replace(':', '_')[:24]}__{entry_source}.json"
            )
            requests.append(
                {
                    **request_payload,
                    "request_id": request_id,
                    "evidence_basis": "historical_backtest",
                    "source_command": "shortpick-portfolio-backtest",
                    "argv": _historical_backtest_argv(request_payload, output_path=output_path),
                    "output_path": output_path,
                    "rule": rule,
                    "leakage_audit_status": "not_run",
                    "leakage_audit_reasons": [],
                    "true_forward_tracking_eligible": False,
                    "paper_tracking_write_policy": "forbidden",
                }
            )

    return {
        "status": "ready",
        "evidence_basis": "historical_backtest",
        "source_command": "shortpick-portfolio-backtest",
        "request_count": len(requests),
        "requests": requests,
        "execution_policy": "request_plan_only_no_backtest_execution_no_data_write",
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
    }


def build_shortpick_retrospective_forward_replay_requests(
    control_rules: list[dict[str, Any]],
    paper_tracking: dict[str, Any],
    *,
    generated_at: str | None = None,
    replay_source: str = "shortpick_paper_tracking_ledger",
) -> dict[str, Any]:
    """Build retrospective forward replay requests without executing them."""

    signal_dates = sorted(
        {
            _date_part(item.get("signal_date") or item.get("run_date"))
            for item in paper_tracking.get("items") or []
            if isinstance(item, dict) and _date_part(item.get("signal_date") or item.get("run_date"))
        }
    )
    requests: list[dict[str, Any]] = []
    blocked_rules: list[dict[str, Any]] = []

    for rule in [_dict(value) for value in control_rules if isinstance(value, dict)]:
        control_group_id = str(rule.get("control_group_id") or "")
        rule_signature = str(rule.get("rule_signature") or "")
        rule_defined_at = _date_part(rule.get("rule_defined_at"))
        if not control_group_id or not rule_signature:
            blocked_rules.append(
                {
                    "control_group_id": control_group_id,
                    "rule_signature": rule_signature,
                    "blocker": "missing_control_group_id_or_rule_signature",
                }
            )
            continue
        if not rule_defined_at:
            blocked_rules.append(
                {
                    "control_group_id": control_group_id,
                    "rule_signature": rule_signature,
                    "blocker": "missing_rule_defined_at",
                }
            )
            continue

        replay_dates = [value for value in signal_dates if value < rule_defined_at]
        if not replay_dates:
            blocked_rules.append(
                {
                    "control_group_id": control_group_id,
                    "rule_signature": rule_signature,
                    "rule_defined_at": rule_defined_at,
                    "blocker": "no_paper_tracking_signal_dates_before_rule_defined_at",
                }
            )
            continue

        request_payload = {
            "control_group_id": control_group_id,
            "rule_signature": rule_signature,
            "rule_defined_at": rule_defined_at,
            "replay_start_date": replay_dates[0],
            "replay_end_date": replay_dates[-1],
            "source_signal_count": len(replay_dates),
            "replay_source": replay_source,
        }
        requests.append(
            {
                **request_payload,
                "request_id": _retrospective_forward_replay_request_id(request_payload),
                "evidence_basis": "retrospective_forward_replay",
                "retrospective": True,
                "source_feature_cutoff_policy": "signal_date_available_inputs_only",
                "generated_at": generated_at,
                "rule": rule,
                "leakage_audit_status": "not_run",
                "leakage_audit_reasons": [],
                "true_forward_tracking_eligible": False,
                "paper_tracking_write_policy": "forbidden",
            }
        )

    return {
        "status": "ready" if requests else "blocked",
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "replay_source": replay_source,
        "paper_tracking_signal_date_count": len(signal_dates),
        "paper_tracking_observed_start_date": signal_dates[0] if signal_dates else None,
        "paper_tracking_observed_end_date": signal_dates[-1] if signal_dates else None,
        "request_count": len(requests),
        "blocked_rule_count": len(blocked_rules),
        "requests": requests,
        "blocked_rules": blocked_rules,
        "execution_policy": "request_plan_only_no_replay_execution_no_data_write",
        "paper_tracking_write_policy": "forbidden",
        "true_forward_tracking_eligible": False,
    }


def build_shortpick_true_forward_tracking_activation_plan(
    control_rules: list[dict[str, Any]],
    *,
    tracking_started_at: str,
    generated_at: str | None = None,
    registered_control_group_ids: set[str] | frozenset[str] | None = None,
    artifact_family_id: str = "shortpick_paper_tracking_ledger",
) -> dict[str, Any]:
    """Build a true-forward activation plan without writing tracking rows."""

    tracking_start_request_date = _date_part(tracking_started_at)
    if not tracking_start_request_date:
        raise ValueError("tracking_started_at must include a date")
    if not artifact_family_id:
        raise ValueError("artifact_family_id must be non-empty")

    registered_ids = set(registered_control_group_ids or REGISTERED_SHORTPICK_CONTROL_GROUP_IDS)
    activations: list[dict[str, Any]] = []
    blocked_rules: list[dict[str, Any]] = []

    for rule in [_dict(value) for value in control_rules if isinstance(value, dict)]:
        control_group_id = str(rule.get("control_group_id") or "")
        rule_signature = str(rule.get("rule_signature") or "")
        rule_defined_at = _date_part(rule.get("rule_defined_at"))
        base = {
            "control_group_id": control_group_id,
            "rule_signature": rule_signature,
        }
        if not control_group_id or not rule_signature:
            blocked_rules.append({**base, "blocker": "missing_control_group_id_or_rule_signature"})
            continue
        if control_group_id not in registered_ids:
            blocked_rules.append({**base, "blocker": "unregistered_control_group_id"})
            continue
        if not rule_defined_at:
            blocked_rules.append({**base, "blocker": "missing_rule_defined_at"})
            continue

        tracking_start_date = max(tracking_start_request_date, rule_defined_at)
        payload = {
            "control_group_id": control_group_id,
            "rule_signature": rule_signature,
            "rule_defined_at": rule_defined_at,
            "tracking_start_date": tracking_start_date,
            "artifact_family_id": artifact_family_id,
        }
        activations.append(
            {
                **payload,
                "activation_id": _true_forward_tracking_activation_id(payload),
                "tracking_start_requested_at": tracking_start_request_date,
                "generated_at": generated_at,
                "evidence_basis": "true_forward_tracking",
                "retrospective": False,
                "retroactive_backfill_allowed": False,
                "true_forward_tracking_eligible": True,
                "source_feature_cutoff_policy": "signal_date_available_inputs_only",
                "paper_tracking_write_policy": "not_written_by_plan_runtime_wiring_required",
                "forbidden_signal_date_policy": "do_not_write_rows_before_tracking_start_date",
                "rule": rule,
            }
        )

    return {
        "status": "ready" if activations else "blocked",
        "evidence_basis": "true_forward_tracking",
        "retrospective": False,
        "artifact_family_id": artifact_family_id,
        "registered_control_group_ids": sorted(registered_ids),
        "tracking_start_requested_at": tracking_start_request_date,
        "activation_count": len(activations),
        "blocked_rule_count": len(blocked_rules),
        "activations": activations,
        "blocked_rules": blocked_rules,
        "execution_policy": "activation_plan_only_no_tracking_execution_no_data_write",
        "paper_tracking_write_policy": "not_written_by_plan_runtime_wiring_required",
        "retroactive_backfill_allowed": False,
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


def _exposure_group_key(row: dict[str, Any], group_fields: list[str]) -> tuple[str, ...]:
    values = tuple(str(row.get(field) or "") for field in group_fields)
    return values if all(values) else ()


def _exposure_group_key_label(group_key: tuple[str, ...]) -> str:
    return "|".join(group_key)


def _historical_backtest_request_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "shortpick-historical-backtest-request:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _historical_backtest_argv(payload: dict[str, Any], *, output_path: str) -> list[str]:
    return [
        "shortpick-portfolio-backtest",
        "--start-date",
        str(payload["start_date"]),
        "--end-date",
        str(payload["end_date"]),
        "--pool-limit",
        str(payload["pool_limit"]),
        "--rank-limit",
        str(payload["rank_limit"]),
        "--horizon-days",
        str(payload["horizon_days"]),
        "--cost-bps",
        str(payload["cost_bps"]),
        "--min-signal-symbol-count",
        str(payload["min_signal_symbol_count"]),
        "--benchmark-mode",
        str(payload["benchmark_mode"]),
        "--account-profile",
        str(payload["account_profile"]),
        "--entry-price-source",
        str(payload["entry_price_source"]),
        "--output",
        output_path,
    ]


def _retrospective_forward_replay_request_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "shortpick-retrospective-forward-replay-request:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _true_forward_tracking_activation_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "shortpick-true-forward-activation:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _strategy_status_display(value: Any) -> dict[str, str]:
    key = str(value or "unknown")
    display = SHORTPICK_STRATEGY_STATUS_DISPLAY.get(key, {"label": "Unknown", "tone": "default", "primary_section": "primary"})
    return {"key": key, **display}


def _evidence_basis_display(value: Any) -> dict[str, str]:
    key = str(value or "unknown")
    display = SHORTPICK_EVIDENCE_BASIS_DISPLAY.get(key, {"label": "Unknown evidence", "tone": "default"})
    return {"key": key, **display}


def _leakage_coverage_note(item: dict[str, Any]) -> dict[str, Any]:
    evidence_basis = str(item.get("evidence_basis") or "unknown")
    leakage_status = str(item.get("leakage_audit_status") or "not_run")
    leakage_reasons = item.get("leakage_audit_reasons")
    source_feature_cutoff_policy = item.get("source_feature_cutoff_policy")
    if not source_feature_cutoff_policy and evidence_basis == "retrospective_forward_replay":
        source_feature_cutoff_policy = "signal_date_available_inputs_only"
    feature_cutoff_at = (
        item.get("feature_cutoff_at")
        or item.get("feature_cutoff_date")
        or item.get("source_feature_cutoff_at")
        or item.get("source_feature_cutoff_date")
    )
    feature_coverage_status = str(item.get("feature_coverage_status") or item.get("coverage_status") or "unknown")

    return {
        "evidence_basis": evidence_basis,
        "leakage_audit_status": leakage_status,
        "leakage_audit_reasons": leakage_reasons if isinstance(leakage_reasons, list) else [],
        "source_feature_cutoff_policy": source_feature_cutoff_policy,
        "feature_cutoff_at": feature_cutoff_at,
        "feature_coverage_status": feature_coverage_status,
        "display_required": (
            evidence_basis in {"historical_backtest", "retrospective_forward_replay"}
            or leakage_status != "not_run"
            or feature_coverage_status != "unknown"
        ),
    }


def _evidence_basis_sections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        basis = str(item.get("evidence_basis") or "unknown")
        grouped[basis].append(item)

    def sort_key(value: str) -> tuple[int, str]:
        if value in SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER:
            return (SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER.index(value), value)
        return (len(SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER), value)

    sections: list[dict[str, Any]] = []
    for basis in sorted(grouped, key=sort_key):
        section_items = grouped[basis]
        sections.append(
            {
                "evidence_basis": basis,
                "evidence_basis_display": _evidence_basis_display(basis),
                "item_count": len(section_items),
                "primary_count": sum(1 for item in section_items if item.get("view_section") == "primary"),
                "archive_count": sum(1 for item in section_items if item.get("view_section") == "archive"),
                "items": section_items,
            }
        )
    return sections


def _archive_summary_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        evidence_basis = str(record.get("evidence_basis") or "unknown")
        strategy_family = str(record.get("strategy_family") or "unknown")
        entry_price_source = str(record.get("entry_price_source") or "unknown")
        key = (evidence_basis, strategy_family, entry_price_source)
        row = grouped.setdefault(
            key,
            {
                "summary_key": "__".join(key),
                "evidence_basis": evidence_basis,
                "evidence_basis_display": _evidence_basis_display(evidence_basis),
                "strategy_family": strategy_family,
                "entry_price_source": entry_price_source,
                "archived_strategy_count": 0,
                "signal_count": 0,
                "completed_observation_count": 0,
                "first_signal_date": None,
                "latest_signal_date": None,
                "retirement_artifact_count": 0,
            },
        )
        row["archived_strategy_count"] = int(row["archived_strategy_count"]) + 1
        row["signal_count"] = int(row["signal_count"]) + int(record.get("signal_count") or 0)
        row["completed_observation_count"] = int(row["completed_observation_count"]) + int(record.get("completed_observation_count") or 0)
        if _dict(record.get("retirement_artifact_ref")).get("artifact_id"):
            row["retirement_artifact_count"] = int(row["retirement_artifact_count"]) + 1
        _extend_date_bounds(row, str(record.get("first_signal_date") or ""))
        _extend_date_bounds(row, str(record.get("latest_signal_date") or ""))

    return [
        grouped[key]
        for key in sorted(
            grouped,
            key=lambda item: (
                _evidence_basis_section_sort_key(item[0]),
                item[1],
                item[2],
            ),
        )
    ]


def _evidence_basis_section_sort_key(value: str) -> tuple[int, str]:
    if value in SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER:
        return (SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER.index(value), value)
    return (len(SHORTPICK_EVIDENCE_BASIS_SECTION_ORDER), value)


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
