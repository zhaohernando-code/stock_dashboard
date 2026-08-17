from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from calendar import monthrange
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.external_context_news_summary import NEWS_STORAGE_HARD_CAP_BYTES
from ashare_evidence.external_context_replay import (
    ExternalContextStorageBudget,
    materialize_external_context_pilot,
    replay_external_context_offline,
)
from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, account_trade_eligibility
from ashare_evidence.models import ProviderCredential
from ashare_evidence.tushare_transport import (
    DEFAULT_TUSHARE_BASE_URL,
    post_tushare,
    secure_tushare_base_url,
)

SCHEMA_VERSION = "tushare_structured_event_acquisition_plan.v1"
CHECKPOINT_SCHEMA_VERSION = "tushare_structured_event_checkpoint.v1"
PROVIDER_ID = "tushare_structured_events"
SHANGHAI = ZoneInfo("Asia/Shanghai")
ATTRIBUTION = "hernando_zhao / Tushare"
MAX_ROWS_PER_RESPONSE = 5_000
SUMMARY_MAX_CHARS = 1_000

ENDPOINTS: dict[str, dict[str, Any]] = {
    "forecast_vip": {
        "event_type": "earnings_forecast",
        "availability_evidence_ref": "https://tushare.pro/document/2?doc_id=45",
        "fields": (
            "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,"
            "last_parent_net,first_ann_date,summary,change_reason"
        ),
    },
    "express_vip": {
        "event_type": "earnings_express",
        "availability_evidence_ref": "https://tushare.pro/document/1?doc_id=108",
        "fields": (
            "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,"
            "total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,bps,yoy_sales,yoy_op,"
            "yoy_tp,yoy_dedu_np,yoy_eps,yoy_roe,growth_assets,yoy_equity,growth_bps,or_last_year,"
            "op_last_year,tp_last_year,np_last_year,eps_last_year,open_net_assets,open_bps,"
            "perf_summary,is_audit,remark"
        ),
    },
    "repurchase": {
        "event_type": "share_repurchase",
        "availability_evidence_ref": "https://tushare.pro/document/2?doc_id=124",
        "fields": "ts_code,ann_date,end_date,proc,exp_date,vol,amount,high_limit,low_limit",
    },
}
COMPACT_ENDPOINT_FIELDS = {
    "forecast_vip": (
        "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,"
        "last_parent_net,first_ann_date"
    ),
    "express_vip": (
        "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,"
        "total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,bps,yoy_sales,yoy_op,"
        "yoy_tp,yoy_dedu_np,yoy_eps,yoy_roe,growth_assets,yoy_equity,growth_bps,or_last_year,"
        "op_last_year,tp_last_year,np_last_year,eps_last_year,open_net_assets,open_bps,is_audit"
    ),
    "repurchase": ENDPOINTS["repurchase"]["fields"],
}


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _parse_api_rows(response: dict[str, Any] | None, *, api_name: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise RuntimeError(f"Tushare {api_name} returned no response")
    if int(response.get("code") or 0) != 0:
        message = str(response.get("msg") or response.get("message") or "unknown provider error")
        raise RuntimeError(f"Tushare {api_name} failed: {message}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Tushare {api_name} returned an invalid data envelope")
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        raise RuntimeError(f"Tushare {api_name} returned invalid fields/items")
    if len(items) >= MAX_ROWS_PER_RESPONSE:
        raise RuntimeError(f"Tushare {api_name} response reached the safe row ceiling")
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, list) or len(item) != len(fields):
            raise RuntimeError(f"Tushare {api_name} returned a malformed row")
        rows.append(dict(zip(fields, item, strict=False)))
    return rows


def _quarter_ends(start: date, end: date) -> list[str]:
    periods: list[str] = []
    maximum_period = next(
        date(end.year, month, day)
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31))
        if date(end.year, month, day) >= end
    )
    for year in range(start.year - 1, end.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            period = date(year, month, day)
            if period >= date(start.year - 1, 12, 31) and period <= maximum_period:
                periods.append(period.strftime("%Y%m%d"))
    return periods


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        window_start = max(cursor, start)
        window_end = min(date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1]), end)
        windows.append((window_start, window_end))
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
    return windows


def build_tushare_structured_event_plan(*, start_date: str, end_date: str) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    tasks: list[dict[str, Any]] = []
    for api_name in ("forecast_vip", "express_vip"):
        for period in _quarter_ends(start, end):
            identity = {"api_name": api_name, "params": {"period": period}}
            tasks.append({**identity, "task_id": f"tushare-event-{_digest(identity)[:24]}"})
    for window_start, window_end in _month_windows(start, end):
        identity = {
            "api_name": "repurchase",
            "params": {
                "start_date": window_start.strftime("%Y%m%d"),
                "end_date": window_end.strftime("%Y%m%d"),
            },
        }
        tasks.append({**identity, "task_id": f"tushare-event-{_digest(identity)[:24]}"})
    tasks.sort(key=lambda row: (row["api_name"], json.dumps(row["params"], sort_keys=True)))
    identity = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "tasks": tasks,
        "provider_id": PROVIDER_ID,
        "account_profile": ACCOUNT_PROFILE_NEW_RETAIL_CASH,
    }
    return {
        "artifact_type": "tushare_structured_event_acquisition_plan",
        "schema_version": SCHEMA_VERSION,
        "plan_id": f"tushare-structured-events-{_digest(identity)[:24]}",
        "generated_at": datetime.now(UTC).isoformat(),
        **identity,
        "task_count": len(tasks),
        "usage_contract": {
            "use": "personal_internal_research_only",
            "authorized_by_user": True,
            "attribution": ATTRIBUTION,
            "redistribution": "forbidden",
            "article_body_retained": False,
            "structured_summaries_only": True,
        },
        "temporal_contract": {
            "provider_timestamp_granularity": "announcement_date_only",
            "provider_published_at": "announcement_date_start_Asia_Shanghai",
            "available_from": "announcement_date_end_Asia_Shanghai",
            "decision_rule": "available_from <= decision_cutoff",
            "same_day_signal_use": False,
            "provider_revision_id_available": False,
            "revision_fallback": "content_sha256_not_provider_revision_lineage",
        },
        "storage_contract": {
            "hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
            "content": "requested_structured_fields_and_source_summaries_only_no_document_body",
        },
        "claim_ceiling": "provisional_structured_event_research_input_not_production_vendor_data",
        "v3_signal_changed": False,
    }


def _compact_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized[:SUMMARY_MAX_CHARS] or None


def _number(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _forecast_payload(row: dict[str, Any]) -> dict[str, Any]:
    p_min = _number(row.get("p_change_min"))
    p_max = _number(row.get("p_change_max"))
    n_min = _number(row.get("net_profit_min"))
    n_max = _number(row.get("net_profit_max"))
    return {
        "forecast_type": _compact_text(row.get("type")),
        "profit_change_min_pct": p_min,
        "profit_change_max_pct": p_max,
        "profit_change_mid_pct": (
            (p_min + p_max) / 2 if p_min is not None and p_max is not None else p_min if p_min is not None else p_max
        ),
        "net_profit_min_10k_cny": n_min,
        "net_profit_max_10k_cny": n_max,
        "net_profit_mid_10k_cny": (
            (n_min + n_max) / 2 if n_min is not None and n_max is not None else n_min if n_min is not None else n_max
        ),
        "last_parent_net_10k_cny": _number(row.get("last_parent_net")),
        "first_announcement_date": row.get("first_ann_date") or None,
        "summary": _compact_text(row.get("summary")),
        "change_reason_summary": _compact_text(row.get("change_reason")),
    }


def _express_payload(row: dict[str, Any]) -> dict[str, Any]:
    numeric_fields = (
        "revenue",
        "operate_profit",
        "total_profit",
        "n_income",
        "total_assets",
        "total_hldr_eqy_exc_min_int",
        "diluted_eps",
        "diluted_roe",
        "yoy_net_profit",
        "bps",
        "yoy_sales",
        "yoy_op",
        "yoy_tp",
        "yoy_dedu_np",
        "yoy_eps",
        "yoy_roe",
        "growth_assets",
        "yoy_equity",
        "growth_bps",
        "or_last_year",
        "op_last_year",
        "tp_last_year",
        "np_last_year",
        "eps_last_year",
        "open_net_assets",
        "open_bps",
    )
    return {
        "metrics": {field: _number(row.get(field)) for field in numeric_fields},
        "performance_summary": _compact_text(row.get("perf_summary")),
        "audit_status": row.get("is_audit"),
        "remark_summary": _compact_text(row.get("remark")),
    }


def _repurchase_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "progress": _compact_text(row.get("proc")),
        "end_date": row.get("end_date") or None,
        "expiry_date": row.get("exp_date") or None,
        "volume_shares": _number(row.get("vol")),
        "amount_cny": _number(row.get("amount")),
        "price_high_cny": _number(row.get("high_limit")),
        "price_low_cny": _number(row.get("low_limit")),
        "positive_buy_trigger_allowed": False,
    }


def normalize_tushare_structured_event_rows(
    api_name: str,
    rows: Iterable[dict[str, Any]],
    *,
    start: date,
    end: date,
    retrieved_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if api_name not in ENDPOINTS:
        raise ValueError(f"unsupported Tushare structured event endpoint: {api_name}")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    records: list[dict[str, Any]] = []
    excluded = {"outside_window": 0, "account_board": 0, "invalid_date": 0, "exact_duplicate": 0}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        symbol = str(row.get("ts_code") or "").strip().upper()
        raw_ann_date = str(row.get("ann_date") or "")
        try:
            ann_date = datetime.strptime(raw_ann_date, "%Y%m%d").date()
        except ValueError:
            excluded["invalid_date"] += 1
            continue
        if ann_date < start or ann_date > end:
            excluded["outside_window"] += 1
            continue
        structural = account_trade_eligibility(
            symbol,
            stock_profile=None,
            account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            as_of=ann_date,
            profile_is_point_in_time=False,
        )
        if not structural["tradable"]:
            excluded["account_board"] += 1
            continue
        published_at = datetime.combine(ann_date, datetime_time.min, tzinfo=SHANGHAI)
        available_from = datetime.combine(ann_date, datetime_time.max, tzinfo=SHANGHAI)
        if available_from.astimezone(UTC) > retrieved_at.astimezone(UTC):
            raise ValueError(f"future structured event returned by provider: {api_name}:{symbol}:{raw_ann_date}")
        raw_payload = {field: row.get(field) for field in str(ENDPOINTS[api_name]["fields"]).split(",")}
        content_hash = _digest(raw_payload)
        identity_parts = [api_name, symbol, raw_ann_date, str(row.get("end_date") or "")]
        if api_name == "repurchase":
            identity_parts.extend([str(row.get("proc") or ""), str(row.get("exp_date") or "")])
        normalized_event_id = ":".join([*identity_parts, content_hash[:16]])
        uniqueness = (normalized_event_id, content_hash)
        if uniqueness in seen:
            excluded["exact_duplicate"] += 1
            continue
        seen.add(uniqueness)
        if api_name == "forecast_vip":
            fact_payload = _forecast_payload(row)
        elif api_name == "express_vip":
            fact_payload = _express_payload(row)
        else:
            fact_payload = _repurchase_payload(row)
        normalized_payload = {
            "channel_scope": "stock_event_increment",
            "provider_api": api_name,
            "symbol": symbol,
            "announcement_date": ann_date.isoformat(),
            "report_period": row.get("end_date") or None,
            "fact": fact_payload,
            "provider_revision_id_available": False,
            "revision_lineage": "content_sha256_only",
            "same_day_signal_use": False,
            "stock_core_remains_primary": True,
        }
        records.append(
            {
                "provider_item_id": f"{api_name}-{content_hash[:24]}",
                "normalized_event_id": normalized_event_id,
                "revision_id": f"content-sha256-{content_hash}",
                "provider_published_at": published_at.isoformat(),
                "provider_updated_at": None,
                "first_seen_at": retrieved_at.isoformat(),
                "available_from": available_from.isoformat(),
                "availability_basis": "provider_published_at_documented",
                "availability_evidence_ref": ENDPOINTS[api_name]["availability_evidence_ref"],
                "event_type": ENDPOINTS[api_name]["event_type"],
                "source_authority": "low_cost_structured_aggregator_not_official_issuer",
                "entities": [symbol],
                "sectors": [],
                "geographies": ["CN"],
                "raw_payload": raw_payload,
                "normalized_payload": normalized_payload,
            }
        )
    records.sort(key=lambda item: (item["available_from"], item["normalized_event_id"], item["revision_id"]))
    return records, excluded


def _write_immutable_gzip(
    path: Path,
    payload: dict[str, Any],
    *,
    storage_budget: ExternalContextStorageBudget,
) -> None:
    rendered = gzip.compress(_canonical_bytes(payload), compresslevel=6, mtime=0)
    if path.exists():
        if path.read_bytes() != rendered:
            raise RuntimeError(f"immutable checkpoint collision: {path}")
        return
    storage_budget.ensure_can_add(len(rendered))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    storage_budget.record_addition(len(rendered))


def _read_checkpoint(path: Path) -> dict[str, Any]:
    payload = json.loads(gzip.decompress(path.read_bytes()))
    if not isinstance(payload, dict) or payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError(f"invalid structured event checkpoint: {path}")
    return payload


def write_tushare_structured_event_plan(path: str | Path, plan: dict[str, Any]) -> Path:
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Tushare structured event plan")
    output = Path(path).expanduser().resolve()
    rendered = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output.exists() and output.read_text(encoding="utf-8") != rendered:
        existing = json.loads(output.read_text(encoding="utf-8"))
        comparable_fields = ("plan_id", "start_date", "end_date", "tasks", "task_count")
        if any(existing.get(field) != plan.get(field) for field in comparable_fields):
            raise RuntimeError(f"immutable plan collision: {output}")
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        output.write_text(rendered, encoding="utf-8")
    return output


def execute_tushare_structured_event_plan(
    session: Session,
    plan: dict[str, Any],
    *,
    artifact_root: str | Path,
    max_tasks_this_run: int = 100,
    min_request_interval_seconds: float = 0.5,
    request_fn: Callable[..., dict[str, Any] | None] = post_tushare,
    sleeper: Callable[[float], None] = time.sleep,
    progress_fn: Callable[[dict[str, Any]], None] | None = None,
    max_transient_attempts: int = 3,
) -> dict[str, Any]:
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Tushare structured event plan")
    usage = plan.get("usage_contract") or {}
    if usage.get("authorized_by_user") is not True or usage.get("redistribution") != "forbidden":
        raise ValueError("structured event acquisition must be authorized for personal use without redistribution")
    if not 1 <= max_tasks_this_run <= 1_000:
        raise ValueError("max_tasks_this_run must be between 1 and 1000")
    if not 0 <= min_request_interval_seconds <= 60:
        raise ValueError("min_request_interval_seconds must be between 0 and 60")
    if not 1 <= max_transient_attempts <= 5:
        raise ValueError("max_transient_attempts must be between 1 and 5")
    credential = session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )
    if credential is None or not credential.access_token:
        raise ValueError("enabled Tushare credential is not configured")
    base_url = secure_tushare_base_url(credential.base_url or DEFAULT_TUSHARE_BASE_URL)
    token = credential.access_token.strip()
    root = Path(artifact_root).expanduser().resolve()
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError("artifact_root cannot be a filesystem root or the home directory")
    root.mkdir(parents=True, exist_ok=True)
    storage_budget = ExternalContextStorageBudget.from_root(root, hard_cap_bytes=NEWS_STORAGE_HARD_CAP_BYTES)
    processed = 0
    skipped = 0
    raw_rows = 0
    retained_rows = 0
    manifest_ids: list[str] = []
    exclusion_counts: dict[str, int] = {}
    retrieved_at = datetime.now(UTC)
    for task in plan.get("tasks") or []:
        checkpoint_path = root / "checkpoints" / f"{task['task_id']}.json.gz"
        if checkpoint_path.exists():
            checkpoint = _read_checkpoint(checkpoint_path)
            skipped += 1
            if checkpoint.get("manifest_id"):
                manifest_ids.append(str(checkpoint["manifest_id"]))
            continue
        if processed >= max_tasks_this_run:
            continue
        if processed:
            sleeper(min_request_interval_seconds)
        api_name = str(task["api_name"])
        response = None
        request_variant = "full_structured_fields_with_source_summaries"
        requested_fields = str(ENDPOINTS[api_name]["fields"])
        variants = [(request_variant, requested_fields)]
        compact_fields = str(COMPACT_ENDPOINT_FIELDS[api_name])
        if compact_fields != requested_fields:
            variants.append(("numeric_structured_fields_transport_fallback", compact_fields))
        for variant, fields in variants:
            for attempt in range(1, max_transient_attempts + 1):
                response = request_fn(
                    base_url=base_url,
                    token=token,
                    api_name=api_name,
                    params=dict(task["params"]),
                    fields=fields,
                    timeout_seconds=20.0,
                )
                if response is not None:
                    request_variant = variant
                    requested_fields = fields
                    break
                if attempt < max_transient_attempts:
                    sleeper(float(2 ** (attempt - 1)))
            if response is not None:
                break
        rows = _parse_api_rows(response, api_name=api_name)
        raw_rows += len(rows)
        records, excluded = normalize_tushare_structured_event_rows(
            api_name,
            rows,
            start=date.fromisoformat(str(plan["start_date"])),
            end=date.fromisoformat(str(plan["end_date"])),
            retrieved_at=retrieved_at,
        )
        retained_rows += len(records)
        for reason, count in excluded.items():
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + count
        manifest_id = None
        manifest_path = None
        if records:
            result = materialize_external_context_pilot(
                {
                    "schema_version": "external_context_pilot_input.v1",
                    "dataset_id": task["task_id"],
                    "provider_id": PROVIDER_ID,
                    "content_class": "official_fact",
                    "source_endpoint": base_url,
                    "license_tier": "personal_noncommercial_research_no_redistribution",
                    "retrieved_at": retrieved_at.isoformat(),
                    "records": records,
                },
                artifact_root=root,
                enforce_root_hard_cap_bytes=NEWS_STORAGE_HARD_CAP_BYTES,
                storage_budget=storage_budget,
            )
            manifest_id = result["manifest"]["manifest_id"]
            manifest_path = result["manifest_path"]
            manifest_ids.append(manifest_id)
        checkpoint = {
            "artifact_type": "tushare_structured_event_checkpoint",
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "plan_id": plan["plan_id"],
            "task_id": task["task_id"],
            "api_name": api_name,
            "params": task["params"],
            "request_variant": request_variant,
            "requested_fields": requested_fields,
            "retrieved_at": retrieved_at.isoformat(),
            "raw_row_count": len(rows),
            "retained_row_count": len(records),
            "exclusion_counts": excluded,
            "manifest_id": manifest_id,
            "manifest_path": manifest_path,
            "network_used": True,
            "v3_signal_changed": False,
        }
        _write_immutable_gzip(checkpoint_path, checkpoint, storage_budget=storage_budget)
        processed += 1
        if progress_fn is not None:
            progress_fn(
                {
                    "completed_tasks": skipped + processed,
                    "total_tasks": int(plan["task_count"]),
                    "api_name": api_name,
                    "raw_row_count": len(rows),
                    "retained_row_count": len(records),
                    "request_variant": request_variant,
                    "root_bytes": storage_budget.used_bytes,
                }
            )
    completed_checkpoints = list((root / "checkpoints").glob("*.json.gz")) if (root / "checkpoints").exists() else []
    used_bytes = storage_budget.used_bytes
    return {
        "artifact_type": "tushare_structured_event_acquisition_run",
        "plan_id": plan["plan_id"],
        "processed_tasks": processed,
        "skipped_completed_tasks": skipped,
        "completed_tasks": len(completed_checkpoints),
        "total_tasks": int(plan["task_count"]),
        "plan_ready": len(completed_checkpoints) == int(plan["task_count"]),
        "raw_rows_this_run": raw_rows,
        "retained_rows_this_run": retained_rows,
        "exclusion_counts_this_run": exclusion_counts,
        "manifest_ids_this_run": sorted(set(manifest_ids)),
        "transport": "https",
        "root_bytes": used_bytes,
        "hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
        "hard_cap_respected": used_bytes <= NEWS_STORAGE_HARD_CAP_BYTES,
        "v3_signal_changed": False,
    }


def verify_tushare_structured_event_replay(
    plan: dict[str, Any],
    *,
    artifact_root: str | Path,
    decision_cutoff: str,
) -> dict[str, Any]:
    root = Path(artifact_root).expanduser().resolve()
    checkpoints = sorted((root / "checkpoints").glob("*.json.gz"))
    verified_files = 0
    visible_records = 0
    manifest_ids: list[str] = []
    for path in checkpoints:
        checkpoint = _read_checkpoint(path)
        manifest_path = checkpoint.get("manifest_path")
        if not manifest_path:
            continue
        replay = replay_external_context_offline(manifest_path, decision_cutoff=decision_cutoff)
        if replay["network_used"] is not False or replay["hash_verification_status"] != "passed":
            raise RuntimeError(f"offline replay verification failed: {manifest_path}")
        verified_files += int(replay["verified_file_count"])
        visible_records += int(replay["selected_record_count"])
        manifest_ids.append(str(replay["manifest_id"]))
    return {
        "artifact_type": "tushare_structured_event_offline_replay_verification",
        "plan_id": plan["plan_id"],
        "completed_tasks": len(checkpoints),
        "total_tasks": int(plan["task_count"]),
        "plan_ready": len(checkpoints) == int(plan["task_count"]),
        "manifest_count": len(manifest_ids),
        "manifest_scope_digest": _digest(sorted(manifest_ids)),
        "verified_file_count": verified_files,
        "visible_record_count": visible_records,
        "decision_cutoff": decision_cutoff,
        "network_used": False,
        "hash_verification_status": "passed",
        "v3_signal_changed": False,
        "claim_ceiling": "offline_replay_integrity_and_structured_event_coverage_only",
    }


__all__ = [
    "build_tushare_structured_event_plan",
    "execute_tushare_structured_event_plan",
    "normalize_tushare_structured_event_rows",
    "verify_tushare_structured_event_replay",
    "write_tushare_structured_event_plan",
]
