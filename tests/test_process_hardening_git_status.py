from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ashare_evidence import cli
from ashare_evidence.process_hardening import parse_line_budget, run_process_hardening_check


class ProcessHardeningGitStatusTests(unittest.TestCase):
    def test_clean_git_repo_passes_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = _init_git_repo(temp_root / "repo")
            evaluation_doc = _write_evaluation_doc(temp_root / "evaluation.md")
            target = _write_lines(temp_root / "module.py", 1)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10")],
                require_clean_git_status=True,
                git_root=root,
            )

        self.assertEqual("pass", payload["status"])
        self.assertEqual("clean", payload["git_status"]["status"])

    def test_untracked_file_fails_with_porcelain_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = _init_git_repo(temp_root / "repo")
            evaluation_doc = _write_evaluation_doc(temp_root / "evaluation.md")
            target = _write_lines(temp_root / "module.py", 1)
            (root / "scratch.txt").write_text("leftover\n", encoding="utf-8")

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10")],
                require_clean_git_status=True,
                git_root=root,
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("git_status_dirty", _issue_codes(payload))
        self.assertIn("?? scratch.txt", _raw_git_entries(payload))

    def test_staged_or_modified_tracked_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = _init_git_repo(temp_root / "repo")
            tracked = root / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            _git(root, "add", "tracked.txt")
            tracked.write_text("changed\n", encoding="utf-8")
            evaluation_doc = _write_evaluation_doc(temp_root / "evaluation.md")
            target = _write_lines(temp_root / "module.py", 1)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10")],
                require_clean_git_status=True,
                git_root=root,
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("git_status_dirty", _issue_codes(payload))
        self.assertIn("AM tracked.txt", _raw_git_entries(payload))

    def test_non_git_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 1)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10")],
                require_clean_git_status=True,
                git_root=root,
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("git_status_unavailable", _issue_codes(payload))

    def test_cli_outputs_git_status_and_does_not_initialize_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = _init_git_repo(temp_root / "repo")
            evaluation_doc = _write_evaluation_doc(temp_root / "evaluation.md")
            target = _write_lines(temp_root / "module.py", 1)
            stdout = io.StringIO()

            with patch.object(cli, "init_database", side_effect=AssertionError("database init called")):
                with redirect_stdout(stdout):
                    exit_code = cli.main(
                        [
                            "process-hardening-check",
                            "--evaluation-doc",
                            str(evaluation_doc),
                            "--line-budget",
                            f"{target}:10",
                            "--require-clean-git-status",
                            "--git-root",
                            str(root),
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("clean", payload["git_status"]["status"])


def _init_git_repo(root: Path) -> Path:
    root.mkdir()
    _git(root, "init")
    return root


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _write_evaluation_doc(path: Path) -> Path:
    sections = ["子任务", "评分", "结果", "主进程验证", "重跑记录", "自评"]
    lines = ["# Trial 评估记录", ""]
    for index, section in enumerate(sections, start=1):
        lines.extend([f"## {index}. {section}", "已完成。", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_lines(path: Path, line_count: int) -> Path:
    path.write_text("\n".join(f"line {index}" for index in range(line_count)), encoding="utf-8")
    return path


def _issue_codes(payload: dict[str, object]) -> set[str]:
    return {issue["code"] for issue in payload["issues"]}  # type: ignore[index]


def _raw_git_entries(payload: dict[str, object]) -> set[str]:
    entries = payload["git_status"]["entries"]  # type: ignore[index]
    return {entry["raw"] for entry in entries}
