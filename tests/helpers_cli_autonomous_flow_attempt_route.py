from __future__ import annotations

from pathlib import Path
from typing import Any


class _FakeResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def _result(
    *,
    cycle_id: str,
    action: str = "retry_failed_step",
    route_type: str = "execution_output",
) -> _FakeResult:
    return _FakeResult({"cycle_id": cycle_id, "action": action, "route_type": route_type})


def _apply_result(*, cycle_id: str, status: str) -> _FakeResult:
    return _FakeResult(
        {
            "cycle_id": cycle_id,
            "route_type": "execution_output",
            "execution_mode": "attempt_route_apply",
            "attempt_context_status": "ready" if status != "blocked" else "blocked",
            "execution_status": status,
            "preflight_status": "ready" if status != "blocked" else "blocked",
            "applied_output": "execution" if status == "applied" else "none",
            "required_arguments": ["cycle_id", "issued_at", "runner_id"],
            "missing_arguments": [],
            "reason": "fake attempt route apply result",
        }
    )


def _files_under(root: Path) -> tuple[str, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
