from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class _FakeServiceResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _FakeTickResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.exit_code = int(payload["exit_code"])

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _FakePlanResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _FakeDryRunResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _FakeDiagnosticResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def _args(**overrides: Any) -> argparse.Namespace:
    payload = {
        "cycle_id": "cycle-1",
        "gate_id": None,
        "recovery_ticket_id": None,
        "projection_id": None,
        "finished_at": None,
        "diagnostic_id": None,
        "observed_at": None,
        "execution_id": None,
        "idempotency_key": None,
        "created_at": None,
        "attempt_id": None,
        "issued_at": None,
        "runner_id": None,
        "record_attempt_run": False,
        "attempt_run_id": None,
        "apply_closeout": False,
        "require_publish_verification": False,
        "artifact_root": None,
        "output": "status",
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def _expected_tick_args(**overrides: Any) -> dict[str, Any]:
    payload = {
        "cycle_id": "cycle-1",
        "gate_id": None,
        "recovery_ticket_id": None,
        "projection_id": None,
        "finished_at": None,
        "apply_closeout": False,
        "require_publish_verification": False,
        "root": None,
    }
    payload.update(overrides)
    return payload


def _assert_no_nested_flow_payload(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)

    assert '"plan_status":' not in serialized
    assert '"source_tick_status":' not in serialized
    assert '"status":' not in serialized
    assert '"error":' not in serialized
    assert "input_bundle" not in serialized
    assert "runner_result" not in serialized
    assert "release-manifest:" not in serialized
    assert "sha256:" not in serialized
    assert "Traceback" not in serialized


def _assert_rich_tick_args(calls: list[dict[str, Any]], *, cycle_id: str, root: Path) -> None:
    assert calls == [
        _expected_tick_args(
            cycle_id=cycle_id,
            gate_id="gate-1",
            recovery_ticket_id="ticket-1",
            projection_id="projection-1",
            finished_at="2026-05-20T10:00:00Z",
            apply_closeout=True,
            require_publish_verification=True,
            root=root,
        )
    ]


def _ok_service_result(cycle_id: str = "cycle-1") -> _FakeServiceResult:
    return _FakeServiceResult(
        {
            "cycle_id": cycle_id,
            "input_bundle": {"cycle": {"cycle_id": cycle_id}},
            "runner_result": {"status": "dry_run"},
            "release_manifest_ref": "release-manifest:phase5:20260520",
            "digest": "sha256:abc123",
            "missing_refs": [],
        }
    )


def _ok_tick_result(cycle_id: str = "cycle-1") -> _FakeTickResult:
    return _FakeTickResult(
        {
            "cycle_id": cycle_id,
            "tick_status": "ok",
            "exit_code": 0,
            "status": {
                "cycle_id": cycle_id,
                "cycle_status": "running",
                "decision_status": "completed",
                "next_action": "continue_tracking",
                "claim_ceiling": "paper_tracking_candidate",
                "decision_reason": "all planner inputs are fresh and unblocked",
                "missing_refs": [],
                "blocking_reasons": [],
                "source_refs": [cycle_id],
                "closeout_applied": False,
                "finished_at": None,
                "publish_verification_status": "not_required",
                "staleness_status": "fresh",
                "summary_status": "completed",
            },
            "error": None,
            "recommended_next_action": "continue_tracking",
            "summary_status": "completed",
        }
    )


def _error_tick_result(cycle_id: str = "cycle-1") -> _FakeTickResult:
    return _FakeTickResult(
        {
            "cycle_id": cycle_id,
            "tick_status": "error",
            "exit_code": 1,
            "status": None,
            "error": {
                "error_type": "ValueError",
                "message": "phase5 local cycle service apply_closeout requires finished_at",
                "failure_class": "contract-violation",
                "recommended_recovery_action": "block_cycle",
            },
            "recommended_next_action": "blocked",
            "summary_status": "blocked",
        }
    )


def _plan_result(
    *,
    cycle_id: str = "cycle-1",
    source_tick_status: str = "ok",
    action: str = "continue_tracking",
) -> _FakePlanResult:
    return _FakePlanResult(
        {
            "cycle_id": cycle_id,
            "plan_status": "ready",
            "action": action,
            "reason": "planner selected follow-up action",
            "source_tick_status": source_tick_status,
            "summary_status": "completed" if source_tick_status == "ok" else "degraded",
            "claim_ceiling": "paper_tracking_candidate" if source_tick_status == "ok" else None,
            "blocking_reasons": [],
        }
    )


def _dry_run_result(
    *,
    cycle_id: str = "cycle-1",
    planned_action: str = "continue_tracking",
    execution_status: str = "planned",
    planned_effects: list[str] | None = None,
) -> _FakeDryRunResult:
    return _FakeDryRunResult(
        {
            "cycle_id": cycle_id,
            "execution_mode": "dry_run",
            "execution_status": execution_status,
            "planned_action": planned_action,
            "would_execute": False,
            "planned_effects": planned_effects or ["keep_cycle_open_for_next_tick"],
            "reason": "scheduler dry-run selected follow-up action",
            "blocking_reasons": [],
        }
    )


def _diagnostic_result(
    *,
    cycle_id: str = "cycle-1",
    diagnostic_id: str = "diagnostic-1",
    action: str = "continue_tracking",
    severity: str = "info",
    cycle_event_recorded: bool = True,
    blocking_reasons: list[str] | None = None,
) -> _FakeDiagnosticResult:
    return _FakeDiagnosticResult(
        {
            "cycle_id": cycle_id,
            "diagnostic_id": diagnostic_id,
            "execution_mode": "diagnostic_record",
            "execution_status": "recorded",
            "action": action,
            "severity": severity,
            "diagnostic_recorded": True,
            "cycle_event_recorded": cycle_event_recorded,
            "reason": "scheduler diagnostic recorded follow-up action",
            "blocking_reasons": blocking_reasons or [],
        }
    )
