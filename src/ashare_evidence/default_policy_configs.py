from __future__ import annotations

from copy import deepcopy
from typing import Any

POLICY_SCOPE_STOCK_DASHBOARD = "stock_dashboard"
POLICY_SCOPE_SIGNAL_ENGINE = "signal_engine"
POLICY_SCOPE_PHASE5 = "phase5"
POLICY_SCOPE_SHORTPICK_LAB = "shortpick_lab"
POLICY_SCOPE_FRONTEND = "frontend"

DATA_QUALITY_CONFIG_KEY = "data_quality.scoring_v1"
SIGNAL_FUSION_CONFIG_KEY = "signal_engine.fusion_v1"
PHASE5_SIMULATION_CONFIG_KEY = "phase5.simulation_policy_v1"
SHORTPICK_VALIDATION_CONFIG_KEY = "shortpick_lab.validation_v1"
FRONTEND_DISPLAY_CONFIG_KEY = "frontend.display_v1"

DEFAULT_POLICY_CONFIGS: dict[tuple[str, str], dict[str, Any]] = {
    (POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY): {
        "weights": {
            "daily_completeness": 0.40,
            "price_freshness": 0.15,
            "news_coverage": 0.20,
            "financial_freshness": 0.15,
            "profile_completeness": 0.10,
        },
        "thresholds": {"pass": 0.85, "warn": 0.65},
        "daily_completeness": {"recent_day_limit": 20, "qa_warning_score_cap": 0.75},
        "price_freshness": {"pass_age_days": 2, "warn_age_days": 5, "warn_score": 0.70, "stale_score": 0.25},
        "news_coverage": {
            "lookback_days": 30,
            "pass_recent_count": 2,
            "single_news_score": 0.80,
            "missing_news_score": 0.65,
        },
        "financial_freshness": {
            "pass_age_days": 120,
            "warn_age_days": 210,
            "warn_score": 0.70,
            "stale_score": 0.25,
        },
        "profile_completeness": {"missing_field_penalty": 0.20},
    },
    (POLICY_SCOPE_SIGNAL_ENGINE, SIGNAL_FUSION_CONFIG_KEY): {
        "base_weights": {
            "price_baseline": 0.35,
            "news_event": 0.20,
            "fundamental": 0.15,
            "size_factor": 0.10,
            "reversal": 0.10,
            "liquidity": 0.10,
        },
        "no_fundamental_size_weights": {
            "price_baseline": 0.47,
            "news_event": 0.27,
            "fundamental": 0.0,
            "size_factor": 0.0,
            "reversal": 0.13,
            "liquidity": 0.13,
        },
        "confidence_defaults": {
            "price_baseline": 0.44,
            "news_event": 0.36,
            "fundamental": 0.30,
            "size_factor": 0.35,
            "reversal": 0.30,
            "liquidity": 0.30,
        },
        "confidence_tilts": {
            "price_baseline": {"center": 0.50, "scale": 0.30},
            "news_event": {"center": 0.50, "scale": 0.30},
            "fundamental": {"center": 0.30, "scale": 0.30},
            "size_factor": {"center": 0.35, "scale": 0.30},
            "reversal": {"center": 0.30, "scale": 0.30},
            "liquidity": {"center": 0.30, "scale": 0.30},
        },
        "penalties": {
            "stale_hours_threshold": 36,
            "stale_score_penalty": 0.10,
            "evidence_gap_score_penalty": 0.12,
            "confidence_stale_penalty_scale": 0.15,
            "event_conflict_high_threshold": 0.45,
        },
        "confidence": {
            "minimum": 0.10,
            "maximum": 0.85,
            "fallback": 0.35,
        },
        "model_result": {
            "non_primary_horizon_multiplier": 0.94,
            "return_feature_weight": 0.18,
            "trend_component_weight": 0.08,
            "risk_pressure_weight": 0.06,
            "news_conflict_weight": 0.06,
            "expected_return_scale": 0.05,
            "expected_return_min": -0.15,
            "expected_return_max": 0.18,
            "confidence_fusion_weight": 0.70,
            "confidence_score_weight": 0.20,
        },
    },
    (POLICY_SCOPE_PHASE5, PHASE5_SIMULATION_CONFIG_KEY): {
        "max_position_count": 5,
        "max_single_weight": 0.20,
        "board_lot": 100,
        "cash_allowed": True,
        "promotion_gate_version": "phase5-holding-policy-promotion-gate-draft-v1",
    },
    (POLICY_SCOPE_SHORTPICK_LAB, SHORTPICK_VALIDATION_CONFIG_KEY): {
        "horizons": [1, 3, 5, 10, 20],
        "benchmarks": ["CSI300", "CSI1000", "primary_sector_equal_weight_proxy"],
        "normal_display_blocked_validation_statuses": [
            "pending_market_data",
            "pending_entry_bar",
            "suspended_or_no_current_bar",
            "entry_unfillable_limit_up",
            "tradeability_uncertain",
        ],
    },
    (POLICY_SCOPE_FRONTEND, FRONTEND_DISPLAY_CONFIG_KEY): {
        "status_projection": "backend_status_first",
        "frontend_business_thresholds": "forbidden_except_api_projection",
        "default_operations_policy_tab": "governance",
    },
}

DEFAULT_POLICY_CONFIG_SCHEMAS: dict[tuple[str, str], dict[str, Any]] = {
    key: {
        "type": "object",
        "required": sorted(value.keys()),
        "additionalProperties": True,
    }
    for key, value in DEFAULT_POLICY_CONFIGS.items()
}

DEFAULT_POLICY_CONFIG_REASONS: dict[tuple[str, str], str] = {
    (POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY): "Initial code-default snapshot of data-quality scoring weights and thresholds.",
    (POLICY_SCOPE_SIGNAL_ENGINE, SIGNAL_FUSION_CONFIG_KEY): "Initial code-default snapshot of signal-fusion formula parameters.",
    (POLICY_SCOPE_PHASE5, PHASE5_SIMULATION_CONFIG_KEY): "Initial Phase 5 simulation policy constraints remain code-governed defaults.",
    (POLICY_SCOPE_SHORTPICK_LAB, SHORTPICK_VALIDATION_CONFIG_KEY): "Initial Short Pick Lab validation and display boundary parameters.",
    (POLICY_SCOPE_FRONTEND, FRONTEND_DISPLAY_CONFIG_KEY): "Initial frontend governance contract: display reads backend projections instead of hardcoding business thresholds.",
}


def default_policy_config_payload(scope: str, config_key: str) -> dict[str, Any]:
    payload = DEFAULT_POLICY_CONFIGS[(scope, config_key)]
    return deepcopy(payload)


def default_policy_config_schema(scope: str, config_key: str) -> dict[str, Any]:
    return deepcopy(DEFAULT_POLICY_CONFIG_SCHEMAS[(scope, config_key)])


def iter_default_policy_configs() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (scope, config_key, default_policy_config_payload(scope, config_key))
        for scope, config_key in sorted(DEFAULT_POLICY_CONFIGS)
    ]
