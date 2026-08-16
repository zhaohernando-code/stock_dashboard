from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev
from typing import Any

import numpy as np

from ashare_evidence.external_context_sector_market_research import SW_L1_BY_SUBINDUSTRY
from ashare_evidence.external_inventory_rerank import _z_scores
from ashare_evidence.global_sector_state_account_ablation import _sigmoid, fit_l2_logistic
from ashare_evidence.hotspot_secondary_start import DEFAULT_MEMORY_SIGNAL_DAYS, _bar_index
from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, build_trade_eligibility_snapshot

STOCK_FEATURE_NAMES = (
    "memory_quality",
    "memory_recency",
    "current_core_present",
    "current_core_quality",
    "return_2d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_5d_acceleration",
    "distance_from_20d_high",
    "maximum_drawdown_20d",
    "volatility_20d",
    "close_vs_sma5",
    "close_vs_sma10",
    "shock_drawdown_60d",
    "trough_age_60d",
)
SECTOR_FEATURE_NAMES = (
    "sector_current_positive_breadth",
    "sector_prior_positive_breadth",
    "sector_mean_two_day_return",
    "sector_median_two_day_return",
    "sector_two_day_return_percentile",
)

PREFILTER_TOP_K = 50
MINIMUM_HISTORY = 60
MINIMUM_TRAINING_ROWS = 3000
MAXIMUM_TRAINING_ROWS = 30000
REFIT_SIGNAL_DAYS = 20
L2_PENALTY = 10.0
MINIMUM_PROBABILITY = 0.55
MINIMUM_CONFIDENCE_PERCENTILE = 0.80
MINIMUM_PRIOR_PREDICTION_DAYS = 40
COOLDOWN_SIGNAL_DAYS = 10
BUY_COST_BPS = 20.0
SELL_COST_BPS = 25.0
LABEL_HORIZON = 10


@dataclass(frozen=True)
class StandardizedLogisticModel:
    centers: np.ndarray
    scales: np.ndarray
    beta: np.ndarray
    training_row_count: int
    maximum_label_available_day: str

    def predict(self, features: list[float]) -> float:
        standardized = (np.asarray(features, dtype=float) - self.centers) / self.scales
        design = np.asarray([1.0, *standardized], dtype=float)
        return float(_sigmoid(np.asarray([design @ self.beta]))[0])


def _maximum_drawdown(values: list[float]) -> tuple[float, int]:
    peak = values[0]
    maximum_drawdown = 0.0
    trough_index = 0
    for index, value in enumerate(values):
        peak = max(peak, value)
        drawdown = value / peak - 1.0
        if drawdown < maximum_drawdown:
            maximum_drawdown = drawdown
            trough_index = index
    return maximum_drawdown, trough_index


def stock_state_features(rows: list[dict[str, Any]], *, signal_day: str, bar_index: int | None = None) -> dict[str, float] | None:
    index = _bar_index(rows, signal_day) if bar_index is None else bar_index
    if index is None or index < MINIMUM_HISTORY:
        return None
    closes = [float(row["close"]) for row in rows]
    window = closes[index - 60 : index + 1]
    if min(window) <= 0.0:
        return None
    returns_20 = [closes[position] / closes[position - 1] - 1.0 for position in range(index - 19, index + 1)]
    drawdown_20, _ = _maximum_drawdown(closes[index - 19 : index + 1])
    shock_drawdown, shock_trough = _maximum_drawdown(window[:-1])
    return {
        "return_2d": closes[index] / closes[index - 2] - 1.0,
        "return_5d": closes[index] / closes[index - 5] - 1.0,
        "return_10d": closes[index] / closes[index - 10] - 1.0,
        "return_20d": closes[index] / closes[index - 20] - 1.0,
        "return_5d_acceleration": (
            closes[index] / closes[index - 5] - closes[index - 1] / closes[index - 6]
        ),
        "distance_from_20d_high": closes[index] / max(closes[index - 19 : index + 1]) - 1.0,
        "maximum_drawdown_20d": drawdown_20,
        "volatility_20d": pstdev(returns_20),
        "close_vs_sma5": closes[index] / mean(closes[index - 4 : index + 1]) - 1.0,
        "close_vs_sma10": closes[index] / mean(closes[index - 9 : index + 1]) - 1.0,
        "shock_drawdown_60d": shock_drawdown,
        "trough_age_60d": float((len(window) - 2) - shock_trough) / 60.0,
    }


def _current_eligibility(symbol: str, *, signal_day: str, close: float) -> bool:
    snapshot = build_trade_eligibility_snapshot(
        symbol,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        as_of=date.fromisoformat(signal_day),
        decision_cutoff=signal_day,
        price_cny=close,
        price_observed_at=signal_day,
        price_source="frozen_execution_snapshot.market_bars_by_symbol.close",
        price_adjustment="unadjusted",
        profile_is_point_in_time=False,
    )
    return bool(snapshot["eligible_before_scoring"])


def build_prefilter_rows(
    *,
    signal_day: str,
    signal_index: int,
    registry: dict[str, dict[str, Any]],
    current_inventory: list[dict[str, Any]],
    original_top3: list[dict[str, Any]],
    sector_states: dict[str, dict[str, float]],
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    bar_indices_by_symbol: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    original_symbols = {str(row["symbol"]) for row in original_top3}
    current_by_symbol = {str(row["symbol"]): row for row in current_inventory}
    candidates: list[dict[str, Any]] = []
    for symbol, memory in registry.items():
        recency = signal_index - int(memory["last_seen_signal_index"])
        if recency > DEFAULT_MEMORY_SIGNAL_DAYS or symbol in original_symbols:
            continue
        rows = market_bars_by_symbol.get(symbol) or []
        index = bar_indices_by_symbol.get(symbol, {}).get(signal_day)
        features = stock_state_features(rows, signal_day=signal_day, bar_index=index)
        if features is None:
            continue
        close = float(rows[index]["close"])
        if not _current_eligibility(symbol, signal_day=signal_day, close=close):
            continue
        memory_quality = 1.0 - (min(max(int(memory["best_rank"]), 1), 20) - 1) / 19.0
        current = current_by_symbol.get(symbol)
        current_quality = 0.0 if current is None else 1.0 - (int(float(current["rank"])) - 1) / 19.0
        sw_name = SW_L1_BY_SUBINDUSTRY.get(str(memory["row"].get("industry_name") or ""), "")
        sector = sector_states.get(sw_name) or {}
        row = {
            "signal_day": signal_day,
            "symbol": symbol,
            "stock_name": memory["row"].get("stock_name") or symbol,
            "memory_row": memory["row"],
            "memory_quality": memory_quality,
            "memory_recency": math.log1p(recency) / math.log1p(DEFAULT_MEMORY_SIGNAL_DAYS),
            "current_core_present": float(current is not None),
            "current_core_quality": current_quality,
            **features,
            "sector_current_positive_breadth": float(sector.get("current_positive_breadth") or 0.0),
            "sector_prior_positive_breadth": float(sector.get("prior_positive_breadth") or 0.0),
            "sector_mean_two_day_return": float(sector.get("mean_two_day_return") or 0.0),
            "sector_median_two_day_return": float(sector.get("median_two_day_return") or 0.0),
            "sector_two_day_return_percentile": float(sector.get("two_day_return_percentile") or 0.0),
        }
        candidates.append(row)
    if not candidates:
        return []
    components = {
        "memory": _z_scores([float(row["memory_quality"]) for row in candidates]),
        "return_2d": _z_scores([float(row["return_2d"]) for row in candidates]),
        "return_5d": _z_scores([float(row["return_5d"]) for row in candidates]),
        "sma10": _z_scores([float(row["close_vs_sma10"]) for row in candidates]),
        "volatility": _z_scores([float(row["volatility_20d"]) for row in candidates]),
    }
    for index, row in enumerate(candidates):
        row["prefilter_score"] = (
            0.40 * components["memory"][index]
            + 0.20 * components["return_2d"][index]
            + 0.15 * components["return_5d"][index]
            + 0.15 * components["sma10"][index]
            - 0.10 * components["volatility"][index]
        )
    candidates.sort(key=lambda row: (-float(row["prefilter_score"]), str(row["symbol"])))
    return candidates[:PREFILTER_TOP_K]


def feature_vector(row: dict[str, Any], *, feature_set: str) -> list[float]:
    names = list(STOCK_FEATURE_NAMES)
    if feature_set == "stock_plus_sector":
        names.extend(SECTOR_FEATURE_NAMES)
    elif feature_set != "stock_only":
        raise ValueError(f"unsupported hotspot state feature set: {feature_set}")
    return [float(row[name]) for name in names]


def attach_forward_label(
    row: dict[str, Any],
    *,
    market_bars_by_symbol: dict[str, list[dict[str, Any]]],
    bar_indices_by_symbol: dict[str, dict[str, int]],
) -> dict[str, Any]:
    symbol = str(row["symbol"])
    bars = market_bars_by_symbol.get(symbol) or []
    signal_index = bar_indices_by_symbol.get(symbol, {}).get(str(row["signal_day"]))
    output = dict(row)
    output["label_available_day"] = None
    output["net_return_10d"] = None
    output["positive_label"] = None
    if signal_index is None or signal_index + 1 + LABEL_HORIZON >= len(bars):
        return output
    entry_index = signal_index + 1
    exit_index = entry_index + LABEL_HORIZON
    entry = float(bars[entry_index]["close"])
    exit_price = float(bars[exit_index]["close"])
    net_return = (
        exit_price * (1.0 - SELL_COST_BPS / 10000.0)
        / (entry * (1.0 + BUY_COST_BPS / 10000.0))
        - 1.0
    )
    output["label_available_day"] = str(bars[exit_index]["day"])
    output["net_return_10d"] = net_return
    output["positive_label"] = int(net_return > 0.0)
    return output


def fit_standardized_model(rows: list[dict[str, Any]], *, feature_set: str, fit_day: str) -> StandardizedLogisticModel:
    eligible = [
        row
        for row in rows
        if row.get("positive_label") is not None
        and row.get("label_available_day") is not None
        and str(row["label_available_day"]) <= fit_day
    ][-MAXIMUM_TRAINING_ROWS:]
    if len(eligible) < MINIMUM_TRAINING_ROWS:
        raise ValueError("insufficient causal training rows")
    matrix = np.asarray([feature_vector(row, feature_set=feature_set) for row in eligible], dtype=float)
    labels = np.asarray([int(row["positive_label"]) for row in eligible], dtype=float)
    if len(set(labels.tolist())) < 2:
        raise ValueError("causal training rows require both classes")
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales <= 1e-12, 1.0, scales)
    beta = fit_l2_logistic((matrix - centers) / scales, labels, l2_penalty=L2_PENALTY)
    return StandardizedLogisticModel(
        centers=centers,
        scales=scales,
        beta=beta,
        training_row_count=len(eligible),
        maximum_label_available_day=max(str(row["label_available_day"]) for row in eligible),
    )


def past_only_percentile(value: float, prior_values: list[float]) -> float | None:
    if len(prior_values) < MINIMUM_PRIOR_PREDICTION_DAYS:
        return None
    return sum(prior <= value for prior in prior_values) / len(prior_values)
