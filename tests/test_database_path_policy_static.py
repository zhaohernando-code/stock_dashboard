from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ashare_evidence.db import DEFAULT_DB_PATH, DEFAULT_DB_URL

REPO_ROOT = Path(__file__).resolve().parents[1]


LIVE_DB_POLICY_FILES = [
    Path("src/ashare_evidence/db.py"),
    Path("scripts/start-local-backend.sh"),
    Path("scripts/run-scheduled-refresh.sh"),
    Path("scripts/prewarm-shortpick-v2-paper-cache.sh"),
    Path("scripts/refresh-shortpick-v1-control-combined-ledger.sh"),
    Path("scripts/refresh-shortpick-v2-paper-ledger.sh"),
    Path("scripts/run-shortpick-v2-h10-paper-governance.sh"),
    Path("scripts/verify-shortpick-10d-runtime-refresh.sh"),
    Path("scripts/migrate_005_add_market_cap_columns.py"),
    Path("scripts/backfill_shortpick_prefreeze_20260508_paper_tracking.py"),
]

LEGACY_LIVE_DEFAULT_PATTERNS = [
    re.compile(r":-[^}\n]*ashare_dashboard\.db"),
    re.compile(r"default\s*=\s*[\"']sqlite:///data/ashare_dashboard\.db[\"']"),
    re.compile(r"DB_PATH\s*=\s*[\"'][^\"']*runtime/projects/ashare-dashboard/data/ashare_dashboard\.db[\"']"),
    re.compile(r"DEFAULT_DB_PATH\s*=\s*Path\([\"']data/ashare_dashboard\.db[\"']\)"),
    re.compile(r"Path\.home\(\)[^\n]*ashare_dashboard\.db"),
]


def test_default_database_url_targets_hot_db() -> None:
    assert DEFAULT_DB_PATH == Path("data/ashare_hot.db")
    assert DEFAULT_DB_URL == "sqlite:///data/ashare_hot.db"
    assert "ashare_dashboard.db" not in DEFAULT_DB_URL


def test_live_database_defaults_do_not_target_legacy_dashboard_db() -> None:
    offenders: list[str] = []
    for relative in LIVE_DB_POLICY_FILES:
        body = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for pattern in LEGACY_LIVE_DEFAULT_PATTERNS:
            if pattern.search(body):
                offenders.append(f"{relative}: {pattern.pattern}")

    assert offenders == []


def test_runtime_scripts_keep_hot_db_fallbacks() -> None:
    expected = {
        "scripts/start-local-backend.sh": "data/ashare_hot.db",
        "scripts/run-scheduled-refresh.sh": "data/ashare_hot.db",
        "scripts/prewarm-shortpick-v2-paper-cache.sh": "data/ashare_hot.db",
        "scripts/refresh-shortpick-v1-control-combined-ledger.sh": "data/ashare_hot.db",
        "scripts/refresh-shortpick-v2-paper-ledger.sh": "data/ashare_hot.db",
        "scripts/run-shortpick-v2-h10-paper-governance.sh": "data/ashare_hot.db",
        "scripts/verify-shortpick-10d-runtime-refresh.sh": "data/ashare_hot.db",
        "scripts/migrate_005_add_market_cap_columns.py": "ashare_hot.db",
    }
    for relative, needle in expected.items():
        assert needle in (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_runtime_shell_scripts_have_valid_bash_syntax() -> None:
    for relative in [
        "scripts/ashare-backend-env.sh",
        "scripts/start-local-backend.sh",
        "scripts/run-scheduled-refresh.sh",
        "scripts/prewarm-shortpick-v2-paper-cache.sh",
        "scripts/refresh-shortpick-v1-control-combined-ledger.sh",
        "scripts/refresh-shortpick-v2-paper-ledger.sh",
        "scripts/run-shortpick-v2-h10-paper-governance.sh",
        "scripts/verify-shortpick-10d-runtime-refresh.sh",
    ]:
        subprocess.run(["bash", "-n", str(REPO_ROOT / relative)], check=True)


def test_backend_env_helper_preserves_explicit_database_overrides(tmp_path: Path) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        "\n".join(
            [
                "ASHARE_DATABASE_URL=sqlite:////env/ashare_hot.db",
                "ASHARE_RUNTIME_DB_PATH=/env/ashare_hot.db",
                "ASHARE_MARKET_HISTORY_DATABASE_URL=sqlite:////env/market.db",
            ]
        ),
        encoding="utf-8",
    )

    command = (
        f"source {REPO_ROOT / 'scripts/ashare-backend-env.sh'}; "
        "ASHARE_DATABASE_URL=sqlite:////explicit/ashare_hot.db "
        "ASHARE_RUNTIME_DB_PATH=/explicit/ashare_hot.db "
        f"ashare_source_backend_env {env_file}; "
        'printf "%s\\n%s\\n%s\\n" "$ASHARE_DATABASE_URL" "$ASHARE_RUNTIME_DB_PATH" '
        '"$ASHARE_MARKET_HISTORY_DATABASE_URL"'
    )
    result = subprocess.run(["bash", "-c", command], check=True, text=True, stdout=subprocess.PIPE)

    assert result.stdout.splitlines() == [
        "sqlite:////explicit/ashare_hot.db",
        "/explicit/ashare_hot.db",
        "sqlite:////env/market.db",
    ]
