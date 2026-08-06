from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.intraday_market import DEFAULT_TUSHARE_BASE_URL, _post_tushare
from ashare_evidence.models import ProviderCredential

EXTERNAL_CONTEXT_PROVIDER_AUDIT_VERSION = "external-context-provider-audit-v1"
TUSHARE_EXTERNAL_CONTEXT_POC_VERSION = "tushare-external-context-transport-poc-v1"
ALLOWED_LAYERS = {"official_fact", "global_market", "professional_news"}
PASSING_GATE_STATUSES = {"pass", "not_applicable"}
KNOWN_GATE_STATUSES = PASSING_GATE_STATUSES | {"fail", "pending"}
REQUIRED_TIME_LINEAGE_FIELDS = ("published_at", "first_seen_at", "available_at", "revision_id")
POC_SAMPLE_RULES = {
    "required_field_completeness_min": ("required_field_completeness", "gte"),
    "timestamp_parse_success_min": ("timestamp_parse_success", "gte"),
    "stable_key_unique_rate_min": ("stable_key_unique_rate", "gte"),
    "entity_mapping_precision_min": ("entity_mapping_precision", "gte"),
    "entity_mapping_recall_min": ("entity_mapping_recall", "gte"),
    "repeat_pull_hash_match_rate": ("repeat_pull_hash_match_rate", "gte"),
    "future_available_at_violation_count": ("future_available_at_violation_count", "lte"),
    "unlinked_revision_rate_max": ("unlinked_revision_rate", "lte"),
    "full713_plus_warmup_start_max": ("coverage_start", "date_lte"),
    "full713_end_min": ("coverage_end", "date_gte"),
}


def load_external_context_registry(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider registry must be a JSON object")
    return payload


def build_external_context_provider_audit(
    registry: dict[str, Any],
    *,
    sample_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    providers = registry.get("providers")
    hard_gate_ids = registry.get("hard_gate_ids")
    if not isinstance(providers, list) or not providers:
        raise ValueError("provider registry must contain providers")
    if not isinstance(hard_gate_ids, list) or not hard_gate_ids:
        raise ValueError("provider registry must contain hard_gate_ids")

    sample_by_provider = _sample_metrics_by_provider(sample_metrics)
    provider_rows = [
        _audit_provider(
            provider,
            hard_gate_ids=hard_gate_ids,
            sample=sample_by_provider.get(str(provider.get("provider_id"))),
            scorecard_dimensions=registry.get("scorecard_dimensions") or [],
        )
        for provider in providers
    ]
    layer_rows = []
    for layer in sorted(ALLOWED_LAYERS):
        candidates = [row for row in provider_rows if row["layer"] == layer]
        ready_primary = [row["provider_id"] for row in candidates if row["audit_status"] == "ready" and row["target_role"] == "primary"]
        ready_fallback = [row["provider_id"] for row in candidates if row["audit_status"] == "ready" and row["target_role"] == "fallback"]
        ready_candidates = [
            row
            for row in candidates
            if row["audit_status"] == "ready" and row["target_role"] != "discovery_only"
        ]
        readiness_rule = registry.get("layer_readiness_rule") or {}
        if readiness_rule.get("mode") == "parallel_candidates":
            required_count = max(2, int(readiness_rule.get("required_ready_candidate_count") or 2))
            independence_groups = {
                str(row.get("independence_group") or row["provider_id"])
                for row in ready_candidates
            }
            layer_ready = len(ready_candidates) >= required_count and len(independence_groups) >= required_count
            blocking_reason = (
                None
                if layer_ready
                else "required_ready_independent_parallel_candidates_not_available"
            )
        else:
            required_count = 2
            independence_groups = {
                str(row.get("independence_group") or row["provider_id"])
                for row in ready_candidates
            }
            layer_ready = bool(ready_primary and ready_fallback)
            blocking_reason = None if layer_ready else "primary_and_independent_fallback_not_both_ready"
        layer_rows.append(
            {
                "layer": layer,
                "candidate_count": len(candidates),
                "required_ready_candidate_count": required_count,
                "ready_provider_ids": [row["provider_id"] for row in ready_candidates],
                "ready_independence_group_count": len(independence_groups),
                "ready_primary_provider_ids": ready_primary,
                "ready_fallback_provider_ids": ready_fallback,
                "layer_status": "ready" if layer_ready else "blocked",
                "blocking_reason": blocking_reason,
            }
        )

    overall_ready = all(row["layer_status"] == "ready" for row in layer_rows)
    canonical = json.dumps(
        {"registry_id": registry.get("registry_id"), "providers": provider_rows, "layers": layer_rows},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "artifact_type": "external_context_provider_audit",
        "audit_version": EXTERNAL_CONTEXT_PROVIDER_AUDIT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_id": registry.get("registry_id"),
        "registry_as_of": registry.get("as_of"),
        "baseline_contract": registry.get("baseline_contract"),
        "gate_status": "passed" if overall_ready else "blocked",
        "external_context_replay_ready": overall_ready,
        "v3_signal_changed": False,
        "claim_ceiling": "provider_poc_only_no_strategy_validation",
        "provider_status_counts": dict(Counter(row["audit_status"] for row in provider_rows)),
        "providers": provider_rows,
        "layers": layer_rows,
        "recommended_poc_order": registry.get("recommended_poc_order") or [],
        "vendor_questions": registry.get("vendor_questions") or [],
        "audit_digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def build_external_context_poc_readiness(
    registry: dict[str, Any],
    event_set: dict[str, Any],
    *,
    sample_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_external_context_provider_audit(registry, sample_metrics=sample_metrics)
    thresholds = registry.get("sample_acceptance_gates")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ValueError("registry must define sample_acceptance_gates")
    if event_set.get("schema_version") != "external_context_poc_event_set.v1":
        raise ValueError("unsupported external-context event-set schema")
    sample_by_provider = _sample_metrics_by_provider(sample_metrics)
    provider_rows: list[dict[str, Any]] = []
    for provider in audit["providers"]:
        provider_id = provider["provider_id"]
        checks: list[dict[str, Any]] = []
        sample = sample_by_provider.get(provider_id)
        for threshold_id, threshold in thresholds.items():
            rule = POC_SAMPLE_RULES.get(str(threshold_id))
            if rule is None:
                continue
            metric, operator = rule
            value = _nested_value(sample, metric) if sample is not None else None
            status = (
                "pending"
                if value is None
                else "pass"
                if _compare_metric(value, operator=operator, threshold=threshold)
                else "fail"
            )
            checks.append(
                {
                    "gate_id": threshold_id,
                    "metric": metric,
                    "operator": operator,
                    "threshold": threshold,
                    "observed": value,
                    "status": status,
                }
            )
        failures = [row["gate_id"] for row in checks if row["status"] == "fail"]
        pending = [row["gate_id"] for row in checks if row["status"] == "pending"]
        if provider["audit_status"] == "eliminated":
            readiness = "eliminated"
            severity = "critical"
        elif provider["audit_status"] == "blocked" or failures:
            readiness = "blocked"
            severity = "high"
        elif provider["audit_status"] != "ready" or pending:
            readiness = "pending"
            severity = "medium"
        else:
            readiness = "sample_ready"
            severity = "low"
        provider_rows.append(
            {
                "provider_id": provider_id,
                "layer": provider["layer"],
                "documentary_audit_status": provider["audit_status"],
                "poc_readiness": readiness,
                "data_quality_severity": severity,
                "documentary_score_100": provider["scorecard"]["weighted_score_100"],
                "timestamp_failures": provider["timestamp_failures"],
                "timestamp_pending": provider["timestamp_pending"],
                "sample_failures": failures,
                "sample_pending": pending,
                "sample_checks": checks,
                "sample_observed_at": sample.get("observed_at") if isinstance(sample, dict) else None,
                "credential_or_entitlement_present": (
                    sample.get("credential_or_entitlement_present") if isinstance(sample, dict) else None
                ),
            }
        )
    readiness_counts = dict(Counter(row["poc_readiness"] for row in provider_rows))
    sample_ready_by_layer = {
        layer: [
            row["provider_id"]
            for row in provider_rows
            if row["layer"] == layer and row["poc_readiness"] == "sample_ready"
        ]
        for layer in sorted(ALLOWED_LAYERS)
    }
    required_count = max(
        2,
        int((registry.get("layer_readiness_rule") or {}).get("required_ready_candidate_count") or 2),
    )
    full713_ready = all(len(provider_ids) >= required_count for provider_ids in sample_ready_by_layer.values())
    identity = {
        "registry_id": registry.get("registry_id"),
        "event_set_id": event_set.get("event_set_id"),
        "providers": provider_rows,
        "sample_ready_by_layer": sample_ready_by_layer,
    }
    return {
        "artifact_type": "external_context_poc_readiness",
        "schema_version": "external_context_poc_readiness.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_id": registry.get("registry_id"),
        "event_set_id": event_set.get("event_set_id"),
        "baseline_contract": registry.get("baseline_contract"),
        "gate_status": "passed" if full713_ready else "blocked",
        "full713_external_context_ready": full713_ready,
        "v3_signal_changed": False,
        "claim_ceiling": "provider_and_sample_readiness_only_no_weight_backtest",
        "provider_readiness_counts": readiness_counts,
        "sample_ready_provider_ids_by_layer": sample_ready_by_layer,
        "providers": provider_rows,
        "readiness_digest": hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest(),
    }


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sample_metrics_by_provider(sample_metrics: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not sample_metrics:
        return {}
    rows = sample_metrics.get("providers")
    if isinstance(rows, dict):
        return {str(key): value for key, value in rows.items() if isinstance(value, dict)}
    if isinstance(rows, list):
        return {
            str(row.get("provider_id")): row
            for row in rows
            if isinstance(row, dict) and row.get("provider_id")
        }
    return {}


def _audit_provider(
    provider: dict[str, Any],
    *,
    hard_gate_ids: list[str],
    sample: dict[str, Any] | None,
    scorecard_dimensions: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_id = str(provider.get("provider_id") or "").strip()
    layer = str(provider.get("layer") or "").strip()
    if not provider_id:
        raise ValueError("provider_id is required")
    if layer not in ALLOWED_LAYERS:
        raise ValueError(f"unsupported provider layer: {layer}")
    gate_evidence = provider.get("gate_evidence")
    if not isinstance(gate_evidence, dict):
        raise ValueError(f"provider {provider_id} must define gate_evidence")

    documentation_failures: list[str] = []
    documentation_pending: list[str] = []
    gate_rows: list[dict[str, Any]] = []
    for gate_id in hard_gate_ids:
        evidence = gate_evidence.get(gate_id)
        if not isinstance(evidence, dict):
            status = "pending"
            note = "missing_gate_evidence"
            evidence_urls: list[str] = []
        else:
            status = str(evidence.get("status") or "pending")
            note = str(evidence.get("note") or "")
            evidence_urls = [str(url) for url in evidence.get("evidence_urls") or []]
        if status not in KNOWN_GATE_STATUSES:
            raise ValueError(f"provider {provider_id} gate {gate_id} has unsupported status {status}")
        if status == "fail":
            documentation_failures.append(gate_id)
        elif status == "pending":
            documentation_pending.append(gate_id)
        gate_rows.append({"gate_id": gate_id, "status": status, "note": note, "evidence_urls": evidence_urls})

    sample_checks = [
        _evaluate_sample_gate(gate, sample)
        for gate in provider.get("sample_gates") or []
        if isinstance(gate, dict)
    ]
    sample_failures = [str(row["gate_id"]) for row in sample_checks if row["status"] == "fail"]
    sample_pending = [str(row["gate_id"]) for row in sample_checks if row["status"] == "pending"]
    timestamp_checks = _audit_time_lineage(provider)
    timestamp_failures = [row["field"] for row in timestamp_checks if row["status"] == "fail"]
    timestamp_pending = [row["field"] for row in timestamp_checks if row["status"] == "pending"]
    scorecard = _audit_scorecard(provider, scorecard_dimensions=scorecard_dimensions)
    limitations = [str(value) for value in provider.get("limitations") or []]
    if timestamp_failures:
        audit_status = "eliminated"
    elif documentation_failures or sample_failures:
        audit_status = "blocked"
    elif documentation_pending or sample_pending or timestamp_pending:
        audit_status = "pending"
    else:
        audit_status = "ready"
    if str(provider.get("target_role")) == "discovery_only" and audit_status == "ready":
        audit_status = "discovery_only"

    return {
        "provider_id": provider_id,
        "provider_name": provider.get("provider_name"),
        "layer": layer,
        "coverage_scope": provider.get("coverage_scope") or [],
        "target_role": provider.get("target_role") or "candidate",
        "independence_group": provider.get("independence_group") or provider_id,
        "cost": provider.get("cost") or {},
        "audit_status": audit_status,
        "elimination_reason": (
            "required_time_lineage_field_explicitly_unavailable"
            if timestamp_failures
            else None
        ),
        "documentation_failures": documentation_failures,
        "documentation_pending": documentation_pending,
        "sample_failures": sample_failures,
        "sample_pending": sample_pending,
        "timestamp_failures": timestamp_failures,
        "timestamp_pending": timestamp_pending,
        "timestamp_checks": timestamp_checks,
        "scorecard": scorecard,
        "gate_evidence": gate_rows,
        "sample_checks": sample_checks,
        "limitations": limitations,
        "next_action": provider.get("next_action"),
    }


def _audit_time_lineage(provider: dict[str, Any]) -> list[dict[str, Any]]:
    contract = provider.get("timestamp_contract")
    if contract is None:
        return []
    if not isinstance(contract, dict):
        raise ValueError(f"provider {provider.get('provider_id')} timestamp_contract must be an object")
    checks: list[dict[str, Any]] = []
    for field in REQUIRED_TIME_LINEAGE_FIELDS:
        evidence = contract.get(field)
        if not isinstance(evidence, dict):
            status = "pending"
            note = "missing_timestamp_contract"
            evidence_urls: list[str] = []
        else:
            status = str(evidence.get("status") or "pending")
            note = str(evidence.get("note") or "")
            evidence_urls = [str(url) for url in evidence.get("evidence_urls") or []]
        if status not in KNOWN_GATE_STATUSES:
            raise ValueError(
                f"provider {provider.get('provider_id')} timestamp field {field} has unsupported status {status}"
            )
        checks.append({"field": field, "status": status, "note": note, "evidence_urls": evidence_urls})
    return checks


def _audit_scorecard(
    provider: dict[str, Any],
    *,
    scorecard_dimensions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not scorecard_dimensions:
        return {"status": "not_configured", "weighted_score_100": None, "dimensions": []}
    evidence = provider.get("score_evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    rows: list[dict[str, Any]] = []
    weighted_total = 0.0
    total_weight = 0.0
    complete = True
    for dimension in scorecard_dimensions:
        dimension_id = str(dimension.get("dimension_id") or "").strip()
        if not dimension_id:
            raise ValueError("scorecard dimension_id is required")
        weight = float(dimension.get("weight") or 0.0)
        observed = evidence.get(dimension_id)
        score = observed.get("score") if isinstance(observed, dict) else None
        note = str(observed.get("note") or "") if isinstance(observed, dict) else "missing_score_evidence"
        if score is None:
            complete = False
            numeric_score = None
        else:
            numeric_score = float(score)
            if not 0.0 <= numeric_score <= 5.0:
                raise ValueError(
                    f"provider {provider.get('provider_id')} score {dimension_id} must be between 0 and 5"
                )
            weighted_total += numeric_score * weight
        total_weight += weight
        rows.append(
            {
                "dimension_id": dimension_id,
                "weight": weight,
                "score": numeric_score,
                "note": note,
            }
        )
    weighted_score = round(weighted_total / (5.0 * total_weight) * 100.0, 3) if complete and total_weight > 0 else None
    return {
        "status": "complete" if complete else "pending",
        "weighted_score_100": weighted_score,
        "dimensions": rows,
    }


def _evaluate_sample_gate(gate: dict[str, Any], sample: dict[str, Any] | None) -> dict[str, Any]:
    gate_id = str(gate.get("gate_id") or gate.get("metric") or "sample_gate")
    metric = str(gate.get("metric") or "")
    operator = str(gate.get("operator") or "eq")
    threshold = gate.get("threshold")
    value = _nested_value(sample, metric) if sample is not None else None
    if value is None:
        status = "pending"
    else:
        status = "pass" if _compare_metric(value, operator=operator, threshold=threshold) else "fail"
    return {
        "gate_id": gate_id,
        "metric": metric,
        "operator": operator,
        "threshold": threshold,
        "observed": value,
        "status": status,
    }


def _nested_value(payload: dict[str, Any] | None, path: str) -> Any:
    value: Any = payload
    for key in path.split(".") if path else []:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _compare_metric(value: Any, *, operator: str, threshold: Any) -> bool:
    if operator == "eq":
        return value == threshold
    if operator == "gte":
        return float(value) >= float(threshold)
    if operator == "lte":
        return float(value) <= float(threshold)
    if operator == "date_lte":
        return date.fromisoformat(str(value)) <= date.fromisoformat(str(threshold))
    if operator == "date_gte":
        return date.fromisoformat(str(value)) >= date.fromisoformat(str(threshold))
    raise ValueError(f"unsupported sample gate operator: {operator}")


def probe_tushare_external_context_transport(
    *,
    base_url: str,
    token: str,
    stock_st_date: date,
    index_start: date,
    index_end: date,
    index_codes: tuple[str, ...] = ("SPX", "IXIC", "HKTECH"),
    news_days: tuple[date, ...] = (),
    news_hours: tuple[int, ...] = tuple(range(24)),
    max_attempts: int = 3,
    max_batch_seconds: float = 60.0,
    request_fn: Callable[..., dict[str, Any] | None] = _post_tushare,
    retry_delay_seconds: float = 0.25,
) -> dict[str, Any]:
    if not token.strip():
        raise ValueError("Tushare token is required")
    if index_start > index_end:
        raise ValueError("index_start must be <= index_end")
    if any(hour < 0 or hour > 23 for hour in news_hours):
        raise ValueError("news_hours must be between 0 and 23")
    started_at = time.monotonic()

    stock_response = _request_with_retry(
        request_fn,
        base_url=base_url,
        token=token,
        api_name="stock_st",
        params={"trade_date": stock_st_date.strftime("%Y%m%d")},
        fields="ts_code,name,trade_date,type,type_name",
        max_attempts=max_attempts,
        retry_delay_seconds=retry_delay_seconds,
    )
    stock_rows = _response_rows(stock_response["response"])
    stock_metric = {
        "provider_id": "tushare_stock_st",
        "api_code": stock_response["code"],
        "attempt_count": stock_response["attempt_count"],
        "provider_message": stock_response["message"],
        "sample_date": stock_st_date.isoformat(),
        "record_count": len(stock_rows),
        "response_rows_digest": _rows_digest(stock_rows),
        "timestamp_parse_rate": _compact_date_parse_rate(stock_rows, "trade_date"),
        "stable_derived_id_unique_rate": _derived_key_unique_rate(stock_rows, ("ts_code", "trade_date", "type")),
        "required_fields_present": _required_fields_present(stock_rows, {"ts_code", "trade_date", "type"}),
    }

    index_metrics: dict[str, Any] = {}
    for code in index_codes:
        result = _request_with_retry(
            request_fn,
            base_url=base_url,
            token=token,
            api_name="index_global",
            params={
                "ts_code": code,
                "start_date": index_start.strftime("%Y%m%d"),
                "end_date": index_end.strftime("%Y%m%d"),
            },
            fields="ts_code,trade_date,open,close,high,low,vol",
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
        rows = _response_rows(result["response"])
        index_metrics[code] = {
            "api_code": result["code"],
            "attempt_count": result["attempt_count"],
            "provider_message": result["message"],
            "record_count": len(rows),
            "response_rows_digest": _rows_digest(rows),
            "timestamp_parse_rate": _compact_date_parse_rate(rows, "trade_date"),
            "stable_derived_id_unique_rate": _derived_key_unique_rate(rows, ("ts_code", "trade_date")),
            "required_fields_present": _required_fields_present(rows, {"ts_code", "trade_date", "open", "close"}),
        }
    index_metric = {
        "provider_id": "tushare_index_global",
        "coverage_start": index_start.isoformat(),
        "coverage_end": index_end.isoformat(),
        "requested_index_count": len(index_codes),
        "successful_index_count": sum(row["api_code"] == 0 for row in index_metrics.values()),
        "all_requests_succeeded": all(row["api_code"] == 0 for row in index_metrics.values()),
        "indices": index_metrics,
    }

    news_metrics: dict[str, Any] = {}
    for news_day in news_days:
        day_rows: list[dict[str, Any]] = []
        shard_results: list[dict[str, Any]] = []
        for hour in news_hours:
            if max_batch_seconds > 0 and time.monotonic() - started_at >= max_batch_seconds:
                shard_results.append(
                    {
                        "hour": hour,
                        "api_code": "batch_budget_exhausted",
                        "attempt_count": 0,
                        "record_count": 0,
                    }
                )
                continue
            result = _request_with_retry(
                request_fn,
                base_url=base_url,
                token=token,
                api_name="major_news",
                params={
                    "start_date": f"{news_day.isoformat()} {hour:02d}:00:00",
                    "end_date": f"{news_day.isoformat()} {hour:02d}:59:59",
                },
                fields="title,pub_time,src",
                max_attempts=max_attempts,
                retry_delay_seconds=retry_delay_seconds,
            )
            rows = _response_rows(result["response"])
            day_rows.extend(rows)
            shard_results.append(
                {
                    "hour": hour,
                    "api_code": result["code"],
                    "attempt_count": result["attempt_count"],
                    "record_count": len(rows),
                    "provider_message": result["message"],
                }
            )
        source_counts = Counter(str(row.get("src") or "unknown") for row in day_rows)
        news_metrics[news_day.isoformat()] = {
            "full_day_shards_requested": set(news_hours) == set(range(24)),
            "request_count": len(shard_results),
            "successful_request_count": sum(row["api_code"] == 0 for row in shard_results),
            "all_shards_succeeded": all(row["api_code"] == 0 for row in shard_results),
            "record_count_before_dedupe": len(day_rows),
            "record_count_after_dedupe": _derived_key_count(day_rows, ("src", "pub_time", "title")),
            "timestamp_parse_rate": _iso_datetime_parse_rate(day_rows, "pub_time"),
            "stable_derived_id_unique_rate": _derived_key_unique_rate(day_rows, ("src", "pub_time", "title")),
            "source_count": len(source_counts),
            "top_source_counts": dict(source_counts.most_common(8)),
            "max_shard_record_count": max((row["record_count"] for row in shard_results), default=0),
            "saturated_shard_count": sum(row["record_count"] >= 800 for row in shard_results),
            "shards": shard_results,
        }
    news_metric = {
        "provider_id": "tushare_major_news",
        "sample_day_count": len(news_days),
        "all_requested_shards_succeeded": all(
            row["all_shards_succeeded"] for row in news_metrics.values()
        ) if news_days else True,
        "all_days_transport_complete": bool(news_days)
        and all(
            row["full_day_shards_requested"]
            and row["all_shards_succeeded"]
            and row["saturated_shard_count"] == 0
            for row in news_metrics.values()
        ),
        "minimum_timestamp_parse_rate": min(
            (row["timestamp_parse_rate"] for row in news_metrics.values() if row["timestamp_parse_rate"] is not None),
            default=None,
        ),
        "minimum_stable_derived_id_unique_rate": min(
            (
                row["stable_derived_id_unique_rate"]
                for row in news_metrics.values()
                if row["stable_derived_id_unique_rate"] is not None
            ),
            default=None,
        ),
        "days": news_metrics,
    }

    return {
        "artifact_type": "external_context_transport_poc",
        "poc_version": TUSHARE_EXTERNAL_CONTEXT_POC_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "tushare",
        "credential_present": True,
        "raw_payload_retained": False,
        "raw_content_retained": False,
        "network_used": True,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "max_batch_seconds": max_batch_seconds,
        "v3_signal_changed": False,
        "claim_ceiling": "transport_schema_and_permission_poc_only",
        "providers": {
            "tushare_stock_st": stock_metric,
            "tushare_index_global": index_metric,
            "tushare_major_news": news_metric,
        },
    }


def probe_tushare_external_context_from_session(
    session: Session,
    *,
    stock_st_date: date,
    index_start: date,
    index_end: date,
    index_codes: tuple[str, ...],
    news_days: tuple[date, ...],
    news_hours: tuple[int, ...] = tuple(range(24)),
    max_attempts: int = 3,
    max_batch_seconds: float = 60.0,
) -> dict[str, Any]:
    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )
    if credential is None or not credential.access_token:
        return {
            "artifact_type": "external_context_transport_poc",
            "poc_version": TUSHARE_EXTERNAL_CONTEXT_POC_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "provider": "tushare",
            "credential_present": False,
            "gate_status": "blocked",
            "blocker": "enabled_tushare_credential_not_configured",
            "v3_signal_changed": False,
            "claim_ceiling": "transport_schema_and_permission_poc_only",
            "providers": {},
        }
    payload = probe_tushare_external_context_transport(
        base_url=(credential.base_url or DEFAULT_TUSHARE_BASE_URL).strip(),
        token=credential.access_token.strip(),
        stock_st_date=stock_st_date,
        index_start=index_start,
        index_end=index_end,
        index_codes=index_codes,
        news_days=news_days,
        news_hours=news_hours,
        max_attempts=max_attempts,
        max_batch_seconds=max_batch_seconds,
    )
    stock_ready = payload["providers"]["tushare_stock_st"]["api_code"] == 0
    index_ready = payload["providers"]["tushare_index_global"]["all_requests_succeeded"]
    news_ready = payload["providers"]["tushare_major_news"]["all_requested_shards_succeeded"]
    payload["gate_status"] = "passed" if stock_ready and index_ready and news_ready else "blocked"
    return payload


def _request_with_retry(
    request_fn: Callable[..., dict[str, Any] | None],
    *,
    base_url: str,
    token: str,
    api_name: str,
    params: dict[str, Any],
    fields: str,
    max_attempts: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    response: dict[str, Any] | None = None
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        response = request_fn(
            base_url=base_url,
            token=token,
            api_name=api_name,
            params=params,
            fields=fields,
        )
        code = response.get("code") if isinstance(response, dict) else None
        message = _safe_provider_message(response, secret=token)
        if code in {0, None} and isinstance(response, dict):
            return {"response": response, "code": code, "attempt_count": attempt, "message": message}
        if code == 40203:
            return {"response": response, "code": code, "attempt_count": attempt, "message": message}
        if attempt < attempts and retry_delay_seconds > 0:
            time.sleep(min(retry_delay_seconds * attempt, 1.0))
    return {
        "response": response,
        "code": response.get("code") if isinstance(response, dict) else None,
        "attempt_count": attempts,
        "message": _safe_provider_message(response, secret=token),
    }


def _safe_provider_message(response: dict[str, Any] | None, *, secret: str) -> str | None:
    if not isinstance(response, dict):
        return "no_response"
    message = str(response.get("msg") or "").strip()
    if secret:
        message = message.replace(secret, "[redacted]")
    return message[:200] or None


def _response_rows(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response, dict) else None
    fields = data.get("fields") if isinstance(data, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(fields, list) or not isinstance(items, list):
        return []
    return [
        dict(zip(fields, item, strict=False))
        for item in items
        if isinstance(item, list) and len(item) == len(fields)
    ]


def _canonical_key(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    canonical = "|".join(str(row.get(field) or "") for field in fields)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rows_digest(rows: list[dict[str, Any]]) -> str:
    canonical_rows = sorted(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        for row in rows
    )
    return hashlib.sha256("\n".join(canonical_rows).encode("utf-8")).hexdigest()


def _derived_key_count(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> int:
    return len({_canonical_key(row, fields) for row in rows})


def _derived_key_unique_rate(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> float | None:
    return round(_derived_key_count(rows, fields) / len(rows), 6) if rows else None


def _required_fields_present(rows: list[dict[str, Any]], required: set[str]) -> bool:
    return bool(rows) and all(required.issubset(row) for row in rows)


def _compact_date_parse_rate(rows: list[dict[str, Any]], field: str) -> float | None:
    parsed = 0
    for row in rows:
        try:
            datetime.strptime(str(row.get(field) or ""), "%Y%m%d")
            parsed += 1
        except ValueError:
            pass
    return round(parsed / len(rows), 6) if rows else None


def _iso_datetime_parse_rate(rows: list[dict[str, Any]], field: str) -> float | None:
    parsed = 0
    for row in rows:
        try:
            datetime.fromisoformat(str(row.get(field) or "").replace("Z", "+00:00"))
            parsed += 1
        except ValueError:
            pass
    return round(parsed / len(rows), 6) if rows else None


def write_external_context_artifact(payload: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
