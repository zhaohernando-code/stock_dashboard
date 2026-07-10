from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashare_evidence.runtime_storage_governance import (
    archive_runtime_storage_candidates,
    audit_runtime_storage,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "artifacts"
    feature_relative = "research_validation/pit_feature_matrices/pit-feature-matrix-current.json"
    input_relative = "research_validation/model_exploration_input_snapshots/input-current.json"
    candidate_relative = (
        "research_validation/walk_forward_model_candidate_runs/walk-forward-model-candidate-run-current.json"
    )
    _write_json(
        root / feature_relative,
        {
            "artifact_id": "pit-feature-matrix-current",
            "code_version": "unresolved_local_checkout",
            "row_content_digest": "feature-digest",
            "source_input_snapshot_id": "input-current",
            "source_universe_date_matrix_id": "universe-logical",
            "rows": [],
        },
    )
    _write_json(root / input_relative, {"artifact_id": "input-current"})
    _write_json(root / candidate_relative, {"artifact_id": "walk-forward-model-candidate-run-current"})
    _write_json(
        root / "research_validation/model_comparison_reports/report.json",
        {"artifact_id": "compact-report"},
    )
    _write_json(
        root / "research_validation/pit_feature_matrices/pit-feature-matrix-old.json",
        {"artifact_id": "pit-feature-matrix-old", "rows": []},
    )
    policy = {
        "schema_version": "runtime_storage_governance.v1",
        "max_online_research_bytes": 1024 * 1024,
        "max_compact_evidence_bytes": 1024 * 1024,
        "archive_unpinned_folders": [
            "research_validation/pit_feature_matrices",
            "research_validation/walk_forward_model_candidate_runs",
        ],
        "pinned_artifacts": [
            {
                "artifact_id": "pit-feature-matrix-current",
                "relative_path": feature_relative,
                "required": True,
                "role": "canonical_reusable_feature_matrix",
            },
            {
                "artifact_id": "walk-forward-model-candidate-run-current",
                "relative_path": candidate_relative,
                "required": True,
                "role": "current_complete_history_candidate_source",
            },
        ],
        "required_files": [{"relative_path": input_relative}],
        "canonical_feature_lineage": {
            "artifact_id": "pit-feature-matrix-current",
            "feature_matrix_relative_path": feature_relative,
            "historical_code_version_unresolved": True,
            "logical_universe_reference_id": "universe-logical",
            "row_content_digest": "feature-digest",
            "source_input_snapshot_id": "input-current",
            "universe_reference_materialization": "logical_only_not_materialized_by_streaming_rebuild",
        },
    }
    return root, policy


def test_runtime_storage_audit_blocks_only_unpinned_heavy_payloads(tmp_path: Path) -> None:
    root, policy = _fixture(tmp_path)

    audit = audit_runtime_storage(artifact_root=root, policy=policy)

    assert audit["gate_status"] == "blocked"
    assert audit["blocking_gate_ids"] == ["runtime_storage:archive_candidates_present_online"]
    assert audit["online"]["pinned_file_count"] == 2
    assert audit["online"]["compact_evidence_file_count"] == 2
    assert audit["online"]["archive_candidate_file_count"] == 1
    assert audit["lineage"]["status"] == "acknowledged_partial_reproducibility"


def test_runtime_storage_audit_passes_after_archive_candidate_is_removed(tmp_path: Path) -> None:
    root, policy = _fixture(tmp_path)
    (root / "research_validation/pit_feature_matrices/pit-feature-matrix-old.json").unlink()

    audit = audit_runtime_storage(artifact_root=root, policy=policy)

    assert audit["gate_status"] == "passed"
    assert audit["blocking_gate_ids"] == []


def test_runtime_storage_archive_dry_run_preserves_sources(tmp_path: Path) -> None:
    root, policy = _fixture(tmp_path)
    source = root / "research_validation/pit_feature_matrices/pit-feature-matrix-old.json"

    result = archive_runtime_storage_candidates(
        artifact_root=root,
        policy=policy,
        archive_root=tmp_path / "archive",
        apply=False,
    )

    assert result["planned_file_count"] == 1
    assert source.exists()
    assert not (tmp_path / "archive").exists()


def test_runtime_storage_archive_refuses_unacknowledged_lineage(tmp_path: Path) -> None:
    root, policy = _fixture(tmp_path)
    policy["canonical_feature_lineage"]["historical_code_version_unresolved"] = False

    with pytest.raises(ValueError, match="unresolved_code_version_not_acknowledged"):
        archive_runtime_storage_candidates(
            artifact_root=root,
            policy=policy,
            archive_root=tmp_path / "archive",
            apply=False,
        )
