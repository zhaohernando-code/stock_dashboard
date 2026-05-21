from __future__ import annotations

from pathlib import Path

from ashare_evidence.research_artifact_store import read_phase5_scheduler_diagnostic_artifact
from ashare_evidence.scheduler_attempt_run_followup_policy import decide_phase5_scheduler_attempt_run_followup
from ashare_evidence.scheduler_attempt_run_intervention_executor import (
    apply_phase5_scheduler_attempt_run_intervention,
)
from ashare_evidence.scheduler_attempt_run_intervention_plan import (
    plan_phase5_scheduler_attempt_run_intervention,
)
from ashare_evidence.scheduler_attempt_run_readout import Phase5SchedulerAttemptRunReadout
from tests.helpers_autonomous_flow_scheduler_execution import _start_cycle


def test_intervention_apply_records_diagnostic_for_route_apply_plan(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-cc1")
    plan = _plan_for_readout(
        _readout(
            latest_run_id="run-blocked",
            latest_apply_status="blocked",
            latest_attempt_status="blocked",
            blocked_count=1,
            staleness_status="blocked",
        )
    )

    result = apply_phase5_scheduler_attempt_run_intervention(plan, root=root)
    diagnostic = read_phase5_scheduler_diagnostic_artifact(result.diagnostic_id or "", root=root)

    assert result.execution_status == "applied"
    assert result.applied_output == "diagnostic"
    assert result.diagnostic_id is not None
    assert result.observed_at == "2026-05-21T12:00:00Z"
    assert result.cycle_event_recorded is True
    assert diagnostic.scheduler_action == "open_recovery_ticket"
    assert diagnostic.recommended_recovery_action == "open_recovery_ticket"
    assert diagnostic.evidence_refs == ["run-blocked"]


def test_intervention_apply_skips_observe_only_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    plan = _plan_for_readout(_readout(total_runs=0))

    result = apply_phase5_scheduler_attempt_run_intervention(plan, root=root)

    assert result.execution_status == "skipped"
    assert result.applied_output == "none"
    assert not root.exists()


def test_intervention_apply_blocks_missing_observed_at_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    plan = _plan_for_readout(
        _readout(
            latest_run_id="run-blocked",
            latest_apply_status="blocked",
            latest_attempt_status="blocked",
            latest_issued_at=None,
            blocked_count=1,
            staleness_status="blocked",
        )
    )

    result = apply_phase5_scheduler_attempt_run_intervention(plan, root=root)

    assert result.execution_status == "blocked"
    assert result.applied_output == "none"
    assert result.missing_arguments == ("observed_at",)
    assert not root.exists()


def test_intervention_apply_allows_explicit_observed_at_override(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    _start_cycle(root, "cycle-cc1")
    plan = _plan_for_readout(
        _readout(
            latest_run_id="run-blocked",
            latest_apply_status="blocked",
            latest_attempt_status="blocked",
            latest_issued_at=None,
            blocked_count=1,
            staleness_status="blocked",
        )
    )

    result = apply_phase5_scheduler_attempt_run_intervention(plan, observed_at="manual-time", root=root)

    assert result.execution_status == "applied"
    assert result.observed_at == "manual-time"


def _plan_for_readout(readout: Phase5SchedulerAttemptRunReadout):
    decision = decide_phase5_scheduler_attempt_run_followup(readout)
    return plan_phase5_scheduler_attempt_run_intervention(readout, decision)


def _readout(**overrides) -> Phase5SchedulerAttemptRunReadout:
    payload = {
        "cycle_id": "cycle-cc1",
        "runner_id": "runner-cc1",
        "total_runs": 1,
        "latest_run_id": "run-cc1",
        "latest_apply_status": "applied",
        "latest_attempt_status": "ready",
        "latest_issued_at": "2026-05-21T12:00:00Z",
        "applied_count": 1,
        "blocked_count": 0,
        "skipped_count": 0,
        "latest_blocked_run_id": None,
        "latest_applied_run_id": "run-cc1",
        "staleness_status": "current",
        "run_refs": ["run-cc1"],
    }
    if overrides.get("total_runs") == 0:
        payload.update(
            {
                "cycle_id": None,
                "runner_id": None,
                "latest_run_id": None,
                "latest_apply_status": None,
                "latest_attempt_status": None,
                "latest_issued_at": None,
                "applied_count": 0,
                "latest_applied_run_id": None,
                "staleness_status": "degraded",
                "run_refs": [],
            }
        )
    payload.update(overrides)
    return Phase5SchedulerAttemptRunReadout(**payload)
