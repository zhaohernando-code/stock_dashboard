from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.research_artifact_store import write_research_validation_artifact

MULTIPLE_TESTING_DIAGNOSTICS_SCHEMA_VERSION = "pbo_dsr_multiple_comparison.v1"
MULTIPLE_TESTING_DIAGNOSTICS_VERSION = "pbo_dsr_multiple_comparison:v1"
MIN_TRIALS_FOR_PBO = 4
MIN_PERIODS_FOR_DSR = 20


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        rendered = float(value)
    except (TypeError, ValueError):
        return None
    return rendered if math.isfinite(rendered) else None


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _trial_rows(sweep_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in sweep_results:
        label = str(result.get("label") or "")
        for horizon_key, metrics in (result.get("horizon_metrics") or {}).items():
            ic_ir = _safe_float((metrics or {}).get("ic_ir"))
            sample_count = int((metrics or {}).get("sample_count") or 0)
            snapshot_count = int((metrics or {}).get("snapshot_count") or 0)
            spread = _safe_float((metrics or {}).get("mean_top_bottom_spread"))
            rows.append(
                {
                    "trial_id": f"{label}:{horizon_key}",
                    "label": label,
                    "horizon": horizon_key,
                    "ic_ir": ic_ir,
                    "sample_count": sample_count,
                    "snapshot_count": snapshot_count,
                    "mean_top_bottom_spread": spread,
                    "eligible_for_statistics": ic_ir is not None and snapshot_count >= MIN_PERIODS_FOR_DSR,
                }
            )
    return rows


def build_multiple_testing_diagnostics_artifact(
    *,
    validation_run_id: str,
    source_db_snapshot_id: str | None,
    source_data_time_range: dict[str, Any],
    weight_sweep: dict[str, Any],
) -> dict[str, Any]:
    trials = _trial_rows(list(weight_sweep.get("sweep_results") or []))
    eligible_trials = [trial for trial in trials if trial["eligible_for_statistics"]]
    best_trial = max(eligible_trials, key=lambda trial: float(trial["ic_ir"])) if eligible_trials else None
    trial_count = len(trials)
    eligible_trial_count = len(eligible_trials)
    pbo_proxy = None
    dsr_confidence = None
    alpha_t_stat_equivalent = None
    if best_trial is not None and trial_count > 0:
        best_ic_ir = float(best_trial["ic_ir"])
        alpha_t_stat_equivalent = best_ic_ir * math.sqrt(max(int(best_trial["snapshot_count"]), 1))
        # Conservative deterministic proxy: every unvalidated trial carries overfit mass unless OOS proves otherwise.
        pbo_proxy = max(0.0, min(1.0, 1.0 - (eligible_trial_count / max(trial_count, 1))))
        comparison_penalty = math.sqrt(max(2.0 * math.log(max(trial_count, 2)), 1.0))
        dsr_confidence = _normal_cdf(alpha_t_stat_equivalent - comparison_penalty)

    blocked_ids: list[str] = []
    if eligible_trial_count < MIN_TRIALS_FOR_PBO:
        blocked_ids.append("insufficient_eligible_trials_for_pbo")
    if best_trial is None:
        blocked_ids.append("missing_deflated_sharpe_inputs")
    else:
        if pbo_proxy is None or pbo_proxy > 0.10:
            blocked_ids.append("pbo_above_threshold")
        if dsr_confidence is None or dsr_confidence < 0.95:
            blocked_ids.append("deflated_sharpe_confidence_below_95pct")
        if alpha_t_stat_equivalent is None or alpha_t_stat_equivalent < 3.0:
            blocked_ids.append("alpha_t_stat_below_multiple_testing_threshold")

    diagnostics_digest = _stable_digest(
        {
            "diagnostics_version": MULTIPLE_TESTING_DIAGNOSTICS_VERSION,
            "source_weight_sweep_id": weight_sweep.get("artifact_id"),
            "trial_count": trial_count,
            "eligible_trial_count": eligible_trial_count,
            "trials": trials,
        }
    )
    artifact_id = f"pbo-dsr-multiple-comparison-{diagnostics_digest[:16]}"
    return {
        "artifact_type": "pbo_dsr_multiple_comparison",
        "schema_version": MULTIPLE_TESTING_DIAGNOSTICS_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_db_snapshot_id,
        "source_data_time_range": source_data_time_range,
        "feature_version": "not_applicable_multiple_testing_diagnostics",
        "label_version": "daily_close_forward_excess_return:v1",
        "code_version": "unresolved_local_checkout",
        "config_version": MULTIPLE_TESTING_DIAGNOSTICS_VERSION,
        "validation_protocol": {
            "artifact_role": "pbo_dsr_multiple_comparison",
            "diagnostics_version": MULTIPLE_TESTING_DIAGNOSTICS_VERSION,
            "pbo_threshold": 0.10,
            "deflated_sharpe_confidence_threshold": 0.95,
            "alpha_t_stat_threshold": 3.0,
            "minimum_eligible_trials_for_pbo": MIN_TRIALS_FOR_PBO,
            "minimum_periods_for_dsr": MIN_PERIODS_FOR_DSR,
        },
        "gate_readout": {
            "gate_status": "blocked" if blocked_ids else "multiple_testing_ready",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "multiple_testing_diagnostic_only",
            "blocking_gate_ids": blocked_ids,
        },
        "claim_ceiling": "multiple_testing_diagnostic_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_artifacts": {
            "weight_sweep_study_id": weight_sweep.get("artifact_id"),
            "walk_forward_protocol_id": (weight_sweep.get("walk_forward_protocol") or {}).get("artifact_id"),
        },
        "trial_count": trial_count,
        "eligible_trial_count": eligible_trial_count,
        "best_trial": best_trial,
        "pbo": pbo_proxy,
        "deflated_sharpe_confidence": dsr_confidence,
        "alpha_t_stat_equivalent": alpha_t_stat_equivalent,
        "diagnostics_content_digest": diagnostics_digest,
        "trials": trials,
    }


def multiple_testing_diagnostics_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "schema_version": payload.get("schema_version"),
        "artifact_id": payload.get("artifact_id"),
        "trial_count": payload.get("trial_count"),
        "eligible_trial_count": payload.get("eligible_trial_count"),
        "pbo": payload.get("pbo"),
        "deflated_sharpe_confidence": payload.get("deflated_sharpe_confidence"),
        "alpha_t_stat_equivalent": payload.get("alpha_t_stat_equivalent"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "gate_readout": payload.get("gate_readout"),
        "storage_boundary": payload.get("storage_boundary"),
    }


def write_multiple_testing_diagnostics_artifact(payload: dict[str, Any], *, artifact_root: str) -> Path:
    return write_research_validation_artifact(
        "pbo_dsr_multiple_comparison",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
