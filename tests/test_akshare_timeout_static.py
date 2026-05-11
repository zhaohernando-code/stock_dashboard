from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_timeout_worker_uses_posix_spawn_friendly_launch() -> None:
    helper_source = (REPO_ROOT / "src" / "ashare_evidence" / "akshare_timeout.py").read_text(encoding="utf-8")

    assert "close_fds=False" in helper_source
    assert "close_fds=True" not in helper_source
