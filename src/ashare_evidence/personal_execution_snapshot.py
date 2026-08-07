from __future__ import annotations

import copy
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, build_trade_eligibility_snapshot
from ashare_evidence.rolling_account_execution_snapshot import (
    build_rolling_account_execution_snapshot,
    load_rolling_account_execution_snapshot,
    stable_digest,
    write_rolling_account_execution_snapshot,
)
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact

_ALLOCATION_FIELDS = (
    "base_gross_exposure",
    "date_exposure_floor",
    "date_exposure_scale",
    "date_exposure_scale_reasons",
    "date_position_scale",
    "date_position_scale_reasons",
    "portfolio_weight",
    "rank_portfolio_adjustment_multiplier",
    "rank_portfolio_adjustment_reasons",
    "rank_position_scale",
    "rank_position_scale_reasons",
    "rank_weight_multiplier",
    "signal_position_scale",
    "signal_position_scale_reasons",
    "target_horizon_days",
)


def build_personal_eligible_execution_snapshot(
    source_snapshot: dict[str, Any],
    *,
    account_profile: str = ACCOUNT_PROFILE_NEW_RETAIL_CASH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    trial_id = str(source_snapshot["trial_id"])
    source_trial = source_snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]
    top_k = int(source_trial["selected_top_k"])
    bars = source_snapshot["inputs"]["market_bars_by_symbol"]
    closes = {
        (symbol, str(row["day"])): float(row["close"])
        for symbol, rows in bars.items()
        for row in rows
    }
    original_selected_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_trial["selected_top_k_picks_by_date"]:
        original_selected_by_day[str(row["as_of_date"])].append(row)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    audited_inventory: list[dict[str, Any]] = []
    exclusion_counts: Counter[str] = Counter()
    for row in source_snapshot["inputs"]["candidate_inventory_rows"]:
        signal_day = str(row["as_of_date"])
        symbol = str(row["symbol"])
        price = closes.get((symbol, signal_day))
        eligibility = build_trade_eligibility_snapshot(
            symbol,
            account_profile=account_profile,
            as_of=date.fromisoformat(signal_day),
            decision_cutoff=signal_day,
            price_cny=price,
            price_observed_at=signal_day if price is not None else None,
            price_source="frozen_execution_snapshot.market_bars_by_symbol.close",
            price_adjustment="unadjusted",
            profile_is_point_in_time=False,
        )
        audited = {**row, "_trade_eligibility_snapshot": eligibility}
        audited_inventory.append(audited)
        by_day[signal_day].append(audited)
        exclusion_counts.update(eligibility["exclusion_reason_codes"])

    eligibility_by_day_symbol = {
        (str(row["as_of_date"]), str(row["symbol"])): row["_trade_eligibility_snapshot"]
        for row in audited_inventory
    }
    selected: list[dict[str, Any]] = []
    underfilled_days: list[str] = []
    for signal_day, rows in sorted(by_day.items()):
        original = sorted(
            original_selected_by_day.get(signal_day) or [],
            key=lambda row: int(float(row.get("rank") or 999)),
        )
        retained = [
            row
            for row in original
            if eligibility_by_day_symbol.get((signal_day, str(row["symbol"])), {}).get(
                "eligible_before_scoring"
            )
        ]
        retained_symbols = {str(row["symbol"]) for row in retained}
        refill = sorted(
            (
                row
                for row in rows
                if row["_trade_eligibility_snapshot"]["eligible_before_scoring"]
                and str(row["symbol"]) not in retained_symbols
            ),
            key=lambda row: (int(float(row.get("rank") or 999)), str(row.get("symbol") or "")),
        )
        chosen = (retained + refill)[:top_k]
        if len(chosen) < top_k:
            underfilled_days.append(signal_day)
        inventory_by_symbol = {str(row["symbol"]): row for row in rows}
        for rank, row in enumerate(chosen, start=1):
            template = next(
                (candidate for candidate in original if int(float(candidate["rank"])) == rank),
                None,
            )
            if template is None:
                raise ValueError(f"missing frozen allocation template for {signal_day} rank {rank}")
            inventory_row = inventory_by_symbol.get(str(row["symbol"]), row)
            selected_row = {
                **inventory_row,
                **{field: copy.deepcopy(template.get(field)) for field in _ALLOCATION_FIELDS},
                "rank": rank,
                "original_inventory_rank": int(float(inventory_row.get("rank") or 0)),
                "rank_weight_feature_values": copy.deepcopy(inventory_row.get("rank_weight_feature_values") or {}),
                "benchmark_return_10d": inventory_row.get("benchmark_return_10d"),
            }
            selected.append(selected_row)

    candidate_run = copy.deepcopy(source_snapshot["inputs"]["candidate_run"])
    trial = candidate_run["trial_diagnostics"][0]
    trial["selected_top_k_picks_by_date"] = selected
    candidate_run["artifact_id"] = f"personal-eligible-{stable_digest(selected)[:16]}"
    replay = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run,
        trial_id=trial_id,
        market_bars_by_symbol=bars,
        candidate_inventory_rows=audited_inventory,
        candidate_configurations=[copy.deepcopy(source_snapshot["inputs"]["baseline_config"])],
        **source_snapshot["inputs"]["account_profile"],
    )["results"][0]
    audit = {
        "account_profile": account_profile,
        "filter_stage": "before_strategy_scoring_and_ranking",
        "profile_is_point_in_time": False,
        "current_static_name_status_backfilled": False,
        "source_inventory_row_count": len(audited_inventory),
        "eligible_inventory_row_count": sum(
            bool(row["_trade_eligibility_snapshot"]["eligible_before_scoring"])
            for row in audited_inventory
        ),
        "excluded_inventory_row_count": sum(
            not row["_trade_eligibility_snapshot"]["eligible_before_scoring"]
            for row in audited_inventory
        ),
        "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
        "selected_pick_count": len(selected),
        "underfilled_signal_days": underfilled_days,
        "source_selected_excluded_count": sum(
            not eligibility_by_day_symbol.get((str(row["as_of_date"]), str(row["symbol"])), {}).get(
                "eligible_before_scoring", False
            )
            for row in source_trial["selected_top_k_picks_by_date"]
        ),
        "changed_selected_key_count": sum(
            (str(left["as_of_date"]), int(float(left["rank"])), str(left["symbol"]))
            != (str(right["as_of_date"]), int(float(right["rank"])), str(right["symbol"]))
            for left, right in zip(source_trial["selected_top_k_picks_by_date"], selected, strict=True)
        ),
        "eligibility_snapshot_digest": stable_digest(
            [row["_trade_eligibility_snapshot"] for row in audited_inventory]
        ),
    }
    snapshot = build_rolling_account_execution_snapshot(
        candidate_run=candidate_run,
        trial_id=trial_id,
        candidate_inventory_rows=audited_inventory,
        market_bars_by_symbol=bars,
        baseline_config=source_snapshot["inputs"]["baseline_config"],
        account_profile=source_snapshot["inputs"]["account_profile"],
        baseline_result=replay,
        source_lineage={
            **source_snapshot["source_lineage"],
            "parent_execution_snapshot_id": source_snapshot["artifact_id"],
            "personal_trade_eligibility": audit,
        },
    )
    return snapshot, audit


def build_and_write_personal_eligible_execution_snapshot(
    *, source_path: Path, output_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot, audit = build_personal_eligible_execution_snapshot(
        load_rolling_account_execution_snapshot(source_path)
    )
    write_rolling_account_execution_snapshot(output_path, snapshot)
    return snapshot, audit
