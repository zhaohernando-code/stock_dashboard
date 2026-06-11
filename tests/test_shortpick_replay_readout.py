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
    assert projection["regime_stability"]["status"] == "missing_artifact"
    assert projection["confidence_intervals"]["status"] == "missing_artifact"
    assert projection["return_attribution"]["status"] == "missing_artifact"
    assert projection["forward_tracking_alignment"]["status"] == "insufficient_forward_sample"
    governance = projection["strategy_governance_reporting"]
    assert governance["status"] == "missing_artifact"
    assert governance["may_infer_status_from_role_name"] is False
    assert "tracking_role" in governance["reason"]


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


def test_shortpick_replay_readout_reads_strategy_governance_contract_fields_not_role_names():
    projection = build_shortpick_replay_decision_projection(
        _replay_feedback(),
        market_study=_market_study(),
        entry_artifacts={},
        paper_tracking={},
        strategy_governance={
            "recommendations": [
                {
                    "strategy_id": "retro-candidate",
                    "tracking_role": "frozen_paper_primary",
                    "recommended_status": "retire_candidate",
                    "evidence_basis": "retrospective_forward_replay",
                    "leakage_audit_status": "not_run",
                    "leakage_audit_reasons": ["audit_pending"],
                    "strategy_family": "cooldown",
                    "entry_price_source": "next_close",
                },
                {
                    "strategy_id": "true-retired",
                    "tracking_role": "frozen_paper_primary",
                    "recommended_status": "retired",
                    "evidence_basis": "true_forward_tracking",
                    "strategy_family": "low_turnover",
                    "entry_price_source": "next_close",
                },
            ],
            "archive_records": {
                "summary_rows": [
                    {
                        "summary_key": "true_forward_tracking__low_turnover__next_close",
                        "evidence_basis": "true_forward_tracking",
                        "strategy_family": "low_turnover",
                        "entry_price_source": "next_close",
                        "archived_strategy_count": 1,
                        "signal_count": 10,
                        "completed_observation_count": 10,
                        "retirement_artifact_count": 1,
                    }
                ]
            },
        },
    )

    governance = projection["strategy_governance_reporting"]
    assert governance["status"] == "ready"
    assert governance["source_policy"] == "read_governance_projection_not_role_names"
    assert governance["may_infer_status_from_role_name"] is False
    assert governance["primary_count"] == 0
    assert governance["archive_count"] == 2
    assert governance["status_counts"] == {"retire_candidate": 1, "retired": 1}
    assert [section["evidence_basis"] for section in governance["sections"]] == [
        "true_forward_tracking",
        "retrospective_forward_replay",
    ]
    assert [section["archive_count"] for section in governance["sections"]] == [1, 1]
    assert governance["archive_summary_rows"][0]["summary_key"] == "true_forward_tracking__low_turnover__next_close"
    assert governance["leakage_coverage_rows"] == [
        {
            "strategy_id": "retro-candidate",
            "recommended_status": "retire_candidate",
            "evidence_basis": "retrospective_forward_replay",
            "leakage_audit_status": "not_run",
            "leakage_audit_reasons": ["audit_pending"],
            "source_feature_cutoff_policy": "signal_date_available_inputs_only",
            "feature_cutoff_at": None,
            "feature_coverage_status": "unknown",
        }
    ]


def test_shortpick_replay_readout_surfaces_phase_two_three_artifacts():
    feedback = _replay_feedback()
    feedback["overall"]["confidence_intervals"] = {
        "status": "ready",
        "rows": [
            {
                "id": "default_5d_tradable",
                "family": "momentum_10d_turnover_cooldown_rank",
                "eligibility": "tradable",
                "lower_bound_positive": False,
            }
        ],
    }
    feedback["overall"]["return_attribution"] = {
        "status": "ready",
        "rows": [{"family": "momentum_10d_turnover_cooldown_rank", "best_symbol": "002384.SZ"}],
    }
    feedback["overall"]["regime_stability"] = {
        "status": "ready",
        "time_slices": {"month": [{"period": "2026-04"}]},
    }
    entry = _entry_artifact("next_close", "次日收盘买入。")
    entry["payload"]["results"]["daily_rolling_5x10k"]["low_turnover_20d_uptrend_liquid_top120"]["monthly"] = [
        {"period": "2026-04", "excess_return": 0.1},
        {"period": "2026-05", "excess_return": -0.2},
    ]
    entry["payload"]["results"]["daily_rolling_5x10k"]["low_turnover_20d_uptrend_liquid_top120"]["yearly"] = [
        {"period": "2026", "excess_return": -0.05},
    ]

    projection = build_shortpick_replay_decision_projection(
        feedback,
        market_study=_market_study(),
        entry_artifacts={"next_close": entry},
        paper_tracking={"current_status": "tracking_active", "summary": {"tracked_signal_count": 4}},
    )

    assert projection["confidence_intervals"]["status"] == "ready"
    assert projection["return_attribution"]["rows"][0]["best_symbol"] == "002384.SZ"
    assert projection["regime_stability"]["status"] == "ready"
    assert projection["regime_stability"]["portfolio_periods"]
    assert projection["forward_tracking_alignment"]["historical_portfolio_expected_excess"] == 0.1314
