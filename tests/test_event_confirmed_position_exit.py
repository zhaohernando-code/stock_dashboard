from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ashare_evidence.event_confirmed_position_exit import (
    OfficialEvent,
    _matched_events,
    expanding_position_predictions,
    load_curated_official_events,
)


def test_load_curated_official_events_applies_exact_revision_exclusion(tmp_path: Path) -> None:
    root = tmp_path / "external"
    records = root / "pit" / "records"
    records.mkdir(parents=True)
    retained = _record("event-1", "revision-1", "600000", "2026-01-02T23:59:59.999999+08:00")
    excluded = _record("event-2", "revision-2", "000001", "2026-01-03T23:59:59.999999+08:00")
    (records / "a.json").write_text(json.dumps(retained), encoding="utf-8")
    (records / "b.json").write_text(json.dumps(excluded), encoding="utf-8")
    curation = tmp_path / "curation.json"
    curation.write_text(
        json.dumps(
            {
                "active_relevance_policy_version": "v-test",
                "excluded_event_versions_sha256": "digest",
                "excluded_event_versions": [
                    {"normalized_event_id": "event-2", "revision_id": "revision-2"}
                ],
            }
        ),
        encoding="utf-8",
    )

    events, audit = load_curated_official_events(external_root=root, curation_path=curation)

    assert list(events) == ["600000.SH"]
    assert events["600000.SH"][0].category == "material_operations"
    assert audit["curation_excluded_records"] == 1
    assert audit["retained_event_count"] == 1


def test_matched_events_excludes_same_day_end_of_day_record_until_next_decision() -> None:
    event = OfficialEvent(
        symbol="600000.SH",
        available_from=datetime.fromisoformat("2026-01-02T23:59:59.999999+08:00"),
        category="material_operations",
        normalized_event_id="event-1",
        revision_id="revision-1",
    )

    assert _matched_events([event], decision_day=date(2026, 1, 2), lookback_days=20) == []
    assert _matched_events([event], decision_day=date(2026, 1, 3), lookback_days=20) == [event]


def test_expanding_predictions_require_strictly_prior_label_availability() -> None:
    observations = [
        _observation("p1", "2026-01-02", "2026-01-02", 0.02, [0.0], [0.0, 1.0]),
        _observation("p2", "2026-01-03", "2026-01-02", 0.01, [1.0], [1.0, 0.0]),
    ]

    predictions, audit = expanding_position_predictions(
        observations,
        minimum_training_labels=1,
        minimum_prior_predictions=0,
        l2_penalty=1.0,
    )

    assert predictions[("p1", "2026-01-02")] is None
    assert predictions[("p2", "2026-01-03")] is not None
    assert audit["future_label_violations"] == 0


def _record(event_id: str, revision_id: str, sec_code: str, available_from: str) -> dict[str, object]:
    return {
        "normalized_event_id": event_id,
        "knowledge_version": revision_id,
        "available_from": available_from,
        "feature_value": {
            "sec_code": sec_code,
            "materiality_category": "material_operations",
        },
    }


def _observation(
    position_key: str,
    decision_day: str,
    label_available_day: str,
    target: float,
    core: list[float],
    full: list[float],
) -> dict[str, object]:
    return {
        "position_key": position_key,
        "decision_day": decision_day,
        "label_available_day": label_available_day,
        "early_exit_advantage": target,
        "core_features": core,
        "full_features": full,
    }
