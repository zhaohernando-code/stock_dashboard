from __future__ import annotations

import json
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_ranking_backtest import (
    ARTIFACT_FAMILY,
    RANKING_VARIANTS,
    validate_shortpick_v2_ranking_backtest_payload,
)


def test_ranking_backtest_validate_cli_is_no_db() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-ranking-backtest-validate", "--artifact", "x.json"])

    assert args.command == "shortpick-v2-ranking-backtest-validate"
    assert "shortpick-v2-ranking-backtest-validate" in cli_module.NO_DB_COMMANDS


def test_ranking_backtest_payload_keeps_research_only_contract(tmp_path: Path) -> None:
    payload = _payload()
    artifact_path = tmp_path / "ranking.json"
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    validation = validate_shortpick_v2_ranking_backtest_payload(payload)

    assert validation["status"] == "passed"
    assert validation["artifact_summary"]["artifact_family"] == ARTIFACT_FAMILY


def _payload() -> dict[str, object]:
    rows = []
    for variant in RANKING_VARIANTS:
        for window_id in ("train", "holdout", "historical_all", "paper"):
            rows.append(
                {
                    "window_id": window_id,
                    "window_label_cn": window_id,
                    "window_start_date": "2023-04-13",
                    "window_end_date": "2026-06-16",
                    "variant_id": variant.variant_id,
                    "label_cn": variant.label_cn,
                    "source_id": variant.source_id,
                    "description_cn": variant.description_cn,
                    "total_return": 0.20,
                    "annualized_return": 0.15,
                    "market_excess_total_return": 0.10,
                    "max_drawdown": -0.10,
                    "trade_count": 10,
                    "skipped_ratio": 0.20,
                    "meets_user_floor": False,
                }
            )
    return {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": "v1",
        "claim_ceiling": "research_observation",
        "analysis_scope": {"promotion_status": "research_only_no_strategy_promotion"},
        "variant_definitions": [],
        "result_rows": rows,
        "comparison": {"candidate_variant_ids": [], "delta_rows": []},
        "interpretation": {"status": "no_ranking_variant_promoted"},
        "leakage_audit": {"status": "passed"},
    }
