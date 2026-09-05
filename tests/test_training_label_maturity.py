from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashare_evidence.model_candidate_runner import (
    build_streamed_walk_forward_model_candidate_run_artifact,
    build_walk_forward_model_candidate_run_artifact,
)


def inputs(
    *,
    immature_target: float = 1.0,
    omit_maturity: bool = False,
    model_type: str = "regularized_rank_linear",
    horizon: int = 20,
):
    features, labels = [], []
    for day, maturity in [("2026-01-01", "2026-01-30"), ("2026-02-02", "2026-03-03"), ("2026-02-03", "2026-03-04")]:
        for i, symbol in enumerate(["A", "B"]):
            uid = f"{day}:{symbol}"
            features.append(
                {
                    "universe_row_id": uid,
                    "symbol": symbol,
                    "as_of_date": day,
                    "feature_values": {
                        "price_momentum": {"return_20d": float(i)},
                        "liquidity": {"avg_amount_20d": 30_000_000.0},
                    },
                }
            )
            target = float(i) if day == "2026-01-01" else immature_target * (1 - i)
            row = {
                "universe_row_id": uid,
                "symbol": symbol,
                "as_of_date": day,
                "label_status": "ready",
                "labels": {"excess_return_20d": target, "net_excess_return_10d_after_costs": target},
            }
            if not omit_maturity:
                row["exit_dates_by_horizon"] = {"20": maturity}
            labels.append(row)
    registry = {
        "artifact_id": "maturity-registry",
        "model_specs": [
            {
                "model_spec_id": "maturity-linear",
                "model_type": model_type,
                "prediction_horizon_days": horizon,
                "selection_policy": {"top_k": 1},
                "hyperparameter_grid": {"regularization_alpha": [0.5], "tail_positive_top_k": [1]},
            }
        ],
    }
    return (
        {"artifact_id": "maturity-features", "rows": features},
        {"artifact_id": "maturity-labels", "rows": labels},
        registry,
    )


def run_case(tmp_path: Path, *, streamed: bool, min_train_dates: int = 1, **kwargs):
    features, labels, registry = inputs(**kwargs)
    shared = dict(
        validation_run_id="maturity-check",
        model_spec_registry=registry,
        min_train_dates=min_train_dates,
        test_window_dates=1,
    )
    if streamed:
        fp, lp = tmp_path / "features.json", tmp_path / "labels.json"
        fp.write_text(json.dumps(features))
        lp.write_text(json.dumps(labels))
        return build_streamed_walk_forward_model_candidate_run_artifact(
            feature_matrix_artifact=fp, label_matrix_artifact=lp, **shared
        )
    return build_walk_forward_model_candidate_run_artifact(feature_matrix=features, label_matrix=labels, **shared)


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("model_type", ["regularized_rank_linear", "tail_capture_linear_ranker"])
def test_unobserved_future_returns_cannot_change_fitted_model(tmp_path, streamed, model_type):
    normal = run_case(tmp_path, streamed=streamed, immature_target=1.0, model_type=model_type)
    changed_future = run_case(tmp_path, streamed=streamed, immature_target=-100.0, model_type=model_type)
    normal_fits = normal["trial_summaries"][0]["fit_summaries"]
    changed_fits = changed_future["trial_summaries"][0]["fit_summaries"]
    assert [r["fitted_model_digest"] for r in normal_fits] == [r["fitted_model_digest"] for r in changed_fits]
    assert [r["train_row_count"] for r in normal_fits] == [2, 2]


@pytest.mark.parametrize("streamed", [False, True])
def test_missing_label_maturity_cannot_generate_learned_predictions(tmp_path, streamed):
    result = run_case(tmp_path, streamed=streamed, omit_maturity=True)
    assert result["prediction_row_count"] == 0
    assert all(
        row["fit_status"] == "blocked_no_mature_training_labels"
        for row in result["trial_summaries"][0]["fit_summaries"]
    )


def test_same_day_and_unknown_cohort_maturities_are_not_available():
    from ashare_evidence.training_label_maturity import cohort_available_day, mature_training_dates

    rows = [{"as_of_date": "2026-01-01", "exit_dates_by_horizon": {"20": end}} for end in ["2026-01-30", "2026-02-03"]]
    assert cohort_available_day(rows, horizon_days=20) == "2026-02-03"
    assert (
        mature_training_dates(["2026-01-01"], available_by_date={"2026-01-01": "2026-02-03"}, test_start="2026-02-03")
        == []
    )
    rows.append({"as_of_date": "2026-01-01"})
    assert cohort_available_day(rows, horizon_days=20) is None


@pytest.mark.parametrize("value", ["2026-02-30", "2025-12-31", "2026-01-01", None])
def test_invalid_or_nonfuture_outcome_dates_fail_closed(value):
    from ashare_evidence.training_label_maturity import label_available_day

    assert (
        label_available_day({"as_of_date": "2026-01-01", "exit_dates_by_horizon": {"20": value}}, horizon_days=20)
        is None
    )


@pytest.mark.parametrize("streamed", [False, True])
def test_minimum_training_dates_is_enforced_after_maturity_filter(tmp_path, streamed):
    result = run_case(tmp_path, streamed=streamed, min_train_dates=2)
    assert result["prediction_row_count"] == 0
    fits = result["trial_summaries"][0]["fit_summaries"]
    assert fits[0]["fit_status"] == "blocked_insufficient_mature_training_dates"
    assert fits[0]["train_date_count"] == 1


@pytest.mark.parametrize("streamed", [False, True])
def test_missing_requested_horizon_cannot_silently_train_on_ten_day_target(tmp_path, streamed):
    result = run_case(tmp_path, streamed=streamed, horizon=5)
    assert result["prediction_row_count"] == 0


def test_short_horizon_waits_for_shared_long_horizon_readiness_gate():
    from ashare_evidence.training_label_maturity import label_available_day

    row = {"as_of_date": "2026-01-01", "exit_dates_by_horizon": {"5": "2026-01-09", "20": "2026-01-30"}}
    assert label_available_day(row, horizon_days=5) == "2026-01-30"
    row["label_available_dates_by_horizon"] = {"5": "2026-02-02"}
    assert label_available_day(row, horizon_days=5) == "2026-02-02"


def test_label_generator_waits_for_benchmark_outcome_and_shared_horizons():
    from datetime import date, timedelta

    from ashare_evidence.model_exploration_snapshot import _label_for_row

    def bar(day, price):
        return {
            "observed_date": day,
            "open_price": price,
            "close_price": price,
            "high_price": price + 1,
            "low_price": price - 1,
            "volume": 1000,
        }

    start = date(2026, 1, 1)
    stock = [bar(start + timedelta(days=i), 100 + i) for i in range(11)]
    benchmark = [bar(start + timedelta(days=2 * i), 100 + i) for i in range(11)]
    row = _label_for_row(
        symbol="600001.SH",
        as_of_day=start,
        stock_bars=stock,
        stock_index=0,
        benchmark_bars=benchmark,
        benchmark_by_day={b["observed_date"]: i for i, b in enumerate(benchmark)},
        horizons=(5, 10),
        universe_row_id="test",
        source_snapshot_id="fixture",
        entry_price_source="same_day_close_research_proxy",
    )
    assert row["exit_dates_by_horizon"]["10"] == "2026-01-11"
    assert row["benchmark_exit_dates_by_horizon"]["10"] == "2026-01-21"
    assert row["label_available_dates_by_horizon"] == {"5": "2026-01-21", "10": "2026-01-21"}
