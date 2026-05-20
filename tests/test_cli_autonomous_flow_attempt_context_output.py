from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import ashare_evidence.cli as cli_module
import ashare_evidence.cli_autonomous_flow as cli_autonomous_flow
import ashare_evidence.cli_autonomous_flow_attempt_outputs as attempt_outputs
from tests.helpers_cli_autonomous_flow import _args
from tests.helpers_cli_autonomous_flow_smoke import _guard_init_database


class _FakeAttemptResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.status = payload["status"]

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


def test_attempt_context_output_does_not_run_tick_or_apply(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_calls: list[dict[str, str | None]] = []

    def fake_build_context(**kwargs: str | None) -> _FakeAttemptResult:
        build_calls.append(kwargs)
        return _FakeAttemptResult(
            {
                "status": "ready",
                "attempt_id": "attempt-cycle-ctx-runner-bk1-issued-abc123",
                "cycle_id": kwargs["cycle_id"],
                "issued_at": kwargs["issued_at"],
                "runner_id": kwargs["runner_id"],
                "required_arguments": ["cycle_id", "issued_at", "runner_id"],
                "missing_arguments": [],
                "reason": "fake context",
            }
        )

    def fail_unexpected(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("attempt-context output called an execution-path handler")

    monkeypatch.setattr(attempt_outputs, "build_phase5_scheduler_attempt_context", fake_build_context)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_tick", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "plan_phase5_scheduler_followup", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "execute_phase5_scheduler_noop_action", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "route_phase5_scheduler_action_result", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "apply_phase5_scheduler_action_route", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "bind_and_apply_phase5_scheduler_action_route", fail_unexpected)
    monkeypatch.setattr(cli_autonomous_flow, "run_phase5_local_cycle_service", fail_unexpected)

    exit_code = cli_autonomous_flow.handle_phase5_local_cycle_step_command(
        _args(
            output="attempt-context",
            cycle_id="cycle-ctx",
            issued_at="issued",
            runner_id="runner-bk1",
            artifact_root=Path("tmp/artifacts"),
        )
    )

    assert exit_code == 0
    assert build_calls == [{"cycle_id": "cycle-ctx", "issued_at": "issued", "runner_id": "runner-bk1"}]
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["attempt_id"] == "attempt-cycle-ctx-runner-bk1-issued-abc123"


def test_attempt_context_output_ready_uses_explicit_inputs_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle/2026 05:21 #001",
            "--artifact-root",
            str(artifact_root),
            "--issued-at",
            "2026-05-21T10:00:00+08:00",
            "--runner-id",
            "runner:bk/primary",
            "--output",
            "attempt-context",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    assert payload["status"] == "ready"
    assert payload["attempt_id"].startswith(
        "attempt-cycle-2026-05-21-001-runner-bk-primary-2026-05-21T10-00-00-08-00-"
    )
    assert payload["required_arguments"] == ["cycle_id", "issued_at", "runner_id"]
    assert payload["missing_arguments"] == []


@pytest.mark.parametrize(
    ("extra_args", "missing_arguments"),
    [
        (["--runner-id", "runner-bk1"], ["issued_at"]),
        (["--issued-at", "2026-05-21T10:00:00Z"], ["runner_id"]),
    ],
)
def test_attempt_context_output_blocks_missing_explicit_inputs_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
    missing_arguments: list[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    init_database_calls = _guard_init_database(monkeypatch)

    exit_code = cli_module.main(
        [
            "phase5-local-cycle-step",
            "--cycle-id",
            "cycle-missing-context",
            "--artifact-root",
            str(artifact_root),
            "--output",
            "attempt-context",
            *extra_args,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert init_database_calls == []
    assert _files_under(artifact_root) == ()
    assert payload["status"] == "blocked"
    assert payload["attempt_id"] is None
    assert payload["missing_arguments"] == missing_arguments


def _files_under(root: Path) -> tuple[str, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
