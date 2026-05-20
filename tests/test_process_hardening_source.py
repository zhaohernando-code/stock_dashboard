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
from ashare_evidence.process_hardening_source import (
    check_forbidden_source_tokens,
    parse_forbidden_source_token,
)


class ProcessHardeningSourceTests(unittest.TestCase):
    def test_parse_forbidden_source_token_allows_colons_in_token(self) -> None:
        parsed = parse_forbidden_source_token("src/example.py:route.reason == 'a:b'")

        self.assertEqual("src/example.py", parsed["path"])
        self.assertEqual("route.reason == 'a:b'", parsed["token"])

    def test_parse_forbidden_source_token_rejects_empty_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "path must not be empty"):
            parse_forbidden_source_token(":route.reason ==")
        with self.assertRaisesRegex(ValueError, "token must not be empty"):
            parse_forbidden_source_token("src/example.py:")

    def test_missing_file_returns_error_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.py"

            payload = check_forbidden_source_tokens(
                [parse_forbidden_source_token(f"{missing_file}:route.reason ==")]
            )

        self.assertEqual(["forbidden_source_file_missing"], _issue_codes(payload))
        self.assertEqual("missing", payload["forbidden_source_tokens"][0]["status"])

    def test_forbidden_token_hit_reports_line_and_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "module.py"
            source_file.write_text("safe = True\nroute.reason == 'blocked:a'\n", encoding="utf-8")

            payload = check_forbidden_source_tokens(
                [parse_forbidden_source_token(f"{source_file}:route.reason == 'blocked:a'")]
            )

        issue = payload["issues"][0]
        self.assertEqual(["forbidden_source_token_found"], _issue_codes(payload))
        self.assertEqual(str(source_file), issue["path"])
        self.assertEqual("route.reason == 'blocked:a'", issue["token"])
        self.assertEqual(2, issue["line"])
        self.assertIn("forbidden source token", issue["message"])

    def test_missing_forbidden_token_passes_without_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "module.py"
            source_file.write_text("safe = True\n", encoding="utf-8")

            payload = check_forbidden_source_tokens(
                [parse_forbidden_source_token(f"{source_file}:route.reason ==")]
            )

        self.assertEqual([], payload["issues"])
        self.assertEqual("checked", payload["forbidden_source_tokens"][0]["status"])

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
        self.assertNotIn("forbidden_source_tokens", payload)

    def test_cli_repeated_forbidden_source_token_and_no_database_init(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            budget_target = _write_lines(root / "module.py", 1)
            source_file = root / "source.py"
            source_file.write_text("a = 'safe'\nroute.reason == 'blocked:a'\n", encoding="utf-8")
            clean_file = root / "clean.py"
            clean_file.write_text("a = 'safe'\n", encoding="utf-8")
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
                            f"{budget_target}:10:8",
                            "--forbidden-source-token",
                            f"{source_file}:route.reason == 'blocked:a'",
                            "--forbidden-source-token",
                            f"{clean_file}:route.reason ==",
                        ]
                    )
            after = set(root.iterdir())

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertEqual(2, len(payload["forbidden_source_tokens"]))
        self.assertEqual(["forbidden_source_token_found"], _issue_codes(payload))
        self.assertEqual(before, after)


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


def _issue_codes(payload: dict[str, object]) -> list[str]:
    return [issue["code"] for issue in payload["issues"]]  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
