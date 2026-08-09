from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_timeout_worker_isolates_file_descriptors_and_preserves_diagnostics() -> None:
    helper_source = (REPO_ROOT / "src" / "ashare_evidence" / "akshare_timeout.py").read_text(encoding="utf-8")

    assert "close_fds=True" in helper_source
    assert "str(Path(__file__).resolve())" in helper_source
    assert 'stderr_path = temp_root / "stderr.log"' in helper_source
