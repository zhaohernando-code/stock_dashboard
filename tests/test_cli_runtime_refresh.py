from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pytest

from ashare_evidence.cli import main
from ashare_evidence.db import get_engine, init_database, session_scope
from tests.fixtures import seed_watchlist_fixture

pytestmark = pytest.mark.runtime_integration


class CliRuntimeRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "runtime.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_phase5_daily_refresh_fails_fast_when_sqlite_database_is_not_writable(self) -> None:
        database_path = Path(self.temp_dir.name) / "readonly-runtime.db"
        database_url = f"sqlite:///{database_path}"
        init_database(database_url)
        get_engine(database_url).dispose()
        database_path.chmod(0o444)
        try:
            with self.assertRaisesRegex(RuntimeError, "database write preflight failed"):
                main(["phase5-daily-refresh", "--database-url", database_url, "--skip-simulation"])
        finally:
            database_path.chmod(0o644)

    def test_phase5_horizon_study_write_artifact_marks_reused_snapshot(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        first_stdout = io.StringIO()
        with contextlib.redirect_stdout(first_stdout):
            first_exit = main(["phase5-horizon-study", "--database-url", self.database_url, "--write-artifact"])
        self.assertEqual(first_exit, 0)
        self.assertIn('"reused_existing_snapshot": false', first_stdout.getvalue())

        second_stdout = io.StringIO()
        with contextlib.redirect_stdout(second_stdout):
            second_exit = main(["phase5-horizon-study", "--database-url", self.database_url, "--write-artifact"])
        self.assertEqual(second_exit, 0)
        self.assertIn('"reused_existing_snapshot": true', second_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
