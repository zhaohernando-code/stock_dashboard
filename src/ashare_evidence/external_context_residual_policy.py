from __future__ import annotations

from datetime import datetime
from typing import Any

STATIC_EXTERNAL_WEIGHT_LADDER = (0.0, 0.025, 0.05, 0.075, 0.1, 0.15)
SUPPORTED_RESIDUAL_CAPS = (0.15, 0.3, 0.5)
SUPPORTED_EXTERNAL_CHANNELS = {"global_state", "sector_state", "individual_event"}
CONSTRAINED_MODEL_LADDER = (
    "regularized_logistic",
    "generalized_additive_model",
    "monotonic_gradient_boosted_tree",
)


def _aware_datetime(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def compute_external_residual(
    *,
    external_signal: float,
    predicted_external_from_core: float,
    prediction_model_fit_end: str,
    decision_cutoff: str,
) -> dict[str, Any]:
    fit_end = _aware_datetime(prediction_model_fit_end, field="prediction_model_fit_end")
    cutoff = _aware_datetime(decision_cutoff, field="decision_cutoff")
    if fit_end >= cutoff:
        raise ValueError("residual model must be fitted strictly before the decision cutoff")
    residual = float(external_signal) - float(predicted_external_from_core)
    return {
        "external_signal": float(external_signal),
        "predicted_external_from_core": float(predicted_external_from_core),
        "external_residual": residual,
        "prediction_model_fit_end": fit_end.isoformat(),
        "decision_cutoff": cutoff.isoformat(),
        "fit_is_past_only": True,
        "interpretation": "positive_residual_is_incremental_adverse_external_information",
    }


def apply_bounded_external_residual(
    *,
    channel: str,
    core_score_z: float,
    external_residual_z: float,
    lambda_weight: float,
    cap: float,
    core_eligible: bool,
    official_major_negative_gate: bool = False,
) -> dict[str, Any]:
    if channel not in SUPPORTED_EXTERNAL_CHANNELS:
        raise ValueError(f"unsupported external channel: {channel}")
    weight = float(lambda_weight)
    if weight not in STATIC_EXTERNAL_WEIGHT_LADDER:
        raise ValueError("lambda_weight must be a preregistered static ladder value")
    bounded_cap = float(cap)
    if bounded_cap not in SUPPORTED_RESIDUAL_CAPS:
        raise ValueError("cap must be a preregistered primary or sensitivity value")
    residual_adjustment = _clip(weight * float(external_residual_z), -bounded_cap, bounded_cap)

    final_score_z = float(core_score_z)
    gross_exposure_multiplier = 1.0
    score_scope = "none"
    if channel == "global_state":
        gross_exposure_multiplier = _clip(1.0 - residual_adjustment, 0.0, 1.0)
        score_scope = "portfolio_gross_exposure_only"
    elif channel == "sector_state":
        final_score_z -= residual_adjustment
        score_scope = "within_sector_ranking_only"
    else:
        final_score_z -= residual_adjustment
        score_scope = "individual_incremental_score_only"

    risk_gate_blocked = bool(official_major_negative_gate)
    final_eligible = bool(core_eligible) and not risk_gate_blocked
    return {
        "channel": channel,
        "formula": "z(core_score)-clip(lambda*z(external_residual),-cap,+cap)",
        "external_residual_direction": "positive_is_adverse",
        "core_score_z": float(core_score_z),
        "external_residual_z": float(external_residual_z),
        "lambda_weight": weight,
        "cap": bounded_cap,
        "bounded_residual_adjustment": residual_adjustment,
        "final_score_z": final_score_z,
        "gross_exposure_multiplier": gross_exposure_multiplier,
        "score_scope": score_scope,
        "core_eligible": bool(core_eligible),
        "official_major_negative_gate": risk_gate_blocked,
        "final_eligible": final_eligible,
        "positive_external_information_can_create_eligibility": False,
        "v3_baseline_preserved": weight == 0.0,
    }


def select_smallest_weight_within_one_standard_error(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        weight = float(candidate.get("lambda_weight"))
        if weight not in STATIC_EXTERNAL_WEIGHT_LADDER:
            raise ValueError("candidate lambda_weight must be in the preregistered ladder")
        if not candidate.get("all_gates_passed"):
            continue
        mean = float(candidate.get("oos_mean"))
        standard_error = float(candidate.get("oos_standard_error"))
        if standard_error < 0:
            raise ValueError("oos_standard_error must be non-negative")
        eligible.append(
            {
                **candidate,
                "lambda_weight": weight,
                "oos_mean": mean,
                "oos_standard_error": standard_error,
            }
        )
    if not eligible:
        return {
            "status": "blocked_no_gate_passing_candidate",
            "selected_lambda_weight": None,
            "selection_rule": "smallest_weight_within_one_standard_error_of_best_oos_mean",
        }
    best = max(eligible, key=lambda row: (row["oos_mean"], -row["lambda_weight"]))
    lower_bound = best["oos_mean"] - best["oos_standard_error"]
    within_one_se = [row for row in eligible if row["oos_mean"] >= lower_bound]
    selected = min(within_one_se, key=lambda row: row["lambda_weight"])
    return {
        "status": "selected_research_candidate",
        "selection_rule": "smallest_weight_within_one_standard_error_of_best_oos_mean",
        "best_lambda_weight": best["lambda_weight"],
        "best_oos_mean": best["oos_mean"],
        "best_oos_standard_error": best["oos_standard_error"],
        "one_standard_error_lower_bound": lower_bound,
        "selected_lambda_weight": selected["lambda_weight"],
        "selected_oos_mean": selected["oos_mean"],
        "eligible_candidate_count": len(eligible),
        "within_one_standard_error_count": len(within_one_se),
        "v3_lambda_zero_retained_in_comparison": any(row["lambda_weight"] == 0.0 for row in eligible),
    }
