from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ashare_evidence.research_artifact_store import read_shortpick_combined_ledger_backfill_artifacts
from ashare_evidence.shortpick_combined_ledger_writer import (
    discover_shortpick_retrospective_forward_replay_artifacts,
    materialize_shortpick_combined_ledger_from_artifact_root,
    run_shortpick_combined_ledger_backfill_artifact,
)
from ashare_evidence.shortpick_strategy_governance import (
    SAME_SYMBOL_COOLDOWN_CONTROL_ID,
    apply_shortpick_drawdown_reversal_filter_control,
    apply_shortpick_repeated_exposure_limit_control,
    apply_shortpick_same_symbol_cooldown_control,
    build_shortpick_combined_ledger_retrospective_backfill,
    build_shortpick_credible_control_comparison_line_plan,
    build_shortpick_drawdown_reversal_filter_rule,
    build_shortpick_historical_backtest_generation_requests,
    build_shortpick_redundant_control_archive_decisions,
    build_shortpick_repeated_exposure_limit_rule,
    build_shortpick_retrospective_forward_replay_requests,
    build_shortpick_same_symbol_cooldown_rule,
    build_shortpick_strategy_archive_records,
    build_shortpick_strategy_retirement_evidence_packs,
    build_shortpick_strategy_status_recommendations,
    build_shortpick_true_forward_tracking_activation_plan,
    filter_shortpick_combined_ledger_rows_by_evidence_basis,
    filter_shortpick_generation_eligible_items,
    partition_paper_tracking_rows_by_governance,
    project_shortpick_strategy_view_sections,
)
from ashare_evidence.shortpick_strategy_replay_runner import run_shortpick_retrospective_forward_replay_request
from ashare_evidence.shortpick_strategy_retirement_writer import run_shortpick_strategy_retirement_artifact


def test_retirement_evidence_pack_aggregates_forward_metrics_without_deciding_status() -> None:
    payload = {
        "items": [
            _item("2026-05-10", "002371.SZ", "北方华创", -0.10, -0.12),
            _item("2026-05-11", "002371.SZ", "北方华创", -0.05, -0.02),
            _item("2026-05-12", "300750.SZ", "宁德时代", 0.30, 0.28),
        ]
    }

    result = build_shortpick_strategy_retirement_evidence_packs(
        payload,
        historical_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "after_cost_excess_return": -0.03,
            }
        },
        baseline_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "baseline_id": "evaluation_baseline_random_pool:v1",
                "mean_excess_return_gap": -0.02,
            }
        },
        generated_at="2026-06-10T12:00:00+08:00",
    )

    assert result["status"] == "ready"
    assert result["strategy_count"] == 1
    assert result["decision_policy"] == "evidence_only_no_retirement_decision"
    assert "retired" not in json.dumps(result["packs"], ensure_ascii=False)

    pack = result["packs"][0]
    assert pack["evidence_basis"] == "true_forward_tracking"
    assert pack["decision_status"] == "not_evaluated"
    assert pack["signal_count"] == 3
    assert pack["completed_observation_count"] == 3
    assert pack["historical_evidence"]["after_cost_excess_return"] == -0.03
    assert pack["baseline_comparison"]["baseline_id"] == "evaluation_baseline_random_pool:v1"

    horizon = pack["horizon_summaries"][0]
    assert horizon["horizon_days"] == 10
    assert horizon["completed_sample_count"] == 3
    assert horizon["maturity_status"] == "insufficient_completed_sample"
    assert horizon["mean_stock_return"] == 0.05
    assert horizon["median_stock_return"] == -0.05
    assert horizon["win_rate"] == 0.333333
    assert horizon["mean_excess_return"] == 0.046667
    assert horizon["worst_stock_return"] == -0.10
    assert horizon["best_stock_return"] == 0.30
    assert horizon["negative_completed_count"] == 2
    assert horizon["max_additive_drawdown"] == -0.15
    assert horizon["tail_dependency"] == {
        "best_positive_share": 1.0,
        "tail_dependent": True,
        "basis": "best_positive_stock_return_share_of_positive_stock_return_sum",
    }
    assert horizon["same_symbol_loss_repeats"] == [
        {"symbol": "002371.SZ", "negative_completed_count": 2}
    ]


def test_retirement_evidence_pack_separates_next_close_and_next_open_variants() -> None:
    payload = {
        "items": [
            _item("2026-05-10", "002371.SZ", "北方华创", -0.10, -0.12),
            _item(
                "2026-05-10",
                "002371.SZ",
                "北方华创",
                0.04,
                0.03,
                tracking_group="frozen_strategy_v2",
                entry_price_source="next_open",
                entry_rule="次一交易日开盘买入；开盘直接接近涨停时标记为不可假设成交",
            ),
        ]
    }

    result = build_shortpick_strategy_retirement_evidence_packs(payload)

    assert result["strategy_count"] == 2
    entry_sources = sorted(pack["entry_price_source"] for pack in result["packs"])
    assert entry_sources == ["next_close", "next_open"]
    groups = sorted(pack["tracking_group"] for pack in result["packs"])
    assert groups == ["frozen_strategy", "frozen_strategy_v2"]


def test_retirement_evidence_pack_ignores_incomplete_horizons() -> None:
    payload = {
        "items": [
            {
                **_item("2026-05-10", "002371.SZ", "北方华创", -0.10, -0.12),
                "validation_by_horizon": [
                    {
                        "horizon_days": 10,
                        "status": "pending",
                        "stock_return": 0.99,
                        "excess_return": 0.99,
                    },
                    {
                        "horizon_days": 5,
                        "status": "completed",
                        "stock_return": None,
                        "excess_return": None,
                    },
                ],
            }
        ]
    }

    result = build_shortpick_strategy_retirement_evidence_packs(payload)

    assert result["strategy_count"] == 1
    pack = result["packs"][0]
    assert pack["signal_count"] == 1
    assert pack["completed_observation_count"] == 0
    assert pack["horizon_summaries"] == []
    assert pack["decision_status"] == "not_evaluated"


def test_retirement_evidence_pack_preserves_evidence_basis_and_source_rank_zero() -> None:
    payload = {
        "items": [
            _item(
                "2026-05-10",
                "002371.SZ",
                "北方华创",
                -0.10,
                -0.12,
                source_rank=0,
            )
        ]
    }

    result = build_shortpick_strategy_retirement_evidence_packs(
        payload,
        evidence_basis="retrospective_forward_replay",
    )

    pack = result["packs"][0]
    assert result["evidence_basis"] == "retrospective_forward_replay"
    assert pack["evidence_basis"] == "retrospective_forward_replay"
    assert pack["source_rank"] == 0
    assert pack["strategy_id"].endswith("__0")


def test_retirement_evidence_pack_rejects_unknown_evidence_basis() -> None:
    with pytest.raises(ValueError, match="unsupported shortpick evidence_basis"):
        build_shortpick_strategy_retirement_evidence_packs({"items": []}, evidence_basis="mixed")


def test_status_recommendation_marks_weak_mature_strategy_as_retire_candidate_not_retired() -> None:
    evidence = _evidence_from_returns(
        [-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02],
        historical_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "after_cost_excess_return": -0.03,
            }
        },
        baseline_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "mean_excess_return_gap": -0.02,
            }
        },
    )

    result = build_shortpick_strategy_status_recommendations(evidence)

    recommendation = result["recommendations"][0]
    assert result["decision_policy"] == "retired_requires_strategy_retirement_artifact_and_decision_log_ref"
    assert recommendation["recommended_status"] == "retire_candidate"
    assert recommendation["retirement_artifact_ref"] is None
    assert "strategy_retirement_artifact_and_decision_log_ref_present" not in recommendation["reasons"]
    assert recommendation["blockers"] == []
    assert "historical_after_cost_excess_negative" in recommendation["reasons"]
    assert "forward_win_rate_below_45pct" in recommendation["reasons"]


def test_status_recommendation_requires_artifact_and_decision_log_for_retired() -> None:
    evidence = _evidence_from_returns(
        [-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02],
        historical_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "after_cost_excess_return": -0.03,
            }
        },
    )
    strategy_id = evidence["packs"][0]["strategy_id"]

    result = build_shortpick_strategy_status_recommendations(
        evidence,
        retirement_artifacts={
            strategy_id: {
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "artifact_id": "shortpick-retirement-fixture",
                "decision_log_ref": "DECISIONS.md#2026-06-10-fixture",
            }
        },
    )

    recommendation = result["recommendations"][0]
    assert recommendation["recommended_status"] == "retired"
    assert recommendation["retirement_artifact_ref"]["artifact_id"] == "shortpick-retirement-fixture"
    assert recommendation["reasons"] == ["strategy_retirement_artifact_and_decision_log_ref_present"]


def test_strategy_retirement_writer_records_artifact_consumed_by_status_recommendation() -> None:
    evidence = _evidence_from_returns(
        [-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02],
        historical_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "after_cost_excess_return": -0.03,
                "evidence_basis": "historical_backtest",
            }
        },
    )
    recommendations = build_shortpick_strategy_status_recommendations(evidence)
    strategy_id = evidence["packs"][0]["strategy_id"]

    artifact = run_shortpick_strategy_retirement_artifact(
        evidence,
        recommendations,
        strategy_id=strategy_id,
        decision_log_ref="docs/DECISIONS.md#2026-06-11-retire-test",
        evidence_snapshot_refs=["output/shortpick/evidence-pack.json"],
        retired_at="2026-06-11T12:00:00+08:00",
        replacement_guidance="Use registered cooldown and drawdown controls instead.",
    )

    assert artifact["status"] == "ready"
    assert artifact["artifact_family"] == "shortpick_strategy_retirement"
    assert artifact["schema_version"] == "v1"
    assert artifact["strategy_id"] == strategy_id
    assert artifact["strategy_status_before"] == "retire_candidate"
    assert artifact["retirement_reason_code"] in {
        "persistent_negative_after_cost_excess",
        "tail_dependence_failure",
    }
    assert artifact["evidence_basis_refs"] == ["historical_backtest", "true_forward_tracking"]
    assert "shortpick.strategy_retirement.recorded.v1" in artifact["event_refs"]

    retired = build_shortpick_strategy_status_recommendations(
        evidence,
        retirement_artifacts={"artifacts": [artifact]},
    )["recommendations"][0]
    assert retired["recommended_status"] == "retired"
    assert retired["retirement_artifact_ref"]["artifact_id"] == artifact["artifact_id"]


def test_strategy_retirement_writer_blocks_non_retire_candidate() -> None:
    evidence = _evidence_from_returns([0.02, 0.03, 0.01, 0.04, 0.02])
    recommendations = build_shortpick_strategy_status_recommendations(evidence)
    strategy_id = evidence["packs"][0]["strategy_id"]

    artifact = run_shortpick_strategy_retirement_artifact(
        evidence,
        recommendations,
        strategy_id=strategy_id,
        decision_log_ref="docs/DECISIONS.md#2026-06-11-blocked",
        evidence_snapshot_refs=["output/shortpick/evidence-pack.json"],
        retired_at="2026-06-11T12:00:00+08:00",
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocker"] == "strategy_must_be_retire_candidate_before_retirement_artifact"


def test_status_recommendation_keeps_weak_immature_or_missing_history_in_observe() -> None:
    evidence = _evidence_from_returns([-0.10, -0.05, 0.01])

    result = build_shortpick_strategy_status_recommendations(evidence)

    recommendation = result["recommendations"][0]
    assert recommendation["recommended_status"] == "observe"
    assert "forward_sample_not_mature" in recommendation["blockers"]
    assert "historical_after_cost_evidence_missing" in recommendation["blockers"]


def test_status_recommendation_keeps_non_triggering_strategy_active() -> None:
    evidence = _evidence_from_returns([0.02, 0.03, 0.01, 0.04, 0.02])

    result = build_shortpick_strategy_status_recommendations(evidence)

    recommendation = result["recommendations"][0]
    assert recommendation["recommended_status"] == "active"
    assert recommendation["reasons"] == ["no_retirement_evidence_trigger"]
    assert recommendation["blockers"] == []


def test_generation_filter_excludes_only_retired_strategies() -> None:
    retired = _generation_item("market_factor_control_cooldown_top1", "momentum_10d_turnover_cooldown_rank", 1)
    candidate = _generation_item("market_factor_control_offensive_top1", "momentum_10d_turnover_rank", 1)
    observed = _generation_item("market_factor_control_random_pool", "momentum_pool_deterministic_random_control", 1)
    untracked = _generation_item("market_factor_control_golden_cross_10_200", "momentum_volume_golden_cross_10_200", 1)
    status_result = {
        "recommendations": [
            {"strategy_id": retired["strategy_id"], "recommended_status": "retired"},
            {"strategy_id": candidate["strategy_id"], "recommended_status": "retire_candidate"},
            {"strategy_id": observed["strategy_id"], "recommended_status": "observe"},
        ]
    }

    result = filter_shortpick_generation_eligible_items(
        [retired, candidate, observed, untracked],
        status_result,
    )

    assert result["decision_policy"] == "exclude_retired_and_inventory_archived_from_active_generation"
    assert result["input_count"] == 4
    assert result["eligible_count"] == 3
    assert result["excluded_count"] == 1
    assert [item["strategy_id"] for item in result["excluded_items"]] == [retired["strategy_id"]]
    eligible_statuses = {item["strategy_id"]: item["governance_status"] for item in result["eligible_items"]}
    assert eligible_statuses[candidate["strategy_id"]] == "retire_candidate"
    assert eligible_statuses[observed["strategy_id"]] == "observe"
    assert eligible_statuses[untracked["strategy_id"]] == "untracked"


def test_generation_filter_can_include_retired_for_archive_rebuild() -> None:
    retired = _generation_item("market_factor_control_cooldown_top1", "momentum_10d_turnover_cooldown_rank", 1)
    status_result = {"recommendations": [{"strategy_id": retired["strategy_id"], "recommended_status": "retired"}]}

    result = filter_shortpick_generation_eligible_items([retired], status_result, include_retired=True)

    assert result["include_retired"] is True
    assert result["eligible_count"] == 1
    assert result["excluded_count"] == 0
    assert result["eligible_items"][0]["governance_status"] == "retired"


def test_inventory_archive_decisions_require_inventory_basis_and_reason_code() -> None:
    archive_item = _generation_item(
        "market_factor_control_legacy_second_candidate",
        "momentum_10d_turnover_legacy_second_candidate",
        2,
    )
    performance_item = _generation_item(
        "market_factor_control_cooldown_top1",
        "momentum_10d_turnover_cooldown_rank",
        1,
    )
    missing_basis_item = _generation_item(
        "market_factor_control_golden_cross_10_200",
        "momentum_volume_golden_cross_10_200",
        1,
    )

    result = build_shortpick_redundant_control_archive_decisions(
        [
            {
                **archive_item,
                "archive_action": "archive",
                "decision_basis": "inventory_diagnostic_value",
                "archive_reason_code": "redundant_with_registered_control",
                "archive_note": "covered by a stronger registered comparison line",
            },
            {
                **performance_item,
                "archive_action": "archive",
                "decision_basis": "performance_retirement",
                "archive_reason_code": "poor_forward_returns",
            },
            {
                **missing_basis_item,
                "archive_action": "archive",
                "archive_reason_code": "no_unique_diagnostic_value",
            },
        ],
        generated_at="2026-06-11T10:00:00+08:00",
    )

    assert result["status"] == "ready"
    assert result["decision_policy"] == "inventory_diagnostic_value_archive_separate_from_performance_retirement"
    assert result["archived_count"] == 1
    assert result["blocked_count"] == 2
    assert result["archived_records"][0]["governance_status"] == "inventory_archived"
    assert result["archived_records"][0]["governance_view_section"] == "deprecated"
    assert result["archived_records"][0]["archive_reason_code"] == "redundant_with_registered_control"
    assert {item["blocker"] for item in result["blocked_records"]} == {
        "inventory_archive_requires_inventory_diagnostic_value_basis",
    }


def test_generation_filter_excludes_inventory_archived_controls_separately_from_retirement() -> None:
    archived = _generation_item(
        "market_factor_control_legacy_second_candidate",
        "momentum_10d_turnover_legacy_second_candidate",
        2,
    )
    active = _generation_item("market_factor_control_offensive_top1", "momentum_10d_turnover_rank", 1)
    inventory = build_shortpick_redundant_control_archive_decisions(
        [
            {
                **archived,
                "archive_action": "archive",
                "decision_basis": "inventory_diagnostic_value",
                "archive_reason_code": "no_unique_diagnostic_value",
            }
        ]
    )

    result = filter_shortpick_generation_eligible_items(
        [archived, active],
        {"recommendations": []},
        inventory_archive_decision_result=inventory,
    )

    assert result["decision_policy"] == "exclude_retired_and_inventory_archived_from_active_generation"
    assert result["eligible_count"] == 1
    assert result["excluded_count"] == 1
    assert result["excluded_items"][0]["governance_status"] == "inventory_archived"
    assert result["excluded_items"][0]["reason"] == "inventory_archived_control_excluded_from_active_generation"

    archive_rebuild = filter_shortpick_generation_eligible_items(
        [archived],
        {"recommendations": []},
        inventory_archive_decision_result=inventory,
        include_inventory_archived=True,
    )
    assert archive_rebuild["eligible_count"] == 1
    assert archive_rebuild["eligible_items"][0]["governance_status"] == "inventory_archived"


def test_generation_filter_derives_strategy_id_from_generation_fields() -> None:
    strategy_id = "market_factor_control__market_factor_control_cooldown_top1__momentum_10d_turnover_cooldown_rank__next_close__1"
    status_result = {"recommendations": [{"strategy_id": strategy_id, "recommended_status": "retired"}]}

    result = filter_shortpick_generation_eligible_items(
        [
            {
                "tracking_group": "market_factor_control",
                "role": "market_factor_control_cooldown_top1",
                "family": "momentum_10d_turnover_cooldown_rank",
                "entry_price_source": "next_close",
                "source_rank": 1,
            }
        ],
        status_result,
    )

    assert result["eligible_items"] == []
    assert result["excluded_items"][0]["strategy_id"] == strategy_id


def test_strategy_view_projection_splits_retired_into_archive_only() -> None:
    result = project_shortpick_strategy_view_sections(
        {
            "recommendations": [
                {
                    "strategy_id": "active-id",
                    "recommended_status": "active",
                    "evidence_basis": "true_forward_tracking",
                    "tracking_group": "market_factor_control",
                    "reasons": ["no_retirement_evidence_trigger"],
                    "primary_horizon_summary": {"heavy": True},
                    "retirement_artifact_ref": None,
                },
                {
                    "strategy_id": "observe-id",
                    "recommended_status": "observe",
                    "evidence_basis": "true_forward_tracking",
                    "tracking_group": "market_factor_control",
                    "blockers": ["forward_sample_not_mature"],
                },
                {
                    "strategy_id": "candidate-id",
                    "recommended_status": "retire_candidate",
                    "evidence_basis": "true_forward_tracking",
                    "tracking_group": "market_factor_control",
                    "reasons": ["forward_win_rate_below_45pct"],
                },
                {
                    "strategy_id": "retired-id",
                    "recommended_status": "retired",
                    "evidence_basis": "true_forward_tracking",
                    "tracking_group": "market_factor_control",
                    "reasons": ["strategy_retirement_artifact_and_decision_log_ref_present"],
                    "retirement_artifact_ref": {"artifact_id": "retired-fixture"},
                },
            ]
        }
    )

    assert result["decision_policy"] == "retired_status_hidden_from_primary_view_and_kept_in_archive"
    assert result["primary_count"] == 3
    assert result["archive_count"] == 1
    assert [item["strategy_id"] for item in result["primary_items"]] == [
        "active-id",
        "observe-id",
        "candidate-id",
    ]
    assert result["archive_items"] == [
        {
            "strategy_id": "retired-id",
            "recommended_status": "retired",
            "status_display": {
                "key": "retired",
                "label": "Retired",
                "tone": "default",
                "primary_section": "archive",
            },
            "evidence_basis": "true_forward_tracking",
            "evidence_basis_display": {
                "key": "true_forward_tracking",
                "label": "True forward tracking",
                "tone": "green",
            },
            "tracking_group": "market_factor_control",
            "tracking_role": None,
            "strategy_family": None,
            "entry_price_source": None,
            "primary_horizon_days": None,
            "reasons": ["strategy_retirement_artifact_and_decision_log_ref_present"],
            "blockers": [],
            "leakage_coverage_note": {
                "evidence_basis": "true_forward_tracking",
                "leakage_audit_status": "not_run",
                "leakage_audit_reasons": [],
                "source_feature_cutoff_policy": None,
                "feature_cutoff_at": None,
                "feature_coverage_status": "unknown",
                "display_required": False,
            },
            "governance_archive_basis": None,
            "inventory_archive_decision": None,
            "view_section": "archive",
        }
    ]
    assert result["evidence_basis_section_policy"] == "separate_historical_retrospective_and_true_forward_sections"
    assert result["evidence_basis_sections"][0]["evidence_basis"] == "true_forward_tracking"
    assert result["evidence_basis_sections"][0]["item_count"] == 4
    assert result["evidence_basis_sections"][0]["primary_count"] == 3
    assert result["evidence_basis_sections"][0]["archive_count"] == 1
    assert "primary_horizon_summary" not in result["primary_items"][0]
    assert "retirement_artifact_ref" not in result["archive_items"][0]


def test_strategy_view_projection_moves_inventory_archived_to_archive() -> None:
    inventory = build_shortpick_redundant_control_archive_decisions(
        [
            {
                "strategy_id": "inventory-id",
                "tracking_group": "market_factor_control",
                "role": "market_factor_control_legacy_second_candidate",
                "family": "momentum_10d_turnover_legacy_second_candidate",
                "entry_price_source": "next_close",
                "source_rank": 2,
                "archive_action": "archive",
                "decision_basis": "inventory_diagnostic_value",
                "archive_reason_code": "redundant_with_registered_control",
            }
        ]
    )

    result = project_shortpick_strategy_view_sections(
        {
            "recommendations": [
                {
                    "strategy_id": "inventory-id",
                    "recommended_status": "active",
                    "evidence_basis": "true_forward_tracking",
                    "tracking_group": "market_factor_control",
                    "tracking_role": "market_factor_control_legacy_second_candidate",
                    "strategy_family": "momentum_10d_turnover_legacy_second_candidate",
                    "entry_price_source": "next_close",
                }
            ]
        },
        inventory_archive_decision_result=inventory,
    )

    assert result["primary_count"] == 0
    assert result["archive_count"] == 1
    archived = result["archive_items"][0]
    assert archived["recommended_status"] == "inventory_archived"
    assert archived["status_display"]["primary_section"] == "archive"
    assert archived["view_section"] == "archive"
    assert archived["governance_archive_basis"] == "inventory_diagnostic_value"
    assert archived["inventory_archive_decision"]["archive_reason_code"] == "redundant_with_registered_control"


def test_strategy_view_projection_tolerates_missing_lists() -> None:
    result = project_shortpick_strategy_view_sections(
        {"recommendations": [{"strategy_id": "id", "recommended_status": "observe"}]}
    )

    assert result["primary_items"][0]["reasons"] == []
    assert result["primary_items"][0]["blockers"] == []
    assert result["primary_items"][0]["status_display"] == {
        "key": "observe",
        "label": "Observe",
        "tone": "gold",
        "primary_section": "primary",
    }
    assert result["primary_items"][0]["evidence_basis_display"] == {
        "key": "unknown",
        "label": "Unknown evidence",
        "tone": "default",
    }


def test_strategy_view_projection_adds_status_and_evidence_labels() -> None:
    result = project_shortpick_strategy_view_sections(
        {
            "recommendations": [
                {
                    "strategy_id": "candidate-id",
                    "recommended_status": "retire_candidate",
                    "evidence_basis": "retrospective_forward_replay",
                },
                {
                    "strategy_id": "unknown-id",
                    "recommended_status": "custom_future_status",
                    "evidence_basis": "custom_basis",
                },
            ]
        }
    )

    candidate, unknown = result["primary_items"]
    assert candidate["status_display"] == {
        "key": "retire_candidate",
        "label": "Retire candidate",
        "tone": "orange",
        "primary_section": "primary",
    }
    assert candidate["evidence_basis_display"] == {
        "key": "retrospective_forward_replay",
        "label": "Retrospective replay",
        "tone": "purple",
    }
    assert unknown["status_display"] == {
        "key": "custom_future_status",
        "label": "Unknown",
        "tone": "default",
        "primary_section": "primary",
    }
    assert unknown["evidence_basis_display"] == {
        "key": "custom_basis",
        "label": "Unknown evidence",
        "tone": "default",
    }


def test_strategy_view_projection_adds_leakage_and_coverage_notes_for_retrospective_rows() -> None:
    result = project_shortpick_strategy_view_sections(
        {
            "recommendations": [
                {
                    "strategy_id": "retrospective-id",
                    "recommended_status": "observe",
                    "evidence_basis": "retrospective_forward_replay",
                    "leakage_audit_status": "not_run",
                    "leakage_audit_reasons": ["audit_pending"],
                    "source_feature_cutoff_policy": "signal_date_available_inputs_only",
                    "feature_cutoff_at": "2026-05-10T15:00:00+08:00",
                    "feature_coverage_status": "partial",
                }
            ]
        }
    )

    note = result["primary_items"][0]["leakage_coverage_note"]
    assert note == {
        "evidence_basis": "retrospective_forward_replay",
        "leakage_audit_status": "not_run",
        "leakage_audit_reasons": ["audit_pending"],
        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
        "feature_cutoff_at": "2026-05-10T15:00:00+08:00",
        "feature_coverage_status": "partial",
        "display_required": True,
    }
    assert result["evidence_basis_sections"][0]["items"][0]["leakage_coverage_note"] == note


def test_strategy_view_projection_defaults_retrospective_cutoff_policy_when_missing() -> None:
    result = project_shortpick_strategy_view_sections(
        {
            "recommendations": [
                {
                    "strategy_id": "retrospective-id",
                    "recommended_status": "observe",
                    "evidence_basis": "retrospective_forward_replay",
                }
            ]
        }
    )

    note = result["primary_items"][0]["leakage_coverage_note"]
    assert note["leakage_audit_status"] == "not_run"
    assert note["leakage_audit_reasons"] == []
    assert note["source_feature_cutoff_policy"] == "signal_date_available_inputs_only"
    assert note["feature_coverage_status"] == "unknown"
    assert note["display_required"] is True


def test_strategy_view_projection_separates_evidence_basis_sections() -> None:
    result = project_shortpick_strategy_view_sections(
        {
            "recommendations": [
                {
                    "strategy_id": "true-forward-id",
                    "recommended_status": "active",
                    "evidence_basis": "true_forward_tracking",
                },
                {
                    "strategy_id": "retrospective-id",
                    "recommended_status": "observe",
                    "evidence_basis": "retrospective_forward_replay",
                },
                {
                    "strategy_id": "historical-id",
                    "recommended_status": "observe",
                    "evidence_basis": "historical_backtest",
                },
                {
                    "strategy_id": "retired-retrospective-id",
                    "recommended_status": "retired",
                    "evidence_basis": "retrospective_forward_replay",
                },
            ]
        }
    )

    sections = result["evidence_basis_sections"]
    assert [item["evidence_basis"] for item in sections] == [
        "true_forward_tracking",
        "retrospective_forward_replay",
        "historical_backtest",
    ]
    retrospective = sections[1]
    assert retrospective["evidence_basis_display"] == {
        "key": "retrospective_forward_replay",
        "label": "Retrospective replay",
        "tone": "purple",
    }
    assert retrospective["item_count"] == 2
    assert retrospective["primary_count"] == 1
    assert retrospective["archive_count"] == 1
    assert [item["view_section"] for item in retrospective["items"]] == ["primary", "archive"]


def test_archive_records_preserve_statistics_and_evidence_refs_for_retired_rows() -> None:
    evidence = _evidence_from_returns(
        [-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02],
        historical_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "artifact_ref": "historical-fixture",
                "after_cost_excess_return": -0.03,
            }
        },
        baseline_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "baseline_id": "evaluation_baseline_random_pool:v1",
                "artifact_ref": "baseline-fixture",
            }
        },
    )
    strategy_id = evidence["packs"][0]["strategy_id"]
    status_result = build_shortpick_strategy_status_recommendations(
        evidence,
        retirement_artifacts={
            strategy_id: {
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "artifact_id": "retirement-fixture",
                "decision_log_ref": "DECISIONS.md#fixture",
            }
        },
    )
    view = project_shortpick_strategy_view_sections(status_result)

    archive = build_shortpick_strategy_archive_records(
        view,
        evidence,
        retirement_artifacts={
            strategy_id: {
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "artifact_id": "retirement-fixture",
                "decision_log_ref": "DECISIONS.md#fixture",
            }
        },
    )

    assert archive["decision_policy"] == "preserve_retired_strategy_statistics_and_evidence_refs"
    assert archive["archive_count"] == 1
    record = archive["records"][0]
    assert record["strategy_id"] == strategy_id
    assert record["recommended_status"] == "retired"
    assert record["archive_reason"] == "retired_strategy_removed_from_primary_view"
    assert record["signal_count"] == 10
    assert record["completed_observation_count"] == 10
    assert record["horizon_summaries"][0]["maturity_status"] == "mature_one_stock_review_sample"
    assert record["historical_evidence"]["artifact_ref"] == "historical-fixture"
    assert record["baseline_comparison"]["baseline_id"] == "evaluation_baseline_random_pool:v1"
    assert record["retirement_artifact_ref"]["artifact_id"] == "retirement-fixture"
    assert archive["archive_summary_policy"] == "group_retired_strategies_by_evidence_basis_family_and_entry_source"
    assert archive["summary_rows"][0]["archived_strategy_count"] == 1
    assert archive["summary_rows"][0]["signal_count"] == 10
    assert archive["summary_rows"][0]["completed_observation_count"] == 10
    assert archive["summary_rows"][0]["retirement_artifact_count"] == 1


def test_archive_records_mark_inventory_archived_reason_separately_from_retirement() -> None:
    items = [
        _control_tracking_item(
            f"2026-05-{index + 1:02d}",
            "002371.SZ",
            "北方华创",
            role="market_factor_control_legacy_second_candidate",
            family="momentum_10d_turnover_legacy_second_candidate",
            source_rank=2,
        )
        for index in range(3)
    ]
    evidence = build_shortpick_strategy_retirement_evidence_packs({"items": items})
    strategy_id = evidence["packs"][0]["strategy_id"]
    inventory = build_shortpick_redundant_control_archive_decisions(
        [
            {
                "strategy_id": strategy_id,
                "tracking_group": "market_factor_control",
                "role": "market_factor_control_legacy_second_candidate",
                "family": "momentum_10d_turnover_legacy_second_candidate",
                "entry_price_source": "next_close",
                "source_rank": 2,
                "archive_action": "archive",
                "decision_basis": "inventory_diagnostic_value",
                "archive_reason_code": "dormant_legacy_control",
            }
        ]
    )
    status = {
        "recommendations": [
            {
                "strategy_id": strategy_id,
                "recommended_status": "active",
                "evidence_basis": "true_forward_tracking",
                "tracking_group": "market_factor_control",
                "tracking_role": "market_factor_control_legacy_second_candidate",
                "strategy_family": "momentum_10d_turnover_legacy_second_candidate",
                "entry_price_source": "next_close",
            }
        ]
    }
    view = project_shortpick_strategy_view_sections(status, inventory_archive_decision_result=inventory)

    archive = build_shortpick_strategy_archive_records(view, evidence)

    assert archive["archive_count"] == 1
    record = archive["records"][0]
    assert record["recommended_status"] == "inventory_archived"
    assert record["archive_reason"] == "inventory_archived_control_removed_from_primary_view"
    assert record["inventory_archive_decision"]["archive_reason_code"] == "dormant_legacy_control"
    assert record["retirement_artifact_ref"] == {}
    assert archive["summary_rows"][0]["retirement_artifact_count"] == 0


def test_archive_records_ignore_primary_rows() -> None:
    archive = build_shortpick_strategy_archive_records(
        {"primary_items": [{"strategy_id": "active-id", "recommended_status": "active"}], "archive_items": []},
        {"packs": [{"strategy_id": "active-id", "signal_count": 1}]},
    )

    assert archive["archive_count"] == 0
    assert archive["summary_rows"] == []


def test_archive_records_preserve_leakage_coverage_notes_for_retired_rows() -> None:
    archive = build_shortpick_strategy_archive_records(
        {
            "archive_items": [
                {
                    "strategy_id": "retrospective-id",
                    "recommended_status": "retired",
                    "leakage_coverage_note": {
                        "evidence_basis": "retrospective_forward_replay",
                        "leakage_audit_status": "passed",
                        "leakage_audit_reasons": ["used_only_signal_date_or_prior_features"],
                        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
                        "feature_cutoff_at": "2026-05-10",
                        "feature_coverage_status": "ready",
                        "display_required": True,
                    },
                }
            ]
        },
        {
            "packs": [
                {
                    "strategy_id": "retrospective-id",
                    "evidence_basis": "retrospective_forward_replay",
                    "strategy_family": "cooldown",
                    "entry_price_source": "next_close",
                }
            ]
        },
    )

    assert archive["records"][0]["leakage_coverage_note"] == {
        "evidence_basis": "retrospective_forward_replay",
        "leakage_audit_status": "passed",
        "leakage_audit_reasons": ["used_only_signal_date_or_prior_features"],
        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
        "feature_cutoff_at": "2026-05-10",
        "feature_coverage_status": "ready",
        "display_required": True,
    }


def test_archive_records_build_leakage_coverage_notes_from_pack_when_projection_missing() -> None:
    archive = build_shortpick_strategy_archive_records(
        {"archive_items": [{"strategy_id": "retrospective-id", "recommended_status": "retired"}]},
        {
            "packs": [
                {
                    "strategy_id": "retrospective-id",
                    "evidence_basis": "retrospective_forward_replay",
                    "source_feature_cutoff_policy": "signal_date_available_inputs_only",
                    "feature_cutoff_date": "2026-05-10",
                    "feature_coverage_status": "missing",
                    "leakage_audit_status": "blocked",
                    "leakage_audit_reasons": ["feature_snapshot_missing"],
                }
            ]
        },
    )

    assert archive["records"][0]["leakage_coverage_note"] == {
        "evidence_basis": "retrospective_forward_replay",
        "leakage_audit_status": "blocked",
        "leakage_audit_reasons": ["feature_snapshot_missing"],
        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
        "feature_cutoff_at": "2026-05-10",
        "feature_coverage_status": "missing",
        "display_required": True,
    }


def test_archive_records_build_summary_rows_by_basis_family_and_entry_source() -> None:
    archive = build_shortpick_strategy_archive_records(
        {
            "archive_items": [
                {"strategy_id": "true-1", "recommended_status": "retired"},
                {"strategy_id": "true-2", "recommended_status": "retired"},
                {"strategy_id": "retro-1", "recommended_status": "retired"},
            ]
        },
        {
            "packs": [
                {
                    "strategy_id": "true-1",
                    "evidence_basis": "true_forward_tracking",
                    "strategy_family": "family_a",
                    "entry_price_source": "next_close",
                    "first_signal_date": "2026-05-01",
                    "latest_signal_date": "2026-05-03",
                    "signal_count": 3,
                    "completed_observation_count": 2,
                },
                {
                    "strategy_id": "true-2",
                    "evidence_basis": "true_forward_tracking",
                    "strategy_family": "family_a",
                    "entry_price_source": "next_close",
                    "first_signal_date": "2026-04-29",
                    "latest_signal_date": "2026-05-04",
                    "signal_count": 2,
                    "completed_observation_count": 1,
                },
                {
                    "strategy_id": "retro-1",
                    "evidence_basis": "retrospective_forward_replay",
                    "strategy_family": "family_b",
                    "entry_price_source": "next_open",
                    "first_signal_date": "2026-05-02",
                    "latest_signal_date": "2026-05-05",
                    "signal_count": 4,
                    "completed_observation_count": 4,
                },
            ]
        },
        retirement_artifacts={
            "true-1": {"artifact_id": "retire-true-1"},
            "true-2": {"artifact_id": "retire-true-2"},
        },
    )

    assert [item["evidence_basis"] for item in archive["summary_rows"]] == [
        "true_forward_tracking",
        "retrospective_forward_replay",
    ]
    true_forward = archive["summary_rows"][0]
    assert true_forward["summary_key"] == "true_forward_tracking__family_a__next_close"
    assert true_forward["archived_strategy_count"] == 2
    assert true_forward["signal_count"] == 5
    assert true_forward["completed_observation_count"] == 3
    assert true_forward["first_signal_date"] == "2026-04-29"
    assert true_forward["latest_signal_date"] == "2026-05-04"
    assert true_forward["retirement_artifact_count"] == 2
    assert archive["summary_rows"][1]["summary_key"] == "retrospective_forward_replay__family_b__next_open"
    assert len(archive["records"]) == 3


def test_same_symbol_cooldown_rule_signature_is_stable_and_parameter_sensitive() -> None:
    first = build_shortpick_same_symbol_cooldown_rule(cooldown_signal_days=5)
    second = build_shortpick_same_symbol_cooldown_rule(cooldown_signal_days=5)
    changed = build_shortpick_same_symbol_cooldown_rule(cooldown_signal_days=6)

    assert first["rule_signature"] == second["rule_signature"]
    assert first["rule_signature"].startswith("sha256:")
    assert first["rule_signature"] != changed["rule_signature"]


def test_same_symbol_cooldown_rule_rejects_invalid_windows() -> None:
    with pytest.raises(ValueError, match="cooldown_signal_days must be positive"):
        build_shortpick_same_symbol_cooldown_rule(cooldown_signal_days=0)

    with pytest.raises(ValueError, match="severe_cooldown_signal_days"):
        build_shortpick_same_symbol_cooldown_rule(cooldown_signal_days=5, severe_cooldown_signal_days=4)

    with pytest.raises(ValueError, match="negative_horizon_days must be positive"):
        build_shortpick_same_symbol_cooldown_rule(negative_horizon_days=0)


def test_same_symbol_cooldown_blocks_prior_completed_negative_same_symbol_only() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(cooldown_signal_days=2, severe_cooldown_signal_days=4)
    candidates = [
        {"candidate_id": "aaa-3", "symbol": "AAA.SZ", "signal_date": "2026-05-03"},
        {"candidate_id": "aaa-4", "symbol": "AAA.SZ", "signal_date": "2026-05-04"},
        {"candidate_id": "aaa-5", "symbol": "AAA.SZ", "signal_date": "2026-05-05"},
        {"candidate_id": "bbb-3", "symbol": "BBB.SZ", "signal_date": "2026-05-03"},
    ]
    outcomes = [
        {
            "candidate_id": "loss-aaa",
            "run_id": "run-1",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-02",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.03,
        },
        {
            "candidate_id": "loss-bbb",
            "symbol": "BBB.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-02",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.03,
        },
        {
            "candidate_id": "wrong-horizon",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-02",
            "horizon_days": 5,
            "status": "completed",
            "stock_return": -0.50,
        },
    ]

    result = apply_shortpick_same_symbol_cooldown_control(candidates, outcomes, rule=rule)

    by_id = {row["candidate_id"]: row for row in result["rows"]}
    assert result["blocked_count"] == 3
    assert result["allowed_count"] == 1
    assert by_id["aaa-3"]["cooldown_action"] == "blocked"
    assert by_id["aaa-3"]["cooldown_blocker_events"][0]["elapsed_signal_days"] == 1
    assert by_id["aaa-4"]["cooldown_action"] == "blocked"
    assert by_id["aaa-5"]["cooldown_action"] == "allowed"
    assert by_id["bbb-3"]["cooldown_action"] == "blocked"


def test_same_symbol_cooldown_uses_longer_window_after_severe_loss() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(
        cooldown_signal_days=2,
        severe_loss_threshold=-0.08,
        severe_cooldown_signal_days=4,
    )
    candidates = [
        {"candidate_id": f"aaa-{day}", "symbol": "AAA.SZ", "signal_date": f"2026-05-{day:02d}"}
        for day in range(4, 9)
    ]
    outcomes = [
        {
            "candidate_id": "severe-loss",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-03",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.10,
        }
    ]

    result = apply_shortpick_same_symbol_cooldown_control(candidates, outcomes, rule=rule)

    by_id = {row["candidate_id"]: row for row in result["rows"]}
    assert by_id["aaa-7"]["cooldown_action"] == "blocked"
    assert by_id["aaa-7"]["cooldown_blocker_events"][0]["cooldown_signal_days"] == 4
    assert by_id["aaa-8"]["cooldown_action"] == "allowed"


def test_same_symbol_cooldown_can_use_external_signal_date_calendar() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(
        cooldown_signal_days=2,
        severe_loss_threshold=-0.08,
        severe_cooldown_signal_days=4,
    )
    candidates = [{"candidate_id": "aaa-8", "symbol": "AAA.SZ", "signal_date": "2026-05-08"}]
    outcomes = [
        {
            "candidate_id": "severe-loss",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-03",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.10,
        }
    ]
    signal_date_rows = [{"signal_date": f"2026-05-{day:02d}"} for day in range(4, 9)]

    result = apply_shortpick_same_symbol_cooldown_control(
        candidates,
        outcomes,
        rule=rule,
        signal_date_rows=signal_date_rows,
    )

    assert result["rows"][0]["cooldown_action"] == "allowed"


def test_same_symbol_cooldown_ignores_same_day_or_future_outcomes_for_leakage() -> None:
    candidates = [{"candidate_id": "aaa-2", "symbol": "AAA.SZ", "signal_date": "2026-05-02"}]
    outcomes = [
        {
            "candidate_id": "same-day-loss",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-02",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.03,
        },
        {
            "candidate_id": "future-loss",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-21",
            "exit_date": "2026-05-03",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.04,
        },
    ]

    result = apply_shortpick_same_symbol_cooldown_control(candidates, outcomes)

    assert result["leakage_audit_status"] == "passed"
    assert result["ignored_future_or_same_day_outcome_count"] == 2
    assert result["rows"][0]["cooldown_action"] == "allowed"
    assert result["rows"][0]["cooldown_blocker_events"] == []


def test_drawdown_reversal_filter_rule_signature_is_stable_and_parameter_sensitive() -> None:
    first = build_shortpick_drawdown_reversal_filter_rule(max_recent_drawdown_return=-0.08)
    second = build_shortpick_drawdown_reversal_filter_rule(max_recent_drawdown_return=-0.08)
    changed = build_shortpick_drawdown_reversal_filter_rule(max_recent_drawdown_return=-0.09)

    assert first["rule_signature"] == second["rule_signature"]
    assert first["rule_signature"].startswith("sha256:")
    assert first["rule_signature"] != changed["rule_signature"]


def test_drawdown_reversal_filter_rule_rejects_invalid_lookback() -> None:
    with pytest.raises(ValueError, match="drawdown_lookback_days must be positive"):
        build_shortpick_drawdown_reversal_filter_rule(drawdown_lookback_days=0)


def test_drawdown_reversal_filter_blocks_any_registered_trigger() -> None:
    rule = build_shortpick_drawdown_reversal_filter_rule(
        max_recent_drawdown_return=-0.08,
        short_window_return_threshold=-0.03,
        price_vs_ma20_threshold=0.0,
        high_level_reversal_return_threshold=-0.05,
    )
    candidates = [
        {"candidate_id": "drawdown", "symbol": "AAA.SZ", "signal_date": "2026-05-10"},
        {"candidate_id": "breakdown", "symbol": "BBB.SZ", "signal_date": "2026-05-10"},
        {"candidate_id": "reversal", "symbol": "CCC.SZ", "signal_date": "2026-05-10"},
        {"candidate_id": "clean", "symbol": "DDD.SZ", "signal_date": "2026-05-10"},
    ]
    features = [
        {
            "symbol": "AAA.SZ",
            "feature_date": "2026-05-10",
            "recent_drawdown_return": -0.09,
            "short_window_return": 0.01,
            "price_vs_ma20": 0.02,
            "high_level_reversal_return": 0.01,
        },
        {
            "symbol": "BBB.SZ",
            "feature_date": "2026-05-10",
            "recent_drawdown_return": -0.01,
            "short_window_return": -0.04,
            "price_vs_ma20": -0.01,
            "high_level_reversal_return": 0.01,
        },
        {
            "symbol": "CCC.SZ",
            "feature_date": "2026-05-10",
            "recent_drawdown_return": -0.01,
            "short_window_return": 0.01,
            "price_vs_ma20": 0.02,
            "high_level_reversal_return": -0.06,
        },
        {
            "symbol": "DDD.SZ",
            "feature_date": "2026-05-10",
            "recent_drawdown_return": -0.01,
            "short_window_return": 0.01,
            "price_vs_ma20": 0.02,
            "high_level_reversal_return": 0.01,
        },
    ]

    result = apply_shortpick_drawdown_reversal_filter_control(candidates, features, rule=rule)

    by_id = {row["candidate_id"]: row for row in result["rows"]}
    assert result["blocked_count"] == 3
    assert result["allowed_count"] == 1
    assert by_id["drawdown"]["filter_triggers"][0]["reason"] == "recent_drawdown_threshold_triggered"
    assert by_id["breakdown"]["filter_triggers"][0]["reason"] == "short_window_breakdown_triggered"
    assert by_id["reversal"]["filter_triggers"][0]["reason"] == "high_level_reversal_threshold_triggered"
    assert by_id["clean"]["filter_action"] == "allowed"


def test_drawdown_reversal_filter_uses_latest_signal_date_or_prior_feature_only() -> None:
    candidates = [{"candidate_id": "aaa-10", "symbol": "AAA.SZ", "signal_date": "2026-05-10"}]
    features = [
        {
            "symbol": "AAA.SZ",
            "feature_date": "2026-05-08",
            "recent_drawdown_return": -0.01,
            "short_window_return": 0.01,
            "price_vs_ma20": 0.02,
            "high_level_reversal_return": 0.01,
        },
        {
            "symbol": "AAA.SZ",
            "feature_date": "2026-05-09",
            "recent_drawdown_return": -0.09,
            "short_window_return": 0.01,
            "price_vs_ma20": 0.02,
            "high_level_reversal_return": 0.01,
        },
        {
            "symbol": "AAA.SZ",
            "feature_date": "2026-05-11",
            "recent_drawdown_return": -0.50,
            "short_window_return": -0.50,
            "price_vs_ma20": -0.50,
            "high_level_reversal_return": -0.50,
        },
    ]

    result = apply_shortpick_drawdown_reversal_filter_control(candidates, features)

    row = result["rows"][0]
    assert result["ignored_future_feature_count"] == 1
    assert row["feature_cutoff_date"] == "2026-05-09"
    assert row["filter_action"] == "blocked"
    assert row["filter_triggers"][0]["reason"] == "recent_drawdown_threshold_triggered"
    assert result["leakage_audit_status"] == "passed"


def test_drawdown_reversal_filter_allows_missing_features_with_coverage_flag() -> None:
    candidates = [{"candidate_id": "missing", "symbol": "AAA.SZ", "signal_date": "2026-05-10"}]

    result = apply_shortpick_drawdown_reversal_filter_control(candidates, [])

    assert result["blocked_count"] == 0
    assert result["missing_feature_count"] == 1
    assert result["rows"][0]["filter_action"] == "allowed"
    assert result["rows"][0]["feature_coverage_status"] == "missing"
    assert result["rows"][0]["filter_triggers"] == []


def test_repeated_exposure_limit_rule_signature_is_stable_and_parameter_sensitive() -> None:
    first = build_shortpick_repeated_exposure_limit_rule(exposure_window_signal_days=10)
    second = build_shortpick_repeated_exposure_limit_rule(exposure_window_signal_days=10)
    changed = build_shortpick_repeated_exposure_limit_rule(exposure_window_signal_days=5)

    assert first["rule_signature"] == second["rule_signature"]
    assert first["rule_signature"].startswith("sha256:")
    assert first["rule_signature"] != changed["rule_signature"]


def test_repeated_exposure_limit_rule_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="exposure_window_signal_days must be positive"):
        build_shortpick_repeated_exposure_limit_rule(exposure_window_signal_days=0)

    with pytest.raises(ValueError, match="max_prior_signals_per_group must be non-negative"):
        build_shortpick_repeated_exposure_limit_rule(max_prior_signals_per_group=-1)


def test_repeated_exposure_limit_blocks_prior_same_symbol_within_window() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule(
        exposure_window_signal_days=1,
        max_prior_signals_per_group=0,
    )
    candidates = [
        {"candidate_id": "aaa-3", "symbol": "AAA.SZ", "signal_date": "2026-05-03"},
        {"candidate_id": "aaa-5", "symbol": "AAA.SZ", "signal_date": "2026-05-05"},
        {"candidate_id": "bbb-3", "symbol": "BBB.SZ", "signal_date": "2026-05-03"},
    ]
    exposure_rows = [
        {"candidate_id": "aaa-prior", "symbol": "AAA.SZ", "signal_date": "2026-05-02"},
        {"candidate_id": "aaa-old", "symbol": "AAA.SZ", "signal_date": "2026-04-20"},
        {"candidate_id": "bbb-prior", "symbol": "BBB.SZ", "signal_date": "2026-05-02"},
    ]

    result = apply_shortpick_repeated_exposure_limit_control(candidates, exposure_rows, rule=rule)

    by_id = {row["candidate_id"]: row for row in result["rows"]}
    assert result["blocked_count"] == 2
    assert result["allowed_count"] == 1
    assert by_id["aaa-3"]["exposure_action"] == "blocked"
    assert by_id["aaa-3"]["exposure_prior_signal_count"] == 1
    assert by_id["aaa-3"]["exposure_blocker_rows"][0]["candidate_id"] == "aaa-prior"
    assert by_id["aaa-5"]["exposure_action"] == "allowed"
    assert by_id["bbb-3"]["exposure_action"] == "blocked"


def test_repeated_exposure_limit_ignores_same_day_and_future_signals() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule(max_prior_signals_per_group=0)
    candidates = [{"candidate_id": "aaa-3", "symbol": "AAA.SZ", "signal_date": "2026-05-03"}]
    exposure_rows = [
        {"candidate_id": "same-day", "symbol": "AAA.SZ", "signal_date": "2026-05-03"},
        {"candidate_id": "future", "symbol": "AAA.SZ", "signal_date": "2026-05-04"},
    ]

    result = apply_shortpick_repeated_exposure_limit_control(candidates, exposure_rows, rule=rule)

    assert result["ignored_same_day_or_future_signal_count"] == 2
    assert result["blocked_count"] == 0
    assert result["rows"][0]["exposure_action"] == "allowed"
    assert result["rows"][0]["exposure_blocker_rows"] == []
    assert result["leakage_audit_status"] == "passed"


def test_repeated_exposure_limit_supports_explicit_group_fields() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule(
        max_prior_signals_per_group=0,
        group_fields=["symbol", "industry"],
    )
    candidates = [{"candidate_id": "aaa-3", "symbol": "AAA.SZ", "industry": "semi", "signal_date": "2026-05-03"}]
    exposure_rows = [
        {"candidate_id": "same-symbol-other-industry", "symbol": "AAA.SZ", "industry": "battery", "signal_date": "2026-05-02"},
        {"candidate_id": "same-group", "symbol": "AAA.SZ", "industry": "semi", "signal_date": "2026-05-02"},
    ]

    result = apply_shortpick_repeated_exposure_limit_control(candidates, exposure_rows, rule=rule)

    row = result["rows"][0]
    assert row["exposure_action"] == "blocked"
    assert row["exposure_group_key"] == "AAA.SZ|semi"
    assert [item["candidate_id"] for item in row["exposure_blocker_rows"]] == ["same-group"]


def test_repeated_exposure_limit_allows_missing_group_key() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule(max_prior_signals_per_group=0)
    candidates = [{"candidate_id": "missing-symbol", "signal_date": "2026-05-03"}]
    exposure_rows = [{"candidate_id": "prior", "symbol": "AAA.SZ", "signal_date": "2026-05-02"}]

    result = apply_shortpick_repeated_exposure_limit_control(candidates, exposure_rows, rule=rule)

    assert result["blocked_count"] == 0
    assert result["rows"][0]["exposure_action"] == "allowed"
    assert result["rows"][0]["exposure_group_key"] == ""


def test_historical_backtest_generation_requests_are_deterministic_and_read_only() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")

    first = build_shortpick_historical_backtest_generation_requests(
        [rule],
        start_date="2023-04-13",
        end_date="2026-05-08",
        entry_price_sources=["next_close"],
        horizon_days=10,
        cost_bps=20,
    )
    second = build_shortpick_historical_backtest_generation_requests(
        [rule],
        start_date="2023-04-13",
        end_date="2026-05-08",
        entry_price_sources=["next_close"],
        horizon_days=10,
        cost_bps=20,
    )

    assert first == second
    assert first["execution_policy"] == "request_plan_only_no_backtest_execution_no_data_write"
    assert first["paper_tracking_write_policy"] == "forbidden"
    assert first["true_forward_tracking_eligible"] is False
    request = first["requests"][0]
    assert request["request_id"].startswith("shortpick-historical-backtest-request:")
    assert request["evidence_basis"] == "historical_backtest"
    assert request["leakage_audit_status"] == "not_run"
    assert request["control_group_id"] == rule["control_group_id"]
    assert request["rule_signature"] == rule["rule_signature"]
    assert request["portfolio_strategies"] == ["control_same_symbol_cooldown_low_turnover_uptrend"]
    assert request["source_command"] == "shortpick-portfolio-backtest"
    assert "--output" in request["argv"]
    assert "output/shortpick-governance-backtests/" in request["output_path"]


def test_historical_backtest_generation_requests_expand_entry_sources() -> None:
    rule = build_shortpick_drawdown_reversal_filter_rule(rule_defined_at="2026-06-10")

    result = build_shortpick_historical_backtest_generation_requests(
        [rule],
        start_date="2023-04-13",
        end_date="2026-05-08",
        entry_price_sources=["next_close", "next_open"],
        benchmark_mode="csi300",
        account_profile="new_retail_cash_account",
        min_signal_symbol_count=1000,
    )

    assert result["request_count"] == 2
    entry_sources = [item["entry_price_source"] for item in result["requests"]]
    assert entry_sources == ["next_close", "next_open"]
    assert all(item["argv"][item["argv"].index("--benchmark-mode") + 1] == "csi300" for item in result["requests"])
    assert all(item["argv"][item["argv"].index("--min-signal-symbol-count") + 1] == "1000" for item in result["requests"])


def test_historical_backtest_generation_requests_attach_registered_p3_control_strategy_mappings() -> None:
    result = build_shortpick_historical_backtest_generation_requests(
        [
            build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10"),
            build_shortpick_drawdown_reversal_filter_rule(rule_defined_at="2026-06-10"),
            build_shortpick_repeated_exposure_limit_rule(rule_defined_at="2026-06-10"),
        ],
        start_date="2023-04-13",
        end_date="2026-05-08",
    )

    mappings = {item["control_group_id"]: item["portfolio_strategies"] for item in result["requests"]}

    assert mappings == {
        "control_same_symbol_cooldown:v1": ["control_same_symbol_cooldown_low_turnover_uptrend"],
        "control_drawdown_reversal_filter:v1": ["control_drawdown_reversal_low_turnover_uptrend"],
        "control_repeated_exposure_limit:v1": ["control_repeated_exposure_low_turnover_uptrend"],
    }


def test_historical_backtest_generation_requests_skip_rules_without_signature() -> None:
    result = build_shortpick_historical_backtest_generation_requests(
        [{"control_group_id": "control_without_signature"}],
        start_date="2023-04-13",
        end_date="2026-05-08",
    )

    assert result["status"] == "ready"
    assert result["request_count"] == 0
    assert result["requests"] == []


def test_historical_backtest_generation_requests_validate_inputs() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule()

    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        build_shortpick_historical_backtest_generation_requests([rule], start_date="2026-05-09", end_date="2026-05-08")

    with pytest.raises(ValueError, match="unsupported entry_price_sources"):
        build_shortpick_historical_backtest_generation_requests(
            [rule],
            start_date="2023-04-13",
            end_date="2026-05-08",
            entry_price_sources=["intraday_unknown"],
        )

    with pytest.raises(ValueError, match="horizon_days must be positive"):
        build_shortpick_historical_backtest_generation_requests(
            [rule],
            start_date="2023-04-13",
            end_date="2026-05-08",
            horizon_days=0,
        )

    with pytest.raises(ValueError, match="cost_bps must be non-negative"):
        build_shortpick_historical_backtest_generation_requests(
            [rule],
            start_date="2023-04-13",
            end_date="2026-05-08",
            cost_bps=-1,
        )


def test_retrospective_forward_replay_requests_derive_window_from_paper_tracking() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10T09:00:00+08:00")
    paper_tracking = {
        "items": [
            {"candidate_id": "a", "signal_date": "2026-05-08"},
            {"candidate_id": "b", "signal_date": "2026-05-10"},
            {"candidate_id": "c", "signal_date": "2026-06-10"},
            {"candidate_id": "d", "signal_date": "2026-06-11"},
        ]
    }

    result = build_shortpick_retrospective_forward_replay_requests(
        [rule],
        paper_tracking,
        generated_at="2026-06-10T12:00:00+08:00",
    )

    assert result["status"] == "ready"
    assert result["paper_tracking_observed_start_date"] == "2026-05-08"
    assert result["paper_tracking_observed_end_date"] == "2026-06-11"
    assert result["request_count"] == 1
    request = result["requests"][0]
    assert request["request_id"].startswith("shortpick-retrospective-forward-replay-request:")
    assert request["evidence_basis"] == "retrospective_forward_replay"
    assert request["retrospective"] is True
    assert request["true_forward_tracking_eligible"] is False
    assert request["paper_tracking_write_policy"] == "forbidden"
    assert request["leakage_audit_status"] == "not_run"
    assert request["replay_start_date"] == "2026-05-08"
    assert request["replay_end_date"] == "2026-05-10"
    assert request["source_signal_count"] == 2
    assert request["generated_at"] == "2026-06-10T12:00:00+08:00"


def test_retrospective_forward_replay_requests_block_rules_without_required_identity() -> None:
    result = build_shortpick_retrospective_forward_replay_requests(
        [
            {"control_group_id": "control_without_signature", "rule_defined_at": "2026-06-10"},
            {"control_group_id": "control_without_defined_at", "rule_signature": "sha256:test"},
        ],
        {"items": [{"signal_date": "2026-05-08"}]},
    )

    assert result["status"] == "blocked"
    assert result["request_count"] == 0
    blockers = [item["blocker"] for item in result["blocked_rules"]]
    assert blockers == ["missing_control_group_id_or_rule_signature", "missing_rule_defined_at"]


def test_retrospective_forward_replay_requests_block_when_no_prior_paper_dates() -> None:
    rule = build_shortpick_drawdown_reversal_filter_rule(rule_defined_at="2026-05-08")

    result = build_shortpick_retrospective_forward_replay_requests(
        [rule],
        {"items": [{"signal_date": "2026-05-08"}, {"signal_date": "2026-05-09"}]},
    )

    assert result["status"] == "blocked"
    assert result["request_count"] == 0
    assert result["blocked_rules"][0]["blocker"] == "no_paper_tracking_signal_dates_before_rule_defined_at"


def test_retrospective_forward_replay_requests_are_deterministic() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule(rule_defined_at="2026-06-10")
    paper_tracking = {"items": [{"signal_date": "2026-05-08"}, {"run_date": "2026-05-09"}]}

    first = build_shortpick_retrospective_forward_replay_requests([rule], paper_tracking)
    second = build_shortpick_retrospective_forward_replay_requests([rule], paper_tracking)

    assert first == second
    assert first["execution_policy"] == "request_plan_only_no_replay_execution_no_data_write"


def _ranked_replay_paper_tracking_fixture() -> dict[str, object]:
    return {
        "items": [
            {"candidate_id": "loss", "signal_date": "2026-05-20", "symbol": "002028.SZ"},
            {"candidate_id": "blocked", "signal_date": "2026-05-26", "symbol": "002028.SZ"},
        ],
        "ranked_candidate_pools": [
            {
                "signal_date": "2026-05-20",
                "candidates": [
                    {
                        "candidate_id": "loss",
                        "signal_date": "2026-05-20",
                        "symbol": "002028.SZ",
                        "name": "思源电气",
                        "candidate_rank": 1,
                        "validation_by_horizon": [
                            {
                                "horizon_days": 10,
                                "status": "completed",
                                "stock_return": -0.09,
                                "exit_date": "2026-05-24",
                            }
                        ],
                    }
                ],
            },
            {
                "signal_date": "2026-05-26",
                "candidates": [
                    {
                        "candidate_id": "blocked",
                        "signal_date": "2026-05-26",
                        "symbol": "002028.SZ",
                        "name": "思源电气",
                        "candidate_rank": 1,
                    },
                    {
                        "candidate_id": "fallback",
                        "signal_date": "2026-05-26",
                        "symbol": "300750.SZ",
                        "name": "宁德时代",
                        "candidate_rank": 2,
                    },
                ],
            },
        ],
    }


def test_retrospective_forward_replay_runner_applies_same_symbol_cooldown_and_prepares_rows() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
    paper_tracking = _ranked_replay_paper_tracking_fixture()
    request = build_shortpick_retrospective_forward_replay_requests(
        [rule],
        paper_tracking,
        generated_at="2026-06-10T12:00:00+08:00",
    )["requests"][0]

    replay = run_shortpick_retrospective_forward_replay_request(request, paper_tracking)

    assert replay["status"] == "ready"
    assert replay["evidence_basis"] == "retrospective_forward_replay"
    assert replay["retrospective"] is True
    assert replay["paper_tracking_write_policy"] == "forbidden"
    assert replay["true_forward_tracking_eligible"] is False
    assert replay["selection_policy"] == "filter_ranked_pool_select_first_allowed"
    assert replay["input_candidate_count"] == 3
    rows_by_id = {row["candidate_id"]: row for row in replay["rows"]}
    assert rows_by_id["loss"]["cooldown_action"] == "allowed"
    assert "blocked" not in rows_by_id
    assert rows_by_id["fallback"]["cooldown_action"] == "allowed"
    assert rows_by_id["fallback"]["candidate_rank"] == 2
    assert rows_by_id["fallback"]["blocked_higher_ranked_candidates"][0]["candidate_id"] == "blocked"
    assert rows_by_id["fallback"]["leakage_audit_status"] == "passed"
    assert rows_by_id["fallback"]["rule_defined_at"] == "2026-06-10"
    assert rows_by_id["fallback"]["pairing_key"] == (
        f"control_same_symbol_cooldown:v1|{rule['rule_signature']}|300750.SZ|2026-05-26"
    )

    prepared = build_shortpick_combined_ledger_retrospective_backfill(
        replay["rows"],
        replay_request=request,
        source_artifact_ref="output/replay.json",
    )
    assert prepared["status"] == "ready"
    assert prepared["retrospective_count"] == 2
    assert all(row["evidence_basis"] == "retrospective_forward_replay" for row in prepared["retrospective_rows"])


def test_retrospective_forward_replay_runner_uses_ranked_candidate_features_for_drawdown_reselect() -> None:
    rule = build_shortpick_drawdown_reversal_filter_rule(rule_defined_at="2026-06-10")
    paper_tracking = {
        "items": [{"candidate_id": "frozen", "signal_date": "2026-05-26", "symbol": "002028.SZ"}],
        "ranked_candidate_pools": [
            {
                "signal_date": "2026-05-26",
                "candidates": [
                    {
                        "candidate_id": "rank1",
                        "signal_date": "2026-05-26",
                        "symbol": "002028.SZ",
                        "candidate_rank": 1,
                        "drawdown_reversal_features": {
                            "feature_date": "2026-05-26",
                            "recent_drawdown_return": -0.09,
                        },
                    },
                    {
                        "candidate_id": "rank2",
                        "signal_date": "2026-05-26",
                        "symbol": "300750.SZ",
                        "candidate_rank": 2,
                        "drawdown_reversal_features": {
                            "feature_date": "2026-05-26",
                            "recent_drawdown_return": -0.01,
                            "short_window_return": 0.02,
                            "price_vs_ma20": 0.03,
                        },
                    },
                ],
            }
        ],
    }
    request = build_shortpick_retrospective_forward_replay_requests(
        [rule],
        paper_tracking,
        generated_at="2026-06-10T12:00:00+08:00",
    )["requests"][0]

    replay = run_shortpick_retrospective_forward_replay_request(request, paper_tracking)

    assert replay["status"] == "ready"
    assert replay["selection_policy"] == "filter_ranked_pool_select_first_allowed"
    assert replay["replay_row_count"] == 1
    selected = replay["rows"][0]
    assert selected["candidate_id"] == "rank2"
    assert selected["candidate_rank"] == 2
    assert selected["filter_action"] == "allowed"
    assert selected["blocked_higher_ranked_candidates"][0]["candidate_id"] == "rank1"
    assert selected["blocked_higher_ranked_candidates"][0]["filter_action"] == "blocked"


def test_retrospective_forward_replay_runner_blocks_windows_that_reach_rule_date() -> None:
    request = {
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "control_group_id": "control_same_symbol_cooldown:v1",
        "rule_signature": "sha256:test",
        "rule_defined_at": "2026-06-10",
        "replay_start_date": "2026-05-08",
        "replay_end_date": "2026-06-10",
    }

    replay = run_shortpick_retrospective_forward_replay_request(
        request,
        {"items": [{"candidate_id": "a", "signal_date": "2026-05-08", "symbol": "002028.SZ"}]},
    )

    assert replay["status"] == "blocked"
    assert replay["blocker"] == "replay_window_must_end_before_rule_defined_at"
    assert replay["leakage_audit_status"] == "blocked"


def test_retrospective_forward_replay_runner_rejects_true_forward_or_headline_tampering() -> None:
    request = {
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "control_group_id": "control_same_symbol_cooldown:v1",
        "rule_signature": "sha256:test",
        "rule_defined_at": "2026-06-10",
        "replay_start_date": "2026-05-08",
        "replay_end_date": "2026-05-31",
        "true_forward_tracking_eligible": True,
    }

    replay = run_shortpick_retrospective_forward_replay_request(
        request,
        {"items": [{"candidate_id": "a", "signal_date": "2026-05-20", "symbol": "002028.SZ"}]},
    )

    assert replay["status"] == "blocked"
    assert replay["blocker"] == "request_must_not_be_true_forward_eligible"
    assert replay["paper_tracking_write_policy"] == "forbidden"
    assert replay["true_forward_tracking_eligible"] is False

    headline_replay = run_shortpick_retrospective_forward_replay_request(
        {**request, "true_forward_tracking_eligible": False, "headline_metric_eligible": True},
        {"items": [{"candidate_id": "a", "signal_date": "2026-05-20", "symbol": "002028.SZ"}]},
    )

    assert headline_replay["status"] == "blocked"
    assert headline_replay["blocker"] == "request_must_not_be_headline_metric_eligible"


def test_retrospective_forward_replay_runner_limits_cooldown_auxiliary_rows_to_replay_scope() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
    request = {
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "control_group_id": rule["control_group_id"],
        "rule": rule,
        "rule_signature": rule["rule_signature"],
        "rule_defined_at": "2026-06-10",
        "replay_start_date": "2026-05-20",
        "replay_end_date": "2026-05-31",
    }
    paper_tracking = {
        "items": [
            {
                "candidate_id": "before-window-loss",
                "signal_date": "2026-05-10",
                "symbol": "002028.SZ",
                "validation_by_horizon": [
                    {"horizon_days": 10, "status": "completed", "stock_return": -0.12, "exit_date": "2026-05-24"}
                ],
            },
            {"candidate_id": "inside-window-candidate", "signal_date": "2026-05-26", "symbol": "002028.SZ"},
        ],
        "ranked_candidate_pools": [
            {
                "signal_date": "2026-05-26",
                "candidates": [
                    {
                        "candidate_id": "inside-window-candidate",
                        "signal_date": "2026-05-26",
                        "symbol": "002028.SZ",
                        "candidate_rank": 1,
                    }
                ],
            }
        ],
    }

    replay = run_shortpick_retrospective_forward_replay_request(request, paper_tracking)

    assert replay["status"] == "ready"
    assert replay["input_candidate_count"] == 1
    row = replay["rows"][0]
    assert row["candidate_id"] == "inside-window-candidate"
    assert row["cooldown_action"] == "allowed"
    assert row["cooldown_blocker_events"] == []


def test_retrospective_forward_replay_runner_limits_drawdown_features_to_replay_scope() -> None:
    rule = build_shortpick_drawdown_reversal_filter_rule(rule_defined_at="2026-06-10")
    request = {
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "control_group_id": rule["control_group_id"],
        "rule": rule,
        "rule_signature": rule["rule_signature"],
        "rule_defined_at": "2026-06-10",
        "replay_start_date": "2026-05-20",
        "replay_end_date": "2026-05-31",
    }
    paper_tracking = {
        "items": [
            {
                "candidate_id": "before-window-feature",
                "signal_date": "2026-05-10",
                "symbol": "002028.SZ",
                "drawdown_reversal_features": {
                    "feature_date": "2026-05-10",
                    "recent_drawdown_return": -0.20,
                },
            },
            {"candidate_id": "inside-window-candidate", "signal_date": "2026-05-26", "symbol": "002028.SZ"},
        ],
        "ranked_candidate_pools": [
            {
                "signal_date": "2026-05-26",
                "candidates": [
                    {
                        "candidate_id": "inside-window-candidate",
                        "signal_date": "2026-05-26",
                        "symbol": "002028.SZ",
                        "candidate_rank": 1,
                    }
                ],
            }
        ],
    }

    replay = run_shortpick_retrospective_forward_replay_request(request, paper_tracking)

    assert replay["status"] == "ready"
    assert replay["input_candidate_count"] == 1
    row = replay["rows"][0]
    assert row["candidate_id"] == "inside-window-candidate"
    assert row["filter_action"] == "allowed"
    assert row["feature_coverage_status"] == "missing"


def test_combined_ledger_backfill_writer_materializes_labeled_replay_rows() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
    paper_tracking = _ranked_replay_paper_tracking_fixture()
    request = build_shortpick_retrospective_forward_replay_requests([rule], paper_tracking)["requests"][0]
    replay = run_shortpick_retrospective_forward_replay_request(request, paper_tracking)

    artifact = run_shortpick_combined_ledger_backfill_artifact(
        [replay],
        true_forward_rows=[
            {
                "candidate_id": "live",
                "signal_date": "2026-06-11",
                "symbol": "002028.SZ",
                "control_group_id": rule["control_group_id"],
                "rule_signature": rule["rule_signature"],
            }
        ],
        generated_at="2026-06-11T12:00:00+08:00",
    )

    assert artifact["status"] == "ready"
    assert artifact["write_policy"] == "artifact_only_no_database_or_paper_tracking_write"
    assert artifact["true_forward_count"] == 1
    assert artifact["retrospective_count"] == 2
    assert artifact["combined_row_count"] == 3
    retrospective_rows = artifact["retrospective_rows"]
    assert all(row["evidence_basis"] == "retrospective_forward_replay" for row in retrospective_rows)
    assert all(row["retrospective"] is True for row in retrospective_rows)
    assert all(row["headline_metric_eligible"] is False for row in retrospective_rows)
    assert all(row["source_artifact_ref"].startswith("shortpick-retrospective-forward-replay:") for row in retrospective_rows)
    assert artifact["true_forward_rows"][0]["evidence_basis"] == "true_forward_tracking"


def test_combined_ledger_discovery_reads_only_ready_governance_replay_artifacts() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
    ready = _ready_retrospective_replay_artifact(rule, artifact_id="shortpick-retrospective-forward-replay:ready")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        replay_dir = root / "shortpick_retrospective_replays"
        replay_dir.mkdir()
        (replay_dir / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
        (replay_dir / "blocked.json").write_text(
            json.dumps({**ready, "artifact_id": "blocked", "status": "blocked"}),
            encoding="utf-8",
        )
        (replay_dir / "wrong-basis.json").write_text(
            json.dumps({**ready, "artifact_id": "wrong-basis", "evidence_basis": "historical_backtest"}),
            encoding="utf-8",
        )
        (replay_dir / "z-duplicate.json").write_text(json.dumps(ready), encoding="utf-8")
        legacy_dir = root / "replays"
        legacy_dir.mkdir()
        (legacy_dir / "old-replay-alignment.json").write_text(
            json.dumps({"artifact_type": "replay_alignment", "status": "ready", "rows": [{}]}),
            encoding="utf-8",
        )
        (legacy_dir / "broken.json").write_text("{", encoding="utf-8")

        discovery = discover_shortpick_retrospective_forward_replay_artifacts(root=root)

    assert discovery["artifact_count"] == 1
    assert discovery["artifacts"][0]["artifact_id"] == "shortpick-retrospective-forward-replay:ready"
    assert discovery["artifacts"][0]["artifact"]["path"].endswith("ready.json")
    reasons = [item["reason"] for item in discovery["ignored"]]
    assert reasons.count("not_ready_retrospective_forward_replay_artifact") == 3
    assert reasons.count("duplicate_artifact_id") == 1
    assert any(reason.startswith("unreadable_json:") for reason in reasons)


def test_combined_ledger_materializer_writes_runtime_artifact_from_discovery_root() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
    ready = _ready_retrospective_replay_artifact(rule)
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        replay_dir = root / "shortpick_retrospective_replays"
        replay_dir.mkdir()
        (replay_dir / "ready.json").write_text(json.dumps(ready), encoding="utf-8")

        payload = materialize_shortpick_combined_ledger_from_artifact_root(
            root=root,
            generated_at="2026-06-11T12:00:00+08:00",
        )
        source = read_shortpick_combined_ledger_backfill_artifacts(root=root)

    assert payload["status"] == "ready"
    assert payload["artifact"]["path"].endswith(".json")
    assert payload["source_discovery"]["artifact_count"] == 1
    assert payload["retrospective_count"] == 1
    assert source["artifact_count"] == 1
    assert source["artifacts"][0]["artifact_id"] == payload["artifact_id"]
    assert source["artifacts"][0]["combined_rows"][0]["evidence_basis"] == "retrospective_forward_replay"


def test_true_forward_tracking_activation_plan_starts_no_earlier_than_rule_definition() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10T09:00:00+08:00")

    result = build_shortpick_true_forward_tracking_activation_plan(
        [rule],
        tracking_started_at="2026-06-09T15:00:00+08:00",
        generated_at="2026-06-10T12:00:00+08:00",
    )

    assert result["status"] == "ready"
    assert result["evidence_basis"] == "true_forward_tracking"
    assert result["retrospective"] is False
    assert result["retroactive_backfill_allowed"] is False
    assert result["execution_policy"] == "activation_plan_only_no_tracking_execution_no_data_write"
    assert result["paper_tracking_write_policy"] == "not_written_by_plan_runtime_wiring_required"
    activation = result["activations"][0]
    assert activation["activation_id"].startswith("shortpick-true-forward-activation:")
    assert activation["tracking_start_requested_at"] == "2026-06-09"
    assert activation["tracking_start_date"] == "2026-06-10"
    assert activation["true_forward_tracking_eligible"] is True
    assert activation["retrospective"] is False
    assert activation["retroactive_backfill_allowed"] is False
    assert activation["forbidden_signal_date_policy"] == "do_not_write_rows_before_tracking_start_date"
    assert activation["generated_at"] == "2026-06-10T12:00:00+08:00"


def test_true_forward_tracking_activation_plan_blocks_missing_identity_and_defined_at() -> None:
    result = build_shortpick_true_forward_tracking_activation_plan(
        [
            {"control_group_id": "control_same_symbol_cooldown:v1", "rule_defined_at": "2026-06-10"},
            {"control_group_id": "control_drawdown_reversal_filter:v1", "rule_signature": "sha256:test"},
        ],
        tracking_started_at="2026-06-10",
    )

    assert result["status"] == "blocked"
    assert result["activation_count"] == 0
    assert [item["blocker"] for item in result["blocked_rules"]] == [
        "missing_control_group_id_or_rule_signature",
        "missing_rule_defined_at",
    ]


def test_true_forward_tracking_activation_plan_blocks_unregistered_controls() -> None:
    result = build_shortpick_true_forward_tracking_activation_plan(
        [
            {
                "control_group_id": "control_not_registered:v1",
                "rule_signature": "sha256:test",
                "rule_defined_at": "2026-06-10",
            }
        ],
        tracking_started_at="2026-06-10",
    )

    assert result["status"] == "blocked"
    assert result["blocked_rule_count"] == 1
    assert result["blocked_rules"][0]["blocker"] == "unregistered_control_group_id"


def test_true_forward_tracking_activation_plan_is_deterministic_and_validates_inputs() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule(rule_defined_at="2026-06-10")

    first = build_shortpick_true_forward_tracking_activation_plan([rule], tracking_started_at="2026-06-11")
    second = build_shortpick_true_forward_tracking_activation_plan([rule], tracking_started_at="2026-06-11")

    assert first == second
    assert first["activations"][0]["tracking_start_date"] == "2026-06-11"
    assert "control_repeated_exposure_limit:v1" in first["registered_control_group_ids"]

    with pytest.raises(ValueError, match="tracking_started_at must include a date"):
        build_shortpick_true_forward_tracking_activation_plan([rule], tracking_started_at="")

    with pytest.raises(ValueError, match="artifact_family_id must be non-empty"):
        build_shortpick_true_forward_tracking_activation_plan([rule], tracking_started_at="2026-06-11", artifact_family_id="")


def test_combined_ledger_retrospective_backfill_labels_rows_and_pairing_key() -> None:
    replay_request = {
        "control_group_id": "control_same_symbol_cooldown:v1",
        "rule_signature": "sha256:cooldown",
        "rule_defined_at": "2026-06-10T09:00:00+08:00",
        "source_feature_cutoff_policy": "signal_date_available_inputs_only",
        "leakage_audit_status": "passed",
        "leakage_audit_reasons": [],
    }
    true_forward = {
        "signal_date": "2026-06-11",
        "symbol": "002028.SZ",
        "control_group_id": "control_same_symbol_cooldown:v1",
        "rule_signature": "sha256:cooldown",
        "tracking_group": "market_factor_control",
    }
    retrospective = {
        "signal_date": "2026-05-26",
        "symbol": "002028.SZ",
        "name": "思源电气",
        "tracking_group": "market_factor_control",
        "validation_by_horizon": [{"horizon_days": 10, "status": "completed", "stock_return": 0.05}],
    }

    result = build_shortpick_combined_ledger_retrospective_backfill(
        [retrospective],
        true_forward_rows=[true_forward],
        replay_request=replay_request,
        generated_at="2026-06-11T10:00:00+08:00",
        source_artifact_ref="output/shortpick/replay/control_same_symbol_cooldown.json",
    )

    assert result["status"] == "ready"
    assert result["write_policy"] == "prepared_rows_only_no_database_write_without_runtime_writer"
    assert result["headline_metric_filter_policy"] == "true_forward_queries_must_filter_evidence_basis_true_forward_tracking"
    assert result["true_forward_count"] == 1
    assert result["retrospective_count"] == 1
    assert result["combined_row_count"] == 2
    retro_row = result["retrospective_rows"][0]
    assert retro_row["evidence_basis"] == "retrospective_forward_replay"
    assert retro_row["retrospective"] is True
    assert retro_row["true_forward_tracking_eligible"] is False
    assert retro_row["headline_metric_eligible"] is False
    assert retro_row["rule_defined_at"] == "2026-06-10"
    assert retro_row["leakage_audit_status"] == "passed"
    assert retro_row["source_feature_cutoff_policy"] == "signal_date_available_inputs_only"
    assert retro_row["pairing_key"] == "control_same_symbol_cooldown:v1|sha256:cooldown|002028.SZ|2026-05-26"
    assert retro_row["pairing_key_basis"] == "control_group_id__rule_signature__symbol__signal_date"
    assert retro_row["combined_ledger_row_id"].startswith("shortpick-combined-ledger-retrospective:")
    assert retro_row["source_artifact_ref"] == "output/shortpick/replay/control_same_symbol_cooldown.json"

    true_forward_row = result["true_forward_rows"][0]
    assert true_forward_row["evidence_basis"] == "true_forward_tracking"
    assert true_forward_row["retrospective"] is False
    assert true_forward_row["true_forward_tracking_eligible"] is True
    assert true_forward_row["combined_ledger_row_id"].startswith("shortpick-combined-ledger-true-forward:")


def test_combined_ledger_backfill_blocks_missing_identity_and_future_replay_rows() -> None:
    result = build_shortpick_combined_ledger_retrospective_backfill(
        [
            {"signal_date": "2026-05-26", "symbol": "002028.SZ"},
            {
                "signal_date": "2026-06-10",
                "symbol": "002028.SZ",
                "control_group_id": "control_same_symbol_cooldown:v1",
                "rule_signature": "sha256:cooldown",
                "rule_defined_at": "2026-06-10",
            },
            {
                "signal_date": "2026-05-26",
                "symbol": "002028.SZ",
                "control_group_id": "control_same_symbol_cooldown:v1",
                "rule_signature": "sha256:cooldown",
                "rule_defined_at": "2026-06-10",
                "leakage_audit_status": "unchecked",
            },
        ]
    )

    assert result["status"] == "blocked"
    assert result["retrospective_count"] == 0
    assert [item["blocker"] for item in result["blocked_rows"]] == [
        "missing_required_combined_ledger_identity",
        "retrospective_signal_date_not_before_rule_defined_at",
        "unsupported_leakage_audit_status",
    ]
    assert result["blocked_rows"][0]["missing_fields"] == [
        "control_group_id",
        "rule_signature",
        "rule_defined_at",
    ]


def test_combined_ledger_basis_filter_defaults_to_true_forward_headline_rows() -> None:
    result = build_shortpick_combined_ledger_retrospective_backfill(
        [
            {
                "signal_date": "2026-05-26",
                "symbol": "002028.SZ",
                "control_group_id": "control_same_symbol_cooldown:v1",
                "rule_signature": "sha256:cooldown",
                "rule_defined_at": "2026-06-10",
            }
        ],
        true_forward_rows=[
            {
                "signal_date": "2026-06-11",
                "symbol": "002028.SZ",
                "control_group_id": "control_same_symbol_cooldown:v1",
                "rule_signature": "sha256:cooldown",
            }
        ],
    )

    filtered = filter_shortpick_combined_ledger_rows_by_evidence_basis(result["combined_rows"])

    assert filtered["evidence_basis"] == "true_forward_tracking"
    assert filtered["selected_count"] == 1
    assert filtered["excluded_count"] == 1
    assert filtered["excluded_basis_counts"] == {"retrospective_forward_replay": 1}
    assert filtered["rows"][0]["retrospective"] is False


def test_combined_ledger_basis_filter_rejects_unknown_basis() -> None:
    with pytest.raises(ValueError, match="unsupported shortpick combined-ledger evidence_basis"):
        filter_shortpick_combined_ledger_rows_by_evidence_basis([], evidence_basis="mixed")


def test_combined_ledger_backfill_empty_inputs_are_explicitly_blocked() -> None:
    result = build_shortpick_combined_ledger_retrospective_backfill([])

    assert result["status"] == "blocked"
    assert result["true_forward_count"] == 0
    assert result["retrospective_count"] == 0
    assert result["combined_row_count"] == 0
    assert result["blocked_row_count"] == 0
    assert result["write_policy"] == "prepared_rows_only_no_database_write_without_runtime_writer"


def test_combined_ledger_backfill_blocks_non_true_forward_basis_in_true_forward_inputs() -> None:
    result = build_shortpick_combined_ledger_retrospective_backfill(
        [],
        true_forward_rows=[
            {
                "signal_date": "2026-06-11",
                "symbol": "002028.SZ",
                "control_group_id": "control_same_symbol_cooldown:v1",
                "rule_signature": "sha256:cooldown",
                "evidence_basis": "retrospective_forward_replay",
            }
        ],
    )

    assert result["status"] == "blocked"
    assert result["true_forward_count"] == 0
    assert result["blocked_row_count"] == 1
    assert result["blocked_rows"][0]["blocker"] == "true_forward_input_row_has_non_true_forward_basis"


def test_credible_control_comparison_line_plan_generates_three_registered_lines_with_backtest_gate() -> None:
    paper_tracking = {
        "items": [
            {"candidate_id": "a", "symbol": "002028.SZ", "signal_date": "2026-05-26"},
            {"candidate_id": "b", "symbol": "300750.SZ", "signal_date": "2026-05-27"},
        ]
    }

    result = build_shortpick_credible_control_comparison_line_plan(
        paper_tracking,
        rule_defined_at="2026-06-11T09:00:00+08:00",
        generated_at="2026-06-11T10:00:00+08:00",
    )

    assert result["status"] == "blocked"
    assert result["comparison_line_policy"] == "historical_backtest_gate_before_retrospective_backfill"
    assert result["paper_tracking_write_policy"] == "plan_only_no_backfill_rows_written"
    assert result["runtime_dependency_status"] == "runner_and_writer_required_before_rows_exist"
    assert result["line_count"] == 3
    assert result["ready_line_count"] == 0
    assert result["blocked_line_count"] == 3
    assert result["baseline_ids"] == [
        "evaluation_baseline_cooldown_control:v1",
        "evaluation_baseline_random_pool:v1",
    ]
    assert result["historical_backtest_plan"]["request_count"] == 3
    assert result["retrospective_replay_plan"]["request_count"] == 3
    assert result["true_forward_activation_plan"]["activation_count"] == 3
    assert result["historical_backtest_plan"]["requests"][0]["end_date"] == "2026-05-25"

    control_ids = [line["control_group_id"] for line in result["lines"]]
    assert control_ids == [
        "control_same_symbol_cooldown:v1",
        "control_drawdown_reversal_filter:v1",
        "control_repeated_exposure_limit:v1",
    ]
    assert all(line["line_id"].startswith("shortpick-credible-control-line:") for line in result["lines"])
    assert all(line["paper_tracking_backfill_policy"] == "blocked_until_historical_backtest_gate_passes" for line in result["lines"])
    assert all(line["historical_backtest_gate"]["blockers"] == ["historical_backtest_evidence_missing"] for line in result["lines"])
    assert all(line["retrospective_replay_request_id"] for line in result["lines"])
    assert all(line["true_forward_activation_id"] for line in result["lines"])


def test_credible_control_comparison_line_plan_allows_backfill_only_after_passed_historical_gate() -> None:
    paper_tracking = {"items": [{"candidate_id": "a", "symbol": "002028.SZ", "signal_date": "2026-05-26"}]}
    blocked = build_shortpick_credible_control_comparison_line_plan(
        paper_tracking,
        rule_defined_at="2026-06-11",
    )
    first_line = blocked["lines"][0]

    passed = build_shortpick_credible_control_comparison_line_plan(
        paper_tracking,
        rule_defined_at="2026-06-11",
        historical_backtest_evidence={
            first_line["rule_signature"]: {
                "status": "ready",
                "evidence_basis": "historical_backtest",
                "gate_status": "passed",
                "leakage_audit_status": "passed",
                "artifact_id": "hist-pass",
            }
        },
    )

    assert passed["status"] == "ready"
    assert passed["ready_line_count"] == 1
    by_control = {line["control_group_id"]: line for line in passed["lines"]}
    ready_line = by_control[first_line["control_group_id"]]
    assert ready_line["status"] == "ready_for_retrospective_backfill"
    assert ready_line["historical_backtest_gate"]["gate_status"] == "passed"
    assert ready_line["historical_backtest_gate"]["evidence_ref"]["artifact_id"] == "hist-pass"
    assert ready_line["paper_tracking_backfill_policy"] == "allowed_after_historical_backtest_gate_passed"
    assert ready_line["blockers"] == []

    blocked_lines = [line for line in passed["lines"] if line["control_group_id"] != first_line["control_group_id"]]
    assert [line["status"] for line in blocked_lines] == [
        "blocked_pending_historical_backtest",
        "blocked_pending_historical_backtest",
    ]


def test_credible_control_comparison_line_plan_accepts_runner_evidence_aggregate() -> None:
    paper_tracking = {"items": [{"candidate_id": "a", "symbol": "002028.SZ", "signal_date": "2026-05-26"}]}
    blocked = build_shortpick_credible_control_comparison_line_plan(
        paper_tracking,
        rule_defined_at="2026-06-11",
    )
    first_line = blocked["lines"][0]

    passed = build_shortpick_credible_control_comparison_line_plan(
        paper_tracking,
        rule_defined_at="2026-06-11",
        historical_backtest_evidence={
            "status": "ready",
            "evidence_basis": "historical_backtest",
            "evidence": [
                {
                    "status": "ready",
                    "evidence_basis": "historical_backtest",
                    "gate_status": "passed",
                    "leakage_audit_status": "passed",
                    "artifact_id": "hist-aggregate-pass",
                    "control_group_id": first_line["control_group_id"],
                    "rule_signature": first_line["rule_signature"],
                }
            ],
        },
    )

    ready_line = next(line for line in passed["lines"] if line["control_group_id"] == first_line["control_group_id"])
    assert ready_line["status"] == "ready_for_retrospective_backfill"
    assert ready_line["historical_backtest_gate"]["gate_status"] == "passed"
    assert ready_line["historical_backtest_gate"]["evidence_ref"]["artifact_id"] == "hist-aggregate-pass"


def test_credible_control_comparison_line_plan_rejects_unregistered_baseline_ids() -> None:
    with pytest.raises(ValueError, match="unsupported shortpick evaluation baseline ids"):
        build_shortpick_credible_control_comparison_line_plan(
            {"items": [{"signal_date": "2026-05-26"}]},
            rule_defined_at="2026-06-11",
            baseline_ids=["unregistered_baseline:v1"],
        )


def test_credible_control_comparison_line_plan_requires_explicit_historical_evidence_basis() -> None:
    blocked = build_shortpick_credible_control_comparison_line_plan(
        {"items": [{"candidate_id": "a", "symbol": "002028.SZ", "signal_date": "2026-05-26"}]},
        rule_defined_at="2026-06-11",
    )
    first_line = blocked["lines"][0]

    result = build_shortpick_credible_control_comparison_line_plan(
        {"items": [{"candidate_id": "a", "symbol": "002028.SZ", "signal_date": "2026-05-26"}]},
        rule_defined_at="2026-06-11",
        historical_backtest_evidence={
            first_line["rule_signature"]: {
                "status": "ready",
                "gate_status": "passed",
                "leakage_audit_status": "passed",
            }
        },
    )

    gated_line = result["lines"][0]
    assert gated_line["status"] == "blocked_pending_historical_backtest"
    assert "historical_backtest_evidence_basis_mismatch" in gated_line["historical_backtest_gate"]["blockers"]


def test_credible_control_comparison_line_plan_requires_rule_defined_at() -> None:
    with pytest.raises(ValueError, match="rule_defined_at must include a date"):
        build_shortpick_credible_control_comparison_line_plan({"items": []}, rule_defined_at="")


# --- Round 27 hardening: status-recommendation follow-ups (Round 6) ---


_RETIRE_CANDIDATE_RETURNS = [-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02]
_RETIRE_CANDIDATE_HISTORICAL = {
    "low_turnover_20d_uptrend_liquid_top120": {
        "status": "ready",
        "after_cost_excess_return": -0.03,
    }
}


def test_status_recommendation_positive_registered_baseline_gap_blocks_retire_candidate() -> None:
    # Same weak-but-mature evidence that otherwise yields retire_candidate, but the
    # registered baseline gap is non-negative, so the baseline gate must block.
    evidence = _evidence_from_returns(
        _RETIRE_CANDIDATE_RETURNS,
        historical_evidence=_RETIRE_CANDIDATE_HISTORICAL,
        baseline_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "mean_excess_return_gap": 0.02,
            }
        },
    )

    recommendation = build_shortpick_strategy_status_recommendations(evidence)["recommendations"][0]

    assert recommendation["recommended_status"] == "observe"
    assert recommendation["blockers"] == ["registered_baseline_gap_not_negative"]
    assert "registered_baseline_gap_negative" not in recommendation["reasons"]


def test_status_recommendation_mixed_positive_mean_negative_median_is_tail_dependent_retire_candidate() -> None:
    # A single large winner lifts the mean above zero while the median stays negative;
    # the tail-dependence path should still trigger retire_candidate, not active.
    evidence = _evidence_from_returns(
        [0.50, -0.02, -0.03, -0.01, -0.04, -0.02, -0.03, -0.01, -0.02, -0.05],
        historical_evidence=_RETIRE_CANDIDATE_HISTORICAL,
    )

    recommendation = build_shortpick_strategy_status_recommendations(evidence)["recommendations"][0]
    horizon = recommendation["primary_horizon_summary"]

    assert recommendation["recommended_status"] == "retire_candidate"
    assert recommendation["blockers"] == []
    assert horizon["mean_stock_return"] == 0.027
    assert horizon["median_stock_return"] == -0.02
    assert horizon["tail_dependency"]["tail_dependent"] is True
    assert "forward_mean_negative_or_tail_dependent" in recommendation["reasons"]


def test_status_recommendation_incomplete_retirement_artifact_cannot_retire() -> None:
    # An artifact that is present but missing decision_log_ref lacks retirement authority,
    # so the status must fall back to metric-driven retire_candidate, never retired.
    evidence = _evidence_from_returns(
        _RETIRE_CANDIDATE_RETURNS,
        historical_evidence=_RETIRE_CANDIDATE_HISTORICAL,
        baseline_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "mean_excess_return_gap": -0.02,
            }
        },
    )
    strategy_id = evidence["packs"][0]["strategy_id"]

    recommendation = build_shortpick_strategy_status_recommendations(
        evidence,
        retirement_artifacts={
            strategy_id: {
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "artifact_id": "incomplete-fixture",
                # decision_log_ref deliberately omitted
            }
        },
    )["recommendations"][0]

    assert recommendation["recommended_status"] == "retire_candidate"
    assert recommendation["retirement_artifact_ref"] is None
    assert "strategy_retirement_artifact_and_decision_log_ref_present" not in recommendation["reasons"]


def test_status_recommendation_resolves_retirement_artifact_from_list_form_source() -> None:
    evidence = _evidence_from_returns(
        _RETIRE_CANDIDATE_RETURNS,
        historical_evidence=_RETIRE_CANDIDATE_HISTORICAL,
    )
    strategy_id = evidence["packs"][0]["strategy_id"]

    recommendation = build_shortpick_strategy_status_recommendations(
        evidence,
        retirement_artifacts={
            "artifacts": [
                {
                    "strategy_id": strategy_id,
                    "status": "ready",
                    "artifact_family": "strategy_retirement:v1",
                    "artifact_id": "list-form-fixture",
                    "decision_log_ref": "DECISIONS.md#2026-06-10-list-form",
                }
            ]
        },
    )["recommendations"][0]

    assert recommendation["recommended_status"] == "retired"
    assert recommendation["retirement_artifact_ref"]["artifact_id"] == "list-form-fixture"


def test_status_recommendation_handles_empty_or_missing_packs() -> None:
    empty = build_shortpick_strategy_status_recommendations({"packs": []})
    assert empty["status"] == "ready"
    assert empty["strategy_count"] == 0
    assert empty["recommendations"] == []

    missing = build_shortpick_strategy_status_recommendations({})
    assert missing["strategy_count"] == 0
    assert missing["recommendations"] == []


def test_status_recommendation_falls_back_to_first_horizon_when_primary_horizon_absent() -> None:
    # The evidence only carries a 10-day horizon; asking for a 40-day primary horizon
    # must fall back to the first available summary instead of dropping to observe.
    evidence = _evidence_from_returns([0.02, 0.03, 0.01, 0.04, 0.02])

    recommendation = build_shortpick_strategy_status_recommendations(
        evidence,
        primary_horizon_days=40,
    )["recommendations"][0]

    assert recommendation["primary_horizon_days"] == 40
    assert recommendation["primary_horizon_summary"]["horizon_days"] == 10
    assert recommendation["recommended_status"] == "active"


# --- Round 27 hardening: same-symbol cooldown follow-ups (Round 10) ---


def test_same_symbol_cooldown_handles_empty_inputs() -> None:
    result = apply_shortpick_same_symbol_cooldown_control([], [])

    assert result["status"] == "ready"
    assert result["rows"] == []
    assert result["input_candidate_count"] == 0
    assert result["blocked_count"] == 0
    assert result["allowed_count"] == 0
    assert result["ignored_future_or_same_day_outcome_count"] == 0
    assert result["rule_signature"].startswith("sha256:")


def test_same_symbol_cooldown_uses_default_rule_when_none_provided() -> None:
    candidates = [{"candidate_id": "aaa-1", "symbol": "AAA.SZ", "signal_date": "2026-05-05"}]
    outcomes = [
        {
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-04",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.03,
        }
    ]

    result = apply_shortpick_same_symbol_cooldown_control(candidates, outcomes)

    assert result["control_group_id"] == SAME_SYMBOL_COOLDOWN_CONTROL_ID
    assert result["rule"]["cooldown_signal_days"] == 5
    assert result["rows"][0]["cooldown_action"] == "blocked"


def test_same_symbol_cooldown_threshold_equality_uses_severe_window_and_excludes_zero_return() -> None:
    # severe_loss_threshold and loss_return_threshold are both boundary-tested:
    # a -0.08 outcome (== severe threshold) must select the longer severe window,
    # and a 0.0 outcome (== loss threshold) must not count as a loss at all.
    rule = build_shortpick_same_symbol_cooldown_rule(
        cooldown_signal_days=2,
        severe_loss_threshold=-0.08,
        severe_cooldown_signal_days=4,
        loss_return_threshold=0.0,
    )
    candidates = [
        {"candidate_id": f"aaa-{day:02d}", "symbol": "AAA.SZ", "signal_date": f"2026-05-{day:02d}"}
        for day in (3, 4, 5, 6, 7)
    ] + [{"candidate_id": "bbb-03", "symbol": "BBB.SZ", "signal_date": "2026-05-03"}]
    outcomes = [
        {
            "candidate_id": "severe-equal",
            "symbol": "AAA.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-02",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": -0.08,
        },
        {
            "candidate_id": "zero-return",
            "symbol": "BBB.SZ",
            "signal_date": "2026-04-20",
            "exit_date": "2026-05-02",
            "horizon_days": 10,
            "status": "completed",
            "stock_return": 0.0,
        },
    ]

    result = apply_shortpick_same_symbol_cooldown_control(candidates, outcomes, rule=rule)
    by_id = {row["candidate_id"]: row for row in result["rows"]}

    # elapsed signal days from exit 2026-05-02: day 06 -> 4 (severe window length), day 07 -> 5 (> window)
    assert by_id["aaa-06"]["cooldown_action"] == "blocked"
    assert by_id["aaa-06"]["cooldown_blocker_events"][0]["cooldown_signal_days"] == 4
    assert by_id["aaa-06"]["cooldown_blocker_events"][0]["elapsed_signal_days"] == 4
    assert by_id["aaa-07"]["cooldown_action"] == "allowed"
    # 0.0 == loss_return_threshold is not a loss, so BBB is never blocked.
    assert by_id["bbb-03"]["cooldown_action"] == "allowed"


# --- Round 27 hardening: historical-backtest request follow-ups (Round 13) ---


def test_historical_backtest_generation_requests_reject_non_positive_min_signal_symbol_count() -> None:
    rule = build_shortpick_repeated_exposure_limit_rule()

    with pytest.raises(ValueError, match="min_signal_symbol_count must be positive"):
        build_shortpick_historical_backtest_generation_requests(
            [rule],
            start_date="2023-04-13",
            end_date="2026-05-08",
            min_signal_symbol_count=0,
        )


def test_historical_backtest_generation_requests_with_empty_control_rules_produce_no_requests() -> None:
    result = build_shortpick_historical_backtest_generation_requests(
        [],
        start_date="2023-04-13",
        end_date="2026-05-08",
    )

    assert result["status"] == "ready"
    assert result["request_count"] == 0
    assert result["requests"] == []


def test_historical_backtest_generation_requests_support_same_close_proxy_entry_source() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")

    result = build_shortpick_historical_backtest_generation_requests(
        [rule],
        start_date="2023-04-13",
        end_date="2026-05-08",
        entry_price_sources=["same_close_proxy"],
    )

    assert result["request_count"] == 1
    request = result["requests"][0]
    assert request["entry_price_source"] == "same_close_proxy"
    assert request["evidence_basis"] == "historical_backtest"
    assert request["true_forward_tracking_eligible"] is False
    assert "same_close_proxy" in request["output_path"]


# --- Round 29: primary/deprecated governance partition of the paper-tracking ledger ---


def test_partition_moves_retire_candidate_to_deprecated_and_keeps_active_primary() -> None:
    weak = [
        _item(f"2026-05-{index + 1:02d}", "002371.SZ", "北方华创", value, value - 0.01)
        for index, value in enumerate([-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02])
    ]
    strong = [
        _item(
            f"2026-05-{index + 1:02d}",
            "300750.SZ",
            "宁德时代",
            value,
            value + 0.01,
            tracking_group="llm_paper_control",
            source_rank=2,
        )
        for index, value in enumerate([0.02, 0.03, 0.01, 0.04, 0.02])
    ]
    paper_tracking = {"items": [*weak, *strong]}
    evidence = build_shortpick_strategy_retirement_evidence_packs(
        paper_tracking,
        historical_evidence={
            "low_turnover_20d_uptrend_liquid_top120": {
                "status": "ready",
                "after_cost_excess_return": -0.03,
            }
        },
    )
    recommendations = build_shortpick_strategy_status_recommendations(evidence)

    partition = partition_paper_tracking_rows_by_governance(paper_tracking, recommendations)

    assert partition["status"] == "ready"
    assert partition["deprecated_status_set"] == ["inventory_archived", "retire_candidate", "retired"]
    assert partition["deprecated_count"] == 10
    assert partition["primary_count"] == 5
    assert len(partition["items"]) == 15  # original order preserved, all annotated
    assert {row["governance_status"] for row in partition["deprecated_items"]} == {"retire_candidate"}
    assert {row["governance_status"] for row in partition["primary_items"]} == {"active"}
    assert all(row["governance_view_section"] == "deprecated" for row in partition["deprecated_items"])
    assert partition["deprecated_items"][0]["symbol"] == "002371.SZ"  # original fields retained


def test_partition_moves_retired_strategy_to_deprecated() -> None:
    items = [
        _item(f"2026-05-{index + 1:02d}", "002371.SZ", "北方华创", value, value - 0.01)
        for index, value in enumerate([-0.10, -0.05, -0.04, -0.03, -0.02, -0.01, -0.09, -0.02, 0.01, 0.02])
    ]
    paper_tracking = {"items": items}
    evidence = build_shortpick_strategy_retirement_evidence_packs(paper_tracking)
    strategy_id = evidence["packs"][0]["strategy_id"]
    recommendations = build_shortpick_strategy_status_recommendations(
        evidence,
        retirement_artifacts={
            strategy_id: {
                "status": "ready",
                "artifact_family": "shortpick_strategy_retirement",
                "artifact_id": "partition-fixture",
                "decision_log_ref": "DECISIONS.md#2026-06-11-partition",
            }
        },
    )

    partition = partition_paper_tracking_rows_by_governance(paper_tracking, recommendations)

    assert partition["deprecated_count"] == 10
    assert partition["primary_count"] == 0
    assert partition["deprecated_strategy_ids"] == [strategy_id]
    assert all(row["governance_status"] == "retired" for row in partition["deprecated_items"])


def test_partition_defaults_unrecommended_rows_to_primary() -> None:
    items = [_item("2026-05-10", "002371.SZ", "北方华创", -0.10, -0.12)]

    partition = partition_paper_tracking_rows_by_governance({"items": items}, {"recommendations": []})

    assert partition["primary_count"] == 1
    assert partition["deprecated_count"] == 0
    assert partition["deprecated_strategy_ids"] == []
    row = partition["items"][0]
    assert row["governance_status"] == "untracked"
    assert row["governance_view_section"] == "primary"
    assert row["symbol"] == "002371.SZ"


def test_partition_moves_inventory_archived_control_to_deprecated_without_performance_status() -> None:
    item = _control_tracking_item(
        "2026-05-10",
        "002371.SZ",
        "北方华创",
        role="market_factor_control_legacy_second_candidate",
        family="momentum_10d_turnover_legacy_second_candidate",
        source_rank=2,
    )
    inventory = build_shortpick_redundant_control_archive_decisions(
        [
            {
                "tracking_group": "market_factor_control",
                "role": "market_factor_control_legacy_second_candidate",
                "family": "momentum_10d_turnover_legacy_second_candidate",
                "entry_price_source": "next_close",
                "source_rank": 2,
                "archive_action": "archive",
                "decision_basis": "inventory_diagnostic_value",
                "archive_reason_code": "dormant_legacy_control",
            }
        ]
    )

    partition = partition_paper_tracking_rows_by_governance(
        {"items": [item]},
        {"recommendations": []},
        inventory_archive_decision_result=inventory,
    )

    assert partition["primary_count"] == 0
    assert partition["deprecated_count"] == 1
    assert partition["inventory_archived_count"] == 1
    archived = partition["deprecated_items"][0]
    assert archived["governance_status"] == "inventory_archived"
    assert archived["governance_view_section"] == "deprecated"
    assert archived["governance_archive_basis"] == "inventory_diagnostic_value"
    assert archived["inventory_archive_decision"]["archive_reason_code"] == "dormant_legacy_control"


def _evidence_from_returns(
    returns: list[float],
    *,
    historical_evidence: dict[str, object] | None = None,
    baseline_evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "items": [
            _item(
                f"2026-05-{index + 1:02d}",
                "002371.SZ",
                "北方华创",
                value,
                value - 0.01,
            )
            for index, value in enumerate(returns)
        ]
    }
    return build_shortpick_strategy_retirement_evidence_packs(
        payload,
        historical_evidence=historical_evidence,
        baseline_evidence=baseline_evidence,
    )


def _generation_item(role: str, family: str, source_rank: int) -> dict[str, object]:
    strategy_id = (
        "market_factor_control"
        f"__{role}"
        f"__{family}"
        "__next_close"
        f"__{source_rank}"
    )
    return {
        "strategy_id": strategy_id,
        "tracking_group": "market_factor_control",
        "role": role,
        "family": family,
        "entry_price_source": "next_close",
        "source_rank": source_rank,
    }


def _ready_retrospective_replay_artifact(
    rule: dict[str, object],
    *,
    artifact_id: str = "shortpick-retrospective-forward-replay:test",
) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": "shortpick_retrospective_forward_replay",
        "status": "ready",
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "selection_policy": "filter_ranked_pool_select_first_allowed",
        "paper_tracking_write_policy": "forbidden",
        "request": {
            "control_group_id": rule["control_group_id"],
            "rule_signature": rule["rule_signature"],
            "rule_defined_at": "2026-06-10",
        },
        "rows": [
            {
                "candidate_id": "retrospective-row",
                "signal_date": "2026-05-20",
                "symbol": "002028.SZ",
                "control_group_id": rule["control_group_id"],
                "rule_signature": rule["rule_signature"],
                "rule_defined_at": "2026-06-10",
                "leakage_audit_status": "passed",
            }
        ],
    }


def _item(
    signal_date: str,
    symbol: str,
    name: str,
    stock_return: float,
    excess_return: float,
    *,
    tracking_group: str = "frozen_strategy",
    entry_price_source: str = "next_close",
    entry_rule: str = "次一交易日收盘买入",
    source_rank: int = 1,
) -> dict[str, object]:
    return {
        "run_id": 1,
        "candidate_id": hash((signal_date, symbol, tracking_group)) % 100000,
        "run_date": signal_date,
        "signal_date": signal_date,
        "entry_date": signal_date,
        "symbol": symbol,
        "name": name,
        "tracking_group": tracking_group,
        "tracking_role": "frozen_paper_primary",
        "selection_label": "冻结纸面策略",
        "source_rank": source_rank,
        "entry_rule": entry_rule,
        "selection_score_components": {
            "family": "low_turnover_20d_uptrend_liquid_top120",
            "entry_price_source": entry_price_source,
        },
        "validation_by_horizon": [
            {
                "horizon_days": 10,
                "status": "completed",
                "entry_at": f"{signal_date}T15:00:00+08:00",
                "exit_at": "2026-05-24T15:00:00+08:00",
                "stock_return": stock_return,
                "excess_return": excess_return,
            }
        ],
    }


def _control_tracking_item(
    signal_date: str,
    symbol: str,
    name: str,
    *,
    role: str,
    family: str,
    source_rank: int,
) -> dict[str, object]:
    return {
        **_item(
            signal_date,
            symbol,
            name,
            0.01,
            0.0,
            tracking_group="market_factor_control",
            source_rank=source_rank,
        ),
        "tracking_role": role,
        "selection_score_components": {
            "family": family,
            "entry_price_source": "next_close",
        },
    }
