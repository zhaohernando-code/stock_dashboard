from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ashare_evidence.cli import build_parser
from ashare_evidence.external_context_poc import (
    build_external_context_poc_readiness,
    build_external_context_provider_audit,
    load_external_context_registry,
    probe_tushare_external_context_transport,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/contracts/SHORTPICK_V3_EXTERNAL_CONTEXT_PROVIDER_REGISTRY_2026-08-06.json"
REGISTRY_V2 = ROOT / "docs/contracts/SHORTPICK_V3_EXTERNAL_CONTEXT_PROVIDER_REGISTRY_V2_2026-08-06.json"
EVENT_SET = ROOT / "docs/contracts/SHORTPICK_V3_EXTERNAL_CONTEXT_POC_EVENT_SET_2026-08-06.json"
SAMPLE_METRICS = ROOT / "docs/analysis/SHORTPICK_V3_EXTERNAL_CONTEXT_CURRENT_SAMPLE_METRICS_2026-08-06.json"


def test_real_registry_is_valid_and_remains_blocked_before_poc_completion() -> None:
    registry = load_external_context_registry(REGISTRY)
    audit = build_external_context_provider_audit(registry)

    assert audit["gate_status"] == "blocked"
    assert audit["external_context_replay_ready"] is False
    assert audit["v3_signal_changed"] is False
    assert {row["layer"] for row in audit["layers"]} == {
        "official_fact",
        "global_market",
        "professional_news",
    }
    assert all(row["layer_status"] == "blocked" for row in audit["layers"])


def test_sample_gate_evaluation_can_promote_documented_primary_and_fallback() -> None:
    hard_gate_ids = ["license"]
    provider = {
        "provider_name": "fixture",
        "layer": "official_fact",
        "coverage_scope": ["fixture"],
        "gate_evidence": {"license": {"status": "pass"}},
        "sample_gates": [
            {"gate_id": "coverage", "metric": "coverage", "operator": "gte", "threshold": 0.95}
        ],
    }
    registry = {
        "registry_id": "fixture",
        "hard_gate_ids": hard_gate_ids,
        "providers": [
            {**provider, "provider_id": "primary", "target_role": "primary"},
            {**provider, "provider_id": "fallback", "target_role": "fallback"},
            {
                **provider,
                "provider_id": "market-primary",
                "layer": "global_market",
                "target_role": "primary",
            },
            {
                **provider,
                "provider_id": "market-fallback",
                "layer": "global_market",
                "target_role": "fallback",
            },
            {
                **provider,
                "provider_id": "news-primary",
                "layer": "professional_news",
                "target_role": "primary",
            },
            {
                **provider,
                "provider_id": "news-fallback",
                "layer": "professional_news",
                "target_role": "fallback",
            },
        ],
    }
    samples = {"providers": {row["provider_id"]: {"coverage": 1.0} for row in registry["providers"]}}

    audit = build_external_context_provider_audit(registry, sample_metrics=samples)

    assert audit["gate_status"] == "passed"
    assert audit["external_context_replay_ready"] is True


def test_v2_registry_restores_frozen_parallel_channels_and_eliminates_missing_revision_ids() -> None:
    registry = load_external_context_registry(REGISTRY_V2)
    audit = build_external_context_provider_audit(registry)
    providers = {row["provider_id"]: row for row in audit["providers"]}

    assert len(providers) == 13
    assert audit["provider_status_counts"] == {"pending": 8, "eliminated": 5}
    assert all(row["layer_status"] == "blocked" for row in audit["layers"])
    assert providers["sec_edgar"]["scorecard"]["weighted_score_100"] == 89.6
    assert providers["lseg_mrn"]["scorecard"]["weighted_score_100"] == 76.8
    assert providers["ravenpack_news_analytics"]["scorecard"]["weighted_score_100"] == 73.8
    for provider_id in (
        "tushare_stock_st",
        "tushare_index_global",
        "tiingo_eod",
        "tiingo_news",
        "tushare_major_news",
    ):
        assert providers[provider_id]["audit_status"] == "eliminated"
        assert providers[provider_id]["timestamp_failures"] == ["revision_id"]


def test_current_sample_readiness_blocks_full713_weight_research() -> None:
    registry = load_external_context_registry(REGISTRY_V2)
    event_set = json.loads(EVENT_SET.read_text(encoding="utf-8"))
    samples = json.loads(SAMPLE_METRICS.read_text(encoding="utf-8"))

    readiness = build_external_context_poc_readiness(registry, event_set, sample_metrics=samples)

    assert readiness["gate_status"] == "blocked"
    assert readiness["full713_external_context_ready"] is False
    assert readiness["provider_readiness_counts"] == {"pending": 8, "eliminated": 5}
    assert all(not provider_ids for provider_ids in readiness["sample_ready_provider_ids_by_layer"].values())


def test_tushare_probe_shards_news_and_does_not_emit_raw_content_or_token() -> None:
    def fake_request(**kwargs):
        api_name = kwargs["api_name"]
        params = kwargs["params"]
        if api_name == "stock_st":
            fields = ["ts_code", "name", "trade_date", "type", "type_name"]
            items = [["600000.SH", "ST样本", "20260526", "ST", "风险警示板"]]
        elif api_name == "index_global":
            fields = ["ts_code", "trade_date", "open", "close", "high", "low", "vol"]
            items = [[params["ts_code"], "20260526", 1.0, 1.1, 1.2, 0.9, 100.0]]
        else:
            fields = ["title", "pub_time", "src"]
            hour = params["start_date"][11:13]
            items = [[f"样本-{hour}", f"2026-05-26 {hour}:30:00", "测试源"]]
        return {"code": 0, "data": {"fields": fields, "items": items}}

    payload = probe_tushare_external_context_transport(
        base_url="https://example.invalid",
        token="secret-token-must-not-leak",
        stock_st_date=date(2026, 5, 26),
        index_start=date(2023, 5, 1),
        index_end=date(2026, 5, 26),
        news_days=(date(2026, 5, 26),),
        request_fn=fake_request,
        retry_delay_seconds=0.0,
    )

    news = payload["providers"]["tushare_major_news"]
    assert news["all_days_transport_complete"] is True
    assert news["days"]["2026-05-26"]["successful_request_count"] == 24
    assert news["days"]["2026-05-26"]["record_count_after_dedupe"] == 24
    assert len(payload["providers"]["tushare_stock_st"]["response_rows_digest"]) == 64
    assert len(payload["providers"]["tushare_index_global"]["indices"]["SPX"]["response_rows_digest"]) == 64
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "secret-token-must-not-leak" not in serialized
    assert "样本-00" not in serialized
    assert payload["raw_content_retained"] is False


def test_tushare_probe_does_not_retry_frequency_limit_or_leak_token_in_message() -> None:
    request_counts = {"major_news": 0}

    def fake_request(**kwargs):
        api_name = kwargs["api_name"]
        if api_name == "stock_st":
            return {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "name", "trade_date", "type", "type_name"],
                    "items": [["600000.SH", "ST样本", "20260526", "ST", "风险警示板"]],
                },
            }
        if api_name == "index_global":
            return {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "trade_date", "open", "close", "high", "low", "vol"],
                    "items": [[kwargs["params"]["ts_code"], "20260526", 1.0, 1.1, 1.2, 0.9, 100.0]],
                },
            }
        request_counts["major_news"] += 1
        return {"code": 40203, "msg": "secret-token-must-not-leak exceeded 30 requests/hour"}

    payload = probe_tushare_external_context_transport(
        base_url="https://example.invalid",
        token="secret-token-must-not-leak",
        stock_st_date=date(2026, 5, 26),
        index_start=date(2023, 5, 1),
        index_end=date(2026, 5, 26),
        news_days=(date(2026, 5, 26),),
        news_hours=(0,),
        max_attempts=3,
        request_fn=fake_request,
        retry_delay_seconds=0.0,
    )

    shard = payload["providers"]["tushare_major_news"]["days"]["2026-05-26"]["shards"][0]
    assert request_counts["major_news"] == 1
    assert shard["api_code"] == 40203
    assert shard["attempt_count"] == 1
    assert shard["provider_message"].startswith("[redacted]")
    assert "secret-token-must-not-leak" not in json.dumps(payload, ensure_ascii=False)


def test_cli_registers_external_context_poc_commands() -> None:
    parser = build_parser()
    audit_args = parser.parse_args(
        ["research-external-context-provider-audit", "--registry-json", str(REGISTRY)]
    )
    probe_args = parser.parse_args(["research-external-context-tushare-poc", "--news-day", "2026-05-26"])
    readiness_args = parser.parse_args(
        [
            "research-external-context-poc-readiness",
            "--registry-json",
            str(REGISTRY_V2),
            "--event-set-json",
            str(EVENT_SET),
        ]
    )

    assert audit_args.command == "research-external-context-provider-audit"
    assert probe_args.command == "research-external-context-tushare-poc"
    assert readiness_args.command == "research-external-context-poc-readiness"
