"""Short-pick strategy governance evidence builders.

The functions in this module are intentionally read-only. They aggregate
already materialized paper-tracking rows into evidence packs for later human
or policy-governed retirement decisions, but they do not decide retirement.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any


def build_shortpick_strategy_retirement_evidence_packs(
    paper_tracking: dict[str, Any],
    *,
    evidence_basis: str = "true_forward_tracking",
    historical_evidence: dict[str, Any] | None = None,
    baseline_evidence: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build strategy-level evidence packs from the paper-tracking ledger.

    ``paper_tracking`` is expected to match the JSON returned by
    ``_build_shortpick_paper_tracking_ledger``. ``evidence_basis`` defaults to
    true forward tracking because that is the source ledger, but callers must
    override it for retrospective or historical inputs. Optional historical and
    baseline inputs are copied by strategy key/family when available; missing
    optional evidence is represented explicitly instead of inferred.
    """

    if evidence_basis not in {"true_forward_tracking", "retrospective_forward_replay", "historical_backtest"}:
        raise ValueError(f"unsupported shortpick evidence_basis: {evidence_basis}")

    items = [_dict(item) for item in paper_tracking.get("items") or [] if isinstance(item, dict)]
    grouped: dict[str, dict[str, Any]] = {}
    observations_by_strategy_horizon: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for item in items:
        metadata = _strategy_metadata(item)
        strategy_id = str(metadata["strategy_id"])
        existing = grouped.get(strategy_id)
        if existing is None:
            grouped[strategy_id] = {
                **metadata,
                "signal_count": 0,
                "symbols": set(),
                "names": set(),
                "first_signal_date": None,
                "latest_signal_date": None,
            }
            existing = grouped[strategy_id]

        existing["signal_count"] = int(existing.get("signal_count") or 0) + 1
        symbol = str(item.get("symbol") or "")
        name = str(item.get("name") or "")
        if symbol:
            existing["symbols"].add(symbol)
        if name:
            existing["names"].add(name)
        _extend_date_bounds(existing, str(item.get("signal_date") or item.get("run_date") or ""))

        for horizon in item.get("validation_by_horizon") or []:
            if not isinstance(horizon, dict) or horizon.get("status") != "completed":
                continue
            stock_return = _float(horizon.get("stock_return"))
            if stock_return is None:
                continue
            horizon_days = _horizon_key(horizon.get("horizon_days"))
            observations_by_strategy_horizon[strategy_id][horizon_days].append(
                {
                    "candidate_id": item.get("candidate_id"),
                    "run_id": item.get("run_id"),
                    "signal_date": item.get("signal_date") or item.get("run_date"),
                    "entry_date": item.get("entry_date") or _date_part(horizon.get("entry_at") or item.get("entry_at")),
                    "exit_date": _date_part(horizon.get("exit_at") or item.get("exit_at")),
                    "symbol": symbol,
                    "name": name,
                    "stock_return": stock_return,
                    "excess_return": _float(horizon.get("excess_return")),
                }
            )

    packs: list[dict[str, Any]] = []
    for strategy_id in sorted(grouped):
        metadata = grouped[strategy_id]
        horizon_summaries = [
            _horizon_summary(horizon_days, observations)
            for horizon_days, observations in sorted(
                observations_by_strategy_horizon.get(strategy_id, {}).items(),
                key=lambda item: int(item[0]) if item[0].isdigit() else 9999,
            )
        ]
        completed_count = sum(int(summary["completed_sample_count"]) for summary in horizon_summaries)
        packs.append(
            {
                "strategy_id": strategy_id,
                "evidence_basis": evidence_basis,
                "decision_status": "not_evaluated",
                "tracking_group": metadata["tracking_group"],
                "tracking_role": metadata["tracking_role"],
                "strategy_family": metadata["strategy_family"],
                "entry_price_source": metadata["entry_price_source"],
                "source_rank": metadata["source_rank"],
                "selection_label": metadata["selection_label"],
                "entry_rule": metadata["entry_rule"],
                "signal_count": metadata["signal_count"],
                "completed_observation_count": completed_count,
                "distinct_symbol_count": len(metadata["symbols"]),
                "symbols": sorted(metadata["symbols"]),
                "names": sorted(metadata["names"]),
                "first_signal_date": metadata["first_signal_date"],
                "latest_signal_date": metadata["latest_signal_date"],
                "horizon_summaries": horizon_summaries,
                "historical_evidence": _evidence_lookup(historical_evidence, metadata),
                "baseline_comparison": _evidence_lookup(baseline_evidence, metadata),
            }
        )

    return {
        "status": "ready",
        "generated_at": generated_at,
        "evidence_basis": evidence_basis,
        "source": "shortpick_paper_tracking_ledger",
        "decision_policy": "evidence_only_no_retirement_decision",
        "strategy_count": len(packs),
        "packs": packs,
    }


def _strategy_metadata(item: dict[str, Any]) -> dict[str, Any]:
    components = _dict(item.get("selection_score_components"))
    tracking_group = str(item.get("tracking_group") or "unknown")
    tracking_role = str(item.get("tracking_role") or "")
    family = str(
        components.get("family")
        or item.get("baseline_family")
        or item.get("strategy_family")
        or ("llm" if tracking_group == "llm_paper_control" else "unknown")
    )
    source_rank = item.get("source_rank")
    entry_rule = str(item.get("entry_rule") or "")
    entry_price_source = str(
        components.get("entry_price_source")
        or item.get("entry_price_source")
        or _infer_entry_price_source(tracking_group=tracking_group, entry_rule=entry_rule)
    )
    strategy_id = _strategy_id(
        [
            tracking_group,
            tracking_role or "primary",
            family,
            entry_price_source,
            "" if source_rank is None else str(source_rank),
        ]
    )
    return {
        "strategy_id": strategy_id,
        "tracking_group": tracking_group,
        "tracking_role": tracking_role,
        "strategy_family": family,
        "entry_price_source": entry_price_source,
        "source_rank": source_rank,
        "selection_label": str(item.get("selection_label") or ""),
        "entry_rule": entry_rule,
        "signal_count": 0,
    }


def _horizon_summary(horizon_days: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    stock_returns = [float(item["stock_return"]) for item in observations]
    excess_returns = [float(item["excess_return"]) for item in observations if item.get("excess_return") is not None]
    signal_dates = sorted({str(item.get("signal_date") or "") for item in observations if item.get("signal_date")})
    symbol_negative_counts = Counter(
        str(item.get("symbol") or "")
        for item in observations
        if item.get("symbol") and float(item["stock_return"]) < 0
    )
    repeated_losses = [
        {"symbol": symbol, "negative_completed_count": count}
        for symbol, count in sorted(symbol_negative_counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ]
    positive_returns = [value for value in stock_returns if value > 0]
    positive_sum = sum(positive_returns)
    best_positive_share = max(positive_returns) / positive_sum if positive_sum > 0 else None
    return {
        "horizon_days": int(horizon_days) if horizon_days.isdigit() else horizon_days,
        "completed_sample_count": len(observations),
        "distinct_signal_date_count": len(signal_dates),
        "maturity_status": _maturity_status(len(observations), len(signal_dates)),
        "mean_stock_return": _round(mean(stock_returns)),
        "median_stock_return": _round(median(stock_returns)),
        "win_rate": _round(sum(1 for value in stock_returns if value > 0) / len(stock_returns)),
        "mean_excess_return": _round(mean(excess_returns)) if excess_returns else None,
        "median_excess_return": _round(median(excess_returns)) if excess_returns else None,
        "worst_stock_return": _round(min(stock_returns)),
        "best_stock_return": _round(max(stock_returns)),
        "negative_completed_count": sum(1 for value in stock_returns if value < 0),
        "max_additive_drawdown": _round(_max_additive_drawdown(observations)),
        "tail_dependency": {
            "best_positive_share": _round(best_positive_share),
            "tail_dependent": bool(best_positive_share is not None and best_positive_share > 0.5),
            "basis": "best_positive_stock_return_share_of_positive_stock_return_sum",
        },
        "same_symbol_loss_repeats": repeated_losses,
        "first_signal_date": signal_dates[0] if signal_dates else None,
        "latest_signal_date": signal_dates[-1] if signal_dates else None,
    }


def _maturity_status(completed_count: int, distinct_signal_date_count: int) -> str:
    if completed_count >= 30 and distinct_signal_date_count >= 10:
        return "mature_multi_row_review_sample"
    if completed_count >= 10:
        return "mature_one_stock_review_sample"
    return "insufficient_completed_sample"


def _max_additive_drawdown(observations: list[dict[str, Any]]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for item in sorted(observations, key=lambda row: str(row.get("signal_date") or "")):
        cumulative += float(item["stock_return"])
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
    return drawdown


def _evidence_lookup(source: dict[str, Any] | None, metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict) or not source:
        return {"status": "missing_artifact"}
    for key in (
        str(metadata.get("strategy_id") or ""),
        str(metadata.get("strategy_family") or ""),
        str(metadata.get("tracking_role") or ""),
        str(metadata.get("tracking_group") or ""),
    ):
        value = source.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {"status": "missing_artifact"}


def _extend_date_bounds(metadata: dict[str, Any], value: str) -> None:
    if not value:
        return
    first = metadata.get("first_signal_date")
    latest = metadata.get("latest_signal_date")
    if not first or value < first:
        metadata["first_signal_date"] = value
    if not latest or value > latest:
        metadata["latest_signal_date"] = value


def _infer_entry_price_source(*, tracking_group: str, entry_rule: str) -> str:
    if tracking_group == "frozen_strategy_v2":
        return "next_open"
    return "unknown"


def _strategy_id(parts: list[str]) -> str:
    return "__".join(_slug(part) for part in parts if part)


def _slug(value: str) -> str:
    safe = []
    for char in value.lower():
        if char.isalnum():
            safe.append(char)
        else:
            safe.append("_")
    return "_".join("".join(safe).strip("_").split("_")) or "unknown"


def _horizon_key(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value or "")
    return text if text else "unknown"


def _date_part(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return value.split("T", 1)[0].split(" ", 1)[0]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)
