from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class AgentConstraintTests(unittest.TestCase):
    def test_constraint_script_passes(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/check-agent-constraints.sh"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_claude_entry_contains_hard_gates_and_no_stale_full_pytest(self) -> None:
        text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        required = [
            "bash scripts/install-git-hooks.sh",
            "python3 -m pytest -q",
            "policy-audit",
            "bash scripts/test-runtime-integration.sh",
            "scripts/hooks/pre-push-stock-dashboard.sh",
            "origin/main",
            "policy_config_loader",
            "publish-local-runtime.sh",
        ]
        for marker in required:
            self.assertIn(marker, text)
        self.assertNotIn("PYTHONPATH=src python3 -m pytest tests/ -v", text)

    def test_pre_push_and_ci_enforce_agent_constraints(self) -> None:
        pre_push = (REPO_ROOT / "scripts" / "hooks" / "pre-push-stock-dashboard.sh").read_text(encoding="utf-8")
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("bash scripts/check-agent-constraints.sh", pre_push)
        self.assertIn("python3 -m pytest -q", pre_push)
        self.assertIn("policy-audit", pre_push)
        self.assertIn("bash scripts/check-agent-constraints.sh", ci)
        self.assertIn("python3 -m pytest -q", ci)
        self.assertIn("policy-audit", ci)
        self.assertNotIn("pytest tests/ -v", ci)

    def test_hook_scripts_are_executable(self) -> None:
        for path in [
            "scripts/check-agent-constraints.sh",
            "scripts/test-runtime-integration.sh",
            "scripts/hooks/pre-push-stock-dashboard.sh",
            "scripts/install-git-hooks.sh",
        ]:
            self.assertTrue(os.access(REPO_ROOT / path, os.X_OK), path)


if __name__ == "__main__":
    unittest.main()
