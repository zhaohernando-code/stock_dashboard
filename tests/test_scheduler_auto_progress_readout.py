from __future__ import annotations

from pathlib import Path

from ashare_evidence.scheduler_auto_progress_artifact_store import (
    write_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact
from ashare_evidence.scheduler_auto_progress_readout import (
    build_phase5_scheduler_auto_progress_run_readout,
    read_phase5_scheduler_auto_progress_run_readout,
)


def test_auto_progress_readout_summarizes_latest_run(tmp_path: Path) -> None:
    write_phase5_scheduler_auto_progress_run_artifact(
        _run(
            auto_progress_run_id="auto-progress-run-old",
            issued_at="2026-05-21T10:00:00Z",
            apply_status="blocked",
            applied_output="none",
            blocking_reasons=["missing required auto-progress argument: created_at"],
        ),
        root=tmp_path,
    )
    write_phase5_scheduler_auto_progress_run_artifact(
        _run(
            auto_progress_run_id="auto-progress-run-new",
            issued_at="2026-05-21T10:10:00Z",
            phase="recovery_followup_apply",
            apply_status="applied",
            applied_output="followup_cycle",
            result_refs=["phase5_cycle_ledger:followup-cycle-cn1"],
        ),
        root=tmp_path,
    )

    readout = read_phase5_scheduler_auto_progress_run_readout(
        cycle_id="cycle-cn1",
        runner_id="runner-cn1",
        root=tmp_path,
    )

    assert readout.total_runs == 2
    assert readout.latest_auto_progress_run_id == "auto-progress-run-new"
    assert readout.latest_phase == "recovery_followup_apply"
    assert readout.latest_apply_status == "applied"
    assert readout.latest_applied_output == "followup_cycle"
    assert readout.applied_count == 1
    assert readout.blocked_count == 1
    assert readout.latest_blocked_run_id == "auto-progress-run-old"
    assert readout.latest_applied_run_id == "auto-progress-run-new"
    assert readout.result_refs == [
        "phase5_cycle_ledger:followup-cycle-cn1",
        "phase5_scheduler_attempt_intervention_run:intervention-run-cn1",
    ]
    assert readout.evidence_refs == ["phase5_scheduler_diagnostic:diagnostic-cn1"]
    assert readout.auto_progress_run_refs == ["auto-progress-run-new", "auto-progress-run-old"]
    assert readout.readout_status == "current"


def test_auto_progress_readout_handles_empty_store_without_writing(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"

    readout = read_phase5_scheduler_auto_progress_run_readout(
        cycle_id="cycle-empty",
        runner_id="runner-empty",
        root=artifact_root,
    )

    assert readout.total_runs == 0
    assert readout.readout_status == "degraded"
    assert readout.auto_progress_run_refs == []
    assert not artifact_root.exists()


def test_auto_progress_readout_marks_latest_blocked() -> None:
    readout = build_phase5_scheduler_auto_progress_run_readout(
        [
            _run(
                auto_progress_run_id="auto-progress-run-blocked",
                apply_status="blocked",
                applied_output="none",
            )
        ]
    )

    assert readout.readout_status == "blocked"
    assert readout.latest_blocked_run_id == "auto-progress-run-blocked"


def _run(**overrides) -> Phase5SchedulerAutoProgressRunArtifact:
    payload = {
        "auto_progress_run_id": "auto-progress-run-cn1",
        "cycle_id": "cycle-cn1",
        "runner_id": "runner-cn1",
        "issued_at": "2026-05-21T10:00:00Z",
        "plan_status": "ready",
        "phase": "intervention_apply",
        "apply_status": "applied",
        "applied_output": "intervention_run",
        "recommended_output": "attempt-run-intervention-apply",
        "recommended_flags": ["--record-intervention-run"],
        "required_arguments": ["issued_at", "runner_id"],
        "missing_arguments": [],
        "blocking_reasons": [],
        "evidence_refs": ["phase5_scheduler_diagnostic:diagnostic-cn1"],
        "result_refs": ["phase5_scheduler_attempt_intervention_run:intervention-run-cn1"],
        "notes": "auto-progress recorded intervention run",
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAutoProgressRunArtifact(**payload)
