from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.requests import Request

from ashare_evidence.access import require_beta_access, require_beta_write_access
from ashare_evidence.dashboard import bootstrap_dashboard_demo, list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.watchlist import add_watchlist_symbol, list_watchlist_entries


class BetaAccessApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "api-access.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        self.original_mode = os.environ.get("ASHARE_BETA_ACCESS_MODE")
        self.original_allowlist = os.environ.get("ASHARE_BETA_ALLOWLIST")
        self.original_header = os.environ.get("ASHARE_BETA_ACCESS_HEADER")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self._restore_env("ASHARE_BETA_ACCESS_MODE", self.original_mode)
        self._restore_env("ASHARE_BETA_ALLOWLIST", self.original_allowlist)
        self._restore_env("ASHARE_BETA_ACCESS_HEADER", self.original_header)

    @staticmethod
    def _restore_env(key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    @staticmethod
    def _build_request(headers: dict[str, str] | None = None) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [
                    (key.lower().encode("utf-8"), value.encode("utf-8"))
                    for key, value in (headers or {}).items()
                ],
            }
        )

    def test_dashboard_routes_require_beta_key_when_allowlist_enabled(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "viewer-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"

        with self.assertRaises(HTTPException) as denied:
            require_beta_access(self._build_request())
        self.assertEqual(denied.exception.status_code, 403)
        self.assertIn("beta access denied", denied.exception.detail)

        viewer_access = require_beta_access(self._build_request({"X-Ashare-Beta-Key": "viewer-token"}))
        self.assertEqual(viewer_access.role, "viewer")
        with self.assertRaises(HTTPException) as viewer_write_denied:
            require_beta_write_access(viewer_access)
        self.assertEqual(viewer_write_denied.exception.status_code, 403)

        operator_access = require_beta_access(self._build_request({"X-Ashare-Beta-Key": "operator-token"}))
        self.assertEqual(operator_access.role, "operator")
        self.assertEqual(require_beta_write_access(operator_access), operator_access)

        with session_scope(self.database_url) as session:
            bootstrap = bootstrap_dashboard_demo(session)
        self.assertEqual(bootstrap["candidate_count"], 4)

        with session_scope(self.database_url) as session:
            allowed = list_candidate_recommendations(session, limit=8)
        self.assertGreaterEqual(len(allowed["items"]), 1)

        with session_scope(self.database_url) as session:
            operator_write = add_watchlist_symbol(session, "688981", stock_name="中芯国际")
        self.assertEqual(operator_write["symbol"], "688981.SH")

        with session_scope(self.database_url) as session:
            watchlist = list_watchlist_entries(session)
        self.assertIn("688981.SH", {item["symbol"] for item in watchlist["items"]})


if __name__ == "__main__":
    unittest.main()
