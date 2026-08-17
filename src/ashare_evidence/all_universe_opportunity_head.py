from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

import numpy as np

from ashare_evidence.all_universe_opportunity_data import load_gzip_dataset
from ashare_evidence.global_sector_state_account_ablation import _sigmoid, fit_l2_logistic
from ashare_evidence.rolling_account_execution_snapshot import stable_digest

SCHEMA_VERSION = "all_universe_opportunity_head_result.v1"
FEATURE_NAMES = (
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_3d_minus_return_5d",
    "distance_from_20d_high",
    "maximum_drawdown_20d",
    "volatility_20d",
    "close_vs_sma5",
    "close_vs_sma10",
    "amount_1d_vs_20d",
    "amount_5d_vs_20d",
    "turnover_1d_vs_20d",
    "turnover_5d_vs_20d",
    "return_20d_percentile",
    "amount_1d_vs_20d_percentile",
    "turnover_rate_percentile",
    "volatility_20d_percentile",
    "v3_soft_quality",
)


@dataclass(frozen=True)
class OpportunityModel:
    centers: np.ndarray
    scales: np.ndarray
    recovery_beta: np.ndarray
    risk_beta: np.ndarray
    training_row_count: int
    maximum_label_available_day: str

    def predict(self, row: dict[str, Any]) -> tuple[float, float]:
        values = np.asarray([float(row[name]) for name in FEATURE_NAMES], dtype=float)
        standardized = (values - self.centers) / self.scales
        design = np.asarray([1.0, *standardized], dtype=float)
        return (
            float(design @ self.recovery_beta),
            float(_sigmoid(np.asarray([design @ self.risk_beta]))[0]),
        )


def fit_opportunity_model(rows: list[dict[str, Any]], *, fit_day: str, design: dict[str, Any]) -> OpportunityModel:
    model_design = design["model"]
    eligible = [
        row
        for row in rows
        if row.get("entry_status") == "tradable_research_proxy"
        and row.get("net_return_5d") is not None
        and row.get("downside_label") is not None
        and row.get("label_available_day") is not None
        and str(row["label_available_day"]) <= fit_day
        and str(row["signal_day"]) < fit_day
    ][-int(model_design["maximum_training_rows"]) :]
    if len(eligible) < int(model_design["minimum_training_rows"]):
        raise ValueError("insufficient causal all-universe opportunity training rows")
    matrix = np.asarray([[float(row[name]) for name in FEATURE_NAMES] for row in eligible], dtype=float)
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales <= 1e-12, 1.0, scales)
    standardized = (matrix - centers) / scales
    design_matrix = np.column_stack([np.ones(len(standardized)), standardized])
    clip = 0.30
    targets = np.asarray([min(clip, max(-clip, float(row["net_return_5d"]))) for row in eligible])
    recovery_l2 = float(model_design["recovery_head"]["l2_penalty"])
    penalty = np.eye(design_matrix.shape[1]) * recovery_l2
    penalty[0, 0] = 0.0
    recovery_beta = np.linalg.solve(
        design_matrix.T @ design_matrix + penalty,
        design_matrix.T @ targets,
    )
    risk_labels = np.asarray([int(row["downside_label"]) for row in eligible], dtype=float)
    if len(set(risk_labels.tolist())) < 2:
        raise ValueError("all-universe risk head requires both classes")
    risk_beta = fit_l2_logistic(
        standardized,
        risk_labels,
        l2_penalty=float(model_design["risk_head"]["l2_penalty"]),
    )
    return OpportunityModel(
        centers=centers,
        scales=scales,
        recovery_beta=recovery_beta,
        risk_beta=risk_beta,
        training_row_count=len(eligible),
        maximum_label_available_day=max(str(row["label_available_day"]) for row in eligible),
    )


def _percentile(values: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    denominator = max(1, len(ordered) - 1)
    return {symbol: index / denominator for index, (symbol, _value) in enumerate(ordered)}


def _segment(day: str, design: dict[str, Any]) -> str:
    data = design["data_contract"]
    if day <= str(data["tuning_end"]):
        return "tuning"
    if day <= str(data["validation_end"]):
        return "validation"
    if day <= str(data["historical_end"]):
        return "final"
    return "recent_diagnostic"


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        row
        for row in rows
        if row.get("entry_status") == "tradable_research_proxy" and row.get("net_return_5d") is not None
    ]
    returns = [float(row["net_return_5d"]) for row in completed]
    return {
        "signal_count": len(rows),
        "completed_signal_count": len(completed),
        "mean_net_return_5d": mean(returns) if returns else None,
        "median_net_return_5d": median(returns) if returns else None,
        "win_rate": sum(value > 0.0 for value in returns) / len(returns) if returns else None,
        "distinct_symbol_count": len({str(row["symbol"]) for row in completed}),
        "v3_top20_presence_count": sum(float(row.get("v3_soft_quality") or 0.0) > 0.0 for row in completed),
    }


def _gate_segment(model: dict[str, Any], control: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    evaluation = design["evaluation"]
    checks = {
        "minimum_completed_signals": model["completed_signal_count"]
        >= int(evaluation["minimum_completed_signals_per_validation_segment"]),
        "minimum_win_rate": model["win_rate"] is not None
        and float(model["win_rate"]) >= float(evaluation["minimum_net_5d_win_rate"]),
        "minimum_mean_return": model["mean_net_return_5d"] is not None
        and float(model["mean_net_return_5d"]) >= float(evaluation["minimum_mean_net_5d_return"]),
        "minimum_median_return": model["median_net_return_5d"] is not None
        and float(model["median_net_return_5d"]) >= float(evaluation["minimum_median_net_5d_return"]),
        "model_not_below_prefilter_control": model["mean_net_return_5d"] is not None
        and control["mean_net_return_5d"] is not None
        and float(model["mean_net_return_5d"]) >= float(control["mean_net_return_5d"]),
    }
    return {"passed": all(checks.values()), "checks": checks}


def run_all_universe_opportunity_head(*, dataset_path: Path, design_path: Path) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    expected = "frozen_after_named_case_schema_preflight_before_broad_model_evaluation"
    if design.get("status") != expected:
        raise ValueError("all-universe opportunity design is not frozen")
    dataset = load_gzip_dataset(dataset_path)
    if dataset["source_recent_snapshot_id"] != design["data_contract"]["recent_snapshot_id"]:
        raise ValueError("all-universe design and dataset recent source differ")
    rows_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dataset["rows"]:
        rows_by_day[str(row["signal_day"])].append(row)
    training_pool = dataset["rows"]
    selection = design["model"]["selection"]
    evaluation_start = str(design["data_contract"]["historical_evaluation_from"])
    model_selected: list[dict[str, Any]] = []
    control_selected: list[dict[str, Any]] = []
    daily_readout: list[dict[str, Any]] = []
    last_model_selection: dict[str, int] = {}
    last_control_selection: dict[str, int] = {}
    model: OpportunityModel | None = None
    last_fit_index = -10_000
    fit_audits: list[dict[str, Any]] = []
    evaluation_days = [day for day in sorted(rows_by_day) if day >= evaluation_start]
    for signal_index, day in enumerate(evaluation_days):
        if model is None or signal_index - last_fit_index >= int(design["model"]["refit_signal_days"]):
            try:
                model = fit_opportunity_model(training_pool, fit_day=day, design=design)
            except ValueError:
                model = None
            if model is not None:
                last_fit_index = signal_index
                fit_audits.append(
                    {
                        "fit_day": day,
                        "training_row_count": model.training_row_count,
                        "maximum_label_available_day": model.maximum_label_available_day,
                        "future_label_violation": model.maximum_label_available_day > day,
                        "model_digest": stable_digest(
                            {
                                "centers": model.centers.tolist(),
                                "scales": model.scales.tolist(),
                                "recovery_beta": model.recovery_beta.tolist(),
                                "risk_beta": model.risk_beta.tolist(),
                            }
                        ),
                    }
                )
        candidates = rows_by_day[day]
        if model is None or not candidates:
            daily_readout.append({"signal_day": day, "status": "model_unavailable", "candidate_count": len(candidates)})
            continue
        scored: list[dict[str, Any]] = []
        for row in candidates:
            recovery, risk = model.predict(row)
            scored.append({"row": row, "recovery_prediction": recovery, "downside_probability": risk})
        recovery_percentiles = _percentile(
            [(str(item["row"]["symbol"]), float(item["recovery_prediction"])) for item in scored]
        )
        risk_percentiles = _percentile(
            [(str(item["row"]["symbol"]), float(item["downside_probability"])) for item in scored]
        )
        for item in scored:
            symbol = str(item["row"]["symbol"])
            item["recovery_prediction_percentile"] = recovery_percentiles[symbol]
            item["downside_probability_percentile"] = risk_percentiles[symbol]
            item["transition_score"] = (
                0.65 * recovery_percentiles[symbol]
                + 0.25 * (1.0 - risk_percentiles[symbol])
                + 0.10 * float(item["row"]["v3_soft_quality"])
            )
        scored.sort(key=lambda item: (-float(item["transition_score"]), str(item["row"]["symbol"])))
        top = scored[0]
        symbol = str(top["row"]["symbol"])
        passes = bool(
            top["recovery_prediction_percentile"] >= float(selection["minimum_recovery_prediction_percentile"])
            and top["downside_probability_percentile"] <= float(selection["maximum_downside_probability_percentile"])
            and signal_index - last_model_selection.get(symbol, -10_000)
            > int(selection["same_symbol_cooldown_signal_days"])
        )
        compact_candidates = [
            {
                "rank": rank,
                "symbol": item["row"]["symbol"],
                "stock_name": item["row"]["stock_name"],
                "transition_score": item["transition_score"],
                "recovery_prediction": item["recovery_prediction"],
                "downside_probability": item["downside_probability"],
                "recovery_prediction_percentile": item["recovery_prediction_percentile"],
                "downside_probability_percentile": item["downside_probability_percentile"],
                "v3_soft_quality": item["row"]["v3_soft_quality"],
            }
            for rank, item in enumerate(scored[:10], start=1)
        ]
        case_symbols = set(design["evaluation"]["named_cases"])
        for rank, item in enumerate(scored, start=1):
            if item["row"]["symbol"] in case_symbols and rank > 10:
                compact_candidates.append(
                    {
                        "rank": rank,
                        "symbol": item["row"]["symbol"],
                        "stock_name": item["row"]["stock_name"],
                        "transition_score": item["transition_score"],
                        "recovery_prediction": item["recovery_prediction"],
                        "downside_probability": item["downside_probability"],
                        "recovery_prediction_percentile": item["recovery_prediction_percentile"],
                        "downside_probability_percentile": item["downside_probability_percentile"],
                        "v3_soft_quality": item["row"]["v3_soft_quality"],
                    }
                )
        daily_readout.append(
            {
                "signal_day": day,
                "status": "selected" if passes else "gated",
                "candidate_count": len(scored),
                "top_symbol": symbol,
                "ranked_candidates": compact_candidates,
            }
        )
        if passes:
            model_selected.append({**top["row"], "transition_score": top["transition_score"], "segment": _segment(day, design)})
            last_model_selection[symbol] = signal_index
        control = max(candidates, key=lambda row: (float(row["prefilter_score"]), str(row["symbol"])))
        control_symbol = str(control["symbol"])
        if signal_index - last_control_selection.get(control_symbol, -10_000) > int(
            selection["same_symbol_cooldown_signal_days"]
        ):
            control_selected.append({**control, "segment": _segment(day, design)})
            last_control_selection[control_symbol] = signal_index
    segments = ("tuning", "validation", "final", "recent_diagnostic")
    model_metrics = {segment: _metrics([row for row in model_selected if row["segment"] == segment]) for segment in segments}
    control_metrics = {
        segment: _metrics([row for row in control_selected if row["segment"] == segment]) for segment in segments
    }
    segment_gates = {
        segment: _gate_segment(model_metrics[segment], control_metrics[segment], design)
        for segment in design["evaluation"]["segments_required"]
    }
    case_symbols = set(design["evaluation"]["named_cases"])
    case_deadline = str(design["evaluation"]["named_case_latest_admission_day"])
    case_rows = [
        row
        for row in dataset["rows"]
        if row["symbol"] in case_symbols
        and str(row["signal_day"]) <= case_deadline
        and str(row["signal_day"]) >= str(design["data_contract"]["recent_diagnostic_from"])
    ]
    admitted_cases = sorted({str(row["symbol"]) for row in case_rows})
    missing_cases = sorted(case_symbols - set(admitted_cases))
    performance_passed = all(row["passed"] for row in segment_gates.values())
    mechanism_passed = not missing_cases
    if not mechanism_passed:
        status = "rejected_named_case_admission_failed"
    elif not performance_passed:
        status = "rejected_historical_performance_gate_failed"
    else:
        status = "historical_mechanism_pass_forward_blocked_missing_st_pit"
    material = {
        "artifact_type": "all_universe_opportunity_head_result",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "claim_ceiling": design["claim_boundary"]["maximum_claim"],
        "source_design_digest": stable_digest(design),
        "source_dataset_id": dataset["artifact_id"],
        "source_data_amendment_digest": dataset["source_data_amendment_digest"],
        "feature_names": list(FEATURE_NAMES),
        "training_audit": {
            "fit_count": len(fit_audits),
            "future_label_violation_count": sum(row["future_label_violation"] for row in fit_audits),
            "historical_st_status_point_in_time": dataset["historical_st_status_point_in_time"],
            "future_static_status_backfill_used": dataset["future_static_status_backfill_used"],
            "fits": fit_audits,
        },
        "named_case_admission": {
            "deadline": case_deadline,
            "required_symbols": sorted(case_symbols),
            "admitted_symbols": admitted_cases,
            "missing_symbols": missing_cases,
            "passed": mechanism_passed,
            "rows": case_rows,
        },
        "model_metrics": model_metrics,
        "prefilter_control_metrics": control_metrics,
        "segment_gates": segment_gates,
        "performance_gate_passed": performance_passed,
        "daily_readout": daily_readout,
        "model_selections": model_selected,
        "prefilter_control_selections": control_selected,
        "forward_shadow": {
            "activation_allowed": False,
            "activation_date": None,
            "status": "blocked_missing_historical_st_pit_lineage",
            "historical_backfill_counts_as_forward": False,
            "paper_tracking_or_frontend_module": False,
        },
        "promotion_allowed": False,
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
        "runtime_publish_required": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"all-universe-opportunity-head-{digest[:16]}", **material, "content_digest": digest}


def write_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("all-universe opportunity result digest mismatch")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
