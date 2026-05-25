from __future__ import annotations

import os
from pathlib import Path


def scheduled_refresh_lock_active() -> bool:
    state_dir = Path(
        os.path.expanduser(os.getenv("ASHARE_SCHEDULED_REFRESH_STATE_DIR", "~/.cache/codex/ashare-dashboard-refresh"))
    )
    pid_path = state_dir / "run.lock" / "pid"
    try:
        pid_text = pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        pid = int(pid_text)
    except ValueError:
        return True
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
