from __future__ import annotations

import copy
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from ashare_evidence.external_inventory_rerank import _z_scores
from ashare_evidence.global_sector_state_account_ablation import _sigmoid, fit_l2_logistic
from ashare_evidence.hotspot_secondary_start import DEFAULT_MEMORY_SIGNAL_DAYS
from ashare_evidence.hotspot_state_model import (
    BUY_COST_BPS,
    COOLDOWN_SIGNAL_DAYS,
    MAXIMUM_TRAINING_ROWS,
    SELL_COST_BPS,
    STOCK_FEATURE_NAMES,
    attach_forward_label,
    build_prefilter_rows,
    stock_state_features,
)
from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.recent_hotspot_pit import load_gzip_artifact
from ashare_evidence.rolling_account_execution_snapshot import load_rolling_account_execution_snapshot, stable_digest

SCHEMA_VERSION = "hotspot_recovery_dual_head.v1"
ACTIVITY_FEATURE_NAMES = (
    "amount_1d_vs_20d",
    "amount_5d_vs_20d",
    "turnover_1d_vs_20d",
    "turnover_5d_vs_20d",
)
FEATURE_NAMES = (*STOCK_FEATURE_NAMES, *ACTIVITY_FEATURE_NAMES)
RECOVERY_L2 = 10.0
RISK_L2 = 10.0
RECOVERY_CLIP = 0.30
RISK_DRAWDOWN = -0.05
MINIMUM_RECOVERY_PERCENTILE = 0.90
MAXIMUM_RISK_PERCENTILE = 0.70
RECOVERY_SCORE_WEIGHT = 0.65
RISK_SCORE_WEIGHT = 0.35
PREFILTER_TOP_K = 50


@dataclass(frozen=True)
class DualHeadModel:
    centers: np.ndarray
    scales: np.ndarray
    ridge_beta: np.ndarray
    risk_beta: np.ndarray
    training_row_count: int
    maximum_label_available_day: str

    def predict(self, features: list[float]) -> tuple[float, float]:
        standardized = (np.asarray(features, dtype=float) - self.centers) / self.scales
        design = np.asarray([1.0, *standardized], dtype=float)
        recovery = float(design @ self.ridge_beta)
        risk = float(_sigmoid(np.asarray([design @ self.risk_beta]))[0])
        return recovery, risk


def _group(rows: list[dict[str, Any]], *, key: str) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        output[str(row[key])].append(row)
    return dict(output)


def _historical_rows(snapshot: dict[str, Any], *, cutoff: date) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    trial = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    original = _group(
        [row for row in trial["selected_top_k_picks_by_date"] if str(row["as_of_date"]) <= cutoff.isoformat()],
        key="as_of_date",
    )
    inventory = _group(
        [row for row in snapshot["inputs"]["candidate_inventory_rows"] if str(row["as_of_date"]) <= cutoff.isoformat()],
        key="as_of_date",
    )
    if set(original) != set(inventory):
        raise ValueError("historical V3 selection and inventory coverage differ")
    bars = snapshot["inputs"]["market_bars_by_symbol"]
    indices = {symbol: {str(row["day"]): index for index, row in enumerate(rows)} for symbol, rows in bars.items()}
    registry: dict[str, dict[str, Any]] = {}
    rows_by_day: dict[str, list[dict[str, Any]]] = {}
    for signal_index, day in enumerate(sorted(inventory)):
        for row in inventory[day]:
            symbol = str(row["symbol"])
            current = registry.get(symbol)
            registry[symbol] = {
                "row": copy.deepcopy(row),
                "best_rank": min(int(float(row["rank"])), int(current["best_rank"]) if current else 999),
                "last_seen_day": day,
                "last_seen_signal_index": signal_index,
            }
        candidates = build_prefilter_rows(
            signal_day=day,
            signal_index=signal_index,
            registry=registry,
            current_inventory=inventory[day],
            original_top3=original[day],
            sector_states={},
            market_bars_by_symbol=bars,
            bar_indices_by_symbol=indices,
        )
        rows_by_day[day] = [
            attach_forward_label(row, market_bars_by_symbol=bars, bar_indices_by_symbol=indices) for row in candidates
        ]
    return rows_by_day, {
        "registry": registry,
        "last_signal_index": len(inventory) - 1,
        "historical_signal_days": sorted(inventory),
    }


def _activity_bars(database_path: Path, *, symbols: set[str], start: str, end: str) -> dict[str, list[dict[str, Any]]]:
    connection = sqlite3.connect(f"file:{database_path}?immutable=1", uri=True)
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ordered = sorted(symbols)
    for offset in range(0, len(ordered), 400):
        chunk = ordered[offset : offset + 400]
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"""
            SELECT s.symbol, substr(m.observed_at, 1, 10), m.close_price, m.amount, m.turnover_rate
            FROM market_bars m JOIN stocks s ON s.id = m.stock_id
            WHERE m.timeframe = '1d' AND s.symbol IN ({placeholders})
              AND substr(m.observed_at, 1, 10) >= ? AND substr(m.observed_at, 1, 10) <= ?
            ORDER BY s.symbol, m.observed_at
            """,
            [*chunk, start, end],
        ).fetchall()
        for symbol, day, close, amount, turnover in rows:
            output[str(symbol)].append(
                {
                    "day": str(day),
                    "close": float(close),
                    "amount": float(amount or 0.0),
                    "turnover": float(turnover or 0.0),
                }
            )
    connection.close()
    return dict(output)


def activity_features(rows: list[dict[str, Any]], *, index: int) -> dict[str, float]:
    if index < 19:
        return {name: 0.0 for name in ACTIVITY_FEATURE_NAMES}
    amounts = [float(row["amount"]) for row in rows[index - 19 : index + 1]]
    turnovers = [float(row["turnover"]) for row in rows[index - 19 : index + 1]]
    amount20 = mean(amounts)
    turnover20 = mean(turnovers)
    return {
        "amount_1d_vs_20d": amounts[-1] / max(amount20, 1.0) - 1.0,
        "amount_5d_vs_20d": mean(amounts[-5:]) / max(amount20, 1.0) - 1.0,
        "turnover_1d_vs_20d": turnovers[-1] / max(turnover20, 0.000001) - 1.0,
        "turnover_5d_vs_20d": mean(turnovers[-5:]) / max(turnover20, 0.000001) - 1.0,
    }


def _augment_training_rows(
    rows_by_day: dict[str, list[dict[str, Any]]], *, activity: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    indices = {symbol: {row["day"]: index for index, row in enumerate(rows)} for symbol, rows in activity.items()}
    output: list[dict[str, Any]] = []
    for day in sorted(rows_by_day):
        for row in rows_by_day[day]:
            symbol = str(row["symbol"])
            bars = activity.get(symbol) or []
            index = indices.get(symbol, {}).get(day)
            if index is None:
                continue
            enriched = {**row, **activity_features(bars, index=index)}
            enriched["downside_label"] = None
            if row.get("label_available_day") and index + 11 < len(bars):
                entry = float(bars[index + 1]["close"])
                adverse = min(float(value["close"]) / entry - 1.0 for value in bars[index + 1 : index + 12])
                enriched["maximum_adverse_return_10d"] = adverse
                enriched["downside_label"] = int(adverse <= RISK_DRAWDOWN)
            output.append(enriched)
    return output


def feature_vector(row: dict[str, Any]) -> list[float]:
    return [float(row[name]) for name in FEATURE_NAMES]


def fit_dual_head(rows: list[dict[str, Any]], *, fit_day: str) -> DualHeadModel:
    eligible = [
        row
        for row in rows
        if row.get("net_return_10d") is not None
        and row.get("downside_label") is not None
        and row.get("label_available_day") is not None
        and str(row["label_available_day"]) <= fit_day
    ][-MAXIMUM_TRAINING_ROWS:]
    if len(eligible) < 3000:
        raise ValueError("insufficient causal dual-head training rows")
    matrix = np.asarray([feature_vector(row) for row in eligible], dtype=float)
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales <= 1e-12, 1.0, scales)
    standardized = (matrix - centers) / scales
    design = np.column_stack([np.ones(len(standardized)), standardized])
    targets = np.asarray(
        [min(RECOVERY_CLIP, max(-RECOVERY_CLIP, float(row["net_return_10d"]))) for row in eligible],
        dtype=float,
    )
    penalty = np.eye(design.shape[1]) * RECOVERY_L2
    penalty[0, 0] = 0.0
    ridge_beta = np.linalg.solve(design.T @ design + penalty, design.T @ targets)
    risk_labels = np.asarray([int(row["downside_label"]) for row in eligible], dtype=float)
    if len(set(risk_labels.tolist())) < 2:
        raise ValueError("dual-head risk labels require both classes")
    risk_beta = fit_l2_logistic(standardized, risk_labels, l2_penalty=RISK_L2)
    return DualHeadModel(
        centers=centers,
        scales=scales,
        ridge_beta=ridge_beta,
        risk_beta=risk_beta,
        training_row_count=len(eligible),
        maximum_label_available_day=max(str(row["label_available_day"]) for row in eligible),
    )


def _percentiles(values: list[tuple[str, float]], *, higher_is_better: bool = True) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (item[1], item[0]), reverse=not higher_is_better)
    denominator = max(1, len(ordered) - 1)
    ranks = {symbol: index / denominator for index, (symbol, _value) in enumerate(ordered)}
    return ranks if higher_is_better else {symbol: 1.0 - value for symbol, value in ranks.items()}


def _prefilter_recent(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    return sorted(candidates, key=lambda row: (-float(row["prefilter_score"]), str(row["symbol"])))[:PREFILTER_TOP_K]


def _recent_opportunities(
    snapshot: dict[str, Any], *, state: dict[str, Any], activity: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    registry = copy.deepcopy(state["registry"])
    signal_index = int(state["last_signal_index"])
    compact_by_day = _group(snapshot["rows"], key="signal_day")
    bar_indices = {symbol: {row["day"]: index for index, row in enumerate(rows)} for symbol, rows in activity.items()}
    output: dict[str, list[dict[str, Any]]] = {}
    for day in sorted(compact_by_day):
        signal_index += 1
        rows = compact_by_day[day]
        current = {str(row["symbol"]): row for row in rows if row.get("v3_top20_rank") is not None}
        top3 = {str(row["symbol"]) for row in rows if row.get("v3_top3_rank") is not None}
        for symbol, row in current.items():
            previous = registry.get(symbol)
            rank = int(row["v3_top20_rank"])
            registry[symbol] = {
                "row": {
                    "symbol": symbol,
                    "stock_name": row["stock_name"],
                    "industry_name": row.get("industry_name"),
                    "rank": rank,
                    "as_of_date": day,
                },
                "best_rank": min(rank, int(previous["best_rank"]) if previous else 999),
                "last_seen_day": day,
                "last_seen_signal_index": signal_index,
            }
        candidates: list[dict[str, Any]] = []
        compact = {str(row["symbol"]): row for row in rows}
        for symbol, memory in registry.items():
            recency = signal_index - int(memory["last_seen_signal_index"])
            row = compact.get(symbol)
            bars = activity.get(symbol) or []
            index = bar_indices.get(symbol, {}).get(day)
            if recency > DEFAULT_MEMORY_SIGNAL_DAYS or symbol in top3 or row is None or index is None:
                continue
            if not row.get("personally_eligible"):
                continue
            state_features = stock_state_features(bars, signal_day=day, bar_index=index)
            if state_features is None:
                continue
            current_row = current.get(symbol)
            candidates.append(
                {
                    "signal_day": day,
                    "symbol": symbol,
                    "stock_name": row["stock_name"],
                    "industry_name": row.get("industry_name"),
                    "memory_quality": 1.0 - (min(max(int(memory["best_rank"]), 1), 20) - 1) / 19.0,
                    "memory_recency": math.log1p(recency) / math.log1p(DEFAULT_MEMORY_SIGNAL_DAYS),
                    "current_core_present": float(current_row is not None),
                    "current_core_quality": (
                        0.0 if current_row is None else 1.0 - (int(current_row["v3_top20_rank"]) - 1) / 19.0
                    ),
                    **state_features,
                    **activity_features(bars, index=index),
                    "recent_pit_row": row,
                }
            )
        output[day] = _prefilter_recent(candidates)
    return output


def score_recent_shadow(
    rows_by_day: dict[str, list[dict[str, Any]]], *, model: DualHeadModel, activation_date: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    last_selected_index: dict[str, int] = {}
    for signal_index, day in enumerate(sorted(rows_by_day)):
        predictions = []
        for row in rows_by_day[day]:
            recovery, risk = model.predict(feature_vector(row))
            predictions.append({"row": row, "recovery": recovery, "risk": risk})
        if not predictions:
            daily.append({"signal_day": day, "status": "no_opportunity"})
            continue
        recovery_pct = _percentiles([(item["row"]["symbol"], item["recovery"]) for item in predictions])
        risk_pct = _percentiles(
            [(item["row"]["symbol"], item["risk"]) for item in predictions], higher_is_better=False
        )
        for item in predictions:
            symbol = str(item["row"]["symbol"])
            item["recovery_percentile"] = recovery_pct[symbol]
            item["risk_percentile"] = risk_pct[symbol]
            item["transition_score"] = (
                RECOVERY_SCORE_WEIGHT * recovery_pct[symbol] + RISK_SCORE_WEIGHT * (1.0 - risk_pct[symbol])
            )
        predictions.sort(key=lambda item: (-float(item["transition_score"]), str(item["row"]["symbol"])))
        top = predictions[0]
        symbol = str(top["row"]["symbol"])
        passes = bool(
            top["recovery_percentile"] >= MINIMUM_RECOVERY_PERCENTILE
            and top["risk_percentile"] <= MAXIMUM_RISK_PERCENTILE
            and signal_index - last_selected_index.get(symbol, -10_000) > COOLDOWN_SIGNAL_DAYS
        )
        readout = {
            "signal_day": day,
            "symbol": symbol,
            "stock_name": top["row"]["stock_name"],
            "industry_name": top["row"].get("industry_name"),
            "recovery_prediction": top["recovery"],
            "downside_probability": top["risk"],
            "recovery_prediction_percentile": top["recovery_percentile"],
            "downside_probability_percentile": top["risk_percentile"],
            "transition_score": top["transition_score"],
            "selected": passes,
            "evidence_basis": "true_forward_shadow" if day >= activation_date else "retrospective_diagnostic",
            "candidate_count": len(predictions),
            "ranked_candidates": [
                {
                    "rank": rank,
                    "symbol": item["row"]["symbol"],
                    "stock_name": item["row"]["stock_name"],
                    "industry_name": item["row"].get("industry_name"),
                    "recovery_prediction": item["recovery"],
                    "downside_probability": item["risk"],
                    "recovery_prediction_percentile": item["recovery_percentile"],
                    "downside_probability_percentile": item["risk_percentile"],
                    "transition_score": item["transition_score"],
                }
                for rank, item in enumerate(predictions, start=1)
            ],
        }
        daily.append(readout)
        if passes:
            recent = top["row"]["recent_pit_row"]
            compact_readout = {key: value for key, value in readout.items() if key != "ranked_candidates"}
            selected.append(
                {
                    **compact_readout,
                    "entry_date": recent.get("entry_date"),
                    "entry_status": recent.get("entry_status"),
                    "forward_return_5d": recent.get("forward_return_5d"),
                    "forward_return_10d": recent.get("forward_return_10d"),
                    "same_day_v3_top3_overlap": recent.get("v3_top3_rank") is not None,
                }
            )
            last_selected_index[symbol] = signal_index
    return selected, daily


def run_hotspot_recovery_dual_head(
    *,
    execution_snapshot_path: Path,
    recent_snapshot_path: Path,
    hot_database: Path,
    design_path: Path,
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    source = load_rolling_account_execution_snapshot(execution_snapshot_path)
    if source["artifact_id"] != design["data_contract"]["historical_execution_snapshot_id"]:
        raise ValueError("dual-head design and historical execution snapshot differ")
    personal, eligibility_audit = build_personal_eligible_execution_snapshot(source)
    cutoff = date.fromisoformat(design["data_contract"]["historical_training_cutoff"])
    historical_by_day, state = _historical_rows(personal, cutoff=cutoff)
    recent = load_gzip_artifact(recent_snapshot_path)
    symbols = {
        str(row["symbol"]) for rows in historical_by_day.values() for row in rows
    } | {str(row["symbol"]) for row in recent["rows"] if row.get("v3_top20_rank") is not None}
    activity = _activity_bars(
        hot_database,
        symbols=symbols,
        start="2023-06-01",
        end=str(recent["observed_to"]),
    )
    training_rows = _augment_training_rows(historical_by_day, activity=activity)
    model = fit_dual_head(training_rows, fit_day=cutoff.isoformat())
    recent_opportunities = _recent_opportunities(recent, state=state, activity=activity)
    selected, daily = score_recent_shadow(
        recent_opportunities,
        model=model,
        activation_date=str(design["forward_shadow"]["activation_date"]),
    )
    case_symbols = set(design["evaluation"]["named_cases"])
    case_readout = [
        {"signal_day": row["signal_day"], **candidate}
        for row in daily
        for candidate in row.get("ranked_candidates") or []
        if candidate["symbol"] in case_symbols
    ]
    observed_case_symbols = sorted({str(row["symbol"]) for row in case_readout})
    missing_case_symbols = sorted(case_symbols - set(observed_case_symbols))
    completed_5d = [
        row for row in selected if row.get("entry_status") == "tradable_research_proxy" and row.get("forward_return_5d") is not None
    ]
    completed_10d = [
        row
        for row in selected
        if row.get("entry_status") == "tradable_research_proxy" and row.get("forward_return_10d") is not None
    ]
    material = {
        "artifact_type": "hotspot_recovery_dual_head",
        "schema_version": SCHEMA_VERSION,
        "status": "rejected_mechanism_gate_failed_no_forward_activation",
        "claim_ceiling": "reused_history_and_outcome_aware_recent_diagnostic_not_v3_candidate",
        "source_design_digest": stable_digest(design),
        "source_execution_snapshot_id": source["artifact_id"],
        "source_recent_snapshot_id": recent["artifact_id"],
        "personal_eligibility_audit": eligibility_audit,
        "feature_names": list(FEATURE_NAMES),
        "training_audit": {
            "training_row_count": model.training_row_count,
            "maximum_label_available_day": model.maximum_label_available_day,
            "fit_day": cutoff.isoformat(),
            "future_label_violation_count": int(model.maximum_label_available_day > cutoff.isoformat()),
            "risk_positive_rate": (
                sum(int(row.get("downside_label") or 0) for row in training_rows if row.get("downside_label") is not None)
                / max(1, sum(row.get("downside_label") is not None for row in training_rows))
            ),
            "model_digest": stable_digest(
                {
                    "centers": model.centers.tolist(),
                    "scales": model.scales.tolist(),
                    "ridge_beta": model.ridge_beta.tolist(),
                    "risk_beta": model.risk_beta.tolist(),
                }
            ),
        },
        "recent_opportunity_row_count": sum(len(rows) for rows in recent_opportunities.values()),
        "retrospective_selected_signal_count": len(selected),
        "retrospective_completed_5d_count": len(completed_5d),
        "retrospective_completed_10d_count": len(completed_10d),
        "retrospective_mean_5d_return": (
            mean(float(row["forward_return_5d"]) - (BUY_COST_BPS + SELL_COST_BPS) / 10000.0 for row in completed_5d)
            if completed_5d
            else None
        ),
        "retrospective_mean_10d_return": (
            mean(float(row["forward_return_10d"]) - (BUY_COST_BPS + SELL_COST_BPS) / 10000.0 for row in completed_10d)
            if completed_10d
            else None
        ),
        "retrospective_10d_win_rate": (
            sum(
                float(row["forward_return_10d"]) - (BUY_COST_BPS + SELL_COST_BPS) / 10000.0 > 0.0
                for row in completed_10d
            )
            / len(completed_10d)
            if completed_10d
            else None
        ),
        "retrospective_10d_median_return": (
            float(
                np.median(
                    [
                        float(row["forward_return_10d"]) - (BUY_COST_BPS + SELL_COST_BPS) / 10000.0
                        for row in completed_10d
                    ]
                )
            )
            if completed_10d
            else None
        ),
        "same_day_v3_top3_overlap_count": sum(row["same_day_v3_top3_overlap"] for row in selected),
        "retrospective_selections": selected,
        "daily_top1_readout": daily,
        "named_case_candidate_readout": case_readout,
        "named_case_opportunity_coverage": {
            "required_symbols": sorted(case_symbols),
            "observed_symbols": observed_case_symbols,
            "missing_symbols": missing_case_symbols,
            "coverage_rate": len(observed_case_symbols) / max(1, len(case_symbols)),
            "mechanism_gate_passed": not missing_case_symbols,
            "interpretation": (
                "The frozen V3-memory opportunity set excludes at least one named fast-recovery case, so the "
                "downstream ranker cannot answer the registered research question. Positive reused-window "
                "returns are not selectable evidence."
            ),
        },
        "forward_shadow": {
            "activation_date": design["forward_shadow"]["activation_date"],
            "activation_allowed": False,
            "signal_count": 0,
            "status": "not_activated_mechanism_gate_failed",
            "historical_backfill_counts_as_forward": False,
            "paper_tracking_or_frontend_module": False,
        },
        "promotion_allowed": False,
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
        "runtime_publish_required": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"hotspot-recovery-dual-head-{digest[:16]}", **material, "content_digest": digest}


def write_dual_head_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("dual-head result digest mismatch")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable dual-head result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
