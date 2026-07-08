from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence import model_candidate_runner
from ashare_evidence.cli import main as cli_main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.model_candidate_runner import (
    _exit_horizon_days,
    _model_feature_values,
    _position_weight,
    _rank_weight_multiplier,
    _rank_weight_multipliers_for_rows,
    _rank_signal_feature_subset,
    _select_top_k_rows,
    _selection_allowed,
    _top_k_picks_by_date,
    _top_k_returns_by_date,
    _uses_defensive_branch,
    _weighted_return,
    build_streamed_walk_forward_model_candidate_run_artifact,
    build_walk_forward_model_candidate_run_artifact,
    write_walk_forward_model_candidate_run_artifact,
)
from ashare_evidence.model_comparison_report import (
    _rolling_sleeve_curve,
    _sort_key,
    build_model_comparison_report_artifact,
    write_model_comparison_report_artifact,
)
from ashare_evidence.model_exploration_snapshot import build_model_exploration_p1_artifacts
from ashare_evidence.model_governance_gate import (
    build_model_governance_and_projection_artifacts,
    write_model_governance_and_projection_artifacts,
)
from ashare_evidence.model_spec_registry import build_model_spec_registry_artifact
from ashare_evidence.models import MarketBar, Stock


class ModelCandidateWorkbenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.temp_dir.name) / 'candidate-workbench.db'}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_stock(self, symbol: str, name: str, prices: list[float], *, industry: str = "制造业") -> None:
        ticker, _, exchange = symbol.partition(".")
        with session_scope(self.database_url) as session:
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange or "SH",
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={"industry": industry},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            for index, price in enumerate(prices):
                observed_day = date(2026, 1, 1) + timedelta(days=index)
                session.add(
                    MarketBar(
                        bar_key=f"bar-{symbol}-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(
                            observed_day.year,
                            observed_day.month,
                            observed_day.day,
                            7,
                            0,
                            tzinfo=UTC,
                        ),
                        open_price=price - 0.5,
                        high_price=price + 1.0,
                        low_price=price - 1.0,
                        close_price=price,
                        volume=2000 + index,
                        amount=price * (2000 + index),
                        turnover_rate=1.0,
                        total_mv=2_000_000_000.0 + index,
                        circ_mv=1_500_000_000.0 + index,
                        pe_ttm=18.0 + index / 10,
                        pb=1.8 + index / 100,
                        raw_payload={},
                        license_tag="test",
                        usage_scope="internal-test",
                        redistribution_scope="none",
                        source_uri=f"test://bar/{symbol}/{index}",
                        lineage_hash=compute_lineage_hash({"symbol": symbol, "index": index}),
                    )
                )

    def _build_inputs(self) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        days = [date(2026, 1, 11) + timedelta(days=index) for index in range(4)]
        self._seed_stock("600001.SH", "主板甲", [10 + index * 0.4 for index in range(28)])
        self._seed_stock("600002.SH", "主板乙", [20 + index * 0.15 for index in range(28)])
        self._seed_stock("000300.SH", "沪深300", [100 + index * 0.1 for index in range(28)], industry="benchmark")
        with session_scope(self.database_url) as session:
            artifacts = build_model_exploration_p1_artifacts(
                session,
                validation_run_id="unit-run",
                as_of_dates=days,
                horizons=(10,),
                min_history_days=2,
            )
        registry = build_model_spec_registry_artifact(
            validation_run_id="unit-run",
            source_input_snapshot_id=str(artifacts["model_exploration_input_snapshot"]["artifact_id"]),
        )
        return artifacts["pit_feature_matrix"], artifacts["executable_label_matrix"], registry

    def test_candidate_runner_executes_registered_specs_only_and_blocks_promotion(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()

        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )

        self.assertEqual(run["artifact_type"], "walk_forward_model_candidate_run")
        self.assertEqual(run["promotion_status"], "blocked_from_production")
        self.assertEqual(run["trial_count"], 1)
        self.assertGreater(run["prediction_row_count"], 0)
        self.assertGreater(run["stored_prediction_row_count"], 0)
        self.assertEqual(run["evaluable_row_count"], run["joined_row_count"])
        self.assertGreater(len(run["trial_summaries"][0]["fit_summaries"]), 0)
        self.assertIn("top_5_net_excess_mean", run["trial_summaries"][0]["metrics"])
        self.assertIn("top_10_net_excess_mean", run["trial_summaries"][0]["metrics"])
        self.assertGreater(len(run["trial_diagnostics"][0]["date_rank_ics"]), 0)
        self.assertIn("fitted_model_digest", run["prediction_rows"][0])
        self.assertIn("target_total_return", run["prediction_rows"][0])
        self.assertIn("selection_allowed", run["prediction_rows"][0])
        self.assertIn("selection_block_reasons", run["prediction_rows"][0])
        self.assertIn("portfolio_weight", run["prediction_rows"][0])
        self.assertIn("industry_name", run["prediction_rows"][0])
        self.assertIn("stock_name", run["prediction_rows"][0])
        self.assertIn("industry_name", run["trial_diagnostics"][0]["selected_top_k_picks_by_date"][0])
        self.assertIn("selected_top_k_industry_exposure_by_month", run["trial_diagnostics"][0])
        self.assertEqual(
            run["prediction_storage_policy"]["mode"],
            "bounded_inline_sample_with_full_trial_diagnostics",
        )
        self.assertEqual(run["validation_protocol"]["runner_policy"], "registered_model_specs_only")
        self.assertIn("governance_promotion_pending", run["gate_readout"]["blocking_gate_ids"])

    def test_candidate_runner_rejects_unregistered_specs(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()

        with self.assertRaisesRegex(ValueError, "unregistered model specs requested"):
            build_walk_forward_model_candidate_run_artifact(
                validation_run_id="unit-run",
                feature_matrix=feature_matrix,
                label_matrix=label_matrix,
                model_spec_registry=registry,
                min_train_dates=1,
                test_window_dates=2,
                selected_model_spec_ids=["not-registered"],
            )

    def test_streamed_candidate_runner_fits_regularized_linear_model(self) -> None:
        feature_path = Path(self.temp_dir.name) / "stream-linear-features.json"
        label_path = Path(self.temp_dir.name) / "stream-linear-labels.json"
        rows = []
        labels = []
        for as_of_date in ["2026-01-01", "2026-01-02", "2026-01-03"]:
            for index, symbol in enumerate(["A", "B", "C"], start=1):
                universe_id = f"{as_of_date}-{symbol}"
                rows.append(
                    {
                        "universe_row_id": universe_id,
                        "as_of_date": as_of_date,
                        "symbol": symbol,
                        "feature_values": {
                            "price_momentum": {
                                "return_5d": float(4 - index),
                                "return_10d": float(4 - index),
                                "return_20d": float(index),
                            },
                            "liquidity": {"avg_amount_20d": 30_000_000.0},
                            "cross_sectional": {"return_20d_percentile": index / 3.0},
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
        feature_path.write_text(
            json.dumps({"artifact_id": "feature-unit", "artifact_type": "pit_feature_matrix", "rows": rows}),
            encoding="utf-8",
        )
        label_path.write_text(
            json.dumps({"artifact_id": "label-unit", "artifact_type": "executable_label_matrix", "rows": labels}),
            encoding="utf-8",
        )
        registry = {
            "artifact_id": "registry-unit",
            "model_specs": [
                {
                    "model_spec_id": "stream_linear_unit_v1",
                    "model_type": "regularized_rank_linear",
                    "prediction_horizon_days": 20,
                    "selection_policy": {"top_k": 1, "evaluation_return_metric": "selected_top_k_net_excess_mean"},
                    "hyperparameter_grid": {"regularization_alpha": [0.5]},
                }
            ],
        }

        run = build_streamed_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix_artifact=feature_path,
            label_matrix_artifact=label_path,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=1,
            selected_model_spec_ids=["stream_linear_unit_v1"],
        )

        summary = run["trial_summaries"][0]
        self.assertEqual(summary["fit_summaries"][0]["fitted_model_family"], "stream_split_fitted_rank_linear")
        self.assertEqual(summary["fit_summaries"][0]["train_row_count"], 3)
        self.assertGreater(summary["metrics"]["selected_top_k_net_excess_mean"], 0.0)
        selected_symbols = [row["symbol"] for row in run["trial_diagnostics"][0]["selected_top_k_picks_by_date"]]
        self.assertEqual(selected_symbols, ["C", "C"])

    def test_streamed_candidate_runner_fits_tail_capture_linear_model(self) -> None:
        feature_path = Path(self.temp_dir.name) / "stream-tail-features.json"
        label_path = Path(self.temp_dir.name) / "stream-tail-labels.json"
        rows = []
        labels = []
        for as_of_date in ["2026-01-01", "2026-01-02", "2026-01-03"]:
            for index, symbol in enumerate(["A", "B", "C"], start=1):
                universe_id = f"{as_of_date}-{symbol}"
                rows.append(
                    {
                        "universe_row_id": universe_id,
                        "as_of_date": as_of_date,
                        "symbol": symbol,
                        "feature_values": {
                            "price_momentum": {
                                "return_5d": float(index),
                                "return_10d": float(index),
                                "return_20d": float(index),
                            },
                            "liquidity": {"avg_amount_20d": 30_000_000.0},
                            "cross_sectional": {
                                "return_5d_percentile": index / 3.0,
                                "return_20d_percentile": index / 3.0,
                                "amount_10d_vs_20d_percentile": index / 3.0,
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
        feature_path.write_text(
            json.dumps({"artifact_id": "feature-unit", "artifact_type": "pit_feature_matrix", "rows": rows}),
            encoding="utf-8",
        )
        label_path.write_text(
            json.dumps({"artifact_id": "label-unit", "artifact_type": "executable_label_matrix", "rows": labels}),
            encoding="utf-8",
        )
        registry = {
            "artifact_id": "registry-unit",
            "model_specs": [
                {
                    "model_spec_id": "tail_capture_unit_v1",
                    "model_type": "tail_capture_linear_ranker",
                    "prediction_horizon_days": 20,
                    "selection_policy": {
                        "top_k": 1,
                        "evaluation_return_metric": "selected_top_k_net_excess_mean",
                        "feature_gate": {"min_avg_amount_20d": 18_200_000.0},
                    },
                    "hyperparameter_grid": {
                        "regularization_alpha": [0.5],
                        "tail_positive_top_k": [1],
                        "min_avg_amount_20d": [18_200_000.0],
                    },
                }
            ],
        }

        run = build_streamed_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix_artifact=feature_path,
            label_matrix_artifact=label_path,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=1,
            selected_model_spec_ids=["tail_capture_unit_v1"],
        )

        summary = run["trial_summaries"][0]
        self.assertEqual(summary["fit_summaries"][0]["fitted_model_family"], "stream_split_fitted_rank_linear")
        self.assertEqual(summary["fit_summaries"][0]["train_row_count"], 3)
        self.assertGreater(summary["metrics"]["selected_top_k_net_excess_mean"], 0.0)
        selected_symbols = [row["symbol"] for row in run["trial_diagnostics"][0]["selected_top_k_picks_by_date"]]
        self.assertEqual(selected_symbols, ["C", "C"])

    def test_selection_feature_gate_blocks_weak_amount_expansion(self) -> None:
        allowed, blockers = _selection_allowed(
            {
                "amount_10d_vs_20d": 0.10,
                "return_20d_percentile": 0.95,
                "turnover_rate_percentile": 0.20,
                "volatility_20d_percentile": 0.20,
            },
            selection_policy={"feature_gate": {"min_amount_10d_vs_20d": 0.15}},
            params={},
        )

        self.assertFalse(allowed)
        self.assertIn("amount_10d_vs_20d_below_feature_gate", blockers)

    def test_model_feature_values_preserves_execution_gate_fields(self) -> None:
        values = _model_feature_values(
            {
                "feature_values": {
                    "execution": {
                        "limit_state": "limit_up_like",
                        "suspension_or_stale_proxy": True,
                    },
                    "liquidity": {
                        "avg_amount_20d": 12_000_000.0,
                    },
                    "valuation_capacity": {
                        "total_mv": 2_000_000_000.0,
                        "circ_mv": 1_500_000_000.0,
                        "pe_ttm": 18.5,
                        "pb": 1.8,
                    },
                    "cross_sectional": {
                        "total_mv_percentile": 0.80,
                        "circ_mv_percentile": 0.75,
                        "small_total_mv_percentile": 0.20,
                        "small_circ_mv_percentile": 0.25,
                        "pe_ttm_percentile": 0.60,
                        "pb_percentile": 0.40,
                    },
                }
            }
        )

        self.assertEqual(values["limit_state"], "limit_up_like")
        self.assertTrue(values["suspension_or_stale_proxy"])
        self.assertEqual(values["avg_amount_20d"], 12_000_000.0)
        self.assertEqual(values["total_mv"], 2_000_000_000.0)
        self.assertEqual(values["circ_mv"], 1_500_000_000.0)
        self.assertEqual(values["pe_ttm"], 18.5)
        self.assertEqual(values["pb"], 1.8)
        self.assertEqual(values["total_mv_percentile"], 0.80)
        self.assertEqual(values["circ_mv_percentile"], 0.75)
        self.assertEqual(values["small_total_mv_percentile"], 0.20)
        self.assertEqual(values["small_circ_mv_percentile"], 0.25)
        self.assertEqual(values["pe_ttm_percentile"], 0.60)
        self.assertEqual(values["pb_percentile"], 0.40)

    def test_selection_feature_gate_blocks_unfillable_execution_states(self) -> None:
        allowed, blockers = _selection_allowed(
            {
                "limit_state": "limit_up_like",
                "suspension_or_stale_proxy": False,
                "avg_amount_20d": 80_000_000.0,
            },
            selection_policy={
                "feature_gate": {
                    "block_limit_up_like_entry": True,
                    "block_suspension_or_stale_proxy": True,
                    "min_avg_amount_20d": 100_000_000.0,
                }
            },
            params={},
        )

        self.assertFalse(allowed)
        self.assertEqual(
            blockers,
            [
                "avg_amount_20d_below_feature_gate",
                "limit_up_like_entry_unfillable_feature_gate",
            ],
        )

    def test_capacity_aware_ranker_penalizes_low_adv_small_cap_pressure(self) -> None:
        params = {
            "capacity_full_fill_avg_amount_20d": 18_200_000.0,
            "capacity_shortfall_penalty": 1.6,
            "small_cap_pressure_weight": 0.5,
            "low_turnover_pressure_weight": 0.5,
            "market_cap_percentile_bonus": 0.2,
            "capacity_depth_bonus": 0.2,
        }
        model_spec = {"model_type": "capacity_aware_regime_breakout_ranker"}
        common_values = {
            "benchmark_return_20d": -0.02,
            "benchmark_return_10d": -0.01,
            "benchmark_volatility_20d": 0.03,
            "return_20d_percentile": 0.7,
            "return_5d_percentile": 0.7,
            "amount_10d_vs_20d_percentile": 0.7,
            "amount_vs_20d_avg_percentile": 0.7,
            "low_volatility_percentile": 0.98,
            "return_1d": 0.0,
        }
        low_capacity_score = model_candidate_runner._score_row(
            {},
            model_spec=model_spec,
            params=params,
            feature_values={
                **common_values,
                "avg_amount_20d": 2_200_000.0,
                "small_total_mv_percentile": 0.92,
                "small_circ_mv_percentile": 0.85,
                "low_turnover_percentile": 0.99,
                "total_mv_percentile": 0.08,
                "circ_mv_percentile": 0.14,
            },
        )
        high_capacity_score = model_candidate_runner._score_row(
            {},
            model_spec=model_spec,
            params=params,
            feature_values={
                **common_values,
                "avg_amount_20d": 120_000_000.0,
                "small_total_mv_percentile": 0.15,
                "small_circ_mv_percentile": 0.10,
                "low_turnover_percentile": 0.50,
                "total_mv_percentile": 0.85,
                "circ_mv_percentile": 0.90,
            },
        )

        self.assertGreater(high_capacity_score, low_capacity_score)

    def test_fillable_weak_turnaround_ranker_prefers_fillable_turnover_recovery(self) -> None:
        params = {
            "capacity_full_fill_avg_amount_20d": 18_200_000.0,
            "capacity_shortfall_penalty": 2.0,
            "capacity_depth_bonus": 0.8,
            "defensive_condition_mode": "benchmark_20d_or_transition_stress",
            "low_turnover_penalty_weight": 0.4,
            "ultra_low_vol_penalty_weight": 0.3,
            "weak_amount_10d_vs_20d_percentile_weight": 1.0,
            "weak_return_5d_percentile_weight": 1.2,
            "weak_turnover_rate_percentile_weight": 0.5,
        }
        model_spec = {"model_type": "fillable_weak_turnaround_ranker"}
        common_values = {
            "benchmark_return_20d": -0.02,
            "benchmark_return_10d": -0.01,
            "benchmark_volatility_20d": 0.03,
            "amount_vs_20d_avg_percentile": 0.85,
            "return_1d": 0.0,
        }

        low_adv_defensive_score = model_candidate_runner._score_row(
            {},
            model_spec=model_spec,
            params=params,
            feature_values={
                **common_values,
                "avg_amount_20d": 2_200_000.0,
                "return_5d_percentile": 0.49,
                "return_20d_percentile": 0.42,
                "amount_10d_vs_20d_percentile": 0.75,
                "turnover_rate_percentile": 0.01,
                "low_turnover_percentile": 0.99,
                "low_volatility_percentile": 0.99,
                "volatility_20d_percentile": 0.01,
            },
        )
        fillable_turnaround_score = model_candidate_runner._score_row(
            {},
            model_spec=model_spec,
            params=params,
            feature_values={
                **common_values,
                "avg_amount_20d": 120_000_000.0,
                "return_5d_percentile": 0.82,
                "return_20d_percentile": 0.38,
                "amount_10d_vs_20d_percentile": 0.78,
                "turnover_rate_percentile": 0.88,
                "low_turnover_percentile": 0.12,
                "low_volatility_percentile": 0.25,
                "volatility_20d_percentile": 0.75,
            },
        )

        self.assertGreater(fillable_turnaround_score, low_adv_defensive_score)

    def test_date_exposure_scaling_reduces_returns_and_pick_weights_consistently(self) -> None:
        predictions = [
            {
                "symbol": "600001.SH",
                "stock_name": "甲",
                "as_of_date": "2026-01-02",
                "target_label": 0.10,
                "target_total_return": 0.12,
                "portfolio_weight": 0.1,
                "score": 10.0,
                "selection_allowed": True,
                "target_horizon_days": 20,
                "rank_weight_feature_values": {"avg_amount_20d": 50_000_000.0},
            },
            {
                "symbol": "600002.SH",
                "stock_name": "乙",
                "as_of_date": "2026-01-02",
                "target_label": 0.04,
                "target_total_return": 0.05,
                "portfolio_weight": 0.1,
                "score": 9.0,
                "selection_allowed": True,
                "target_horizon_days": 20,
                "rank_weight_feature_values": {"avg_amount_20d": 50_000_000.0},
            },
        ]
        selection_policy = {
            "mode": "concentrated_top_k",
            "top_k": 2,
            "date_exposure_scaling": {
                "enabled": True,
                "mode": "gross_exposure_floor_linear_scale",
                "gross_exposure_floor": 0.5,
            },
        }

        returns = _top_k_returns_by_date(
            predictions,
            top_k=2,
            selection_policy=selection_policy,
            params={},
        )
        picks = _top_k_picks_by_date(
            predictions,
            top_k=2,
            selection_policy=selection_policy,
            params={},
        )

        self.assertEqual(returns[0]["base_gross_exposure"], 0.1)
        self.assertEqual(returns[0]["date_exposure_scale"], 0.2)
        self.assertEqual(returns[0]["date_position_scale"], 0.2)
        self.assertEqual(returns[0]["gross_exposure"], 0.020000000000000004)
        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.0014000000000000002)
        self.assertEqual(returns[0]["date_exposure_scale_reasons"], ["gross_exposure_floor_linear_scale"])
        self.assertEqual(returns[0]["date_position_scale_reasons"], ["gross_exposure_floor_linear_scale"])
        self.assertTrue(all(pick["date_exposure_scale"] == 0.2 for pick in picks))
        self.assertAlmostEqual(sum(pick["weighted_net_excess_return"] for pick in picks), 0.0028000000000000004)

    def test_transition_defensive_branch_requires_explicit_mode_and_all_transition_signals(self) -> None:
        transition_values = {
            "benchmark_return_10d": -0.02,
            "benchmark_return_20d": 0.01,
            "benchmark_volatility_20d": 0.06,
        }

        self.assertFalse(_uses_defensive_branch(transition_values, {"defensive_benchmark_return_20d_threshold": 0.0}))
        self.assertTrue(
            _uses_defensive_branch(
                transition_values,
                {
                    "defensive_benchmark_return_20d_threshold": 0.0,
                    "defensive_condition_mode": "benchmark_20d_or_transition_stress",
                    "transition_benchmark_return_10d_threshold": -0.01,
                    "transition_benchmark_return_20d_ceiling": 0.03,
                    "transition_benchmark_volatility_20d_threshold": 0.04,
                },
            )
        )
        self.assertFalse(
            _uses_defensive_branch(
                {
                    **transition_values,
                    "benchmark_volatility_20d": 0.03,
                },
                {
                    "defensive_condition_mode": "benchmark_20d_or_transition_stress",
                    "transition_benchmark_volatility_20d_threshold": 0.04,
                },
            )
        )

    def test_portfolio_constraints_can_force_cross_industry_top_k_selection(self) -> None:
        ordered_rows = [
            {"symbol": "600001.SH", "industry_name": "电子", "score": 0.90},
            {"symbol": "600002.SH", "industry_name": "电子", "score": 0.80},
            {"symbol": "600003.SH", "industry_name": "医药", "score": 0.70},
        ]

        selected = _select_top_k_rows(
            ordered_rows,
            top_k=2,
            selection_policy={
                "portfolio_constraints": {
                    "enabled": True,
                    "max_same_industry_picks": 1,
                }
            },
        )

        self.assertEqual([row["symbol"] for row in selected], ["600001.SH", "600003.SH"])

    def test_slot_replacement_can_substitute_low_score_low_amount_rank1(self) -> None:
        ordered_rows = [
            {
                "as_of_date": "2026-01-02",
                "symbol": "600001.SH",
                "score": 3.0,
                "selection_allowed": True,
                "target_label": -0.01,
                "target_total_return": -0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 100_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600002.SH",
                "score": 2.99,
                "selection_allowed": True,
                "target_label": 0.02,
                "target_total_return": 0.01,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 10_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600003.SH",
                "score": 2.98,
                "selection_allowed": True,
                "target_label": 0.03,
                "target_total_return": 0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 10_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600004.SH",
                "score": 2.97,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 50_000_000.0},
            },
        ]
        selection_policy = {
            "slot_replacement": {
                "enabled": True,
                "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
                "max_score": 3.1,
                "max_avg_amount_20d": 150_000_000.0,
                "min_replacement_avg_amount_20d": 20_000_000.0,
                "pool_top_n": 20,
            }
        }

        selected = _select_top_k_rows(
            ordered_rows,
            top_k=3,
            selection_policy=selection_policy,
        )
        returns = _top_k_returns_by_date(ordered_rows, top_k=3, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(ordered_rows, top_k=3, selection_policy=selection_policy)

        self.assertEqual([row["symbol"] for row in selected], ["600004.SH", "600002.SH", "600003.SH"])
        self.assertEqual(selected[0]["slot_replacement_source_symbol"], "600001.SH")
        self.assertEqual(
            selected[0]["slot_replacement_reason"],
            "rank1_low_score_low_amount_full_fill_topn_substitute",
        )
        self.assertEqual(returns[0]["slot_replacement_count"], 1)
        self.assertEqual(
            returns[0]["slot_replacement_reasons"],
            ["rank1_low_score_low_amount_full_fill_topn_substitute"],
        )
        self.assertEqual(picks[0]["slot_replacement_source_symbol"], "600001.SH")

    def test_slot_replacement_can_apply_additional_rank1_rule(self) -> None:
        ordered_rows = [
            {
                "as_of_date": "2026-01-02",
                "symbol": "600001.SH",
                "score": 3.18,
                "selection_allowed": True,
                "target_label": -0.01,
                "target_total_return": -0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 15_000_000.0,
                    "turnover_rate_percentile": 0.12,
                    "amount_10d_vs_20d_percentile": 0.70,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600002.SH",
                "score": 3.10,
                "selection_allowed": True,
                "target_label": 0.02,
                "target_total_return": 0.01,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 80_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600003.SH",
                "score": 3.05,
                "selection_allowed": True,
                "target_label": 0.03,
                "target_total_return": 0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 80_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600004.SH",
                "score": 3.00,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 120_000_000.0},
            },
        ]
        selection_policy = {
            "slot_replacement": {
                "enabled": True,
                "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
                "max_score": 3.1,
                "max_avg_amount_20d": 150_000_000.0,
                "min_replacement_avg_amount_20d": 20_000_000.0,
                "pool_top_n": 20,
                "additional_rank1_replacement_rules": [
                    {
                        "enabled": True,
                        "reason": "rank1_very_low_liquidity_top20_high_amount_substitute",
                        "max_score": 3.2,
                        "max_avg_amount_20d": 20_000_000.0,
                        "max_turnover_rate_percentile": 0.2,
                        "max_amount_10d_vs_20d_percentile": 0.85,
                        "min_replacement_avg_amount_20d": 100_000_000.0,
                        "pool_top_n": 20,
                    }
                ],
            }
        }

        selected = _select_top_k_rows(ordered_rows, top_k=3, selection_policy=selection_policy)
        returns = _top_k_returns_by_date(ordered_rows, top_k=3, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(ordered_rows, top_k=3, selection_policy=selection_policy)

        self.assertEqual([row["symbol"] for row in selected], ["600004.SH", "600002.SH", "600003.SH"])
        self.assertEqual(selected[0]["slot_replacement_source_symbol"], "600001.SH")
        self.assertEqual(
            selected[0]["slot_replacement_reason"],
            "rank1_very_low_liquidity_top20_high_amount_substitute",
        )
        self.assertEqual(returns[0]["slot_replacement_count"], 1)
        self.assertEqual(
            returns[0]["slot_replacement_reasons"],
            ["rank1_very_low_liquidity_top20_high_amount_substitute"],
        )
        self.assertEqual(picks[0]["slot_replacement_source_symbol"], "600001.SH")

    def test_additional_rank1_replacement_rule_can_require_min_amount_expansion_percentile(self) -> None:
        ordered_rows = [
            {
                "as_of_date": "2026-01-02",
                "symbol": "600001.SH",
                "score": 3.30,
                "selection_allowed": True,
                "target_label": -0.01,
                "target_total_return": -0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 120_000_000.0,
                    "turnover_rate_percentile": 0.10,
                    "amount_10d_vs_20d_percentile": 0.90,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600002.SH",
                "score": 3.20,
                "selection_allowed": True,
                "target_label": 0.02,
                "target_total_return": 0.01,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 50_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600003.SH",
                "score": 3.10,
                "selection_allowed": True,
                "target_label": 0.03,
                "target_total_return": 0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 50_000_000.0},
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600004.SH",
                "score": 3.00,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {"avg_amount_20d": 600_000_000.0},
            },
        ]
        selection_policy = {
            "slot_replacement": {
                "enabled": True,
                "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
                "max_score": 3.1,
                "max_avg_amount_20d": 150_000_000.0,
                "min_replacement_avg_amount_20d": 20_000_000.0,
                "pool_top_n": 20,
                "additional_rank1_replacement_rules": [
                    {
                        "enabled": True,
                        "reason": "rank1_high_amount_expansion_top20_high_amount_substitute",
                        "max_score": 3.4,
                        "max_avg_amount_20d": 150_000_000.0,
                        "max_turnover_rate_percentile": 0.2,
                        "min_amount_10d_vs_20d_percentile": 0.85,
                        "min_replacement_avg_amount_20d": 500_000_000.0,
                        "pool_top_n": 20,
                    }
                ],
            }
        }

        selected = _select_top_k_rows(ordered_rows, top_k=3, selection_policy=selection_policy)

        self.assertEqual([row["symbol"] for row in selected], ["600004.SH", "600002.SH", "600003.SH"])
        self.assertEqual(selected[0]["slot_replacement_source_symbol"], "600001.SH")
        self.assertEqual(
            selected[0]["slot_replacement_reason"],
            "rank1_high_amount_expansion_top20_high_amount_substitute",
        )

    def test_additional_rank1_replacement_rule_can_filter_source_and_candidate_momentum_turnover(self) -> None:
        ordered_rows = [
            {
                "as_of_date": "2026-01-02",
                "symbol": "600001.SH",
                "score": 3.30,
                "selection_allowed": True,
                "target_label": -0.10,
                "target_total_return": -0.10,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 120_000_000.0,
                    "return_5d_percentile": 0.08,
                    "turnover_rate_percentile": 0.08,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600002.SH",
                "score": 3.25,
                "selection_allowed": True,
                "target_label": 0.02,
                "target_total_return": 0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 150_000_000.0,
                    "return_5d_percentile": 0.05,
                    "turnover_rate_percentile": 0.05,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600003.SH",
                "score": 3.20,
                "selection_allowed": True,
                "target_label": 0.03,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 160_000_000.0,
                    "return_5d_percentile": 0.30,
                    "turnover_rate_percentile": 0.30,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600004.SH",
                "score": 3.15,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.04,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 180_000_000.0,
                    "return_5d_percentile": 0.20,
                    "turnover_rate_percentile": 0.09,
                },
            },
        ]
        selection_policy = {
            "slot_replacement": {
                "enabled": True,
                "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
                "max_score": 3.1,
                "max_avg_amount_20d": 10_000_000.0,
                "min_replacement_avg_amount_20d": 20_000_000.0,
                "pool_top_n": 20,
                "additional_rank1_replacement_rules": [
                    {
                        "enabled": True,
                        "reason": "rank1_defensive_crowding_top50_substitute",
                        "max_score": 999.0,
                        "max_avg_amount_20d": 10_000_000_000.0,
                        "max_return_5d_percentile": 0.10,
                        "max_turnover_rate_percentile": 0.10,
                        "min_replacement_avg_amount_20d": 100_000_000.0,
                        "min_candidate_return_5d_percentile": 0.10,
                        "max_candidate_turnover_rate_percentile": 0.10,
                        "pool_top_n": 20,
                    }
                ],
            }
        }

        selected = _select_top_k_rows(ordered_rows, top_k=3, selection_policy=selection_policy)

        self.assertEqual([row["symbol"] for row in selected], ["600004.SH", "600002.SH", "600003.SH"])
        self.assertEqual(selected[0]["slot_replacement_source_symbol"], "600001.SH")
        self.assertEqual(selected[0]["slot_replacement_reason"], "rank1_defensive_crowding_top50_substitute")

    def test_additional_rank1_replacement_rule_can_filter_high_momentum_volatile_sources(self) -> None:
        ordered_rows = [
            {
                "as_of_date": "2026-01-02",
                "symbol": "600001.SH",
                "score": 3.40,
                "selection_allowed": True,
                "target_label": -0.08,
                "target_total_return": -0.08,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 200_000_000.0,
                    "return_5d_percentile": 0.95,
                    "return_20d_percentile": 0.99,
                    "benchmark_volatility_20d": 0.06,
                    "max_drawdown_20d": -0.02,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600002.SH",
                "score": 3.25,
                "selection_allowed": True,
                "target_label": 0.02,
                "target_total_return": 0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 40_000_000.0,
                    "return_5d_percentile": 0.80,
                    "return_20d_percentile": 0.90,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600003.SH",
                "score": 3.20,
                "selection_allowed": True,
                "target_label": 0.03,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 80_000_000.0,
                    "return_5d_percentile": 0.30,
                    "return_20d_percentile": 0.90,
                    "turnover_rate_percentile": 0.90,
                },
            },
        ]
        selection_policy = {
            "slot_replacement": {
                "enabled": True,
                "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
                "max_score": 3.1,
                "max_avg_amount_20d": 10_000_000.0,
                "min_replacement_avg_amount_20d": 20_000_000.0,
                "pool_top_n": 20,
                "additional_rank1_replacement_rules": [
                    {
                        "enabled": True,
                        "reason": "rank1_high_momentum_volatile_top50_substitute",
                        "max_score": 999.0,
                        "max_avg_amount_20d": 10_000_000_000.0,
                        "min_return_5d_percentile": 0.90,
                        "min_return_20d_percentile": 0.98,
                        "min_benchmark_volatility_20d": 0.055,
                        "max_drawdown_20d": -0.015,
                        "min_replacement_avg_amount_20d": 50_000_000.0,
                        "min_candidate_return_5d_percentile": 0.0,
                        "max_candidate_turnover_rate_percentile": 1.0,
                        "max_candidate_return_20d_percentile": 1.0,
                        "pool_top_n": 20,
                    }
                ],
            }
        }

        selected = _select_top_k_rows(ordered_rows, top_k=2, selection_policy=selection_policy)

        self.assertEqual([row["symbol"] for row in selected], ["600003.SH", "600002.SH"])
        self.assertEqual(selected[0]["slot_replacement_source_symbol"], "600001.SH")
        self.assertEqual(selected[0]["slot_replacement_reason"], "rank1_high_momentum_volatile_top50_substitute")

    def test_additional_rank1_replacement_rule_supports_generic_source_and_candidate_conditions(self) -> None:
        ordered_rows = [
            {
                "as_of_date": "2026-01-02",
                "symbol": "600001.SH",
                "score": 3.40,
                "selection_allowed": True,
                "target_label": -0.08,
                "target_total_return": -0.08,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 200_000_000.0,
                    "benchmark_return_20d": -0.04,
                    "low_volatility_percentile": 0.99,
                    "return_5d_percentile": 0.96,
                    "turnover_rate_percentile": 0.05,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600002.SH",
                "score": 3.25,
                "selection_allowed": True,
                "target_label": -0.02,
                "target_total_return": -0.02,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 160_000_000.0,
                    "return_20d_percentile": 0.99,
                    "turnover_rate_percentile": 0.80,
                },
            },
            {
                "as_of_date": "2026-01-02",
                "symbol": "600003.SH",
                "score": 3.20,
                "selection_allowed": True,
                "target_label": 0.03,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "feature_values_flat": {
                    "avg_amount_20d": 180_000_000.0,
                    "return_20d_percentile": 0.60,
                    "turnover_rate_percentile": 0.20,
                },
            },
        ]
        selection_policy = {
            "slot_replacement": {
                "enabled": True,
                "mode": "rank1_low_score_low_amount_full_fill_topn_substitute",
                "max_score": 3.1,
                "max_avg_amount_20d": 10_000_000.0,
                "min_replacement_avg_amount_20d": 20_000_000.0,
                "pool_top_n": 20,
                "additional_rank1_replacement_rules": [
                    {
                        "enabled": True,
                        "param_prefix": "rank1_generic",
                        "reason": "rank1_weak_overheated_low_turnover_generic_substitute",
                        "max_score": 999.0,
                        "max_avg_amount_20d": 10_000_000_000.0,
                        "min_replacement_avg_amount_20d": 100_000_000.0,
                        "pool_top_n": 20,
                        "source_conditions": [
                            {"feature": "benchmark_return_20d", "op": "<=", "threshold": -0.03},
                            {"feature": "low_volatility_percentile", "op": ">=", "threshold": 0.98},
                            {"feature": "return_5d_percentile", "op": ">=", "threshold": 0.95},
                            {"feature": "turnover_rate_percentile", "op": "<=", "threshold": 0.10},
                        ],
                        "candidate_conditions": [
                            {
                                "feature": "return_20d_percentile",
                                "op": "<=",
                                "threshold": 0.50,
                                "param_key": "max_candidate_return_20d_percentile",
                            },
                            {"feature": "turnover_rate_percentile", "op": "<=", "threshold": 0.30},
                        ],
                    }
                ],
            }
        }

        selected = _select_top_k_rows(
            ordered_rows,
            top_k=2,
            selection_policy=selection_policy,
            params={"rank1_generic_max_candidate_return_20d_percentile": 0.80},
        )

        self.assertEqual([row["symbol"] for row in selected], ["600003.SH", "600002.SH"])
        self.assertEqual(selected[0]["slot_replacement_source_symbol"], "600001.SH")
        self.assertEqual(
            selected[0]["slot_replacement_reason"],
            "rank1_weak_overheated_low_turnover_generic_substitute",
        )

    def test_conditional_rank_weighting_shifts_first_rank_risk_when_margin_is_low(self) -> None:
        selection_policy = {
            "rank_weighting": {
                "enabled": True,
                "mode": "conditional_first_rank_risk_shift",
                "profile": "top2_91_09",
                "conditional_profile": "top2_50_50",
                "rank1_shift_min_volatility_20d_percentile": 0.80,
                "rank1_shift_max_score_margin": 0.05,
            }
        }
        rows = [
            {
                "score": 1.00,
                "feature_row": {
                    "feature_values": {
                        "cross_sectional": {
                            "volatility_20d_percentile": 0.85,
                        }
                    }
                },
            },
            {"score": 0.97, "feature_row": {"feature_values": {"cross_sectional": {}}}},
        ]

        shifted = _rank_weight_multipliers_for_rows(rows, selection_policy=selection_policy)
        unshifted = _rank_weight_multipliers_for_rows(
            [
                {
                    **rows[0],
                    "feature_row": {
                        "feature_values": {
                            "cross_sectional": {
                                "volatility_20d_percentile": 0.70,
                            }
                        }
                    },
                },
                rows[1],
            ],
            selection_policy=selection_policy,
        )

        self.assertEqual(shifted, [1.0, 1.0])
        self.assertEqual(unshifted, [1.82, 0.18])

        prediction_style_shifted = _rank_weight_multipliers_for_rows(
            [
                {"score": 1.00, "rank_weight_feature_values": {"volatility_20d_percentile": 0.85}},
                {"score": 0.97, "rank_weight_feature_values": {"volatility_20d_percentile": 0.20}},
            ],
            selection_policy=selection_policy,
        )

        self.assertEqual(prediction_style_shifted, [1.0, 1.0])

    def test_conditional_rank_weighting_can_shift_into_top3_tail_blend(self) -> None:
        selection_policy = {
            "rank_weighting": {
                "enabled": True,
                "mode": "conditional_first_rank_risk_shift",
                "profile": "top2_91_09",
                "conditional_profile": "top3_50_30_20",
                "rank1_shift_min_volatility_20d_percentile": 0.78,
                "rank1_shift_max_score_margin": 0.07,
            }
        }
        rows = [
            {"score": 1.00, "feature_values_flat": {"volatility_20d_percentile": 0.80}},
            {"score": 0.95, "feature_values_flat": {"volatility_20d_percentile": 0.20}},
            {"score": 0.90, "feature_values_flat": {"volatility_20d_percentile": 0.10}},
        ]

        shifted = _rank_weight_multipliers_for_rows(rows, selection_policy=selection_policy)
        unshifted = _rank_weight_multipliers_for_rows(
            [{**rows[0], "score": 1.00}, {**rows[1], "score": 0.80}, rows[2]],
            selection_policy=selection_policy,
        )

        self.assertEqual([round(value, 2) for value in shifted], [1.5, 0.9, 0.6])
        self.assertEqual([round(value, 2) for value in unshifted], [2.73, 0.27, 0.0])

    def test_signal_cash_switch_skips_rank1_overheat_reversal_date(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": "rank1_overheat_reversal_cash",
                "rank1_overheat_max_score_margin": 0.03,
                "rank1_overheat_min_return_20d_percentile": 0.98,
                "rank1_overheat_min_return_5d_percentile": 0.90,
                "rank1_overheat_min_benchmark_return_20d": 0.04,
            }
        }
        rows = [
            {
                "score": 1.00,
                "feature_values_flat": {
                    "return_20d_percentile": 0.99,
                    "return_5d_percentile": 0.95,
                    "benchmark_return_20d": 0.05,
                },
            },
            {"score": 0.98, "feature_values_flat": {"return_20d_percentile": 0.40}},
            {"score": 0.90, "feature_values_flat": {"return_20d_percentile": 0.30}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        below_threshold_rows = [
            {**rows[0], "feature_values_flat": {**rows[0]["feature_values_flat"], "return_5d_percentile": 0.89}},
            rows[1],
            rows[2],
        ]

        self.assertEqual(
            [
                row["score"]
                for row in _select_top_k_rows(
                    below_threshold_rows,
                    top_k=3,
                    selection_policy=selection_policy,
                )
            ],
            [1.00, 0.98, 0.90],
        )

    def test_top_k_returns_records_cash_when_signal_cash_switch_blocks_date(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": "rank1_overheat_reversal_cash",
                "rank1_overheat_max_score_margin": 0.03,
                "rank1_overheat_min_return_20d_percentile": 0.98,
                "rank1_overheat_min_return_5d_percentile": 0.90,
                "rank1_overheat_min_benchmark_return_20d": 0.04,
            }
        }
        predictions = [
            {
                "as_of_date": "2026-05-07",
                "score": 1.00,
                "target_label": -0.20,
                "target_total_return": -0.18,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "selection_allowed": True,
                "rank_weight_feature_values": {
                    "return_20d_percentile": 1.0,
                    "return_5d_percentile": 0.98,
                    "benchmark_return_20d": 0.10,
                },
            },
            {
                "as_of_date": "2026-05-07",
                "score": 0.99,
                "target_label": 0.05,
                "target_total_return": 0.04,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "selection_allowed": True,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=3, selection_policy=selection_policy)

        self.assertEqual(len(returns), 1)
        self.assertEqual(returns[0]["selection_state"], "cash")
        self.assertEqual(returns[0]["pick_count"], 0)
        self.assertEqual(returns[0]["mean_net_excess_return"], 0.0)
        self.assertEqual(returns[0]["selection_block_reasons"], ["rank1_overheat_reversal_cash_switch"])

    def test_signal_cash_switch_can_block_weak_regime_low_volatility_rank1(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": "rank1_overheat_or_weak_regime_low_volatility_cash",
                "rank1_overheat_max_score_margin": 0.03,
                "rank1_overheat_min_return_20d_percentile": 0.98,
                "rank1_overheat_min_return_5d_percentile": 0.90,
                "rank1_overheat_min_benchmark_return_20d": 0.04,
                "weak_regime_low_volatility_cash": {
                    "enabled": True,
                    "max_benchmark_return_10d": -0.02,
                    "min_benchmark_volatility_20d": 0.035,
                    "min_low_volatility_percentile": 0.95,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "benchmark_return_10d": -0.03,
                    "benchmark_volatility_20d": 0.04,
                    "low_volatility_percentile": 0.97,
                    "return_20d_percentile": 0.50,
                    "return_5d_percentile": 0.50,
                    "benchmark_return_20d": -0.04,
                },
            },
            {"score": 0.70, "rank_weight_feature_values": {}},
            {"score": 0.60, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        calm_market_rows = [
            {
                **rows[0],
                "rank_weight_feature_values": {
                    **rows[0]["rank_weight_feature_values"],
                    "benchmark_volatility_20d": 0.03,
                },
            },
            rows[1],
            rows[2],
        ]

        self.assertEqual(len(_select_top_k_rows(calm_market_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_cash_switch_can_block_high_confidence_rank1_tail(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_cash",
                "rank1_overheat_max_score_margin": 0.03,
                "rank1_overheat_min_return_20d_percentile": 0.98,
                "rank1_overheat_min_return_5d_percentile": 0.90,
                "rank1_overheat_min_benchmark_return_20d": 0.04,
                "rank1_high_confidence_cash": {
                    "enabled": True,
                    "min_score_margin": 0.10,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "return_20d_percentile": 0.50,
                    "return_5d_percentile": 0.50,
                    "benchmark_return_20d": 0.01,
                },
            },
            {"score": 0.89, "rank_weight_feature_values": {}},
            {"score": 0.80, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        lower_margin_rows = [{**rows[0], "score": 0.98}, rows[1], rows[2]]

        self.assertEqual(len(_select_top_k_rows(lower_margin_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_cash_switch_can_block_market_euphoric_volume_tail(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": (
                    "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_"
                    "market_euphoric_volume_tail_cash"
                ),
                "rank1_market_euphoric_volume_tail_cash": {
                    "enabled": True,
                    "min_benchmark_return_20d": 0.04,
                    "min_return_5d_percentile": 0.98,
                    "min_return_20d_percentile": 0.94,
                    "min_amount_10d_vs_20d_percentile": 0.90,
                    "min_volatility_20d_percentile": 0.55,
                    "max_avg_amount_20d": 300_000_000,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.06,
                    "return_5d_percentile": 0.99,
                    "return_20d_percentile": 0.96,
                    "amount_10d_vs_20d_percentile": 0.92,
                    "volatility_20d_percentile": 0.70,
                    "avg_amount_20d": 180_000_000,
                },
            },
            {"score": 0.96, "rank_weight_feature_values": {}},
            {"score": 0.93, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        high_liquidity_rows = [
            {
                **rows[0],
                "rank_weight_feature_values": {
                    **rows[0]["rank_weight_feature_values"],
                    "avg_amount_20d": 500_000_000,
                },
            },
            rows[1],
            rows[2],
        ]

        self.assertEqual(len(_select_top_k_rows(high_liquidity_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_cash_switch_can_block_weak_low_liquidity_tail(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": (
                    "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                    "weak_low_liquidity_tail_cash"
                ),
                "rank1_weak_low_liquidity_tail_cash": {
                    "enabled": True,
                    "max_benchmark_return_20d": -0.04,
                    "max_benchmark_return_10d": -0.005,
                    "min_low_volatility_percentile": 0.97,
                    "max_turnover_rate_percentile": 0.05,
                    "max_avg_amount_20d": 50_000_000,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": -0.05,
                    "benchmark_return_10d": -0.01,
                    "low_volatility_percentile": 0.99,
                    "turnover_rate_percentile": 0.03,
                    "avg_amount_20d": 20_000_000,
                },
            },
            {"score": 0.96, "rank_weight_feature_values": {}},
            {"score": 0.93, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        stronger_market_rows = [
            {
                **rows[0],
                "rank_weight_feature_values": {
                    **rows[0]["rank_weight_feature_values"],
                    "benchmark_return_20d": -0.01,
                },
            },
            rows[1],
            rows[2],
        ]

        self.assertEqual(len(_select_top_k_rows(stronger_market_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_cash_switch_can_block_congested_low_liquidity_momentum_tail(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": (
                    "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                    "weak_low_liquidity_or_congested_momentum_tail_cash"
                ),
                "rank1_congested_low_liquidity_momentum_tail_cash": {
                    "enabled": True,
                    "min_benchmark_return_20d": -0.02,
                    "max_benchmark_return_10d": 0.01,
                    "min_return_5d_percentile": 0.94,
                    "min_return_20d_percentile": 0.90,
                    "min_amount_10d_vs_20d_percentile": 0.88,
                    "min_volatility_20d_percentile": 0.55,
                    "max_avg_amount_20d": 100_000_000,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.00,
                    "benchmark_return_10d": 0.005,
                    "return_5d_percentile": 0.95,
                    "return_20d_percentile": 0.92,
                    "amount_10d_vs_20d_percentile": 0.90,
                    "volatility_20d_percentile": 0.60,
                    "avg_amount_20d": 80_000_000,
                },
            },
            {"score": 0.96, "rank_weight_feature_values": {}},
            {"score": 0.93, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        high_liquidity_rows = [
            {
                **rows[0],
                "rank_weight_feature_values": {
                    **rows[0]["rank_weight_feature_values"],
                    "avg_amount_20d": 180_000_000,
                },
            },
            rows[1],
            rows[2],
        ]

        self.assertEqual(len(_select_top_k_rows(high_liquidity_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_cash_switch_can_block_high_turnover_momentum_tail(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": (
                    "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                    "weak_low_liquidity_or_congested_momentum_or_high_turnover_momentum_tail_cash"
                ),
                "rank1_high_turnover_momentum_tail_cash": {
                    "enabled": True,
                    "min_benchmark_return_20d": 0.0,
                    "max_benchmark_return_10d": 0.02,
                    "min_return_5d_percentile": 0.98,
                    "min_return_20d_percentile": 0.94,
                    "min_amount_10d_vs_20d_percentile": 0.95,
                    "min_volatility_20d_percentile": 0.65,
                    "min_turnover_rate_percentile": 0.85,
                    "max_avg_amount_20d": 300_000_000,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.01,
                    "benchmark_return_10d": 0.015,
                    "return_5d_percentile": 0.99,
                    "return_20d_percentile": 0.95,
                    "amount_10d_vs_20d_percentile": 0.96,
                    "volatility_20d_percentile": 0.70,
                    "turnover_rate_percentile": 0.90,
                    "avg_amount_20d": 280_000_000,
                },
            },
            {"score": 0.96, "rank_weight_feature_values": {}},
            {"score": 0.93, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        lower_turnover_rows = [
            {
                **rows[0],
                "rank_weight_feature_values": {
                    **rows[0]["rank_weight_feature_values"],
                    "turnover_rate_percentile": 0.80,
                },
            },
            rows[1],
            rows[2],
        ]

        self.assertEqual(len(_select_top_k_rows(lower_turnover_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_cash_switch_can_block_weak_defensive_grind_tail(self) -> None:
        selection_policy = {
            "signal_cash_switch": {
                "enabled": True,
                "mode": (
                    "rank1_overheat_or_weak_regime_low_volatility_or_high_confidence_or_market_euphoric_or_"
                    "weak_low_liquidity_or_congested_momentum_or_weak_defensive_grind_tail_cash"
                ),
                "rank1_weak_defensive_grind_tail_cash": {
                    "enabled": True,
                    "max_benchmark_return_20d": -0.02,
                    "max_benchmark_return_10d": 0.005,
                    "min_low_volatility_percentile": 0.99,
                    "max_turnover_rate_percentile": 0.05,
                    "max_avg_amount_20d": 500_000_000,
                },
            }
        }
        rows = [
            {
                "score": 1.00,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": -0.03,
                    "benchmark_return_10d": -0.01,
                    "benchmark_volatility_20d": 0.03,
                    "low_volatility_percentile": 0.995,
                    "turnover_rate_percentile": 0.03,
                    "avg_amount_20d": 40_000_000,
                },
            },
            {"score": 0.96, "rank_weight_feature_values": {}},
            {"score": 0.93, "rank_weight_feature_values": {}},
        ]

        self.assertEqual(_select_top_k_rows(rows, top_k=3, selection_policy=selection_policy), [])

        higher_turnover_rows = [
            {
                **rows[0],
                "rank_weight_feature_values": {
                    **rows[0]["rank_weight_feature_values"],
                    "turnover_rate_percentile": 0.12,
                },
            },
            rows[1],
            rows[2],
        ]

        self.assertEqual(len(_select_top_k_rows(higher_turnover_rows, top_k=3, selection_policy=selection_policy)), 3)

    def test_signal_position_scaling_reduces_weak_defensive_grind_exposure_without_cash(self) -> None:
        selection_policy = {
            "signal_position_scaling": {
                "enabled": True,
                "mode": "rank1_weak_defensive_grind_scale",
                "max_benchmark_return_20d": -0.04,
                "max_benchmark_return_10d": 0.01,
                "min_low_volatility_percentile": 0.98,
                "max_turnover_rate_percentile": 0.07,
                "max_avg_amount_20d": 80_000_000,
                "position_scale": 0.2,
            }
        }
        predictions = [
            {
                "as_of_date": "2024-09-06",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.28,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": -0.05,
                    "benchmark_return_10d": -0.02,
                    "low_volatility_percentile": 0.99,
                    "turnover_rate_percentile": 0.03,
                    "avg_amount_20d": 40_000_000,
                },
            },
            {
                "as_of_date": "2024-09-06",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.10,
                "target_total_return": 0.11,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertEqual(returns[0]["selection_state"], "invested")
        self.assertAlmostEqual(returns[0]["signal_position_scale"], 0.2)
        self.assertEqual(returns[0]["signal_position_scale_reasons"], ["rank1_weak_defensive_grind_position_scale"])
        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], -0.02)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.2)

    def test_signal_position_scaling_reduces_residual_momentum_amount_tail_exposure(self) -> None:
        selection_policy = {
            "signal_position_scaling": {
                "enabled": True,
                "mode": "rank1_weak_defensive_grind_scale",
                "rank1_residual_momentum_amount_tail_scale": {
                    "enabled": True,
                    "min_benchmark_return_20d": 0.03,
                    "max_benchmark_return_10d": 0.04,
                    "min_return_5d_percentile": 0.98,
                    "min_return_20d_percentile": 0.96,
                    "min_amount_10d_vs_20d_percentile": 0.95,
                    "min_volatility_20d_percentile": 0.30,
                    "max_avg_amount_20d": 600_000_000,
                    "position_scale": 0.3,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2025-08-12",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.25,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.04,
                    "benchmark_return_10d": 0.02,
                    "return_5d_percentile": 0.99,
                    "return_20d_percentile": 0.97,
                    "amount_10d_vs_20d_percentile": 0.96,
                    "volatility_20d_percentile": 0.50,
                    "avg_amount_20d": 500_000_000,
                },
            },
            {
                "as_of_date": "2025-08-12",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.12,
                "target_total_return": 0.10,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertEqual(returns[0]["selection_state"], "invested")
        self.assertAlmostEqual(returns[0]["signal_position_scale"], 0.3)
        self.assertEqual(
            returns[0]["signal_position_scale_reasons"],
            ["rank1_residual_momentum_amount_tail_position_scale"],
        )
        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], -0.027)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.3)

    def test_signal_position_scaling_supports_neutral_chop_date_scale(self) -> None:
        selection_policy = {
            "signal_position_scaling": {
                "enabled": True,
                "mode": "rank1_weak_defensive_grind_scale",
                "rank1_neutral_chop_date_scale": {
                    "enabled": True,
                    "min_benchmark_return_20d": -0.02,
                    "max_benchmark_return_20d": 0.01,
                    "min_benchmark_volatility_20d": 0.03,
                    "max_return_20d_percentile": 0.95,
                    "min_return_5d_percentile": 0.80,
                    "max_drawdown_20d": -0.003,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2026-03-10",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.20,
                "target_total_return": -0.18,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": -0.01,
                    "benchmark_volatility_20d": 0.04,
                    "return_20d_percentile": 0.90,
                    "return_5d_percentile": 0.85,
                    "max_drawdown_20d": -0.01,
                },
            },
            {
                "as_of_date": "2026-03-10",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.08,
                "target_total_return": 0.07,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertEqual(returns[0]["selection_state"], "invested")
        self.assertAlmostEqual(returns[0]["signal_position_scale"], 0.0)
        self.assertEqual(
            returns[0]["signal_position_scale_reasons"],
            ["rank1_neutral_chop_date_position_scale"],
        )
        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.0)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.0)

    def test_rank_position_scaling_reduces_rank1_tail_without_cashing_whole_signal(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "min_benchmark_return_20d": 0.0,
                "max_benchmark_return_10d": 0.04,
                "min_return_5d_percentile": 0.90,
                "min_return_20d_percentile": 0.94,
                "min_amount_10d_vs_20d_percentile": 0.90,
                "min_volatility_20d_percentile": 0.55,
                "min_turnover_rate_percentile": 0.85,
                "max_avg_amount_20d": 100_000_000,
                "position_scale": 0.0,
            }
        }
        predictions = [
            {
                "as_of_date": "2025-11-12",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.25,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.02,
                    "benchmark_return_10d": 0.03,
                    "return_5d_percentile": 0.95,
                    "return_20d_percentile": 0.96,
                    "amount_10d_vs_20d_percentile": 0.93,
                    "volatility_20d_percentile": 0.60,
                    "turnover_rate_percentile": 0.88,
                    "avg_amount_20d": 80_000_000,
                },
            },
            {
                "as_of_date": "2025-11-12",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.12,
                "target_total_return": 0.10,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertEqual(returns[0]["selection_state"], "invested")
        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.06)
        self.assertAlmostEqual(returns[0]["mean_total_return_after_cost"], 0.05)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_high_momentum_low_liquidity_turnover_position_scale"],
        )
        self.assertEqual(picks[0]["rank"], 1)
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(picks[0]["portfolio_weight"], 0.0)
        self.assertEqual(picks[0]["weighted_net_excess_return"], 0.0)
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)

    def test_rank_position_scaling_supports_extreme_momentum_turnover_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "min_benchmark_return_20d": 0.0,
                "max_benchmark_return_10d": 0.04,
                "min_return_5d_percentile": 0.90,
                "min_return_20d_percentile": 0.94,
                "min_amount_10d_vs_20d_percentile": 0.90,
                "min_volatility_20d_percentile": 0.55,
                "min_turnover_rate_percentile": 0.85,
                "max_avg_amount_20d": 100_000_000,
                "position_scale": 0.0,
                "rank1_extreme_momentum_turnover_scale": {
                    "enabled": True,
                    "min_benchmark_return_20d": 0.03,
                    "max_benchmark_return_10d": 0.06,
                    "min_return_5d_percentile": 0.98,
                    "min_return_20d_percentile": 0.96,
                    "min_amount_10d_vs_20d_percentile": 0.88,
                    "min_volatility_20d_percentile": 0.30,
                    "min_turnover_rate_percentile": 0.75,
                    "max_avg_amount_20d": 600_000_000,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2025-08-21",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.20,
                "target_total_return": -0.18,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.04,
                    "benchmark_return_10d": 0.05,
                    "return_5d_percentile": 0.99,
                    "return_20d_percentile": 0.97,
                    "amount_10d_vs_20d_percentile": 0.89,
                    "volatility_20d_percentile": 0.40,
                    "turnover_rate_percentile": 0.80,
                    "avg_amount_20d": 500_000_000,
                },
            },
            {
                "as_of_date": "2025-08-21",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.08,
                "target_total_return": 0.07,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.04)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_extreme_momentum_turnover_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[0]["rank_position_scale_reasons"],
            ["rank1_extreme_momentum_turnover_position_scale"],
        )

    def test_rank_position_scaling_supports_rank2_momentum_turnover_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank2_high_momentum_turnover_scale": {
                    "enabled": True,
                    "min_benchmark_return_20d": 0.0,
                    "max_benchmark_return_10d": 0.02,
                    "min_return_5d_percentile": 0.94,
                    "min_return_20d_percentile": 0.90,
                    "min_amount_10d_vs_20d_percentile": 0.94,
                    "min_volatility_20d_percentile": 0.55,
                    "min_turnover_rate_percentile": 0.85,
                    "max_avg_amount_20d": 800_000_000,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2025-11-11",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": 0.12,
                "target_total_return": 0.10,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
            {
                "as_of_date": "2025-11-11",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.28,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.01,
                    "benchmark_return_10d": 0.01,
                    "return_5d_percentile": 0.95,
                    "return_20d_percentile": 0.91,
                    "amount_10d_vs_20d_percentile": 0.95,
                    "volatility_20d_percentile": 0.60,
                    "turnover_rate_percentile": 0.88,
                    "avg_amount_20d": 700_000_000,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.06)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank2_high_momentum_turnover_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 1.0)
        self.assertEqual(picks[1]["rank_position_scale"], 0.0)
        self.assertEqual(picks[1]["avg_amount_20d"], 700_000_000)
        self.assertEqual(picks[1]["turnover_rate_percentile"], 0.88)
        self.assertEqual(
            picks[1]["rank_position_scale_reasons"],
            ["rank2_high_momentum_turnover_position_scale"],
        )

    def test_rank_position_scaling_supports_rank3_momentum_turnover_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank3_high_momentum_turnover_scale": {
                    "enabled": True,
                    "min_benchmark_return_20d": 0.03,
                    "max_benchmark_return_10d": 0.06,
                    "min_return_5d_percentile": 0.96,
                    "min_return_20d_percentile": 0.90,
                    "min_amount_10d_vs_20d_percentile": 0.90,
                    "min_volatility_20d_percentile": 0.75,
                    "min_turnover_rate_percentile": 0.75,
                    "max_avg_amount_20d": 800_000_000,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2025-08-12",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": 0.10,
                "target_total_return": 0.08,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
            {
                "as_of_date": "2025-08-12",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
            {
                "as_of_date": "2025-08-12",
                "score": 0.8,
                "selection_allowed": True,
                "target_label": -0.24,
                "target_total_return": -0.22,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.04,
                    "benchmark_return_10d": 0.05,
                    "return_5d_percentile": 0.97,
                    "return_20d_percentile": 0.91,
                    "amount_10d_vs_20d_percentile": 0.92,
                    "volatility_20d_percentile": 0.76,
                    "turnover_rate_percentile": 0.78,
                    "avg_amount_20d": 700_000_000,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=3, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=3, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], (0.10 + 0.04) / 3)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 2 / 3)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank3_high_momentum_turnover_position_scale"],
        )
        self.assertEqual(picks[2]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[2]["rank_position_scale_reasons"],
            ["rank3_high_momentum_turnover_position_scale"],
        )

    def test_rank_position_scaling_supports_segment_risk_rules(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "segment_risk_scale_rules": [
                    {
                        "enabled": True,
                        "reason": "rank2_high_turnover_segment_risk_position_scale",
                        "scope": "rank2",
                        "feature": "turnover_rate_percentile",
                        "op": ">=",
                        "threshold": 0.88,
                        "position_scale": 0.5,
                    },
                    {
                        "enabled": True,
                        "reason": "rank3_high_score_segment_risk_position_scale",
                        "scope": "rank3",
                        "feature": "score",
                        "op": ">=",
                        "threshold": 3.3,
                        "position_scale": 0.25,
                    },
                ],
            }
        }
        predictions = [
            {
                "as_of_date": "2025-11-11",
                "score": 3.6,
                "selection_allowed": True,
                "target_label": 0.30,
                "target_total_return": 0.30,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {"turnover_rate_percentile": 0.10},
            },
            {
                "as_of_date": "2025-11-11",
                "score": 3.5,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.30,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {"turnover_rate_percentile": 0.90},
            },
            {
                "as_of_date": "2025-11-11",
                "score": 3.4,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.30,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {"turnover_rate_percentile": 0.10},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=3, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=3, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.025)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5833333333333334)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 2)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            [
                "rank2_high_turnover_segment_risk_position_scale",
                "rank3_high_score_segment_risk_position_scale",
            ],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 1.0)
        self.assertEqual(picks[1]["rank_position_scale"], 0.5)
        self.assertEqual(picks[2]["rank_position_scale"], 0.25)
        self.assertEqual(
            picks[1]["rank_position_scale_reasons"],
            ["rank2_high_turnover_segment_risk_position_scale"],
        )
        self.assertEqual(
            picks[2]["rank_position_scale_reasons"],
            ["rank3_high_score_segment_risk_position_scale"],
        )

    def test_rank_position_scaling_supports_segment_risk_multi_condition_rules(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "segment_risk_scale_rules": [
                    {
                        "enabled": True,
                        "reason": "rank1_low_return_low_turnover_defensive_crowding_position_scale",
                        "scope": "rank1",
                        "conditions": [
                            {
                                "feature": "return_5d_percentile",
                                "op": "<=",
                                "threshold": 0.10,
                            },
                            {
                                "feature": "turnover_rate_percentile",
                                "op": "<=",
                                "threshold": 0.10,
                            },
                        ],
                        "position_scale": 0.0,
                    },
                ],
            }
        }
        predictions = [
            {
                "as_of_date": "2025-11-11",
                "score": 3.6,
                "selection_allowed": True,
                "target_label": -0.30,
                "target_total_return": -0.30,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "return_5d_percentile": 0.08,
                    "turnover_rate_percentile": 0.09,
                },
            },
            {
                "as_of_date": "2025-11-11",
                "score": 3.5,
                "selection_allowed": True,
                "target_label": 0.12,
                "target_total_return": 0.12,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "return_5d_percentile": 0.08,
                    "turnover_rate_percentile": 0.09,
                },
            },
            {
                "as_of_date": "2025-11-11",
                "score": 3.4,
                "selection_allowed": True,
                "target_label": 0.12,
                "target_total_return": 0.12,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "return_5d_percentile": 0.20,
                    "turnover_rate_percentile": 0.09,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=3, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=3, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.08)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.6666666666666666)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_low_return_low_turnover_defensive_crowding_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)
        self.assertEqual(picks[2]["rank_position_scale"], 1.0)

    def test_rank_position_scaling_supports_rank1_neutral_chop_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank1_neutral_chop_scale": {
                    "enabled": True,
                    "min_benchmark_return_20d": -0.01,
                    "max_benchmark_return_20d": 0.03,
                    "max_benchmark_return_10d": 0.03,
                    "min_benchmark_volatility_20d": 0.04,
                    "min_return_5d_percentile": 0.64,
                    "max_return_20d_percentile": 0.97,
                    "min_amount_10d_vs_20d_percentile": 0.59,
                    "max_drawdown_20d": -0.003,
                    "max_avg_amount_20d": 2_300_000_000,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2025-11-12",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.09,
                "target_total_return": -0.08,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_20d": 0.02,
                    "benchmark_return_10d": 0.01,
                    "benchmark_volatility_20d": 0.045,
                    "return_5d_percentile": 0.70,
                    "return_20d_percentile": 0.85,
                    "amount_10d_vs_20d_percentile": 0.80,
                    "max_drawdown_20d": -0.02,
                    "avg_amount_20d": 500_000_000,
                },
            },
            {
                "as_of_date": "2025-11-12",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {},
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.02)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_neutral_chop_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[0]["rank_position_scale_reasons"],
            ["rank1_neutral_chop_position_scale"],
        )
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)

    def test_rank_position_scaling_supports_rank1_no_drawdown_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank1_no_drawdown_scale": {
                    "enabled": True,
                    "min_max_drawdown_20d": 0.0,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2025-08-18",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.10,
                "target_total_return": -0.09,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "max_drawdown_20d": 0.0,
                },
            },
            {
                "as_of_date": "2025-08-18",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.06,
                "target_total_return": 0.05,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "max_drawdown_20d": -0.02,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.03)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_no_drawdown_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[0]["rank_position_scale_reasons"],
            ["rank1_no_drawdown_position_scale"],
        )
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)

    def test_rank_position_scaling_supports_rank1_high_position_pullback_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank1_high_position_pullback_scale": {
                    "enabled": True,
                    "min_max_drawdown_40d": -0.044,
                    "max_return_1d": -0.016,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2026-03-13",
                "score": 1.0,
                "selection_allowed": True,
                "target_label": -0.08,
                "target_total_return": -0.07,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "max_drawdown_40d": -0.03,
                    "return_1d": -0.02,
                },
            },
            {
                "as_of_date": "2026-03-13",
                "score": 0.9,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "max_drawdown_40d": -0.08,
                    "return_1d": -0.02,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.02)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_high_position_pullback_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[0]["rank_position_scale_reasons"],
            ["rank1_high_position_pullback_position_scale"],
        )
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)

    def test_rank_position_scaling_supports_rank1_low_score_high_position_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank1_low_score_high_position_scale": {
                    "enabled": True,
                    "max_score": 3.39,
                    "min_distance_from_40d_high": -0.003,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2026-03-13",
                "score": 3.2,
                "selection_allowed": True,
                "target_label": -0.08,
                "target_total_return": -0.07,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "distance_from_40d_high": -0.001,
                },
            },
            {
                "as_of_date": "2026-03-13",
                "score": 3.0,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "distance_from_40d_high": -0.001,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.02)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_low_score_high_position_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[0]["rank_position_scale_reasons"],
            ["rank1_low_score_high_position_position_scale"],
        )
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)

    def test_rank_position_scaling_supports_rank1_benchmark_momentum_pullback_subrule(self) -> None:
        selection_policy = {
            "rank_position_scaling": {
                "enabled": True,
                "mode": "rank1_high_momentum_low_liquidity_turnover_scale",
                "rank1_benchmark_momentum_pullback_scale": {
                    "enabled": True,
                    "min_benchmark_return_10d": 0.02,
                    "min_return_20d_percentile": 0.98,
                    "max_return_1d": -0.014,
                    "position_scale": 0.0,
                },
            }
        }
        predictions = [
            {
                "as_of_date": "2024-02-20",
                "score": 3.8,
                "selection_allowed": True,
                "target_label": -0.08,
                "target_total_return": -0.07,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_10d": 0.025,
                    "return_20d_percentile": 0.99,
                    "return_1d": -0.02,
                },
            },
            {
                "as_of_date": "2024-02-20",
                "score": 3.1,
                "selection_allowed": True,
                "target_label": 0.04,
                "target_total_return": 0.03,
                "target_horizon_days": 20,
                "portfolio_weight": 1.0,
                "rank_weight_feature_values": {
                    "benchmark_return_10d": 0.025,
                    "return_20d_percentile": 0.99,
                    "return_1d": -0.02,
                },
            },
        ]

        returns = _top_k_returns_by_date(predictions, top_k=2, selection_policy=selection_policy)
        picks = _top_k_picks_by_date(predictions, top_k=2, selection_policy=selection_policy)

        self.assertAlmostEqual(returns[0]["mean_net_excess_return"], 0.02)
        self.assertAlmostEqual(returns[0]["gross_exposure"], 0.5)
        self.assertEqual(returns[0]["rank_position_scaled_pick_count"], 1)
        self.assertEqual(
            returns[0]["rank_position_scale_reasons"],
            ["rank1_benchmark_momentum_pullback_position_scale"],
        )
        self.assertEqual(picks[0]["rank_position_scale"], 0.0)
        self.assertEqual(
            picks[0]["rank_position_scale_reasons"],
            ["rank1_benchmark_momentum_pullback_position_scale"],
        )
        self.assertEqual(picks[1]["rank_position_scale"], 1.0)

    def test_rank_signal_feature_subset_keeps_market_tail_cash_inputs(self) -> None:
        subset = _rank_signal_feature_subset(
            {
                "avg_amount_20d": 180_000_000,
                "amount_10d_vs_20d_percentile": 0.92,
                "return_5d_percentile": 0.99,
                "return_20d_percentile": 0.96,
                "turnover_rate_percentile": 0.04,
                "max_drawdown_20d": -0.05,
                "max_drawdown_40d": -0.08,
                "distance_from_40d_high": -0.03,
                "return_1d": -0.02,
                "unrelated_feature": 1.23,
            }
        )

        self.assertEqual(subset["avg_amount_20d"], 180_000_000)
        self.assertEqual(subset["turnover_rate_percentile"], 0.04)
        self.assertEqual(subset["max_drawdown_20d"], -0.05)
        self.assertEqual(subset["max_drawdown_40d"], -0.08)
        self.assertEqual(subset["distance_from_40d_high"], -0.03)
        self.assertEqual(subset["return_1d"], -0.02)
        self.assertNotIn("unrelated_feature", subset)

    def test_cash_switch_all_condition_mode_requires_every_market_stress_condition(self) -> None:
        selection_policy = {
            "cash_switch": {
                "enabled": True,
                "condition_mode": "all",
                "min_benchmark_return_10d": -0.01,
                "min_benchmark_return_20d": -0.03,
                "max_benchmark_volatility_20d": 0.08,
            }
        }

        allowed, blockers = _selection_allowed(
            {
                "benchmark_return_10d": -0.02,
                "benchmark_return_20d": -0.02,
                "benchmark_volatility_20d": 0.09,
            },
            selection_policy=selection_policy,
            params={},
        )
        blocked, stress_blockers = _selection_allowed(
            {
                "benchmark_return_10d": -0.02,
                "benchmark_return_20d": -0.04,
                "benchmark_volatility_20d": 0.09,
            },
            selection_policy=selection_policy,
            params={},
        )

        self.assertTrue(allowed)
        self.assertEqual(blockers, [])
        self.assertFalse(blocked)
        self.assertEqual(
            stress_blockers,
            [
                "benchmark_return_10d_below_cash_switch",
                "benchmark_return_20d_below_cash_switch",
                "benchmark_volatility_20d_above_cash_switch",
            ],
        )

    def test_regime_scaled_position_weight_reduces_exposure_in_weak_volatile_market(self) -> None:
        selection_policy = {
            "position_weighting": {
                "enabled": True,
                "mode": "volatility_turnover_regime_scaled",
                "full_weight_max_volatility_20d_percentile": 0.80,
                "min_weight_volatility_20d_percentile": 0.96,
                "full_weight_max_turnover_rate_percentile": 0.80,
                "min_weight_turnover_rate_percentile": 0.93,
                "min_position_weight": 0.70,
                "full_weight_min_benchmark_return_20d": 0.0,
                "min_weight_benchmark_return_20d": -0.06,
                "full_weight_max_benchmark_volatility_20d": 0.04,
                "min_weight_benchmark_volatility_20d": 0.08,
                "regime_min_position_weight": 0.55,
            }
        }

        normal_weight = _position_weight(
            {
                "volatility_20d_percentile": 0.50,
                "turnover_rate_percentile": 0.50,
                "benchmark_return_20d": 0.02,
                "benchmark_volatility_20d": 0.02,
            },
            selection_policy=selection_policy,
            params={},
        )
        weak_weight = _position_weight(
            {
                "volatility_20d_percentile": 0.50,
                "turnover_rate_percentile": 0.50,
                "benchmark_return_20d": -0.06,
                "benchmark_volatility_20d": 0.09,
            },
            selection_policy=selection_policy,
            params={},
        )

        self.assertEqual(normal_weight, 1.0)
        self.assertEqual(weak_weight, 0.55)

    def test_conditional_regime_stock_risk_scaling_keeps_low_risk_weak_market_pick_full_weight(self) -> None:
        selection_policy = {
            "position_weighting": {
                "enabled": True,
                "mode": "conditional_regime_stock_risk_scaled",
                "full_weight_max_volatility_20d_percentile": 0.85,
                "min_weight_volatility_20d_percentile": 0.96,
                "full_weight_max_turnover_rate_percentile": 0.85,
                "min_weight_turnover_rate_percentile": 0.93,
                "min_position_weight": 0.80,
                "weak_regime_benchmark_return_20d_threshold": 0.0,
                "weak_full_weight_max_volatility_20d_percentile": 0.70,
                "weak_full_weight_max_turnover_rate_percentile": 0.80,
                "weak_regime_min_position_weight": 0.60,
            }
        }

        low_risk_weak_market = _position_weight(
            {
                "volatility_20d_percentile": 0.50,
                "turnover_rate_percentile": 0.50,
                "benchmark_return_20d": -0.04,
                "benchmark_volatility_20d": 0.03,
            },
            selection_policy=selection_policy,
            params={},
        )
        high_risk_weak_market = _position_weight(
            {
                "volatility_20d_percentile": 0.95,
                "turnover_rate_percentile": 0.90,
                "benchmark_return_20d": -0.04,
                "benchmark_volatility_20d": 0.03,
            },
            selection_policy=selection_policy,
            params={},
        )

        self.assertEqual(low_risk_weak_market, 1.0)
        self.assertLess(high_risk_weak_market, 0.80)

    def test_exit_policy_selects_short_horizon_for_weak_high_risk_rows(self) -> None:
        selection_policy = {
            "exit_policy": {
                "enabled": True,
                "mode": "regime_stock_risk_adaptive_5_10_20",
                "weak_regime_benchmark_return_20d_threshold": 0.0,
                "exit_stock_risk_volatility_20d_percentile": 0.80,
                "risk_exit_horizon_days": 5,
                "weak_regime_exit_horizon_days": 10,
                "strong_regime_exit_horizon_days": 20,
            }
        }

        self.assertEqual(
            _exit_horizon_days(
                {
                    "benchmark_return_20d": -0.02,
                    "benchmark_volatility_20d": 0.03,
                    "volatility_20d_percentile": 0.90,
                    "turnover_rate_percentile": 0.20,
                },
                selection_policy=selection_policy,
                params={},
                default_horizon_days=20,
            ),
            5,
        )
        self.assertEqual(
            _exit_horizon_days(
                {
                    "benchmark_return_20d": -0.02,
                    "benchmark_volatility_20d": 0.03,
                    "volatility_20d_percentile": 0.50,
                    "turnover_rate_percentile": 0.20,
                },
                selection_policy=selection_policy,
                params={},
                default_horizon_days=20,
            ),
            10,
        )
        self.assertEqual(
            _exit_horizon_days(
                {
                    "benchmark_return_20d": 0.05,
                    "benchmark_volatility_20d": 0.03,
                    "volatility_20d_percentile": 0.90,
                    "turnover_rate_percentile": 0.20,
                },
                selection_policy=selection_policy,
                params={},
                default_horizon_days=20,
            ),
            20,
        )

    def test_rank_weight_profile_preserves_full_notional_while_tilting_to_top_rank(self) -> None:
        selection_policy = {
            "rank_weighting": {
                "enabled": True,
                "mode": "fixed_share_profile",
                "profile": "top2_91_09",
            }
        }

        first_rank = _rank_weight_multiplier(1, top_k=2, selection_policy=selection_policy, params={})
        second_rank = _rank_weight_multiplier(2, top_k=2, selection_policy=selection_policy, params={})
        sleeve_return = _weighted_return(
            [
                {"target_label": 0.10, "portfolio_weight": 1.0},
                {"target_label": -0.10, "portfolio_weight": 1.0},
            ],
            selection_policy=selection_policy,
            params={},
        )

        self.assertEqual(first_rank, 1.82)
        self.assertEqual(second_rank, 0.18)
        self.assertAlmostEqual((first_rank + second_rank) / 2, 1.0)
        self.assertAlmostEqual(sleeve_return, 0.082)

    def test_stability_adjusted_sort_key_honors_declared_tie_break_order(self) -> None:
        selection_policy = {
            "mode": "concentrated_top_k",
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "trial_selection_policy": {
                "mode": "stability_adjusted",
                "minimum_period_count_for_total_return_floor": 500,
                "minimum_portfolio_total_return": 1.50,
                "minimum_portfolio_max_drawdown": -0.12,
                "tie_break_order": [
                    "portfolio_total_return_floor_first_after_500_periods",
                    "negative_month_count_asc",
                    "portfolio_total_return_desc",
                    "portfolio_max_drawdown_desc",
                ],
            },
        }
        lower_return = {
            "selection_policy": selection_policy,
            "selected_top_k_net_excess_mean": 0.017,
            "trial_stability": {
                "period_count": 653,
                "portfolio_total_return": 1.51,
                "portfolio_max_drawdown": -0.11,
                "negative_month_count": 12,
            },
        }
        higher_return = {
            "selection_policy": selection_policy,
            "selected_top_k_net_excess_mean": 0.018,
            "trial_stability": {
                "period_count": 653,
                "portfolio_total_return": 1.53,
                "portfolio_max_drawdown": -0.112,
                "negative_month_count": 12,
            },
        }

        self.assertGreater(_sort_key(higher_return), _sort_key(lower_return))

    def test_comparison_report_arbitrates_with_registry_selection_policy(self) -> None:
        old_candidate_run_policy = {
            "mode": "concentrated_top_k",
            "top_k": 1,
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "trial_selection_policy": {
                "mode": "stability_adjusted",
                "minimum_period_count_for_total_return_floor": 500,
                "minimum_portfolio_total_return": 1.0,
                "minimum_portfolio_max_drawdown": -0.20,
                "tie_break_order": [
                    "portfolio_total_return_floor_first_after_500_periods",
                    "negative_month_count_asc",
                    "portfolio_total_return_desc",
                ],
            },
        }
        registry_policy = {
            **old_candidate_run_policy,
            "trial_selection_policy": {
                **old_candidate_run_policy["trial_selection_policy"],
                "tie_break_order": [
                    "portfolio_total_return_floor_first_after_500_periods",
                    "portfolio_total_return_desc",
                    "portfolio_path_drawdown_sum_desc",
                    "negative_month_count_asc",
                ],
            },
        }

        def _summary(trial_id: str, selected_mean: float) -> dict[str, object]:
            return {
                "trial_id": trial_id,
                "model_spec_id": "spec",
                "selection_policy": old_candidate_run_policy,
                "blocking_gate_ids": [],
                "metrics": {
                    "rank_ic_mean": 0.01,
                    "positive_rank_ic_rate": 0.5,
                    "selected_top_k": 1,
                    "selected_top_k_net_excess_mean": selected_mean,
                    "positive_selected_top_k_rate": 0.5,
                    "top_5_net_excess_mean": selected_mean,
                    "positive_top_5_rate": 0.5,
                    "top_10_net_excess_mean": selected_mean,
                    "top_quantile_net_excess_mean": selected_mean,
                    "top_bottom_spread_mean": 0.02,
                    "labeled_prediction_count": 520,
                },
            }

        def _returns(*, net_return: float, total_return: float, negative_first_month: bool) -> list[dict[str, object]]:
            rows: list[dict[str, object]] = []
            for offset in range(520):
                as_of_date = date(2024, 1, 1) + timedelta(days=offset)
                row_net_return = -0.01 if negative_first_month and offset < 31 else net_return
                rows.append(
                    {
                        "as_of_date": as_of_date.isoformat(),
                        "month": as_of_date.isoformat()[:7],
                        "mean_net_excess_return": row_net_return,
                        "mean_total_return_after_cost": total_return,
                    }
                )
            return rows

        run = {
            "artifact_id": "candidate-run-unit",
            "trial_count": 2,
            "prediction_row_count": 1040,
            "trial_summaries": [
                _summary("spec:stable-lower-return", 0.03),
                _summary("spec:higher-return-path-choice", 0.04),
            ],
            "trial_diagnostics": [
                {
                    "trial_id": "spec:stable-lower-return",
                    "target_horizon_days": 20,
                    "selected_top_k_returns_by_date": _returns(
                        net_return=0.02,
                        total_return=0.01,
                        negative_first_month=False,
                    ),
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2024-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
                {
                    "trial_id": "spec:higher-return-path-choice",
                    "target_horizon_days": 20,
                    "selected_top_k_returns_by_date": _returns(
                        net_return=0.025,
                        total_return=0.035,
                        negative_first_month=True,
                    ),
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2024-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
            ],
        }
        registry = {
            "artifact_id": "registry-unit",
            "model_specs": [{"model_spec_id": "spec", "selection_policy": registry_policy}],
        }

        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        best = report["candidate_leaderboard"][0]
        self.assertEqual(best["trial_id"], "spec:higher-return-path-choice")
        self.assertEqual(best["selection_policy"], registry_policy)
        self.assertEqual(best["candidate_run_selection_policy"], old_candidate_run_policy)

    def test_rolling_sleeve_curve_uses_row_level_target_horizon(self) -> None:
        variable_horizon = _rolling_sleeve_curve(
            [
                {
                    "mean_total_return_after_cost": 0.05,
                    "mean_net_excess_return": 0.04,
                    "mean_target_horizon_days": 5,
                }
            ],
            horizon_days=20,
        )
        fixed_horizon = _rolling_sleeve_curve(
            [{"mean_total_return_after_cost": 0.05, "mean_net_excess_return": 0.04}],
            horizon_days=20,
        )

        self.assertGreater(variable_horizon["total_return"], fixed_horizon["total_return"])
        self.assertEqual(variable_horizon["mean_target_horizon_days"], 5)

    def test_deterministic_concentrated_specs_do_not_fit_unused_linear_models(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()

        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["concentrated_liquidity_momentum_20d_v1"],
        )

        families = {
            summary["fitted_model_family"]
            for trial in run["trial_summaries"]
            for summary in trial["fit_summaries"]
        }
        self.assertEqual(families, {"concentrated_liquidity_momentum_ranker_no_fit"})

    def test_artifact_row_iterator_streams_chunked_nested_rows(self) -> None:
        artifact_path = Path(self.temp_dir.name) / "chunked-artifact.json"
        payload = {
            "artifact_id": "unit-artifact",
            "rows": [
                {
                    "row_id": "r1",
                    "payload": {"nested": ["alpha", {"text": "brace } inside string"}]},
                },
                {
                    "row_id": "r2",
                    "payload": {"quote": 'escaped " quote', "bracket": "] inside string"},
                },
            ],
            "tail": "ignored",
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        original_chunk_size = model_candidate_runner.ARTIFACT_ROW_ITER_CHUNK_BYTES
        try:
            model_candidate_runner.ARTIFACT_ROW_ITER_CHUNK_BYTES = 17
            rows = list(model_candidate_runner._iter_artifact_rows(artifact_path))
        finally:
            model_candidate_runner.ARTIFACT_ROW_ITER_CHUNK_BYTES = original_chunk_size

        self.assertEqual([row["row_id"] for row in rows], ["r1", "r2"])
        self.assertEqual(rows[0]["payload"]["nested"][1]["text"], "brace } inside string")
        self.assertEqual(rows[1]["payload"]["quote"], 'escaped " quote')

    def test_streamed_candidate_runner_reuses_matrix_files_without_full_payload_load(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        feature_path = Path(self.temp_dir.name) / "feature-matrix.json"
        label_path = Path(self.temp_dir.name) / "label-matrix.json"
        feature_path.write_text(json.dumps(feature_matrix, ensure_ascii=False), encoding="utf-8")
        label_path.write_text(json.dumps(label_matrix, ensure_ascii=False), encoding="utf-8")
        regular = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run-regular",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )

        run = build_streamed_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run-streamed",
            feature_matrix_artifact=feature_path,
            label_matrix_artifact=label_path,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
            source_db_snapshot_id="unit-snapshot",
            source_data_time_range={"as_of_start": "2026-01-01", "as_of_end": "2026-01-03"},
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run-streamed",
            candidate_run=run,
            model_spec_registry=registry,
        )

        self.assertTrue(run["validation_protocol"]["stream_replay"])
        self.assertEqual(run["source_db_snapshot_id"], "unit-snapshot")
        self.assertEqual(run["source_data_time_range"], {"as_of_start": "2026-01-01", "as_of_end": "2026-01-03"})
        self.assertEqual(run["trial_count"], 1)
        self.assertGreater(run["prediction_row_count"], 0)
        self.assertGreater(run["stored_prediction_row_count"], 0)
        self.assertEqual(run["prediction_rows_truncated"], False)
        self.assertGreater(len(run["trial_diagnostics"][0]["selected_top_k_returns_by_date"]), 0)
        self.assertEqual(run["trial_summaries"][0]["metrics"], regular["trial_summaries"][0]["metrics"])
        self.assertEqual(
            run["trial_diagnostics"][0]["selected_top_k_returns_by_date"],
            regular["trial_diagnostics"][0]["selected_top_k_returns_by_date"],
        )
        self.assertEqual(report["summary"]["candidate_run_id"], run["artifact_id"])
        self.assertEqual(report["source_db_snapshot_id"], "unit-snapshot")

    def test_comparison_report_summarizes_trials_and_remains_blocked(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )

        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        self.assertEqual(report["artifact_type"], "model_comparison_report")
        self.assertEqual(report["promotion_status"], "blocked_from_production")
        self.assertEqual(report["summary"]["candidate_run_id"], run["artifact_id"])
        self.assertEqual(len(report["candidate_leaderboard"]), 1)
        self.assertIn("top_5_net_excess_mean", report["candidate_leaderboard"][0])
        self.assertEqual(report["overfit_diagnostics"]["diagnostic_scope"], "candidate_run_trial_split_proxy")
        self.assertEqual(report["overfit_diagnostics"]["period_source"], "best_trial_as_of_date_rank_ic")
        self.assertEqual(
            report["execution_diagnostics"]["diagnostic_scope"],
            "comparison_report_execution_stress_proxy",
        )
        self.assertIn("cost_stress", report["execution_diagnostics"])
        self.assertIn("capacity_diagnostics", report["execution_diagnostics"])
        capacity = report["execution_diagnostics"]["capacity_diagnostics"]
        self.assertIn("capacity_envelope", capacity)
        self.assertIn("capacity_tier_stats", capacity["capacity_envelope"])
        self.assertIn("all_active_full_fill_portfolio_notional_cny", capacity["capacity_envelope"])
        self.assertIn("capacity_contract", capacity)
        self.assertIn("configured_governance_status", capacity["capacity_contract"])
        self.assertIn("claim_ceiling", capacity["capacity_contract"])

    def test_comparison_report_can_select_stability_adjusted_trial(self) -> None:
        selection_policy = {
            "mode": "concentrated_top_k",
            "top_k": 1,
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "trial_selection_policy": {
                "mode": "stability_adjusted",
                "minimum_selected_top_k_net_excess_mean": 0.06,
            },
        }
        run = {
            "artifact_id": "candidate-run-unit",
            "trial_count": 2,
            "prediction_row_count": 4,
            "trial_summaries": [
                {
                    "trial_id": "spec:trial-high-mean",
                    "model_spec_id": "spec",
                    "selection_policy": selection_policy,
                    "blocking_gate_ids": [],
                    "metrics": {
                        "rank_ic_mean": 0.01,
                        "positive_rank_ic_rate": 0.5,
                        "selected_top_k": 1,
                        "selected_top_k_net_excess_mean": 0.071,
                        "positive_selected_top_k_rate": 0.5,
                        "top_5_net_excess_mean": 0.071,
                        "positive_top_5_rate": 0.5,
                        "top_10_net_excess_mean": 0.04,
                        "top_quantile_net_excess_mean": 0.01,
                        "top_bottom_spread_mean": 0.02,
                        "labeled_prediction_count": 4,
                    },
                },
                {
                    "trial_id": "spec:trial-stable",
                    "model_spec_id": "spec",
                    "selection_policy": selection_policy,
                    "blocking_gate_ids": [],
                    "metrics": {
                        "rank_ic_mean": 0.01,
                        "positive_rank_ic_rate": 0.5,
                        "selected_top_k": 1,
                        "selected_top_k_net_excess_mean": 0.069,
                        "positive_selected_top_k_rate": 0.5,
                        "top_5_net_excess_mean": 0.069,
                        "positive_top_5_rate": 0.5,
                        "top_10_net_excess_mean": 0.04,
                        "top_quantile_net_excess_mean": 0.01,
                        "top_bottom_spread_mean": 0.02,
                        "labeled_prediction_count": 4,
                    },
                },
            ],
            "trial_diagnostics": [
                {
                    "trial_id": "spec:trial-high-mean",
                    "selected_top_k_returns_by_date": [
                        {"as_of_date": "2026-01-01", "month": "2026-01", "mean_net_excess_return": 0.20},
                        {"as_of_date": "2026-02-01", "month": "2026-02", "mean_net_excess_return": -0.03},
                    ],
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2026-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
                {
                    "trial_id": "spec:trial-stable",
                    "selected_top_k_returns_by_date": [
                        {"as_of_date": "2026-01-01", "month": "2026-01", "mean_net_excess_return": 0.07},
                        {"as_of_date": "2026-02-01", "month": "2026-02", "mean_net_excess_return": 0.068},
                    ],
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2026-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
            ],
        }
        registry = {"artifact_id": "registry-unit", "model_specs": [{"model_spec_id": "spec"}]}

        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        self.assertEqual(report["candidate_leaderboard"][0]["trial_id"], "spec:trial-stable")
        self.assertEqual(report["candidate_leaderboard"][0]["trial_stability"]["negative_month_count"], 0)
        self.assertIn("monthly_return_summary", report["execution_diagnostics"])
        self.assertIn("portfolio_curve", report["execution_diagnostics"])
        self.assertIn("result_anchor_comparison", report["execution_diagnostics"])
        self.assertIn(
            "strict_next_close_governance_leader",
            report["execution_diagnostics"]["result_anchor_comparison"]["anchors"],
        )
        self.assertIn(
            "overfit:insufficient_eligible_trials_for_pbo",
            report["gate_readout"]["blocking_gate_ids"],
        )
        self.assertIn(
            "overfit:insufficient_independent_walk_forward_splits_for_overfit",
            report["gate_readout"]["blocking_gate_ids"],
        )
        self.assertEqual(report["winner_dependency"]["best_trial_id"], "spec:trial-stable")
        self.assertIn("removal_checks", report["winner_dependency"])

    def test_comparison_report_uses_portfolio_floor_for_long_stability_window(self) -> None:
        selection_policy = {
            "mode": "concentrated_top_k",
            "top_k": 1,
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "trial_selection_policy": {
                "mode": "stability_adjusted",
                "minimum_selected_top_k_net_excess_mean": 0.06,
                "minimum_period_count_for_total_return_floor": 500,
                "minimum_portfolio_total_return": 1.0,
                "minimum_portfolio_max_drawdown": -0.20,
            },
        }

        def _summary(trial_id: str, selected_mean: float) -> dict[str, object]:
            return {
                "trial_id": trial_id,
                "model_spec_id": "spec",
                "selection_policy": selection_policy,
                "blocking_gate_ids": [],
                "metrics": {
                    "rank_ic_mean": 0.01,
                    "positive_rank_ic_rate": 0.5,
                    "selected_top_k": 1,
                    "selected_top_k_net_excess_mean": selected_mean,
                    "positive_selected_top_k_rate": 0.5,
                    "top_5_net_excess_mean": selected_mean,
                    "positive_top_5_rate": 0.5,
                    "top_10_net_excess_mean": 0.04,
                    "top_quantile_net_excess_mean": 0.01,
                    "top_bottom_spread_mean": 0.02,
                    "labeled_prediction_count": 520,
                },
            }

        def _returns(start: date, *, net_return: float, total_return: float) -> list[dict[str, object]]:
            rows: list[dict[str, object]] = []
            for offset in range(520):
                as_of_date = start + timedelta(days=offset)
                rows.append(
                    {
                        "as_of_date": as_of_date.isoformat(),
                        "month": as_of_date.isoformat()[:7],
                        "mean_net_excess_return": net_return,
                        "mean_total_return_after_cost": total_return,
                    }
                )
            return rows

        run = {
            "artifact_id": "candidate-run-unit",
            "trial_count": 2,
            "prediction_row_count": 1040,
            "trial_summaries": [
                _summary("spec:trial-short-mean-only", 0.08),
                _summary("spec:trial-long-portfolio-floor", 0.055),
            ],
            "trial_diagnostics": [
                {
                    "trial_id": "spec:trial-short-mean-only",
                    "target_horizon_days": 20,
                    "selected_top_k_returns_by_date": _returns(
                        date(2024, 1, 1),
                        net_return=0.08,
                        total_return=0.005,
                    ),
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2024-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
                {
                    "trial_id": "spec:trial-long-portfolio-floor",
                    "target_horizon_days": 20,
                    "selected_top_k_returns_by_date": _returns(
                        date(2024, 1, 1),
                        net_return=0.055,
                        total_return=0.05,
                    ),
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2024-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
            ],
        }
        registry = {"artifact_id": "registry-unit", "model_specs": [{"model_spec_id": "spec"}]}

        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        best = report["candidate_leaderboard"][0]
        self.assertEqual(best["trial_id"], "spec:trial-long-portfolio-floor")
        self.assertLess(best["selected_top_k_net_excess_mean"], 0.06)
        self.assertGreater(best["trial_stability"]["portfolio_total_return"], 1.0)

    def test_comparison_report_prefers_return_when_long_window_trials_miss_floor(self) -> None:
        selection_policy = {
            "mode": "concentrated_top_k",
            "top_k": 1,
            "evaluation_return_metric": "selected_top_k_net_excess_mean",
            "trial_selection_policy": {
                "mode": "stability_adjusted",
                "minimum_period_count_for_total_return_floor": 500,
                "minimum_portfolio_total_return": 2.0,
                "minimum_portfolio_max_drawdown": -0.20,
            },
        }

        def _summary(trial_id: str, selected_mean: float) -> dict[str, object]:
            return {
                "trial_id": trial_id,
                "model_spec_id": "spec",
                "selection_policy": selection_policy,
                "blocking_gate_ids": [],
                "metrics": {
                    "rank_ic_mean": 0.01,
                    "positive_rank_ic_rate": 0.5,
                    "selected_top_k": 1,
                    "selected_top_k_net_excess_mean": selected_mean,
                    "positive_selected_top_k_rate": 0.5,
                    "top_5_net_excess_mean": selected_mean,
                    "positive_top_5_rate": 0.5,
                    "top_10_net_excess_mean": selected_mean,
                    "top_quantile_net_excess_mean": selected_mean,
                    "top_bottom_spread_mean": 0.02,
                    "labeled_prediction_count": 520,
                },
            }

        def _returns(*, total_return: float, negative_first_month: bool) -> list[dict[str, object]]:
            rows: list[dict[str, object]] = []
            for offset in range(520):
                as_of_date = date(2024, 1, 1) + timedelta(days=offset)
                net_return = -0.02 if negative_first_month and offset < 31 else 0.02
                rows.append(
                    {
                        "as_of_date": as_of_date.isoformat(),
                        "month": as_of_date.isoformat()[:7],
                        "mean_net_excess_return": net_return,
                        "mean_total_return_after_cost": total_return,
                    }
                )
            return rows

        run = {
            "artifact_id": "candidate-run-unit",
            "trial_count": 2,
            "prediction_row_count": 1040,
            "trial_summaries": [
                _summary("spec:lower-return-stable", 0.03),
                _summary("spec:higher-return-less-stable", 0.04),
            ],
            "trial_diagnostics": [
                {
                    "trial_id": "spec:lower-return-stable",
                    "target_horizon_days": 20,
                    "selected_top_k_returns_by_date": _returns(total_return=0.01, negative_first_month=False),
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2024-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
                {
                    "trial_id": "spec:higher-return-less-stable",
                    "target_horizon_days": 20,
                    "selected_top_k_returns_by_date": _returns(total_return=0.035, negative_first_month=True),
                    "selected_top_k_picks_by_date": [],
                    "date_rank_ics": [{"as_of_date": "2024-01-01", "rank_ic": 0.1, "row_count": 2}],
                },
            ],
        }
        registry = {"artifact_id": "registry-unit", "model_specs": [{"model_spec_id": "spec"}]}

        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        self.assertEqual(report["candidate_leaderboard"][0]["trial_id"], "spec:higher-return-less-stable")
        self.assertLess(report["candidate_leaderboard"][0]["trial_stability"]["portfolio_total_return"], 2.0)

    def test_candidate_run_and_report_write_to_research_validation_namespace(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )
        root = Path(self.temp_dir.name) / "artifacts"

        run_path = write_walk_forward_model_candidate_run_artifact(run, artifact_root=root)
        report_path = write_model_comparison_report_artifact(report, artifact_root=root)

        self.assertEqual(
            run_path.parent,
            root / "research_validation" / "walk_forward_model_candidate_runs",
        )
        self.assertEqual(report_path.parent, root / "research_validation" / "model_comparison_reports")

    def test_governance_and_dashboard_projection_gate_model_report(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )

        self.assertEqual(
            report["execution_label_contract"]["label_version"],
            "shortpick_model_executable_label_matrix:v3",
        )
        self.assertIn(
            "t_plus_1_execution_model",
            report["execution_label_contract"]["covered_execution_gate_ids"],
        )
        self.assertIn(
            "suspension_limit_buy_sellability",
            report["execution_label_contract"]["covered_execution_gate_ids"],
        )

        artifacts = build_model_governance_and_projection_artifacts(
            validation_run_id="unit-run",
            candidate_run=run,
            comparison_report=report,
        )
        governance = artifacts["governance_promotion_decision"]
        projection = artifacts["dashboard_approved_projection_registry"]

        self.assertEqual(governance["artifact_type"], "governance_promotion_decision")
        self.assertEqual(governance["current_state"], "diagnostic_only")
        self.assertIn("multiple_testing_not_ready", governance["gate_readout"]["blocking_gate_ids"])
        self.assertNotIn("execution:t_plus_1_execution_model", governance["gate_readout"]["blocking_gate_ids"])
        self.assertNotIn(
            "execution:suspension_limit_buy_sellability",
            governance["gate_readout"]["blocking_gate_ids"],
        )
        self.assertIn("execution:fees_slippage_stamp_tax", governance["gate_readout"]["blocking_gate_ids"])
        self.assertIn("execution:adv_capacity_fill_rate", governance["gate_readout"]["blocking_gate_ids"])
        adv_check = next(
            row
            for row in governance["gate_readout"]["execution_gate_readout"]["checks"]
            if row["gate_id"] == "adv_capacity_fill_rate"
        )
        self.assertIn("capacity_contract", adv_check)
        if adv_check["capacity_contract"]:
            self.assertIn("configured_governance_status", adv_check["capacity_contract"])
            self.assertIn("max_ready_research_portfolio_notional_cny", adv_check["capacity_contract"])
        self.assertEqual(projection["artifact_type"], "dashboard_approved_projection_registry")
        self.assertEqual(projection["approved_projection_count"], 0)
        self.assertEqual(
            governance["feature_version"],
            report["feature_version"],
        )
        self.assertEqual(
            projection["feature_version"],
            report["feature_version"],
        )
        self.assertNotIn(
            "governance_promotion_decision_missing_required_field_feature_version",
            projection["gate_readout"]["blocking_gate_ids"],
        )
        self.assertIn(
            "governance_not_approved_for_dashboard_projection",
            projection["gate_readout"]["blocking_gate_ids"],
        )

    def test_research_model_governance_refresh_rebuilds_artifacts_from_existing_candidate_run(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        candidate_run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        root = Path(self.temp_dir.name) / "refresh-root"
        candidate_run_path = write_walk_forward_model_candidate_run_artifact(candidate_run, artifact_root=root)
        registry_path = Path(self.temp_dir.name) / "registry.json"
        registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

        exit_code = cli_main(
            [
                "research-model-governance-refresh",
                "--validation-run-id",
                "unit-refresh",
                "--candidate-run-artifact",
                str(candidate_run_path),
                "--model-spec-registry-artifact",
                str(registry_path),
                "--artifact-root",
                str(root),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue((root / "research_validation" / "model_comparison_reports").exists())
        self.assertTrue((root / "research_validation" / "governance_promotion_decisions").exists())
        self.assertTrue((root / "research_validation" / "dashboard_approved_projection_registries").exists())

    def test_governance_and_projection_artifacts_write_to_research_validation_namespace(self) -> None:
        feature_matrix, label_matrix, registry = self._build_inputs()
        run = build_walk_forward_model_candidate_run_artifact(
            validation_run_id="unit-run",
            feature_matrix=feature_matrix,
            label_matrix=label_matrix,
            model_spec_registry=registry,
            min_train_dates=1,
            test_window_dates=2,
            selected_model_spec_ids=["baseline_momentum_10d_turnover_cooldown_v1"],
        )
        report = build_model_comparison_report_artifact(
            validation_run_id="unit-run",
            candidate_run=run,
            model_spec_registry=registry,
        )
        artifacts = build_model_governance_and_projection_artifacts(
            validation_run_id="unit-run",
            candidate_run=run,
            comparison_report=report,
        )
        root = Path(self.temp_dir.name) / "artifacts"

        written = write_model_governance_and_projection_artifacts(artifacts, artifact_root=root)

        self.assertEqual(
            written["governance_promotion_decision"].parent,
            root / "research_validation" / "governance_promotion_decisions",
        )
        self.assertEqual(
            written["dashboard_approved_projection_registry"].parent,
            root / "research_validation" / "dashboard_approved_projection_registries",
        )


if __name__ == "__main__":
    unittest.main()
