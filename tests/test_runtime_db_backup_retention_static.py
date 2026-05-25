from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prune-runtime-db-backups.sh"


def test_runtime_db_backup_retention_script_has_valid_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True)


def test_runtime_db_backup_retention_keeps_current_db_out_of_scope() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ashare_dashboard.before-*.db" in script
    assert "ashare_dashboard.db.bak-*" in script
    assert "ashare_dashboard.db" not in script.replace("ashare_dashboard.db.bak-*", "")
    assert "ASHARE_DB_BACKUP_KEEP_RECENT" in script
    assert "ASHARE_DB_BACKUP_MIN_AGE_DAYS" in script
    assert "ASHARE_DB_BACKUP_ARCHIVE_RETENTION_DAYS" in script
    assert "ASHARE_DB_BACKUP_PRUNE_DRY_RUN" in script
    assert "lsof \"$path\"" in script
    assert "gzip -c \"$path\"" in script
    assert "$HOME/Library/Logs/codex-archive/ashare-dashboard-db-backups" in script
