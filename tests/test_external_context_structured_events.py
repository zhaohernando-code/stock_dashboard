from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

from ashare_evidence.cli import NO_DB_COMMANDS, build_parser
from ashare_evidence.external_context_news_summary import NEWS_STORAGE_HARD_CAP_BYTES
from ashare_evidence.external_context_structured_events import (
    build_tushare_structured_event_plan,
    execute_tushare_structured_event_plan,
    normalize_tushare_structured_event_rows,
    verify_tushare_structured_event_replay,
    write_tushare_structured_event_plan,
)


def _forecast_row(symbol: str = "600183.SH") -> dict:
    return {
        "ts_code": symbol,
        "ann_date": "20260814",
        "end_date": "20260630",
        "type": "预增",
        "p_change_min": 40.0,
        "p_change_max": 60.0,
        "net_profit_min": 10000.0,
        "net_profit_max": 12000.0,
        "last_parent_net": 7000.0,
        "first_ann_date": "20260715",
        "summary": "归母净利润预计增长",
        "change_reason": "产品需求增长",
    }


def _response(rows: list[dict]) -> dict:
    fields = list(rows[0]) if rows else ["ts_code", "ann_date"]
    return {"code": 0, "msg": "", "data": {"fields": fields, "items": [[row.get(key) for key in fields] for row in rows]}}


def test_structured_event_plan_uses_quarter_bulk_and_monthly_repurchase_tasks() -> None:
    plan = build_tushare_structured_event_plan(start_date="2023-06-13", end_date="2026-08-14")

    apis = [task["api_name"] for task in plan["tasks"]]
    assert apis.count("forecast_vip") == 16
    assert apis.count("express_vip") == 16
    assert apis.count("repurchase") == 39
    assert plan["task_count"] == 71
    assert plan["temporal_contract"]["same_day_signal_use"] is False
    assert plan["storage_contract"]["hard_cap_bytes"] == NEWS_STORAGE_HARD_CAP_BYTES
    assert NEWS_STORAGE_HARD_CAP_BYTES < 2 * 1024**3
    assert plan["v3_signal_changed"] is False


def test_cli_registers_structured_event_plan_run_and_verify_commands() -> None:
    parser = build_parser()

    plan_args = parser.parse_args(
        [
            "research-external-context-tushare-structured-plan",
            "--start-date",
            "2023-06-13",
            "--end-date",
            "2026-08-14",
            "--output-json",
            "plan.json",
        ]
    )
    run_args = parser.parse_args(
        [
            "research-external-context-tushare-structured-run",
            "--plan-json",
            "plan.json",
            "--artifact-root",
            "artifacts",
        ]
    )
    verify_args = parser.parse_args(
        [
            "research-external-context-tushare-structured-verify",
            "--plan-json",
            "plan.json",
            "--artifact-root",
            "artifacts",
            "--decision-cutoff",
            "2026-08-15T00:00:00+08:00",
        ]
    )

    assert plan_args.command.endswith("structured-plan")
    assert run_args.command.endswith("structured-run")
    assert verify_args.command.endswith("structured-verify")
    assert plan_args.command in NO_DB_COMMANDS
    assert run_args.command not in NO_DB_COMMANDS
    assert verify_args.command in NO_DB_COMMANDS


def test_equivalent_regenerated_plan_reuses_immutable_file(tmp_path: Path) -> None:
    first = build_tushare_structured_event_plan(start_date="2023-06-13", end_date="2026-08-14")
    second = {**first, "generated_at": "2099-01-01T00:00:00+00:00"}
    path = write_tushare_structured_event_plan(tmp_path / "plan.json", first)

    write_tushare_structured_event_plan(path, second)

    assert path.read_text(encoding="utf-8").find(first["generated_at"]) >= 0
    assert path.read_text(encoding="utf-8").find(second["generated_at"]) == -1


def test_normalization_is_conservative_pit_and_excludes_unavailable_boards() -> None:
    records, excluded = normalize_tushare_structured_event_rows(
        "forecast_vip",
        [_forecast_row(), _forecast_row("688981.SH")],
        start=date(2026, 8, 1),
        end=date(2026, 8, 15),
        retrieved_at=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert len(records) == 1
    assert excluded["account_board"] == 1
    record = records[0]
    assert record["provider_published_at"] == "2026-08-14T00:00:00+08:00"
    assert record["available_from"] == "2026-08-14T23:59:59.999999+08:00"
    assert record["normalized_payload"]["fact"]["profit_change_mid_pct"] == 50.0
    assert record["normalized_payload"]["same_day_signal_use"] is False
    assert record["normalized_payload"]["provider_revision_id_available"] is False


def test_acquisition_checkpoints_and_replays_without_network(tmp_path: Path) -> None:
    plan = build_tushare_structured_event_plan(start_date="2026-08-14", end_date="2026-08-14")
    plan["tasks"] = [task for task in plan["tasks"] if task["api_name"] == "forecast_vip"][:1]
    plan["task_count"] = 1
    session = SimpleNamespace(
        scalar=lambda *_args, **_kwargs: SimpleNamespace(
            base_url="http://api.tushare.pro",
            access_token="secret-token",
        )
    )
    calls = []

    def fake_request(**kwargs):
        calls.append({key: value for key, value in kwargs.items() if key != "token"})
        return _response([_forecast_row()])

    first = execute_tushare_structured_event_plan(
        session,
        plan,
        artifact_root=tmp_path,
        request_fn=fake_request,
        sleeper=lambda _seconds: None,
    )
    repeated = execute_tushare_structured_event_plan(
        session,
        plan,
        artifact_root=tmp_path,
        request_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("resume attempted network")),
        sleeper=lambda _seconds: None,
    )
    replay = verify_tushare_structured_event_replay(
        plan,
        artifact_root=tmp_path,
        decision_cutoff="2026-08-15T00:00:00+08:00",
    )

    assert first["processed_tasks"] == 1
    assert first["plan_ready"] is True
    assert first["transport"] == "https"
    assert calls[0]["base_url"] == "https://api.tushare.pro"
    assert repeated["processed_tasks"] == 0
    assert repeated["skipped_completed_tasks"] == 1
    assert replay["network_used"] is False
    assert replay["hash_verification_status"] == "passed"
    assert replay["visible_record_count"] == 1


def test_acquisition_retries_only_empty_transport_responses(tmp_path: Path) -> None:
    plan = build_tushare_structured_event_plan(start_date="2026-08-14", end_date="2026-08-14")
    plan["tasks"] = [task for task in plan["tasks"] if task["api_name"] == "forecast_vip"][:1]
    plan["task_count"] = 1
    session = SimpleNamespace(
        scalar=lambda *_args, **_kwargs: SimpleNamespace(
            base_url="http://api.tushare.pro",
            access_token="secret-token",
        )
    )
    responses = iter([None, None, _response([_forecast_row()])])
    sleeps = []

    result = execute_tushare_structured_event_plan(
        session,
        plan,
        artifact_root=tmp_path,
        request_fn=lambda **_kwargs: next(responses),
        sleeper=sleeps.append,
    )

    assert result["plan_ready"] is True
    assert sleeps == [1.0, 2.0]


def test_acquisition_falls_back_to_numeric_fields_after_repeated_large_response_failure(tmp_path: Path) -> None:
    plan = build_tushare_structured_event_plan(start_date="2026-08-14", end_date="2026-08-14")
    plan["tasks"] = [task for task in plan["tasks"] if task["api_name"] == "forecast_vip"][:1]
    plan["task_count"] = 1
    session = SimpleNamespace(
        scalar=lambda *_args, **_kwargs: SimpleNamespace(
            base_url="https://api.tushare.pro",
            access_token="secret-token",
        )
    )
    requested_fields = []

    def fake_request(**kwargs):
        requested_fields.append(kwargs["fields"])
        return None if "change_reason" in kwargs["fields"] else _response([_forecast_row()])

    result = execute_tushare_structured_event_plan(
        session,
        plan,
        artifact_root=tmp_path,
        request_fn=fake_request,
        sleeper=lambda _seconds: None,
        max_transient_attempts=1,
    )

    assert result["plan_ready"] is True
    assert "change_reason" in requested_fields[0]
    assert "change_reason" not in requested_fields[1]
