from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ashare_evidence.model_spec_registry import (
    build_model_spec_registry_artifact,
    validate_model_spec_registry_payload,
    write_model_spec_registry_artifact,
)


class ModelSpecRegistryTests(unittest.TestCase):
    def test_default_registry_has_stable_bounded_specs(self) -> None:
        artifact = build_model_spec_registry_artifact(
            validation_run_id="unit-run",
            source_input_snapshot_id="model-exploration-input-snapshot-unit",
        )

        self.assertEqual(artifact["artifact_type"], "model_spec_registry")
        self.assertEqual(artifact["promotion_status"], "blocked_from_production")
        self.assertEqual(artifact["validation"]["status"], "passed")
        self.assertEqual(
            artifact["model_spec_ids"],
            [
                "baseline_momentum_10d_turnover_cooldown_v1",
                "ranked_feature_linear_v1",
                "ranked_tree_shallow_v1",
                "regime_conditioned_linear_v1",
            ],
        )
        for spec in artifact["model_specs"]:
            self.assertLessEqual(spec["max_trials"], 16)
            self.assertEqual(spec["production_effect"], "forbidden")
            self.assertTrue(spec["allowed_feature_groups"])

    def test_dynamic_weight_spec_requires_oos_and_governance(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        dynamic_spec = next(
            spec for spec in artifact["model_specs"] if spec["model_spec_id"] == "regime_conditioned_linear_v1"
        )

        self.assertTrue(dynamic_spec["dynamic_weight_policy"]["enabled"])
        self.assertTrue(dynamic_spec["dynamic_weight_policy"]["requires_oos_gate_pass"])
        self.assertTrue(dynamic_spec["dynamic_weight_policy"]["requires_governance_approval"])
        self.assertEqual(dynamic_spec["dynamic_weight_policy"]["multiplier_clip"], [0.5, 1.5])

    def test_registry_validation_rejects_unbounded_search_space(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        artifact["model_specs"][0]["hyperparameter_grid"]["top_k"] = list(range(20))
        artifact["model_specs"][0]["max_trials"] = 20

        validation = validate_model_spec_registry_payload(artifact)

        self.assertEqual(validation["status"], "failed")
        self.assertIn("baseline_momentum_10d_turnover_cooldown_v1:unbounded_search_space", validation["failures"])

    def test_registry_writes_to_research_validation_namespace(self) -> None:
        artifact = build_model_spec_registry_artifact(validation_run_id="unit-run")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_model_spec_registry_artifact(artifact, artifact_root=Path(temp_dir))

            self.assertEqual(path.parent, Path(temp_dir) / "research_validation" / "model_spec_registries")


if __name__ == "__main__":
    unittest.main()
