# ruff: noqa: F401
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.improvement_suggestions import (
    _run_reviewer,
    _snapshot_counts,
    _transport_for_model_key,
    _write_snapshot,
    accept_suggestion_for_plan,
    collect_improvement_suggestions,
    parse_reviewer_json,
    run_improvement_suggestion_review,
    suggestion_details,
    summarize_suggestion_review,
    update_suggestion_status,
)
from ashare_evidence.llm_service import AnthropicCompatibleTransport, OpenAICompatibleTransport
from ashare_evidence.models import FeatureSnapshot, ModelApiKey, Stock
from ashare_evidence.research_artifact_store import artifact_root_from_database_url
from tests.fixtures import seed_watchlist_fixture

pytestmark = pytest.mark.runtime_integration


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ImprovementSuggestionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "suggestions.db"
        self.database_url = f"sqlite:///{self.database_path}"
        init_database(self.database_url)
        self.original_mode = os.environ.get("ASHARE_BETA_ACCESS_MODE")
        self.original_allowlist = os.environ.get("ASHARE_BETA_ALLOWLIST")
        self.original_header = os.environ.get("ASHARE_BETA_ACCESS_HEADER")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self._restore_env("ASHARE_BETA_ACCESS_MODE", self.original_mode)
        self._restore_env("ASHARE_BETA_ALLOWLIST", self.original_allowlist)
        self._restore_env("ASHARE_BETA_ACCESS_HEADER", self.original_header)

    def _restore_env(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def _write_event_analysis(self, symbol: str = "600519.SH", suggestion: str = "首页风险展示应优先解释 RankIC 冲突。") -> None:
        artifact_root = artifact_root_from_database_url(self.database_url)
        event_dir = artifact_root / "event_analysis" / symbol
        event_dir.mkdir(parents=True, exist_ok=True)
        filename = "20260501T090000_factor_conflict.json"
        payload = {
            "symbol": symbol,
            "trigger_type": "factor_conflict",
            "triggered_at": "2026-05-01T09:00:00+08:00",
            "generated_at": "2026-05-01T09:01:00+08:00",
            "status": "completed",
            "independent_direction": "partial_agree",
            "confidence": 0.62,
            "correction_suggestion": suggestion,
        }
        (event_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (event_dir / "index.json").write_text(
            json.dumps(
                [
                    {
                        "file": filename,
                        "trigger_type": "factor_conflict",
                        "generated_at": payload["generated_at"],
                        "status": "completed",
                        "independent_direction": "partial_agree",
                        "confidence": 0.62,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

__all__ = [name for name in globals() if not name.startswith("__")]
