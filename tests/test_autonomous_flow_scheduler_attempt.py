from __future__ import annotations

import inspect
import re
from pathlib import Path

import ashare_evidence.autonomous_flow_scheduler_attempt as scheduler_attempt
from ashare_evidence.autonomous_flow_scheduler_attempt import build_phase5_scheduler_attempt_context


def test_attempt_context_builds_stable_filename_safe_attempt_id() -> None:
    result = build_phase5_scheduler_attempt_context(
        cycle_id="cycle/2026 05:21 #001",
        issued_at="2026-05-21T10:00:00+08:00",
        runner_id="runner:bj/primary",
    )
    second = build_phase5_scheduler_attempt_context(
        cycle_id="cycle/2026 05:21 #001",
        issued_at="2026-05-21T10:00:00+08:00",
        runner_id="runner:bj/primary",
    )

    assert result.status == "ready"
    assert result.ready is True
    assert result.attempt_id == second.attempt_id
    assert result.attempt_id is not None
    assert result.attempt_id.startswith(
        "attempt-cycle-2026-05-21-001-runner-bj-primary-2026-05-21T10-00-00-08-00-"
    )
    assert _filename_safe(result.attempt_id)
    assert result.required_arguments == ("cycle_id", "issued_at", "runner_id")
    assert result.missing_arguments == ()
    assert result.cycle_id == "cycle/2026 05:21 #001"
    assert result.issued_at == "2026-05-21T10:00:00+08:00"
    assert result.runner_id == "runner:bj/primary"


def test_attempt_context_digest_uses_raw_inputs_not_slug_only() -> None:
    first = build_phase5_scheduler_attempt_context(
        cycle_id="cycle/a",
        issued_at="2026-05-21 10:00",
        runner_id="runner:a",
    )
    second = build_phase5_scheduler_attempt_context(
        cycle_id="cycle a",
        issued_at="2026/05/21 10:00",
        runner_id="runner/a",
    )

    assert first.attempt_id != second.attempt_id
    assert first.attempt_id is not None
    assert second.attempt_id is not None
    assert first.attempt_id.rsplit("-", 1)[0] == second.attempt_id.rsplit("-", 1)[0]


def test_attempt_context_blocks_missing_inputs_without_io(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    cases = (
        ({}, ("cycle_id", "issued_at", "runner_id")),
        ({"cycle_id": ""}, ("cycle_id", "issued_at", "runner_id")),
        ({"cycle_id": "cycle-1", "issued_at": "issued"}, ("runner_id",)),
        ({"cycle_id": "cycle-1", "runner_id": "runner-1"}, ("issued_at",)),
        ({"issued_at": "issued", "runner_id": "runner-1"}, ("cycle_id",)),
        ({"cycle_id": "cycle-1", "issued_at": "", "runner_id": ""}, ("issued_at", "runner_id")),
    )

    for kwargs, missing_arguments in cases:
        result = build_phase5_scheduler_attempt_context(**kwargs)

        assert result.status == "blocked"
        assert result.ready is False
        assert result.attempt_id is None
        assert result.required_arguments == ("cycle_id", "issued_at", "runner_id")
        assert result.missing_arguments == missing_arguments
        assert result.reason.endswith(", ".join(missing_arguments))

    assert _files_under(tmp_path) == ()


def test_attempt_context_is_sensitive_to_each_raw_input() -> None:
    base = {
        "cycle_id": "cycle-20260521-001",
        "issued_at": "2026-05-21T10:00:00Z",
        "runner_id": "runner-bj1",
    }
    baseline = build_phase5_scheduler_attempt_context(**base).attempt_id

    for key in base:
        changed = dict(base)
        changed[key] = changed[key] + "-changed"

        assert build_phase5_scheduler_attempt_context(**changed).attempt_id != baseline


def test_attempt_context_has_no_runtime_io_clock_random_cli_or_writer_dependencies() -> None:
    source = inspect.getsource(scheduler_attempt)

    for token in (
        "datetime",
        "time.",
        "Path(",
        "open(",
        "mkdir(",
        "read_text(",
        "write_text(",
        "uuid",
        "random",
        "subprocess",
        "ashare_evidence.cli",
        "route_phase5",
        "apply_phase5",
        "write_",
    ):
        assert token not in source


def _filename_safe(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None


def _files_under(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))
