from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "publish-local-runtime.sh"


def test_publish_script_has_valid_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True)


def test_publish_sync_does_not_copy_git_metadata_to_runtime() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'rm -rf "$RUNTIME_ROOT/.git"' in script
    assert '"$RSYNC_BIN" -a --delete \\\n  --exclude ".git" \\\n  --exclude "data"' in script


def test_publish_python_bin_covers_verifier_and_refresh() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'PYTHON_BIN="${PYTHON_BIN:-python3}"' in script
    assert 'PYTHONPATH=src "$PYTHON_BIN" -m ashare_evidence.release_verifier' in script
    assert '--release-output-root "$RUNTIME_ROOT/output/releases"' in script
    assert 'PYTHONPATH="$RUNTIME_ROOT/src" "$PYTHON_BIN" -m ashare_evidence.cli refresh-runtime-data' in script
