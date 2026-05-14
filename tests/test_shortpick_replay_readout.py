from ashare_evidence.shortpick_replay_readout import build_shortpick_replay_decision_projection


def _replay_feedback():
    return {
        "overall": {
            "validation_count": 400,
            "completed_official_sample_count": 96,
            "completed_tradable_sample_count": 244,
            "statistical_gate": {"status": "ready"},
            "validation_by_horizon": [
                {"group_key": "5", "status_counts": {"entry_unfillable_limit_up": 3}},
                {"group_key": "10", "status_counts": {"entry_unfillable_limit_up": 2}},
            ],
        },
        "families": [
            {
                "baseline_family": "llm",
                "validation_by_horizon": [
                    {
                        "group_key": "5",
                        "tradable_mean_excess_return": 0.012,
                        "completed_tradable_sample_count": 244,
                    }
                ],
            },
            {
                "baseline_family": "momentum_10d_turnover_cooldown_rank",
                "validation_by_horizon": [
                    {
                        "group_key": "5",
                        "tradable_mean_excess_return": 0.018,
                        "completed_tradable_sample_count": 306,
                    }
                ],
            },
        ],
    }


def _market_study():
    return {
        "data_scope": {
            "raw_stock_like_series_count": 3019,
            "stock_like_series_count": 2999,
            "account_eligibility": {"included_series_count": 2999},
        },
        "frozen_paper_strategy": {
            "evidence": {
                "summary": {
                    "trade_count": 394,
                    "excess_total_return": 0.1314,
                    "max_drawdown": -0.3011,
                },
                "production_evidence": {"failed_check_ids": ["weak_year_gate"]},
            }
        },
    }


def _entry_artifact(entry_source: str, note: str):
    return {
        "artifact_path": f"output/full_window-{entry_source}.json",
        "payload": {
            "config": {"entry_price_source_note": note},
            "results": {
                "daily_rolling_5x10k": {
                    "low_turnover_20d_uptrend_liquid_top120": {
                        "summary": {
                            "trade_count": 10,
                            "skipped_count": 1,
                            "blocked_exit_count": 0,
                            "total_return": 0.2,
                            "excess_total_return": 0.08,
                            "max_drawdown": -0.05,
                        }
                    }
                }
            },
        },
    }


def test_shortpick_replay_readout_builds_decision_funnel_and_entry_matrix():
    projection = build_shortpick_replay_decision_projection(
        _replay_feedback(),
        market_study=_market_study(),
        entry_artifacts={
            "next_close": _entry_artifact("next_close", "次日收盘买入。"),
            "next_open": _entry_artifact("next_open", "次日开盘买入。"),
            "same_close_proxy": _entry_artifact("same_close_proxy", "同日收盘价近似。"),
        },
        paper_tracking={
            "current_status": "tracking_active",
            "summary": {"tracked_signal_count": 2},
            "items": [
                {"selection_score_components": {"entry_price_source": "same_day_intraday_current"}},
            ],
        },
    )

    decision = projection["decision_readout"]
    assert decision["status"] == "ready"
    questions = {item["id"]: item for item in decision["questions"]}
    assert questions["llm_free_pick"]["status"] == "observe_only"
    assert questions["frozen_strategy"]["status"] == "paper_tracking_only"
    assert questions["candidate_vs_portfolio"]["candidate_metric_value"] == 0.018
    assert questions["candidate_vs_portfolio"]["portfolio_metric_value"] == 0.1314
    assert "候选逐条验证" in questions["candidate_vs_portfolio"]["reason"]
    assert "组合资金曲线" in questions["candidate_vs_portfolio"]["reason"]

    funnel = projection["execution_funnel"]
    assert funnel["status"] == "ready"
    assert [step["label"] for step in funnel["steps"]] == [
        "全量股票",
        "新开户主板可交易池",
        "当日可交易",
        "非涨停不可买",
        "完整K线",
        "正式样本",
        "完成验证",
    ]
    limit_step = next(step for step in funnel["steps"] if step["id"] == "limit_up_fillable")
    assert limit_step["count"] == 5
    assert limit_step["invert_meaning"] is True

    rows = {row["entry_price_source"]: row for row in projection["entry_sensitivity_matrix"]["rows"]}
    assert rows["next_close"]["trade_count"] == 10
    assert rows["same_day_intraday_current"]["status"] == "forward_tracking_only"


def test_shortpick_replay_readout_handles_missing_artifacts_without_frontend_guessing():
    projection = build_shortpick_replay_decision_projection(
        _replay_feedback(),
        market_study={},
        entry_artifacts={},
        paper_tracking={},
    )

    assert projection["execution_funnel"]["status"] == "missing_artifact"
    assert "不得临时重算" in projection["execution_funnel"]["reason"]
    assert projection["entry_sensitivity_matrix"]["status"] == "missing_artifact"
    assert "不得临时回测" in projection["entry_sensitivity_matrix"]["reason"]
    assert projection["entry_sensitivity_matrix"]["rows"][0]["status"] == "missing_artifact"
    assert projection["regime_stability"]["status"] == "phase_2_backlog"
    assert projection["return_attribution"]["status"] == "phase_3_backlog"


def test_same_close_proxy_is_serialized_as_daily_proxy_not_intraday_proof():
    projection = build_shortpick_replay_decision_projection(
        _replay_feedback(),
        market_study=_market_study(),
        entry_artifacts={
            "same_close_proxy": _entry_artifact("same_close_proxy", "同日收盘价近似。"),
        },
        paper_tracking={},
    )

    row = next(
        item
        for item in projection["entry_sensitivity_matrix"]["rows"]
        if item["entry_price_source"] == "same_close_proxy"
    )
    assert row["assumption_level"] == "diagnostic_proxy"
    assert "代理" in row["entry_price_source_note"]
    assert "不等同真实14:00" in row["entry_price_source_note"]
