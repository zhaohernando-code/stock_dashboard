from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.model_comparison_report import build_model_comparison_report_artifact
from ashare_evidence.model_governance_gate import build_model_governance_and_projection_artifacts
from ashare_evidence.order_level_capacity_proxy import _exposure_overlay_scale, _safe_float


EXPOSURE_FLOOR_OVERLAY_GOVERNANCE_VERSION = "exposure_floor_overlay_governance.v1"
STAGGERED_EXPOSURE_COMBO_GOVERNANCE_VERSION = "staggered_exposure_combo_governance.v1"


def build_exposure_floor_overlay_governance_summary(
    *,
    candidate_run: dict[str, Any],
    model_spec_registry: dict[str, Any],
    trial_id: str,
    overlay_mode: str,
    gross_exposure_floor: float,
    validation_run_id: str | None = None,
    source_exposure_proxy_artifact: str | None = None,
) -> dict[str, Any]:
    """Build compact comparison/governance evidence for a selected-return exposure overlay.

    This intentionally does not persist a transformed candidate-run artifact. It constructs the
    overlay trial in memory, runs the existing comparison/governance builders, and retains only a
    compact summary so research evidence does not grow into another candidate-run payload.
    """

    source_trial = _find_trial_summary(candidate_run, trial_id)
    source_diagnostic = _find_trial_diagnostic(candidate_run, trial_id)
    overlay_trial_id = f"{trial_id}:exposure_floor_{overlay_mode}_{gross_exposure_floor:.6f}"
    overlay_returns = _overlay_selected_returns(
        source_diagnostic.get("selected_top_k_returns_by_date") or [],
        overlay_mode=overlay_mode,
        gross_exposure_floor=gross_exposure_floor,
    )
    overlay_trial = copy.deepcopy(source_trial)
    overlay_trial["trial_id"] = overlay_trial_id
    overlay_trial["parent_trial_id"] = trial_id
    overlay_trial["claim_ceiling"] = "selected_return_overlay_governance_proxy_only"
    overlay_trial["selection_policy"] = _overlay_selection_policy(
        source_trial.get("selection_policy") or {},
        overlay_mode=overlay_mode,
        gross_exposure_floor=gross_exposure_floor,
        source_exposure_proxy_artifact=source_exposure_proxy_artifact,
    )
    overlay_trial["metrics"] = _overlay_metrics(source_trial.get("metrics") or {}, overlay_returns)

    overlay_diagnostic = copy.deepcopy(source_diagnostic)
    overlay_diagnostic["trial_id"] = overlay_trial_id
    overlay_diagnostic["parent_trial_id"] = trial_id
    overlay_diagnostic["claim_ceiling"] = "selected_return_overlay_governance_proxy_only"
    overlay_diagnostic["selected_top_k_returns_by_date"] = overlay_returns

    overlay_candidate_run = copy.deepcopy(candidate_run)
    overlay_candidate_run["artifact_id"] = _overlay_candidate_run_id(
        candidate_run.get("artifact_id"), overlay_trial_id
    )
    overlay_candidate_run["validation_run_id"] = validation_run_id or str(candidate_run.get("validation_run_id") or "")
    overlay_candidate_run["config_version"] = (
        f"{candidate_run.get('config_version')}:selected_return_exposure_floor_overlay_governance_proxy"
    )
    overlay_candidate_run["claim_ceiling"] = "selected_return_overlay_candidate_run_proxy_only"
    overlay_candidate_run["trial_summaries"] = [
        *(copy.deepcopy(candidate_run.get("trial_summaries") or [])),
        overlay_trial,
    ]
    overlay_candidate_run["trial_diagnostics"] = [
        *(copy.deepcopy(candidate_run.get("trial_diagnostics") or [])),
        overlay_diagnostic,
    ]
    overlay_candidate_run["trial_count"] = len(overlay_candidate_run["trial_summaries"])

    comparison_report = build_model_comparison_report_artifact(
        validation_run_id=overlay_candidate_run["validation_run_id"],
        candidate_run=overlay_candidate_run,
        model_spec_registry=model_spec_registry,
    )
    governance_artifacts = build_model_governance_and_projection_artifacts(
        validation_run_id=overlay_candidate_run["validation_run_id"],
        candidate_run=overlay_candidate_run,
        comparison_report=comparison_report,
    )
    overlay_row = _leaderboard_row(comparison_report, overlay_trial_id)
    source_row = _leaderboard_row(comparison_report, trial_id)
    if not overlay_row:
        raise ValueError(f"overlay trial missing from generated comparison report: {overlay_trial_id}")
    if not source_row:
        raise ValueError(f"source trial missing from generated comparison report: {trial_id}")

    return {
        "artifact_type": "exposure_floor_overlay_governance_summary",
        "schema_version": EXPOSURE_FLOOR_OVERLAY_GOVERNANCE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "claim_ceiling": "selected_return_overlay_governance_proxy_only_no_model_replay_no_promotion",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "source_trial_id": trial_id,
        "overlay_trial_id": overlay_trial_id,
        "overlay_leaderboard_rank": _leaderboard_rank(comparison_report, overlay_trial_id),
        "source_leaderboard_rank": _leaderboard_rank(comparison_report, trial_id),
        "source_exposure_proxy_artifact": source_exposure_proxy_artifact,
        "overlay": {
            "mode": overlay_mode,
            "gross_exposure_floor": gross_exposure_floor,
            "low_exposure_active_date_count": sum(1 for row in overlay_returns if row.get("exposure_overlay_applied")),
        },
        "comparison_report_id": comparison_report.get("artifact_id"),
        "governance_promotion_decision_id": governance_artifacts["governance_promotion_decision"].get("artifact_id"),
        "dashboard_approved_projection_registry_id": governance_artifacts[
            "dashboard_approved_projection_registry"
        ].get("artifact_id"),
        "source_trial": _compact_leaderboard_row(source_row),
        "overlay_trial": _compact_leaderboard_row(overlay_row),
        "metric_deltas": _metric_deltas(source_row, overlay_row),
        "metric_consistency_note": (
            "trial_summary selected_top_k rates can differ from diagnostic stability rates in source artifacts; "
            "promotion-style return, drawdown, DSR and PBO checks use the generated comparison/governance artifacts."
        ),
        "overfit_diagnostics": _compact_overfit(comparison_report.get("overfit_diagnostics") or {}),
        "governance_gate_readout": governance_artifacts["governance_promotion_decision"].get("gate_readout"),
        "comparison_gate_readout": comparison_report.get("gate_readout"),
        "interpretation": (
            "This summary proves the overlay can be evaluated by the existing comparison/governance stack without "
            "retaining another candidate-run payload. It is still a selected-return overlay proxy, not a full model "
            "replay or production/paper promotion."
        ),
    }


def write_exposure_floor_overlay_governance_summary(payload: dict[str, Any], output_json: str | Path) -> Path:
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def build_staggered_exposure_combo_governance_summary(
    *,
    candidate_run: dict[str, Any],
    model_spec_registry: dict[str, Any],
    combo_proxy: dict[str, Any],
    trial_id: str,
    entry_days: int,
    exit_policy: str,
    exposure_overlay_mode: str,
    gross_exposure_floor: float,
    validation_run_id: str | None = None,
    source_combo_proxy_artifact: str | None = None,
) -> dict[str, Any]:
    """Build compact governance evidence for the staggered-entry + exposure-floor combo proxy."""

    source_trial = _find_trial_summary(candidate_run, trial_id)
    source_diagnostic = _find_trial_diagnostic(candidate_run, trial_id)
    combo_scan = _find_combo_scan(
        combo_proxy,
        entry_days=entry_days,
        exit_policy=exit_policy,
        exposure_overlay_mode=exposure_overlay_mode,
        gross_exposure_floor=gross_exposure_floor,
    )
    combo_trial_id = (
        f"{trial_id}:staggered_{entry_days}_{exit_policy}:"
        f"exposure_{exposure_overlay_mode}_{gross_exposure_floor:.6f}"
    )
    combo_returns = _combo_selected_returns(
        source_diagnostic.get("selected_top_k_returns_by_date") or [],
        combo_scan=combo_scan,
        exposure_overlay_mode=exposure_overlay_mode,
        gross_exposure_floor=gross_exposure_floor,
    )
    combo_trial = copy.deepcopy(source_trial)
    combo_trial["trial_id"] = combo_trial_id
    combo_trial["parent_trial_id"] = trial_id
    combo_trial["claim_ceiling"] = "staggered_entry_exposure_combo_governance_proxy_only"
    combo_trial["selection_policy"] = _combo_selection_policy(
        source_trial.get("selection_policy") or {},
        combo_scan=combo_scan,
        source_combo_proxy_artifact=source_combo_proxy_artifact,
    )
    combo_trial["metrics"] = _overlay_metrics(source_trial.get("metrics") or {}, combo_returns)

    combo_diagnostic = copy.deepcopy(source_diagnostic)
    combo_diagnostic["trial_id"] = combo_trial_id
    combo_diagnostic["parent_trial_id"] = trial_id
    combo_diagnostic["claim_ceiling"] = "staggered_entry_exposure_combo_governance_proxy_only"
    combo_diagnostic["selected_top_k_returns_by_date"] = combo_returns

    combo_candidate_run = copy.deepcopy(candidate_run)
    combo_candidate_run["artifact_id"] = _overlay_candidate_run_id(candidate_run.get("artifact_id"), combo_trial_id)
    combo_candidate_run["validation_run_id"] = validation_run_id or str(candidate_run.get("validation_run_id") or "")
    combo_candidate_run["config_version"] = (
        f"{candidate_run.get('config_version')}:staggered_entry_exposure_combo_governance_proxy"
    )
    combo_candidate_run["claim_ceiling"] = "staggered_entry_exposure_combo_candidate_run_proxy_only"
    combo_candidate_run["trial_summaries"] = [*(copy.deepcopy(candidate_run.get("trial_summaries") or [])), combo_trial]
    combo_candidate_run["trial_diagnostics"] = [
        *(copy.deepcopy(candidate_run.get("trial_diagnostics") or [])),
        combo_diagnostic,
    ]
    combo_candidate_run["trial_count"] = len(combo_candidate_run["trial_summaries"])

    comparison_report = build_model_comparison_report_artifact(
        validation_run_id=combo_candidate_run["validation_run_id"],
        candidate_run=combo_candidate_run,
        model_spec_registry=model_spec_registry,
    )
    governance_artifacts = build_model_governance_and_projection_artifacts(
        validation_run_id=combo_candidate_run["validation_run_id"],
        candidate_run=combo_candidate_run,
        comparison_report=comparison_report,
    )
    combo_row = _leaderboard_row(comparison_report, combo_trial_id)
    source_row = _leaderboard_row(comparison_report, trial_id)
    if not combo_row:
        raise ValueError(f"combo trial missing from generated comparison report: {combo_trial_id}")
    if not source_row:
        raise ValueError(f"source trial missing from generated comparison report: {trial_id}")

    return {
        "artifact_type": "staggered_exposure_combo_governance_summary",
        "schema_version": STAGGERED_EXPOSURE_COMBO_GOVERNANCE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "claim_ceiling": "staggered_entry_exposure_combo_governance_proxy_only_no_model_replay_no_promotion",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "source_trial_id": trial_id,
        "combo_trial_id": combo_trial_id,
        "combo_leaderboard_rank": _leaderboard_rank(comparison_report, combo_trial_id),
        "source_leaderboard_rank": _leaderboard_rank(comparison_report, trial_id),
        "source_combo_proxy_artifact": source_combo_proxy_artifact,
        "combo": {
            "entry_days": entry_days,
            "exit_policy": exit_policy,
            "exposure_overlay_mode": exposure_overlay_mode,
            "gross_exposure_floor": gross_exposure_floor,
            "full_fill_repaired_pick_count": combo_scan.get("full_fill_repaired_pick_count"),
            "min_staggered_fill_rate": combo_scan.get("min_staggered_fill_rate"),
            "low_exposure_active_date_count": sum(1 for row in combo_returns if row.get("exposure_overlay_applied")),
        },
        "comparison_report_id": comparison_report.get("artifact_id"),
        "governance_promotion_decision_id": governance_artifacts["governance_promotion_decision"].get("artifact_id"),
        "dashboard_approved_projection_registry_id": governance_artifacts[
            "dashboard_approved_projection_registry"
        ].get("artifact_id"),
        "source_trial": _compact_leaderboard_row(source_row),
        "combo_trial": _compact_leaderboard_row(combo_row),
        "metric_deltas": _metric_deltas(source_row, combo_row),
        "metric_consistency_note": (
            "Staggered-entry total-return-after-cost is approximated by applying the net-excess delta to source "
            "total-return-after-cost, then applying the exposure overlay. This is a compact governance proxy, not "
            "a full order-level replay."
        ),
        "overfit_diagnostics": _compact_overfit(comparison_report.get("overfit_diagnostics") or {}),
        "governance_gate_readout": governance_artifacts["governance_promotion_decision"].get("gate_readout"),
        "comparison_gate_readout": comparison_report.get("gate_readout"),
        "interpretation": (
            "This summary evaluates the combined staggered-entry and exposure-floor transformation through the "
            "existing comparison/governance stack without retaining another candidate-run payload. It remains a "
            "proxy until formal replay or an order-level governance implementation exists."
        ),
    }


def write_staggered_exposure_combo_governance_summary(payload: dict[str, Any], output_json: str | Path) -> Path:
    return write_exposure_floor_overlay_governance_summary(payload, output_json)


def _find_trial_summary(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    trial = next((row for row in candidate_run.get("trial_summaries") or [] if row.get("trial_id") == trial_id), None)
    if not isinstance(trial, dict):
        raise ValueError(f"trial_id not found in trial_summaries: {trial_id}")
    return trial


def _find_trial_diagnostic(candidate_run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    diagnostic = next(
        (row for row in candidate_run.get("trial_diagnostics") or [] if row.get("trial_id") == trial_id),
        None,
    )
    if not isinstance(diagnostic, dict):
        raise ValueError(f"trial_id not found in trial_diagnostics: {trial_id}")
    return diagnostic


def _overlay_selected_returns(
    rows: list[dict[str, Any]],
    *,
    overlay_mode: str,
    gross_exposure_floor: float,
) -> list[dict[str, Any]]:
    overlay_rows: list[dict[str, Any]] = []
    for row in rows:
        gross_exposure = _safe_float(row.get("gross_exposure"))
        pick_count = int(_safe_float(row.get("pick_count")))
        is_low_exposure = pick_count > 0 and gross_exposure < gross_exposure_floor
        scale = (
            _exposure_overlay_scale(
                gross_exposure=gross_exposure,
                gross_exposure_floor=gross_exposure_floor,
                overlay_mode=overlay_mode,
            )
            if is_low_exposure
            else 1.0
        )
        overlay_row = dict(row)
        overlay_row["pre_overlay_mean_net_excess_return"] = _safe_float(row.get("mean_net_excess_return"))
        overlay_row["mean_net_excess_return"] = _safe_float(row.get("mean_net_excess_return")) * scale
        if "mean_total_return_after_cost" in row:
            overlay_row["pre_overlay_mean_total_return_after_cost"] = _safe_float(
                row.get("mean_total_return_after_cost")
            )
            overlay_row["mean_total_return_after_cost"] = (
                _safe_float(row.get("mean_total_return_after_cost")) * scale
            )
        overlay_row["exposure_overlay_mode"] = overlay_mode
        overlay_row["exposure_overlay_floor"] = gross_exposure_floor
        overlay_row["exposure_overlay_scale"] = scale
        overlay_row["exposure_overlay_applied"] = is_low_exposure
        overlay_rows.append(overlay_row)
    return overlay_rows


def _find_combo_scan(
    combo_proxy: dict[str, Any],
    *,
    entry_days: int,
    exit_policy: str,
    exposure_overlay_mode: str,
    gross_exposure_floor: float,
) -> dict[str, Any]:
    for scan in combo_proxy.get("scan_summaries") or []:
        if (
            int(_safe_float(scan.get("entry_days"))) == entry_days
            and str(scan.get("exit_policy") or "") == exit_policy
            and str(scan.get("exposure_overlay_mode") or "") == exposure_overlay_mode
            and abs(_safe_float(scan.get("gross_exposure_floor")) - gross_exposure_floor) < 1e-9
        ):
            return scan
    raise ValueError(
        "combo scan not found for "
        f"entry_days={entry_days}, exit_policy={exit_policy}, "
        f"exposure_overlay_mode={exposure_overlay_mode}, gross_exposure_floor={gross_exposure_floor}"
    )


def _combo_selected_returns(
    rows: list[dict[str, Any]],
    *,
    combo_scan: dict[str, Any],
    exposure_overlay_mode: str,
    gross_exposure_floor: float,
) -> list[dict[str, Any]]:
    replacements_by_date: dict[str, list[dict[str, Any]]] = {}
    for replacement in combo_scan.get("fill_details") or []:
        replacements_by_date.setdefault(str(replacement.get("as_of_date") or ""), []).append(replacement)

    combo_rows: list[dict[str, Any]] = []
    for row in rows:
        as_of_date = str(row.get("as_of_date") or "")
        base_net = _safe_float(row.get("mean_net_excess_return"))
        adjusted_net = base_net
        for replacement in replacements_by_date.get(as_of_date, []):
            adjusted_net += _safe_float(replacement.get("staggered_contribution")) - _safe_float(
                replacement.get("baseline_contribution")
            )
        adjusted_row = dict(row)
        adjusted_row["pre_staggered_mean_net_excess_return"] = base_net
        adjusted_row["mean_net_excess_return"] = adjusted_net
        if "mean_total_return_after_cost" in row:
            adjusted_row["pre_staggered_mean_total_return_after_cost"] = _safe_float(
                row.get("mean_total_return_after_cost")
            )
            adjusted_row["mean_total_return_after_cost"] = _safe_float(row.get("mean_total_return_after_cost")) + (
                adjusted_net - base_net
            )
        adjusted_row["staggered_entry_adjusted"] = as_of_date in replacements_by_date
        adjusted_row["staggered_entry_replacement_count"] = len(replacements_by_date.get(as_of_date, []))
        combo_rows.append(adjusted_row)
    return _overlay_selected_returns(combo_rows, overlay_mode=exposure_overlay_mode, gross_exposure_floor=gross_exposure_floor)


def _overlay_metrics(metrics: dict[str, Any], overlay_returns: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_safe_float(row.get("mean_net_excess_return")) for row in overlay_returns]
    adjusted = dict(metrics)
    adjusted["selected_top_k_net_excess_mean"] = sum(values) / len(values) if values else None
    adjusted["positive_selected_top_k_rate"] = sum(1 for value in values if value > 0) / len(values) if values else None
    adjusted["exposure_overlay_adjusted"] = True
    return adjusted


def _overlay_selection_policy(
    selection_policy: dict[str, Any],
    *,
    overlay_mode: str,
    gross_exposure_floor: float,
    source_exposure_proxy_artifact: str | None,
) -> dict[str, Any]:
    policy = copy.deepcopy(selection_policy)
    policy["date_exposure_scaling"] = {
        "enabled": True,
        "mode": overlay_mode,
        "gross_exposure_floor": gross_exposure_floor,
        "source_proxy_artifact": source_exposure_proxy_artifact,
        "claim_ceiling": "selected_return_overlay_governance_proxy_only",
    }
    return policy


def _combo_selection_policy(
    selection_policy: dict[str, Any],
    *,
    combo_scan: dict[str, Any],
    source_combo_proxy_artifact: str | None,
) -> dict[str, Any]:
    policy = copy.deepcopy(selection_policy)
    policy["staggered_entry_execution_overlay"] = {
        "enabled": True,
        "entry_days": combo_scan.get("entry_days"),
        "exit_policy": combo_scan.get("exit_policy"),
        "full_fill_repaired_pick_count": combo_scan.get("full_fill_repaired_pick_count"),
        "min_staggered_fill_rate": combo_scan.get("min_staggered_fill_rate"),
        "source_proxy_artifact": source_combo_proxy_artifact,
        "claim_ceiling": "staggered_entry_exposure_combo_governance_proxy_only",
    }
    policy["date_exposure_scaling"] = {
        "enabled": True,
        "mode": combo_scan.get("exposure_overlay_mode"),
        "gross_exposure_floor": combo_scan.get("gross_exposure_floor"),
        "low_exposure_active_date_count": combo_scan.get("low_exposure_active_date_count"),
        "source_proxy_artifact": source_combo_proxy_artifact,
        "claim_ceiling": "staggered_entry_exposure_combo_governance_proxy_only",
    }
    return policy


def _overlay_candidate_run_id(source_id: Any, overlay_trial_id: str) -> str:
    digest_source = f"{source_id}:{overlay_trial_id}".encode("utf-8")
    import hashlib

    return f"walk-forward-overlay-candidate-run-{hashlib.sha256(digest_source).hexdigest()[:16]}"


def _leaderboard_row(comparison_report: dict[str, Any], trial_id: str) -> dict[str, Any] | None:
    return next(
        (row for row in comparison_report.get("candidate_leaderboard") or [] if row.get("trial_id") == trial_id),
        None,
    )


def _leaderboard_rank(comparison_report: dict[str, Any], trial_id: str) -> int | None:
    for index, row in enumerate(comparison_report.get("candidate_leaderboard") or [], start=1):
        if row.get("trial_id") == trial_id:
            return index
    return None


def _compact_leaderboard_row(row: dict[str, Any]) -> dict[str, Any]:
    stability = row.get("trial_stability") if isinstance(row.get("trial_stability"), dict) else {}
    return {
        "trial_id": row.get("trial_id"),
        "model_spec_id": row.get("model_spec_id"),
        "rank_ic_mean": row.get("rank_ic_mean"),
        "positive_rank_ic_rate": row.get("positive_rank_ic_rate"),
        "selected_top_k_net_excess_mean": row.get("selected_top_k_net_excess_mean"),
        "positive_selected_top_k_rate": row.get("positive_selected_top_k_rate"),
        "trial_stability": {
            "period_count": stability.get("period_count"),
            "portfolio_total_return": stability.get("portfolio_total_return"),
            "portfolio_annualized_return": stability.get("portfolio_annualized_return"),
            "portfolio_max_drawdown": stability.get("portfolio_max_drawdown"),
            "portfolio_path_drawdown_sum": stability.get("portfolio_path_drawdown_sum"),
            "negative_month_count": stability.get("negative_month_count"),
            "min_monthly_mean_net_excess": stability.get("min_monthly_mean_net_excess"),
            "positive_date_rate": stability.get("positive_date_rate"),
        },
    }


def _metric_deltas(source_row: dict[str, Any], overlay_row: dict[str, Any]) -> dict[str, Any]:
    source = _compact_leaderboard_row(source_row)
    overlay = _compact_leaderboard_row(overlay_row)
    source_stability = source["trial_stability"]
    overlay_stability = overlay["trial_stability"]
    fields = {
        "selected_top_k_net_excess_mean": (source, overlay),
        "positive_selected_top_k_rate": (source, overlay),
        "portfolio_total_return": (source_stability, overlay_stability),
        "portfolio_annualized_return": (source_stability, overlay_stability),
        "portfolio_max_drawdown": (source_stability, overlay_stability),
        "portfolio_path_drawdown_sum": (source_stability, overlay_stability),
        "negative_month_count": (source_stability, overlay_stability),
        "min_monthly_mean_net_excess": (source_stability, overlay_stability),
        "positive_date_rate": (source_stability, overlay_stability),
    }
    return {
        field: _safe_float(after.get(field)) - _safe_float(before.get(field))
        for field, (before, after) in fields.items()
    }


def _compact_overfit(overfit: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": overfit.get("status"),
        "pbo_proxy": overfit.get("pbo_proxy"),
        "deflated_sharpe_confidence": overfit.get("deflated_sharpe_confidence"),
        "alpha_t_stat": overfit.get("alpha_t_stat"),
        "period_count": overfit.get("period_count"),
        "period_source": overfit.get("period_source"),
        "eligible_trial_count": overfit.get("eligible_trial_count"),
        "split_count": overfit.get("split_count"),
        "blocking_gate_ids": overfit.get("blocking_gate_ids"),
    }
