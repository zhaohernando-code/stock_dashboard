from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from ashare_evidence.external_shadow_control import validate_external_shadow_signal_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETENTION_CONTRACT = PROJECT_ROOT / "docs/contracts/STRATEGY_RESEARCH_RETENTION_CONTRACT_2026-08-17.json"


def test_retained_research_assets_match_the_closeout_contract() -> None:
    contract = json.loads(RETENTION_CONTRACT.read_text(encoding="utf-8"))
    assets = {row["role"]: row for row in contract["retained_assets"]}

    dataset = assets["reusable_full_universe_hotspot_opportunity_candidates"]
    dataset_path = PROJECT_ROOT / dataset["path"]
    assert hashlib.sha256(dataset_path.read_bytes()).hexdigest() == dataset["sha256"]
    with gzip.open(dataset_path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["artifact_id"] == dataset["artifact_id"]
    assert payload["content_digest"] == dataset["content_digest"]
    assert payload["candidate_row_count"] == dataset["candidate_rows"]
    assert payload["historical_st_status_point_in_time"] is False

    signal_path = PROJECT_ROOT / assets["active_append_only_external_shadow_signal_registry"]["path"]
    signal_asset = assets["active_append_only_external_shadow_signal_registry"]
    assert signal_asset["materialization"] == "runtime_local_not_git_tracked"
    if signal_path.exists():
        signals = json.loads(signal_path.read_text(encoding="utf-8"))
        validation = validate_external_shadow_signal_registry(signals)
        assert validation["future_information_violation_count"] == 0


def test_retired_research_engines_do_not_return_to_runtime_source() -> None:
    retired = {
        "global_sector_state_account_ablation.py",
        "event_confirmed_position_extension.py",
        "external_reversal_rotation.py",
        "hotspot_secondary_start.py",
        "hotspot_recovery_dual_head.py",
        "all_universe_opportunity_head.py",
        "all_universe_hotspot_classifier.py",
    }
    source_names = {path.name for path in (PROJECT_ROOT / "src/ashare_evidence").glob("*.py")}
    assert retired.isdisjoint(source_names)
