from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ashare_evidence import cli
from ashare_evidence.process_hardening import parse_line_budget, run_process_hardening_check


class ProcessHardeningTests(unittest.TestCase):
    def test_complete_evaluation_doc_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 2)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10:8")],
            )

        self.assertEqual("pass", payload["status"])
        self.assertEqual(0, payload["issue_count"])
        self.assertEqual(str(evaluation_doc), payload["checked_docs"][0]["path"])
        self.assertEqual(str(target), payload["line_budgets"][0]["path"])
        self.assertEqual("skipped", payload["git_status"]["status"])

    def test_missing_evaluation_section_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md", omit_section="自评")
            target = _write_lines(root / "module.py", 1)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10")],
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("evaluation_section_missing", _issue_codes(payload))

    def test_incomplete_marker_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md", extra_line="待补录")
            target = _write_lines(root / "module.py", 1)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10")],
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("evaluation_incomplete_marker", _issue_codes(payload))

    def test_line_count_over_hard_limit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 4)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:3")],
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("line_budget_hard_limit_exceeded", _issue_codes(payload))

    def test_warning_limit_reached_passes_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 3)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10:3")],
            )

        self.assertEqual("pass", payload["status"])
        self.assertEqual(1, payload["issue_count"])
        self.assertIn("line_budget_warning_limit_reached", _issue_codes(payload))

    def test_fail_on_warning_turns_warning_into_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 3)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10:3")],
                fail_on_warning=True,
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("line_budget_warning_limit_reached", _issue_codes(payload))

    def test_cli_outputs_json_and_does_not_initialize_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 1)
            before = set(root.iterdir())
            stdout = io.StringIO()

            with patch.object(cli, "init_database", side_effect=AssertionError("database init called")):
                with redirect_stdout(stdout):
                    exit_code = cli.main(
                        [
                            "process-hardening-check",
                            "--evaluation-doc",
                            str(evaluation_doc),
                            "--line-budget",
                            f"{target}:10:8",
                        ]
                    )
            after = set(root.iterdir())

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(before, after)


def _write_evaluation_doc(path: Path, *, omit_section: str | None = None, extra_line: str = "") -> Path:
    sections = ["子任务", "评分", "结果", "主进程验证", "重跑记录", "自评"]
    lines = ["# Trial 评估记录", ""]
    for index, section in enumerate(sections, start=1):
        if section == omit_section:
            continue
        lines.extend([f"## {index}. {section}", "已完成。", ""])
    if extra_line:
        lines.append(extra_line)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_lines(path: Path, line_count: int) -> Path:
    path.write_text("\n".join(f"line {index}" for index in range(line_count)), encoding="utf-8")
    return path


def _issue_codes(payload: dict[str, object]) -> set[str]:
    return {issue["code"] for issue in payload["issues"]}  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
