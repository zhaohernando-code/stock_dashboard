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
    assert 'acquire_publish_lock' in script
    assert 'PUBLISH_LOCK_DIR="$LOCK_DIR/publish.lock"' in script
    assert 'if mkdir "$PUBLISH_LOCK_DIR" 2>/dev/null; then' in script
    assert 'rm -rf "$PUBLISH_LOCK_DIR"' in script
    assert script.index('DIRTY_STATUS="$(git -C "$REPO_ROOT" status') < script.index(
        '\nacquire_publish_lock\n\n# Pause scheduled'
    )


def test_publish_python_bin_covers_verifier_and_refresh() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'PYTHON_BIN="${PYTHON_BIN:-python3}"' in script
    assert 'export ASHARE_ARTIFACT_ROOT="${ASHARE_ARTIFACT_ROOT:-$RUNTIME_ROOT/data/artifacts}"' in script
    assert 'PYTHONPATH=src "$PYTHON_BIN" -m ashare_evidence.release_verifier' in script
    assert '--release-output-root "$RUNTIME_ROOT/output/releases"' in script
    assert (
        'RELEASE_OPERATIONS_SAMPLE_SYMBOL="${ASHARE_RELEASE_OPERATIONS_SAMPLE_SYMBOL:-'
        '${ASHARE_OPERATIONS_PREWARM_SAMPLE_SYMBOL:-600519.SH}}"'
    ) in script
    assert 'RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS="${ASHARE_RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS:-90}"' in script
    assert '--operations-sample-symbol "$RELEASE_OPERATIONS_SAMPLE_SYMBOL"' in script
    assert '--operations-warmup-timeout-seconds "$RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS"' in script
    assert 'PYTHONPATH="$RUNTIME_ROOT/src" "$PYTHON_BIN" -m ashare_evidence.cli refresh-runtime-data' in script


def test_publish_installs_frontend_dependencies_before_build() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'FRONTEND_DIR="$REPO_ROOT/frontend"' in script
    assert 'ensure_frontend_dependencies' in script
    assert 'node_modules/.bin/tsc' in script
    assert 'node_modules/.bin/vite' in script
    assert 'npm --prefix "$FRONTEND_DIR" ci' in script
    assert 'ensure_frontend_dependencies\nnpm --prefix "$FRONTEND_DIR" run build' in script


def test_local_frontend_uses_managed_static_dist_server() -> None:
    script = (REPO_ROOT / "scripts" / "start-local-frontend.sh").read_text(encoding="utf-8")
    server = (REPO_ROOT / "scripts" / "serve-frontend-dist.mjs").read_text(encoding="utf-8")

    assert 'exec "$NODE_RUNNER" "$REPO_ROOT/scripts/serve-frontend-dist.mjs"' in script
    assert '--root "$FRONTEND_DIR/dist" --host 127.0.0.1 --port "$PORT"' in script
    assert "npx vite preview" not in script
    assert "vite preview" not in script
    assert "createServer" in server
    assert 'path.join(root, "index.html")' in server


def test_publish_build_uses_same_frontend_env_as_runtime() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'FRONTEND_ENV_FILE="${ASHARE_LOCAL_FRONTEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.frontend.env}"' in script
    assert 'source "$FRONTEND_ENV_FILE"' in script
    assert script.index('source "$FRONTEND_ENV_FILE"') < script.index('command -v npm')


def test_publish_bootstraps_scheduled_refresh_when_launchagent_is_unloaded() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'SCHEDULED_PLIST="$HOME/Library/LaunchAgents/${SCHEDULED_LABEL}.plist"' in script
    assert 'ensure_scheduled_refresh_calendar' in script
    assert 'trap cleanup_on_exit EXIT' in script
    assert 'wait_for_scheduled_refresh_quiescent' in script
    assert 'SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS="${ASHARE_PUBLISH_SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS:-180}"' in script
    assert 'Scheduled refresh is still running after ${SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS}s' in script
    assert 'resume_scheduled_refresh || true' in script
    assert 'launchctl bootout "gui/$(id -u)" "$SCHEDULED_PLIST"' in script
    assert 'launchctl bootstrap "gui/$(id -u)" "$SCHEDULED_PLIST"' in script
    assert script.index('wait_for_scheduled_refresh_quiescent') < script.index('echo "[publish] Building repo frontend"')
    assert script.index('if [[ "$VERIFY_MODE" == "canonical" ]]') < script.index(
        'echo "[publish] Triggering post-deploy data refresh"'
    )
    # Publish must NOT force-start the refresh: kickstart -k would launch a
    # full ~50min phase5-daily-refresh on every publish, holding the DB lock.
    assert 'kickstart -k "gui/$(id -u)/$SCHEDULED_LABEL"' not in script


def test_publish_restarts_runtime_launchagents_without_unload_load_race() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'MAX_WAIT_SECONDS="${ASHARE_PUBLISH_MAX_WAIT_SECONDS:-180}"' in script
    assert 'launchctl bootout "gui/$(id -u)" "$plist_path"' in script
    assert 'launchctl bootstrap "gui/$(id -u)" "$plist_path"' in script
    assert 'launchctl unload "$plist_path"' not in script
    assert 'launchctl load "$plist_path"' not in script
    assert script.index('launchctl bootout "gui/$(id -u)" "$plist_path"') < script.index(
        'launchctl bootstrap "gui/$(id -u)" "$plist_path"'
    )


def test_publish_forces_scheduled_refresh_runatload_false() -> None:
    # RunAtLoad=true would fire a full ~50min phase5-daily-refresh on every
    # publish/reload (launchctl bootstrap), which holds the DB lock and times
    # out the dashboard. ensure_scheduled_refresh_calendar must pin it false.
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'payload["RunAtLoad"] = False' in script
