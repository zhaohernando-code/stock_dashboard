from __future__ import annotations

import ashare_evidence.api as api
from ashare_evidence.api import (
    _build_shortpick_replay_aggregate_feedback_response,
    _build_shortpick_strategy_governance_projection,
    _clear_shortpick_replay_aggregate_feedback_cache,
    _slim_shortpick_strategy_slice_evidence,
)


def test_strategy_slice_response_projection_keeps_ui_fields_and_drops_heavy_detail() -> None:
    payload = {
        "experiment": "shortpick_strategy_slice_evidence",
        "status": "ready",
        "data_scope": {"signal_day_count": 717},
        "sample_adequacy": {"status": "broad_enough_for_controls"},
        "artifact_path": "output/shortpick-strategy-slice-evidence.json",
        "trade_regime_evidence": {
            "status": "ready",
            "data_scope": {"signal_day_count": 717},
            "regime_winner_rows": [{"market_regime_tag": "range_bound", "winner_trade_count": 162}],
            "trade_attribution": {
                "status": "ready",
                "sample_trade_count": 2,
                "top_symbol_rows": [{"symbol": "600001.SH"}],
                "top_industry_rows": [{"industry": "光模块"}],
                "top_signal_day_rows": [{"signal_day": "2025-01-02"}],
            },
            "regime_strategy_rows": [{"heavy": True}],
        },
        "overall_strategy_rows": [{"strategy": "low_turnover"}],
        "regime_winner_rows": [{"regime": "up"}],
        "regime_coverage_rows": [{"regime": "up", "month_count": 3}],
        "period_strategy_rows": [{"heavy": True}],
        "regime_strategy_rows": [
            {
                "entry_price_source": "next_close",
                "trend_regime": "range_bound",
                "market_regime_tag": "range_bound:low_volatility:balanced_size",
                "strategy": "low_turnover_20d_uptrend_liquid_top120",
                "label": "低换手上升趋势",
                "period_count": 8,
                "mean_net_return": 0.02,
                "mean_net_excess_return": 0.03,
                "positive_net_excess_rate": 0.75,
            },
            {
                "entry_price_source": "next_close",
                "trend_regime": "range_bound",
                "market_regime_tag": "range_bound:normal_volatility:balanced_size",
                "strategy": "low_turnover_20d_uptrend_liquid_top120",
                "label": "低换手上升趋势",
                "period_count": 4,
                "mean_net_return": 0.01,
                "mean_net_excess_return": 0.02,
                "positive_net_excess_rate": 0.5,
            },
            {
                "entry_price_source": "next_close",
                "trend_regime": "range_bound",
                "market_regime_tag": "range_bound:low_volatility:balanced_size",
                "strategy": "base",
                "label": "基础动量",
                "period_count": 12,
                "mean_net_return": 0.01,
                "mean_net_excess_return": 0.01,
                "positive_net_excess_rate": 0.5,
            },
        ],
        "portfolio_confidence_intervals": {
            "status": "ready",
            "method": "bootstrap",
            "rows": [{"strategy": "low_turnover", "ci_lower": 0.01}],
            "raw_samples": [{"heavy": True}],
        },
        "portfolio_stability": {
            "status": "ready",
            "period_summary_rows": [{"period_kind": "month"}],
            "time_slices": [{"heavy": True}],
            "market_regime": {
                "status": "ready",
                "basis": "monthly_index_proxy",
                "rows": [{"heavy": True}],
            },
        },
        "portfolio_return_attribution": {
            "status": "ready",
            "rows": [{"strategy": "low_turnover"}],
            "symbol_industry": {"status": "missing_artifact", "reason": "trades_sample only"},
            "raw_trades": [{"heavy": True}],
        },
        "portfolio_forward_tracking_alignment": {"status": "insufficient_forward_sample"},
    }

    slim = _slim_shortpick_strategy_slice_evidence(payload)

    assert slim["data_scope"] == {"signal_day_count": 717}
    assert slim["trade_regime_evidence"] == {
        "status": "ready",
        "data_scope": {"signal_day_count": 717},
        "regime_winner_rows": [{"market_regime_tag": "range_bound", "winner_trade_count": 162}],
        "trade_attribution": {
            "status": "ready",
            "sample_trade_count": 2,
            "top_symbol_rows": [{"symbol": "600001.SH"}],
            "top_industry_rows": [{"industry": "光模块"}],
            "top_signal_day_rows": [{"signal_day": "2025-01-02"}],
        },
    }
    assert slim["overall_strategy_rows"] == [{"strategy": "low_turnover"}]
    assert slim["regime_winner_rows"] == [{"regime": "up"}]
    assert slim["coarse_regime_winner_rows"][0]["market_regime_tag"] == "range_bound"
    assert slim["coarse_regime_winner_rows"][0]["regime_granularity"] == "trend_regime"
    assert slim["coarse_regime_winner_rows"][0]["winner_sample_count"] == 12
    assert slim["coarse_regime_winner_rows"][0]["winner_mean_net_excess_return"] == 0.026667
    assert slim["coarse_regime_winner_rows"][0]["frozen_is_winner"] is True
    assert slim["regime_coverage_rows"] == [{"regime": "up", "month_count": 3}]
    assert slim["portfolio_forward_tracking_alignment"] == {"status": "insufficient_forward_sample"}
    assert slim["portfolio_confidence_intervals"] == {
        "status": "ready",
        "method": "bootstrap",
        "rows": [{"strategy": "low_turnover", "ci_lower": 0.01}],
    }
    assert slim["portfolio_stability"] == {
        "status": "ready",
        "period_summary_rows": [{"period_kind": "month"}],
        "market_regime": {"status": "ready", "basis": "monthly_index_proxy"},
    }
    assert slim["portfolio_return_attribution"] == {
        "status": "ready",
        "rows": [{"strategy": "low_turnover"}],
        "symbol_industry": {
            "status": "ready",
            "sample_trade_count": 2,
            "top_symbol_rows": [{"symbol": "600001.SH"}],
            "top_industry_rows": [{"industry": "光模块"}],
            "top_signal_day_rows": [{"signal_day": "2025-01-02"}],
        },
    }
    assert "period_strategy_rows" not in slim
    assert "regime_strategy_rows" not in slim
    assert "time_slices" not in slim["portfolio_stability"]
    assert "raw_trades" not in slim["portfolio_return_attribution"]


def test_api_builds_shortpick_strategy_governance_projection_from_paper_tracking() -> None:
    projection = _build_shortpick_strategy_governance_projection(
        {
            "items": [
                _paper_tracking_item(f"2026-05-{index + 1:02d}", stock_return=value)
                for index, value in enumerate([-0.10, -0.05, 0.01])
            ]
        }
    )

    assert projection["status"] == "ready"
    assert projection["source_policy"] == "read_only_paper_tracking_ledger_no_role_name_status_inference"
    assert projection["strategy_count"] == 1
    view = projection["view_projection"]
    assert view["primary_count"] == 1
    assert view["archive_count"] == 0
    assert view["primary_items"][0]["evidence_basis"] == "true_forward_tracking"
    assert view["primary_items"][0]["status_display"]["key"] == view["primary_items"][0]["recommended_status"]
    assert projection["archive_records"]["archive_count"] == 0


def test_api_strategy_governance_projection_does_not_infer_status_from_empty_ledger() -> None:
    projection = _build_shortpick_strategy_governance_projection({"items": []})

    assert projection == {
        "status": "missing_source",
        "source_policy": "read_only_paper_tracking_ledger_no_role_name_status_inference",
        "reason": "paper tracking ledger has no strategy rows for governance projection",
    }


def test_api_enriches_ready_replay_feedback_frontend_projection(monkeypatch) -> None:
    _clear_shortpick_replay_aggregate_feedback_cache()
    session = object()
    ready_projection = {
        "generated_at": "2026-05-14T16:02:11+00:00",
        "overall": {"run_count": 1},
    }

    monkeypatch.setattr(
        api,
        "get_ready_frontend_projection_payload",
        lambda actual_session, projection_key: ready_projection,
    )
    monkeypatch.setattr(
        api,
        "_load_shortpick_replay_feedback_from_cache",
        lambda run_id=None: (_ for _ in ()).throw(AssertionError("cache fallback should not run")),
    )

    def attach_projection(payload: dict[str, object], *, session: object) -> dict[str, object]:
        assert payload is ready_projection
        return {
            **payload,
            "overall": {
                **payload["overall"],  # type: ignore[arg-type]
                "strategy_governance_reporting": {"status": "ready"},
            },
        }

    monkeypatch.setattr(api, "_attach_shortpick_replay_decision_projection", attach_projection)

    response = _build_shortpick_replay_aggregate_feedback_response(session)  # type: ignore[arg-type]

    assert response["overall"]["strategy_governance_reporting"] == {"status": "ready"}  # type: ignore[index]
    _clear_shortpick_replay_aggregate_feedback_cache()


def test_api_caches_enriched_replay_feedback_for_short_ttl(monkeypatch) -> None:
    _clear_shortpick_replay_aggregate_feedback_cache()
    session = object()
    now = {"value": 100.0}
    ready_projection = {
        "generated_at": "2026-05-14T16:02:11+00:00",
        "overall": {"run_count": 1},
    }
    attach_calls = {"count": 0}

    monkeypatch.setattr(api.time, "perf_counter", lambda: now["value"])
    monkeypatch.setattr(
        api,
        "get_ready_frontend_projection_payload",
        lambda actual_session, projection_key: ready_projection,
    )
    monkeypatch.setattr(
        api,
        "_load_shortpick_replay_feedback_from_cache",
        lambda run_id=None: (_ for _ in ()).throw(AssertionError("cache fallback should not run")),
    )

    def attach_projection(payload: dict[str, object], *, session: object) -> dict[str, object]:
        attach_calls["count"] += 1
        return {
            **payload,
            "overall": {
                **payload["overall"],  # type: ignore[arg-type]
                "strategy_governance_reporting": {
                    "status": "ready",
                    "sequence": attach_calls["count"],
                },
            },
        }

    monkeypatch.setattr(api, "_attach_shortpick_replay_decision_projection", attach_projection)

    first = _build_shortpick_replay_aggregate_feedback_response(session)  # type: ignore[arg-type]
    first["overall"]["strategy_governance_reporting"]["status"] = "mutated"  # type: ignore[index]
    second = _build_shortpick_replay_aggregate_feedback_response(session)  # type: ignore[arg-type]

    assert attach_calls["count"] == 1
    assert second["overall"]["strategy_governance_reporting"] == {  # type: ignore[index]
        "status": "ready",
        "sequence": 1,
    }

    now["value"] += api.SHORTPICK_REPLAY_AGGREGATE_FEEDBACK_TTL_SECONDS + 0.1
    third = _build_shortpick_replay_aggregate_feedback_response(session)  # type: ignore[arg-type]

    assert attach_calls["count"] == 2
    assert third["overall"]["strategy_governance_reporting"] == {  # type: ignore[index]
        "status": "ready",
        "sequence": 2,
    }
    _clear_shortpick_replay_aggregate_feedback_cache()


def _paper_tracking_item(signal_date: str, *, stock_return: float) -> dict[str, object]:
    return {
        "run_id": 1,
        "candidate_id": hash(signal_date) % 100000,
        "run_date": signal_date,
        "signal_date": signal_date,
        "entry_date": signal_date,
        "symbol": "002371.SZ",
        "name": "北方华创",
        "tracking_group": "frozen_strategy",
        "tracking_role": "frozen_paper_primary",
        "selection_label": "冻结纸面策略",
        "source_rank": 1,
        "entry_rule": "次一交易日收盘买入",
        "selection_score_components": {
            "family": "low_turnover_20d_uptrend_liquid_top120",
            "entry_price_source": "next_close",
        },
        "validation_by_horizon": [
            {
                "horizon_days": 10,
                "status": "completed",
                "entry_at": f"{signal_date}T15:00:00+08:00",
                "exit_at": "2026-05-24T15:00:00+08:00",
                "stock_return": stock_return,
                "excess_return": stock_return - 0.01,
            }
        ],
    }
