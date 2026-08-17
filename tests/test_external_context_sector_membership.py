from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from ashare_evidence.external_context_sector_membership import (
    acquire_tushare_sector_membership_snapshot,
    build_sector_membership_snapshot,
    sector_memberships_as_of,
)


def _response(fields: list[str], items: list[list[object]]) -> dict[str, object]:
    return {"code": 0, "msg": "", "data": {"fields": fields, "items": items}}


def test_membership_snapshot_separates_effective_date_research_from_strict_pit() -> None:
    classifications = _response(
        ["index_code", "industry_name", "level", "industry_code", "is_pub", "parent_code", "src"],
        [[f"801{index:03d}.SI", f"行业{index}", "L1", str(index), "1", "", "SW2021"] for index in range(30)],
    )
    memberships = _response(
        ["l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name", "ts_code", "name", "in_date", "out_date", "is_new"],
        [
            [f"801{index:03d}.SI", f"行业{index}", "", "", "", "", f"60{index:04d}.SH", f"股票{index}", "20230101", None, "Y"]
            for index in range(30)
        ],
    )
    snapshot = build_sector_membership_snapshot(
        classification_response=classifications,
        membership_responses=[memberships],
        membership_requests=[{"is_new": "Y"}],
        retrieved_at=datetime(2026, 8, 17, tzinfo=UTC),
        source_endpoint="https://api.tushare.pro",
    )
    historical_cutoff = datetime(2025, 1, 2, 23, 59, tzinfo=UTC)
    assert sector_memberships_as_of(snapshot, decision_cutoff=historical_cutoff, mode="strict_pit") == {}
    assert len(
        sector_memberships_as_of(snapshot, decision_cutoff=historical_cutoff, mode="effective_date_research")
    ) == 30
    assert snapshot["readiness"]["strict_historical_pit_ready"] is False
    assert snapshot["raw"]["raw_payload_retained"] is True
    assert snapshot["raw"]["credential_or_token_retained"] is False


def test_membership_acquisition_queries_current_and_historical_per_l1() -> None:
    session = SimpleNamespace(
        scalar=lambda _query: SimpleNamespace(
            access_token="token", base_url="https://api.tushare.pro", enabled=True
        )
    )
    classification_fields = [
        "index_code", "industry_name", "level", "industry_code", "is_pub", "parent_code", "src"
    ]
    membership_fields = [
        "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name", "ts_code", "name",
        "in_date", "out_date", "is_new",
    ]
    calls: list[tuple[str, dict[str, str]]] = []

    def request_fn(**kwargs):  # type: ignore[no-untyped-def]
        calls.append((kwargs["api_name"], kwargs["params"]))
        if kwargs["api_name"] == "index_classify":
            return _response(
                classification_fields,
                [[f"801{index:03d}.SI", f"行业{index}", "L1", str(index), "1", "", "SW2021"] for index in range(30)],
            )
        code = kwargs["params"]["l1_code"]
        flag = kwargs["params"]["is_new"]
        index = int(code[3:6])
        if flag == "N":
            return _response(membership_fields, [])
        return _response(
            membership_fields,
            [[code, f"行业{index}", "", "", "", "", f"60{index:04d}.SH", f"股票{index}", "20230101", None, flag]],
        )

    snapshot = acquire_tushare_sector_membership_snapshot(
        session,  # type: ignore[arg-type]
        retrieved_at=datetime(2026, 8, 17, tzinfo=UTC),
        request_fn=request_fn,
        sleeper=lambda _seconds: None,
        min_request_interval_seconds=0,
    )
    member_calls = [params for api, params in calls if api == "index_member_all"]
    assert len(member_calls) == 60
    assert {params["is_new"] for params in member_calls} == {"Y", "N"}
    assert snapshot["quality"]["normalized_row_count"] == 30
