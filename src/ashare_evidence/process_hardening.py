from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

REQUIRED_EVALUATION_SECTIONS = ("子任务", "评分", "结果", "主进程验证", "重跑记录", "自评")
INCOMPLETE_MARKERS = ("待执行", "待补录", "等待主进程", "TODO")


def parse_line_budget(raw_value: str) -> dict[str, Any]:
    parts = raw_value.rsplit(":", maxsplit=2)
    if len(parts) not in {2, 3}:
        raise ValueError("line budget must use path:hard_limit or path:hard_limit:warning_limit")
    path = parts[0].strip()
    if not path:
        raise ValueError("line budget path must not be empty")
    try:
        hard_limit = int(parts[1])
        warning_limit = int(parts[2]) if len(parts) == 3 else None
    except ValueError as exc:
        raise ValueError("line budget limits must be integers") from exc
    if hard_limit <= 0:
        raise ValueError("line budget hard limit must be positive")
    if warning_limit is not None and warning_limit <= 0:
        raise ValueError("line budget warning limit must be positive")
    return {
        "path": path,
        "hard_limit": hard_limit,
        "warning_limit": warning_limit,
    }


def run_process_hardening_check(
    *,
    evaluation_docs: list[str | Path],
    line_budgets: list[dict[str, Any]],
    fail_on_warning: bool = False,
    require_clean_git_status: bool = False,
    git_root: str | Path = ".",
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    checked_docs: list[dict[str, Any]] = []
    checked_line_budgets: list[dict[str, Any]] = []
    git_status = _skipped_git_status(git_root)

    for doc_path_value in evaluation_docs:
        doc_path = Path(doc_path_value)
        doc_result = {
            "path": str(doc_path),
            "exists": doc_path.exists(),
            "required_sections": list(REQUIRED_EVALUATION_SECTIONS),
        }
        checked_docs.append(doc_result)
        if not doc_path.exists():
            issues.append(
                {
                    "severity": "error",
                    "code": "evaluation_doc_missing",
                    "path": str(doc_path),
                    "message": "evaluation doc does not exist",
                }
            )
            continue

        content = doc_path.read_text(encoding="utf-8")
        headings = _markdown_headings(content)
        missing_sections = [section for section in REQUIRED_EVALUATION_SECTIONS if not _has_section(headings, section)]
        doc_result["missing_sections"] = missing_sections
        for section in missing_sections:
            issues.append(
                {
                    "severity": "error",
                    "code": "evaluation_section_missing",
                    "path": str(doc_path),
                    "section": section,
                    "message": f"evaluation doc is missing section: {section}",
                }
            )

        incomplete_matches = _find_incomplete_markers(content)
        doc_result["incomplete_markers"] = incomplete_matches
        for match in incomplete_matches:
            issues.append(
                {
                    "severity": "error",
                    "code": "evaluation_incomplete_marker",
                    "path": str(doc_path),
                    "marker": match["marker"],
                    "line": match["line"],
                    "message": f"evaluation doc contains unfinished marker: {match['marker']}",
                }
            )

    for budget in line_budgets:
        budget_result = _check_line_budget(budget)
        checked_line_budgets.append(budget_result)
        if budget_result["status"] == "missing":
            issues.append(
                {
                    "severity": "error",
                    "code": "line_budget_file_missing",
                    "path": budget_result["path"],
                    "message": "line budget target does not exist",
                }
            )
            continue
        if budget_result["line_count"] > budget_result["hard_limit"]:
            issues.append(
                {
                    "severity": "error",
                    "code": "line_budget_hard_limit_exceeded",
                    "path": budget_result["path"],
                    "line_count": budget_result["line_count"],
                    "hard_limit": budget_result["hard_limit"],
                    "message": "line count exceeds hard limit",
                }
            )
        warning_limit = budget_result.get("warning_limit")
        if warning_limit is not None and budget_result["line_count"] >= warning_limit:
            issues.append(
                {
                    "severity": "warning",
                    "code": "line_budget_warning_limit_reached",
                    "path": budget_result["path"],
                    "line_count": budget_result["line_count"],
                    "warning_limit": warning_limit,
                    "message": "line count reached warning limit",
                }
            )

    if require_clean_git_status:
        git_status = _check_git_status(git_root)
        if git_status["status"] in {"dirty", "unavailable"}:
            issues.append(_git_status_issue(git_status))

    has_error = any(issue["severity"] == "error" for issue in issues)
    has_warning = any(issue["severity"] == "warning" for issue in issues)
    status = "fail" if has_error or (fail_on_warning and has_warning) else "pass"
    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
        "checked_docs": checked_docs,
        "line_budgets": checked_line_budgets,
        "git_status": git_status,
    }


def _markdown_headings(content: str) -> list[str]:
    headings: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        headings.append(stripped.lstrip("#").strip())
    return headings


def _has_section(headings: list[str], section: str) -> bool:
    return any(section in heading for heading in headings)


def _find_incomplete_markers(content: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for marker in INCOMPLETE_MARKERS:
            if marker in line:
                matches.append({"marker": marker, "line": line_number})
    return matches


def _check_line_budget(budget: dict[str, Any]) -> dict[str, Any]:
    path = Path(budget["path"])
    result = {
        "path": str(path),
        "hard_limit": budget["hard_limit"],
        "warning_limit": budget.get("warning_limit"),
        "exists": path.exists(),
    }
    if not path.exists():
        return {**result, "status": "missing"}
    line_count = len(path.read_text(encoding="utf-8").splitlines())
    return {
        **result,
        "status": "checked",
        "line_count": line_count,
    }


def _skipped_git_status(git_root: str | Path) -> dict[str, Any]:
    return {"required": False, "root": str(git_root), "status": "skipped", "entries": []}


def _check_git_status(git_root: str | Path) -> dict[str, Any]:
    root = Path(git_root)
    if shutil.which("git") is None:
        return _unavailable_git_status(root, "git executable not found")
    command = ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return _unavailable_git_status(root, str(exc))
    if completed.returncode != 0:
        return _unavailable_git_status(root, (completed.stderr or completed.stdout).strip())
    entries = [_parse_git_status_entry(line) for line in completed.stdout.splitlines() if line]
    return {"required": True, "root": str(root), "status": "dirty" if entries else "clean", "entries": entries}


def _unavailable_git_status(root: Path, detail: str) -> dict[str, Any]:
    return {"required": True, "root": str(root), "status": "unavailable", "entries": [], "detail": detail}


def _git_status_issue(git_status: dict[str, Any]) -> dict[str, Any]:
    issue = {"severity": "error", "git_root": git_status["root"]}
    if git_status["status"] == "dirty":
        return {
            **issue,
            "code": "git_status_dirty",
            "entries": git_status["entries"],
            "message": "git status is not clean",
        }
    return {
        **issue,
        "code": "git_status_unavailable",
        "message": "git status could not be checked",
        "detail": git_status.get("detail", ""),
    }


def _parse_git_status_entry(line: str) -> dict[str, str]:
    return {"raw": line, "status": line[:2], "path": line[3:] if len(line) > 3 else ""}
