from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_forbidden_source_token(raw_value: str) -> dict[str, str]:
    parts = raw_value.split(":", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("forbidden source token must use path:token")
    path = parts[0].strip()
    token = parts[1].strip()
    if not path:
        raise ValueError("forbidden source token path must not be empty")
    if not token:
        raise ValueError("forbidden source token must not be empty")
    return {"path": path, "token": token}


def check_forbidden_source_tokens(forbidden_source_tokens: list[dict[str, str]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []

    for forbidden_token in forbidden_source_tokens:
        path = Path(forbidden_token["path"])
        token = forbidden_token["token"]
        result: dict[str, Any] = {"path": str(path), "token": token, "exists": path.exists()}
        checked.append(result)
        if not path.exists():
            result["status"] = "missing"
            issues.append(
                {
                    "severity": "error",
                    "code": "forbidden_source_file_missing",
                    "path": str(path),
                    "token": token,
                    "message": "forbidden source token target does not exist",
                }
            )
            continue

        matches = _matching_lines(path, token)
        result["matches"] = matches
        result["status"] = "failed" if matches else "checked"
        for match in matches:
            issues.append(
                {
                    "severity": "error",
                    "code": "forbidden_source_token_found",
                    "path": str(path),
                    "token": token,
                    "line": match["line"],
                    "message": "forbidden source token was found",
                }
            )

    return {"forbidden_source_tokens": checked, "issues": issues}


def _matching_lines(path: Path, token: str) -> list[dict[str, int]]:
    matches: list[dict[str, int]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if token in line:
            matches.append({"line": line_number})
    return matches
