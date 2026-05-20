from __future__ import annotations

import json
from typing import Any

import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
from ashare_evidence.autonomous_flow import Phase5SchedulerExecutionIdempotencyConflictError
from tests import helpers_cli_autonomous_flow as flow_helpers


class _FakeExecutionResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def _execution_result(
    *,
    cycle_id: str = "cycle-1",
    execution_id: str = "execution-1",
    idempotency_key: str = "idempotency:execution-1",
    action: str = "continue_tracking",
    execution_status: str = "planned",
    cycle_event_recorded: bool = True,
    blocking_reasons: list[str] | None = None,
    diagnostic_refs: list[str] | None = None,
) -> _FakeExecutionResult:
    return _FakeExecutionResult(
        {
            "cycle_id": cycle_id,
            "execution_id": execution_id,
            "idempotency_key": idempotency_key,
            "execution_mode": "ledger_record",
            "execution_status": execution_status,
            "action": action,
            "would_execute": False,
            "ledger_recorded": True,
            "cycle_event_recorded": cycle_event_recorded,
            "reason": "scheduler execution ledger recorded follow-up action",
            "blocking_reasons": blocking_reasons or [],
            "diagnostic_refs": diagnostic_refs or [],
        }
    )


def _assert_execution_conflict_cli_returns_typed_json(monkeypatch: Any, capsys: Any) -> None:
    def fake_tick(**kwargs: Any) -> flow_helpers._FakeTickResult:
        return flow_helpers._ok_tick_result(kwargs["cycle_id"])

    def fake_plan(tick_result: flow_helpers._FakeTickResult) -> flow_helpers._FakePlanResult:
        return flow_helpers._plan_result(cycle_id=tick_result.payload["cycle_id"], action="retry_failed_step")

    def fake_record(plan: flow_helpers._FakePlanResult, **kwargs: Any) -> _FakeExecutionResult:
        raise Phase5SchedulerExecutionIdempotencyConflictError(
            idempotency_key=kwargs["idempotency_key"],
            existing_execution_id="execution-existing",
            requested_execution_id=kwargs["execution_id"],
        )

    def fail_unexpected(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("execution conflict output must not call non-execution handlers")

    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fake_tick)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fake_plan)
    monkeypatch.setattr(cli_autonomous_flow, "record_phase5_scheduler_plan_execution", fake_record)
    for name in (
        "run_phase5_local_cycle_service",
        "dry_run_phase5_scheduler_plan",
        "record_phase5_scheduler_plan_diagnostic",
    ):
        monkeypatch.setattr(cli_autonomous_flow, name, fail_unexpected)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        flow_helpers._args(
            output="execution",
            execution_id="execution-requested",
            idempotency_key="idempotency:conflict",
            created_at="2026-05-20T10:01:00Z",
        )
    )

    assert exit_code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["command"] == "phase5-local-cycle-step"
    assert payload["error_type"] == "Phase5SchedulerExecutionIdempotencyConflictError"
    assert payload["message"] == "phase5 scheduler execution idempotency conflict"
    assert payload["idempotency_key"] == "idempotency:conflict"
    assert payload["existing_execution_id"] == "execution-existing"
    assert payload["requested_execution_id"] == "execution-requested"
    assert payload["recommended_next_action"] == "reuse_existing_execution_id_or_retry_with_new_idempotency_key"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert all(
        token not in serialized
        for token in ("plan_status", "source_tick_status", "input_bundle", "runner_result")
    )
