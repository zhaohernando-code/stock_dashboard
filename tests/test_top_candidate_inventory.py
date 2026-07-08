from __future__ import annotations

import json
from pathlib import Path

from ashare_evidence.cli import main as cli_main
from ashare_evidence.model_candidate_runner import (
    build_streamed_score_rank_probe_artifact,
    build_streamed_top_candidate_inventory_artifact,
)
from ashare_evidence.order_level_capacity_proxy import build_order_level_capacity_proxy
from ashare_evidence.top_candidate_learned_rerank_proxy import (
    build_top_candidate_learned_fillable_rerank_proxy,
    write_top_candidate_learned_fillable_rerank_proxy,
)
from ashare_evidence.top_candidate_objective_calibration_proxy import (
    build_top_candidate_objective_calibration_proxy,
    write_top_candidate_objective_calibration_proxy,
)


def test_streamed_top_candidate_inventory_keeps_bounded_ranked_candidates(tmp_path: Path) -> None:
    feature_path = tmp_path / "features.json"
    label_path = tmp_path / "labels.json"
    rows = []
    labels = []
    for as_of_date in ["2026-01-01", "2026-01-02"]:
        for index, symbol in enumerate(["A", "B", "C"], start=1):
            universe_id = f"{as_of_date}-{symbol}"
            rows.append(
                {
                    "universe_row_id": universe_id,
                    "as_of_date": as_of_date,
                    "symbol": symbol,
                    "feature_values": {
                        "price_momentum": {"return_1d": 0.0, "return_20d": 0.01 * index},
                        "liquidity": {"avg_amount_20d": 10_000_000.0 * index},
                        "cross_sectional": {
                            "return_20d_percentile": index / 10,
                            "amount_10d_vs_20d_percentile": index / 20,
                            "amount_vs_20d_avg_percentile": index / 30,
                        },
                    },
                }
            )
            labels.append(
                {
                    "universe_row_id": universe_id,
                    "as_of_date": as_of_date,
                    "symbol": symbol,
                    "label_status": "ready",
                    "labels": {
                        "net_excess_return_10d_after_costs": 0.01 * index,
                        "excess_return_5d": 0.005 * index,
                        "excess_return_20d": 0.02 * index,
                        "forward_return_5d": 0.006 * index,
                        "forward_return_10d": 0.011 * index,
                        "forward_return_20d": 0.021 * index,
                    },
                }
            )
    rows.sort(key=lambda row: str(row["symbol"]))
    feature_path.write_text(
        json.dumps(
            {
                "artifact_id": "pit-feature-matrix-unit",
                "artifact_type": "pit_feature_matrix",
                "feature_version": "unit",
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    label_path.write_text(
        json.dumps(
            {
                "artifact_id": "executable-label-matrix-unit",
                "artifact_type": "executable_label_matrix",
                "label_version": "unit",
                "rows": labels,
            }
        ),
        encoding="utf-8",
    )
    registry = {
        "artifact_id": "model-spec-registry-unit",
        "model_specs": [
            {
                "model_spec_id": "breakout_amount_confirmation_top2_20d_v1",
                "model_type": "breakout_amount_confirmation_ranker",
                "prediction_horizon_days": 20,
                "selection_policy": {"top_k": 2},
                "hyperparameter_grid": {
                    "amount_10d_vs_20d_percentile_weight": [1.0],
                    "liquidity_percentile_weight": [1.0],
                    "momentum_20d_percentile_weight": [1.0],
                    "one_day_overheat_penalty": [0.0],
                },
            }
        ],
    }

    inventory = build_streamed_top_candidate_inventory_artifact(
        validation_run_id="unit",
        feature_matrix_artifact=feature_path,
        label_matrix_artifact=label_path,
        model_spec_registry=registry,
        trial_id="breakout_amount_confirmation_top2_20d_v1:trial-000",
        top_n=2,
        min_train_dates=1,
        test_window_dates=1,
    )

    assert inventory["artifact_type"] == "top_candidate_inventory"
    assert inventory["storage_boundary"] == "compact_top_n_per_date_no_full_prediction_rows"
    assert inventory["prediction_row_count"] == 3
    assert inventory["candidate_row_count"] == 2
    assert [row["symbol"] for row in inventory["candidate_rows"]] == ["C", "B"]
    assert inventory["candidate_rows"][0]["rank_weight_feature_values"]["avg_amount_20d"] == 30_000_000.0
    assert inventory["candidate_rows"][0]["rank_weight_feature_values"]["return_20d_percentile"] == 0.3

    proxy = build_order_level_capacity_proxy(
        selected_picks=inventory["candidate_rows"][:1],
        selected_top_k=1,
        top_candidate_picks=inventory["candidate_rows"],
    )
    assert proxy["top_candidate_pick_count"] == 2
    assert proxy["candidate_inventory_scope"] == "trial_diagnostic_top_candidate_picks"


def test_streamed_score_rank_probe_keeps_target_rank_and_top_peers(tmp_path: Path) -> None:
    feature_path = tmp_path / "features.json"
    rows = []
    for index, symbol in enumerate(["A", "B", "C", "D"], start=1):
        rows.append(
            {
                "universe_row_id": f"2026-01-01-{symbol}",
                "as_of_date": "2026-01-01",
                "symbol": symbol,
                "feature_values": {
                    "price_momentum": {"return_1d": 0.0, "return_20d": 0.01 * index},
                    "liquidity": {"avg_amount_20d": 10_000_000.0 * index},
                    "cross_sectional": {
                        "return_20d_percentile": index / 10,
                        "amount_10d_vs_20d_percentile": index / 20,
                        "amount_vs_20d_avg_percentile": index / 30,
                    },
                },
            }
        )
    feature_path.write_text(
        json.dumps(
            {
                "artifact_id": "pit-feature-matrix-unit",
                "artifact_type": "pit_feature_matrix",
                "feature_version": "unit",
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    registry = {
        "artifact_id": "model-spec-registry-unit",
        "model_specs": [
            {
                "model_spec_id": "breakout_amount_confirmation_top2_20d_v1",
                "model_type": "breakout_amount_confirmation_ranker",
                "prediction_horizon_days": 20,
                "selection_policy": {"top_k": 2},
                "hyperparameter_grid": {
                    "amount_10d_vs_20d_percentile_weight": [1.0],
                    "liquidity_percentile_weight": [1.0],
                    "momentum_20d_percentile_weight": [1.0],
                    "one_day_overheat_penalty": [0.0],
                },
            }
        ],
    }

    probe = build_streamed_score_rank_probe_artifact(
        validation_run_id="unit",
        feature_matrix_artifact=feature_path,
        model_spec_registry=registry,
        trial_id="breakout_amount_confirmation_top2_20d_v1:trial-000",
        target_symbols_by_date={"2026-01-01": ["B", "D"]},
        top_n=2,
    )

    assert probe["artifact_type"] == "score_rank_probe"
    assert probe["storage_boundary"] == "compact_target_rows_and_top_n_per_date_no_full_prediction_rows"
    assert probe["scored_row_count"] == 4
    ranks = {row["symbol"]: row["rank"] for row in probe["target_rows"]}
    assert ranks == {"B": 3, "D": 1}
    assert [row["symbol"] for row in probe["top_candidate_rows"]] == ["D", "C"]
    assert probe["top_candidate_rows"][0]["rank_weight_feature_values"]["amount_vs_20d_avg_percentile"] == 4 / 30


def test_score_rank_probe_cli_can_use_opportunity_discovery_targets(tmp_path: Path) -> None:
    feature_path = tmp_path / "features.json"
    registry_path = tmp_path / "registry.json"
    opportunity_path = tmp_path / "opportunity.json"
    output_path = tmp_path / "probe.json"
    feature_path.write_text(
        json.dumps(
            {
                "artifact_id": "pit-feature-matrix-unit",
                "artifact_type": "pit_feature_matrix",
                "feature_version": "unit",
                "rows": [
                    {
                        "universe_row_id": "2026-01-01-A",
                        "as_of_date": "2026-01-01",
                        "symbol": "A",
                        "feature_values": {
                            "price_momentum": {"return_1d": 0.0},
                            "cross_sectional": {
                                "return_20d_percentile": 0.1,
                                "amount_10d_vs_20d_percentile": 0.1,
                                "amount_vs_20d_avg_percentile": 0.1,
                            },
                        },
                    },
                    {
                        "universe_row_id": "2026-01-01-B",
                        "as_of_date": "2026-01-01",
                        "symbol": "B",
                        "feature_values": {
                            "price_momentum": {"return_1d": 0.0},
                            "cross_sectional": {
                                "return_20d_percentile": 0.9,
                                "amount_10d_vs_20d_percentile": 0.9,
                                "amount_vs_20d_avg_percentile": 0.9,
                            },
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    registry_path.write_text(
        json.dumps(
            {
                "artifact_id": "model-spec-registry-unit",
                "model_specs": [
                    {
                        "model_spec_id": "breakout_amount_confirmation_top2_20d_v1",
                        "model_type": "breakout_amount_confirmation_ranker",
                        "prediction_horizon_days": 20,
                        "selection_policy": {"top_k": 2},
                        "hyperparameter_grid": {
                            "amount_10d_vs_20d_percentile_weight": [1.0],
                            "liquidity_percentile_weight": [1.0],
                            "momentum_20d_percentile_weight": [1.0],
                            "one_day_overheat_penalty": [0.0],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    opportunity_path.write_text(
        json.dumps(
            {
                "dates": [
                    {
                        "as_of_date": "2026-01-01",
                        "source_symbol": "A",
                        "top_liquid_by_future_excess": [{"symbol": "B"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli_main(
        [
            "research-score-rank-probe",
            "--validation-run-id",
            "unit",
            "--feature-matrix-artifact",
            str(feature_path),
            "--model-spec-registry-artifact",
            str(registry_path),
            "--trial-id",
            "breakout_amount_confirmation_top2_20d_v1:trial-000",
            "--opportunity-discovery-artifact",
            str(opportunity_path),
            "--opportunity-top-k",
            "1",
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert {row["symbol"] for row in payload["target_rows"]} == {"A", "B"}


def _top_candidate_inventory_for_learned_rerank_proxy() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    training_returns = {"A": -0.05, "B": 0.03, "C": 0.02, "D": 0.01}
    evaluation_returns = {"A": 0.08, "B": -0.02, "C": -0.03, "D": -0.04}
    for as_of_date, returns in [
        ("2026-01-01", training_returns),
        ("2026-01-02", evaluation_returns),
        ("2026-01-03", evaluation_returns),
    ]:
        for rank, symbol in enumerate(["A", "B", "C", "D"], start=1):
            rows.append(
                {
                    "as_of_date": as_of_date,
                    "symbol": symbol,
                    "rank": rank,
                    "portfolio_weight": 1.0,
                    "net_excess_return": returns[symbol],
                    "score": float(5 - rank),
                    "return_5d_percentile": 1.0 - (rank / 10.0),
                    "return_20d_percentile": 1.0 - (rank / 10.0),
                    "amount_10d_vs_20d_percentile": rank / 10.0,
                    "turnover_rate_percentile": rank / 10.0,
                    "avg_amount_20d": 1_000_000.0 if symbol == "A" else 10_000_000.0 * rank,
                    "low_volatility_percentile": rank / 10.0,
                    "max_drawdown_20d": -0.01 * rank,
                }
            )
    return {
        "artifact_id": "top-candidate-inventory-unit",
        "trial_id": "unit-trial:trial-000",
        "candidate_rows": rows,
    }


def test_learned_fillable_rerank_proxy_is_bounded_and_blocks_weak_diagnostic(tmp_path: Path) -> None:
    inventory = _top_candidate_inventory_for_learned_rerank_proxy()

    payload = build_top_candidate_learned_fillable_rerank_proxy(
        inventory,
        min_train_dates=1,
        top_k=2,
        fillable_avg_amount_20d_threshold=10_000_000.0,
    )

    assert payload["artifact_type"] == "top_candidate_learned_fillable_rerank_proxy"
    assert payload["claim_ceiling"] == "retained_top_candidate_inventory_proxy_only_no_model_replay_no_promotion"
    assert payload["source_inventory_id"] == "top-candidate-inventory-unit"
    assert payload["evaluated_date_count"] == 2
    assert "candidate_rows" not in payload
    assert set(payload["variants"]) == {
        "baseline_topk_original_rank",
        "original_rank_topk_fillable_only",
        "learned_topk_all_candidates",
        "learned_topk_fillable_only",
    }
    assert payload["gate_status"] == "blocked"
    assert "learned_fillable_mean_below_baseline" in payload["blocking_gate_ids"]

    output_path = write_top_candidate_learned_fillable_rerank_proxy(payload, tmp_path / "proxy.json")
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["gate_status"] == "blocked"


def test_learned_fillable_rerank_proxy_cli_writes_blocked_artifact(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "proxy.json"
    inventory_path.write_text(
        json.dumps(_top_candidate_inventory_for_learned_rerank_proxy()),
        encoding="utf-8",
    )

    exit_code = cli_main(
        [
            "research-top-candidate-learned-rerank-proxy",
            "--top-candidate-inventory-artifact",
            str(inventory_path),
            "--min-train-dates",
            "1",
            "--top-k",
            "2",
            "--fillable-avg-amount-20d-threshold",
            "10000000",
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["source_top_candidate_inventory_artifact"] == str(inventory_path)
    assert payload["gate_status"] == "blocked"


def test_objective_calibration_proxy_is_bounded_and_blocks_unpromising_objectives(tmp_path: Path) -> None:
    inventory = _top_candidate_inventory_for_learned_rerank_proxy()

    payload = build_top_candidate_objective_calibration_proxy(
        inventory,
        min_train_dates=1,
        top_k=2,
        fillable_avg_amount_20d_threshold=10_000_000.0,
        positive_top_k=1,
        negative_bottom_k=1,
    )

    assert payload["artifact_type"] == "top_candidate_objective_calibration_proxy"
    assert payload["claim_ceiling"] == "retained_top_candidate_inventory_objective_proxy_only_no_model_replay_no_promotion"
    assert payload["source_inventory_id"] == "top-candidate-inventory-unit"
    assert payload["evaluated_date_count"] == 2
    assert "candidate_rows" not in payload
    assert set(payload["variants"]) == {
        "baseline_topk_original_rank",
        "original_rank_topk_fillable_only",
        "return_linear_topk_fillable",
        "return_magnitude_topk_fillable",
        "positive_return_magnitude_topk_fillable",
        "calibrated_tail_topk_fillable",
        "pairwise_top_bottom_topk_fillable",
    }
    assert payload["gate_status"] == "blocked"
    assert "no_objective_variant_beats_fillable_baseline_and_retains_original_rank_floor" in payload["blocking_gate_ids"]

    output_path = write_top_candidate_objective_calibration_proxy(payload, tmp_path / "objective.json")
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["gate_status"] == "blocked"


def test_objective_calibration_proxy_cli_writes_blocked_artifact(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "objective.json"
    inventory_path.write_text(
        json.dumps(_top_candidate_inventory_for_learned_rerank_proxy()),
        encoding="utf-8",
    )

    exit_code = cli_main(
        [
            "research-top-candidate-objective-calibration-proxy",
            "--top-candidate-inventory-artifact",
            str(inventory_path),
            "--min-train-dates",
            "1",
            "--top-k",
            "2",
            "--fillable-avg-amount-20d-threshold",
            "10000000",
            "--positive-top-k",
            "1",
            "--negative-bottom-k",
            "1",
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["source_top_candidate_inventory_artifact"] == str(inventory_path)
    assert payload["gate_status"] == "blocked"
