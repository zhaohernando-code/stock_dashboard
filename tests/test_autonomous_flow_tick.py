from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.autonomous_flow_tick as tick_module
from ashare_evidence.autonomous_flow_resolver import Phase5RunnerInputResolutionError
from ashare_evidence.autonomous_flow_status import Phase5LocalCycleStatusProjection
from ashare_evidence.autonomous_flow_tick import run_phase5_local_cycle_tick


def _status_projection(
    *,
    cycle_id: str = "cycle-20260520-001",
    next_action: str = "continue_tracking",
    summary_status: str = "completed",
) -> Phase5LocalCycleStatusProjection:
    return Phase5LocalCycleStatusProjection(
        cycle_id=cycle_id,
        cycle_status="running",
        decision_status="completed",
        next_action=next_action,
        claim_ceiling="paper_tracking_candidate",
        decision_reason="all planner inputs are fresh and unblocked",
        missing_refs=[],
        blocking_reasons=[],
        source_refs=[cycle_id],
        closeout_applied=False,
        finished_at=None,
        publish_verification_status="not_required",
        staleness_status="fresh",
        summary_status=summary_status,
    )


def test_success_calls_service_and_projection_and_returns_small_status_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service_result = object()
    calls: list[dict[str, Any]] = []

    def fake_service(**kwargs: Any) -> object:
        calls.append(kwargs)
        return service_result

    def fake_projection(result: object) -> Phase5LocalCycleStatusProjection:
        assert result is service_result
        return _status_projection(cycle_id="cycle-ok", next_action="rebuild_projection", summary_status="degraded")

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)
    monkeypatch.setattr(tick_module, "project_phase5_local_cycle_status", fake_projection)

    result = run_phase5_local_cycle_tick(
        cycle_id="cycle-ok",
        gate_id="gate-1",
        recovery_ticket_id="ticket-1",
        projection_id="projection-1",
        finished_at="2026-05-20T10:00:00Z",
        apply_closeout=True,
        require_publish_verification=True,
        root=tmp_path,
    )

    assert calls == [
        {
            "cycle_id": "cycle-ok",
            "gate_id": "gate-1",
            "recovery_ticket_id": "ticket-1",
            "projection_id": "projection-1",
            "finished_at": "2026-05-20T10:00:00Z",
            "apply_closeout": True,
            "require_publish_verification": True,
            "root": tmp_path,
        }
    ]
    assert result.tick_status == "ok"
    assert result.exit_code == 0
    assert result.error is None
    assert result.status is not None
    assert result.recommended_next_action == "rebuild_projection"
    assert result.summary_status == "degraded"

    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "input_bundle" not in rendered
    assert "runner_result" not in rendered
    assert "release-manifest" not in rendered
    assert "sha256:" not in rendered
    assert "digest" not in rendered


def test_value_error_maps_to_blocked_contract_violation_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**_kwargs: Any) -> object:
        raise ValueError("invalid contract release-manifest:phase5:20260520 sha256:abc123")

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-contract")

    assert result.tick_status == "error"
    assert result.exit_code == 1
    assert result.status is None
    assert result.summary_status == "blocked"
    assert result.recommended_next_action == "blocked"
    assert result.error is not None
    assert result.error.error_type == "ValueError"
    assert result.error.failure_class == "contract-violation"
    assert result.error.recommended_recovery_action == "block_cycle"
    assert "release-manifest:" not in result.error.message
    assert "sha256:" not in result.error.message


def test_structured_missing_cycle_error_maps_to_degraded_artifact_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**_kwargs: Any) -> object:
        raise Phase5RunnerInputResolutionError(
            "misleading contract wording should not drive classification",
            failure_class="artifact-missing",
            recommended_recovery_action="open_recovery_ticket",
            summary_status="degraded",
            recommended_next_action="retry_failed_step",
        )

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-missing")

    assert result.tick_status == "error"
    assert result.exit_code == 1
    assert result.summary_status == "degraded"
    assert result.recommended_next_action == "retry_failed_step"
    assert result.error is not None
    assert result.error.error_type == "Phase5RunnerInputResolutionError"
    assert result.error.failure_class == "artifact-missing"
    assert result.error.recommended_recovery_action == "open_recovery_ticket"


def test_real_missing_cycle_resolution_error_maps_to_degraded_artifact_missing(tmp_path: Path) -> None:
    result = run_phase5_local_cycle_tick(cycle_id="cycle-missing", root=tmp_path / "artifacts")

    assert result.tick_status == "error"
    assert result.exit_code == 1
    assert result.summary_status == "degraded"
    assert result.recommended_next_action == "retry_failed_step"
    assert result.error is not None
    assert result.error.error_type == "Phase5RunnerInputResolutionError"
    assert result.error.failure_class == "artifact-missing"
    assert result.error.recommended_recovery_action == "open_recovery_ticket"


def test_structured_cycle_mismatch_error_maps_to_blocked_contract_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**_kwargs: Any) -> object:
        raise Phase5RunnerInputResolutionError(
            "missing artifact wording should not drive classification",
            failure_class="contract-violation",
            recommended_recovery_action="block_cycle",
            summary_status="blocked",
            recommended_next_action="blocked",
        )

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-mismatch")

    assert result.tick_status == "error"
    assert result.exit_code == 1
    assert result.summary_status == "blocked"
    assert result.recommended_next_action == "blocked"
    assert result.error is not None
    assert result.error.error_type == "Phase5RunnerInputResolutionError"
    assert result.error.failure_class == "contract-violation"
    assert result.error.recommended_recovery_action == "block_cycle"


def test_file_not_found_maps_to_degraded_artifact_missing_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**_kwargs: Any) -> object:
        raise FileNotFoundError("phase5 cycle ledger artifact is missing: cycle-missing")

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-missing")

    assert result.tick_status == "error"
    assert result.exit_code == 1
    assert result.summary_status == "degraded"
    assert result.recommended_next_action == "retry_failed_step"
    assert result.error is not None
    assert result.error.error_type == "FileNotFoundError"
    assert result.error.failure_class == "artifact-missing"
    assert result.error.recommended_recovery_action == "open_recovery_ticket"


def test_unexpected_error_maps_to_degraded_retry_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**_kwargs: Any) -> object:
        raise RuntimeError("backend failed for digest sha256:abc123")

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-unexpected")
    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False)

    assert result.tick_status == "error"
    assert result.summary_status == "degraded"
    assert result.recommended_next_action == "retry_failed_step"
    assert result.error is not None
    assert result.error.error_type == "RuntimeError"
    assert result.error.failure_class == "unexpected-error"
    assert result.error.recommended_recovery_action == "retry_with_backoff"
    assert "Traceback" not in rendered
    assert "sha256:" not in rendered
    assert "input_bundle" not in rendered
    assert "runner_result" not in rendered


def test_apply_closeout_without_finished_at_is_mapped_from_service_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**kwargs: Any) -> object:
        assert kwargs["apply_closeout"] is True
        assert kwargs["finished_at"] is None
        raise ValueError("phase5 local cycle service apply_closeout requires finished_at")

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-closeout", apply_closeout=True)

    assert result.tick_status == "error"
    assert result.summary_status == "blocked"
    assert result.error is not None
    assert result.error.failure_class == "contract-violation"
    assert result.error.recommended_recovery_action == "block_cycle"


def test_failure_payload_does_not_call_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(**_kwargs: Any) -> object:
        raise FileNotFoundError("missing artifact")

    def fail_projection(_result: object) -> Phase5LocalCycleStatusProjection:
        raise AssertionError("projection should not run when service fails")

    monkeypatch.setattr(tick_module, "run_phase5_local_cycle_service", fake_service)
    monkeypatch.setattr(tick_module, "project_phase5_local_cycle_status", fail_projection)

    result = run_phase5_local_cycle_tick(cycle_id="cycle-failure")

    assert result.tick_status == "error"
    assert result.status is None
