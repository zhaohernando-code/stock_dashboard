# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from ashare_evidence.dashboard import (
    _candidate_primary_risk,
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.improvement_suggestions import _snapshot_counts, _write_snapshot
from ashare_evidence.manual_research_contract import EXECUTOR_KIND_BUILTIN_GPT
from ashare_evidence.manual_research_workflow import (
    complete_manual_research_request,
    create_manual_research_request,
    fail_manual_research_request,
)
from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.operations import (
    build_operations_dashboard,
    build_operations_detail,
)
from ashare_evidence.operations_projection_compaction import OPERATIONS_NAV_HISTORY_POINT_LIMIT
from ashare_evidence.phase2 import PHASE2_WINDOW_DEFINITION, phase2_target_horizon_label
from ashare_evidence.release_verifier import audit_user_visible_operations_text
from ashare_evidence.research_artifact_store import artifact_root_from_database_url
from ashare_evidence.schemas.stock import StockDashboardResponse
from ashare_evidence.watchlist import (
    add_watchlist_symbol,
    list_watchlist_entries,
    refresh_watchlist_symbol,
    remove_watchlist_symbol,
)
from tests.fixtures import inject_market_data_stale_backfill, seed_recommendation_fixture, seed_watchlist_fixture

pytestmark = pytest.mark.runtime_integration


class DashboardViewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "dashboard.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()


__all__ = [name for name in globals() if not name.startswith("__")]
