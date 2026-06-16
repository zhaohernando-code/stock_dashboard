from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_market_factor_study import _Bar, _Series
from ashare_evidence.shortpick_v2_risk_switch_experiment import (
    ARTIFACT_FAMILY,
    DEFAULT_BASELINE_CONFIG_ID,
    DEFAULT_WEAK_MARKET_RETURN_THRESHOLD,
    build_shortpick_v2_risk_switch_experiment_artifact,
    render_shortpick_v2_risk_switch_experiment_markdown,
    validate_shortpick_v2_risk_switch_experiment_payload,
)


def test_risk_switch_experiment_builds_frozen_research_rows(monkeypatch) -> None:
    days = _business_days(date(2026, 1, 5), 52)
    symbols = [f"60010{index}.SH" for index in range(1, 7)]
    series_by_symbol = {
        symbol: _series(symbol, days, start_price=8.0 + index, daily_step=0.05)
        for index, symbol in enumerate(symbols)
    }
    series_by_symbol["000300.SH"] = _series("000300.SH", days, start_price=100.0, daily_step=-1.0)

    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_risk_switch_experiment._load_daily_series",
        lambda _session: series_by_symbol,
    )
    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_risk_switch_experiment._build_strategy_selections",
        lambda *args, signal_days, **kwargs: {signal_day: symbols for signal_day in signal_days},
    )
    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_risk_switch_experiment._regime_features_by_day",
        lambda *args, signal_days, **kwargs: {signal_day: {"pool_ret1_mean": 0.12} for signal_day in signal_days},
    )

    artifact = build_shortpick_v2_risk_switch_experiment_artifact(
        None,  # type: ignore[arg-type]
        historical_start_date=days[5],
        historical_end_date=days[24],
        paper_start_date=days[25],
        paper_end_date=days[38],
        min_signal_symbol_count=1,
        generated_at=datetime(2026, 6, 16, 10, 0, tzinfo=UTC),
    )

    rows = artifact["variant_rows"]
    assert artifact["artifact_family"] == ARTIFACT_FAMILY
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["analysis_scope"]["promotion_status"] == "research_only_no_paper_tracking_promotion"
    assert artifact["weak_market_rule"]["status"] == "frozen_before_run"
    assert artifact["weak_market_rule"]["return_threshold"] == DEFAULT_WEAK_MARKET_RETURN_THRESHOLD
    assert len(rows) == 8
    assert {row["variant_id"] for row in rows} >= {
        DEFAULT_BASELINE_CONFIG_ID,
        "risk_switch_weak_market_50k_max5",
        "risk_switch_all_defensive_skip_drawdown_max3",
    }
    assert all(row["exit_policy_cn"] == "固定 H10 机械卖出" for row in rows)
    assert all("delay" not in action for row in rows for action in row["allowed_actions"])

    lower_notional = next(row for row in rows if row["variant_id"] == "risk_switch_weak_market_50k_max5")
    assert lower_notional["weak_target_notional"] == 50_000.0
    assert lower_notional["historical"]["weak_market_lower_notional_signal_count"] > 0
    max3 = next(row for row in rows if row["variant_id"] == "risk_switch_fixed85_max3")
    assert max3["historical"]["max_position_count"] <= 3
    assert validate_shortpick_v2_risk_switch_experiment_payload(artifact)["status"] == "passed"

    summary = render_shortpick_v2_risk_switch_experiment_markdown(artifact)
    assert "## 研究结论" in summary
    assert "弱势定义" in summary
    assert "弱势日降到 5 万" in summary


def test_risk_switch_experiment_validator_rejects_delay_action(monkeypatch) -> None:
    payload = {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": "v1",
        "claim_ceiling": "research_observation",
        "analysis_scope": {
            "promotion_status": "research_only_no_paper_tracking_promotion",
            "horizon_days": 10,
            "baseline_config_id": DEFAULT_BASELINE_CONFIG_ID,
        },
        "weak_market_rule": {
            "status": "frozen_before_run",
            "index_symbol": "000300.SH",
            "lookback_trade_days": 5,
            "return_threshold": -0.02,
        },
        "variant_rows": [
            {
                "variant_id": DEFAULT_BASELINE_CONFIG_ID,
                "allowed_actions": ["buy_primary", "delay_buy"],
                "historical": {},
                "paper": {},
                "exit_policy_cn": "固定 H10 机械卖出",
            }
            for _ in range(8)
        ],
        "leakage_audit": {"status": "passed"},
    }
    payload = copy.deepcopy(payload)
    payload["variant_rows"][1]["variant_id"] = "v2"
    payload["variant_rows"][2]["variant_id"] = "v3"
    payload["variant_rows"][3]["variant_id"] = "v4"
    payload["variant_rows"][4]["variant_id"] = "v5"
    payload["variant_rows"][5]["variant_id"] = "v6"
    payload["variant_rows"][6]["variant_id"] = "v7"
    payload["variant_rows"][7]["variant_id"] = "v8"

    validation = validate_shortpick_v2_risk_switch_experiment_payload(payload)

    assert validation["status"] == "failed"
    assert any(check["check_id"] == "no_delay_actions" and not check["passed"] for check in validation["checks"])


def test_risk_switch_experiment_validator_rejects_promoted_payload() -> None:
    payload = _minimal_valid_payload()
    payload["analysis_scope"]["promotion_status"] = "promoted_to_paper_tracking"

    validation = validate_shortpick_v2_risk_switch_experiment_payload(payload)

    assert validation["status"] == "failed"
    assert any(check["check_id"] == "research_only" and not check["passed"] for check in validation["checks"])


def test_risk_switch_experiment_cli_parser_and_no_db_validation_command() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-risk-switch-experiment",
            "--historical-start-date",
            "2023-04-13",
            "--paper-end-date",
            "2026-06-15",
            "--output",
            "output/custom-risk-switch.json",
        ]
    )

    assert args.command == "shortpick-v2-risk-switch-experiment"
    assert args.horizon_days == 10
    assert args.output == "output/custom-risk-switch.json"
    assert "shortpick-v2-risk-switch-experiment-validate" in cli_module.NO_DB_COMMANDS


def _minimal_valid_payload() -> dict[str, object]:
    return {
        "artifact_family": ARTIFACT_FAMILY,
        "schema_version": "v1",
        "claim_ceiling": "research_observation",
        "analysis_scope": {
            "promotion_status": "research_only_no_paper_tracking_promotion",
            "horizon_days": 10,
            "baseline_config_id": DEFAULT_BASELINE_CONFIG_ID,
        },
        "weak_market_rule": {
            "status": "frozen_before_run",
            "index_symbol": "000300.SH",
            "lookback_trade_days": 5,
            "return_threshold": -0.02,
        },
        "variant_rows": [
            {
                "variant_id": variant_id,
                "allowed_actions": ["buy_primary", "buy_fallback", "skip"],
                "historical": {},
                "paper": {},
                "exit_policy_cn": "固定 H10 机械卖出",
            }
            for variant_id in [
                DEFAULT_BASELINE_CONFIG_ID,
                "v2",
                "v3",
                "v4",
                "v5",
                "v6",
                "v7",
                "v8",
            ]
        ],
        "leakage_audit": {"status": "passed"},
    }


def _business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _series(symbol: str, days: list[date], *, start_price: float, daily_step: float) -> _Series:
    bars = [
        _Bar(
            day=day,
            open=max(start_price + index * daily_step, 1.0),
            high=max(start_price + index * daily_step, 1.0) * 1.01,
            low=max(start_price + index * daily_step, 1.0) * 0.99,
            close=max(start_price + index * daily_step, 1.0),
            amount=2_000_000.0,
            turnover=1.0,
        )
        for index, day in enumerate(days)
    ]
    return _Series(
        symbol=symbol,
        name=f"样本{symbol}",
        industry="test",
        bars=bars,
        by_day={bar.day: index for index, bar in enumerate(bars)},
    )
