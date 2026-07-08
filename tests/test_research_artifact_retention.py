from __future__ import annotations

from pathlib import Path

from ashare_evidence.research_artifact_retention import audit_research_artifact_retention


def test_research_artifact_retention_audit_passes_bounded_compact_evidence(tmp_path: Path) -> None:
    retained_root = tmp_path / "retained"
    retained_root.mkdir()
    (retained_root / "formal-rejection.json").write_text('{"status":"rejected"}\n', encoding="utf-8")
    replay_root = tmp_path / "frontier-replay"
    replay_root.mkdir()
    (replay_root / "research_validation").mkdir()

    audit = audit_research_artifact_retention(
        retained_root=retained_root,
        compact_replay_roots=[replay_root],
        max_retained_root_bytes=1024,
        max_compact_replay_root_bytes=1024,
    )

    assert audit["gate_status"] == "passed"
    assert audit["blocking_gate_ids"] == []
    assert audit["retained_root"]["candidate_run_file_count"] == 0
    assert audit["compact_replay_roots"]["count"] == 1


def test_research_artifact_retention_audit_blocks_retained_candidate_runs(tmp_path: Path) -> None:
    retained_root = tmp_path / "retained"
    candidate_dir = retained_root / "research_validation" / "walk_forward_model_candidate_runs"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "walk-forward-model-candidate-run-unit.json").write_text("{}", encoding="utf-8")

    audit = audit_research_artifact_retention(retained_root=retained_root)

    assert audit["gate_status"] == "blocked"
    assert "research_artifact_retention:retained_candidate_run_payloads" in audit["blocking_gate_ids"]
    assert audit["retained_root"]["candidate_run_file_count"] == 1


def test_research_artifact_retention_audit_blocks_replay_root_explosion(tmp_path: Path) -> None:
    retained_root = tmp_path / "retained"
    retained_root.mkdir()
    replay_roots = []
    for index in range(3):
        replay_root = tmp_path / f"replay-{index}"
        replay_root.mkdir()
        replay_roots.append(replay_root)

    audit = audit_research_artifact_retention(
        retained_root=retained_root,
        compact_replay_roots=replay_roots,
        max_compact_replay_roots=2,
    )

    assert audit["gate_status"] == "blocked"
    assert "research_artifact_retention:too_many_compact_replay_roots" in audit["blocking_gate_ids"]
    assert audit["compact_replay_roots"]["count"] == 3


def test_research_artifact_retention_audit_blocks_oversized_replay_root(tmp_path: Path) -> None:
    retained_root = tmp_path / "retained"
    retained_root.mkdir()
    replay_root = tmp_path / "replay"
    replay_root.mkdir()
    (replay_root / "large.json").write_text("x" * 33, encoding="utf-8")

    audit = audit_research_artifact_retention(
        retained_root=retained_root,
        compact_replay_roots=[replay_root],
        max_compact_replay_root_bytes=32,
    )

    assert audit["gate_status"] == "blocked"
    assert "research_artifact_retention:compact_replay_root_size_exceeded" in audit["blocking_gate_ids"]
