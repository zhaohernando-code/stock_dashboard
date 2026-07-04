from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.model_exploration_snapshot import (
    build_model_exploration_p1_artifacts,
    write_model_exploration_p1_artifacts,
)
from ashare_evidence.models import MarketBar, Stock


class ModelExplorationSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.temp_dir.name) / 'model-exploration.db'}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_stock(self, symbol: str, name: str, prices: list[float], *, industry: str = "制造业") -> None:
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
                profile_payload={"industry": industry},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            for index, price in enumerate(prices):
                observed_day = date(2026, 1, 1) + timedelta(days=index)
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
                        open_price=price - 0.5,
                        high_price=price + 1.0,
                        low_price=price - 1.0,
                        close_price=price,
                        volume=1000 + index,
                        amount=price * (1000 + index),
                        turnover_rate=1.0 + index / 100,
                        raw_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://bar/{symbol}/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": symbol, "index": index}),
                    )
                )

    def test_universe_date_matrix_is_primary_without_recommendations(self) -> None:
        self._seed_stock("600001.SH", "主板甲", [10, 11, 12, 13, 14, 15])
        self._seed_stock("600002.SH", "主板乙", [20, 20.5, 21, 21.5, 22, 22.5])
        self._seed_stock("000300.SH", "沪深300", [100, 101, 102, 103, 104, 105], industry="benchmark")

        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=[date(2026, 1, 2), date(2026, 1, 3)],
                horizons=(2,),
                min_history_days=2,
            )

        snapshot = artifacts["model_exploration_input_snapshot"]
        matrix = artifacts["universe_date_matrix"]
        symbols = {row["symbol"] for row in matrix["rows"]}

        self.assertEqual(snapshot["validation_protocol"]["primary_row_source"], "objective_universe_x_as_of_date")
        self.assertIn("recommendation_rows", snapshot["validation_protocol"]["forbidden_primary_sources"])
        self.assertEqual(symbols, {"600001.SH", "600002.SH"})
        self.assertEqual(matrix["row_count"], 4)
        self.assertFalse(any(row["symbol"] == "000300.SH" for row in matrix["rows"]))

    def test_feature_matrix_uses_only_bars_at_or_before_as_of(self) -> None:
        self._seed_stock("600001.SH", "主板甲", [10, 11, 12, 80, 90, 100])
        self._seed_stock("000300.SH", "沪深300", [100, 101, 102, 103, 104, 105], industry="benchmark")

        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=[date(2026, 1, 3)],
                horizons=(2,),
                min_history_days=2,
            )

        feature_row = artifacts["pit_feature_matrix"]["rows"][0]

        self.assertTrue(feature_row["source_cutoff_at_or_before_as_of"])
        self.assertEqual(feature_row["latest_feature_bar_date"], "2026-01-03")
        self.assertIsNone(feature_row["feature_values"]["price_momentum"]["return_3d"])
        self.assertFalse(feature_row["feature_values"]["crowding"]["winner_identity_used"])

    def test_feature_matrix_adds_cross_sectional_features_per_as_of_date(self) -> None:
        self._seed_stock("600001.SH", "行业甲A", [10, 10.5, 11, 12, 13, 14], industry="行业甲")
        self._seed_stock("600002.SH", "行业甲B", [10, 10.1, 10.2, 10.3, 10.4, 10.5], industry="行业甲")
        self._seed_stock("600003.SH", "行业乙A", [10, 9.9, 9.8, 9.7, 9.6, 9.5], industry="行业乙")
        self._seed_stock("000300.SH", "沪深300", [100, 101, 102, 103, 104, 105], industry="benchmark")

        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=[date(2026, 1, 6)],
                horizons=(1,),
                min_history_days=2,
            )

        rows_by_symbol = {row["symbol"]: row for row in artifacts["pit_feature_matrix"]["rows"]}
        strong = rows_by_symbol["600001.SH"]["feature_values"]["cross_sectional"]
        weak = rows_by_symbol["600003.SH"]["feature_values"]["cross_sectional"]

        self.assertIn("cross_sectional", artifacts["pit_feature_matrix"]["feature_groups"])
        self.assertGreater(strong["return_5d_percentile"], weak["return_5d_percentile"])
        self.assertNotEqual(strong["industry_return_5d_excess"], 0.0)
        self.assertIn("cross_sectional", rows_by_symbol["600001.SH"]["feature_group_versions"])

    def test_label_matrix_blocks_missing_benchmark_instead_of_self_benchmarking(self) -> None:
        self._seed_stock("600001.SH", "主板甲", [10, 11, 12, 13, 14, 15])

        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=[date(2026, 1, 2)],
                horizons=(2,),
                min_history_days=2,
            )

        universe_row = artifacts["universe_date_matrix"]["rows"][0]
        label_row = artifacts["executable_label_matrix"]["rows"][0]

        self.assertFalse(universe_row["has_benchmark_bar"])
        self.assertEqual(label_row["label_status"], "blocked")
        self.assertIn("missing_benchmark_entry_bar", label_row["label_block_reasons"])
        self.assertIn("missing_benchmark_exit_bar_2d", label_row["label_block_reasons"])
        self.assertIsNone(label_row["labels"]["excess_return_2d"])

    def test_recent_auto_as_of_dates_leave_forward_label_window(self) -> None:
        self._seed_stock("600001.SH", "主板甲", [10 + index * 0.2 for index in range(14)])
        self._seed_stock("000300.SH", "沪深300", [100 + index * 0.2 for index in range(14)], industry="benchmark")

        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                max_as_of_dates=2,
                horizons=(10,),
                min_history_days=2,
            )

        snapshot = artifacts["model_exploration_input_snapshot"]
        label_rows = artifacts["executable_label_matrix"]["rows"]

        self.assertEqual(snapshot["source_data_time_range"]["as_of_start"], "2026-01-03")
        self.assertEqual(snapshot["source_data_time_range"]["as_of_end"], "2026-01-04")
        self.assertEqual({row["label_status"] for row in label_rows}, {"ready"})

    def test_model_exploration_artifacts_write_to_research_validation_namespace(self) -> None:
        self._seed_stock("600001.SH", "主板甲", [10, 11, 12, 13])
        self._seed_stock("000300.SH", "沪深300", [100, 101, 102, 103], industry="benchmark")

        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=[date(2026, 1, 2)],
                horizons=(1,),
                min_history_days=2,
            )
        root = Path(self.temp_dir.name) / "artifacts"

        written = write_model_exploration_p1_artifacts(artifacts, artifact_root=root)

        self.assertEqual(
            written["model_exploration_input_snapshot"].parent,
            root / "research_validation" / "model_exploration_input_snapshots",
        )
        self.assertEqual(written["universe_date_matrix"].parent, root / "research_validation" / "universe_date_matrices")
        self.assertEqual(written["pit_feature_matrix"].parent, root / "research_validation" / "pit_feature_matrices")
        self.assertEqual(
            written["executable_label_matrix"].parent,
            root / "research_validation" / "executable_label_matrices",
        )


if __name__ == "__main__":
    unittest.main()
