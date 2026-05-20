from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ashare_evidence import cli
from ashare_evidence.process_hardening_evidence import check_required_evidence, parse_required_evidence


class ProcessHardeningEvidenceTests(unittest.TestCase):
    def test_required_evidence_passes_when_file_contains_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_file = Path(temp_dir) / "test_legacy.py"
            evidence_file.write_text("def test_legacy_ledger_conflict():\n    pass\n", encoding="utf-8")

            payload = check_required_evidence(
                [parse_required_evidence(f"{evidence_file}:legacy_ledger_conflict")]
            )

        self.assertEqual([], payload["issues"])
        self.assertTrue(payload["required_evidence"][0]["contains_token"])
        self.assertEqual("checked", payload["required_evidence"][0]["status"])

    def test_required_evidence_missing_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.py"

            payload = check_required_evidence([parse_required_evidence(f"{missing_file}:legacy_ledger_conflict")])

        self.assertEqual(["required_evidence_file_missing"], _issue_codes(payload))
        self.assertEqual("missing", payload["required_evidence"][0]["status"])

    def test_required_evidence_missing_token_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_file = Path(temp_dir) / "test_legacy.py"
            evidence_file.write_text("def test_other_case():\n    pass\n", encoding="utf-8")

            payload = check_required_evidence(
                [parse_required_evidence(f"{evidence_file}:legacy_ledger_conflict")]
            )

        self.assertEqual(["required_evidence_token_missing"], _issue_codes(payload))
        self.assertFalse(payload["required_evidence"][0]["contains_token"])
        self.assertEqual("missing_token", payload["required_evidence"][0]["status"])

    def test_cli_outputs_required_evidence_and_does_not_initialize_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evaluation_doc = _write_evaluation_doc(root / "evaluation.md")
            budget_target = _write_lines(root / "module.py", 1)
            evidence_file = root / "test_legacy.py"
            evidence_file.write_text("def test_legacy_ledger_conflict():\n    pass\n", encoding="utf-8")
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
                            "--required-evidence",
                            f"{evidence_file}:legacy_ledger_conflict",
                        ]
                    )
            after = set(root.iterdir())

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual("checked", payload["required_evidence"][0]["status"])
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
