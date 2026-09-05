"""Point-in-time admission for supervised research labels (stable chronology rules)."""

from __future__ import annotations

from datetime import date
from typing import Any


def label_available_day(row: dict[str, Any], *, horizon_days: int) -> str | None:
    """Read actual outcome dates; never approximate trading days with calendar days."""
    label = row.get("label_row") or row
    explicit_dates = label.get("label_available_dates_by_horizon")
    exit_dates = label.get("exit_dates_by_horizon") or {}
    dates = explicit_dates or exit_dates
    value = dates.get(str(horizon_days), dates.get(horizon_days))
    # Legacy label_status is shared across horizons, so even a 5-day target can
    # depend on the 20-day tradability gate. Wait for all gate outcomes.
    values = [value] if explicit_dates else [value, *exit_dates.values()]
    try:
        available = [date.fromisoformat(str(item)) for item in values]
        signal = date.fromisoformat(str(row.get("as_of_date") or label.get("as_of_date")))
    except (TypeError, ValueError):
        return None
    return max(available).isoformat() if all(day > signal for day in available) else None


def cohort_available_day(rows: list[dict[str, Any]], *, horizon_days: int) -> str | None:
    """A cross-sectional target cohort is usable only once every target is known."""
    available = [label_available_day(row, horizon_days=horizon_days) for row in rows]
    if not available or any(day is None for day in available):
        return None
    return max(available)


def mature_training_dates(
    train_dates: list[str], *, available_by_date: dict[str, str | None], test_start: str
) -> list[str]:
    """Fit before the first test session; a same-day close is not yet observable."""
    return [day for day in train_dates if available_by_date.get(day) and available_by_date[day] < test_start]
