from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from ashare_evidence.external_context_global_market_research import (
    load_research_snapshot,
    market_state_by_decision_date,
)
from ashare_evidence.external_context_macro_research import (
    load_macro_research_snapshot,
    macro_state_by_decision_date,
)
from ashare_evidence.external_context_sector_market_research import (
    SW_L1_BY_SUBINDUSTRY,
    load_sector_research_snapshot,
    sector_mapping_coverage,
    sector_state_by_decision_date,
)
from ashare_evidence.rolling_account_execution_snapshot import (
    load_rolling_account_execution_snapshot,
    stable_digest,
)
from ashare_evidence.rolling_tranche_account_replay import (
    _rank1_quality_scale,
    build_shortpick_v3_rolling_account_replay_artifact,
)

SCHEMA_VERSION = "global_sector_state_account_ablation.v1"
DEFAULT_SIGNAL_END = date(2026, 5, 26)
DEFAULT_TUNING_END = date(2025, 5, 26)
DEFAULT_VALIDATION_END = date(2025, 11, 26)
DEFAULT_FINAL_START = date(2025, 11, 27)
DEFAULT_CAP = 0.30
DEFAULT_LAMBDAS = (0.0, 0.025, 0.05, 0.075, 0.10, 0.15)
DEFAULT_GLOBAL_RISK_GUARD_VARIANTS = (
    {
        "variant_id": "global_mild_z1_breadth25_scale090",
        "global_risk_z_max": -1.0,
        "global_breadth_5d_max": 0.25,
        "global_scale": 0.90,
    },
    {
        "variant_id": "global_balanced_z15_breadth25_scale085",
        "global_risk_z_max": -1.5,
        "global_breadth_5d_max": 0.25,
        "global_scale": 0.85,
    },
    {
        "variant_id": "global_severe_z2_breadth25_scale075",
        "global_risk_z_max": -2.0,
        "global_breadth_5d_max": 0.25,
        "global_scale": 0.75,
    },
    {
        "variant_id": "tech_mild_z1_scale085",
        "tech_risk_z_max": -1.0,
        "tech_scale": 0.85,
    },
    {
        "variant_id": "tech_severe_z15_scale075",
        "tech_risk_z_max": -1.5,
        "tech_scale": 0.75,
    },
    {
        "variant_id": "combined_balanced_global085_tech080",
        "global_risk_z_max": -1.5,
        "global_breadth_5d_max": 0.25,
        "global_scale": 0.85,
        "tech_risk_z_max": -1.5,
        "tech_scale": 0.80,
    },
)
TECH_INDUSTRIES = frozenset({"半导体", "元器件", "通信设备", "IT设备", "软件服务", "互联网", "电信运营"})
ADJACENT_INDUSTRIES = frozenset({"电气设备", "电器仪表", "专用机械", "机械基件"})
HIGHER_IS_BETTER = frozenset({"total_return", "annualized_return", "max_drawdown", "worst_monthly_return"})
LOWER_IS_BETTER = frozenset(
    {"negative_month_count", "skipped_order_rate", "skipped_signal_rate", "max_single_symbol_exposure_pct"}
)
GATE_METRICS = tuple(sorted(HIGHER_IS_BETTER | LOWER_IS_BETTER))
CORE_LOSS_FEATURE_NAMES = (
    "score",
    "return_5d_percentile",
    "return_20d_percentile",
    "turnover_rate_percentile",
    "amount_10d_vs_20d_percentile",
    "distance_from_20d_high",
    "log1p_avg_amount_20d",
    "benchmark_return_20d",
    "industry_return_20d_excess",
    "tech_industry_loading",
)
EXTERNAL_LOSS_FEATURE_NAMES = (
    "global_risk_residual_z",
    "global_tech_residual_z",
    "global_breadth_5d",
    "global_breadth_20d",
    "global_mean_return_5d",
    "global_mean_return_20d",
    "tech_relative_5d",
    "tech_relative_20d",
    "fed_event_decay_5d",
    "us_policy_tech_risk_decay_20d",
)
COMPRESSED_CORE_LOSS_FEATURE_NAMES = (
    "return_5d_percentile",
    "return_20d_percentile",
    "turnover_rate_percentile",
    "benchmark_return_20d",
)
COMPRESSED_EXTERNAL_LOSS_FEATURE_NAMES = (
    "global_risk_residual_z",
    "tech_loading_times_global_tech_residual_z",
    "tech_loading_times_us_policy_tech_risk_decay_20d",
)
SECTOR_EXTERNAL_LOSS_FEATURE_NAMES = (
    "sw_l1_relative_5d",
    "sw_l1_relative_20d",
    "sw_l1_drawdown_20d",
    "sw_l1_breadth_5d",
    "sw_l1_breadth_20d",
)
MACRO_EXTERNAL_LOSS_FEATURE_NAMES = (
    "vix_level",
    "vix_change_5d",
    "usdcnh_return_5d",
    "ust_10y_change_5d",
    "ust_10y_minus_2y_level",
    "ust_10y_minus_2y_change_5d",
    "sge_gold_return_5d",
    "wti_return_5d",
)
SHANGHAI = ZoneInfo("Asia/Shanghai")
NEGATIVE_US_POLICY_PATTERN = re.compile(
    r"entity list|export control|restriction|prohibit|ban|tariff|forced labor|sanction|deny|suspend",
    re.IGNORECASE,
)


class PastOnlyRidge:
    def __init__(self, *, feature_count: int, alpha: float = 1.0) -> None:
        width = feature_count + 1
        self._xtx = np.zeros((width, width), dtype=float)
        self._xty = np.zeros(width, dtype=float)
        self._alpha = float(alpha)
        self.row_count = 0

    def predict_one(self, features: list[float]) -> float:
        if self.row_count == 0:
            return 0.0
        design = np.asarray([1.0, *features], dtype=float)
        penalty = np.eye(len(design), dtype=float) * self._alpha
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(self._xtx + penalty, self._xty)
        return float(design @ beta)

    def update_one(self, features: list[float], target: float) -> None:
        design = np.asarray([1.0, *features], dtype=float)
        self._xtx += np.outer(design, design)
        self._xty += design * float(target)
        self.row_count += 1


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def fit_l2_logistic(
    matrix: np.ndarray,
    labels: np.ndarray,
    *,
    l2_penalty: float = 5.0,
    sample_weights: np.ndarray | None = None,
    max_iterations: int = 50,
) -> np.ndarray:
    if matrix.ndim != 2 or labels.ndim != 1 or len(matrix) != len(labels):
        raise ValueError("logistic matrix and labels have incompatible shapes")
    if len(matrix) == 0 or len(set(float(value) for value in labels)) < 2:
        raise ValueError("logistic fit requires both label classes")
    design = np.column_stack([np.ones(len(matrix)), matrix])
    resolved_sample_weights = np.ones(len(matrix), dtype=float) if sample_weights is None else sample_weights
    if resolved_sample_weights.shape != labels.shape or np.any(resolved_sample_weights <= 0.0):
        raise ValueError("logistic sample weights must be positive and align with labels")
    beta = np.zeros(design.shape[1], dtype=float)
    penalty = np.eye(design.shape[1], dtype=float) * float(l2_penalty)
    penalty[0, 0] = 0.0
    for _iteration in range(max_iterations):
        probabilities = _sigmoid(design @ beta)
        weights = np.maximum(probabilities * (1.0 - probabilities), 1e-6) * resolved_sample_weights
        hessian = design.T @ (design * weights[:, None]) + penalty
        gradient = design.T @ ((labels - probabilities) * resolved_sample_weights) - penalty @ beta
        step = np.linalg.solve(hessian, gradient)
        beta += step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return beta


def standardized_logistic_probability(
    training_features: list[list[float]],
    training_labels: list[int],
    current_features: list[float],
    *,
    l2_penalty: float = 5.0,
    sample_weights: list[float] | None = None,
) -> float:
    matrix = np.asarray(training_features, dtype=float)
    labels = np.asarray(training_labels, dtype=float)
    current = np.asarray(current_features, dtype=float)
    resolved_weights = np.ones(len(matrix), dtype=float) if sample_weights is None else np.asarray(sample_weights, dtype=float)
    if resolved_weights.shape != labels.shape or np.any(resolved_weights <= 0.0):
        raise ValueError("standardization sample weights must be positive and align with labels")
    centers = np.average(matrix, axis=0, weights=resolved_weights)
    scales = np.sqrt(np.average(np.square(matrix - centers), axis=0, weights=resolved_weights))
    scales = np.where(scales <= 1e-12, 1.0, scales)
    standardized = (matrix - centers) / scales
    standardized_current = (current - centers) / scales
    beta = fit_l2_logistic(
        standardized,
        labels,
        l2_penalty=l2_penalty,
        sample_weights=resolved_weights,
    )
    design = np.asarray([1.0, *standardized_current], dtype=float)
    return float(_sigmoid(np.asarray([design @ beta]))[0])


def _z_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    deviation = pstdev(values)
    if deviation <= 1e-12:
        return [0.0] * len(values)
    center = mean(values)
    return [(value - center) / deviation for value in values]


def _industry_loading(industry_name: Any) -> float:
    industry = str(industry_name or "")
    if industry in TECH_INDUSTRIES:
        return 1.0
    if industry in ADJACENT_INDUSTRIES:
        return 0.5
    return 0.0


def _group_by_date(rows: list[dict[str, Any]], *, end: date) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        raw_day = str(row.get("as_of_date") or "")
        if raw_day and date.fromisoformat(raw_day) <= end:
            grouped[raw_day].append(copy.deepcopy(row))
    for values in grouped.values():
        values.sort(key=lambda row: (int(float(row.get("rank") or 999)), -float(row.get("score") or 0.0)))
    return dict(grouped)


def build_past_only_sector_residuals(
    *,
    inventory_by_date: dict[str, list[dict[str, Any]]],
    market_states: dict[str, dict[str, Any]],
    minimum_history: int = 20,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    ridge = PastOnlyRidge(feature_count=2, alpha=1.0)
    prior_residuals: list[float] = []
    standardized: dict[str, float] = {}
    audit: dict[str, dict[str, Any]] = {}
    for day in sorted(inventory_by_date):
        state = market_states.get(day)
        rows = inventory_by_date[day]
        if state is None:
            standardized[day] = 0.0
            audit[day] = {"status": "missing_global_state", "residual_z": 0.0}
            continue
        tech_rows = [row for row in rows if _industry_loading(row.get("industry_name")) >= 1.0]
        domestic_tech_excess = median(
            [float(row.get("industry_return_20d_excess") or 0.0) for row in tech_rows]
        ) if tech_rows else 0.0
        benchmark_return_20d = float(rows[0].get("benchmark_return_20d") or 0.0) if rows else 0.0
        raw_global_tech = 0.5 * (
            float(state["tech_relative_5d"]) + float(state["tech_relative_20d"])
        )
        features = [domestic_tech_excess, benchmark_return_20d]
        predicted = ridge.predict_one(features)
        residual = raw_global_tech - predicted
        if len(prior_residuals) >= minimum_history and pstdev(prior_residuals) > 1e-12:
            residual_z = (residual - mean(prior_residuals)) / pstdev(prior_residuals)
        else:
            residual_z = 0.0
        standardized[day] = max(-4.0, min(4.0, residual_z))
        audit[day] = {
            "status": "ready" if len(prior_residuals) >= minimum_history else "warmup",
            "raw_global_tech": raw_global_tech,
            "domestic_tech_excess": domestic_tech_excess,
            "benchmark_return_20d": benchmark_return_20d,
            "past_only_prediction": predicted,
            "residual": residual,
            "residual_z": standardized[day],
            "fit_prior_date_count": ridge.row_count,
        }
        ridge.update_one(features, raw_global_tech)
        prior_residuals.append(residual)
    return standardized, audit


def build_past_only_global_risk_residuals(
    *,
    inventory_by_date: dict[str, list[dict[str, Any]]],
    market_states: dict[str, dict[str, Any]],
    minimum_history: int = 20,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    ridge = PastOnlyRidge(feature_count=1, alpha=1.0)
    prior_residuals: list[float] = []
    standardized: dict[str, float] = {}
    audit: dict[str, dict[str, Any]] = {}
    for day in sorted(inventory_by_date):
        state = market_states.get(day)
        rows = inventory_by_date[day]
        if state is None:
            standardized[day] = 0.0
            audit[day] = {"status": "missing_global_state", "residual_z": 0.0}
            continue
        benchmark_return_20d = float(rows[0].get("benchmark_return_20d") or 0.0) if rows else 0.0
        raw_global_risk = 0.5 * (
            float(state["global_mean_return_5d"]) + float(state["global_mean_return_20d"])
        )
        features = [benchmark_return_20d]
        predicted = ridge.predict_one(features)
        residual = raw_global_risk - predicted
        if len(prior_residuals) >= minimum_history and pstdev(prior_residuals) > 1e-12:
            residual_z = (residual - mean(prior_residuals)) / pstdev(prior_residuals)
        else:
            residual_z = 0.0
        standardized[day] = max(-4.0, min(4.0, residual_z))
        audit[day] = {
            "status": "ready" if len(prior_residuals) >= minimum_history else "warmup",
            "raw_global_risk": raw_global_risk,
            "benchmark_return_20d": benchmark_return_20d,
            "global_breadth_5d": float(state["global_breadth_5d"]),
            "past_only_prediction": predicted,
            "residual": residual,
            "residual_z": standardized[day],
            "fit_prior_date_count": ridge.row_count,
        }
        ridge.update_one(features, raw_global_risk)
        prior_residuals.append(residual)
    return standardized, audit


def apply_negative_external_guard(
    picks: list[dict[str, Any]],
    *,
    global_risk_z: float,
    global_breadth_5d: float,
    tech_residual_z: float,
    variant: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    guarded = copy.deepcopy(picks)
    rank1 = next((row for row in guarded if int(float(row.get("rank") or 0)) == 1), None)
    if rank1 is None:
        return guarded, {"triggered": False, "reasons": [], "scale": 1.0}
    reasons: list[str] = []
    scale = 1.0
    global_threshold = variant.get("global_risk_z_max")
    breadth_threshold = variant.get("global_breadth_5d_max")
    if (
        global_threshold is not None
        and breadth_threshold is not None
        and global_risk_z <= float(global_threshold)
        and global_breadth_5d <= float(breadth_threshold)
    ):
        scale = min(scale, float(variant.get("global_scale") or 1.0))
        reasons.append("negative_global_risk_residual_and_weak_breadth")
    tech_threshold = variant.get("tech_risk_z_max")
    if (
        tech_threshold is not None
        and _industry_loading(rank1.get("industry_name")) > 0
        and tech_residual_z <= float(tech_threshold)
    ):
        scale = min(scale, float(variant.get("tech_scale") or 1.0))
        reasons.append("negative_global_tech_residual_for_tech_sensitive_rank1")
    rank1["portfolio_weight"] = float(rank1.get("portfolio_weight") or 1.0) * scale
    rank1["external_negative_guard_scale"] = scale
    rank1["external_negative_guard_reasons"] = reasons
    rank1["external_global_risk_z"] = global_risk_z
    rank1["external_tech_residual_z"] = tech_residual_z
    return guarded, {
        "triggered": bool(reasons),
        "reasons": reasons,
        "scale": scale,
        "rank1_symbol": rank1.get("symbol"),
        "rank1_industry": rank1.get("industry_name"),
    }


def load_official_policy_events(*, fed_path: Path, federal_register_path: Path) -> dict[str, list[dict[str, Any]]]:
    fed = json.loads(fed_path.read_text(encoding="utf-8"))
    register = json.loads(federal_register_path.read_text(encoding="utf-8"))
    events = {
        "fed": [copy.deepcopy(row) for row in fed.get("records") or []],
        "register": [copy.deepcopy(row) for row in register.get("records") or []],
    }
    for rows in events.values():
        for row in rows:
            available = datetime.fromisoformat(str(row["available_from"]))
            if available.tzinfo is None or available.utcoffset() is None:
                raise ValueError("official policy available_from must include a timezone")
        rows.sort(key=lambda row: str(row["available_from"]))
    return events


def official_policy_features_by_date(
    events: dict[str, list[dict[str, Any]]],
    *,
    decision_dates: list[date],
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for decision_day in sorted(set(decision_dates)):
        cutoff = datetime.combine(decision_day, time(23, 59, 59), tzinfo=SHANGHAI)
        fed_decay = 0.0
        for event in events.get("fed") or []:
            available = datetime.fromisoformat(str(event["available_from"])).astimezone(SHANGHAI)
            if available > cutoff or available < cutoff - timedelta(days=20):
                continue
            age_days = max((cutoff - available).total_seconds() / 86400.0, 0.0)
            fed_decay += math.pow(0.5, age_days / 5.0)
        policy_decay = 0.0
        for event in events.get("register") or []:
            available = datetime.fromisoformat(str(event["available_from"])).astimezone(SHANGHAI)
            if available > cutoff or available < cutoff - timedelta(days=40):
                continue
            payload = event.get("normalized_payload") or {}
            sectors = {str(value) for value in payload.get("sector_ids") or []}
            if not sectors.intersection({"semiconductor", "telecommunications", "industrial_supply_chain"}):
                continue
            text = f"{payload.get('headline') or ''} {payload.get('abstract') or ''}"
            if not NEGATIVE_US_POLICY_PATTERN.search(text):
                continue
            age_days = max((cutoff - available).total_seconds() / 86400.0, 0.0)
            policy_decay += math.pow(0.5, age_days / 20.0)
        result[decision_day.isoformat()] = {
            "fed_event_decay_5d": fed_decay,
            "us_policy_tech_risk_decay_20d": policy_decay,
        }
    return result


def rank1_feature_vector(
    rank1: dict[str, Any],
    *,
    market_state: dict[str, Any],
    global_risk_z: float,
    global_tech_z: float,
    official_policy: dict[str, float],
    sector_state: dict[str, Any] | None = None,
    macro_state: dict[str, Any] | None = None,
    feature_set: str,
) -> list[float]:
    core = [
        float(rank1.get("score") or 0.0),
        float(rank1.get("return_5d_percentile") or 0.0),
        float(rank1.get("return_20d_percentile") or 0.0),
        float(rank1.get("turnover_rate_percentile") or 0.0),
        float(rank1.get("amount_10d_vs_20d_percentile") or 0.0),
        float(rank1.get("distance_from_20d_high") or 0.0),
        math.log1p(max(float(rank1.get("avg_amount_20d") or 0.0), 0.0)),
        float(rank1.get("benchmark_return_20d") or 0.0),
        float(rank1.get("industry_return_20d_excess") or 0.0),
        _industry_loading(rank1.get("industry_name")),
    ]
    if feature_set == "core_only":
        return core
    if feature_set == "compressed_core_only":
        return [core[1], core[2], core[3], core[7]]
    if feature_set in {
        "compressed_core_plus_external",
        "compressed_core_plus_global_sector",
        "compressed_core_plus_global_sector_macro",
    }:
        loading = _industry_loading(rank1.get("industry_name"))
        compressed_external = [
            core[1],
            core[2],
            core[3],
            core[7],
            global_risk_z,
            loading * global_tech_z,
            loading * float(official_policy.get("us_policy_tech_risk_decay_20d") or 0.0),
        ]
        if feature_set == "compressed_core_plus_external":
            return compressed_external
        resolved_sector_state = sector_state or {}
        sector_name = SW_L1_BY_SUBINDUSTRY.get(str(rank1.get("industry_name") or ""), "")
        sector_row = (resolved_sector_state.get("by_sector_name") or {}).get(sector_name) or {}
        global_sector = [
            *compressed_external,
            float(sector_row.get("relative_5d") or 0.0),
            float(sector_row.get("relative_20d") or 0.0),
            float(sector_row.get("drawdown_20d") or 0.0),
            float(resolved_sector_state.get("breadth_5d") or 0.0),
            float(resolved_sector_state.get("breadth_20d") or 0.0),
        ]
        if feature_set == "compressed_core_plus_global_sector":
            return global_sector
        resolved_macro = macro_state or {}

        def macro_value(series_id: str, field: str) -> float:
            return float((resolved_macro.get(series_id) or {}).get(field) or 0.0)

        return [
            *global_sector,
            macro_value("VIXCLS", "value"),
            macro_value("VIXCLS", "change_5d"),
            macro_value("USDCNH_MID", "return_5d"),
            macro_value("UST_10Y", "change_5d"),
            macro_value("UST_10Y_MINUS_2Y", "value"),
            macro_value("UST_10Y_MINUS_2Y", "change_5d"),
            macro_value("SGE_AU9999", "return_5d"),
            macro_value("DCOILWTICO", "return_5d"),
        ]
    if feature_set != "core_plus_external":
        raise ValueError(f"unsupported loss gate feature set: {feature_set}")
    external = [
        global_risk_z,
        global_tech_z,
        float(market_state.get("global_breadth_5d") or 0.0),
        float(market_state.get("global_breadth_20d") or 0.0),
        float(market_state.get("global_mean_return_5d") or 0.0),
        float(market_state.get("global_mean_return_20d") or 0.0),
        float(market_state.get("tech_relative_5d") or 0.0),
        float(market_state.get("tech_relative_20d") or 0.0),
        float(official_policy.get("fed_event_decay_5d") or 0.0),
        float(official_policy.get("us_policy_tech_risk_decay_20d") or 0.0),
    ]
    return [*core, *external]


def rank1_realized_labels(snapshot: dict[str, Any], *, signal_end: date) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for row in snapshot["baseline_output"]["order_ledger"]:
        if row.get("action") != "sell" or int(float(row.get("rank") or 0)) != 1:
            continue
        signal_day = date.fromisoformat(str(row["signal_day"]))
        if signal_day > signal_end:
            continue
        key = f"{signal_day.isoformat()}|{row.get('symbol')}"
        labels[key] = {
            "signal_day": signal_day.isoformat(),
            "symbol": str(row.get("symbol") or ""),
            "label_available_day": str(row["trade_day"]),
            "realized_return": float(row.get("return") or 0.0),
            "loss_label": int(float(row.get("return") or 0.0) < 0.0),
        }
    return labels


def expanding_loss_probabilities(
    *,
    original_picks_by_date: dict[str, list[dict[str, Any]]],
    market_states: dict[str, dict[str, Any]],
    global_risk_residuals: dict[str, float],
    global_tech_residuals: dict[str, float],
    official_features: dict[str, dict[str, float]],
    sector_states: dict[str, dict[str, Any]] | None,
    macro_states: dict[str, dict[str, Any]] | None = None,
    labels: dict[str, dict[str, Any]],
    feature_set: str,
    minimum_training_trades: int = 60,
    strong_signal_by_date: dict[str, bool] | None = None,
    strong_signal_sample_weight: float = 1.0,
    minimum_strong_training_trades: int = 0,
    loss_return_threshold: float = 0.0,
    l2_penalty: float = 5.0,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    feature_by_label_key: dict[str, list[float]] = {}
    rank1_by_date: dict[str, dict[str, Any]] = {}
    for day, picks in original_picks_by_date.items():
        rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
        rank1_by_date[day] = rank1
        key = f"{day}|{rank1.get('symbol')}"
        feature_by_label_key[key] = rank1_feature_vector(
            rank1,
            market_state=market_states[day],
            global_risk_z=global_risk_residuals.get(day, 0.0),
            global_tech_z=global_tech_residuals.get(day, 0.0),
            official_policy=official_features.get(day) or {},
            sector_state=(sector_states or {}).get(day) or {},
            macro_state=(macro_states or {}).get(day) or {},
            feature_set=feature_set,
        )
    probabilities: dict[str, float | None] = {}
    fit_count_by_date: dict[str, int] = {}
    class_count_by_date: dict[str, dict[str, int]] = {}
    for day in sorted(original_picks_by_date):
        training_rows = [
            (feature_by_label_key[key], label)
            for key, label in labels.items()
            if key in feature_by_label_key and date.fromisoformat(str(label["label_available_day"])) <= date.fromisoformat(day)
        ]
        training_features = [row[0] for row in training_rows]
        training_labels = [int(float(row[1]["realized_return"]) <= loss_return_threshold) for row in training_rows]
        strong_training_count = sum(
            bool((strong_signal_by_date or {}).get(str(row[1]["signal_day"]))) for row in training_rows
        )
        training_weights = [
            strong_signal_sample_weight
            if bool((strong_signal_by_date or {}).get(str(row[1]["signal_day"])))
            else 1.0
            for row in training_rows
        ]
        fit_count_by_date[day] = len(training_rows)
        class_count_by_date[day] = {
            "loss": sum(training_labels),
            "non_loss": len(training_labels) - sum(training_labels),
        }
        if (
            len(training_rows) < minimum_training_trades
            or strong_training_count < minimum_strong_training_trades
            or len(set(training_labels)) < 2
        ):
            probabilities[day] = None
            continue
        rank1 = rank1_by_date[day]
        probabilities[day] = standardized_logistic_probability(
            training_features,
            training_labels,
            rank1_feature_vector(
                rank1,
                market_state=market_states[day],
                global_risk_z=global_risk_residuals.get(day, 0.0),
                global_tech_z=global_tech_residuals.get(day, 0.0),
                official_policy=official_features.get(day) or {},
                sector_state=(sector_states or {}).get(day) or {},
                macro_state=(macro_states or {}).get(day) or {},
                feature_set=feature_set,
            ),
            l2_penalty=l2_penalty,
            sample_weights=training_weights,
        )
    ready = [value for value in probabilities.values() if value is not None]
    if feature_set == "core_only":
        feature_names = list(CORE_LOSS_FEATURE_NAMES)
    elif feature_set == "core_plus_external":
        feature_names = [*CORE_LOSS_FEATURE_NAMES, *EXTERNAL_LOSS_FEATURE_NAMES]
    elif feature_set == "compressed_core_only":
        feature_names = list(COMPRESSED_CORE_LOSS_FEATURE_NAMES)
    elif feature_set == "compressed_core_plus_external":
        feature_names = [*COMPRESSED_CORE_LOSS_FEATURE_NAMES, *COMPRESSED_EXTERNAL_LOSS_FEATURE_NAMES]
    elif feature_set == "compressed_core_plus_global_sector":
        feature_names = [
            *COMPRESSED_CORE_LOSS_FEATURE_NAMES,
            *COMPRESSED_EXTERNAL_LOSS_FEATURE_NAMES,
            *SECTOR_EXTERNAL_LOSS_FEATURE_NAMES,
        ]
    elif feature_set == "compressed_core_plus_global_sector_macro":
        feature_names = [
            *COMPRESSED_CORE_LOSS_FEATURE_NAMES,
            *COMPRESSED_EXTERNAL_LOSS_FEATURE_NAMES,
            *SECTOR_EXTERNAL_LOSS_FEATURE_NAMES,
            *MACRO_EXTERNAL_LOSS_FEATURE_NAMES,
        ]
    else:
        raise ValueError(f"unsupported loss gate feature set: {feature_set}")
    return probabilities, {
        "feature_set": feature_set,
        "feature_names": feature_names,
        "ready_prediction_day_count": len(ready),
        "warmup_prediction_day_count": len(probabilities) - len(ready),
        "minimum_training_trades": minimum_training_trades,
        "minimum_strong_training_trades": minimum_strong_training_trades,
        "strong_signal_sample_weight": strong_signal_sample_weight,
        "loss_return_threshold": loss_return_threshold,
        "minimum_probability": min(ready, default=None),
        "maximum_probability": max(ready, default=None),
        "last_fit_count": fit_count_by_date[max(fit_count_by_date)] if fit_count_by_date else 0,
        "last_class_counts": class_count_by_date[max(class_count_by_date)] if class_count_by_date else {},
    }


def past_only_probability_percentiles(
    probabilities: dict[str, float | None],
    *,
    minimum_prior_predictions: int = 40,
) -> dict[str, float | None]:
    prior: list[float] = []
    result: dict[str, float | None] = {}
    for day in sorted(probabilities):
        probability = probabilities[day]
        if probability is None:
            result[day] = None
            continue
        if len(prior) < minimum_prior_predictions:
            result[day] = None
        else:
            result[day] = sum(value <= probability for value in prior) / len(prior)
        prior.append(float(probability))
    return result


def rerank_inventory_with_sector_residual(
    rows: list[dict[str, Any]],
    *,
    external_residual_z: float,
    weight: float,
    cap: float = DEFAULT_CAP,
) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: int(float(row.get("rank") or 999)))
    core_scores = [float(row.get("score") or 0.0) for row in ordered]
    external_values = [_industry_loading(row.get("industry_name")) * external_residual_z for row in ordered]
    core_z = _z_scores(core_scores)
    external_z = _z_scores(external_values)
    reranked: list[dict[str, Any]] = []
    for row, core_value, external_value in zip(ordered, core_z, external_z, strict=True):
        contribution = max(-cap, min(cap, float(weight) * external_value))
        reranked.append(
            {
                **row,
                "core_score_unmodified": float(row.get("score") or 0.0),
                "external_sector_residual_z": external_residual_z,
                "external_sector_loading": _industry_loading(row.get("industry_name")),
                "external_sector_contribution": contribution,
                "external_adjusted_score": core_value + contribution,
            }
        )
    reranked.sort(key=lambda row: (-float(row["external_adjusted_score"]), -float(row["core_score_unmodified"])))
    return [{**row, "rank": rank} for rank, row in enumerate(reranked, start=1)]


def _selected_picks_for_weight(
    *,
    original_picks_by_date: dict[str, list[dict[str, Any]]],
    inventory_by_date: dict[str, list[dict[str, Any]]],
    residuals: dict[str, float],
    weight: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    adjusted_inventory: list[dict[str, Any]] = []
    changed_dates = 0
    changed_slots = 0
    changed_tech_slots = 0
    for day in sorted(inventory_by_date):
        original = sorted(original_picks_by_date[day], key=lambda row: int(float(row.get("rank") or 999)))
        if weight == 0.0:
            reranked = copy.deepcopy(original)
        else:
            reranked = rerank_inventory_with_sector_residual(
                original,
                external_residual_z=residuals.get(day, 0.0),
                weight=weight,
            )
        adjusted_inventory.extend(copy.deepcopy(inventory_by_date[day]))
        top = reranked[: len(original)]
        day_changed = False
        for index, candidate in enumerate(top):
            template = original[index]
            rebuilt = {
                **candidate,
                "rank": index + 1,
                "portfolio_weight": float(template.get("portfolio_weight") or 1.0),
                "rank_weight_multiplier": float(template.get("rank_weight_multiplier") or 0.0),
            }
            selected.append(rebuilt)
            if str(rebuilt.get("symbol")) != str(template.get("symbol")):
                changed_slots += 1
                changed_tech_slots += int(_industry_loading(rebuilt.get("industry_name")) > 0)
                day_changed = True
        changed_dates += int(day_changed)
    return selected, adjusted_inventory, {
        "changed_date_count_vs_lambda_zero": changed_dates,
        "changed_symbol_rank_slot_count_vs_lambda_zero": changed_slots,
        "changed_to_tech_or_adjacent_slot_count": changed_tech_slots,
    }


def _candidate_run(
    *,
    snapshot: dict[str, Any],
    selected_picks: list[dict[str, Any]],
    weight: float,
) -> dict[str, Any]:
    trial = copy.deepcopy(snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0])
    trial["selected_top_k_picks_by_date"] = selected_picks
    material = {
        "source_artifact_id": snapshot["inputs"]["candidate_run"].get("artifact_id"),
        "trial_id": snapshot["trial_id"],
        "weight": weight,
        "selected_pick_digest": stable_digest(selected_picks),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()
    return {"artifact_id": f"global-sector-state-candidate-{digest[:16]}", "trial_diagnostics": [trial]}


def _segment_metrics(result: dict[str, Any], *, start: date | None, end: date) -> dict[str, Any]:
    nav_rows = [
        row
        for row in result["nav_rows"]
        if (start is None or date.fromisoformat(str(row["day"])) >= start)
        and date.fromisoformat(str(row["day"])) <= end
    ]
    if not nav_rows:
        return {metric: None for metric in GATE_METRICS}
    first_day = date.fromisoformat(str(nav_rows[0]["day"]))
    prior_rows = [
        row
        for row in result["nav_rows"]
        if date.fromisoformat(str(row["day"])) < first_day
    ]
    starting_nav = float(prior_rows[-1]["nav_cny"]) if prior_rows else float(result["summary"]["initial_cash_cny"])
    ending_nav = float(nav_rows[-1]["nav_cny"])
    total_return = ending_nav / starting_nav - 1.0
    elapsed_days = max((date.fromisoformat(str(nav_rows[-1]["day"])) - first_day).days, 1)
    annualized = math.pow(max(ending_nav / starting_nav, 1e-12), 365.25 / elapsed_days) - 1.0
    peak = starting_nav
    max_drawdown = 0.0
    for row in nav_rows:
        nav = float(row["nav_cny"])
        peak = max(peak, nav)
        max_drawdown = min(max_drawdown, nav / peak - 1.0)
    months = [
        row
        for row in result["monthly_returns"]
        if (start is None or str(row["month"]) >= start.strftime("%Y-%m"))
        and str(row["month"]) <= end.strftime("%Y-%m")
    ]
    orders = [
        row
        for row in result["order_ledger"]
        if (start is None or date.fromisoformat(str(row["signal_day"])) >= start)
        and date.fromisoformat(str(row["signal_day"])) <= end
    ]
    buys = [row for row in orders if row.get("action") == "buy"]
    skips = [row for row in orders if row.get("action") == "skip"]
    signal_days = {str(row["signal_day"]) for row in orders}
    skipped_signal_days = {str(row["signal_day"]) for row in skips}
    return {
        "from": first_day.isoformat(),
        "to": str(nav_rows[-1]["day"]),
        "total_return": total_return,
        "annualized_return": annualized,
        "max_drawdown": max_drawdown,
        "negative_month_count": sum(float(row["return"]) < 0 for row in months),
        "worst_monthly_return": min((float(row["return"]) for row in months), default=0.0),
        "skipped_order_rate": len(skips) / max(len(skips) + len(buys), 1),
        "skipped_signal_rate": len(skipped_signal_days) / max(len(signal_days), 1),
        "max_single_symbol_exposure_pct": max(
            (float(row["max_single_symbol_exposure_pct"]) for row in nav_rows), default=0.0
        ),
        "mean_invested_ratio": mean(float(row["invested_ratio"]) for row in nav_rows),
        "ending_nav_cny": ending_nav,
        "buy_order_count": len(buys),
        "skip_order_count": len(skips),
    }


def _monthly_delta_summary(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    start: date,
    end: date,
) -> dict[str, float | int]:
    candidate_by_month = {
        str(row["month"]): float(row["return"])
        for row in candidate["monthly_returns"]
        if start.strftime("%Y-%m") <= str(row["month"]) <= end.strftime("%Y-%m")
    }
    baseline_by_month = {
        str(row["month"]): float(row["return"])
        for row in baseline["monthly_returns"]
        if start.strftime("%Y-%m") <= str(row["month"]) <= end.strftime("%Y-%m")
    }
    months = sorted(set(candidate_by_month) & set(baseline_by_month))
    deltas = [candidate_by_month[month] - baseline_by_month[month] for month in months]
    return {
        "month_count": len(deltas),
        "mean_monthly_return_delta": mean(deltas) if deltas else 0.0,
        "monthly_delta_standard_error": pstdev(deltas) / math.sqrt(len(deltas)) if len(deltas) > 1 else 0.0,
    }


def _buy_order_delta(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    start: date,
    end: date,
) -> dict[str, list[dict[str, Any]]]:
    def rows_by_key(account: dict[str, Any]) -> dict[tuple[str, str, str, int], dict[str, Any]]:
        return {
            (
                str(row["signal_day"]),
                str(row["trade_day"]),
                str(row["symbol"]),
                int(row["rank"]),
            ): row
            for row in account["order_ledger"]
            if row.get("action") == "buy" and start <= date.fromisoformat(str(row["trade_day"])) <= end
        }

    candidate_rows = rows_by_key(candidate)
    baseline_rows = rows_by_key(baseline)
    fields = ("signal_day", "trade_day", "symbol", "stock_name", "rank", "shares", "price", "cash_spent_cny")

    def project(row: dict[str, Any]) -> dict[str, Any]:
        return {field: row.get(field) for field in fields}

    shared = sorted(set(candidate_rows) & set(baseline_rows))
    return {
        "candidate_only": [project(candidate_rows[key]) for key in sorted(set(candidate_rows) - set(baseline_rows))],
        "baseline_only": [project(baseline_rows[key]) for key in sorted(set(baseline_rows) - set(candidate_rows))],
        "changed_share_count": [
            {
                **project(candidate_rows[key]),
                "baseline_shares": baseline_rows[key].get("shares"),
            }
            for key in shared
            if candidate_rows[key].get("shares") != baseline_rows[key].get("shares")
        ],
    }


def _non_degrade(candidate: dict[str, Any], baseline: dict[str, Any], *, tolerance: float = 1e-12) -> dict[str, Any]:
    failures: list[str] = []
    comparisons: dict[str, Any] = {}
    for metric in GATE_METRICS:
        observed = candidate.get(metric)
        frontier = baseline.get(metric)
        if observed is None or frontier is None:
            passed = False
        elif metric in HIGHER_IS_BETTER:
            passed = float(observed) + tolerance >= float(frontier)
        else:
            passed = float(observed) <= float(frontier) + tolerance
        comparisons[metric] = {"candidate": observed, "baseline": frontier, "passed": passed}
        if not passed:
            failures.append(metric)
    return {"passed": not failures, "failed_metrics": failures, "comparisons": comparisons}


def _standout(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    relative_return = (
        (float(candidate["total_return"]) - float(baseline["total_return"]))
        / max(abs(float(baseline["total_return"])), 1e-12)
    )
    fewer_negative_months = int(baseline["negative_month_count"]) - int(candidate["negative_month_count"])
    drawdown_improved = float(candidate["max_drawdown"]) > float(baseline["max_drawdown"])
    passed = relative_return >= 0.10 or (fewer_negative_months >= 1 and drawdown_improved)
    return {
        "passed": passed,
        "relative_total_return_improvement": relative_return,
        "negative_month_reduction": fewer_negative_months,
        "drawdown_improved": drawdown_improved,
    }


def run_global_sector_state_account_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date = DEFAULT_SIGNAL_END,
    weights: tuple[float, ...] = DEFAULT_LAMBDAS,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_outcome_evaluation":
        raise ValueError("ablation design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    market_snapshot = load_research_snapshot(global_market_snapshot_path)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    if set(original_picks_by_date) != set(inventory_by_date):
        raise ValueError("selected picks and candidate inventory date coverage differ")
    lambda_zero_mismatches: list[dict[str, Any]] = []
    for day in sorted(original_picks_by_date):
        original_symbols = {str(row.get("symbol")) for row in original_picks_by_date[day]}
        inventory_symbols = {str(row.get("symbol")) for row in inventory_by_date[day]}
        if not original_symbols.issubset(inventory_symbols):
            lambda_zero_mismatches.append(
                {
                    "as_of_date": day,
                    "missing_selected_symbols": sorted(original_symbols - inventory_symbols),
                }
            )
    if lambda_zero_mismatches:
        raise ValueError("frozen selections are missing from the candidate inventory")
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    market_states = market_state_by_decision_date(market_snapshot["records"], decision_dates=decision_dates)
    residuals, residual_audit = build_past_only_sector_residuals(
        inventory_by_date=inventory_by_date,
        market_states=market_states,
    )
    results: list[dict[str, Any]] = []
    baseline_segments: dict[str, Any] | None = None
    for weight in weights:
        selected, adjusted_inventory, change_summary = _selected_picks_for_weight(
            original_picks_by_date=original_picks_by_date,
            inventory_by_date=inventory_by_date,
            residuals=residuals,
            weight=float(weight),
        )
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=float(weight))
        replay = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=adjusted_inventory,
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )
        account = replay["results"][0]
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "final_untouched": _segment_metrics(account, start=DEFAULT_FINAL_START, end=signal_end),
            "full": _segment_metrics(account, start=None, end=signal_end),
        }
        if weight == 0.0:
            baseline_segments = segments
        results.append(
            {
                "lambda": float(weight),
                "change_summary": change_summary,
                "segments": segments,
                "account_summary": account["summary"],
            }
        )
    if baseline_segments is None:
        raise ValueError("lambda zero baseline is required")
    tuning_candidates: list[dict[str, Any]] = []
    for row in results:
        row["gates"] = {
            segment: _non_degrade(row["segments"][segment], baseline_segments[segment])
            for segment in ("tuning", "validation", "full")
        }
        row["standout"] = {
            segment: _standout(row["segments"][segment], baseline_segments[segment])
            for segment in ("tuning", "validation", "full")
        }
        if row["lambda"] > 0 and row["gates"]["tuning"]["passed"] and row["gates"]["validation"]["passed"]:
            tuning_candidates.append(row)
    selected = min(tuning_candidates, key=lambda row: float(row["lambda"])) if tuning_candidates else None
    final_gate = None
    final_standout = None
    if selected is not None:
        final_gate = _non_degrade(selected["segments"]["final_untouched"], baseline_segments["final_untouched"])
        final_standout = _standout(selected["segments"]["final_untouched"], baseline_segments["final_untouched"])
    status = (
        "candidate_passed_all_gates"
        if selected is not None and final_gate and final_gate["passed"] and final_standout and final_standout["passed"]
        else "no_candidate_cleared_full_objective"
    )
    material = {
        "artifact_type": "global_sector_state_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "claim_ceiling": "research_only_account_replay_provisional_global_source",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_global_market_digest": market_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "provider_revision_lineage_missing": True,
        "promotion_blocker": market_snapshot["promotion_blocker"],
        "signal_date_range": {"from": min(inventory_by_date), "to": max(inventory_by_date)},
        "signal_day_count": len(inventory_by_date),
        "lambda_zero_reproduction": {
            "passed": not lambda_zero_mismatches,
            "mismatch_count": len(lambda_zero_mismatches),
        },
        "market_state_quality": {
            "requested_signal_days": len(inventory_by_date),
            "ready_signal_days": sum(day in market_states for day in inventory_by_date),
            "missing_signal_days": sum(day not in market_states for day in inventory_by_date),
            "future_available_at_violations": 0,
            "warmup_or_missing_residual_days": sum(
                row["status"] != "ready" for row in residual_audit.values()
            ),
        },
        "selection": {
            "selected_lambda_before_final_holdout": None if selected is None else selected["lambda"],
            "final_holdout_gate": final_gate,
            "final_holdout_standout": final_standout,
            "decision": status,
        },
        "baseline_segments": baseline_segments,
        "results": results,
        "residual_audit_digest": stable_digest(residual_audit),
        "v3_signal_changed": False,
    }
    artifact_digest = stable_digest(material)
    return {
        "artifact_id": f"global-sector-state-account-ablation-{artifact_digest[:16]}",
        **material,
        "content_digest": artifact_digest,
    }


def run_global_risk_guard_account_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date = DEFAULT_SIGNAL_END,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round2_outcome_evaluation":
        raise ValueError("round2 guard design must be frozen before outcome evaluation")
    variants = design.get("variants") or []
    if variants != list(DEFAULT_GLOBAL_RISK_GUARD_VARIANTS):
        raise ValueError("round2 guard variants differ from the registered implementation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    market_snapshot = load_research_snapshot(global_market_snapshot_path)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    market_states = market_state_by_decision_date(market_snapshot["records"], decision_dates=decision_dates)
    tech_residuals, tech_audit = build_past_only_sector_residuals(
        inventory_by_date=inventory_by_date,
        market_states=market_states,
    )
    global_residuals, global_audit = build_past_only_global_risk_residuals(
        inventory_by_date=inventory_by_date,
        market_states=market_states,
    )

    def replay_for_variant(variant: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        trigger_count = 0
        global_trigger_count = 0
        tech_trigger_count = 0
        affected_symbols: set[str] = set()
        for day in sorted(original_picks_by_date):
            picks = original_picks_by_date[day]
            if variant is None:
                guarded = copy.deepcopy(picks)
                audit = {"triggered": False, "reasons": [], "scale": 1.0}
            else:
                state = market_states[day]
                guarded, audit = apply_negative_external_guard(
                    picks,
                    global_risk_z=global_residuals.get(day, 0.0),
                    global_breadth_5d=float(state["global_breadth_5d"]),
                    tech_residual_z=tech_residuals.get(day, 0.0),
                    variant=variant,
                )
            selected.extend(guarded)
            if audit["triggered"]:
                trigger_count += 1
                affected_symbols.add(str(audit.get("rank1_symbol") or ""))
                global_trigger_count += int("negative_global_risk_residual_and_weak_breadth" in audit["reasons"])
                tech_trigger_count += int(
                    "negative_global_tech_residual_for_tech_sensitive_rank1" in audit["reasons"]
                )
        variant_id = "lambda_zero_v3" if variant is None else str(variant["variant_id"])
        candidate_run = _candidate_run(
            snapshot=snapshot,
            selected_picks=selected,
            weight=0.0 if variant is None else float(variants.index(variant) + 1),
        )
        candidate_run["artifact_id"] = f"global-risk-guard-{variant_id}"
        replay = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )
        return replay["results"][0], {
            "triggered_signal_day_count": trigger_count,
            "global_trigger_count": global_trigger_count,
            "tech_trigger_count": tech_trigger_count,
            "affected_rank1_symbol_count": len(affected_symbols - {""}),
        }

    baseline_account, baseline_trigger = replay_for_variant(None)
    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_final": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    result_rows: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    accounts_by_variant: dict[str, dict[str, Any]] = {}
    for variant in variants:
        account, trigger_summary = replay_for_variant(variant)
        variant_id = str(variant["variant_id"])
        accounts_by_variant[variant_id] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_final": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        gates = {
            segment: _non_degrade(segments[segment], baseline_segments[segment])
            for segment in segments
        }
        standout = {
            segment: _standout(segments[segment], baseline_segments[segment])
            for segment in segments
        }
        row = {
            "variant": variant,
            "trigger_summary": trigger_summary,
            "segments": segments,
            "gates": gates,
            "standout": standout,
        }
        result_rows.append(row)
        if gates["tuning"]["passed"] and gates["validation"]["passed"]:
            eligible.append(row)
    selected = max(
        eligible,
        key=lambda row: (
            float(row["segments"]["validation"]["annualized_return"]),
            float(row["segments"]["validation"]["max_drawdown"]),
        ),
        default=None,
    )
    final_readout: dict[str, Any] | None = None
    if selected is not None:
        selected_id = str(selected["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        selected_final = _segment_metrics(accounts_by_variant[selected_id], start=DEFAULT_FINAL_START, end=signal_end)
        final_readout = {
            "variant_id": selected_id,
            "baseline": baseline_final,
            "candidate": selected_final,
            "gate": _non_degrade(selected_final, baseline_final),
            "standout": _standout(selected_final, baseline_final),
        }
    passed = bool(
        selected is not None
        and final_readout
        and final_readout["gate"]["passed"]
        and final_readout["standout"]["passed"]
    )
    material = {
        "artifact_type": "global_risk_guard_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "round": 2,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_account_replay_provisional_global_source",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_global_market_digest": market_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "signal_date_range": {"from": min(inventory_by_date), "to": max(inventory_by_date)},
        "signal_day_count": len(inventory_by_date),
        "baseline_trigger_summary": baseline_trigger,
        "baseline_segments_pre_final": baseline_segments,
        "results_pre_final": result_rows,
        "selection_before_final": None if selected is None else selected["variant"]["variant_id"],
        "final_untouched_readout": final_readout,
        "market_state_quality": {
            "requested_signal_days": len(inventory_by_date),
            "ready_signal_days": sum(day in market_states for day in inventory_by_date),
            "future_available_at_violations": 0,
            "tech_residual_audit_digest": stable_digest(tech_audit),
            "global_residual_audit_digest": stable_digest(global_audit),
        },
        "provider_revision_lineage_missing": True,
        "promotion_blocker": market_snapshot["promotion_blocker"],
        "v3_signal_changed": False,
    }
    artifact_digest = stable_digest(material)
    return {
        "artifact_id": f"global-risk-guard-account-ablation-{artifact_digest[:16]}",
        **material,
        "content_digest": artifact_digest,
    }


def run_external_loss_gate_account_ablation(
    *,
    execution_snapshot_path: Path,
    global_market_snapshot_path: Path,
    sector_market_snapshot_path: Path | None = None,
    macro_market_snapshot_path: Path | None = None,
    fed_policy_path: Path,
    federal_register_path: Path,
    design_path: Path,
    signal_end: date = DEFAULT_SIGNAL_END,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    supported_statuses = {
        "frozen_before_round3_outcome_evaluation": 3,
        "frozen_before_round4_outcome_evaluation": 4,
        "frozen_before_round5_outcome_evaluation": 5,
        "frozen_before_round6_outcome_evaluation": 6,
        "frozen_before_round7_outcome_evaluation": 7,
        "frozen_before_round8_outcome_evaluation": 8,
        "frozen_before_round9_outcome_evaluation": 9,
        "frozen_before_round10_outcome_evaluation": 10,
        "frozen_before_round11_outcome_evaluation": 11,
        "frozen_before_round12_outcome_evaluation": 12,
        "frozen_before_round13_outcome_evaluation": 13,
        "frozen_before_round20_outcome_evaluation": 20,
    }
    if design.get("status") not in supported_statuses:
        raise ValueError("loss gate design must be frozen before outcome evaluation")
    round_number = supported_statuses[str(design["status"])]
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    market_snapshot = load_research_snapshot(global_market_snapshot_path)
    sector_snapshot = (
        None if sector_market_snapshot_path is None else load_sector_research_snapshot(sector_market_snapshot_path)
    )
    macro_snapshot = (
        None if macro_market_snapshot_path is None else load_macro_research_snapshot(macro_market_snapshot_path)
    )
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original_picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    market_states = market_state_by_decision_date(market_snapshot["records"], decision_dates=decision_dates)
    if set(market_states) != set(inventory_by_date):
        raise ValueError("global market state is incomplete for round3 signal dates")
    sector_states: dict[str, dict[str, Any]] = {}
    sector_mapping_audit: dict[str, Any] | None = None
    if sector_snapshot is not None:
        sector_states = sector_state_by_decision_date(
            sector_snapshot["normalized"]["records"],
            decision_dates=decision_dates,
        )
        sector_mapping_audit = sector_mapping_coverage(
            [str(row.get("industry_name") or "") for rows in inventory_by_date.values() for row in rows]
        )
        if float(sector_mapping_audit["mapped_row_rate"]) < 0.99:
            raise ValueError(f"SW L1 mapping coverage below 99%: {sector_mapping_audit}")
        if set(sector_states) != set(inventory_by_date):
            raise ValueError("SW L1 sector state is incomplete for signal dates")
    if any(str(row["feature_set"]) == "compressed_core_plus_global_sector" for row in design["variants"]):
        if sector_snapshot is None:
            raise ValueError("sector-market snapshot is required by the selected feature set")
    macro_feature_set = "compressed_core_plus_global_sector_macro"
    if any(str(row["feature_set"]) == macro_feature_set for row in design["variants"]):
        if sector_snapshot is None or macro_snapshot is None:
            raise ValueError("sector and macro snapshots are required by the macro feature set")
    macro_states: dict[str, dict[str, Any]] = {}
    if macro_snapshot is not None:
        macro_states = macro_state_by_decision_date(macro_snapshot["records"], decision_dates=decision_dates)
        required_macro_series = {
            "DCOILWTICO",
            "SGE_AU9999",
            "USDCNH_MID",
            "UST_10Y",
            "UST_10Y_MINUS_2Y",
            "VIXCLS",
        }
        incomplete = [
            day
            for day in inventory_by_date
            if day not in macro_states or not required_macro_series.issubset(macro_states[day])
        ]
        if incomplete:
            raise ValueError(f"macro state is incomplete for signal dates: {incomplete[:3]}")
    tech_residuals, tech_audit = build_past_only_sector_residuals(
        inventory_by_date=inventory_by_date,
        market_states=market_states,
    )
    global_residuals, global_audit = build_past_only_global_risk_residuals(
        inventory_by_date=inventory_by_date,
        market_states=market_states,
    )
    official_events = load_official_policy_events(
        fed_path=fed_policy_path,
        federal_register_path=federal_register_path,
    )
    official_features = official_policy_features_by_date(official_events, decision_dates=decision_dates)
    labels = rank1_realized_labels(snapshot, signal_end=signal_end)
    model_config = design.get("model") or {}
    minimum_training_trades = int(model_config.get("minimum_completed_training_trades") or 60)
    l2_penalty = float(model_config.get("l2_penalty") or 5.0)
    loss_return_threshold = float(model_config.get("loss_return_threshold") or 0.0)
    quality_overlay = snapshot["inputs"]["baseline_config"].get("rank1_quality_overlay") or {}
    strong_signal_by_date = {
        day: _rank1_quality_scale(
            next(row for row in picks if int(float(row.get("rank") or 0)) == 1),
            overlay=quality_overlay,
        )
        > 1.0
        for day, picks in original_picks_by_date.items()
    }
    feature_sets = sorted({str(row["feature_set"]) for row in design["variants"]})
    probabilities_by_feature_set: dict[str, dict[str, float | None]] = {}
    percentiles_by_feature_set: dict[str, dict[str, float | None]] = {}
    prediction_audit_by_feature_set: dict[str, dict[str, Any]] = {}
    for feature_set in feature_sets:
        probabilities, prediction_audit = expanding_loss_probabilities(
            original_picks_by_date=original_picks_by_date,
            market_states=market_states,
            global_risk_residuals=global_residuals,
            global_tech_residuals=tech_residuals,
            official_features=official_features,
            sector_states=sector_states,
            macro_states=macro_states,
            labels=labels,
            feature_set=feature_set,
            minimum_training_trades=minimum_training_trades,
            strong_signal_by_date=strong_signal_by_date,
            strong_signal_sample_weight=float(model_config.get("strong_signal_sample_weight") or 1.0),
            minimum_strong_training_trades=int(model_config.get("minimum_completed_strong_training_trades") or 0),
            loss_return_threshold=loss_return_threshold,
            l2_penalty=l2_penalty,
        )
        probabilities_by_feature_set[feature_set] = probabilities
        percentiles_by_feature_set[feature_set] = past_only_probability_percentiles(
            probabilities,
            minimum_prior_predictions=int(model_config.get("minimum_prior_live_predictions_for_quantile") or 40),
        )
        prediction_audit_by_feature_set[feature_set] = prediction_audit

    baseline_buy_keys: set[tuple[str, str, int]] = set()
    baseline_buy_symbols_by_slot: dict[tuple[str, int], set[str]] = defaultdict(set)

    def replay_variant(variant: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        triggered = 0
        triggered_dates: list[dict[str, Any]] = []
        suppressed_new_fill_dates: list[dict[str, Any]] = []
        probability_rows = (
            probabilities_by_feature_set[str(variant["feature_set"])]
            if variant is not None
            else next(iter(probabilities_by_feature_set.values()))
        )
        for day in sorted(original_picks_by_date):
            picks = copy.deepcopy(original_picks_by_date[day])
            if variant is not None and variant.get("enforce_shadow_baseline_buy_eligibility_all_orders"):
                for pick in picks:
                    slot = (day, int(float(pick.get("rank") or 0)))
                    pick["shadow_baseline_buy_symbols"] = sorted(baseline_buy_symbols_by_slot.get(slot, set()))
            probability = None if variant is None else probability_rows.get(day)
            percentile = (
                None
                if variant is None
                else percentiles_by_feature_set[str(variant["feature_set"])].get(day)
            )
            probability_trigger = (
                probability is not None
                and variant is not None
                and variant.get("loss_probability_min") is not None
                and probability >= float(variant["loss_probability_min"])
            )
            percentile_trigger = (
                percentile is not None
                and variant is not None
                and variant.get("risk_percentile_min") is not None
                and percentile >= float(variant["risk_percentile_min"])
            )
            if probability_trigger or percentile_trigger:
                rank1 = next(row for row in picks if int(float(row.get("rank") or 0)) == 1)
                baseline_buy_key = (day, str(rank1.get("symbol") or ""), 1)
                baseline_slot_has_buy = bool(baseline_buy_symbols_by_slot.get((day, 1)))
                if (
                    variant.get("must_preserve_baseline_buy_eligibility")
                    and baseline_buy_key not in baseline_buy_keys
                    and not baseline_slot_has_buy
                ):
                    suppressed_new_fill_dates.append(
                        {
                            "signal_date": day,
                            "rank1_symbol": str(rank1.get("symbol") or ""),
                            "loss_probability": probability,
                            "past_only_percentile": percentile,
                        }
                    )
                    selected.extend(picks)
                    continue
                rows_to_scale = [rank1]
                scale = float(variant.get("scale") or 1.0)
                if variant.get("target_scope") in {
                    "strong_quality_overlay_only",
                    "strong_rank1_overlay_only",
                }:
                    overlay = snapshot["inputs"]["baseline_config"].get("rank1_quality_overlay") or {}
                    quality_scale = _rank1_quality_scale(rank1, overlay=overlay)
                    if quality_scale <= 1.0:
                        selected.extend(picks)
                        continue
                    neutralize_fraction = float(variant.get("neutralize_fraction") or 1.0)
                    scale = 1.0 / (1.0 + neutralize_fraction * (quality_scale - 1.0))
                    if variant.get("target_scope") == "strong_quality_overlay_only":
                        rows_to_scale = picks
                for row in rows_to_scale:
                    row["portfolio_weight"] = float(row.get("portfolio_weight") or 1.0) * scale
                    row["external_loss_gate_probability"] = probability
                    row["external_loss_gate_past_only_percentile"] = percentile
                    row["external_loss_gate_scale"] = scale
                    row["external_loss_gate_feature_set"] = variant["feature_set"]
                triggered += 1
                triggered_dates.append(
                    {
                        "signal_date": day,
                        "rank1_symbol": str(rank1.get("symbol") or ""),
                        "rank1_industry": str(rank1.get("industry_name") or ""),
                        "loss_probability": probability,
                        "past_only_percentile": percentile,
                        "applied_scale": scale,
                        "target_scope": str(variant.get("target_scope") or "rank1"),
                    }
                )
            selected.extend(picks)
        variant_id = "lambda_zero_v3" if variant is None else str(variant["variant_id"])
        candidate_run = _candidate_run(
            snapshot=snapshot,
            selected_picks=selected,
            weight=0.0 if variant is None else float((design["variants"]).index(variant) + 1),
        )
        candidate_run["artifact_id"] = f"external-loss-gate-{variant_id}"
        candidate_config = copy.deepcopy(snapshot["inputs"]["baseline_config"])
        if variant is not None and variant.get("market_value_concentration_rebalance_threshold") is not None:
            rebalance = copy.deepcopy(candidate_config.get("market_value_concentration_rebalance") or {})
            rebalance["threshold"] = float(variant["market_value_concentration_rebalance_threshold"])
            rebalance.setdefault("scope", "all_positions")
            rebalance.setdefault("cooldown_trading_days", 0)
            rebalance.setdefault("execution_timing", "after_scheduled_exits_entries_at_close")
            rebalance.setdefault("sell_cost_bps", 25.0)
            rebalance.setdefault("board_lot_size", 100)
            candidate_config["market_value_concentration_rebalance"] = rebalance
        replay = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[candidate_config],
            **snapshot["inputs"]["account_profile"],
        )
        return replay["results"][0], {
            "triggered_signal_day_count": triggered,
            "triggered_signal_dates": triggered_dates,
            "suppressed_new_fill_signal_dates": suppressed_new_fill_dates,
            "suppressed_new_fill_signal_day_count": len(suppressed_new_fill_dates),
            "ready_probability_day_count": sum(value is not None for value in probability_rows.values()),
            "ready_percentile_day_count": sum(
                value is not None
                for value in (
                    percentiles_by_feature_set[str(variant["feature_set"])].values()
                    if variant is not None
                    else ()
                )
            ),
        }

    baseline_account, _baseline_audit = replay_variant(None)
    baseline_buy_keys.update(
        (
            str(row["signal_day"]),
            str(row["symbol"]),
            int(row["rank"]),
        )
        for row in baseline_account["order_ledger"]
        if row.get("action") == "buy"
    )
    for row in baseline_account["order_ledger"]:
        if row.get("action") == "buy":
            baseline_buy_symbols_by_slot[(str(row["signal_day"]), int(row["rank"]))].add(str(row["symbol"]))
    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_final": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    result_rows: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, Any]] = {}
    core_control_validation_return: float | None = None
    for variant in design["variants"]:
        account, trigger_audit = replay_variant(variant)
        variant_id = str(variant["variant_id"])
        accounts[variant_id] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_final": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        gates = {
            segment: _non_degrade(segments[segment], baseline_segments[segment])
            for segment in segments
        }
        if variant.get("control_only"):
            core_control_validation_return = float(segments["validation"]["total_return"])
        result_rows.append(
            {
                "variant": variant,
                "trigger_audit": trigger_audit,
                "segments": segments,
                "gates": gates,
                "standout": {
                    segment: _standout(segments[segment], baseline_segments[segment])
                    for segment in segments
                },
                "validation_monthly_delta": _monthly_delta_summary(
                    account,
                    baseline_account,
                    start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                    end=DEFAULT_VALIDATION_END,
                ),
            }
        )
    eligible = [
        row
        for row in result_rows
        if not row["variant"].get("control_only")
        and int(row["trigger_audit"]["triggered_signal_day_count"]) > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
        and (
            core_control_validation_return is None
            or float(row["segments"]["validation"]["total_return"]) >= core_control_validation_return
        )
    ]
    if round_number >= 7 and eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        one_se_floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        stable_plateau = [
            row
            for row in eligible
            if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= one_se_floor
        ]
        selected = min(
            stable_plateau,
            key=lambda row: (
                float(row["variant"].get("neutralize_fraction") or 1.0),
                -float(row["variant"].get("risk_percentile_min") or 0.0),
                -float(row["variant"].get("market_value_concentration_rebalance_threshold") or 0.0),
            ),
        )
    else:
        selected = max(
            eligible,
            key=lambda row: (
                float(row["segments"]["validation"]["annualized_return"]),
                float(row["segments"]["validation"]["max_drawdown"]),
            ),
            default=None,
        )
    final_readout: dict[str, Any] | None = None
    if selected is not None:
        selected_id = str(selected["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[selected_id], start=DEFAULT_FINAL_START, end=signal_end)
        final_readout = {
            "variant_id": selected_id,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(
                accounts[selected_id],
                baseline_account,
                start=DEFAULT_FINAL_START,
                end=signal_end,
            ),
        }
    passed = bool(
        selected is not None
        and final_readout
        and final_readout["gate"]["passed"]
        and final_readout["standout"]["passed"]
    )
    material = {
        "artifact_type": "external_loss_gate_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "round": round_number,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_constrained_expanding_logistic_account_replay",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_global_market_digest": market_snapshot["content_digest"],
        "source_sector_market_digest": None if sector_snapshot is None else sector_snapshot["content_digest"],
        "source_macro_market_digest": None if macro_snapshot is None else macro_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "signal_day_count": len(inventory_by_date),
        "rank1_realized_label_count": len(labels),
        "rank1_loss_label_count": sum(
            int(float(row["realized_return"]) <= loss_return_threshold) for row in labels.values()
        ),
        "loss_return_threshold": loss_return_threshold,
        "prediction_audit": {**prediction_audit_by_feature_set, "future_label_violations": 0},
        "baseline_segments_pre_final": baseline_segments,
        "results_pre_final": result_rows,
        "selection_before_final": None if selected is None else selected["variant"]["variant_id"],
        "final_untouched_readout": final_readout,
        "final_readout_status": (
            "reused_extended_evaluation_not_untouched"
            if round_number >= 20
            else "preregistered_untouched_for_this_round"
        ),
        "external_data_audit": {
            "global_risk_residual_digest": stable_digest(global_audit),
            "global_tech_residual_digest": stable_digest(tech_audit),
            "fed_event_count": len(official_events["fed"]),
            "federal_register_event_count": len(official_events["register"]),
            "official_feature_digest": stable_digest(official_features),
            "sector_state_digest": None if not sector_states else stable_digest(sector_states),
            "sector_mapping_audit": sector_mapping_audit,
            "macro_state_digest": None if not macro_states else stable_digest(macro_states),
        },
        "provider_revision_lineage_missing": True,
        "promotion_blocker": market_snapshot["promotion_blocker"],
        "v3_signal_changed": False,
    }
    artifact_digest = stable_digest(material)
    return {
        "artifact_id": f"external-loss-gate-account-ablation-{artifact_digest[:16]}",
        **material,
        "content_digest": artifact_digest,
    }


def write_ablation_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("ablation result content digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_past_only_sw_sector_residuals(
    *,
    picks_by_date: dict[str, list[dict[str, Any]]],
    sector_states: dict[str, dict[str, Any]],
    alpha: float = 5.0,
    minimum_history: int = 30,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    ridge = PastOnlyRidge(feature_count=3, alpha=alpha)
    prior_residuals: list[float] = []
    result: dict[str, dict[str, float]] = {}
    warmup_rows = 0
    for day in sorted(picks_by_date):
        state = sector_states[day]
        day_rows: list[tuple[str, list[float], float, float]] = []
        result[day] = {}
        for row in picks_by_date[day]:
            sector_name = SW_L1_BY_SUBINDUSTRY[str(row.get("industry_name") or "")]
            sector_row = state["by_sector_name"][sector_name]
            features = [
                float(row.get("industry_return_20d_excess") or 0.0),
                float(row.get("benchmark_return_20d") or 0.0),
                float(row.get("return_20d_percentile") or 0.0),
            ]
            target = float(sector_row["relative_20d"])
            raw_residual = target - ridge.predict_one(features)
            if len(prior_residuals) < minimum_history or pstdev(prior_residuals) <= 1e-12:
                residual_z = 0.0
                warmup_rows += 1
            else:
                residual_z = (raw_residual - mean(prior_residuals)) / pstdev(prior_residuals)
            symbol = str(row.get("symbol") or "")
            result[day][symbol] = residual_z
            day_rows.append((symbol, features, target, raw_residual))
        for _symbol, features, target, raw_residual in day_rows:
            ridge.update_one(features, target)
            prior_residuals.append(raw_residual)
    return result, {
        "past_only": True,
        "ridge_alpha": alpha,
        "minimum_history_rows": minimum_history,
        "trained_row_count": ridge.row_count,
        "warmup_row_count": warmup_rows,
        "future_observation_violations": 0,
    }


def apply_sector_near_tie_budget_shift(
    picks: list[dict[str, Any]],
    *,
    residuals_by_symbol: dict[str, float],
    baseline_buy_keys: set[tuple[str, str, int]],
    signal_day: str,
    score_gap_max: float,
    residual_advantage_min: float,
    transfer_fraction: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    adjusted = copy.deepcopy(sorted(picks, key=lambda row: int(float(row.get("rank") or 999))))
    rank1 = next(row for row in adjusted if int(float(row.get("rank") or 0)) == 1)
    rank2 = next(row for row in adjusted if int(float(row.get("rank") or 0)) == 2)
    rank1_key = (signal_day, str(rank1.get("symbol") or ""), 1)
    rank2_key = (signal_day, str(rank2.get("symbol") or ""), 2)
    score_gap = float(rank1.get("score") or 0.0) - float(rank2.get("score") or 0.0)
    residual_advantage = residuals_by_symbol.get(str(rank2.get("symbol") or ""), 0.0) - residuals_by_symbol.get(
        str(rank1.get("symbol") or ""), 0.0
    )
    triggered = (
        rank1_key in baseline_buy_keys
        and rank2_key in baseline_buy_keys
        and score_gap <= score_gap_max
        and residual_advantage >= residual_advantage_min
    )
    if not triggered:
        return adjusted, {
            "triggered": False,
            "score_gap": score_gap,
            "residual_advantage": residual_advantage,
        }
    rank1_multiplier = float(rank1.get("rank_weight_multiplier") or 0.0)
    rank2_multiplier = float(rank2.get("rank_weight_multiplier") or 0.0)
    if rank1_multiplier <= 0.0 or rank2_multiplier <= 0.0:
        raise ValueError("rank1/rank2 multipliers must be positive for budget transfer")
    rank1_effective = float(rank1.get("portfolio_weight") or 1.0) * rank1_multiplier
    rank2_effective = float(rank2.get("portfolio_weight") or 1.0) * rank2_multiplier
    transfer = rank1_effective * transfer_fraction
    rank1["portfolio_weight"] = (rank1_effective - transfer) / rank1_multiplier
    rank2["portfolio_weight"] = (rank2_effective + transfer) / rank2_multiplier
    for row in (rank1, rank2):
        row["external_sector_budget_shift"] = transfer_fraction
        row["external_sector_residual_advantage"] = residual_advantage
        row["external_sector_core_score_gap"] = score_gap
    return adjusted, {
        "triggered": True,
        "score_gap": score_gap,
        "residual_advantage": residual_advantage,
        "effective_budget_before": rank1_effective + rank2_effective,
        "effective_budget_after": (
            float(rank1["portfolio_weight"]) * rank1_multiplier
            + float(rank2["portfolio_weight"]) * rank2_multiplier
        ),
    }


def run_sector_near_tie_budget_shift_ablation(
    *,
    execution_snapshot_path: Path,
    sector_market_snapshot_path: Path,
    design_path: Path,
    signal_end: date = date(2026, 6, 26),
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "frozen_before_round14_outcome_evaluation":
        raise ValueError("round14 design must be frozen before outcome evaluation")
    snapshot = load_rolling_account_execution_snapshot(execution_snapshot_path)
    sector_snapshot = load_sector_research_snapshot(sector_market_snapshot_path)
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    picks_by_date = _group_by_date(trial["selected_top_k_picks_by_date"], end=signal_end)
    inventory_by_date = _group_by_date(snapshot["inputs"]["candidate_inventory_rows"], end=signal_end)
    decision_dates = [date.fromisoformat(day) for day in inventory_by_date]
    sector_states = sector_state_by_decision_date(
        sector_snapshot["normalized"]["records"],
        decision_dates=decision_dates,
    )
    if set(sector_states) != set(inventory_by_date):
        raise ValueError("SW L1 sector state is incomplete for round14")
    mapping_audit = sector_mapping_coverage(
        [str(row.get("industry_name") or "") for rows in inventory_by_date.values() for row in rows]
    )
    if float(mapping_audit["mapped_row_rate"]) < 0.99:
        raise ValueError("SW L1 mapping coverage is below the round14 floor")
    residuals, residual_audit = build_past_only_sw_sector_residuals(
        picks_by_date=picks_by_date,
        sector_states=sector_states,
    )

    def replay(selected: list[dict[str, Any]], artifact_id: str) -> dict[str, Any]:
        candidate_run = _candidate_run(snapshot=snapshot, selected_picks=selected, weight=0.0)
        candidate_run["artifact_id"] = artifact_id
        result = build_shortpick_v3_rolling_account_replay_artifact(
            candidate_run=candidate_run,
            trial_id=snapshot["trial_id"],
            market_bars_by_symbol=snapshot["inputs"]["market_bars_by_symbol"],
            candidate_inventory_rows=[row for day in sorted(inventory_by_date) for row in inventory_by_date[day]],
            candidate_configurations=[copy.deepcopy(snapshot["inputs"]["baseline_config"])],
            **snapshot["inputs"]["account_profile"],
        )
        return result["results"][0]

    baseline_selected = [copy.deepcopy(row) for day in sorted(picks_by_date) for row in picks_by_date[day]]
    baseline_account = replay(baseline_selected, "round14-lambda-zero-v3")
    baseline_buy_keys = {
        (str(row["signal_day"]), str(row["symbol"]), int(row["rank"]))
        for row in baseline_account["order_ledger"]
        if row.get("action") == "buy"
    }
    baseline_segments = {
        "tuning": _segment_metrics(baseline_account, start=None, end=DEFAULT_TUNING_END),
        "validation": _segment_metrics(
            baseline_account,
            start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
            end=DEFAULT_VALIDATION_END,
        ),
        "full_pre_final": _segment_metrics(baseline_account, start=None, end=DEFAULT_VALIDATION_END),
    }
    result_rows: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, Any]] = {}
    for variant in design["variants"]:
        selected: list[dict[str, Any]] = []
        trigger_dates: list[dict[str, Any]] = []
        for day in sorted(picks_by_date):
            adjusted, audit = apply_sector_near_tie_budget_shift(
                picks_by_date[day],
                residuals_by_symbol=residuals[day],
                baseline_buy_keys=baseline_buy_keys,
                signal_day=day,
                score_gap_max=float(variant["score_gap_max"]),
                residual_advantage_min=float(variant["residual_advantage_min"]),
                transfer_fraction=float(variant["transfer_fraction"]),
            )
            selected.extend(adjusted)
            if audit["triggered"]:
                trigger_dates.append({"signal_date": day, **audit})
        variant_id = str(variant["variant_id"])
        account = replay(selected, f"round14-{variant_id}")
        accounts[variant_id] = account
        segments = {
            "tuning": _segment_metrics(account, start=None, end=DEFAULT_TUNING_END),
            "validation": _segment_metrics(
                account,
                start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                end=DEFAULT_VALIDATION_END,
            ),
            "full_pre_final": _segment_metrics(account, start=None, end=DEFAULT_VALIDATION_END),
        }
        result_rows.append(
            {
                "variant": variant,
                "trigger_audit": {
                    "triggered_signal_day_count": len(trigger_dates),
                    "triggered_signal_dates": trigger_dates,
                    "created_new_symbol_order": False,
                    "effective_budget_conserved": True,
                },
                "segments": segments,
                "gates": {
                    segment: _non_degrade(segments[segment], baseline_segments[segment]) for segment in segments
                },
                "standout": {
                    segment: _standout(segments[segment], baseline_segments[segment]) for segment in segments
                },
                "validation_monthly_delta": _monthly_delta_summary(
                    account,
                    baseline_account,
                    start=DEFAULT_TUNING_END + (DEFAULT_FINAL_START - DEFAULT_VALIDATION_END),
                    end=DEFAULT_VALIDATION_END,
                ),
            }
        )
    eligible = [
        row
        for row in result_rows
        if int(row["trigger_audit"]["triggered_signal_day_count"]) > 0
        and row["gates"]["tuning"]["passed"]
        and row["gates"]["validation"]["passed"]
    ]
    selected_row: dict[str, Any] | None = None
    if eligible:
        best = max(eligible, key=lambda row: float(row["validation_monthly_delta"]["mean_monthly_return_delta"]))
        floor = float(best["validation_monthly_delta"]["mean_monthly_return_delta"]) - float(
            best["validation_monthly_delta"]["monthly_delta_standard_error"]
        )
        plateau = [
            row for row in eligible if float(row["validation_monthly_delta"]["mean_monthly_return_delta"]) >= floor
        ]
        selected_row = min(
            plateau,
            key=lambda row: (
                float(row["variant"]["transfer_fraction"]),
                float(row["variant"]["score_gap_max"]),
                -float(row["variant"]["residual_advantage_min"]),
            ),
        )
    final_readout: dict[str, Any] | None = None
    if selected_row is not None:
        selected_id = str(selected_row["variant"]["variant_id"])
        baseline_final = _segment_metrics(baseline_account, start=DEFAULT_FINAL_START, end=signal_end)
        candidate_final = _segment_metrics(accounts[selected_id], start=DEFAULT_FINAL_START, end=signal_end)
        final_readout = {
            "variant_id": selected_id,
            "baseline": baseline_final,
            "candidate": candidate_final,
            "gate": _non_degrade(candidate_final, baseline_final),
            "standout": _standout(candidate_final, baseline_final),
            "buy_order_delta": _buy_order_delta(
                accounts[selected_id], baseline_account, start=DEFAULT_FINAL_START, end=signal_end
            ),
        }
    passed = bool(
        selected_row is not None
        and final_readout
        and final_readout["gate"]["passed"]
        and final_readout["standout"]["passed"]
    )
    material = {
        "artifact_type": "sector_near_tie_budget_shift_account_ablation",
        "schema_version": SCHEMA_VERSION,
        "round": 14,
        "status": "candidate_passed_all_gates" if passed else "no_candidate_cleared_full_objective",
        "claim_ceiling": "research_only_budget_conserving_sector_residual_account_replay",
        "source_execution_snapshot_id": snapshot["artifact_id"],
        "source_sector_market_digest": sector_snapshot["content_digest"],
        "source_design_digest": stable_digest(design),
        "signal_day_count": len(picks_by_date),
        "sector_mapping_audit": mapping_audit,
        "sector_residual_audit": residual_audit,
        "baseline_segments_pre_final": baseline_segments,
        "results_pre_final": result_rows,
        "selection_before_final": None if selected_row is None else selected_row["variant"]["variant_id"],
        "final_untouched_readout": final_readout,
        "provider_revision_lineage_missing": True,
        "promotion_blocker": sector_snapshot["promotion_blocker"],
        "v3_symbol_selection_changed": False,
        "total_signal_budget_changed": False,
    }
    digest = stable_digest(material)
    return {
        "artifact_id": f"sector-near-tie-budget-shift-account-ablation-{digest[:16]}",
        **material,
        "content_digest": digest,
    }
