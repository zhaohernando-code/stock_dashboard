from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from ashare_evidence.external_context_exact_core import build_exact_v3_core_snapshot


def _feature_row(signal_day: str, symbol: str, percentile: float) -> dict[str, object]:
    feature_values = {
        "cross_sectional": {
            "amount_10d_vs_20d_percentile": percentile,
            "amount_vs_20d_avg_percentile": percentile,
            "low_turnover_percentile": 1 - percentile,
            "low_volatility_percentile": 1 - percentile,
            "return_20d_percentile": percentile,
            "return_5d_percentile": percentile,
            "turnover_rate_percentile": percentile,
            "volatility_20d_percentile": percentile,
        },
        "liquidity": {"avg_amount_20d": 100_000_000.0, "turnover_rate": 0.01},
        "price_momentum": {"return_20d": 0.01, "return_5d": 0.01},
        "regime": {"benchmark_return_10d": 0.01, "benchmark_return_20d": 0.01, "benchmark_volatility_20d": 0.02},
        "reversal_overheat": {"return_1d": 0.0, "distance_from_20d_high": -0.01, "distance_from_40d_high": -0.01},
        "valuation_capacity": {"total_mv": 1_000_000.0, "circ_mv": 900_000.0},
        "volatility_risk": {"max_drawdown_20d": -0.01, "max_drawdown_40d": -0.02},
        "execution": {"limit_state": "normal", "suspension_or_stale_proxy": False},
        "crowding": {},
    }
    return {
        "as_of_date": signal_day,
        "symbol": symbol,
        "stock_name": symbol,
        "industry_code": None,
        "industry_name": "电子",
        "feature_version": "shortpick_model_pit_feature_matrix:v3",
        "feature_values": feature_values,
        "source_cutoff_at_or_before_as_of": True,
        "row_digest": f"digest-{symbol}",
        "universe_row_id": f"universe:{symbol}:{signal_day}",
    }


def test_exact_core_snapshot_scores_only_requested_candidates(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidates.json.gz"
    with gzip.open(candidate_path, "wt", encoding="utf-8") as handle:
        json.dump(
            {
                "artifact_id": "candidate-v1",
                "content_digest": "candidate-digest",
                "rows": [
                    {"signal_day": "2026-01-05", "symbol": "600001.SH"},
                    {"signal_day": "2026-01-05", "symbol": "600002.SH"},
                ],
            },
            handle,
        )
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "artifact_id": "matrix-v3",
                "feature_version": "shortpick_model_pit_feature_matrix:v3",
                "source_data_time_range": {"as_of_start": "2026-01-05", "as_of_end": "2026-01-05"},
                "rows": [
                    _feature_row("2026-01-05", "600001.SH", 0.8),
                    _feature_row("2026-01-05", "600002.SH", 0.4),
                    _feature_row("2026-01-05", "600003.SH", 0.9),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = build_exact_v3_core_snapshot(
        candidate_dataset_path=candidate_path,
        feature_matrix_paths=[matrix_path],
    )
    assert payload["resolved_core_score_count"] == 2
    assert payload["missing_core_score_count"] == 0
    assert payload["quality"]["exact_raw_core_score_ready"] is True
    assert {row["symbol"] for row in payload["rows"]} == {"600001.SH", "600002.SH"}
    assert all("core_score" in row and "core_feature_values" in row for row in payload["rows"])
    assert {row["candidate_pool_core_rank"] for row in payload["rows"]} == {1, 2}
    assert payload["v3_active_window_candidate_row_count"] == 2
    for row in payload["rows"]:
        digest_material = {key: value for key, value in row.items() if key != "row_digest"}
        rendered = json.dumps(
            digest_material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        assert row["row_digest"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()
