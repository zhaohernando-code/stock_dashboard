from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import ashare_evidence.shortpick_v2_read_model as shortpick_v2_read_model
from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock
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
    SHORTPICK_V2_H5_OBSERVATION_CONFIG_ID,
    SHORTPICK_V2_H5_STOP8_OBSERVATION_CONFIG_ID,
    SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
    SHORTPICK_V2_PAPER_DISPLAY_CACHE_VERSION,
    SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS,
    SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID,
    SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV,
    SHORTPICK_V2_REPLAY_ARTIFACT_ENV,
    SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV,
    _paper_display_account_curves_from_rows,
    _paper_display_row_from_replay_decision,
    build_shortpick_v2_historical_replay_read_model,
    build_shortpick_v2_paper_tracking_read_model,
)
from ashare_evidence.shortpick_v2_rule_selection import build_shortpick_v2_rule_selection_artifact


def _lineage(payload: object, uri: str) -> dict[str, str]:
    return {
        "license_tag": "test",
        "usage_scope": "internal-test",
        "redistribution_scope": "none",
        "source_uri": uri,
        "lineage_hash": compute_lineage_hash(payload),
    }


def _business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _seed_v2_paper_display_market_fixture(
    database_url: str,
    *,
    end_date: date = date(2026, 6, 15),
) -> None:
    days = _business_days(date(2026, 4, 1), end_date)
    symbols = [
        (f"600{index:03d}.SH", f"测试主板{index:03d}", "fixture", 8.0 + index * 0.12)
        for index in range(50)
    ]
    symbols.extend(
        [
            ("000300.SH", "沪深300", "benchmark", 100.0),
            ("000905.SH", "中证500", "benchmark", 120.0),
            ("000852.SH", "中证1000", "benchmark", 80.0),
        ]
    )
    with session_scope(database_url) as session:
        for symbol, name, industry, base_price in symbols:
            ticker, _, exchange = symbol.partition(".")
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange,
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={"industry": industry},
                **_lineage({"symbol": symbol}, f"test://stock/{symbol}"),
            )
            session.add(stock)
            session.flush()
            for day_index, observed_day in enumerate(days):
                pulse = 1.15 if observed_day >= date(2026, 5, 8) and observed_day.weekday() in {0, 1, 2} else 1.0
                close_price = (base_price + day_index * (0.04 + (day_index % 3) * 0.005)) * pulse
                open_price = close_price * 0.99
                session.add(
                    MarketBar(
                        bar_key=f"v2-paper-display-{symbol}-{observed_day.isoformat()}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(
                            observed_day.year,
                            observed_day.month,
                            observed_day.day,
                            7,
                            0,
                            tzinfo=UTC,
                        ),
                        open_price=open_price,
                        high_price=close_price * 1.03,
                        low_price=close_price * 0.97,
                        close_price=close_price,
                        volume=1_000_000 + day_index * 100 + len(symbol),
                        amount=(1_000_000 + day_index * 100 + len(symbol)) * close_price,
                        turnover_rate=0.8 + (day_index % 10) * 0.02,
                        total_mv=1_000_000_000 + day_index * 100_000,
                        circ_mv=900_000_000 + day_index * 100_000,
                        raw_payload={},
                        **_lineage(
                            {"symbol": symbol, "day": observed_day.isoformat()},
                            f"test://bar/{symbol}/{observed_day.isoformat()}",
                        ),
                    )
                )


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
    if config_id == H10_QUIET_CAPITAL_SHADOW_CONFIG_ID:
        total_return = 2.572453
        market_excess = 2.154009
        trade_count = 192
        turnover = 73.018706
        skipped_ratio = 0.733703
    else:
        total_return = 2.712294
        market_excess = 2.29385
        trade_count = 190
        turnover = 76.672058
        skipped_ratio = 0.736477
    summary = {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "market_reference_total_return": 0.418,
        "market_excess_total_return": market_excess,
        "max_drawdown": -0.119,
        "trade_count": trade_count,
        "turnover": turnover,
        "skipped_ratio": skipped_ratio,
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
    assert len(payload["baseline_configs"][0]["decision_samples"]) == 1
    assert payload["holdout_configs"] == []
    assert {item["config_id"] for item in payload["rejected_configs"]} == {
        "conservative_cash_reserve_60k_top5_v1",
        "fixed_notional_40k_top5_v1",
        "position_cap_utilization_top5_v1",
        "top3_fallback_v1",
    }
    assert payload["leakage_audit"]["read_model_policy"] == "read_only_precomputed_artifacts_no_dynamic_replay"

    summary_only_payload = build_shortpick_v2_historical_replay_read_model(sample_limit=0)
    assert summary_only_payload["baseline_configs"][0]["decision_samples"] == []
    assert summary_only_payload["summary"]["decision_sample_limit"] == 0


def test_shortpick_v2_historical_replay_read_model_restores_h10_governance_inventory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    governance_path = _write_h10_paper_governance_artifact(tmp_path, monkeypatch)

    payload = build_shortpick_v2_historical_replay_read_model(sample_limit=0)

    assert payload["status"] == "ready"
    assert [item["config_id"] for item in payload["selected_configs"]] == list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    fixed85 = payload["selected_configs"][0]
    fixed80 = payload["selected_configs"][1]
    assert fixed85["summary"]["total_return"] == 2.712294
    assert fixed85["summary"]["annualized_return"] == 0.5396
    assert fixed85["summary"]["max_drawdown"] == -0.119
    assert fixed85["summary"]["market_excess_total_return"] == 2.29385
    assert fixed85["summary"]["trade_count"] == 190
    assert fixed80["summary"]["total_return"] == 2.572453
    assert fixed80["summary"]["annualized_return"] == 0.5203
    assert fixed80["summary"]["trade_count"] == 192
    assert payload["summary"]["selected_config_count"] == 2
    assert payload["summary"]["h10_strategy_inventory"]["benchmark_config_id"] == H10_QUIET_CHAMPION_CONFIG_ID
    assert payload["summary"]["h10_strategy_inventory"]["capital_shadow_config_id"] == H10_QUIET_CAPITAL_SHADOW_CONFIG_ID
    assert payload["summary"]["h10_strategy_inventory"]["rank2_support_label"] == "supported"
    assert payload["source_artifacts"]["h10_paper_governance"]["path"] == str(governance_path)
    assert payload["holdout_configs"][0]["config_id"] == H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID
    assert payload["holdout_configs"][0]["gate_status"] == "diagnostic_only"
    assert payload["baseline_configs"][0]["role"] == "legacy_baseline_control"
    assert payload["baseline_configs"][0]["gate_status"] == "legacy_reference"
    assert "旧 strategy-search" in payload["baseline_configs"][0]["reason"]
    assert payload["rejected_configs"][0]["role"] == "legacy_rejected"
    assert payload["summary"]["legacy_strategy_search_context"]["status"] == "reference_only"
    assert "不计为真实前向纸面收益" in payload["data_disclaimer"]
    assert payload["leakage_audit"]["read_model_policy"] == (
        "read_only_precomputed_artifacts_with_h10_governance_overlay_no_dynamic_replay"
    )


def test_shortpick_v2_historical_replay_read_model_can_use_h10_only_when_old_artifacts_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(SHORTPICK_V2_REPLAY_ARTIFACT_ENV, str(tmp_path / "missing-replay.json"))
    monkeypatch.setenv(SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV, str(tmp_path / "missing-selection.json"))
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)

    payload = build_shortpick_v2_historical_replay_read_model(sample_limit=0)

    assert payload["status"] == "ready"
    assert payload["evidence_basis"] == "h10_governance_summary_only"
    assert payload["source_artifacts"]["replay"]["status"] == "missing"
    assert payload["source_artifacts"]["rule_selection"]["status"] == "missing"
    assert [item["config_id"] for item in payload["selected_configs"]] == list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    assert payload["baseline_configs"] == []
    assert payload["rejected_configs"] == []
    assert payload["holdout_configs"][0]["config_id"] == H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID
    assert payload["summary"]["h10_strategy_inventory"]["status"] == "ready"
    assert payload["leakage_audit"]["read_model_policy"] == "h10_governance_summary_only_no_dynamic_replay"


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


def test_shortpick_v2_paper_tracking_display_replays_since_start_with_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    assert payload["summary"]["record_count"] == 0
    assert payload["summary"]["true_forward_record_count"] == 0
    display = payload["paper_display"]
    assert display["latest_trade"]["title"] == "最新模拟交易"
    assert display["strategy_explanation"]["title"] == "策略说明"
    assert {chart["title"] for chart in display["charts"]} == {"覆盖情况", "动作分布"}
    assert [column["label"] for column in display["table"]["columns"]][:4] == [
        "信号日",
        "记录类型",
        "策略",
        "动作",
    ]
    assert {"退出状态", "退出日", "收益"} <= {column["label"] for column in display["table"]["columns"]}
    column_keys = [column["key"] for column in display["table"]["columns"]]
    assert column_keys.index("exit_state_text") < column_keys.index("exit_date_text") < column_keys.index("return_text")
    coverage = display["coverage"]
    assert coverage["coverage_start"] == "2026-05-08"
    assert coverage["coverage_end"] == "2026-06-15"
    assert coverage["latest_source_signal_date"] == "2026-06-15"
    assert "2026-05-08" in coverage["available_source_signal_dates"]
    assert coverage["row_or_gap_accounting_passed"] is True
    assert coverage["row_or_gap_config_accounting_passed"] is True
    assert coverage["available_source_signal_config_count"] == len(coverage["available_source_signal_dates"]) * 4
    assert payload["summary"]["replay_record_count"] == coverage["replay_row_count"]
    assert display["table"]["rows"]
    assert {row["tracking_tag"] for row in display["table"]["rows"]} == {"回放"}
    assert {"exit_state_text", "exit_date_text", "return_text"} <= set(display["table"]["rows"][0])
    assert {
        "8.5 万目标买入方案",
        "8 万目标买入方案",
        "8.5 万目标买入 H5 对照",
        "8.5 万目标买入 H5 止损对照",
    } <= {row["strategy_text"] for row in display["table"]["rows"]}
    account_curves = display["account_curves"]
    assert isinstance(account_curves, list)
    assert coverage["account_curve_count"] == len(account_curves)
    for curve in account_curves:
        assert curve["points"]
        assert curve["latest_nav"] == curve["points"][-1]["nav"]
        assert -1.0 < curve["max_drawdown"] <= 0.0
        assert "config_id" not in curve
        assert all("config_id" not in point for point in curve["points"])


def test_shortpick_v2_paper_display_uses_persistent_cache_after_cold_build(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-persistent-cache.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    with session_scope(database_url) as session:
        first_payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    cache_path = tmp_path / "shortpick-v2-paper-display-cache.json"
    assert cache_path.exists()
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache_payload["identity"]["cache_version"] == SHORTPICK_V2_PAPER_DISPLAY_CACHE_VERSION
    assert cache_payload["coverage"]["coverage_end"] == "2026-06-15"
    assert len(cache_payload["rows"]) == first_payload["paper_display"]["coverage"]["replay_row_count"]

    with shortpick_v2_read_model._paper_display_replay_cache_lock:
        shortpick_v2_read_model._paper_display_replay_cache.clear()

    import ashare_evidence.shortpick_ranked_pool_replay_input as replay_input

    def _fail_market_window_loader(*args, **kwargs):
        raise AssertionError("persistent cache hit must not rebuild the market replay window")

    monkeypatch.setattr(replay_input, "_load_daily_series_for_replay_window", _fail_market_window_loader)

    with session_scope(database_url) as session:
        second_payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    assert second_payload["paper_display"]["coverage"] == first_payload["paper_display"]["coverage"]
    assert second_payload["paper_display"]["table"]["rows"] == first_payload["paper_display"]["table"]["rows"]
    assert second_payload["paper_display"]["account_curves"] == first_payload["paper_display"]["account_curves"]


def test_shortpick_v2_paper_display_persistent_cache_misses_when_market_data_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-persistent-cache-miss.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    with session_scope(database_url) as session:
        build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    with shortpick_v2_read_model._paper_display_replay_cache_lock:
        shortpick_v2_read_model._paper_display_replay_cache.clear()

    with session_scope(database_url) as session:
        latest_bar = session.execute(
            select(MarketBar).where(MarketBar.timeframe == "1d").order_by(MarketBar.observed_at.desc()).limit(1)
        ).scalar_one()
        latest_bar.observed_at = latest_bar.observed_at + timedelta(minutes=1)

    import ashare_evidence.shortpick_ranked_pool_replay_input as replay_input

    real_window_loader = replay_input._load_daily_series_for_replay_window
    calls = {"count": 0}

    def _counting_window_loader(session, *, start_date: date, end_date: date):
        calls["count"] += 1
        return real_window_loader(session, start_date=start_date, end_date=end_date)

    monkeypatch.setattr(replay_input, "_load_daily_series_for_replay_window", _counting_window_loader)

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    assert calls["count"] == 1
    assert payload["paper_display"]["coverage"]["source_status"] == "ready"


def test_shortpick_v2_paper_display_ignores_corrupt_persistent_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-corrupt-cache.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)
    (tmp_path / "shortpick-v2-paper-display-cache.json").write_text("{not-json", encoding="utf-8")

    with shortpick_v2_read_model._paper_display_replay_cache_lock:
        shortpick_v2_read_model._paper_display_replay_cache.clear()

    import ashare_evidence.shortpick_ranked_pool_replay_input as replay_input

    real_window_loader = replay_input._load_daily_series_for_replay_window
    calls = {"count": 0}

    def _counting_window_loader(session, *, start_date: date, end_date: date):
        calls["count"] += 1
        return real_window_loader(session, start_date=start_date, end_date=end_date)

    monkeypatch.setattr(replay_input, "_load_daily_series_for_replay_window", _counting_window_loader)

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    assert calls["count"] == 1
    assert payload["paper_display"]["coverage"]["source_status"] == "ready"
    repaired_cache = json.loads((tmp_path / "shortpick-v2-paper-display-cache.json").read_text(encoding="utf-8"))
    assert repaired_cache["identity"]["cache_version"] == SHORTPICK_V2_PAPER_DISPLAY_CACHE_VERSION


def test_shortpick_v2_paper_display_buy_row_projects_exit_and_return() -> None:
    class _Bar:
        def __init__(self, day: date, close: float) -> None:
            self.day = day
            self.close = close

    class _Series:
        def __init__(self, bars: list[_Bar]) -> None:
            self.bars = bars
            self.by_day = {bar.day: index for index, bar in enumerate(bars)}

    trade_days = _business_days(date(2026, 5, 8), date(2026, 5, 29))
    bars = [_Bar(day, 10.0 + index) for index, day in enumerate(trade_days)]
    row = _paper_display_row_from_replay_decision(
        {
            "signal_date": "2026-05-08",
            "action": "buy_primary",
            "reason": "bought_primary",
            "selected_rank": 2,
            "symbol": "600001.SH",
            "cash_before": 200000.0,
            "cash_after": 150000.0,
            "quantity": 1000,
        },
        H10_QUIET_CHAMPION_CONFIG_ID,
        symbol_names={"600001.SH": "测试股票"},
        series_by_symbol={"600001.SH": _Series(bars)},
        trade_days=trade_days,
    )

    assert row["entry_date_text"] == "2026-05-11"
    assert row["exit_date_text"] == "2026-05-25"
    assert row["exit_state_text"] == "已按10日退出"
    assert row["exit_reason_text"] == "机械10日退出"
    assert row["return"] == 0.909091
    assert row["return_text"] == "+90.9%"


def test_shortpick_v2_paper_display_h5_row_projects_5_day_exit() -> None:
    class _Bar:
        def __init__(self, day: date, close: float) -> None:
            self.day = day
            self.close = close

    class _Series:
        def __init__(self, bars: list[_Bar]) -> None:
            self.bars = bars
            self.by_day = {bar.day: index for index, bar in enumerate(bars)}

    trade_days = _business_days(date(2026, 5, 8), date(2026, 5, 29))
    bars = [_Bar(day, 10.0 + index) for index, day in enumerate(trade_days)]
    row = _paper_display_row_from_replay_decision(
        {
            "signal_date": "2026-05-08",
            "action": "buy_primary",
            "reason": "bought_primary",
            "selected_rank": 2,
            "symbol": "600001.SH",
            "cash_before": 200000.0,
            "cash_after": 150000.0,
            "quantity": 1000,
        },
        SHORTPICK_V2_H5_OBSERVATION_CONFIG_ID,
        symbol_names={"600001.SH": "测试股票"},
        series_by_symbol={"600001.SH": _Series(bars)},
        trade_days=trade_days,
    )

    assert row["entry_date_text"] == "2026-05-11"
    assert row["exit_date_text"] == "2026-05-18"
    assert row["exit_state_text"] == "已按5日退出"
    assert row["exit_reason_text"] == "机械5日退出"
    assert row["holding_days_text"] == "5个交易日"


def test_shortpick_v2_paper_display_h5_stop8_row_projects_early_stop_loss() -> None:
    class _Bar:
        def __init__(self, day: date, close: float) -> None:
            self.day = day
            self.close = close

    class _Series:
        def __init__(self, bars: list[_Bar]) -> None:
            self.bars = bars
            self.by_day = {bar.day: index for index, bar in enumerate(bars)}

    trade_days = _business_days(date(2026, 5, 8), date(2026, 5, 29))
    closes = [10.0, 10.0, 9.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7]
    bars = [_Bar(day, closes[index] if index < len(closes) else 9.7) for index, day in enumerate(trade_days)]
    row = _paper_display_row_from_replay_decision(
        {
            "signal_date": "2026-05-08",
            "action": "buy_primary",
            "reason": "bought_primary",
            "selected_rank": 2,
            "symbol": "600001.SH",
            "cash_before": 200000.0,
            "cash_after": 150000.0,
            "quantity": 1000,
        },
        SHORTPICK_V2_H5_STOP8_OBSERVATION_CONFIG_ID,
        symbol_names={"600001.SH": "测试股票"},
        series_by_symbol={"600001.SH": _Series(bars)},
        trade_days=trade_days,
    )

    assert row["entry_date_text"] == "2026-05-11"
    assert row["exit_date_text"] == "2026-05-13"
    assert row["exit_state_text"] == "已止损退出"
    assert row["exit_reason_text"] == "止损退出"
    assert row["holding_days_text"] == "2个交易日"
    assert row["return"] == pytest.approx(-0.09)


def test_shortpick_v2_paper_account_curve_uses_account_nav_not_full_trade_compounding() -> None:
    class _Bar:
        def __init__(self, day: date, close: float) -> None:
            self.day = day
            self.close = close

    class _Series:
        def __init__(self, bars: list[_Bar]) -> None:
            self.bars = bars
            self.by_day = {bar.day: index for index, bar in enumerate(bars)}

    trade_days = _business_days(date(2026, 5, 11), date(2026, 5, 22))
    series = _Series([_Bar(day, 10.0 if index == 0 else 8.0) for index, day in enumerate(trade_days)])
    rows = [
        {
            "config_id": H10_QUIET_CHAMPION_CONFIG_ID,
            "strategy_text": "8.5 万目标买入方案",
            "action": "buy_primary",
            "symbol": "600001.SH",
            "quantity": 5000,
            "cash_before": 200000.0,
            "cash_after": 150000.0,
            "entry_date": "2026-05-11",
            "exit_date": "2026-05-13",
            "return": -0.2,
        },
        {
            "config_id": H10_QUIET_CHAMPION_CONFIG_ID,
            "strategy_text": "8.5 万目标买入方案",
            "action": "buy_primary",
            "symbol": "600001.SH",
            "quantity": 5000,
            "cash_before": 150000.0,
            "cash_after": 100000.0,
            "entry_date": "2026-05-12",
            "exit_date": "2026-05-14",
            "return": -0.2,
        },
    ]

    curves = _paper_display_account_curves_from_rows(
        rows,
        series_by_symbol={"600001.SH": series},
        trade_days=trade_days,
        initial_cash=200000.0,
    )

    assert len(curves) == 1
    wrong_full_trade_compounding = (1 - 0.2) * (1 - 0.2) - 1
    assert wrong_full_trade_compounding == pytest.approx(-0.36)
    assert curves[0]["max_drawdown"] == pytest.approx(-0.101)
    assert curves[0]["max_drawdown"] > wrong_full_trade_compounding
    assert curves[0]["latest_return"] == pytest.approx(-0.101)


def test_shortpick_v2_paper_account_curve_marks_open_position_drawdown() -> None:
    class _Bar:
        def __init__(self, day: date, close: float) -> None:
            self.day = day
            self.close = close

    class _Series:
        def __init__(self, bars: list[_Bar]) -> None:
            self.bars = bars
            self.by_day = {bar.day: index for index, bar in enumerate(bars)}

    trade_days = _business_days(date(2026, 5, 11), date(2026, 5, 15))
    series = _Series([
        _Bar(trade_days[0], 10.0),
        _Bar(trade_days[1], 4.0),
        _Bar(trade_days[2], 5.0),
        _Bar(trade_days[3], 6.0),
        _Bar(trade_days[4], 7.0),
    ])

    curves = _paper_display_account_curves_from_rows(
        [
            {
                "config_id": H10_QUIET_CHAMPION_CONFIG_ID,
                "strategy_text": "8.5 万目标买入方案",
                "action": "buy_primary",
                "symbol": "600001.SH",
                "quantity": 10000,
                "cash_before": 200000.0,
                "cash_after": 100000.0,
                "entry_date": "2026-05-11",
                "exit_date": None,
                "return": None,
            },
        ],
        series_by_symbol={"600001.SH": series},
        trade_days=trade_days,
        initial_cash=200000.0,
    )

    assert len(curves) == 1
    assert curves[0]["points"][1]["position_value"] == pytest.approx(40000.0)
    assert curves[0]["points"][1]["nav"] == pytest.approx(140000.0)
    assert curves[0]["max_drawdown"] == pytest.approx(-0.3)
    assert curves[0]["latest_return"] == pytest.approx(-0.15)
    assert curves[0]["completed_trade_count"] == 0


def test_shortpick_v2_paper_account_curve_releases_exit_cash_before_same_day_entry() -> None:
    class _Bar:
        def __init__(self, day: date, close: float) -> None:
            self.day = day
            self.close = close

    class _Series:
        def __init__(self, bars: list[_Bar]) -> None:
            self.bars = bars
            self.by_day = {bar.day: index for index, bar in enumerate(bars)}

    trade_days = _business_days(date(2026, 5, 11), date(2026, 5, 18))
    series_a = _Series([_Bar(day, 10.0) for day in trade_days])
    series_b = _Series([_Bar(day, 20.0) for day in trade_days])
    rows = [
        {
            "config_id": H10_QUIET_CHAMPION_CONFIG_ID,
            "strategy_text": "8.5 万目标买入方案",
            "action": "buy_primary",
            "symbol": "600001.SH",
            "quantity": 8500,
            "cash_before": 200000.0,
            "cash_after": 115000.0,
            "entry_date": trade_days[0].isoformat(),
            "exit_date": trade_days[2].isoformat(),
            "return": 0.0,
        },
        {
            "config_id": H10_QUIET_CHAMPION_CONFIG_ID,
            "strategy_text": "8.5 万目标买入方案",
            "action": "buy_primary",
            "symbol": "600002.SH",
            "quantity": 4000,
            "cash_before": 200000.0,
            "cash_after": 120000.0,
            "entry_date": trade_days[2].isoformat(),
            "exit_date": trade_days[4].isoformat(),
            "return": 0.0,
        },
    ]

    curves = _paper_display_account_curves_from_rows(
        rows,
        series_by_symbol={"600001.SH": series_a, "600002.SH": series_b},
        trade_days=trade_days,
        initial_cash=200000.0,
    )

    same_day_point = next(point for point in curves[0]["points"] if point["date"] == trade_days[2].isoformat())
    assert same_day_point["cash"] == pytest.approx(119787.5)
    assert same_day_point["cash"] >= 0
    assert same_day_point["open_position_count"] == 1


def test_shortpick_v2_paper_tracking_display_avoids_full_daily_series_loader(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-windowed.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    import ashare_evidence.shortpick_market_factor_study as market_factor_study
    import ashare_evidence.shortpick_ranked_pool_replay_input as replay_input
    import ashare_evidence.shortpick_v2_strategy_search as strategy_search

    def _fail_full_loader(*args, **kwargs):
        raise AssertionError("paper display must not load the full daily market table")

    monkeypatch.setattr(market_factor_study, "_load_daily_series", _fail_full_loader)
    real_window_loader = replay_input._load_daily_series_for_replay_window
    captured_window: dict[str, date] = {}

    def _capture_window_loader(session, *, start_date: date, end_date: date):
        captured_window["start_date"] = start_date
        captured_window["end_date"] = end_date
        return real_window_loader(session, start_date=start_date, end_date=end_date)

    monkeypatch.setattr(replay_input, "_load_daily_series_for_replay_window", _capture_window_loader)
    real_candidate_sources = strategy_search.build_h10_quiet_champion_strategy_search_candidate_sources
    captured_source_ids: list[tuple[str, ...] | None] = []

    def _capture_candidate_sources(*args, **kwargs):
        captured_source_ids.append(kwargs.get("source_ids"))
        return real_candidate_sources(*args, **kwargs)

    monkeypatch.setattr(
        strategy_search,
        "build_h10_quiet_champion_strategy_search_candidate_sources",
        _capture_candidate_sources,
    )

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    assert captured_window == {
        "start_date": date(2026, 5, 8) - timedelta(days=SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS),
        "end_date": date(2026, 6, 15),
    }
    assert captured_source_ids == [(SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID,)]
    coverage = payload["paper_display"]["coverage"]
    assert coverage["coverage_start"] == "2026-05-08"
    assert coverage["coverage_end"] == "2026-06-15"
    assert coverage["source_status"] != "replay_generation_error"
    assert coverage["row_or_gap_accounting_passed"] is True
    assert payload["paper_display"]["table"]["rows"]


def test_shortpick_v2_paper_tracking_window_loader_filters_market_bars_by_date(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "paper-display-window-filter.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    from ashare_evidence.shortpick_ranked_pool_replay_input import _load_daily_series_for_replay_window

    start = date(2026, 5, 8)
    end = date(2026, 5, 12)
    with session_scope(database_url) as session:
        series_by_symbol = _load_daily_series_for_replay_window(session, start_date=start, end_date=end)

    bar_days = {
        bar.day
        for series in series_by_symbol.values()
        for bar in series.bars
    }
    assert bar_days
    assert min(bar_days) >= start
    assert max(bar_days) <= end
    assert date(2026, 5, 7) not in bar_days
    assert date(2026, 5, 13) not in bar_days


def test_shortpick_v2_paper_tracking_display_uses_readable_chinese_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-readable.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    display = payload["paper_display"]
    visible_table_rows = [
        {
            "记录类型": row["tracking_tag"],
            "策略": row["strategy_text"],
            "动作": row["action_text"],
            "原因": row["reason_text"],
            "标的": row["stock_text"],
            "退出": row["exit_state_text"],
            "收益": row["return_text"],
            "说明": row["note"],
        }
        for row in display["table"]["rows"]
    ]
    visible_text = json.dumps(
        [
            display["latest_trade"],
            display["strategy_explanation"],
            display["charts"],
            display["table"]["columns"],
            visible_table_rows,
            display["table"]["rows"],
        ],
        ensure_ascii=False,
    )
    for forbidden in (
        "config_id",
        "decision_action",
        "buy_primary",
        "buy_fallback",
        "fixed_notional",
        "paper_tracking",
        "source_gap",
    ):
        assert forbidden not in visible_text
    assert "回放" in visible_text
    assert "不允许延迟买入" in visible_text


def test_shortpick_v2_paper_tracking_display_handles_missing_h10_source_as_gap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-missing-source.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    import ashare_evidence.shortpick_v2_strategy_search as strategy_search

    monkeypatch.setattr(
        strategy_search,
        "build_h10_quiet_champion_strategy_search_candidate_sources",
        lambda *args, **kwargs: (),
    )

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    coverage = payload["paper_display"]["coverage"]
    assert coverage["source_status"] == "missing_h10_replay_source"
    assert coverage["row_or_gap_accounting_passed"] is True
    assert coverage["source_gap_count"] > 0
    assert payload["summary"]["record_count"] == 0
    assert payload["paper_display"]["table"]["rows"][0]["action_text"] == "数据缺口"


def test_shortpick_v2_paper_tracking_display_not_limited_to_default_decision_samples(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-long-window.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url, end_date=date(2026, 8, 31))

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    coverage = payload["paper_display"]["coverage"]
    assert len(coverage["available_source_signal_dates"]) > 40
    assert coverage["coverage_end"] == "2026-08-31"
    assert coverage["row_or_gap_accounting_passed"] is True
    assert coverage["row_or_gap_config_accounting_passed"] is True
    assert coverage["available_source_signal_config_count"] == len(coverage["available_source_signal_dates"]) * 4


def test_shortpick_v2_paper_tracking_display_replay_error_does_not_break_read_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-display-error.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    import ashare_evidence.shortpick_v2_replay as replay

    def _raise_replay_error(*args, **kwargs):
        raise RuntimeError("fixture replay failure")

    monkeypatch.setattr(replay, "build_shortpick_v2_replay_artifact_from_series", _raise_replay_error)

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_tracking_read_model(include_records=True, session=session)

    coverage = payload["paper_display"]["coverage"]
    assert payload["status"] == "contract_ready"
    assert payload["summary"]["record_count"] == 0
    assert coverage["source_status"] == "replay_generation_error"
    assert payload["paper_display"]["table"]["rows"] == []


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
    assert payload["paper_display"]["coverage"]["true_forward_record_count"] == 1


def test_shortpick_v2_paper_tracking_rejects_ledger_records_before_tracking_start(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, ledger_path = _write_v2_artifacts(tmp_path, monkeypatch, replay=_qualified_replay_artifact())
    ledger = _valid_v2_paper_ledger(selection_path)
    ledger["records"][0]["record_id"] = "shortpick_v2:test:2026-05-07:conservative"
    ledger["records"][0]["signal_date"] = "2026-05-07"
    ledger["records"][0]["decision_date"] = "2026-05-07"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="signal_date must be on or after 2026-05-08"):
        build_shortpick_v2_paper_tracking_read_model(include_records=True)


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
    assert paper_response.json()["paper_display"]["table"]["rows"] == []
    assert paper_response.json()["paper_display"]["coverage"]["source_status"] == "summary_rows_omitted"


def test_shortpick_v2_paper_tracking_routes_skip_response_model_validation() -> None:
    app = create_app(enable_background_ops_tick=False)
    routes = {
        getattr(route, "path", ""): route
        for route in app.routes
        if getattr(route, "path", "").startswith("/shortpick-lab-v2/")
    }

    assert getattr(routes["/shortpick-lab-v2/paper-tracking"], "response_model", None) is None
    assert getattr(routes["/shortpick-lab-v2/paper-tracking/summary"], "response_model", None) is None
    assert getattr(routes["/shortpick-lab-v2/historical-replay"], "response_model", None) is not None


def test_shortpick_v2_read_api_full_paper_tracking_returns_display_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_v2_artifacts(tmp_path, monkeypatch)
    _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "api-full-paper.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url)

    client = TestClient(create_app(database_url, enable_background_ops_tick=False))
    response = client.get("/shortpick-lab-v2/paper-tracking")

    assert response.status_code == 200
    body = response.json()
    assert body["records"] == []
    rows = body["paper_display"]["table"]["rows"]
    assert rows
    assert {row["tracking_tag"] for row in rows} == {"回放"}
    assert body["paper_display"]["coverage"]["coverage_start"] == "2026-05-08"
    assert body["paper_display"]["coverage"]["row_or_gap_config_accounting_passed"] is True


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
    assert body["paper_display"]["table"]["rows"] == []
    assert body["paper_display"]["coverage"]["source_status"] == "summary_rows_omitted"
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
