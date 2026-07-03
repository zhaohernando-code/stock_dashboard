from __future__ import annotations

from typing import Any

OPERATIONS_NAV_HISTORY_POINT_LIMIT = 90


def sample_operations_nav_history(
    points: list[dict[str, Any]],
    *,
    limit: int = OPERATIONS_NAV_HISTORY_POINT_LIMIT,
) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return list(points)
    if limit <= 0:
        return []
    if limit == 1:
        return [points[-1]]

    def numeric_value(index: int, key: str, *, default: float) -> float:
        value = points[index].get(key)
        return float(value) if isinstance(value, (int, float)) else default

    last_index = len(points) - 1
    priority_indexes: list[int] = [0, last_index]
    extrema_specs = [
        ("nav", min, float("inf")),
        ("nav", max, float("-inf")),
        ("benchmark_nav", min, float("inf")),
        ("benchmark_nav", max, float("-inf")),
        ("drawdown", min, float("inf")),
        ("exposure", max, float("-inf")),
    ]
    for key, picker, default in extrema_specs:
        candidate = picker(range(len(points)), key=lambda index: numeric_value(index, key, default=default))
        if candidate not in priority_indexes:
            priority_indexes.append(candidate)
        if len(priority_indexes) >= limit:
            return [points[index] for index in sorted(priority_indexes[:limit])]

    sampled_indexes = set(priority_indexes)
    remaining_budget = limit - len(sampled_indexes)
    for index in range(remaining_budget):
        sampled_indexes.add(round(index * last_index / max(remaining_budget - 1, 1)))
    return [points[index] for index in sorted(sampled_indexes)]


def compact_operations_simulation_workspace(workspace: dict[str, Any]) -> dict[str, Any]:
    compact = dict(workspace)
    for track_key in ("manual_track", "model_track"):
        track = compact.get(track_key)
        if not isinstance(track, dict):
            continue
        track_copy = dict(track)
        portfolio = track_copy.get("portfolio")
        if isinstance(portfolio, dict):
            portfolio_copy = dict(portfolio)
            nav_history = portfolio_copy.get("nav_history")
            if isinstance(nav_history, list):
                portfolio_copy["nav_history"] = sample_operations_nav_history(nav_history)
            track_copy["portfolio"] = portfolio_copy
        compact[track_key] = track_copy
    return compact
