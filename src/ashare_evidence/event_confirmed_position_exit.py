from __future__ import annotations

import bisect
import copy
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
)
from ashare_evidence.external_context_macro_research import load_macro_research_snapshot, macro_state_by_decision_date
from ashare_evidence.external_context_sector_market_research import (
    SW_L1_BY_SUBINDUSTRY,
    load_sector_research_snapshot,
    sector_state_by_decision_date,
)
from ashare_evidence.global_sector_state_account_ablation import (
    DEFAULT_FINAL_START,
    DEFAULT_TUNING_END,
    DEFAULT_VALIDATION_END,
    _buy_order_delta,
    _candidate_run,
    _group_by_date,
    _monthly_delta_summary,
    _non_degrade,
    _segment_metrics,
    _standout,
)
from ashare_evidence.official_facts_static_ablation import _symbol_from_sec_code
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

SCHEMA_VERSION = "event_confirmed_position_exit_account_ablation.v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
EVENT_CATEGORIES = (
    "capital_and_ownership",
    "financial_performance_and_distribution",
    "risk_enforcement_and_correction",
    "financing_and_mna",
    "material_operations",
    "management_change",
)


@dataclass(frozen=True)
class OfficialEvent:
    symbol: str
    available_from: datetime
    category: str
    normalized_event_id: str
    revision_id: str


def _parse_aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone-aware datetime required: {value}")
    return parsed


def load_curated_official_events(
    *, external_root: Path, curation_path: Path
) -> tuple[dict[str, list[OfficialEvent]], dict[str, Any]]:
    curation = json.loads(curation_path.read_text(encoding="utf-8"))
    excluded = {
        (str(row.get("normalized_event_id") or ""), str(row.get("revision_id") or ""))
        for row in curation.get("excluded_event_versions") or []
    }
    events: dict[str, list[OfficialEvent]] = defaultdict(list)
    category_counts: dict[str, int] = defaultdict(int)
    scanned = 0
    excluded_count = 0
    for path in sorted((external_root / "pit" / "records").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        feature = record.get("feature_value") or {}
        if "sec_code" not in feature:
            continue
        scanned += 1
        event_key = (
            str(record.get("normalized_event_id") or ""),
            str(record.get("knowledge_version") or ""),
        )
        if event_key in excluded:
            excluded_count += 1
            continue
        symbol = _symbol_from_sec_code(str(feature.get("sec_code") or ""))
        available_from = record.get("available_from")
        category = str(feature.get("materiality_category") or "")
        if symbol is None or not available_from or category not in EVENT_CATEGORIES:
            continue
        event = OfficialEvent(
            symbol=symbol,
            available_from=_parse_aware(str(available_from)),
            category=category,
            normalized_event_id=event_key[0],
            revision_id=event_key[1],
        )
        events[symbol].append(event)
        category_counts[category] += 1
    for rows in events.values():
        rows.sort(key=lambda row: row.available_from)
    return dict(events), {
        "pit_records_scanned": scanned,
        "curation_excluded_records": excluded_count,
        "retained_event_count": sum(len(rows) for rows in events.values()),
        "retained_symbol_count": len(events),
        "category_counts": dict(sorted(category_counts.items())),
        "curation_policy_version": curation.get("active_relevance_policy_version"),
        "curation_exclusion_digest": curation.get("excluded_event_versions_sha256"),
    }


def load_merged_curated_official_events(
    *, sources: list[tuple[Path, Path]]
) -> tuple[dict[str, list[OfficialEvent]], dict[str, Any]]:
    if not sources:
        raise ValueError("at least one curated official-event source is required")
    merged: dict[str, list[OfficialEvent]] = defaultdict(list)
    seen: dict[tuple[str, str], OfficialEvent] = {}
    source_audits: list[dict[str, Any]] = []
    duplicate_event_versions = 0
    category_counts: dict[str, int] = defaultdict(int)
    for external_root, curation_path in sources:
        events_by_symbol, audit = load_curated_official_events(
            external_root=external_root,
            curation_path=curation_path,
        )
        source_audits.append(audit)
        for symbol, events in events_by_symbol.items():
            for event in events:
                key = (event.normalized_event_id, event.revision_id)
                prior = seen.get(key)
                if prior is not None:
                    if prior != event:
                        raise ValueError(f"conflicting official-event version across sources: {key}")
                    duplicate_event_versions += 1
                    continue
                seen[key] = event
                merged[symbol].append(event)
                category_counts[event.category] += 1
    for rows in merged.values():
        rows.sort(key=lambda row: row.available_from)
    return dict(merged), {
        "source_count": len(sources),
        "source_audits": source_audits,
        "pit_records_scanned": sum(int(row["pit_records_scanned"]) for row in source_audits),
        "curation_excluded_records": sum(
            int(row["curation_excluded_records"]) for row in source_audits
        ),
        "duplicate_event_versions": duplicate_event_versions,
        "retained_event_count": len(seen),
        "retained_symbol_count": len(merged),
        "category_counts": dict(sorted(category_counts.items())),
        "curation_policy_versions": [row.get("curation_policy_version") for row in source_audits],
        "curation_exclusion_digests": [
            row.get("curation_exclusion_digest") for row in source_audits
        ],
    }


def _bar_index_by_day(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row["day"]): index for index, row in enumerate(rows)}


def _position_key(*, signal_day: str, entry_day: str, symbol: str, rank: int) -> str:
    return f"{signal_day}|{entry_day}|{symbol}|{rank}"


def _matched_events(
    events: list[OfficialEvent], *, decision_day: date, lookback_days: int
) -> list[OfficialEvent]:
    cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
    available = [row.available_from for row in events]
    right = bisect.bisect_right(available, cutoff)
    left = bisect.bisect_left(available, cutoff - timedelta(days=lookback_days), hi=right)
    return events[left:right]


def _event_features(
    *,
    events: list[OfficialEvent],
    decision_day: date,
    lookback_days: int,
    bars: list[dict[str, Any]],
    current_index: int,
) -> tuple[list[float], dict[str, Any]]:
    matched = _matched_events(events, decision_day=decision_day, lookback_days=lookback_days)
    category_counts = {category: 0 for category in EVENT_CATEGORIES}
    for event in matched:
        category_counts[event.category] += 1
    latest = max(matched, key=lambda row: row.available_from, default=None)
    reaction = 0.0
    latest_age_days = float(lookback_days + 1)
    if latest is not None:
        latest_age_days = max(0.0, (decision_day - latest.available_from.date()).days)
        first_usable_index = next(
            (index for index, row in enumerate(bars) if date.fromisoformat(str(row["day"])) > latest.available_from.date()),
            None,
        )
        if first_usable_index is not None and first_usable_index <= current_index:
            start = float(bars[first_usable_index]["close"])
            reaction = float(bars[current_index]["close"]) / start - 1.0 if start else 0.0
    features = [
        float(len(matched)),
        float(latest_age_days),
        reaction,
        *[float(category_counts[category]) for category in EVENT_CATEGORIES],
    ]
    return features, {
        "event_count": len(matched),
        "latest_event_age_days": latest_age_days,
        "post_event_price_confirmation": reaction,
        "category_counts": category_counts,
    }


def _macro_value(state: dict[str, Any], series_id: str, field: str) -> float:
    raw = (state.get(series_id) or {}).get(field)
    return float(raw) if raw is not None else 0.0


def _position_features(
    *,
    buy: dict[str, Any],
    bars: list[dict[str, Any]],
    entry_index: int,
    current_index: int,
    market_state: dict[str, Any],
    sector_state: dict[str, Any],
    macro_state: dict[str, Any],
    event_features: list[float],
) -> tuple[list[float], list[float], dict[str, float]]:
    entry_price = float(bars[entry_index]["close"])
    prices = [float(row["close"]) for row in bars[entry_index : current_index + 1]]
    current_price = prices[-1]
    peak = max(prices)
    position_return = current_price / entry_price - 1.0
    peak_return = peak / entry_price - 1.0
    drawdown = current_price / peak - 1.0

    def trailing_return(period: int) -> float:
        if current_index < period:
            return 0.0
        prior = float(bars[current_index - period]["close"])
        return current_price / prior - 1.0 if prior else 0.0

    entry = buy.get("entry_features") or {}
    core = [
        position_return,
        peak_return,
        drawdown,
        float(current_index - entry_index),
        float(buy.get("rank") or 0),
        trailing_return(1),
        trailing_return(3),
        trailing_return(5),
        float(entry.get("score") or 0.0),
        float(entry.get("return_5d_percentile") or 0.0),
        float(entry.get("return_20d_percentile") or 0.0),
        float(entry.get("turnover_rate_percentile") or 0.0),
        float(entry.get("amount_10d_vs_20d_percentile") or 0.0),
        float(entry.get("distance_from_20d_high") or 0.0),
        float(entry.get("industry_return_20d_excess") or 0.0),
        float(entry.get("benchmark_return_20d") or 0.0),
    ]
    sector_name = SW_L1_BY_SUBINDUSTRY.get(str(entry.get("industry_name") or ""), "")
    sector = (sector_state.get("by_sector_name") or {}).get(sector_name) or {}
    external = [
        float(market_state.get("global_mean_return_5d") or 0.0),
        float(market_state.get("global_mean_return_20d") or 0.0),
        float(market_state.get("global_breadth_5d") or 0.0),
        float(market_state.get("global_breadth_20d") or 0.0),
        float(market_state.get("tech_relative_5d") or 0.0),
        float(market_state.get("tech_relative_20d") or 0.0),
        float(sector.get("relative_5d") or 0.0),
        float(sector.get("relative_20d") or 0.0),
        float(sector.get("drawdown_20d") or 0.0),
        _macro_value(macro_state, "VIXCLS", "value"),
        _macro_value(macro_state, "VIXCLS", "change_5d"),
        _macro_value(macro_state, "USDCNH_MID", "return_5d"),
        _macro_value(macro_state, "UST_10Y", "change_5d"),
        _macro_value(macro_state, "UST_10Y_MINUS_2Y", "value"),
        *event_features,
    ]
    return core, [*core, *external], {
        "position_return": position_return,
        "peak_return": peak_return,
        "drawdown_from_peak": drawdown,
    }


def build_position_day_observations(
    *,
    snapshot: dict[str, Any],
    events_by_symbol: dict[str, list[OfficialEvent]],
    market_states: dict[str, dict[str, Any]],
    sector_states: dict[str, dict[str, Any]],
    macro_states: dict[str, dict[str, Any]],
    minimum_holding_trade_days: int,
    event_lookback_days: int,
    signal_end: date,
) -> list[dict[str, Any]]:
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    baseline = snapshot["baseline_output"]
    sells_by_key: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in baseline["order_ledger"]:
        if row.get("action") == "sell":
            sells_by_key[(str(row["signal_day"]), str(row["symbol"]), int(row["rank"]))].append(row)
    observations: list[dict[str, Any]] = []
    for buy in baseline["order_ledger"]:
        if buy.get("action") != "buy":
            continue
        signal_day = str(buy["signal_day"])
        symbol = str(buy["symbol"])
        rank = int(buy["rank"])
        matching_sells = sells_by_key.get((signal_day, symbol, rank)) or []
        if len(matching_sells) != 1:
            continue
        sell = matching_sells[0]
        sell_day = date.fromisoformat(str(sell["trade_day"]))
        if sell_day > signal_end:
            continue
        bars = bars_by_symbol.get(symbol) or []
        index_by_day = _bar_index_by_day(bars)
        entry_day = str(buy["trade_day"])
        if entry_day not in index_by_day or sell_day.isoformat() not in index_by_day:
            continue
        entry_index = index_by_day[entry_day]
        sell_index = index_by_day[sell_day.isoformat()]
        if sell_index - entry_index <= minimum_holding_trade_days + 1:
            continue
        frozen_exit_price = float(bars[sell_index]["close"])
        entry_features = next(
            (
                row
                for row in snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0][
                    "selected_top_k_picks_by_date"
                ]
                if str(row.get("as_of_date")) == signal_day
                and str(row.get("symbol")) == symbol
                and int(float(row.get("rank") or 0)) == rank
            ),
            {},
        )
        enriched_buy = {**buy, "entry_features": entry_features}
        for current_index in range(entry_index + minimum_holding_trade_days, sell_index - 1):
            decision_day = date.fromisoformat(str(bars[current_index]["day"]))
            day_key = decision_day.isoformat()
            if day_key not in market_states or day_key not in sector_states or day_key not in macro_states:
                continue
            event_vector, event_audit = _event_features(
                events=events_by_symbol.get(symbol) or [],
                decision_day=decision_day,
                lookback_days=event_lookback_days,
                bars=bars,
                current_index=current_index,
            )
            core, full, path = _position_features(
                buy=enriched_buy,
                bars=bars,
                entry_index=entry_index,
                current_index=current_index,
                market_state=market_states[day_key],
                sector_state=sector_states[day_key],
                macro_state=macro_states[day_key],
                event_features=event_vector,
            )
            next_index = current_index + 1
            next_price = float(bars[next_index]["close"])
            entry_price = float(bars[entry_index]["close"])
            observations.append(
                {
                    "position_key": _position_key(
                        signal_day=signal_day, entry_day=entry_day, symbol=symbol, rank=rank
                    ),
                    "signal_day": signal_day,
                    "entry_day": entry_day,
                    "symbol": symbol,
                    "rank": rank,
                    "decision_day": day_key,
                    "effective_exit_day": str(bars[next_index]["day"]),
                    "label_available_day": sell_day.isoformat(),
                    "early_exit_advantage": (next_price - frozen_exit_price) / entry_price if entry_price else 0.0,
                    "core_features": core,
                    "full_features": full,
                    **path,
                    **event_audit,
                }
            )
    return sorted(observations, key=lambda row: (row["decision_day"], row["position_key"]))


def _ridge_batch(
    train_x: list[list[float]], train_y: list[float], test_x: list[list[float]], *, alpha: float
) -> list[float]:
    if not test_x:
        return []
    matrix = np.asarray(train_x, dtype=float)
    target = np.asarray(train_y, dtype=float)
    test = np.asarray(test_x, dtype=float)
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales <= 1e-12] = 1.0
    standardized = (matrix - means) / scales
    standardized_test = (test - means) / scales
    design = np.column_stack([np.ones(len(standardized)), standardized])
    test_design = np.column_stack([np.ones(len(standardized_test)), standardized_test])
    penalty = np.eye(design.shape[1], dtype=float) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    return [float(value) for value in test_design @ beta]


def expanding_position_predictions(
    observations: list[dict[str, Any]],
    *,
    minimum_training_labels: int,
    minimum_prior_predictions: int,
    l2_penalty: float,
) -> tuple[dict[tuple[str, str], dict[str, float] | None], dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_day[str(row["decision_day"])].append(row)
    predictions: dict[tuple[str, str], dict[str, float] | None] = {}
    prior_core: list[float] = []
    prior_full: list[float] = []
    fit_counts: dict[str, int] = {}
    for day in sorted(by_day):
        training = [row for row in observations if str(row["label_available_day"]) < day]
        fit_counts[day] = len(training)
        rows = by_day[day]
        if len(training) < minimum_training_labels:
            for row in rows:
                predictions[(str(row["position_key"]), day)] = None
            continue
        target = [float(row["early_exit_advantage"]) for row in training]
        core = _ridge_batch(
            [row["core_features"] for row in training],
            target,
            [row["core_features"] for row in rows],
            alpha=l2_penalty,
        )
        full = _ridge_batch(
            [row["full_features"] for row in training],
            target,
            [row["full_features"] for row in rows],
            alpha=l2_penalty,
        )
        for row, core_value, full_value in zip(rows, core, full, strict=True):
            key = (str(row["position_key"]), day)
            if len(prior_full) < minimum_prior_predictions:
                predictions[key] = None
                continue
            predictions[key] = {
                "core_prediction": core_value,
                "full_prediction": full_value,
                "external_increment": full_value - core_value,
                "core_percentile": (
                    sum(value <= core_value for value in prior_core) / len(prior_core) if prior_core else 0.5
                ),
                "full_percentile": (
                    sum(value <= full_value for value in prior_full) / len(prior_full) if prior_full else 0.5
                ),
            }
        prior_core.extend(core)
        prior_full.extend(full)
    ready = [row for row in predictions.values() if row is not None]
    return predictions, {
        "observation_count": len(observations),
        "ready_prediction_count": len(ready),
        "warmup_prediction_count": len(predictions) - len(ready),
        "last_fit_count": fit_counts[max(fit_counts)] if fit_counts else 0,
        "future_label_violations": 0,
    }


def _signals_for_variant(
    *,
    observations: list[dict[str, Any]],
    predictions: dict[tuple[str, str], dict[str, float] | None],
    variant: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    signals: dict[str, dict[str, str]] = defaultdict(dict)
    triggers: list[dict[str, Any]] = []
    exited_positions: set[str] = set()
    for row in observations:
        position_key = str(row["position_key"])
        if position_key in exited_positions or int(row["event_count"]) <= 0:
            continue
        prediction = predictions.get((position_key, str(row["decision_day"])))
        if prediction is None:
            continue
        control = bool(variant.get("control_only"))
        predicted = float(prediction["core_prediction"] if control else prediction["full_prediction"])
        percentile = float(prediction["core_percentile"] if control else prediction["full_percentile"])
        if not control and float(prediction["external_increment"]) <= 0:
            continue
        if predicted < float(variant["minimum_predicted_advantage"]):
            continue
        if percentile < float(variant["prediction_percentile_min"]):
            continue
        if float(row["position_return"]) > float(variant["maximum_position_return"]):
            continue
        trade_day = str(row["effective_exit_day"])
        signals[trade_day][position_key] = "pit_external_event_confirmed_risk_exit"
        exited_positions.add(position_key)
        triggers.append(
            {
                "position_key": position_key,
                "decision_day": row["decision_day"],
                "effective_exit_day": trade_day,
                "symbol": row["symbol"],
                "rank": row["rank"],
                "event_count": row["event_count"],
                "post_event_price_confirmation": row["post_event_price_confirmation"],
                "position_return": row["position_return"],
                **prediction,
            }
        )
    return dict(signals), triggers


def run_event_confirmed_position_exit_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    macro_market_snapshot_path: Path,
    external_root: Path,
    curation_path: Path,
    design_path: Path,
    signal_end: date,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round30_outcome_evaluation":
        raise ValueError("event-confirmed exit design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    global_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    macro_snapshot = load_macro_research_snapshot(macro_market_snapshot_path)
    actual_digests = {
        "global_market_digest": global_snapshot["content_digest"],
        "sector_market_digest": sector_snapshot["content_digest"],
        "macro_market_digest": macro_snapshot["content_digest"],
        "cninfo_curation_file_sha256": hashlib.sha256(curation_path.read_bytes()).hexdigest(),
    }
    expected = design["data_contract"]
    mismatches = {
        key: {"expected": expected.get(key), "actual": value}
        for key, value in actual_digests.items()
        if expected.get(key) != value
    }
    if mismatches:
        raise ValueError(f"round30 data digest mismatch: {mismatches}")
    events_by_symbol, event_audit = load_curated_official_events(
        external_root=external_root, curation_path=curation_path
    )
    if event_audit["curation_exclusion_digest"] != expected["cninfo_curation_exclusion_digest"]:
        raise ValueError("round30 CNINFO exclusion digest mismatch")
    bars_by_symbol = snapshot["inputs"]["market_bars_by_symbol"]
    baseline_buy_days = [
        date.fromisoformat(str(row["trade_day"]))
        for row in snapshot["baseline_output"]["order_ledger"]
        if row.get("action") == "buy"
    ]
    if not baseline_buy_days:
        raise ValueError("round30 requires at least one frozen baseline buy")
    first_position_day = min(baseline_buy_days)
    all_days = sorted(
        {
            date.fromisoformat(str(row["day"]))
            for rows in bars_by_symbol.values()
            for row in rows
            if first_position_day <= date.fromisoformat(str(row["day"])) <= signal_end
        }
    )
    market_states = market_state_by_decision_date(global_snapshot["records"], decision_dates=all_days)
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"], decision_dates=all_days
    )
    macro_states = macro_state_by_decision_date(macro_snapshot["records"], decision_dates=all_days)
    boundary = design["boundary"]
    observations = build_position_day_observations(
        snapshot=snapshot,
        events_by_symbol=events_by_symbol,
        market_states=market_states,
        sector_states=sector_states,
        macro_states=macro_states,
        minimum_holding_trade_days=int(boundary["minimum_holding_trade_days"]),
        event_lookback_days=int(boundary["event_lookback_calendar_days"]),
        signal_end=signal_end,
    )
    model = design["model"]
    predictions, prediction_audit = expanding_position_predictions(
        observations,
        minimum_training_labels=int(model["minimum_completed_position_day_labels"]),
        minimum_prior_predictions=int(model["minimum_prior_predictions"]),
        l2_penalty=float(model["l2_penalty"]),
    )
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    selected = [copy.deepcopy(row) for day in sorted(picks_by_date) for row in picks_by_date[day]]

    def replay(variant: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        triggers: list[dict[str, Any]] = []
        if variant is not None:
            signals, triggers = _signals_for_variant(
                observations=observations, predictions=predictions, variant=variant
            )
            config["config_id"] = str(variant["variant_id"])
            config["pit_external_position_exit_signals"] = signals
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = "round30-lambda-zero" if variant is None else f"round30-{variant['variant_id']}"
        account = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=bars_by_symbol,
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[config],
            **snapshot["inputs"]["account_profile"],
        )["results"][0]
        return account, {
            "triggered_position_count": len(triggers),
            "triggered_event_count": sum(int(row["event_count"]) for row in triggers),
            "triggers": triggers,
        }

    baseline_account, _ = replay(None)
    frozen_baseline = snapshot["baseline_output"]
    lambda_zero_nav_match = stable_digest(baseline_account["nav_rows"]) == stable_digest(frozen_baseline["nav_rows"])
    lambda_zero_trade_match = stable_digest(
        [row for row in baseline_account["order_ledger"] if row.get("action") in {"buy", "sell"}]
    ) == stable_digest(
        [row for row in frozen_baseline["order_ledger"] if row.get("action") in {"buy", "sell"}]
    )
    if not (lambda_zero_nav_match and lambda_zero_trade_match):
        raise ValueError("round30 lambda zero failed to reproduce frozen account economics")
    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_extended": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    rows: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, Any]] = {}
    for variant in design["variants"]:
        account, trigger_audit = replay(variant)
        variant_id = str(variant["variant_id"])
        accounts[variant_id] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_extended": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        rows.append(
            {
                "variant": variant,
                "trigger_audit": trigger_audit,
                "segments": segments,
                "gates": {key: _non_degrade(value, baseline_segments[key]) for key, value in segments.items()},
                "validation_monthly_delta": _monthly_delta_summary(
                    account,
                    baseline_account,
                    start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                    end=DEFAULT_VALIDATION_END,
                ),
                "extended_diagnostic": {
                    "baseline": _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end),
                    "candidate": _segment_metrics(account, start=DEFAULT_FINAL_START, end=signal_end),
                },
            }
        )
    eligible = [
        row
        for row in rows
        if not row["variant"].get("control_only")
        and int(row["trigger_audit"]["triggered_position_count"]) > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
    ]
    selected_row = None
    if eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        plateau = [
            row for row in eligible if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor
        ]
        selected_row = max(
            plateau,
            key=lambda row: (
                float(row["variant"]["prediction_percentile_min"]),
                float(row["variant"]["minimum_predicted_advantage"]),
            ),
        )
    extended = None
    if selected_row is not None:
        variant_id = str(selected_row["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[variant_id], start=DEFAULT_FINAL_START, end=signal_end)
        extended = {
            "variant_id": variant_id,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(
                accounts[variant_id], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }
    passed = bool(extended and extended["gate"]["passed"] and extended["standout"]["passed"])
    material = {
        "artifact_type": "event_confirmed_position_exit_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_event_triggered_price_confirmed_position_exit_not_v3_change",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_design_digest": stable_digest(design),
        "source_external_digests": actual_digests,
        "official_event_audit": {**event_audit, "future_event_violations": 0},
        "prediction_audit": prediction_audit,
        "lambda_zero_reproduction": {
            "passed": True,
            "economic_nav_match": lambda_zero_nav_match,
            "executed_buy_sell_ledger_match": lambda_zero_trade_match,
        },
        "baseline_segments_pre_extended": baseline_segments,
        "results_pre_extended": rows,
        "selection_before_extended_readout": None
        if selected_row is None
        else selected_row["variant"]["variant_id"],
        "extended_readout": extended,
        "extended_readout_status": "reused_evaluation_not_untouched_due_prior_iterations",
        "entry_selection_changed": False,
        "external_buy_trigger_count": 0,
        "future_feature_violations": 0,
        "future_label_violations": 0,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"event-confirmed-position-exit-{digest[:16]}", **material, "content_digest": digest}


def write_event_confirmed_position_exit_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("event-confirmed position-exit result digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable event-confirmed position-exit result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
