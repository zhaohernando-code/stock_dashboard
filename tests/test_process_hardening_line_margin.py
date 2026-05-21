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
from ashare_evidence.process_hardening_line_margin import (
    check_line_budget_warning_margins,
    parse_line_budget_warning_margin,
)


class ProcessHardeningLineMarginTests(unittest.TestCase):
    def test_parse_line_budget_warning_margin_allows_colons_in_path(self) -> None:
        parsed = parse_line_budget_warning_margin("tmp/a:b/module.py:5")

        self.assertEqual("tmp/a:b/module.py", parsed["path"])
        self.assertEqual(5, parsed["minimum_remaining"])

    def test_parse_line_budget_warning_margin_rejects_invalid_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "path:minimum_remaining"):
            parse_line_budget_warning_margin("src/example.py")
        with self.assertRaisesRegex(ValueError, "path must not be empty"):
            parse_line_budget_warning_margin(":5")
        with self.assertRaisesRegex(ValueError, "must be positive"):
            parse_line_budget_warning_margin("src/example.py:0")

    def test_warning_margin_reports_warning_when_remaining_is_too_low(self) -> None:
        payload = check_line_budget_warning_margins(
            [{"path": "src/example.py", "status": "checked", "line_count": 7, "warning_limit": 10}],
            [parse_line_budget_warning_margin("src/example.py:5")],
        )

        self.assertEqual(["line_budget_warning_margin_low"], _issue_codes(payload))
        self.assertEqual(3, payload["line_budget_warning_margins"][0]["remaining"])

    def test_warning_margin_passes_when_remaining_meets_minimum(self) -> None:
        payload = check_line_budget_warning_margins(
            [{"path": "src/example.py", "status": "checked", "line_count": 5, "warning_limit": 10}],
            [parse_line_budget_warning_margin("src/example.py:5")],
        )

        self.assertEqual([], payload["issues"])
        self.assertEqual("checked", payload["line_budget_warning_margins"][0]["status"])

    def test_warning_margin_fails_closed_for_missing_line_budget(self) -> None:
        payload = check_line_budget_warning_margins([], [parse_line_budget_warning_margin("src/example.py:5")])

        self.assertEqual(["line_budget_warning_margin_missing_budget"], _issue_codes(payload))
        self.assertEqual("missing_line_budget", payload["line_budget_warning_margins"][0]["status"])

    def test_warning_margin_fails_closed_without_warning_limit(self) -> None:
        payload = check_line_budget_warning_margins(
            [{"path": "src/example.py", "status": "checked", "line_count": 5, "warning_limit": None}],
            [parse_line_budget_warning_margin("src/example.py:5")],
        )

        self.assertEqual(["line_budget_warning_margin_missing_warning_limit"], _issue_codes(payload))
        self.assertEqual("missing_warning_limit", payload["line_budget_warning_margins"][0]["status"])

    def test_core_process_check_payload_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            target = _write_lines(root / "module.py", 1)

            payload = run_process_hardening_check(
                evaluation_docs=[evaluation_doc],
                line_budgets=[parse_line_budget(f"{target}:10:8")],
            )

        self.assertEqual("pass", payload["status"])
        self.assertNotIn("line_budget_warning_margins", payload)

    def test_cli_reports_warning_margin_without_fail_on_warning(self) -> None:
        exit_code, payload = _run_cli_with_margin(fail_on_warning=False)

        self.assertEqual(0, exit_code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(["line_budget_warning_margin_low"], _issue_codes(payload))

    def test_cli_fails_on_warning_margin_when_fail_on_warning_is_set(self) -> None:
        exit_code, payload = _run_cli_with_margin(fail_on_warning=True)

        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertEqual(["line_budget_warning_margin_low"], _issue_codes(payload))


def _run_cli_with_margin(*, fail_on_warning: bool) -> tuple[int, dict[str, object]]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
        target = _write_lines(root / "module.py", 7)
        stdout = io.StringIO()
        args = [
            "process-hardening-check",
            "--evaluation-doc",
            str(evaluation_doc),
            "--line-budget",
            f"{target}:20:10",
            "--line-budget-warning-margin",
            f"{target}:5",
        ]
        if fail_on_warning:
            args.append("--fail-on-warning")

        with patch.object(cli, "init_database", side_effect=AssertionError("database init called")):
            with redirect_stdout(stdout):
                exit_code = cli.main(args)

    return exit_code, json.loads(stdout.getvalue())


def _write_evaluation_doc(path: Path) -> Path:
    sections = ["子任务", "评分", "结果", "主进程验证", "重跑记录", "自评"]
    lines = ["# Trial evaluation", ""]
    for index, section in enumerate(sections, start=1):
        lines.extend([f"## {index}. {section}", "Done.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_lines(path: Path, line_count: int) -> Path:
    path.write_text("\n".join(f"line {index}" for index in range(line_count)), encoding="utf-8")
    return path


def _issue_codes(payload: dict[str, object]) -> list[str]:
    return [issue["code"] for issue in payload["issues"]]  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
