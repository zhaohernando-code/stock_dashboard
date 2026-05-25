from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_evidence.runtime_locks import scheduled_refresh_lock_active


class ApiBackgroundLockTests(unittest.TestCase):
    def test_scheduled_refresh_lock_is_inactive_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"ASHARE_SCHEDULED_REFRESH_STATE_DIR": temp_dir},
        ):
            self.assertFalse(scheduled_refresh_lock_active())

    def test_scheduled_refresh_lock_is_active_for_live_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"ASHARE_SCHEDULED_REFRESH_STATE_DIR": temp_dir},
        ):
            lock_dir = Path(temp_dir) / "run.lock"
            lock_dir.mkdir()
            (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")

            self.assertTrue(scheduled_refresh_lock_active())

    def test_scheduled_refresh_lock_is_inactive_for_stale_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"ASHARE_SCHEDULED_REFRESH_STATE_DIR": temp_dir},
        ):
            lock_dir = Path(temp_dir) / "run.lock"
            lock_dir.mkdir()
            (lock_dir / "pid").write_text("99999999", encoding="utf-8")

            self.assertFalse(scheduled_refresh_lock_active())
