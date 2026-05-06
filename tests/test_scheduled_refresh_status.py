from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from ashare_evidence.scheduled_refresh_status import get_scheduled_refresh_status


def test_scheduled_refresh_status_reads_success_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SCHEDULED_REFRESH_STATE_DIR", str(tmp_path))
    (tmp_path / "daily-2026-05-06-postmarket.ok").write_text(
        "target_date=2026-05-06\nslot=postmarket\ncompleted_at=2026-05-06T16:45:00+0800\n",
        encoding="utf-8",
    )
    (tmp_path / "daily-2026-05-06-shortpick_lab.ok").write_text(
        "target_date=2026-05-06\nslot=shortpick_lab\ncompleted_at=2026-05-06T17:20:00+0800\n",
        encoding="utf-8",
    )

    payload = get_scheduled_refresh_status(datetime(2026, 5, 6, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert payload["status"] == "success"
    assert payload["label"] == "已完成"
    assert payload["target_date"] == "2026-05-06"
    assert payload["completed_at"] == "2026-05-06T17:20:00+0800"
    assert [(item["slot"], item["status"]) for item in payload["components"]] == [
        ("postmarket", "success"),
        ("shortpick_lab", "success"),
    ]


def test_scheduled_refresh_status_reports_shortpick_pending_when_main_done(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SCHEDULED_REFRESH_STATE_DIR", str(tmp_path))
    (tmp_path / "daily-2026-05-06-postmarket.ok").write_text(
        "target_date=2026-05-06\nslot=postmarket\ncompleted_at=2026-05-06T16:45:00+0800\n",
        encoding="utf-8",
    )

    payload = get_scheduled_refresh_status(datetime(2026, 5, 6, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert payload["status"] == "pending_catchup"
    assert payload["slot"] == "shortpick_lab"
    assert payload["components"][0]["status"] == "success"
    assert payload["components"][1]["status"] == "pending_catchup"
    assert payload["components"][1]["label"] == "试验田"


def test_scheduled_refresh_status_prefers_running_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SCHEDULED_REFRESH_STATE_DIR", str(tmp_path))
    lock = tmp_path / "run.lock"
    lock.mkdir()
    (lock / "context").write_text(
        f"pid={os.getpid()}\ntarget_date=2026-05-06\nslot=postmarket\nstarted_at=2026-05-06T16:20:05+0800\n",
        encoding="utf-8",
    )

    payload = get_scheduled_refresh_status(datetime(2026, 5, 6, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert payload["status"] == "running"
    assert payload["label"] == "正在跑"
    assert payload["pid"] == os.getpid()
    assert payload["started_at"] == "2026-05-06T16:20:05+0800"
    assert payload["components"][0]["status"] == "running"


def test_scheduled_refresh_status_reports_failed_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ASHARE_SCHEDULED_REFRESH_STATE_DIR", str(tmp_path))
    (tmp_path / "daily-2026-05-06-postmarket.failed").write_text(
        "\n".join(
            [
                "target_date=2026-05-06",
                "slot=postmarket",
                "started_at=2026-05-06T16:20:05+0800",
                "failed_at=2026-05-06T16:30:00+0800",
                "exit_code=124",
                "reason=daily refresh 执行失败，将等待下一次 5 分钟轮询重试。",
            ]
        ),
        encoding="utf-8",
    )

    payload = get_scheduled_refresh_status(datetime(2026, 5, 6, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert payload["status"] == "failed"
    assert payload["label"] == "部分失败"
    assert payload["exit_code"] == 124
