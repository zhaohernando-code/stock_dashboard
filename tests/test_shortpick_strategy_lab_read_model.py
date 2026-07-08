from __future__ import annotations

import json
from datetime import date

from ashare_evidence.shortpick_strategy_lab_read_model import (
    CONTROL_CONFIG_ID,
    MAIN_CONFIG_ID,
    PAPER_STATE_SCHEMA_VERSION,
    build_shortpick_strategy_lab_historical_replay_read_model,
    build_shortpick_strategy_lab_paper_tracking_read_model,
)


def test_historical_replay_is_static_full_history_metrics() -> None:
    payload = build_shortpick_strategy_lab_historical_replay_read_model()

    assert payload["status"] == "ready"
    assert payload["evidence_basis"] == "static_full_history_account_replay"
    assert payload["data_scope"]["static_read_model"] is True
    assert payload["summary"]["main_total_return"] == 2.9891730075000016
    assert payload["summary"]["main_negative_month_count"] == 4
    assert payload["selected_configs"][0]["config_id"] == MAIN_CONFIG_ID
    assert payload["baseline_configs"][0]["config_id"] == CONTROL_CONFIG_ID
    assert payload["metric_groups"]
    assert payload["leakage_audit"]["read_model_policy"] == "static_metrics_only_no_market_scan_no_dynamic_replay"


def test_paper_tracking_renders_mock_next_order_without_forward_records(tmp_path) -> None:
    state_path = tmp_path / "shortpick-strategy-lab-paper-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": PAPER_STATE_SCHEMA_VERSION,
                "tracking_start_date": "2026-07-08",
                "records": [],
                "planned_orders": [
                    {
                        "strategy_id": MAIN_CONFIG_ID,
                        "strategy_label": "主策略：14 tranche 分层退出",
                        "signal_date": "2026-07-08",
                        "planned_entry_date": "2026-07-09",
                        "symbol": "002371.SZ",
                        "name": "北方华创",
                        "shares": 100,
                        "entry_timing": "次日收盘",
                        "estimated_notional_cny": 12750.0,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_shortpick_strategy_lab_paper_tracking_read_model(
        paper_state_path=state_path,
        today=date(2026, 7, 8),
    )

    assert payload["summary"]["record_count"] == 0
    assert payload["summary"]["planned_order_count"] == 1
    assert payload["paper_display"]["account_curves"] == []
    assert payload["paper_display"]["charts"] == []
    assert payload["paper_display"]["table"]["rows"] == []
    latest_trade = payload["paper_display"]["latest_trade"]
    assert latest_trade["tag"] == "待执行"
    assert "北方华创" in latest_trade["summary"]
    assert "买 100 股" in latest_trade["summary"]
    assert "次日收盘" in latest_trade["summary"]
