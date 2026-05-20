from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_action_router import (
    Phase5SchedulerActionRouteResult,
    Phase5SchedulerActionRouteType,
)

Phase5SchedulerActionRouteArgumentBindingStatus = Literal["ready", "blocked"]


class Phase5SchedulerActionRouteArgumentBindingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    status: Phase5SchedulerActionRouteArgumentBindingStatus
    required_arguments: tuple[str, ...]
    provided_arguments: dict[str, str] = Field(default_factory=dict)
    missing_arguments: tuple[str, ...]
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "ready"


def bind_phase5_scheduler_action_route_arguments(
    route: Phase5SchedulerActionRouteResult,
    *,
    attempt_id: str,
    issued_at: str | None = None,
) -> Phase5SchedulerActionRouteArgumentBindingResult:
    if route.route_type in {"wait_for_next_tick", "terminal"}:
        return _result(
            route,
            status="ready",
            provided_arguments={},
            missing_arguments=(),
            reason=f"{route.route_type} route does not require generated arguments",
        )

    if not issued_at:
        return _result(
            route,
            status="blocked",
            provided_arguments={},
            missing_arguments=route.required_arguments,
            reason="issued_at is required to bind scheduler action route arguments",
        )

    if route.route_type == "diagnostic_output":
        diagnostic_id = _stable_id("diagnostic", route=route, attempt_id=attempt_id)
        return _result(
            route,
            status="ready",
            provided_arguments={"diagnostic_id": diagnostic_id, "observed_at": issued_at},
            missing_arguments=(),
            reason="diagnostic action route arguments bound from scheduler attempt",
        )

    execution_id = _stable_id("execution", route=route, attempt_id=attempt_id)
    return _result(
        route,
        status="ready",
        provided_arguments={
            "execution_id": execution_id,
            "idempotency_key": f"idempotency:{execution_id}",
            "created_at": issued_at,
        },
        missing_arguments=(),
        reason="execution action route arguments bound from scheduler attempt",
    )


def _result(
    route: Phase5SchedulerActionRouteResult,
    *,
    status: Phase5SchedulerActionRouteArgumentBindingStatus,
    provided_arguments: dict[str, str],
    missing_arguments: tuple[str, ...],
    reason: str,
) -> Phase5SchedulerActionRouteArgumentBindingResult:
    return Phase5SchedulerActionRouteArgumentBindingResult(
        cycle_id=route.cycle_id,
        route_type=route.route_type,
        status=status,
        required_arguments=route.required_arguments,
        provided_arguments=provided_arguments,
        missing_arguments=missing_arguments,
        reason=reason,
    )


def _stable_id(prefix: str, *, route: Phase5SchedulerActionRouteResult, attempt_id: str) -> str:
    raw = f"{prefix}|{route.cycle_id}|{route.action}|{attempt_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return "-".join(
        (
            prefix,
            _slug(route.cycle_id),
            _slug(route.action),
            _slug(attempt_id),
            digest,
        )
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "x"
