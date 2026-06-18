from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.shortpick_v2_h10_paper_governance import H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS
from ashare_evidence.shortpick_v2_paper_ledger import (
    build_shortpick_v2_paper_ledger_artifact,
    refresh_shortpick_v2_paper_ledger_artifact,
)
from ashare_evidence.shortpick_v2_read_model import build_shortpick_v2_paper_tracking_read_model
from tests.test_shortpick_v2_read_model_api import (
    _seed_v2_paper_display_market_fixture,
    _write_h10_paper_governance_artifact,
    _write_v2_artifacts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
H10_GOVERNANCE_GENERATED_DATE = "2026-06-15"
H10_TRUE_FORWARD_MIN_SIGNAL_DATE = "2026-06-16"


def test_shortpick_v2_paper_ledger_writer_emits_post_governance_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, ledger_path = _write_v2_artifacts(tmp_path, monkeypatch)
    governance_path = _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-ledger.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url, end_date=date(2026, 6, 18))

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_ledger_artifact(
            session,
            rule_selection_artifact_path=selection_path,
            paper_governance_artifact_path=governance_path,
            generated_at=datetime(2026, 6, 18, 9, 0, tzinfo=UTC),
            target_date=date(2026, 6, 18),
        )

    assert payload["status"] == "active"
    assert payload["summary"]["record_count"] > 0
    assert payload["summary"]["record_count"] == len(payload["records"])
    assert payload["source_selection_artifact"]["selected_config_ids"] == list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    signal_dates = {record["signal_date"] for record in payload["records"]}
    assert min(signal_dates) > H10_GOVERNANCE_GENERATED_DATE
    assert min(signal_dates) >= H10_TRUE_FORWARD_MIN_SIGNAL_DATE
    assert max(signal_dates) == "2026-06-18"
    assert all(record["signal_date"] >= "2026-05-08" for record in payload["records"])
    assert all(record["evidence_basis"] == "true_forward_tracking" for record in payload["records"])
    assert {record["config_id"] for record in payload["records"]} == set(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    assert all(record["decision_action"] in {"buy_primary", "buy_fallback", "skip"} for record in payload["records"])
    assert not any(record["decision_action"].startswith(("delay", "later", "retry")) for record in payload["records"])

    with session_scope(database_url) as session:
        written_payload, path = refresh_shortpick_v2_paper_ledger_artifact(
            session,
            output_path=ledger_path,
            rule_selection_artifact_path=selection_path,
            paper_governance_artifact_path=governance_path,
            generated_at=datetime(2026, 6, 18, 9, 0, tzinfo=UTC),
            target_date=date(2026, 6, 18),
        )
        read_model = build_shortpick_v2_paper_tracking_read_model(
            include_records=True,
            session=session,
            rule_selection_artifact_path=selection_path,
            ledger_artifact_path=path,
            paper_governance_artifact_path=governance_path,
        )

    assert path == ledger_path
    assert json.loads(path.read_text(encoding="utf-8"))["ledger_id"] == written_payload["ledger_id"]
    assert read_model["status"] == "active"
    assert read_model["summary"]["record_count"] == written_payload["summary"]["record_count"]
    assert read_model["paper_display"]["coverage"]["true_forward_record_count"] == written_payload["summary"][
        "record_count"
    ]


def test_shortpick_v2_paper_ledger_requires_h10_governance_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, _ledger_path = _write_v2_artifacts(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-ledger-missing-governance.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url, end_date=date(2026, 6, 18))

    with session_scope(database_url) as session:
        with pytest.raises(ValueError, match="requires H10 paper governance artifact"):
            build_shortpick_v2_paper_ledger_artifact(
                session,
                rule_selection_artifact_path=selection_path,
                paper_governance_artifact_path=tmp_path / "missing-h10-paper-governance.json",
                generated_at=datetime(2026, 6, 18, 9, 0, tzinfo=UTC),
                target_date=date(2026, 6, 18),
            )


def test_shortpick_v2_paper_ledger_does_not_write_records_on_governance_date(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, _ledger_path = _write_v2_artifacts(tmp_path, monkeypatch)
    governance_path = _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-ledger-boundary.db"
    database_url = f"sqlite:///{database_path}"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url, end_date=date(2026, 6, 18))

    with session_scope(database_url) as session:
        payload = build_shortpick_v2_paper_ledger_artifact(
            session,
            rule_selection_artifact_path=selection_path,
            paper_governance_artifact_path=governance_path,
            generated_at=datetime(2026, 6, 18, 9, 0, tzinfo=UTC),
            target_date=date.fromisoformat(H10_GOVERNANCE_GENERATED_DATE),
        )

    assert payload["status"] == "contract_ready"
    assert payload["records"] == []
    assert payload["summary"]["record_count"] == 0


def test_shortpick_v2_paper_ledger_cli_writes_runtime_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, selection_path, _missing_ledger_path = _write_v2_artifacts(tmp_path, monkeypatch)
    governance_path = _write_h10_paper_governance_artifact(tmp_path, monkeypatch)
    database_path = tmp_path / "paper-ledger-cli.db"
    database_url = f"sqlite:///{database_path}"
    output_path = tmp_path / "shortpick-v2-paper-tracking-ledger.json"
    init_database(database_url)
    _seed_v2_paper_display_market_fixture(database_url, end_date=date(2026, 6, 18))

    result = subprocess.run(
        [
            "python3",
            "-m",
            "ashare_evidence.cli",
            "shortpick-v2-paper-ledger-refresh",
            "--database-url",
            database_url,
            "--rule-selection-artifact",
            str(selection_path),
            "--paper-governance-artifact",
            str(governance_path),
            "--target-date",
            "2026-06-18",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )

    cli_payload = json.loads(result.stdout)
    ledger = json.loads(output_path.read_text(encoding="utf-8"))
    assert cli_payload["status"] == "ok"
    assert cli_payload["summary"]["record_count"] == ledger["summary"]["record_count"]
    assert ledger["artifact_family"] == "shortpick_v2_paper_tracking_ledger"
    assert ledger["summary"]["record_count"] > 0
