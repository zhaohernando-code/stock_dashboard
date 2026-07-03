from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.model_exploration_snapshot import (
    DEFAULT_HORIZONS,
    MODEL_EXPLORATION_ACCOUNT_PROFILE,
    MODEL_EXPLORATION_PROTOCOL_VERSION,
)
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_SPEC_REGISTRY_SCHEMA_VERSION = "model_spec_registry.v1"
MODEL_SPEC_REGISTRY_ID = "shortpick-model-spec-registry-v1"


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _grid_trial_count(grid: dict[str, list[Any]]) -> int:
    count = 1
    for values in grid.values():
        count *= max(len(values), 1)
    return count


def _promotion_gates() -> dict[str, Any]:
    return {
        "oos_rank_ic_min": 0.02,
        "icir_min": 0.35,
        "positive_ic_month_rate_min": 0.55,
        "deflated_sharpe_confidence_min": 0.95,
        "pbo_max": 0.10,
        "alpha_t_stat_min": 3.0,
        "cost_stress_multiplier": 2.0,
        "winner_dependency_policy": "top_symbol_day_month_removal_must_not_collapse",
    }


def _base_spec(
    *,
    model_spec_id: str,
    model_type: str,
    purpose: str,
    feature_groups: list[str],
    hyperparameter_grid: dict[str, list[Any]],
    training_window_days: list[int],
    prediction_horizon_days: int = 10,
    dynamic_weight_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    max_trials = _grid_trial_count(hyperparameter_grid)
    return {
        "model_spec_id": model_spec_id,
        "model_type": model_type,
        "purpose": purpose,
        "status": "research_candidate_spec",
        "account_profile": MODEL_EXPLORATION_ACCOUNT_PROFILE,
        "allowed_feature_groups": feature_groups,
        "prediction_horizon_days": prediction_horizon_days,
        "training_window_days": training_window_days,
        "purge_days": max(DEFAULT_HORIZONS),
        "embargo_days": max(DEFAULT_HORIZONS),
        "hyperparameter_grid": hyperparameter_grid,
        "max_trials": max_trials,
        "monotonic_or_sign_constraints": {},
        "dynamic_weight_policy": dynamic_weight_policy
        or {
            "enabled": False,
            "reason": "static_or_baseline_spec",
        },
        "cost_model": {
            "round_trip_cost": 0.001,
            "stress_multiplier": 2.0,
        },
        "promotion_gates": _promotion_gates(),
        "production_effect": "forbidden",
        "claim_ceiling": "research_spec_only",
    }


def default_model_specs() -> list[dict[str, Any]]:
    return [
        _base_spec(
            model_spec_id="baseline_momentum_10d_turnover_cooldown_v1",
            model_type="deterministic_baseline",
            purpose="Recreate the current momentum-volume family as a controlled baseline, not a promoted strategy.",
            feature_groups=["price_momentum", "liquidity", "execution", "crowding"],
            training_window_days=[120],
            hyperparameter_grid={
                "top_k": [5],
                "momentum_horizon_days": [10],
                "turnover_rank_weight": [1.0],
                "cooldown_days": [10],
            },
        ),
        _base_spec(
            model_spec_id="ranked_feature_linear_v1",
            model_type="regularized_rank_linear",
            purpose="Combine PIT feature groups with bounded coefficients and fixed walk-forward windows.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "crowding",
            ],
            training_window_days=[120, 240],
            hyperparameter_grid={
                "regularization_alpha": [0.1, 1.0],
                "rank_normalization": ["cross_sectional_percentile"],
                "winsorize_quantile": [0.01, 0.05],
            },
        ),
        _base_spec(
            model_spec_id="ranked_tree_shallow_v1",
            model_type="shallow_tree_ranker",
            purpose="Test bounded nonlinear feature interactions without opening a broad search.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "crowding",
            ],
            training_window_days=[240],
            hyperparameter_grid={
                "max_depth": [2, 3],
                "min_samples_leaf": [50, 100],
                "learning_rate": [0.03],
            },
        ),
        _base_spec(
            model_spec_id="regime_conditioned_linear_v1",
            model_type="bounded_regime_conditioned_linear",
            purpose="Allow slow regime-conditioned weights only after enough independent windows exist.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
                "crowding",
            ],
            training_window_days=[240],
            hyperparameter_grid={
                "regularization_alpha": [0.5, 1.0],
                "regime_bucket": ["benchmark_trend_volatility"],
                "weight_multiplier_clip": [(0.5, 1.5)],
            },
            dynamic_weight_policy={
                "enabled": True,
                "function_family": "slow_regime_conditioned_multiplier",
                "min_independent_windows": 20,
                "min_rolling_ic_periods": 60,
                "sensitivity_max": 0.3,
                "multiplier_clip": [0.5, 1.5],
                "requires_oos_gate_pass": True,
                "requires_governance_approval": True,
            },
        ),
        _base_spec(
            model_spec_id="pullback_reversal_5d_v1",
            model_type="pullback_reversal_ranker",
            purpose="Search for short-horizon recoveries after mild pullbacks without chasing one-day overheated names.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
            ],
            prediction_horizon_days=5,
            training_window_days=[60, 120],
            hyperparameter_grid={
                "pullback_weight": [1.0, 1.2],
                "trend_context_weight": [0.25, 0.35],
                "volatility_penalty": [0.35],
            },
        ),
        _base_spec(
            model_spec_id="liquidity_breakout_5d_v1",
            model_type="liquidity_breakout_ranker",
            purpose="Search for short-horizon momentum names with liquidity confirmation and overheat penalty.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "crowding",
                "regime",
            ],
            prediction_horizon_days=5,
            training_window_days=[60, 120],
            hyperparameter_grid={
                "momentum_weight": [0.5, 0.7],
                "liquidity_confirmation_weight": [0.25, 0.35],
                "overheat_penalty": [0.25],
            },
        ),
        _base_spec(
            model_spec_id="trend_quality_20d_v1",
            model_type="trend_quality_ranker",
            purpose="Search for longer-horizon trend quality after controlling volatility and distance from recent highs.",
            feature_groups=[
                "price_momentum",
                "reversal_overheat",
                "volatility_risk",
                "liquidity",
                "execution",
                "regime",
            ],
            prediction_horizon_days=20,
            training_window_days=[120, 240],
            hyperparameter_grid={
                "trend_weight": [0.8, 1.0],
                "high_distance_weight": [0.4, 0.5],
                "volatility_penalty": [0.35, 0.45],
            },
        ),
    ]


def validate_model_spec_registry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    specs = list(payload.get("model_specs") or [])
    spec_ids = [str(spec.get("model_spec_id") or "") for spec in specs]
    failures: list[str] = []
    if len(spec_ids) != len(set(spec_ids)):
        failures.append("duplicate_model_spec_id")
    for spec in specs:
        spec_id = str(spec.get("model_spec_id") or "")
        grid = spec.get("hyperparameter_grid")
        if not isinstance(grid, dict) or not grid:
            failures.append(f"{spec_id}:missing_hyperparameter_grid")
            continue
        declared_max_trials = int(spec.get("max_trials") or 0)
        actual_trials = _grid_trial_count({str(key): list(value) for key, value in grid.items() if isinstance(value, list)})
        if declared_max_trials != actual_trials:
            failures.append(f"{spec_id}:max_trials_mismatch")
        if actual_trials > 16:
            failures.append(f"{spec_id}:unbounded_search_space")
        if spec.get("production_effect") != "forbidden":
            failures.append(f"{spec_id}:production_effect_not_forbidden")
        if not spec.get("allowed_feature_groups"):
            failures.append(f"{spec_id}:missing_feature_groups")
    return {
        "status": "passed" if not failures else "failed",
        "failure_count": len(failures),
        "failures": failures,
    }


def build_model_spec_registry_artifact(
    *,
    validation_run_id: str,
    source_input_snapshot_id: str | None = None,
) -> dict[str, Any]:
    model_specs = default_model_specs()
    content_digest = _stable_digest(model_specs)
    artifact_id = f"model-spec-registry-{content_digest[:16]}"
    payload = {
        "artifact_type": "model_spec_registry",
        "schema_version": MODEL_SPEC_REGISTRY_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "registry_id": MODEL_SPEC_REGISTRY_ID,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_input_snapshot_id or "not_applicable_registry_only",
        "source_data_time_range": {"status": "not_applicable_registry_only"},
        "feature_version": "declared_by_candidate_runner",
        "label_version": "declared_by_candidate_runner",
        "code_version": "unresolved_local_checkout",
        "config_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
        "validation_protocol": {
            "protocol_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
            "primary_role": "governed_model_spec_registry",
            "runner_policy": "candidate_runner_may_only_execute_registered_specs",
            "broad_search_policy": "forbidden_outside_registered_hyperparameter_grid",
            "production_effect": "forbidden",
        },
        "gate_readout": {
            "gate_status": "registry_ready",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "research_spec_only",
            "blocking_gate_ids": ["candidate_runner_not_implemented", "oos_validation_not_run"],
        },
        "claim_ceiling": "research_spec_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_input_snapshot_id": source_input_snapshot_id,
        "model_spec_count": len(model_specs),
        "model_spec_ids": [str(spec["model_spec_id"]) for spec in model_specs],
        "model_specs": model_specs,
        "registry_content_digest": content_digest,
    }
    payload["validation"] = validate_model_spec_registry_payload(payload)
    return payload


def write_model_spec_registry_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> Path:
    return write_research_validation_artifact(
        "model_spec_registry",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
