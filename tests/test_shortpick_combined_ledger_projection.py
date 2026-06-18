from __future__ import annotations

from ashare_evidence.api import _shortpick_combined_ledger_projection
from ashare_evidence.shortpick_combined_ledger_writer import run_shortpick_combined_ledger_backfill_artifact
from ashare_evidence.shortpick_strategy_governance import build_shortpick_same_symbol_cooldown_rule


def test_combined_ledger_projection_prefers_latest_duplicate_artifact_row() -> None:
    row_id = "shortpick-combined-ledger-retrospective:duplicate"
    old_row = {
        "combined_ledger_row_id": row_id,
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "symbol": "600183.SH",
        "signal_date": "2026-06-02",
        "combined_ledger_materialized_at": "2026-06-11T15:20:00+08:00",
        "validation_by_horizon": [{"horizon_days": 10, "status": "pending_forward_window"}],
    }
    new_row = {
        **old_row,
        "combined_ledger_materialized_at": "2026-06-17T18:00:00+08:00",
        "validation_by_horizon": [
            {
                "horizon_days": 10,
                "status": "completed",
                "exit_date": "2026-06-17",
                "stock_return": 0.276845,
            }
        ],
    }

    payload = _shortpick_combined_ledger_projection(
        {
            "artifacts": [
                {
                    "artifact_id": "shortpick-combined-ledger-backfill:old",
                    "generated_at": "2026-06-11T15:20:00+08:00",
                    "combined_rows": [old_row],
                },
                {
                    "artifact_id": "shortpick-combined-ledger-backfill:new",
                    "generated_at": "2026-06-17T18:00:00+08:00",
                    "combined_rows": [new_row],
                },
            ]
        }
    )

    assert payload["combined_row_count"] == 1
    assert payload["duplicate_row_count"] == 1
    assert payload["rows"][0]["source_combined_ledger_artifact_id"] == "shortpick-combined-ledger-backfill:new"
    assert payload["rows"][0]["validation_by_horizon"][0]["status"] == "completed"


def test_combined_ledger_backfill_writer_defaults_generated_at() -> None:
    rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
    replay = {
        "artifact_id": "shortpick-retrospective-forward-replay:test",
        "artifact_type": "shortpick_retrospective_forward_replay",
        "status": "ready",
        "evidence_basis": "retrospective_forward_replay",
        "retrospective": True,
        "selection_policy": "filter_ranked_pool_select_first_allowed",
        "paper_tracking_write_policy": "forbidden",
        "request": {
            "control_group_id": rule["control_group_id"],
            "rule_signature": rule["rule_signature"],
            "rule_defined_at": "2026-06-10",
        },
        "rows": [
            {
                "candidate_id": "retrospective-row",
                "signal_date": "2026-05-20",
                "symbol": "002028.SZ",
                "control_group_id": rule["control_group_id"],
                "rule_signature": rule["rule_signature"],
                "rule_defined_at": "2026-06-10",
                "leakage_audit_status": "passed",
            }
        ],
    }

    artifact = run_shortpick_combined_ledger_backfill_artifact([replay])

    assert artifact["generated_at"]
    assert artifact["retrospective_rows"][0]["combined_ledger_materialized_at"] == artifact["generated_at"]
