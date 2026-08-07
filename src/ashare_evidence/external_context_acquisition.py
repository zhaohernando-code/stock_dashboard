from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import sqlite3
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from ashare_evidence.external_context_news_summary import (
    NEWS_STORAGE_HARD_CAP_BYTES,
    NEWS_STORAGE_TARGET_BYTES,
)
from ashare_evidence.external_context_public_sources import (
    CNINFO_RELEVANCE_RULE_VERSION,
    classify_cninfo_materiality_title,
    fetch_cninfo_announcement_poc,
    probe_gdelt_daily_public_discovery,
)
from ashare_evidence.external_context_replay import ExternalContextStorageBudget, materialize_external_context_pilot
from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, account_trade_eligibility

CNINFO_PERSONAL_PLAN_VERSION = "cninfo_personal_historical_acquisition_plan.v1"
CNINFO_PERSONAL_RUN_VERSION = "cninfo_personal_historical_acquisition_run.v1"
GDELT_MULTIDAY_CANARY_VERSION = "gdelt_multiday_relevance_canary.v1"
CNINFO_PERSONAL_LICENSE_TIER = "personal_internal_research_user_authorized_no_redistribution"
CNINFO_PERSONAL_ATTRIBUTION = "hernando_zhao"
CNINFO_PERSONAL_DEFAULT_REQUEST_INTERVAL_SECONDS = 1.0
CNINFO_PERSONAL_MAX_TASKS_PER_RUN = 100
CNINFO_PERSONAL_MAX_TRANSIENT_ATTEMPTS = 2


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _write_immutable(
    path: Path,
    payload: dict[str, Any],
    *,
    storage_budget: ExternalContextStorageBudget,
) -> None:
    rendered = _canonical_bytes(payload) + b"\n"
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


def _write_immutable_gzip(
    path: Path,
    payload: dict[str, Any],
    *,
    storage_budget: ExternalContextStorageBudget,
) -> None:
    compressed = gzip.compress(_canonical_bytes(payload), compresslevel=6, mtime=0)
    if path.exists():
        if path.read_bytes() != compressed:
            raise RuntimeError(f"immutable checkpoint collision: {path}")
        return
    storage_budget.ensure_can_add(len(compressed))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(compressed)
        handle.flush()
        os.fsync(handle.fileno())
    storage_budget.record_addition(len(compressed))


def _read_gzip_json(path: Path) -> dict[str, Any]:
    payload = json.loads(gzip.decompress(path.read_bytes()))
    if not isinstance(payload, dict):
        raise ValueError(f"checkpoint must contain an object: {path}")
    return payload


def _task_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=365), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def build_cninfo_personal_acquisition_plan(
    *,
    database_path: str | Path,
    start_date: str,
    end_date: str,
    max_symbols: int | None = None,
    requested_symbols: list[str] | None = None,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    if max_symbols is not None and (max_symbols < 1 or max_symbols > 10_000):
        raise ValueError("max_symbols must be between 1 and 10000")
    normalized_requested_symbols = sorted(
        {str(symbol).strip().upper() for symbol in (requested_symbols or []) if str(symbol).strip()}
    )
    if requested_symbols is not None and not normalized_requested_symbols:
        raise ValueError("requested_symbols must contain at least one symbol when provided")
    if len(normalized_requested_symbols) > 10_000:
        raise ValueError("requested_symbols cannot contain more than 10000 symbols")
    resolved_path = Path(database_path).expanduser().resolve()
    if not resolved_path.is_file():
        raise ValueError(f"database_path does not exist: {resolved_path}")
    connection = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                s.symbol AS symbol,
                MIN(date(m.observed_at)) AS first_eligible_price_date,
                MAX(date(m.observed_at)) AS last_eligible_price_date,
                MIN(m.close_price) AS min_unadjusted_close,
                MAX(m.close_price) AS max_unadjusted_close,
                COUNT(*) AS eligible_price_day_count
            FROM market_bars AS m
            JOIN stocks AS s ON s.id = m.stock_id
            WHERE m.timeframe = '1d'
              AND date(m.observed_at) BETWEEN ? AND ?
              AND m.close_price > 0
              AND m.close_price <= 200
            GROUP BY s.symbol
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    finally:
        connection.close()
    symbols: list[dict[str, Any]] = []
    requested_symbol_set = set(normalized_requested_symbols)
    for row in rows:
        symbol = str(row["symbol"])
        if requested_symbol_set and symbol not in requested_symbol_set:
            continue
        structural = account_trade_eligibility(
            symbol,
            stock_profile=None,
            account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            as_of=start,
            profile_is_point_in_time=False,
        )
        if not structural["tradable"]:
            continue
        symbols.append(
            {
                "symbol": symbol,
                "provider_symbol": symbol.split(".", 1)[0],
                "first_eligible_price_date": row["first_eligible_price_date"],
                "last_eligible_price_date": row["last_eligible_price_date"],
                "min_unadjusted_close": float(row["min_unadjusted_close"]),
                "max_unadjusted_close": float(row["max_unadjusted_close"]),
                "eligible_price_day_count": int(row["eligible_price_day_count"]),
                "pit_risk_status_verified": False,
            }
        )
    symbols.sort(key=lambda row: hashlib.sha256(f"{start}:{end}:{row['symbol']}".encode()).hexdigest())
    resolved_symbols = {str(row["symbol"]) for row in symbols}
    missing_requested_symbols = sorted(requested_symbol_set - resolved_symbols)
    if missing_requested_symbols:
        raise ValueError(
            "requested symbols are absent from the personal PIT-eligible universe: "
            + ", ".join(missing_requested_symbols)
        )
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    tasks: list[dict[str, Any]] = []
    for symbol in symbols:
        for window_start, window_end in _task_windows(start, end):
            identity = {
                "symbol": symbol["symbol"],
                "provider_symbol": symbol["provider_symbol"],
                "start_date": window_start.isoformat(),
                "end_date": window_end.isoformat(),
            }
            tasks.append({**identity, "task_id": f"cninfo-task-{_digest(identity)[:24]}"})
    identity = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "symbols": symbols,
        "tasks": tasks,
        "requested_symbols": normalized_requested_symbols,
        "usage_profile": CNINFO_PERSONAL_LICENSE_TIER,
        "attribution": CNINFO_PERSONAL_ATTRIBUTION,
    }
    return {
        "artifact_type": "cninfo_personal_historical_acquisition_plan",
        "schema_version": CNINFO_PERSONAL_PLAN_VERSION,
        "plan_id": f"cninfo-personal-plan-{_digest(identity)[:24]}",
        "generated_at": datetime.now(UTC).isoformat(),
        "database_source": str(resolved_path),
        "database_open_mode": "read_only",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "account_profile": ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        "historical_current_profile_fields_used": False,
        "pit_risk_status_verified": False,
        "symbol_inclusion_rule": (
            "explicit_requested_symbols_intersected_with_main_board_code_and_at_least_one_"
            "historical_unadjusted_close_in_0_to_200_cny"
            if normalized_requested_symbols
            else "main_board_code_and_at_least_one_historical_unadjusted_close_in_0_to_200_cny"
        ),
        "requested_symbols": normalized_requested_symbols,
        "symbol_count": len(symbols),
        "task_count": len(tasks),
        "symbols": symbols,
        "tasks": tasks,
        "usage_contract": {
            "use": "personal_internal_research_only",
            "authorized_by_user": True,
            "attribution": CNINFO_PERSONAL_ATTRIBUTION,
            "redistribution": "forbidden",
            "announcement_body_retained": False,
            "license_tier": CNINFO_PERSONAL_LICENSE_TIER,
        },
        "storage_contract": {
            "target_bytes": NEWS_STORAGE_TARGET_BYTES,
            "hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
        },
        "v3_signal_changed": False,
    }


def execute_cninfo_personal_acquisition(
    plan: dict[str, Any],
    *,
    artifact_root: str | Path,
    max_tasks_this_run: int = 25,
    min_request_interval_seconds: float = CNINFO_PERSONAL_DEFAULT_REQUEST_INTERVAL_SECONDS,
    fetcher: Any = None,
    materializer: Any = None,
    sleeper: Any = time.sleep,
) -> dict[str, Any]:
    if plan.get("schema_version") != CNINFO_PERSONAL_PLAN_VERSION:
        raise ValueError("unsupported CNINFO personal acquisition plan")
    usage = plan.get("usage_contract") or {}
    if usage.get("authorized_by_user") is not True or usage.get("redistribution") != "forbidden":
        raise ValueError("plan must be explicitly authorized for personal use with redistribution forbidden")
    if usage.get("attribution") != CNINFO_PERSONAL_ATTRIBUTION:
        raise ValueError(f"plan attribution must be {CNINFO_PERSONAL_ATTRIBUTION}")
    if max_tasks_this_run < 1 or max_tasks_this_run > CNINFO_PERSONAL_MAX_TASKS_PER_RUN:
        raise ValueError(f"max_tasks_this_run must be between 1 and {CNINFO_PERSONAL_MAX_TASKS_PER_RUN}")
    if min_request_interval_seconds < 0 or min_request_interval_seconds > 60:
        raise ValueError("min_request_interval_seconds must be between 0 and 60")
    root = Path(artifact_root).expanduser().resolve()
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError("artifact_root cannot be a filesystem root or the home directory")
    root.mkdir(parents=True, exist_ok=True)
    storage_budget = ExternalContextStorageBudget.from_root(root, hard_cap_bytes=NEWS_STORAGE_HARD_CAP_BYTES)
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("plan tasks must be a non-empty list")
    client_fetcher = fetcher or fetch_cninfo_announcement_poc
    client_materializer = materializer or materialize_external_context_pilot
    plan_root = root / "acquisition" / str(plan["plan_id"])
    completed_before = 0
    processed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    network_fetch_count = 0
    network_fetch_attempt_count = 0
    transient_retry_count = 0
    network_request_count = 0
    last_request_started_at: float | None = None
    stock_map_cache: dict[str, Any] = {}

    def request_gate() -> None:
        nonlocal last_request_started_at, network_request_count
        current = time.monotonic()
        if last_request_started_at is not None:
            remaining = min_request_interval_seconds - (current - last_request_started_at)
            if remaining > 0:
                sleeper(remaining)
        last_request_started_at = time.monotonic()
        network_request_count += 1

    for task in tasks:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            raise ValueError("every acquisition task must have task_id")
        result_path = plan_root / "results" / f"{task_id}.json"
        input_path = plan_root / "inputs" / f"{task_id}.json.gz"
        if result_path.exists():
            completed_before += 1
            continue
        if len(processed) + len(failures) >= max_tasks_this_run:
            break
        try:
            if input_path.exists():
                pilot_input = _read_gzip_json(input_path)
                input_source = "checkpoint_resume"
            else:
                fetch_kwargs = {
                    "symbol": str(task["provider_symbol"]),
                    "start_date": str(task["start_date"]).replace("-", ""),
                    "end_date": str(task["end_date"]).replace("-", ""),
                }
                for fetch_attempt in range(1, CNINFO_PERSONAL_MAX_TRANSIENT_ATTEMPTS + 1):
                    if network_fetch_attempt_count and client_fetcher is not fetch_cninfo_announcement_poc:
                        sleeper(min_request_interval_seconds)
                    network_fetch_attempt_count += 1
                    try:
                        if client_fetcher is fetch_cninfo_announcement_poc:
                            sample = client_fetcher(
                                **fetch_kwargs,
                                request_gate=request_gate,
                                stock_map_cache=stock_map_cache,
                            )
                        else:
                            sample = client_fetcher(**fetch_kwargs)
                        break
                    except requests.RequestException:
                        if fetch_attempt == CNINFO_PERSONAL_MAX_TRANSIENT_ATTEMPTS:
                            raise
                        transient_retry_count += 1
                network_fetch_count += 1
                pilot_input = dict(sample["pilot_input"])
                pilot_input["license_tier"] = CNINFO_PERSONAL_LICENSE_TIER
                pilot_input["attribution"] = CNINFO_PERSONAL_ATTRIBUTION
                _write_immutable_gzip(input_path, pilot_input, storage_budget=storage_budget)
                input_source = "network_fetch"
            records = pilot_input.get("records") or []
            manifest_id = None
            manifest_path = None
            if records:
                materialized = client_materializer(
                    pilot_input,
                    artifact_root=root,
                    enforce_root_hard_cap_bytes=NEWS_STORAGE_HARD_CAP_BYTES,
                    storage_budget=storage_budget,
                )
                manifest_id = materialized["manifest"]["manifest_id"]
                manifest_path = materialized["manifest_path"]
            result = {
                "artifact_type": "cninfo_personal_acquisition_task_result",
                "schema_version": "cninfo_personal_acquisition_task_result.v1",
                "plan_id": plan["plan_id"],
                "task_id": task_id,
                "symbol": task["symbol"],
                "start_date": task["start_date"],
                "end_date": task["end_date"],
                "input_source": input_source,
                "record_count": len(records),
                "input_digest": _digest(pilot_input),
                "manifest_id": manifest_id,
                "manifest_path": manifest_path,
                "attribution": CNINFO_PERSONAL_ATTRIBUTION,
                "redistribution": "forbidden",
                "completed_at": datetime.now(UTC).isoformat(),
            }
            _write_immutable(result_path, result, storage_budget=storage_budget)
            processed.append(result)
        except Exception as exc:
            failures.append(
                {
                    "task_id": task_id,
                    "symbol": task.get("symbol"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    completed_after = len(list((plan_root / "results").glob("*.json")))
    remaining = max(0, len(tasks) - completed_after)
    return {
        "artifact_type": "cninfo_personal_historical_acquisition_run",
        "schema_version": CNINFO_PERSONAL_RUN_VERSION,
        "plan_id": plan["plan_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "attribution": CNINFO_PERSONAL_ATTRIBUTION,
        "usage": "personal_internal_research_only",
        "redistribution": "forbidden",
        "task_count": len(tasks),
        "completed_before_count": completed_before,
        "processed_count": len(processed),
        "network_fetch_count": network_fetch_count,
        "network_fetch_attempt_count": network_fetch_attempt_count,
        "transient_retry_count": transient_retry_count,
        "network_request_count": network_request_count,
        "network_request_rate_scope": "every_http_get_and_post",
        "stock_map_network_fetch_count": 1 if network_request_count and stock_map_cache else 0,
        "checkpoint_resume_count": sum(row["input_source"] == "checkpoint_resume" for row in processed),
        "failure_count": len(failures),
        "failures": failures,
        "completed_after_count": completed_after,
        "remaining_task_count": remaining,
        "run_status": "complete" if remaining == 0 and not failures else "partial" if processed else "failed",
        "artifact_root": str(root),
        "artifact_root_bytes": storage_budget.used_bytes,
        "storage_target_bytes": NEWS_STORAGE_TARGET_BYTES,
        "storage_hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
        "storage_hard_cap_respected": storage_budget.used_bytes <= NEWS_STORAGE_HARD_CAP_BYTES,
        "v3_signal_changed": False,
    }


def audit_cninfo_personal_curation(
    plan: dict[str, Any],
    *,
    artifact_root: str | Path,
) -> dict[str, Any]:
    if plan.get("schema_version") != CNINFO_PERSONAL_PLAN_VERSION:
        raise ValueError("unsupported CNINFO personal acquisition plan")
    root = Path(artifact_root).expanduser().resolve()
    plan_root = root / "acquisition" / str(plan["plan_id"])
    result_paths = sorted((plan_root / "results").glob("*.json"))
    expected_tasks_by_symbol = Counter(str(task["symbol"]) for task in plan.get("tasks") or [])
    completed_tasks_by_symbol: Counter[str] = Counter()
    input_rule_versions: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    excluded_event_versions: list[dict[str, str]] = []
    review_candidates: dict[str, list[dict[str, str]]] = {}
    retained_record_count = 0
    source_record_count = 0
    available_dates: list[str] = []
    cninfo_artifact_bytes = 0
    verified_manifest_count = 0
    for result_path in result_paths:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        task_id = str(result["task_id"])
        completed_tasks_by_symbol[str(result["symbol"])] += 1
        input_path = plan_root / "inputs" / f"{task_id}.json.gz"
        if not input_path.is_file():
            raise ValueError(f"completed CNINFO task is missing its frozen input: {task_id}")
        cninfo_artifact_bytes += result_path.stat().st_size + input_path.stat().st_size
        pilot_input = _read_gzip_json(input_path)
        for record in pilot_input.get("records") or []:
            source_record_count += 1
            normalized = record.get("normalized_payload") or {}
            input_rule_versions[str(normalized.get("materiality_rule_version") or "unknown")] += 1
            raw = record.get("raw_payload") or {}
            titles = raw.get("announcement_titles") or [raw.get("announcement_title")]
            retained_categories = {
                category
                for title in titles
                if (category := classify_cninfo_materiality_title(str(title or ""))) is not None
            }
            if retained_categories:
                retained_record_count += 1
                category_counts.update(retained_categories)
                available_dates.append(str(record["available_from"])[:10])
                retained_title = next(
                    str(title)
                    for title in titles
                    if classify_cninfo_materiality_title(str(title or "")) is not None
                )
                review_category = sorted(retained_categories)[0]
                review_candidates.setdefault(review_category, []).append(
                    {
                        "normalized_event_id": str(record["normalized_event_id"]),
                        "revision_id": str(record["revision_id"]),
                        "symbol": str(normalized.get("sec_code") or result["symbol"]),
                        "available_date": str(record["available_from"])[:10],
                        "category": review_category,
                        "headline": retained_title,
                    }
                )
            else:
                excluded_event_versions.append(
                    {
                        "normalized_event_id": str(record["normalized_event_id"]),
                        "revision_id": str(record["revision_id"]),
                        "reason": "excluded_by_active_cninfo_title_materiality_policy",
                    }
                )
        manifest_path_value = result.get("manifest_path")
        if manifest_path_value:
            manifest_path = Path(str(manifest_path_value)).resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cninfo_artifact_bytes += manifest_path.stat().st_size
            cninfo_artifact_bytes += sum(int(row["byte_size"]) for row in manifest.get("artifact_files") or [])
            verified_manifest_count += 1
    full_window_symbols = sorted(
        symbol
        for symbol, expected_count in expected_tasks_by_symbol.items()
        if completed_tasks_by_symbol[symbol] == expected_count
    )
    partial_symbols = sorted(
        symbol
        for symbol, completed_count in completed_tasks_by_symbol.items()
        if completed_count < expected_tasks_by_symbol[symbol]
    )
    completed_task_count = len(result_paths)
    total_task_count = int(plan["task_count"])
    current_root_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    fixed_non_cninfo_bytes = max(0, current_root_bytes - cninfo_artifact_bytes)
    projected_cninfo_bytes = (
        math.ceil(cninfo_artifact_bytes / completed_task_count * total_task_count)
        if completed_task_count
        else 0
    )
    projected_total_bytes = fixed_non_cninfo_bytes + projected_cninfo_bytes
    excluded_event_versions.sort(key=lambda row: (row["normalized_event_id"], row["revision_id"]))
    review_seed = "cninfo-v3-manual-review-2026-08-06"
    review_queues = {
        category: sorted(
            rows,
            key=lambda row: hashlib.sha256(
                f"{review_seed}:{row['normalized_event_id']}:{row['revision_id']}".encode()
            ).hexdigest(),
        )
        for category, rows in review_candidates.items()
    }
    manual_review_sample: list[dict[str, str]] = []
    while len(manual_review_sample) < min(200, retained_record_count):
        added = False
        for category in sorted(review_queues):
            if review_queues[category]:
                manual_review_sample.append(review_queues[category].pop(0))
                added = True
                if len(manual_review_sample) >= min(200, retained_record_count):
                    break
        if not added:
            break
    return {
        "artifact_type": "cninfo_personal_curation_audit",
        "schema_version": "cninfo_personal_curation_audit.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "plan_id": plan["plan_id"],
        "active_relevance_policy_version": CNINFO_RELEVANCE_RULE_VERSION,
        "completed_task_count": completed_task_count,
        "total_task_count": total_task_count,
        "task_coverage_ratio": completed_task_count / total_task_count,
        "completed_symbol_count": len(completed_tasks_by_symbol),
        "full_window_symbol_count": len(full_window_symbols),
        "partial_symbol_count": len(partial_symbols),
        "full_window_symbols": full_window_symbols,
        "partial_symbols": partial_symbols,
        "source_record_count": source_record_count,
        "curated_record_count": retained_record_count,
        "curation_exclusion_count": len(excluded_event_versions),
        "curation_exclusion_ratio": (
            len(excluded_event_versions) / source_record_count if source_record_count else 0.0
        ),
        "input_rule_version_counts": dict(sorted(input_rule_versions.items())),
        "curated_category_counts": dict(sorted(category_counts.items())),
        "curated_available_date_min": min(available_dates) if available_dates else None,
        "curated_available_date_max": max(available_dates) if available_dates else None,
        "excluded_event_versions": excluded_event_versions,
        "excluded_event_versions_sha256": _digest(excluded_event_versions),
        "manual_review_sample": {
            "sampling_method": "deterministic_category_round_robin_then_seeded_hash_order",
            "seed": review_seed,
            "sample_count": len(manual_review_sample),
            "rows": manual_review_sample,
            "review_status": "unreviewed",
        },
        "manifest_count": verified_manifest_count,
        "storage_observation": {
            "current_root_bytes": current_root_bytes,
            "observed_cninfo_bytes": cninfo_artifact_bytes,
            "fixed_non_cninfo_bytes": fixed_non_cninfo_bytes,
            "projected_cninfo_full_plan_bytes_linear": projected_cninfo_bytes,
            "projected_total_full_plan_bytes_linear": projected_total_bytes,
            "target_bytes": NEWS_STORAGE_TARGET_BYTES,
            "hard_cap_bytes": NEWS_STORAGE_HARD_CAP_BYTES,
            "linear_projection_below_hard_cap": projected_total_bytes <= NEWS_STORAGE_HARD_CAP_BYTES,
            "projection_authority": "preflight_only_incremental_hard_cap_remains_authoritative",
        },
        "replay_filter_contract": {
            "rule": "exclude exact normalized_event_id plus revision_id pairs listed in excluded_event_versions",
            "default_for_unlisted_completed_records": "include",
            "future_records_must_use_policy_version": CNINFO_RELEVANCE_RULE_VERSION,
        },
        "v3_signal_changed": False,
        "claim_ceiling": "curation_and_capacity_preflight_only",
    }


def run_gdelt_multiday_relevance_canary(
    *,
    start_date: str,
    end_date: str,
    probe: Any = None,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    day_count = (end - start).days + 1
    if day_count > 31:
        raise ValueError("GDELT multi-day canary cannot exceed 31 calendar days")
    client_probe = probe or probe_gdelt_daily_public_discovery
    daily: list[dict[str, Any]] = []
    records_by_event: dict[str, dict[str, Any]] = {}
    daily_topic_counts: Counter[str] = Counter()
    cursor = start
    while cursor <= end:
        sample = client_probe(archive_date=cursor.strftime("%Y%m%d"))
        daily.append(
            {
                "archive_date": sample["archive_date"],
                "archive_bytes_read_in_memory": sample["archive_bytes_read_in_memory"],
                "row_count": sample["row_count"],
                "relevant_row_count_before_url_dedup": sample["relevant_row_count_before_url_dedup"],
                "unique_relevant_url_count": sample["unique_relevant_url_count"],
                "selected_record_count": sample["selected_record_count"],
                "selected_topic_counts": sample["selected_topic_counts"],
                "relevance_quality_exclusion_counts": sample.get("relevance_quality_exclusion_counts", {}),
                "relevance_rule_version": sample.get("relevance_rule_version"),
                "archive_sha256": sample["archive_sha256"],
                "sample_digest": sample["sample_digest"],
            }
        )
        for record in sample["pilot_input"]["records"]:
            event_id = str(record["normalized_event_id"])
            records_by_event.setdefault(event_id, record)
            daily_topic_counts.update(record["normalized_payload"]["topic_tags"])
        cursor += timedelta(days=1)
    records = list(records_by_event.values())
    deduplicated_topic_counts: Counter[str] = Counter()
    for record in records:
        deduplicated_topic_counts.update(record["normalized_payload"]["topic_tags"])
    retrieved_at = max((record["first_seen_at"] for record in records), default=datetime.now(UTC).isoformat())
    pilot_input = {
        "schema_version": "external_context_pilot_input.v1",
        "dataset_id": f"gdelt-multiday-relevance-canary-{start}-{end}",
        "provider_id": "gdelt_daily_public_discovery",
        "content_class": "news_summary",
        "source_endpoint": "https://storage.googleapis.com/data.gdeltproject.org/events/",
        "license_tier": "gdelt_unrestricted_use_with_attribution_summary_only",
        "attribution": "GDELT Project; personal analysis by hernando_zhao",
        "retrieved_at": retrieved_at,
        "records": records,
    }
    return {
        "artifact_type": "gdelt_multiday_relevance_canary",
        "schema_version": GDELT_MULTIDAY_CANARY_VERSION,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "day_count": day_count,
        "days_completed": len(daily),
        "archive_bytes_read_in_memory_total": sum(row["archive_bytes_read_in_memory"] for row in daily),
        "rows_scanned_total": sum(row["row_count"] for row in daily),
        "unique_relevant_url_daily_sum": sum(row["unique_relevant_url_count"] for row in daily),
        "selected_record_daily_sum": sum(row["selected_record_count"] for row in daily),
        "deduplicated_record_count": len(records),
        "selected_topic_daily_counts": dict(sorted(daily_topic_counts.items())),
        "selected_topic_counts": dict(sorted(deduplicated_topic_counts.items())),
        "daily": daily,
        "pilot_input": pilot_input,
        "sample_digest": _digest(pilot_input),
        "archive_persisted": False,
        "article_body_downloaded": False,
        "attribution": "GDELT Project; personal analysis by hernando_zhao",
        "v3_signal_changed": False,
        "claim_ceiling": "multiday_relevance_canary_no_external_alpha_validation",
    }
