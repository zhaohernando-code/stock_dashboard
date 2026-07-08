from __future__ import annotations

import json
from pathlib import Path

from ashare_evidence.research_model_preflight_compaction import compact_model_preflight_root


def test_compact_model_preflight_root_writes_summary_and_deletes_source(tmp_path: Path) -> None:
    root = tmp_path / "preflight"
    research = root / "research_validation"
    _write_artifact(
        research / "model_exploration_input_snapshots" / "input.json",
        {
            "artifact_type": "model_exploration_input_snapshot",
            "artifact_id": "input-1",
            "validation_run_id": "unit-preflight",
            "feature_version": "shortpick_model_pit_feature_matrix:v3",
            "source_data_time_range": {"as_of_start": "2024-02-07", "as_of_end": "2024-06-05"},
            "eligible_symbol_count": 300,
            "as_of_date_count": 75,
            "universe_row_count": 22500,
            "gate_readout": {"gate_status": "research_input_ready", "blocking_gate_ids": []},
        },
    )
    _write_artifact(
        research / "pit_feature_matrices" / "feature.json",
        _matrix_payload(
            artifact_type="pit_feature_matrix",
            artifact_id="feature-1",
            feature_version="shortpick_model_pit_feature_matrix:v3",
            row_count=22500,
            rows=[{"row_id": "feature:a"}, {"row_id": "feature:b"}],
        ),
    )
    _write_artifact(
        research / "executable_label_matrices" / "label.json",
        _matrix_payload(
            artifact_type="executable_label_matrix",
            artifact_id="label-1",
            feature_version="not_applicable_label_matrix",
            row_count=22500,
            rows=[{"row_id": "label:a"}],
            gate_readout={"gate_status": "blocked", "ready_row_count": 21000, "blocking_gate_ids": ["partial"]},
        ),
    )
    _write_artifact(
        research / "walk_forward_model_candidate_runs" / "candidate.json",
        {
            "artifact_type": "walk_forward_model_candidate_run",
            "artifact_id": "candidate-1",
            "validation_run_id": "unit-preflight",
            "feature_version": "shortpick_model_pit_feature_matrix:v3",
            "trial_count": 1,
            "prediction_row_count": 10,
            "stored_prediction_row_count": 2,
            "trial_diagnostics": [
                {
                    "trial_id": "spec:trial-000",
                    "model_spec_id": "spec",
                    "total_return": 0.1,
                    "predictions": [{"heavy": "row"}],
                }
            ],
            "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": ["comparison_report_pending"]},
        },
    )
    _write_artifact(
        research / "model_comparison_reports" / "report.json",
        {
            "artifact_type": "model_comparison_report",
            "artifact_id": "report-1",
            "validation_run_id": "unit-preflight",
            "feature_version": "shortpick_model_pit_feature_matrix:v3",
            "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": ["insufficient_periods"]},
        },
    )
    _write_artifact(
        research / "governance_promotion_decisions" / "governance.json",
        {
            "artifact_type": "governance_promotion_decision",
            "artifact_id": "governance-1",
            "gate_readout": {"gate_status": "blocked", "blocking_gate_ids": ["execution:adv_capacity_fill_rate"]},
        },
    )
    output = tmp_path / "retained" / "summary.json"

    summary = compact_model_preflight_root(preflight_root=root, output_json=output, delete_source_root=True)

    assert output.exists()
    assert not root.exists()
    assert summary["source_root_exists_after_cleanup"] is False
    assert summary["validation_run_id"] == "unit-preflight"
    assert summary["feature_version"] == "shortpick_model_pit_feature_matrix:v3"
    assert summary["matrix_readout"]["feature_row_count"] == 22500
    assert summary["matrix_readout"]["label_ready_row_count"] == 21000
    assert summary["candidate_run_readout"]["compact_trial_diagnostics"] == [
        {
            "trial_id": "spec:trial-000",
            "model_spec_id": "spec",
            "trial_rank": None,
            "total_return": 0.1,
            "annualized_return": None,
            "mean_selected_net_excess_return": None,
            "positive_selected_top_k_rate": None,
            "max_drawdown": None,
            "negative_month_count": None,
            "worst_monthly_mean": None,
            "path_drawdown_sum": None,
            "adv_capacity_full_fill_rate": None,
            "active_underfilled_pick_count": None,
        }
    ]
    retained_payload = json.loads(output.read_text(encoding="utf-8"))
    assert "rows" not in json.dumps(retained_payload["artifacts"]["pit_feature_matrix"])
    assert "predictions" not in json.dumps(retained_payload["candidate_run_readout"])
    assert "governance:execution:adv_capacity_fill_rate" in retained_payload["blocking_gate_ids"]


def _matrix_payload(
    *,
    artifact_type: str,
    artifact_id: str,
    feature_version: str,
    row_count: int,
    rows: list[dict[str, str]],
    gate_readout: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "feature_version": feature_version,
        "row_count": row_count,
        "feature_groups": ["valuation_capacity"],
        "gate_readout": gate_readout or {"gate_status": "ready", "blocking_gate_ids": []},
        "rows": rows,
    }


def _write_artifact(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
