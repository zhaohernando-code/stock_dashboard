from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.phase2.common import spearman_correlation
from ashare_evidence.research_artifact_store import write_research_validation_artifact

OOS_VALIDATION_SCHEMA_VERSION = "oos_validation.v1"
OOS_VALIDATION_VERSION = "walk_forward_holdout_oos:v1"
MIN_OOS_PERIODS = 3
MIN_OOS_ROWS = 60


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _fusion_score(row: dict[str, Any]) -> float:
    weights = row.get("dynamic_weights") if isinstance(row.get("dynamic_weights"), dict) else {}
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    return sum(float(scores.get(key, 0.0)) * float(weights.get(key, 0.0)) for key in scores)


def _test_dates(walk_forward_protocol: dict[str, Any]) -> set[str]:
    dates: set[str] = set()
    for split in walk_forward_protocol.get("splits") or []:
        if split.get("status") != "ready":
            continue
        test_range = split.get("test_range") if isinstance(split.get("test_range"), dict) else {}
        start = test_range.get("start")
        end = test_range.get("end")
        if start and start == end:
            dates.add(str(start))
        elif start:
            dates.add(str(start))
        if end:
            dates.add(str(end))
    return dates


def _oos_rows(observation_rows: list[dict[str, Any]], test_dates: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in observation_rows:
        as_of_date = str(row.get("as_of_date") or "")[:10]
        if as_of_date not in test_dates:
            continue
        score = _fusion_score(row)
        rows.append(
            {
                "symbol": row.get("symbol"),
                "recommendation_key": row.get("recommendation_key"),
                "as_of_date": as_of_date,
                "horizon_days": row.get("horizon_days"),
                "fusion_score": round(score, 8),
                "forward_excess_return": row.get("forward_excess_return"),
            }
        )
    return rows


def _period_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["as_of_date"]), int(row["horizon_days"])), []).append(row)
    metrics: list[dict[str, Any]] = []
    for (as_of_date, horizon), group in sorted(grouped.items()):
        if len(group) < 2:
            continue
        scores = [float(row["fusion_score"]) for row in group]
        returns = [float(row["forward_excess_return"]) for row in group]
        ranked = sorted(zip(scores, returns), key=lambda item: item[0])
        bucket_size = max(1, len(ranked) // 3)
        bottom = ranked[:bucket_size]
        top = ranked[-bucket_size:]
        top_mean = sum(item[1] for item in top) / len(top)
        bottom_mean = sum(item[1] for item in bottom) / len(bottom)
        metrics.append(
            {
                "as_of_date": as_of_date,
                "horizon_days": horizon,
                "rank_ic": round(spearman_correlation(scores, returns), 8),
                "top_quantile_mean_excess": round(top_mean, 8),
                "top_bottom_spread": round(top_mean - bottom_mean, 8),
                "sample_count": len(group),
            }
        )
    return metrics


def build_oos_validation_artifact(
    *,
    validation_run_id: str,
    source_db_snapshot_id: str | None,
    source_data_time_range: dict[str, Any],
    factor_study: dict[str, Any],
    walk_forward_protocol: dict[str, Any],
) -> dict[str, Any]:
    rows = _oos_rows(list(factor_study.get("observation_rows") or []), _test_dates(walk_forward_protocol))
    period_metrics = _period_metrics(rows)
    temporal_period_count = len({str(row.get("as_of_date")) for row in rows})
    rank_ics = [float(item["rank_ic"]) for item in period_metrics]
    top_quantile_excess = [float(item["top_quantile_mean_excess"]) for item in period_metrics]
    rank_ic_mean = _safe_mean(rank_ics)
    rank_ic_std = _safe_std(rank_ics)
    if rank_ic_mean is None:
        icir = None
    elif rank_ic_std > 0:
        icir = rank_ic_mean / rank_ic_std
    else:
        icir = 999.0 if rank_ic_mean > 0 else None
    positive_ic_rate = (
        sum(1 for value in rank_ics if value > 0) / len(rank_ics)
        if rank_ics
        else None
    )
    top_quantile_mean_excess = _safe_mean(top_quantile_excess)
    top_quantile_net_excess_positive = top_quantile_mean_excess is not None and top_quantile_mean_excess > 0
    blocked_ids: list[str] = []
    if temporal_period_count < MIN_OOS_PERIODS:
        blocked_ids.append("insufficient_oos_periods")
    if len(rows) < MIN_OOS_ROWS:
        blocked_ids.append("insufficient_oos_rows")
    if rank_ic_mean is None or rank_ic_mean <= 0.02:
        blocked_ids.append("oos_rank_ic_below_0_02")
    if icir is None or icir <= 0.35:
        blocked_ids.append("oos_icir_below_0_35")
    if positive_ic_rate is None or positive_ic_rate < 0.55:
        blocked_ids.append("positive_ic_months_below_55pct")
    if not top_quantile_net_excess_positive:
        blocked_ids.append("top_quantile_net_excess_not_positive")

    digest = _stable_digest(
        {
            "oos_version": OOS_VALIDATION_VERSION,
            "factor_study_id": factor_study.get("artifact_id"),
            "walk_forward_protocol_id": walk_forward_protocol.get("artifact_id"),
            "rows": rows,
            "period_metrics": period_metrics,
        }
    )
    artifact_id = f"oos-validation-{digest[:16]}"
    return {
        "artifact_type": "oos_validation",
        "schema_version": OOS_VALIDATION_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_db_snapshot_id,
        "source_data_time_range": source_data_time_range,
        "feature_version": factor_study.get("lineage", {}).get("independent_pit_feature_version"),
        "label_version": "daily_close_forward_excess_return:v1",
        "code_version": "unresolved_local_checkout",
        "config_version": OOS_VALIDATION_VERSION,
        "validation_protocol": {
            "artifact_role": "oos_validation",
            "oos_version": OOS_VALIDATION_VERSION,
            "source_split_policy": (walk_forward_protocol.get("validation_protocol") or {}).get("protocol_version"),
            "rank_ic_threshold": 0.02,
            "icir_threshold": 0.35,
            "positive_ic_rate_threshold": 0.55,
            "min_oos_periods": MIN_OOS_PERIODS,
            "min_oos_rows": MIN_OOS_ROWS,
        },
        "gate_readout": {
            "gate_status": "blocked" if blocked_ids else "oos_ready",
            "promotion_status": "blocked_from_production",
            "claim_ceiling": "oos_validation_only",
            "blocking_gate_ids": blocked_ids,
        },
        "claim_ceiling": "oos_validation_only",
        "promotion_status": "blocked_from_production",
        "storage_boundary": "research_validation_artifact_store_only",
        "source_artifacts": {
            "factor_ic_study_id": factor_study.get("artifact_id"),
            "walk_forward_protocol_id": walk_forward_protocol.get("artifact_id"),
        },
        "oos_row_count": len(rows),
        "oos_period_count": temporal_period_count,
        "oos_metric_row_count": len(period_metrics),
        "oos_rank_ic": rank_ic_mean,
        "oos_icir": icir,
        "positive_ic_rate": positive_ic_rate,
        "top_quantile_mean_excess": top_quantile_mean_excess,
        "top_quantile_net_excess_positive": top_quantile_net_excess_positive,
        "oos_content_digest": digest,
        "period_metrics": period_metrics,
        "oos_rows": rows,
    }


def oos_validation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "schema_version": payload.get("schema_version"),
        "artifact_id": payload.get("artifact_id"),
        "oos_row_count": payload.get("oos_row_count"),
        "oos_period_count": payload.get("oos_period_count"),
        "oos_metric_row_count": payload.get("oos_metric_row_count"),
        "oos_rank_ic": payload.get("oos_rank_ic"),
        "oos_icir": payload.get("oos_icir"),
        "positive_ic_rate": payload.get("positive_ic_rate"),
        "top_quantile_mean_excess": payload.get("top_quantile_mean_excess"),
        "top_quantile_net_excess_positive": payload.get("top_quantile_net_excess_positive"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "gate_readout": payload.get("gate_readout"),
        "storage_boundary": payload.get("storage_boundary"),
    }


def write_oos_validation_artifact(payload: dict[str, Any], *, artifact_root: str) -> Path:
    return write_research_validation_artifact(
        "oos_validation",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
