from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.scheduler_auto_progress_artifact_store import (
    write_phase5_scheduler_auto_progress_run_artifact,
)
from ashare_evidence.scheduler_auto_progress_artifacts import Phase5SchedulerAutoProgressRunArtifact
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


def test_auto_progress_readout_output_reads_recorded_runs(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)
    write_phase5_scheduler_auto_progress_run_artifact(_run(), root=artifact_root)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-cn-cli",
            "--runner-id",
            "runner-cn-cli",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-auto-progress-readout",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["total_runs"] == 1
    assert payload["latest_auto_progress_run_id"] == "auto-progress-run-cn-cli"
    assert payload["latest_phase"] == "recovery_followup_apply"
    assert payload["result_refs"] == ["phase5_cycle_ledger:followup-cycle-cn-cli"]


def test_auto_progress_readout_output_handles_empty_store(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact_root = tmp_path / "artifacts"
    _guard_init_database(monkeypatch)
    _install_scheduler_handler_guards(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-empty",
            "--runner-id",
            "runner-empty",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-run-auto-progress-readout",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["total_runs"] == 0
    assert payload["readout_status"] == "degraded"
    assert not artifact_root.exists()


def _install_scheduler_handler_guards(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-run-auto-progress-readout must not run scheduler handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail)
    monkeypatch.setattr(cli_autonomous_flow, "build_attempt_context_and_apply_phase5_scheduler_action_route", fail)


def _run(**overrides) -> Phase5SchedulerAutoProgressRunArtifact:
    payload = {
        "auto_progress_run_id": "auto-progress-run-cn-cli",
        "cycle_id": "cycle-cn-cli",
        "runner_id": "runner-cn-cli",
        "issued_at": "2026-05-21T10:10:00Z",
        "plan_status": "ready",
        "phase": "recovery_followup_apply",
        "apply_status": "applied",
        "applied_output": "followup_cycle",
        "recommended_output": "attempt-run-recovery-followup-apply",
        "recommended_flags": [],
        "required_arguments": ["created_at"],
        "missing_arguments": [],
        "blocking_reasons": [],
        "evidence_refs": ["phase5_scheduler_diagnostic:diagnostic-cn-cli"],
        "result_refs": ["phase5_cycle_ledger:followup-cycle-cn-cli"],
        "notes": "recovery follow-up cycle started from intent",
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAutoProgressRunArtifact(**payload)
