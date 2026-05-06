from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run-scheduled-refresh.sh"


def test_scheduled_refresh_script_has_valid_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True)


def test_postmarket_daily_refresh_is_single_1620_slot() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'POSTMARKET_REFRESH_AT="${ASHARE_POSTMARKET_DAILY_REFRESH_AT:-16:20}"' in script
    assert "PREMARKET_REFRESH_AT" not in script
    assert '"08:10"' not in script
    assert '"19:20"' not in script
    assert '"21:15"' not in script


def test_daily_refresh_has_catchup_guards() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "REFRESH_STATE_DIR" in script
    assert "slot_completed" in script
    assert "mark_slot_completed" in script
    assert "network_available" in script
    assert "acquire_run_lock" in script
    assert "run_with_timeout" in script
    assert "run_with_timeout \"$DAILY_REFRESH_TIMEOUT_SECONDS\" run_phase5_daily_refresh --analysis-only\n  local exit_code=$?" in script


def test_shortpick_lab_is_part_of_postmarket_daily_cycle() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'ASHARE_ENABLE_SHORTPICK_LAB:-1' in script
    assert "shortpick-lab-validate-recent" in script
    assert "run_shortpick_daily_cycle" in script
    assert "run_shortpick_lab_slot \"$TODAY_STR\"" in script
    assert "run_with_timeout \"$SHORTPICK_TIMEOUT_SECONDS\" run_shortpick_daily_cycle\n  local exit_code=$?" in script
