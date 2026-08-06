from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ashare_evidence.cli import NO_DB_COMMANDS, build_parser
from ashare_evidence.external_context_global_market_import import (
    build_global_market_pilot_from_vendor_export,
)
from ashare_evidence.external_context_replay import (
    materialize_external_context_pilot,
    replay_external_context_offline,
)


def _envelope() -> dict:
    return {
        "schema_version": "external_context_global_market_vendor_export.v1",
        "provider_id": "wind_global_market",
        "dataset_id": "wind-global-market-sample",
        "source_endpoint": "wind-client-api-export",
        "license_tier": "trial_with_local_frozen_replay_approved",
        "attribution": "hernando_zhao",
        "retrieved_at": "2026-08-06T16:00:00+00:00",
        "local_frozen_replay_approved": True,
        "rights_evidence_ref": "contract://wind/trial/frozen-replay",
        "revision_semantics_evidence_ref": "contract://wind/fields/revision-id",
        "records": [
            {
                "instrument_id": "SPX",
                "provider_item_id": "wind:SPX:2025-01-24",
                "revision_id": "wind-revision-1",
                "vendor_revision_is_provider_supplied": True,
                "observation_at": "2025-01-24T16:00:00-05:00",
                "published_at": "2025-01-24T16:15:00-05:00",
                "available_at": "2025-01-24T16:20:00-05:00",
                "first_seen_at": "2026-08-06T15:59:00+00:00",
                "provider_updated_at": None,
                "open": 6100.0,
                "high": 6120.0,
                "low": 6080.0,
                "close": 6110.0,
                "volume": 1000000.0,
                "currency": "USD",
                "calendar": "XNYS",
                "adjustment_status": "unadjusted_index_level",
            }
        ],
    }


def test_global_market_import_requires_provider_revision_and_replay_rights() -> None:
    missing_revision = deepcopy(_envelope())
    missing_revision["records"][0]["vendor_revision_is_provider_supplied"] = False
    with pytest.raises(ValueError, match="provider-supplied revision"):
        build_global_market_pilot_from_vendor_export(missing_revision)

    missing_rights = deepcopy(_envelope())
    missing_rights["local_frozen_replay_approved"] = False
    with pytest.raises(ValueError, match="local_frozen_replay_approved"):
        build_global_market_pilot_from_vendor_export(missing_rights)


def test_global_market_import_rejects_future_availability_and_unknown_instrument() -> None:
    future = deepcopy(_envelope())
    future["records"][0]["available_at"] = "2026-08-06T16:01:00+00:00"
    with pytest.raises(ValueError, match="observation_at <= published_at"):
        build_global_market_pilot_from_vendor_export(future)

    unknown = deepcopy(_envelope())
    unknown["records"][0]["instrument_id"] = "UNFROZEN"
    with pytest.raises(ValueError, match="outside the frozen basket"):
        build_global_market_pilot_from_vendor_export(unknown)


def test_global_market_import_materializes_and_replays_offline(tmp_path: Path) -> None:
    result = build_global_market_pilot_from_vendor_export(_envelope())

    assert result["audit"]["required_lineage_fields_complete"] is True
    assert result["audit"]["full713_coverage_claimed"] is False
    assert result["audit"]["frozen_basket_missing_instruments"] == [
        "HKTECH",
        "HSI",
        "IXIC",
        "SOX_OR_SEMICONDUCTOR_INDEX",
        "US10Y",
        "USD_CNH",
        "WTI",
    ]
    record = result["pilot_input"]["records"][0]
    assert record["revision_id"] == "wind-revision-1"
    assert record["normalized_payload"]["channel_scope"] == "global_state"

    materialized = materialize_external_context_pilot(result["pilot_input"], artifact_root=tmp_path)
    replay = replay_external_context_offline(
        materialized["manifest_path"],
        decision_cutoff="2025-01-25T09:25:00+08:00",
    )
    assert replay["selected_record_count"] == 1
    assert replay["hash_verification_status"] == "passed"
    assert replay["network_used"] is False


def test_cli_registers_global_market_import_as_no_database_command() -> None:
    args = build_parser().parse_args(
        [
            "research-external-context-global-market-import-validate",
            "--input-json",
            "/tmp/input.json",
            "--output-audit-json",
            "/tmp/audit.json",
            "--output-pilot-json",
            "/tmp/pilot.json",
        ]
    )

    assert args.command == "research-external-context-global-market-import-validate"
    assert args.command in NO_DB_COMMANDS
