from __future__ import annotations

from ashare_evidence.exposure_floor_overlay_governance import (
    build_exposure_floor_overlay_governance_summary,
    build_staggered_exposure_combo_governance_summary,
)


def test_exposure_floor_overlay_governance_adds_compact_overlay_trial() -> None:
    trial_id = "model_v1:trial-000"
    candidate_run = {
        "artifact_id": "walk-forward-model-candidate-run-unit",
        "validation_run_id": "unit-validation",
        "source_db_snapshot_id": "unit-db",
        "source_data_time_range": {"start": "2026-01-01", "end": "2026-01-05"},
        "feature_version": "feature-v1",
        "label_version": "label-v1",
        "split_count": 4,
        "prediction_row_count": 100,
        "trial_count": 1,
        "splits": [
            {"split_id": "s1", "status": "ready"},
            {"split_id": "s2", "status": "ready"},
            {"split_id": "s3", "status": "ready"},
            {"split_id": "s4", "status": "ready"},
        ],
        "trial_summaries": [
            {
                "trial_id": trial_id,
                "model_spec_id": "model_v1",
                "metrics": {
                    "rank_ic_mean": 0.1,
                    "positive_rank_ic_rate": 0.75,
                    "selected_top_k": 1,
                    "selected_top_k_net_excess_mean": 0.01,
                    "positive_selected_top_k_rate": 0.5,
                    "labeled_prediction_count": 100,
                },
                "blocking_gate_ids": [],
                "selection_policy": {
                    "mode": "concentrated_top_k",
                    "evaluation_return_metric": "selected_top_k_net_excess_mean",
                },
            }
        ],
        "trial_diagnostics": [
            {
                "trial_id": trial_id,
                "selected_top_k": 1,
                "target_horizon_days": 1,
                "split_rank_ics": [{"split_id": "s1", "rank_ic": 0.1}],
                "date_rank_ics": [{"as_of_date": "2026-01-02", "rank_ic": 0.1}],
                "selected_top_k_picks_by_date": [],
                "selected_top_k_returns_by_date": [
                    {
                        "as_of_date": "2026-01-02",
                        "month": "2026-01",
                        "mean_net_excess_return": -0.03,
                        "mean_total_return_after_cost": -0.02,
                        "gross_exposure": 0.1,
                        "pick_count": 1,
                    },
                    {
                        "as_of_date": "2026-01-03",
                        "month": "2026-01",
                        "mean_net_excess_return": 0.05,
                        "mean_total_return_after_cost": 0.06,
                        "gross_exposure": 0.8,
                        "pick_count": 1,
                    },
                ],
            }
        ],
    }
    registry = {
        "artifact_id": "model-spec-registry-unit",
        "model_specs": [
            {
                "model_spec_id": "model_v1",
                "selection_policy": {
                    "mode": "concentrated_top_k",
                    "evaluation_return_metric": "selected_top_k_net_excess_mean",
                },
            }
        ],
    }

    summary = build_exposure_floor_overlay_governance_summary(
        candidate_run=candidate_run,
        model_spec_registry=registry,
        trial_id=trial_id,
        overlay_mode="linear_scale",
        gross_exposure_floor=0.2,
        validation_run_id="unit-overlay",
        source_exposure_proxy_artifact="/tmp/source-proxy.json",
    )

    assert summary["artifact_type"] == "exposure_floor_overlay_governance_summary"
    assert summary["claim_ceiling"] == "selected_return_overlay_governance_proxy_only_no_model_replay_no_promotion"
    assert summary["overlay"]["low_exposure_active_date_count"] == 1
    assert summary["overlay_trial"]["selected_top_k_net_excess_mean"] > summary["source_trial"][
        "selected_top_k_net_excess_mean"
    ]
    assert summary["metric_deltas"]["portfolio_total_return"] > 0
    assert "candidate_run" not in summary


def test_staggered_exposure_combo_governance_uses_combo_fill_details() -> None:
    trial_id = "model_v1:trial-000"
    candidate_run = {
        "artifact_id": "walk-forward-model-candidate-run-unit",
        "validation_run_id": "unit-validation",
        "source_db_snapshot_id": "unit-db",
        "source_data_time_range": {"start": "2026-01-01", "end": "2026-01-05"},
        "feature_version": "feature-v1",
        "label_version": "label-v1",
        "split_count": 4,
        "prediction_row_count": 100,
        "trial_count": 1,
        "splits": [{"split_id": f"s{index}", "status": "ready"} for index in range(1, 5)],
        "trial_summaries": [
            {
                "trial_id": trial_id,
                "model_spec_id": "model_v1",
                "metrics": {
                    "rank_ic_mean": 0.1,
                    "positive_rank_ic_rate": 0.75,
                    "selected_top_k": 1,
                    "selected_top_k_net_excess_mean": 0.01,
                    "positive_selected_top_k_rate": 0.5,
                    "labeled_prediction_count": 100,
                },
                "blocking_gate_ids": [],
                "selection_policy": {
                    "mode": "concentrated_top_k",
                    "evaluation_return_metric": "selected_top_k_net_excess_mean",
                },
            }
        ],
        "trial_diagnostics": [
            {
                "trial_id": trial_id,
                "selected_top_k": 1,
                "target_horizon_days": 1,
                "split_rank_ics": [{"split_id": "s1", "rank_ic": 0.1}],
                "date_rank_ics": [{"as_of_date": "2026-01-02", "rank_ic": 0.1}],
                "selected_top_k_picks_by_date": [],
                "selected_top_k_returns_by_date": [
                    {
                        "as_of_date": "2026-01-02",
                        "month": "2026-01",
                        "mean_net_excess_return": -0.04,
                        "mean_total_return_after_cost": -0.03,
                        "gross_exposure": 0.1,
                        "pick_count": 1,
                    },
                    {
                        "as_of_date": "2026-01-03",
                        "month": "2026-01",
                        "mean_net_excess_return": 0.06,
                        "mean_total_return_after_cost": 0.07,
                        "gross_exposure": 0.8,
                        "pick_count": 1,
                    },
                ],
            }
        ],
    }
    registry = {
        "artifact_id": "model-spec-registry-unit",
        "model_specs": [
            {
                "model_spec_id": "model_v1",
                "selection_policy": {
                    "mode": "concentrated_top_k",
                    "evaluation_return_metric": "selected_top_k_net_excess_mean",
                },
            }
        ],
    }
    combo_proxy = {
        "scan_summaries": [
            {
                "entry_days": 10,
                "exit_policy": "per_tranche_horizon",
                "exposure_overlay_mode": "linear_scale",
                "gross_exposure_floor": 0.2,
                "full_fill_repaired_pick_count": 1,
                "min_staggered_fill_rate": 1.0,
                "fill_details": [
                    {
                        "as_of_date": "2026-01-02",
                        "baseline_contribution": -0.04,
                        "staggered_contribution": 0.02,
                    }
                ],
            }
        ]
    }

    summary = build_staggered_exposure_combo_governance_summary(
        candidate_run=candidate_run,
        model_spec_registry=registry,
        combo_proxy=combo_proxy,
        trial_id=trial_id,
        entry_days=10,
        exit_policy="per_tranche_horizon",
        exposure_overlay_mode="linear_scale",
        gross_exposure_floor=0.2,
        validation_run_id="unit-combo",
        source_combo_proxy_artifact="/tmp/combo-proxy.json",
    )

    assert summary["artifact_type"] == "staggered_exposure_combo_governance_summary"
    assert summary["combo"]["full_fill_repaired_pick_count"] == 1
    assert summary["combo_trial"]["selected_top_k_net_excess_mean"] > summary["source_trial"][
        "selected_top_k_net_excess_mean"
    ]
    assert summary["metric_deltas"]["portfolio_total_return"] > 0
    assert "candidate_run" not in summary


def test_staggered_exposure_combo_governance_can_clear_capacity_proxy_gate() -> None:
    trial_id = "model_v1:trial-000"
    returns_by_date = [
        {
            "as_of_date": f"2026-01-{day:02d}",
            "month": "2026-01",
            "mean_net_excess_return": -0.04 if day == 2 else 0.02,
            "mean_total_return_after_cost": -0.03 if day == 2 else 0.021,
            "gross_exposure": 0.8,
            "pick_count": 1,
        }
        for day in range(1, 21)
    ]
    selected_picks = [
        {
            "as_of_date": f"2026-01-{day:02d}",
            "month": "2026-01",
            "symbol": f"600{day:03d}.SH",
            "rank": 1,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "avg_amount_20d": 1_000_000.0 if day == 2 else 30_000_000.0,
        }
        for day in range(1, 21)
    ]
    candidate_run = {
        "artifact_id": "walk-forward-model-candidate-run-unit",
        "validation_run_id": "unit-validation",
        "source_db_snapshot_id": "unit-db",
        "source_data_time_range": {"start": "2026-01-01", "end": "2026-01-20"},
        "feature_version": "feature-v1",
        "label_version": "label-v1",
        "split_count": 4,
        "prediction_row_count": 100,
        "trial_count": 1,
        "splits": [{"split_id": f"s{index}", "status": "ready"} for index in range(1, 5)],
        "trial_summaries": [
            {
                "trial_id": trial_id,
                "model_spec_id": "model_v1",
                "metrics": {
                    "rank_ic_mean": 0.1,
                    "positive_rank_ic_rate": 0.75,
                    "selected_top_k": 1,
                    "selected_top_k_net_excess_mean": 0.017,
                    "positive_selected_top_k_rate": 0.95,
                    "labeled_prediction_count": 100,
                },
                "blocking_gate_ids": [],
                "selection_policy": {
                    "mode": "concentrated_top_k",
                    "evaluation_return_metric": "selected_top_k_net_excess_mean",
                },
            }
        ],
        "trial_diagnostics": [
            {
                "trial_id": trial_id,
                "selected_top_k": 1,
                "target_horizon_days": 1,
                "split_rank_ics": [{"split_id": "s1", "rank_ic": 0.1}],
                "date_rank_ics": [{"as_of_date": "2026-01-02", "rank_ic": 0.1}],
                "selected_top_k_picks_by_date": selected_picks,
                "selected_top_k_returns_by_date": returns_by_date,
            }
        ],
    }
    registry = {
        "artifact_id": "model-spec-registry-unit",
        "model_specs": [
            {
                "model_spec_id": "model_v1",
                "selection_policy": {
                    "mode": "concentrated_top_k",
                    "evaluation_return_metric": "selected_top_k_net_excess_mean",
                },
            }
        ],
    }
    combo_proxy = {
        "scan_summaries": [
            {
                "entry_days": 10,
                "exit_policy": "per_tranche_horizon",
                "exposure_overlay_mode": "linear_scale",
                "gross_exposure_floor": 0.2,
                "underfilled_pick_count": 1,
                "full_fill_repaired_pick_count": 1,
                "min_staggered_fill_rate": 1.0,
                "fill_details": [
                    {
                        "as_of_date": "2026-01-02",
                        "baseline_contribution": -0.04,
                        "staggered_contribution": 0.02,
                    }
                ],
            }
        ]
    }

    summary = build_staggered_exposure_combo_governance_summary(
        candidate_run=candidate_run,
        model_spec_registry=registry,
        combo_proxy=combo_proxy,
        trial_id=trial_id,
        entry_days=10,
        exit_policy="per_tranche_horizon",
        exposure_overlay_mode="linear_scale",
        gross_exposure_floor=0.2,
        validation_run_id="unit-combo",
        source_combo_proxy_artifact="/tmp/combo-proxy.json",
    )

    blockers = summary["governance_gate_readout"]["blocking_gate_ids"]
    assert "execution:adv_capacity_fill_rate" not in blockers
    assert "model_comparison_report:execution_stress:capacity:adv_capacity_fill_rate_below_floor" not in blockers
    capacity_check = next(
        check
        for check in summary["governance_gate_readout"]["execution_gate_readout"]["checks"]
        if check["gate_id"] == "adv_capacity_fill_rate"
    )
    assert capacity_check["status"] == "ready"
    assert capacity_check["capacity_contract"]["status"] == "configured_staggered_execution_capacity_proxy_ready"
