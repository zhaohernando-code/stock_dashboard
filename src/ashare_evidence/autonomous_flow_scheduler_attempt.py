from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Phase5SchedulerAttemptContextStatus = Literal["ready", "blocked"]

_REQUIRED_ARGUMENTS = ("cycle_id", "issued_at", "runner_id")


class Phase5SchedulerAttemptContextResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Phase5SchedulerAttemptContextStatus
    attempt_id: str | None
    cycle_id: str | None
    issued_at: str | None
    runner_id: str | None
    required_arguments: tuple[str, ...] = Field(default_factory=lambda: _REQUIRED_ARGUMENTS)
    missing_arguments: tuple[str, ...]
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "ready"


def build_phase5_scheduler_attempt_context(
    *,
    cycle_id: str | None = None,
    issued_at: str | None = None,
    runner_id: str | None = None,
) -> Phase5SchedulerAttemptContextResult:
    missing_arguments = _missing_arguments(
        cycle_id=cycle_id,
        issued_at=issued_at,
        runner_id=runner_id,
    )
    if missing_arguments:
        return Phase5SchedulerAttemptContextResult(
            status="blocked",
            attempt_id=None,
            cycle_id=_present_value(cycle_id),
            issued_at=_present_value(issued_at),
            runner_id=_present_value(runner_id),
            missing_arguments=missing_arguments,
            reason="missing required scheduler attempt context inputs: " + ", ".join(missing_arguments),
        )

    assert cycle_id is not None
    assert issued_at is not None
    assert runner_id is not None
    attempt_id = _attempt_id(cycle_id=cycle_id, issued_at=issued_at, runner_id=runner_id)

    return Phase5SchedulerAttemptContextResult(
        status="ready",
        attempt_id=attempt_id,
        cycle_id=cycle_id,
        issued_at=issued_at,
        runner_id=runner_id,
        missing_arguments=(),
        reason="scheduler attempt context built from explicit inputs",
    )


def _missing_arguments(
    *,
    cycle_id: str | None,
    issued_at: str | None,
    runner_id: str | None,
) -> tuple[str, ...]:
    values = {
        "cycle_id": cycle_id,
        "issued_at": issued_at,
        "runner_id": runner_id,
    }
    return tuple(name for name in _REQUIRED_ARGUMENTS if not _present_value(values[name]))


def _present_value(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "":
        return None
    return value


def _attempt_id(*, cycle_id: str, issued_at: str, runner_id: str) -> str:
    raw = f"phase5_scheduler_attempt|{cycle_id}|{runner_id}|{issued_at}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(
        (
            "attempt",
            _slug(cycle_id),
            _slug(runner_id),
            _slug(issued_at),
            digest,
        )
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"
