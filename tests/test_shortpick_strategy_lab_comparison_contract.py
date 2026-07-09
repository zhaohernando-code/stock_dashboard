from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ashare_evidence.cli import main
from ashare_evidence.shortpick_strategy_lab_comparison_contract import (
    build_shortpick_strategy_lab_fair_comparison_readiness,
)


class ShortpickStrategyLabComparisonContractTests(unittest.TestCase):
    def test_blocks_short_window_candidate_against_frontend_full_history(self) -> None:
        payload = build_shortpick_strategy_lab_fair_comparison_readiness(
            candidate_replay_artifact={
                "artifact_id": "candidate-short-window",
                "data_scope": {
                    "signal_date_from": "2025-07-03",
                    "signal_date_to": "2026-06-05",
                    "signal_day_count": 176,
                    "selected_pick_count": 528,
                },
                "baseline_summary": {
                    "total_return": 1.0613,
                    "annualized_return": 1.0462,
                    "max_drawdown": -0.0472,
                    "negative_month_count": 1,
                },
            }
        )

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["claim_ceiling"], "directional_research_only_no_frontend_replacement_claim")
        self.assertFalse(payload["comparison_rules"]["total_return_cross_window_comparison_allowed"])
        self.assertFalse(payload["comparison_rules"]["frontend_replacement_claim_allowed"])
        self.assertIn("candidate_signal_date_from_not_equal_frontend_full_history", payload["blocking_reasons"])
        self.assertEqual(payload["baseline_reference"]["data_scope"]["signal_day_count"], 509)
        self.assertEqual(payload["candidate_reference"]["data_scope"]["signal_day_count"], 176)
        self.assertGreaterEqual(payload["baseline_reference"]["best_metric_floor"]["best_total_return"], 3.3)

    def test_allows_same_window_candidate_for_research_metric_comparison(self) -> None:
        payload = build_shortpick_strategy_lab_fair_comparison_readiness(
            candidate_replay_artifact={
                "artifact_id": "candidate-full-window",
                "data_scope": {
                    "signal_date_from": "2023-09-07",
                    "signal_date_to": "2026-06-26",
                    "signal_day_count": 511,
                    "selected_pick_count": 1533,
                },
                "summary": {
                    "total_return": 3.5,
                    "annualized_return": 0.7,
                    "max_drawdown": -0.06,
                    "negative_month_count": 2,
                    "worst_monthly_return": -0.01,
                    "skipped_order_rate": 0.2,
                    "skipped_signal_rate": 0.2,
                    "final_nav_cny": 900000,
                },
            }
        )

        self.assertEqual(payload["status"], "passed_same_window_metrics_ready")
        self.assertTrue(payload["comparison_rules"]["frontend_replacement_claim_allowed"])
        self.assertEqual(payload["blocking_reasons"], [])
        self.assertTrue(all(row["status"] == "passed" for row in payload["window_checks"]))
        self.assertEqual(payload["comparison_rules"]["same_window_required_keys"], ["signal_date_from", "signal_date_to"])
        self.assertIn("signal_day_count", payload["comparison_rules"]["diagnostic_scope_keys"])

    def test_reads_candidate_summary_from_best_account_replay_result(self) -> None:
        payload = build_shortpick_strategy_lab_fair_comparison_readiness(
            candidate_replay_artifact={
                "source_candidate_run_id": "candidate-run",
                "trial_id": "spec:trial-003",
                "data_scope": {
                    "signal_date_from": "2023-09-07",
                    "signal_date_to": "2026-06-26",
                    "signal_day_count": 511,
                    "selected_pick_count": 1533,
                },
                "leaderboard": [{"config_id": "best-config", "total_return": 3.0}],
                "results": [
                    {
                        "config_id": "other-config",
                        "summary": {"total_return": 2.0, "annualized_return": 0.5},
                    },
                    {
                        "config_id": "best-config",
                        "summary": {
                            "total_return": 3.5,
                            "annualized_return": 0.7,
                            "max_drawdown": -0.06,
                            "negative_month_count": 2,
                            "worst_monthly_return": -0.01,
                            "skipped_order_rate": 0.2,
                            "skipped_signal_rate": 0.2,
                            "buy_order_count": 700,
                            "final_nav_cny": 900000,
                            "mean_invested_ratio": 0.65,
                            "max_single_symbol_exposure_pct": 0.24,
                        },
                    },
                ],
            }
        )

        self.assertEqual(payload["status"], "passed_same_window_metrics_ready")
        self.assertEqual(payload["candidate_reference"]["artifact_id"], "candidate-run")
        self.assertEqual(payload["candidate_reference"]["summary"]["total_return"], 3.5)
        self.assertEqual(payload["candidate_reference"]["summary"]["buy_order_count"], 700)

    def test_cli_returns_non_zero_for_window_mismatch_and_can_write_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "candidate.json"
            output_path = Path(temp_dir) / "readiness.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "artifact_id": "candidate-short-window",
                        "data_scope": {
                            "signal_date_from": "2025-07-03",
                            "signal_date_to": "2026-06-05",
                            "signal_day_count": 176,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "shortpick-strategy-lab-comparison-readiness",
                        "--candidate-replay-artifact",
                        str(artifact_path),
                        "--output-json",
                        str(output_path),
                    ]
                )
            payload = json.loads(stdout.getvalue())
            written = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(written["artifact_id"], payload["artifact_id"])


if __name__ == "__main__":
    unittest.main()
