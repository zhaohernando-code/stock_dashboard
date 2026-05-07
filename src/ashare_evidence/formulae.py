from __future__ import annotations

from math import sqrt
from typing import Any


def score_status(score: float, *, pass_threshold: float, warn_threshold: float) -> str:
    if score >= pass_threshold:
        return "pass"
    if score >= warn_threshold:
        return "warn"
    return "fail"


def weighted_component_score(components: dict[str, dict[str, Any]], weights: dict[str, float]) -> float:
    return sum(float(components[key]["score"]) * float(weight) for key, weight in weights.items())


def missing_field_completeness_score(missing: list[str], *, penalty_per_field: float) -> float:
    return max(1.0 - len(set(missing)) * penalty_per_field, 0.0)


def freshness_score(
    age_days: int | None,
    *,
    pass_age_days: int,
    warn_age_days: int,
    warn_score: float,
    stale_score: float,
) -> float:
    if age_days is None:
        return 0.0
    if age_days <= pass_age_days:
        return 1.0
    if age_days <= warn_age_days:
        return warn_score
    return stale_score


def dynamic_factor_weights(
    *,
    base_weights: dict[str, float],
    no_fundamental_size_weights: dict[str, float],
    confidences: dict[str, float],
    fundamental_weight: float,
    size_weight: float,
    confidence_tilts: dict[str, dict[str, float]],
) -> dict[str, float]:
    if fundamental_weight == 0 and size_weight == 0:
        return dict(no_fundamental_size_weights)
    total_confidence = sum(float(value) for value in confidences.values())
    factor_count = len(confidences)
    if total_confidence <= 0 or factor_count <= 0:
        return dict(base_weights)
    normalized: dict[str, float] = {}
    average_confidence = total_confidence / factor_count
    for factor_key, base_weight in base_weights.items():
        confidence = float(confidences.get(factor_key, 0.0))
        tilt = confidence_tilts.get(factor_key, {})
        center = float(tilt.get("center", 0.5))
        scale = float(tilt.get("scale", 0.3))
        normalized[factor_key] = round(
            float(base_weight) * (confidence / average_confidence) * (1 + (confidence - center) * scale),
            4,
        )
    total_weight = sum(normalized.values())
    if total_weight > 0:
        normalized = {key: round(value / total_weight, 4) for key, value in normalized.items()}
    return normalized


def weighted_rms_confidence(
    *,
    weights: dict[str, float],
    confidences: dict[str, float],
    fallback: float,
) -> float:
    numerator = sum((float(weights.get(key, 0.0)) ** 2) * (float(confidences.get(key, fallback)) ** 2) for key in weights)
    denominator = sum(float(value) ** 2 for value in weights.values())
    return sqrt(numerator / denominator) if denominator > 0 else fallback
