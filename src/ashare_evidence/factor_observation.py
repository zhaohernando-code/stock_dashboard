from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.recommendation_selection import collapse_recommendation_history, recommendation_recency_ordering

FACTOR_KEYS = ("price_baseline", "news_event", "fundamental", "size_factor", "reversal", "liquidity")
FUSION_BASELINE = {"price_baseline": 0.35, "news_event": 0.20, "fundamental": 0.15, "size_factor": 0.10, "reversal": 0.10, "liquidity": 0.10}


def _extract_factor_scores(payload: dict[str, Any]) -> dict[str, float]:
    fb = payload.get("factor_breakdown", {})
    scores: dict[str, float] = {}
    for key in FACTOR_KEYS:
        card = fb.get(key, {})
        if isinstance(card, dict):
            scores[key] = float(card.get("score") or 0)
        else:
            scores[key] = 0.0
    return scores


def build_factor_observations(session: Session, *, artifact_root: str, min_records: int = 3) -> dict[str, Any]:
    stocks = session.scalars(select(Stock)).all()
    results: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat(), "symbols": {}}
    for stock in stocks:
        recs = session.scalars(
            select(Recommendation)
            .where(Recommendation.stock_id == stock.id)
            .options(joinedload(Recommendation.model_run))
            .order_by(*recommendation_recency_ordering())
        ).all()
        history = collapse_recommendation_history(recs, limit=min_records + 1)
        if len(history) < min_records:
            continue
        observations: list[dict[str, Any]] = []
        for reco in history:
            payload = dict(reco.recommendation_payload or {})
            scores = _extract_factor_scores(payload)
            validation = payload.get("historical_validation", {})
            metrics = validation.get("metrics", {}) if isinstance(validation, dict) else {}
            observations.append({
                "as_of": reco.as_of_data_time.isoformat() if reco.as_of_data_time else None,
                "generated_at": reco.generated_at.isoformat() if reco.generated_at else None,
                "direction": reco.direction,
                "scores": scores,
                "forward_rank_ic": metrics.get("rank_ic_mean"),
                "forward_positive_excess": metrics.get("positive_excess_rate"),
            })
        per_factor: dict[str, list[float]] = {k: [] for k in FACTOR_KEYS}
        for obs in observations:
            for key in FACTOR_KEYS:
                per_factor[key].append(obs["scores"].get(key, 0.0))
        factor_stats: dict[str, dict[str, float]] = {}
        for key in FACTOR_KEYS:
            vals = per_factor[key]
            if len(vals) >= min_records:
                factor_stats[key] = {
                    "mean": round(sum(vals) / len(vals), 4),
                    "std": round((sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals)) ** 0.5, 4),
                    "count": len(vals),
                    "recent": round(vals[-1], 4) if vals else 0,
                }
        results["symbols"][stock.symbol] = {
            "observation_count": len(observations),
            "factor_stats": factor_stats,
            "observations": observations,
        }
    results["symbol_count"] = len(results["symbols"])
    _write_artifact(results, artifact_root=artifact_root)
    return results


def _write_artifact(results: dict[str, Any], *, artifact_root: str) -> None:
    directory = Path(artifact_root) / "studies"
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    filepath = directory / f"factor-observation:{ts}.json"
    filepath.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sweep_weights(session: Session, *, artifact_root: str) -> dict[str, Any]:
    observations = build_factor_observations(session, artifact_root=artifact_root, min_records=3)
    weight_grid = _build_weight_grid()
    results: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_weights": FUSION_BASELINE,
        "sweep_results": [],
    }
    for label, weights in weight_grid:
        sweep_entry: dict[str, Any] = {"label": label, "weights": weights, "symbols": {}}
        for symbol, data in observations.get("symbols", {}).items():
            obs_list = data.get("observations", [])
            if len(obs_list) < 3:
                continue
            fusion_scores: list[float] = []
            for obs in obs_list:
                fusion = sum(obs["scores"].get(k, 0) * weights.get(k, 0) for k in FACTOR_KEYS)
                fusion_scores.append(round(fusion, 4))
            mean_score = sum(fusion_scores) / len(fusion_scores) if fusion_scores else 0
            sweep_entry["symbols"][symbol] = {
                "mean_fusion": round(mean_score, 4),
                "score_range": [round(min(fusion_scores), 4), round(max(fusion_scores), 4)],
            }
        results["sweep_results"].append(sweep_entry)
    _write_sweep_artifact(results, artifact_root=artifact_root)
    return results


def _build_weight_grid() -> list[tuple[str, dict[str, float]]]:
    grid: list[tuple[str, dict[str, float]]] = []
    grid.append(("baseline", dict(FUSION_BASELINE)))
    grid.append(("price_heavy", {**FUSION_BASELINE, "price_baseline": 0.45, "news_event": 0.15, "fundamental": 0.10}))
    grid.append(("news_heavy", {**FUSION_BASELINE, "price_baseline": 0.25, "news_event": 0.30, "fundamental": 0.15}))
    grid.append(("balanced", {"price_baseline": 0.25, "news_event": 0.20, "fundamental": 0.20, "size_factor": 0.12, "reversal": 0.12, "liquidity": 0.11}))
    grid.append(("size_aware", {**FUSION_BASELINE, "size_factor": 0.15, "reversal": 0.08, "liquidity": 0.07}))
    return grid


def _write_sweep_artifact(results: dict[str, Any], *, artifact_root: str) -> None:
    directory = Path(artifact_root) / "studies"
    directory.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    filepath = directory / f"weight-sweep:{ts}.json"
    filepath.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
