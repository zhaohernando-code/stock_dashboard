from __future__ import annotations

from pathlib import Path
from typing import Any

CANDIDATE_RUN_FOLDER = Path("research_validation") / "walk_forward_model_candidate_runs"
DEFAULT_MAX_RETAINED_ROOT_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_COMPACT_REPLAY_ROOT_BYTES = 128 * 1024 * 1024


def audit_research_artifact_retention(
    *,
    retained_root: str | Path,
    compact_replay_roots: list[str | Path] | None = None,
    max_retained_candidate_run_files: int = 0,
    max_compact_replay_roots: int = 2,
    max_retained_root_bytes: int | None = DEFAULT_MAX_RETAINED_ROOT_BYTES,
    max_compact_replay_root_bytes: int | None = DEFAULT_MAX_COMPACT_REPLAY_ROOT_BYTES,
) -> dict[str, Any]:
    retained_path = Path(retained_root)
    replay_paths = [Path(path) for path in compact_replay_roots or []]
    blocking_gate_ids: list[str] = []

    retained_exists = retained_path.exists()
    retained_root_bytes = _directory_size(retained_path) if retained_exists else 0
    retained_candidate_run_files = _candidate_run_files(retained_path) if retained_exists else []

    if not retained_exists:
        blocking_gate_ids.append("research_artifact_retention:retained_root_missing")
    if len(retained_candidate_run_files) > max_retained_candidate_run_files:
        blocking_gate_ids.append("research_artifact_retention:retained_candidate_run_payloads")
    if max_retained_root_bytes is not None and retained_root_bytes > max_retained_root_bytes:
        blocking_gate_ids.append("research_artifact_retention:retained_root_size_exceeded")
    if len(replay_paths) > max_compact_replay_roots:
        blocking_gate_ids.append("research_artifact_retention:too_many_compact_replay_roots")

    replay_root_summaries = []
    for replay_path in replay_paths:
        exists = replay_path.exists()
        size_bytes = _directory_size(replay_path) if exists else 0
        replay_root_summaries.append(
            {
                "path": str(replay_path),
                "exists": exists,
                "size_bytes": size_bytes,
            }
        )
        if not exists:
            blocking_gate_ids.append("research_artifact_retention:compact_replay_root_missing")
        if max_compact_replay_root_bytes is not None and size_bytes > max_compact_replay_root_bytes:
            blocking_gate_ids.append("research_artifact_retention:compact_replay_root_size_exceeded")

    blocking_gate_ids = sorted(set(blocking_gate_ids))
    return {
        "artifact_type": "research_artifact_retention_audit",
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "retained_root": {
            "path": str(retained_path),
            "exists": retained_exists,
            "size_bytes": retained_root_bytes,
            "candidate_run_file_count": len(retained_candidate_run_files),
            "candidate_run_files": [str(path) for path in retained_candidate_run_files[:20]],
            "max_candidate_run_files": max_retained_candidate_run_files,
            "max_size_bytes": max_retained_root_bytes,
        },
        "compact_replay_roots": {
            "count": len(replay_paths),
            "max_count": max_compact_replay_roots,
            "max_size_bytes_per_root": max_compact_replay_root_bytes,
            "roots": replay_root_summaries,
        },
    }


def _candidate_run_files(root: Path) -> list[Path]:
    candidate_dir = root / CANDIDATE_RUN_FOLDER
    if not candidate_dir.exists():
        return []
    return sorted(path for path in candidate_dir.rglob("*.json") if path.is_file())


def _directory_size(root: Path) -> int:
    if not root.exists():
        return 0
    if root.is_file():
        return root.stat().st_size
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total
