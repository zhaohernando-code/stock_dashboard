from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.capacity_opportunity_set_discovery import build_capacity_opportunity_set_discovery
from ashare_evidence.capacity_opportunity_feature_gap import build_capacity_opportunity_feature_gap_probe
from ashare_evidence.capacity_opportunity_archetype_sample import (
    _is_executable_main_board_stock,
    _is_main_board_stock_symbol,
    build_capacity_opportunity_archetype_sample_preflight,
)
from ashare_evidence.capacity_opportunity_learned_sample import (
    VARIANT_OBJECTIVES,
    build_capacity_opportunity_learned_sample_preflight,
)
from ashare_evidence.cli import main as cli_main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock


class CapacityOpportunitySetDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "capacity-opportunity.db"
        self.database_url = f"sqlite:///{self.database_path}"
        init_database(self.database_url)
        self.as_of_date = date(2026, 1, 22)
        self.summary_path = Path(self.temp_dir.name) / "top200-summary.json"
        self._seed_stock("000300.SH", "沪深300", lambda index: 100.0 + index * 0.1, amount=100_000_000)
        self._seed_stock("603117.SH", "源低流动性", lambda index: 10.0 if index <= 21 else 15.0, amount=2_000_000)
        self._seed_stock("002869.SZ", "液体赢家", lambda index: 20.0 if index <= 21 else 32.0, amount=30_000_000)
        self._seed_stock("600001.SH", "液体输家", lambda index: 20.0 if index <= 21 else 18.0, amount=35_000_000)
        self.summary_path.write_text(
            json.dumps(
                {
                    "artifact_type": "top_candidate_inventory_oracle_summary",
                    "summary": [
                        {
                            "as_of_date": self.as_of_date.isoformat(),
                            "source_symbol": "603117.SH",
                            "source_avg_amount_20d": 2_000_000,
                            "source_net_excess_return": 0.40,
                            "best_liquid_candidate": {"symbol": "600001.SH"},
                            "top10_liquid_by_future_return": [{"symbol": "600001.SH"}],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_stock(self, symbol: str, name: str, price_fn, *, amount: float) -> None:
        ticker, _, exchange = symbol.partition(".")
        with session_scope(self.database_url) as session:
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange or "SH",
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={"industry": "benchmark" if symbol == "000300.SH" else "制造业"},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            start = date(2026, 1, 1)
            for index in range(42):
                observed_day = start + timedelta(days=index)
                price = float(price_fn(index))
                session.add(
                    MarketBar(
                        bar_key=f"bar-{symbol}-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(
                            observed_day.year,
                            observed_day.month,
                            observed_day.day,
                            7,
                            0,
                            tzinfo=UTC,
                        ),
                        open_price=price,
                        high_price=price * 1.02,
                        low_price=price * 0.98,
                        close_price=price,
                        volume=amount / max(price, 0.01),
                        amount=amount,
                        turnover_rate=0.02,
                        total_mv=1_000_000 + index,
                        circ_mv=900_000 + index,
                        pe_ttm=20.0,
                        pb=2.0,
                        raw_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://bar/{symbol}/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": symbol, "index": index}),
                    )
                )

    def test_build_discovers_full_market_liquid_future_winner_outside_retained_top10(self) -> None:
        with session_scope(self.database_url) as session:
            payload = build_capacity_opportunity_set_discovery(
                session,
                top_candidate_summary_artifact=self.summary_path,
            )

        self.assertEqual(payload["gate_status"], "passed")
        self.assertEqual(payload["dates_with_non_degrading_liquid_candidates_vs_artifact_net"], 1)
        day = payload["dates"][0]
        self.assertEqual(day["best_liquid_symbol"], "002869.SZ")
        self.assertGreater(day["best_liquid_future_excess_return_20d"], 0.40)
        best = day["top_liquid_by_future_excess"][0]
        self.assertFalse(best["present_in_retained_top10_liquid_summary"])
        self.assertGreaterEqual(best["avg_amount_20d"], payload["full_fill_avg_amount_20d_required"])

    def test_cli_writes_compact_capacity_opportunity_discovery(self) -> None:
        output_path = Path(self.temp_dir.name) / "capacity-opportunity.json"

        exit_code = cli_main(
            [
                "research-capacity-opportunity-set-discovery",
                "--database-url",
                self.database_url,
                "--top-candidate-summary-artifact",
                str(self.summary_path),
                "--output-json",
                str(output_path),
            ]
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "capacity_opportunity_set_discovery")
        self.assertEqual(payload["dates"][0]["best_liquid_symbol"], "002869.SZ")

    def test_feature_gap_probe_blocks_when_archetype_candidate_does_not_clear_all_source_floors(self) -> None:
        payload = {
            "artifact_type": "capacity_opportunity_set_discovery",
            "full_fill_avg_amount_20d_required": 18_200_000.0,
            "dates": [
                {
                    "as_of_date": "2026-01-22",
                    "source_symbol": "603117.SH",
                    "source_artifact_net_excess_return": 0.40,
                    "best_liquid_symbol": "002869.SZ",
                    "best_liquid_future_excess_return_20d": 0.55,
                    "top_liquid_by_future_excess": [
                        {
                            "symbol": "002869.SZ",
                            "name": "液体赢家",
                            "future_excess_return_20d": 0.55,
                            "avg_amount_20d": 30_000_000,
                            "avg_amount_20d_percentile": 0.60,
                            "amount_10d_vs_20d_percentile": 0.90,
                            "return_5d_percentile": 0.90,
                            "return_20d_percentile": 0.50,
                            "turnover_rate_percentile": 0.90,
                            "volatility_20d_percentile": 0.70,
                            "total_mv_percentile": 0.20,
                            "present_in_retained_top10_liquid_summary": False,
                        }
                    ],
                },
                {
                    "as_of_date": "2026-01-23",
                    "source_symbol": "603117.SH",
                    "source_artifact_net_excess_return": 0.60,
                    "best_liquid_symbol": "603171.SH",
                    "best_liquid_future_excess_return_20d": 0.50,
                    "top_liquid_by_future_excess": [
                        {
                            "symbol": "603171.SH",
                            "name": "近似候选",
                            "future_excess_return_20d": 0.50,
                            "avg_amount_20d": 35_000_000,
                            "avg_amount_20d_percentile": 0.20,
                            "amount_10d_vs_20d_percentile": 0.85,
                            "return_5d_percentile": 0.65,
                            "return_20d_percentile": 0.30,
                            "turnover_rate_percentile": 0.70,
                            "volatility_20d_percentile": 0.25,
                            "total_mv_percentile": 0.60,
                            "present_in_retained_top10_liquid_summary": False,
                        }
                    ],
                },
            ],
        }

        result = build_capacity_opportunity_feature_gap_probe(payload)

        self.assertEqual(result["artifact_type"], "capacity_opportunity_feature_gap")
        self.assertEqual(result["gate_status"], "blocked")
        self.assertIn(
            "capacity_opportunity_feature_gap:not_all_dates_have_nondegrading_covered_liquid_archetype",
            result["blocking_gate_ids"],
        )
        self.assertEqual(result["dates_with_archetype_covered_best_liquid_candidate"], 2)
        self.assertEqual(result["dates_with_nondegrading_archetype_candidate"], 1)
        self.assertEqual(result["dates"][0]["top_candidates"][0]["archetypes"][0], "turnover_amount_rebound")

    def test_feature_gap_cli_writes_blocked_probe(self) -> None:
        opportunity_path = Path(self.temp_dir.name) / "opportunity.json"
        output_path = Path(self.temp_dir.name) / "feature-gap.json"
        opportunity_path.write_text(
            json.dumps(
                {
                    "artifact_type": "capacity_opportunity_set_discovery",
                    "full_fill_avg_amount_20d_required": 18_200_000.0,
                    "dates": [
                        {
                            "as_of_date": "2026-01-22",
                            "source_symbol": "603117.SH",
                            "source_artifact_net_excess_return": 0.60,
                            "best_liquid_symbol": "603171.SH",
                            "best_liquid_future_excess_return_20d": 0.50,
                            "top_liquid_by_future_excess": [
                                {
                                    "symbol": "603171.SH",
                                    "future_excess_return_20d": 0.50,
                                    "avg_amount_20d": 35_000_000,
                                    "amount_10d_vs_20d_percentile": 0.85,
                                    "return_20d_percentile": 0.30,
                                    "volatility_20d_percentile": 0.25,
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = cli_main(
            [
                "research-capacity-opportunity-feature-gap",
                "--opportunity-discovery-artifact",
                str(opportunity_path),
                "--output-json",
                str(output_path),
            ]
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "capacity_opportunity_feature_gap")
        self.assertEqual(payload["gate_status"], "blocked")

    def test_archetype_sample_preflight_compares_against_candidate_run_dates(self) -> None:
        candidate_run = {
            "artifact_id": "candidate-run-test",
            "trial_diagnostics": [
                {
                    "trial_id": "trial-000",
                    "selected_top_k_returns_by_date": [
                        {
                            "as_of_date": self.as_of_date.isoformat(),
                            "mean_net_excess_return": 0.10,
                        }
                    ],
                }
            ],
        }

        with session_scope(self.database_url) as session:
            payload = build_capacity_opportunity_archetype_sample_preflight(
                session,
                candidate_run=candidate_run,
                trial_id="trial-000",
                sample_date_count=1,
                top_k=1,
            )

        self.assertEqual(payload["artifact_type"], "capacity_opportunity_archetype_sample")
        self.assertEqual(payload["sample_date_count_completed"], 1)
        self.assertIn(payload["gate_status"], {"passed", "blocked"})
        self.assertIn("archetype_sample_stats", payload)

    def test_archetype_sample_cli_writes_preflight(self) -> None:
        candidate_run_path = Path(self.temp_dir.name) / "candidate-run.json"
        output_path = Path(self.temp_dir.name) / "archetype-sample.json"
        candidate_run_path.write_text(
            json.dumps(
                {
                    "artifact_id": "candidate-run-test",
                    "trial_diagnostics": [
                        {
                            "trial_id": "trial-000",
                            "selected_top_k_returns_by_date": [
                                {
                                    "as_of_date": self.as_of_date.isoformat(),
                                    "mean_net_excess_return": 0.10,
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = cli_main(
            [
                "research-capacity-opportunity-archetype-sample",
                "--database-url",
                self.database_url,
                "--candidate-run-artifact",
                str(candidate_run_path),
                "--trial-id",
                "trial-000",
                "--sample-date-count",
                "1",
                "--top-k",
                "1",
                "--output-json",
                str(output_path),
            ]
        )

        self.assertIn(exit_code, {0, 1})
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "capacity_opportunity_archetype_sample")
        self.assertEqual(payload["sample_date_count_completed"], 1)

    def test_archetype_sample_main_board_filter_excludes_chinext_and_star_board(self) -> None:
        self.assertTrue(_is_main_board_stock_symbol("002869.SZ"))
        self.assertTrue(_is_main_board_stock_symbol("603171.SH"))
        self.assertFalse(_is_main_board_stock_symbol("300762.SZ"))
        self.assertFalse(_is_main_board_stock_symbol("301511.SZ"))
        self.assertFalse(_is_main_board_stock_symbol("688001.SH"))
        self.assertTrue(_is_executable_main_board_stock("002869.SZ", "金溢科技"))
        self.assertFalse(_is_executable_main_board_stock("002024.SZ", "ST易购"))
        self.assertFalse(_is_executable_main_board_stock("600000.SH", "*ST测试"))
        self.assertFalse(_is_executable_main_board_stock("000000.SZ", "退市测试"))

    def test_learned_sample_preflight_uses_prior_sample_dates_only(self) -> None:
        sample_dates = [(self.as_of_date + timedelta(days=offset)).isoformat() for offset in range(3)]
        candidate_run = {
            "artifact_id": "candidate-run-test",
            "trial_diagnostics": [
                {
                    "trial_id": "trial-000",
                    "selected_top_k_returns_by_date": [
                        {"as_of_date": sample_date, "mean_net_excess_return": 0.10}
                        for sample_date in sample_dates
                    ],
                }
            ],
        }

        with session_scope(self.database_url) as session:
            payload = build_capacity_opportunity_learned_sample_preflight(
                session,
                candidate_run=candidate_run,
                trial_id="trial-000",
                sample_date_count=3,
                min_train_dates=1,
                top_k=1,
            )

        self.assertEqual(payload["artifact_type"], "capacity_opportunity_learned_sample")
        self.assertIn(payload["gate_status"], {"passed", "blocked"})
        self.assertEqual(payload["min_train_dates"], 1)
        self.assertEqual(payload["variant_objectives"], VARIANT_OBJECTIVES)
        self.assertEqual(set(payload["variant_stats"]), set(VARIANT_OBJECTIVES))

    def test_learned_sample_cli_writes_preflight(self) -> None:
        candidate_run_path = Path(self.temp_dir.name) / "learned-candidate-run.json"
        output_path = Path(self.temp_dir.name) / "learned-sample.json"
        sample_dates = [(self.as_of_date + timedelta(days=offset)).isoformat() for offset in range(3)]
        candidate_run_path.write_text(
            json.dumps(
                {
                    "artifact_id": "candidate-run-test",
                    "trial_diagnostics": [
                        {
                            "trial_id": "trial-000",
                            "selected_top_k_returns_by_date": [
                                {"as_of_date": sample_date, "mean_net_excess_return": 0.10}
                                for sample_date in sample_dates
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = cli_main(
            [
                "research-capacity-opportunity-learned-sample",
                "--database-url",
                self.database_url,
                "--candidate-run-artifact",
                str(candidate_run_path),
                "--trial-id",
                "trial-000",
                "--sample-date-count",
                "3",
                "--min-train-dates",
                "1",
                "--top-k",
                "1",
                "--output-json",
                str(output_path),
            ]
        )

        self.assertIn(exit_code, {0, 1})
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "capacity_opportunity_learned_sample")
