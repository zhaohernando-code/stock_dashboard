from __future__ import annotations

from pathlib import Path

import pytest

from ashare_evidence.rolling_account_execution_snapshot import (
    build_rolling_account_execution_snapshot,
    load_rolling_account_execution_snapshot,
    stable_digest,
    write_rolling_account_execution_snapshot,
)


def _snapshot() -> dict:
    return build_rolling_account_execution_snapshot(
        candidate_run={
            "artifact_id": "candidate-run-unit",
            "trial_diagnostics": [
                {
                    "trial_id": "trial-unit",
                    "selected_top_k_picks_by_date": [{"as_of_date": "2026-01-02", "symbol": "600001.SH"}],
                }
            ],
        },
        trial_id="trial-unit",
        candidate_inventory_rows=[{"as_of_date": "2026-01-02", "symbol": "600002.SH", "rank": 4}],
        market_bars_by_symbol={"600001.SH": [{"day": "2026-01-05", "close": 10.0}]},
        baseline_config={"config_id": "baseline"},
        account_profile={"initial_cash_cny": 200_000.0},
        baseline_result={
            "config_id": "baseline",
            "summary": {"total_return": 0.1},
            "reason_counts": {},
            "monthly_returns": [],
            "order_ledger": [{"action": "buy", "symbol": "600001.SH"}],
            "nav_rows": [{"day": "2026-01-05", "nav_cny": 200_000.0}],
        },
        source_lineage={"source": "unit"},
    )


def test_execution_snapshot_round_trips_deterministically(tmp_path: Path) -> None:
    payload = _snapshot()
    first = tmp_path / "snapshot-first.json.gz"
    second = tmp_path / "snapshot-second.json.gz"

    write_rolling_account_execution_snapshot(first, payload)
    write_rolling_account_execution_snapshot(second, payload)

    assert first.read_bytes() == second.read_bytes()
    assert load_rolling_account_execution_snapshot(first) == payload
    assert payload["input_counts"]["market_bar_row_count"] == 1
    assert payload["output_counts"]["order_ledger_row_count"] == 1


def test_execution_snapshot_rejects_tampered_content(tmp_path: Path) -> None:
    payload = _snapshot()
    payload["inputs"]["baseline_config"]["config_id"] = "tampered"
    path = tmp_path / "snapshot.json"
    write_rolling_account_execution_snapshot(path, payload)

    with pytest.raises(ValueError, match="input digest mismatch"):
        load_rolling_account_execution_snapshot(path)


def test_stable_digest_ignores_mapping_order() -> None:
    assert stable_digest({"a": 1, "b": 2}) == stable_digest({"b": 2, "a": 1})
