from __future__ import annotations

import json

import pytest

from ashare_evidence.shortpick_strategy_governance import (
    build_shortpick_strategy_retirement_evidence_packs,
    build_shortpick_strategy_status_recommendations,
    filter_shortpick_generation_eligible_items,
)


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

    assert result["decision_policy"] == "exclude_only_retired_status_from_active_generation"
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
