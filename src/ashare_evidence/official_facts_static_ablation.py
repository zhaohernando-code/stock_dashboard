from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import numpy as np

from ashare_evidence.external_context_residual_policy import (
    STATIC_EXTERNAL_WEIGHT_LADDER,
    apply_bounded_external_residual,
    select_smallest_weight_within_one_standard_error,
)
from ashare_evidence.market_rules import (
    ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    build_trade_eligibility_snapshot,
)
from ashare_evidence.model_candidate_runner import (
    _fit_model,
    _grid_trials,
    _iter_artifact_rows,
    _make_prediction_from_joined_row,
    _model_feature_values,
    _top_k_picks_from_ordered_rows,
)
from ashare_evidence.model_exploration_snapshot import _label_for_row
from ashare_evidence.model_spec_registry import default_model_specs

SCHEMA_VERSION = "official_facts_static_ablation.v1"
DEFAULT_MODEL_SPEC_ID = "negative_month_rank_weight_adjusted_capacity_cluster_v3_top3_20d_v1"
DEFAULT_TRIAL_ID = f"{DEFAULT_MODEL_SPEC_ID}:trial-000"
DEFAULT_LOOKBACK_DAYS = 20
DEFAULT_HALF_LIFE_DAYS = 5.0
DEFAULT_RESIDUAL_CAP = 0.3
DEFAULT_TUNING_END = "2025-05-26"
DEFAULT_ABLATION_END = "2026-05-26"
RIDGE_ALPHA = 1.0
RESIDUAL_FEATURE_NAMES = (
    "return_5d_percentile",
    "return_20d_percentile",
    "amount_10d_vs_20d_percentile",
    "low_volatility_percentile",
    "low_turnover_percentile",
    "turnover_rate_percentile",
)

_SEVERITY_RULES: tuple[tuple[float, tuple[str, ...]], ...] = (
    (
        1.0,
        (
            "立案调查",
            "立案告知",
            "重大违法",
            "终止上市",
            "退市风险警示",
            "破产清算",
            "被申请破产",
            "债务违约",
            "逾期未偿",
            "行政处罚",
        ),
    ),
    (
        0.7,
        (
            "纪律处分",
            "监管警示",
            "责令改正",
            "司法冻结",
            "轮候冻结",
            "重大诉讼",
            "重大仲裁",
            "业绩预亏",
            "预计亏损",
            "大额计提",
            "重大资产减值",
        ),
    ),
    (
        0.4,
        (
            "诉讼",
            "仲裁",
            "冻结",
            "减持计划",
            "计提减值",
            "经营异常",
            "终止筹划",
            "交易失败",
        ),
    ),
)
_SUPPRESSION_TERMS = (
    "解除冻结",
    "解除轮候冻结",
    "撤销退市风险警示",
    "撤回减持计划",
    "终止减持计划",
    "减持计划完成",
    "增持计划",
    "不予处罚",
    "免予处罚",
    "结案",
)


@dataclass(frozen=True)
class OfficialRiskEvent:
    symbol: str
    available_from: datetime
    severity: float
    normalized_event_id: str
    revision_id: str
    title: str
    rule: str


def _stable_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone-aware datetime required: {value}")
    return parsed


def official_fact_risk_severity(title: str) -> tuple[float, str | None]:
    normalized = "".join(str(title or "").split())
    if not normalized or any(term in normalized for term in _SUPPRESSION_TERMS):
        return 0.0, None
    for severity, terms in _SEVERITY_RULES:
        matched = next((term for term in terms if term in normalized), None)
        if matched:
            return severity, matched
    return 0.0, None


def _symbol_from_sec_code(sec_code: str) -> str | None:
    ticker = str(sec_code or "").strip().zfill(6)
    if ticker.startswith("6"):
        return f"{ticker}.SH"
    if ticker.startswith(("0", "3")):
        return f"{ticker}.SZ"
    if ticker.startswith(("4", "8", "920")):
        return f"{ticker}.BJ"
    return None


def load_official_risk_events(
    *,
    external_root: Path,
    curation_path: Path,
) -> tuple[dict[str, list[OfficialRiskEvent]], dict[str, Any]]:
    curation = json.loads(curation_path.read_text(encoding="utf-8"))
    excluded = {
        (str(row.get("normalized_event_id") or ""), str(row.get("revision_id") or ""))
        for row in curation.get("excluded_event_versions") or []
    }
    events: dict[str, list[OfficialRiskEvent]] = defaultdict(list)
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
        titles = [str(value) for value in (feature.get("announcement_titles") or [feature.get("announcement_title")]) if value]
        title = "；".join(titles)
        classified_titles: list[tuple[float, str]] = []
        for item in titles:
            item_severity, item_rule = official_fact_risk_severity(item)
            if item_severity > 0 and item_rule is not None:
                classified_titles.append((item_severity, item_rule))
        severity, rule = max(classified_titles, default=(0.0, None), key=lambda row: row[0])
        if severity <= 0 or rule is None:
            continue
        symbol = _symbol_from_sec_code(str(feature.get("sec_code") or ""))
        available_from = record.get("available_from")
        if symbol is None or not available_from:
            continue
        events[symbol].append(
            OfficialRiskEvent(
                symbol=symbol,
                available_from=_parse_aware(str(available_from)),
                severity=severity,
                normalized_event_id=event_key[0],
                revision_id=event_key[1],
                title=title,
                rule=rule,
            )
        )
    for rows in events.values():
        rows.sort(key=lambda row: row.available_from)
    retained = sum(len(rows) for rows in events.values())
    return dict(events), {
        "pit_records_scanned": scanned,
        "curation_excluded_records": excluded_count,
        "adverse_event_count": retained,
        "adverse_symbol_count": len(events),
        "curation_policy_version": curation.get("active_relevance_policy_version"),
        "curation_exclusion_digest": curation.get("excluded_event_versions_sha256"),
    }


def official_risk_signal(
    events: list[OfficialRiskEvent],
    *,
    decision_cutoff: datetime,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> tuple[float, list[OfficialRiskEvent]]:
    if not events:
        return 0.0, []
    ordered_events = sorted(events, key=lambda row: row.available_from)
    available = [row.available_from for row in ordered_events]
    right = bisect.bisect_right(available, decision_cutoff)
    earliest = decision_cutoff - timedelta(days=lookback_days)
    left = bisect.bisect_left(available, earliest, hi=right)
    matched = ordered_events[left:right]
    score = 0.0
    for event in matched:
        age_days = max(0.0, (decision_cutoff - event.available_from).total_seconds() / 86400.0)
        score += event.severity * math.pow(0.5, age_days / half_life_days)
    return score, matched


class PastOnlyRidgeResidualizer:
    def __init__(self, *, feature_count: int, alpha: float = RIDGE_ALPHA) -> None:
        width = feature_count + 1
        self._xtx = np.zeros((width, width), dtype=float)
        self._xty = np.zeros(width, dtype=float)
        self._alpha = float(alpha)
        self.row_count = 0
        self.fit_end: str | None = None

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        design = np.column_stack([np.ones(len(matrix)), matrix])
        if self.row_count == 0:
            return np.zeros(len(matrix), dtype=float)
        penalty = np.eye(design.shape[1], dtype=float) * self._alpha
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(self._xtx + penalty, self._xty)
        return design @ beta

    def update(self, matrix: np.ndarray, target: np.ndarray, *, as_of_date: str) -> None:
        design = np.column_stack([np.ones(len(matrix)), matrix])
        self._xtx += design.T @ design
        self._xty += design.T @ target
        self.row_count += len(matrix)
        self.fit_end = as_of_date


def _z_scores(values: np.ndarray) -> np.ndarray:
    if not len(values):
        return values
    deviation = float(np.std(values))
    if deviation <= 1e-12:
        return np.zeros(len(values), dtype=float)
    return (values - float(np.mean(values))) / deviation


def _decision_cutoff(as_of_date: str) -> datetime:
    return datetime.combine(date.fromisoformat(as_of_date), time(23, 59, 59), tzinfo=timezone(timedelta(hours=8)))


def _query_prices_for_date(conn: sqlite3.Connection, as_of_date: str) -> dict[str, tuple[float, str]]:
    next_day = (date.fromisoformat(as_of_date) + timedelta(days=1)).isoformat()
    rows = conn.execute(
        "SELECT s.symbol, mb.close_price, mb.observed_at FROM market_bars mb "
        "JOIN stocks s ON s.id = mb.stock_id "
        "WHERE mb.timeframe = '1d' AND mb.observed_at >= ? AND mb.observed_at < ? "
        "ORDER BY mb.id",
        (as_of_date, next_day),
    )
    return {str(symbol): (float(close), str(observed_at)) for symbol, close, observed_at in rows}


def _prediction_for_feature_row(
    feature_row: dict[str, Any],
    *,
    spec: dict[str, Any],
    params: dict[str, Any],
    fitted_model: dict[str, Any],
    trial_id: str,
) -> dict[str, Any]:
    feature_values = _model_feature_values(feature_row)
    joined = {
        "universe_row_id": str(feature_row.get("universe_row_id") or ""),
        "symbol": feature_row.get("symbol"),
        "stock_name": feature_row.get("stock_name"),
        "board": feature_row.get("board"),
        "industry_code": feature_row.get("industry_code"),
        "industry_name": feature_row.get("industry_name"),
        "as_of_date": str(feature_row.get("as_of_date") or ""),
        "feature_row": feature_row,
        "feature_values_flat": feature_values,
        "label_status": "not_required_for_selection",
        "target_label": None,
        "target_labels_by_horizon": {},
        "target_total_return": None,
        "target_total_returns_by_horizon": {},
    }
    prediction = _make_prediction_from_joined_row(
        joined=joined,
        spec=spec,
        params=params,
        trial_id=trial_id,
        split_id="official-facts-static-ablation",
        fitted_model_digest="deterministic-score-only-no-fit",
        fitted_model=fitted_model,
        horizon_days=int(spec.get("prediction_horizon_days") or 20),
    )
    prediction["_residual_features"] = [float(feature_values.get(name, 0.0) or 0.0) for name in RESIDUAL_FEATURE_NAMES]
    return prediction


def _select(
    rows: list[dict[str, Any]],
    *,
    as_of_date: str,
    top_k: int,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
    ranking_key: str,
) -> list[dict[str, Any]]:
    active = [row for row in rows if row.get("selection_allowed", True)]
    ordered = sorted(active, key=lambda row: float(row.get(ranking_key, row.get("score", 0.0))), reverse=True)
    return _top_k_picks_from_ordered_rows(
        as_of_date=as_of_date,
        ordered=ordered,
        top_k=top_k,
        selection_policy=selection_policy,
        params=params,
    )


def _frozen_picks_by_date(candidate_run: dict[str, Any], trial_id: str) -> dict[str, list[dict[str, Any]]]:
    diagnostic = next(row for row in candidate_run.get("trial_diagnostics") or [] if row.get("trial_id") == trial_id)
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in diagnostic.get("selected_top_k_picks_by_date") or []:
        by_date[str(row["as_of_date"])].append(row)
    return dict(by_date)


def _load_bars_for_symbols(
    conn: sqlite3.Connection,
    symbols: Iterable[str],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ordered_symbols = sorted(set(symbols))
    for offset in range(0, len(ordered_symbols), 400):
        chunk = ordered_symbols[offset : offset + 400]
        placeholders = ",".join("?" for _ in chunk)
        query = (
            "SELECT mb.id, s.id, s.symbol, mb.observed_at, mb.open_price, mb.high_price, mb.low_price, "
            "mb.close_price, mb.volume, mb.amount, mb.turnover_rate, mb.total_mv, mb.circ_mv, mb.pe_ttm, mb.pb, "
            "mb.lineage_hash FROM market_bars mb JOIN stocks s ON s.id = mb.stock_id "
            f"WHERE mb.timeframe = '1d' AND s.symbol IN ({placeholders}) ORDER BY s.symbol, mb.observed_at, mb.id"
        )
        for row in conn.execute(query, chunk):
            observed = datetime.fromisoformat(str(row[3]))
            output[str(row[2])].append(
                {
                    "id": int(row[0]),
                    "stock_id": int(row[1]),
                    "symbol": str(row[2]),
                    "observed_at": observed,
                    "observed_date": observed.date(),
                    "open_price": float(row[4]),
                    "high_price": float(row[5]),
                    "low_price": float(row[6]),
                    "close_price": float(row[7]),
                    "volume": float(row[8]),
                    "amount": float(row[9]),
                    "turnover_rate": row[10],
                    "total_mv": row[11],
                    "circ_mv": row[12],
                    "pe_ttm": row[13],
                    "pb": row[14],
                    "lineage_hash": str(row[15]),
                }
            )
    return dict(output)


def _attach_labels(
    selections: dict[float, list[dict[str, Any]]],
    *,
    conn: sqlite3.Connection,
    benchmark_symbol: str = "000300.SH",
) -> dict[str, Any]:
    symbols = {benchmark_symbol}
    for picks in selections.values():
        symbols.update(str(row["symbol"]) for row in picks)
    bars = _load_bars_for_symbols(conn, symbols)
    benchmark_bars = bars.get(benchmark_symbol, [])
    benchmark_by_day = {row["observed_date"]: index for index, row in enumerate(benchmark_bars)}
    blocked = Counter()
    label_cache: dict[tuple[str, str, int], float | None] = {}
    for picks in selections.values():
        for pick in picks:
            symbol = str(pick["symbol"])
            as_of_date = str(pick["as_of_date"])
            horizon = int(pick.get("target_horizon_days") or 20)
            key = (symbol, as_of_date, horizon)
            if key not in label_cache:
                stock_bars = bars.get(symbol, [])
                index_by_day = {row["observed_date"]: index for index, row in enumerate(stock_bars)}
                as_of_day = date.fromisoformat(as_of_date)
                stock_index = index_by_day.get(as_of_day)
                if stock_index is None:
                    label_cache[key] = None
                    blocked["missing_signal_bar"] += 1
                else:
                    label = _label_for_row(
                        symbol=symbol,
                        as_of_day=as_of_day,
                        stock_bars=stock_bars,
                        stock_index=stock_index,
                        benchmark_bars=benchmark_bars,
                        benchmark_by_day=benchmark_by_day,
                        horizons=(5, 10, 20),
                        universe_row_id=f"universe:{symbol}:{as_of_date}",
                        source_snapshot_id="official-facts-static-ablation",
                        entry_price_source="next_close",
                    )
                    value = (label.get("labels") or {}).get(f"excess_return_{horizon}d")
                    relevant_reasons = [
                        str(reason)
                        for reason in label.get("label_block_reasons") or []
                        if str(reason).endswith("_entry")
                        or str(reason).endswith(f"_{horizon}d")
                        or str(reason) in {"missing_stock_entry_bar", "missing_benchmark_entry_bar"}
                    ]
                    if relevant_reasons or value is None:
                        label_cache[key] = None
                        for reason in relevant_reasons or ["blocked_label"]:
                            blocked[str(reason)] += 1
                    else:
                        label_cache[key] = float(value) - 0.001
            net_return = label_cache[key]
            pick["label_status"] = "ready" if net_return is not None else "blocked_cash_proxy"
            pick["net_excess_return"] = float(net_return or 0.0)
            pick["weighted_net_excess_return"] = (
                float(net_return or 0.0)
                * float(pick.get("portfolio_weight") or 0.0)
                * float(pick.get("rank_weight_multiplier") or 1.0)
            )
    return {
        "unique_label_count": len(label_cache),
        "ready_label_count": sum(value is not None for value in label_cache.values()),
        "blocked_label_count": sum(value is None for value in label_cache.values()),
        "blocked_label_reason_counts": dict(sorted(blocked.items())),
    }


def _metric_summary(picks: list[dict[str, Any]], *, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    by_date: dict[str, list[float]] = defaultdict(list)
    for row in picks:
        as_of_date = str(row["as_of_date"])
        if start and as_of_date < start:
            continue
        if end and as_of_date > end:
            continue
        by_date[as_of_date].append(float(row.get("weighted_net_excess_return") or 0.0))
    daily = [(day, mean(values)) for day, values in sorted(by_date.items())]
    daily_values = [value for _, value in daily]
    monthly: dict[str, list[float]] = defaultdict(list)
    for day, value in daily:
        monthly[day[:7]].append(value)
    monthly_means = {month: mean(values) for month, values in sorted(monthly.items())}
    curve = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in daily_values:
        curve *= 1.0 + value
        peak = max(peak, curve)
        max_drawdown = min(max_drawdown, curve / peak - 1.0)
    standard_error = stdev(daily_values) / math.sqrt(len(daily_values)) if len(daily_values) > 1 else 0.0
    return {
        "signal_day_count": len(daily_values),
        "selected_pick_count": sum(len(values) for values in by_date.values()),
        "mean_daily_weighted_net_excess": mean(daily_values) if daily_values else 0.0,
        "daily_standard_error": standard_error,
        "positive_signal_day_rate": (
            sum(value > 0 for value in daily_values) / len(daily_values) if daily_values else 0.0
        ),
        "compounded_signal_curve_proxy": curve - 1.0,
        "max_drawdown_signal_curve_proxy": max_drawdown,
        "negative_month_count": sum(value < 0 for value in monthly_means.values()),
        "worst_month_mean": min(monthly_means.values()) if monthly_means else 0.0,
        "monthly_means": monthly_means,
        "claim_note": "overlapping_signal_curve_proxy_not_account_level_return",
    }


def run_official_facts_static_ablation(
    *,
    feature_matrix_path: Path,
    candidate_run_path: Path,
    database_path: Path,
    external_root: Path,
    curation_path: Path,
    output_path: Path,
    model_spec_id: str = DEFAULT_MODEL_SPEC_ID,
    trial_id: str = DEFAULT_TRIAL_ID,
    tuning_end: str = DEFAULT_TUNING_END,
    ablation_end: str = DEFAULT_ABLATION_END,
) -> dict[str, Any]:
    candidate_run = json.loads(candidate_run_path.read_text(encoding="utf-8"))
    trial_summary = next(row for row in candidate_run.get("trial_summaries") or [] if row.get("trial_id") == trial_id)
    params = dict(trial_summary.get("params") or {})
    spec = next(row for row in default_model_specs() if row.get("model_spec_id") == model_spec_id)
    expected_params = _grid_trials(spec.get("hyperparameter_grid") or {})[int(trial_id.rsplit("-", 1)[-1])]
    if params != expected_params:
        raise ValueError("candidate run trial params no longer match the registered frozen spec")
    selection_policy = spec.get("selection_policy") or {}
    top_k = int(selection_policy.get("top_k") or 3)
    fitted_model = _fit_model([], model_spec=spec, params=params)
    frozen_by_date = _frozen_picks_by_date(candidate_run, trial_id)
    events_by_symbol, event_audit = load_official_risk_events(
        external_root=external_root,
        curation_path=curation_path,
    )
    conn = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    residualizer = PastOnlyRidgeResidualizer(feature_count=len(RESIDUAL_FEATURE_NAMES))
    selections: dict[float, list[dict[str, Any]]] = {weight: [] for weight in STATIC_EXTERNAL_WEIGHT_LADDER}
    reproduction_actual: dict[str, list[dict[str, Any]]] = {}
    exclusion_counts: Counter[str] = Counter()
    exclusion_samples: list[dict[str, Any]] = []
    eligibility_snapshot_digest = hashlib.sha256()
    pit_violation_count = 0
    used_event_ids: set[str] = set()
    date_audit: list[dict[str, Any]] = []

    def process_date(as_of_date: str, feature_rows: list[dict[str, Any]]) -> None:
        nonlocal pit_violation_count
        prices = _query_prices_for_date(conn, as_of_date)
        cutoff = _decision_cutoff(as_of_date)
        all_predictions: list[dict[str, Any]] = []
        eligible_predictions: list[dict[str, Any]] = []
        raw_signals: list[float] = []
        residual_features: list[list[float]] = []
        matched_events_by_symbol: dict[str, list[OfficialRiskEvent]] = {}
        for feature_row in feature_rows:
            prediction = _prediction_for_feature_row(
                feature_row,
                spec=spec,
                params=params,
                fitted_model=fitted_model,
                trial_id=trial_id,
            )
            prediction["_ranking_score"] = float(prediction["score"])
            all_predictions.append(prediction)
            symbol = str(prediction["symbol"])
            price = prices.get(symbol)
            snapshot = build_trade_eligibility_snapshot(
                symbol,
                account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
                as_of=date.fromisoformat(as_of_date),
                decision_cutoff=cutoff,
                price_cny=price[0] if price else None,
                price_observed_at=price[1] if price else None,
                price_source="runtime_market_bars.daily.close",
                price_adjustment="unadjusted",
                profile_is_point_in_time=False,
            )
            eligibility_snapshot_digest.update(str(snapshot["snapshot_id"]).encode("utf-8"))
            eligibility_snapshot_digest.update(b"\n")
            if not snapshot["eligible_before_scoring"]:
                for reason in snapshot["exclusion_reason_codes"]:
                    exclusion_counts[str(reason)] += 1
                if len(exclusion_samples) < 100:
                    exclusion_samples.append(
                        {
                            "as_of_date": as_of_date,
                            "symbol": symbol,
                            "price_cny": price[0] if price else None,
                            "reason_codes": snapshot["exclusion_reason_codes"],
                            "snapshot_id": snapshot["snapshot_id"],
                        }
                    )
                continue
            signal, matched = official_risk_signal(events_by_symbol.get(symbol, []), decision_cutoff=cutoff)
            for event in matched:
                if event.available_from > cutoff:
                    pit_violation_count += 1
                used_event_ids.add(event.normalized_event_id)
            matched_events_by_symbol[symbol] = matched
            eligible_predictions.append(prediction)
            raw_signals.append(signal)
            residual_features.append(list(prediction["_residual_features"]))

        reproduced = _select(
            all_predictions,
            as_of_date=as_of_date,
            top_k=top_k,
            selection_policy=selection_policy,
            params=params,
            ranking_key="_ranking_score",
        )
        reproduction_actual[as_of_date] = reproduced
        if not eligible_predictions:
            return
        feature_matrix = np.asarray(residual_features, dtype=float)
        raw_array = np.asarray(raw_signals, dtype=float)
        predicted = residualizer.predict(feature_matrix)
        residual = raw_array - predicted
        core_z = _z_scores(np.asarray([float(row["score"]) for row in eligible_predictions], dtype=float))
        residual_z = _z_scores(residual)
        for index, prediction in enumerate(eligible_predictions):
            prediction["_external_raw_signal"] = float(raw_array[index])
            prediction["_external_predicted_from_core"] = float(predicted[index])
            prediction["_external_residual"] = float(residual[index])
            prediction["_external_residual_z"] = float(residual_z[index])
            prediction["_core_score_z"] = float(core_z[index])
        if as_of_date <= ablation_end:
            for weight in STATIC_EXTERNAL_WEIGHT_LADDER:
                ranked_rows: list[dict[str, Any]] = []
                for prediction in eligible_predictions:
                    row = dict(prediction)
                    applied = apply_bounded_external_residual(
                        channel="individual_event",
                        core_score_z=float(row["_core_score_z"]),
                        external_residual_z=float(row["_external_residual_z"]),
                        lambda_weight=weight,
                        cap=DEFAULT_RESIDUAL_CAP,
                        core_eligible=True,
                    )
                    row["_ranking_score"] = float(applied["final_score_z"])
                    ranked_rows.append(row)
                picks = _select(
                    ranked_rows,
                    as_of_date=as_of_date,
                    top_k=top_k,
                    selection_policy=selection_policy,
                    params=params,
                    ranking_key="_ranking_score",
                )
                row_by_symbol = {str(row["symbol"]): row for row in ranked_rows}
                for pick in picks:
                    source = row_by_symbol[str(pick["symbol"])]
                    pick["lambda_weight"] = weight
                    pick["core_score_z"] = source["_core_score_z"]
                    pick["external_raw_signal"] = source["_external_raw_signal"]
                    pick["external_predicted_from_core"] = source["_external_predicted_from_core"]
                    pick["external_residual"] = source["_external_residual"]
                    pick["external_residual_z"] = source["_external_residual_z"]
                    pick["final_ranking_score_z"] = source["_ranking_score"]
                    pick["matched_official_event_ids"] = [
                        event.normalized_event_id for event in matched_events_by_symbol.get(str(pick["symbol"]), [])
                    ]
                selections[weight].extend(picks)
        date_audit.append(
            {
                "as_of_date": as_of_date,
                "candidate_count": len(all_predictions),
                "eligible_before_scoring_count": len(eligible_predictions),
                "adverse_signal_candidate_count": sum(value > 0 for value in raw_signals),
                "residual_model_training_row_count_before_date": residualizer.row_count,
                "residual_model_fit_end_before_date": residualizer.fit_end,
            }
        )
        residualizer.update(feature_matrix, raw_array, as_of_date=as_of_date)

    current_date: str | None = None
    current_rows: list[dict[str, Any]] = []
    for feature_row in _iter_artifact_rows(feature_matrix_path):
        as_of_date = str(feature_row.get("as_of_date") or "")
        if current_date is None:
            current_date = as_of_date
        elif as_of_date != current_date:
            process_date(current_date, current_rows)
            current_rows = []
            current_date = as_of_date
        current_rows.append(feature_row)
    if current_date is not None:
        process_date(current_date, current_rows)

    reproduction_mismatches: list[dict[str, Any]] = []
    for as_of_date, expected in sorted(frozen_by_date.items()):
        actual = reproduction_actual.get(as_of_date, [])
        expected_pairs = [(str(row["symbol"]), int(row["rank"])) for row in expected]
        actual_pairs = [(str(row["symbol"]), int(row["rank"])) for row in actual]
        if expected_pairs != actual_pairs:
            reproduction_mismatches.append(
                {"as_of_date": as_of_date, "expected": expected_pairs, "actual": actual_pairs}
            )
    unexpected_active_dates = sorted(
        as_of_date
        for as_of_date, rows in reproduction_actual.items()
        if rows and as_of_date not in frozen_by_date
    )
    reproduction_mismatches.extend(
        {"as_of_date": as_of_date, "expected": [], "actual": "unexpected_non_cash_selection"}
        for as_of_date in unexpected_active_dates
    )
    if reproduction_mismatches:
        raise RuntimeError(f"lambda-zero frozen selection reproduction failed on {len(reproduction_mismatches)} dates")

    label_audit = _attach_labels(selections, conn=conn)
    conn.close()
    tuning_baseline = _metric_summary(selections[0.0], end=tuning_end)
    candidate_metrics: list[dict[str, Any]] = []
    metrics_by_weight: dict[str, Any] = {}
    for weight, picks in selections.items():
        tuning = _metric_summary(picks, end=tuning_end)
        holdout = _metric_summary(picks, start=(date.fromisoformat(tuning_end) + timedelta(days=1)).isoformat(), end=ablation_end)
        full = _metric_summary(picks, end=ablation_end)
        non_degradation_floor = (
            tuning_baseline["mean_daily_weighted_net_excess"] - tuning_baseline["daily_standard_error"]
        )
        all_gates_passed = (
            pit_violation_count == 0
            and not reproduction_mismatches
            and tuning["mean_daily_weighted_net_excess"] >= non_degradation_floor
            and tuning["negative_month_count"] <= tuning_baseline["negative_month_count"] + 1
        )
        candidate_metrics.append(
            {
                "lambda_weight": weight,
                "oos_mean": tuning["mean_daily_weighted_net_excess"],
                "oos_standard_error": tuning["daily_standard_error"],
                "all_gates_passed": all_gates_passed,
            }
        )
        metrics_by_weight[str(weight)] = {
            "tuning": tuning,
            "untouched_holdout": holdout,
            "full_available_window": full,
            "all_gates_passed_for_one_se_selection": all_gates_passed,
            "stock_only_non_degradation_floor": non_degradation_floor,
        }
    selection = select_smallest_weight_within_one_standard_error(candidate_metrics)
    selected_weight = selection.get("selected_lambda_weight")
    symbol_changes_by_weight: dict[str, list[dict[str, Any]]] = {}
    baseline_keys = {(row["as_of_date"], row["rank"]): row for row in selections[0.0]}
    for weight, picks in selections.items():
        comparison_keys = {(row["as_of_date"], row["rank"]): row for row in picks}
        changes: list[dict[str, Any]] = []
        for key in sorted(set(baseline_keys) | set(comparison_keys)):
            baseline = baseline_keys.get(key)
            comparison = comparison_keys.get(key)
            if (baseline or {}).get("symbol") != (comparison or {}).get("symbol"):
                changes.append(
                    {
                        "as_of_date": key[0],
                        "rank": key[1],
                        "lambda_zero_symbol": (baseline or {}).get("symbol"),
                        "comparison_symbol": (comparison or {}).get("symbol"),
                    }
                )
        symbol_changes_by_weight[str(weight)] = changes
    selected_changes: list[dict[str, Any]] = []
    if selected_weight is not None:
        selected_changes = symbol_changes_by_weight[str(float(selected_weight))]
    personal_baseline_by_date: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in selections[0.0]:
        personal_baseline_by_date[str(row["as_of_date"])].append((str(row["symbol"]), int(row["rank"])))
    personal_baseline_changes = []
    for as_of_date, expected in sorted(frozen_by_date.items()):
        if as_of_date > ablation_end:
            continue
        expected_pairs = [(str(row["symbol"]), int(row["rank"])) for row in expected]
        actual_pairs = personal_baseline_by_date.get(as_of_date, [])
        if expected_pairs != actual_pairs:
            personal_baseline_changes.append(
                {"as_of_date": as_of_date, "unfiltered": expected_pairs, "personal_eligible": actual_pairs}
            )
    payload = {
        "artifact_type": "official_facts_static_ablation",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "claim_ceiling": "research_only_signal_level_static_weight_ablation_not_account_replay_not_v3_promotion",
        "promotion_status": "blocked_from_production",
        "v3_signal_changed": False,
        "source_contract": {
            "model_spec_id": model_spec_id,
            "trial_id": trial_id,
            "source_feature_matrix_id": candidate_run.get("source_feature_matrix_id"),
            "source_candidate_run_id": candidate_run.get("artifact_id"),
            "full713_data_window": {"start": "2023-06-13", "end": ablation_end},
            "model_signal_window": {"start": min(reproduction_actual), "end": max(reproduction_actual)},
            "ablation_available_end": ablation_end,
            "tuning_end": tuning_end,
            "holdout_start": (date.fromisoformat(tuning_end) + timedelta(days=1)).isoformat(),
        },
        "formula_contract": {
            "formula": "z(core_score)-clip(lambda*z(past_only_external_residual),-0.3,+0.3)",
            "weights": list(STATIC_EXTERNAL_WEIGHT_LADDER),
            "cap": DEFAULT_RESIDUAL_CAP,
            "lookback_calendar_days": DEFAULT_LOOKBACK_DAYS,
            "half_life_calendar_days": DEFAULT_HALF_LIFE_DAYS,
            "residual_model": "expanding_past_only_ridge_on_stock_native_percentile_features",
            "residual_features": list(RESIDUAL_FEATURE_NAMES),
            "positive_official_information_can_create_eligibility": False,
        },
        "lambda_zero_reproduction": {
            "status": "passed",
            "expected_signal_day_count": len(frozen_by_date),
            "matrix_date_count": len(reproduction_actual),
            "reproduced_signal_day_count": sum(bool(rows) for rows in reproduction_actual.values()),
            "mismatch_count": 0,
        },
        "personal_eligibility": {
            "profile": ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            "applied_before_scoring": True,
            "price_source": "runtime_market_bars.daily.close",
            "price_adjustment": "unadjusted",
            "profile_is_point_in_time": False,
            "pit_risk_status_limitation": "current_static_name_status_not_backfilled; historical_ST_status_not_verified",
            "eligibility_snapshot_digest": eligibility_snapshot_digest.hexdigest(),
            "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
            "exclusion_samples": exclusion_samples,
            "unfiltered_to_personal_baseline_changed_date_count": len(personal_baseline_changes),
            "unfiltered_to_personal_baseline_changes": personal_baseline_changes,
        },
        "official_event_audit": {
            **event_audit,
            "pit_future_event_violation_count": pit_violation_count,
            "used_event_count": len(used_event_ids),
        },
        "residual_audit": {
            "final_training_row_count": residualizer.row_count,
            "final_fit_end": residualizer.fit_end,
            "date_audit": date_audit,
        },
        "label_audit": label_audit,
        "metrics_by_weight": metrics_by_weight,
        "one_standard_error_selection": selection,
        "symbol_change_count_by_weight_vs_lambda_zero": {
            weight: len(changes) for weight, changes in symbol_changes_by_weight.items()
        },
        "selected_weight_symbol_change_count": len(selected_changes),
        "selected_weight_symbol_changes": selected_changes,
        "limitations": [
            "signal returns overlap and are not an account-level capital replay",
            "historical ST/risk-warning status lacks a point-in-time security-master feed",
            "official announcement direction is deterministic title taxonomy, not document-body NLP",
            "global market and professional news channels are not included in this ablation",
            "DSR/PBO and production promotion gates remain pending account-level replay",
        ],
    }
    digest = _stable_digest(payload)
    payload["artifact_id"] = f"official-facts-static-ablation-{digest[:16]}"
    payload["content_digest"] = digest
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline PIT official-facts static-weight ablation.")
    parser.add_argument("--feature-matrix", type=Path, required=True)
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--curation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tuning-end", default=DEFAULT_TUNING_END)
    parser.add_argument("--ablation-end", default=DEFAULT_ABLATION_END)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_official_facts_static_ablation(
        feature_matrix_path=args.feature_matrix,
        candidate_run_path=args.candidate_run,
        database_path=args.database,
        external_root=args.external_root,
        curation_path=args.curation,
        output_path=args.output,
        tuning_end=args.tuning_end,
        ablation_end=args.ablation_end,
    )
    print(json.dumps({
        "artifact_id": result["artifact_id"],
        "output": str(args.output),
        "one_standard_error_selection": result["one_standard_error_selection"],
        "v3_signal_changed": result["v3_signal_changed"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
