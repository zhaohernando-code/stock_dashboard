from __future__ import annotations

import json
from pathlib import Path


def build_horizon_readout(artifact_root: str) -> str | None:
    if not artifact_root:
        return None
    studies_dir = Path(artifact_root) / "studies"
    if not studies_dir.exists():
        return None
    candidates = sorted(
        studies_dir.glob("phase5-horizon-study:history*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        candidates = sorted(
            studies_dir.glob("phase5-horizon-study:latest*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if not candidates:
        return None
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    decision = data.get("decision", {})
    status = data.get("primary_horizon_status", "pending")
    if status == "approved":
        return "主周期已批准。"
    candidate_frontier = decision.get("candidate_frontier", [])
    note = decision.get("note", "")
    if not candidate_frontier:
        return None
    frontier_str = "、".join(f"{h}d" for h in candidate_frontier)
    source_date = data.get("generated_at", "")[:10]
    return (
        f"当前研究领先窗口：{frontier_str}（来源：Phase 5 horizon study {source_date}）；"
        f"产品主展示窗口：20d；主周期尚未批准，展示口径仍以 20d 为准。"
        + (f" {note}" if note else "")
    )
