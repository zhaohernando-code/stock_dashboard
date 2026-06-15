from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH
from ashare_evidence.shortpick_market_factor_study import ENTRY_PRICE_SOURCE_NEXT_CLOSE
from ashare_evidence.shortpick_v2_h10_robustness import (
    DEFAULT_MAX_HOLDOUT_CONFIGS,
    DIAGNOSTIC_ANALYSIS_ROLE,
    H10_QUIET_DIAGNOSTIC_CONFIG_IDS,
    SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY,
    build_shortpick_v2_h10_robustness_artifact,
)
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_COST_BPS,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STAMP_TAX_BPS,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)

SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY = (
    "shortpick_v2_h10_execution_decomposition_artifact"
)
SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_SCHEMA_VERSION = "v1"
SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_CONFIG_IDS = (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0],
)
DEFAULT_BOARD_LOT_SIZE = 100


def build_shortpick_v2_h10_execution_decomposition_artifact(
    session: Session,
    *,
    replay_artifact_path: str | Path,
    selection_artifact_path: str | Path,
    start_date: date,
    end_date: date,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    entry_price_source: str = ENTRY_PRICE_SOURCE_NEXT_CLOSE,
    horizon_days: int = 10,
    pool_limit: int = 40,
    rank_limit: int = 6,
    cost_bps: float = DEFAULT_COST_BPS,
    stamp_tax_bps: float = DEFAULT_STAMP_TAX_BPS,
    min_signal_symbol_count: int = 45,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    max_holdout_configs: int = DEFAULT_MAX_HOLDOUT_CONFIGS,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    robustness_artifact = build_shortpick_v2_h10_robustness_artifact(
        session,
        replay_artifact_path=replay_artifact_path,
        selection_artifact_path=selection_artifact_path,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        entry_price_source=entry_price_source,
        horizon_days=horizon_days,
        pool_limit=pool_limit,
        rank_limit=rank_limit,
        cost_bps=cost_bps,
        stamp_tax_bps=stamp_tax_bps,
        min_signal_symbol_count=min_signal_symbol_count,
        account_profile=account_profile,
        max_holdout_configs=max_holdout_configs,
        generated_at=generated_at,
    )
    return build_shortpick_v2_h10_execution_decomposition_artifact_from_robustness_artifact(
        robustness_artifact,
        generated_at=generated_at,
    )


def build_shortpick_v2_h10_execution_decomposition_artifact_from_robustness_artifact(
    robustness_artifact: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    _validate_robustness_artifact(robustness_artifact)
    generated_at = generated_at or datetime.now(UTC)
    analysis_scope = robustness_artifact.get("analysis_scope") or {}
    initial_cash = _optional_float(analysis_scope.get("initial_cash")) or DEFAULT_INITIAL_CASH
    parameter_by_config = {
        str(row.get("config_id")): row
        for row in (robustness_artifact.get("parameter_stability") or {}).get("rows", [])
        if isinstance(row, dict) and row.get("config_id")
    }
    analyzed_by_config = {
        str(row.get("config_id")): row
        for row in robustness_artifact.get("analyzed_configs") or []
        if isinstance(row, dict) and row.get("config_id")
    }
    rows = [
        _decomposition_row(
            config_id,
            analyzed_by_config[config_id],
            parameter_by_config.get(config_id) or {},
            initial_cash=initial_cash,
            fixed85_summary=(analyzed_by_config.get(H10_QUIET_CHAMPION_CONFIG_ID) or {}).get("summary") or {},
        )
        for config_id in SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_CONFIG_IDS
        if config_id in analyzed_by_config
    ]
    missing_config_ids = [
        config_id
        for config_id in SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_CONFIG_IDS
        if config_id not in analyzed_by_config
    ]
    # fixed80/fixed85 are required decision rows; 90k is diagnostic-only and may be absent in older artifacts.
    status = "ready" if not missing_config_ids[:2] and rows else "blocked"
    return {
        "artifact_family": SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, robustness_artifact),
        "generated_at": generated_at.isoformat(),
        "status": status,
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_execution_decomposition",
        "source_robustness_artifact": _source_artifact_ref(robustness_artifact),
        "analysis_scope": {
            "config_ids": list(SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_CONFIG_IDS),
            "decomposed_config_count": len(rows),
            "missing_config_ids": missing_config_ids,
            "initial_cash": initial_cash,
            "horizon_days": analysis_scope.get("horizon_days"),
            "entry_price_source": analysis_scope.get("entry_price_source"),
        },
        "decomposition_policy": {
            "target_configs": "fixed80_capital_shadow_fixed85_champion_and_90k_diagnostic",
            "cash_policy": "Cash deployment uses robustness summary totals and mean invested ratio.",
            "board_lot_policy": "Board-lot pressure uses reason counts and replay rule metadata when available.",
            "winner_policy": "Winner concentration uses post-hoc trade contribution stress, not a resimulated path.",
            "promotion_policy": "90k remains diagnostic-only and cannot be promoted by this artifact.",
        },
        "config_decompositions": rows,
        "pairwise_funding_effects": _pairwise_funding_effects(rows),
        "event_refs": [
            "shortpick_v2.h10_quiet.execution_decomposition.generated",
            f"shortpick_v2.execution_decomposition.source.{robustness_artifact.get('artifact_id')}",
        ],
    }


def write_shortpick_v2_h10_execution_decomposition_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _decomposition_row(
    config_id: str,
    analyzed: dict[str, Any],
    parameter_row: dict[str, Any],
    *,
    initial_cash: float,
    fixed85_summary: dict[str, Any],
) -> dict[str, Any]:
    summary = analyzed.get("summary") or {}
    reason_counts = analyzed.get("reason_counts") or {}
    target_notional = _optional_float(parameter_row.get("target_notional"))
    board_lot_size = _optional_int(parameter_row.get("board_lot_size")) or DEFAULT_BOARD_LOT_SIZE
    top_winner = _first(analyzed.get("top_winning_trades") or [])
    top_winner_stress = _stress_by_remove_count(analyzed.get("trade_contribution_stress") or [], 1)
    return {
        "config_id": config_id,
        "role": str(analyzed.get("role") or "unknown"),
        "diagnostic_only": str(analyzed.get("role") or "") == DIAGNOSTIC_ANALYSIS_ROLE,
        "target_notional": target_notional,
        "board_lot": {
            "board_lot_size": board_lot_size,
            "target_notional": target_notional,
            "target_notional_pct_of_initial_cash": _safe_ratio(target_notional, initial_cash),
            "board_lot_block_count": _count_reasons(reason_counts, "board_lot_minimum"),
            "insufficient_cash_count": _count_reasons(reason_counts, "insufficient_cash"),
        },
        "cash_deployment": {
            "initial_cash": initial_cash,
            "final_cash": _optional_float(summary.get("final_cash")),
            "final_market_value": _optional_float(summary.get("final_market_value")),
            "final_cash_ratio": _safe_ratio(_optional_float(summary.get("final_cash")), initial_cash),
            "mean_invested_ratio": _optional_float(summary.get("mean_invested_ratio")),
            "cash_drag_proxy": _cash_drag_proxy(summary),
            "total_buy_value": _optional_float(summary.get("total_buy_value")),
            "total_buy_value_to_initial_cash": _safe_ratio(_optional_float(summary.get("total_buy_value")), initial_cash),
        },
        "turnover_skip": {
            "turnover": _optional_float(summary.get("turnover")),
            "trade_count": _optional_int(summary.get("trade_count")),
            "skip_count": _optional_int(summary.get("skip_count")),
            "skipped_ratio": _optional_float(summary.get("skipped_ratio")),
            "fallback_trade_count": _optional_int(summary.get("fallback_trade_count")),
            "buy_primary_count": _optional_int(reason_counts.get("action:buy_primary")),
            "buy_fallback_count": _optional_int(reason_counts.get("action:buy_fallback")),
            "skip_reason_counts": _reason_subset(reason_counts),
        },
        "winner_concentration": {
            "largest_symbol_abs_pnl_share": (analyzed.get("symbol_concentration") or {}).get("largest_abs_pnl_share"),
            "largest_industry_abs_pnl_share": (analyzed.get("industry_concentration") or {}).get(
                "largest_abs_pnl_share"
            ),
            "top_winner_symbol": top_winner.get("symbol"),
            "top_winner_net_pnl": _optional_float(top_winner.get("net_pnl")),
            "remove_top_1_total_return_proxy": top_winner_stress.get("total_return_proxy"),
            "remove_top_1_annualized_return_proxy": top_winner_stress.get("annualized_return_proxy"),
            "remove_top_1_market_excess_total_return_proxy": top_winner_stress.get(
                "market_excess_total_return_proxy"
            ),
        },
        "funding_effect_vs_fixed85": _summary_delta(summary, fixed85_summary),
    }


def _pairwise_funding_effects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_config = {row["config_id"]: row for row in rows}
    fixed85 = by_config.get(H10_QUIET_CHAMPION_CONFIG_ID)
    if fixed85 is None:
        return []
    output = []
    for config_id in (H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]):
        row = by_config.get(config_id)
        if row is None:
            continue
        output.append(
            {
                "comparison_id": f"{config_id}_vs_fixed85",
                "config_id": config_id,
                "baseline_config_id": H10_QUIET_CHAMPION_CONFIG_ID,
                "target_notional_delta": _delta(row.get("target_notional"), fixed85.get("target_notional")),
                "total_return_delta": row["funding_effect_vs_fixed85"]["total_return_delta"],
                "annualized_return_delta": row["funding_effect_vs_fixed85"]["annualized_return_delta"],
                "turnover_delta": row["funding_effect_vs_fixed85"]["turnover_delta"],
                "skip_count_delta": row["funding_effect_vs_fixed85"]["skip_count_delta"],
            }
        )
    return output


def _summary_delta(summary: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_return_delta": _delta(summary.get("total_return"), baseline.get("total_return")),
        "annualized_return_delta": _delta(summary.get("annualized_return"), baseline.get("annualized_return")),
        "turnover_delta": _delta(summary.get("turnover"), baseline.get("turnover")),
        "trade_count_delta": _int_delta(summary.get("trade_count"), baseline.get("trade_count")),
        "skip_count_delta": _int_delta(summary.get("skip_count"), baseline.get("skip_count")),
        "mean_invested_ratio_delta": _delta(summary.get("mean_invested_ratio"), baseline.get("mean_invested_ratio")),
        "final_cash_delta": _delta(summary.get("final_cash"), baseline.get("final_cash")),
    }


def _source_artifact_ref(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.get("artifact_id") or ""),
        "artifact_family": str(artifact.get("artifact_family") or ""),
        "schema_version": str(artifact.get("schema_version") or ""),
        "status": str(artifact.get("status") or ""),
        "claim_ceiling": str(artifact.get("claim_ceiling") or ""),
        "evidence_basis": str(artifact.get("evidence_basis") or ""),
    }


def _validate_robustness_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("artifact_family") != SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY:
        raise ValueError("robustness_artifact must be shortpick_v2_h10_robustness_artifact")
    if artifact.get("schema_version") != "v1":
        raise ValueError("robustness_artifact schema_version must be v1")
    if artifact.get("claim_ceiling") != "research_observation":
        raise ValueError("robustness_artifact claim_ceiling must be research_observation")


def _artifact_id(generated_at: datetime, robustness_artifact: dict[str, Any]) -> str:
    return f"shortpick_v2_h10_execution_decomposition:{robustness_artifact.get('artifact_id')}:{generated_at.date()}"


def _reason_subset(reason_counts: dict[str, Any]) -> dict[str, int]:
    return {
        key.removeprefix("reason:"): int(value)
        for key, value in sorted(reason_counts.items())
        if key.startswith("reason:")
    }


def _count_reasons(reason_counts: dict[str, Any], reason: str) -> int:
    return int(reason_counts.get(f"reason:{reason}") or 0) + int(reason_counts.get(f"candidate_reject:{reason}") or 0)


def _cash_drag_proxy(summary: dict[str, Any]) -> float | None:
    mean_invested_ratio = _optional_float(summary.get("mean_invested_ratio"))
    return None if mean_invested_ratio is None else round(1.0 - mean_invested_ratio, 6)


def _stress_by_remove_count(stress_rows: list[dict[str, Any]], remove_count: int) -> dict[str, Any]:
    return next(
        (row for row in stress_rows if int(row.get("remove_top_winner_count") or 0) == remove_count),
        {},
    )


def _first(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def _delta(value: Any, baseline: Any) -> float | None:
    left = _optional_float(value)
    right = _optional_float(baseline)
    if left is None or right is None:
        return None
    return round(left - right, 6)


def _int_delta(value: Any, baseline: Any) -> int | None:
    left = _optional_int(value)
    right = _optional_int(baseline)
    if left is None or right is None:
        return None
    return left - right


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
