from __future__ import annotations

from ashare_evidence.personal_execution_snapshot import build_personal_eligible_execution_snapshot
from ashare_evidence.rolling_account_execution_snapshot import build_rolling_account_execution_snapshot
from ashare_evidence.rolling_tranche_account_replay import build_shortpick_v3_rolling_account_replay_artifact
from ashare_evidence.rolling_tranche_execution_contract import build_shortpick_v3_rolling_tranche_execution_contract


def test_personal_snapshot_filters_before_ranking_and_promotes_next_main_board_pick() -> None:
    day = "2026-01-02"
    bars = {
        "600001.SH": [{"day": day, "close": 250.0}, {"day": "2026-01-05", "close": 251.0}],
        "300001.SZ": [{"day": day, "close": 10.0}, {"day": "2026-01-05", "close": 10.1}],
        "600002.SH": [{"day": day, "close": 10.0}, {"day": "2026-01-05", "close": 10.1}],
        "600003.SH": [{"day": day, "close": 11.0}, {"day": "2026-01-05", "close": 11.1}],
    }
    picks = [
        {"as_of_date": day, "symbol": symbol, "rank": rank, "stock_name": symbol,
         "portfolio_weight": 1.0, "rank_weight_multiplier": 1.0, "target_horizon_days": 1}
        for rank, symbol in enumerate(bars, start=1)
    ]
    candidate_run = {"artifact_id": "candidate", "trial_diagnostics": [{
        "trial_id": "trial", "model_spec_id": "model", "selected_top_k": 2,
        "selected_top_k_picks_by_date": picks[:2],
    }]}
    config = build_shortpick_v3_rolling_tranche_execution_contract(model_spec_id="model")[
        "candidate_configurations"
    ][0]
    profile = {"initial_cash_cny": 200000.0, "buy_cost_bps": 0.0, "sell_cost_bps": 0.0,
               "min_order_notional_cny": 250.0, "max_entry_lag_days": 7}
    baseline = build_shortpick_v3_rolling_account_replay_artifact(
        candidate_run=candidate_run, trial_id="trial", market_bars_by_symbol=bars,
        candidate_inventory_rows=picks, candidate_configurations=[config], **profile,
    )["results"][0]
    source = build_rolling_account_execution_snapshot(
        candidate_run=candidate_run, trial_id="trial", candidate_inventory_rows=picks,
        market_bars_by_symbol=bars, baseline_config=config, account_profile=profile,
        baseline_result=baseline, source_lineage={},
    )

    snapshot, audit = build_personal_eligible_execution_snapshot(source)
    selected = snapshot["inputs"]["candidate_run"]["trial_diagnostics"][0]["selected_top_k_picks_by_date"]

    assert [row["symbol"] for row in selected] == ["600002.SH", "600003.SH"]
    assert [row["rank"] for row in selected] == [1, 2]
    assert audit["exclusion_reason_counts"] == {
        "account_board_permission_required": 1,
        "price_above_profile_maximum": 1,
    }
    assert audit["filter_stage"] == "before_strategy_scoring_and_ranking"
