from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_industry_theme_experiment import (
    ARTIFACT_FAMILY,
    VARIANTS,
    _comparison,
    render_shortpick_v2_industry_theme_experiment_markdown,
    validate_shortpick_v2_industry_theme_experiment_artifact,
    validate_shortpick_v2_industry_theme_experiment_payload,
    write_shortpick_v2_industry_theme_experiment_artifact,
)


def test_industry_theme_payload_validation_and_summary() -> None:
    payload = _payload()

    validation = validate_shortpick_v2_industry_theme_experiment_payload(payload)
    markdown = render_shortpick_v2_industry_theme_experiment_markdown(payload)

    assert validation["status"] == "passed"
    assert validation["artifact_summary"]["future_research_variant_ids"] == []
    assert "# 试验田 v2 行业主线实验" in markdown
    assert "实际数据截止日：2026-06-17" in markdown
    assert "不晋级或替换纸面追踪策略" in markdown


def test_industry_theme_validator_rejects_promoted_payload() -> None:
    payload = _payload()
    payload["analysis_scope"]["promotion_status"] = "promoted_to_paper_tracking"

    validation = validate_shortpick_v2_industry_theme_experiment_payload(payload)

    assert validation["status"] == "failed"
    assert any(check["check_id"] == "research_only" and not check["passed"] for check in validation["checks"])


def test_industry_theme_comparison_keeps_future_research_separate_from_candidates() -> None:
    rows = []
    capture_rows = []
    for variant in VARIANTS:
        for window_id in ("holdout", "paper"):
            rows.append(
                {
                    "window_id": window_id,
                    "variant_id": variant.variant_id,
                    "label_cn": variant.label_cn,
                    "variant_group": variant.variant_group,
                    "total_return": 0.20,
                    "max_drawdown": -0.10,
                }
            )
        capture_rows.append(
            {
                "variant_id": variant.variant_id,
                "label_cn": variant.label_cn,
                "top5_hit_rate": 0.10,
            }
        )
    for row in rows:
        if row["variant_id"] == "theme_breadth_pullback_rank2_mtw" and row["window_id"] == "holdout":
            row["total_return"] = 0.35
            row["max_drawdown"] = -0.12
        if row["variant_id"] == "theme_breadth_pullback_rank2_mtw" and row["window_id"] == "paper":
            row["total_return"] = 0.25
    for row in capture_rows:
        if row["variant_id"] == "theme_breadth_pullback_rank2_mtw":
            row["top5_hit_rate"] = 0.16

    comparison = _comparison(
        rows,
        capture_rows=capture_rows,
        min_holdout_return_delta=0.10,
        max_holdout_drawdown_worsening=-0.05,
    )

    assert comparison["candidate_variant_ids"] == []
    assert comparison["future_research_variant_ids"] == ["theme_breadth_pullback_rank2_mtw"]


def test_industry_theme_comparison_rejects_paper_only_improvement_when_holdout_is_weak() -> None:
    rows = []
    capture_rows = []
    for variant in VARIANTS:
        for window_id in ("holdout", "paper"):
            rows.append(
                {
                    "window_id": window_id,
                    "variant_id": variant.variant_id,
                    "label_cn": variant.label_cn,
                    "variant_group": variant.variant_group,
                    "total_return": 0.20,
                    "max_drawdown": -0.10,
                }
            )
        capture_rows.append({"variant_id": variant.variant_id, "label_cn": variant.label_cn, "top5_hit_rate": 0.10})
    for row in rows:
        if row["variant_id"] == "theme_breakout_cluster_rank2_mtw" and row["window_id"] == "holdout":
            row["total_return"] = -0.30
            row["max_drawdown"] = -0.45
        if row["variant_id"] == "theme_breakout_cluster_rank2_mtw" and row["window_id"] == "paper":
            row["total_return"] = 0.45
    for row in capture_rows:
        if row["variant_id"] == "theme_breakout_cluster_rank2_mtw":
            row["top5_hit_rate"] = 0.18

    comparison = _comparison(
        rows,
        capture_rows=capture_rows,
        min_holdout_return_delta=0.10,
        max_holdout_drawdown_worsening=-0.05,
    )
    verdict = next(
        row["verdict_cn"]
        for row in comparison["delta_rows"]
        if row["variant_id"] == "theme_breakout_cluster_rank2_mtw"
    )

    assert comparison["candidate_variant_ids"] == []
    assert "theme_breakout_cluster_rank2_mtw" not in comparison["future_research_variant_ids"]
    assert verdict == "强势股捕捉改善，但样本外收益不足"


def test_industry_theme_validate_cli_parser_and_main_output(tmp_path: Path, capsys) -> None:
    artifact_path = write_shortpick_v2_industry_theme_experiment_artifact(
        _payload(),
        output_path=tmp_path / "industry-theme.json",
    )["artifact"]

    assert "shortpick-v2-industry-theme-experiment-validate" in cli_module.NO_DB_COMMANDS
    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-industry-theme-experiment",
            "--paper-end-date",
            "2026-06-17",
            "--output",
            str(tmp_path / "generated.json"),
        ]
    )
    assert args.command == "shortpick-v2-industry-theme-experiment"
    assert args.paper_end_date == "2026-06-17"
    assert args.output == str(tmp_path / "generated.json")

    exit_code = cli_module.main(
        [
            "shortpick-v2-industry-theme-experiment-validate",
            "--artifact",
            str(artifact_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["artifact_summary"]["artifact_family"] == ARTIFACT_FAMILY

    direct_validation = validate_shortpick_v2_industry_theme_experiment_artifact(artifact_path=artifact_path)
    assert direct_validation["status"] == "passed"


def _payload() -> dict[str, object]:
    rows = []
    for variant in VARIANTS:
        for window_id in ("train", "holdout", "historical_all", "paper"):
            rows.append(
                {
                    "window_id": window_id,
                    "window_label_cn": window_id,
                    "window_start_date": "2023-04-13",
                    "window_end_date": "2026-06-17",
                    "variant_id": variant.variant_id,
                    "label_cn": variant.label_cn,
                    "source_id": variant.source_id,
                    "variant_group": variant.variant_group,
                    "description_cn": variant.description_cn,
                    "total_return": 0.20,
                    "annualized_return": 0.15,
                    "market_excess_total_return": 0.10,
                    "max_drawdown": -0.10,
                    "trade_count": 10,
                    "skipped_ratio": 0.20,
                    "meets_min_annualized_return": False,
                    "beats_market_reference": True,
                    "drawdown_within_limit": True,
                    "meets_user_floor": False,
                }
            )
    variant_rows = [
        {
            "variant_id": variant.variant_id,
            "label_cn": variant.label_cn,
            "variant_group": variant.variant_group,
            "top5_hit_count": 5,
            "top5_hit_rate": 0.10,
            "pre_launch_top5_hit_count": 2,
            "pre_launch_top5_hit_rate": 0.04,
            "top5_hit_rate_delta_vs_baseline": 0.0,
        }
        for variant in VARIANTS
    ]
    return {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_industry_theme_experiment:test",
        "generated_at": datetime(2026, 6, 18, 6, 0, tzinfo=UTC).isoformat(),
        "status": "ready",
        "claim_ceiling": "research_observation",
        "source_ref": "test",
        "analysis_scope": {
            "question_cn": "test",
            "historical_start_date": "2023-04-13",
            "train_end_date": "2025-04-30",
            "holdout_start_date": "2025-05-01",
            "historical_end_date": "2026-05-08",
            "paper_start_date": "2026-05-08",
            "paper_end_date": "2026-06-17",
            "actual_cutoff_date": "2026-06-17",
            "current_month_start_date": "2026-06-01",
            "weekday_mode": "mtw",
            "horizon_days": 10,
            "initial_cash": 200000.0,
            "target_notional": 85000.0,
            "entry_price_source": "next_close",
            "promotion_status": "research_only_no_strategy_promotion",
        },
        "data_scope": {"stock_like_series_count": 100, "signal_day_count": 200, "trade_day_count": 200},
        "prior_evidence_inventory": {"known_dead_ends": ["simple_industry_10d_average_heat_as_candidate"]},
        "variant_definitions": [
            {
                "variant_id": variant.variant_id,
                "label_cn": variant.label_cn,
                "source_id": variant.source_id,
                "description_cn": variant.description_cn,
                "variant_group": variant.variant_group,
            }
            for variant in VARIANTS
        ],
        "result_rows": rows,
        "strong_stock_capture": {
            "top_winner_count": 50,
            "paper_signal_day_count": 20,
            "eligible_universe_hit_count": 49,
            "eligible_universe_hit_rate": 0.98,
            "top_industries": [],
            "variant_rows": variant_rows,
        },
        "comparison": {
            "baseline_variant_id": "baseline_quiet_rank2_mtw",
            "candidate_variant_ids": [],
            "future_research_variant_ids": [],
            "thresholds": {},
            "delta_rows": [],
        },
        "interpretation": {
            "status": "no_theme_variant_promoted",
            "message_cn": "本轮没有通过门槛。",
            "recommended_next_steps_cn": ["不要进入纸面候选。"],
        },
        "leakage_audit": {"status": "passed", "notes": []},
        "event_refs": ["shortpick_v2.industry_theme_experiment.generated"],
    }
