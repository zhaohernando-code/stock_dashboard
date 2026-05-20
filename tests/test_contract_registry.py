from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_evidence.cli import main
from ashare_evidence.contract_registry import (
    DEFAULT_REGISTRY_PATH,
    check_contract_registry,
    load_registry,
    validate_registry_structure,
)


class ContractRegistryTests(unittest.TestCase):
    def test_registry_structure_is_valid(self) -> None:
        registry = load_registry(DEFAULT_REGISTRY_PATH)

        issues = validate_registry_structure(registry)

        self.assertEqual([], issues)
        self.assertGreaterEqual(len(registry["events"]), 16)
        self.assertIn("claim_ceiling_levels", registry)

    def test_checker_accepts_registered_trial_b_and_c_ids(self) -> None:
        result = check_contract_registry(
            registry_path=DEFAULT_REGISTRY_PATH,
            docs=[
                "docs/contracts/autonomous-flow-trial/TRIAL_B_GLOBAL_PROTOCOL_CN.md",
                "docs/contracts/autonomous-flow-trial/TRIAL_C_LEDGER_AND_PUBLISH_DECISION_CN.md",
                "docs/contracts/autonomous-flow-trial/TRIAL_C_REGISTRY_AND_CLAIM_GATE_DECISION_CN.md",
            ],
            fail_on_unregistered=True,
            fail_on_deprecated=True,
        )

        self.assertEqual("pass", result["status"], result["issues"])

    def test_checker_reports_unregistered_and_deprecated_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            doc = Path(temp_dir) / "contract.md"
            doc.write_text(
                "\n".join(
                    [
                        "Uses `phase5.cycle.started` and `phase5.unregistered.created.v1`.",
                        "Registered dependency: `proposed_event.phase5.new.v1`.",
                    ]
                ),
                encoding="utf-8",
            )

            result = check_contract_registry(
                registry_path=DEFAULT_REGISTRY_PATH,
                docs=[doc],
                fail_on_unregistered=True,
                fail_on_deprecated=True,
            )

        codes = {issue["code"] for issue in result["issues"]}
        self.assertEqual("fail", result["status"])
        self.assertIn("deprecated_id", codes)
        self.assertIn("unregistered_id", codes)
        self.assertIn("proposed_registered_dependency", codes)

    def test_cli_contract_registry_check_does_not_initialize_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            doc = Path(temp_dir) / "contract.md"
            doc.write_text("Uses `phase5.cycle.started.v1` and `phase5_cycle_ledger`.\n", encoding="utf-8")
            before = set(Path(temp_dir).iterdir())

            exit_code = main(
                [
                    "contract-registry-check",
                    "--registry",
                    str(DEFAULT_REGISTRY_PATH),
                    "--docs",
                    str(doc),
                    "--fail-on-unregistered",
                    "--fail-on-deprecated",
                ]
            )

            after = set(Path(temp_dir).iterdir())

        self.assertEqual(0, exit_code)
        self.assertEqual(before, after)

    def test_registry_json_is_parseable_without_external_schema_dependency(self) -> None:
        schema_path = Path("docs/contracts/registry/schemas/autonomous_flow_registry.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual("Autonomous Flow Registry", schema["title"])
        self.assertIn("events", schema["required"])


if __name__ == "__main__":
    unittest.main()
