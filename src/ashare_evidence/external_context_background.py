from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.external_context_ablation_readiness import audit_external_context_ablation_readiness
from ashare_evidence.external_context_acquisition import (
    audit_cninfo_personal_curation,
    execute_cninfo_personal_acquisition,
)

BACKGROUND_PIPELINE_SCHEMA_VERSION = "external_context_background_pipeline.v1"


def _write_mutable_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


def _event(name: str, **values: Any) -> None:
    print(
        json.dumps(
            {"event": name, "at": datetime.now(UTC).isoformat(), **values},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


def run_external_context_background_pipeline(
    *,
    plan_path: str | Path,
    artifact_root: str | Path,
    state_path: str | Path,
    curation_output_path: str | Path,
    readiness_output_path: str | Path,
    decision_cutoff: str,
    global_import_audit_path: str | Path | None = None,
    batch_size: int = 100,
    min_request_interval_seconds: float = 1.0,
    max_zero_progress_cycles: int = 12,
    zero_progress_backoff_seconds: float = 60.0,
    executor: Callable[..., dict[str, Any]] = execute_cninfo_personal_acquisition,
    curation_auditor: Callable[..., dict[str, Any]] = audit_cninfo_personal_curation,
    readiness_auditor: Callable[..., dict[str, Any]] = audit_external_context_ablation_readiness,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100")
    if max_zero_progress_cycles < 1 or max_zero_progress_cycles > 100:
        raise ValueError("max_zero_progress_cycles must be between 1 and 100")
    root = Path(artifact_root).expanduser().resolve()
    plan_file = Path(plan_path).expanduser().resolve()
    state_file = Path(state_path).expanduser().resolve()
    curation_file = Path(curation_output_path).expanduser().resolve()
    readiness_file = Path(readiness_output_path).expanduser().resolve()
    if not plan_file.is_file():
        raise ValueError(f"acquisition plan does not exist: {plan_file}")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    lock_file = state_file.with_suffix(f"{state_file.suffix}.lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            result = {
                "schema_version": BACKGROUND_PIPELINE_SCHEMA_VERSION,
                "status": "already_running",
                "state_path": str(state_file),
                "v3_signal_changed": False,
            }
            _event("external_context_background.already_running", state_path=str(state_file))
            return result

        started_at = datetime.now(UTC).isoformat()
        cycle_count = 0
        zero_progress_cycles = 0
        last_run: dict[str, Any] | None = None
        while True:
            cycle_count += 1
            _event("external_context_background.batch_started", cycle=cycle_count, batch_size=batch_size)
            last_run = executor(
                plan,
                artifact_root=root,
                max_tasks_this_run=batch_size,
                min_request_interval_seconds=min_request_interval_seconds,
            )
            processed = int(last_run.get("processed_count") or 0)
            failure_count = int(last_run.get("failure_count") or 0)
            remaining = int(last_run.get("remaining_task_count") or 0)
            zero_progress_cycles = zero_progress_cycles + 1 if processed == 0 and remaining else 0
            state = {
                "schema_version": BACKGROUND_PIPELINE_SCHEMA_VERSION,
                "status": "acquiring_cninfo" if remaining else "finalizing_offline_gates",
                "started_at": started_at,
                "updated_at": datetime.now(UTC).isoformat(),
                "pid": os.getpid(),
                "cycle_count": cycle_count,
                "zero_progress_cycles": zero_progress_cycles,
                "last_run": last_run,
                "plan_path": str(plan_file),
                "artifact_root": str(root),
                "v3_signal_changed": False,
            }
            _write_mutable_json(state_file, state)
            _event(
                "external_context_background.batch_finished",
                cycle=cycle_count,
                processed=processed,
                failures=failure_count,
                completed=last_run.get("completed_after_count"),
                remaining=remaining,
                root_bytes=last_run.get("artifact_root_bytes"),
            )
            if remaining == 0 and failure_count == 0:
                break
            if zero_progress_cycles >= max_zero_progress_cycles:
                state["status"] = "waiting_for_launchd_retry_after_zero_progress"
                state["updated_at"] = datetime.now(UTC).isoformat()
                _write_mutable_json(state_file, state)
                raise RuntimeError("CNINFO acquisition reached the bounded zero-progress restart threshold")
            if processed == 0:
                sleeper(zero_progress_backoff_seconds)

        curation = curation_auditor(plan, artifact_root=root)
        _write_mutable_json(curation_file, curation)
        readiness = readiness_auditor(
            artifact_root=root,
            curation_audit_path=curation_file,
            decision_cutoff=decision_cutoff,
            global_import_audit_path=global_import_audit_path,
        )
        _write_mutable_json(readiness_file, readiness)
        final_status = (
            "ready_for_external_weight_backtest"
            if readiness.get("full713_weight_backtest_allowed") is True
            else "complete_cninfo_blocked_external_weight_backtest"
        )
        final = {
            "schema_version": BACKGROUND_PIPELINE_SCHEMA_VERSION,
            "status": final_status,
            "started_at": started_at,
            "completed_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "cycle_count": cycle_count,
            "last_run": last_run,
            "curation_output_path": str(curation_file),
            "readiness_output_path": str(readiness_file),
            "full713_weight_backtest_allowed": readiness.get("full713_weight_backtest_allowed") is True,
            "blockers": readiness.get("blockers") or [],
            "v3_signal_changed": False,
        }
        _write_mutable_json(state_file, final)
        _event(
            "external_context_background.completed",
            status=final_status,
            full713_weight_backtest_allowed=final["full713_weight_backtest_allowed"],
            blockers=final["blockers"],
        )
        return final
