from __future__ import annotations

from typing import Any


def parse_line_budget_warning_margin(raw_value: str) -> dict[str, Any]:
    parts = raw_value.rsplit(":", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("line budget warning margin must use path:minimum_remaining")
    path = parts[0].strip()
    if not path:
        raise ValueError("line budget warning margin path must not be empty")
    try:
        minimum_remaining = int(parts[1])
    except ValueError as exc:
        raise ValueError("line budget warning margin minimum remaining must be an integer") from exc
    if minimum_remaining <= 0:
        raise ValueError("line budget warning margin minimum remaining must be positive")
    return {"path": path, "minimum_remaining": minimum_remaining}


def check_line_budget_warning_margins(
    checked_line_budgets: list[dict[str, Any]],
    margin_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    by_path = {budget["path"]: budget for budget in checked_line_budgets}
    issues: list[dict[str, Any]] = []
    checked_margins: list[dict[str, Any]] = []

    for spec in margin_specs:
        path = spec["path"]
        minimum_remaining = spec["minimum_remaining"]
        budget = by_path.get(path)
        result = {"path": path, "minimum_remaining": minimum_remaining}
        if budget is None:
            checked_margins.append({**result, "status": "missing_line_budget"})
            issues.append(
                {
                    "severity": "error",
                    "code": "line_budget_warning_margin_missing_budget",
                    "path": path,
                    "message": "warning margin target is not present in line budgets",
                }
            )
            continue

        warning_limit = budget.get("warning_limit")
        if warning_limit is None:
            checked_margins.append({**result, "status": "missing_warning_limit"})
            issues.append(
                {
                    "severity": "error",
                    "code": "line_budget_warning_margin_missing_warning_limit",
                    "path": path,
                    "message": "warning margin target has no line budget warning limit",
                }
            )
            continue

        if "line_count" not in budget:
            checked_margins.append({**result, "status": "line_budget_not_checked"})
            continue

        line_count = budget["line_count"]
        remaining = warning_limit - line_count
        checked_margins.append(
            {
                **result,
                "status": "checked",
                "line_count": line_count,
                "warning_limit": warning_limit,
                "remaining": remaining,
            }
        )
        if remaining < minimum_remaining:
            issues.append(
                {
                    "severity": "warning",
                    "code": "line_budget_warning_margin_low",
                    "path": path,
                    "line_count": line_count,
                    "warning_limit": warning_limit,
                    "minimum_remaining": minimum_remaining,
                    "remaining": remaining,
                    "message": "line count is too close to warning limit",
                }
            )

    return {"issues": issues, "line_budget_warning_margins": checked_margins}
