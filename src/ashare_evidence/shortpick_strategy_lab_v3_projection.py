from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.model_candidate_runner import (
    _exit_horizon_days,
    _fit_model,
    _grid_trials,
    _model_feature_values,
    _position_weight,
    _rank_signal_feature_subset,
    _safe_float,
    _score_row,
    _selection_allowed,
    _signal_cash_switch_block_reasons,
    _stable_digest,
    _top_k_picks_by_date,
)
from ashare_evidence.model_exploration_snapshot import build_model_exploration_p1_artifacts
from ashare_evidence.model_spec_registry import build_model_spec_registry_artifact
from ashare_evidence.models import MarketBar, Stock

V3_MODEL_SPEC_ID = "selected_exhaustion_date_scaled_v3_top3_20d_v1"
NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID = "negative_month_rank_weight_adjusted_capacity_cluster_v3_top3_20d_v1"
DEFAULT_V3_MODEL_SPEC_IDS = (V3_MODEL_SPEC_ID, NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID)
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"
DEFAULT_V3_CANDIDATE_RUN_SOURCE_NAME = "shortpick-strategy-lab-v3-candidate-run-source.json"
FORWARD_REPLACEMENT_INVENTORY_TOP_K = 20


def default_v3_candidate_run_source_path(repo_root: Path) -> Path:
    return repo_root / "data" / DEFAULT_V3_CANDIDATE_RUN_SOURCE_NAME


def latest_model_as_of_date(
    session: Session,
    *,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    min_market_bar_count: int = 200,
) -> date:
    broad_market_day = session.execute(
        select(func.date(MarketBar.observed_at), func.count())
        .where(MarketBar.timeframe == "1d")
        .group_by(func.date(MarketBar.observed_at))
        .having(func.count() >= min_market_bar_count)
        .order_by(func.date(MarketBar.observed_at).desc())
        .limit(1)
    ).one_or_none()
    if broad_market_day is not None:
        return date.fromisoformat(str(broad_market_day[0]))
    benchmark = session.scalar(select(Stock).where(Stock.symbol == benchmark_symbol).limit(1))
    query = select(MarketBar.observed_at).where(MarketBar.timeframe == "1d")
    if benchmark is not None:
        query = query.where(MarketBar.stock_id == benchmark.id)
    observed_at = session.scalar(query.order_by(MarketBar.observed_at.desc(), MarketBar.id.desc()).limit(1))
    if observed_at is None:
        raise RuntimeError("cannot build v3 candidate-run source: no 1d market bars available")
    return observed_at.date()


def build_latest_v3_candidate_run_source(
    session: Session,
    *,
    validation_run_id: str | None = None,
    as_of_date: date | None = None,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    model_spec_id: str = V3_MODEL_SPEC_ID,
    model_spec_ids: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    signal_date = as_of_date or latest_model_as_of_date(session, benchmark_symbol=benchmark_symbol)
    resolved_validation_run_id = validation_run_id or f"shortpick-strategy-lab-v3-forward-{signal_date.isoformat()}"
    requested_model_spec_ids = tuple(dict.fromkeys(model_spec_ids or DEFAULT_V3_MODEL_SPEC_IDS or (model_spec_id,)))
    if model_spec_id not in requested_model_spec_ids:
        requested_model_spec_ids = (model_spec_id, *requested_model_spec_ids)
    matrix_artifacts = build_model_exploration_p1_artifacts(
        session,
        validation_run_id=resolved_validation_run_id,
        as_of_dates=[signal_date],
        benchmark_symbol=benchmark_symbol,
        entry_price_source="next_close",
    )
    registry = build_model_spec_registry_artifact(
        validation_run_id=resolved_validation_run_id,
        source_input_snapshot_id=str(matrix_artifacts["model_exploration_input_snapshot"]["artifact_id"]),
    )
    feature_rows = [
        row
        for row in matrix_artifacts["pit_feature_matrix"].get("rows", [])
        if str(row.get("as_of_date") or "") == signal_date.isoformat()
    ]
    trial_summaries: list[dict[str, Any]] = []
    trial_diagnostics: list[dict[str, Any]] = []
    selected_pick_count_by_model_spec: dict[str, int] = {}
    prediction_row_count_by_model_spec: dict[str, int] = {}
    selection_allowed_row_count_by_model_spec: dict[str, int] = {}
    signal_block_reasons_by_model_spec: dict[str, list[str]] = {}
    selected_top_k_picks_for_digest: dict[str, list[dict[str, Any]]] = {}
    replacement_inventory_for_digest: dict[str, list[dict[str, Any]]] = {}
    for current_model_spec_id in requested_model_spec_ids:
        spec = _model_spec_by_id(registry, current_model_spec_id)
        params = _grid_trials(spec.get("hyperparameter_grid") or {})[0]
        selection_policy = spec.get("selection_policy") or {}
        horizon_days = int(spec.get("prediction_horizon_days") or 20)
        selected_top_k = max(1, int(_safe_float(selection_policy.get("top_k"), 3.0)))
        fitted_model = _fit_model([], model_spec=spec, params=params)
        fitted_model_digest = _stable_digest(
            {
                "model_spec_id": current_model_spec_id,
                "signal_date": signal_date.isoformat(),
                "fitted_model": fitted_model,
                "projection_mode": "latest_pit_feature_projection",
            }
        )
        predictions = [
            _projection_prediction(
                feature_row=row,
                spec=spec,
                params=params,
                selection_policy=selection_policy,
                trial_id=f"{current_model_spec_id}:trial-000",
                fitted_model=fitted_model,
                fitted_model_digest=fitted_model_digest,
                horizon_days=horizon_days,
            )
            for row in feature_rows
        ]
        picks = _top_k_picks_by_date(
            predictions,
            top_k=selected_top_k,
            selection_policy=selection_policy,
            params=params,
        )
        replacement_inventory = _top_k_picks_by_date(
            predictions,
            top_k=FORWARD_REPLACEMENT_INVENTORY_TOP_K,
            selection_policy=selection_policy,
            params=params,
        )
        signal_block_reasons = _signal_block_reasons(
            predictions,
            selection_policy=selection_policy,
            params=params,
        )
        selected_pick_count_by_model_spec[current_model_spec_id] = len(picks)
        prediction_row_count_by_model_spec[current_model_spec_id] = len(predictions)
        selection_allowed_row_count_by_model_spec[current_model_spec_id] = sum(
            1 for row in predictions if row.get("selection_allowed", True)
        )
        signal_block_reasons_by_model_spec[current_model_spec_id] = signal_block_reasons
        selected_top_k_picks_for_digest[current_model_spec_id] = picks
        replacement_inventory_for_digest[current_model_spec_id] = replacement_inventory
        trial_summaries.append(
            {
                "trial_id": f"{current_model_spec_id}:trial-000",
                "model_spec_id": current_model_spec_id,
                "selection_policy": selection_policy,
                "params": params,
                "projection_metrics": {
                    "return_metrics_available": False,
                    "selected_top_k": selected_top_k,
                    "selected_pick_count": len(picks),
                },
                "gate_status": "ready_for_forward_paper_plan",
            }
        )
        trial_diagnostics.append(
            {
                "trial_id": f"{current_model_spec_id}:trial-000",
                "model_spec_id": current_model_spec_id,
                "target_horizon_days": horizon_days,
                "selected_top_k": selected_top_k,
                "selected_top_k_picks_by_date": picks,
                "ranked_candidate_inventory_by_date": replacement_inventory,
                "ranked_candidate_inventory_top_k": FORWARD_REPLACEMENT_INVENTORY_TOP_K,
                "selected_top_k_returns_by_date": [],
                "signal_block_reasons": signal_block_reasons,
                "projection_note": "Forward projection uses PIT features only; no forward returns are present.",
            }
        )
    content_digest = _stable_digest(
        {
            "model_spec_ids": requested_model_spec_ids,
            "signal_date": signal_date.isoformat(),
            "source_feature_matrix": matrix_artifacts["pit_feature_matrix"].get("artifact_id"),
            "selected_top_k_picks_by_model_spec": selected_top_k_picks_for_digest,
            "ranked_candidate_inventory_by_model_spec": replacement_inventory_for_digest,
        }
    )
    generated_at = datetime.now(UTC).isoformat()
    return {
        "artifact_type": "shortpick_strategy_lab_v3_candidate_run_source",
        "schema_version": "shortpick_strategy_lab_v3_candidate_run_source.v1",
        "artifact_id": f"shortpick-strategy-lab-v3-candidate-run-source-{content_digest[:16]}",
        "generated_at": generated_at,
        "validation_run_id": resolved_validation_run_id,
        "projection_mode": "latest_pit_feature_projection_no_forward_labels",
        "claim_ceiling": "forward_candidate_source_only_no_return_claim",
        "model_spec_id": model_spec_id,
        "model_spec_ids": list(requested_model_spec_ids),
        "signal_date": signal_date.isoformat(),
        "benchmark_symbol": benchmark_symbol,
        "source_input_snapshot_id": matrix_artifacts["model_exploration_input_snapshot"].get("artifact_id"),
        "source_feature_matrix_id": matrix_artifacts["pit_feature_matrix"].get("artifact_id"),
        "source_universe_row_count": matrix_artifacts["model_exploration_input_snapshot"].get("universe_row_count"),
        "feature_row_count": len(matrix_artifacts["pit_feature_matrix"].get("rows", [])),
        "prediction_row_count": prediction_row_count_by_model_spec.get(model_spec_id, 0),
        "prediction_row_count_by_model_spec": prediction_row_count_by_model_spec,
        "selection_allowed_row_count": selection_allowed_row_count_by_model_spec.get(model_spec_id, 0),
        "selection_allowed_row_count_by_model_spec": selection_allowed_row_count_by_model_spec,
        "selected_pick_count": selected_pick_count_by_model_spec.get(model_spec_id, 0),
        "selected_pick_count_by_model_spec": selected_pick_count_by_model_spec,
        "signal_block_reasons": signal_block_reasons_by_model_spec.get(model_spec_id, []),
        "signal_block_reasons_by_model_spec": signal_block_reasons_by_model_spec,
        "trial_summaries": trial_summaries,
        "trial_diagnostics": trial_diagnostics,
    }


def write_latest_v3_candidate_run_source(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f".{target.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp_path.replace(target)
    return target


def _model_spec_by_id(registry: dict[str, Any], model_spec_id: str) -> dict[str, Any]:
    for spec in registry.get("model_specs") or []:
        if isinstance(spec, dict) and spec.get("model_spec_id") == model_spec_id:
            return spec
    raise RuntimeError(f"v3 model spec not registered: {model_spec_id}")


def _signal_block_reasons(
    predictions: list[dict[str, Any]],
    *,
    selection_policy: dict[str, Any],
    params: dict[str, Any],
) -> list[str]:
    active_rows = [row for row in predictions if row.get("selection_allowed", True)]
    ordered = sorted(active_rows, key=lambda row: _safe_float(row.get("score")), reverse=True)
    return _signal_cash_switch_block_reasons(ordered, selection_policy=selection_policy, params=params)


def _projection_prediction(
    *,
    feature_row: dict[str, Any],
    spec: dict[str, Any],
    params: dict[str, Any],
    selection_policy: dict[str, Any],
    trial_id: str,
    fitted_model: dict[str, Any],
    fitted_model_digest: str,
    horizon_days: int,
) -> dict[str, Any]:
    values = _model_feature_values(feature_row)
    selection_allowed, selection_block_reasons = _selection_allowed(
        values,
        selection_policy=selection_policy,
        params=params,
    )
    portfolio_weight = _position_weight(values, selection_policy=selection_policy, params=params)
    target_horizon_days = _exit_horizon_days(
        values,
        selection_policy=selection_policy,
        params=params,
        default_horizon_days=horizon_days,
    )
    return {
        "trial_id": trial_id,
        "model_spec_id": str(spec.get("model_spec_id") or ""),
        "split_id": "forward-latest-pit",
        "fitted_model_digest": fitted_model_digest,
        "symbol": feature_row.get("symbol"),
        "stock_name": feature_row.get("stock_name"),
        "board": feature_row.get("board"),
        "industry_code": feature_row.get("industry_code"),
        "industry_name": feature_row.get("industry_name"),
        "as_of_date": feature_row.get("as_of_date"),
        "universe_row_id": feature_row.get("universe_row_id"),
        "score": _score_row(
            feature_row,
            model_spec=spec,
            params=params,
            fitted_model=fitted_model,
            feature_values=values,
        ),
        "target_label": 0.0,
        "target_total_return": 0.0,
        "target_horizon_days": target_horizon_days,
        "base_horizon_days": horizon_days,
        "label_status": "forward_projection_no_label",
        "selection_allowed": selection_allowed,
        "selection_block_reasons": selection_block_reasons,
        "portfolio_weight": portfolio_weight if selection_allowed else 0.0,
        "rank_weight_feature_values": _rank_signal_feature_subset(values),
    }
