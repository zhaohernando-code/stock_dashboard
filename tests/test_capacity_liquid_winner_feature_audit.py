from __future__ import annotations

from ashare_evidence.capacity_liquid_winner_feature_audit import (
    _attach_industry_relative_features,
    _recipe_summary,
    _score_candidate,
    _target_fitted_combo_search,
)


def test_score_candidate_uses_recipe_weights() -> None:
    row = {
        "amount_10d_vs_20d_percentile": 0.8,
        "return_5d_percentile": 0.7,
        "turnover_rate_percentile": 0.6,
        "avg_amount_20d_percentile": 0.4,
    }

    assert _score_candidate(
        row,
        {
            "amount_10d_vs_20d_percentile": 1.0,
            "return_5d_percentile": 1.0,
            "avg_amount_20d_percentile": -0.5,
        },
    ) == 1.3


def test_recipe_summary_counts_dates_with_target_rank_threshold() -> None:
    date_results = [
        {
            "recipe_results": [
                {
                    "recipe": "pressure_turnover_rebound",
                    "best_target_rank": 5,
                    "fallback_ranks": [{"symbol": "BAD", "rank": 100}],
                },
                {
                    "recipe": "mid_liquidity_pressure_turn",
                    "best_target_rank": 50,
                    "fallback_ranks": [],
                },
                {"recipe": "pullback_pressure_turn", "best_target_rank": 10, "fallback_ranks": []},
                {"recipe": "low_drawdown_turnover_pressure", "best_target_rank": 12, "fallback_ranks": []},
                {"recipe": "industry_strength_pressure_turn", "best_target_rank": 7, "fallback_ranks": []},
                {"recipe": "industry_pullback_pressure_turn", "best_target_rank": 8, "fallback_ranks": []},
            ]
        },
        {
            "recipe_results": [
                {
                    "recipe": "pressure_turnover_rebound",
                    "best_target_rank": 15,
                    "fallback_ranks": [{"symbol": "BAD", "rank": 80}],
                },
                {
                    "recipe": "mid_liquidity_pressure_turn",
                    "best_target_rank": 70,
                    "fallback_ranks": [],
                },
                {"recipe": "pullback_pressure_turn", "best_target_rank": 30, "fallback_ranks": []},
                {"recipe": "low_drawdown_turnover_pressure", "best_target_rank": 40, "fallback_ranks": []},
                {"recipe": "industry_strength_pressure_turn", "best_target_rank": 27, "fallback_ranks": []},
                {"recipe": "industry_pullback_pressure_turn", "best_target_rank": 16, "fallback_ranks": []},
            ]
        },
    ]

    summary = {row["recipe"]: row for row in _recipe_summary(date_results, top_rank_threshold=25)}

    assert summary["pressure_turnover_rebound"]["dates_with_target_top_rank_within_threshold"] == 2
    assert summary["pressure_turnover_rebound"]["median_best_target_rank"] == 10.0
    assert summary["pressure_turnover_rebound"]["median_fallback_best_rank"] == 90.0
    assert summary["mid_liquidity_pressure_turn"]["dates_with_target_top_rank_within_threshold"] == 0
    assert summary["industry_pullback_pressure_turn"]["dates_with_target_top_rank_within_threshold"] == 2


def test_attach_industry_relative_features_uses_industry_medians() -> None:
    rows = [
        {"industry_name": "通信设备", "return_5d": 0.10, "return_20d": 0.30},
        {"industry_name": "通信设备", "return_5d": 0.02, "return_20d": 0.10},
        {"industry_name": "软件服务", "return_5d": -0.01, "return_20d": 0.00},
    ]

    _attach_industry_relative_features(rows)

    assert round(rows[0]["industry_return_5d_excess"], 6) == 0.04
    assert round(rows[0]["industry_return_20d_excess"], 6) == 0.1
    assert rows[2]["industry_return_5d_excess"] == 0.0


def test_target_fitted_combo_search_finds_existing_feature_separator() -> None:
    date_results = [
        {
            "as_of_date": "2024-05-30",
            "target_symbols": ["WIN"],
            "fallback_symbols": ["BAD"],
            "combo_search_candidates": [
                {"symbol": "WIN", "name": "winner", "return_5d_percentile": 0.9, "avg_amount_20d": 10.0},
                {"symbol": "MID", "name": "middle", "return_5d_percentile": 0.5, "avg_amount_20d": 20.0},
                {"symbol": "BAD", "name": "bad", "return_5d_percentile": 0.1, "avg_amount_20d": 30.0},
            ],
        },
        {
            "as_of_date": "2024-06-03",
            "target_symbols": ["WIN2"],
            "fallback_symbols": ["BAD2"],
            "combo_search_candidates": [
                {"symbol": "WIN2", "name": "winner2", "return_5d_percentile": 0.8, "avg_amount_20d": 10.0},
                {"symbol": "BAD2", "name": "bad2", "return_5d_percentile": 0.2, "avg_amount_20d": 30.0},
            ],
        },
    ]

    result = _target_fitted_combo_search(date_results, top_rank_threshold=1, max_terms=2)

    assert result["gate_status"] == "passed"
    assert result["best_target_ranks"] == [1, 1]
    assert {"field": "return_5d_percentile", "weight": 1.0} in result["selected_terms"]
