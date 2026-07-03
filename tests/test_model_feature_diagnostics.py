from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

from ashare_evidence.cli import main
from ashare_evidence.model_candidate_runner import MODEL_FEATURE_DEFS
from ashare_evidence.model_feature_diagnostics import (
    build_model_feature_diagnostic_report_artifact,
    run_model_feature_diagnostics,
)


def _feature_row(universe_row_id: str, symbol: str, as_of_date: str, *, return_5d: float) -> dict:
    return {
        "universe_row_id": universe_row_id,
        "symbol": symbol,
        "as_of_date": as_of_date,
        "feature_values": {
            "price_momentum": {
                "return_5d": return_5d,
                "return_10d": return_5d,
                "return_20d": return_5d,
            },
            "reversal_overheat": {
                "return_1d": -return_5d,
                "distance_from_20d_high": return_5d,
            },
            "volatility_risk": {"volatility_20d": 0.02},
            "liquidity": {"avg_amount_20d": 10_000_000 + return_5d},
            "crowding": {"amount_vs_20d_avg": 1.0 + return_5d},
            "regime": {
                "benchmark_return_20d": 0.01,
                "benchmark_volatility_20d": 0.02,
            },
        },
    }


def _label_row(universe_row_id: str, *, target: float) -> dict:
    return {
        "universe_row_id": universe_row_id,
        "label_status": "ready",
        "labels": {
            "excess_return_5d": target,
            "net_excess_return_10d_after_costs": target,
            "excess_return_20d": target,
        },
    }


class ModelFeatureDiagnosticsTests(unittest.TestCase):
    def _matrices(self) -> tuple[dict, dict]:
        feature_rows = []
        label_rows = []
        for index, as_of_date in enumerate(("2026-01-01", "2026-01-02", "2026-01-03")):
            high_id = f"{as_of_date}:high"
            low_id = f"{as_of_date}:low"
            feature_rows.append(_feature_row(high_id, "600001.SH", as_of_date, return_5d=0.08 + index * 0.01))
            feature_rows.append(_feature_row(low_id, "600002.SH", as_of_date, return_5d=-0.02 - index * 0.01))
            label_rows.append(_label_row(high_id, target=0.04))
            label_rows.append(_label_row(low_id, target=-0.02))
        return (
            {
                "artifact_type": "pit_feature_matrix",
                "schema_version": "pit_feature_matrix.test",
                "artifact_id": "pit-feature-matrix-unit",
                "source_input_snapshot_id": "snapshot-unit",
                "rows": feature_rows,
            },
            {
                "artifact_type": "executable_label_matrix",
                "schema_version": "executable_label_matrix.test",
                "artifact_id": "executable-label-matrix-unit",
                "source_input_snapshot_id": "snapshot-unit",
                "rows": label_rows,
            },
        )

    def test_builds_ranked_feature_direction_horizon_diagnostics(self) -> None:
        feature_matrix, label_matrix = self._matrices()

        payload = build_model_feature_diagnostic_report_artifact(
            validation_run_id="diagnostic-unit",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            generated_at=datetime(2026, 1, 4, tzinfo=UTC),
        )

        self.assertEqual(payload["artifact_type"], "model_feature_diagnostic_report")
        self.assertEqual(payload["promotion_status"], "blocked_from_production")
        self.assertGreater(payload["passing_direction_horizon_count"], 0)
        self.assertGreaterEqual(payload["tested_feature_count"], 20)
        self.assertEqual(payload["feature_leaderboard"][0]["feature_name"], "return_5d")
        self.assertTrue(payload["feature_leaderboard"][0]["passes_basic_signal_gate"])
        self.assertEqual(payload["candidate_generation_hints"][0]["status"], "eligible_for_candidate_spec_seed")

    def test_diagnostic_feature_universe_includes_existing_matrix_fields_beyond_initial_ten(self) -> None:
        feature_names = {name for name, _, _ in MODEL_FEATURE_DEFS}

        self.assertIn("turnover_rate", feature_names)
        self.assertIn("return_40d", feature_names)
        self.assertIn("volatility_10d", feature_names)
        self.assertIn("max_drawdown_40d", feature_names)
        self.assertIn("avg_amount_10d", feature_names)

    def test_run_writes_report_to_research_validation_store(self) -> None:
        feature_matrix, label_matrix = self._matrices()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "artifacts"
            feature_path = root / "research_validation" / "pit_feature_matrices" / "feature.json"
            label_path = root / "research_validation" / "executable_label_matrices" / "label.json"
            feature_path.parent.mkdir(parents=True)
            label_path.parent.mkdir(parents=True)
            feature_path.write_text(json.dumps(feature_matrix), encoding="utf-8")
            label_path.write_text(json.dumps(label_matrix), encoding="utf-8")

            result = run_model_feature_diagnostics(
                validation_run_id="diagnostic-write-unit",
                feature_matrix_artifact=feature_path,
                label_matrix_artifact=label_path,
            )

            report_path = Path(result["artifact_summary"]["path"])
            self.assertEqual(
                report_path.parent,
                (root / "research_validation" / "model_feature_diagnostic_reports").resolve(),
            )
            self.assertTrue(report_path.exists())
            self.assertEqual(result["runtime_db_write_policy"], "read_only_artifact_inputs_no_business_table_writes")

    def test_cli_runs_feature_diagnostics_without_writing(self) -> None:
        feature_matrix, label_matrix = self._matrices()
        with tempfile.TemporaryDirectory() as temp_dir:
            feature_path = Path(temp_dir) / "feature.json"
            label_path = Path(temp_dir) / "label.json"
            feature_path.write_text(json.dumps(feature_matrix), encoding="utf-8")
            label_path.write_text(json.dumps(label_matrix), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "shortpick-model-feature-diagnostics-run",
                        "--validation-run-id",
                        "diagnostic-cli-unit",
                        "--feature-matrix-artifact",
                        str(feature_path),
                        "--label-matrix-artifact",
                        str(label_path),
                        "--no-write-artifacts",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["workflow"], "shortpick_model_feature_diagnostics_v1")
        self.assertFalse(payload["write_artifacts"])
        self.assertEqual(payload["promotion_status"], "blocked_from_production")


if __name__ == "__main__":
    unittest.main()
