from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import IngestionRun, Recommendation, Stock
from ashare_evidence.services import bootstrap_demo_data, get_latest_recommendation_summary, get_recommendation_trace


class EvidenceFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_demo_seed_creates_traceable_recommendation(self) -> None:
        with session_scope(self.database_url) as session:
            summary = bootstrap_demo_data(session, "600519.SH")

        self.assertEqual(summary["symbol"], "600519.SH")
        self.assertGreaterEqual(summary["evidence_count"], 5)
        self.assertGreaterEqual(summary["simulation_order_count"], 2)

        with session_scope(self.database_url) as session:
            latest = get_latest_recommendation_summary(session, "600519.SH")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["recommendation"]["direction"], "buy")
            self.assertEqual(latest["model"]["version"], "2026.04.14-r1")
            self.assertEqual(latest["prompt"]["version"], "v1")

            recommendation_id = latest["recommendation"]["id"]
            trace = get_recommendation_trace(session, recommendation_id)

            evidence_types = {item["evidence_type"] for item in trace["evidence"]}
            self.assertEqual(
                evidence_types,
                {"market_bar", "news_item", "feature_snapshot", "model_result", "sector_membership"},
            )
            for evidence in trace["evidence"]:
                self.assertTrue(evidence["lineage"]["license_tag"])
                self.assertTrue(evidence["lineage"]["source_uri"])
                self.assertTrue(evidence["lineage"]["lineage_hash"])
            self.assertEqual(len(trace["simulation_orders"]), 2)
            first_fill_hash = trace["simulation_orders"][0]["fills"][0]["lineage"]["lineage_hash"]
            second_fill_hash = trace["simulation_orders"][1]["fills"][0]["lineage"]["lineage_hash"]
            self.assertNotEqual(first_fill_hash, second_fill_hash)

    def test_mandatory_lineage_fields_exist_on_persisted_entities(self) -> None:
        with session_scope(self.database_url) as session:
            bootstrap_demo_data(session, "600519.SH")

        with session_scope(self.database_url) as session:
            stock = session.scalar(select(Stock).where(Stock.symbol == "600519.SH"))
            recommendation = session.scalar(select(Recommendation))
            ingestion_run = session.scalar(select(IngestionRun))

            self.assertIsNotNone(stock)
            self.assertIsNotNone(recommendation)
            self.assertIsNotNone(ingestion_run)

            for record in (stock, recommendation, ingestion_run):
                self.assertTrue(record.license_tag)
                self.assertTrue(record.usage_scope)
                self.assertTrue(record.redistribution_scope)
                self.assertTrue(record.source_uri)
                self.assertTrue(record.lineage_hash)

    def test_lineage_hash_changes_when_payload_changes(self) -> None:
        first = compute_lineage_hash({"a": 1, "b": 2})
        second = compute_lineage_hash({"a": 1, "b": 3})
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
