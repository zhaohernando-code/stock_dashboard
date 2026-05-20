from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path

import ashare_evidence.autonomous_flow_scheduler_action_executor as action_executor
from ashare_evidence.autonomous_flow_scheduler_action_contract import Phase5SchedulerActionPreflightResult
from ashare_evidence.autonomous_flow_scheduler_action_executor import execute_phase5_scheduler_noop_action
from tests.helpers_autonomous_flow_scheduler import _plan


def test_noop_action_executor_completes_continue_tracking_without_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    before_files = _files_under(tmp_path)

    result = execute_phase5_scheduler_noop_action(_plan(action="continue_tracking"))

    assert result.execution_mode == "contract_action"
    assert result.execution_status == "completed"
    assert result.action == "continue_tracking"
    assert result.preflight_status == "ready"
    assert result.recommended_next_action == "continue_scheduler_tracking"
    assert result.performed_effects == ("keep_cycle_open_for_next_tick",)
    assert result.skipped_reason is None
    assert result.durable_outputs == ()
    assert result.may_close_cycle is False
    assert _files_under(tmp_path) == before_files


def test_noop_action_executor_completes_none_without_writes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before_files = _files_under(tmp_path)

    result = execute_phase5_scheduler_noop_action(_plan(action="none", reason="no follow-up action required"))

    assert result.execution_status == "completed"
    assert result.action == "none"
    assert result.preflight_status == "ready"
    assert result.recommended_next_action == "finish_without_followup"
    assert result.performed_effects == ("no_op",)
    assert result.durable_outputs == ()
    assert result.may_close_cycle is False
    assert result.reason == "no follow-up action required"
    assert _files_under(tmp_path) == before_files


def test_noop_action_executor_calls_preflight_with_plan_inputs(monkeypatch) -> None:
    calls: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    def fake_preflight(action, *, provided_input_names, requested_side_effects=()):
        calls.append((action, tuple(provided_input_names), tuple(requested_side_effects)))
        return Phase5SchedulerActionPreflightResult(
            action=action,
            status="ready",
            reason="stubbed ready preflight",
        )

    monkeypatch.setattr(action_executor, "preflight_phase5_scheduler_action", fake_preflight)

    result = execute_phase5_scheduler_noop_action(_plan(action="continue_tracking"))

    assert result.execution_status == "completed"
    assert calls == [
        (
            "continue_tracking",
            (
                "cycle_id",
                "scheduler_followup_plan",
                "plan_status",
                "action",
                "reason",
                "source_tick_status",
                "summary_status",
                "claim_ceiling",
                "blocking_reasons",
            ),
            (),
        )
    ]


def test_noop_action_executor_blocks_preflight_missing_input() -> None:
    result = execute_phase5_scheduler_noop_action(_plan(action="open_recovery_ticket"))

    assert result.execution_status == "blocked"
    assert result.action == "open_recovery_ticket"
    assert result.preflight_status == "blocked"
    assert result.recommended_next_action == "record_scheduler_diagnostic"
    assert result.performed_effects == ()
    assert result.skipped_reason == "scheduler action preflight blocked by missing inputs"
    assert result.reason == "scheduler action preflight blocked by missing inputs"


def test_noop_action_executor_blocks_non_noop_action_even_when_preflight_ready(monkeypatch) -> None:
    def fake_preflight(action, *, provided_input_names, requested_side_effects=()):
        return Phase5SchedulerActionPreflightResult(
            action=action,
            status="ready",
            durable_outputs=("frontend_projection_manifest",),
            reason="stubbed ready preflight",
        )

    monkeypatch.setattr(action_executor, "preflight_phase5_scheduler_action", fake_preflight)

    result = execute_phase5_scheduler_noop_action(_plan(action="rebuild_projection"))

    assert result.execution_status == "blocked"
    assert result.action == "rebuild_projection"
    assert result.preflight_status == "ready"
    assert result.recommended_next_action == "record_scheduler_execution_intent"
    assert result.performed_effects == ()
    assert result.skipped_reason == "scheduler action executor only supports no-op actions in this trial"
    assert result.durable_outputs == ("frontend_projection_manifest",)


def test_noop_action_executor_does_not_modify_input_object() -> None:
    plan = _plan(action="continue_tracking", blocking_reasons=["existing blocker"])
    before = deepcopy(plan.model_dump(mode="json"))

    execute_phase5_scheduler_noop_action(plan)

    assert plan.model_dump(mode="json") == before


def test_action_executor_module_has_no_runtime_io_clock_network_or_db_dependencies() -> None:
    source = inspect.getsource(action_executor)

    for token in (
        "datetime",
        "time.",
        "Path(",
        "open(",
        "mkdir(",
        "read_text(",
        "write_text(",
        "requests",
        "httpx",
        "sqlite",
        "database",
    ):
        assert token not in source


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
