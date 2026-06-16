from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_paper_divergence_attribution import (
    H10_QUIET_CHAMPION_CONFIG_ID,
    V1_DERIVED_CONTROL_ID,
    AccountSimulationConfig,
    PaperCandidateObservation,
    build_shortpick_paper_divergence_attribution_artifact_from_inputs,
    simulate_candidate_account,
    validate_shortpick_paper_divergence_attribution_artifact,
    write_shortpick_paper_divergence_attribution_artifact,
)


def test_v1_derived_account_skips_when_board_lot_is_unaffordable() -> None:
    result = simulate_candidate_account(
        [
            PaperCandidateObservation(
                signal_date=date(2026, 5, 8),
                symbol="600001.SH",
                name="高价股",
                source_rank=1,
                entry_date=date(2026, 5, 11),
                exit_date=date(2026, 5, 25),
                entry_price=2500.0,
                exit_price=2600.0,
                stock_return=0.04,
            )
        ],
        config=AccountSimulationConfig(
            strategy_id=V1_DERIVED_CONTROL_ID,
            label_cn="v1 20w",
            initial_cash=200_000.0,
            target_notional=200_000.0,
            fallback_enabled=False,
        ),
    )

    assert result["summary"]["trade_count"] == 0
    assert result["summary"]["skip_count"] == 1
    assert result["reason_counts"]["reason:board_lot_minimum"] == 1


def test_v1_derived_account_uses_top1_or_skip_without_fallback_or_delay() -> None:
    result = simulate_candidate_account(
        [
            PaperCandidateObservation(
                signal_date=date(2026, 5, 8),
                symbol="600001.SH",
                name="高价股",
                source_rank=1,
                entry_date=date(2026, 5, 11),
                exit_date=date(2026, 5, 25),
                entry_price=2500.0,
                exit_price=2600.0,
                stock_return=0.04,
            ),
            PaperCandidateObservation(
                signal_date=date(2026, 5, 8),
                symbol="600002.SH",
                name="候补股",
                source_rank=2,
                entry_date=date(2026, 5, 11),
                exit_date=date(2026, 5, 25),
                entry_price=10.0,
                exit_price=11.0,
                stock_return=0.1,
            ),
        ],
        config=AccountSimulationConfig(
            strategy_id=V1_DERIVED_CONTROL_ID,
            label_cn="v1 20w",
            initial_cash=200_000.0,
            target_notional=200_000.0,
            fallback_enabled=False,
        ),
    )

    assert result["summary"]["trade_count"] == 0
    assert result["summary"]["fallback_trade_count"] == 0
    assert all("delay" not in sample["action"] for sample in result["decision_samples"])


def test_v1_derived_account_buys_affordable_rank1_in_board_lots() -> None:
    result = simulate_candidate_account(
        [
            PaperCandidateObservation(
                signal_date=date(2026, 5, 8),
                symbol="600006.SH",
                name="可买股",
                source_rank=1,
                entry_date=date(2026, 5, 11),
                exit_date=date(2026, 5, 25),
                entry_price=20.0,
                exit_price=22.0,
                stock_return=0.1,
            )
        ],
        config=AccountSimulationConfig(
            strategy_id=V1_DERIVED_CONTROL_ID,
            label_cn="v1 20w",
            initial_cash=200_000.0,
            target_notional=200_000.0,
            fallback_enabled=False,
        ),
    )

    assert result["summary"]["trade_count"] == 1
    assert result["summary"]["completed_trade_count"] == 1
    assert result["summary"]["skip_count"] == 0
    assert result["decision_samples"][0]["action"] == "buy_primary"
    assert result["decision_samples"][0]["quantity"] == 10000
    assert result["summary"]["total_return"] == 0.1


def test_artifact_separates_v1_raw_observations_from_derived_account() -> None:
    artifact = build_shortpick_paper_divergence_attribution_artifact_from_inputs(
        v1_observations=[
            PaperCandidateObservation(
                signal_date=date(2026, 5, 8),
                symbol="600003.SH",
                name="样本股",
                source_rank=1,
                entry_date=date(2026, 5, 11),
                exit_date=date(2026, 5, 25),
                entry_price=20.0,
                exit_price=22.0,
                stock_return=0.1,
            )
        ],
        v2_read_model=_v2_read_model(),
        start_date=date(2026, 5, 8),
        initial_cash=200_000.0,
        generated_at=datetime(2026, 6, 16, 10, 0, tzinfo=UTC),
    )

    by_id = {row["strategy_id"]: row for row in artifact["strategies"]}
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["account_constraints"]["delayed_buy_allowed"] is False
    assert by_id["v1_raw_candidate_forward_h10"]["source_kind"] == "v1_candidate_forward_return_not_account_nav"
    assert by_id[V1_DERIVED_CONTROL_ID]["source_kind"] == "derived_v1_200k_account_control"
    assert by_id[H10_QUIET_CHAMPION_CONFIG_ID]["summary"]["total_return"] == -0.08
    assert by_id[H10_QUIET_CHAMPION_CONFIG_ID]["summary"]["cash_or_lot_rejection_count"] is None
    assert artifact["validation_status"] == "passed"


def test_artifact_write_validate_and_cli_parser(tmp_path: Path) -> None:
    artifact = build_shortpick_paper_divergence_attribution_artifact_from_inputs(
        v1_observations=[],
        v2_read_model=_v2_read_model(),
        generated_at=datetime(2026, 6, 16, 10, 30, tzinfo=UTC),
    )
    paths = write_shortpick_paper_divergence_attribution_artifact(
        artifact,
        output_path=tmp_path / "paper-divergence.json",
        summary_path=tmp_path / "paper-divergence.md",
    )

    validation = validate_shortpick_paper_divergence_attribution_artifact(artifact_path=paths["artifact"])

    assert validation["status"] == "passed"
    assert paths["summary"].read_text(encoding="utf-8").startswith("# 试验田 v1/v2 纸面分歧归因")
    assert "shortpick-paper-divergence-attribution-validate" in cli_module.NO_DB_COMMANDS
    args = cli_module.build_parser().parse_args(
        [
            "shortpick-paper-divergence-attribution",
            "--start-date",
            "2026-05-08",
            "--initial-cash",
            "200000",
            "--output",
            str(tmp_path / "out.json"),
            "--summary-output",
            str(tmp_path / "out.md"),
        ]
    )
    assert args.start_date == "2026-05-08"
    validate_args = cli_module.build_parser().parse_args(
        ["shortpick-paper-divergence-attribution-validate", "--artifact", str(paths["artifact"])]
    )
    assert validate_args.artifact == str(paths["artifact"])


def _v2_read_model() -> dict[str, object]:
    return {
        "summary": {"latest_paper_display_signal_date": "2026-06-15"},
        "paper_display": {
            "account_curves": [
                {
                    "strategy": "8.5 万目标买入方案",
                    "initial_cash": 200_000.0,
                    "latest_nav": 184_000.0,
                    "latest_return": -0.08,
                    "max_drawdown": -0.12,
                    "completed_trade_count": 3,
                    "points": [{"date": "2026-06-15", "account_return": -0.08}],
                },
                {
                    "strategy": "8 万目标买入方案",
                    "initial_cash": 200_000.0,
                    "latest_nav": 186_000.0,
                    "latest_return": -0.07,
                    "max_drawdown": -0.11,
                    "completed_trade_count": 3,
                    "points": [{"date": "2026-06-15", "account_return": -0.07}],
                },
            ],
            "table": {
                "rows": [
                    {"strategy_text": "8.5 万目标买入方案", "action_text": "买入首选"},
                    {"strategy_text": "8.5 万目标买入方案", "action_text": "买入候补"},
                    {"strategy_text": "8.5 万目标买入方案", "action_text": "不买入"},
                ]
            },
        },
    }
