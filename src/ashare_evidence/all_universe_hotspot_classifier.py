from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ashare_evidence.all_universe_opportunity_data import load_gzip_dataset
from ashare_evidence.all_universe_opportunity_head import FEATURE_NAMES, _metrics, _percentile
from ashare_evidence.global_sector_state_account_ablation import _sigmoid, fit_l2_logistic
from ashare_evidence.rolling_account_execution_snapshot import stable_digest

SCHEMA_VERSION = "all_universe_hotspot_classifier_result.v1"


@dataclass(frozen=True)
class HotspotClassifier:
    centers: np.ndarray
    scales: np.ndarray
    hotspot_beta: np.ndarray
    risk_beta: np.ndarray
    training_row_count: int
    maximum_label_available_day: str
    hotspot_positive_rate: float

    def predict(self, row: dict[str, Any]) -> tuple[float, float]:
        values = np.asarray([float(row[name]) for name in FEATURE_NAMES], dtype=float)
        standardized = (values - self.centers) / self.scales
        design = np.asarray([1.0, *standardized], dtype=float)
        return (
            float(_sigmoid(np.asarray([design @ self.hotspot_beta]))[0]),
            float(_sigmoid(np.asarray([design @ self.risk_beta]))[0]),
        )


def fit_hotspot_classifier(rows: list[dict[str, Any]], *, fit_day: str, design: dict[str, Any]) -> HotspotClassifier:
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
        raise ValueError("insufficient causal hotspot classifier training rows")
    matrix = np.asarray([[float(row[name]) for name in FEATURE_NAMES] for row in eligible], dtype=float)
    centers = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales = np.where(scales <= 1e-12, 1.0, scales)
    standardized = (matrix - centers) / scales
    hotspot_labels = np.asarray([float(row["net_return_5d"]) >= 0.03 for row in eligible], dtype=float)
    risk_labels = np.asarray([int(row["downside_label"]) for row in eligible], dtype=float)
    if len(set(hotspot_labels.tolist())) < 2 or len(set(risk_labels.tolist())) < 2:
        raise ValueError("hotspot classifier requires both classes in both heads")
    return HotspotClassifier(
        centers=centers,
        scales=scales,
        hotspot_beta=fit_l2_logistic(
            standardized,
            hotspot_labels,
            l2_penalty=float(model_design["hotspot_head"]["l2_penalty"]),
        ),
        risk_beta=fit_l2_logistic(
            standardized,
            risk_labels,
            l2_penalty=float(model_design["risk_head"]["l2_penalty"]),
        ),
        training_row_count=len(eligible),
        maximum_label_available_day=max(str(row["label_available_day"]) for row in eligible),
        hotspot_positive_rate=float(hotspot_labels.mean()),
    )


def _segment(day: str, design: dict[str, Any]) -> str:
    segments = design["evaluation"]["segments"]
    if day <= str(segments["tuning_end"]):
        return "tuning"
    if day <= str(segments["validation_end"]):
        return "validation"
    if day <= str(segments["final_end"]):
        return "final"
    return "recent_diagnostic"


def _segment_gate(metrics: dict[str, Any], control: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    evaluation = design["evaluation"]
    checks = {
        "minimum_completed_signals": metrics["completed_signal_count"]
        >= int(evaluation["minimum_completed_signals"]),
        "minimum_mean_return": metrics["mean_net_return_5d"] is not None
        and float(metrics["mean_net_return_5d"]) >= float(evaluation["minimum_mean_net_5d_return"]),
        "minimum_median_return": metrics["median_net_return_5d"] is not None
        and float(metrics["median_net_return_5d"]) >= float(evaluation["minimum_median_net_5d_return"]),
        "minimum_win_rate": metrics["win_rate"] is not None
        and float(metrics["win_rate"]) >= float(evaluation["minimum_win_rate"]),
        "not_below_prefilter_control_mean": metrics["mean_net_return_5d"] is not None
        and control["mean_net_return_5d"] is not None
        and float(metrics["mean_net_return_5d"]) >= float(control["mean_net_return_5d"]),
    }
    return {"passed": all(checks.values()), "checks": checks}


def run_hotspot_classifier(
    *, dataset_path: Path, design_path: Path, regression_result_path: Path
) -> dict[str, Any]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    expected = "frozen_after_mean_return_regression_failure_before_classifier_outcome_evaluation"
    if design.get("status") != expected:
        raise ValueError("hotspot classifier design is not frozen")
    dataset = load_gzip_dataset(dataset_path)
    regression = json.loads(regression_result_path.read_text(encoding="utf-8"))
    if dataset["artifact_id"] != design["source_dataset_id"]:
        raise ValueError("hotspot classifier design and dataset differ")
    if regression["artifact_id"] != design["source_regression_result_id"]:
        raise ValueError("hotspot classifier design and regression result differ")
    rows_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dataset["rows"]:
        if str(row["signal_day"]) >= "2023-09-07":
            rows_by_day[str(row["signal_day"])].append(row)
    model: HotspotClassifier | None = None
    last_fit_index = -10_000
    last_selection: dict[str, int] = {}
    selections: list[dict[str, Any]] = []
    daily_readout: list[dict[str, Any]] = []
    fit_audits: list[dict[str, Any]] = []
    selection_design = design["model"]["selection"]
    named_symbols = set(design["evaluation"]["named_cases"])
    for signal_index, day in enumerate(sorted(rows_by_day)):
        if model is None or signal_index - last_fit_index >= int(design["model"]["refit_signal_days"]):
            try:
                model = fit_hotspot_classifier(dataset["rows"], fit_day=day, design=design)
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
                        "hotspot_positive_rate": model.hotspot_positive_rate,
                        "model_digest": stable_digest(
                            {
                                "centers": model.centers.tolist(),
                                "scales": model.scales.tolist(),
                                "hotspot_beta": model.hotspot_beta.tolist(),
                                "risk_beta": model.risk_beta.tolist(),
                            }
                        ),
                    }
                )
        if model is None:
            continue
        scored: list[dict[str, Any]] = []
        for row in rows_by_day[day]:
            hotspot, risk = model.predict(row)
            scored.append({"row": row, "hotspot_probability": hotspot, "downside_probability": risk})
        hotspot_percentiles = _percentile(
            [(str(item["row"]["symbol"]), float(item["hotspot_probability"])) for item in scored]
        )
        risk_percentiles = _percentile(
            [(str(item["row"]["symbol"]), float(item["downside_probability"])) for item in scored]
        )
        for item in scored:
            symbol = str(item["row"]["symbol"])
            item["hotspot_probability_percentile"] = hotspot_percentiles[symbol]
            item["downside_probability_percentile"] = risk_percentiles[symbol]
            item["transition_score"] = (
                0.65 * hotspot_percentiles[symbol]
                + 0.25 * (1.0 - risk_percentiles[symbol])
                + 0.10 * float(item["row"]["v3_soft_quality"])
            )
        scored.sort(key=lambda item: (-float(item["transition_score"]), str(item["row"]["symbol"])))
        top = scored[0]
        top_symbol = str(top["row"]["symbol"])
        passes = bool(
            top["hotspot_probability_percentile"]
            >= float(selection_design["minimum_hotspot_probability_percentile"])
            and top["downside_probability_percentile"]
            <= float(selection_design["maximum_downside_probability_percentile"])
            and signal_index - last_selection.get(top_symbol, -10_000)
            > int(selection_design["same_symbol_cooldown_signal_days"])
        )
        compact: list[dict[str, Any]] = []
        for rank, item in enumerate(scored, start=1):
            if rank <= 10 or item["row"]["symbol"] in named_symbols:
                compact.append(
                    {
                        "rank": rank,
                        "symbol": item["row"]["symbol"],
                        "stock_name": item["row"]["stock_name"],
                        "hotspot_probability": item["hotspot_probability"],
                        "downside_probability": item["downside_probability"],
                        "transition_score": item["transition_score"],
                        "v3_soft_quality": item["row"]["v3_soft_quality"],
                    }
                )
        daily_readout.append(
            {
                "signal_day": day,
                "candidate_count": len(scored),
                "selected": passes,
                "top_symbol": top_symbol,
                "ranked_candidates": compact,
            }
        )
        if passes:
            selections.append({**top["row"], "segment": _segment(day, design), "transition_score": top["transition_score"]})
            last_selection[top_symbol] = signal_index
    segment_names = ("tuning", "validation", "final", "recent_diagnostic")
    metrics = {segment: _metrics([row for row in selections if row["segment"] == segment]) for segment in segment_names}
    segment_gates = {
        segment: _segment_gate(metrics[segment], regression["prefilter_control_metrics"][segment], design)
        for segment in design["evaluation"]["required_segments"]
    }
    case_from = str(design["evaluation"]["named_case_rank_window_from"])
    case_deadline = str(design["evaluation"]["named_case_rank_deadline"])
    case_rows = [
        {"signal_day": row["signal_day"], **candidate}
        for row in daily_readout
        if case_from <= str(row["signal_day"]) <= case_deadline
        for candidate in row["ranked_candidates"]
        if candidate["symbol"] in named_symbols
    ]
    best_case_ranks = {
        symbol: min((int(row["rank"]) for row in case_rows if row["symbol"] == symbol), default=None)
        for symbol in sorted(named_symbols)
    }
    maximum_rank = int(design["evaluation"]["maximum_named_case_rank"])
    case_rank_passed = all(rank is not None and rank <= maximum_rank for rank in best_case_ranks.values())
    performance_passed = all(row["passed"] for row in segment_gates.values())
    status = (
        "diagnostic_pass_but_forward_forbidden_reused_history"
        if performance_passed and case_rank_passed
        else "rejected_hotspot_classifier_gates_failed"
    )
    material = {
        "artifact_type": "all_universe_hotspot_classifier_result",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "claim_ceiling": "reused_history_target_family_diagnostic_not_forward_evidence",
        "source_design_digest": stable_digest(design),
        "source_dataset_id": dataset["artifact_id"],
        "source_regression_result_id": regression["artifact_id"],
        "training_audit": {
            "fit_count": len(fit_audits),
            "future_label_violation_count": sum(row["future_label_violation"] for row in fit_audits),
            "fits": fit_audits,
        },
        "model_metrics": metrics,
        "prefilter_control_metrics": regression["prefilter_control_metrics"],
        "segment_gates": segment_gates,
        "performance_gate_passed": performance_passed,
        "named_case_rank_gate": {
            "window_from": case_from,
            "deadline": case_deadline,
            "maximum_rank": maximum_rank,
            "best_ranks": best_case_ranks,
            "passed": case_rank_passed,
            "rows": case_rows,
        },
        "daily_readout": daily_readout,
        "selections": selections,
        "forward_shadow": {
            "activation_allowed": False,
            "activation_date": None,
            "status": "forbidden_reused_history_and_missing_historical_st_pit",
        },
        "promotion_allowed": False,
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
        "runtime_publish_required": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"all-universe-hotspot-classifier-{digest[:16]}", **material, "content_digest": digest}


def write_classifier_result(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("all-universe hotspot classifier result digest mismatch")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable classifier result already exists: {path}")
    path.write_text(rendered, encoding="utf-8")
