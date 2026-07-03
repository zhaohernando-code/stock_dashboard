from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_COMPARISON_REPORT_SCHEMA_VERSION = "model_comparison_report.v1"


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _leaderboard_row(trial: dict[str, Any]) -> dict[str, Any]:
    metrics = trial.get("metrics") or {}
    blockers = list(trial.get("blocking_gate_ids") or [])
    return {
        "trial_id": trial.get("trial_id"),
        "model_spec_id": trial.get("model_spec_id"),
        "rank_ic_mean": metrics.get("rank_ic_mean"),
        "positive_rank_ic_rate": metrics.get("positive_rank_ic_rate"),
        "top_quantile_net_excess_mean": metrics.get("top_quantile_net_excess_mean"),
        "top_bottom_spread_mean": metrics.get("top_bottom_spread_mean"),
        "labeled_prediction_count": metrics.get("labeled_prediction_count"),
        "decision": "kill" if blockers else "observe_blocked",
        "blocking_gate_ids": blockers,
    }


def _sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        _safe_float(row.get("rank_ic_mean"), -999.0),
        _safe_float(row.get("top_quantile_net_excess_mean"), -999.0),
        _safe_float(row.get("top_bottom_spread_mean"), -999.0),
    )


def build_model_comparison_report_artifact(
    *,
    validation_run_id: str,
    candidate_run: dict[str, Any],
    model_spec_registry: dict[str, Any],
) -> dict[str, Any]:
    leaderboard = [_leaderboard_row(trial) for trial in candidate_run.get("trial_summaries") or []]
    leaderboard.sort(key=_sort_key, reverse=True)
    spec_ids = [str(spec.get("model_spec_id")) for spec in model_spec_registry.get("model_specs") or []]
    baseline_rows = [
        row for row in leaderboard if row.get("model_spec_id") == "baseline_momentum_10d_turnover_cooldown_v1"
    ]
    best_baseline = baseline_rows[0] if baseline_rows else None
    kill_list = [
        {
            "trial_id": row.get("trial_id"),
            "model_spec_id": row.get("model_spec_id"),
            "reasons": row.get("blocking_gate_ids") or ["blocked_until_governance_review"],
        }
        for row in leaderboard
        if row.get("blocking_gate_ids")
    ]
    report_body = {
        "summary": {
            "candidate_run_id": candidate_run.get("artifact_id"),
            "model_spec_registry_id": model_spec_registry.get("artifact_id"),
            "registered_model_spec_ids": spec_ids,
            "trial_count": candidate_run.get("trial_count"),
            "prediction_row_count": candidate_run.get("prediction_row_count"),
            "claim_ceiling": "comparison_report_only",
            "promotion_status": "blocked_from_production",
        },
        "candidate_leaderboard": leaderboard,
        "baseline_comparison": {
            "baseline_model_spec_id": "baseline_momentum_10d_turnover_cooldown_v1",
            "best_baseline": best_baseline,
            "best_overall": leaderboard[0] if leaderboard else None,
            "same_window_policy": "all rows come from the same candidate_run splits",
        },
        "overfit_diagnostics": {
            "status": "blocked",
            "reason": "PBO/DSR full diagnostics are pending the next comparison hardening slice",
        },
        "winner_dependency": {
            "status": "blocked",
            "reason": "top symbol/date/month removal diagnostics are pending the next comparison hardening slice",
        },
        "execution_diagnostics": {
            "status": "partial",
            "source": "executable_label_matrix label block reasons are included through candidate run labels",
        },
        "kill_list": kill_list,
        "next_research_questions": [
            "Implement full PBO/DSR diagnostics over registered trial results.",
            "Add winner-dependency recomputation by removing top symbol, date and month contributors.",
            "Harden candidate runner training logic beyond deterministic foundation scoring.",
        ],
    }
    content_digest = _stable_digest(report_body)
    artifact_id = f"model-comparison-report-{content_digest[:16]}"
    return {
        "artifact_type": "model_comparison_report",
        "schema_version": MODEL_COMPARISON_REPORT_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": candidate_run.get("source_db_snapshot_id"),
        "source_data_time_range": candidate_run.get("source_data_time_range"),
        "feature_version": candidate_run.get("feature_version"),
        "label_version": candidate_run.get("label_version"),
        "code_version": "unresolved_local_checkout",
        "config_version": "shortpick_model_comparison_report:v1",
        "validation_protocol": {
            "comparison_policy": "registered_candidate_run_trials_only",
            "raw_prediction_policy": "summarize_and_gate_do_not_promote",
            "production_effect": "forbidden",
        },
        "gate_readout": {
            "gate_status": "blocked",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "comparison_report_only",
            "blocking_gate_ids": [
                "pbo_dsr_diagnostics_pending",
                "winner_dependency_diagnostics_pending",
                "governance_promotion_pending",
            ],
        },
        "claim_ceiling": "comparison_report_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_candidate_run_id": candidate_run.get("artifact_id"),
        "source_model_spec_registry_id": model_spec_registry.get("artifact_id"),
        "report_content_digest": content_digest,
        **report_body,
    }


def write_model_comparison_report_artifact(
    payload: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
) -> Path:
    return write_research_validation_artifact(
        "model_comparison_report",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
