from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema

from ashare_evidence.shortpick_v2_h10_paper_governance import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
)

SCHEMA_PATH = Path("docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json")
CONTRACT_PATH = Path("docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md")


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _base_ledger() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_paper_tracking_ledger",
        "schema_version": "v1",
        "ledger_id": "shortpick_v2_paper_tracking_ledger:contract:2026-06-12",
        "generated_at": "2026-06-12T10:00:00+00:00",
        "status": "contract_ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "true_forward_tracking",
        "source_contract_ref": "docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md",
        "source_selection_artifact": {
            "artifact_id": (
                "shortpick_v2_rule_selection_artifact:shortpick_v2_replay_artifact:"
                "2023-04-13:2026-05-08:200000:2026-06-12:2026-06-12"
            ),
            "artifact_family": "shortpick_v2_rule_selection_artifact",
            "schema_version": "v1",
            "path": "/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json",
            "selected_config_ids": [],
            "baseline_config_ids": ["top1_or_skip_v1"],
            "holdout_config_ids": [],
            "rejected_config_ids": [
                "top3_fallback_v1",
                "fixed_notional_40k_top5_v1",
                "position_cap_utilization_top5_v1",
                "conservative_cash_reserve_60k_top5_v1",
            ],
            "claim_ceiling": "research_observation",
        },
        "tracking_window": {
            "start_date": "2026-05-08",
            "start_policy": "v1_aligned_forward_window",
            "source_gap_policy": "record_source_gap_or_not_observed_without_shifting_start_date",
            "backfill_policy": "historical_replay_rows_must_not_be_backfilled_as_true_forward_tracking",
        },
        "account_contract": {
            "initial_cash": 200_000.0,
            "currency": "CNY",
            "board_lot_size": 100,
            "account_profile": "new_retail_cash_account",
            "selected_config_ids": [],
            "baseline_config_ids": ["top1_or_skip_v1"],
        },
        "row_contract": {
            "allowed_signal_actions": ["buy_primary", "buy_fallback", "skip"],
            "forbidden_signal_actions": ["delay_buy", "later_buy", "retry_buy", "discretionary_buy"],
            "entry_policy": "declared_entry_date_only_fallback_or_skip_no_delayed_entry",
            "source_gap_policy": "record_source_gap_or_not_observed",
            "ledger_policy": "future_true_forward_only_no_historical_backfill",
        },
        "records": [],
        "summary": {
            "record_count": 0,
            "buy_count": 0,
            "skip_count": 0,
            "source_gap_count": 0,
            "open_position_count": 0,
            "closed_position_count": 0,
        },
        "leakage_audit": {
            "status": "not_run",
            "source_selection_artifact_required": True,
            "used_only_signal_day_or_earlier_data": True,
            "notes": ["Contract artifact only; row-level leakage audit runs when future paper rows are produced."],
        },
        "research_labeling": {
            "claim_ceiling": "research_observation",
            "evidence_basis": "true_forward_tracking",
            "prohibited_claims": ["production_ready", "investment_advice", "automated_trading"],
            "notes": ["V2 paper tracking is paper research only."],
        },
        "event_refs": ["shortpick_v2.phase5.paper_tracking_contract.defined"],
    }


def _buy_row() -> dict[str, object]:
    return {
        "record_id": "2026-05-08:conservative_cash_reserve_60k_top5_v1:buy",
        "config_id": "conservative_cash_reserve_60k_top5_v1",
        "config_role": "phase5_contract_candidate",
        "signal_date": "2026-05-08",
        "decision_date": "2026-05-08",
        "decision_action": "buy_primary",
        "reason": "rank1_executable_under_account_constraints",
        "selected_rank": 1,
        "symbol": "600000.SH",
        "entry_trade_date": "2026-05-11",
        "entry_price_source": "next_close",
        "quantity": 100,
        "board_lot_size": 100,
        "cash_before": 200_000.0,
        "cash_after": 196_000.0,
        "position_state": "open",
        "evidence_basis": "true_forward_tracking",
        "source_state": "observed",
        "validation_status": "open",
        "exit_trade_date": None,
        "exit_reason": None,
        "notes": [],
    }


def _skip_row() -> dict[str, object]:
    return {
        "record_id": "2026-05-08:fixed_notional_40k_top5_v1:skip",
        "config_id": "fixed_notional_40k_top5_v1",
        "config_role": "phase5_contract_candidate",
        "signal_date": "2026-05-08",
        "decision_date": "2026-05-08",
        "decision_action": "skip",
        "reason": "board_lot_minimum",
        "selected_rank": None,
        "symbol": None,
        "entry_trade_date": None,
        "entry_price_source": None,
        "quantity": 0,
        "board_lot_size": 100,
        "cash_before": 200_000.0,
        "cash_after": 200_000.0,
        "position_state": "not_opened",
        "evidence_basis": "true_forward_tracking",
        "source_state": "observed",
        "validation_status": "skipped",
        "exit_trade_date": None,
        "exit_reason": None,
        "notes": ["No delayed entry may be recorded for this signal."],
    }


def _h10_buy_row(config_id: str) -> dict[str, object]:
    row = _buy_row()
    row["record_id"] = f"2026-05-08:{config_id}:buy"
    row["config_id"] = config_id
    row["config_role"] = "phase6_forward_observation_candidate"
    row["reason"] = "h10_forward_observation_candidate_executable"
    return row


def test_shortpick_v2_paper_tracking_schema_accepts_empty_contract_ledger() -> None:
    jsonschema.Draft202012Validator(_schema()).validate(_base_ledger())


def test_shortpick_v2_paper_tracking_schema_accepts_buy_and_skip_rows() -> None:
    ledger = _base_ledger()
    ledger["records"] = [_buy_row(), _skip_row()]
    ledger["summary"] = {
        "record_count": 2,
        "buy_count": 1,
        "skip_count": 1,
        "source_gap_count": 0,
        "open_position_count": 1,
        "closed_position_count": 0,
    }

    jsonschema.Draft202012Validator(_schema()).validate(ledger)


def test_shortpick_v2_paper_tracking_schema_accepts_h10_fixed85_fixed80_candidates() -> None:
    ledger = _base_ledger()
    # Schema coverage only: these rows model future true-forward ledger rows, not historical backfill.
    ledger["source_selection_artifact"]["selected_config_ids"] = [
        H10_QUIET_CHAMPION_CONFIG_ID,
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    ]
    ledger["account_contract"]["selected_config_ids"] = [
        H10_QUIET_CHAMPION_CONFIG_ID,
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    ]
    ledger["row_contract"]["ledger_policy"] = "future_true_forward_only_no_historical_backfill"
    ledger["records"] = [
        _h10_buy_row(H10_QUIET_CHAMPION_CONFIG_ID),
        _h10_buy_row(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID),
    ]
    ledger["summary"] = {
        "record_count": 2,
        "buy_count": 2,
        "skip_count": 0,
        "source_gap_count": 0,
        "open_position_count": 2,
        "closed_position_count": 0,
    }

    jsonschema.Draft202012Validator(_schema()).validate(ledger)


def test_shortpick_v2_paper_tracking_schema_rejects_h10_fixed90_active_row() -> None:
    ledger = _base_ledger()
    ledger["records"] = [_h10_buy_row(H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID)]
    ledger["summary"] = {
        "record_count": 1,
        "buy_count": 1,
        "skip_count": 0,
        "source_gap_count": 0,
        "open_position_count": 1,
        "closed_position_count": 0,
    }

    errors = list(jsonschema.Draft202012Validator(_schema()).iter_errors(ledger))
    assert errors
    assert any(H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID in str(error.message) for error in errors)


def test_shortpick_v2_paper_tracking_schema_rejects_delayed_entry_action() -> None:
    ledger = _base_ledger()
    row = _buy_row()
    row["decision_action"] = "delay_buy"
    ledger["records"] = [row]
    ledger["summary"] = {
        "record_count": 1,
        "buy_count": 0,
        "skip_count": 0,
        "source_gap_count": 0,
        "open_position_count": 0,
        "closed_position_count": 0,
    }

    errors = list(jsonschema.Draft202012Validator(_schema()).iter_errors(ledger))
    assert errors
    assert any("delay_buy" in str(error.message) for error in errors)


def test_shortpick_v2_paper_tracking_schema_rejects_unselected_active_config() -> None:
    ledger = _base_ledger()
    row = copy.deepcopy(_buy_row())
    row["config_id"] = "legacy_v1_equal_notional"
    ledger["records"] = [row]

    errors = list(jsonschema.Draft202012Validator(_schema()).iter_errors(ledger))
    assert errors
    assert any("legacy_v1_equal_notional" in str(error.message) for error in errors)


def test_shortpick_v2_paper_tracking_contract_contains_required_boundaries() -> None:
    body = CONTRACT_PATH.read_text(encoding="utf-8")

    assert "2026-05-08" in body
    assert "conservative_cash_reserve_60k_top5_v1" in body
    assert "fixed_notional_40k_top5_v1" in body
    assert "top1_or_skip_v1" in body
    assert H10_QUIET_CHAMPION_CONFIG_ID in body
    assert H10_QUIET_CAPITAL_SHADOW_CONFIG_ID in body
    assert H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID in body
    assert "H10 paper governance; future true-forward only; fixed90 diagnostic only." in body
    assert "No delayed-entry action is allowed." in body
    assert "does not write paper-tracking rows" in body
    assert "backend APIs" in body
    assert "frontend tabs" in body
    assert "refresh market data" in body
