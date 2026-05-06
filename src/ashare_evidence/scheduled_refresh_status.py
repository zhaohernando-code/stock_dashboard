"""Read-only scheduled daily refresh status projection."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_POSTMARKET_REFRESH_AT = "16:20"
POSTMARKET_SLOT = "postmarket"
SHORTPICK_SLOT = "shortpick_lab"
SLOT_LABELS = {
    POSTMARKET_SLOT: "主分析",
    SHORTPICK_SLOT: "试验田",
}


def _state_dir() -> Path:
    return Path(
        os.environ.get(
            "ASHARE_SCHEDULED_REFRESH_STATE_DIR",
            str(Path.home() / ".cache" / "codex" / "ashare-dashboard-refresh"),
        )
    )


def _timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("ASHARE_REFRESH_TIMEZONE", DEFAULT_TIMEZONE))


def _postmarket_time() -> str:
    return os.environ.get("ASHARE_POSTMARKET_DAILY_REFRESH_AT", DEFAULT_POSTMARKET_REFRESH_AT)


def _shortpick_enabled() -> bool:
    return os.environ.get("ASHARE_ENABLE_SHORTPICK_LAB", "1") == "1"


def _expected_slots() -> list[str]:
    slots = [POSTMARKET_SLOT]
    if _shortpick_enabled():
        slots.append(SHORTPICK_SLOT)
    return slots


def _read_key_value_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def _pid_alive(pid_value: str | None) -> bool:
    if not pid_value:
        return False
    try:
        pid = int(pid_value)
    except ValueError:
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _slot_file(target_date: str, slot: str, suffix: str) -> Path:
    return _state_dir() / f"daily-{target_date}-{slot}.{suffix}"


def _slot_display_name(slot: str) -> str:
    return SLOT_LABELS.get(slot, slot)


def _state_time(values: dict[str, str]) -> str | None:
    return (
        values.get("completed_at")
        or values.get("failed_at")
        or values.get("deferred_at")
        or values.get("started_at")
    )


def _slot_component(target_date: str, slot: str, *, missing_status: str = "pending_catchup") -> dict[str, Any]:
    display = _slot_display_name(slot)
    ok = _read_key_value_file(_slot_file(target_date, slot, "ok"))
    if ok:
        completed_at = ok.get("completed_at")
        return {
            "slot": slot,
            "label": display,
            "status": "success",
            "status_label": "已完成",
            "message": f"{target_date} {display}已完成。",
            "started_at": ok.get("started_at"),
            "completed_at": completed_at,
            "failed_at": None,
            "deferred_at": None,
            "exit_code": None,
            "state_updated_at": completed_at,
        }

    failed = _read_key_value_file(_slot_file(target_date, slot, "failed"))
    if failed:
        failed_at = failed.get("failed_at")
        return {
            "slot": slot,
            "label": display,
            "status": "failed",
            "status_label": "失败待重试",
            "message": failed.get("reason") or f"{target_date} {display}上次执行失败。",
            "started_at": failed.get("started_at"),
            "completed_at": None,
            "failed_at": failed_at,
            "deferred_at": None,
            "exit_code": int(failed["exit_code"]) if failed.get("exit_code", "").isdigit() else None,
            "state_updated_at": failed_at,
        }

    deferred = _read_key_value_file(_slot_file(target_date, slot, "deferred"))
    if deferred:
        deferred_at = deferred.get("deferred_at")
        return {
            "slot": slot,
            "label": display,
            "status": "pending_catchup",
            "status_label": "待补跑",
            "message": deferred.get("reason") or f"{target_date} {display}等待联网后补跑。",
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "deferred_at": deferred_at,
            "exit_code": None,
            "state_updated_at": deferred_at,
        }

    status_label = "等待 16:20" if missing_status == "scheduled" else "待补跑"
    message = (
        f"{target_date} {display}尚未到触发时间。"
        if missing_status == "scheduled"
        else f"{target_date} {display}尚未完成，等待 5 分钟轮询补跑。"
    )
    return {
        "slot": slot,
        "label": display,
        "status": missing_status,
        "status_label": status_label,
        "message": message,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "deferred_at": None,
        "exit_code": None,
        "state_updated_at": None,
    }


def _running_payload(now: datetime) -> dict[str, Any] | None:
    lock_dir = _state_dir() / "run.lock"
    pid_value = _read_key_value_file(lock_dir / "context").get("pid")
    if not pid_value and (lock_dir / "pid").exists():
        pid_value = (lock_dir / "pid").read_text(encoding="utf-8", errors="replace").strip()
    if not _pid_alive(pid_value):
        return None

    context = _read_key_value_file(lock_dir / "context")
    target_date = context.get("target_date") or now.date().isoformat()
    started_at = context.get("started_at")
    running_slot = context.get("slot") or POSTMARKET_SLOT
    components = [
        (
            {
                **_slot_component(target_date, slot),
                "status": "running",
                "status_label": "正在跑",
                "message": f"{target_date} {_slot_display_name(slot)}正在执行。",
                "started_at": started_at,
                "state_updated_at": started_at,
            }
            if slot == running_slot
            else _slot_component(target_date, slot)
        )
        for slot in _expected_slots()
    ]
    return {
        "status": "running",
        "label": "正在跑",
        "message": f"{target_date} {_slot_display_name(running_slot)}正在执行。",
        "target_date": target_date,
        "slot": running_slot,
        "scheduled_time": _postmarket_time(),
        "started_at": started_at,
        "completed_at": None,
        "failed_at": None,
        "deferred_at": None,
        "exit_code": None,
        "pid": int(pid_value) if pid_value and pid_value.isdigit() else None,
        "state_updated_at": started_at,
        "next_action": "等待当前任务结束；完成后会写入成功标记，失败后会等待下一次 5 分钟轮询重试。",
        "components": components,
    }


def _latest_known_target_date(now: datetime) -> str:
    postmarket = _postmarket_time()
    if now.strftime("%H:%M") >= postmarket and now.isoweekday() <= 5:
        return now.date().isoformat()
    return (now.date() - timedelta(days=1)).isoformat()


def get_scheduled_refresh_status(now: datetime | None = None) -> dict[str, Any]:
    """Return a frontend-friendly status for the post-market daily refresh slots."""

    tz = _timezone()
    now_local = (now or datetime.now(tz)).astimezone(tz)
    running = _running_payload(now_local)
    if running:
        return running

    before_postmarket = now_local.strftime("%H:%M") < _postmarket_time() and now_local.isoweekday() <= 5
    target_date = now_local.date().isoformat() if before_postmarket else _latest_known_target_date(now_local)
    components = [
        _slot_component(target_date, slot, missing_status="scheduled" if before_postmarket else "pending_catchup")
        for slot in _expected_slots()
    ]
    component_times = [value for value in (_state_time(component) for component in components) if value is not None]
    latest_component_time = max(component_times) if component_times else None
    if components and all(component["status"] == "success" for component in components):
        return {
            "status": "success",
            "label": "已完成",
            "message": f"{target_date} 盘后 daily refresh 与试验田已完成。",
            "target_date": target_date,
            "slot": POSTMARKET_SLOT,
            "scheduled_time": _postmarket_time(),
            "started_at": None,
            "completed_at": latest_component_time,
            "failed_at": None,
            "deferred_at": None,
            "exit_code": None,
            "pid": None,
            "state_updated_at": latest_component_time,
            "next_action": "下一次 daily refresh 将在下一个交易日 16:20 后触发。",
            "components": components,
        }

    failed_components = [component for component in components if component["status"] == "failed"]
    if failed_components:
        primary = failed_components[0]
        return {
            "status": "failed",
            "label": "部分失败",
            "message": primary["message"],
            "target_date": target_date,
            "slot": primary["slot"],
            "scheduled_time": _postmarket_time(),
            "started_at": primary["started_at"],
            "completed_at": None,
            "failed_at": primary["failed_at"],
            "deferred_at": None,
            "exit_code": primary["exit_code"],
            "pid": None,
            "state_updated_at": primary["state_updated_at"],
            "next_action": "联网后会由 5 分钟轮询自动重试，也可手动触发运行脚本。",
            "components": components,
        }

    pending_components = [component for component in components if component["status"] == "pending_catchup"]
    if pending_components:
        primary = pending_components[0]
        return {
            "status": "pending_catchup",
            "label": "待补跑",
            "message": primary["message"],
            "target_date": target_date,
            "slot": primary["slot"],
            "scheduled_time": _postmarket_time(),
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "deferred_at": primary["deferred_at"],
            "exit_code": None,
            "pid": None,
            "state_updated_at": primary["state_updated_at"],
            "next_action": "检测到联网后会自动补跑。",
            "components": components,
        }

    if before_postmarket:
        return {
            "status": "scheduled",
            "label": "等待 16:20",
            "message": f"今日盘后 daily refresh 尚未到触发时间，将在 {_postmarket_time()} 后执行。",
            "target_date": now_local.date().isoformat(),
            "slot": POSTMARKET_SLOT,
            "scheduled_time": _postmarket_time(),
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "deferred_at": None,
            "exit_code": None,
            "pid": None,
            "state_updated_at": None,
            "next_action": "到达 16:20 后由 LaunchAgent 或 5 分钟轮询触发。",
            "components": components,
        }

    return {
        "status": "pending_catchup",
        "label": "待补跑",
        "message": f"{target_date} 盘后 daily refresh 尚未完成，等待 5 分钟轮询补跑。",
        "target_date": target_date,
        "slot": POSTMARKET_SLOT,
        "scheduled_time": _postmarket_time(),
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "deferred_at": None,
        "exit_code": None,
        "pid": None,
        "state_updated_at": None,
        "next_action": "电脑醒来且联网后会自动补跑。",
        "components": components,
    }
