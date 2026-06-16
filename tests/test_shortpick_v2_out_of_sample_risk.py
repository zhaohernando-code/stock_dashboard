from __future__ import annotations

import json
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_out_of_sample_risk import (
    ARTIFACT_FAMILY,
    _window_diagnostic,
    render_shortpick_v2_out_of_sample_risk_markdown,
    validate_shortpick_v2_out_of_sample_risk_payload,
)


def test_out_of_sample_risk_window_diagnostic_marks_extreme_drawdown() -> None:
    timeline = [
        {"date": "2026-01-01", "nav": 100.0},
        {"date": "2026-01-02", "nav": 110.0},
        {"date": "2026-01-03", "nav": 108.0},
        {"date": "2026-01-04", "nav": 112.0},
        {"date": "2026-01-05", "nav": 111.0},
        {"date": "2026-01-06", "nav": 109.0},
    ]

    diagnostic = _window_diagnostic(timeline, window_size=3, observed_paper_max_drawdown=-0.15)

    assert diagnostic["historical_window_count"] == 4
    assert diagnostic["equal_or_worse_historical_window_count"] == 0
    assert diagnostic["rarity_label_cn"] == "历史极少见"


def test_out_of_sample_risk_payload_validation_and_summary() -> None:
    payload = _payload()

    validation = validate_shortpick_v2_out_of_sample_risk_payload(payload)
    markdown = render_shortpick_v2_out_of_sample_risk_markdown(payload)

    assert validation["status"] == "passed"
    assert validation["artifact_summary"]["interpretation_status"] == "sample_out_pressure_unusual"
    assert "# 试验田 v2 样本外回撤压力诊断" in markdown
    assert "风险治理诊断" in markdown


def test_out_of_sample_risk_validate_cli_parser_and_main_output(tmp_path: Path, capsys) -> None:
    artifact_path = tmp_path / "risk.json"
    artifact_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

    assert "shortpick-v2-out-of-sample-risk-validate" in cli_module.NO_DB_COMMANDS
    args = cli_module.build_parser().parse_args(
        ["shortpick-v2-out-of-sample-risk-validate", "--artifact", str(artifact_path)]
    )
    assert args.artifact == str(artifact_path)

    exit_code = cli_module.main(["shortpick-v2-out-of-sample-risk-validate", "--artifact", str(artifact_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["artifact_summary"]["observed_paper_max_drawdown"] == -0.175


def _payload() -> dict[str, object]:
    return {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_out_of_sample_risk_diagnostic:test",
        "generated_at": "2026-06-16T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_rolling_window_vs_current_paper_pressure",
        "analysis_scope": {
            "strategy_id": "h10_quiet_rank2_primary_poolhot10_mtw_drawdown_off__fixed_notional_85k_top5_h10_v1",
            "strategy_label_cn": "安静突破 Rank2 + 热度池 10% + 周一至周三 + H10 + 8.5 万目标买入",
            "historical_start_date": "2023-04-13",
            "historical_end_date": "2026-05-08",
            "paper_start_date": "2026-05-08",
            "paper_end_date": "2026-06-15",
            "observed_paper_max_drawdown": -0.175,
            "window_sizes_trade_days": [25],
            "promotion_status": "risk_warning_only_no_strategy_replacement",
        },
        "data_scope": {"signal_day_count": 10, "trade_day_count": 30, "timeline_point_count": 30},
        "historical_replay_summary": {"total_return": 2.712, "max_drawdown": -0.119},
        "rolling_window_diagnostics": [
            {
                "window_size_trade_days": 25,
                "historical_window_count": 100,
                "observed_paper_max_drawdown": -0.175,
                "equal_or_worse_historical_window_count": 3,
                "equal_or_worse_historical_window_ratio": 0.03,
                "rarity_label_cn": "历史偏少见",
                "drawdown_distribution": {
                    "min": -0.22,
                    "p05": -0.16,
                    "p10": -0.12,
                    "p25": -0.08,
                    "median": -0.04,
                    "p75": -0.02,
                    "max": 0.0,
                },
                "worst_windows": [],
            }
        ],
        "index_window_diagnostics": [],
        "interpretation": {
            "status": "sample_out_pressure_unusual",
            "observed_paper_max_drawdown": -0.175,
            "minimum_equal_or_worse_historical_window_ratio": 0.03,
            "message_cn": "当前纸面回撤偏少见，需要风险预警。",
        },
        "leakage_audit": {"status": "passed"},
        "event_refs": ["shortpick_v2.out_of_sample_risk_diagnostic.generated"],
    }
