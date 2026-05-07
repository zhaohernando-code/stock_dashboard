from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import ProviderCredential
from ashare_evidence.stock_master import resolve_stock_profile


class StockMasterResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "stock-master.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_local_override_resolves_002028(self) -> None:
        with session_scope(self.database_url) as session:
            resolved = resolve_stock_profile(session, symbol="002028.SZ")

        self.assertEqual(resolved.name, "思源电气")
        self.assertEqual(resolved.industry, "电力设备")
        self.assertEqual(resolved.template_key, "power_equipment")
        self.assertEqual(resolved.source, "local_override")

    def test_tushare_stock_basic_can_supply_name_and_industry(self) -> None:
        with session_scope(self.database_url) as session:
            session.add(
                ProviderCredential(
                    provider_name="tushare",
                    display_name="Tushare",
                    access_token="test-token",
                    base_url="http://api.tushare.pro",
                    enabled=True,
                    notes=None,
                    config_payload={},
                )
            )
            session.commit()

        mocked_response = {
            "code": 0,
            "data": {
                "fields": ["ts_code", "symbol", "name", "industry", "list_date"],
                "items": [["300750.SZ", "300750", "宁德时代", "电气设备", "20180611"]],
            },
        }
        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.stock_master._query_akshare_stock_basic", return_value=None):
                with patch("ashare_evidence.stock_master._post_tushare", return_value=mocked_response):
                    resolved = resolve_stock_profile(session, symbol="300750.SZ")

        self.assertEqual(resolved.name, "宁德时代")
        self.assertEqual(resolved.industry, "电气设备")
        self.assertEqual(resolved.template_key, "power_equipment")
        self.assertEqual(str(resolved.listed_date), "2018-06-11")
        self.assertEqual(resolved.source, "tushare_stock_basic")

    def test_akshare_stock_basic_can_supply_name_and_industry_without_token(self) -> None:
        mocked_response = {
            "name": "宁德时代",
            "industry": "电气设备",
            "list_date": "20180611",
        }
        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.stock_master._query_akshare_stock_basic", return_value=mocked_response):
                resolved = resolve_stock_profile(session, symbol="300750.SZ")

        self.assertEqual(resolved.name, "宁德时代")
        self.assertEqual(resolved.industry, "电气设备")
        self.assertEqual(resolved.template_key, "power_equipment")
        self.assertEqual(str(resolved.listed_date), "2018-06-11")
        self.assertEqual(resolved.source, "akshare_stock_master")

    def test_akshare_can_fallback_to_tushare_when_industry_is_missing(self) -> None:
        with session_scope(self.database_url) as session:
            session.add(
                ProviderCredential(
                    provider_name="tushare",
                    display_name="Tushare",
                    access_token="test-token",
                    base_url="http://api.tushare.pro",
                    enabled=True,
                    notes=None,
                    config_payload={},
                )
            )
            session.commit()

        akshare_response = {
            "name": "宁德时代",
            "industry": None,
            "list_date": "20180611",
        }
        tushare_response = {
            "code": 0,
            "data": {
                "fields": ["ts_code", "symbol", "name", "industry", "list_date"],
                "items": [["300750.SZ", "300750", "宁德时代", "电气设备", "20180611"]],
            },
        }
        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.stock_master._query_akshare_stock_basic", return_value=akshare_response):
                with patch("ashare_evidence.stock_master._post_tushare", return_value=tushare_response):
                    resolved = resolve_stock_profile(session, symbol="300750.SZ")

        self.assertEqual(resolved.name, "宁德时代")
        self.assertEqual(resolved.industry, "电气设备")
        self.assertEqual(resolved.template_key, "power_equipment")
        self.assertEqual(resolved.source, "akshare_stock_master+tushare_stock_basic")


if __name__ == "__main__":
    unittest.main()
