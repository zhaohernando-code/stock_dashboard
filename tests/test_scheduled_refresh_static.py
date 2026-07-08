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
    assert 'ARTIFACT_ROOT_HELPER="$REPO_ROOT/scripts/ashare-artifact-root.sh"' in script
    assert 'source "$ARTIFACT_ROOT_HELPER"' in script
    assert 'ashare_resolve_local_artifact_root "$REPO_ROOT"' in script
    assert "slot_completed" in script
    assert "postmarket_slot_due" in script
    assert 'time_lt "$NOW_HHMM" "$POSTMARKET_REFRESH_AT"' in script
    assert "mark_slot_completed" in script
    assert "network_available" in script
    assert "acquire_run_lock" in script
    assert "run_with_timeout" in script
    assert "process_tree_pids" in script
    assert 'pgrep -P "$root_pid"' in script
    assert 'kill $descendant_pids' in script
    assert "run_with_timeout \"$DAILY_REFRESH_TIMEOUT_SECONDS\" run_phase5_daily_refresh --analysis-only\n  local exit_code=$?" in script


def test_slot_retry_interval_is_at_least_daily_refresh_duration() -> None:
    # The daily refresh can run ~50min; a short (30min) retry let an
    # interrupted slot relaunch while the prior attempt was still settling,
    # stacking heavy DB writers. Default must be >= 2h.
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'SLOT_RETRY_INTERVAL_SECONDS="${ASHARE_SLOT_RETRY_INTERVAL_SECONDS:-7200}"' in script
    assert ':-1800}' not in script


def test_shortpick_lab_is_part_of_postmarket_daily_cycle() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'ASHARE_ENABLE_SHORTPICK_LAB:-1' in script
    assert "shortpick-lab-validate-recent" in script
    assert "frontend-projections-refresh" in script
    assert "--projection all" in script
    assert 'SHORTPICK_VALIDATION_TIMEOUT_SECONDS="${ASHARE_SHORTPICK_VALIDATION_TIMEOUT_SECONDS:-600}"' in script
    assert 'SHORTPICK_VALIDATE_RECENT_BEFORE_RUN="${ASHARE_SHORTPICK_VALIDATE_RECENT_BEFORE_RUN:-0}"' in script
    assert 'SHORTPICK_VALIDATE_RECENT_AFTER_RUN="${ASHARE_SHORTPICK_VALIDATE_RECENT_AFTER_RUN:-1}"' in script
    assert "--existing-market-data-only" in script
    assert 'SHORTPICK_RETRY_FAILED_AFTER_RUN="${ASHARE_SHORTPICK_RETRY_FAILED_AFTER_RUN:-0}"' in script
    assert 'DATABASE_LOCK_WAIT_SECONDS="${ASHARE_DATABASE_LOCK_WAIT_SECONDS:-60}"' in script
    assert 'run_with_timeout "$SHORTPICK_VALIDATION_TIMEOUT_SECONDS" run_shortpick_validation_refresh' in script
    assert 'set ASHARE_SHORTPICK_VALIDATE_RECENT_BEFORE_RUN=1 for maintenance catch-up' in script
    assert 'set ASHARE_SHORTPICK_RETRY_FAILED_AFTER_RUN=1 for maintenance retry' in script
    assert "continuing with ${target_date} run" in script
    assert "continuing with frontend projection refresh" in script
    assert "wait_for_database_writable" in script
    assert 'connection.execute(text("BEGIN IMMEDIATE"))' in script
    assert '--run-date "$target_date"' in script
    assert "run_shortpick_daily_cycle" in script
    assert "run_frontend_projection_refresh" in script
    assert "refresh_shortpick_strategy_lab_v3_candidate_run_source" in script
    assert "refresh_shortpick_strategy_lab_paper_state" in script
    assert "build-shortpick-strategy-lab-v3-candidate-run-source.py" in script
    assert "refresh-shortpick-strategy-lab-paper-state.py" in script
    assert "Shortpick strategy lab v3 candidate-run source refresh failed." in script
    assert "Shortpick strategy lab paper state refresh failed." in script
    assert "Shortpick strategy lab paper state refresh failed; keeping previous state." not in script
    assert "keeping previous projection rows" in script
    assert "prewarm_shortpick_v2_paper_cache" not in script
    assert "prewarm-shortpick-v2-paper-cache.sh" not in script
    assert "run_shortpick_lab_slot \"$TODAY_STR\"" in script
    assert "run_with_timeout \"$SHORTPICK_TIMEOUT_SECONDS\" run_shortpick_daily_cycle \"$target_date\"\n  local exit_code=$?" in script


def test_intraday_same_day_shortpick_control_has_timeboxed_slot() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'INTRADAY_SAME_DAY_REFRESH_AT="${ASHARE_INTRADAY_SAME_DAY_REFRESH_AT:-13:55}"' in script
    assert 'SHORTPICK_INTRADAY_TIMEOUT_SECONDS="${ASHARE_SHORTPICK_INTRADAY_TIMEOUT_SECONDS:-600}"' in script
    assert 'SHORTPICK_INTRADAY_RETRY_INTERVAL_SECONDS="${ASHARE_SHORTPICK_INTRADAY_RETRY_INTERVAL_SECONDS:-60}"' in script
    assert "shortpick-lab-intraday-same-day" in script
    assert "run_shortpick_intraday_same_day_slot \"$TODAY_STR\"" in script
    assert 'slot_recently_failed "$target_date" "$slot_name" "$SHORTPICK_INTRADAY_RETRY_INTERVAL_SECONDS"' in script
    assert 'time_lt "$NOW_HHMM" "$POSTMARKET_REFRESH_AT"' in script
    assert 'run_with_timeout "$SHORTPICK_INTRADAY_TIMEOUT_SECONDS" run_shortpick_intraday_same_day "$target_date"' in script


def test_previous_trading_day_catchup_never_runs_today_before_postmarket() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '[[ "$previous_date" == "$TODAY_STR" ]] && time_lt "$NOW_HHMM" "$POSTMARKET_REFRESH_AT"' in script
    assert "Skipping previous trading day refresh; resolved ${previous_date} equals today before postmarket slot" in script


def test_scheduled_refresh_never_treats_weekends_as_trading_days() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "target_date = date.fromisoformat(target)" in script
    assert "if target_date.weekday() >= 5:" in script
    assert "sys.exit(1)" in script
    assert "weekends are already rejected above" in script


def test_publish_reloads_scheduled_refresh_calendar_slots() -> None:
    script = (REPO_ROOT / "scripts" / "publish-local-runtime.sh").read_text(encoding="utf-8")

    assert "ensure_scheduled_refresh_calendar" in script
    assert '{"Hour": 13, "Minute": 55}' in script
    assert '{"Hour": 14, "Minute": 0}' in script
    assert '{"Hour": 14, "Minute": 5}' in script
    assert '{"Hour": 16, "Minute": 20}' in script
    assert 'launchctl bootout "gui/$(id -u)" "$SCHEDULED_PLIST"' in script
    assert 'launchctl bootstrap "gui/$(id -u)" "$SCHEDULED_PLIST"' in script


def test_daily_refresh_no_longer_prewarms_shortpick_v2_paper_cache_after_market_data_refresh() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "Shortpick v2 paper cache prewarm failed after daily refresh" not in script
    assert "prewarm_shortpick_v2_paper_cache" not in script
    assert script.index('run_with_timeout "$DAILY_REFRESH_TIMEOUT_SECONDS" run_phase5_daily_refresh --analysis-only') < (
        script.index('mark_slot_completed "$target_date" "$slot_name"')
    )


def test_deepseek_shortpick_round_has_in_process_soft_timeout() -> None:
    source = (REPO_ROOT / "src" / "ashare_evidence" / "shortpick_lab.py").read_text(encoding="utf-8")

    assert "ASHARE_SHORTPICK_DEEPSEEK_ROUND_TIMEOUT_SECONDS" in source
    assert "SHORTPICK_DEEPSEEK_SEARCH_TIMEOUT_SECONDS = 180" in source
    assert "signal.setitimer(signal.ITIMER_REAL, timeout_seconds)" in source
    assert "deepseek_tool_search_lobechat_searxng_v1" in source
    assert "with _shortpick_executor_round_timeout(executor):\n            raw_answer = executor.complete(prompt)" in source
