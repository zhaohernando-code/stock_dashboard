from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ashare_evidence.autonomous_flow_resolver import Phase5RunnerInputResolutionError
from ashare_evidence.autonomous_flow_service import run_phase5_local_cycle_service
from ashare_evidence.autonomous_flow_status import (
    Phase5LocalCycleStatusProjection,
    Phase5NextAction,
    Phase5SummaryStatus,
    project_phase5_local_cycle_status,
)

Phase5LocalCycleTickStatus = Literal["ok", "error"]
Phase5LocalCycleTickFailureClass = Literal[
    "contract-violation",
    "artifact-missing",
    "unexpected-error",
]
Phase5LocalCycleTickRecoveryAction = Literal[
    "block_cycle",
    "open_recovery_ticket",
    "retry_with_backoff",
]


class Phase5LocalCycleTickError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: str
    message: str
    failure_class: Phase5LocalCycleTickFailureClass
    recommended_recovery_action: Phase5LocalCycleTickRecoveryAction


class Phase5LocalCycleTickResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    tick_status: Phase5LocalCycleTickStatus
    exit_code: int
    status: Phase5LocalCycleStatusProjection | None = None
    error: Phase5LocalCycleTickError | None = None
    recommended_next_action: Phase5NextAction
    summary_status: Phase5SummaryStatus


def run_phase5_local_cycle_tick(
    *,
    cycle_id: str,
    gate_id: str | None = None,
    recovery_ticket_id: str | None = None,
    projection_id: str | None = None,
    finished_at: str | None = None,
    apply_closeout: bool = False,
    require_publish_verification: bool = False,
    root: Path | None = None,
) -> Phase5LocalCycleTickResult:
    try:
        service_result = run_phase5_local_cycle_service(
            cycle_id=cycle_id,
            gate_id=gate_id,
            recovery_ticket_id=recovery_ticket_id,
            projection_id=projection_id,
            finished_at=finished_at,
            apply_closeout=apply_closeout,
            require_publish_verification=require_publish_verification,
            root=root,
        )
        status = project_phase5_local_cycle_status(service_result)
    except Phase5RunnerInputResolutionError as exc:
        return _error_result(
            cycle_id=cycle_id,
            exc=exc,
            failure_class=exc.failure_class,
            recommended_recovery_action=exc.recommended_recovery_action,
            recommended_next_action=exc.recommended_next_action,
            summary_status=exc.summary_status,
        )
    except FileNotFoundError as exc:
        return _error_result(
            cycle_id=cycle_id,
            exc=exc,
            failure_class="artifact-missing",
            recommended_recovery_action="open_recovery_ticket",
            recommended_next_action="retry_failed_step",
            summary_status="degraded",
        )
    except ValueError as exc:
        return _error_result(
            cycle_id=cycle_id,
            exc=exc,
            failure_class="contract-violation",
            recommended_recovery_action="block_cycle",
            recommended_next_action="blocked",
            summary_status="blocked",
        )
    except Exception as exc:
        return _error_result(
            cycle_id=cycle_id,
            exc=exc,
            failure_class="unexpected-error",
            recommended_recovery_action="retry_with_backoff",
            recommended_next_action="retry_failed_step",
            summary_status="degraded",
        )

    return Phase5LocalCycleTickResult(
        cycle_id=status.cycle_id,
        tick_status="ok",
        exit_code=0,
        status=status,
        error=None,
        recommended_next_action=status.next_action,
        summary_status=status.summary_status,
    )


def _error_result(
    *,
    cycle_id: str,
    exc: Exception,
    failure_class: Phase5LocalCycleTickFailureClass,
    recommended_recovery_action: Phase5LocalCycleTickRecoveryAction,
    recommended_next_action: Phase5NextAction,
    summary_status: Phase5SummaryStatus,
) -> Phase5LocalCycleTickResult:
    return Phase5LocalCycleTickResult(
        cycle_id=cycle_id,
        tick_status="error",
        exit_code=1,
        status=None,
        error=Phase5LocalCycleTickError(
            error_type=type(exc).__name__,
            message=_safe_error_message(exc),
            failure_class=failure_class,
            recommended_recovery_action=recommended_recovery_action,
        ),
        recommended_next_action=recommended_next_action,
        summary_status=summary_status,
    )


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"sha256:[A-Za-z0-9._:-]+", "[redacted-digest]", message)
    message = re.sub(r"release-manifest:[^\s,'\"}]+", "[redacted-release-manifest-ref]", message)
    if len(message) > 500:
        return f"{message[:497]}..."
    return message
