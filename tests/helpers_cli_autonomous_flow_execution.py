from __future__ import annotations

from typing import Any


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
