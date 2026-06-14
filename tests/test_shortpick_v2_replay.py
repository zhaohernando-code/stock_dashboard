from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import jsonschema
import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_market_factor_study import _Bar, _Series
from ashare_evidence.shortpick_v2_replay import (
    DEFAULT_INITIAL_CASH,
    ShortpickV2RuleConfig,
    build_shortpick_v2_replay_artifact_from_series,
)


def _series(symbol: str, prices: list[float]) -> _Series:
    start = date(2026, 1, 1)
    bars = [
        _Bar(
            day=start + timedelta(days=index),
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            amount=1_000_000.0,
            turnover=1.0,
        )
        for index, price in enumerate(prices)
    ]
    return _Series(
        symbol=symbol,
        name=f"测试{symbol}",
        industry="test",
        bars=bars,
        by_day={bar.day: index for index, bar in enumerate(bars)},
    )


def _series_for_days(symbol: str, prices_by_day: dict[date, float]) -> _Series:
    bars = [
        _Bar(
            day=day,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            amount=1_000_000.0,
            turnover=1.0,
        )
        for day, price in sorted(prices_by_day.items())
    ]
    return _Series(
        symbol=symbol,
        name=f"测试{symbol}",
        industry="test",
        bars=bars,
        by_day={bar.day: index for index, bar in enumerate(bars)},
    )


def _artifact_for_rules(rule_configs: tuple[ShortpickV2RuleConfig, ...]) -> dict[str, object]:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(8)]
    series_by_symbol = {
        "600001.SH": _series("600001.SH", [290, 295, 300, 300, 302, 303, 304, 305]),
        "600002.SH": _series("600002.SH", [18, 19, 20, 20, 21, 22, 22, 23]),
    }
    return build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=[days[2]],
        trade_days=days[2:7],
        selections={days[2]: ["600001.SH", "600002.SH"]},
        start_date=days[0],
        end_date=days[6],
        initial_cash=20_000.0,
        horizon_days=2,
        account_profile="new_retail_cash_account",
        rule_configs=rule_configs,
        generated_at=datetime(2026, 6, 12, 8, 0, tzinfo=UTC),
    )


def _dynamic_exit_artifact(rule: ShortpickV2RuleConfig, prices: list[float]) -> dict[str, object]:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(len(prices))]
    return build_shortpick_v2_replay_artifact_from_series(
        {"600001.SH": _series("600001.SH", prices)},
        signal_days=[days[1]],
        trade_days=days[1:],
        selections={days[1]: ["600001.SH"]},
        start_date=days[0],
        end_date=days[-1],
        initial_cash=20_000.0,
        horizon_days=4,
        account_profile="new_retail_cash_account",
        rule_configs=(rule,),
        generated_at=datetime(2026, 6, 15, 8, 0, tzinfo=UTC),
    )


def test_shortpick_v2_topn_fallback_buys_candidate_without_delayed_entry() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_top2_fallback",
        family="topn_fallback",
        candidate_rank_limit=2,
        fallback_enabled=True,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "buy_fallback", "skip"),
    )

    artifact = _artifact_for_rules((rule,))

    assert artifact["artifact_family"] == "shortpick_v2_replay_artifact"
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["evidence_basis"] == "historical_account_replay"
    assert artifact["promotion_gate"]["status"] == "not_evaluated"  # type: ignore[index]
    assert artifact["leakage_audit"]["status"] == "passed"  # type: ignore[index]
    assert set(artifact) == {
        "artifact_family",
        "schema_version",
        "artifact_id",
        "generated_at",
        "status",
        "claim_ceiling",
        "evidence_basis",
        "source_plan_ref",
        "data_scope",
        "input_contracts",
        "rule_matrix",
        "results",
        "promotion_gate",
        "leakage_audit",
        "event_refs",
    }

    result = artifact["results"][0]  # type: ignore[index]
    decision = result["decision_samples"][0]  # type: ignore[index]
    assert artifact["data_scope"]["market_reference_mode"] == (  # type: ignore[index]
        "eligible_universe_equal_weight_close_to_close"
    )
    assert artifact["data_scope"]["market_reference_sample_count"] == 2  # type: ignore[index]
    assert artifact["data_scope"]["market_reference_total_return"] == 0.0  # type: ignore[index]
    assert result["summary"]["market_reference_total_return"] == 0.0  # type: ignore[index]
    assert result["summary"]["market_excess_total_return"] is not None  # type: ignore[index]
    assert decision["action"] == "buy_fallback"
    assert decision["selected_rank"] == 2
    assert decision["symbol"] == "600002.SH"
    assert decision["quantity"] >= 100
    assert result["summary"]["fallback_trade_count"] == 1  # type: ignore[index]
    assert result["reason_counts"]["candidate_reject:insufficient_cash"] == 1  # type: ignore[index]
    assert {item["action"] for item in result["decision_samples"]} <= {  # type: ignore[index]
        "buy_primary",
        "buy_fallback",
        "skip",
    }


def test_shortpick_v2_close_stop_loss_exits_before_horizon_and_validates_schema() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_fixed_notional_stop_loss",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="fixed_notional",
        target_notional=10_000.0,
        stop_loss_pct=0.08,
        allowed_actions=("buy_primary", "skip"),
    )
    artifact = _dynamic_exit_artifact(rule, [10.0, 10.0, 10.0, 9.7, 9.1, 9.0, 12.0, 12.0])
    schema = json.loads(
        Path("docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json").read_text(encoding="utf-8")
    )

    jsonschema.Draft202012Validator(schema).validate(artifact)
    assert artifact["rule_matrix"][0]["exit_policy"]["dynamic_exit_triggers"] == ["stop_loss"]  # type: ignore[index]
    assert artifact["input_contracts"]["exit_model"]["exit_tracks"] == [  # type: ignore[index]
        "mechanical_horizon_exit",
        "limit_down_blocked_exit",
        "close_stop_loss_exit",
    ]
    result = artifact["results"][0]  # type: ignore[index]
    assert result["reason_counts"]["exit:stop_loss"] == 1
    assert result["summary"]["dynamic_exit_count"] == 1  # type: ignore[index]
    assert result["summary"]["exit_reason_counts"] == {"stop_loss": 1}  # type: ignore[index]
    assert result["summary"]["open_position_count"] == 0  # type: ignore[index]


def test_shortpick_v2_close_take_profit_exits_before_horizon() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_fixed_notional_take_profit",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="fixed_notional",
        target_notional=10_000.0,
        take_profit_pct=0.08,
        allowed_actions=("buy_primary", "skip"),
    )

    artifact = _dynamic_exit_artifact(rule, [10.0, 10.0, 10.0, 10.5, 10.9, 11.0, 9.0, 9.0])
    result = artifact["results"][0]  # type: ignore[index]

    assert result["reason_counts"]["exit:take_profit"] == 1
    assert result["summary"]["dynamic_exit_count"] == 1  # type: ignore[index]
    assert result["summary"]["exit_reason_counts"] == {"take_profit": 1}  # type: ignore[index]


def test_shortpick_v2_close_trailing_stop_exits_after_activation() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_fixed_notional_trailing_stop",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="fixed_notional",
        target_notional=10_000.0,
        trailing_stop_pct=0.05,
        trailing_activation_pct=0.08,
        allowed_actions=("buy_primary", "skip"),
    )

    artifact = _dynamic_exit_artifact(rule, [10.0, 10.0, 10.0, 11.0, 10.3, 10.2, 12.0, 12.0])
    result = artifact["results"][0]  # type: ignore[index]

    assert result["reason_counts"]["exit:trailing_stop"] == 1
    assert result["summary"]["dynamic_exit_count"] == 1  # type: ignore[index]
    assert result["summary"]["exit_reason_counts"] == {"trailing_stop": 1}  # type: ignore[index]


def test_shortpick_v2_trailing_exit_requires_stop_and_activation_pair() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_invalid_trailing",
        family="fixed_notional_lot_rounding",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="fixed_notional",
        target_notional=10_000.0,
        trailing_stop_pct=0.06,
        allowed_actions=("buy_primary", "skip"),
    )

    with pytest.raises(ValueError, match="trailing exit requires both stop and activation pct"):
        _artifact_for_rules((rule,))


def test_shortpick_v2_top1_rule_skips_instead_of_using_fallback() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_top1_or_skip",
        family="top1_or_skip",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "skip"),
    )

    artifact = _artifact_for_rules((rule,))
    result = artifact["results"][0]  # type: ignore[index]
    decision = result["decision_samples"][0]  # type: ignore[index]

    assert decision["action"] == "skip"
    assert decision["reason"] == "insufficient_cash"
    assert decision["selected_rank"] is None
    assert decision["quantity"] == 0
    assert result["summary"]["trade_count"] == 0  # type: ignore[index]
    assert result["summary"]["skip_count"] == 1  # type: ignore[index]
    assert "action:buy_fallback" not in result["reason_counts"]  # type: ignore[operator]


def test_shortpick_v2_missing_declared_entry_day_does_not_delay_buy() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_no_delayed_entry",
        family="top1_or_skip",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "skip"),
    )
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(5)]
    series_by_symbol = {
        "600003.SH": _series_for_days(
            "600003.SH",
            {
                days[0]: 10.0,
                days[2]: 10.5,
                days[3]: 10.8,
                days[4]: 11.0,
            },
        )
    }

    artifact = build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=[days[0]],
        trade_days=days,
        selections={days[0]: ["600003.SH"]},
        start_date=days[0],
        end_date=days[-1],
        initial_cash=20_000.0,
        horizon_days=2,
        account_profile="new_retail_cash_account",
        rule_configs=(rule,),
        generated_at=datetime(2026, 6, 12, 8, 0, tzinfo=UTC),
    )

    result = artifact["results"][0]  # type: ignore[index]
    decision = result["decision_samples"][0]  # type: ignore[index]
    assert decision["action"] == "skip"
    assert decision["reason"] == "no_ranked_candidates"
    assert result["summary"]["trade_count"] == 0  # type: ignore[index]


def test_shortpick_v2_empty_signal_scope_keeps_blocked_result_entry() -> None:
    rule = ShortpickV2RuleConfig(
        config_id="test_empty_scope",
        family="top1_or_skip",
        candidate_rank_limit=1,
        fallback_enabled=False,
        target_mode="position_cap",
        allowed_actions=("buy_primary", "skip"),
    )

    artifact = build_shortpick_v2_replay_artifact_from_series(
        {},
        signal_days=[],
        trade_days=[],
        selections={},
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        initial_cash=20_000.0,
        horizon_days=2,
        account_profile="new_retail_cash_account",
        rule_configs=(rule,),
        generated_at=datetime(2026, 6, 12, 8, 0, tzinfo=UTC),
    )

    assert artifact["status"] == "blocked"
    assert artifact["data_scope"]["coverage_status"] == "blocked"  # type: ignore[index]
    assert artifact["data_scope"]["market_reference_sample_count"] == 0  # type: ignore[index]
    assert artifact["data_scope"]["market_reference_total_return"] is None  # type: ignore[index]
    assert len(artifact["results"]) == 1  # type: ignore[arg-type]
    result = artifact["results"][0]  # type: ignore[index]
    assert result["status"] == "blocked"
    assert result["summary"]["signal_count"] == 0  # type: ignore[index]
    assert result["summary"]["market_reference_total_return"] is None  # type: ignore[index]
    assert result["decision_samples"] == []


def test_shortpick_v2_replay_cli_parser_defaults_to_offline_artifact_output() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-replay"])

    assert args.initial_cash == DEFAULT_INITIAL_CASH
    assert args.entry_price_source == "next_close"
    assert args.output == str(Path("output/shortpick-v2-replay-artifact.json"))
