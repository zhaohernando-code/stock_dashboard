from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_required_evidence(raw_value: str) -> dict[str, str]:
    parts = raw_value.split(":", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("required evidence must use path:token")
    path = parts[0].strip()
    token = parts[1].strip()
    if not path:
        raise ValueError("required evidence path must not be empty")
    if not token:
        raise ValueError("required evidence token must not be empty")
    return {"path": path, "token": token}


def check_required_evidence(required_evidence: list[dict[str, str]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []

    for evidence in required_evidence:
        path = Path(evidence["path"])
        token = evidence["token"]
        result = {
            "path": str(path),
            "token": token,
            "exists": path.exists(),
        }
        checked.append(result)
        if not path.exists():
            result["status"] = "missing"
            issues.append(
                {
                    "severity": "error",
                    "code": "required_evidence_file_missing",
                    "path": str(path),
                    "token": token,
                    "message": "required evidence file does not exist",
                }
            )
            continue

        contains_token = token in path.read_text(encoding="utf-8")
        result["contains_token"] = contains_token
        result["status"] = "checked" if contains_token else "missing_token"
        if not contains_token:
            issues.append(
                {
                    "severity": "error",
                    "code": "required_evidence_token_missing",
                    "path": str(path),
                    "token": token,
                    "message": "required evidence token was not found",
                }
            )

    return {"required_evidence": checked, "issues": issues}
