from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ashare_evidence.cli import NO_DB_COMMANDS, build_parser
from ashare_evidence.external_context_background import run_external_context_background_pipeline


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _plan(path: Path) -> Path:
    payload = {
        "schema_version": "cninfo_personal_historical_acquisition_plan.v1",
        "plan_id": "plan-test",
        "task_count": 1,
        "tasks": [{"task_id": "task-1", "symbol": "600000.SH"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_background_pipeline_runs_to_offline_gate_and_records_blockers(tmp_path: Path) -> None:
    executor_calls = 0

    def executor(*args, **kwargs):
        nonlocal executor_calls
        executor_calls += 1
        return {
            "processed_count": 1,
            "failure_count": 0,
            "completed_after_count": 1,
            "remaining_task_count": 0,
            "artifact_root_bytes": 100,
        }

    exclusions: list[dict[str, str]] = []

    def curation(*args, **kwargs):
        return {
            "schema_version": "cninfo_personal_curation_audit.v1",
            "excluded_event_versions": exclusions,
            "excluded_event_versions_sha256": _digest(exclusions),
        }

    def readiness(**kwargs):
        assert Path(kwargs["curation_audit_path"]).is_file()
        return {
            "full713_weight_backtest_allowed": False,
            "blockers": ["qualified_global_market_full_window_export_missing"],
        }

    state_path = tmp_path / "operations" / "state.json"
    result = run_external_context_background_pipeline(
        plan_path=_plan(tmp_path / "plan.json"),
        artifact_root=tmp_path / "artifacts",
        state_path=state_path,
        curation_output_path=tmp_path / "curation.json",
        readiness_output_path=tmp_path / "readiness.json",
        decision_cutoff="2026-05-27T23:59:59+08:00",
        executor=executor,
        curation_auditor=curation,
        readiness_auditor=readiness,
    )

    assert executor_calls == 1
    assert result["status"] == "complete_cninfo_blocked_external_weight_backtest"
    assert result["v3_signal_changed"] is False
    assert json.loads(state_path.read_text())["status"] == result["status"]


def test_cli_registers_background_pipeline_as_no_database_command() -> None:
    args = build_parser().parse_args(
        [
            "research-external-context-background-run",
            "--plan-json",
            "/tmp/plan.json",
            "--artifact-root",
            "/tmp/artifacts",
            "--state-json",
            "/tmp/state.json",
            "--curation-output-json",
            "/tmp/curation.json",
            "--readiness-output-json",
            "/tmp/readiness.json",
            "--decision-cutoff",
            "2026-05-27T23:59:59+08:00",
        ]
    )

    assert args.command == "research-external-context-background-run"
    assert args.command in NO_DB_COMMANDS
