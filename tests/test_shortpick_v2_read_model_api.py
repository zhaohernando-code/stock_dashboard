from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ashare_evidence.api import create_app
from ashare_evidence.db import init_database
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    ENTRY_POLICY,
    FIXED90_POLICY,
    FORWARD_OBSERVATION_DISPOSITION,
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
    H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS,
    LEDGER_POLICY,
    MIN_ANNUALIZED_RETURN,
    NO_DELAYED_BUY_POLICY,
    PAPER_TRACKING_STATUS,
    PRIOR_NO_PROMOTION_DECISION,
    RECOMMENDATION_STATUS,
    RISK_FLAG_DISPOSITION,
    SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_read_model import (
    SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
    SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV,
    SHORTPICK_V2_REPLAY_ARTIFACT_ENV,
    SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV,
    build_shortpick_v2_historical_replay_read_model,
    build_shortpick_v2_paper_tracking_read_model,
)
from ashare_evidence.shortpick_v2_rule_selection import build_shortpick_v2_rule_selection_artifact


def _result(
    config_id: str,
    *,
    trade_count: int,
    skip_count: int,
    fallback_trade_count: int,
    total_return: float,
    max_drawdown: float,
    mean_invested_ratio: float,
    turnover: float,
    market_reference_total_return: float | None = None,
) -> dict[str, object]:
    signal_count = 721
    summary = {
        "signal_count": signal_count,
        "trade_count": trade_count,
        "skip_count": skip_count,
        "fallback_trade_count": fallback_trade_count,
        "final_nav": 200_000 * (1 + total_return),
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "mean_invested_ratio": mean_invested_ratio,
        "max_position_count": 5,
        "turnover": turnover,
        "skipped_ratio": round(skip_count / signal_count, 6),
    }
    if market_reference_total_return is not None:
        summary["market_reference_total_return"] = market_reference_total_return
    return {
        "config_id": config_id,
        "status": "ready",
        "summary": summary,
        "reason_counts": {
            "action:buy_primary": max(trade_count - fallback_trade_count, 0),
            "action:buy_fallback": fallback_trade_count,
            "action:skip": skip_count,
            "exit:mechanical_horizon": trade_count,
        },
        "decision_samples": [
            {
                "signal_date": "2023-05-16",
                "action": "buy_primary",
                "reason": "bought_primary",
                "selected_rank": 1,
                "symbol": "601988.SH",
                "cash_before": 200000.0,
                "cash_after": 160080.32,
                "quantity": 9600,
            },
            {
                "signal_date": "2023-05-17",
                "action": "skip",
                "reason": "insufficient_cash",
                "selected_rank": None,
                "symbol": None,
                "cash_before": 1200.0,
                "cash_after": 1200.0,
                "quantity": 0,
            },
        ],
        "detail_refs": {},
    }


def _replay_artifact() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_replay_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_replay_artifact:test:20260612",
        "generated_at": "2026-06-12T08:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay",
        "source_plan_ref": "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-3",
        "data_scope": {
            "signal_date_from": "2023-05-16",
            "signal_date_to": "2026-05-08",
            "signal_day_count": 721,
            "trade_day_count": 761,
            "coverage_status": "complete",
        },
        "input_contracts": {},
        "rule_matrix": [],
        "results": [
            _result(
                "top1_or_skip_v1",
                trade_count=212,
                skip_count=509,
                fallback_trade_count=0,
                total_return=0.113162,
                max_drawdown=-0.308438,
                mean_invested_ratio=0.352473,
                turnover=52.105779,
            ),
            _result(
                "top3_fallback_v1",
                trade_count=352,
                skip_count=369,
                fallback_trade_count=143,
                total_return=0.26501,
                max_drawdown=-0.327548,
                mean_invested_ratio=0.526949,
                turnover=79.638865,
            ),
            _result(
                "fixed_notional_40k_top5_v1",
                trade_count=398,
                skip_count=323,
                fallback_trade_count=126,
                total_return=0.249952,
                max_drawdown=-0.325321,
                mean_invested_ratio=0.421972,
                turnover=62.040153,
            ),
            _result(
                "position_cap_utilization_top5_v1",
                trade_count=372,
                skip_count=349,
                fallback_trade_count=156,
                total_return=0.213425,
                max_drawdown=-0.382083,
                mean_invested_ratio=0.525921,
                turnover=75.0798,
            ),
            _result(
                "conservative_cash_reserve_60k_top5_v1",
                trade_count=363,
                skip_count=358,
                fallback_trade_count=139,
                total_return=0.245516,
                max_drawdown=-0.261957,
                mean_invested_ratio=0.386994,
                turnover=59.527422,
            ),
        ],
        "promotion_gate": {"status": "not_evaluated"},
        "leakage_audit": {"status": "passed"},
        "event_refs": ["shortpick_v2.phase3.replay_artifact.generated"],
    }


def _qualified_replay_artifact() -> dict[str, object]:
    market_reference_total_return = 0.45
    return {
        **_replay_artifact(),
        "results": [
            _result(
                "top1_or_skip_v1",
                trade_count=212,
                skip_count=509,
                fallback_trade_count=0,
                total_return=0.35,
                max_drawdown=-0.308438,
                mean_invested_ratio=0.352473,
                turnover=52.105779,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "top3_fallback_v1",
                trade_count=352,
                skip_count=369,
                fallback_trade_count=143,
                total_return=1.25,
                max_drawdown=-0.327548,
                mean_invested_ratio=0.526949,
                turnover=79.638865,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "fixed_notional_40k_top5_v1",
                trade_count=398,
                skip_count=323,
                fallback_trade_count=126,
                total_return=1.35,
                max_drawdown=-0.325321,
                mean_invested_ratio=0.421972,
                turnover=62.040153,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "position_cap_utilization_top5_v1",
                trade_count=372,
                skip_count=349,
                fallback_trade_count=156,
                total_return=1.4,
                max_drawdown=-0.382083,
                mean_invested_ratio=0.525921,
                turnover=75.0798,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "conservative_cash_reserve_60k_top5_v1",
                trade_count=363,
                skip_count=358,
                fallback_trade_count=139,
                total_return=1.45,
                max_drawdown=-0.261957,
                mean_invested_ratio=0.386994,
                turnover=59.527422,
                market_reference_total_return=market_reference_total_return,
            ),
        ],
    }


def _write_v2_artifacts(
    tmp_path: Path,
    monkeypatch,
    *,
    replay: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    replay_path = tmp_path / "shortpick-v2-replay.json"
    selection_path = tmp_path / "shortpick-v2-rule-selection.json"
    missing_ledger_path = tmp_path / "missing-paper-ledger.json"
    replay = replay or _replay_artifact()
    selection = build_shortpick_v2_rule_selection_artifact(
        replay,
        replay_artifact_path=replay_path,
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )
    replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
    selection_path.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv(SHORTPICK_V2_REPLAY_ARTIFACT_ENV, str(replay_path))
    monkeypatch.setenv(SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV, str(selection_path))
    monkeypatch.setenv(SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV, str(missing_ledger_path))
    monkeypatch.setenv(
        SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
        str(tmp_path / "missing-h10-paper-governance.json"),
    )
    return replay_path, selection_path, missing_ledger_path


def _write_h10_paper_governance_artifact(tmp_path: Path, monkeypatch) -> Path:
    governance_path = tmp_path / "shortpick-v2-h10-paper-governance.json"
    governance_path.write_text(
        json.dumps(_h10_paper_governance_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv(SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV, str(governance_path))
    return governance_path


def _h10_paper_governance_artifact() -> dict[str, object]:
    return {
        "artifact_family": SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_h10_paper_governance:test",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_governance_evidence_future_true_forward_observation_only",
        "source_plan_ref": "plans/active/plan-20260615-h10-paper-governance.md",
        "source_artifacts": {
            "rank_ablation": _source_ref("shortpick_v2_h10_rank_ablation_artifact"),
            "parameter_significance": _source_ref("shortpick_v2_h10_parameter_significance_artifact"),
            "robustness": _source_ref("shortpick_v2_h10_robustness_artifact"),
            "execution_decomposition": _source_ref("shortpick_v2_h10_execution_decomposition_artifact"),
        },
        "analysis_scope": {
            "horizon_days": 10,
            "initial_cash": 200_000.0,
            "signal_date_from": "2023-04-13",
            "signal_date_to": "2026-05-08",
            "paper_tracking_start_date": "2026-05-08",
            "primary_config_id": H10_QUIET_CHAMPION_CONFIG_ID,
            "capital_shadow_config_id": H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
            "diagnostic_config_ids": [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID],
        },
        "governance_policy": {
            "ledger_policy": LEDGER_POLICY,
            "entry_policy": ENTRY_POLICY,
            "no_delayed_buy_policy": NO_DELAYED_BUY_POLICY,
            "fixed90_policy": FIXED90_POLICY,
            "qualification_floor": {
                "min_annualized_return": MIN_ANNUALIZED_RETURN,
                "must_beat_market": True,
            },
            "claim_policy": "historical_replay_is_not_true_forward_paper_performance",
        },
        "source_validation": {
            "overall_status": "passed",
            "rank_ablation": {"status": "passed", "rank2_support_label": "supported"},
            "parameter_significance": {"status": "passed", "failed_check_count": 0},
            "robustness": {
                "status": "passed",
                "recommendation_status": "not_ready_for_paper_tracking",
                "risk_flag_count": 1,
                "high_risk_flag_count": 1,
            },
            "execution_decomposition": {"status": "passed", "missing_config_ids": []},
        },
        "source_disposition": {
            "prior_decision": PRIOR_NO_PROMOTION_DECISION,
            "robustness_recommendation_status": "not_ready_for_paper_tracking",
            "risk_flag_count": 1,
            "high_risk_flag_count": 1,
            "risk_flag_disposition": RISK_FLAG_DISPOSITION,
            "governance_disposition": FORWARD_OBSERVATION_DISPOSITION,
        },
        "candidate_configs": [
            _h10_candidate_config(
                H10_QUIET_CHAMPION_CONFIG_ID,
                "primary_future_observation_candidate",
                annualized_return=0.5396,
            ),
            _h10_candidate_config(
                H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
                "capital_shadow_future_observation_candidate",
                annualized_return=0.5203,
            ),
        ],
        "diagnostic_configs": [
            {
                "config_id": H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
                "role": "diagnostic_boundary",
                "diagnostic_only": True,
                "paper_tracking_eligible": False,
                "blocked_reason": FIXED90_POLICY,
                "target_notional": 90_000.0,
            }
        ],
        "ledger_contract_overlay": {
            "selected_config_ids": list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS),
            "diagnostic_rejected_config_ids": [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID],
            "allowed_signal_actions": ["buy_primary", "buy_fallback", "skip"],
            "forbidden_signal_actions": ["delay_buy", "later_buy", "retry_buy", "discretionary_buy"],
            "entry_policy": ENTRY_POLICY,
            "ledger_policy": LEDGER_POLICY,
            "paper_tracking_start_date": "2026-05-08",
            "record_backfill_allowed": False,
            "current_true_forward_record_count": 0,
            "row_evidence_basis": "future_true_forward_paper_tracking_only",
        },
        "recommendation": {
            "status": RECOMMENDATION_STATUS,
            "paper_tracking_status": PAPER_TRACKING_STATUS,
            "notes": ["Future observation only; no true-forward rows yet."],
        },
        "leakage_audit": {
            "status": "passed",
            "no_historical_paper_row_backfill": True,
            "no_delayed_buy_action": True,
            "no_fixed90_promotion": True,
            "no_database_write_or_refresh": True,
            "no_investment_or_production_claim": True,
        },
        "event_refs": ["shortpick_v2.h10_paper_governance.test"],
    }


def _source_ref(artifact_family: str) -> dict[str, object]:
    return {
        "artifact_id": f"{artifact_family}:test",
        "artifact_family": artifact_family,
        "schema_version": "v1",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_test_fixture",
        "path": f"{artifact_family}.json",
    }


def _h10_candidate_config(config_id: str, role: str, *, annualized_return: float) -> dict[str, object]:
    summary = {
        "total_return": 2.7,
        "annualized_return": annualized_return,
        "market_reference_total_return": 0.418,
        "market_excess_total_return": 2.282,
        "max_drawdown": -0.119,
        "trade_count": 190,
        "turnover": 76.67,
        "skipped_ratio": 0.7365,
    }
    return {
        "config_id": config_id,
        "role": role,
        "source_role": "benchmark_control",
        "eligibility_status": "future_true_forward_observation_candidate_only",
        "paper_tracking_performance_claim": False,
        "current_true_forward_record_count": 0,
        "summary": summary,
        "qualification_checks": {
            "passed": True,
            "min_annualized_return": MIN_ANNUALIZED_RETURN,
            "annualized_return": annualized_return,
            "annualized_return_meets_floor": True,
            "market_excess_total_return": summary["market_excess_total_return"],
            "beats_market": True,
        },
    }


def _source_selection_artifact_ref(
    selection_path: Path,
    *,
    selected_config_ids: list[str] | None = None,
) -> dict[str, object]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    return {
        "artifact_id": selection["artifact_id"],
        "artifact_family": "shortpick_v2_rule_selection_artifact",
        "schema_version": "v1",
        "path": str(selection_path),
        "selected_config_ids": selected_config_ids
        if selected_config_ids is not None
        else [str(row["config_id"]) for row in selection.get("selected_configs", [])],
        "baseline_config_ids": [str(row["config_id"]) for row in selection.get("baseline_configs", [])],
        "holdout_config_ids": [str(row["config_id"]) for row in selection.get("holdout_configs", [])],
        "rejected_config_ids": [str(row["config_id"]) for row in selection.get("rejected_configs", [])],
        "claim_ceiling": "research_observation",
    }


def _valid_v2_paper_ledger(selection_path: Path) -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_paper_tracking_ledger",
        "schema_version": "v1",
        "ledger_id": "shortpick_v2_paper_tracking_ledger:test",
        "generated_at": "2026-06-12T10:00:00+00:00",
        "status": "active",
        "claim_ceiling": "research_observation",
        "evidence_basis": "true_forward_tracking",
        "source_contract_ref": "docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md",
        "source_selection_artifact": _source_selection_artifact_ref(selection_path),
        "tracking_window": {
            "start_date": "2026-05-08",
            "start_policy": "v1_aligned_forward_window",
            "source_gap_policy": "record_source_gap_or_not_observed_without_shifting_start_date",
            "backfill_policy": "historical_replay_rows_must_not_be_backfilled_as_true_forward_tracking",
        },
        "account_contract": {
            "initial_cash": 200000,
            "currency": "CNY",
            "board_lot_size": 100,
            "account_profile": "new_retail_cash_account",
            "selected_config_ids": [
                "conservative_cash_reserve_60k_top5_v1",
                "fixed_notional_40k_top5_v1",
            ],
            "baseline_config_ids": ["top1_or_skip_v1"],
            "selection_policy": "shortpick_v2_rule_selection_v2",
        },
        "row_contract": {
            "allowed_signal_actions": ["buy_primary", "buy_fallback", "skip"],
            "forbidden_signal_actions": ["delay_buy", "later_buy", "retry_buy", "discretionary_buy"],
            "entry_policy": "declared_entry_date_only_fallback_or_skip_no_delayed_entry",
            "source_gap_policy": "record_source_gap_or_not_observed",
            "ledger_policy": "future_true_forward_only_no_historical_backfill",
        },
        "records": [_valid_v2_paper_record()],
        "summary": {
            "record_count": 1,
            "buy_count": 1,
            "skip_count": 0,
            "source_gap_count": 0,
            "open_position_count": 1,
            "closed_position_count": 0,
        },
        "leakage_audit": {
            "status": "passed",
            "source_selection_artifact_required": True,
            "used_only_signal_day_or_earlier_data": True,
            "notes": ["Fixture ledger follows the public v2 paper-tracking JSON schema."],
        },
        "research_labeling": {
            "claim_ceiling": "research_observation",
            "evidence_basis": "true_forward_tracking",
            "prohibited_claims": ["production_ready", "investment_advice", "automated_trading"],
            "notes": ["V2 paper tracking is paper research only."],
        },
        "event_refs": ["shortpick_v2.phase6.test_ledger"],
    }


def _valid_v2_paper_record() -> dict[str, object]:
    return {
        "record_id": "shortpick_v2:test:2026-05-08:conservative",
        "config_id": "conservative_cash_reserve_60k_top5_v1",
        "config_role": "phase5_contract_candidate",
        "signal_date": "2026-05-08",
        "decision_date": "2026-05-08",
        "decision_action": "buy_primary",
        "reason": "bought_primary",
        "selected_rank": 1,
        "symbol": "601988.SH",
        "source_state": "observed",
        "entry_trade_date": "2026-05-11",
        "entry_price_source": "next_close",
        "quantity": 9600,
        "board_lot_size": 100,
        "cash_before": 200000,
        "cash_after": 160080.32,
        "position_state": "open",
        "evidence_basis": "true_forward_tracking",
        "validation_status": "open",
        "exit_trade_date": None,
        "exit_reason": None,
        "notes": [],
    }


def test_shortpick_v2_historical_replay_read_model_uses_selected_precomputed_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)

    payload = build_shortpick_v2_historical_replay_read_model(sample_limit=1)

    assert payload["status"] == "blocked"
    assert payload["claim_ceiling"] == "research_observation"
    assert payload["evidence_basis"] == "historical_account_replay_selection"
    assert payload["selected_configs"] == []
    assert [item["config_id"] for item in payload["baseline_configs"]] == ["top1_or_skip_v1"]
    assert payload["holdout_configs"] == []
    assert {item["config_id"] for item in payload["rejected_configs"]} == {
        "conservative_cash_reserve_60k_top5_v1",
        "fixed_notional_40k_top5_v1",
        "position_cap_utilization_top5_v1",
        "top3_fallback_v1",
    }
    assert payload["leakage_audit"]["read_model_policy"] == "read_only_precomputed_artifacts_no_dynamic_replay"


def test_shortpick_v2_paper_tracking_returns_contract_ready_empty_projection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, _, missing_ledger_path = _write_v2_artifacts(tmp_path, monkeypatch)

    payload = build_shortpick_v2_paper_tracking_read_model(include_records=True)

    assert payload["status"] == "blocked"
    assert payload["current_status"] == "blocked"
    assert payload["evidence_basis"] == "true_forward_tracking"
    assert payload["records"] == []
    assert payload["source_artifacts"]["paper_ledger"]["status"] == "missing"
    assert payload["source_artifacts"]["paper_ledger"]["path"] == str(missing_ledger_path)
    assert payload["selected_configs"] == []
    assert payload["baseline_configs"][0]["config_id"] == "top1_or_skip_v1"
    assert "No v2 config currently qualifies" in payload["current_message"]
    assert payload["tracking_window"]["start_date"] == "2026-05-08"
    assert payload["row_contract"]["allowed_signal_actions"] == ["buy_primary", "buy_fallback", "skip"]
    assert "delay_buy" in payload["row_contract"]["forbidden_signal_actions"]


def test_shortpick_v2_paper_tracking_projects_h10_governance_without_backfilled_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    governance_path = _write_h10_paper_governance_artifact(tmp_path, monkeypatch)

    payload = build_shortpick_v2_paper_tracking_read_model(include_records=True)

    assert payload["status"] == "contract_ready"
    assert payload["current_status"] == RECOMMENDATION_STATUS
    assert payload["records"] == []
    assert [row["config_id"] for row in payload["selected_configs"]] == list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    assert payload["summary"]["record_count"] == 0
    assert payload["summary"]["paper_tracking_status"] == PAPER_TRACKING_STATUS
    assert payload["paper_governance"]["selected_config_ids"] == list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    assert payload["paper_governance"]["diagnostic_rejected_config_ids"] == [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID]
    assert payload["paper_governance"]["current_true_forward_record_count"] == 0
    assert payload["source_artifacts"]["paper_governance"]["path"] == str(governance_path)
    assert "历史回放不计为纸面追踪收益" in payload["data_disclaimer"]


def test_shortpick_v2_paper_tracking_reads_existing_v2_ledger_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, ledger_path = _write_v2_artifacts(tmp_path, monkeypatch, replay=_qualified_replay_artifact())
    ledger = _valid_v2_paper_ledger(selection_path)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = build_shortpick_v2_paper_tracking_read_model(include_records=True)

    assert payload["status"] == "active"
    assert payload["source_artifacts"]["paper_ledger"]["artifact_family"] == "shortpick_v2_paper_tracking_ledger"
    assert payload["tracking_window"]["start_date"] == "2026-05-08"
    assert payload["summary"]["record_count"] == 1
    assert payload["records"][0]["decision_action"] == "buy_primary"
    assert payload["records"][0]["evidence_basis"] == "true_forward_tracking"


def test_shortpick_v2_paper_tracking_rejects_h10_fixed90_active_ledger_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, ledger_path = _write_v2_artifacts(tmp_path, monkeypatch, replay=_qualified_replay_artifact())
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    ledger = _valid_v2_paper_ledger(selection_path)
    ledger["account_contract"]["selected_config_ids"] = [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID]
    ledger["records"][0]["config_id"] = H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="fixed90"):
        build_shortpick_v2_paper_tracking_read_model(include_records=True)


def test_shortpick_v2_paper_tracking_rejects_delayed_entry_action_in_read_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, ledger_path = _write_v2_artifacts(tmp_path, monkeypatch, replay=_qualified_replay_artifact())
    ledger = _valid_v2_paper_ledger(selection_path)
    ledger["records"][0]["decision_action"] = "delay_buy"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="delay_buy"):
        build_shortpick_v2_paper_tracking_read_model(include_records=True)


def test_shortpick_v2_read_api_routes_return_v2_payloads(tmp_path: Path, monkeypatch) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    database_path = tmp_path / "api.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    replay_response = client.get("/shortpick-lab-v2/historical-replay?sample_limit=1")
    paper_response = client.get("/shortpick-lab-v2/paper-tracking/summary")

    assert replay_response.status_code == 200
    assert replay_response.json()["status"] == "blocked"
    assert replay_response.json()["selected_configs"] == []
    assert paper_response.status_code == 200
    assert paper_response.json()["status"] == "blocked"
    assert paper_response.json()["summary"]["record_count"] == 0


def test_shortpick_v2_read_api_preserves_h10_paper_governance_projection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "api.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    response = client.get("/shortpick-lab-v2/paper-tracking/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "contract_ready"
    assert body["summary"]["record_count"] == 0
    assert body["records"] == []
    assert body["paper_governance"]["selected_config_ids"] == list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    assert body["paper_governance"]["paper_tracking_status"] == PAPER_TRACKING_STATUS


def test_shortpick_v2_read_api_fails_closed_when_required_artifact_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    replay_path, _, _ = _write_v2_artifacts(tmp_path, monkeypatch)
    monkeypatch.setenv(SHORTPICK_V2_REPLAY_ARTIFACT_ENV, str(replay_path))
    monkeypatch.setenv(SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV, str(tmp_path / "missing-selection.json"))
    database_path = tmp_path / "api.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    response = client.get("/shortpick-lab-v2/historical-replay")

    assert response.status_code == 503
    assert "shortpick v2 rule selection artifact is missing" in response.json()["detail"]


def test_shortpick_v2_read_api_rejects_overclaimed_selection_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, _ = _write_v2_artifacts(tmp_path, monkeypatch)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["claim_ceiling"] = "production_ready"
    selection_path.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
    database_path = tmp_path / "api.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    response = client.get("/shortpick-lab-v2/historical-replay")

    assert response.status_code == 500
    assert "claim_ceiling must be research_observation" in response.json()["detail"]
