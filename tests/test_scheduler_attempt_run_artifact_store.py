from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ashare_evidence.scheduler_attempt_run_artifact_store import (
    find_latest_phase5_scheduler_attempt_run_artifact,
    list_phase5_scheduler_attempt_run_artifacts,
    read_phase5_scheduler_attempt_run_artifact,
    read_phase5_scheduler_attempt_run_artifact_if_exists,
    write_phase5_scheduler_attempt_run_artifact,
)
from ashare_evidence.scheduler_attempt_run_artifacts import (
    PHASE5_SCHEDULER_ATTEMPT_RUN_RECORDED_EVENT_ID,
    Phase5SchedulerAttemptRunArtifact,
)


def test_write_read_and_missing_scheduler_attempt_run_artifact(tmp_path) -> None:
    artifact = _attempt_run(run_id="run-store")

    path = write_phase5_scheduler_attempt_run_artifact(artifact, root=tmp_path)

    stored = read_phase5_scheduler_attempt_run_artifact("run-store", root=tmp_path)
    maybe_stored = read_phase5_scheduler_attempt_run_artifact_if_exists("run-store", root=tmp_path)
    missing = read_phase5_scheduler_attempt_run_artifact_if_exists("missing", root=tmp_path)

    assert path == tmp_path / "autonomous_flow" / "phase5_scheduler_attempt_run" / "run-store.json"
    assert stored == artifact
    assert maybe_stored == artifact
    assert missing is None
    assert stored.applied_output == "execution"
    assert stored.required_arguments == ["execution_id", "idempotency_key", "created_at"]
    assert stored.missing_arguments == []
    assert stored.cycle_event_recorded is True


def test_scheduler_attempt_run_rejects_sensitive_identity_fields() -> None:
    with pytest.raises(ValidationError):
        _attempt_run(run_id="sha256:raw-diagnostic")

    with pytest.raises(ValidationError):
        _attempt_run(diagnostic_id="release-manifest:phase5:20260521")


def test_scheduler_attempt_run_cleans_sensitive_reason_and_refs(tmp_path) -> None:
    artifact = _attempt_run(
        run_id="run-safe",
        reason="Traceback from runner_result should not persist",
        required_arguments=["execution_id", "execution_id", "input_bundle"],
        missing_arguments=["created_at", "created_at", "sha256:abc"],
        blocking_reasons=["missing route args", "missing route args", "input_bundle raw"],
        event_refs=["custom.event.v1", "custom.event.v1", "sha256:abc"],
    )

    write_phase5_scheduler_attempt_run_artifact(artifact, root=tmp_path)
    payload = json.loads(
        (tmp_path / "autonomous_flow" / "phase5_scheduler_attempt_run" / "run-safe.json").read_text(encoding="utf-8")
    )
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert payload["reason"] == "[redacted sensitive scheduler attempt run detail]"
    assert payload["required_arguments"] == ["execution_id"]
    assert payload["missing_arguments"] == ["created_at"]
    assert payload["blocking_reasons"] == ["missing route args"]
    assert payload["event_refs"] == ["custom.event.v1", PHASE5_SCHEDULER_ATTEMPT_RUN_RECORDED_EVENT_ID]
    for forbidden in ("input_bundle", "runner_result", "release-manifest:", "sha256:", "Traceback"):
        assert forbidden not in payload_text


def test_list_attempt_run_artifacts_filters_and_sorts(tmp_path) -> None:
    for artifact in [
        _attempt_run(run_id="run-1", issued_at="2026-05-21T08:00:00Z", runner_id="runner-a"),
        _attempt_run(run_id="run-3", issued_at="2026-05-21T10:00:00Z", apply_status="blocked"),
        _attempt_run(run_id="run-2", issued_at="2026-05-21T10:00:00Z", runner_id="runner-b"),
        _attempt_run(run_id="run-4", cycle_id="cycle-other", issued_at="2026-05-21T11:00:00Z"),
        _attempt_run(run_id="run-0", attempt_status="blocked", issued_at="2026-05-21T07:00:00Z"),
    ]:
        write_phase5_scheduler_attempt_run_artifact(artifact, root=tmp_path)

    assert [
        artifact.run_id for artifact in list_phase5_scheduler_attempt_run_artifacts(cycle_id="cycle-20260521-am", root=tmp_path)
    ] == ["run-3", "run-2", "run-1", "run-0"]
    assert [
        artifact.run_id
        for artifact in list_phase5_scheduler_attempt_run_artifacts(
            runner_id="runner-b",
            attempt_status="ready",
            root=tmp_path,
        )
    ] == ["run-2"]
    assert [
        artifact.run_id
        for artifact in list_phase5_scheduler_attempt_run_artifacts(apply_status="blocked", root=tmp_path)
    ] == ["run-3"]


def test_find_latest_attempt_run_artifact_returns_none_for_empty_store(tmp_path) -> None:
    assert list_phase5_scheduler_attempt_run_artifacts(root=tmp_path) == []
    assert find_latest_phase5_scheduler_attempt_run_artifact(root=tmp_path) is None


def test_find_latest_attempt_run_artifact_returns_latest_filtered_run(tmp_path) -> None:
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(run_id="older-blocked", issued_at="2026-05-21T08:00:00Z", apply_status="blocked"),
        root=tmp_path,
    )
    write_phase5_scheduler_attempt_run_artifact(
        _attempt_run(run_id="latest-applied", issued_at="2026-05-21T10:00:00Z"),
        root=tmp_path,
    )

    latest_blocked = find_latest_phase5_scheduler_attempt_run_artifact(apply_status="blocked", root=tmp_path)
    latest_any = find_latest_phase5_scheduler_attempt_run_artifact(root=tmp_path)

    assert latest_blocked is not None
    assert latest_blocked.run_id == "older-blocked"
    assert latest_any is not None
    assert latest_any.run_id == "latest-applied"


def _attempt_run(**overrides) -> Phase5SchedulerAttemptRunArtifact:
    payload = {
        "run_id": "run-20260521-am",
        "attempt_id": "attempt-20260521-am",
        "cycle_id": "cycle-20260521-am",
        "runner_id": "runner-bq1",
        "issued_at": "2026-05-21T09:00:00Z",
        "attempt_status": "ready",
        "route_type": "execution_output",
        "preflight_status": "ready",
        "apply_status": "applied",
        "applied_output": "execution",
        "required_arguments": ["execution_id", "idempotency_key", "created_at"],
        "missing_arguments": [],
        "diagnostic_id": None,
        "execution_id": "execution-20260521-am",
        "idempotency_key": "cycle:cycle-20260521-am:retry_failed_step",
        "cycle_event_recorded": True,
        "reason": "captured scheduler attempt route apply result",
        "error_type": None,
        "blocking_reasons": [],
        "event_refs": [],
    }
    payload.update(overrides)
    return Phase5SchedulerAttemptRunArtifact(**payload)
